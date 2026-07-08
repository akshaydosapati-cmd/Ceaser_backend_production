# CEASER Backend

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Fill `backend/.env` with the real Supabase project values:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `DATABASE_URL`

`DATABASE_URL` must be the Supabase PostgreSQL connection string, not the Supabase project API URL. It should start with `postgresql+psycopg://` or `postgresql://`.

## Migrations

```bash
.\.venv\Scripts\alembic upgrade head
```

## Run

```bash
.\.venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

Expected:

```json
{"status":"healthy"}
```

## Tests

```bash
.\.venv\Scripts\python -m pytest -q
```

## Infrastructure Validation

After `backend/.env` is filled and migrations have been applied:

```bash
.\.venv\Scripts\python scripts\validate_infrastructure.py
```

## Render Deployment

This repository includes `render.yaml`.

1. Create a Render Blueprint from this repository.
2. Add the production values from `.env.example` in the Render dashboard.
3. Never upload or commit the local `.env` file.
4. Set `CORS_ORIGINS` to the deployed frontend URL.
5. Update Google and other OAuth callback URLs to use the deployed Render URL.

Render runs:

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
