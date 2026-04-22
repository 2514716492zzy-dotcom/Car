#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ====================================================================
// 模块1：引脚定义
// ====================================================================

// 电机引脚
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

// 超声波引脚
#define FRONT_LEFT_TRIG_PIN 48
#define FRONT_LEFT_ECHO_PIN 47
#define FRONT_RIGHT_TRIG_PIN 33
#define FRONT_RIGHT_ECHO_PIN 32

// OLED
#define OLED_SCREEN_WIDTH 128
#define OLED_SCREEN_HEIGHT 64
#define OLED_RESET -1
#define OLED_I2C_ADDRESS 0x3C
Adafruit_SSD1306 oledDisplay(OLED_SCREEN_WIDTH, OLED_SCREEN_HEIGHT, &Wire, OLED_RESET);

// 报警输出
#define ALARM_LED_PIN 22
#define ALARM_BUZZER_PIN 23

// ====================================================================
// 模块2：全局参数配置
// ====================================================================

// PWM 设置
const int PWM_MIN = 0;
const int PWM_MAX = 255;
const int  BASE_PWM = 60;
const int SIDE_PWM = 40;
const int ROTATE_PWM = 65;

// 避障阈值
const int FRONT_OBSTACLE_CM = 6;

// 周期参数
const unsigned long SONAR_READ_INTERVAL_MS = 120UL;
const unsigned long OLED_REFRESH_INTERVAL_MS = 250UL;
const unsigned long ALARM_BLINK_INTERVAL_MS = 300UL;
const unsigned long COMMAND_TIMEOUT_MS = 800UL;
const unsigned long EMERGENCY_OLED_BLINK_INTERVAL_MS = 120UL;

// ====================================================================
// 模块3：枚举和全局变量
// ====================================================================

enum RobotState {
  ROBOT_STOP = 0,
  ROBOT_FORWARD,
  ROBOT_BACKWARD,
  ROBOT_LEFT,
  ROBOT_RIGHT,
  ROBOT_ROTATE_LEFT,
  ROBOT_ROTATE_RIGHT,
  ROBOT_ALARM
};

RobotState robotState = ROBOT_STOP;

// 串口命令
char lastCmd = 'S';
unsigned long lastCommandTimeMs = 0;

// 报警相关
bool alarmActive = false;
bool alarmToggleState = false;
unsigned long lastAlarmBlinkMs = 0;
bool emergencyObstacleActive = false;
bool emergencyOledBlinkOn = false;
unsigned long lastEmergencyOledBlinkMs = 0;

// 超声波测距结果
long frontLeftDistCm = -1;
long frontRightDistCm = -1;
unsigned long lastSonarReadMs = 0;

// OLED
bool oledReady = false;
unsigned long lastOledRefreshMs = 0;

// ====================================================================
// 模块5：电机控制宏定义
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
// 模块6：电机控制函数（全部开环）
// ====================================================================

int clampPwm(int pwm) {
  return constrain(pwm, PWM_MIN, PWM_MAX);
}

void stopAllMotors() {
  MOTORA_STOP();
  MOTORB_STOP();
  MOTORC_STOP();
  MOTORD_STOP();
}

void moveForward(int pwm) {
  int p = clampPwm(pwm);
  MOTORA_FORWARD(p + 10);  // 保留原本偏置
  MOTORC_FORWARD(p + 20);
  MOTORB_BACKOFF(p);
  MOTORD_BACKOFF(p);
}

void moveBackward(int pwm) {
  int p = clampPwm(pwm);
  MOTORA_BACKOFF(p + 10);
  MOTORC_BACKOFF(p + 20);
  MOTORB_FORWARD(p);
  MOTORD_FORWARD(p);
}

void moveLeft(int pwm) {
  int p = clampPwm(pwm);
  MOTORA_BACKOFF(p);
  MOTORC_FORWARD(p + 10);
  MOTORB_BACKOFF(p);
  MOTORD_FORWARD(p);
}

