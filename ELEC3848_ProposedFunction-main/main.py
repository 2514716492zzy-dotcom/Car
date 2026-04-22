"""
Neko Voice Assistant - Main Entry Point
A friendly robot companion for mental health support

Architecture:
    1. Module initialization & configuration
    2. TTS (Text-to-Speech) system
    3. LCD display system (for emotion visualization)
    4. Intent handling (commands & chat)
    5. Owner setup
    6. Main voice loop
"""

# ============================================================
# IMPORTS
# ============================================================

# Standard library
import os
import time
import json
import queue
import threading
from typing import Optional

# Third-party
import speech_recognition as sr

# Local modules
from modules.intent_classifier.intent_classifier import IntentClassifier
from modules.audio_device_manager import initialize_microphone
from modules.neko_agent import NekoAgent
from modules.text_to_speech import TextToSpeech
from modules.hardware_communication import SerialManager
# Face-follow integration (do not modify face_follow implementation here)
from modules.face_detection import face_follow as ff


# ============================================================
# CONFIGURATION & INITIALIZATION
# ============================================================

# Conversation settings
SILENCE_TIMEOUT = 20  # seconds before clearing conversation history

# Display behavior default (can be overridden by CLI flag --display-blocking)
DISPLAY_BLOCKING_DEFAULT = False
# Auto-calibration default (can be overridden by CLI flag --auto-calibrate
# or environment variable `NEKO_FACE_AUTO_CALIBRATE=1`). When False, the
# face-follow subsystem will use hard-coded/default calibration values from
# `ff.DEFAULT_CONFIG` and will NOT prompt for interactive calibration.
AUTO_CALIBRATE_DEFAULT = False
# Dry-run default: by default we allow sending commands to the motors. Use
# `--dry-run` or the environment variable `NEKO_FACE_DRY_RUN=1` to enable
# dry-run (no motor commands) for testing.
DRY_RUN_DEFAULT = False

# Initialize components
mic, recognizer = initialize_microphone()
classifier = IntentClassifier()
neko_agent = NekoAgent(silence_timeout=SILENCE_TIMEOUT)
tts_engine = TextToSpeech()
hardware = SerialManager()

# TTS state management
speaking_event = threading.Event()


# Face-follow runtime handles (managed by start_follow/stop_follow)
follow_lock = threading.Lock()
follow_handles = None


# ============================================================
# TEXT-TO-SPEECH SYSTEM
# ============================================================

def speak_async(text: str):
    """
    Speak text in background thread (non-blocking)
    
    Args:
        text: Text to synthesize and play
    """
    thread = threading.Thread(target=speak_blocking, args=(text,), daemon=True)
    thread.start()


def speak_blocking(text: str):
    """
    Speak text synchronously with state management
    
    Args:
        text: Text to synthesize and play
    """
    speaking_event.set()
    try:
        tts_engine.speak(text)
    finally:
        speaking_event.clear()


def wait_for_speaking_to_finish():
    """Block until current TTS playback completes"""
    while speaking_event.is_set():
        time.sleep(0.05)


# ============================================================
# LCD DISPLAY SYSTEM (Emotion Visualization)
# ============================================================

# Display queue for async updates
display_queue = queue.Queue()


def display_on_lcd(emotion: str, emoji: Optional[str] = None):
    """
    Display emotion on LCD screen (platform-specific)
    
    Args:
        emotion: Emotion label (e.g., "happy", "calm")
        emoji: Optional emoji character
        
    Note: Currently a placeholder. Replace with actual LCD driver code.
    """
    try:
        print(f"🖥️ LCD: emotion={emotion}, emoji={emoji}")
        # TODO: Replace with actual LCD driver code
        # Example: lcd.clear(); lcd.text(f"{emoji} {emotion}")
    except Exception as e:
        print(f"⚠️ display_on_lcd error: {e}")


def _display_worker():
    """Background thread worker for LCD updates"""
    while True:
        item = display_queue.get()
        try:
            if item and 'emotion' in item:
                display_on_lcd(item.get('emotion'), item.get('emoji'))
        except Exception as e:
            print(f"⚠️ Display worker exception: {e}")
        finally:
            display_queue.task_done()
        time.sleep(0.01)


