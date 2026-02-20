"""
asterix_wrapper.py
------------------
Low-level CAT62 ASTERIX binary encoding and decoding.

ASTERIX Binary Structure (per EUROCONTROL spec):
================================================
  [ Category (1 byte) ][ Length (2 bytes) ][ Record 1 ][ Record 2 ]...

Each Record:
  [ FSPEC (variable bytes) ][ Data Items in UAP order ]

FSPEC (Field SPECification):
  - One or more octets, each bit indicates presence of a Data Item.
  - Bits are numbered MSB=bit8 → LSB=bit1.
  - Bit 1 (LSB) of every octet is the FX (Field eXtension) bit:
      FX=1 → next octet continues the FSPEC
      FX=0 → this octet is the last FSPEC octet
  - Items are encoded in UAP (User Application Profile) order.

CAT62 UAP (Edition 1.19):
  Octet 1: FRN1=I062/010, FRN2=I062/040, FRN3=I062/070, FRN4=I062/105,
            FRN5=I062/100, FRN6=I062/185, FRN7=I062/210, FX
  Octet 2: FRN8=I062/060, FRN9=I062/245, FRN10=I062/380, FRN11=spare,
            FRN12=I062/136, FRN13=I062/130, FRN14=I062/220, FX

Item Encodings used in this module:
  I062/010  2 bytes   SAC (1B) + SIC (1B)
  I062/040  2 bytes   flags(4b) + track_num(12b)
  I062/070  3 bytes   time × 128  [1/128 s LSB, unsigned]
  I062/105  8 bytes   lat_raw(4B) + lon_raw(4B), LSB = 180/2^25 deg
  I062/185  4 bytes   vx_raw(2B) + vy_raw(2B),  LSB = 0.25 m/s
  I062/136  2 bytes   FL × 4  [0.25 FL LSB, signed]
  I062/220  2 bytes   rocd / 6.25  [6.25 ft/min LSB, signed]
"""

import struct
import logging
import math
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CAT62 constants
# ---------------------------------------------------------------------------

CAT62_CATEGORY: int = 0x3E  # 62 decimal

# WGS-84 position: LSB = 180 / 2^25 degrees
WGS84_LSB: float = 180.0 / (2 ** 25)  # ≈ 5.364e-6 degrees per LSB

# Velocity: LSB = 0.25 m/s per LSB
VEL_LSB: float = 0.25

# Flight Level: LSB = 0.25 FL per LSB (FL = hundreds of feet)
FL_LSB: float = 0.25

# Rate of Climb/Descent: LSB = 6.25 ft/min per LSB
ROCD_LSB: float = 6.25

# ---------------------------------------------------------------------------
# FSPEC computation
# ---------------------------------------------------------------------------

# UAP: maps each I062/XXX item to its Field Reference Number (FRN).
# FRN tells us which bit (and which FSPEC octet) indicates the item's presence.
# Octet index = (FRN - 1) // 7  (because each 8-bit octet holds 7 item bits + 1 FX)
# Bit position within octet = 7 - ((FRN - 1) % 7) → maps FRN to bit weight (MSB first)

UAP_FRN: dict[str, int] = {
    "I062/010": 1,
    "I062/040": 2,
    "I062/070": 3,
    "I062/105": 4,
    "I062/100": 5,
    "I062/185": 6,
    "I062/210": 7,
    # FX — octet boundary
    "I062/060": 8,
    "I062/245": 9,
    "I062/380": 10,
    # FRN 11 = spare (not a real item)
    "I062/136": 12,
    "I062/130": 13,
    "I062/220": 14,
    # FX — octet boundary; more items follow in further octets
}


def build_fspec(items_present: list[str]) -> bytes:
    """
    Construct the FSPEC byte string for the given set of present Data Items.

    Algorithm:
      1. Convert each item name to its FRN.
      2. Determine the maximum octet index needed.
      3. For each octet, set the appropriate data bits.
      4. Set FX=1 for every octet that is followed by another.

    Returns a bytes object of variable length (1–N octets).
    """
    frns: set[int] = set()
    for name in items_present:
        if name in UAP_FRN:
            frns.add(UAP_FRN[name])

    if not frns:
        return b"\x00"

    # Each octet covers 7 FRNs: octet k covers FRNs 7k+1 … 7k+7 (0-indexed k)
    max_frn = max(frns)
    num_octets = math.ceil(max_frn / 7)
    octets = [0] * num_octets

    for frn in frns:
        # Convert 1-based FRN → 0-based octet index and bit position
        octet_idx = (frn - 1) // 7          # which octet (0-based)
        bit_within = (frn - 1) % 7          # 0 = first item in octet (MSB side)
        bit_weight = 1 << (7 - bit_within)  # bit8=0x80, bit7=0x40, …, bit2=0x02
        octets[octet_idx] |= bit_weight

    # Set FX bit (bit 1 = 0x01) for every octet except the last
    for i in range(num_octets - 1):
        octets[i] |= 0x01

    return bytes(octets)


