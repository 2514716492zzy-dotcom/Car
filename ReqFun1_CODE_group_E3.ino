#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#define SCREEN_WIDTH 128 // OLED display width, in pixels
#define SCREEN_HEIGHT 32 // OLED display height, in pixels
#define FACE_MAX_ITERS 40     // max iterations when facing wall
#define ALIGN_MAX_ITERS 60    // max iterations when aligning with light
#define ADVANCE_STEP_MS 300   // ms to advance in small steps toward light
#define FINE_TUNE_MAX_ITERS 12
#define FINE_TUNE_STEP_MS 50
#define FINE_TUNE_SETTLE_MS 120

// Declaration for an SSD1306 display connected to I2C (SDA, SCL pins)
#define OLED_RESET     28 //4 // Reset pin # (or -1 if sharing Arduino reset pin)

#define DISABLE_OLED_OUTPUT 1

#if DISABLE_OLED_OUTPUT
class NoopDisplay {
public:
  template<typename... Args>
  bool begin(Args...) { return true; }

  template<typename... Args>
  void clearDisplay(Args...) {}

  template<typename... Args>
  void setTextSize(Args...) {}

  template<typename... Args>
  void setTextColor(Args...) {}

  template<typename... Args>
  void setCursor(Args...) {}

  template<typename... Args>
  size_t print(Args...) { return 0; }

  template<typename... Args>
  size_t println(Args...) { return 0; }

  template<typename... Args>
  void display(Args...) {}

  template<typename... Args>
  void cp437(Args...) {}
};

NoopDisplay display;
#else
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
#endif
int oldV=1, newV=0;
#include <SoftwareSerial.h>
//UNO: (2, 3)
//SoftwareSerial mySerial(4, 6); // RX, TX
int PARA_STEP_MS = 100;
int pan = 90;
int tilt = 120;
int window_size = 0;
int BT_alive_cnt = 0;
int voltCount = 0;
int goLeft = -1;
#include <Servo.h>
Servo servo_pan;
Servo servo_tilt;
int servo_min = 20;
int servo_max = 160;
bool isAligned = false;

unsigned long time;

//FaBoPWM faboPWM;
int pos = 0;
int MAX_VALUE = 2000;
int MIN_VALUE = 300;

// Define motor pins
#define PWMA 12    //Motor A PWM
#define DIRA1 34
#define DIRA2 35  //Motor A Direction
#define PWMB 8    //Motor B PWM
#define DIRB1 37
#define DIRB2 36  //Motor B Direction
#define PWMC 9   //Motor C PWM --> from 6 to 9
#define DIRC1 43
#define DIRC2 42  //Motor C Direction
#define PWMD 5    //Motor D PWM
#define DIRD1 A4  //26  
#define DIRD2 A5  //27  //Motor D Direction



#define LDR_LEFT_PIN A0
#define LDR_RIGHT_PIN A2
#define lefttrigPin 29
#define leftechoPin 28
#define righttrigPin 45
#define rightechoPin 44
#define FACE_MAX_ITERS 100 // maximum safety for large misalignment


#define MOTORA_FORWARD(pwm)    do{digitalWrite(DIRA1,HIGH);digitalWrite(DIRA2,LOW); analogWrite(PWMA,pwm);}while(0)
#define MOTORA_STOP(x)         do{digitalWrite(DIRA1,LOW); digitalWrite(DIRA2,LOW); analogWrite(PWMA,0);}while(0)
#define MOTORA_BACKOFF(pwm)    do{digitalWrite(DIRA1,LOW); digitalWrite(DIRA2,HIGH);analogWrite(PWMA,pwm);}while(0)

#define MOTORB_FORWARD(pwm)    do{digitalWrite(DIRB1,LOW); digitalWrite(DIRB2,HIGH);analogWrite(PWMB,pwm+5);}while(0)
#define MOTORB_STOP(x)         do{digitalWrite(DIRB1,LOW); digitalWrite(DIRB2,LOW); analogWrite(PWMB,0);}while(0)
#define MOTORB_BACKOFF(pwm)    do{digitalWrite(DIRB1,HIGH);digitalWrite(DIRB2,LOW); analogWrite(PWMB,pwm+5);}while(0)

