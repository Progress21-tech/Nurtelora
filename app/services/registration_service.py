import hashlib, hmac, uuid
from datetime import datetime, timedelta, timezone
from app.config import get_settings
from app.db.database import connection

NOTICE_VERSION = "draft-1"
_WORKFLOW_STATE_TTL = timedelta(hours=24)
PRIVACY_NOTICE = ("I can help with appointment information, participating clinics and clinician-reviewed maternal-health information. "
                  "I am not a doctor and cannot assess emergencies. To reply, your message and any voice note are processed by our messaging and authorised AI providers. "
                  "To match your YES or NO reply, a protected sender identifier and temporary consent state are stored for up to 24 hours, then removed. "
                  "If you consent, we will also save your protected sender identifier, language, clinic choice and appointment details you choose to enter. We do not store raw audio by default. "
                  "Reply YES to consent or NO to continue without a saved profile. Reply STOP to stop.")

def sender_digest(sender: str) -> str:
    return hmac.new(get_settings().phone_hash_secret.encode(), sender.encode(), hashlib.sha256).hexdigest()

def get_user(sender: str):
    with connection() as c: return c.execute("SELECT * FROM users WHERE sender_hash=? AND deleted_at IS NULL", (sender_digest(sender),)).fetchone()

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _clear_expired(sender_hash: str, c) -> None:
    now = _now().isoformat()
    c.execute("UPDATE workflow_states SET pending_consent_expires_at=NULL WHERE sender_hash=? AND pending_consent_expires_at<=?", (sender_hash, now))
    c.execute("UPDATE workflow_states SET pending_deletion_expires_at=NULL WHERE sender_hash=? AND pending_deletion_expires_at<=?", (sender_hash, now))
    c.execute("DELETE FROM workflow_states WHERE sender_hash=? AND pending_consent_expires_at IS NULL AND pending_deletion_expires_at IS NULL", (sender_hash,))

def cleanup_expired_workflow_states() -> None:
    now=_now().isoformat()
    with connection() as c:
        c.execute("UPDATE workflow_states SET pending_consent_expires_at=NULL WHERE pending_consent_expires_at<=?",(now,))
        c.execute("UPDATE workflow_states SET pending_deletion_expires_at=NULL WHERE pending_deletion_expires_at<=?",(now,))
        c.execute("DELETE FROM workflow_states WHERE pending_consent_expires_at IS NULL AND pending_deletion_expires_at IS NULL")

def start_registration(sender: str) -> str:
    digest = sender_digest(sender)
    expiry = (_now() + _WORKFLOW_STATE_TTL).isoformat()
    with connection() as c:
        c.execute("""INSERT INTO workflow_states(sender_hash,pending_consent_expires_at,pending_deletion_expires_at)
            VALUES(?,?,NULL) ON CONFLICT(sender_hash) DO UPDATE SET
            pending_consent_expires_at=excluded.pending_consent_expires_at,
            updated_at=CURRENT_TIMESTAMP""", (digest, expiry))
    return PRIVACY_NOTICE

def has_pending_consent(sender: str) -> bool:
    digest = sender_digest(sender)
    with connection() as c:
        _clear_expired(digest, c)
        row = c.execute("SELECT pending_consent_expires_at FROM workflow_states WHERE sender_hash=?", (digest,)).fetchone()
        return bool(row and row["pending_consent_expires_at"] and row["pending_consent_expires_at"] > _now().isoformat())

