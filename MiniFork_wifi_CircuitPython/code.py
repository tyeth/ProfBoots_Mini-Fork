
from asyncio import create_task, gather, run, sleep as async_sleep
import time
import board
import analogio
import digitalio
import pwmio
from adafruit_motorkit import MotorKit
from adafruit_motor import servo, motor
# from adafruit_esp32spi import adafruit_esp32spi
# from adafruit_esp32spi import adafruit_esp32spi_wifimanager
import adafruit_requests as requests
from html_home_page import html_home_page

# Constants
I2C_MOTOR_DRIVER = False
I2C_MOTOR_DRIVER_ADDRESS = 0x60
REPORT_BATTERY = False
BATTERY_PIN = None
if board.board_id == "adafruit_feather_huzzah32":
    BATTERY_PIN = analogio.AnalogIn(board.VOLTAGE_MONITOR)
    REPORT_BATTERY = True
    MAST_TILT_SERVO_PIN = board.D27
    STEERING_SERVO_PIN = board.D33
    CAB_LIGHTS_PIN = board.D15
    AUX_LIGHTS_PIN = board.D32
    i2c = board.I2C()
    while not i2c.try_lock():
        pass
    if I2C_MOTOR_DRIVER_ADDRESS in i2c.scan():
        i2c.unlock()
        print("Found Adafruit Motor FeatherWing!")
        I2C_MOTOR_DRIVER = True
        # USE 1+2 FOR L+R, AND 3 FOR AUX, 4 FOR MAST
        kit = MotorKit(i2c=i2c, address=I2C_MOTOR_DRIVER_ADDRESS)
        MAST_MOTOR = kit.motor4
        AUX_MOTOR = kit.motor3
        LEFT_MOTOR = kit.motor1
        RIGHT_MOTOR = kit.motor2
        left_motor1 = None
        left_motor0 = LEFT_MOTOR
        right_motor1 = None
        right_motor0 = RIGHT_MOTOR
        mast_motor0 = MAST_MOTOR
        mast_motor1 = None
        aux_attach0 = AUX_MOTOR
        aux_attach1 = None
    else:
        i2c.unlock()
        MAST_MOTOR0_PIN = board.D25
        MAST_MOTOR1_PIN = board.D26
        AUX_ATTACH0_PIN = board.D18
        AUX_ATTACH1_PIN = board.D17

        LEFT_MOTOR0_PIN = board.D21
        LEFT_MOTOR1_PIN = board.D19
        RIGHT_MOTOR0_PIN = board.D33
        RIGHT_MOTOR1_PIN = board.D32


else: # adafruit feather bluetooth nrf52840 pins:
    raise NotImplementedError("This board is not supported.")

# WiFi credentials
SSID = "MiniFork"
PASSWORD = ""

# Setup pins
steering_servo = servo.Servo(pwmio.PWMOut(STEERING_SERVO_PIN, frequency=50))
mast_tilt_servo = servo.Servo(pwmio.PWMOut(MAST_TILT_SERVO_PIN, frequency=50))

cab_lights = digitalio.DigitalInOut(CAB_LIGHTS_PIN)
cab_lights.direction = digitalio.Direction.OUTPUT

aux_lights = digitalio.DigitalInOut(AUX_LIGHTS_PIN)
aux_lights.direction = digitalio.Direction.OUTPUT

if not I2C_MOTOR_DRIVER:
    mast_motor0 = digitalio.DigitalInOut(MAST_MOTOR0_PIN)
    mast_motor0.direction = digitalio.Direction.OUTPUT

    mast_motor1 = digitalio.DigitalInOut(MAST_MOTOR1_PIN)
    mast_motor1.direction = digitalio.Direction.OUTPUT

    aux_attach0 = digitalio.DigitalInOut(AUX_ATTACH0_PIN)
    aux_attach0.direction = digitalio.Direction.OUTPUT

    aux_attach1 = digitalio.DigitalInOut(AUX_ATTACH1_PIN)
    aux_attach1.direction = digitalio.Direction.OUTPUT

    left_motor0 = digitalio.DigitalInOut(LEFT_MOTOR0_PIN)
    left_motor0.direction = digitalio.Direction.OUTPUT

    left_motor1 = digitalio.DigitalInOut(LEFT_MOTOR1_PIN)
    left_motor1.direction = digitalio.Direction.OUTPUT

    right_motor0 = digitalio.DigitalInOut(RIGHT_MOTOR0_PIN)
    right_motor0.direction = digitalio.Direction.OUTPUT

    right_motor1 = digitalio.DigitalInOut(RIGHT_MOTOR1_PIN)
    right_motor1.direction = digitalio.Direction.OUTPUT


