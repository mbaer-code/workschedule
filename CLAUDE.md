# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WorkSchedule is a Flask web app that converts uploaded work schedule PDFs into iCalendar (.ics) files. Users upload a PDF, the app parses shift data, processes payment via Stripe, then delivers an .ics file via email (Mailgun) and GCS signed URL.

## Tech Stack

- **Backend:** Flask 2.x, Python 3.10, Gunicorn (production)
- **Database:** PostgreSQL via Flask-SQLAlchemy + Flask-Migrate (Alembic)
- **Auth:** Firebase Authentication (client-side SDK + server-side Admin SDK verification)
- **PDF Processing:** PyMuPDF (primary) with Google Document AI as alternative
- **Payments:** Stripe (one-time checkout sessions)
- **Email:** Mailgun API
- **Storage:** Google Cloud Storage (ICS file delivery with signed URLs)
- **Deployment:** Docker on Google Cloud Run, Cloud SQL (PostgreSQL)

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server (port 8080)
python workschedule/wsgi.py

# Run tests
pytest
pytest tests/unit/
pytest tests/integration/

# Database migrations
flask db migrate -m "description"
flask db upgrade
flask db downgrade

# Deploy to Cloud Run
gcloud builds submit --tag gcr.io/work-schedule-cloud/workschedule
```

## Architecture

### Application Factory
`workschedule/app.py` — `create_app()` initializes Flask, SQLAlchemy, Migrate, Firebase Admin SDK, GCS client, and registers blueprints. Also creates a module-level `app = create_app()` for Gunicorn. Entry point for Gunicorn is `workschedule/wsgi.py` which imports `create_app`.

### Route Blueprints
- `workschedule/routes/schedule.py` — `/schedule/*` endpoints: PDF upload, parsing, Stripe checkout, payment webhooks, ICS export/download
- `workschedule/routes/auth.py` — `/auth/*` endpoints: login/signup pages, Firebase token verification via `/auth/authenticate-session`, session management
- Root routes (`/`, `/index`, `/dashboard`, `/upload`) are defined directly in `app.py`

### Service Layer (`workschedule/services/`)
- `ics_generator.py` — Converts parsed shift entries into ICS calendar format (handles midnight-crossing shifts, break calculation, timezone localization)
- `ics_delivery.py` — Uploads ICS to GCS, returns 5-minute signed URL
- `stripe_service.py` — Creates Stripe checkout sessions with job metadata
- `mailgun_service.py` — Sends emails with ICS attachments and calendar import links
- `src/services/documentai_processor.py` — Google Document AI integration (alternative PDF extraction)

### Models (`workschedule/models.py`)
- **User** — firebase_uid, email, subscription_status, ics_feed_token
- **Schedule** — user_email, job_id, schedule_data (JSON string), created_at

### Auth Flow
Client-side Firebase SDK handles login → sends ID token to `/auth/authenticate-session` → server verifies with Firebase Admin SDK → sets `user_id` in Flask session.

### Payment/Export Flow
PDF upload → PyMuPDF text extraction + regex parsing → schedule review → Stripe checkout → webhook confirms payment → ICS generated → uploaded to GCS → emailed via Mailgun.

## Configuration (`workschedule/config.py`)

Database URI is resolved by priority:
1. `SQLALCHEMY_DATABASE_URI` env var (if set directly)
2. Cloud SQL Unix socket (detected via `K_SERVICE` env var on Cloud Run)
3. Local TCP connection using `DB_HOST`/`DB_PORT`

Key env vars: `FLASK_SECRET_KEY`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `FIREBASE_SERVICE_ACCOUNT_KEY`, `GCS_BUCKET_NAME`, `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET`, `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `BASE_URL`.

## Templates

Jinja2 templates in `workschedule/templates/` — organized into `auth/`, `emails/`, `payments/` subdirectories. Static CSS in `workschedule/static/css/`.
