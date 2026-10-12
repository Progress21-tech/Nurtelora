from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.whatsapp_webhook import router as whatsapp_router
from app.db.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app=FastAPI(title="Nurtelora Maternal Care Navigator",version="0.1.0",lifespan=lifespan)
app.include_router(health_router)
app.include_router(whatsapp_router)