#define MOTORC_FORWARD(pwm)    do{digitalWrite(DIRC1,HIGH);digitalWrite(DIRC2,LOW); analogWrite(PWMC,pwm);}while(0)
#define MOTORC_STOP(x)         do{digitalWrite(DIRC1,LOW); digitalWrite(DIRC2,LOW); analogWrite(PWMC,0);}while(0)
#define MOTORC_BACKOFF(pwm)    do{digitalWrite(DIRC1,LOW); digitalWrite(DIRC2,HIGH);analogWrite(PWMC,pwm);}while(0)

#define MOTORD_FORWARD(pwm)    do{digitalWrite(DIRD1,HIGH);digitalWrite(DIRD2,LOW); analogWrite(PWMD,pwm+5);}while(0)
#define MOTORD_STOP(x)         do{digitalWrite(DIRD1,LOW); digitalWrite(DIRD2,LOW); analogWrite(PWMD,0);}while(0)
#define MOTORD_BACKOFF(pwm)    do{digitalWrite(DIRD1,LOW); digitalWrite(DIRD2,HIGH);analogWrite(PWMD,pwm+5);}while(0)

#define SERIAL  Serial
#define BTSERIAL Serial3

#define LOG_DEBUG

#ifdef LOG_DEBUG
  #define M_LOG SERIAL.print
#else
  #define M_LOG BTSERIAL.println
#endif

//PWM Definition
#define MAX_PWM   2000
#define MIN_PWM   300

int Motor_PWM = 295;


//    ↑A-----B↑
//     |  ↑  |
//     |  |  |
//    ↑C-----D↑
void BACK()
{
  MOTORA_BACKOFF(Motor_PWM); 
  MOTORB_FORWARD(Motor_PWM);
  MOTORC_BACKOFF(Motor_PWM); 
  MOTORD_FORWARD(Motor_PWM);
}

//    ↓A-----B↓
//     |  |  |
//     |  ↓  |
//    ↓C-----D↓
void ADVANCE()
{
  MOTORA_FORWARD(Motor_PWM); 
  MOTORB_BACKOFF(Motor_PWM);
  MOTORC_FORWARD(Motor_PWM); 
  MOTORD_BACKOFF(Motor_PWM);
}
//    =A-----B↑
//     |   ↖ |
//     | ↖   |
//    ↑C-----D=
void LEFT_1()
{
  MOTORA_STOP(Motor_PWM); 
  MOTORB_FORWARD(Motor_PWM);
  MOTORC_BACKOFF(Motor_PWM); 
  MOTORD_STOP(Motor_PWM);
}

//    ↓A-----B↑
//     |  ←  |
//     |  ←  |
//    ↑C-----D↓
void RIGHT_2()
{
  MOTORA_FORWARD(Motor_PWM); 
  MOTORB_FORWARD(Motor_PWM);
  MOTORC_BACKOFF(Motor_PWM); 
  MOTORD_BACKOFF(Motor_PWM);
}
//    ↓A-----B=
//     | ↙   |
//     |   ↙ |
//    =C-----D↓
void LEFT_3()
{
  MOTORA_FORWARD(Motor_PWM); 
  MOTORB_STOP(Motor_PWM);
  MOTORC_STOP(Motor_PWM); 
  MOTORD_BACKOFF(Motor_PWM);
}
//    ↑A-----B=
//     | ↗   |
//     |   ↗ |
//    =C-----D↑
void RIGHT_1()
{
  MOTORA_BACKOFF(Motor_PWM); 
  MOTORB_STOP(Motor_PWM);
  MOTORC_STOP(Motor_PWM); 
  MOTORD_FORWARD(Motor_PWM);
}
//    ↑A-----B↓
//     |  →  |
//     |  →  |
//    ↓C-----D↑
void LEFT_2()
{
  MOTORA_BACKOFF(Motor_PWM); 
  MOTORB_BACKOFF(Motor_PWM);
  MOTORC_FORWARD(Motor_PWM); 
  MOTORD_FORWARD(Motor_PWM);
}
//    =A-----B↓
//     |   ↘ |
//     | ↘   |
//    ↓C-----D=
void RIGHT_3()
{
  MOTORA_STOP(Motor_PWM); 
  MOTORB_BACKOFF(Motor_PWM);
  MOTORC_FORWARD(Motor_PWM); 
  MOTORD_STOP(Motor_PWM);
}

