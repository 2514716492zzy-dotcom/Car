#include <Arduino.h>

// =========================================================
// PID 自测文件（独立于 fall_down.ino）
// 功能：
// 1) F/B/L/R 四种动作都使用编码器 PID
// 2) 上电等待 5 秒后自动执行：前进/后退/左移/右移，各 5 秒
// 3) 完成后自动停车（不依赖串口命令）
// =========================================================

// -------------------- 电机引脚 --------------------
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

// -------------------- 编码器引脚 --------------------
// TODO: 以下引脚必须与你实际接线一致
#define ENC_A_A 18
#define ENC_A_B 31
#define ENC_B_A 19
#define ENC_B_B 38
#define ENC_C_A 3
#define ENC_C_B 49
#define ENC_D_A 2
#define ENC_D_B A1

// TODO: 编码器方向极性（前进时计数应为正，不对就改成 -1）
const int ENC_SIGN_A = 1;
const int ENC_SIGN_B = 1;
const int ENC_SIGN_C = 1;
const int ENC_SIGN_D = 1;

// -------------------- PID 参数 --------------------
const unsigned long PID_INTERVAL_MS = 40UL;
const unsigned long TEST_DURATION_MS = 8000UL;  // 8 秒
const unsigned long STARTUP_WAIT_MS = 5000UL;   // 上电等待 5 秒
const int PWM_MIN = 0;
const int PWM_MAX = 255;
const int BASE_PWM = 60;  // 按你的要求：target pwm = 50

// TODO: 前后(F/B) PID 参数
const float KP_FB = 0.9f;
const float KI_FB = 0.03f;
const float KD_FB = 0.00f;
// TODO: 左右平移(L/R) PID 参数（独立于前后）
const float KP_LR = 0.9f;
const float KI_LR = 0.03f;
const float KD_LR = 0.00f;
const float INTEGRAL_MAX = 120.0f;
const int OUTPUT_MAX = 30;
// PID 总开关：true=启用 PID，false=关闭 PID（仅 BASE_PWM + 静态补偿）
const bool USE_PID_CONTROL = true;

// TODO: 目标速度（每个 PID 周期的编码器脉冲数）
const float TARGET_TICKS_FORWARD = 10.0f;
const float TARGET_TICKS_BACKWARD = 10.0f;
const float TARGET_TICKS_LEFT = 9.0f;
const float TARGET_TICKS_RIGHT = 9.0f;

// -------------------- 静态补偿（解决固定偏航/偏移） --------------------
// TODO: 直走偏左/偏右时调这个（单位 PWM）
// TODO: 车“直走偏左”通常需要让左组更快或右组更慢：先把 FORWARD_GROUP1_TRIM_PWM 往 + 调
const int FORWARD_GROUP1_TRIM_PWM = 7;   // 组1(A+C)
const int FORWARD_GROUP2_TRIM_PWM = 0;   // 组2(B+D)

// TODO: 左平移若“向左后偏”，先增大 后轮组
// TODO: 若出现向前偏，则回调 FRONT 或增加 REAR
const int LEFT_STRAFE_FRONT_TRIM_PWM = 0;   // 左平移时前轮组(A+B)
const int LEFT_STRAFE_REAR_TRIM_PWM = 10;     // 左平移时后轮组(C+D)
const int RIGHT_STRAFE_FRONT_TRIM_PWM = 0;  // 右平移时前轮组(A+B)
const int RIGHT_STRAFE_REAR_TRIM_PWM = 10;    // 右平移时后轮组(C+D)

enum RunMode {
  MODE_STOP = 0,
  MODE_FORWARD,
  MODE_BACKWARD,
  MODE_LEFT,
  MODE_RIGHT
};

enum AutoStage {
  STAGE_WAIT = 0,
  STAGE_FORWARD,
  STAGE_BACKWARD,
  STAGE_LEFT,
  STAGE_RIGHT,
  STAGE_DONE
};

struct Pid {
  float kp;
  float ki;
  float kd;
  float integral;
  float lastError;
  float integralMax;
};

// 两组 PID：避免四轮各自独立互相“打架”导致转圈
Pid pidGroup1 = {KP_FB, KI_FB, KD_FB, 0.0f, 0.0f, INTEGRAL_MAX};
Pid pidGroup2 = {KP_FB, KI_FB, KD_FB, 0.0f, 0.0f, INTEGRAL_MAX};

volatile long encA = 0;
volatile long encB = 0;
volatile long encC = 0;
volatile long encD = 0;

long lastA = 0;
long lastB = 0;
long lastC = 0;
long lastD = 0;

