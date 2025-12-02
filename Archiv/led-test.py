from gpiozero import RGBLED
from time import sleep

# Define RGB LED pins (change as needed)
led = RGBLED(red=6, green=13, blue=5)

print("Starting RGB LED test. Press Ctrl+C to exit.")

try:
    while True:
        # Basic colors
        led.color = (1, 0, 0)   # Red
        print("Red")
        sleep(1)
        led.color = (0, 1, 0)   # Green
        print("Green")
        sleep(1)
        led.color = (0, 0, 1)   # Blue
        print("Blue")
        sleep(1)

        # Mixed colors
        led.color = (1, 1, 0)   # Yellow
        print("Yellow")
        sleep(1)
        led.color = (0, 1, 1)   # Cyan
        print("Cyan")
        sleep(1)
        led.color = (1, 0, 1)   # Magenta
        print("Magenta")
        sleep(1)
        led.color = (1, 1, 1)   # White
        print("White")
        sleep(1)

        # Fade example
        # print("Fading red...")
        # for i in range(100):
        #     led.color = (i/100, 0, 0)
        #     sleep(0.02)

except KeyboardInterrupt:
    print("\nTest stopped.")
    led.off()