# # Initialize WiFi
# esp32_cs = digitalio.DigitalInOut(board.D10)
# esp32_ready = digitalio.DigitalInOut(board.D9)
# esp32_reset = digitalio.DigitalInOut(board.D5)

# spi = board.SPI()
# esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
# wifi = adafruit_esp32spi_wifimanager.ESPSPI_WiFiManager(esp, secrets)

# # Web server setup
# server = requests.Session(wifi)
import wifi
import socketpool
import ipaddress
import ssl
import os
import microcontroller
import adafruit_requests as requests
# from adafruit_httpserver import Server, Request, Response, POST

from adafruit_httpserver import Server, Request, Response, Websocket, GET

# ipv4 =  ipaddress.IPv4Address("192.168.50.177")
# netmask =  ipaddress.IPv4Address("255.255.255.0")
# gateway =  ipaddress.IPv4Address("192.168.50.1")
# wifi.radio.set_ipv4_address(ipv4=ipv4,netmask=netmask,gateway=gateway)
# #  connect to your SSID
# wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'), os.getenv('CIRCUITPY_WIFI_PASSWORD'))

print("Connected to WiFi")
websocket: Websocket = None
pool = socketpool.SocketPool(wifi.radio)
server = Server(pool, None, debug=True)

@server.route("/")
def base(request: Request):  # pylint: disable=unused-argument
    #  serve the HTML f string
    #  with content type text/html
    print("serving home page")
    return Response(request, f"{html_home_page}", content_type='text/html')

print("starting server..")
# startup the server
try:
    server.start(str(wifi.radio.ipv4_address),80)
    print("Listening on http://%s:80" % wifi.radio.ipv4_address)
#  if the server fails to begin, restart the pico w
except OSError:
    time.sleep(5)
    print("restarting..")
    microcontroller.reset()

# Global variables
servo_delay = 0
steering_servo_value = 86
steering_adjustment = 1
throttle_value = 0
steering_trim = 0  # 60?
mast_tilt_servo_value = 90
mast_tilt_value = 90
light_switch_time = 0
horizontal_screen = False
lights_on = False

def steering_control(steering_value):
    global steering_servo_value, steering_adjustment
    steering_servo_value = steering_value
    steering_servo.angle = steering_servo_value - steering_trim
    if steering_servo_value > 100:
        steering_adjustment = ((200 - steering_servo_value) / 100)
    elif steering_servo_value < 80:
        steering_adjustment = ((200 - (90 + (90 - steering_servo_value))) / 100)
    process_throttle(throttle_value)

def mast_tilt_control(mast_tilt_servo_value):
    mast_tilt_servo.angle = mast_tilt_servo_value

def mast_control(mast_value):
    if mast_value == 5:
        if mast_motor1 is None:
            mast_motor0.throttle = -1.0
        else:
            mast_motor0.value = True
            mast_motor1.value = False
    elif mast_value == 6:
        if mast_motor1 is None:
            mast_motor0.throttle = 1.0
        else:
            mast_motor0.value = False
            mast_motor1.value = True
    else:
        if mast_motor1 is None:
            mast_motor0.throttle = 0 # consider free wheeling with None
        else:
            mast_motor0.value = False
            mast_motor1.value = False

def process_throttle(throttle):
    global throttle_value
    throttle_value = throttle
    if throttle_value > 15 or throttle_value < -15:
        if steering_servo_value > 100:
            move_motor(left_motor0, left_motor1, throttle_value * steering_adjustment)
            move_motor(right_motor0, right_motor1, throttle_value)
        elif steering_servo_value < 80:
            move_motor(left_motor0, left_motor1, throttle_value)
            move_motor(right_motor0, right_motor1, throttle_value * steering_adjustment)
        else:
            move_motor(left_motor0, left_motor1, throttle_value)
            move_motor(right_motor0, right_motor1, throttle_value)
    else:
        move_motor(left_motor0, left_motor1, 0)
        move_motor(right_motor0, right_motor1, 0)

