## Author: Tyeth Gundry
## TODO: Get OTA type setup going where it checks https://api.github.com/repos/tyeth/ProfBoots_Mini-Fork/contents/MiniFork_wifi_CircuitPython/code.py?ref=adafruit_motor_library
##       and compares the sha to the current code.py sha. If different, check if we need to
#        download the new code.py (or already have and matches - free space issues) and use
#        supervisor.set_next_code_file to load new version, then no rollback needed if error.
from asyncio import create_task, gather, run, sleep as async_sleep
import time
import board
import analogio
import digitalio
import pwmio
from adafruit_motorkit import MotorKit
from adafruit_motor import servo, motor
import adafruit_requests as requests
from html_home_page import html_home_page
import wifi
import socketpool
import ipaddress
import ssl
import os
import microcontroller
from adafruit_httpserver import Server, Request, Response, Websocket, GET

import adafruit_logging as logging

logger = logging.getLogger("MiniFork")
logger.setLevel(logging.DEBUG)
logger.info("MiniFork WiFi CircuitPython edition starting..")
# Constants
I2C_MOTOR_DRIVER = False
I2C_MOTOR_DRIVER_ADDRESS = 0x60
REPORT_BATTERY = False
BATTERY_PIN = None
STEERING_SERVO_TOTAL_ANGLE = 180
MAST_SERVO_TOTAL_ANGLE = 180
# Global variables
servo_delay = 0
steering_servo_value = 0  # 135
steering_left_right_motor_ratio_adjustment = 1
throttle_value = 0
steering_trim = 132
mast_tilt_servo_value = 90
mast_tilt_value = 90
mast_motor_speed = 1.0

logger.debug("Globals:")
logger.debug(f"servo_delay: {servo_delay}")
logger.debug(f"steering_servo_value: {steering_servo_value}")
logger.debug(f"steering_left_right_motor_ratio_adjustment: {steering_left_right_motor_ratio_adjustment}")
logger.debug(f"steering_trim: {steering_trim}")
logger.debug(f"throttle_value: {throttle_value}")
logger.debug(f"mast_tilt_servo_value: {mast_tilt_servo_value}")
logger.debug(f"mast_tilt_value: {mast_tilt_value}")


if board.board_id == "adafruit_feather_huzzah32":
    logger.info("Adafruit Feather Huzzah32 detected")
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
        logger.info("Found Adafruit Motor FeatherWing!")
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
        logger.info("Adafruit Motor FeatherWing not found, falling back to original design\n")
        i2c.unlock()
        MAST_MOTOR0_PIN = board.D25
        MAST_MOTOR1_PIN = board.D26
        AUX_ATTACH0_PIN = board.D18
        AUX_ATTACH1_PIN = board.D17

        LEFT_MOTOR0_PIN = board.D21
        LEFT_MOTOR1_PIN = board.D19
        RIGHT_MOTOR0_PIN = board.D33
        RIGHT_MOTOR1_PIN = board.D32
else:  # adafruit feather bluetooth nrf52840 pins:
    raise NotImplementedError("This board is not supported.")

# WiFi credentials if hosting AP - set HOST_AP to True and comment out settings.toml
HOST_AP = os.getenv('CIRCUITPYTHON_WIFI_SSID',None) is None
SSID = "MiniFork"
PASSWORD = ""

# Setup pins
steering_servo = servo.Servo(pwmio.PWMOut(STEERING_SERVO_PIN, frequency=50))
steering_servo.actuation_range = STEERING_SERVO_TOTAL_ANGLE
mast_tilt_servo = servo.Servo(pwmio.PWMOut(MAST_TILT_SERVO_PIN, frequency=50))
mast_tilt_servo.actuation_range = MAST_SERVO_TOTAL_ANGLE

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

# Initialize WiFi
if HOST_AP:
    logger.info(f"Starting AP {SSID} (192.168.4.1)...")
    ipv4 = ipaddress.IPv4Address("192.168.4.1")
    netmask = ipaddress.IPv4Address("255.255.255.0")
    gateway = ipaddress.IPv4Address("192.168.4.1")
    wifi.radio.set_ipv4_address(ipv4=ipv4, netmask=netmask, gateway=gateway)
    wifi.radio.start_ap(SSID, PASSWORD)
else:
    if wifi.radio.connected:
        logger.info("Already connected to WiFi")
    else:
        logger.info("Connecting to WiFi..", end="")
        wifi.radio.connect(
            os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD")
        )
        while not wifi.radio.connected:
            logger.info(".", end="")
            time.sleep(1)
    logger.info("Connected to WiFi")

websocket: Websocket = None
pool = socketpool.SocketPool(wifi.radio)
server = Server(pool, None, debug=True)


@server.route("/")
def base(request: Request):  # pylint: disable=unused-argument
    logger.debug("serving home page")
    return Response(request, html_home_page, content_type="text/html")


logger.info("starting server..")
try:
    server.start(str(wifi.radio.ipv4_address if wifi.radio.ipv4_address else ipv4), 80)
    logger.info("Listening on http://%s:80" % wifi.radio.ipv4_address if wifi.radio.ipv4_address else ipv4)
except OSError:
    time.sleep(5)
    logger.info("restarting..")
    microcontroller.reset()

# Global variables
light_switch_time = 0
horizontal_screen = False
lights_on = False


def scale_factor_for_servo_angle(total_angle):
    return 1 / (total_angle / 180)


