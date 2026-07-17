from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import admin, auth, encounters, icd10, templates

settings = get_settings()

app = FastAPI(title="Kyron Clinical Scribe API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(encounters.router)
app.include_router(icd10.router)
app.include_router(admin.router)
app.include_router(templates.router)


@app.get("/health")
def health():
    return {"status": "ok"}
