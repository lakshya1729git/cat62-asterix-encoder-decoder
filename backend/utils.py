"""
utils.py
--------
Shared utility functions for CAT62 ASTERIX processing.

Covers:
- ISO timestamp <-> seconds-since-midnight conversion (with 1/128 sec scaling)
- Velocity component math (speed + heading)
- Signed integer encoding helpers for fixed-point fields
"""

import math
import struct
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Time utilities
# ---------------------------------------------------------------------------

def iso_to_seconds_since_midnight(iso_str: str) -> float:
    """
    Convert an ISO-8601 UTC timestamp string to floating-point seconds
    since midnight of the same UTC day.

    CAT62 I062/070 encodes time as:
        raw_value = floor(seconds_since_midnight * 128)
    stored in a 3-byte unsigned integer (allowing up to 86400 * 128 = 11,059,200
    which fits comfortably in 24 bits).

    The LSB of 1/128 second (≈7.8 ms) is mandated by the ASTERIX spec so that
    high-frequency radar plots can be timestamped with sub-10-ms precision.
    """
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    # Midnight of the same UTC day
    midnight_utc = dt.replace(hour=0, minute=0, second=0, microsecond=0,
                              tzinfo=timezone.utc)
    delta = dt.astimezone(timezone.utc) - midnight_utc
    return delta.total_seconds()


def seconds_since_midnight_to_iso(seconds: float, reference_date: str | None = None) -> str:
    """
    Convert seconds-since-midnight back to an ISO-8601 UTC string.

    If reference_date (YYYY-MM-DD) is not supplied, today's UTC date is used.
    This is acceptable for same-day round-trips; for multi-day archives a date
    must be tracked separately (ASTERIX itself does not encode the date).
    """
    if reference_date:
        base = datetime.strptime(reference_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0,
                                                  microsecond=0)
    result = base + timedelta(seconds=seconds)
    return result.isoformat().replace("+00:00", "Z")


def encode_time_of_track(seconds_since_midnight: float) -> bytes:
    """
    Encode seconds-since-midnight into 3-byte CAT62 I062/070 format.

    Encoding:
        raw = round(seconds_since_midnight × 128)   [units: 1/128 second]
        packed as big-endian unsigned 24-bit integer

    Maximum representable time: 2^23 - 1 / 128 ≈ 65535 s (just over 18 hours).
    The full 24-bit range covers 86400 s × 128 = 11,059,200 which fits in 24 bits.
    """
    raw = int(round(seconds_since_midnight * 128)) & 0xFFFFFF
    # Pack as 3 bytes big-endian
    return struct.pack(">I", raw)[1:]  # strip leading zero byte of uint32


def decode_time_of_track(raw_bytes: bytes) -> float:
    """
    Decode 3-byte I062/070 field back to floating-point seconds since midnight.
    """
    raw = int.from_bytes(raw_bytes, byteorder="big")
    return raw / 128.0


# ---------------------------------------------------------------------------
# Velocity math
# ---------------------------------------------------------------------------

def compute_ground_speed(vx: float, vy: float) -> float:
    """
    Cartesian ground speed in m/s from East (vx) and North (vy) components.
    """
    return math.sqrt(vx ** 2 + vy ** 2)


def compute_heading_degrees(vx: float, vy: float) -> float:
    """
    True heading in degrees [0, 360) from Cartesian velocity components.

    Convention (ASTERIX I062/185):
        vx = East component  (positive → East)
        vy = North component (positive → North)

    atan2(vx, vy) gives the clockwise angle from North, which is
    the standard aviation heading convention.
    """
    heading_rad = math.atan2(vx, vy)
    heading_deg = math.degrees(heading_rad)
    return heading_deg % 360.0


# ---------------------------------------------------------------------------
# Fixed-point encoding helpers
# ---------------------------------------------------------------------------

def encode_signed_16(value: float, lsb: float) -> bytes:
    """
    Encode a real-world value into a 2-byte signed big-endian integer
    using the given LSB resolution.

    Example: velocity component at LSB=0.25 m/s
        vx = 100.0 m/s → raw = round(100.0 / 0.25) = 400 → 0x0190
    """
    raw = int(round(value / lsb))
    # Clamp to signed 16-bit range
    raw = max(-32768, min(32767, raw))
    return struct.pack(">h", raw)


def decode_signed_16(raw_bytes: bytes, lsb: float) -> float:
    """
    Decode a 2-byte signed big-endian integer back to a real-world value.
    """
    raw = struct.unpack(">h", raw_bytes)[0]
    return raw * lsb


def encode_signed_32(value: float, lsb: float) -> bytes:
    """
    Encode a real-world value into a 4-byte signed big-endian integer.
    """
    raw = int(round(value / lsb))
    raw = max(-2147483648, min(2147483647, raw))
    return struct.pack(">i", raw)


def decode_signed_32(raw_bytes: bytes, lsb: float) -> float:
    raw = struct.unpack(">i", raw_bytes)[0]
    return raw * lsb


def encode_unsigned_16(value: float, lsb: float) -> bytes:
    """
    Encode a non-negative real-world value into a 2-byte unsigned big-endian integer.
    """
    raw = int(round(value / lsb))
    raw = max(0, min(65535, raw))
    return struct.pack(">H", raw)


def decode_unsigned_16(raw_bytes: bytes, lsb: float) -> float:
    raw = struct.unpack(">H", raw_bytes)[0]
    return raw * lsb