def record_consent(sender: str, yes: bool) -> str:
    digest=sender_digest(sender)
    with connection() as c:
        _clear_expired(digest, c)
        claimed=c.execute("UPDATE workflow_states SET pending_consent_expires_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE sender_hash=? AND pending_consent_expires_at>?",(digest,_now().isoformat()))
        if claimed.rowcount!=1: return "Reply START to see the privacy notice first."
        if not yes:
            c.execute("DELETE FROM workflow_states WHERE sender_hash=? AND pending_consent_expires_at IS NULL AND pending_deletion_expires_at IS NULL",(digest,))
            return "Understood. No saved profile was created. You can use HELP or reply START later."
        user = c.execute("SELECT id FROM users WHERE sender_hash=? AND deleted_at IS NULL", (digest,)).fetchone()
        if not user:
            uid=str(uuid.uuid4())
            c.execute("INSERT INTO users(id,sender_hash,consent_status,registration_state) VALUES(?,?,'granted','language_pending')", (uid,digest))
        else:
            uid=user["id"]
            c.execute("UPDATE users SET consent_status='granted',registration_state='language_pending',stopped=FALSE,updated_at=CURRENT_TIMESTAMP WHERE id=?",(uid,))
        c.execute("INSERT INTO consent_records(id,user_id,consent_type,status,notice_version) VALUES(?,?,?,?,?)", (str(uuid.uuid4()),uid,"persistent_profile","granted",NOTICE_VERSION))
        c.execute("DELETE FROM workflow_states WHERE sender_hash=? AND pending_deletion_expires_at IS NULL", (digest,))
    languages=sorted(get_settings().configured_languages)
    if not languages:
        return "Thanks for consenting. No pilot language has been configured and tested yet, so I can't continue the conversation safely. Reply DELETE if you want your saved profile removed."
    return "Thanks. Choose a configured language: " + ", ".join(languages)

def select_language(sender: str, language: str) -> str:
    if language not in get_settings().configured_languages: return "That language is not configured. Reply LANGUAGE to see available choices."
    with connection() as c:
        u=c.execute("SELECT id,consent_status FROM users WHERE sender_hash=? AND deleted_at IS NULL",(sender_digest(sender),)).fetchone()
        if not u or u["consent_status"]!="granted": return "Please reply START and choose whether to consent first."
        c.execute("UPDATE users SET preferred_language=?,registration_state='facility_pending',updated_at=CURRENT_TIMESTAMP WHERE id=?",(language,u["id"]))
        facilities=c.execute("SELECT id,name,state,lga FROM facilities WHERE verification_status='verified' ORDER BY name").fetchall()
    if facilities:
        choices="\n".join(f"{r['id']}: {r['name']} ({r['lga'] or r['state'] or 'area not listed'})" for r in facilities)
        return f"Language set to {language}. Choose your clinic by replying with its facility ID, or reply SKIP.\n{choices}"
    return f"Language set to {language}. There are no verified participating clinics configured yet. Reply SKIP to continue without linking a clinic."

def handle_onboarding(sender: str, text: str) -> str | None:
    """Deterministic facility and appointment-card capture workflow."""
    cmd=text.strip()
    with connection() as c:
        u=c.execute("SELECT * FROM users WHERE sender_hash=? AND deleted_at IS NULL",(sender_digest(sender),)).fetchone()
        if not u or u['consent_status']!='granted': return None
        if u['registration_state']=='facility_pending':
            if cmd.upper()=='SKIP':
                c.execute("UPDATE users SET registration_state='registered',updated_at=CURRENT_TIMESTAMP WHERE id=?",(u['id'],))
                return "You can save the next date from your antenatal card at any time by sending APPOINTMENT SAVE. Reply HELP for options."
            facility=c.execute("SELECT id,name FROM facilities WHERE id=? AND verification_status='verified'",(cmd,)).fetchone()
            if not facility: return "I couldn't match that to a verified participating clinic. Reply with a listed facility ID or SKIP."
            c.execute("UPDATE users SET facility_id=?,registration_state='registered',updated_at=CURRENT_TIMESTAMP WHERE id=?",(facility['id'],u['id']))
            return f"Clinic set to {facility['name']}. You can save the next date from your antenatal card by sending APPOINTMENT SAVE."
        if u['registration_state']=='appointment_date_pending':
            try:
                value=datetime.fromisoformat(cmd)
                if len(cmd)!=10 and ('T' not in cmd or value.tzinfo is None):
                    return "Include a timezone offset with a time, or send only the date as YYYY-MM-DD."
            except ValueError:
                return "Please enter the date shown on your card as YYYY-MM-DD, or YYYY-MM-DDTHH:MM+/-HH:MM. I will not calculate a date."
            c.execute("UPDATE users SET pending_appointment_at=?,registration_state='appointment_confirmation_pending',updated_at=CURRENT_TIMESTAMP WHERE id=?",(cmd,u['id']))
            return f"I heard {cmd}. This will be saved as a date you entered, not clinic-confirmed. Reply YES to save it or NO to enter it again."
        if u['registration_state']=='appointment_confirmation_pending':
            if cmd.upper()=='NO':
                c.execute("UPDATE users SET pending_appointment_at=NULL,registration_state='appointment_date_pending',updated_at=CURRENT_TIMESTAMP WHERE id=?",(u['id'],))
                return "Please re-enter the date from your card in YYYY-MM-DD format."
            if cmd.upper()=='YES':
                appointment_id=str(uuid.uuid4())
                c.execute("INSERT INTO appointments(id,user_id,facility_id,scheduled_at,source,confirmation_status,owner) VALUES(?,?,?,?,?,?,?)",
                          (appointment_id,u['id'],u['facility_id'],u['pending_appointment_at'],'user','user_entered','user'))
                c.execute("UPDATE users SET pending_appointment_at=NULL,registration_state='registered',updated_at=CURRENT_TIMESTAMP WHERE id=?",(u['id'],))
                return "Saved. This appointment date was entered by you and is not confirmed by your clinic. Reply APPOINTMENT to read it back."
            return "Please reply YES to save this user-entered date or NO to change it."
    return None

