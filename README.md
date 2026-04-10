## Production Setup

Recommended topology:

- `example.com` or `www.example.com` -> site on Netlify
- `YOUR_VPS_IP:8000` -> this Python backend in Docker on a VPS
- YooKassa webhook -> `https://example.com/webhooks/yookassa` on Netlify
- YooKassa return URL -> `https://example.com/payment-return`

### Files for VPS

- `Dockerfile` builds the API-only container for webhook handling
- `docker-compose.prod.yml` runs only the API container on port `8000`
- `deploy/.env.production.example` is the template for `.env.production`

### First Deploy On VPS

1. Install Docker and Docker Compose plugin.
2. Clone this repository to the VPS.
3. Copy `deploy/.env.production.example` to `.env.production`.
4. Fill in production values, especially `DATABASE_URL`, `BOT_TOKEN`, `THREEXUI_*`, `YOOKASSA_*`, and `INTERNAL_API_TOKEN`.
5. Make sure `DATABASE_URL` points to the existing PostgreSQL instance. If PostgreSQL is already published on the VPS host as `5433:5432`, you can use `host.docker.internal:5433` from the API container.
6. Start the stack:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

7. Check health:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
curl http://YOUR_VPS_IP:8000/health
```

The production Docker stack should run only the FastAPI API. Keep the Telegram bot polling process under `systemd` or another separate supervisor so only one polling instance is running. This compose file does not create or manage PostgreSQL, and it does not start the Telegram bot.

### YooKassa Values

- Webhook URL: `https://example.com/webhooks/yookassa`
- Return URL: `https://example.com/payment-return`

### Netlify Webhook Fallback

Receive the YooKassa webhook on Netlify and forward activation to the backend API on the VPS.

Files:

- `netlify.toml`
- `netlify/functions/yookassa-webhook.js`
- `netlify/functions/payment-return.js`
- `netlify/functions/subscription-proxy.js`

Netlify environment variables:

- `YOOKASSA_SHOP_ID`
- `YOOKASSA_SECRET_KEY`
- `BACKEND_ACTIVATE_URL`
- `BACKEND_BASE_URL`
- `INTERNAL_API_TOKEN`

Recommended values:

- `BACKEND_ACTIVATE_URL=http://YOUR_VPS_IP:8000/internal/yookassa/activate`
- `BACKEND_BASE_URL=http://YOUR_VPS_IP:8000`
- `INTERNAL_API_TOKEN` should match `INTERNAL_API_TOKEN` in `.env.production`

Then set YooKassa webhook to:

- `https://example.com/webhooks/yookassa`

And set the YooKassa return URL to:

- `https://example.com/payment-return`

In this fallback topology, the public webhook lives on Netlify, while the actual subscription activation still happens in the Python backend on the VPS.
The same pattern is used for subscription links, so users can keep one public `https://your-domain/s/...` URL while you move the backend or VPN servers later.

### Multi-Server Subscription Notes

- Every active server can have its own 3x-ui panel settings stored in the `servers` table.
- If a server does not have panel settings filled in, the app falls back to global `THREEXUI_*` values from `.env`.
- The public subscription endpoint `/s/<token>` returns configs for all active servers and adds standard profile headers for clients such as Happ.
- To seed one server with explicit panel settings, use `SEED_SERVER_PANEL_*` environment variables with `python -m app.init_data`.

### Migration To Another VPS Later

To move to another VPS later:

1. Deploy the same repository on the new VPS.
2. Copy `.env.production`.
3. Migrate PostgreSQL data.
4. Start the new stack.
5. Verify `http://NEW_VPS_IP:8000/health`.
6. Update `BACKEND_ACTIVATE_URL` and `BACKEND_BASE_URL` on Netlify to the new VPS IP.

Because the public Netlify URLs stay the same, YooKassa does not need code changes when the VPS changes.