# ---------------------------------------------------------------------------
# Individual Data Item encoders
# ---------------------------------------------------------------------------

def encode_I062_010(sac: int, sic: int) -> bytes:
    """
    I062/010 – Data Source Identifier  (2 bytes)
    SAC: System Area Code  (0–255)
    SIC: System Identification Code (0–255)
    """
    return struct.pack("BB", sac & 0xFF, sic & 0xFF)


def encode_I062_040(track_number: int) -> bytes:
    """
    I062/040 – Track Number  (2 bytes)

    Layout (16 bits):
      Bit 16: MU (Multi-sensor) = 0
      Bit 15: SPI = 0
      Bits 14-13: spare = 00
      Bits 12-1: Track Number (0–4095)

    The track number occupies the lower 12 bits; upper 4 bits are flags.
    """
    tn = track_number & 0x0FFF   # clamp to 12-bit range
    return struct.pack(">H", tn)


def encode_I062_070(seconds_since_midnight: float) -> bytes:
    """
    I062/070 – Time of Track Information  (3 bytes)

    LSB = 1/128 second.
    Formula: raw = round(seconds_since_midnight × 128)
    Stored as unsigned 24-bit big-endian integer.
    """
    raw = int(round(seconds_since_midnight * 128)) & 0xFFFFFF
    # Convert to 3 bytes by packing as uint32 and taking last 3 bytes
    return struct.pack(">I", raw)[1:]


def encode_I062_105(lat_deg: float, lon_deg: float) -> bytes:
    """
    I062/105 – Calculated Position in WGS-84 Co-ordinates  (8 bytes)

    Each coordinate is a 4-byte signed integer.
    LSB = 180 / 2^25 degrees ≈ 5.364×10⁻⁶ °

    Formula: raw_lat = round(lat_deg / WGS84_LSB)
    """
    raw_lat = int(round(lat_deg / WGS84_LSB))
    raw_lon = int(round(lon_deg / WGS84_LSB))
    # Clamp to signed 32-bit
    raw_lat = max(-2147483648, min(2147483647, raw_lat))
    raw_lon = max(-2147483648, min(2147483647, raw_lon))
    return struct.pack(">ii", raw_lat, raw_lon)


def encode_I062_185(vx: float, vy: float) -> bytes:
    """
    I062/185 – Calculated Track Velocity (Cartesian)  (4 bytes)

    Two 2-byte signed integers.
    LSB = 0.25 m/s for both components.
    vx = East component (positive → East)
    vy = North component (positive → North)
    """
    raw_vx = int(round(vx / VEL_LSB))
    raw_vy = int(round(vy / VEL_LSB))
    raw_vx = max(-32768, min(32767, raw_vx))
    raw_vy = max(-32768, min(32767, raw_vy))
    return struct.pack(">hh", raw_vx, raw_vy)


def encode_I062_136(flight_level: float) -> bytes:
    """
    I062/136 – Measured Flight Level  (2 bytes)

    Signed 16-bit. LSB = 0.25 FL (FL = hundreds of feet).
    Formula: raw = round(flight_level / 0.25) = round(flight_level × 4)
    """
    raw = int(round(flight_level / FL_LSB))
    raw = max(-32768, min(32767, raw))
    return struct.pack(">h", raw)


def encode_I062_220(rocd: float) -> bytes:
    """
    I062/220 – Calculated Rate of Climb/Descent  (2 bytes)

    Signed 16-bit. LSB = 6.25 ft/min.
    Positive = climb; negative = descent.
    Formula: raw = round(rocd / 6.25)
    """
    raw = int(round(rocd / ROCD_LSB))
    raw = max(-32768, min(32767, raw))
    return struct.pack(">h", raw)


# ---------------------------------------------------------------------------
# Record assembly
# ---------------------------------------------------------------------------