def send_emotion(emotion_dict: dict) -> bool:
    """
    Queue emotion for display on LCD (async)
    
    Args:
        emotion_dict: Dict with 'emotion' and optional 'emoji' keys
        
    Returns:
        True if queued successfully, False otherwise
    """
    if not emotion_dict or 'emotion' not in emotion_dict:
        return False
    try:
        display_queue.put_nowait({
            'emotion': emotion_dict.get('emotion'),
            'emoji': emotion_dict.get('emoji') if isinstance(emotion_dict.get('emoji'), str) else None,
        })
        return True
    except Exception:
        return False


# Start display worker thread
display_thread = threading.Thread(target=_display_worker, daemon=True)
display_thread.start()


# ============================================================
# INTENT HANDLERS
# ============================================================


def start_follow(display_blocking: Optional[bool] = None):
    """Start face-follow.

    By default this starts the display in a background thread so the assistant
    remains responsive. If `display_blocking=True` the `display_loop` is run in
    the main thread (blocking) which is useful for interactive testing.

    Control the default via the environment variable `NEKO_FACE_DISPLAY_BLOCKING=1`.
    """
    global follow_handles
    with follow_lock:
        if follow_handles:
            print("⚠️ Face-follow already running")
            return follow_handles

        # Determine display_blocking default from module-level CLI flag if not provided
        if display_blocking is None:
            try:
                display_blocking = bool(DISPLAY_BLOCKING_DEFAULT)
            except Exception:
                display_blocking = False

        # Build runtime config from face_follow defaults, then apply requested defaults
        cfg = ff.DEFAULT_CONFIG.copy()
        # Defaults requested by user: raspi + visualize + dry-run + index 0
        cfg['pi_camera'] = True
        cfg['visualize'] = True
        # Default behavior: allow sending motor commands. This can be overridden
        # by the CLI `--dry-run` flag or env `NEKO_FACE_DRY_RUN` which sets
        # `DRY_RUN_DEFAULT`.
        try:
            cfg['disable_sending'] = bool(DRY_RUN_DEFAULT)
        except Exception:
            cfg['disable_sending'] = False
        cfg['camera_index'] = 0

        # Auto-calibration is optional. Only run interactive calibration if the
        # runtime default is enabled (controlled by CLI flag or env var).
        if AUTO_CALIBRATE_DEFAULT:
            try:
                # Keep face_follow logging verbose so user sees the same output as running it directly
                print('🔧 Running auto-calibration (interactive)... (camera window will show overlays)')
                n_samples = 20 if cfg.get('pi_camera') else 40
                auto_res = ff.auto_calibrate(output_path=None, config=cfg, n_samples=n_samples, visualize=cfg.get('visualize', False), camera_index=cfg.get('camera_index', 0), write_file=False)
                if auto_res is not None:
                    cfg.update(auto_res)
                    print('✅ Auto-calibration succeeded and merged into runtime config')
                    # Print calibration medians (far/ideal/close) for user visibility
                    try:
                        meds = auto_res.get('calibration_medians') if isinstance(auto_res, dict) else None
                        if meds:
                            print('Calibration medians:')
                            for k in ('far', 'ideal', 'close'):
                                if k in meds:
                                    print(f"  {k}: {meds[k]:.6f}")
                    except Exception:
                        pass
                else:
                    print('⚠️ Auto-calibration skipped or failed; continuing with defaults')
            except Exception as e:
                print(f'⚠️ Auto-calibration raised exception: {e}; continuing')
        else:
            # Use hard-coded/default calibration values found in ff.DEFAULT_CONFIG
            print('ℹ️ Auto-calibration disabled (using existing calibration values).')
            print('   Use --auto-calibrate or set NEKO_FACE_AUTO_CALIBRATE=1 to enable interactive calibration.')

        # Initialize hardware and tts objects from main runtime
        sm = None
        try:
            sm = hardware
        except Exception:
            sm = None

        tts_obj = None
        try:
            tts_obj = tts_engine
        except Exception:
            tts_obj = None

        # Start face-follow (keep verbose logging). If visualization is enabled,
        # either run display in main thread (blocking) for testing or start a
        # background thread so the assistant remains responsive.
        handles = ff.start_face_follow(hardware=sm, tts=tts_obj, config=cfg)
        if handles:
            # store config for later reference
            handles['config'] = cfg
            follow_handles = handles
            # If visualization is enabled and a display queue was created, run the display loop
            try:
                if cfg.get('visualize') and handles.get('display_q') is not None:
                    if display_blocking:
                        # Run display loop in main thread (blocking) for testing.
                        print('ℹ️ Running display in foreground (blocking) for testing')
                        ff.display_loop(handles['display_q'], handles['state'], handles['stop_event'], cfg)
                    else:
                        disp_thread = threading.Thread(target=ff.display_loop, args=(handles['display_q'], handles['state'], handles['stop_event'], cfg), daemon=True)
                        disp_thread.start()
                        handles['display_thread'] = disp_thread
            except Exception:
                pass
            print('✅ Face-follow started (verbose output enabled; camera overlays visible)')
        else:
            print('❌ Failed to start face-follow')
        return follow_handles