void moveRight(int pwm) {
  int p = clampPwm(pwm);
  MOTORA_FORWARD(p);
  MOTORC_BACKOFF(p);
  MOTORB_FORWARD(p);
  MOTORD_BACKOFF(p + 10);
}

void rotateLeft(int pwm) {
  int p = clampPwm(pwm-40);
  // 与你提供的 rotate_1 方向一致：四轮 BACKOFF
  MOTORA_BACKOFF(p);
  MOTORB_BACKOFF(p);
  MOTORC_BACKOFF(p);
  MOTORD_BACKOFF(p);
}

void rotateRight(int pwm) {
  int p = clampPwm(pwm-40);
  // 与你提供的 rotate_2 方向一致：四轮 FORWARD
  MOTORA_FORWARD(p);
  MOTORB_FORWARD(p);
  MOTORC_FORWARD(p);
  MOTORD_FORWARD(p);
}

// ====================================================================
// 模块7：硬件初始化
// ====================================================================

void initMotorPins() {
  pinMode(PWMA, OUTPUT);
  pinMode(DIRA1, OUTPUT);
  pinMode(DIRA2, OUTPUT);

  pinMode(PWMB, OUTPUT);
  pinMode(DIRB1, OUTPUT);
  pinMode(DIRB2, OUTPUT);

  pinMode(PWMC, OUTPUT);
  pinMode(DIRC1, OUTPUT);
  pinMode(DIRC2, OUTPUT);

  pinMode(PWMD, OUTPUT);
  pinMode(DIRD1, OUTPUT);
  pinMode(DIRD2, OUTPUT);
}

void initSonarPins() {
  pinMode(FRONT_LEFT_TRIG_PIN, OUTPUT);
  pinMode(FRONT_LEFT_ECHO_PIN, INPUT);

  pinMode(FRONT_RIGHT_TRIG_PIN, OUTPUT);
  pinMode(FRONT_RIGHT_ECHO_PIN, INPUT);

  digitalWrite(FRONT_LEFT_TRIG_PIN, LOW);
  digitalWrite(FRONT_RIGHT_TRIG_PIN, LOW);
}

void initAlarmPins() {
  pinMode(ALARM_LED_PIN, OUTPUT);
  pinMode(ALARM_BUZZER_PIN, OUTPUT);
  digitalWrite(ALARM_LED_PIN, LOW);
  digitalWrite(ALARM_BUZZER_PIN, LOW);
}

void initOLED() {
  if (oledDisplay.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDRESS)) {
    oledReady = true;
    oledDisplay.clearDisplay();
    oledDisplay.setTextSize(1);
    oledDisplay.setTextColor(SSD1306_WHITE);
    oledDisplay.setCursor(0, 0);
    oledDisplay.println("Robot Booting...");
    oledDisplay.display();
  } else {
    oledReady = false;
  }
}

// ====================================================================
// 模块8：超声波读取
// ====================================================================

long readUltrasonicCM(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(3);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH, 30000);
  if (duration == 0) return -1;

  long distance = duration / 58;
  if (distance < 2 || distance > 400) return -1;

  return distance;
}

void updateSonars() {
  unsigned long now = millis();
  if (now - lastSonarReadMs < SONAR_READ_INTERVAL_MS) return;
  lastSonarReadMs = now;

  frontLeftDistCm = readUltrasonicCM(FRONT_LEFT_TRIG_PIN, FRONT_LEFT_ECHO_PIN);
  delay(8);
  frontRightDistCm = readUltrasonicCM(FRONT_RIGHT_TRIG_PIN, FRONT_RIGHT_ECHO_PIN);
}

bool isFrontObstacle() {
  if (frontLeftDistCm > 0 && frontLeftDistCm < FRONT_OBSTACLE_CM) return true;
  if (frontRightDistCm > 0 && frontRightDistCm < FRONT_OBSTACLE_CM) return true;
  return false;
}

