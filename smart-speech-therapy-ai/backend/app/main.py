from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings


def _validate_production_config() -> None:
    """Refuse to boot with known-insecure defaults in production (spec
    section 83: secrets/config discipline). This is a deliberate hard
    failure, not a warning log easy to miss — an app running in production
    with the default SECRET_KEY lets anyone forge valid JWTs for any user,
    including admin."""
    if not settings.is_production:
        return
    problems = []
    if settings.SECRET_KEY == "insecure-dev-key-change-me":
        problems.append("SECRET_KEY is still the insecure development default.")
    if settings.FIRST_ADMIN_PASSWORD == "change-me-strong-password":
        problems.append("FIRST_ADMIN_PASSWORD is still the insecure development default.")
    if "*" in settings.cors_origins_list:
        problems.append("CORS_ORIGINS includes '*', which is unsafe alongside allow_credentials=True.")
    if problems:
        raise RuntimeError(
            "Refusing to start in production (APP_ENV=production) with insecure configuration:\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\nSet real values via environment variables before deploying."
        )


def create_app() -> FastAPI:
    _validate_production_config()

    app = FastAPI(
        title=settings.APP_NAME,
        description="Smart Speech Therapy AI — backend API (auth/RBAC scaffold)",
        version="0.1.0",
        # Interactive API docs leak the full endpoint/schema surface, which
        # is useful in development but unnecessary attack-surface exposure
        # in production — disabled there, not just "security by obscurity"
        # since the API itself still enforces real auth either way.
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        """Baseline security response headers (spec section 83-adjacent
        hardening) — defense-in-depth, not a replacement for proper auth
        checks which remain the primary control throughout this API."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/health", tags=["System"])
    def health():
        """Liveness check — does the process respond at all."""
        return {"status": "ok"}

    @app.get("/ready", tags=["System"])
    def ready():
        """Readiness check — can we reach the database."""
        from sqlalchemy import text

        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception as exc:  # noqa: BLE001
            db_status = f"error: {exc}"
        finally:
            db.close()

        overall = "ok" if db_status == "ok" else "degraded"
        return {"status": overall, "database": db_status}

    return app


app = create_app()
