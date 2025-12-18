import json
import csv
import threading
import paho.mqtt.client as mqtt
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from collections import deque
import time
import os
from tkinter import messagebox
import tkinter as tk

# ===============================
# Configuration
# ===============================
MQTT_BROKER = "192.168.4.1"
MQTT_PORT = 1883

TOPIC_SENSOR1 = "Sensor/s104"
TOPIC_SENSOR2 = "Sensor/s105"
TOPIC_EDGES   = "Sensor/Frequency"   # now edge timestamps

MAX_POINTS = 4600
INITIAL_POINTS = 100

timestring = time.strftime("%d_%m_%H_%M_%S")
CSV_FILE = ("C:/Users/fra4/OneDrive - Berner Fachhochschule/Desktop/Messungen/"f"Messung_{timestring}.csv")
# CSV_FILE = f"Messdaten/Messung_{timestring}.csv"

# ===============================
# Data buffers
# ===============================
# Accelerometer data
x1_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)
y1_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)
z1_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)

x2_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)
y2_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)
z2_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)

# Rising edge timestamps
edge_data = deque(maxlen=MAX_POINTS)

# Message queues
msg_queue1 = deque()
msg_queue2 = deque()
msg_queue_edges = deque()

data_lock = threading.Lock()

# Activity flags
sensor1_active = False
sensor2_active = False
edges_active = False

# ===============================
# CSV Logging
# ===============================
csv_lock = threading.Lock()

SENSOR_CSV_FILE = CSV_FILE
EDGE_CSV_FILE = CSV_FILE.replace(".csv", "_edges.csv")

# Write headers
with csv_lock:
    with open(SENSOR_CSV_FILE, "w", newline="") as f:
        csv.writer(f).writerow(
            ["timestamp", "x1", "y1", "z1", "x2", "y2", "z2"]
        )

    with open(EDGE_CSV_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["edge_timestamp"])

latest_s1 = {"x": "", "y": "", "z": ""}
latest_s2 = {"x": "", "y": "", "z": ""}

def log_sensor_samples(s1_samples=None, s2_samples=None):
    """
    Logs all sensor samples to the main CSV file.
    Each sample has its own 't' field (time since run start in seconds).
    """
    global latest_s1, latest_s2

    with csv_lock:
        with open(SENSOR_CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)

            if s1_samples:
                for s in s1_samples:
                    latest_s1 = s
                    writer.writerow([
                        s['t'],  # use individual sample timestamp
                        s.get('x', ''), s.get('y', ''), s.get('z', ''),
                        latest_s2.get('x', ''), latest_s2.get('y', ''), latest_s2.get('z', '')
                    ])

            if s2_samples:
                for s in s2_samples:
                    latest_s2 = s
                    writer.writerow([
                        s['t'],  # use individual sample timestamp
                        latest_s1.get('x', ''), latest_s1.get('y', ''), latest_s1.get('z', ''),
                        s.get('x', ''), s.get('y', ''), s.get('z', '')
                    ])


def log_edges(edge_timestamps):
    with csv_lock, open(EDGE_CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        for t in edge_timestamps:
            writer.writerow([t])


# ===============================
# MQTT Callbacks
# ===============================
def on_message(client, userdata, msg):
    global sensor1_active, sensor2_active, edges_active

    payload = json.loads(msg.payload.decode("utf-8"))
    timestamp = payload.get("timestamp", "")

    with data_lock:
        if msg.topic == TOPIC_SENSOR1:
            samples = payload.get("samples", [])
            if samples:
                sensor1_active = True
                msg_queue1.extend(samples)
                log_sensor_samples(timestamp, s1_samples=samples)

        elif msg.topic == TOPIC_SENSOR2:
            samples = payload.get("samples", [])
            if samples:
                sensor2_active = True
                msg_queue2.extend(samples)
                log_sensor_samples(timestamp, s2_samples=samples)

        elif msg.topic == TOPIC_EDGES:
            edges = payload.get("timestamps", [])
            if edges:
                edges_active = True
                msg_queue_edges.extend(edges)
                log_edges(edges)


def on_connect(client, userdata, flags, rc, properties):
    print(f"Connected to MQTT broker with code {rc}")
    client.subscribe([
        (TOPIC_SENSOR1, 0),
        (TOPIC_SENSOR2, 0),
        (TOPIC_EDGES, 0),
    ])


# ===============================
# Plot setup
# ===============================
fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=False)
ax1, ax2, ax3 = axs
fig.suptitle("Real-Time Sensor Data")

