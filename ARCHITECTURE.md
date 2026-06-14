# Hedge - Modular Architecture

## Overview

This is the **modular-approach** branch that splits the original monolithic `server.py` into two independent, scalable components:

### Architecture

```
┌─────────────────────────────┐
│   LOCAL MACHINE             │
│   local_ble_scanner.py      │
│  (BLE Hardware Scanning)    │
└─────────────┬───────────────┘
              │ HTTP POST
              │ /api/telemetry
              │
              ▼
┌─────────────────────────────┐
│   RENDER.COM CLOUD          │
│   cloud_api_server.py       │
│  (API, WebSocket, DB)       │
└─────────────┬───────────────┘
              │ WebSocket
              │ /ws/monitor
              │
              ▼
┌─────────────────────────────┐
│   BROWSER                   │
│   index.html                │
│  (Dashboard UI)             │
└─────────────────────────────┘
```

## Components

### 1. **local_ble_scanner.py** (Local Machine)
- Runs on your laptop/desktop with Bluetooth
- Continuously scans for BLE beacons
- Calculates RSSI signal strength every 1 second
- **Sends telemetry to cloud API** via HTTP POST
- Lightweight and focused on hardware interaction

**Key Features:**
- Asynchronous BLE scanning with `bleak`
- RSSI buffering for signal smoothing
- Automatic breach detection
- Error handling and reconnection logic

**Dependencies:**
- `bleak` - BLE scanning library
- `requests` - HTTP client for cloud API communication

### 2. **cloud_api_server.py** (Render.com)
- FastAPI web server hosted on Render.com
- Receives RSSI telemetry from local scanner
- Broadcasts real-time updates to frontend via WebSocket
- Logs all telemetry to SQLite database
- Serves the dashboard HTML interface

**Key Features:**
- RESTful API endpoint `/api/telemetry`
- WebSocket endpoint `/ws/monitor` for real-time updates
- SQLite database with Guardian, Child, and BeaconTelemetry tables
- CORS enabled for cross-origin requests
- Health check endpoint for monitoring

**Dependencies:**
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `sqlalchemy` - ORM for database
- `pydantic` - Data validation

### 3. **index.html** (Browser Frontend)
- Responsive dashboard UI
- Real-time status display (SECURE/WEAK/LOST)
- WebSocket connection for live updates
- Color-coded alerts (green/yellow/red)
- Sound alerts for breach events

## Deployment

### Local Setup
```bash
# Clone and checkout modular branch
git clone https://github.com/Enoch-Ilemona/Hedge.git
cd Hedge
git checkout modular-approach

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install bleak requests
```

### Cloud Deployment (Render.com)
1. Sign up at https://render.com
2. Create new Web Service
3. Connect GitHub repository
4. Configure:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn cloud_api_server:app --host 0.0.0.0 --port 8000`
5. Get your Render URL (e.g., `https://hedge-api-xyz.onrender.com`)

### Configuration
Update `local_ble_scanner.py` with your Render URL:
```python
CLOUD_API_BASE_URL = "https://hedge-api-xyz.onrender.com"
```

## Running the System

**Terminal 1 - Local Scanner:**
```bash
python local_ble_scanner.py
```

**Terminal 2 - Open Dashboard:**
```
https://your-render-url.onrender.com/
```

## Data Flow

1. **BLE Detection:** Beacon sends BLE advertisement
2. **Local Scan:** `local_ble_scanner.py` detects and calculates RSSI
3. **HTTP Request:** Sends `{child_id, child_name, rssi}` to cloud API
4. **API Processing:** Cloud server logs to database and validates status
5. **WebSocket Broadcast:** Status pushed to all connected browsers
6. **Dashboard Update:** `index.html` receives update via WebSocket and re-renders

## Advantages of Modular Approach

| Feature | Original | Modular |
|---------|----------|---------|
| **Deployment** | Single monolith | Independent scaling |
| **Maintenance** | Coupled concerns | Separated responsibilities |
| **Local Performance** | Full FastAPI overhead | Lightweight HTTP client |
| **Cloud Cost** | Heavy polling | Only stores & broadcasts |
| **Scalability** | Limited | Multiple local scanners → 1 cloud server |
| **Offline Support** | None | Local scanner keeps running |
| **Hardware Dependency** | Required everywhere | Only on local machine |

## File Structure

```
modular-approach/
├── local_ble_scanner.py      # ← Local machine component
├── cloud_api_server.py       # ← Cloud server component
├── index.html                # ← Frontend dashboard
├── tracker.py                # ← Utility for testing
├── requirements.txt          # ← Python dependencies
├── ARCHITECTURE.md           # ← This file
└── LICENSE
```

## Configuration Options

### local_ble_scanner.py
```python
TARGET_NAME = "Melody's A07"              # Beacon name to track
CHILD_ID = "CH_01"                        # Child identifier
CHILD_NAME = "Ifeoluwa Olaloye"          # Child name
STRONG_THRESHOLD = -70                    # dBm: secure range
WEAK_THRESHOLD = -100                     # dBm: warning range
RSSI_BUFFER_SIZE = 5                      # Samples for averaging
SCAN_INTERVAL = 1.0                       # Seconds between polls
CLOUD_API_BASE_URL = "https://..."       # Your Render URL
```

### cloud_api_server.py
```python
MOCK_GUARDIAN_ID = "g-uuid-1111-2222"    # Mock guardian for demo
MOCK_BEACON_MAC = "00:1a:7d:da:71:11"   # Mock beacon MAC
DATABASE_URL = "sqlite:///..."            # SQLite database path
```

## API Endpoints

### Cloud Server

**POST /api/telemetry**
- Receives RSSI data from local scanner
- Request: `{child_id, child_name, rssi}`
- Response: `{status: "Processed", child_status: "SECURE|NOT_FOUND|BREACH"}`

**GET /health**
- Health check endpoint
- Response: `{status: "Hedge Cloud API is Running"}`

**GET /**
- Serves dashboard HTML

**WebSocket /ws/monitor**
- Real-time updates to connected clients
- Receives broadcasted telemetry messages

## Troubleshooting

### Local Scanner Can't Find Beacon
- Enable Bluetooth on your machine
- Verify beacon is broadcasting
- Check beacon name matches `TARGET_NAME`

### Can't Connect to Cloud API
- Verify Render deployment is successful
- Check `CLOUD_API_BASE_URL` is correct
- Test: `curl https://your-url/health`

### Dashboard Not Updating
- Check browser console (F12) for WebSocket errors
- Verify local scanner is running
- Check Render logs for API errors

## Future Enhancements

- [ ] Multi-scanner support (multiple local scanners → single cloud)
- [ ] PostgreSQL for production deployments
- [ ] Authentication & authorization
- [ ] Historical data analytics
- [ ] Mobile app integration
- [ ] Push notifications
- [ ] Geofencing with multiple beacons
- [ ] Machine learning for anomaly detection

## License

MIT License - See LICENSE file
