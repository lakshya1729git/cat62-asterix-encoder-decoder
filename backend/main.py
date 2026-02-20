"""
main.py
-------
FastAPI application for CAT62 ASTERIX Encoding and Decoding.

Endpoints
---------
  POST /encode
      Accepts a JSON file containing a "plots" array.
      Returns a binary ASTERIX CAT62 datablock as an octet-stream download.

  POST /decode
      Accepts a binary CAT62 datablock file.
      Returns structured JSON with decoded track records.

  GET /health
      Simple liveness probe for deployment environments.

Run
---
    uvicorn main:app --reload

Or for network-accessible deployment:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import io
import json
import logging
import sys
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from decoder import decode_datablock
from encoder import encode_plots

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("main")

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CAT62 ASTERIX Encoder / Decoder",
    description=(
        "Encodes structured radar plot JSON into binary ASTERIX CAT62 datablocks "
        "and decodes them back into structured JSON.  "
        "Implements EUROCONTROL CAT62 Edition 1.19 at the binary level."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow the React frontend (Vite dev server on :5173) to call these endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Liveness probe — returns 200 OK when the service is running."""
    return {"status": "ok", "service": "CAT62 ASTERIX API"}


# ---------------------------------------------------------------------------
# POST /encode
# ---------------------------------------------------------------------------

@app.post(
    "/encode",
    tags=["CAT62"],
    summary="Encode JSON plots → CAT62 binary datablock",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "Binary CAT62 datablock (.bin)",
        },
        400: {"description": "Invalid input JSON"},
        422: {"description": "JSON validation / field error"},
    },
)
async def encode_endpoint(
    file: Annotated[UploadFile, File(description="JSON file containing a 'plots' array")],
) -> StreamingResponse:
    """
    Upload a JSON file.  Only the top-level **"plots"** array is encoded;
    fields such as `id`, `centre_ctrl`, and `fpl` are ignored.

    Each plot must contain:
    - `I062/105`:  `{lat, lon}`  (WGS-84 degrees)
    - `I062/136`:  `{measured_flight_level}`  (FL units)
    - `I062/185`:  `{vx, vy}`  (m/s, East/North)
    - `I062/220`:  `{rocd}`  (ft/min)
    - `time_of_track`:  ISO-8601 UTC string

    Returns a binary octet-stream (`application/octet-stream`) containing
    a valid ASTERIX CAT62 datablock.
    """
    # --- Read uploaded file ---
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    log.info("Received encode request: filename='%s' size=%d bytes",
             file.filename, len(raw_bytes))

    # --- Parse JSON ---
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("JSON parse error: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON: {exc}",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail="JSON root must be an object",
        )

    # --- Encode ---
    try:
        datablock: bytes = encode_plots(payload)
    except ValueError as exc:
        log.warning("Encode error: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    log.info("Encode complete: %d bytes returned", len(datablock))

    return StreamingResponse(
        content=io.BytesIO(datablock),
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="cat62_output.bin"'},
    )


# ---------------------------------------------------------------------------
# POST /decode
# ---------------------------------------------------------------------------

@app.post(
    "/decode",
    tags=["CAT62"],
    summary="Decode CAT62 binary datablock → structured JSON",
    responses={
        200: {"description": "Structured JSON with decoded track records"},
        400: {"description": "Invalid binary input"},
        422: {"description": "Binary structural error"},
    },
)
async def decode_endpoint(
    file: Annotated[UploadFile, File(description="Binary CAT62 datablock file")],
    reference_date: Annotated[
        str | None,
        Query(
            description=(
                "Optional date (YYYY-MM-DD) used to reconstruct ISO timestamps. "
                "Defaults to today's UTC date when omitted."
            )
        ),
    ] = None,
) -> dict:
    """
    Upload a binary CAT62 datablock (e.g. the output of **/encode**).

    Returns structured JSON:
    ```json
    {
      "count": 3,
      "records": [
        {
          "record_index": 1,
          "track_number": 1,
          "position": {"lat": 28.6139, "lon": 77.2090},
          "measured_flight_level_FL": 100.0,
          "velocity": {"vx_ms": 50.0, "vy_ms": 100.0},
          "ground_speed_ms": 111.8034,
          "heading_deg": 26.5651,
          "rate_of_climb_descent_ftmin": 500.0,
          "time_of_track_seconds": 35280.0,
          "time_of_track_iso": "2026-02-21T09:48:00Z",
          "fspec_hex": "F50A"
        }
      ]
    }
    ```
    """
    # --- Read uploaded file ---
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    log.info("Received decode request: filename='%s' size=%d bytes",
             file.filename, len(raw_bytes))

    # --- Decode ---
    try:
        result = decode_datablock(raw_bytes, reference_date=reference_date)
    except ValueError as exc:
        log.warning("Decode structural error: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Unexpected decode error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to decode binary data: {exc}",
        ) from exc

    log.info("Decode complete: %d record(s) returned", result["count"])
    return result
