import cv2
import time
import math
import serial
import mediapipe as mp
import threading
from collections import deque

# ===================== Web预览支持 =====================
try:
    from flask import Flask, Response
    FLASK_AVAILABLE = True
except Exception:
    FLASK_AVAILABLE = False

# ===================== 配置 =====================
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
SHOW_WINDOW = False  # Jetson headless设为False
DEBUG_PRINT = True
DEBUG_PRINT_INTERVAL = 0.5

SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE = 115200
SERIAL_ENABLED = True  # 调试先关闭串口

# ===================== Web预览配置 =====================
WEB_PREVIEW = True
WEB_HOST = "0.0.0.0"
WEB_PORT = 5000
WEB_JPEG_QUALITY = 80

# 跟随阈值
X_TOL = 50  # 水平容忍
FORWARD_HEIGHT = 320
STOP_HEIGHT = 400
SHOULDER_NEAR = 60  # 肩宽阈值，小于这个说明离得远

# 串口节流
MIN_CMD_INTERVAL = 0.1
SMOOTH_ALPHA = 0.35
VISIBILITY_THRESHOLD = 0.5

# ===================== Web预览变量 =====================
latest_jpeg = None
latest_jpeg_lock = threading.Lock()

def update_web_frame(frame):
    """更新Web预览帧"""
    global latest_jpeg
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), WEB_JPEG_QUALITY]
    ok, buffer = cv2.imencode(".jpg", frame, encode_param)
    if not ok:
        return
    with latest_jpeg_lock:
        latest_jpeg = buffer.tobytes()

