## Production Setup

Recommended topology:

- `example.com` or `www.example.com` -> site on Netlify
- `api.example.com` -> this Python backend on a VPS
- YooKassa webhook -> `https://api.example.com/webhooks/yookassa`
- YooKassa return URL -> `https://example.com/payment-return`

### Files for VPS

- `Dockerfile` builds the API-only container for webhook handling
- `docker-compose.prod.yml` runs `app`, `db`, and `caddy`
- `deploy/Caddyfile` terminates HTTPS and proxies to FastAPI
- `deploy/.env.production.example` is the template for `.env.production`

### DNS

Create these records:

- `A` record: `api` -> your VPS public IP
- `CNAME` or Netlify-managed record: `www` / apex domain -> Netlify

### First Deploy On VPS

1. Install Docker and Docker Compose plugin.
2. Clone this repository to the VPS.
3. Copy `deploy/.env.production.example` to `.env.production`.
4. Fill in production values, especially `BOT_TOKEN`, `THREEXUI_*`, `YOOKASSA_*`, `POSTGRES_PASSWORD`, and `API_DOMAIN`.
5. Make sure DNS for `api.example.com` already points to the VPS.
6. Start the stack:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

7. Check health:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
curl https://api.example.com/health
```

The production Docker stack should run only the FastAPI API. Keep the Telegram bot polling process under `systemd` or another separate supervisor so only one polling instance is running.

### YooKassa Values

- Webhook URL: `https://api.example.com/webhooks/yookassa`
- Return URL: `https://example.com/payment-return`

### Netlify Webhook Fallback

If the VPS cannot expose `443` because another service already owns it, you can receive the YooKassa webhook on Netlify and forward activation to the backend.

Files:

- `netlify.toml`
- `netlify/functions/yookassa-webhook.js`

Netlify environment variables:

- `YOOKASSA_SHOP_ID`
- `YOOKASSA_SECRET_KEY`
- `BACKEND_ACTIVATE_URL`
- `INTERNAL_API_TOKEN`

Recommended values:

- `BACKEND_ACTIVATE_URL=http://YOUR_VPS_IP:8000/internal/yookassa/activate`
- `INTERNAL_API_TOKEN` should match `INTERNAL_API_TOKEN` in `.env.production`

Then set YooKassa webhook to:

- `https://example.com/webhooks/yookassa`

In this fallback topology, the public webhook lives on Netlify, while the actual subscription activation still happens in the Python backend on the VPS.

### Migration To Another VPS Later

To move to another VPS later:

1. Deploy the same repository on the new VPS.
2. Copy `.env.production`.
3. Migrate PostgreSQL data.
4. Start the new stack.
5. Verify `https://api.example.com/health`.
6. Change the `A` record for `api.example.com` to the new VPS IP.

Because the public URL stays the same, Telegram and YooKassa do not need code changes.
