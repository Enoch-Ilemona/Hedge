import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Enable CORS - allows frontend to connect from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the index.html at root
@app.get("/")
def serve_frontend():
    return FileResponse("index.html")

# Track active WebSocket connections (the parent dashboards)
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

# Data structure for incoming beacon simulations
class BeaconPayload(BaseModel):
    child_id: str
    child_name: str
    rssi: int  # Signal strength (e.g., -60 is strong, -95 is weak)

@app.get("/health")
def health_check():
    return {"status": "SafeOrbit Engine is Running"}

# Endpoint for your simulation script to POST data into
@app.post("/api/telemetry")
async def receive_telemetry(payload: BeaconPayload):
    # Core Logic: If RSSI drops below -85, it's a breach
    SAFE_THRESHOLD = -85
    status = "SECURE" if payload.rssi >= SAFE_THRESHOLD else "BREACH"
    
    alert_data = {
        "child_id": payload.child_id,
        "child_name": payload.child_name,
        "rssi": payload.rssi,
        "status": status,
        "message": "Child inside safe perimeter" if status == "SECURE" else "ALERT: Child out of bounds!"
    }
    
    # Push the data instantly over WebSockets to the web app frontend
    await manager.broadcast(alert_data)
    return {"status": "Processed", "child_status": status}

# WebSocket route for the Parent Web App to listen to
@app.websocket("/ws/monitor")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)