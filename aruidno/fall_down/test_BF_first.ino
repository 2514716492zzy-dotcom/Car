// ============================================================
// Arduino Mega Robot 控制程序
// 前进禁用 PID，前方停止 4cm
// ============================================================

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ====================================================================
// 模块1：引脚定义
// ====================================================================
#define PWMA 12
#define DIRA1 34
#define DIRA2 35
#define PWMB 8
#define DIRB1 37
#define DIRB2 36
#define PWMC 9
#define DIRC1 43
#define DIRC2 42
#define PWMD 5
#define DIRD1 A4
#define DIRD2 A5

#define ENC_A_A 18
#define ENC_A_B 31
#define ENC_B_A 19
#define ENC_B_B 38
#define ENC_C_A 3
#define ENC_C_B 49
#define ENC_D_A 2
#define ENC_D_B A1

#define FRONT_LEFT_TRIG_PIN 48
#define FRONT_LEFT_ECHO_PIN 47
#define FRONT_RIGHT_TRIG_PIN 33
#define FRONT_RIGHT_ECHO_PIN 32

#define USB_SERIAL Serial
#define BT_SERIAL Serial3

#define OLED_SCREEN_WIDTH 128
#define OLED_SCREEN_HEIGHT 64
#define OLED_RESET -1
#define OLED_I2C_ADDRESS 0x3C
Adafruit_SSD1306 oledDisplay(OLED_SCREEN_WIDTH, OLED_SCREEN_HEIGHT, &Wire, OLED_RESET);

#define ALARM_LED_PIN 22
#define ALARM_BUZZER_PIN 23

// ====================================================================
// 模块2：全局参数
// ====================================================================
const int PWM_MIN = 0;
const int PWM_MAX = 255;
const int BASE_PWM = 40;
const int SEARCH_PWM = 60;
const int ROTATE_PWM = 40;
const int SIDE_PWM = 40;

// 前方停止阈值 4cm
const int FRONT_OBSTACLE_CM = 4;

const unsigned long SONAR_READ_INTERVAL_MS = 120UL;
const unsigned long OLED_REFRESH_INTERVAL_MS = 250UL;
const unsigned long ALARM_BLINK_INTERVAL_MS = 300UL;
const unsigned long COMMAND_TIMEOUT_MS = 800UL;

// ====================================================================
// 模块3：枚举和全局变量
// ====================================================================
enum RobotState { ROBOT_STOP=0, ROBOT_FORWARD, ROBOT_BACKWARD, ROBOT_LEFT, ROBOT_RIGHT, ROBOT_ALARM };
RobotState robotState = ROBOT_STOP;
char lastCmd = 'S';
unsigned long lastCommandTimeMs = 0;
bool alarmActive = false;
bool alarmToggleState = false;
unsigned long lastAlarmBlinkMs = 0;

long frontLeftDistCm = -1;
long frontRightDistCm = -1;
unsigned long lastSonarReadMs = 0;
bool oledReady = false;
unsigned long lastOledRefreshMs = 0;

// ====================================================================
// 模块4：电机控制宏
// ====================================================================
#define MOTORA_FORWARD(pwm) do{ digitalWrite(DIRA1, LOW);  digitalWrite(DIRA2, HIGH); analogWrite(PWMA, (pwm)); }while(0)
#define MOTORA_BACKOFF(pwm) do{ digitalWrite(DIRA1, HIGH); digitalWrite(DIRA2, LOW);  analogWrite(PWMA, (pwm)); }while(0)
#define MOTORA_STOP()       do{ digitalWrite(DIRA1, LOW);  digitalWrite(DIRA2, LOW);  analogWrite(PWMA, 0); }while(0)

#define MOTORB_FORWARD(pwm) do{ digitalWrite(DIRB1, LOW);  digitalWrite(DIRB2, HIGH); analogWrite(PWMB, (pwm)); }while(0)
#define MOTORB_BACKOFF(pwm) do{ digitalWrite(DIRB1, HIGH); digitalWrite(DIRB2, LOW);  analogWrite(PWMB, (pwm)); }while(0)
#define MOTORB_STOP()       do{ digitalWrite(DIRB1, LOW);  digitalWrite(DIRB2, LOW);  analogWrite(PWMB, 0); }while(0)

#define MOTORC_FORWARD(pwm) do{ digitalWrite(DIRC1, LOW);  digitalWrite(DIRC2, HIGH); analogWrite(PWMC, (pwm)); }while(0)
#define MOTORC_BACKOFF(pwm) do{ digitalWrite(DIRC1, HIGH); digitalWrite(DIRC2, LOW);  analogWrite(PWMC, (pwm)); }while(0)
#define MOTORC_STOP()       do{ digitalWrite(DIRC1, LOW);  digitalWrite(DIRC2, LOW);  analogWrite(PWMC, 0); }while(0)