def move_motor(motor_pin0, motor_pin1, velocity):
    if velocity > 15:
        if motor_pin1 is None:
            new_velocity = velocity / 255
            print(f"New velocity: {new_velocity}")
            motor_pin0.throttle = new_velocity
        else:
            motor_pin0.value = True
            motor_pin1.value = False
    elif velocity < -15:
        if motor_pin1 is None:
            new_velocity = velocity / 255
            print(f"New velocity: {new_velocity}")
            motor_pin0.throttle = new_velocity
        else:
            motor_pin0.value = False
            motor_pin1.value = True
    else:
        if motor_pin1 is None:
            motor_pin0.throttle = 0
        else:
            motor_pin0.value = False
            motor_pin1.value = False

def light_control():
    global lights_on, light_switch_time
    if (time.monotonic() - light_switch_time) > 0.2:
        if lights_on:
            if aux_attach1 is None:
                aux_attach0.throttle = 0
            else:
                aux_attach0.value = False
                aux_attach1.value = False
            lights_on = False
        else:
            if aux_attach1 is None:
                aux_attach0.throttle = 1.0
            else:
                aux_attach0.value = True
                aux_attach1.value = False
            lights_on = True
        light_switch_time = time.monotonic()

def mast_tilt(mast_tilt):
    global mast_tilt_value, servo_delay
    if mast_tilt == 1:
        if servo_delay == 2:
            if mast_tilt_value >= 10 and mast_tilt_value < 165:
                mast_tilt_value += 2
                mast_tilt_servo.angle = mast_tilt_value
            servo_delay = 0
        servo_delay += 1
    else:
        if servo_delay == 2:
            if mast_tilt_value <= 170 and mast_tilt_value > 15:
                mast_tilt_value -= 2
                mast_tilt_servo.angle = mast_tilt_value
            servo_delay = 0
        servo_delay += 1

def handle_root(request):
    
    return "200 OK", "text/html", html_home_page

def handle_not_found(request):
    return "404 Not Found", "text/plain", "File Not Found"

def on_car_input_websocket_event(data):
    key, value = data.split(',')
    value_int = int(value)
    if key == "steering":
        steering_control(value_int)
    elif key == "throttle":
        process_throttle(value_int)
    elif key == "mast":
        mast_control(value_int)
    elif key == "light":
        light_control()
    elif key == "mTilt":
        mast_tilt(value_int)

def setup():
    steering_servo.angle = steering_servo_value
    mast_tilt_servo.angle = mast_tilt_servo_value
    steering_control(steering_servo_value)
    mast_tilt_control(mast_tilt_servo_value)

def loop():
    # while True:
    #     # Handle web server requests
    #     request = server.get("/")
    #     if request:
    #         if request.path == "/":
    #             response = handle_root(request)
    #         else:
    #             response = handle_not_found(request)
    #         server.send(response)
    #     time.sleep(0.1)
    
    while True:
        try:
            #  poll the server for incoming/outgoing requests
            server.poll()
        # pylint: disable=broad-except
        except Exception as e:
            print(e)
            continue

# Main program
setup()
# loop()


@server.route("/CarInput", GET)
def connect_client(request: Request):
    global websocket  # pylint: disable=global-statement

    if websocket is not None:
        websocket.close()  # Close any existing connection

    websocket = Websocket(request)

    return websocket


async def handle_http_requests():
    while True:
        server.poll()

        await async_sleep(0)


async def handle_websocket_requests():
    while True:
        if websocket is not None:
            if (data := websocket.receive(fail_silently=True)) is not None:
                on_car_input_websocket_event(data)
        await async_sleep(0)


async def send_websocket_messages():
    while True:
        if websocket is not None:
            if REPORT_BATTERY and BATTERY_PIN is not None:
                battery_voltage = BATTERY_PIN.value / 65535 * 5 # /65535 * BATTERY_PIN.reference_voltage * 2
                websocket.send_message(str(battery_voltage), fail_silently=True)

        await async_sleep(2)


async def main():
    await gather(
        create_task(handle_http_requests()),
        create_task(handle_websocket_requests()),
        create_task(send_websocket_messages()),
    )


run(main())