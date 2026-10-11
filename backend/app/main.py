from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import health, dev, resume

app = FastAPI(
    title="InterroX API",
    description="Backend API for InterroX AI Interview Simulator",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Always register the health check router
app.include_router(health.router)

# Resume upload is part of the public API, not dev-only
app.include_router(resume.router)

# Only register the dev router when ENV=dev
if settings.ENV == "dev":
    app.include_router(dev.router)
