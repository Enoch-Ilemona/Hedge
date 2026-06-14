"""
CLOUD API SERVER MODULE
=======================
Runs on Render.com to handle WebSocket connections, database logging,
and real-time status broadcasting to the frontend (index.html).

This module receives RSSI data from local_ble_scanner.py and:
1. Logs telemetry to SQLite database
2. Broadcasts status updates via WebSocket to connected clients
3. Serves the frontend HTML dashboard

Deploy this to Render.com:
- Build: pip install -r requirements.txt
- Start: uvicorn cloud_api_server:app --host 0.0.0.0 --port 8000
"""

import asyncio
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Database imports
from sqlalchemy import create_engine, Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- FastAPI App Setup ---
app = FastAPI(title="Hedge Cloud API", version="1.0")

# Enable CORS for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATABASE CONFIGURATION ---
# Use SQLite for simplicity; upgrade to PostgreSQL for production
DATABASE_URL = "sqlite:///./hedge_tracker.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- DATABASE MODELS ---
class Guardian(Base):
    __tablename__ = "guardians"
    guardian_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    session_token = Column(String, nullable=True)


class Child(Base):
    __tablename__ = "children"
    child_id = Column(String, primary_key=True, index=True)
    guardian_id = Column(String, ForeignKey("guardians.guardian_id"), nullable=False)
    name = Column(String, nullable=False)


class BeaconTelemetry(Base):
    __tablename__ = "beacons"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    beacon_mac = Column(String, nullable=False)
    child_id = Column(String, ForeignKey("children.child_id"), nullable=False)
    rssi_threshold = Column(Integer, nullable=False)
    current_rssi = Column(Integer, nullable=False)
    current_status = Column(String, nullable=False)


# --- CONFIGURATION ---
MOCK_GUARDIAN_ID = "g-uuid-1111-2222"
MOCK_BEACON_MAC = "00:1a:7d:da:71:11"
CHILD_ID = "CH_01"
CHILD_NAME = "Ifeoluwa Olaloye"

# Thresholds
STRONG_THRESHOLD = -70
WEAK_THRESHOLD = -100


# --- DATABASE FUNCTIONS ---
def initialize_and_seed_database():
    """Creates database tables and seeds mock data"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(Guardian).filter(Guardian.guardian_id == MOCK_GUARDIAN_ID).first():
            mock_guardian = Guardian(
                guardian_id=MOCK_GUARDIAN_ID,
                name="Aduojo Ilemona",
                phone_number="+2348000000000",
                session_token="session_active_abc123",
            )
            db.add(mock_guardian)
            db.commit()

        if not db.query(Child).filter(Child.child_id == CHILD_ID).first():
            mock_child = Child(
                child_id=CHILD_ID,
                guardian_id=MOCK_GUARDIAN_ID,
                name=CHILD_NAME,
            )
            db.add(mock_child)
            db.commit()
        print("💾 Database initialized and verified successfully.")
    except Exception as e:
        print(f"Seed warning: {e}")
    finally:
        db.close()


def log_telemetry_to_db(child_id: str, rssi: int, status: str, threshold: int):
    """Logs telemetry reading to database"""
    db = SessionLocal()
    try:
        log_entry = BeaconTelemetry(
            timestamp=datetime.now(),
            beacon_mac=MOCK_BEACON_MAC,
            child_id=child_id,
            rssi_threshold=threshold,
            current_rssi=rssi,
            current_status=status,
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        print(f"Database write error: {e}")
    finally:
        db.close()


# --- WEBSOCKET CONNECTION MANAGER ---
class ConnectionManager:
    """Manages WebSocket connections for real-time broadcasting"""

    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        try:
            await websocket.send_json(
                {
                    "child_id": CHILD_ID,
                    "child_name": CHILD_NAME,
                    "rssi": 0,
                    "status": "INIT",
                    "message": "System connected, waiting for telemetry...",
                }
            )
        except:
            pass

    def disconnect(self, websocket: WebSocket):
        """Remove disconnected WebSocket"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass


manager = ConnectionManager()


# --- API MODELS ---
class BeaconPayload(BaseModel):
    """Payload from local BLE scanner"""
    child_id: str
    child_name: str
    rssi: int


# --- FRONTEND ROUTE ---
@app.get("/")
def serve_frontend():
    """Serve the dashboard HTML"""
    return FileResponse("index.html")


# --- HEALTH CHECK ---
@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "Hedge Cloud API is Running"}


# --- TELEMETRY ENDPOINT ---
@app.post("/api/telemetry")
async def receive_telemetry(payload: BeaconPayload):
    """
    Receives RSSI telemetry from local BLE scanner.
    
    Called by: local_ble_scanner.py
    Triggered by: Every 1 second poll from local scanner
    
    Args:
        payload: {child_id, child_name, rssi}
    
    Returns:
        {status: "Processed", child_status: "SECURE|NOT_FOUND|BREACH"}
    """
    # Determine security status based on RSSI threshold
    if payload.rssi >= STRONG_THRESHOLD:
        status = "SECURE"
    elif payload.rssi >= WEAK_THRESHOLD:
        status = "NOT_FOUND"
    else:
        status = "BREACH"

    # Log to database
    log_telemetry_to_db(payload.child_id, payload.rssi, status, STRONG_THRESHOLD)

    # Broadcast to all connected WebSocket clients
    broadcast_payload = {
        "child_id": payload.child_id,
        "child_name": payload.child_name,
        "rssi": payload.rssi,
        "status": status,
        "message": "Secure" if status == "SECURE" else "Alert!",
    }
    await manager.broadcast(broadcast_payload)

    print(
        f"📊 Telemetry logged: {payload.child_name} | RSSI: {payload.rssi} dBm | Status: {status}"
    )

    return {"status": "Processed", "child_status": status}


# --- WEBSOCKET ENDPOINT ---
@app.websocket("/ws/monitor")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for frontend real-time dashboard updates.
    
    Connected by: index.html JavaScript
    Receives broadcasts from: /api/telemetry endpoint
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and listen for messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("🔌 WebSocket client disconnected")


# --- STARTUP EVENT ---
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    initialize_and_seed_database()
    print("✅ Cloud API Server started successfully!")
    print("📱 Waiting for telemetry from local BLE scanner...")