def mjpeg_generator():
    """MJPEG流生成器"""
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
    """启动Flask Web服务器"""
    app = Flask(__name__)

    @app.route("/")
    def index():
        return (
            "<html><body>"
            "<h3>Pose Follow Web Preview</h3>"
            "<img src='/video_feed' style='max-width:100%;height:auto;' />"
            "<hr>"
            "<p>命令说明：</p>"
            "<ul>"
            "<li><b>F</b> - 前进</li>"
            "<li><b>B</b> - 后退</li>"
            "<li><b>L</b> - 左转</li>"
            "<li><b>R</b> - 右转</li>"
            "<li><b>S</b> - 停止</li>"
            "</ul>"
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
    print(f"[INFO] Web preview started: http://{WEB_HOST}:{WEB_PORT}")
    return server_thread

# ===================== 工具函数 =====================
def midpoint(p1, p2):
    return ((p1[0]+p2[0])*0.5, (p1[1]+p2[1])*0.5)

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
            x = self.alpha*point[0] + (1-self.alpha)*self.value[0]
            y = self.alpha*point[1] + (1-self.alpha)*self.value[1]
            self.value = (x,y)
        return self.value

# ===================== Pose Tracker =====================
class PoseTracker:
    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
    def get_lm(self, landmarks, idx, w, h):
        lm = landmarks[idx]
        return (lm.x*w, lm.y*h, lm.visibility)
    def extract(self, frame):
        h,w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.pose.process(rgb)
        if not result.pose_landmarks:
            return None, result
        lm = result.pose_landmarks.landmark
        P = self.mp_pose.PoseLandmark
        keypoints = {
            "left_shoulder": self.get_lm(lm,P.LEFT_SHOULDER.value,w,h),
            "right_shoulder": self.get_lm(lm,P.RIGHT_SHOULDER.value,w,h),
            "left_hip": self.get_lm(lm,P.LEFT_HIP.value,w,h),
            "right_hip": self.get_lm(lm,P.RIGHT_HIP.value,w,h),
            "left_ankle": self.get_lm(lm,P.LEFT_ANKLE.value,w,h),
            "right_ankle": self.get_lm(lm,P.RIGHT_ANKLE.value,w,h),
            "nose": self.get_lm(lm,P.NOSE.value,w,h)
        }
        return keypoints, result
    @staticmethod
    def valid_pair(a,b,threshold=VISIBILITY_THRESHOLD):
        return a[2]>threshold and b[2]>threshold

# ===================== Follow Controller =====================
class FollowController:
    def __init__(self, frame_width):
        self.frame_width = frame_width
        self.shoulder_smoother = ExpSmoother2D(SMOOTH_ALPHA)
        self.hip_smoother = ExpSmoother2D(SMOOTH_ALPHA)
        self.ankle_smoother = ExpSmoother2D(SMOOTH_ALPHA)
        self.last_cmd = None
        self.last_send_time = 0
    def get_body_points(self,keypoints):
        ls = keypoints["left_shoulder"]
        rs = keypoints["right_shoulder"]
        lh = keypoints["left_hip"]
        rh = keypoints["right_hip"]
        la = keypoints["left_ankle"]
        ra = keypoints["right_ankle"]
        if not PoseTracker.valid_pair(ls,rs): return None
        if not PoseTracker.valid_pair(lh,rh): return None
        if not PoseTracker.valid_pair(la,ra): return None
        shoulder_mid = midpoint(ls[:2],rs[:2])
        hip_mid = midpoint(lh[:2],rh[:2])
        ankle_mid = midpoint(la[:2],ra[:2])
        shoulder_mid = self.shoulder_smoother.update(shoulder_mid)
        hip_mid = self.hip_smoother.update(hip_mid)
        ankle_mid = self.ankle_smoother.update(ankle_mid)
        return shoulder_mid, hip_mid, ankle_mid
    def get_follow_command(self, shoulder_mid, hip_mid, ankle_mid, keypoints):
        # 计算身体中心
        body_center_x = (shoulder_mid[0] + hip_mid[0]) * 0.5
        error_x = body_center_x - self.frame_width * 0.5
    
        # 身体高度和肩宽
        body_height = abs(ankle_mid[1] - shoulder_mid[1])
        shoulder_width = abs(keypoints["left_shoulder"][0] - keypoints["right_shoulder"][0])
    
        # 决策逻辑
        cmd = "S"  # 默认停止
    
        # 前后优先
        if body_height < FORWARD_HEIGHT:
            cmd = "F"
        elif body_height >= STOP_HEIGHT:
            cmd = "B"
        else:
            # 高度合适，再判断横向
            if error_x < -X_TOL:
                cmd = "L"
            elif error_x > X_TOL:
                cmd = "R"
            else:
                cmd = "S"
    
        reason = (f"error_x={error_x:.1f}, body_height={body_height:.1f}, "
                  f"shoulder_width={shoulder_width:.1f}, cmd={cmd}")
        
        return {
            "cmd": cmd,
            "body_center_x": body_center_x,
            "error_x": error_x,
            "body_height": body_height,
            "shoulder_width": shoulder_width,
            "reason": reason,
            "shoulder_mid": shoulder_mid,
            "hip_mid": hip_mid,
            "ankle_mid": ankle_mid
        }
    def should_send(self, cmd):
        """串口节流"""
        now = time.time()
        if cmd == self.last_cmd and (now - self.last_send_time) < MIN_CMD_INTERVAL:
            return False
        self.last_cmd = cmd
        self.last_send_time = now
        return True

# ===================== 可视化 =====================
def draw_point(frame,p,color,label):
    x,y=int(p[0]),int(p[1])
    cv2.circle(frame,(x,y),6,color,-1)
    cv2.putText(frame,label,(x+6,y-6),cv2.FONT_HERSHEY_SIMPLEX,0.5,color,1)
def draw_text_lines(frame,lines,x=10,y=20,color=(0,255,0)):
    for line in lines:
        cv2.putText(frame,line,(x,y),cv2.FONT_HERSHEY_SIMPLEX,0.55,color,2)
        y+=22

# ===================== 串口模拟 =====================
class SerialCommander:
    def __init__(self,port,baud,enabled=False):
        self.enabled=enabled
        self.ser = None
        if enabled:
            try:
                self.ser = serial.Serial(port, baud, timeout=1)
                time.sleep(2)
                print(f"[INFO] Serial connected: {port}")
            except Exception as e:
                print(f"[WARN] Serial not available: {e}")
                self.enabled = False
    def send(self,cmd,force=False):
        if not self.enabled:
            print(f"[CMD] {cmd}")
            return
        if self.ser:
            try:
                self.ser.write((cmd+'\n').encode())
            except Exception as e:
                print(f"[WARN] Serial write failed: {e}")
    def close(self):
        if self.ser:
            self.ser.close()

# ===================== 主循环 =====================
def main():
    # 启动Web预览
    if WEB_PREVIEW and FLASK_AVAILABLE:
        start_web_preview_server()
        print(f"[INFO] Web preview: http://127.0.0.1:{WEB_PORT}")
    elif WEB_PREVIEW and not FLASK_AVAILABLE:
        print("[WARN] WEB_PREVIEW=True but Flask not installed. Run: pip install flask")
    
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    if not cap.isOpened(): 
        print("[ERROR] Cannot open camera")
        return
    
    tracker = PoseTracker()
    follower = FollowController(FRAME_WIDTH)
    commander = SerialCommander(SERIAL_PORT, BAUD_RATE, SERIAL_ENABLED)
    fps_hist = deque(maxlen=10)
    last_time = time.time()
    last_debug = 0.0
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret: 
                break
            
            keypoints, result = tracker.extract(frame)
            now = time.time()
            
            # 绘制骨骼关键点
            if result and result.pose_landmarks:
                mp.solutions.drawing_utils.draw_landmarks(
                    frame,
                    result.pose_landmarks,
                    mp.solutions.pose.POSE_CONNECTIONS
                )
            
            if keypoints:
                body_points = follower.get_body_points(keypoints)
                if body_points:
                    shoulder_mid, hip_mid, ankle_mid = body_points
                    draw_point(frame, shoulder_mid, (255,0,0), "ShoulderMid")
                    draw_point(frame, hip_mid, (0,255,0), "HipMid")
                    draw_point(frame, ankle_mid, (0,0,255), "AnkleMid")
                    
                    follow_info = follower.get_follow_command(shoulder_mid, hip_mid, ankle_mid, keypoints)
                    cmd = follow_info["cmd"]
                    
                    # 节流发送
                    if follower.should_send(cmd):
                        commander.send(cmd)
                    
                    if DEBUG_PRINT and (now - last_debug) >= DEBUG_PRINT_INTERVAL:
                        print(f"[FOLLOW] {follow_info['reason']}")
                        last_debug = now
                else:
                    cmd = "S"
                    if follower.should_send(cmd):
                        commander.send(cmd)
                    if DEBUG_PRINT and (now - last_debug) >= DEBUG_PRINT_INTERVAL:
                        print("[FOLLOW] missing keypoints")
                        last_debug = now
            else:
                cmd = "S"
                if follower.should_send(cmd):
                    commander.send(cmd)
                if DEBUG_PRINT and (now - last_debug) >= DEBUG_PRINT_INTERVAL:
                    print("[FOLLOW] no pose detected")
                    last_debug = now
            
            # FPS显示
            fps = 1.0/max(now-last_time,1e-6)
            last_time = now
            fps_hist.append(fps)
            fps_avg = sum(fps_hist)/len(fps_hist)
            
            lines = [f"CMD:{cmd}", f"FPS:{fps_avg:.1f}"]
            if keypoints and body_points:
                lines.append(f"body_h:{follow_info['body_height']:.1f} shoulder_w:{follow_info['shoulder_width']:.1f} error_x:{follow_info['error_x']:.1f}")
            draw_text_lines(frame, lines)
            
            # 更新Web预览
            if WEB_PREVIEW and FLASK_AVAILABLE:
                update_web_frame(frame)
            
            if SHOW_WINDOW:
                cv2.imshow("Follow", frame)
                if cv2.waitKey(1)&0xFF in [27, ord('q')]:
                    break
                    
    finally:
        commander.send("S", force=True)
        commander.close()
        cap.release()
        cv2.destroyAllWindows()

if __name__=="__main__":
    main()
