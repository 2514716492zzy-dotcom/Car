import cv2
import time
import math
import serial
import mediapipe as mp
import threading
from collections import deque

# ===================== 配置 =====================
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
SHOW_WINDOW = True
DEBUG_PRINT = True
DEBUG_PRINT_INTERVAL = 0.5

SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE = 115200
SERIAL_ENABLED = False  # 调试先关闭串口

WEB_PREVIEW = False  # 简化版先不启用Web
MIN_CMD_INTERVAL = 0.1
SMOOTH_ALPHA = 0.35
VISIBILITY_THRESHOLD = 0.5

# 跟随阈值
X_TOL = 50  # 水平容忍
FORWARD_HEIGHT = 280
STOP_HEIGHT = 320
SHOULDER_NEAR = 140  # 肩宽阈值，小于这个说明离得远

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
    def get_follow_command(self,shoulder_mid,hip_mid,ankle_mid,keypoints):
        body_center_x = (shoulder_mid[0]+hip_mid[0])*0.5
        error_x = body_center_x - self.frame_width*0.5
        body_height = abs(ankle_mid[1]-shoulder_mid[1])
        shoulder_width = abs(keypoints["left_shoulder"][0]-keypoints["right_shoulder"][0])
        cmd = "S"
        if error_x < -X_TOL: cmd = "L"
        elif error_x > X_TOL: cmd = "R"
        need_forward = (body_height < FORWARD_HEIGHT) and (shoulder_width < SHOULDER_NEAR)
        if abs(error_x)<=X_TOL:
            if need_forward: cmd="F"
            elif body_height>=STOP_HEIGHT: cmd="B"
            else: cmd="S"
        else:
            if need_forward: cmd+="F"
        reason = f"error_x={error_x:.1f}, body_height={body_height:.1f}, shoulder_width={shoulder_width:.1f}, cmd={cmd}"
        return {"cmd":cmd,"body_center_x":body_center_x,"error_x":error_x,
                "body_height":body_height,"shoulder_width":shoulder_width,
                "reason":reason,"shoulder_mid":shoulder_mid,"hip_mid":hip_mid,
                "ankle_mid":ankle_mid}

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
    def send(self,cmd,force=False):
        print(f"[CMD] {cmd}")
    def close(self): pass

# ===================== 主循环 =====================
def main():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    if not cap.isOpened(): print("[ERROR] Cannot open camera"); return
    tracker = PoseTracker()
    follower = FollowController(FRAME_WIDTH)
    commander = SerialCommander(SERIAL_PORT,BAUD_RATE,SERIAL_ENABLED)
    fps_hist = deque(maxlen=10)
    last_time = time.time()
    last_debug = 0.0
    try:
        while True:
            ret, frame = cap.read()
            if not ret: break
            keypoints,result = tracker.extract(frame)
            now = time.time()
            if keypoints:
                body_points = follower.get_body_points(keypoints)
                if body_points:
                    shoulder_mid,hip_mid,ankle_mid = body_points
                    draw_point(frame,shoulder_mid,(255,0,0),"ShoulderMid")
                    draw_point(frame,hip_mid,(0,255,0),"HipMid")
                    draw_point(frame,ankle_mid,(0,0,255),"AnkleMid")
                    follow_info = follower.get_follow_command(shoulder_mid,hip_mid,ankle_mid,keypoints)
                    cmd = follow_info["cmd"]
                    # 调试信息
                    print(f"[FOLLOW DEBUG] {follow_info['reason']}")
                    print(f"  ShoulderMid={follow_info['shoulder_mid']}, HipMid={follow_info['hip_mid']}, AnkleMid={follow_info['ankle_mid']}")
                else:
                    cmd="S"
                    print("[FOLLOW DEBUG] missing keypoints")
            else:
                cmd="S"
                print("[FOLLOW DEBUG] no pose detected")
            commander.send(cmd)
            # FPS显示
            fps = 1.0/max(now-last_time,1e-6)
            last_time = now
            fps_hist.append(fps)
            fps_avg = sum(fps_hist)/len(fps_hist)
            lines=[f"CMD:{cmd}",f"FPS:{fps_avg:.1f}"]
            if keypoints and body_points: lines.append(f"body_h:{follow_info['body_height']:.1f} shoulder_w:{follow_info['shoulder_width']:.1f} error_x:{follow_info['error_x']:.1f}")
            draw_text_lines(frame,lines)
            if SHOW_WINDOW:
                cv2.imshow("Follow",frame)
                if cv2.waitKey(1)&0xFF in [27,ord('q')]: break
    finally:
        commander.close()
        cap.release()
        cv2.destroyAllWindows()

if __name__=="__main__":
    main()