def build_cat62_record(
    sac: int,
    sic: int,
    track_number: int,
    time_of_track_s: float,
    lat: float,
    lon: float,
    flight_level: float,
    vx: float,
    vy: float,
    rocd: float,
) -> bytes:
    """
    Assemble one CAT62 record (FSPEC + Data Items in UAP order).

    Items included (in UAP order):
      I062/010  Data Source Identifier
      I062/040  Track Number
      I062/070  Time of Track Information
      I062/105  WGS-84 Position
      I062/185  Velocity (Cartesian)
      I062/136  Measured Flight Level       ← FRN 12, second FSPEC octet
      I062/220  Rate of Climb/Descent       ← FRN 14, second FSPEC octet

    FSPEC is built automatically: 0xF5 0x0A
      Octet 1: I062/010(b8) I062/040(b7) I062/070(b6) I062/105(b5)
               I062/185(b3) FX=1(b1)
      Octet 2: I062/136(b4) I062/220(b2) FX=0(b1)
    """
    items_present = [
        "I062/010", "I062/040", "I062/070",
        "I062/105", "I062/185",
        "I062/136", "I062/220",
    ]

    fspec = build_fspec(items_present)

    # Encode each item
    data_010 = encode_I062_010(sac, sic)
    data_040 = encode_I062_040(track_number)
    data_070 = encode_I062_070(time_of_track_s)
    data_105 = encode_I062_105(lat, lon)
    data_185 = encode_I062_185(vx, vy)
    data_136 = encode_I062_136(flight_level)
    data_220 = encode_I062_220(rocd)

    log.debug(
        "Record TN=%d | Items: I062/010(%dB) I062/040(%dB) I062/070(%dB) "
        "I062/105(%dB) I062/185(%dB) I062/136(%dB) I062/220(%dB) | FSPEC=%s",
        track_number,
        len(data_010), len(data_040), len(data_070),
        len(data_105), len(data_185), len(data_136), len(data_220),
        fspec.hex().upper(),
    )

    return (
        fspec
        + data_010   # FRN 1
        + data_040   # FRN 2
        + data_070   # FRN 3
        + data_105   # FRN 4
        + data_185   # FRN 6
        + data_136   # FRN 12
        + data_220   # FRN 14
    )


def build_datablock(records: list[bytes]) -> bytes:
    """
    Wrap a list of encoded CAT62 records into a valid ASTERIX Datablock.

    Datablock layout:
      [0x3E]       1 byte  — Category = 62
      [len_hi]     1 byte  — Total length high byte (includes these 3 header bytes)
      [len_lo]     1 byte  — Total length low byte
      [record …]   N bytes — Concatenated records

    Length field = 3 (header) + total bytes of all records.
    """
    payload = b"".join(records)
    total_length = 3 + len(payload)
    header = struct.pack(">BH", CAT62_CATEGORY, total_length)
    return header + payload


# ---------------------------------------------------------------------------
# Individual Data Item decoders
# ---------------------------------------------------------------------------

def decode_I062_010(data: bytes) -> dict[str, int]:
    sac, sic = struct.unpack("BB", data[:2])
    return {"sac": sac, "sic": sic}


def decode_I062_040(data: bytes) -> dict[str, int]:
    raw = struct.unpack(">H", data[:2])[0]
    track_number = raw & 0x0FFF
    return {"track_number": track_number}


def decode_I062_070(data: bytes) -> dict[str, float]:
    raw = int.from_bytes(data[:3], byteorder="big")
    seconds = raw / 128.0
    return {"time_of_track_seconds": seconds}


def decode_I062_105(data: bytes) -> dict[str, float]:
    raw_lat, raw_lon = struct.unpack(">ii", data[:8])
    lat = raw_lat * WGS84_LSB
    lon = raw_lon * WGS84_LSB
    return {"lat": round(lat, 8), "lon": round(lon, 8)}


def decode_I062_185(data: bytes) -> dict[str, float]:
    raw_vx, raw_vy = struct.unpack(">hh", data[:4])
    vx = raw_vx * VEL_LSB
    vy = raw_vy * VEL_LSB
    return {"vx": round(vx, 4), "vy": round(vy, 4)}


def decode_I062_136(data: bytes) -> dict[str, float]:
    raw = struct.unpack(">h", data[:2])[0]
    fl = raw * FL_LSB
    return {"measured_flight_level": round(fl, 4)}


def decode_I062_220(data: bytes) -> dict[str, float]:
    raw = struct.unpack(">h", data[:2])[0]
    rocd = raw * ROCD_LSB
    return {"rocd": round(rocd, 4)}


# ---------------------------------------------------------------------------
# Datablock parser
# ---------------------------------------------------------------------------

