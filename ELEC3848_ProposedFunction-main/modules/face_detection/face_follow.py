"""
Single-file face-follow skeleton for Raspberry Pi + Arduino robot.

- Minimal, single-responsibility functions (open/capture/detect/metric/decide/send)
- Two modes: `detect` (visualize & print metrics) and `follow` (camera + control loops)
- Uses Haar cascade by default (lightweight); can be swapped for MediaPipe later
- Integrates with existing `SerialManager` via `send_mapped_command`

This file is a starting point and contains clear places to calibrate thresholds
and add owner-recognition later.

Usage examples:
  python face_detection/face_follow.py --mode detect
  python face_detection/face_follow.py --mode follow

Note: This file intentionally keeps each function small and single-purpose.
"""

import time
import threading
import queue
import logging
from collections import deque
from pathlib import Path
import argparse
import json
import os
import subprocess
import glob
import sys

try:
    import cv2
    OPENCV_AVAILABLE = True
except Exception:
    OPENCV_AVAILABLE = False

# Optional Raspberry Pi legacy camera support (picamera)
try:
    import picamera
    import picamera.array as picarray
    PICAMERA_AVAILABLE = True
except Exception:
    picamera = None
    picarray = None
    PICAMERA_AVAILABLE = False

# Optional modern Picamera2 (libcamera-based) support
try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except Exception:
    Picamera2 = None
    PICAMERA2_AVAILABLE = False

# Hardware imports (existing project)
try:
    from modules.hardware_communication.serial_manager import SerialManager
except Exception as e:
    SerialManager = None
    SERIAL_MANAGER_IMPORT_ERROR = str(e)
else:
    SERIAL_MANAGER_IMPORT_ERROR = None

try:
    from modules.text_to_speech.tts_module import TextToSpeech
except Exception:
    TextToSpeech = None

# --------------------------------------------------
# Config and defaults
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGFILE = LOGS_DIR / "face_follow.log"

DEFAULT_CONFIG = {
    'frame_size': (320, 240),
    'metric': 'normalized_area',
    'far_threshold': 0.067093,   
    'close_threshold': 0.163649,  # midpoint-based threshold (rounded)
    'x_tolerance_norm': 0.12, # fraction of frame width to consider centered
    'min_command_interval_s': 0.0002,
    'min_frames_for_decision': 3,
    'decision_interval_s': 0.05,
    'min_consistent_frames': 2,
    'ema_alpha_metric': 0.35,
    'ema_alpha_centroid': 0.35,
    'median_window': 6,
    'lost_frames_threshold': 8,
    'lost_confirm_frames': 6,
    'use_obstacle_check': False,
    'safety_distance_cm': 20,
    'haar_cascade': None,  # None => use OpenCV default path
    'visualize': False,
    'camera_index': 0,
    'search_rotate_duration_s': 2.0,  # how long to rotate before switching direction in search
    'search_oscillate_duration_s': 2.0, # total time to oscillate right/left before choosing one direction
    'camera_open_retries': 3,
    'camera_open_retry_delay_s': 1.0,
    'disable_sending': False,
    'search_exit_immediate_stop': True,  # NEW: Stop immediately when face found during search
    'search_pause_duration_s': 0.5,   # How long to pause between rotations
    # Short movement pulse for nudge-style centering/motion (seconds). Set >0 to use pulses.
    # Applies to forward/backward/rotate/search commands. `rotate_pulse_s` is kept
    # for backward compatibility but `movement_pulse_s` is the canonical key.
    'movement_pulse_s': 0.3,
    'rotate_pulse_s': 0.3,
    # If True, the STOP sent after a pulse is forced immediately (bypasses rate-limiter)
    # which ensures the pulse duration is enforced. Set False to send STOP through
    # the normal rate-limiter (may suppress stop if recently sent other commands).
    'pulse_force_stop': True,
    # After completing a pulsed command and forcing STOP, optionally wait this
    # additional delay before allowing the next command. Useful to ensure a
    # visible pause between nudges. Set to 1.0 to match your request.
    'post_pulse_delay_s': 1.0,
}

# --------------------------------------------------
# Logging setup
# --------------------------------------------------
logger = logging.getLogger('face_follow')
# Default to INFO to avoid excessive per-frame logging; DEBUG still available for development
logger.setLevel(logging.INFO)
fmt = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
# Write the stream handler to stdout (not stderr) so logs remain visible
# even when stderr is redirected (e.g. `python main.py 2>/dev/null`).
ch = logging.StreamHandler(stream=sys.stdout)
ch.setFormatter(fmt)
logger.addHandler(ch)
fh = logging.FileHandler(LOGFILE)
fh.setFormatter(fmt)
logger.addHandler(fh)

# --------------------------------------------------
# Small helpers
# --------------------------------------------------

def now() -> float:
    return time.time()


def detect_camera_devices(check_opencv_samples: int = 2):
    """Probe the system for camera devices and try to map working nodes.

    Returns a dict with lists of discovered `/dev/media*` and `/dev/video*` nodes,
    optional outputs of `v4l2-ctl --list-devices` and `media-ctl -p` when available,
    and attempts to open a frame from each `/dev/video*` node (if OpenCV available).
    Also attempts to instantiate `Picamera2` and legacy `picamera` wrappers when
    those libraries are installed to verify which backend can capture frames.
    """
    info = {'media_nodes': [], 'video_nodes': [], 'v4l2_ctl': None, 'media_ctl': None, 'opencv_success': {}, 'picamera2_success': False, 'picamera_success': False}

    # list device nodes
    info['media_nodes'] = sorted(glob.glob('/dev/media*'))
    info['video_nodes'] = sorted(glob.glob('/dev/video*'))

    # attempt to call v4l2-ctl and media-ctl if present
    try:
        out = subprocess.check_output(['v4l2-ctl', '--list-devices'], stderr=subprocess.STDOUT, text=True)
        info['v4l2_ctl'] = out.strip()
    except Exception:
        info['v4l2_ctl'] = None

    try:
        out = subprocess.check_output(['media-ctl', '-p'], stderr=subprocess.STDOUT, text=True)
        info['media_ctl'] = out.strip()
    except Exception:
        info['media_ctl'] = None

    # Try opening video nodes with OpenCV if available
    if OPENCV_AVAILABLE and info['video_nodes']:
        for node in info['video_nodes']:
            try:
                vc = cv2.VideoCapture(node)

                # Force MJPG format for USB webcams
                vc.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                vc.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)   # choose desired resolution
                vc.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                vc.set(cv2.CAP_PROP_FPS, 30)

                ok = False
                if vc and vc.isOpened():
                    # attempt a small number of reads
                    for _ in range(check_opencv_samples):
                        ret, _ = vc.read()
                        if ret:
                            ok = True
                            break

                try:
                    vc.release()
                except Exception:
                    pass
                info['opencv_success'][node] = bool(ok)
            except Exception:
                info['opencv_success'][node] = False

    # Try Picamera2 if available
    if PICAMERA2_AVAILABLE:
        try:
            p2 = Picamera2()
            # try a quick capture
            try:
                p2.start()
                arr = p2.capture_array()
                if arr is not None:
                    info['picamera2_success'] = True
            finally:
                try:
                    p2.stop()
                except Exception:
                    pass
                try:
                    p2.close()
                except Exception:
                    pass
        except Exception:
            info['picamera2_success'] = False

    # Try legacy picamera wrapper
    if PICAMERA_AVAILABLE:
        try:
            pc = PiCameraWrapper(resolution=(320,240))
            try:
                ok, _ = pc.read()
                info['picamera_success'] = bool(ok)
            finally:
                try:
                    pc.release()
                except Exception:
                    pass
        except Exception:
            info['picamera_success'] = False

    return info

