from fastapi import APIRouter
from app.config import get_settings

router=APIRouter()
@router.get('/health')
def health():
    s=get_settings()
    return {"status":"ok","integrations":{"natlas":"configured" if s.natlas_enabled and s.natlas_base_url and s.natlas_api_key else "disabled","whatsapp":"configured" if s.whatsapp_enabled else "disabled"},"clinical_approval":"not_approved"}
