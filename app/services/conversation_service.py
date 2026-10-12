import json, uuid
from app.config import get_settings
from app.db.database import connection
from app.services.appointment_service import appointment_reply
from app.services.facility_service import format_facilities, search_facilities
from app.services.knowledge_service import answer_question
from app.services.natlas_service import NAtlasService
from app.services.registration_service import (delete_user_data, get_user, handle_onboarding, record_consent,
    has_pending_consent, select_language, start_appointment_entry, start_registration, stop_user)
from app.services.safety_router import safety_response

HELP="I can retrieve a saved appointment, search verified participating clinics, and answer questions from reviewed information. Reply START to register, APPOINTMENT for your saved date, APPOINTMENT SAVE to enter a date from your card, HUMAN for clinic contact options, LANGUAGE to change language, DELETE to request deletion, or STOP to opt out. I cannot diagnose or assess emergencies. No live human agent is connected."

async def process_text(sender: str, message_id: str, text: str, language: str|None=None) -> str:
    t=text.strip(); cmd=t.upper()
    if cmd=="START": return start_registration(sender)
    if cmd=="STOP": return stop_user(sender)
    if cmd=="DELETE": return delete_user_data(sender)
    if cmd=="DELETE CONFIRM": return delete_user_data(sender,confirm=True)
    if cmd in {"YES","NO"}:
        onboarding=handle_onboarding(sender,t)
        if onboarding: return onboarding
        if has_pending_consent(sender): return record_consent(sender,cmd=="YES")
        return "I didn't understand that reply. Send HELP to see available options."
    user=get_user(sender)
    if user and user['stopped']: return "You are opted out. Reply START if you want to begin again."
    if cmd=="HELP": return HELP
    if cmd in {"HUMAN","AGENT","HELP PERSON"}:
        if user and user['facility_id']:
            with connection() as c: facility=c.execute("SELECT name,phone FROM facilities WHERE id=? AND verification_status='verified'",(user['facility_id'],)).fetchone()
            if facility and facility['phone']: return f"No live human agent is connected. Please contact {facility['name']} at {facility['phone']}."
        return "No live human agent is connected and I don't have a verified clinic phone number for you. Please contact your antenatal clinic directly."
    if cmd=="LANGUAGE":
        languages=sorted(get_settings().configured_languages)
        return "Available languages: "+", ".join(languages) if languages else "No pilot language has been configured and tested yet."
    if cmd.lower() in get_settings().configured_languages: return select_language(sender,cmd.lower())
    if not user or user['consent_status']!="granted":
        return "Reply START to see the privacy notice and choose whether to create a saved profile. You can also use HELP."
    lang=language or user['preferred_language'] or "en"
    safety=safety_response(t)
    if safety: return safety
    onboarding=handle_onboarding(sender,t)
    if onboarding: return onboarding
    if cmd=="APPOINTMENT SAVE": return start_appointment_entry(sender)
    if cmd=="APPOINTMENT" or any(k in t.casefold() for k in ("appointment","clinic visit","antenatal date","next visit")):
        return appointment_reply(sender)
    if any(k in t.casefold() for k in ("facility","clinic near","health centre","health center","where is my clinic")):
        # No location is inferred from profile or device metadata.
        return format_facilities(search_facilities())
    return await answer_question(t,lang,NAtlasService())

async def process_webhook(payload: dict) -> int:
    processed=0
    for entry in payload.get('entry',[]):
        for change in entry.get('changes',[]):
            value=change.get('value') or {}
            for msg in value.get('messages',[]) or []:
                mid=msg.get('id'); sender=msg.get('from')
                if not mid or not sender: continue
                typ=msg.get('type','unknown')
                with connection() as c:
                    try: c.execute("INSERT INTO processed_messages(message_id,message_type,processing_status) VALUES(?,?,'received')",(mid,typ))
                    except Exception: continue
                outbound_started=False
                try:
                    text=msg.get('text',{}).get('body','') if typ=='text' else ''
                    if typ=='location':
                        loc=msg.get('location') or {}
                        rows=search_facilities(latitude=loc.get('latitude'),longitude=loc.get('longitude'))
                        reply=format_facilities(rows)
                    elif typ=='audio':
                        from app.services.whatsapp_service import WhatsAppService
                        media=msg.get('audio') or {}
                        user=get_user(sender)
                        if not user or user['consent_status']!='granted':
                            reply="Please send START first to read how messages and voice notes are processed and choose whether to consent."
                        else:
                            audio,mime,filename=await WhatsAppService().download_media(media.get('id',''),get_settings().max_audio_bytes)
                            lang=user['preferred_language']
                            if not lang or lang not in get_settings().configured_languages: reply="Voice messages aren't available in your current language setting. Please send a text message."
                            else:
                                transcript=await NAtlasService().transcribe_voice_note(audio,filename,lang)
                                reply=await process_text(sender,mid,transcript,lang)
                    elif typ=='text': reply=await process_text(sender,mid,text)
                    else: reply="I can read text, voice notes and shared locations. Please try one of those."
                    from app.services.whatsapp_service import WhatsAppService
                    outbound_started=True
                    out=await WhatsAppService().send_text_message(sender,reply,mid)
                    with connection() as c: c.execute("UPDATE processed_messages SET processing_status='sent',outbound_message_id=? WHERE message_id=?",(out,mid))
                except Exception as exc:
                    category=type(exc).__name__[:64]
                    with connection() as c: c.execute("UPDATE processed_messages SET processing_status='failed',error_category=? WHERE message_id=?",(category,mid))
                    # A provider timeout can leave delivery ambiguous; avoid a duplicate reply.
                    if not outbound_started:
                        try:
                            from app.services.whatsapp_service import WhatsAppService
                            fallback="I couldn't process that message right now. Please try again as text or contact your antenatal clinic. If you believe this is an emergency, seek urgent care now."
                            out=await WhatsAppService().send_text_message(sender,fallback,mid)
                            with connection() as c: c.execute("UPDATE processed_messages SET outbound_message_id=? WHERE message_id=?",(out,mid))
                        except Exception:
                            pass
                processed+=1
    return processed