# --------------------------------------------------
# Camera helpers
# --------------------------------------------------

# Lightweight wrapper that exposes a VideoCapture-like interface around
# the legacy `picamera` module so the rest of the code can call `.read()`
# and `.release()` uniformly. This is optional and used only when
# `picamera` is installed and `pi_camera=True` is requested.
class PiCameraWrapper:
    def __init__(self, resolution=(640, 480), framerate=60):
        if not PICAMERA_AVAILABLE:
            raise RuntimeError('picamera is not available')
        # picamera expects (width,height) as resolution tuple
        self.resolution = tuple(resolution)
        self.framerate = framerate
        # Initialize camera
        self.camera = picamera.PiCamera()
        self.camera.resolution = self.resolution
        self.camera.framerate = self.framerate
        # Use the RGB array adapter to get frames as numpy arrays
        self.raw_capture = picarray.PiRGBArray(self.camera, size=self.resolution)
        # Allow camera to warm up
        time.sleep(0.2)
        # Create a continuous capture iterator using the video port for speed
        self._stream = self.camera.capture_continuous(self.raw_capture, format='bgr', use_video_port=True)
        self._iterator = iter(self._stream)

    def read(self):
        try:
            f = next(self._iterator)
            frame = f.array
            # Reset buffer for next frame
            self.raw_capture.truncate(0)
            return True, frame
        except Exception:
            return False, None

    def isOpened(self):
        # Always true while the wrapper exists
        return True

    def release(self):
        try:
            # Close the continuous capture stream
            try:
                self._stream.close()
            except Exception:
                pass
            # Close camera
            try:
                self.camera.close()
            except Exception:
                pass
        except Exception:
            pass


class Picamera2Wrapper:
    """Wrapper for the libcamera-based `picamera2` library.

    Provides a minimal VideoCapture-like interface: `read() -> (ret, frame)`,
    `isOpened() -> bool`, and `release()` so the rest of the module can
    operate unchanged.
    """
    def __init__(self, resolution=(640, 480), framerate=60):
        if not PICAMERA2_AVAILABLE:
            raise RuntimeError('picamera2 is not available')
        # Create and configure Picamera2
        self.picam = Picamera2()
        # Picamera2 expects size as (w,h) in configuration
        try:
            config = self.picam.create_preview_configuration({'main': {'size': tuple(resolution)}})
            self.picam.configure(config)
        except Exception:
            # Fall back to default configuration if preview config not supported
            try:
                self.picam.configure(self.picam.create_preview_configuration({'size': tuple(resolution)}))
            except Exception:
                pass
        self.picam.start()
        self._running = True

    def read(self):
        if not self._running:
            return False, None
        try:
            arr = self.picam.capture_array()
            # picamera2 returns RGB arrays; convert to BGR for OpenCV if available
            if OPENCV_AVAILABLE:
                try:
                    arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                except Exception:
                    pass
            return True, arr
        except Exception:
            return False, None

    def isOpened(self):
        return self._running

    def release(self):
        try:
            self._running = False
            try:
                self.picam.stop()
            except Exception:
                pass
            try:
                self.picam.close()
            except Exception:
                pass
        except Exception:
            pass


def open_camera(pi_camera: bool = False, index: int = 0, size=(320,240)):
    """Open camera and return handle.

    If `pi_camera` is True, prefer the V4L2 backend which is commonly used
    on Raspberry Pi with the `bcm2835-v4l2` driver. This function performs
    a short warm-up (reads several frames) to ensure the device is ready.
    """
    # Prefer using Picamera2 (modern libcamera) when requested on Pi and available,
    # then fall back to the legacy picamera wrapper if present.
    if pi_camera:
        if PICAMERA2_AVAILABLE:
            try:
                cam = Picamera2Wrapper(resolution=size)
                logger.info(f'Picamera2 wrapper opened resolution={size}')
                return cam
            except Exception as e:
                logger.warning(f'Failed to open Picamera2 wrapper: {e}; trying legacy picamera')
        if PICAMERA_AVAILABLE:
            try:
                cam = PiCameraWrapper(resolution=size)
                logger.info(f'PiCamera wrapper opened resolution={size}')
                return cam
            except Exception as e:
                logger.warning(f'Failed to open PiCamera wrapper: {e}; falling back to OpenCV VideoCapture')

    if not OPENCV_AVAILABLE:
        logger.error('OpenCV not available. Install opencv-python to use camera.')
        return None

    # Try to open the camera with a small verification step. Some platforms
    # (macOS Continuity Camera) can take a small amount of time to release/reopen
    # the device; attempt multiple retries and verify we can read a frame.
    retries = int(DEFAULT_CONFIG.get('camera_open_retries', 3))
    retry_delay = float(DEFAULT_CONFIG.get('camera_open_retry_delay_s', 1.0))
    w, h = size

    for attempt in range(1, retries + 1):
        # On Raspberry Pi prefer the V4L2 backend to avoid libcamera preview issues
        try:
            if pi_camera and hasattr(cv2, 'CAP_V4L2'):
                cam = cv2.VideoCapture(index, cv2.CAP_V4L2)
            else:
                cam = cv2.VideoCapture(index)
        except Exception:
            cam = cv2.VideoCapture(index)
        if not cam or not cam.isOpened():
            logger.warning(f'Attempt {attempt}/{retries}: failed to open camera index {index}')
            try:
                if cam:
                    cam.release()
            except Exception:
                pass
            if attempt < retries:
                time.sleep(retry_delay)
            continue

        # Set desired size and do a quick read to verify frames are available
        try:
            cam.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cam.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            # warm up: read a few frames (Pi may need longer)
            warm_ok = False
            warm_reads = 3 if pi_camera else 1
            for _ in range(warm_reads):
                ok, _ = cam.read()
                if ok:
                    warm_ok = True
                    break
                time.sleep(0.1)

            if not warm_ok:
                logger.warning(f'Attempt {attempt}/{retries}: opened camera but read failed; retrying')
                cam.release()
                if attempt < retries:
                    time.sleep(retry_delay)
                continue
        except Exception as e:
            logger.warning(f'Attempt {attempt}/{retries}: camera verification failed: {e}')
            try:
                cam.release()
            except Exception:
                pass
            if attempt < retries:
                time.sleep(retry_delay)
            continue

        logger.info(f'Camera opened index={index} size={size} (attempt {attempt})')
        return cam

    logger.error(f'Failed to open camera index {index} after {retries} attempts')
    return None


def close_camera(cam) -> None:
    if cam is None:
        return
    try:
        # Support wrappers (picamera) and OpenCV VideoCapture
        if hasattr(cam, 'release'):
            cam.release()
        elif hasattr(cam, 'close'):
            cam.close()
        logger.info('Camera released')
    except Exception as e:
        logger.warning(f'Error releasing camera: {e}')


def capture_frame(cam):
    """Capture single frame and return (ts, frame) or (ts, None) on failure."""
    if cam is None:
        return now(), None
    ret, frame = cam.read()
    ts = now()
    if not ret:
        logger.debug('Camera read failed')
        return ts, None
    return ts, frame

# --------------------------------------------------
# Detector
# --------------------------------------------------

