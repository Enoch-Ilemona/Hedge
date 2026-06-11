import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bleak import BleakScanner
from collections import deque
from datetime import datetime

# --- RELATIONAL DATABASE IMPORTS ---
from sqlalchemy import create_engine, Column, String, Integer, DateTime, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATABASE ENGINE SETUP ---
DATABASE_URL = "sqlite:///./hedge_tracker.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- RELATIONAL DATA MODELS ---

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


def initialize_and_seed_database():
    """Creates database structural tables and seeds presentation mock data rows"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Seed Mock Guardian if absent
        if not db.query(Guardian).filter(Guardian.guardian_id == MOCK_GUARDIAN_ID).first():
            mock_guardian = Guardian(
                guardian_id=MOCK_GUARDIAN_ID,
                name="Aduojo Ilemona",
                phone_number="+2348000000000",
                session_token="session_active_abc123"
            )
            db.add(mock_guardian)
            db.commit()

        # Seed Mock Child relationship mapping
        if not db.query(Child).filter(Child.child_id == CHILD_ID).first():
            mock_child = Child(
                child_id=CHILD_ID,
                guardian_id=MOCK_GUARDIAN_ID,
                name=CHILD_NAME
            )
            db.add(mock_child)
            db.commit()
        print("💾 Relational Database initialized and verified successfully.")
    except Exception as e:
        print(f"Seed warning: {e}")
    finally:
        db.close()


def log_telemetry_to_db(child_id: str, rssi: int, status: str, threshold: int):
    """Inserts a fresh chronological hardware log directly into the beacons table"""
    db = SessionLocal()
    try:
        log_entry = BeaconTelemetry(
            timestamp=datetime.now(),
            beacon_mac=MOCK_BEACON_MAC,
            child_id=child_id,
            rssi_threshold=threshold,
            current_rssi=rssi,
            current_status=status
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        print(f"Database write error: {e}")
    finally:
        db.close()

# --- APP CONFIGURATION PROPERTIES ---
MOCK_GUARDIAN_ID = "g-uuid-1111-2222"
MOCK_BEACON_MAC = "00:1a:7d:da:71:11"

TARGET_NAME = "Melody's A07"  
CHILD_NAME = "Ifeoluwa Olaloye"
CHILD_ID = "CH_01"

# THRESHOLDS
STRONG_THRESHOLD = -70
WEAK_THRESHOLD = -100

# BALANCED buffer - stable but responsive
rssi_buffer = deque(maxlen=5)  
consecutive_not_found = 0
MIN_CONSECUTIVE_FOR_BREACH = 5  
last_status = "INIT"
last_seen_time = datetime.now()  

@app.get("/")
def serve_frontend():
    return FileResponse("index.html")

@app.get("/health")
def health_check():
    return {"status": "Hedge Engine is Running"}

# Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        try:
            await websocket.send_json({
                "child_id": CHILD_ID,
                "child_name": CHILD_NAME,
                "rssi": 0,
                "status": "INIT",
                "message": "System connected, waiting for scan..."
            })
        except:
            pass

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

class BeaconPayload(BaseModel):
    child_id: str
    child_name: str
    rssi: int


async def ble_scanner_task():
    """Optimized low-latency scanner task leveraging a continuous hardware event listener"""
    global last_status, rssi_buffer, consecutive_not_found, last_seen_time
    
    print(f"Scanner initialized in continuous passive listening mode - tracking: {TARGET_NAME}")
    
    def detection_callback(device, adv_data):
        global consecutive_not_found, last_seen_time
        name = adv_data.local_name or device.name
        
        if name and TARGET_NAME.lower() in name.lower():
            consecutive_not_found = 0
            last_seen_time = datetime.now()
            rssi_buffer.append(adv_data.rssi)

    scanner = BleakScanner(detection_callback=detection_callback)
    await scanner.start()
    
    while True:
        try:
            time_since_last_seen = (datetime.now() - last_seen_time).total_seconds()
            if time_since_last_seen > 2.5:
                consecutive_not_found += 1
            
            if rssi_buffer:
                avg_rssi = round(sum(rssi_buffer) / len(rssi_buffer))
                if time_since_last_seen > 1.5:
                    rssi_buffer.popleft()
            else:
                avg_rssi = -120
            
            # Determine Current Security Context State
            if time_since_last_seen <= 2.5:
                if avg_rssi >= STRONG_THRESHOLD:
                    new_status = "SECURE"
                    msg = "Phone inside safe perimeter"
                elif avg_rssi >= WEAK_THRESHOLD:
                    new_status = "NOT_FOUND"
                    msg = "Signal weak - Move closer"
                else:
                    new_status = "BREACH"
                    msg = "Phone out of bounds!"
            else:
                if consecutive_not_found >= MIN_CONSECUTIVE_FOR_BREACH:
                    new_status = "BREACH"
                    msg = "Beacon NOT DETECTED"
                    avg_rssi = -120
                else:
                    new_status = last_status
                    msg = "Searching..."
            
            # RELATIONAL INTEGRATION: Log entry directly inside DB SQL Table
            log_telemetry_to_db(CHILD_ID, avg_rssi, new_status, STRONG_THRESHOLD)
            
            # Broadcast across WebSocket layers instantly
            payload = {
                "child_id": CHILD_ID,
                "child_name": CHILD_NAME,
                "rssi": avg_rssi,
                "status": new_status,
                "message": msg
            }
            await manager.broadcast(payload)
            last_status = new_status
            
            # Clean Output Stream
            if time_since_last_seen <= 2.5:
                print(f"📱 {CHILD_NAME} | RSSI: {avg_rssi} dBm | {new_status}")
            else:
                print(f"🚫 {CHILD_NAME} | NOT FOUND | {new_status} (missed cycles: {consecutive_not_found})")
                
        except Exception as e:
            print(f"Calculation loop warning: {e}")
            
        await asyncio.sleep(1.0)


@app.post("/api/telemetry")
async def receive_telemetry(payload: BeaconPayload):
    if payload.rssi >= STRONG_THRESHOLD:
        status = "SECURE"
    elif payload.rssi >= WEAK_THRESHOLD:
        status = "NOT_FOUND"
    else:
        status = "BREACH"
    
    # Log post payload variables directly to database infrastructure
    log_telemetry_to_db(payload.child_id, payload.rssi, status, STRONG_THRESHOLD)
    
    await manager.broadcast({
        "child_id": payload.child_id,
        "child_name": payload.child_name,
        "rssi": payload.rssi,
        "status": status,
        "message": "Secure" if status == "SECURE" else "Alert!"
    })
    return {"status": "Processed", "child_status": status}

@app.websocket("/ws/monitor")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.on_event("startup")
async def startup_event():
    # Audit and construct SQLite tables cleanly on start
    initialize_and_seed_database()
    asyncio.create_task(ble_scanner_task())
