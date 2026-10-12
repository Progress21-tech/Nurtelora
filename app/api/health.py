from fastapi import APIRouter, HTTPException
from app.config import get_settings
from app.db.database import DatabaseUnavailable, check_database, get_engine

router=APIRouter()
@router.get('/health')
def health():
    s=get_settings()
    try:
        check_database()
    except DatabaseUnavailable:
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status":"ok","database":{"status":"connected","backend":get_engine().dialect.name},"integrations":{"natlas":"configured" if s.natlas_enabled and s.natlas_base_url and s.natlas_api_key else "disabled","whatsapp":"configured" if s.whatsapp_enabled else "disabled"},"clinical_approval":"not_approved"}
