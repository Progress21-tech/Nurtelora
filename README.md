# Nurtelora

Nurtelora is the working repository for a WhatsApp maternal-care navigator for Nigeria. The current implementation is an early technical prototype; it is not approved for clinical use.

## Current status

The service is being built around FastAPI, SQLite, N-ATLAS hosted chat and ASR, and WhatsApp Cloud API. No real credentials, clinic records, or clinician-reviewed answers are included. No speech language is enabled by default; configure one only after the complete interaction path is tested with intended users and speakers. Safety-sensitive symptom handling is restricted to a generic escalation message. Do not connect real patients until qualified maternal-health professionals and the relevant institutions approve the content, safety routes, privacy notices, and data handling.

The PRD has been read and informs the onboarding, appointment provenance, safety and pilot scope. The research PDF could not be extracted with the available tools; do not treat the report's findings as incorporated yet. No clinical content has been inferred from its filename.

## Run locally

Requires Python 3.10+.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.db.database
uvicorn app.main:app --reload
```

Health check: `GET http://127.0.0.1:8000/health`. The app starts with integrations disabled. Add authorised credentials to `.env` to enable real calls. `NATLAS_BASE_URL` must be supplied by an authorised provider; no endpoint or key is assumed. Keep `.env` private.

## Configuration

See `.env.example`. Configure `WHATSAPP_VERIFY_TOKEN` and `WHATSAPP_APP_SECRET` from Meta. `META_GRAPH_API_VERSION` is required before enabling WhatsApp. Set the webhook URL to `/webhooks/whatsapp` on a stable HTTPS host. Do not enable WhatsApp message handling without consent text and the approved safety fallback.

N-ATLAS uses the documented hosted gateway endpoints `/v1/chat/completions` and `/v1/audio/transcriptions`. The configured `NATLAS_BASE_URL` may end in `/v1` or be an origin. Chat explicitly instructs the model about language; the gateway's chat `language` field is logging metadata only. Voice ASR requires an explicitly configured supported language.

## Data and safety

The SQLite database is initialized on application startup. User profiles use a keyed HMAC digest of sender numbers for lookup; a stable `PHONE_HASH_SECRET` must be set before deployment. Consent-pending and deletion-confirmation tokens are held in process memory, so use a single worker for this prototype. There is no real-patient seed data. The approved FAQ and facility directory are empty until vetted, sourced records are added. Suggested dates are never created by the model. Symptom routing is conservative and disabled for clinical triage; only a generic message directs the user to contact a qualified provider or local emergency service.

SQLite is suitable for local development only. Use a reviewed migration plan for PostgreSQL, TLS, access controls, backups, retention/deletion, and Nigerian data protection obligations before handling real health data. A user deletion workflow is not implemented yet; provide authenticated deletion before any real deployment.

## Tests

Install dependencies, then run `python -m pytest`. Tests are designed to use mocked upstream clients. Live smoke tests are not implemented. No test or live integration result is claimed from this environment because Python could not be launched here.

## Architecture and current limitations

- `app/api/whatsapp_webhook.py` verifies Meta challenges/signatures and parses inbound messages.
- `app/services/` contains the N-ATLAS, WhatsApp, deterministic conversation, knowledge, facility, appointment, registration, and safety boundaries.
- `app/db/` persists minimal profiles, consent, appointments, facilities, approved knowledge entries, and message idempotency records.
- Scheduled reminders, clinical booking, automatic obstetric triage, enabled languages, non-English approved content, and live facility data are not available by default.
- The facility records are empty pending a named pilot partner and verified directory data. The PRD also calls for transcript confirmation when ASR confidence is low; this gateway response does not currently expose a confidence score, so no confidence-based confirmation is claimed.
- The knowledge base, safety message catalog, and facility directory require review and verified data before use.

## External requirements before a demonstration with real users

Authorised N-ATLAS gateway URL/key; Meta app credentials and a configured WhatsApp number; a stable HTTPS deployment; qualified clinical review of all user-facing health and safety content; approved participating-facility data; user-tested languages; privacy/data-protection review and institutional approval; and a deployment authentication and operations plan.
