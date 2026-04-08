import argparse
import time
import cv2


def parse_args():
    parser = argparse.ArgumentParser(description="Simple camera test tool")
    parser.add_argument("--index", type=int, default=0, help="Camera index, default 0")
    parser.add_argument("--width", type=int, default=640, help="Frame width")
    parser.add_argument("--height", type=int, default=480, help="Frame height")
    parser.add_argument("--fps", type=int, default=30, help="Target FPS")
    parser.add_argument(
        "--backend",
        type=str,
        default="any",
        choices=["any", "v4l2", "gstreamer"],
        help="OpenCV backend",
    )
    return parser.parse_args()


def get_backend(backend_name):
    if backend_name == "v4l2":
        return cv2.CAP_V4L2
    if backend_name == "gstreamer":
        return cv2.CAP_GSTREAMER
    return cv2.CAP_ANY


def open_camera(index, width, height, fps, backend):
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        return cap

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    return cap


def main():
    args = parse_args()
    backend = get_backend(args.backend)

    print("[INFO] Opening camera...")
    print(
        f"[INFO] index={args.index}, width={args.width}, "
        f"height={args.height}, fps={args.fps}, backend={args.backend}"
    )

    cap = open_camera(args.index, args.width, args.height, args.fps, backend)
    if not cap.isOpened():
        print("[ERROR] Failed to open camera.")
        return

    print("[INFO] Camera opened. Press 'q' or ESC to quit.")

    last_t = time.time()
    fps_hist = []
    fail_count = 0

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            fail_count += 1
            print(f"[WARN] Failed to capture frame (count={fail_count})")
            if fail_count >= 10:
                print("[WARN] Reopening camera after repeated failures...")
                cap.release()
                time.sleep(0.5)
                cap = open_camera(args.index, args.width, args.height, args.fps, backend)
                fail_count = 0
            continue

        fail_count = 0
        now = time.time()
        fps = 1.0 / max(now - last_t, 1e-6)
        last_t = now

        fps_hist.append(fps)
        if len(fps_hist) > 20:
            fps_hist.pop(0)
        avg_fps = sum(fps_hist) / len(fps_hist)

        h, w = frame.shape[:2]
        text = f"{w}x{h}  FPS:{avg_fps:.1f}"
        cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("camera_test", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q") or key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] Exit.")


if __name__ == "__main__":
    main()
