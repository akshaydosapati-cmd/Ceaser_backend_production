# CEASER Stage 29 Deployment Checklist

## Database

1. Back up the production database.
2. Run `alembic upgrade head` before starting the API.
3. Confirm the active head is `20260812_0027`.
4. Keep Supabase RLS enabled and verify service-role credentials remain backend-only.

## Backend

Set `CEASER_ENV=production` and configure non-local values for `DATABASE_URL`,
`CORS_ORIGINS`, and `FRONTEND_APP_URL`. Configure Supabase URL, anon key,
service-role key, `JWT_SECRET`, and `ENCRYPTION_MASTER_KEY`. Configure at least
one normal-chat provider (`OPENAI_API_KEY`, `GROQ_API_KEY`, or
`GEMINI_API_KEY`). Production startup fails with safe setting names when these
requirements are not met.

Keep V1 flags:

```text
CEASER_LOCAL_CODING_ENABLED=true
CEASER_CLOUD_CODING_ENABLED=false
DEV_AUTH_BYPASS=false
```

Configure integration credentials and callback URLs in the provider consoles.
Do not expose provider, GitHub, Supabase service-role, or encryption credentials
to frontend or desktop builds.

## Frontend

Set `NEXT_PUBLIC_API_URL` to the production API before `npm run build`. Configure
the public Supabase URL and anon key used for web authentication. A production
build has no localhost or hardcoded API fallback.

## Desktop

Set `CEASER_APP_URL` and `CEASER_API_URL`, then run `npm run dist`. The generated
`.env.runtime` must contain only public endpoints and behavior flags. Inspect the
installer contents to confirm that API keys, tokens, backend `.env` files, and
developer paths are absent. Verify `ceaser://` protocol registration and the
packaged Python/Porcupine assets on a clean Windows device.

## Device Gateway

Expose the authenticated WebSocket route through the production proxy with
upgrade support and idle timeouts longer than the heartbeat interval. Verify a
revoked device disconnects and that live gateway presence, ownership, and
advertised capability determine eligibility.

## Release Order

1. Apply migrations.
2. Deploy backend and worker.
3. Verify `/health/live` and `/health/ready`.
4. Build and deploy frontend with the production API URL.
5. Build and sign the desktop installer from sanitized runtime configuration.
6. Continue with Stage 30 clean-device, live-provider, and real-world tests.