#define MOTORD_FORWARD(pwm) do{ digitalWrite(DIRD1, LOW);  digitalWrite(DIRD2, HIGH); analogWrite(PWMD, (pwm)); }while(0)
#define MOTORD_BACKOFF(pwm) do{ digitalWrite(DIRD1, HIGH); digitalWrite(DIRD2, LOW);  analogWrite(PWMD, (pwm)); }while(0)
#define MOTORD_STOP()       do{ digitalWrite(DIRD1, LOW);  digitalWrite(DIRD2, LOW);  analogWrite(PWMD, 0); }while(0)

// ====================================================================
// 模块5：电机控制函数
// ====================================================================
int clampPwm(int pwm){ return constrain(pwm,PWM_MIN,PWM_MAX); }
void stopAllMotors(){ MOTORA_STOP(); MOTORB_STOP(); MOTORC_STOP(); MOTORD_STOP(); }

void moveForward(int pwm){
  int p = clampPwm(pwm);
  MOTORA_FORWARD(p + 10);
  MOTORC_FORWARD(p + 20);
  MOTORB_BACKOFF(p);
  MOTORD_BACKOFF(p);
}

void moveBackward(int pwm){
  int p = clampPwm(pwm);
  MOTORA_BACKOFF(p + 10);
  MOTORC_BACKOFF(p + 20);
  MOTORB_FORWARD(p);
  MOTORD_FORWARD(p);
}

void moveLeft(int pwm){
  int p = clampPwm(pwm);
  MOTORA_BACKOFF(p);
  MOTORC_FORWARD(p + 10);
  MOTORB_BACKOFF(p);
  MOTORD_FORWARD(p);
}

void moveRight(int pwm){
  int p = clampPwm(pwm);
  MOTORA_FORWARD(p);
  MOTORC_BACKOFF(p);
  MOTORB_FORWARD(p);
  MOTORD_BACKOFF(p + 10);
}

// ====================================================================
// 模块6：超声波
// ====================================================================
long readUltrasonicCM(int trigPin, int echoPin){
  digitalWrite(trigPin, LOW); delayMicroseconds(3);
  digitalWrite(trigPin, HIGH); delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH, 30000);
  if(duration==0) return -1;

  long distance = duration/58;
  if(distance<2 || distance>400) return -1;
  return distance;
}

void updateSonars(){
  unsigned long now = millis();
  if(now - lastSonarReadMs < 120) return;
  lastSonarReadMs = now;

  frontLeftDistCm = readUltrasonicCM(FRONT_LEFT_TRIG_PIN, FRONT_LEFT_ECHO_PIN);
  delay(8);
  frontRightDistCm = readUltrasonicCM(FRONT_RIGHT_TRIG_PIN, FRONT_RIGHT_ECHO_PIN);
}

bool isFrontObstacle(){
  if(frontLeftDistCm>0 && frontLeftDistCm<FRONT_OBSTACLE_CM) return true;
  if(frontRightDistCm>0 && frontRightDistCm<FRONT_OBSTACLE_CM) return true;
  return false;
}

// ====================================================================
// 模块7：报警
// ====================================================================
void setAlarmOutputs(bool on){
  digitalWrite(ALARM_LED_PIN,on?HIGH:LOW);
  digitalWrite(ALARM_BUZZER_PIN,on?HIGH:LOW);
}

void updateAlarmOutput(){
  if(!alarmActive){ setAlarmOutputs(false); return; }
  unsigned long now = millis();
  if(now - lastAlarmBlinkMs >= 300){
    lastAlarmBlinkMs = now;
    static bool toggle=false;
    toggle = !toggle;
    setAlarmOutputs(toggle);
  }
}

// ====================================================================
// 模块8：状态执行
// ====================================================================
void applyRobotState(RobotState state){
  robotState = state;
  switch(state){
    case ROBOT_STOP: stopAllMotors(); break;
    case ROBOT_FORWARD: moveForward(BASE_PWM); break; // 禁用 PID
    case ROBOT_BACKWARD: moveBackward(BASE_PWM); break;
    case ROBOT_LEFT: moveLeft(SIDE_PWM); break;
    case ROBOT_RIGHT: moveRight(SIDE_PWM); break;
    case ROBOT_ALARM: stopAllMotors(); alarmActive=true; break;
  }
}

