#!/usr/bin/env python3
import argparse
import time

import serial


def send_cmd(ser: serial.Serial, cmd: str, duration_s: float) -> None:
    end_time = time.time() + duration_s
    print(f"[TEST] send {cmd} for {duration_s:.1f}s")
    while time.time() < end_time:
        ser.write((cmd + "\n").encode("utf-8"))
        ser.flush()
        time.sleep(0.1)


def safe_stop(ser: serial.Serial) -> None:
    for _ in range(5):
        ser.write(b"S\n")
        ser.flush()
        time.sleep(0.05)
    print("[TEST] send STOP")


def main() -> None:
    parser = argparse.ArgumentParser(description="Jetson serial car movement test")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port, e.g. /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate")
    parser.add_argument("--wait", type=float, default=2.0, help="Wait after open port")
    parser.add_argument("--move-time", type=float, default=2.0, help="Each movement duration")
    parser.add_argument("--gap", type=float, default=1.0, help="Stop gap between movements")
    args = parser.parse_args()

    print(f"[INFO] opening serial: {args.port} @ {args.baud}")
    ser = serial.Serial(args.port, args.baud, timeout=1)

    try:
        time.sleep(args.wait)
        print("[INFO] serial ready, start test")

        # Sequence: F -> S -> B -> S -> L -> S -> R -> S
        for cmd in ["F", "B", "L", "R"]:
            send_cmd(ser, cmd, args.move_time)
            safe_stop(ser)
            time.sleep(args.gap)

        print("[OK] test sequence done")
    except KeyboardInterrupt:
        print("\n[WARN] interrupted by user")
    finally:
        safe_stop(ser)
        ser.close()
        print("[INFO] serial closed")


if __name__ == "__main__":
    main()

