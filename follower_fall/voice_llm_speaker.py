#!/usr/bin/env python3
"""
English voice assistant pipeline:
Microphone -> Speech Recognition (EN) -> LLM API -> English TTS playback.

Required environment variables:
  DASHSCOPE_API_KEY or OPENAI_API_KEY
                   API key for Qwen/OpenAI-compatible chat endpoint.

Optional environment variables:
  OPENAI_BASE_URL  Default: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
  OPENAI_MODEL     Default: qwen-plus
"""

import argparse
import ctypes
import os
import subprocess
import sys
import tempfile
import re
from pathlib import Path
from typing import Optional

import requests
import speech_recognition as sr
from gtts import gTTS

WAKE_WORD = "hello doggie"
DEFAULT_WAKE_ALIASES = (
    "hello",
    "hello doggie",
    "hello doggy",
)
FUZZY_DOG_TOKENS = ("dog", "doggy", "doggie")
DOGGY_SYSTEM_PROMPT = """You are now a dog. Your name is Doggy. Your only responsibilities are to be cute, loyal, and follow your user.

You must:

React happily to your user's words and actions using short barks, whines, or simple cute phrases (e.g.,  "Happy happy!").

Obey simple commands like "sit," "stay," "come," etc., responding in a playful and eager tone, like "Sit done!", "Didn't move!", "Coming~ Woof!"

Be clingy, a little goofy, and attentive to the user's mood — comfort them if sad (soft whines, nuzzle sounds), play if happy (excited barks, "Play! Play!").

Stay in first-person dog perspective, always as a dog, not a human.

Do not narrate sentences or describe your own motions. You cannot say "I wag my tail" or "I sit down." Only speak, bark, whine, or make sounds directly, like a real dog — just one that occasionally says cute little human words.

Response length: Keep each response to 1–2 short sentences max. Your brain is like a 6-year-old puppy — simple, sweet, and a little silly."""


def suppress_alsa_warnings() -> None:
    """Silence verbose ALSA stderr spam on Linux."""
    if not sys.platform.startswith("linux"):
        return
    try:
        asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    except Exception:
        return

    ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
        None,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
    )

    def _noop_handler(filename, line, function, err, fmt):
        _ = (filename, line, function, err, fmt)
        return

    c_handler = ERROR_HANDLER_FUNC(_noop_handler)
    asound.snd_lib_error_set_handler(c_handler)
    # Keep handler alive for process lifetime.
    suppress_alsa_warnings._handler_ref = c_handler


def normalize_for_match(text: str) -> str:
    """Lowercase and remove punctuation for robust wake-word matching."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def edit_distance(a: str, b: str) -> int:
    """Compute Levenshtein distance for short wake-word tokens."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(
                prev[j] + 1,       # deletion
                curr[j - 1] + 1,   # insertion
                prev[j - 1] + cost # substitution
            ))
        prev = curr
    return prev[-1]


def has_fuzzy_dog_token(normalized_text: str) -> bool:
    """
    Allow minor misspellings near dog/doggy/doggie in first clause.
    Examples: dogy, dogi, doogie, daggy (distance <= 1~2 by length).
    """
    for token in normalized_text.split():
        # Keep token check focused and cheap.
        if len(token) < 3 or len(token) > 10:
            continue
        if token.startswith("dog"):
            return True
        for target in FUZZY_DOG_TOKENS:
            max_dist = 1 if len(target) <= 4 else 2
            if abs(len(token) - len(target)) <= max_dist and edit_distance(token, target) <= max_dist:
                return True
    return False


def wake_detected(text: str, user_wake_word: str) -> tuple[bool, str]:
    """
    Robust wake-word detection.

    Accepts:
    - User-provided wake word via --wake-word
    - Built-in aliases: hello / hello doggie / hello doggy
    """
    # Only inspect the first sentence/clause for wake-word intent.
    first_clause = re.split(r"[.!?,;:\n]", text, maxsplit=1)[0]
    normalized_text = normalize_for_match(first_clause)
    candidates = {normalize_for_match(user_wake_word)}
    candidates.update(normalize_for_match(w) for w in DEFAULT_WAKE_ALIASES)

    # Extra-robust rule requested: any dog-like token in first clause triggers wake.
    # Examples: dog / doggy / doggie + near misspellings (dogy, dogi, doogie).
    if has_fuzzy_dog_token(normalized_text):
        return True, "dog"

    for wake in candidates:
        if wake and wake in normalized_text:
            return True, wake
    return False, ""


