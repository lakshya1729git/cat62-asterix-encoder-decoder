"""
encoder.py
----------
Converts a validated JSON payload (containing a "plots" array) into a binary
CAT62 ASTERIX datablock.

High-level pipeline:
  JSON input
    │
    ▼
  extract_plots()         ← pull only the "plots" list from the full document
    │
    ▼
  encode_plot()           ← per-plot: compute derived values, call asterix_wrapper
    │
    ▼
  assemble_datablock()    ← wrap all records in a single CAT62 datablock header

Data Source Identifier (I062/010) is fixed to SAC=0, SIC=1 — a placeholder that
an operational system would replace with the real radar site codes.
"""

import logging
import math
from typing import Any

from asterix_wrapper import build_cat62_record, build_datablock
from utils import (
    iso_to_seconds_since_midnight,
    compute_ground_speed,
    compute_heading_degrees,
)

log = logging.getLogger(__name__)

# Fixed Data Source Identifier for this demonstration system
_DEFAULT_SAC: int = 0
_DEFAULT_SIC: int = 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encode_plots(payload: dict[str, Any]) -> bytes:
    """
    Accept a full JSON document, extract the "plots" list, encode every plot as
    a CAT62 record, and return the assembled binary datablock.

    Parameters
    ----------
    payload : dict
        Validated JSON document.  Must contain a top-level "plots" key whose
        value is a non-empty list.

    Returns
    -------
    bytes
        A complete ASTERIX CAT62 datablock ready for transmission or storage.

    Raises
    ------
    ValueError
        If "plots" is absent, empty, or a plot is missing required fields.
    """
    plots: list[dict] = _extract_plots(payload)
    log.info("Encoding %d plot(s) from input JSON", len(plots))

    records: list[bytes] = []
    for index, plot in enumerate(plots):
        track_number = index + 1          # 1-based, incremental per datablock
        record = _encode_single_plot(plot, track_number)
        records.append(record)

    datablock = build_datablock(records)
    log.info(
        "Assembled CAT62 datablock: %d record(s), %d bytes total",
        len(records),
        len(datablock),
    )
    return datablock


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_plots(payload: dict[str, Any]) -> list[dict]:
    """
    Return the "plots" list from the top-level JSON document.

    Only the plots are encoded into CAT62 records; all other keys
    (id, centre_ctrl, fpl) are intentionally ignored by the encoder.
    """
    if "plots" not in payload:
        raise ValueError("Input JSON does not contain a 'plots' key")
    plots = payload["plots"]
    if not isinstance(plots, list) or len(plots) == 0:
        raise ValueError("'plots' must be a non-empty list")
    return plots


def _extract_required_field(plot: dict, key: str, sub_key: str) -> float:
    """Pull a numeric value from a nested structure, raising on absence."""
    if key not in plot:
        raise ValueError(f"Plot is missing required item '{key}'")
    item = plot[key]
    if sub_key not in item:
        raise ValueError(f"Item '{key}' is missing required field '{sub_key}'")
    value = item[sub_key]
    if not isinstance(value, (int, float)):
        raise ValueError(f"Field '{key}/{sub_key}' must be numeric, got {type(value)}")
    return float(value)


def _encode_single_plot(plot: dict[str, Any], track_number: int) -> bytes:
    """
    Derive all required CAT62 fields from one plot dict and return the
    encoded binary record.

    Expected plot structure:
        {
            "I062/105": {"lat": float, "lon": float},
            "I062/136": {"measured_flight_level": float},
            "I062/185": {"vx": float, "vy": float},
            "I062/220": {"rocd": float},
            "time_of_track": "ISO-8601 string"
        }

    Derived values:
        ground_speed = sqrt(vx² + vy²)          [m/s]
        heading      = atan2(vx, vy)             [degrees, clockwise from North]
        time_s       = seconds since midnight    [from ISO timestamp]

    These are logged but ground_speed and heading are informational only;
    CAT62/185 encodes raw Vx/Vy — speed and heading are derived by the consumer.
    """
    # --- Position ---
    lat = _extract_required_field(plot, "I062/105", "lat")
    lon = _extract_required_field(plot, "I062/105", "lon")

    # --- Flight Level ---
    fl = _extract_required_field(plot, "I062/136", "measured_flight_level")

    # --- Velocity components ---
    vx = _extract_required_field(plot, "I062/185", "vx")
    vy = _extract_required_field(plot, "I062/185", "vy")

    # --- Rate of Climb/Descent ---
    rocd = _extract_required_field(plot, "I062/220", "rocd")

    # --- Time ---
    if "time_of_track" not in plot:
        raise ValueError("Plot is missing required field 'time_of_track'")
    time_of_track_s = iso_to_seconds_since_midnight(plot["time_of_track"])

    # --- Derived informational values (logged, not encoded separately) ---
    ground_speed = compute_ground_speed(vx, vy)
    heading = compute_heading_degrees(vx, vy)

    log.debug(
        "Plot TN=%d | lat=%.6f lon=%.6f FL=%.1f vx=%.2f vy=%.2f "
        "speed=%.2f m/s heading=%.1f° rocd=%.1f ft/min time_s=%.3f",
        track_number, lat, lon, fl, vx, vy, ground_speed, heading, rocd, time_of_track_s,
    )

    log.info(
        "Encoding TN=%d with items: I062/010 I062/040 I062/070 "
        "I062/105 I062/185 I062/136 I062/220",
        track_number,
    )

    return build_cat62_record(
        sac=_DEFAULT_SAC,
        sic=_DEFAULT_SIC,
        track_number=track_number,
        time_of_track_s=time_of_track_s,
        lat=lat,
        lon=lon,
        flight_level=fl,
        vx=vx,
        vy=vy,
        rocd=rocd,
    )
