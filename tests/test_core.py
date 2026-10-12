import hashlib, hmac, json, os
from alembic import command
from alembic.config import Config
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from app.config import Settings, get_settings
from app.db.database import configured_database_url, connection, dispose_engines, get_engine, normalize_database_url
from app.main import app
from app.services.facility_service import haversine_km
from app.services.safety_router import requires_safety_route, safety_response
from app.services.natlas_service import IntegrationNotConfigured
from app.services.conversation_service import process_text, process_webhook
from app.services.registration_service import get_user, sender_digest
from app.services.knowledge_service import answer_is_supported
from app.services.whatsapp_service import _is_allowed_media_url

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    configured_test_url=os.environ.get('NURTELORA_TEST_DATABASE_URL')
    test_url=configured_test_url or f'sqlite:///{tmp_path / "test.sqlite"}'
    monkeypatch.setenv('APP_ENV','test')
    monkeypatch.setenv('DATABASE_URL',test_url)
    monkeypatch.setenv('PHONE_HASH_SECRET','ci-only-synthetic-secret-for-tests')
    monkeypatch.setenv('NATLAS_LANGUAGES','en')
    get_settings.cache_clear()
    if test_url.startswith('sqlite:'):
        command.upgrade(Config('alembic.ini'),'head')
    with connection() as c:
        for table in ('processed_messages','appointments','consent_records','interaction_events','workflow_states','users','facilities','knowledge_entries'):
            c.execute(f'DELETE FROM {table}')
    yield
    get_settings.cache_clear()
    dispose_engines()

def test_health_is_explicit_about_approval():
    with TestClient(app) as client:
        result=client.get('/health').json()
        assert result['clinical_approval']=='not_approved'

def test_webhook_challenge_requires_matching_token(monkeypatch):
    monkeypatch.setenv('WHATSAPP_VERIFY_TOKEN','verify-me'); get_settings.cache_clear()
    with TestClient(app) as client:
        good=client.get('/webhooks/whatsapp',params={'hub.mode':'subscribe','hub.verify_token':'verify-me','hub.challenge':'abc'})
        bad=client.get('/webhooks/whatsapp',params={'hub.mode':'subscribe','hub.verify_token':'wrong','hub.challenge':'abc'})
        assert good.status_code==200 and good.text=='abc'
        assert bad.status_code==403

def test_webhook_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv('WHATSAPP_APP_SECRET','secret'); get_settings.cache_clear()
    with TestClient(app) as client:
        response=client.post('/webhooks/whatsapp',content=b'{"object":"whatsapp_business_account"}',headers={'Content-Type':'application/json','X-Hub-Signature-256':'sha256=bad'})
        assert response.status_code==401

def test_safety_routes_generic_concern():
    assert requires_safety_route('I am bleeding')
    assert 'qualified healthcare professional' in safety_response('I am bleeding')

def test_facility_distance():
    assert haversine_km(0,0,0,1)==pytest.approx(111.2,rel=.01)

def test_grounding_guard_rejects_new_advice_and_numbers():
    source='Antenatal visits include routine checks.'
    assert not answer_is_supported('Take medicine daily.',source)
    assert not answer_is_supported('There are 8 visits.',source)

def test_unconfigured_natlas_fails_explicitly():
    service=__import__('app.services.natlas_service',fromlist=['NAtlasService']).NAtlasService(Settings())
    with pytest.raises(IntegrationNotConfigured): service._base()

def test_media_download_url_must_use_an_approved_meta_host():
    assert _is_allowed_media_url('https://lookaside.fbsbx.com/whatsapp/attachment')
    assert _is_allowed_media_url('https://scontent.example.fbcdn.net/media')
    assert not _is_allowed_media_url('https://lookaside.fbsbx.com.attacker.test/media')
    assert not _is_allowed_media_url('http://lookaside.fbsbx.com/media')
    assert not _is_allowed_media_url('https://user@lookaside.fbsbx.com/media')

def test_database_is_postgresql_in_ci():
    configured=os.environ.get('NURTELORA_TEST_DATABASE_URL','')
    if not configured.startswith(('postgresql://','postgres://','postgresql+psycopg://')):
        pytest.skip('PostgreSQL integration check runs in CI; local unit tests use isolated SQLite')
    assert get_engine().dialect.name=='postgresql'

def test_fresh_database_is_at_migration_head():
    with connection() as c:
        revision=c.execute("SELECT version_num FROM alembic_version").fetchone()['version_num']
    assert revision=='20261012_0001'

def test_postgres_url_normalization_preserves_ssl_options():
    normalized=normalize_database_url('postgres://synthetic:dummy-password@db.example.test/nurtelora?sslmode=require')
    assert normalized.startswith('postgresql+psycopg://')
    assert normalized.endswith('?sslmode=require')

