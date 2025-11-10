import json
import csv
import threading
import paho.mqtt.client as mqtt
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from collections import deque

# ===============================
# Configuration
# ===============================
MQTT_BROKER = "192.168.4.12"
MQTT_PORT = 1883
MQTT_TOPIC = "Sensor/s105"
CSV_FILE = "accel_data.csv"
MAX_POINTS = 4600
INITIAL_POINTS = 100  # warm-up buffer

# ===============================
# Data buffers
# ===============================
x_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)
y_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)
z_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)
msg_queue = deque()
data_lock = threading.Lock()

# ===============================
# CSV Logging
# ===============================
def log_to_csv(samples, filename=CSV_FILE):
    with open(filename, 'a', newline='') as f:
        writer = csv.writer(f)
        for s in samples:
            writer.writerow([s['t'], s['x'], s['y'], s['z']])

# ===============================
# MQTT Callbacks
# ===============================
def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker with code {rc}")
    client.subscribe(MQTT_TOPIC)
    print(f"Subscribed to {MQTT_TOPIC}")


def on_message(client, userdata, msg):
    payload = json.loads(msg.payload)
    samples = payload.get('samples', [])
    with data_lock:
        msg_queue.extend(samples)
    log_to_csv(samples)

# ===============================
# Plot setup
# ===============================
fig, ax = plt.subplots()
line_x, = ax.plot([], [], label='X', color='r')
line_y, = ax.plot([], [], label='Y', color='g')
line_z, = ax.plot([], [], label='Z', color='b')

ax.set_ylim(-22, 22)  # adjust if needed
ax.set_xlim(0, MAX_POINTS)
ax.set_xlabel("Sample")
ax.set_ylabel("Acceleration (g)")
ax.legend()

# ===============================
# Update function
# ===============================
def update(frame):
    # Pull all messages from queue
    with data_lock:
        while msg_queue:
            s = msg_queue.popleft()
            x_data.append(s['x'])
            y_data.append(s['y'])
            z_data.append(s['z'])

    line_x.set_data(range(len(x_data)), list(x_data))
    line_y.set_data(range(len(y_data)), list(y_data))
    line_z.set_data(range(len(z_data)), list(z_data))

    ax.set_xlim(max(0, len(x_data)-MAX_POINTS), len(x_data))
    return line_x, line_y, line_z

# ===============================
# Start animation
# ===============================
ani = FuncAnimation(fig, update, interval=50, blit=False)

# ===============================
# MQTT Client
# ===============================
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

# ===============================
# Show plot
# ===============================
plt.show()
client.loop_stop()