void triggerEmergencyObstacle() {
  emergencyObstacleActive = true;
  emergencyOledBlinkOn = true;
  lastEmergencyOledBlinkMs = millis();
}

// ====================================================================
// 模块9：报警控制
// ====================================================================

void setAlarmOutputs(bool on) {
  digitalWrite(ALARM_LED_PIN, on ? HIGH : LOW);
  digitalWrite(ALARM_BUZZER_PIN, on ? HIGH : LOW);
}

void updateAlarmOutput() {
  if (!alarmActive) {
    setAlarmOutputs(false);
    return;
  }

  unsigned long now = millis();
  if (now - lastAlarmBlinkMs >= ALARM_BLINK_INTERVAL_MS) {
    lastAlarmBlinkMs = now;
    alarmToggleState = !alarmToggleState;
    setAlarmOutputs(alarmToggleState);
  }
}

// ====================================================================
// 模块10：状态执行
// ====================================================================

void applyRobotState(RobotState state) {
  robotState = state;

  switch (state) {
    case ROBOT_STOP:
      stopAllMotors();
      break;

    case ROBOT_FORWARD:
      moveForward(BASE_PWM);
      break;

    case ROBOT_BACKWARD:
      moveBackward(BASE_PWM);
      break;

    case ROBOT_LEFT:
      moveLeft(SIDE_PWM);
      break;

    case ROBOT_RIGHT:
      moveRight(SIDE_PWM);
      break;

    case ROBOT_ROTATE_LEFT:
      rotateLeft(ROTATE_PWM);
      break;

    case ROBOT_ROTATE_RIGHT:
      rotateRight(ROTATE_PWM);
      break;

    case ROBOT_ALARM:
      stopAllMotors();
      break;
  }
}

// ====================================================================
// 模块11：串口命令解析
// ====================================================================

void executeCommand(const String& cmd) {
  if (cmd.length() == 0) return;
  lastCmd = cmd[0];
  lastCommandTimeMs = millis();

  if (cmd == "F") {
      alarmActive = false;
      if (isFrontObstacle()) {
        triggerEmergencyObstacle();
        applyRobotState(ROBOT_STOP);
      } else {
        emergencyObstacleActive = false;
        applyRobotState(ROBOT_FORWARD);
      }
      return;
  }

  if (cmd == "B") {
      alarmActive = false;
      emergencyObstacleActive = false;
      applyRobotState(ROBOT_BACKWARD);
      return;
  }

  if (cmd == "L") {
      alarmActive = false;
      emergencyObstacleActive = false;
      applyRobotState(ROBOT_LEFT);
      return;
  }

  if (cmd == "R") {
      alarmActive = false;
      emergencyObstacleActive = false;
      applyRobotState(ROBOT_RIGHT);
      return;
  }

  if (cmd == "LL") {
      alarmActive = false;
      emergencyObstacleActive = false;
      applyRobotState(ROBOT_ROTATE_LEFT);
      return;
  }

  if (cmd == "RR") {
      alarmActive = false;
      emergencyObstacleActive = false;
      applyRobotState(ROBOT_ROTATE_RIGHT);
      return;
  }

  if (cmd == "S") {
      alarmActive = false;
      emergencyObstacleActive = false;
      applyRobotState(ROBOT_STOP);
      return;
  }

  if (cmd == "A") {
      emergencyObstacleActive = false;
      applyRobotState(ROBOT_ALARM);
      alarmActive = true;
      return;
  }

  alarmActive = false;
  emergencyObstacleActive = false;
  applyRobotState(ROBOT_STOP);
}

void readJetsonCommand() {
  static String token = "";
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r' || c == ' ') {
      if (token.length() > 0) {
        executeCommand(token);
        token = "";
      }
      continue;
    }
    token += c;
  }
}

// ====================================================================
// 模块12：安全逻辑
// ====================================================================