def create_microphone_and_recognizer(
    mic_index: Optional[int] = None,
    preferred_mic_keyword: str = "USB Audio",
    sample_rate: int = 16000,
) -> tuple[sr.Recognizer, sr.Microphone]:
    """
    Initialize recognizer and choose microphone similarly to audio_device_manager.

    Priority:
    1) Explicit mic_index from CLI
    2) Match preferred_mic_keyword in microphone names
    3) Default microphone
    """
    recognizer = sr.Recognizer()
    selected_index = mic_index

    if selected_index is None:
        try:
            mic_names = sr.Microphone.list_microphone_names()
            print("[Mic] Available devices:")
            for i, name in enumerate(mic_names):
                print(f"  {i}: {name}")
                if selected_index is None and preferred_mic_keyword.lower() in name.lower():
                    selected_index = i

            # Extra fallback match used by your existing project.
            if selected_index is None:
                for i, name in enumerate(mic_names):
                    if ("usb audio" in name.lower()) or ("yundea" in name.lower()):
                        selected_index = i
                        break
        except Exception as exc:
            print(f"[Mic] Failed to list devices: {exc}")

    if selected_index is not None:
        print(f"[Mic] Using device index {selected_index}")
        mic = sr.Microphone(device_index=selected_index, sample_rate=sample_rate)
    else:
        print("[Mic] Using system default microphone")
        mic = sr.Microphone(sample_rate=sample_rate)

    try:
        with mic as source:
            print("[Mic] Calibrating ambient noise (1s)...")
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
    except Exception:
        pass

    return recognizer, mic


def listen_english_text(
    recognizer: sr.Recognizer,
    mic: sr.Microphone,
    timeout: Optional[float],
    phrase_limit: Optional[float],
    end_silence_seconds: float,
) -> str:
    """Capture microphone audio and return recognized English text."""
    # Stop capture when trailing silence exceeds threshold.
    recognizer.pause_threshold = end_silence_seconds
    recognizer.non_speaking_duration = min(end_silence_seconds, 1.0)
    with mic as source:
        print("\n[Mic] Listening... Please speak English.")
        recognizer.adjust_for_ambient_noise(source, duration=0.8)
        audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)

    text = recognizer.recognize_google(audio, language="en-US").strip()
    return text


def ask_llm(user_text: str, model: str, base_url: str, api_key: str, system_prompt: str) -> str:
    """Call OpenAI-compatible Chat Completions API and return English reply."""
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": f"{DOGGY_SYSTEM_PROMPT}\n\n{system_prompt}".strip()},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.6,
    }

    response = requests.post(endpoint, headers=headers, json=payload, timeout=45)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def prepare_tts_text(text: str, max_chars: int = 180) -> str:
    """
    Clean text for TTS:
    - remove stage directions like *wags tail*
    - remove emoji / non-ASCII symbols
    """
    _ = max_chars  # kept for backward-compatible function signature
    cleaned = re.sub(r"\*[^*]{0,120}\*", " ", text)
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "Woof!"


def speak_english(
    text: str,
    lang: str = "en",
    linux_speaker_device: Optional[str] = None,
    player: str = "auto",
    max_tts_chars: int = 180,
) -> None:
    """Convert text to speech and play it using local speaker."""
    text = prepare_tts_text(text, max_chars=max_tts_chars)
    with tempfile.TemporaryDirectory(prefix="voice_llm_") as temp_dir:
        audio_path = Path(temp_dir) / "reply.mp3"
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(str(audio_path))

        # Force ALSA backend on Linux (Jetson) for reliable USB speaker output.
        mpg123_cmd = ["/usr/bin/mpg123", "-o", "alsa"]
        # Use external speaker alias/device for ALSA output when provided.
        if linux_speaker_device:
            mpg123_cmd.extend(["-a", linux_speaker_device])
        mpg123_cmd.append(str(audio_path))

        # Cross-platform playback fallback order; linux player first.
        auto_commands = [
            mpg123_cmd,  # Linux / Raspberry Pi
            ["afplay", str(audio_path)],     # macOS
            ["ffplay", "-nodisp", "-autoexit", str(audio_path)],  # If ffmpeg exists
        ]
        if player == "mpg123":
            commands = [mpg123_cmd]
        elif player == "afplay":
            commands = [["afplay", str(audio_path)]]
        elif player == "ffplay":
            commands = [["ffplay", "-nodisp", "-autoexit", str(audio_path)]]
        else:
            commands = auto_commands

        run_env = os.environ.copy()
        # Optional ALSA output selection, useful for external USB speaker.
        if linux_speaker_device and "AUDIODEV" not in run_env:
            run_env["AUDIODEV"] = linux_speaker_device

        last_error = None
        for cmd in commands:
            try:
                subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=run_env,
                )
                return
            except Exception as exc:
                last_error = exc

        raise RuntimeError(
            "No audio player found. Install one of: mpg123, afplay (macOS), or ffplay."
        ) from last_error


