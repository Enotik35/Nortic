from fastapi import FastAPI

app = FastAPI(title="Subscription Bot API")


@app.get("/health")
async def health():
    return {"status": "ok"}