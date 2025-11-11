import json
import socket
import time
import subprocess
from gpiozero import RGBLED, Button, DigitalInputDevice
from mpu6050 import mpu6050

# =============== CONFIG ===============
UDP_PORT = 1883
SEND_INTERVAL = 0.1       # seconds
# ======================================

led = RGBLED(red=13, green=19, blue=6)
button1 = Button(10, pull_up=False)
button2 = Button(9, pull_up=False)

# -------------------------------
# Function: Detect connected client IP
# -------------------------------
def get_single_client_ip():
    """
    Checks the ARP table for a connected Wi-Fi client.
    Returns IP as string, or None if no client found.
    """
    try:
        result = subprocess.run(
            ["arp", "-n"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if "wlan0" in line and "incomplete" not in line:
                parts = line.split()
                if len(parts) >= 1 and parts[0].count('.') == 3:
                    return parts[0]
    except Exception as e:
        print("Error getting client IP:", e)
    return None

# -------------------------------
# Wait for receiver to connect
# -------------------------------
def connectHost():
    print("Waiting for a client to connect to the Pi AP...")
    client_ip = None
    while client_ip is None:
        client_ip = get_single_client_ip()
        if client_ip:
            print(f"Detected receiver IP: {client_ip}")
            return client_ip
        time.sleep(1)

# -------------------------------
# Frequency sensor setup
# -------------------------------
freq_pin = DigitalInputDevice(21)
last_edge_time = None
frequency = 0.0

def on_rising_edge():
    global last_edge_time, frequency
    now = time.time()
    if last_edge_time is not None:
        period = now - last_edge_time
        if period > 0:
            frequency = 1.0 / period
    last_edge_time = now

freq_pin.when_activated = on_rising_edge

# -------------------------------
# MPU setup
# -------------------------------
addresses = [0x68, 0x69]
sensors = []
names = ["s104", "s105"]

for addr in addresses:
    try:
        s = mpu6050(addr)
        sensors.append(s)
        print(f"Connected to MPU6050 at 0x{addr:02X}")
    except Exception as e:
        print(f"Failed to connect to MPU6050 at 0x{addr:02X}: {e}")

# -------------------------------
# Connect to receiver
# -------------------------------
receiver_ip = connectHost()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
print(f"Sending UDP packets to {receiver_ip}:{UDP_PORT}")

# -------------------------------
# Main loop
# -------------------------------
led.color = (0, 1, 0)
last_send = time.time()

while True:
    try:
        now = time.time()
        if now - last_send >= SEND_INTERVAL:
            # Send MPU data
            for i, s in enumerate(sensors):
                accel = s.get_accel_data()
                payload = {
                    "topic": f"Sensor/{names[i]}",
                    "timestamp": time.time_ns(),
                    "samples": [{
                        "t": time.time_ns(),
                        "x": round(accel["x"], 3),
                        "y": round(accel["y"], 3),
                        "z": round(accel["z"], 3)
                    }]
                }
                sock.sendto(json.dumps(payload).encode(), (receiver_ip, UDP_PORT))
                print(f"Sent {names[i]} data")

            # Send frequency data
            freq_payload = {
                "topic": "Sensor/Frequency",
                "timestamp": time.time_ns(),
                "frequency_hz": round(frequency, 2)
            }
            sock.sendto(json.dumps(freq_payload).encode(), (receiver_ip, UDP_PORT))
            print(f"Sent frequency: {frequency:.2f} Hz")

            last_send = now

    except KeyboardInterrupt:
        print("Stopped by user.")
        led.off()
        break
    except Exception as e:
        print("Error:", e)
        time.sleep(1)
