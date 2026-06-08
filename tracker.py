import sys
import os

def parse_rssi_file(filepath):
    """Parse the RSSI file and calculate average of first 10 readings"""
    
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        sys.exit(1)
    
    rssi_values = []
    lines_read = 0
    
    with open(filepath, 'r') as f:
        for line in f:
            if lines_read >= 10:
                break
                
            line = line.strip()
            if not line:
                continue
            
            # Format: "2026-06-05 16:29:23.964, -80 dBm, 0x02011A1816AAFE..."
            parts = line.split(',')
            
            if len(parts) >= 2:
                timestamp = parts[0].strip()
                rssi_str = parts[1].strip()  # " -80 dBm"
                rssi_value = int(rssi_str.replace(' dBm', '').strip())
                
                rssi_values.append(rssi_value)
                lines_read += 1
                
                print(f"  [{lines_read}] {timestamp} → {rssi_value} dBm")
    
    if rssi_values:
        average = round(sum(rssi_values) / len(rssi_values))
        return average
    
    print("❌ No RSSI values found in file")
    return None

def send_to_api(rssi_average, child_name="Alex Carter", child_id="kid_01"):
    """Send the averaged RSSI to the SafeOrbit API"""
    import requests
    
    payload = {
        "child_id": child_id,
        "child_name": child_name,
        "rssi": rssi_average
    }
    
    try:
        response = requests.post(
            "http://127.0.0.1:8000/api/telemetry", 
            json=payload, 
            timeout=5
        )
        result = response.json()
        
        status = result.get("child_status", "UNKNOWN")
        icon = "✅" if status == "SECURE" else "🚨"
        
        print(f"\n🚀 API Response:")
        print(f"  {icon} Status: {status}")
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Cannot connect to API. Is uvicorn running?")

def main():
    if len(sys.argv) < 2:
        print("Usage: python rssi_parser.py <file.txt> [--send]")
        print("\nExamples:")
        print("  python rssi_parser.py '5E_44_93_66_5C_EB - 2026-06-05 16_29_39.txt'")
        print("  python rssi_parser.py '5E_44_93_66_5C_EB - 2026-06-05 16_29_39.txt' --send")
        sys.exit(1)
    
    filepath = sys.argv[1]
    send_to_backend = "--send" in sys.argv
    
    print(f"📂 Reading file: {filepath}\n")
    
    average = parse_rssi_file(filepath)
    
    if average is not None and send_to_backend:
        send_to_api(average)

if __name__ == "__main__":
    main()