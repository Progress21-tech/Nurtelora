# Nurtelora

Nurtelora is an early technical prototype for a WhatsApp maternal-care navigator in Nigeria. It is not approved for clinical use. PostgreSQL is the intended deployment database; SQLAlchemy provides synchronous, transaction-scoped connections and Alembic owns all schema changes. SQLite remains an explicit local test/development option.

The PRD informs onboarding, appointment provenance, safety and pilot scope. The research PDF has not been incorporated. No real credentials, clinic records, or clinician-reviewed answers are included. Do not connect real patients until qualified professionals and relevant institutions approve content, safety routes, privacy notices and data handling.

## Database configuration

Set `DATABASE_URL` to a SQLAlchemy PostgreSQL URL. The app supports `postgresql://`, `postgresql+psycopg://` and Render-style `postgres://` URLs; the latter two legacy forms are normalized to Psycopg 3 without dropping URL query options. Production (`APP_ENV=production`) rejects SQLite and requires a PostgreSQL URL. Credentials must be provided through the deployment secret/environment settings, never source control.

`PHONE_HASH_SECRET` must be a unique secret of at least 32 characters in production. Integration settings are optional while their integrations remain disabled. N-ATLAS uses `NATLAS_ENABLED`, `NATLAS_BASE_URL`, `NATLAS_API_KEY`, `NATLAS_MODEL`, `NATLAS_TIMEOUT_SECONDS`, `NATLAS_MAX_RETRIES`, and `NATLAS_LANGUAGES`. WhatsApp uses `WHATSAPP_ENABLED`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, `META_GRAPH_API_VERSION`, and `WHATSAPP_WEBHOOK_PATH`. Never put production secrets in `.env.example` or CI.

## Local development with Docker Compose

Requires Docker Compose v2. Copy `.env.example` to `.env`; its database credentials are synthetic local-only examples. If you change the local PostgreSQL password, use URL-safe characters because Compose assembles `DATABASE_URL` from the three `POSTGRES_*` settings. Start the database, apply migrations as a separate one-off service, then start FastAPI:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose logs -f nurtelora
```

Compose waits for PostgreSQL health and successful completion of `alembic upgrade head` before starting the app. The database is kept in the `postgres_data` named volume. To inspect service status, use `docker compose ps`; the health endpoint is `http://localhost:8000/health` and reports the connected backend without exposing credentials.

For direct Python development, use Python 3.10 or newer, install `requirements-dev.txt`, set `DATABASE_URL` to an explicit local URL such as `sqlite:///./nurtelora.db`, and run `alembic upgrade head` before `uvicorn app.main:app --reload`. Database tables are not created by importing the app or starting Uvicorn. Do not use the local SQLite file in production.

## Schema migrations

The versioned PostgreSQL baseline is in `migrations/versions/`. From an environment that has access to the target database, run:

```powershell
alembic upgrade head
```

Run this once for each release before that application version receives traffic. Render currently documents pre-deploy commands for paid web services, private services and background workers; confirm support for the selected service plan in the [Render deploy documentation](https://render.com/docs/deploys). If a pre-deploy command is unavailable, run the same Alembic command as an authorized one-off operation against the Render internal database URL before switching traffic. Do not add migrations to application startup; that would make every worker race to alter production schema.

## SQLite files and existing data

The repository contains no SQLite database file or included dataset. SQLite files are ignored by Git and are not automatically imported. A fresh PostgreSQL database should be initialized with Alembic. If an operator has a separate local SQLite file containing records, stop before deploying those records and plan a separately reviewed, explicit data migration with count and relationship validation; this repository does not currently include an import utility.

## Tests and CI

Install `requirements-dev.txt` and run `python -m pytest`. Local tests use a fresh temporary SQLite database and apply the migration history for isolation. CI sets `NURTELORA_TEST_DATABASE_URL` to a disposable PostgreSQL service and runs `alembic upgrade head` before the tests, so those tests exercise PostgreSQL without mocking the database layer. Tests use synthetic data and mock the WhatsApp sender; no test calls live N-ATLAS or WhatsApp services.

GitHub Actions also runs `python -m compileall app tests migrations` and builds the Dockerfile without publishing the image. Integrations are disabled in CI.

## Render preparation

Create a managed PostgreSQL database and configure `DATABASE_URL` in the Render service from the database's **internal connection URL** when both resources share a region. Render documents the same-region internal URL as the private-network option; see [Render PostgreSQL connection docs](https://render.com/docs/postgresql-creating-connecting). Also set `APP_ENV=production` and a generated `PHONE_HASH_SECRET`. Add N-ATLAS and Meta values only when authorized and ready to enable those integrations. Do not place credentials in `render.yaml`, this repository, or logs.

Use `alembic upgrade head` as the separate pre-deploy migration command when available, and use this start command for the web service:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

The Dockerfile uses the same single-worker command and honors `PORT`. If the selected service plan does not offer a pre-deploy command, execute Alembic once from a secure one-off operation before directing traffic to the new version. Do not run migrations in each worker. After deployment, `/health` should report `database.backend` as `postgresql`; it checks connectivity and schema presence but does not verify upstream credentials or clinical approval.

## Application data and safety

The database stores HMAC-digested sender identifiers, consent records, user-selected language/facility, user-entered appointment dates, reviewed FAQ content, verified facility content, webhook idempotency records and expiring consent/deletion workflow state. The pending consent and deletion confirmations expire after 24 hours and are stored under the sender digest, not the raw number. Deletion runs in a transaction. `STOP` clears pending workflow state and disables reminders.

The FAQ and facility JSON files are empty until qualified reviewers approve sourced content. Content is validated and loaded at startup after migrations. Facility records are only as verified as the approved source data supplied by the operator. Appointment dates entered by users are not clinic bookings. Safety routing is a generic, English keyword guard, not clinical triage. No speech language is enabled by default; low-confidence transcript confirmation is unavailable from the current gateway response.

The health route reports database connectivity and dialect without including the connection URL. PostgreSQL migration alone does not make the service ready for real health data. Access controls, backup/retention and deletion procedures, privacy review, clinical review, language testing, facility verification, operations monitoring and institutional approvals remain necessary.

## Content files

`app/content/approved_faq.json` and `app/content/facilities.json` are validated and upserted on app startup. Keep them empty until entries have been reviewed. FAQ entries require source URL, reviewer role, version, review dates and `review_status: "approved"`. Facility entries require source, verification owner, timestamp and `verification_status: "verified"`. See the Pydantic models in `app/db/content_loader.py` for the full schema.