unsigned long lastPidMs = 0;
unsigned long modeStartMs = 0;
unsigned long startupMs = 0;
RunMode mode = MODE_STOP;
AutoStage stage = STAGE_WAIT;

int clampPwm(int x) { return constrain(x, PWM_MIN, PWM_MAX); }

void motorA(int dir, int pwm) {
  int p = clampPwm(pwm);
  if (dir > 0) { digitalWrite(DIRA1, LOW);  digitalWrite(DIRA2, HIGH); }
  else if (dir < 0) { digitalWrite(DIRA1, HIGH); digitalWrite(DIRA2, LOW); }
  else { digitalWrite(DIRA1, LOW); digitalWrite(DIRA2, LOW); p = 0; }
  analogWrite(PWMA, p);
}
void motorB(int dir, int pwm) {
  int p = clampPwm(pwm);
  if (dir > 0) { digitalWrite(DIRB1, LOW);  digitalWrite(DIRB2, HIGH); }
  else if (dir < 0) { digitalWrite(DIRB1, HIGH); digitalWrite(DIRB2, LOW); }
  else { digitalWrite(DIRB1, LOW); digitalWrite(DIRB2, LOW); p = 0; }
  analogWrite(PWMB, p);
}
void motorC(int dir, int pwm) {
  int p = clampPwm(pwm);
  if (dir > 0) { digitalWrite(DIRC1, LOW);  digitalWrite(DIRC2, HIGH); }
  else if (dir < 0) { digitalWrite(DIRC1, HIGH); digitalWrite(DIRC2, LOW); }
  else { digitalWrite(DIRC1, LOW); digitalWrite(DIRC2, LOW); p = 0; }
  analogWrite(PWMC, p);
}
void motorD(int dir, int pwm) {
  int p = clampPwm(pwm);
  if (dir > 0) { digitalWrite(DIRD1, LOW);  digitalWrite(DIRD2, HIGH); }
  else if (dir < 0) { digitalWrite(DIRD1, HIGH); digitalWrite(DIRD2, LOW); }
  else { digitalWrite(DIRD1, LOW); digitalWrite(DIRD2, LOW); p = 0; }
  analogWrite(PWMD, p);
}

void stopAll() {
  motorA(0, 0); motorB(0, 0); motorC(0, 0); motorD(0, 0);
}

void resetPid(Pid* p) {
  if (!p) return;
  p->integral = 0.0f;
  p->lastError = 0.0f;
}

float pidStep(Pid* p, float target, float measured, float dt) {
  float e = target - measured;
  p->integral += e * dt;
  p->integral = constrain(p->integral, -p->integralMax, p->integralMax);
  float d = (dt > 1e-6f) ? (e - p->lastError) / dt : 0.0f;
  p->lastError = e;
  float out = p->kp * e + p->ki * p->integral + p->kd * d;
  return constrain(out, (float)-OUTPUT_MAX, (float)OUTPUT_MAX);
}

void isrA() { encA += (digitalRead(ENC_A_A) == digitalRead(ENC_A_B)) ? 1 : -1; }
void isrB() { encB += (digitalRead(ENC_B_A) == digitalRead(ENC_B_B)) ? 1 : -1; }
void isrC() { encC += (digitalRead(ENC_C_A) == digitalRead(ENC_C_B)) ? 1 : -1; }
void isrD() { encD += (digitalRead(ENC_D_A) == digitalRead(ENC_D_B)) ? 1 : -1; }

void resetSpeedLoop() {
  resetPid(&pidGroup1); resetPid(&pidGroup2);
  noInterrupts();
  lastA = encA; lastB = encB; lastC = encC; lastD = encD;
  interrupts();
  lastPidMs = millis();
}

void setMode(RunMode m) {
  mode = m;
  modeStartMs = millis();
  resetSpeedLoop();
  if (mode == MODE_STOP) stopAll();
}

float targetTicksByMode() {
  if (mode == MODE_FORWARD) return TARGET_TICKS_FORWARD;
  if (mode == MODE_BACKWARD) return TARGET_TICKS_BACKWARD;
  if (mode == MODE_LEFT) return TARGET_TICKS_LEFT;
  if (mode == MODE_RIGHT) return TARGET_TICKS_RIGHT;
  return 0.0f;
}