def load_face_detector(method: str = 'haar', cascade_path: str = None):
    """Load and return a face detector object. For Haar cascade returns cv2.CascadeClassifier."""
    if not OPENCV_AVAILABLE:
        logger.error('OpenCV not available; cannot load detector')
        return None

    if method == 'haar':
        try:
            if cascade_path:
                path = cascade_path
            else:
                # Use OpenCV built-in path
                path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            detector = cv2.CascadeClassifier(path)
            if detector.empty():
                logger.error(f'Haar cascade failed to load from {path}')
                return None
            logger.info(f'Haar cascade loaded from {path}')
            return detector
        except Exception as e:
            logger.error(f'Error loading Haar cascade: {e}')
            return None
    else:
        logger.error('Unknown detector method requested')
        return None


def detect_face(detector, frame):
    """Detect primary face using the detector. Return None or dict with bbox, confidence, centroid.
    bbox = (x, y, w, h)
    """
    if detector is None or frame is None:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30,30))
    if faces is None or len(faces) == 0:
        return None

    # Choose the largest face by area
    faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)
    x, y, w, h = faces[0]
    cx = int(x + w/2)
    cy = int(y + h/2)
    return {'bbox': (int(x), int(y), int(w), int(h)), 'confidence': 1.0, 'centroid': (cx, cy)}

# --------------------------------------------------
# Metric helpers
# --------------------------------------------------

def bbox_area(bbox):
    if not bbox:
        return 0
    _, _, w, h = bbox
    return int(w) * int(h)


def normalized_area(bbox, frame_shape):
    if not bbox or not frame_shape:
        return 0.0
    area = bbox_area(bbox)
    H, W = frame_shape[0], frame_shape[1]
    total = max(1, W * H)
    return float(area) / float(total)

# --------------------------------------------------
# Controller: small, single-purpose functions
# --------------------------------------------------

def init_state(max_history: int = 6) -> dict:
    return {
        'last_cmd': 'stop',
        'last_ts': 0.0,
        'history': deque(maxlen=max_history),
        'lost_count': 0,
        'last_candidate': None,
        'last_final': None,
        'current_candidate': None,
        'current_final': None,
        'last_decision_ts': 0.0,
        'last_valid_centroid': None,  # NEW
        'last_valid_centroid_ts': 0.0,  # NEW
    }


