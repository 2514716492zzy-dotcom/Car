"""
Audio Device Manager - Microphone Device Handler
Handles microphone device discovery and initialization for voice input
"""

import speech_recognition as sr


def initialize_microphone():
    """
    Find and initialize the Yundea 1076 USB Audio microphone
    This is the exact logic from minimal.py lines 30-60
    
    Returns:
        tuple: (sr.Microphone, sr.Recognizer) - Initialized microphone and recognizer
    """
    recognizer = sr.Recognizer()
    
    mic_index = None
    try:
        print("Searching for microphone devices...")
        mic_list = sr.Microphone.list_microphone_names()
        for i, name in enumerate(mic_list):
            print(f"  Device {i}: {name}")
            # Find device containing "Y1076" or "USB Audio"
            if "Voicemeeter Out B2" in name or ("USB Audio" in name and "Yundea" in name):
                mic_index = i
                print(f"✓ Selected microphone: {name} (index: {i})")
                break
        
        if mic_index is None:
            # If not found, try matching USB Audio only
            for i, name in enumerate(mic_list):
                if "USB Audio" in name:
                    mic_index = i
                    print(f"✓ Selected microphone: {name} (index: {i})")
                    break
    except Exception as e:
        print(f"⚠️ Microphone search error: {e}")

    # Use found microphone index, or default if not found
    if mic_index is not None:
        mic = sr.Microphone(device_index=mic_index, sample_rate=16000)
    else:
        print("⚠️ Specified microphone not found, using default")
        mic = sr.Microphone()
    
    # One-time ambient calibration at startup to set a reasonable energy threshold.
    try:
        with mic as source:
            print("Calibrating microphone for ambient noise (1s)...")
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
    except Exception:
        pass
    
    return mic, recognizer