//    ↑A-----B↓
//     | ↗ ↘ |
//     | ↖ ↙ |
//    ↑C-----D↓
void rotate_1()  //tate_1(uint8_t pwm_A,uint8_t pwm_B,uint8_t pwm_C,uint8_t pwm_D)
{
  MOTORA_BACKOFF(Motor_PWM); 
  MOTORB_BACKOFF(Motor_PWM);
  MOTORC_BACKOFF(Motor_PWM); 
  MOTORD_BACKOFF(Motor_PWM);
}

//    ↓A-----B↑
//     | ↙ ↖ |
//     | ↘ ↗ |
//    ↓C-----D↑
void rotate_2()  // rotate_2(uint8_t pwm_A,uint8_t pwm_B,uint8_t pwm_C,uint8_t pwm_D)
{
  MOTORA_FORWARD(Motor_PWM);
  MOTORB_FORWARD(Motor_PWM);
  MOTORC_FORWARD(Motor_PWM);
  MOTORD_FORWARD(Motor_PWM);
}
//    =A-----B=
//     |  =  |
//     |  =  |
//    =C-----D=
void STOP()
{
  MOTORA_STOP(Motor_PWM);
  MOTORB_STOP(Motor_PWM);
  MOTORC_STOP(Motor_PWM);
  MOTORD_STOP(Motor_PWM);
}

void UART_Control()
{
  String myString;
  char BT_Data = 0;
  // USB data
  /****
   * Check if USB Serial data contain brackets
   */

  if (SERIAL.available())
  {
    char inputChar = SERIAL.read();
    if (inputChar == '(') { // Start loop when left bracket detected
      myString = "";
      inputChar = SERIAL.read();
      while (inputChar != ')')
      {
        myString = myString + inputChar;
        inputChar = SERIAL.read();
        if (!SERIAL.available()) {
          break;
        }// Break when bracket closed
      }
    }
    int commaIndex = myString.indexOf(','); //Split data in bracket (a, b, c)
    //Search for the next comma just after the first
    int secondCommaIndex = myString.indexOf(',', commaIndex + 1);
    String firstValue = myString.substring(0, commaIndex);
    String secondValue = myString.substring(commaIndex + 1, secondCommaIndex);
    String thirdValue = myString.substring(secondCommaIndex + 1); // To the end of the string
    if ((firstValue.toInt() > servo_min and firstValue.toInt() < servo_max) and  //Convert them to numbers
        (secondValue.toInt() > servo_min and secondValue.toInt() < servo_max)) {
      pan = firstValue.toInt();
      tilt = secondValue.toInt();
      window_size = thirdValue.toInt();
    }
    SERIAL.flush();
    Serial3.println(myString);
    Serial3.println("Done");
    if (myString != "") {
      display.clearDisplay();
      display.setCursor(0, 0);     // Start at top-left corner
      display.println("Serial_Data = ");
      display.println(myString);
      display.display();
    }
  }



  //BT Control
  /*
    Receive data from app and translate it to motor movements
  */
  // BT Module on Serial 3 (D14 & D15)
  if (Serial3.available())
  {
    BT_Data = Serial3.read();
    SERIAL.print(BT_Data);
    Serial3.flush();
    BT_alive_cnt = 100;
    display.clearDisplay();
    display.setCursor(0, 0);     // Start at top-left corner
    display.println("BT_Data = ");
    display.println(BT_Data);
    display.display();
  }

  BT_alive_cnt = BT_alive_cnt - 1;
  if (BT_alive_cnt <= 0) {
    STOP();
  }
  switch (BT_Data)
  {
    case 'A':  ADVANCE();  M_LOG("Run!\r\n"); break;
    case 'B':  RIGHT_2();  M_LOG("Right up!\r\n");     break;
    case 'C':  rotate_1();                            break;
    case 'D':  RIGHT_3();  M_LOG("Right down!\r\n");   break;
    case 'E':  BACK();     M_LOG("Run!\r\n");          break;
    case 'F':  LEFT_3();   M_LOG("Left down!\r\n");    break;
    case 'G':  rotate_2();                              break;
    case 'H':  LEFT_2();   M_LOG("Left up!\r\n");     break;
    case 'Z':  STOP();     M_LOG("Stop!\r\n");        break;
    case 'z':  STOP();     M_LOG("Stop!\r\n");        break;
    case 'd':  LEFT_2();   M_LOG("Left!\r\n");        break;
    case 'b':  RIGHT_2();  M_LOG("Right!\r\n");        break;
    case 'L':  Motor_PWM = 1500;                      break;
    case 'M':  Motor_PWM = 500;                       break;
  }
}

