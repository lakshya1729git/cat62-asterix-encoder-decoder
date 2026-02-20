"""round_trip_test.py — validates encode → decode consistency."""
import sys
sys.path.insert(0, '.')

from encoder import encode_plots
from decoder import decode_datablock

payload = {
    "id": 1,
    "centre_ctrl": [],
    "fpl": {},
    "plots": [
        {
            "I062/105": {"lat": 28.6139, "lon": 77.2090},
            "I062/136": {"measured_flight_level": 100.0},
            "I062/185": {"vx": 50.0, "vy": 100.0},
            "I062/220": {"rocd": 500.0},
            "time_of_track": "2026-02-21T09:48:00Z"
        },
        {
            "I062/105": {"lat": 19.0760, "lon": 72.8777},
            "I062/136": {"measured_flight_level": 350.0},
            "I062/185": {"vx": -75.5, "vy": 200.25},
            "I062/220": {"rocd": -312.5},
            "time_of_track": "2026-02-21T14:22:15.5Z"
        }
    ]
}

# --- Encode ---
datablock = encode_plots(payload)
print(f"[ENCODE] Datablock: {len(datablock)} bytes")
print(f"[ENCODE] Category byte: 0x{datablock[0]:02X}  (expected 0x3E = 62)")
print(f"[ENCODE] Declared length: {int.from_bytes(datablock[1:3], 'big')} bytes")
print(f"[ENCODE] First 30 hex bytes: {datablock[:30].hex().upper()}")

# --- Decode ---
result = decode_datablock(datablock, reference_date="2026-02-21")
print(f"\n[DECODE] Count: {result['count']}")
for rec in result["records"]:
    print(
        f"  TN={rec['track_number']}  pos={rec['position']}  "
        f"FL={rec['measured_flight_level_FL']}  "
        f"speed={rec['ground_speed_ms']} m/s  "
        f"heading={rec['heading_deg']}°  "
        f"rocd={rec['rate_of_climb_descent_ftmin']} ft/min  "
        f"time={rec['time_of_track_iso']}"
    )

# --- Round-trip assertions ---
p0 = payload["plots"][0]
r0 = result["records"][0]
assert abs(r0["position"]["lat"] - p0["I062/105"]["lat"]) < 1e-4, "lat mismatch"
assert abs(r0["position"]["lon"] - p0["I062/105"]["lon"]) < 1e-4, "lon mismatch"
assert abs(r0["measured_flight_level_FL"] - p0["I062/136"]["measured_flight_level"]) < 1.0, "FL mismatch"
assert abs(r0["velocity"]["vx_ms"] - p0["I062/185"]["vx"]) < 1.0, "vx mismatch"
assert abs(r0["velocity"]["vy_ms"] - p0["I062/185"]["vy"]) < 1.0, "vy mismatch"
assert abs(r0["rate_of_climb_descent_ftmin"] - p0["I062/220"]["rocd"]) < 10.0, "rocd mismatch"

p1 = payload["plots"][1]
r1 = result["records"][1]
assert abs(r1["position"]["lat"] - p1["I062/105"]["lat"]) < 1e-4, "lat mismatch plot2"
assert abs(r1["position"]["lon"] - p1["I062/105"]["lon"]) < 1e-4, "lon mismatch plot2"
assert abs(r1["measured_flight_level_FL"] - p1["I062/136"]["measured_flight_level"]) < 1.0, "FL mismatch plot2"

print("\n[VALIDATE] All round-trip assertions PASSED ✓")
