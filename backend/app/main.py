"""Cold-Chain Monitoring Platform - FastAPI Application Entry Point."""

import logging
from fastapi import FastAPI, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from contextlib import asynccontextmanager

from app.api.admin import router as admin_router
from app.api.alerts import router as alerts_router
from app.api.auth import router as auth_router
from app.api.shipments import router as shipments_router
from app.api.telemetry import router as telemetry_router
from app.api.trackers import router as trackers_router
from app.core.config import settings
from app.core.dependencies import get_db
from app.realtime import connection_manager, redis_manager, realtime_router

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("coldchain.api")

from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan managing Redis connections and background bridges."""
    logger.info("Initializing real-time event bus and Redis connection...")
    try:
        await redis_manager.connect()
        await connection_manager.start_redis_bridge()
    except Exception as exc:
        logger.warning("Redis initialization encountered issue (%s). Proceeding with REST fallback.", exc)
    try:
        from app.mqtt.client import mqtt_consumer
        mqtt_consumer.start()
    except Exception as exc:
        logger.warning("MQTT consumer startup failed: %s", exc)
    yield
    logger.info("Shutting down real-time event bus and MQTT consumer...")
    try:
        from app.mqtt.client import mqtt_consumer
        mqtt_consumer.stop()
    except Exception as exc:
        logger.warning("Error stopping MQTT consumer: %s", exc)
    try:
        await connection_manager.stop_redis_bridge()
        await redis_manager.close()
    except Exception as exc:
        logger.warning("Error during real-time shutdown: %s", exc)


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# Enable CORS for frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(trackers_router)
app.include_router(shipments_router)
app.include_router(telemetry_router)
app.include_router(alerts_router)
app.include_router(realtime_router)



@app.get("/health", tags=["Health"])
def health_check():
    """Basic health check endpoint to verify that the service is running."""
    return {"status": "ok"}


@app.get("/health/db", tags=["Health"])
def db_health_check(db: Session = Depends(get_db)):
    """Database connectivity health check.
    
    Verifies that the application can successfully execute a query against PostgreSQL.
    Sensitive connection details and internal exception traces are never exposed.
    """
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        logger.error("Database health check failed: %s", type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "database": "unavailable"},
        )