def stop_follow():
    """Stop the running face-follow instance if any."""
    global follow_handles
    with follow_lock:
        if not follow_handles:
            print('ℹ️ Face-follow not running')
            return
        try:
            ff.stop_face_follow(follow_handles)
        except Exception as e:
            print(f'⚠️ Error stopping face-follow: {e}')

        # Restore face_follow logger level if we changed it when starting
        try:
            old_level = None
            if isinstance(follow_handles, dict):
                old_level = follow_handles.get('_old_logger_level')
            if old_level is not None:
                try:
                    ff.logger.setLevel(old_level)
                except Exception:
                    pass
        except Exception:
            pass

        # Optionally send a hardware stop if follow used active sending
        cfg = follow_handles.get('config', {}) if isinstance(follow_handles, dict) else {}
        disable_sending = cfg.get('disable_sending', True)
        # Clear handles before attempting further commands
        follow_handles = None
        if not disable_sending:
            try:
                hardware.send_mapped_command('stop')
            except Exception:
                pass
        print('✅ Face-follow stopped')


def calibration_wizard(save_path: Optional[str] = None, n_samples: int = 40, visualize: bool = True, camera_index: int = 0):
    """
    Interactive calibration helper that wraps `ff.auto_calibrate` with TTS
    prompts so you can collect calibration medians to hard-copy into your
    configuration.

    Behavior:
    - Announces steps via TTS and prints instructions to stdout.
    - Calls `ff.auto_calibrate(..., write_file=False)` to collect samples.
    - Prints calibration medians and optionally writes them to `save_path`.

    This helper is intended for manual one-off runs during tuning.
    """
    # Prepare runtime config for auto_calibrate
    cfg = ff.DEFAULT_CONFIG.copy()
    cfg['pi_camera'] = True
    cfg['visualize'] = visualize
    cfg['camera_index'] = camera_index

    msg_intro = (
        "Calibration wizard will guide you through collecting camera/metric samples.\n"
        "Stand at the position you consider 'close' for the robot and press Enter to start sampling.\n"
        "After sampling completes you will be asked to move away and press Enter to continue.\n"
        "When finished the medians will be printed and optionally saved to a JSON file."
    )
    print(msg_intro)
    try:
        speak_blocking("Starting calibration wizard. Follow on-screen instructions.")
    except Exception:
        print("(TTS unavailable — continuing in text-only mode.)")

    input("When you're ready at the CLOSE position, press Enter to begin sampling...")
    try:
        auto_res = ff.auto_calibrate(output_path=None, config=cfg, n_samples=n_samples, visualize=visualize, camera_index=camera_index, write_file=False)
    except Exception as e:
        print(f"⚠️ auto_calibrate raised an exception: {e}")
        try:
            speak_blocking("Calibration failed. See console for details.")
        except Exception:
            pass
        return None

    if not auto_res:
        print("⚠️ auto_calibrate returned no result; no medians available.")
        try:
            speak_blocking("Calibration did not return results.")
        except Exception:
            pass
        return None

    # Prefer explicit medians key if available
    meds = None
    if isinstance(auto_res, dict):
        meds = auto_res.get('calibration_medians') or auto_res

    print('\n=== Calibration Results ===')
    if isinstance(meds, dict):
        for k, v in meds.items():
            try:
                print(f"  {k}: {v:.6f}")
            except Exception:
                print(f"  {k}: {v}")
    else:
        # Fallback: print whole dict
        print(json.dumps(auto_res, indent=2))

    # Optionally save to file for easy copy-paste
    if save_path:
        try:
            with open(save_path, 'w') as fh:
                json.dump({'calibration_medians': meds}, fh, indent=2)
            print(f"Saved calibration medians to: {save_path}")
        except Exception as e:
            print(f"⚠️ Failed to write medians to {save_path}: {e}")

    try:
        speak_blocking("Calibration complete. Results printed to console.")
    except Exception:
        pass

    return meds


