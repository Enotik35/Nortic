## Production Setup

Recommended topology:

- `example.com` or `www.example.com` -> site on Netlify
- `api.example.com` -> this Python backend on a VPS
- YooKassa webhook -> `https://api.example.com/webhooks/yookassa`
- YooKassa return URL -> `https://example.com/payment-return`

### Files for VPS

- `Dockerfile` builds the bot + FastAPI app
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

### YooKassa Values

- Webhook URL: `https://api.example.com/webhooks/yookassa`
- Return URL: `https://example.com/payment-return`

### Migration To Another VPS Later

To move to another VPS later:

1. Deploy the same repository on the new VPS.
2. Copy `.env.production`.
3. Migrate PostgreSQL data.
4. Start the new stack.
5. Verify `https://api.example.com/health`.
6. Change the `A` record for `api.example.com` to the new VPS IP.

Because the public URL stays the same, Telegram and YooKassa do not need code changes.
