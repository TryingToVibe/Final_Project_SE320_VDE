"""Web API (FastAPI).                                                OWNER: Teammate C

Run locally:   uvicorn vde.api:app --reload
Docs:          http://127.0.0.1:8000/docs   (auto-generated OpenAPI; share with Teams 4/7)

Endpoints (all JSON; every non-2xx body is an ErrorResponse):

  POST /v1/events            body: CycleReport
      201 Created   -> DisposalEvent   new event
      200 OK        -> DisposalEvent   identical resubmission (duplicate-safe)
      409 Conflict  -> ErrorResponse   code EVENT_CONFLICT
      422           -> ErrorResponse   code VALIDATION_ERROR (bad/missing fields)

  GET  /v1/events/{event_id}
      200 OK        -> DisposalEvent
      404           -> ErrorResponse   code EVENT_NOT_FOUND

  GET  /v1/health  -> {"status": "ok", "schema_version": "..."}
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .errors import EventConflictError, EventNotFoundError
from .models import SCHEMA_VERSION, CycleReport, DisposalEvent, ErrorDetail, ErrorResponse
from .service import submit_report
from .store import EventStore, SQLiteEventStore

app = FastAPI(title="Verified Disposal Event API", version=SCHEMA_VERSION)

# Set VDE_DB_PATH to choose the database file (tests point it at a temp folder).
store: EventStore = SQLiteEventStore(os.environ.get("VDE_DB_PATH", "vde_events.db"))


def error_response(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, details=details or {}))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


@app.exception_handler(RequestValidationError)
async def _validation(_: Request, exc: RequestValidationError):
    return error_response(
        422,
        "VALIDATION_ERROR",
        "Request body failed validation",
        {"errors": jsonable_encoder(exc.errors())},
    )


@app.exception_handler(EventConflictError)
async def _conflict(_: Request, exc: EventConflictError):
    return error_response(409, exc.code, str(exc), {"event_id": exc.event_id})


@app.exception_handler(EventNotFoundError)
async def _not_found(_: Request, exc: EventNotFoundError):
    return error_response(404, exc.code, str(exc), {"event_id": exc.event_id})


@app.get("/v1/health")
def health():
    return {"status": "ok", "schema_version": SCHEMA_VERSION}


@app.post("/v1/events", response_model=DisposalEvent, status_code=201)
def create_event(report: CycleReport, response: Response):
    event, created = submit_report(report, store, datetime.now(timezone.utc))
    if not created:
        response.status_code = 200
    return event


@app.get("/v1/events/{event_id}", response_model=DisposalEvent)
def get_event(event_id: str):
    event = store.get(event_id)
    if event is None:
        raise EventNotFoundError(event_id)
    return event