# Sensor 1
line1x, = ax1.plot([], [], "r", label="X")
line1y, = ax1.plot([], [], "g", label="Y")
line1z, = ax1.plot([], [], "b", label="Z")
ax1.set_ylim(-22, 22)
ax1.set_ylabel("Accel s104 (g)")
ax1.legend()

# Sensor 2
line2x, = ax2.plot([], [], "r", label="X")
line2y, = ax2.plot([], [], "g", label="Y")
line2z, = ax2.plot([], [], "b", label="Z")
ax2.set_ylim(-22, 22)
ax2.set_ylabel("Accel s105 (g)")
ax2.legend()

# Rising edges (event plot)
line_edges, = ax3.plot([], [], "|", markersize=20)
ax3.set_ylabel("Edges")
ax3.set_yticks([])
ax3.set_xlabel("Time (s)")

ax1.set_visible(False)
ax2.set_visible(False)
ax3.set_visible(False)


# ===============================
# Update function
# ===============================
def update(frame):
    global sensor1_active, sensor2_active, edges_active

    with data_lock:
        while msg_queue1:
            s = msg_queue1.popleft()
            x1_data.append(s["x"])
            y1_data.append(s["y"])
            z1_data.append(s["z"])

        while msg_queue2:
            s = msg_queue2.popleft()
            x2_data.append(s["x"])
            y2_data.append(s["y"])
            z2_data.append(s["z"])

        while msg_queue_edges:
            t = msg_queue_edges.popleft()
            edge_data.append(t)

    ax1.set_visible(sensor1_active)
    ax2.set_visible(sensor2_active)
    ax3.set_visible(edges_active)

    if sensor1_active:
        line1x.set_data(range(len(x1_data)), x1_data)
        line1y.set_data(range(len(y1_data)), y1_data)
        line1z.set_data(range(len(z1_data)), z1_data)
        ax1.set_xlim(0, len(x1_data))

    if sensor2_active:
        line2x.set_data(range(len(x2_data)), x2_data)
        line2y.set_data(range(len(y2_data)), y2_data)
        line2z.set_data(range(len(z2_data)), z2_data)
        ax2.set_xlim(0, len(x2_data))

    if edges_active:
        line_edges.set_data(edge_data, [1]*len(edge_data))
        ax3.set_xlim(
            max(0, edge_data[-1] - 5),
            edge_data[-1] + 0.1
        )

    return line1x, line1y, line1z, line2x, line2y, line2z, line_edges


# ===============================
# Start animation & MQTT
# ===============================
ani = FuncAnimation(fig, update, interval=100, blit=False)

client = mqtt.Client(
    clean_session=True,
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2
)
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

plt.tight_layout()
plt.show()
client.loop_stop()


# ===============================
# Cleanup prompt
# ===============================
def cleanup_data_files():
    root = tk.Tk()
    root.withdraw()

    response = messagebox.askyesno(
        "Save Data",
        "Do you want to save the recorded data?\n\n"
        f"Files:\n- {os.path.basename(SENSOR_CSV_FILE)}\n"
        f"- {os.path.basename(EDGE_CSV_FILE)}"
    )

    if response:
        messagebox.showinfo(
            "Data Saved",
            f"Data saved to:\n\n{SENSOR_CSV_FILE}\n{EDGE_CSV_FILE}"
        )
    else:
        for f in (SENSOR_CSV_FILE, EDGE_CSV_FILE):
            if os.path.exists(f):
                os.remove(f)
        messagebox.showinfo("Data Deleted", "Data files have been deleted.")

    root.destroy()


cleanup_data_files()
