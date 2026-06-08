"""
Incident Management - Child Device Uploader
============================================
Run this on the CHILD'S Android device (via Termux or as a background service).
It watches the CSV file your Bluetooth scanner writes to and streams
every new row to the relay server in real time.

Install:  pip install websockets pandas watchdog
Run:      python child_uploader.py

CONFIG: Edit the values below before running.
"""

import asyncio
import json
import os
import time
import csv
import websockets
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ─── CONFIGURE THESE ────────────────────────────────────────────────
SERVER_URL = "ws://YOUR_SERVER_IP:8765"      # Replace with your server URL
CSV_FILE_PATH = "/path/to/your/scan_output.csv"  # Path to your CSV file
DEVICE_MAC = "5E:44:93:66:5C:EB"            # This device's Bluetooth MAC address
POLL_INTERVAL = 0.5                          # How often to check for new CSV rows (seconds)
# ────────────────────────────────────────────────────────────────────


def estimate_distance_from_rssi(rssi: int, tx_power: int = -59) -> float:
    """
    Estimate distance in metres from RSSI using the log-distance path loss model.
    tx_power: RSSI at 1 metre (calibrate this for your device, -59 is typical BLE)
    """
    if rssi == 0:
        return -1.0
    ratio = rssi / tx_power
    if ratio < 1.0:
        return round(ratio ** 10, 2)
    else:
        return round((0.89976 * (ratio ** 7.7095) + 0.111), 2)


def read_new_rows(filepath: str, last_position: int) -> tuple[list[dict], int]:
    """Read only new rows added since last check."""
    new_rows = []
    try:
        with open(filepath, "r", newline="", encoding="utf-8") as f:
            f.seek(last_position)
            reader = csv.DictReader(f) if last_position == 0 else None

            if last_position == 0:
                # First read — get headers and all rows
                for row in reader:
                    new_rows.append(row)
                new_position = f.tell()
            else:
                # Subsequent reads — raw lines (no header)
                lines = f.readlines()
                # Re-read headers from start to map columns
                f.seek(0)
                headers = f.readline().strip().split(",")
                for line in lines:
                    if line.strip():
                        values = line.strip().split(",")
                        row = dict(zip(headers, values))
                        new_rows.append(row)
                new_position = f.tell()

        return new_rows, new_position
    except FileNotFoundError:
        logger.warning(f"CSV file not found: {filepath}. Waiting...")
        return [], last_position
    except Exception as e:
        logger.error(f"Error reading CSV: {e}")
        return [], last_position


def parse_row(row: dict) -> dict:
    """Convert a CSV row into a clean message payload."""
    try:
        rssi = int(row.get("RSSI", 0))
        distance = estimate_distance_from_rssi(rssi)
        return {
            "timestamp": row.get("Time", datetime.now().isoformat()),
            "rssi": rssi,
            "distance_m": distance,
            "raw_data": row.get("Raw data", ""),
            "connectable": row.get("Connectable", ""),
            "signal_quality": get_signal_quality(rssi)
        }
    except Exception as e:
        logger.warning(f"Could not parse row {row}: {e}")
        return {}


def get_signal_quality(rssi: int) -> str:
    """Human-readable signal quality label."""
    if rssi >= -50:
        return "Excellent"
    elif rssi >= -60:
        return "Good"
    elif rssi >= -70:
        return "Fair"
    elif rssi >= -80:
        return "Weak"
    else:
        return "Very Weak"


async def stream_to_server():
    """Main loop: connect to server and stream CSV updates."""
    last_position = 0
    reconnect_delay = 3

    while True:
        try:
            logger.info(f"Connecting to server: {SERVER_URL}")
            async with websockets.connect(SERVER_URL, ping_interval=20) as ws:
                # Send handshake identifying this as a child device
                await ws.send(json.dumps({
                    "role": "child",
                    "mac": DEVICE_MAC,
                    "timestamp": datetime.now().isoformat()
                }))
                logger.info(f"Connected as child device: {DEVICE_MAC}")
                reconnect_delay = 3  # reset on successful connection

                # Main polling loop
                while True:
                    new_rows, last_position = read_new_rows(CSV_FILE_PATH, last_position)

                    for row in new_rows:
                        payload = parse_row(row)
                        if payload:
                            await ws.send(json.dumps(payload))
                            logger.info(
                                f"Sent → RSSI: {payload['rssi']} dBm | "
                                f"Distance: ~{payload['distance_m']}m | "
                                f"Quality: {payload['signal_quality']}"
                            )

                    await asyncio.sleep(POLL_INTERVAL)

        except websockets.ConnectionClosed as e:
            logger.warning(f"Connection closed: {e}. Reconnecting in {reconnect_delay}s...")
        except ConnectionRefusedError:
            logger.warning(f"Server unreachable. Retrying in {reconnect_delay}s...")
        except Exception as e:
            logger.error(f"Unexpected error: {e}. Retrying in {reconnect_delay}s...")

        await asyncio.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, 60)  # exponential backoff, max 60s


if __name__ == "__main__":
    logger.info("=== Incident Management - Child Device Uploader ===")
    logger.info(f"Watching CSV: {CSV_FILE_PATH}")
    logger.info(f"Device MAC:   {DEVICE_MAC}")
    logger.info(f"Server:       {SERVER_URL}")
    asyncio.run(stream_to_server())