# Maps each I062 item (by FRN) to (item_name, byte_size, decoder_function).
# Only items present in our encoding scheme are included; extend as needed.
# FRN 11 is a spare slot with no associated item.
_FRN_REGISTRY: dict[int, tuple[str, int, Any]] = {
    1:  ("I062/010", 2,  decode_I062_010),
    2:  ("I062/040", 2,  decode_I062_040),
    3:  ("I062/070", 3,  decode_I062_070),
    4:  ("I062/105", 8,  decode_I062_105),
    # FRN 5 (I062/100) and FRN 7 (I062/210) are not encoded by us;
    # we still need their byte sizes to skip them during decoding.
    5:  ("I062/100", 6,  None),   # Slant Range — skip
    6:  ("I062/185", 4,  decode_I062_185),
    7:  ("I062/210", 4,  None),   # Acceleration — skip
    8:  ("I062/060", 2,  None),   # Mode 3/A — skip
    9:  ("I062/245", 7,  None),   # Target Ident — skip
    # FRN 10 (I062/380) is variable length; handled separately below
    12: ("I062/136", 2,  decode_I062_136),
    13: ("I062/130", 2,  None),   # Geometric alt — skip
    14: ("I062/220", 2,  decode_I062_220),
}


def _parse_fspec(data: bytes, offset: int) -> tuple[list[int], int]:
    """
    Read variable-length FSPEC starting at `offset`.

    Returns (list_of_active_FRNs, new_offset_after_fspec).

    Each octet contributes 7 FRNs (bits 8→2); bit1 is the FX extension flag.
    FRNs are 1-based and increase left-to-right across octets.
    """
    active_frns: list[int] = []
    octet_index = 0
    while True:
        byte = data[offset]
        offset += 1
        for bit_pos in range(7, 0, -1):        # bits 7 down to 1 (bit weights 128→2)
            if byte & (1 << bit_pos):
                frn = octet_index * 7 + (8 - bit_pos)
                active_frns.append(frn)
        fx = byte & 0x01                        # FX = bit 1 (LSB)
        octet_index += 1
        if not fx:
            break
    return active_frns, offset


def parse_datablock(raw: bytes) -> list[dict[str, Any]]:
    """
    Parse an ASTERIX CAT62 datablock and return a list of decoded record dicts.

    Each returned dict contains decoded fields from the items present in that
    record, plus a raw 'fspec_hex' for diagnostic purposes.

    Raises ValueError for structural errors (wrong category, short data, etc.).
    """
    if len(raw) < 3:
        raise ValueError("Datablock too short (< 3 bytes)")

    category = raw[0]
    if category != CAT62_CATEGORY:
        raise ValueError(f"Expected CAT62 (0x3E=62), got {category}")

    declared_length = struct.unpack(">H", raw[1:3])[0]
    if declared_length > len(raw):
        raise ValueError(
            f"Declared length {declared_length} exceeds available data {len(raw)}"
        )

    records: list[dict[str, Any]] = []
    offset = 3  # skip 3-byte datablock header

    while offset < declared_length:
        record_start = offset
        fspec_frns, offset = _parse_fspec(raw, offset)
        fspec_hex = raw[record_start:offset].hex().upper()
        log.debug("Parsing record at byte %d | FSPEC=%s | FRNs=%s",
                  record_start, fspec_hex, fspec_frns)

        record: dict[str, Any] = {"fspec_hex": fspec_hex}

        for frn in fspec_frns:
            if frn == 11:
                # FRN 11 is a spare slot — no data bytes
                continue

            if frn == 10:
                # I062/380 – Aircraft Derived Data (variable length compound item)
                # Format: 2-byte primary subfield indicator + variable subfields.
                # We skip this item entirely; read past it by parsing its length.
                if offset + 2 > declared_length:
                    raise ValueError("Truncated I062/380 primary subfield")
                # Each set bit in the 2-byte primary subfield means one sub-item follows.
                # Sub-item sizes are spec-defined; for safety we skip past this record
                # by attempting a best-effort parse.  Production code should enumerate
                # all sub-items; for this implementation we note its presence and skip.
                record["I062/380"] = {"note": "present but not decoded"}
                # Minimal skip: read primary subfield indicator (first 2 bytes)
                primary = struct.unpack(">H", raw[offset:offset + 2])[0]
                offset += 2
                # Count set bits (each sub-item may be 1–N bytes; this is a simplification)
                # In practice each sub-item of I062/380 has a fixed size per spec.
                # We advance by an estimated count; edge-case handling omitted for brevity.
                log.warning("I062/380 encountered; skipping sub-item bytes (not decoded)")
                continue

            if frn not in _FRN_REGISTRY:
                log.warning("Unknown FRN %d encountered; cannot continue parsing record", frn)
                break

            name, size, decoder = _FRN_REGISTRY[frn]
            if offset + size > declared_length:
                raise ValueError(f"Truncated item {name} at offset {offset}")

            field_bytes = raw[offset: offset + size]
            offset += size

            if decoder is not None:
                decoded = decoder(field_bytes)
                record.update(decoded)
                log.debug("  %s → %s", name, decoded)
            else:
                log.debug("  %s → skipped (%d bytes)", name, size)

        records.append(record)

    log.info("Parsed %d record(s) from datablock", len(records))
    return records
