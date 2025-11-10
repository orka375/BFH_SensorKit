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
MQTT_BROKER = "192.168.4.245"
MQTT_PORT = 1883
TOPIC_SENSOR1 = "Sensor/s104"
TOPIC_SENSOR2 = "Sensor/s105"
TOPIC_FREQ = "Sensor/Frequency"
CSV_FILE = "all_sensor_data.csv"
MAX_POINTS = 4600
INITIAL_POINTS = 100

# ===============================
# Data buffers
# ===============================
# Accelerometers
x1_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)
y1_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)
z1_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)

x2_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)
y2_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)
z2_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)

freq_data = deque([0]*INITIAL_POINTS, maxlen=MAX_POINTS)

# Message queues
msg_queue1 = deque()
msg_queue2 = deque()
msg_queue_freq = deque()
data_lock = threading.Lock()

# Flags to show which sensors are active
sensor1_active = False
sensor2_active = False
freq_active = False

# ===============================
# CSV Logging (all in one file)
# ===============================
csv_lock = threading.Lock()

def log_to_csv(timestamp, s1, s2, freq):
    """
    Logs a single synchronized line for all data types.
    Each call logs whatever is available at that moment.
    """
    with csv_lock:
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp,
                s1.get('x') if s1 else '',
                s1.get('y') if s1 else '',
                s1.get('z') if s1 else '',
                s2.get('x') if s2 else '',
                s2.get('y') if s2 else '',
                s2.get('z') if s2 else '',
                freq if freq is not None else ''
            ])

# ===============================
# MQTT Callbacks
# ===============================
def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker with code {rc}")
    client.subscribe([(TOPIC_SENSOR1, 0), (TOPIC_SENSOR2, 0), (TOPIC_FREQ, 0)])
    print(f"Subscribed to {TOPIC_SENSOR1}, {TOPIC_SENSOR2}, {TOPIC_FREQ}")

def on_message(client, userdata, msg):
    global sensor1_active, sensor2_active, freq_active

    payload = json.loads(msg.payload.decode('utf-8'))
    timestamp = payload.get("timestamp", "")

    with data_lock:
        if msg.topic == TOPIC_SENSOR1:
            samples = payload.get('samples', [])
            if samples:
                sensor1_active = True
                msg_queue1.extend(samples)
                # Log the last sample from this batch
                log_to_csv(timestamp, samples[-1], None, None)

        elif msg.topic == TOPIC_SENSOR2:
            samples = payload.get('samples', [])
            if samples:
                sensor2_active = True
                msg_queue2.extend(samples)
                log_to_csv(timestamp, None, samples[-1], None)

        elif msg.topic == TOPIC_FREQ:
            freq = payload.get('frequency_hz', 0.0)
            freq_active = True
            msg_queue_freq.append(freq)
            log_to_csv(timestamp, None, None, freq)

# ===============================
# Plot setup
# ===============================
fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
(ax1, ax2, ax3) = axs
fig.suptitle("Real-Time Sensor Data")

# --- Sensor 1 ---
line1x, = ax1.plot([], [], 'r', label='X')
line1y, = ax1.plot([], [], 'g', label='Y')
line1z, = ax1.plot([], [], 'b', label='Z')
ax1.set_ylim(-22, 22)
ax1.set_ylabel("Accel s104 (g)")
ax1.legend()

# --- Sensor 2 ---
line2x, = ax2.plot([], [], 'r', label='X')
line2y, = ax2.plot([], [], 'g', label='Y')
line2z, = ax2.plot([], [], 'b', label='Z')
ax2.set_ylim(-22, 22)
ax2.set_ylabel("Accel s105 (g)")
ax2.legend()

# --- Frequency ---
line_freq, = ax3.plot([], [], 'm', label='Frequency (Hz)')
ax3.set_ylim(0, 200)
ax3.set_xlabel("Sample")
ax3.set_ylabel("Freq (Hz)")
ax3.legend()

# Hide all plots initially
ax1.set_visible(False)
ax2.set_visible(False)
ax3.set_visible(False)

# ===============================
# Update function
# ===============================
def update(frame):
    global sensor1_active, sensor2_active, freq_active

    with data_lock:
        while msg_queue1:
            s = msg_queue1.popleft()
            x1_data.append(s['x'])
            y1_data.append(s['y'])
            z1_data.append(s['z'])
        while msg_queue2:
            s = msg_queue2.popleft()
            x2_data.append(s['x'])
            y2_data.append(s['y'])
            z2_data.append(s['z'])
        while msg_queue_freq:
            f = msg_queue_freq.popleft()
            freq_data.append(f)

    # Show only active plots
    ax1.set_visible(sensor1_active)
    ax2.set_visible(sensor2_active)
    ax3.set_visible(freq_active)

    # Update Sensor 1
    if sensor1_active:
        line1x.set_data(range(len(x1_data)), list(x1_data))
        line1y.set_data(range(len(y1_data)), list(y1_data))
        line1z.set_data(range(len(z1_data)), list(z1_data))
        ax1.set_xlim(max(0, len(x1_data) - MAX_POINTS), len(x1_data))

    # Update Sensor 2
    if sensor2_active:
        line2x.set_data(range(len(x2_data)), list(x2_data))
        line2y.set_data(range(len(y2_data)), list(y2_data))
        line2z.set_data(range(len(z2_data)), list(z2_data))
        ax2.set_xlim(max(0, len(x2_data) - MAX_POINTS), len(x2_data))

    # Update Frequency
    if freq_active:
        line_freq.set_data(range(len(freq_data)), list(freq_data))
        ax3.set_xlim(max(0, len(freq_data) - MAX_POINTS), len(freq_data))

    return line1x, line1y, line1z, line2x, line2y, line2z, line_freq

# ===============================
# Start animation
# ===============================
ani = FuncAnimation(fig, update, interval=100, blit=False)

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
plt.tight_layout()
plt.show()
client.loop_stop()