def test_production_does_not_fall_back_to_sqlite(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('DATABASE_URL','sqlite:///./must-not-open.db')
    get_settings.cache_clear()
    with pytest.raises(RuntimeError,match='requires DATABASE_URL to point to PostgreSQL'):
        configured_database_url()
    get_settings.cache_clear()

def test_foreign_key_constraints_and_transaction_rollback():
    with pytest.raises(IntegrityError):
        with connection() as c:
            c.execute("INSERT INTO appointments(id,user_id,source,confirmation_status) VALUES(?,?,?,?)",
                      ('appointment-orphan','missing-user','user','user_entered'))
    with connection() as c:
        count=c.execute("SELECT count(*) AS n FROM appointments").fetchone()['n']
    assert count==0
    with pytest.raises(RuntimeError):
        with connection() as c:
            c.execute("INSERT INTO facilities(id,name,address,source) VALUES(?,?,?,?)",
                      ('rollback-facility','Synthetic clinic','Synthetic address','test fixture'))
            raise RuntimeError('synthetic rollback')
    with connection() as c:
        count=c.execute("SELECT count(*) AS n FROM facilities WHERE id=?",('rollback-facility',)).fetchone()['n']
    assert count==0

def test_valid_signature_is_accepted_without_messages(monkeypatch):
    secret='app-secret'; body=json.dumps({'object':'whatsapp_business_account','entry':[]}).encode()
    monkeypatch.setenv('WHATSAPP_APP_SECRET',secret); get_settings.cache_clear()
    sig='sha256='+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        response=client.post('/webhooks/whatsapp',content=body,headers={'Content-Type':'application/json','X-Hub-Signature-256':sig})
        assert response.status_code==200

@pytest.mark.asyncio
async def test_consent_and_appointment_entry_are_deterministic():
    sender='DEMO-SENDER'
    await process_text(sender,'m1','START')
    assert get_user(sender) is None
    await process_text(sender,'m2','YES')
    await process_text(sender,'m3','EN')
    await process_text(sender,'m4','SKIP')
    await process_text(sender,'m5','APPOINTMENT SAVE')
    await process_text(sender,'m6','2027-04-12')
    saved=await process_text(sender,'m7','YES')
    assert 'not confirmed by your clinic' in saved
    assert '2027-04-12' in await process_text(sender,'m8','APPOINTMENT')

@pytest.mark.asyncio
async def test_delete_confirmation_removes_profile_and_appointment():
    sender='DELETE-DEMO'
    await process_text(sender,'d1','START')
    await process_text(sender,'d2','YES')
    assert get_user(sender) is not None
    await process_text(sender,'d3','DELETE')
    with connection() as c:
        state=c.execute("SELECT pending_deletion_expires_at FROM workflow_states WHERE sender_hash=?",(sender_digest(sender),)).fetchone()
    assert state and state['pending_deletion_expires_at']
    result=await process_text(sender,'d4','DELETE CONFIRM')
    assert 'deleted' in result
    assert get_user(sender) is None
    with connection() as c:
        assert c.execute("SELECT count(*) AS n FROM workflow_states WHERE sender_hash=?",(sender_digest(sender),)).fetchone()['n']==0

@pytest.mark.asyncio
async def test_expired_deletion_confirmation_does_not_delete_profile():
    sender='EXPIRED-DELETE-DEMO'
    await process_text(sender,'e1','START')
    await process_text(sender,'e2','YES')
    await process_text(sender,'e3','DELETE')
    with connection() as c:
        c.execute("UPDATE workflow_states SET pending_deletion_expires_at=? WHERE sender_hash=?",('2000-01-01T00:00:00+00:00',sender_digest(sender)))
    reply=await process_text(sender,'e4','DELETE CONFIRM')
    assert 'Reply DELETE first' in reply
    assert get_user(sender) is not None

@pytest.mark.asyncio
async def test_pending_consent_is_persisted_and_claimed_once():
    sender='CONSENT-DEMO'
    await process_text(sender,'c1','START')
    with connection() as c:
        state=c.execute("SELECT pending_consent_expires_at FROM workflow_states WHERE sender_hash=?",(sender_digest(sender),)).fetchone()
    assert state and state['pending_consent_expires_at']
    consent_reply=await process_text(sender,'c2','YES')
    assert consent_reply.startswith('Thanks.')
    assert get_user(sender) is not None
    assert 'privacy notice first' in await process_text(sender,'c3','YES')

@pytest.mark.asyncio
async def test_stop_clears_workflow_and_blocks_protected_actions():
    sender='STOP-DEMO'
    await process_text(sender,'s1','START')
    await process_text(sender,'s2','YES')
    stopped=await process_text(sender,'s3','STOP')
    assert 'opted out' in stopped
    with connection() as c:
        assert c.execute("SELECT count(*) AS n FROM workflow_states WHERE sender_hash=?",(sender_digest(sender),)).fetchone()['n']==0
    result=await process_text(sender,'s4','APPOINTMENT SAVE')
    assert 'opted out' in result

@pytest.mark.asyncio
async def test_duplicate_webhook_event_is_processed_once(monkeypatch):
    sends=[]
    async def fake_send(self,recipient,text,reply_to_message_id=None):
        sends.append((recipient,text,reply_to_message_id))
        return 'synthetic-outbound-id'
    monkeypatch.setattr('app.services.whatsapp_service.WhatsAppService.send_text_message',fake_send)
    payload={'entry':[{'changes':[{'value':{'messages':[{'id':'synthetic-message-id','from':'SYNTHETIC-WA-SENDER','type':'text','text':{'body':'START'}}]}}]}]}
    assert await process_webhook(payload)==1
    assert await process_webhook(payload)==0
    assert len(sends)==1
    with connection() as c:
        count=c.execute("SELECT count(*) AS n FROM processed_messages WHERE message_id=?",('synthetic-message-id',)).fetchone()['n']
    assert count==1
