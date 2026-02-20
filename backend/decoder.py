"""
decoder.py
----------
Parses a binary CAT62 ASTERIX datablock and converts each record into a
structured Python dict suitable for JSON serialisation.

High-level pipeline:
  Binary bytes
    │
    ▼
  asterix_wrapper.parse_datablock()   ← raw binary → list of raw field dicts
    │
    ▼
  enrich_record()                     ← add derived values (ISO time, speed, heading)
    │
    ▼
  build_decode_response()             ← final {"count": N, "records": [...]}

The ISO timestamp reconstruction uses today's UTC date as the reference day.
For archives spanning midnight or multiple days, callers should supply a
reference_date (YYYY-MM-DD) string extracted from a companion metadata field.
"""

import logging
import math
from typing import Any

from asterix_wrapper import parse_datablock
from utils import (
    seconds_since_midnight_to_iso,
    compute_ground_speed,
    compute_heading_degrees,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decode_datablock(
    raw_bytes: bytes,
    reference_date: str | None = None,
) -> dict[str, Any]:
    """
    Decode a binary CAT62 datablock into a structured JSON-serialisable dict.

    Parameters
    ----------
    raw_bytes : bytes
        Raw ASTERIX CAT62 datablock (as received from /encode or a file upload).
    reference_date : str | None
        Optional YYYY-MM-DD string.  Used when converting the decoded
        seconds-since-midnight back to a full ISO timestamp.  If omitted,
        today's UTC date is used.

    Returns
    -------
    dict with keys:
        count   (int)  Number of records decoded.
        records (list) One dict per CAT62 record.

    Raises
    ------
    ValueError
        Propagated from parse_datablock() on structural errors.
    """
    raw_records: list[dict] = parse_datablock(raw_bytes)
    log.info("Decoded %d raw record(s) from binary datablock", len(raw_records))

    enriched: list[dict] = [
        _enrich_record(r, idx + 1, reference_date)
        for idx, r in enumerate(raw_records)
    ]

    return {"count": len(enriched), "records": enriched}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enrich_record(
    raw: dict[str, Any],
    record_index: int,
    reference_date: str | None,
) -> dict[str, Any]:
    """
    Convert a raw decoded record dict (from asterix_wrapper) into a rich
    output dict with human-readable values and derived fields.

    Derived fields added:
        time_of_track_iso   — ISO-8601 UTC timestamp reconstructed from
                              seconds-since-midnight.
        ground_speed_ms     — sqrt(vx² + vy²) in m/s.
        heading_deg         — clockwise heading from North in degrees [0, 360).
    """
    out: dict[str, Any] = {"record_index": record_index}

    # --- Track Number ---
    if "track_number" in raw:
        out["track_number"] = raw["track_number"]

    # --- Position ---
    if "lat" in raw and "lon" in raw:
        out["position"] = {
            "lat": raw["lat"],
            "lon": raw["lon"],
        }

    # --- Flight Level ---
    if "measured_flight_level" in raw:
        out["measured_flight_level_FL"] = raw["measured_flight_level"]

    # --- Velocity (Vx, Vy) and derived speed/heading ---
    if "vx" in raw and "vy" in raw:
        vx: float = raw["vx"]
        vy: float = raw["vy"]
        out["velocity"] = {
            "vx_ms": vx,
            "vy_ms": vy,
        }
        out["ground_speed_ms"] = round(compute_ground_speed(vx, vy), 4)
        out["heading_deg"] = round(compute_heading_degrees(vx, vy), 4)

    # --- Rate of Climb/Descent ---
    if "rocd" in raw:
        out["rate_of_climb_descent_ftmin"] = raw["rocd"]

    # --- Time ---
    if "time_of_track_seconds" in raw:
        t_s: float = raw["time_of_track_seconds"]
        out["time_of_track_seconds"] = round(t_s, 4)
        try:
            out["time_of_track_iso"] = seconds_since_midnight_to_iso(t_s, reference_date)
        except Exception as exc:
            log.warning("Failed to convert time to ISO: %s", exc)
            out["time_of_track_iso"] = None

    # --- Diagnostic ---
    out["fspec_hex"] = raw.get("fspec_hex", "")

    log.debug(
        "Enriched record %d: TN=%s pos=%s FL=%s speed=%s heading=%s time=%s",
        record_index,
        out.get("track_number"),
        out.get("position"),
        out.get("measured_flight_level_FL"),
        out.get("ground_speed_ms"),
        out.get("heading_deg"),
        out.get("time_of_track_iso"),
    )

    return out
