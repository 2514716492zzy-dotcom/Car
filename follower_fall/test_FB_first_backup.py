import cv2
import time
import math
import serial
import mediapipe as mp
import threading
from collections import deque

try:
    from flask import Flask, Response
    FLASK_AVAILABLE = True
except Exception:
    FLASK_AVAILABLE = False


# =========================================================
# 配置区
# =========================================================
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
SHOW_WINDOW = False  # Jetson headless 推荐 False，通过 WEB_PREVIEW 看画面
DEBUG_PRINT = True
DEBUG_PRINT_INTERVAL = 0.5
WEB_PREVIEW = True
WEB_HOST = "0.0.0.0"
WEB_PORT = 5000
WEB_JPEG_QUALITY = 80

# 串口
SERIAL_PORT = '/dev/ttyUSB0'   # 按实际修改
BAUD_RATE = 115200
SERIAL_ENABLED = True # 调试模式：仅打印命令，不与 Arduino 串口通信

# 关键点可见度阈值
VISIBILITY_THRESHOLD = 0.5

# 跟随控制阈值
TURN_THRESHOLD_PX = 70
ALIGN_DONE_THRESHOLD_PX = 20
FORWARD_HEIGHT_THRESHOLD = 360
STOP_HEIGHT_THRESHOLD = 420
FAR_FORWARD_X_TOLERANCE_PX = 120
FB_PULSE_SEC = 1.0
LR_ALIGN_PULSE_SEC = 0.2

# 连续发命令节流
MIN_CMD_INTERVAL = 0.10

# 平滑参数
SMOOTH_ALPHA = 0.35

# 跌倒检测阈值
ANGLE_FALL_THRESHOLD_DEG = 55.0
HEIGHT_RATIO_FALL_THRESHOLD = 0.62
HIP_DROP_THRESHOLD_PX = 16.0
LYING_CONFIRM_SEC = 1.0
ALARM_STILL_SEC = 5.0
STILL_MOTION_THRESHOLD = 8.0

# 姿态状态
STATE_NORMAL = "NORMAL"
STATE_FALLING = "FALLING"
STATE_LYING = "LYING"
STATE_ALARM = "ALARM"


# =========================================================
# Web 预览（MJPEG）
# =========================================================
latest_jpeg = None
latest_jpeg_lock = threading.Lock()


def update_web_frame(frame):
    global latest_jpeg
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), WEB_JPEG_QUALITY]
    ok, buffer = cv2.imencode(".jpg", frame, encode_param)
    if not ok:
        return
    with latest_jpeg_lock:
        latest_jpeg = buffer.tobytes()


def mjpeg_generator():
    while True:
        with latest_jpeg_lock:
            frame = latest_jpeg

        if frame is None:
            time.sleep(0.03)
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )
        time.sleep(0.01)


def start_web_preview_server():
    app = Flask(__name__)

    @app.route("/")
    def index():
        return (
            "<html><body>"
            "<h3>Pose Follow Web Preview</h3>"
            "<img src='/video_feed' style='max-width:100%;height:auto;' />"
            "</body></html>"
        )

    @app.route("/video_feed")
    def video_feed():
        return Response(
            mjpeg_generator(),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )

    server_thread = threading.Thread(
        target=lambda: app.run(
            host=WEB_HOST,
            port=WEB_PORT,
            debug=False,
            threaded=True,
            use_reloader=False
        ),
        daemon=True
    )
    server_thread.start()
    return server_thread