def calibration_auto(save_path: Optional[str] = None, n_samples: int = 40, visualize: bool = True, camera_index: int = 0, max_consecutive_failures: int = 4, wait_between_attempts: float = 5.0):
    """
    Non-interactive automatic calibration run.

    Workflow:
    - Announces instructions via TTS.
    - Repeatedly calls `ff.auto_calibrate` to collect `n_samples`.
    - Records successful medians. On failure increments failure counter.
    - Stops when `max_consecutive_failures` is reached and prints the
      aggregate results (closest and furthest medians seen).

    Returns a dict with collected medians list and aggregate min/max.
    """
    print("🔧 Starting non-interactive automatic calibration")
    try:
        speak_blocking("Starting automatic calibration. Stand at your CLOSE position now.")
    except Exception:
        pass

    cfg = ff.DEFAULT_CONFIG.copy()
    cfg['pi_camera'] = True
    cfg['visualize'] = visualize

    # Open camera and detector once, reuse across attempts
    cam = None
    detector = None
    try:
        cam = ff.open_camera(pi_camera=cfg.get('pi_camera', False), index=camera_index, size=cfg.get('frame_size'))
        detector = ff.load_face_detector('haar', cascade_path=cfg.get('haar_cascade'))
        if cam is None or detector is None:
            print('⚠️ Camera or detector failed to initialize; aborting auto calibration')
            return None

        successes = []
        consecutive_failures = 0
        attempt = 0

        while True:
            attempt += 1
            print(f"\n--- Attempt {attempt}: collecting {n_samples} samples ---")
            try:
                speak_blocking(f"Collecting {n_samples} samples now")
            except Exception:
                pass

            # Use the internal sample collector directly (non-interactive)
            try:
                samples = ff._collect_samples_for_label(cam, detector, cfg, label=f'attempt_{attempt}', n_samples=n_samples, visualize=visualize)
            except Exception as e:
                print(f"⚠️ Sample collection exception: {e}")
                samples = None

            if samples and any(s > 0 for s in samples):
                sorted_s = sorted(samples)
                median = sorted_s[len(sorted_s)//2]
                metric_key = cfg.get('metric', 'metric')
                meds = {metric_key: float(median)}
                print("✓ Sampling successful — median:")
                print(f"  {metric_key}: {median:.6f}")
                successes.append(meds)
                consecutive_failures = 0
                try:
                    speak_blocking("Samples recorded. Please move back slightly and wait for the next round.")
                except Exception:
                    pass
                time.sleep(wait_between_attempts)
                continue

            # Failure path
            consecutive_failures += 1
            print(f"✖ Sampling failed (no face seen). Consecutive failures: {consecutive_failures}/{max_consecutive_failures}")
            try:
                speak_blocking(f"Sampling failed {consecutive_failures} times")
            except Exception:
                pass

            if consecutive_failures >= max_consecutive_failures:
                print("⚠️ Max consecutive failures reached — finishing calibration run.")
                break

            # Wait briefly to allow user to move further back
            time.sleep(wait_between_attempts)

        # Aggregate results
        result = {'attempts': attempt, 'success_count': len(successes), 'successes': successes}
        if successes:
            # compute min/max per numeric key
            keys = set().union(*[s.keys() for s in successes])
            mins = {}
            maxs = {}
            for k in keys:
                vals = []
                for s in successes:
                    v = s.get(k)
                    if isinstance(v, (int, float)):
                        vals.append(float(v))
                if vals:
                    mins[k] = min(vals)
                    maxs[k] = max(vals)
            result['mins'] = mins
            result['maxs'] = maxs

        # Print summary
        print('\n=== Calibration Summary ===')
        print(f"Attempts: {attempt}, successes: {len(successes)}")
        if successes:
            print('Per-key min values:')
            for k, v in result.get('mins', {}).items():
                print(f"  {k}: {v:.6f}")
            print('Per-key max values:')
            for k, v in result.get('maxs', {}).items():
                print(f"  {k}: {v:.6f}")
        else:
            print('No successful samples recorded.')

        if save_path:
            try:
                with open(save_path, 'w') as fh:
                    json.dump(result, fh, indent=2)
                print(f"Saved calibration summary to: {save_path}")
            except Exception as e:
                print(f"⚠️ Failed to write summary to {save_path}: {e}")

        try:
            speak_blocking("Automatic calibration finished. See console for results.")
        except Exception:
            pass

        return result
    finally:
        try:
            if cam:
                ff.close_camera(cam)
        except Exception:
            pass


def handle_command(command: str):
    """
    Execute robot movement/behavior commands
    
    Args:
        command: Command identifier (e.g., "follow_me", "stop")
    """
    print(f"🎮 EXECUTING COMMAND: {command}")
    
    # Command responses
    responses = {
        'follow_me': "Following you, nya~!",
        'stop': "Stopping, nya!",
        'wander': "Time to explore, desu~!",
        'spray': "Water attack mode, nya nya~!",
        'return': "Coming back, master!",
        'battery': "Battery at 85%, nya~",
        'forward': "Moving forward, nya~!",
        'backward': "Moving backward, nya~!",
        'left': "Turning left, nya~!",
        'right': "Turning right, nya~!",
        'rotate_left': "Rotating left, nya~!",
        'rotate_right': "Rotating right, nya~!",
        'unknown': "I didn't understand that command, nya..."
    }
    
    response = responses.get(command, responses['unknown'])
    print(f"📢 Response: {response}")
    
    # Execute response
    speak_async(response)
    neko_agent.clear_history(reason="command")
    # Special handling for follow lifecycle commands
    try:
        if command == 'follow_me':
            # Start follow subsystem instead of sending a single-mapped hardware command
            start_follow()
            return
        if command == 'stop':
            # Stop follow subsystem first
            stop_follow()
            # If follow was not in dry-run mode, allow a hardware stop command
            # (stop_follow already respects disable_sending when it stored the config)
            return
    except Exception as e:
        print(f"⚠️ follow control error: {e}")

    # Default: send mapped command to hardware
    try:
        hardware.send_mapped_command(command)
    except Exception as e:
        print(f"⚠️ Hardware send failed: {e}")


def handle_chat(text: str):
    """
    Handle conversational chat via Neko Agent
    
    Args:
        text: User's input text
    """
    # Get response and emotion from agent
    response, emotion = neko_agent.chat(text)
    print(f"📢 Response: {response}")
    
    # Display emotion on LCD if available
    if emotion:
        try:
            send_emotion(emotion)
        except Exception:
            pass
    
    # Speak response
    speak_async(response)


# ============================================================
# OWNER SETUP
# ============================================================

def get_owner_name():
    """
    Interactive owner name setup (runs once at startup)
    
    Workflow:
        1. Speak introduction
        2. Listen for owner's name via microphone
        3. Store name in neko_agent for personalization
        4. Greet owner
    """
    # Skip if already configured
    if neko_agent.owner_name:
        return

    intro = (
        "Hi! I'm Neko, a robot dog designed to be a friendly pet for mental health. "
        "What's your name?"
    )
    intro = (
        "Hi! I'm Neko, a robot dog designed to be a friendly pet for mental health. "
        "What's your name?"
    )
    
    # Speak introduction (prefer blocking to avoid mic contention)
    played_sync = False
    try:
        speak_blocking(intro)
        played_sync = True
    except Exception:
        speak_async(intro)
    
    if not played_sync:
        time.sleep(1.0)  # Allow async playback to start
    
    # Listen for owner's name
    name = None
    try:
        print("🔔 Say your name now...")
        wait_for_speaking_to_finish()
        time.sleep(0.25)  # Brief pause for user readiness
        
        with mic as source:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=5)
        
        name = recognizer.recognize_google(audio).strip()
        print(f"✓ Heard name: '{name}'")
        
    except Exception as e:
        print(f"⚠️ Microphone capture failed: {e}")
        try:
            print("Available microphones:")
            for i, mic_name in enumerate(sr.Microphone.list_microphone_names()):
                print(f"  {i}: {mic_name}")
        except Exception:
            pass
        name = None
    
    # Store name and greet
    if name:
        neko_agent.set_owner_name(name)
        greeting = f"Hi {name}! I'll be your pet and friend."
        
        try:
            speak_blocking(greeting)
        except Exception:
            speak_async(greeting)
        
        time.sleep(0.4)


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    """
    Main voice interaction loop
    
    Workflow:
        1. Setup: Get owner name
        2. Loop:
            - Wait for voice input
            - Recognize speech
            - Classify intent (command vs chat)
            - Handle appropriately
            - Check silence timeout
    """
    print("=" * 60)
    print("NEKO VOICE ASSISTANT")
    print("=" * 60)
    print("Commands: follow me, stop, wander, spray, forward, backward, etc.")
    print("Chat: anything else")
    print("Press Ctrl+C to quit")
    print("=" * 60)

    # Initial setup
    try:
        get_owner_name()
    except Exception as e:
        print(f"⚠️ Owner name setup failed: {e}")

    # Main interaction loop
    while True:
        try:
            # Wait for TTS to finish before prompting
            wait_for_speaking_to_finish()
            print("\n🎤 Say something...")

            # Listen for speech
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
            
            # Recognize speech
            print("🔄 Processing...")
            text = recognizer.recognize_google(audio)
            print(f"✓ Heard: '{text}'")
            
            # Check silence timeout
            neko_agent.check_silence_timeout()
            
            # Classify intent and handle
            intent, command, metadata = classifier.classify(text)
            
            if intent == "COMMAND":
                handle_command(command)
            else:
                handle_chat(text)
                
        except sr.WaitTimeoutError:
            # No speech detected - check silence timeout
            neko_agent.check_silence_timeout()
            print("⏱️ Timeout - no speech detected")
            
        except sr.UnknownValueError:
            # Speech detected but not understood - continue silently
            time.sleep(0.2)
            continue
            
        except KeyboardInterrupt:
            print("\n\n✓ Goodbye, nya~!")
            break
            
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    # Parse a small set of CLI flags for the assistant runtime.
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--display-blocking', action='store_true', help='Run face-follow display in foreground (main thread) when starting follow')
    parser.add_argument('--interactive-calibrate', action='store_true', help='Run face-follow interactive auto-calibration when starting follow')
    parser.add_argument('--calibration-wizard', action='store_true', help='Run interactive calibration wizard at startup and exit')
    parser.add_argument('--calibration-output', type=str, default=None, help='Path to save calibration medians JSON (used with --calibration-wizard)')
    parser.add_argument('--auto-calibrate', action='store_true', help='Run non-interactive automatic calibration and exit')
    parser.add_argument('--calibration-max-fails', type=int, default=4, help='Max consecutive failures before auto calibration exits')
    parser.add_argument('--calibration-wait', type=float, default=5.0, help='Seconds to wait between auto-calibration attempts')
    parser.add_argument('--dry-run', action='store_true', help='Run face-follow in dry-run mode (do not send motor commands)')
    known_args, _ = parser.parse_known_args()
    try:
        DISPLAY_BLOCKING_DEFAULT = bool(known_args.display_blocking)
    except Exception:
        DISPLAY_BLOCKING_DEFAULT = False
    # Determine auto-calibration default from CLI flag or environment variable
    try:
        env_auto = os.environ.get('NEKO_FACE_AUTO_CALIBRATE', '').lower() in ('1', 'true', 'yes')
    except Exception:
        env_auto = False
    try:
        # interactive calibration flag was renamed to --interactive-calibrate
        AUTO_CALIBRATE_DEFAULT = bool(known_args.interactive_calibrate) or env_auto
    except Exception:
        AUTO_CALIBRATE_DEFAULT = env_auto
    # Dry-run (no motor sends) default from CLI or env
    try:
        env_dry = os.environ.get('NEKO_FACE_DRY_RUN', '').lower() in ('1', 'true', 'yes')
    except Exception:
        env_dry = False
    try:
        DRY_RUN_DEFAULT = bool(known_args.dry_run) or env_dry
    except Exception:
        DRY_RUN_DEFAULT = env_dry

    # Inform user about display, interactive-calibration and dry-run modes
    print(f"ℹ️ Display blocking default: {DISPLAY_BLOCKING_DEFAULT}")
    print(f"ℹ️ Interactive-calibration default: {AUTO_CALIBRATE_DEFAULT} (set --interactive-calibrate or NEKO_FACE_AUTO_CALIBRATE=1 to enable)")
    print(f"ℹ️ Dry-run default: {DRY_RUN_DEFAULT} (set --dry-run or NEKO_FACE_DRY_RUN=1 to enable dry-run)")
    # If requested, run the calibration wizard and exit
    try:
        if bool(known_args.calibration_wizard):
            print('🔧 Running calibration wizard (one-shot)')
            calibration_wizard(save_path=known_args.calibration_output, n_samples=40, visualize=True, camera_index=0)
            print('🔧 Calibration wizard finished — exiting as requested')
            raise SystemExit(0)
        if bool(known_args.auto_calibrate):
            print('🔧 Running non-interactive automatic calibration (one-shot)')
            calibration_auto(save_path=known_args.calibration_output, n_samples=40, visualize=True, camera_index=0, max_consecutive_failures=known_args.calibration_max_fails, wait_between_attempts=known_args.calibration_wait)
            print('🔧 Automatic calibration finished — exiting as requested')
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as e:
        print(f"⚠️ Calibration wizard failed to start: {e}")
    main()