// Reusable OLED display function
void displayMessage(const String &msg) {
#if DISABLE_OLED_OUTPUT
  (void)msg;
#else
  display.clearDisplay();            // Clear the previous display
  display.setTextSize(1);            // Set text size (1 is small, 2 is bigger)
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);           // Start at top-left corner
  display.println(msg);              // Print the message
  display.display();                 // Push to OLED

#endif
}


void displayFineTuneStatus(int iteration, int bestValue, int currentValue, const char* directionLabel) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("FINE TUNE");
  display.setCursor(0, 8);
  display.print("Iter:"); display.println(iteration);
  display.setCursor(0, 16);
  display.print("Best:"); display.println(bestValue);
  display.setCursor(0, 24);
  display.print(directionLabel);
  display.print(" -> ");
  display.println(currentValue);
  display.display();
}



long measureDistance(int trigPin, int echoPin) {
  long duration;
  long distance_in_cm;

  // The sensor is triggered by a HIGH pulse of 10 or more microseconds.
  // Give a short LOW pulse beforehand to ensure a clean HIGH pulse:
 
  digitalWrite(trigPin, LOW); 
  delayMicroseconds(2); 
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10); 
  digitalWrite(trigPin, LOW);
 
  duration = pulseIn(echoPin, HIGH);
  distance_in_cm = (duration/2.0) / 29.1;
  return distance_in_cm;
}

// Rotate in place until the robot faces the wall (left and right ultrasonic equal)
bool faceWall(int ROTATE_STEP_MS) {
  // Serial.println("Facing wall: starting...");
  int iters = 0;
  while (iters++ < FACE_MAX_ITERS) {
    long dR = measureDistance(righttrigPin, rightechoPin);
    long dL = measureDistance(lefttrigPin, leftechoPin);

    int ULTRA_TOL_CM = ROTATE_STEP_MS / 50;

    long diff = dL - dR; // positive => left farther than right (rotate right)
    // Serial.print("faceWall: dL="); Serial.print(dL);
    // Serial.print(" dR="); Serial.print(dR);
    // Serial.print(" diff="); Serial.println(diff);
    
    // 在OLED上显示距离数据和对齐状态
    // display.clearDisplay();
    // display.setTextSize(1);
    // display.setTextColor(SSD1306_WHITE);
    // display.setCursor(0, 0);
    // display.println("FACE WALL MODE");
    // display.setCursor(0, 8);
    // display.print("Left: "); display.print(dL); display.println("cm");
    // display.setCursor(0, 16);
    // display.print("Right:"); display.print(dR); display.println("cm");
    // display.setCursor(0, 24);
    // display.print("Diff: "); display.println(diff);
    // display.display();

    sendMessageBT("FACE WALL MODE");
    sendMessageBT("Left: " + String(dL) + "cm");
    sendMessageBT("Right: " + String(dR) + "cm");
    sendMessageBT("Diff: " + String(diff));

    if (abs(diff) <= ULTRA_TOL_CM && dL <= 120 && dR <= 120) {
      // Serial.println("Facing wall: aligned");
      // displayMessage("ALIGNED!");
      sendMessageBT("ALIGNED!");
      STOP();
      return true;  // aligned!
    }

    if (dL >= 120 || dR >= 120)
    {
      rotate_2();
      continue;
    }

    if (diff > 0) {
      if (goLeft == -1)
      {
        goLeft = 1;
      }
      // left farther than right -> rotate right
      sendMessageBT("ROTATING RIGHT");
      sendMessageBT("L:" + String(dL) + " R:" + String(dR));
      sendMessageBT("Diff:" + String(diff));
      rotate_2();
      delay(ROTATE_STEP_MS);
      rotate_1();
    } else {
      if (goLeft == -1)
      {
        goLeft = 0;
      }
      // right farther than left -> rotate left
      sendMessageBT("ROTATING LEFT");
      sendMessageBT("L:" + String(dL) + " R:" + String(dR));
      sendMessageBT("Diff:" + String(diff));
      rotate_1();
      delay(ROTATE_STEP_MS);
      rotate_2();
    }
    delay(ROTATE_STEP_MS/6);
    STOP();
    delay(100);
    
  }
  // Serial.println("faceWall: max iters reached");
    return false;  // did not align

}

