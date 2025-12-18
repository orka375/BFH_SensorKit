import json
import time
import threading
import paho.mqtt.client as mqtt
from gpiozero import RGBLED, Button, DigitalInputDevice
from mpu6050 import mpu6050
from Functions import *


# ======================================================
# TIME
# ======================================================
start_time = None

def abs_time():
    """Seconds since entering Running state (5-digit precision)."""
    if start_time is None:
        return 0.0
    return round(time.time() - start_time, 5)


# ======================================================
# HARDWARE
# ======================================================
led = RGBLED(red=13, green=19, blue=6)

button1 = Button(10, pull_up=False)
button2 = Button(9, pull_up=False)

freq_pin = DigitalInputDevice(21)


# ======================================================
# GLOBAL STATE
# ======================================================
client = None
sensors = []
dataarray = []
names = []

edge_timestamps = []

EDGE_PUBLISH_INTERVAL = 0.2
last_edge_publish = time.time()

data_lock = threading.Lock()

measure_thread = None
measure_running = threading.Event()


# ======================================================
# EDGE CALLBACK (NO MQTT HERE)
# ======================================================
def on_rising_edge():
    if start_time is None:
        return

    with data_lock:
        edge_timestamps.append(abs_time())


freq_pin.when_activated = on_rising_edge


# ======================================================
# CONNECTIONS
# ======================================================
def connectHW():
    addresses = [0x69, 0x68]
    sensors_local = []
    data_local = []
    names_local = []

    while not sensors_local:
        for addr in addresses:
            try:
                s = mpu6050(addr)
                sensors_local.append(s)
                data_local.append([])
                names_local.append(f"s{addr}")
                print(f"Connected to MPU6050 at 0x{addr:02X}")
            except (OSError, TimeoutError):
                pass

        if not sensors_local:
            time.sleep(1)

    return sensors_local, data_local, names_local


def connectBroker(broker_ip="127.0.0.1"):
    c = mqtt.Client(
        client_id="sim_accel_pub",
        clean_session=True,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    while True:
        try:
            c.connect(broker_ip, 1883, 60)
            print("Connected to MQTT broker")
            break
        except TimeoutError:
            time.sleep(5)

    c.loop_start()
    return c


# ======================================================
# MEASUREMENT THREAD
# ======================================================
def measure_loop():
    """Continuously sample accelerometers while running."""
    while measure_running.is_set():
        with data_lock:
            for ix, s in enumerate(sensors):
                try:
                    accel = s.get_accel_data()
                    dataarray[ix].append({
                        "t": abs_time(),
                        "x": round(accel["x"], 3),
                        "y": round(accel["y"], 3),
                        "z": round(accel["z"], 3)
                    })
                except IOError:
                    pass

        # Slight delay to avoid maxing CPU (adjust/remove if needed)
        time.sleep(0.001)


# ======================================================
# BUFFER FLUSHING (CRITICAL)
# ======================================================
def flush_all_buffers():
    """Publish all remaining buffered data."""
    now = abs_time()

    with data_lock:
        for ix in range(len(sensors)):
            if dataarray[ix]:
                client.publish(
                    f"Sensor/{names[ix]}",
                    json.dumps({
                        "timestamp": now,
                        "samples": dataarray[ix]
                    }),
                    qos=0,
                    retain=False
                )
                dataarray[ix].clear()

        if edge_timestamps:
            client.publish(
                "Sensor/Frequency",
                json.dumps({
                    "timestamps": edge_timestamps
                }),
                qos=0,
                retain=False
            )
            edge_timestamps.clear()


# ======================================================
# STATE MACHINE
# ======================================================
state = States.Default

while True:
    try:
        if button2.is_active:
            raise Exception("Reset pressed")

        match state:

            # --------------------------------------------------
            case States.Default:
                led.off()
                time.sleep(1)
                state = States.SettingUpHW

            # --------------------------------------------------
            case States.SettingUpHW:
                led.color = (1, 0, 0)
                sensors, dataarray, names = connectHW()
                state = States.ConnectingBroker

            # --------------------------------------------------
            case States.ConnectingBroker:
                led.color = (1, 1, 0)
                client = connectBroker()
                down = False
                state = States.Idelling

            # --------------------------------------------------
            case States.Idelling:
                led.color = (0, 0, 1)

                if not button1.is_active:
                    down = True
                if button1.is_active and down:
                    state = States.Preparing

            # --------------------------------------------------
            case States.Preparing:
                led.blink(
                    on_time=0.5,
                    off_time=0.5,
                    on_color=(0, 0, 1),
                    n=5,
                    background=False
                )

                # Reset run state
                start_time = time.time()

                with data_lock:
                    edge_timestamps.clear()
                    for arr in dataarray:
                        arr.clear()

                last_edge_publish = time.time()

                # Start measurement thread
                measure_running.set()
                measure_thread = threading.Thread(
                    target=measure_loop,
                    daemon=True
                )
                measure_thread.start()

                state = States.Running

            # --------------------------------------------------
            case States.Running:
                led.color = (0, 1, 0)

                # Periodic publishing
                now_wall = time.time()
                if (now_wall - last_edge_publish) >= EDGE_PUBLISH_INTERVAL:
                    flush_all_buffers()
                    last_edge_publish = now_wall

                # Stop run
                if not button1.is_active:
                    measure_running.clear()
                    measure_thread.join(timeout=1.0)

                    flush_all_buffers()

                    client.loop_stop()
                    client.disconnect()

                    state = States.ConnectingBroker

    except Exception as e:
        print("ERROR:", e)

        try:
            measure_running.clear()
            if measure_thread:
                measure_thread.join(timeout=1.0)

            if client:
                flush_all_buffers()
                client.loop_stop()
                client.disconnect()
        except Exception:
            pass

        state = States.Default
