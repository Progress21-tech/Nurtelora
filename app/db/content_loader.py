"""Load versioned, explicitly reviewed JSON into the local SQLite content tables."""
import json
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from app.db.database import connection

CONTENT_DIR=Path(__file__).resolve().parents[1]/"content"

class FAQEntry(BaseModel):
    id: str
    topic: str
    intent: str
    language: str
    approved_text: str
    source_title: str
    source_url: str
    reviewed_at: str
    review_due_at: str
    reviewer_role: str
    version: str
    review_status: Literal["approved"]

    @field_validator("source_url")
    @classmethod
    def require_https(cls,value):
        if not value.startswith("https://"): raise ValueError("source_url must use HTTPS")
        return value

    @field_validator("reviewed_at","review_due_at")
    @classmethod
    def validate_dates(cls,value):
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def review_window(self):
        if self.review_due_at < self.reviewed_at: raise ValueError("review_due_at cannot predate reviewed_at")
        return self

class FAQDocument(BaseModel):
    schema_version: Literal[1]
    entries: list[FAQEntry]=Field(default_factory=list)

class FacilityRecord(BaseModel):
    id: str
    name: str
    address: str
    state: str|None=None
    lga: str|None=None
    latitude: float|None=None
    longitude: float|None=None
    phone: str|None=None
    services: list[str]=Field(default_factory=list)
    opening_hours: str|None=None
    source: str
    last_verified_at: str
    owner: str
    verification_status: Literal["verified"]

    @field_validator("last_verified_at")
    @classmethod
    def validate_timestamp(cls,value):
        datetime.fromisoformat(value.replace("Z","+00:00"))
        return value

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None)!=(self.longitude is None): raise ValueError("latitude and longitude must be supplied together")
        if self.latitude is not None and not (-90<=self.latitude<=90 and -180<=self.longitude<=180):
            raise ValueError("coordinates are outside valid ranges")
        return self

class FacilityDocument(BaseModel):
    schema_version: Literal[1]
    facilities: list[FacilityRecord]=Field(default_factory=list)

def load_approved_content(directory: Path=CONTENT_DIR) -> None:
    faq=FAQDocument.model_validate_json((directory/"approved_faq.json").read_text(encoding="utf-8"))
    facility_data=FacilityDocument.model_validate_json((directory/"facilities.json").read_text(encoding="utf-8"))
    today=date.today().isoformat()
    with connection() as c:
        for item in faq.entries:
            c.execute("""INSERT INTO knowledge_entries(id,topic,intent,language,approved_text,source_title,source_url,
                reviewed_at,reviewer_role,version,review_due_at,review_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,'approved')
                ON CONFLICT(id) DO UPDATE SET topic=excluded.topic,intent=excluded.intent,language=excluded.language,
                approved_text=excluded.approved_text,source_title=excluded.source_title,source_url=excluded.source_url,
                reviewed_at=excluded.reviewed_at,reviewer_role=excluded.reviewer_role,version=excluded.version,
                review_due_at=excluded.review_due_at,review_status='approved'""",
                (item.id,item.topic,item.intent,item.language,item.approved_text,item.source_title,item.source_url,
                 item.reviewed_at,item.reviewer_role,item.version,item.review_due_at))
        for item in facility_data.facilities:
            if item.last_verified_at[:10] > today:
                raise ValueError(f"Facility {item.id} has a future verification date")
            c.execute("""INSERT INTO facilities(id,name,address,state,lga,latitude,longitude,phone,services,opening_hours,
                source,last_verified_at,owner,verification_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'verified')
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,address=excluded.address,state=excluded.state,lga=excluded.lga,
                latitude=excluded.latitude,longitude=excluded.longitude,phone=excluded.phone,services=excluded.services,
                opening_hours=excluded.opening_hours,source=excluded.source,last_verified_at=excluded.last_verified_at,
                owner=excluded.owner,verification_status='verified'""",
                (item.id,item.name,item.address,item.state,item.lga,item.latitude,item.longitude,item.phone,
                 json.dumps(item.services,ensure_ascii=False),item.opening_hours,item.source,item.last_verified_at,item.owner))