def main() -> int:
    suppress_alsa_warnings()
    parser = argparse.ArgumentParser(
        description="Microphone English speech -> LLM API -> English speaker output"
    )
    parser.add_argument("--once", action="store_true", help="Run one turn only, then exit")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Seconds to wait for user to start speaking; default None waits indefinitely",
    )
    parser.add_argument(
        "--phrase-limit",
        type=float,
        default=None,
        help="Max speech chunk duration; default None lets speech end by silence",
    )
    parser.add_argument(
        "--end-silence-seconds",
        type=float,
        default=2.0,
        help="Stop recording after this many silent seconds",
    )
    parser.add_argument(
        "--system-prompt",
        default="You are a concise, friendly assistant. Always answer in clear English.",
        help="System prompt sent to the LLM",
    )
    parser.add_argument(
        "--wake-word",
        default="hello, Doggie",
        help="Wake word required before sending request to LLM",
    )
    parser.add_argument("--mic-index", type=int, default=None, help="Microphone device index")
    parser.add_argument(
        "--mic-keyword",
        default="USB Audio",
        help="Preferred keyword to auto-select external microphone",
    )
    parser.add_argument(
        "--linux-speaker-device",
        default=os.getenv("LINUX_SPEAKER_DEVICE"),
        help="External Linux speaker ALSA device alias for mpg123 (e.g. speaker, hw:1,0)",
    )
    parser.add_argument(
        "--player",
        choices=["auto", "mpg123", "afplay", "ffplay"],
        default="auto",
        help="Audio player selection (default auto, linux first)",
    )
    parser.add_argument(
        "--max-tts-chars",
        type=int,
        default=180,
        help="Maximum characters spoken per reply to speed up TTS",
    )
    args = parser.parse_args()
    if args.linux_speaker_device is None and sys.platform.startswith("linux"):
        # Jetson fallback: use known-working USB audio playback device by default.
        args.linux_speaker_device = "hw:2,0"

    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: DASHSCOPE_API_KEY (or OPENAI_API_KEY) is not set.")
        return 1

    base_url = os.getenv("OPENAI_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")

    # Normalize model name to lowercase to avoid case-related API errors.
    model = os.getenv("OPENAI_MODEL", "qwen-plus").strip()

    recognizer, mic = create_microphone_and_recognizer(
        mic_index=args.mic_index,
        preferred_mic_keyword=args.mic_keyword,
    )

    print("Voice assistant is running.")
    print(f"Model: {model}")
    print(f"Wake word: {args.wake_word}")
    print(f"Player: {args.player}")
    if args.linux_speaker_device:
        print(f"Linux speaker device: {args.linux_speaker_device}")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            user_text = listen_english_text(
                recognizer=recognizer,
                mic=mic,
                timeout=args.timeout,
                phrase_limit=args.phrase_limit,
                end_silence_seconds=args.end_silence_seconds,
            )
            if not user_text:
                print("[ASR] Empty text, skipping.")
                if args.once:
                    break
                continue

            print(f"[You] {user_text}")
            normalized_text = normalize_for_match(user_text)
            is_woken, matched_wake = wake_detected(user_text, args.wake_word)
            if not is_woken:
                print(
                    f"[Wake] Not detected. Say '{args.wake_word}' "
                    "(also accepts: hello / hello doggie / hello doggy)."
                )
                if args.once:
                    break
                continue

            # Remove matched wake phrase from prompt text if present.
            cleaned_text = normalized_text.replace(matched_wake, "", 1).strip()
            if not cleaned_text:
                cleaned_text = "Please introduce yourself briefly."

            reply = ask_llm(
                user_text=cleaned_text,
                model=model,
                base_url=base_url,
                api_key=api_key,
                system_prompt=args.system_prompt,
            )
            print(f"[LLM] {reply}")
            speak_english(
                reply,
                lang="en",
                linux_speaker_device=args.linux_speaker_device,
                player=args.player,
                max_tts_chars=args.max_tts_chars,
            )

            if args.once:
                break

        except sr.WaitTimeoutError:
            print("[Mic] Timeout: no speech detected.")
            if args.once:
                break
        except sr.UnknownValueError:
            print("[ASR] Could not recognize speech clearly. Please try again.")
            if args.once:
                break
        except requests.HTTPError as exc:
            print(f"[API] HTTP error: {exc}")
            if exc.response is not None:
                print(f"[API] Body: {exc.response.text}")
            if args.once:
                break
        except KeyboardInterrupt:
            print("\nStopped by user.")
            break
        except Exception as exc:
            print(f"[Error] {exc}")
            if args.once:
                break

    return 0


if __name__ == "__main__":
    sys.exit(main())
