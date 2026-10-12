from app.db.database import connection
from app.services.registration_service import sender_digest
from datetime import datetime
from zoneinfo import ZoneInfo

def next_appointment(sender: str):
    with connection() as c:
        u=c.execute("SELECT id FROM users WHERE sender_hash=? AND deleted_at IS NULL AND consent_status='granted'",(sender_digest(sender),)).fetchone()
        if not u: return None
        today=datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat()
        return c.execute("SELECT a.*,f.name facility_name,f.phone facility_phone FROM appointments a LEFT JOIN facilities f ON f.id=a.facility_id WHERE a.user_id=? AND a.scheduled_at IS NOT NULL AND substr(a.scheduled_at,1,10)>=? ORDER BY a.scheduled_at LIMIT 1",(u['id'],today)).fetchone()

def appointment_reply(sender: str) -> str:
    a=next_appointment(sender)
    if not a: return "Your saved record does not contain a confirmed appointment date. Please contact your clinic to confirm your next visit."
    status=a['confirmation_status']; date=a['scheduled_at']
    label="confirmed by the clinic" if status=="clinic_confirmed" else "entered by you; not confirmed by the clinic" if status=="user_entered" else "not confirmed"
    return f"Your recorded appointment is {date} ({label})." + (f" Contact {a['facility_name']} at {a['facility_phone']}." if a['facility_phone'] else " Please contact your clinic to confirm.")
