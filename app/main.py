from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.whatsapp_webhook import router as whatsapp_router
from app.db.database import init_db
from app.db.content_loader import load_approved_content

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.config import get_settings
    settings=get_settings()
    if settings.app_env.casefold()=="production" and (settings.phone_hash_secret=="development-only-change-me" or len(settings.phone_hash_secret)<32):
        raise RuntimeError("Production requires a unique PHONE_HASH_SECRET of at least 32 characters.")
    init_db()
    load_approved_content()
    yield

app=FastAPI(title="Nurtelora Maternal Care Navigator",version="0.1.0",lifespan=lifespan)
app.include_router(health_router)
app.include_router(whatsapp_router)
