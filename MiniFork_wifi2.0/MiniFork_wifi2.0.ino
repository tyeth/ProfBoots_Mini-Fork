// make sure to upload with ESP32 Dev Module selected as the board under tools>Board>ESP32 Arduino

#include <Arduino.h>

#include <ESP32Servo.h>     // by Kevin Harrington
#include <ESPAsyncWebSrv.h> // by dvarrel
#include <iostream>
#include <sstream>

#include <Wire.h>
#include <Adafruit_MotorShield.h>
#include "utility/Adafruit_MS_PWMServoDriver.h"

#if defined(ESP32)
#include <AsyncTCP.h> // by dvarrel
#include <WiFi.h>
#elif defined(ESP8266)
#include <ESPAsyncTCP.h> // by dvarrel
#endif

// defines

#define steeringServoPin 23
#define mastTiltServoPin 22
#define cabLights 32
#define auxLights 33

#define mastMotor0 25 // Used for controlling auxiliary attachment movement
#define mastMotor1 26 // Used for controlling auxiliary attachment movement
#define auxAttach0 18 // Used for controlling auxiliary attachment movement
#define auxAttach1 17 // Used for controlling auxiliary attachment movement

#define leftMotor0 21  // Used for controlling the left motor movement
#define leftMotor1 19  // Used for controlling the left motor movement
#define rightMotor0 33 // Used for controlling the right motor movementc:\Users\JohnC\Desktop\SOLIDWORKS Connected.lnk
#define rightMotor1 32 // Used for controlling the right motor movement

#define motor_featherwing_i2c_address 0x60 // default, change if needed

// global constants

extern const char *htmlHomePage PROGMEM;
const char *ssid = "MiniFork";

// global variables

Servo steeringServo;
Servo mastTiltServo;

#ifdef motor_featherwing_i2c_address
Adafruit_MotorShield AFMS = Adafruit_MotorShield(motor_featherwing_i2c_address);
Adafruit_DCMotor *leftMotor = AFMS.getMotor(1);
Adafruit_DCMotor *rightMotor = AFMS.getMotor(2);
Adafruit_DCMotor *auxMotor = AFMS.getMotor(3); // N/C
Adafruit_DCMotor *mastMotor = AFMS.getMotor(4);

// Servo and lights pins for Feather V1 Huzzah32
#define steeringServoPin 27
#define mastTiltServoPin 33
#define cabLights 15
#define auxLights 32

#endif

int servoDelay = 0;
float steeringServoValue = 86;
float steeringAdjustment = 1;
int throttleValue = 0;
int steeringTrim = 0;
int mastTiltServoValue = 90;
int mastTiltValue = 90;
int lightSwitchTime = 0;
bool horizontalScreen; // when screen orientation is locked vertically this rotates the D-Pad controls so that forward would now be left.
bool lightsOn = false;

AsyncWebServer server(80);
AsyncWebSocket wsCarInput("/CarInput");

void steeringControl(int steeringValue)
{
  steeringServoValue = steeringValue;
  steeringServo.write(steeringServoValue - steeringTrim);
  if (steeringServoValue > 100)
  {
    steeringAdjustment = ((200 - steeringServoValue) / 100);
  }
  else if (steeringServoValue < 80)
  {
    steeringAdjustment = ((200 - (90 + (90 - steeringServoValue))) / 100);
  }
  processThrottle(throttleValue);
}

void mastTiltControl(int mastTiltServoValue)
{
  mastTiltServo.write(mastTiltServoValue);
}

void mastControl(int mastValue)
{
#ifdef motor_featherwing_i2c_address
  if (mastValue == 5)
  {
    moveMotor(mastMotor, 255); // Full speed forward
  }
  else if (mastValue == 6)
  {
    moveMotor(mastMotor, -255); // Full speed backward
  }
  else
  {
    moveMotor(mastMotor, 0); // Stop
  }
#else
  if (mastValue == 5)
  {
    digitalWrite(mastMotor0, HIGH);
    digitalWrite(mastMotor1, LOW);
  }
  else if (mastValue == 6)
  {
    digitalWrite(mastMotor0, LOW);
    digitalWrite(mastMotor1, HIGH);
  }
  else
  {
    digitalWrite(mastMotor0, LOW);
    digitalWrite(mastMotor1, LOW);
  }
#endif
}

void processThrottle(int throttle)
{
  throttleValue = throttle;
#ifdef motor_featherwing_i2c_address
  if (throttleValue > 15 || throttleValue < -15)
  {
    if (steeringServoValue > 100)
    {
      moveMotor(leftMotor, throttleValue * steeringAdjustment);
      moveMotor(rightMotor, throttleValue);
    }
    else if (steeringServoValue < 80)
    {
      moveMotor(leftMotor, throttleValue);
      moveMotor(rightMotor, throttleValue * steeringAdjustment);
    }
    else
    {
      moveMotor(leftMotor, throttleValue);
      moveMotor(rightMotor, throttleValue);
    }
  }
  else
  {
    moveMotor(leftMotor, 0);
    moveMotor(rightMotor, 0);
  }
#else
  if (throttleValue > 15 || throttleValue < -15)
  {
    if (steeringServoValue > 100)
    {
      moveMotor(leftMotor0, leftMotor1, throttleValue * steeringAdjustment);
      moveMotor(rightMotor0, rightMotor1, throttleValue);
    }
    else if (steeringServoValue < 80)
    {
      moveMotor(leftMotor0, leftMotor1, throttleValue);
      moveMotor(rightMotor0, rightMotor1, throttleValue * steeringAdjustment);
    }
    else
    {
      moveMotor(leftMotor0, leftMotor1, throttleValue);
      moveMotor(rightMotor0, rightMotor1, throttleValue);
    }
  }
  else
  {
    moveMotor(leftMotor0, leftMotor1, 0);
    moveMotor(rightMotor0, rightMotor1, 0);
  }
#endif
}


