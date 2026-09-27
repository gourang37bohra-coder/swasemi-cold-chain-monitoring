"""Core telemetry ingestion service: validation, active-shipment gating, and persistence."""

from dataclasses import dataclass
from datetime import datetime
import json
import logging
from typing import Optional
import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.shipment import Shipment, ShipmentStatus
from app.models.telemetry import Telemetry
from app.models.tracker import Tracker
from app.schemas.telemetry import TelemetryPayload

logger = logging.getLogger("coldchain.telemetry.ingestion")


@dataclass
class IngestionResult:
    """Outcome of processing an incoming telemetry message."""

    success: bool
    status: str
    message: str
    telemetry: Optional[Telemetry] = None


def ingest_telemetry_payload(
    db: Session,
    payload_data: dict | str | bytes,
    topic: Optional[str] = None,
) -> IngestionResult:
    """Process, validate, gate, and persist an incoming telemetry message.

    Business Rules:
      1. Parse and validate against TelemetryPayload (Pydantic schema).
      2. Resolve Tracker in PostgreSQL. If unknown -> reject.
      3. Derive organization_id strictly from PostgreSQL Tracker record (never from payload).
      4. ACTIVE-SHIPMENT GATING:
         Only persist telemetry if the tracker has a shipment currently in ACTIVE status.
         NOT_STARTED, COMPLETED, or no shipment -> reject.
      5. Application-level idempotency: ignore duplicate (tracker_id, timestamp) pairs.
      6. Persist Telemetry row and update tracker.last_seen to payload.timestamp.
      7. Keep transactions safe: rollback on error, never crash consumer.
    """
    # 1. Parse JSON safely if payload is string or bytes
    if isinstance(payload_data, (bytes, bytearray)):
        try:
            payload_str = payload_data.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.warning("Rejected telemetry: UTF-8 decode error (%s)", type(exc).__name__)
            return IngestionResult(
                success=False,
                status="REJECTED_DECODE_ERROR",
                message="Message payload is not valid UTF-8 text.",
            )
        try:
            parsed_dict = json.loads(payload_str)
        except json.JSONDecodeError as exc:
            logger.warning("Rejected telemetry: Invalid JSON format (%s)", type(exc).__name__)
            return IngestionResult(
                success=False,
                status="REJECTED_INVALID_JSON",
                message="Message payload is not valid JSON.",
            )
    elif isinstance(payload_data, str):
        try:
            parsed_dict = json.loads(payload_data)
        except json.JSONDecodeError as exc:
            logger.warning("Rejected telemetry: Invalid JSON string (%s)", type(exc).__name__)
            return IngestionResult(
                success=False,
                status="REJECTED_INVALID_JSON",
                message="Message payload is not valid JSON.",
            )
    elif isinstance(payload_data, dict):
        parsed_dict = payload_data
    else:
        return IngestionResult(
            success=False,
            status="REJECTED_UNSUPPORTED_TYPE",
            message="Payload must be JSON string, bytes, or dict.",
        )

    # 2. Validate payload schema
    try:
        validated_payload = TelemetryPayload.model_validate(parsed_dict)
    except ValidationError as exc:
        logger.warning("Rejected telemetry: Schema validation error: %s", exc.errors(include_url=False))
        return IngestionResult(
            success=False,
            status="REJECTED_SCHEMA_VALIDATION",
            message=f"Schema validation failed: {str(exc.errors(include_url=False))}",
        )

    tracker_id = validated_payload.tracker_id

    # 3. Resolve tracker in database
    try:
        tracker = db.scalar(select(Tracker).where(Tracker.id == tracker_id))
    except SQLAlchemyError as exc:
        logger.error("Database error looking up tracker %s: %s", tracker_id, type(exc).__name__)
        db.rollback()
        return IngestionResult(
            success=False,
            status="ERROR_DATABASE",
            message="Database query failed while looking up tracker.",
        )

    if tracker is None:
        logger.warning("Rejected telemetry: Tracker %s does not exist in database.", tracker_id)
        return IngestionResult(
            success=False,
            status="REJECTED_UNKNOWN_TRACKER",
            message=f"Tracker {tracker_id} not found.",
        )

    # Organization is derived exclusively from the tracker record
    organization_id = tracker.organization_id

    # 4. Active-shipment gating
    try:
        active_shipment = db.scalar(
            select(Shipment).where(
                Shipment.tracker_id == tracker.id,
                Shipment.organization_id == organization_id,
                Shipment.status == ShipmentStatus.ACTIVE,
            )
        )
    except SQLAlchemyError as exc:
        logger.error("Database error querying active shipment: %s", type(exc).__name__)
        db.rollback()
        return IngestionResult(
            success=False,
            status="ERROR_DATABASE",
            message="Database query failed while checking shipment status.",
        )

    if active_shipment is None:
        logger.info(
            "Rejected telemetry: Tracker %s (org=%s) has no ACTIVE shipment. Telemetry discarded.",
            tracker_id,
            organization_id,
        )
        return IngestionResult(
            success=False,
            status="REJECTED_NO_ACTIVE_SHIPMENT",
            message=f"No ACTIVE shipment found for tracker {tracker_id}.",
        )

    # 5. Application-level idempotency / duplicate check
    try:
        duplicate = db.scalar(
            select(Telemetry).where(
                Telemetry.tracker_id == tracker.id,
                Telemetry.timestamp == validated_payload.timestamp,
            )
        )
        if duplicate is not None:
            logger.info(
                "Ignored duplicate telemetry for tracker %s at timestamp %s",
                tracker_id,
                validated_payload.timestamp,
            )
            return IngestionResult(
                success=True,
                status="IGNORED_DUPLICATE",
                message="Duplicate telemetry reading already persisted.",
                telemetry=duplicate,
            )
    except SQLAlchemyError as exc:
        logger.error("Database error checking duplicate telemetry: %s", type(exc).__name__)
        db.rollback()
        return IngestionResult(
            success=False,
            status="ERROR_DATABASE",
            message="Database query failed while checking duplicate telemetry.",
        )

    # 6. Persist Telemetry record and update tracker.last_seen
    telemetry = Telemetry(
        organization_id=organization_id,
        tracker_id=tracker.id,
        shipment_id=active_shipment.id,
        temperature=validated_payload.temperature,
        humidity=validated_payload.humidity,
        battery=validated_payload.battery,
        door_status=validated_payload.door_status,
        latitude=validated_payload.latitude,
        longitude=validated_payload.longitude,
        timestamp=validated_payload.timestamp,
    )
    tracker.last_seen = validated_payload.timestamp

    try:
        db.add(telemetry)
        db.commit()
        db.refresh(telemetry)
    except SQLAlchemyError as exc:
        logger.error("Database error saving telemetry: %s", type(exc).__name__)
        db.rollback()
        return IngestionResult(
            success=False,
            status="ERROR_DATABASE",
            message="Database transaction failed while saving telemetry.",
        )

    logger.info(
        "Successfully ingested telemetry: id=%s tracker=%s shipment=%s temp=%.2fC",
        telemetry.id,
        tracker.id,
        active_shipment.id,
        telemetry.temperature,
    )

    # 7. Evaluate temperature compliance and trigger alerts/emails if breached
    try:
        from app.services.compliance import evaluate_temperature_compliance
        evaluate_temperature_compliance(
            db=db,
            shipment=active_shipment,
            tracker=tracker,
            telemetry=telemetry,
        )
    except Exception as exc:
        logger.error("Error evaluating temperature compliance: %s", exc)

    # 8. Publish to Redis Pub/Sub for real-time WebSocket distribution (non-blocking for DB)
    try:
        from app.realtime.events import publish_telemetry_event
        publish_telemetry_event(telemetry)
    except Exception as exc:
        logger.warning("Redis real-time event dispatch skipped: %s", exc)

    return IngestionResult(
        success=True,
        status="ACCEPTED",
        message="Telemetry successfully recorded.",
        telemetry=telemetry,
    )

