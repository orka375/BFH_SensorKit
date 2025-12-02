import json
import random
import time
import subprocess
import re
import paho.mqtt.client as mqtt

# ----------- Detect the single connected client -----------
def get_single_client_ip():
    """Return the IP of the single client connected to wlan0."""
    # Get MAC addresses using iw
    try:
        iw_output = subprocess.check_output(["iw", "dev", "wlan0", "station", "dump"], text=True)
        macs = re.findall(r"Station ([0-9a-f:]{17})", iw_output)
        if not macs:
            return None
        mac = macs[0]  # pick the first (and only) client
    except subprocess.CalledProcessError:
        return None

    # Map MAC to IP using arp
    try:
        arp_output = subprocess.check_output(["arp", "-n"], text=True)
        ip_map = {}
        for line in arp_output.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                ip_addr, _, mac_addr = parts[0], parts[1], parts[2]
                ip_map[mac_addr.lower()] = ip_addr
        return ip_map.get(mac.lower())
    except subprocess.CalledProcessError:
        return None

# Wait until a client connects
broker_ip = None
print("Waiting for a client to connect to the Pi AP...")
while broker_ip is None:
    broker_ip = get_single_client_ip()
    time.sleep(1)

print(f"Detected client IP: {broker_ip}")

# ----------- MQTT Setup -----------
topic = "sensors/accel"


client = mqtt.Client(client_id="sim_accel_pub", callback_api_version=1)

retry_delay = 5  # seconds between retries

while True:
    try:
        client.connect(broker_ip, 1883, 60)
        print(f"Connected to MQTT broker at {broker_ip}")
        break  # exit loop if successful
    except TimeoutError:
        time.sleep(retry_delay)

client.loop_start()
print(f"Publishing accelerometer data to {broker_ip}...")

# ----------- Simulated accelerometer loop -----------
try:
    while True:
        data = {
            "x": round(random.uniform(-1, 1), 3),
            "y": round(random.uniform(-1, 1), 3),
            "z": round(random.uniform(-1, 1), 3)
        }
        payload = json.dumps(data)
        client.publish(topic, payload)
        print(f"Published: {payload}")
        time.sleep(0.001)

except KeyboardInterrupt:
    print("\nStopping publisher...")
    client.loop_stop()
    client.disconnect()
