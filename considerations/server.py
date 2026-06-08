"""
Incident Management - WebSocket Relay Server
============================================
Run this on a cloud server (Railway, Render, etc.)
It receives data from the child's device and broadcasts
it to the parent's browser dashboard in real time.

Install:  pip install websockets
Run:      python server.py
"""

import asyncio
import json
import websockets
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Store connected clients by role
child_devices = {}   # mac_address -> websocket
parent_clients = set()  # all parent browser connections
latest_data = {}     # mac_address -> last known reading (for new parents joining)


async def broadcast_to_parents(message: dict):
    """Send a message to all connected parent dashboards."""
    if parent_clients:
        data = json.dumps(message)
        disconnected = set()
        for ws in parent_clients:
            try:
                await ws.send(data)
            except websockets.ConnectionClosed:
                disconnected.add(ws)
        parent_clients.difference_update(disconnected)


async def handle_connection(websocket):
    """Handle each incoming WebSocket connection."""
    client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
    role = None
    device_mac = None

    try:
        # First message must identify the role
        raw = await asyncio.wait_for(websocket.recv(), timeout=10)
        handshake = json.loads(raw)
        role = handshake.get("role")  # "child" or "parent"

        if role == "child":
            device_mac = handshake.get("mac", "UNKNOWN")
            child_devices[device_mac] = websocket
            logger.info(f"Child device connected: {device_mac} from {client_ip}")

            # Notify parents a child connected
            await broadcast_to_parents({
                "type": "device_connected",
                "mac": device_mac,
                "timestamp": datetime.now().isoformat()
            })

            # Keep receiving data from child and relay to parents
            async for message in websocket:
                try:
                    data = json.loads(message)
                    data["mac"] = device_mac
                    data["type"] = "location_update"
                    latest_data[device_mac] = data  # cache for late-joining parents
                    await broadcast_to_parents(data)
                    logger.info(f"Relayed update from {device_mac}: RSSI={data.get('rssi')}")
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from child {device_mac}")

        elif role == "parent":
            parent_clients.add(websocket)
            logger.info(f"Parent connected from {client_ip}. Total parents: {len(parent_clients)}")

            # Send current known state of all child devices immediately
            if latest_data:
                await websocket.send(json.dumps({
                    "type": "initial_state",
                    "devices": list(latest_data.values())
                }))

            # Keep connection alive (parents only receive, don't send)
            await websocket.wait_closed()

        else:
            logger.warning(f"Unknown role from {client_ip}: {role}")
            await websocket.close(1008, "Unknown role. Send 'child' or 'parent'.")

    except asyncio.TimeoutError:
        logger.warning(f"Handshake timeout from {client_ip}")
    except websockets.ConnectionClosed:
        logger.info(f"Connection closed: role={role}, mac={device_mac}")
    except Exception as e:
        logger.error(f"Error handling connection: {e}")
    finally:
        # Clean up on disconnect
        if role == "child" and device_mac and device_mac in child_devices:
            del child_devices[device_mac]
            await broadcast_to_parents({
                "type": "device_disconnected",
                "mac": device_mac,
                "timestamp": datetime.now().isoformat()
            })
            logger.info(f"Child device disconnected: {device_mac}")
        elif role == "parent":
            parent_clients.discard(websocket)
            logger.info(f"Parent disconnected. Remaining: {len(parent_clients)}")


async def main():
    host = "0.0.0.0"
    port = 8765
    logger.info(f"Starting Incident Management WebSocket server on ws://{host}:{port}")
    async with websockets.serve(handle_connection, host, port):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