void modeDirections(int& dirA, int& dirB, int& dirC, int& dirD) {
  if (mode == MODE_FORWARD) {
    // 与你的原工程一致：A/C 正向，B/D 反向
    dirA = +1; dirB = -1; dirC = +1; dirD = -1;
  } else if (mode == MODE_BACKWARD) {
    // 与你的原工程 moveBackward 一致
    dirA = -1; dirB = +1; dirC = -1; dirD = +1;
  } else if (mode == MODE_LEFT) {
    // 与你的原工程 moveLeft 一致
    dirA = -1; dirB = -1; dirC = +1; dirD = +1;
  } else if (mode == MODE_RIGHT) {
    // 与你的原工程 moveRight 一致
    dirA = +1; dirB = +1; dirC = -1; dirD = -1;
  } else {
    dirA = 0; dirB = 0; dirC = 0; dirD = 0;
  }
}

void updatePidDrive() {
  if (mode == MODE_STOP) return;
  unsigned long now = millis();
  if (now - lastPidMs < PID_INTERVAL_MS) return;
  float dt = (now - lastPidMs) / 1000.0f;
  lastPidMs = now;

  long a, b, c, d;
  noInterrupts();
  a = encA; b = encB; c = encC; d = encD;
  interrupts();

  long da = a - lastA; lastA = a;
  long db = b - lastB; lastB = b;
  long dc = c - lastC; lastC = c;
  long dd = d - lastD; lastD = d;

  // 用绝对脉冲作为“速度”反馈，避免方向符号配置错误导致打圈
  float ta = (float)abs(da * ENC_SIGN_A);
  float tb = (float)abs(db * ENC_SIGN_B);
  float tc = (float)abs(dc * ENC_SIGN_C);
  float td = (float)abs(dd * ENC_SIGN_D);

  float target = targetTicksByMode();
  int dirA, dirB, dirC, dirD;
  modeDirections(dirA, dirB, dirC, dirD);

  // 前后与左右使用两套独立 PID 系数
  if (mode == MODE_FORWARD || mode == MODE_BACKWARD) {
    pidGroup1.kp = KP_FB; pidGroup1.ki = KI_FB; pidGroup1.kd = KD_FB;
    pidGroup2.kp = KP_FB; pidGroup2.ki = KI_FB; pidGroup2.kd = KD_FB;
  } else {
    pidGroup1.kp = KP_LR; pidGroup1.ki = KI_LR; pidGroup1.kd = KD_LR;
    pidGroup2.kp = KP_LR; pidGroup2.ki = KI_LR; pidGroup2.kd = KD_LR;
  }

  // 根据动作分组做 PID：
  // F/B：组1=A+C，组2=B+D
  // L/R：组1=A+B，组2=C+D
  float group1Ticks = 0.0f;
  float group2Ticks = 0.0f;
  if (mode == MODE_FORWARD || mode == MODE_BACKWARD) {
    group1Ticks = (ta + tc) * 0.5f;
    group2Ticks = (tb + td) * 0.5f;
  } else {
    group1Ticks = (ta + tb) * 0.5f;
    group2Ticks = (tc + td) * 0.5f;
  }

  // ---------------- PID 修正核心 ----------------
  // out1/out2 是两组轮子的动态修正量：
  // - USE_PID_CONTROL=true  : 使用 PID 实时纠偏
  // - USE_PID_CONTROL=false : 不使用 PID（修正量=0），便于对比效果
  float out1 = 0.0f;
  float out2 = 0.0f;
  if (USE_PID_CONTROL) {
    out1 = pidStep(&pidGroup1, target, group1Ticks, dt);
    out2 = pidStep(&pidGroup2, target, group2Ticks, dt);
  }

  int pwmA = BASE_PWM;
  int pwmB = BASE_PWM;
  int pwmC = BASE_PWM;
  int pwmD = BASE_PWM;
  if (mode == MODE_FORWARD || mode == MODE_BACKWARD) {
    // 有 PID：BASE_PWM + outX + trim
    // 无 PID：BASE_PWM + trim
    pwmA += (int)out1;
    pwmC += (int)out1;
    pwmB += (int)out2;
    pwmD += (int)out2;

    // 直走静态偏航补偿（优先于机械误差）
    pwmA += FORWARD_GROUP1_TRIM_PWM;
    pwmC += FORWARD_GROUP1_TRIM_PWM;
    pwmB += FORWARD_GROUP2_TRIM_PWM;
    pwmD += FORWARD_GROUP2_TRIM_PWM;
  } else {
    // 有 PID：BASE_PWM + outX + trim
    // 无 PID：BASE_PWM + trim
    pwmA += (int)out1;
    pwmB += (int)out1;
    pwmC += (int)out2;
    pwmD += (int)out2;

    // 平移前后偏移补偿：左/右平移分开调，便于分别修正“左后偏/右后偏”
    if (mode == MODE_LEFT) {
      pwmA += LEFT_STRAFE_FRONT_TRIM_PWM;
      pwmB += LEFT_STRAFE_FRONT_TRIM_PWM;
      pwmC += LEFT_STRAFE_REAR_TRIM_PWM;
      pwmD += LEFT_STRAFE_REAR_TRIM_PWM;
    } else {
      pwmA += RIGHT_STRAFE_FRONT_TRIM_PWM;
      pwmB += RIGHT_STRAFE_FRONT_TRIM_PWM;
      pwmC += RIGHT_STRAFE_REAR_TRIM_PWM;
      pwmD += RIGHT_STRAFE_REAR_TRIM_PWM;
    }
  }

  motorA(dirA, pwmA);
  motorB(dirB, pwmB);
  motorC(dirC, pwmC);
  motorD(dirD, pwmD);

  static unsigned long lastPrint = 0;
  if (now - lastPrint >= 200) {
    lastPrint = now;
    Serial.print("mode=");
    Serial.print((int)mode);
    Serial.print(" g=[");
    Serial.print(group1Ticks);
    Serial.print(",");
    Serial.print(group2Ticks);
    Serial.print("]");
    Serial.print(" ticks=[");
    Serial.print(ta); Serial.print(",");
    Serial.print(tb); Serial.print(",");
    Serial.print(tc); Serial.print(",");
    Serial.print(td); Serial.print("] pwm=[");
    Serial.print(pwmA); Serial.print(",");
    Serial.print(pwmB); Serial.print(",");
    Serial.print(pwmC); Serial.print(",");
    Serial.print(pwmD); Serial.println("]");
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(PWMA, OUTPUT); pinMode(DIRA1, OUTPUT); pinMode(DIRA2, OUTPUT);
  pinMode(PWMB, OUTPUT); pinMode(DIRB1, OUTPUT); pinMode(DIRB2, OUTPUT);
  pinMode(PWMC, OUTPUT); pinMode(DIRC1, OUTPUT); pinMode(DIRC2, OUTPUT);
  pinMode(PWMD, OUTPUT); pinMode(DIRD1, OUTPUT); pinMode(DIRD2, OUTPUT);

  pinMode(ENC_A_A, INPUT_PULLUP); pinMode(ENC_A_B, INPUT_PULLUP);
  pinMode(ENC_B_A, INPUT_PULLUP); pinMode(ENC_B_B, INPUT_PULLUP);
  pinMode(ENC_C_A, INPUT_PULLUP); pinMode(ENC_C_B, INPUT_PULLUP);
  pinMode(ENC_D_A, INPUT_PULLUP); pinMode(ENC_D_B, INPUT_PULLUP);

  // TODO: 确认这 4 个 A 相引脚都支持外部中断（Mega 常见为 2/3/18/19/20/21）
  attachInterrupt(digitalPinToInterrupt(ENC_A_A), isrA, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_B_A), isrB, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_C_A), isrC, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_D_A), isrD, CHANGE);

  stopAll();
  setMode(MODE_STOP);
  startupMs = millis();
  stage = STAGE_WAIT;

  Serial.println("PID selftest ready.");
  Serial.println("Auto sequence: wait 5s -> F 5s -> B 5s -> L 5s -> R 5s -> STOP");
}

void loop() {
  updatePidDrive();

  unsigned long now = millis();

  if (stage == STAGE_WAIT) {
    if (now - startupMs >= STARTUP_WAIT_MS) {
      setMode(MODE_FORWARD);
      stage = STAGE_FORWARD;
      Serial.println("Stage: FORWARD");
    }
    return;
  }

  if (stage == STAGE_DONE) {
    return;
  }

  if (mode != MODE_STOP && now - modeStartMs >= TEST_DURATION_MS) {
    if (stage == STAGE_FORWARD) {
      setMode(MODE_BACKWARD);
      stage = STAGE_BACKWARD;
      Serial.println("Stage: BACKWARD");
    } else if (stage == STAGE_BACKWARD) {
      setMode(MODE_LEFT);
      stage = STAGE_LEFT;
      Serial.println("Stage: LEFT");
    } else if (stage == STAGE_LEFT) {
      setMode(MODE_RIGHT);
      stage = STAGE_RIGHT;
      Serial.println("Stage: RIGHT");
    } else if (stage == STAGE_RIGHT) {
      setMode(MODE_STOP);
      stage = STAGE_DONE;
      Serial.println("Stage: DONE (STOP)");
    }
  }
}