// ====================================================================
// 模块9：串口命令解析
// ====================================================================
void executeCommand(char cmd){
  lastCmd = cmd;
  lastCommandTimeMs = millis();

  switch(cmd){
    case 'F':
      alarmActive=false;
      if(isFrontObstacle()){ applyRobotState(ROBOT_STOP); USB_SERIAL.println("Obstacle front -> STOP"); }
      else applyRobotState(ROBOT_FORWARD);
      break;
    case 'B': alarmActive=false; applyRobotState(ROBOT_BACKWARD); break;
    case 'L': alarmActive=false; applyRobotState(ROBOT_LEFT); break;
    case 'R': alarmActive=false; applyRobotState(ROBOT_RIGHT); break;
    case 'S': alarmActive=false; applyRobotState(ROBOT_STOP); break;
    case 'A': applyRobotState(ROBOT_ALARM); break;
    default: alarmActive=false; applyRobotState(ROBOT_STOP); break;
  }
}

void readJetsonCommand(){
  while(USB_SERIAL.available()>0){
    char c = USB_SERIAL.read();
    if(c=='\n'||c=='\r'||c==' ') continue;
    executeCommand(c);
  }
}

// ====================================================================
// 模块10：安全逻辑
// ====================================================================
void updateSafetyLogic(){
  if(millis()-lastCommandTimeMs>COMMAND_TIMEOUT_MS) if(robotState!=ROBOT_STOP && robotState!=ROBOT_ALARM) applyRobotState(ROBOT_STOP);
  if(robotState==ROBOT_FORWARD && isFrontObstacle()){ applyRobotState(ROBOT_STOP); USB_SERIAL.println("Safety: front obstacle -> STOP"); }
}

// ====================================================================
// 模块11：OLED显示
// ====================================================================
void updateOLED(){
  if(!oledReady) return;
  static unsigned long lastRefresh=0;
  if(millis()-lastRefresh<OLED_REFRESH_INTERVAL_MS) return;
  lastRefresh=millis();

  oledDisplay.clearDisplay();
  oledDisplay.setCursor(0,0);
  oledDisplay.setTextColor(SSD1306_WHITE);
  oledDisplay.setTextSize(1);
  oledDisplay.print("State: "); oledDisplay.println(robotState);
  oledDisplay.setCursor(0,12); oledDisplay.print("Cmd: "); oledDisplay.println(lastCmd);
  oledDisplay.setCursor(0,24); oledDisplay.print("FL:"); oledDisplay.print(frontLeftDistCm);
  oledDisplay.print(" FR:"); oledDisplay.println(frontRightDistCm);
  oledDisplay.setCursor(0,36); oledDisplay.println("L/R sonar removed");
  oledDisplay.setCursor(0,48); oledDisplay.print("Alarm: "); oledDisplay.println(alarmActive?"ON":"OFF");
  oledDisplay.display();
}

// ====================================================================
// 模块12：setup / loop
// ====================================================================
void setup(){
  USB_SERIAL.begin(115200);
  BT_SERIAL.begin(115200);
  Wire.begin();

  pinMode(PWMA,OUTPUT); pinMode(DIRA1,OUTPUT); pinMode(DIRA2,OUTPUT);
  pinMode(PWMB,OUTPUT); pinMode(DIRB1,OUTPUT); pinMode(DIRB2,OUTPUT);
  pinMode(PWMC,OUTPUT); pinMode(DIRC1,OUTPUT); pinMode(DIRC2,OUTPUT);
  pinMode(PWMD,OUTPUT); pinMode(DIRD1,OUTPUT); pinMode(DIRD2,OUTPUT);

  pinMode(FRONT_LEFT_TRIG_PIN,OUTPUT); pinMode(FRONT_LEFT_ECHO_PIN,INPUT);
  pinMode(FRONT_RIGHT_TRIG_PIN,OUTPUT); pinMode(FRONT_RIGHT_ECHO_PIN,INPUT);

  pinMode(ALARM_LED_PIN,OUTPUT); pinMode(ALARM_BUZZER_PIN,OUTPUT);
  digitalWrite(ALARM_LED_PIN,LOW); digitalWrite(ALARM_BUZZER_PIN,LOW);

  if(oledDisplay.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDRESS)){ oledReady=true; oledDisplay.clearDisplay(); oledDisplay.setTextColor(SSD1306_WHITE); oledDisplay.setCursor(0,0); oledDisplay.println("Robot Booting..."); oledDisplay.display(); }
  else oledReady=false;

  stopAllMotors();
  lastCommandTimeMs=millis();
  USB_SERIAL.println("Arduino Mega ready.");
}

void loop(){
  readJetsonCommand();
  updateSonars();
  updateSafetyLogic();
  updateAlarmOutput();
  updateOLED();
}
