# from mpu6050 import mpu6050
# import time

# # I2C address of the sensor (default is 0x68)
# sensor = mpu6050(0x68)

# print("MPU6050 test using mpu6050-raspberrypi library")
# print("Press Ctrl+C to stop.")

# try:
#     while True:
#         # accel_data = sensor.get_accel_data()
#         # gyro_data  = sensor.get_gyro_data()
        
#         # print(f"Accel (g): X={accel_data['x']:.2f}, Y={accel_data['y']:.2f}, Z={accel_data['z']:.2f}")
#         # print(f"Gyro  (°/s): X={gyro_data['x']:.2f}, Y={gyro_data['y']:.2f}, Z={gyro_data['z']:.2f}")
#         # print("-" * 40)


        
#         time.sleep(0.5)

# except KeyboardInterrupt:
#     print("\nTest stopped by user.")


from mpu6050 import mpu6050
import smbus
import time

# I2C address of the sensor (default is 0x68)
sensor = mpu6050(0x68)
bus = smbus.SMBus(1)  # Use bus 1 on Raspberry Pi

MPU_ADDR = 0x68

# Wake up MPU6050 (it starts in sleep mode)
bus.write_byte_data(MPU_ADDR, 0x6B, 0x00)

print("MPU6050 RAW test")
print("Press Ctrl+C to stop.")

def read_raw_accel():
    # Read 6 bytes starting at ACCEL_XOUT_H (0x3B)
    raw_data = bus.read_i2c_block_data(MPU_ADDR, 0x3B, 6)
    
    raw_x = (raw_data[0] << 8) | raw_data[1]
    raw_y = (raw_data[2] << 8) | raw_data[3]
    raw_z = (raw_data[4] << 8) | raw_data[5]

    # Convert 16-bit signed values
    raw_x = raw_x - 65536 if raw_x > 32767 else raw_x
    raw_y = raw_y - 65536 if raw_y > 32767 else raw_y
    raw_z = raw_z - 65536 if raw_z > 32767 else raw_z

    return raw_x, raw_y, raw_z

try:
    while True:
        raw_x, raw_y, raw_z = read_raw_accel()
        
        # Convert to g (assuming ±2g full scale, sensitivity = 16384 LSB/g)
        accel_x_g = raw_x / 16384.0
        accel_y_g = raw_y / 16384.0
        accel_z_g = raw_z / 16384.0

        print(f"Accel RAW: X={raw_x}, Y={raw_y}, Z={raw_z}")
        print(f"Accel (g): X={accel_x_g:.2f}, Y={accel_y_g:.2f}, Z={accel_z_g:.2f}")
        print("-"*40)
        
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nTest stopped by user.")