void faceWallStable(int ROTATE_STEP_MS)
{
  isAligned = false;
  if (!isAligned) {
    faceWall(ROTATE_STEP_MS);
    ROTATE_STEP_MS /= 2;
    faceWall(ROTATE_STEP_MS);
    ROTATE_STEP_MS /= 2;
    faceWall(ROTATE_STEP_MS);
    ROTATE_STEP_MS /= 2;
    faceWall(ROTATE_STEP_MS);
    ROTATE_STEP_MS /= 2;
    isAligned = faceWall(ROTATE_STEP_MS);  // runs until aligned, then returns true
  }
}


/*Voltage Readings transmitter
Sends them via Serial3*/
void sendVolt(){
    newV = analogRead(A0);
    if(newV!=oldV) {
      if (!Serial3.available()) {
        Serial3.println(newV);
        // Serial.println(newV);
      }
    }
    oldV=newV;
}

void sendMessageBT(const String &message) {
  BTSERIAL.println(message);
}

int int_adc0, int_adc1, int_adc0_c, int_adc1_c, int_adc0_m, int_adc1_m;

void moveForwardTo(int TARGET_DISTANCE)
{
  // Serial.println("moveToLight: Starting continuous movement to 12cm from wall");
  sendMessageBT("Moving to Light");
  
  const int DISTANCE_TOLERANCE = 0; // 距离容差1厘米
  const int COMPENSATION_TIME = 80; // 余力补偿时间
  
  bool isMoving = false;
  bool movingForward = true;
  
  while (1) {
    // 测量左右超声波传感器的距离
    long distanceLeft = measureDistance(lefttrigPin, leftechoPin);
    long distanceRight = measureDistance(righttrigPin, rightechoPin);
    
    // 使用平均距离作为当前距离
    long currentDistance = (distanceLeft + distanceRight) / 2;
    
    // Serial.print("moveToLight: Left="); Serial.print(distanceLeft);
    // Serial.print(" Right="); Serial.print(distanceRight);
    // Serial.print(" Avg="); Serial.print(currentDistance);
    // Serial.print(" Target="); Serial.println(TARGET_DISTANCE);
    
    // 在OLED上显示距离数据
    sendMessageBT("MOVE TO DISTANCE");
    sendMessageBT("Left: " + String(distanceLeft) + "cm");
    sendMessageBT("Right: " + String(distanceRight) + "cm");
    sendMessageBT("Avg: " + String(currentDistance) + " T: " + String(TARGET_DISTANCE));
    
    // 检查是否达到目标距离
    if (abs(currentDistance - TARGET_DISTANCE) <= DISTANCE_TOLERANCE) {
      
      // 如果刚才在向前移动，执行短暂后退来抵消余力
      if (isMoving && movingForward) {
        BACK();
        delay(COMPENSATION_TIME);
        STOP();
      }
      else if (isMoving && !movingForward)
      {
        ADVANCE();
        delay(COMPENSATION_TIME);
        STOP();
      }
      
      if (abs(currentDistance - TARGET_DISTANCE) <= DISTANCE_TOLERANCE)
      {
        sendMessageBT("Position Final!");
        return;
      }
      else
      {
        isMoving = false;
      }
    }
    
    // 根据距离决定移动方向
    if (currentDistance > TARGET_DISTANCE) {
      // 距离太远，需要向前移动
      if (!isMoving || !movingForward) {
        // Serial.println("moveToLight: Starting continuous forward movement");
        sendMessageBT("Moving Forward");
        ADVANCE();
        isMoving = true;
        movingForward = true;
      }
    } else {
      // 距离太近，需要向后移动
      if (!isMoving || movingForward) {
        // Serial.println("moveToLight: Starting continuous backward movement");
        sendMessageBT("Moving Backward");
        BACK();
        isMoving = true;
        movingForward = false;
      }
    }
  }
} 