void updateSafetyLogic() {
  if (millis() - lastCommandTimeMs > COMMAND_TIMEOUT_MS) {
    if (robotState != ROBOT_STOP && robotState != ROBOT_ALARM) {
      applyRobotState(ROBOT_STOP);
    }
  }

  if (robotState == ROBOT_FORWARD && isFrontObstacle()) {
    triggerEmergencyObstacle();
    applyRobotState(ROBOT_STOP);
  }
}

// ====================================================================
// 模块13：OLED 显示
// ====================================================================

const char* stateToString(RobotState state) {
  switch (state) {
    case ROBOT_STOP: return "STOP";
    case ROBOT_FORWARD: return "FORWARD";
    case ROBOT_BACKWARD: return "BACKWARD";
    case ROBOT_LEFT: return "LEFT";
    case ROBOT_RIGHT: return "RIGHT";
    case ROBOT_ROTATE_LEFT: return "ROT_L";
    case ROBOT_ROTATE_RIGHT: return "ROT_R";
    case ROBOT_ALARM: return "ALARM";
    default: return "UNKNOWN";
  }
}

void updateOLED() {
  if (!oledReady) return;

  unsigned long now = millis();

  // 紧急避障优先显示：SSD1306 为单色屏，使用全屏闪烁做强警示
  if (emergencyObstacleActive) {
    if (now - lastEmergencyOledBlinkMs >= EMERGENCY_OLED_BLINK_INTERVAL_MS) {
      lastEmergencyOledBlinkMs = now;
      emergencyOledBlinkOn = !emergencyOledBlinkOn;
    }

    oledDisplay.clearDisplay();
    if (emergencyOledBlinkOn) {
      oledDisplay.fillRect(0, 0, OLED_SCREEN_WIDTH, OLED_SCREEN_HEIGHT, SSD1306_WHITE);
      oledDisplay.setTextColor(SSD1306_BLACK);
    } else {
      oledDisplay.fillRect(0, 0, OLED_SCREEN_WIDTH, OLED_SCREEN_HEIGHT, SSD1306_BLACK);
      oledDisplay.setTextColor(SSD1306_WHITE);
    }
    oledDisplay.setTextSize(2);
    oledDisplay.setCursor(8, 12);
    oledDisplay.println("EMERGENCY");
    oledDisplay.setCursor(24, 38);
    oledDisplay.println("STOP");
    oledDisplay.display();
    return;
  }

  if (now - lastOledRefreshMs < OLED_REFRESH_INTERVAL_MS) return;
  lastOledRefreshMs = now;

  oledDisplay.clearDisplay();
  oledDisplay.setTextSize(1);
  oledDisplay.setTextColor(SSD1306_WHITE);

  oledDisplay.setCursor(0, 0);
  oledDisplay.print("State: ");
  oledDisplay.println(stateToString(robotState));

  oledDisplay.setCursor(0, 12);
  oledDisplay.print("Cmd: ");
  oledDisplay.println(lastCmd);

  oledDisplay.setCursor(0, 24);
  oledDisplay.print("FL:");
  oledDisplay.print(frontLeftDistCm);
  oledDisplay.print(" FR:");
  oledDisplay.println(frontRightDistCm);

  oledDisplay.setCursor(0, 36);
  oledDisplay.println("L/R sonar removed");

  oledDisplay.setCursor(0, 48);
  oledDisplay.print("Alarm: ");
  oledDisplay.println(alarmActive ? "ON" : "OFF");

  oledDisplay.display();
}

// ====================================================================
// setup / loop
// ====================================================================

void setup() {
  Serial.begin(115200);
  Wire.begin();

  initMotorPins();
  initSonarPins();
  initAlarmPins();
  initOLED();

  stopAllMotors();
  lastCommandTimeMs = millis();
}

void loop() {
  readJetsonCommand();
  updateSonars();
  updateSafetyLogic();
  updateAlarmOutput();
  updateOLED();
}
