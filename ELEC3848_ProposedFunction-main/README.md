# Neko Voice Assistant

A friendly robot companion with face-following, voice interaction, and simple calibration utilities.

## Quick start

- Safe visual-only mode (recommended while testing):

```bash
python main.py --dry-run --display-blocking
```

- Normal mode (motors enabled by default — use with caution):

```bash
python main.py 
```

Important safety: motors are enabled by default. Always verify camera/detection in `--dry-run` before allowing actuation.

## CLI flags & environment variables

- `--display-blocking`
  - Run the face-follow display loop in the foreground (helpful for getting the camera preview visible).
  - Note: `--display-blocking` is intended for troubleshooting and debugging only. It runs the camera/display loop in the main thread so GUI windows and overlays update reliably. When the display and capture run in background threads or as a service the preview window may not appear or refresh correctly, so use this flag when you need to watch frames and overlays directly. On headless systems a window still will not appear.
- `--interactive-calibrate`
  - Run the original interactive calibration (press ENTER for each labeled stage).
- `--auto-calibrate`
  - Run non-interactive automatic calibration (collects repeated sample batches as you step backwards).
- `--calibration-wizard`
  - Run a TTS-guided calibration wizard that prompts and prints medians.
- `--calibration-output <path>`
  - Save calibration output JSON to the given path.
- `--calibration-max-fails <n>`
  - How many consecutive failed batches before auto calibration stops (default 4).
- `--calibration-wait <seconds>`
  - Seconds to wait between auto-calibration attempts (default 5.0).
- `--dry-run` (or `NEKO_FACE_DRY_RUN=1`)
  - Run in dry-run (no motor commands sent). When omitted, motor sending is enabled by default.

Environment variable aliases (optional):

- `NEKO_FACE_AUTO_CALIBRATE=1` → equivalent to `--interactive-calibrate`
- `NEKO_FACE_DRY_RUN=1` → equivalent to `--dry-run`
- `NEKO_FACE_DISPLAY_BLOCKING=1` → equivalent to `--display-blocking`

## Calibration

There are three calibration helpers in the codebase:

1. `ff.auto_calibrate()` (in `modules/face_detection/face_follow.py`)

   - Original interactive routine: prompts for `far` and `close` poses and computes thresholds.

2. `calibration_wizard()` (helper in `main.py`)

   - TTS-guided wizard that prompts and collects medians, useful for one-shot guided runs.

3. `calibration_auto()` (non-interactive helper in `main.py`)
   - Repeatedly collects batches (default 40 samples each) while you step back; stops after N consecutive failures and writes a summary JSON with per-attempt medians and aggregated mins/maxs.

Typical calibration workflow (non-interactive recommended for walk-back):

```bash
python main.py --auto-calibrate --display-blocking --calibration-output=cal_summary.json
```

The summary JSON includes `successes` (per-attempt medians), `mins` and `maxs`. From these you can compute thresholds used by the controller.

## How thresholds are computed

The code derives two thresholds from your calibration medians:

- `far_threshold`: below this → robot considers you "too far" and will move forward.
- `close_threshold`: above this → robot considers you "too close" and will move backward.

By default the project uses a robust heuristic (ignore zero samples, use second-extrema or midpoint rules) to avoid outliers. The canonical formula used by the original interactive routine is:

```py
ideal_m = (far_m + close_m) / 2
far_threshold = (far_m + ideal_m) / 2
close_threshold = (ideal_m + close_m) / 2
```

You can change the aggregation method later (percentiles, trimmed ranges, etc.) if you collect many samples.

## Decision pipeline (short)

Camera Frame → Detection → Metrics → CANDIDATE → Smoothing → FINAL → Sending → Arduino

- CANDIDATE (raw): immediate per-frame decision from `decide_command()` (e.g. `rotate_left`, `forward`, `search`).
- FINAL (smoothed): result after EMA smoothing, candidate persistence (`min_consistent_frames`), and hysteresis (in `control_loop()`).
- COMMAND / last_cmd: what was actually sent to Arduino via `send_command_with_rate_limit()` (rate-limited and tracked as `state['last_cmd']`).

The display overlay shows all three values so you can see detection vs smoothing vs sent command.

## Key config values to tune

- `far_threshold`, `close_threshold` (in `DEFAULT_CONFIG` in `modules/face_detection/face_follow.py`)
- `x_tolerance_norm` (centroid horizontal tolerance)
- `ema_alpha_metric`, `ema_alpha_centroid` (EMA smoothing factors)
- `min_consistent_frames` (how many consistent frames before candidate becomes effective)
- `decision_interval_s` and `min_command_interval_s` (timers/rate-limits)
- `lost_frames_threshold`, `lost_confirm_frames` (controls when search behavior triggers)

## Troubleshooting

- Many zero medians during calibration:
  - Improve lighting, ensure your face box is visible, and use `--display-blocking` to watch the overlay.
  - Increase `--calibration-max-fails` or `--calibration-wait` while doing non-interactive runs.
- Jittering decisions:
  - Increase `min_consistent_frames` and `decision_interval_s`, or increase EMA smoothing (lower alpha).
- No camera / OpenCV issues:
  - Verify `opencv-python` is installed and use `detect_camera_devices()` helper in the face_follow module.

## Logging & debugging

- The `face_follow` module logs to stdout and writes a `face_follow.log` in `modules/face_detection/logs`.
- To see more verbose internal state, set the logger to `DEBUG` in `modules/face_detection/face_follow.py`:

```py
import logging
ff.logger.setLevel(logging.DEBUG)
```

## Files of interest

- `main.py` — entrypoint, CLI, helpers, and TTS wrapping
- `modules/face_detection/face_follow.py` — face detection, calibration, decision logic, and command sending mapping
- `modules/hardware_communication/serial_manager.py` — serial command mapping and sending to Arduino

## Next steps / ideas

- Add a CLI flag to select calibration aggregation method (second-extrema, percentile, trimmed).
- Persist calibration medians automatically to a JSON file and auto-load them when `start_follow()` runs.
- Replace discrete forward/back commands with a proportional speed mapping for smoother motion.

## License & Credits

This is your project code. No license was added by the tool — add a license file if you intend to distribute.

## Questions or edits

If you want I can:

- Add the README to the repo (I will create `README.md` now).
- Add a `--calibration-method` CLI flag so you can choose `second|percentile` aggregation.

---

README created by automation. If you'd like wording or content changes, tell me what to adjust.


# 用您的阿里云百炼API Key代替YOUR_DASHSCOPE_API_KEY
echo "export DASHSCOPE_API_KEY=sk-494791b2574b449b99dec440129f1f89" >> ~/.bashrc