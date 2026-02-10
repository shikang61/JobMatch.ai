"""
Job Match Platform - FastAPI application entry point.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from src.config import get_settings
from src.database.connection import close_db, get_db, init_db
from src.utils.logger import get_logger, setup_logging

# Import models so Base.metadata has all tables before init_db()
import src.models  # noqa: F401

from src.api.routes import auth, profile, jobs, matches, interviews, progress, seed_jobs, scrape, deep_scrape
from src.api.middleware.error_handler import register_exception_handlers

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB. Shutdown: close pool."""
    setup_logging()
    try:
        await init_db()
        logger.info("Application started")
    except Exception as e:
        logger.warning(
            "Database connection failed at startup. Start PostgreSQL and check DATABASE_URL. Error: %s",
            e,
        )
    yield
    await close_db()
    logger.info("Application shutdown")


def create_application() -> FastAPI:
    app = FastAPI(
        title="Job Match Platform API",
        description="AI-powered job matching and interview preparation",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Rate limiting (applied per-route for auth vs API limits)
    register_exception_handlers(app)

    prefix = settings.api_prefix
    app.include_router(auth.router, prefix=prefix + "/auth", tags=["auth"])
    app.include_router(profile.router, prefix=prefix + "/profile", tags=["profile"])
    # Register fixed-path routers BEFORE the wildcard /{job_id} router,
    # otherwise FastAPI tries to parse "matches" / "seed-jobs" / "scrape" as a UUID.
    app.include_router(matches.router, prefix=prefix + "/jobs", tags=["matches"])
    app.include_router(seed_jobs.router, prefix=prefix + "/jobs", tags=["jobs"])
    app.include_router(scrape.router, prefix=prefix + "/jobs", tags=["scraping"])
    app.include_router(deep_scrape.router, prefix=prefix + "/jobs", tags=["deep-research"])
    app.include_router(jobs.router, prefix=prefix + "/jobs", tags=["jobs"])
    app.include_router(interviews.router, prefix=prefix + "/interviews", tags=["interviews"])
    app.include_router(progress.router, prefix=prefix + "/progress", tags=["progress"])

    @app.get("/")
    async def root():
        """Redirect to API docs."""
        return RedirectResponse(url="/docs")

    @app.get("/health")
    async def health():
        """Health check for load balancers and monitoring."""
        return {"status": "ok"}

    return app


app = create_application()