def steering_control(steering_value):
    global steering_servo_value, steering_trim, steering_left_right_motor_ratio_adjustment, STEERING_SERVO_TOTAL_ANGLE
    # From -255 to 255, map to 0-180
    logger.debug(f"steering value: {steering_value}")
    steering_servo_value = (steering_value + 255) / 510 * 180
    logger.debug(f"steering_servo_value: {steering_servo_value} (scaled - should be 0-180)")
    # Map and constrain the steering value to the servo's operational range
    constrained_angle = max(
        0,
        min(
            STEERING_SERVO_TOTAL_ANGLE,
            ((steering_servo_value - steering_trim) + 90)
            * scale_factor_for_servo_angle(STEERING_SERVO_TOTAL_ANGLE),
        ),
    )
    logger.debug(f"Constrained angle: {constrained_angle}")
    steering_servo.angle = constrained_angle
    if steering_servo_value > 100:
        logger.debug(f"steering_servo_value > 100, adjustment: 200 - steering_servo_value / 100")
        steering_left_right_motor_ratio_adjustment = (200 - steering_servo_value) / 100
    elif steering_servo_value < 80:
        logger.debug(f"steering_servo_value < 80, adjustment: 200 - (90 + (90 - steering_servo_value))/100")
        steering_left_right_motor_ratio_adjustment = (200 - (90 + (90 - steering_servo_value))) / 100
    logger.debug(f"new steering__left_right_adjustment: {steering_left_right_motor_ratio_adjustment}\nshould be 0-1")
    process_throttle(throttle_value)


def mast_tilt_control(mast_tilt_servo_value):
    mast_tilt_servo.angle = mast_tilt_servo_value

def mast_control(mast_value):
    if mast_value == 5:
        if mast_motor1 is None:
            mast_motor0.throttle = -1.0 * mast_motor_speed
        else:
            mast_motor0.value = True
            mast_motor1.value = False
    elif mast_value == 6:
        if mast_motor1 is None:
            mast_motor0.throttle = mast_motor_speed
        else:
            mast_motor0.value = False
            mast_motor1.value = True
    else:
        if mast_motor1 is None:
            mast_motor0.throttle = 0  # consider free wheeling with None
        else:
            mast_motor0.value = False
            mast_motor1.value = False


def process_throttle(throttle):
    global throttle_value
    throttle_value = throttle
    if throttle_value > 15 or throttle_value < -15:
        if steering_servo_value > 100:
            logger.info("left motor:")
            move_motor(left_motor0, left_motor1, throttle_value * steering_left_right_motor_ratio_adjustment)
            logger.info("right motor:")
            move_motor(right_motor0, right_motor1, throttle_value)
        elif steering_servo_value < 80:
            logger.info("left motor:")
            move_motor(left_motor0, left_motor1, throttle_value)
            logger.info("right motor:")
            move_motor(right_motor0, right_motor1, throttle_value * steering_left_right_motor_ratio_adjustment)
        else:
            logger.info("left motor:")
            move_motor(left_motor0, left_motor1, throttle_value)
            logger.info("right motor:")
            move_motor(right_motor0, right_motor1, throttle_value)
    else:
        logger.info("left motor:")
        move_motor(left_motor0, left_motor1, 0)
        logger.info("right motor:")
        move_motor(right_motor0, right_motor1, 0)


def move_motor(motor_pin0, motor_pin1, velocity):
    if velocity > 15:
        if motor_pin1 is None:
            new_velocity = velocity / 255
            logger.info(f"Positive New velocity: {new_velocity}")
            motor_pin0.throttle = new_velocity
        else:
            motor_pin0.value = True
            motor_pin1.value = False
    elif velocity < -15:
        if motor_pin1 is None:
            new_velocity = velocity / 255
            logger.info(f"Negative New velocity: {new_velocity}")
            motor_pin0.throttle = new_velocity
        else:
            motor_pin0.value = False
            motor_pin1.value = True
    else:
        if motor_pin1 is None:
            logger.info("throttle 0")
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
    # eventually will be -255 to 255 instead of a truncated 0-180 (40-132), apply to MAST_TILT_SERVO_TOTAL_ANGLE
    logger.debug(f"mast_tilt arg: {mast_tilt}")
    angle_scale = scale_factor_for_servo_angle(MAST_SERVO_TOTAL_ANGLE)
    # mast_tilt = (mast_tilt + 255) / 510 * 180
    # logger.debug(f"mast_tilt (scaled by /510 * 180): {mast_tilt}")
    if mast_tilt == 1:  # forwards
        if servo_delay >=2:
            if mast_tilt_value >= (10 * angle_scale) and mast_tilt_value < (165 * angle_scale):
                mast_tilt_value += 2
                mast_tilt_servo.angle = mast_tilt_value * angle_scale
            servo_delay = 0
        servo_delay += 1
    else:               # backwards
        if servo_delay >= 1:
            if mast_tilt_value <= (170 * angle_scale) and mast_tilt_value > (15 * angle_scale):
                mast_tilt_value -= 2
                mast_tilt_servo.angle = mast_tilt_value * angle_scale
            servo_delay = 0
        servo_delay += 1
    logger.debug(f"new mast_tilt_servo.angle: {mast_tilt_servo.angle}")


def on_car_input_websocket_event(data):
    key, value = data.split(",")
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
    return


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
                battery_voltage = BATTERY_PIN.value
                logger.debug(f"Attempting to send Battery voltage: {battery_voltage}")
                websocket.send_message(str(battery_voltage), fail_silently=True)
                logger.debug("sent?")
        await async_sleep(2)


async def main():
    await gather(
        create_task(handle_http_requests()),
        create_task(handle_websocket_requests()),
        create_task(send_websocket_messages()),
    )


# Main program
setup()
run(main())