def decide_command(history: deque, config: dict) -> str:
    """Decide a command based on recent detection history.
    Returns one of 'forward','backward','left','right','stop','search'.
    This function does not send commands; only decides.
    """
    # If no entries or all recent entries are None => search for face
    if not history or all((d is None or d.get('bbox') is None) for d in history):
        return 'search'

    # Use median of metrics to smooth
    metrics = [d['metric'] for d in history if d and d.get('metric') is not None]
    centroids = [d['centroid'] for d in history if d and d.get('centroid') is not None]
    if not metrics:
        return 'search'

    metrics_sorted = sorted(metrics)
    median_metric = metrics_sorted[len(metrics_sorted)//2]

    # centroid median
    xs = sorted([c[0] for c in centroids]) if centroids else []
    cx = xs[len(xs)//2] if xs else None

    # Prefer actual frame width from most recent frame in history
    W = None
    for entry in reversed(history):
        if entry and entry.get('frame') is not None:
            try:
                W = int(entry['frame'].shape[1])
                break
            except Exception:
                W = None
    if W is None:
        W = config.get('frame_size', (320,240))[0]
    x_tol = int(config.get('x_tolerance_norm', 0.12) * W)
    center_x = int(W/2)

    # PRIORITY 1: Horizontal alignment (do this FIRST before distance adjustments)
    if cx is not None:
        if cx > center_x + x_tol:
            logger.debug(f"Decision: rotate_right (cx={cx} > center+tol={center_x + x_tol})")
            return 'rotate_right'
        if cx < center_x - x_tol:
            logger.debug(f"Decision: rotate_left (cx={cx} < center-tol={center_x - x_tol})")
            return 'rotate_left'


    # PRIORITY 2: Distance control (only when horizontally centered)
    far_thresh = config.get('far_threshold', 0.006)
    close_thresh = config.get('close_threshold', 0.03)
    
    logger.debug(f"Decision metrics: median_metric={median_metric:.6f}, far={far_thresh}, close={close_thresh}")
    
    if median_metric < far_thresh:
        logger.debug(f"Decision: forward (too far)")
        return 'forward'
    if median_metric > close_thresh:
        logger.debug(f"Decision: backward (too close)")
        return 'backward'

    # Face is centered and at good distance
    logger.debug(f"Decision: stop (centered and good distance)")
    return 'stop'


def apply_hysteresis(candidate: str, state: dict, config: dict) -> str:
    """Apply simple hysteresis: avoid switching immediately between opposite commands.
    Keeps last_cmd for stability; if candidate equals last_cmd, return it.
    Otherwise allow change. This is intentionally conservative; you can make it
    stricter by requiring N consistent frames before switching (handled via history length).
    """
    last = state.get('last_cmd')
    if candidate == last:
        return candidate
    # Allow immediate stop always
    if candidate == 'stop':
        return 'stop'
    # For opposing forward/backward, require that candidate is different and history already indicates change
    # (higher-level control loop will enforce persistence/min_frames_for_decision)
    return candidate


def implement_search_behavior(hardware, state: dict, config: dict) -> str:
    """Return a rotate command to perform a simple search pattern with pauses.

    The function alternates between rotating and pausing to search slowly.
    Returns one of 'rotate_left', 'rotate_right', or 'stop' (for pause).
    """
    dur = float(config.get('search_rotate_duration_s', 0.8))  # Time to rotate
    pause_dur = float(config.get('search_pause_duration_s', 0.5))  # Time to pause
    osc_total = float(config.get('search_oscillate_duration_s', 4.0))  # Total oscillation time
    now_ts = now()

    # Initialize search state
    if 'search_start_time' not in state:
        state['search_start_time'] = now_ts
        state['search_phase_start'] = now_ts  # Track current phase timing
        state['search_is_paused'] = False  # Start with rotation, not pause
        
        # Use last valid centroid saved in state
        pref = 'right'
        last_valid_cx = None
        
        # Try to get last valid centroid from state (saved before search started)
        if 'last_valid_centroid' in state and state['last_valid_centroid'] is not None:
            last_valid_cx = state['last_valid_centroid'][0]
            logger.debug(f"Using saved last_valid_centroid: {state['last_valid_centroid']}")
        
        # If we have a valid centroid, determine preferred search direction
        if last_valid_cx is not None:
            W = None
            # Try to get frame width from history
            hist = state.get('history')
            if hist:
                for entry in reversed(hist):
                    if entry and entry.get('frame') is not None:
                        try:
                            W = int(entry['frame'].shape[1])
                            break
                        except Exception:
                            pass
            
            if W is None:
                W = config.get('frame_size', (320,240))[0]
            
            center_x = int(W/2)
            # Search in the direction the face was last seen
            pref = 'left' if last_valid_cx < center_x else 'right'
            logger.info(f'Face was last at cx={last_valid_cx}, center={center_x} → search {pref}')
        else:
            logger.info('No recent centroid found; defaulting to search right')

        state['search_preferred_direction'] = pref
        # Save the centroid we used for display
        state['search_reference_centroid'] = state.get('last_valid_centroid')
        logger.info(f'Starting search (oscillate phase), preferred_direction={pref}')

    elapsed = now_ts - state.get('search_start_time', now_ts)
    phase_elapsed = now_ts - state.get('search_phase_start', now_ts)

    # Determine if we should be rotating or paused
    is_paused = state.get('search_is_paused', False)
    
    if is_paused:
        # Currently paused - check if pause is done
        if phase_elapsed >= pause_dur:
            # End pause, start rotation
            state['search_is_paused'] = False
            state['search_phase_start'] = now_ts
            logger.debug("Search: ending pause, resuming rotation")
    else:
        # Currently rotating - check if rotation is done
        if phase_elapsed >= dur:
            # End rotation, start pause
            state['search_is_paused'] = True
            state['search_phase_start'] = now_ts
            logger.debug("Search: ending rotation, starting pause")

    # Decide which direction to rotate (or if paused)
    if elapsed < osc_total:
        # Oscillate: alternate direction every cycle
        cycle = int(elapsed // (dur + pause_dur))
        chosen = 'right' if (cycle % 2 == 0) else 'left'
        phase = 'oscillate'
    else:
        # After oscillation period, choose preferred direction and rotate continuously
        chosen = state.get('search_preferred_direction', 'right')
        phase = 'continuous'

    # If paused, return stop; otherwise return rotation command
    if state.get('search_is_paused', False):
        cmd = 'stop'
        logger.debug(f"Search: PAUSED (phase={phase})")
    else:
        cmd = 'rotate_right' if chosen == 'right' else 'rotate_left'
        logger.debug(f"Search: ROTATING {cmd} (phase={phase})")

    # Record search state for display and debugging
    try:
        state['search_phase'] = phase
        state['search_chosen'] = chosen
        state['search_elapsed'] = elapsed

        # Use saved reference centroid instead of searching history
        state['search_last_centroid'] = state.get('search_reference_centroid')
    except Exception:
        # Never let monitoring break the search behavior
        pass

    # Log at INFO only on phase changes (not every frame)
    log_key = f"{phase}_{chosen}_{'paused' if is_paused else 'rotating'}"
    if state.get('_last_search_log_key') != log_key:
        logger.info(f"Search: phase={phase} dir={chosen} paused={is_paused} last_centroid={state.get('search_last_centroid')}")
        state['_last_search_log_key'] = log_key
    
    return cmd

# --------------------------------------------------
# Actuator wrappers (Serial manager integration)
# --------------------------------------------------

COMMAND_MAP = {
    'forward': 'A',
    'backward': 'E',
    'left': 'H',
    'right': 'B',
    'rotate_left': 'C',
    'rotate_right': 'G',
    'stop': 'Z',  # IMPORTANT: Arduino sketch listens for 'Z' or 'z'
    'spray': 'W',
}


def send_movement_command(hardware, cmd_name: str) -> bool:
    """Send single high-level command to hardware; return True if sent.
    Minimal wrapper to keep one responsibility: sending only.
    """
    if hardware is None:
        logger.debug(f'Hardware not available, would send: {cmd_name}')
        return False

    try:
        return hardware.send_mapped_command(cmd_name)
    except Exception as e:
        logger.error(f'send_movement_command error: {e}')
        return False


def send_command_with_rate_limit(hardware, cmd_name: str, state: dict, config: dict) -> bool:
    now_ts = now()
    # Allow user to disable sending movement commands for dry-run/testing
    if config.get('disable_sending'):
        if not state.get('_dry_run_logged'):
            logger.info('Disable-sending mode active: movement commands will NOT be sent')
            state['_dry_run_logged'] = True
        logger.debug('Dry-run: would send %s', cmd_name)
        # pretend it was not sent so calling code doesn't think hardware acted
        state['last_cmd'] = cmd_name
        state['last_ts'] = now_ts
        return False
    if now_ts - state.get('last_ts', 0.0) < config.get('min_command_interval_s', 0.5):
        logger.debug('Rate limit: suppressing command %s', cmd_name)
        try:
            # Also print to stdout so the operator sees why no RTT was produced
            print(f"RATE-LIMIT: suppressing {cmd_name} now={now_ts:.3f} last_ts={state.get('last_ts', 0.0):.3f} min_int={config.get('min_command_interval_s')}")
            try:
                sys.stdout.flush()
            except Exception:
                pass
        except Exception:
            pass
        return False

    # If no hardware available, log once and act as dry-run (do not spam warnings)
    if hardware is None:
        if not state.get('_hardware_missing_logged'):
            logger.info('Hardware not available; running in dry-run mode. Movement commands will not be sent.')
            state['_hardware_missing_logged'] = True
        try:
            # Mirror the info to stdout for visibility
            print('HARDWARE-MISSING: hardware is None; running dry-run mode')
            try:
                sys.stdout.flush()
            except Exception:
                pass
        except Exception:
            pass
        return False

    # Measure RTT of the hardware send call when possible and record it in state
    start_send = now()
    success = send_movement_command(hardware, cmd_name)
    end_send = now()
    try:
        rtt = float(end_send - start_send)
        # store last RTT and maintain a small history
        state['_last_rtt_s'] = rtt
        hist = state.get('_rtt_history')
        if hist is None:
            from collections import deque as _dq
            state['_rtt_history'] = _dq(maxlen=20)
            hist = state['_rtt_history']
        try:
            hist.append(rtt)
        except Exception:
            pass
        logger.debug(f"Command RTT: {rtt:.4f}s for {cmd_name}")
        try:
            # Also print RTT to stdout for quick visibility
            print(f"RTT {rtt:.4f}s cmd={cmd_name}")
            try:
                sys.stdout.flush()
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        pass

    if success:
        state['last_cmd'] = cmd_name
        state['last_ts'] = now_ts
        logger.info(f"Sent command: {cmd_name} -> '{COMMAND_MAP.get(cmd_name, '?')}'")
    else:
        logger.warning(f'Failed to send command {cmd_name}')
    return success


def send_pulsed_command(hardware, cmd_name: str, state: dict, config: dict, pulse_s: float) -> bool:
    """Send a short movement pulse: send `cmd_name`, wait `pulse_s`, then stop.

    Works for forward/backward/rotate/search commands. The initial command is
    sent via `send_command_with_rate_limit` to respect rate limits; the STOP
    after the pulse can either be forced immediately (bypassing the rate-limiter)
    or sent through the rate-limiter depending on `config['pulse_force_stop']`.
    Returns True if the initial command was actually sent.
    """
    now_ts = now()
    pulse_s = float(pulse_s or 0.0)

    # Schedule a non-blocking pulse: send the initial command (if possible)
    # and record a pending stop time in `state['_pending_pulse']`. The main
    # control loop will process the pending stop when its time arrives.
    # This avoids blocking the control thread with sleeps.
    post_delay = float(config.get('post_pulse_delay_s', 0.0))

    # If we're in dry-run or hardware missing, simulate by scheduling a simulated pending pulse
    if config.get('disable_sending') or hardware is None:
        if not state.get('_dry_run_logged'):
            logger.info('Disable-sending mode active: movement commands will NOT be sent')
            state['_dry_run_logged'] = True
        logger.debug('Dry-run scheduling pulse: %s for %.3fs (post_delay=%.3fs)', cmd_name, pulse_s, post_delay)
        state['last_cmd'] = cmd_name
        state['last_ts'] = now_ts
        state['_pending_pulse'] = {
            'cmd': cmd_name,
            'stop_at': now_ts + float(pulse_s),
            'force_stop': bool(config.get('pulse_force_stop', True)),
            'simulated': True,
            'post_delay': post_delay,
        }
        return False

    # Attempt to send the requested movement (may be rate-limited). Record whether it was sent.
    sent = send_command_with_rate_limit(hardware, cmd_name, state, config)

    # Schedule pending stop to occur at now + pulse_s; control_loop will perform the STOP later.
    state['_pending_pulse'] = {
        'cmd': cmd_name,
        'stop_at': now() + float(pulse_s),
        'force_stop': bool(config.get('pulse_force_stop', True)),
        'simulated': False,
        'post_delay': post_delay,
    }

    logger.debug('Scheduled pending pulse for %s: stop_at=%.3f post_delay=%.3f', cmd_name, state['_pending_pulse']['stop_at'], post_delay)
    return bool(sent)


def send_pulsed_rotation(hardware, cmd_name: str, state: dict, config: dict, pulse_s: float) -> bool:
    """Compatibility wrapper for older rotate-specific calls."""
    return send_pulsed_command(hardware, cmd_name, state, config, pulse_s)


def is_safe_to_move_forward(hardware, config: dict) -> bool:
    """Query obstacle sensor if available. Minimal: return True unless `use_obstacle_check` True
    and hardware provides a get_distance method. This function keeps just the safety check.
    """
    if not config.get('use_obstacle_check'):
        return True
    # If hardware exposes a distance read API, call it. This repo's example used serial queries
    # like car.get_distance(ser, 'C') — the SerialManager doesn't provide that helper, so we return True
    logger.debug('Obstacle check requested but no sensor integration implemented; assuming safe')
    return True

# --------------------------------------------------
# Thread loops
# --------------------------------------------------

def camera_loop(cam, detector, frame_q: queue.Queue, stop_event: threading.Event, config: dict, display_q: queue.Queue = None):
    """Capture frames, detect face, compute metric, and enqueue detection dicts.
    Runs until stop_event is set.
    """
    while not stop_event.is_set():
        ts, frame = capture_frame(cam)
        if frame is None:
            time.sleep(0.02)
            continue

        det = detect_face(detector, frame)
        if det:
            metric = normalized_area(det['bbox'], frame.shape)
            item = {'ts': ts, 'bbox': det['bbox'], 'centroid': det['centroid'], 'metric': metric, 'frame': frame}
        else:
            item = {'ts': ts, 'bbox': None, 'centroid': None, 'metric': None, 'frame': frame}

        try:
            frame_q.put(item, timeout=0.2)
        except queue.Full:
            logger.debug('frame_q full; dropping frame')

        # Also forward to display queue (non-blocking) if requested
        if display_q is not None:
            try:
                display_q.put_nowait(item)
            except queue.Full:
                pass
        # Limit capture rate modestly
        time.sleep(0.02)


def control_loop(frame_q: queue.Queue, hardware, state: dict, config: dict, stop_event: threading.Event, tts=None):
    """Consume detection items and decide/send movement commands.
    """
    min_frames = config.get('min_frames_for_decision', 4)
    decision_interval = float(config.get('decision_interval_s', 0.8))
    ema_alpha_metric = float(config.get('ema_alpha_metric', 0.35))
    ema_alpha_centroid = float(config.get('ema_alpha_centroid', 0.35))
    min_consistent = int(config.get('min_consistent_frames', 2))
    lost_confirm = int(config.get('lost_confirm_frames', 6))

    while not stop_event.is_set():
        try:
            item = frame_q.get(timeout=0.5)
        except queue.Empty:
            continue

        # Maintain history
        state['history'].append(item)

        # Track last valid centroid for search reference
        if item.get('centroid') is not None:
            state['last_valid_centroid'] = tuple(item['centroid'])
            state['last_valid_centroid_ts'] = now()

 
        # Count consecutive lost frames
        if item.get('bbox') is None:
            state['lost_count'] = state.get('lost_count', 0) + 1
        else:
            state['lost_count'] = 0
            
            # Immediately exit search mode when face is detected
            if config.get('search_exit_immediate_stop', True) and 'search_start_time' in state:
                logger.info('Face detected during search - immediate exit')
                try:
                    del state['search_start_time']
                    if 'search_direction' in state:
                        del state['search_direction']
                    if 'search_preferred_direction' in state:
                        del state['search_preferred_direction']
                    if 'search_reference_centroid' in state:
                        del state['search_reference_centroid']
                except Exception:
                    pass
                
                # Force an immediate stop command
                if hardware is not None and not config.get('disable_sending'):
                    try:
                        send_movement_command(hardware, 'stop')
                        state['last_cmd'] = 'stop'
                        state['last_ts'] = now()
                        logger.info("Sent immediate STOP after face reacquired")
                    except Exception as e:
                        logger.warning(f"Failed to send immediate stop: {e}")

        # Only decide when we have enough frames
        if len(state['history']) < min_frames:
            continue

        now_ts = now()

        # Process any pending pulsed-stop events scheduled by `send_pulsed_command`.
        pending = state.get('_pending_pulse')
        if pending:
            # If the pulse is still active (stop time not reached) skip making new sends
            if now_ts < float(pending.get('stop_at', 0.0)):
                logger.debug('Pulse active until %.3f; skipping decision/send', float(pending.get('stop_at')))
                # Keep updating display/state but do not issue new commands yet
                # Update throttling marker to avoid rapid re-entry
                state['last_decision_ts'] = now_ts
                continue

            # Time to send the STOP for the pending pulse
            try:
                logger.debug('Pending pulse stop time reached; performing STOP (simulated=%s)', bool(pending.get('simulated')))
                if pending.get('simulated'):
                    # Simulate STOP and update state
                    state['last_cmd'] = 'stop'
                    state['last_ts'] = now()
                else:
                    # If configured to force stop, call send_movement_command and record RTT
                    if pending.get('force_stop', True):
                        t0 = now()
                        try:
                            send_movement_command(hardware, 'stop')
                        except Exception as e:
                            logger.warning(f'Forced STOP failed: {e}')
                        t1 = now()
                        # record RTT for the forced STOP
                        try:
                            rtt = float(t1 - t0)
                            state['_last_rtt_s'] = rtt
                            hist = state.get('_rtt_history')
                            if hist is None:
                                from collections import deque as _dq
                                state['_rtt_history'] = _dq(maxlen=20)
                                hist = state['_rtt_history']
                            try:
                                hist.append(rtt)
                            except Exception:
                                pass
                            try:
                                # Print RTT to stdout as well
                                print(f"RTT {rtt:.4f}s cmd=stop (forced)")
                                try:
                                    sys.stdout.flush()
                                except Exception:
                                    pass
                            except Exception:
                                pass
                        except Exception:
                            pass
                        state['last_cmd'] = 'stop'
                        state['last_ts'] = now()
                    else:
                        # Respect normal rate-limiter when sending STOP
                        send_command_with_rate_limit(hardware, 'stop', state, config)

                # After STOP, set a non-blocking pulse-block timestamp to prevent new sends
                post = float(pending.get('post_delay', 0.0))
                if post > 0.0:
                    state['pulse_block_until'] = now() + post
                    logger.debug('Pulse block active until %.3f', state['pulse_block_until'])

            except Exception as e:
                logger.warning(f'Error handling pending pulse stop: {e}')
            finally:
                try:
                    del state['_pending_pulse']
                except Exception:
                    pass


        # Build median-based metrics from history (robust to outliers)
        metrics = [d['metric'] for d in state['history'] if d and d.get('metric') is not None]
        centroids = [d['centroid'] for d in state['history'] if d and d.get('centroid') is not None]
        if not metrics:
            median_metric = 0.0
        else:
            metrics_sorted = sorted(metrics)
            median_metric = metrics_sorted[len(metrics_sorted)//2]

        cx = None
        if centroids:
            xs = sorted([c[0] for c in centroids])
            cx = xs[len(xs)//2]

        # Initialize EMA in state if not present
        if state.get('_ema_metric') is None:
            state['_ema_metric'] = median_metric
        else:
            state['_ema_metric'] = ema_alpha_metric * median_metric + (1.0 - ema_alpha_metric) * state['_ema_metric']

        if cx is not None:
            if state.get('_ema_cx') is None:
                state['_ema_cx'] = float(cx)
            else:
                state['_ema_cx'] = ema_alpha_centroid * float(cx) + (1.0 - ema_alpha_centroid) * state['_ema_cx']
        else:
            # If no centroid, keep previous EMA centroid unchanged
            state['_ema_cx'] = state.get('_ema_cx')

        # Use smoothed values for decision making
        sm_metric = float(state.get('_ema_metric', median_metric))
        sm_cx = state.get('_ema_cx')

        # Decide candidate using smoothed values by creating a temporary history-like entry
        temp_entry = {'metric': sm_metric, 'centroid': (int(sm_cx), 0) if sm_cx is not None else None, 'frame': None}
        # We'll call decide_command with a deque copy to reuse existing logic
        hist_copy = deque(state['history'], maxlen=state['history'].maxlen)
        # Replace the most recent entry with our smoothed temp entry to bias decision
        try:
            hist_copy.pop()
            hist_copy.append(temp_entry)
        except Exception:
            pass

        candidate = decide_command(hist_copy, config)

        # Candidate persistence counter: require N consecutive same candidates
        last_decision_cand = state.get('last_decision_candidate')
        if candidate == last_decision_cand:
            state['candidate_consistency'] = state.get('candidate_consistency', 0) + 1
        else:
            state['candidate_consistency'] = 1
            state['last_decision_candidate'] = candidate

        # If candidate is 'search', require a confirmed lost_count before accepting
        if candidate == 'search' and state.get('lost_count', 0) < lost_confirm:
            # Hold last final until we confirm lost frames
            effective_candidate = None
        elif state.get('candidate_consistency', 0) < min_consistent:
            # Not yet stable: do not change final
            effective_candidate = None
        else:
            effective_candidate = candidate

        # Determine final decision
        if effective_candidate is None:
            final = state.get('last_final', state.get('last_cmd', 'stop'))
        else:
            final = apply_hysteresis(effective_candidate, state, config)

        # Update display candidates (what we show)
        state['current_candidate'] = candidate
        state['current_final'] = final

        # Throttle decisions to robot-friendly frequency
        if now_ts - state.get('last_decision_ts', 0.0) < decision_interval:
            # Skip sending; keep showing current candidate while waiting
            continue


        # Handle search mode specially: perform a rotation/search pattern
        if final == 'search':
            search_cmd = implement_search_behavior(hardware, state, config)
            if search_cmd:
                pulse = float(config.get('movement_pulse_s', config.get('rotate_pulse_s', 0.0)))
                if pulse > 0.0:
                    sent = send_pulsed_command(hardware, search_cmd, state, config, pulse)
                else:
                    sent = send_command_with_rate_limit(hardware, search_cmd, state, config)
                # Only announce "Searching" once when entering search mode
                if sent and tts is not None and state.get('_last_tts_final') != 'search':
                    # announce_action(tts, 'Searching', blocking=False)
                    state['_last_tts_final'] = 'search'
            # update markers and continue
            state['last_candidate'] = candidate
            state['last_final'] = final
            state['last_decision_ts'] = now_ts
            state['search_last_cmd'] = search_cmd
            # Log only when final changed
            if final != state.get('_logged_last_final'):
                logger.info(f"Search active: cmd={search_cmd}")
                state['_logged_last_final'] = final
            continue


        
        # Clear search state when face is found
        if 'search_start_time' in state and final != 'search':
            try:
                del state['search_start_time']
                if 'search_direction' in state:
                    del state['search_direction']
                # Clear TTS state so "Searching" can be said again next time
                if '_last_tts_final' in state:
                    del state['_last_tts_final']
            except Exception:
                pass
            logger.info('Face reacquired - ending search')

        # Apply safety for forward if needed
        if final == 'forward' and not is_safe_to_move_forward(hardware, config):
            logger.warning('Forward suppressed by safety check')
            final = 'stop'

        # If a post-pulse block is active, skip sending new commands until it expires
        if float(state.get('pulse_block_until', 0.0)) > now_ts:
            logger.debug('Pulse block active until %.3f; skipping send', float(state.get('pulse_block_until')))
            # Update markers so display reflects current decision but do not send
            state['last_candidate'] = candidate
            state['last_final'] = final
            state['last_decision_ts'] = now_ts
            continue

        # Try to send the command if it's changed from last sent
        if final != state.get('last_cmd'):
            # If configured, send short movement pulses for nudges instead of continuous motion
            pulse = float(config.get('movement_pulse_s', config.get('rotate_pulse_s', 0.0)))
            try:
                # Small diagnostic print so operator can see attempted sends
                print(f"ATTEMPT SEND final={final} pulse={pulse:.3f} last_cmd={state.get('last_cmd')}")
                try:
                    sys.stdout.flush()
                except Exception:
                    pass
            except Exception:
                pass
            if final != 'stop' and pulse > 0.0:
                sent = send_pulsed_command(hardware, final, state, config, pulse)
            else:
                sent = send_command_with_rate_limit(hardware, final, state, config)

            # if sent and tts is not None:
            #     if final == 'forward':
            #         announce_action(tts, 'Moving closer', blocking=False)
            #     elif final == 'backward':
            #         announce_action(tts, 'Backing away', blocking=False)
            #     elif final == 'stop':
            #         announce_action(tts, 'Stopping', blocking=False)
            # Log final change
            logger.info(f"Decision changed -> final={final} (candidate={candidate})")

        # Update last decision markers for display and throttling
        state['last_candidate'] = candidate
        state['last_final'] = final
        state['last_decision_ts'] = now_ts


def display_loop(display_q: queue.Queue, state: dict, stop_event: threading.Event, config: dict):
    """Show frames with bbox and overlayed status. Runs until stop_event is set."""
    if not OPENCV_AVAILABLE:
        logger.warning('OpenCV not available; cannot show display')
        return

    win_name = 'Face Follow'
    # Create named window and attempt to bring it to the front/top-most so it is
    # visible on desktop environments. We try OpenCV window properties first
    # (may not be supported on some backends) and then fall back to calling
    # `wmctrl -a` if present on the system (X11 environments).
    try:
        try:
            cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        except Exception:
            pass
        try:
            # Some backends support WND_PROP_TOPMOST to keep window on top
            cv2.setWindowProperty(win_name, cv2.WND_PROP_TOPMOST, 1)
        except Exception:
            pass
    except Exception:
        pass
    try:
        while not stop_event.is_set():
            try:
                item = display_q.get(timeout=0.5)
            except queue.Empty:
                continue

            frame = item.get('frame')
            if frame is None:
                continue

            det = None
            if item.get('bbox'):
                det = item
                x, y, w, h = det['bbox']
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # Overlay status text: show current candidate, final, desired/displayed cmd, and metric
            # Prefer showing the controller's intended `current_final` so GUI reflects decisions
            displayed_cmd = state.get('current_final') or state.get('last_final') or state.get('last_cmd', 'unknown')
            candidate = state.get('current_candidate') or state.get('last_candidate') or 'None'
            final = state.get('current_final') or state.get('last_final') or 'None'
            metric = item.get('metric')

            # If in search mode, append diagnostics: phase, chosen direction, last centroid x, elapsed
            search_info = ''
            if final == 'search':
                s_phase = state.get('search_phase', 'unknown')
                s_chosen = state.get('search_chosen', '?')
                s_elapsed = state.get('search_elapsed', 0.0)
                s_last_cent = state.get('search_last_centroid')
                s_last_x = s_last_cent[0] if s_last_cent is not None else 'None'
                search_info = f' | SEARCH:{s_phase}:{s_chosen} last_cx={s_last_x} t={s_elapsed:.1f}s'

            if metric is not None:
                txt = f"candidate={candidate} final={final} cmd={displayed_cmd} metric={metric:.6f}{search_info}"
            else:
                txt = f"candidate={candidate} final={final} cmd={displayed_cmd}{search_info}"
            cv2.putText(frame, txt, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            cv2.imshow(win_name, frame)
            # Small wait to keep window responsive. If available, attempt to
            # bring the window to the front via `wmctrl -a` (non-fatal).
            try:
                # Try to activate the window using wmctrl (X11). This is a best-effort
                # fallback and will be ignored if wmctrl isn't installed or not running X.
                import subprocess
                subprocess.run(['wmctrl', '-a', win_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

            if cv2.waitKey(1) & 0xFF == ord('q'):
                stop_event.set()
                break
    finally:
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass


# --------------------------------------------------
# Auto-calibration
# --------------------------------------------------

def _collect_samples_for_label(cam, detector, config, label: str, n_samples: int = 40, delay: float = 0.06, visualize: bool = False):
    """Collect `n_samples` normalized-area metrics while the user holds the desired pose.
    Returns list of float metrics (may include zeros if face not seen).
    """
    samples = []
    # Use stdout prints for interactive prompts so they are visible even when
    # stderr is redirected (logger.StreamHandler writes to stderr).
    print(f"Starting collection for '{label}' ({n_samples} samples)")
    try:
        sys.stdout.flush()
    except Exception:
        pass
    collected = 0
    start_ts = now()
    while collected < n_samples:
        ts, frame = capture_frame(cam)
        if frame is None:
            time.sleep(0.02)
            continue

        det = detect_face(detector, frame)
        metr = 0.0
        if det:
            metr = normalized_area(det['bbox'], frame.shape)

        samples.append(metr)
        collected += 1

        if visualize and OPENCV_AVAILABLE:
            f = frame.copy()
            if det:
                x, y, w, h = det['bbox']
                cv2.rectangle(f, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(f, f'Calibrating: {label} {collected}/{n_samples}', (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.imshow('Calibrate', f)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                logger.info('Calibration cancelled by user (q pressed)')
                break

        # small inter-sample delay
        time.sleep(delay)

    duration = now() - start_ts
    logger.info(f"Collected {len(samples)} samples for '{label}' in {duration:.2f}s")
    return samples


def auto_calibrate(output_path: str = None, config: dict = None, n_samples: int = 40, visualize: bool = True, camera_index: int = 0, write_file: bool = True):
    """Guided auto-calibration routine.

    Steps (interactive):
    - For each position 'far', 'ideal', 'close' the user is prompted to press ENTER to begin sample collection.
    - Median normalized areas are computed for each position.
    - `far_threshold` and `close_threshold` are set to midpoints between the medians.
    - Result is written to `output_path` (JSON).
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    if not OPENCV_AVAILABLE:
        logger.error('OpenCV required for calibration')
        return None

    cam = open_camera(pi_camera=cfg.get('pi_camera', False), index=camera_index, size=cfg.get('frame_size'))
    detector = load_face_detector('haar', cascade_path=cfg.get('haar_cascade'))
    if cam is None or detector is None:
        logger.error('Camera or detector not available; aborting calibration')
        if cam:
            close_camera(cam)
        return None

    try:
        # Simplified calibration: collect only 'far' and 'close'. The 'ideal' region is inferred
        # as the midpoint between far and close. Thresholds are set at midpoints between
        # far->ideal and ideal->close (quartile boundaries).
        labels = ['far', 'close']
        medians = {}
        for lbl in labels:
            # Print prompt to stdout and flush so the user sees it even if stderr
            # has been redirected (for example when running `python main.py 2>/dev/null`).
            print(f"Position the robot/camera for '{lbl}' distance and press ENTER to start {n_samples} samples collection...")
            try:
                sys.stdout.flush()
            except Exception:
                pass
            input()
            samples = _collect_samples_for_label(cam, detector, cfg, lbl, n_samples=n_samples, visualize=visualize)
            if not samples:
                logger.warning(f'No samples collected for {lbl}; aborting')
                return None
            sorted_s = sorted(samples)
            median = sorted_s[len(sorted_s)//2]
            medians[lbl] = median
            logger.info(f"Median {lbl} area = {median:.6f}")

        # Validation: medians must be positive
        far_m = float(medians.get('far', 0.0))
        close_m = float(medians.get('close', 0.0))
        if far_m <= 0 or close_m <= 0:
            logger.error('Invalid calibration medians (zero or missing). Aborting calibration.')
            return None

        # Ensure ordering: far < close for normalized area (smaller area when far)
        if far_m >= close_m:
            logger.warning('Calibration medians inverted (far >= close). Sorting values to recover.')
            a, b = sorted([far_m, close_m])
            far_m, close_m = float(a), float(b)

        # Infer ideal as midpoint and compute thresholds as midpoints between quartiles
        ideal_m = (far_m + close_m) / 2.0
        far_thr = float((far_m + ideal_m) / 2.0)
        close_thr = float((ideal_m + close_m) / 2.0)
        medians['ideal'] = ideal_m

        result = cfg.copy()
        result['far_threshold'] = far_thr
        result['close_threshold'] = close_thr
        result['calibration_medians'] = medians

        # write to disk only when requested
        if write_file:
            # default output path when writing requested
            if output_path is None:
                output_path = str(BASE_DIR / 'my_face_follow_config.json')

            try:
                with open(output_path, 'w') as fo:
                    json.dump(result, fo, indent=2)
                logger.info(f'Calibration saved to {output_path}')
            except Exception as e:
                logger.error(f'Failed to write calibration file: {e}')
                return None

        # show summary
        logger.info('Calibration complete:')
        logger.info(f"  far_threshold = {far_thr:.6f}")
        logger.info(f"  close_threshold = {close_thr:.6f}")
        return result
    finally:
        try:
            close_camera(cam)
            if visualize and OPENCV_AVAILABLE:
                cv2.destroyAllWindows()
        except Exception:
            pass

# --------------------------------------------------
# TTS wrapper
# --------------------------------------------------

def announce_action(tts, message: str, blocking: bool = False):
    if tts is None:
        logger.info(f'TTS (skipped): {message}')
        return
    try:
        if blocking:
            tts.speak(message)
        else:
            # Use a background thread to avoid blocking
            threading.Thread(target=tts.speak, args=(message,), daemon=True).start()
    except Exception as e:
        logger.warning(f'TTS announce failed: {e}')

# --------------------------------------------------
# Lifecycle helpers
# --------------------------------------------------

def start_face_follow(hardware=None, tts=None, config: dict = None):
    config = {**DEFAULT_CONFIG, **(config or {})}

    if not OPENCV_AVAILABLE:
        logger.error('OpenCV is required for face-follow. Aborting start.')
        return None

    cam = open_camera(pi_camera=config.get('pi_camera', False), index=config.get('camera_index', 0), size=config.get('frame_size'))
    detector = load_face_detector('haar', cascade_path=config.get('haar_cascade'))
    if cam is None or detector is None:
        logger.error('Camera or detector not available; aborting start')
        if cam:
            close_camera(cam)
        return None

    frame_q = queue.Queue(maxsize=8)
    stop_event = threading.Event()
    state = init_state(max_history=6)

    display_q = None
    cam_thread = threading.Thread(target=camera_loop, args=(cam, detector, frame_q, stop_event, config, None), daemon=True)
    # If visualization requested, create display queue and pass to camera loop
    if config.get('visualize'):
        display_q = queue.Queue(maxsize=4)
        # restart cam_thread with display queue by creating a new thread instead
        cam_thread = threading.Thread(target=camera_loop, args=(cam, detector, frame_q, stop_event, config, display_q), daemon=True)
    ctrl_thread = threading.Thread(target=control_loop, args=(frame_q, hardware, state, config, stop_event, tts), daemon=True)

    cam_thread.start()
    ctrl_thread.start()

    logger.info('Face follow started')
    return {'cam': cam, 'detector': detector, 'frame_q': frame_q, 'stop_event': stop_event, 'state': state, 'display_q': display_q, 'threads': (cam_thread, ctrl_thread)}


def stop_face_follow(handles: dict):
    if not handles:
        return
    stop_event = handles.get('stop_event')
    cam = handles.get('cam')
    if stop_event:
        stop_event.set()
    # Give threads a moment to stop
    time.sleep(0.5)
    if cam:
        close_camera(cam)
    logger.info('Face follow stopped')

# --------------------------------------------------
# CLI / quick-run for testing
# --------------------------------------------------

def run_detect_mode(args, config):
    """Run detection-only mode: draw bbox & show metric."""
    if not OPENCV_AVAILABLE:
        logger.error('OpenCV not installed; cannot run detect mode')
        return

    cam = open_camera(pi_camera=config.get('pi_camera', False), index=args.index, size=config.get('frame_size'))
    detector = load_face_detector('haar', cascade_path=config.get('haar_cascade'))
    if cam is None or detector is None:
        logger.error('Camera or detector not available')
        return

    logger.info('Running detect mode. Press q to quit.')
    try:
        while True:
            ts, frame = capture_frame(cam)
            if frame is None:
                continue
            det = detect_face(detector, frame)
            if det:
                metr = normalized_area(det['bbox'], frame.shape)
                x, y, w, h = det['bbox']
                cv2.rectangle(frame, (x,y), (x+w, y+h), (0,255,0), 2)
                cv2.putText(frame, f'area={metr:.6f}', (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
                logger.info(f'Detected face area={metr:.6f} centroid={det["centroid"]}')
            else:
                cv2.putText(frame, 'No face', (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 1)

            cv2.imshow('Face Detect', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        close_camera(cam)
        cv2.destroyAllWindows()


def run_follow_mode(args, config):
    # Initialize hardware and tts if available
    sm = None
    tts = None
    if SerialManager is not None:
        try:
            sm = SerialManager()
        except Exception as e:
            logger.warning(f'Could not initialize SerialManager: {e}')
            sm = None
    else:
        # If the import failed earlier, surface that error to logs for debugging
        if 'SERIAL_MANAGER_IMPORT_ERROR' in globals() and SERIAL_MANAGER_IMPORT_ERROR:
            logger.warning(f'SerialManager import failed: {SERIAL_MANAGER_IMPORT_ERROR}')
    if TextToSpeech is not None:
        try:
            tts = TextToSpeech()
        except Exception:
            tts = None

    handles = start_face_follow(hardware=sm, tts=tts, config=config)
    if not handles:
        logger.error('start_face_follow failed')
        return

    try:
        if config.get('visualize') and handles.get('display_q') is not None:
            # Run display loop in main thread for reliable GUI behavior
            logger.info('Running display loop; press q in the window to stop')
            display_loop(handles['display_q'], handles['state'], handles['stop_event'], config)
        else:
            logger.info('Press Ctrl+C to stop')
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info('Interrupt received; stopping')
    finally:
        stop_face_follow(handles)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Face follow test script')
    parser.add_argument('--mode', choices=['detect','follow'], default='detect')
    parser.add_argument('--index', type=int, default=0)
    parser.add_argument('--visualize', action='store_true', help='Show camera window during follow mode')
    parser.add_argument('--raspi', action='store_true', help='Running on Raspberry Pi with Pi Camera (use v4l2 backend and Pi-specific defaults)')
    parser.add_argument('--config', type=str, default='')
    parser.add_argument('--auto-calibrate', action='store_true', help='Run interactive auto-calibration and write config')
    parser.add_argument('--calibrate-output', type=str, default='', help='Path to write calibration config (JSON)')
    parser.add_argument('--dry-run', action='store_true', help='Do not send movement commands (dry run)')
    args = parser.parse_args()

    config = DEFAULT_CONFIG.copy()
    # Expose Pi-mode into config if requested
    if getattr(args, 'raspi', False):
        config['pi_camera'] = True
        # Pi-specific defaults: more retries and slightly smaller calibration samples by default
        config.setdefault('camera_open_retries', 5)
        config.setdefault('camera_open_retry_delay_s', 1.0)
        # keep the frame size modest for Pi by default (user can override)
        config.setdefault('frame_size', (320, 240))
    # Priority 1: explicit --config path
    if args.config:
        try:
            with open(args.config, 'r') as f:
                custom = json.load(f)
            config.update(custom)
        except Exception as e:
            logger.warning(f'Failed to load config {args.config}: {e}')
    else:
        # If no explicit config provided, attempt to auto-load a calibration file
        # Try a few sensible locations (package BASE_DIR, repo-relative path)
        candidate_paths = [str(BASE_DIR / 'my_face_follow_config.json'),
                           os.path.join('modules', 'face_detection', 'my_face_follow_config.json'),
                           'my_face_follow_config.json']
        loaded = False
        for p in candidate_paths:
            try:
                if os.path.exists(p):
                    with open(p, 'r') as f:
                        custom = json.load(f)
                    config.update(custom)
                    logger.info(f'Auto-loaded calibration config from {p}')
                    loaded = True
                    break
            except Exception as e:
                logger.warning(f'Failed to auto-load config {p}: {e}')
        if not loaded:
            logger.debug('No auto calibration config found; using DEFAULT_CONFIG')

    if args.mode == 'detect':
        run_detect_mode(args, config)
    else:
        # Honor dry-run CLI flag to suppress sending commands
        if getattr(args, 'dry_run', False):
            config['disable_sending'] = True
            logger.info('CLI: dry-run enabled; movement commands will be suppressed')
        # Pass visualize and index into config
        config['visualize'] = args.visualize or config.get('visualize', False)
        config['camera_index'] = args.index or config.get('camera_index', 0)
        # If auto-calibrate requested, run that flow first (interactive) and then start follow
        if getattr(args, 'auto_calibrate', False) or getattr(args, 'auto-calibrate', False) or args.auto_calibrate:
            outp = args.calibrate_output if args.calibrate_output else None
            # If user explicitly passed a calibrate-output path, write file; otherwise keep results in-memory
            write_file_flag = True if outp else False
            # reduce sampling on Pi for faster calibration
            n_samples = 20 if config.get('pi_camera') else 40
            auto_res = auto_calibrate(output_path=outp, config=config, n_samples=n_samples, visualize=config.get('visualize', False), camera_index=config.get('camera_index', 0), write_file=write_file_flag)
            if auto_res is None:
                logger.error('Auto-calibration failed or was cancelled')
            else:
                logger.info('Auto-calibration completed successfully; starting follow with calibrated values')
                # merge returned calibration into runtime config
                config.update(auto_res)
                # Give the OS a short moment to fully release/reopen the camera device
                # This avoids a common intermittent failure where reopening immediately
                # after release causes `cam.read()` to fail repeatedly on some platforms.
                import time as _sleep_time
                wait_s = 1.0
                logger.info(f'Waiting {wait_s:.1f}s for camera to become available...')
                _sleep_time.sleep(wait_s)
                run_follow_mode(args, config)
        