void parallelMoveLightBelow(int threshold)
{
  // Serial.println("Scan light (two-pass): A0 < threshold");
  sendMessageBT("Scan 2-pass");

  const unsigned long CHECK_INTERVAL_MS = 20;   // 检测间隔
  const unsigned long MAX_SWEEP_MS = 12000;      // 单侧最大扫动时长
  const unsigned long CALIBRATION_INTERVAL_MS = 2000;  // 扫描时每隔多久校准一次位置(毫秒)

  // 根据 goLeft 选择先扫方向：1=先左，否则先右
  if (goLeft == 1) {
    // 先左
    {
      unsigned long tStart = millis();
      unsigned long lastCalibration = millis();  // 上次校准时间
      LEFT_2();
      while (1) {
        int rawA0 = analogRead(A0);
        int rawA2 = analogRead(A2);

        sendMessageBT("SCAN LEFT");
        sendMessageBT("A0:" + String(rawA0));
        sendMessageBT("A2:" + String(rawA2));
        sendMessageBT("TH:" + String(threshold));

        if (rawA0 < threshold) {
          STOP();
          sendMessageBT("FOUND LEFT");
          return;
        }
        
        // 定时校准
        if (millis() - lastCalibration >= CALIBRATION_INTERVAL_MS) {
          STOP();
          faceWallStable(150);
          moveForwardTo(13);
          lastCalibration = millis();
          LEFT_2();  // 继续扫描
        }
        
        if (millis() - tStart >= MAX_SWEEP_MS) {
          break;
        }
        delay(CHECK_INTERVAL_MS);
      }
      unsigned long elapsedLeft = millis() - tStart;
      
      // 回程也检查光和校准
      faceWallStable(150);
      moveForwardTo(13);
      unsigned long returnStart = millis();
      unsigned long lastCalibrationReturn = millis();
      RIGHT_2();
      while (millis() - returnStart < elapsedLeft) {
        int rawA0 = analogRead(A0);
        int rawA2 = analogRead(A2);

        sendMessageBT("RETURN RIGHT");
        sendMessageBT("A0:" + String(rawA0));
        sendMessageBT("A2:" + String(rawA2));
        sendMessageBT("TH:" + String(threshold));

        if (rawA0 < threshold) {
          STOP();
          sendMessageBT("FOUND RETURN");
          return;
        }
        
        // 定时校准
        if (millis() - lastCalibrationReturn >= CALIBRATION_INTERVAL_MS) {
          STOP();
          faceWallStable(150);
          moveForwardTo(13);
          lastCalibrationReturn = millis();
          RIGHT_2();  // 继续返回
        }
        
        delay(CHECK_INTERVAL_MS);
      }
      STOP();
    }

    faceWallStable(150);
    moveForwardTo(13);

    // 再右
    {
      unsigned long tStart = millis();
      unsigned long lastCalibration = millis();  // 上次校准时间
      RIGHT_2();
      while (1) {
        int rawA0 = analogRead(A0);
        int rawA2 = analogRead(A2);

        sendMessageBT("SCAN RIGHT");
        sendMessageBT("A0:" + String(rawA0));
        sendMessageBT("A2:" + String(rawA2));
        sendMessageBT("TH:" + String(threshold));

        if (rawA0 < threshold) {
          STOP();
          sendMessageBT("FOUND RIGHT");
          return;
        }
        
        // 定时校准
        if (millis() - lastCalibration >= CALIBRATION_INTERVAL_MS) {
          STOP();
          faceWallStable(150);
          moveForwardTo(13);
          lastCalibration = millis();
          RIGHT_2();  // 继续扫描
        }
        
        if (millis() - tStart >= MAX_SWEEP_MS) {
          break;
        }
        delay(CHECK_INTERVAL_MS);
      }
      unsigned long elapsedRight = millis() - tStart;
      
      // 回程也检查光和校准
      faceWallStable(150);
      moveForwardTo(13);
      unsigned long returnStart = millis();
      unsigned long lastCalibrationReturn = millis();
      LEFT_2();
      while (millis() - returnStart < elapsedRight) {
        int rawA0 = analogRead(A0);
        int rawA2 = analogRead(A2);

        sendMessageBT("RETURN LEFT");
        sendMessageBT("A0:" + String(rawA0));
        sendMessageBT("A2:" + String(rawA2));
        sendMessageBT("TH:" + String(threshold));

        if (rawA0 < threshold) {
          STOP();
          sendMessageBT("FOUND RETURN");
          return;
        }
        
        // 定时校准
        if (millis() - lastCalibrationReturn >= CALIBRATION_INTERVAL_MS) {
          STOP();
          faceWallStable(150);
          moveForwardTo(13);
          lastCalibrationReturn = millis();
          LEFT_2();  // 继续返回
        }
        
        delay(CHECK_INTERVAL_MS);
      }
      STOP();
    }
  } else {
    // 先右
    {
      unsigned long tStart = millis();
      unsigned long lastCalibration = millis();  // 上次校准时间
      RIGHT_2();
      while (1) {
        int rawA0 = analogRead(A0);
        int rawA2 = analogRead(A2);

        sendMessageBT("SCAN RIGHT");
        sendMessageBT("A0:" + String(rawA0));
        sendMessageBT("A2:" + String(rawA2));
        sendMessageBT("TH:" + String(threshold));

        if (rawA0 < threshold) {
          STOP();
          sendMessageBT("FOUND RIGHT");
          return;
        }
        
        // 定时校准
        if (millis() - lastCalibration >= CALIBRATION_INTERVAL_MS) {
          STOP();
          faceWallStable(150);
          moveForwardTo(13);
          lastCalibration = millis();
          RIGHT_2();  // 继续扫描
        }
        
        if (millis() - tStart >= MAX_SWEEP_MS) {
          break;
        }
        delay(CHECK_INTERVAL_MS);
      }
      unsigned long elapsedRight = millis() - tStart;
      
      // 回程也检查光和校准
      faceWallStable(150);
      moveForwardTo(13);
      unsigned long returnStart = millis();
      unsigned long lastCalibrationReturn = millis();
      LEFT_2();
      while (millis() - returnStart < elapsedRight) {
        int rawA0 = analogRead(A0);
        int rawA2 = analogRead(A2);

        sendMessageBT("RETURN LEFT");
        sendMessageBT("A0:" + String(rawA0));
        sendMessageBT("A2:" + String(rawA2));
        sendMessageBT("TH:" + String(threshold));

        if (rawA0 < threshold) {
          STOP();
          sendMessageBT("FOUND RETURN");
          return;
        }
        
        // 定时校准
        if (millis() - lastCalibrationReturn >= CALIBRATION_INTERVAL_MS) {
          STOP();
          faceWallStable(150);
          moveForwardTo(13);
          lastCalibrationReturn = millis();
          LEFT_2();  // 继续返回
        }
        
        delay(CHECK_INTERVAL_MS);
      }
      STOP();
    }

    faceWallStable(150);
    moveForwardTo(13);

    // 再左
    {
      unsigned long tStart = millis();
      unsigned long lastCalibration = millis();  // 上次校准时间
      LEFT_2();
      while (1) {
        int rawA0 = analogRead(A0);
        int rawA2 = analogRead(A2);

        sendMessageBT("SCAN LEFT");
        sendMessageBT("A0:" + String(rawA0));
        sendMessageBT("A2:" + String(rawA2));
        sendMessageBT("TH:" + String(threshold));

        if (rawA0 < threshold) {
          STOP();
          sendMessageBT("FOUND LEFT");
          return;
        }
        
        // 定时校准
        if (millis() - lastCalibration >= CALIBRATION_INTERVAL_MS) {
          STOP();
          faceWallStable(150);
          moveForwardTo(13);
          lastCalibration = millis();
          LEFT_2();  // 继续扫描
        }
        
        if (millis() - tStart >= MAX_SWEEP_MS) {
          break;
        }
        delay(CHECK_INTERVAL_MS);
      }
      unsigned long elapsedLeft = millis() - tStart;
      
      // 回程也检查光和校准
      faceWallStable(150);
      moveForwardTo(13);
      unsigned long returnStart = millis();
      unsigned long lastCalibrationReturn = millis();
      RIGHT_2();
      while (millis() - returnStart < elapsedLeft) {
        int rawA0 = analogRead(A0);
        int rawA2 = analogRead(A2);

        sendMessageBT("RETURN RIGHT");
        sendMessageBT("A0:" + String(rawA0));
        sendMessageBT("A2:" + String(rawA2));
        sendMessageBT("TH:" + String(threshold));

        if (rawA0 < threshold) {
          STOP();
          sendMessageBT("FOUND RETURN");
          return;
        }
        
        // 定时校准
        if (millis() - lastCalibrationReturn >= CALIBRATION_INTERVAL_MS) {
          STOP();
          faceWallStable(150);
          moveForwardTo(13);
          lastCalibrationReturn = millis();
          RIGHT_2();  // 继续返回
        }
        
        delay(CHECK_INTERVAL_MS);
      }
      STOP();
    }
  }

  sendMessageBT("NOT FOUND");
}