#ifdef motor_featherwing_i2c_address
void moveMotor(Adafruit_DCMotor *motor, int velocity)
{
  if (velocity > 15)
  {
    motor->setSpeed(velocity);
    motor->run(FORWARD);
  }
  else if (velocity < -15)
  {
    motor->setSpeed(-velocity);
    motor->run(BACKWARD);
  }
  else
  {
    motor->run(RELEASE);
  }
#else
void moveMotor(int motorPin1, int motorPin0, int velocity)
{
  if (velocity > 15)
  {
    analogWrite(motorPin0, velocity);
    analogWrite(motorPin1, LOW);
  }
  else if (velocity < -15)
  {
    analogWrite(motorPin0, LOW);
    analogWrite(motorPin1, (-1 * velocity));
  }
  else
  {
    analogWrite(motorPin0, 0);
    analogWrite(motorPin1, 0);
  }
#endif
}
void lightControl()
{
  if ((millis() - lightSwitchTime) > 200)
  {
    if (lightsOn)
    {
      digitalWrite(auxAttach0, LOW);
      digitalWrite(auxAttach1, LOW);
      lightsOn = false;
    }
    else
    {
      digitalWrite(auxAttach0, HIGH);
      digitalWrite(auxAttach1, LOW);
      lightsOn = true;
    }

    lightSwitchTime = millis();
  }
}
void mastTilt(int mastTilt)
{
  if (mastTilt == 1)
  {
    if (servoDelay == 2)
    {
      if (mastTiltValue >= 10 && mastTiltValue < 165)
      {
        mastTiltValue = mastTiltValue + 2;
        mastTiltServo.write(mastTiltValue);
      }
      servoDelay = 0;
    }
    servoDelay++;
  }
  else
  {
    if (servoDelay == 2)
    {
      if (mastTiltValue <= 170 && mastTiltValue > 15)
      {
        mastTiltValue = mastTiltValue - 2;
        mastTiltServo.write(mastTiltValue);
      }
      servoDelay = 0;
    }
    servoDelay++;
  }
}

void handleRoot(AsyncWebServerRequest *request)
{
  request->send_P(200, "text/html", htmlHomePage);
}

void handleNotFound(AsyncWebServerRequest *request)
{
  request->send(404, "text/plain", "File Not Found");
}

void onCarInputWebSocketEvent(AsyncWebSocket *server,
                              AsyncWebSocketClient *client,
                              AwsEventType type,
                              void *arg,
                              uint8_t *data,
                              size_t len)
{
  switch (type)
  {
  case WS_EVT_CONNECT:
    // Serial.printf("WebSocket client #%u connected from %s\n", client->id(), client->remoteIP().toString().c_str());
    break;
  case WS_EVT_DISCONNECT:
    // Serial.printf("WebSocket client #%u disconnected\n", client->id());
    break;
  case WS_EVT_DATA:
    AwsFrameInfo *info;
    info = (AwsFrameInfo *)arg;
    if (info->final && info->index == 0 && info->len == len && info->opcode == WS_TEXT)
    {
      std::string myData = "";
      myData.assign((char *)data, len);
      std::istringstream ss(myData);
      std::string key, value;
      std::getline(ss, key, ',');
      std::getline(ss, value, ',');
      Serial.printf("Key [%s] Value[%s]\n", key.c_str(), value.c_str());
      int valueInt = atoi(value.c_str());
      if (key == "steering")
      {
        steeringControl(valueInt);
      }
      else if (key == "throttle")
      {
        processThrottle(valueInt);
      }
      else if (key == "mast")
      {
        mastControl(valueInt);
      }
      else if (key == "light")
      {
        lightControl();
      }
      else if (key == "mTilt")
      {
        mastTilt(valueInt);
      }
    }
    break;
  case WS_EVT_PONG:
  case WS_EVT_ERROR:
    break;
  default:
    break;
  }
}

void setUpPinModes()
{

#ifdef motor_featherwing_i2c_address
#else
  pinMode(mastMotor0, OUTPUT);
  pinMode(mastMotor1, OUTPUT);
  pinMode(auxAttach0, OUTPUT);
  pinMode(auxAttach1, OUTPUT);
  pinMode(leftMotor0, OUTPUT);
  pinMode(leftMotor1, OUTPUT);
  pinMode(rightMotor0, OUTPUT);
  pinMode(rightMotor1, OUTPUT);

  digitalWrite(mastMotor0, LOW);
  digitalWrite(mastMotor1, LOW);
  digitalWrite(auxAttach0, LOW);
  digitalWrite(auxAttach1, LOW);
#endif
  steeringServo.attach(steeringServoPin);
  mastTiltServo.attach(mastTiltServoPin);
  steeringControl(steeringServoValue);
  mastTiltControl(mastTiltServoValue);
}

void setup(void)
{
  setUpPinModes();
  Serial.begin(115200);

  WiFi.softAP(ssid);
  IPAddress IP = WiFi.softAPIP();
  Serial.print("AP IP address: ");
  Serial.println(IP);

  server.on("/", HTTP_GET, handleRoot);
  server.onNotFound(handleNotFound);

  wsCarInput.onEvent(onCarInputWebSocketEvent);
  server.addHandler(&wsCarInput);

  server.begin();
  Serial.println("HTTP server started");

  Serial.println("Motor driver initialising...");
  AFMS.begin(); // create with the default frequency 1.6KHz
  Serial.println("Motor driver initialised");
}

void loop()
{
  wsCarInput.cleanupClients();
}