# =========================================================
# 串口发送
# =========================================================
class SerialCommander:
    def __init__(self, port, baud_rate, enabled=True):
        self.enabled = enabled
        self.ser = None
        self.last_cmd = None
        self.last_send_time = 0.0

        if enabled:
            try:
                self.ser = serial.Serial(port, baud_rate, timeout=1)
                time.sleep(2.0)
                print(f"[INFO] Serial connected: {port}")
            except Exception as e:
                print(f"[WARN] Serial not available: {e}")
                self.enabled = False

    def send(self, cmd, force=False):
        now = time.time()
        if not force:
            if cmd == self.last_cmd and (now - self.last_send_time) < MIN_CMD_INTERVAL:
                return

        self.last_cmd = cmd
        self.last_send_time = now

        if self.enabled and self.ser:
            try:
                self.ser.write((cmd + '\n').encode('utf-8'))
            except Exception as e:
                print(f"[WARN] Serial write failed: {e}")

        print(f"[CMD] {cmd}")

    def close(self):
        if self.ser:
            self.ser.close()


# =========================================================
# 工具函数
# =========================================================
def midpoint(p1, p2):
    return ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)

def dist2d(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

class ExpSmoother2D:
    def __init__(self, alpha=0.35):
        self.alpha = alpha
        self.value = None

    def update(self, point):
        if point is None:
            return self.value

        if self.value is None:
            self.value = point
        else:
            x = self.alpha * point[0] + (1 - self.alpha) * self.value[0]
            y = self.alpha * point[1] + (1 - self.alpha) * self.value[1]
            self.value = (x, y)
        return self.value


# =========================================================
# Pose 跟踪器
# =========================================================
class PoseTracker:
    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

    def get_lm(self, landmarks, idx, w, h):
        lm = landmarks[idx]
        return (lm.x * w, lm.y * h, lm.visibility)

    def extract(self, frame):
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.pose.process(rgb)

        if not result.pose_landmarks:
            return None, result

        lm = result.pose_landmarks.landmark
        P = self.mp_pose.PoseLandmark

        keypoints = {
            "left_shoulder": self.get_lm(lm, P.LEFT_SHOULDER.value, w, h),
            "right_shoulder": self.get_lm(lm, P.RIGHT_SHOULDER.value, w, h),
            "left_hip": self.get_lm(lm, P.LEFT_HIP.value, w, h),
            "right_hip": self.get_lm(lm, P.RIGHT_HIP.value, w, h),
            "left_ankle": self.get_lm(lm, P.LEFT_ANKLE.value, w, h),
            "right_ankle": self.get_lm(lm, P.RIGHT_ANKLE.value, w, h),
            "nose": self.get_lm(lm, P.NOSE.value, w, h),
        }
        return keypoints, result

    @staticmethod
    def valid_pair(a, b, threshold=VISIBILITY_THRESHOLD):
        return a[2] > threshold and b[2] > threshold


# =========================================================
# 跟随控制
# =========================================================
class FollowController:
    def __init__(self, frame_width):
        self.frame_width = frame_width
        self.shoulder_smoother = ExpSmoother2D(SMOOTH_ALPHA)
        self.hip_smoother = ExpSmoother2D(SMOOTH_ALPHA)
        self.ankle_smoother = ExpSmoother2D(SMOOTH_ALPHA)
        self.fb_pulse_cmd = None
        self.fb_pulse_end_time = 0.0
        self.lr_align_active = False
        self.lr_pulse_cmd = None
        self.lr_pulse_end_time = 0.0

    def get_body_points(self, keypoints):
        ls = keypoints["left_shoulder"]
        rs = keypoints["right_shoulder"]
        lh = keypoints["left_hip"]
        rh = keypoints["right_hip"]
        la = keypoints["left_ankle"]
        ra = keypoints["right_ankle"]

        if not PoseTracker.valid_pair(ls, rs):
            return None
        if not PoseTracker.valid_pair(lh, rh):
            return None
        if not PoseTracker.valid_pair(la, ra):
            return None

        shoulder_mid = midpoint(ls[:2], rs[:2])
        hip_mid = midpoint(lh[:2], rh[:2])
        ankle_mid = midpoint(la[:2], ra[:2])

        shoulder_mid = self.shoulder_smoother.update(shoulder_mid)
        hip_mid = self.hip_smoother.update(hip_mid)
        ankle_mid = self.ankle_smoother.update(ankle_mid)

        return shoulder_mid, hip_mid, ankle_mid

    def estimate_orientation(self, keypoints):
        ls = keypoints["left_shoulder"]
        rs = keypoints["right_shoulder"]
        nose = keypoints["nose"]

        if not PoseTracker.valid_pair(ls, rs):
            return "unknown"

        shoulder_width = abs(ls[0] - rs[0])

        if nose[2] > VISIBILITY_THRESHOLD:
            shoulder_mid = midpoint(ls[:2], rs[:2])
            nose_offset = nose[0] - shoulder_mid[0]
            if shoulder_width > 90:
                return "front_or_back"
            elif abs(nose_offset) > 20:
                return "side"
            else:
                return "unknown"

        if shoulder_width < 60:
            return "side"
        return "unknown"

    def get_follow_command(self, shoulder_mid, hip_mid, ankle_mid):
        body_center_x = (shoulder_mid[0] + hip_mid[0]) * 0.5
        error_x = body_center_x - self.frame_width * 0.5
        body_height = abs(ankle_mid[1] - shoulder_mid[1])
        now = time.time()

        # 到达前后目标距离区间后，停止跟随（按你的需求）
        if FORWARD_HEIGHT_THRESHOLD <= body_height < STOP_HEIGHT_THRESHOLD:
            self.fb_pulse_cmd = None
            self.fb_pulse_end_time = 0.0
            self.lr_align_active = False
            self.lr_pulse_cmd = None
            self.lr_pulse_end_time = 0.0
            cmd = "S\n"
            reason = (
                f"distance_reached({FORWARD_HEIGHT_THRESHOLD} <= body_height={body_height:.1f} < "
                f"{STOP_HEIGHT_THRESHOLD}) -> stop follow"
            )
        else:
            # 左右对齐阶段：一旦触发，就持续左右移动直到回到中心
            if self.lr_align_active:
                if self.lr_pulse_cmd is not None and now < self.lr_pulse_end_time:
                    cmd = self.lr_pulse_cmd
                    reason = (
                        f"lr_align_pulse_active(cmd={cmd.strip()}, remain={self.lr_pulse_end_time - now:.2f}s)"
                    )
                else:
                    if abs(error_x) <= TURN_THRESHOLD_PX:
                        self.lr_align_active = False
                        self.lr_pulse_cmd = None
                        self.lr_pulse_end_time = 0.0
                        cmd = "S\n"
                        reason = (
                            f"lr_align_done(|error_x|={abs(error_x):.1f} <= {TURN_THRESHOLD_PX}) -> S"
                        )
                    elif error_x < -TURN_THRESHOLD_PX:
                        self.lr_pulse_cmd = "LL\n"
                        self.lr_pulse_end_time = now + LR_ALIGN_PULSE_SEC
                        cmd = "LL\n"
                        reason = (
                            f"lr_align_pulse_start(error_x={error_x:.1f} < -{TURN_THRESHOLD_PX}) "
                            f"-> LL for {LR_ALIGN_PULSE_SEC:.1f}s"
                        )
                    else:
                        self.lr_pulse_cmd = "RR\n"
                        self.lr_pulse_end_time = now + LR_ALIGN_PULSE_SEC
                        cmd = "RR\n"
                        reason = (
                            f"lr_align_pulse_start(error_x={error_x:.1f} > {TURN_THRESHOLD_PX}) "
                            f"-> RR for {LR_ALIGN_PULSE_SEC:.1f}s"
                        )
            # 前后脉冲阶段：每次 F/B 只执行 1s
            elif self.fb_pulse_cmd is not None and now < self.fb_pulse_end_time:
                cmd = self.fb_pulse_cmd
                reason = (
                    f"fb_pulse_active(cmd={cmd}, remain={self.fb_pulse_end_time - now:.2f}s)"
                )
            elif self.fb_pulse_cmd is not None and now >= self.fb_pulse_end_time:
                # 脉冲刚结束：先检查是否居中，再决定要不要 L/R
                self.fb_pulse_cmd = None
                self.fb_pulse_end_time = 0.0
                if error_x < -TURN_THRESHOLD_PX:
                    self.lr_align_active = True
                    self.lr_pulse_cmd = "LL\n"
                    self.lr_pulse_end_time = now + LR_ALIGN_PULSE_SEC
                    cmd = "LL\n"
                    reason = (
                        f"after_1s_fb_check_center(error_x={error_x:.1f} < -{TURN_THRESHOLD_PX}) "
                        f"-> start LL-align pulse {LR_ALIGN_PULSE_SEC:.1f}s"
                    )
                elif error_x > TURN_THRESHOLD_PX:
                    self.lr_align_active = True
                    self.lr_pulse_cmd = "RR\n"
                    self.lr_pulse_end_time = now + LR_ALIGN_PULSE_SEC
                    cmd = "RR\n"
                    reason = (
                        f"after_1s_fb_check_center(error_x={error_x:.1f} > {TURN_THRESHOLD_PX}) "
                        f"-> start RR-align pulse {LR_ALIGN_PULSE_SEC:.1f}s"
                    )
                else:
                    cmd = "S\n"
                    reason = (
                        f"after_1s_fb_check_center(|error_x|={abs(error_x):.1f} <= {TURN_THRESHOLD_PX}) -> S"
                    )
            else:
                # 新一轮前后 1s 脉冲
                if body_height < FORWARD_HEIGHT_THRESHOLD:
                    self.fb_pulse_cmd = "F"
                    self.fb_pulse_end_time = now + FB_PULSE_SEC
                    cmd = "F\n"
                    reason = (
                        f"too_far(body_height={body_height:.1f} < {FORWARD_HEIGHT_THRESHOLD}) "
                        f"-> F for {FB_PULSE_SEC:.1f}s"
                    )
                else:
                    self.fb_pulse_cmd = "B\n"
                    self.fb_pulse_end_time = now + FB_PULSE_SEC
                    cmd = "B\n"
                    reason = (
                        f"too_close(body_height={body_height:.1f} >= {STOP_HEIGHT_THRESHOLD}) "
                        f"-> B for {FB_PULSE_SEC:.1f}s"
                    )

        return {
            "cmd": cmd,
            "body_center_x": body_center_x,
            "error_x": error_x,
            "body_height": body_height,
            "reason": reason
        }


# =========================================================
# 跌倒检测
# =========================================================
class FallDetector:
    def __init__(self):
        self.reference_height = None
        self.last_shoulder_mid = None
        self.last_hip_mid = None
        self.last_hip_y = None

        self.state = STATE_NORMAL
        self.lying_start_time = None
        self.still_start_time = None

    def reset(self):
        self.__init__()

    def angle_deg(self, shoulder_mid, ankle_mid):
        dx = abs(ankle_mid[0] - shoulder_mid[0])
        dy = abs(ankle_mid[1] - shoulder_mid[1]) + 1e-6
        return math.degrees(math.atan2(dx, dy))

    def motion(self, shoulder_mid, hip_mid):
        if self.last_shoulder_mid is None or self.last_hip_mid is None:
            return 999.0
        return dist2d(shoulder_mid, self.last_shoulder_mid) + dist2d(hip_mid, self.last_hip_mid)

    def update_reference_height(self, body_height, angle_deg):
        if angle_deg < 25.0:
            if self.reference_height is None:
                self.reference_height = body_height
            else:
                self.reference_height = 0.9 * self.reference_height + 0.1 * body_height

    def update(self, shoulder_mid, hip_mid, ankle_mid):
        now = time.time()

        body_height = abs(ankle_mid[1] - shoulder_mid[1])
        angle = self.angle_deg(shoulder_mid, ankle_mid)
        motion = self.motion(shoulder_mid, hip_mid)

        if self.last_hip_y is None:
            hip_drop = 0.0
        else:
            hip_drop = hip_mid[1] - self.last_hip_y

        self.update_reference_height(body_height, angle)

        if self.reference_height is None or self.reference_height < 1:
            height_ratio = 1.0
        else:
            height_ratio = body_height / self.reference_height

        falling_condition = (
            angle > ANGLE_FALL_THRESHOLD_DEG and
            height_ratio < HEIGHT_RATIO_FALL_THRESHOLD and
            hip_drop > HIP_DROP_THRESHOLD_PX
        )

        lying_condition = (
            angle > ANGLE_FALL_THRESHOLD_DEG and
            height_ratio < HEIGHT_RATIO_FALL_THRESHOLD
        )

        still_condition = motion < STILL_MOTION_THRESHOLD

        if self.state == STATE_NORMAL:
            if falling_condition:
                self.state = STATE_FALLING
                self.lying_start_time = now
                self.still_start_time = None

        elif self.state == STATE_FALLING:
            if lying_condition:
                if self.lying_start_time is None:
                    self.lying_start_time = now
                elif now - self.lying_start_time >= LYING_CONFIRM_SEC:
                    self.state = STATE_LYING
                    self.still_start_time = now if still_condition else None
            else:
                self.state = STATE_NORMAL
                self.lying_start_time = None
                self.still_start_time = None

        elif self.state == STATE_LYING:
            if not lying_condition:
                self.state = STATE_NORMAL
                self.lying_start_time = None
                self.still_start_time = None
            else:
                if still_condition:
                    if self.still_start_time is None:
                        self.still_start_time = now
                    elif now - self.still_start_time >= ALARM_STILL_SEC:
                        self.state = STATE_ALARM
                else:
                    self.still_start_time = None

        elif self.state == STATE_ALARM:
            pass

        self.last_shoulder_mid = shoulder_mid
        self.last_hip_mid = hip_mid
        self.last_hip_y = hip_mid[1]

        return {
            "state": self.state,
            "angle_deg": angle,
            "body_height": body_height,
            "height_ratio": height_ratio,
            "hip_drop": hip_drop,
            "motion": motion
        }


# =========================================================
# 可视化
# =========================================================
def draw_point(frame, p, color, label):
    x, y = int(p[0]), int(p[1])
    cv2.circle(frame, (x, y), 6, color, -1)
    cv2.putText(frame, label, (x + 6, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

def draw_text_lines(frame, lines, x=10, y=20, color=(0, 255, 0)):
    for line in lines:
        cv2.putText(frame, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        y += 22


def format_kp(name, kp):
    return f"{name}=({kp[0]:.1f},{kp[1]:.1f},vis={kp[2]:.2f})"


# =========================================================
# 主程序
# =========================================================
def main():
    if WEB_PREVIEW and not FLASK_AVAILABLE:
        print("[WARN] WEB_PREVIEW=True but Flask is not installed. Disable web preview.")

    web_enabled = WEB_PREVIEW and FLASK_AVAILABLE
    if web_enabled:
        start_web_preview_server()
        print(f"[INFO] Web preview started: http://127.0.0.1:{WEB_PORT}/video_feed")
        print(f"[INFO] LAN preview URL: http://<jetson-ip>:{WEB_PORT}/video_feed")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not cap.isOpened():
        print("[ERROR] Cannot open camera")
        return

    tracker = PoseTracker()
    follower = FollowController(FRAME_WIDTH)
    fall_detector = FallDetector()
    commander = SerialCommander(SERIAL_PORT, BAUD_RATE, SERIAL_ENABLED)

    fps_hist = deque(maxlen=10)
    last_time = time.time()
    last_debug_print_time = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[WARN] Failed to read frame")
                break

            keypoints, result = tracker.extract(frame)
            now = time.time()

            if DEBUG_PRINT and (now - last_debug_print_time) >= DEBUG_PRINT_INTERVAL:
                h, w = frame.shape[:2]
                has_landmarks = result is not None and result.pose_landmarks is not None
                print(f"[DEBUG] frame_ok={ret} shape={w}x{h} landmarks={has_landmarks}")

                if keypoints is not None:
                    debug_lines = [
                        format_kp("nose", keypoints["nose"]),
                        format_kp("left_shoulder", keypoints["left_shoulder"]),
                        format_kp("right_shoulder", keypoints["right_shoulder"]),
                        format_kp("left_hip", keypoints["left_hip"]),
                        format_kp("right_hip", keypoints["right_hip"]),
                        format_kp("left_ankle", keypoints["left_ankle"]),
                        format_kp("right_ankle", keypoints["right_ankle"]),
                    ]
                    print("[DEBUG] " + " | ".join(debug_lines))
                else:
                    print("[DEBUG] keypoints=None (no person detected)")

                last_debug_print_time = now

            cmd = "S\n"
            orientation = "unknown"
            follow_info = None
            fall_info = None

            if result and result.pose_landmarks:
                mp.solutions.drawing_utils.draw_landmarks(
                    frame,
                    result.pose_landmarks,
                    mp.solutions.pose.POSE_CONNECTIONS
                )

            if keypoints is not None:
                body_points = follower.get_body_points(keypoints)

                if body_points is not None:
                    shoulder_mid, hip_mid, ankle_mid = body_points

                    draw_point(frame, shoulder_mid, (255, 0, 0), "ShoulderMid")
                    draw_point(frame, hip_mid, (0, 255, 0), "HipMid")
                    draw_point(frame, ankle_mid, (0, 0, 255), "AnkleMid")

                    orientation = follower.estimate_orientation(keypoints)
                    fall_info = fall_detector.update(shoulder_mid, hip_mid, ankle_mid)

                    # 跌倒优先级 > 跟随
                    if fall_info["state"] == STATE_ALARM:
                        cmd = "A\n"
                    elif fall_info["state"] in [STATE_FALLING, STATE_LYING]:
                        cmd = "S\n"
                    else:
                        follow_info = follower.get_follow_command(shoulder_mid, hip_mid, ankle_mid)
                        cmd = follow_info["cmd"]
                        if DEBUG_PRINT:
                            print(f"[FOLLOW] cmd={cmd} reason={follow_info['reason']}")
                else:
                    cmd = "S\n"
                    if DEBUG_PRINT:
                        print("[FOLLOW] cmd=S reason=missing_valid_pairs(shoulder/hip/ankle visibility)")
            else:
                cmd = "S\n"
                if DEBUG_PRINT:
                    print("[FOLLOW] cmd=S reason=no_pose_detected")

            commander.send(cmd)

            now = time.time()
            fps = 1.0 / max(now - last_time, 1e-6)
            last_time = now
            fps_hist.append(fps)
            fps_avg = sum(fps_hist) / len(fps_hist)

            lines = [
                f"CMD: {cmd}",
                f"FPS: {fps_avg:.1f}",
                f"Orientation: {orientation}"
            ]

            if follow_info:
                lines.append(f"error_x: {follow_info['error_x']:.1f}")
                lines.append(f"body_h: {follow_info['body_height']:.1f}")

            if fall_info:
                lines.append(f"fall: {fall_info['state']}")
                lines.append(f"angle: {fall_info['angle_deg']:.1f}")
                lines.append(f"h_ratio: {fall_info['height_ratio']:.2f}")
                lines.append(f"hip_drop: {fall_info['hip_drop']:.1f}")
                lines.append(f"motion: {fall_info['motion']:.1f}")

            draw_text_lines(frame, lines)
            if web_enabled:
                update_web_frame(frame)

            if SHOW_WINDOW:
                cv2.imshow("Pose Follow + Fall Detection", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord('q'):
                    break
                elif key == ord('r'):
                    fall_detector.reset()
                    print("[INFO] Fall detector reset")
                elif key == ord('s'):
                    commander.send("S\n", force=True)
                elif key == ord('a'):
                    commander.send("A\n", force=True)

    finally:
        commander.send("S\n", force=True)
        commander.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
