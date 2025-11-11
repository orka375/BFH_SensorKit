import json
import random
import time
import subprocess
import re
import paho.mqtt.client as mqtt
from gpiozero import RGBLED, Button
from gpiozero import DigitalInputDevice

from time import sleep
from Functions import *
from mpu6050 import mpu6050
import time




# Define RGB LED pins (change as needed)
led = RGBLED(red=13, green=19, blue=6)
button1 = Button(10,pull_up=False)
button2 = Button(9,pull_up=False)
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

def connectHW():

    addresses = [0x69, 0x68]
    connected = False
    sensors = []
    dataarray = []
    names = []

    while not connected:
        for addr in addresses:
            try:
                sensor = mpu6050(addr)
                sensors.append(sensor)
                name = "s"+str(addr)
                names.append(name)
                dataarray.append([])
                print(f"Connected to MPU6050 at 0x{addr:02X}")
                connected = True
            except (TimeoutError, OSError) as e:
                print(f"No response from 0x{addr:02X}: {e}")
        if not connected:
            time.sleep(1)
    
    return sensors,dataarray,names

def connectHost():

    broker_ip = None
    print("Waiting for a client to connect to the Pi AP...")
    while broker_ip is None:
        broker_ip = get_single_client_ip()
        time.sleep(1)

    print(f"Detected client IP: {broker_ip}")
    return broker_ip

def connectBroker(broker_ip="127.0.0.1"):

    
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
    return client


def measure(sensor,array):
            # --- Sample accelerometer data ---
            accel = sensor.get_accel_data()
            # Store full reading with timestamp
            array.append({
                "t": time.time_ns(),
                "x": round(accel["x"], 3),
                "y": round(accel["y"], 3),
                "z": round(accel["z"], 3)
            })

            

    
       


last_publish = time.time()


# ------------ STATEMACHINE ---------------
state = States.Default
while True:
    try:
        match state:

            case States.Default: #OFF
                led.off()
                time.sleep(1)
                state = States.SettingUpHW
        
            case States.SettingUpHW: #RED
                led.color = (1, 0, 0)
                sensors,dataarray,names = connectHW()
                state = States.ConnectingHost
            
            case States.ConnectingHost: #ORANGE
                led.color = (1, 0.45, 0)
                hostIP = connectHost()
                state = States.ConnectingBroker
            
            case States.ConnectingBroker: #YELLOW
                led.color = (1, 1, 0)
                client = connectBroker(hostIP)
                state = States.Idelling

                down = False

            case States.Idelling: #BLUE
                led.color = (0, 0, 1)

                if not button1.is_active:
                    down=True
                if button1.is_active and down:
                    state = States.Preparing

            case States.Preparing: #BLUE BLINK
                led.blink(on_time=0.5, off_time=0.5, on_color=(0,0,1),n=5,background=False)
                state = States.Running
                

            case States.Running: #GREEN
                led.color = (0, 1, 0)



                for ix,s in enumerate(sensors):
                    measure(s,dataarray[ix])

                now = time.time_ns(),
                for ix,s in enumerate(sensors):
                    topic = "Sensor/"+names[ix]

                    payload = json.dumps({
                        "timestamp": now,
                        "samples": dataarray[ix],
                    
                    })
                    client.publish(topic, payload)
                    print(f"Published Sensor {names[ix]} data ({len(dataarray[ix])} points)")
                    dataarray[ix] = []

                if (time.time() - last_publish) >= 0.1:
                    #FREQUENCY
                    topic = "Sensor/Frequency"
                    payload = json.dumps({
                        "timestamp": now,
                        "frequency_hz": round(frequency, 2)
                    })
                    client.publish(topic, payload)
                    print(f"Published frequency: {frequency:.2f} Hz")
                    # last_publish = time.time()


                if not button1.is_active:
                    client.loop_stop()
                    client.disconnect()
                    state = States.Idelling

                




    except Exception as e:
        state = States.Default


led.color = (0, 1, 0) #GREEN


