import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.whatsapp_webhook import router as whatsapp_router
from app.db.database import check_database
from app.db.content_loader import load_approved_content
from app.services.registration_service import cleanup_expired_workflow_states

logger=logging.getLogger(__name__)

async def _workflow_cleanup_loop():
    while True:
        await asyncio.sleep(900)
        try:
            await asyncio.to_thread(cleanup_expired_workflow_states)
        except Exception:
            logger.warning("Expired workflow state cleanup failed; it will retry.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.config import get_settings
    settings=get_settings()
    secret=settings.phone_hash_secret.casefold()
    if settings.app_env.casefold()=="production" and (len(settings.phone_hash_secret)<32 or "replace" in secret or "change-me" in secret):
        raise RuntimeError("Production requires a unique PHONE_HASH_SECRET of at least 32 characters.")
    check_database()
    cleanup_expired_workflow_states()
    load_approved_content()
    cleanup_task=asyncio.create_task(_workflow_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        await asyncio.gather(cleanup_task,return_exceptions=True)

app=FastAPI(title="Nurtelora Maternal Care Navigator",version="0.1.0",lifespan=lifespan)
app.include_router(health_router)
app.include_router(whatsapp_router)
