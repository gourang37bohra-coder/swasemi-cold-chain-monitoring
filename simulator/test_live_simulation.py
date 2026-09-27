"""Live end-to-end integration test of the device simulator against public MQTT broker."""

import asyncio
import datetime
import json
import time
import urllib.request
import websockets

import sys
from pathlib import Path

# Add project root to sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from simulator.config import SimulatorSettings, TrackerConfig
from simulator.engine import SimulatorEngine


async def run_live_test():
    print("=" * 60)
    print("MODEL 8: LIVE SIMULATOR INTEGRATION TEST")
    print("=" * 60)

    # 1. Login to get JWT for WebSocket monitoring and shipment API
    login_req = urllib.request.Request(
        "http://127.0.0.1:8000/auth/login",
        data=json.dumps({"email": "operator@apexpharma.com", "password": "Password@123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(login_req, timeout=5.0) as resp:
        token = json.loads(resp.read().decode("utf-8"))["access_token"]
    print("[TEST] Logged in successfully. Bearer token acquired.")

    # 2. Connect WebSocket client to observe live incoming events
    ws_url = f"ws://127.0.0.1:8000/ws/telemetry?token={token}"
    print(f"[TEST] Connecting WebSocket to {ws_url}...")
    
    async with websockets.connect(ws_url) as ws:
        handshake = json.loads(await ws.recv())
        print(f"[TEST] WebSocket Handshake received: {handshake['type']}")
        assert handshake["type"] == "connection.established"

        # 3. Instantiate and start SimulatorEngine
        settings = SimulatorSettings(
            publish_interval_seconds=3.0,
            shipment_refresh_interval_seconds=5.0,
        )
        engine = SimulatorEngine(settings)
        engine.mqtt_client.connect(settings.mqtt_broker_host, settings.mqtt_broker_port, 60)
        engine.mqtt_client.loop_start()
        time.sleep(1.0)
        engine.refresh_shipments()

        # Print initial tracker states
        print("\n--- INITIAL TRACKER FLEET STATUS ---")
        for tid, t in engine.trackers.items():
            active_str = f"ACTIVE (Shipment {t.active_shipment.shipment_id[:8]}...)" if t.is_active else "INACTIVE (No Shipment)"
            print(f"  Tracker: {t.name:<18} | ID: {t.tracker_id} | Status: {active_str}")

        # 4. Run Cycle 1: All 3 active trackers should publish
        print("\n--- EXECUTION: SIMULATION CYCLE 1 (3 Active Trackers) ---")
        published_c1 = engine.publish_cycle()
        print(f"[TEST] Cycle 1 published {published_c1} messages.")
        assert published_c1 == 3, f"Expected 3 active trackers to publish, got {published_c1}"

        # Receive WebSocket events for cycle 1
        received_c1 = {}
        for _ in range(3):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10.0))
            if msg.get("type") == "telemetry.updated":
                t_id = msg["data"]["tracker_id"]
                received_c1[t_id] = msg["data"]
                print(f"  [WS-RECV] Tracker {t_id[:8]} | Temp: {msg['data']['temperature']}°C | GPS: {msg['data']['latitude']}, {msg['data']['longitude']}")

        assert len(received_c1) == 3, "WebSocket did not receive events for all 3 active trackers!"

        # 5. Run Cycle 2: Verify GPS coordinates advance (moving trackers)
        print("\n--- EXECUTION: SIMULATION CYCLE 2 (Verifying GPS Movement) ---")
        time.sleep(2.0)
        published_c2 = engine.publish_cycle()
        assert published_c2 == 3

        received_c2 = {}
        for _ in range(3):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10.0))
            if msg.get("type") == "telemetry.updated":
                t_id = msg["data"]["tracker_id"]
                received_c2[t_id] = msg["data"]

        # Verify GPS moved for each tracker
        for t_id in received_c1:
            loc1 = (received_c1[t_id]["latitude"], received_c1[t_id]["longitude"])
            loc2 = (received_c2[t_id]["latitude"], received_c2[t_id]["longitude"])
            print(f"  [MOVEMENT] Tracker {t_id[:8]} moved: {loc1} -> {loc2}")
            assert loc1 != loc2, f"Tracker {t_id} did not move between cycles!"

        # 6. Lifecycle Gate Test: End shipment for Medical_UnitB
        med_b_id = "05d3d094-58c7-41ff-b57e-a772948539d6"
        med_b_shipment = engine.trackers[med_b_id].active_shipment.shipment_id
        print(f"\n--- LIFECYCLE GATE: ENDING SHIPMENT {med_b_shipment} FOR Medical_UnitB ---")
        
        complete_req = urllib.request.Request(
            f"http://127.0.0.1:8000/shipments/{med_b_shipment}/complete",
            data=b"{}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(complete_req, timeout=5.0) as resp:
            comp_res = json.loads(resp.read().decode("utf-8"))
            print(f"[TEST] Shipment completed successfully: status={comp_res['status']}")
            assert comp_res["status"] == "COMPLETED"

        # Force gate refresh
        engine.refresh_shipments()
        assert not engine.trackers[med_b_id].is_active, "Medical_UnitB must now be INACTIVE!"
        print(f"[TEST] Medical_UnitB is now INACTIVE. Gating should skip publishing.")

        # 7. Run Cycle 3: Only the 2 remaining active trackers should publish
        print("\n--- EXECUTION: SIMULATION CYCLE 3 (Verifying Inactive Tracker Stops) ---")
        published_c3 = engine.publish_cycle()
        print(f"[TEST] Cycle 3 published {published_c3} messages.")
        assert published_c3 == 2, f"Expected exactly 2 active trackers to publish, got {published_c3}"

        received_c3 = []
        for _ in range(2):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10.0))
            if msg.get("type") == "telemetry.updated":
                received_c3.append(msg["data"]["tracker_id"])

        assert med_b_id not in received_c3, "CRITICAL ERROR: Medical_UnitB telemetry published after shipment completed!"
        print(f"[TEST] Confirmed: Medical_UnitB telemetry stopped completely. Remaining trackers continue.")

        # Cleanup
        engine.mqtt_client.loop_stop()
        engine.mqtt_client.disconnect()
        print("\n" + "=" * 60)
        print("ALL LIVE INTEGRATION CHECKS PASSED SUCCESSFULLY!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_live_test())
