import hashlib, hmac, json
import pytest
from fastapi.testclient import TestClient
from app.config import Settings, get_settings
from app.db.database import init_db
from app.main import app
from app.services.facility_service import haversine_km
from app.services.safety_router import requires_safety_route, safety_response
from app.services.natlas_service import IntegrationNotConfigured
from app.services.conversation_service import process_text
from app.services.registration_service import get_user
from app.services.knowledge_service import answer_is_supported

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL',f'sqlite:///{tmp_path / "test.sqlite"}')
    monkeypatch.setenv('NATLAS_LANGUAGES','en')
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()

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
    result=await process_text(sender,'d4','DELETE CONFIRM')
    assert 'deleted' in result
    assert get_user(sender) is None