void fineTuneLightPeak()
{
  // Serial.println("Fine tuning for peak light...");
  sendMessageBT("Fine Tune Start");

  int bestValue = analogRead(A0);
  int direction = 1; // 1=右转, -1=左转
  int iteration = 0;

  sendMessageBT("Fine Tune Start");

  while (iteration < FINE_TUNE_MAX_ITERS)
  {
    if (direction > 0)
    {
      RIGHT_2();
      sendMessageBT("MOVE R");
    }
    else
    {
      LEFT_2();
      sendMessageBT("MOVE L");
    }

    delay(FINE_TUNE_STEP_MS);
    STOP();
    delay(FINE_TUNE_SETTLE_MS);

    int currentValue = analogRead(A0);
    sendMessageBT(direction > 0 ? "RIGHT" : "LEFT");
    // Serial.print("FineTune iter="); Serial.print(iteration + 1);
    // Serial.print(" dir="); Serial.print(direction > 0 ? "R" : "L");
    // Serial.print(" value="); Serial.println(currentValue);

    if (currentValue < bestValue)
    {
      bestValue = currentValue;
      iteration++;
      continue;
    }

    if (direction > 0)
    {
      LEFT_2();
    }
    else
    {
      RIGHT_2();
    }
    delay(FINE_TUNE_STEP_MS);
    STOP();
    delay(FINE_TUNE_SETTLE_MS);

    direction *= -1;
    iteration++;
  }

  sendMessageBT("Fine Tune Done");
  // Serial.print("Fine tuning finished, best A0 = ");
  // Serial.println(bestValue);
}