def start_appointment_entry(sender: str) -> str:
    with connection() as c:
        u=c.execute("SELECT id,consent_status FROM users WHERE sender_hash=? AND deleted_at IS NULL",(sender_digest(sender),)).fetchone()
        if not u or u['consent_status']!='granted': return "Reply START and consent before saving an appointment."
        c.execute("UPDATE users SET registration_state='appointment_date_pending',updated_at=CURRENT_TIMESTAMP WHERE id=?",(u['id'],))
    return "Enter the appointment date from your clinic card as YYYY-MM-DD. You may include a timezone offset with a time, for example YYYY-MM-DDTHH:MM+01:00. I will save it as user-entered, not clinic-confirmed."

def delete_user_data(sender: str, confirm: bool=False) -> str:
    digest=sender_digest(sender)
    if not confirm:
        expiry=(_now()+_WORKFLOW_STATE_TTL).isoformat()
        with connection() as c:
            c.execute("""INSERT INTO workflow_states(sender_hash,pending_deletion_expires_at,pending_consent_expires_at)
                VALUES(?,?,NULL) ON CONFLICT(sender_hash) DO UPDATE SET
                pending_deletion_expires_at=excluded.pending_deletion_expires_at,updated_at=CURRENT_TIMESTAMP""",(digest,expiry))
        return "To delete your saved profile and appointments, reply DELETE CONFIRM. This cannot be undone."
    with connection() as c:
        _clear_expired(digest,c)
        claimed=c.execute("UPDATE workflow_states SET pending_deletion_expires_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE sender_hash=? AND pending_deletion_expires_at>?",(digest,_now().isoformat()))
        if claimed.rowcount!=1: return "Reply DELETE first if you want to request deletion."
        user=c.execute("SELECT id FROM users WHERE sender_hash=?",(digest,)).fetchone()
        if not user:
            c.execute("DELETE FROM workflow_states WHERE sender_hash=?",(digest,))
            return "No saved profile was found for deletion."
        uid=user['id']
        c.execute("DELETE FROM appointments WHERE user_id=?",(uid,))
        c.execute("DELETE FROM consent_records WHERE user_id=?",(uid,))
        c.execute("DELETE FROM interaction_events WHERE session_id=?",(uid,))
        c.execute("DELETE FROM users WHERE id=?",(uid,))
        c.execute("DELETE FROM workflow_states WHERE sender_hash=?",(digest,))
    return "Your saved profile, consent record and appointments have been deleted."

def stop_user(sender: str) -> str:
    digest=sender_digest(sender)
    with connection() as c:
        c.execute("DELETE FROM workflow_states WHERE sender_hash=?",(digest,))
        u=c.execute("SELECT id FROM users WHERE sender_hash=?",(digest,)).fetchone()
        if u: c.execute("UPDATE users SET stopped=TRUE,reminder_opt_in=FALSE,updated_at=CURRENT_TIMESTAMP WHERE id=?",(u["id"],))
    return "You have been opted out. I will not send further reminders. Reply START if you want to begin again."
