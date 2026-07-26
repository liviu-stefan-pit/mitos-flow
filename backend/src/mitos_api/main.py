import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Mitos Flow API", version="0.1.0")

extra_origins = os.getenv("CORS_ORIGINS", "").split(",")
extra_origins = [o.strip() for o in extra_origins if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=extra_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}