//Where the program starts
void setup()
{
  SERIAL.begin(115200); // USB serial setup
  // SERIAL.println("Start");
  STOP(); // Stop the robot
  Serial3.begin(38400); // BT serial setup
  //Pan=PL4=>48, Tilt=PL5=>47
   servo_pan.attach(48);
   servo_tilt.attach(47);
  //////////////////////////////////////////////
  //OLED Setup//////////////////////////////////
  
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) { // Address 0x3C for 128x32
    // Serial.println(F("SSD1306 allocation failed"));
  }
  display.clearDisplay();
  display.setTextSize(2);      // Normal 1:1 pixel scale
  display.setTextColor(SSD1306_WHITE); // Draw white text
  display.cp437(true);         // Use full 256 char 'Code Page 437' font
  display.setCursor(0, 0);     // Start at top-left corner
  display.println("AI Robot");
  display.display();

  //Setup Voltage detector
  pinMode(A0, INPUT);


  pinMode(righttrigPin, OUTPUT); pinMode(rightechoPin, INPUT);
  pinMode(lefttrigPin, OUTPUT);  pinMode(leftechoPin, INPUT);
  pinMode(LDR_LEFT_PIN, INPUT);  pinMode(LDR_RIGHT_PIN, INPUT);

  int initial_light = analogRead(A0);

  faceWallStable(150);
  moveForwardTo(15);
  if (initial_light > 1000) {
    parallelMoveLightBelow(900);
  } else {
    parallelMoveLightBelow(750);
  }
  moveForwardTo(13);
  faceWallStable(100);
  fineTuneLightPeak();
  faceWallStable(100);
  moveForwardTo(13);
  fineTuneLightPeak();
  faceWallStable(100);
}

void loop()
{
  // sendMessageBT(String(analogRead(A0)));
  // delay(300);
  // sendMessageBT("Hello, this is a test message from the robot!");
  //Serial.println("Hello, this is a test message from the robot!");
}
