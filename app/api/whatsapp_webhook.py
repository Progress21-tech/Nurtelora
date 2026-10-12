import hashlib, hmac, json
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from app.config import get_settings
from app.services.conversation_service import process_webhook

router=APIRouter()
WEBHOOK_PATH=get_settings().whatsapp_webhook_path

@router.get(WEBHOOK_PATH)
async def verify_meta(request: Request):
    q=request.query_params; s=get_settings()
    if not s.whatsapp_verify_token or q.get('hub.verify_token')!=s.whatsapp_verify_token or q.get('hub.mode')!='subscribe':
        raise HTTPException(403,"Webhook verification failed")
    return PlainTextResponse(q.get('hub.challenge',''))

@router.post(WEBHOOK_PATH)
async def receive(request: Request, background_tasks: BackgroundTasks, x_hub_signature_256: str|None=Header(default=None)):
    s=get_settings()
    if request.headers.get('content-type','').split(';',1)[0].lower()!='application/json':
        raise HTTPException(415,"Expected JSON")
    body=[]; total=0
    async for chunk in request.stream():
        total+=len(chunk)
        if total>1_000_000: raise HTTPException(413,"Webhook payload too large")
        body.append(chunk)
    raw=b''.join(body)
    if not s.whatsapp_app_secret or not x_hub_signature_256 or not x_hub_signature_256.startswith('sha256='):
        raise HTTPException(401,"Invalid webhook signature")
    expected='sha256='+hmac.new(s.whatsapp_app_secret.encode(),raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,x_hub_signature_256): raise HTTPException(401,"Invalid webhook signature")
    try: payload=json.loads(raw)
    except (ValueError,UnicodeDecodeError): raise HTTPException(400,"Invalid JSON") from None
    if not isinstance(payload,dict) or payload.get('object')!='whatsapp_business_account': raise HTTPException(400,"Unsupported webhook payload")
    # Process only after FastAPI has returned the acknowledgement to Meta.
    background_tasks.add_task(process_webhook,payload)
    return {"status":"accepted"}
