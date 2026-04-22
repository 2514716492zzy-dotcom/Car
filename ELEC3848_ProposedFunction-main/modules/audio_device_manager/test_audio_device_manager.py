"""
Test script for Audio Device Manager
Shows available microphone devices and the selected device
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Check PyAudio availability
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print("⚠️ PyAudio not installed - some tests will be skipped")
    print("   This is normal on Windows development environment")
    print("   Install on Raspberry Pi with: sudo apt-get install python3-pyaudio\n")

import speech_recognition as sr
from modules.audio_device_manager import initialize_microphone


def test_device_discovery():
    """Display all available microphone devices"""
    print("=" * 60)
    print("MICROPHONE DEVICE DISCOVERY TEST")
    print("=" * 60)
    
    if not PYAUDIO_AVAILABLE:
        print("\n⏭️ Skipped: PyAudio not available")
        print("   This test requires PyAudio to enumerate audio devices")
        print("\n" + "=" * 60)
        return
    
    try:
        mic_list = sr.Microphone.list_microphone_names()
        print(f"\n📋 Found {len(mic_list)} audio device(s):\n")
        
        for i, name in enumerate(mic_list):
            # Highlight USB Audio devices
            if "USB Audio" in name or "Y1076" in name:
                print(f"  ✨ Device {i}: {name} [USB AUDIO]")
            else:
                print(f"     Device {i}: {name}")
        
    except Exception as e:
        print(f"❌ Error listing devices: {e}")
    
    print("\n" + "=" * 60)


def test_microphone_initialization():
    """Test microphone initialization and show selected device"""
    print("\n🔧 TESTING MICROPHONE INITIALIZATION")
    print("=" * 60)
    
    if not PYAUDIO_AVAILABLE:
        print("\n⏭️ Skipped: PyAudio not available")
        print("   Microphone initialization requires PyAudio")
        print("\n" + "=" * 60)
        return
    
    try:
        mic, recognizer = initialize_microphone()
        
        print("\n✅ Microphone initialized successfully!")
        print(f"\n📊 Configuration:")
        print(f"   Sample Rate: 16000 Hz")
        print(f"   Device Index: {mic.device_index if mic.device_index is not None else 'Default'}")
        
        # Show which device was actually selected
        if mic.device_index is not None:
            try:
                mic_list = sr.Microphone.list_microphone_names()
                selected_name = mic_list[mic.device_index]
                print(f"   Selected Device: {selected_name}")
            except:
                print(f"   Selected Device: Unknown (index {mic.device_index})")
        else:
            print(f"   Selected Device: System Default")
        
        print(f"\n🎤 Recognizer Settings:")
        print(f"   Energy Threshold: {recognizer.energy_threshold}")
        print(f"   Dynamic Energy: {recognizer.dynamic_energy_threshold}")
        
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)


def test_microphone_recording():
    """Quick test to verify microphone can record"""
    print("\n🎙️ TESTING MICROPHONE RECORDING")
    print("=" * 60)
    
    if not PYAUDIO_AVAILABLE:
        print("\n⏭️ Skipped: PyAudio not available")
        print("   Audio recording requires PyAudio")
        print("\n" + "=" * 60)
        return
    
    try:
        mic, recognizer = initialize_microphone()
        
        print("\n🔴 Recording a 2-second test sample...")
        print("   (Make some noise to test!)")
        
        with mic as source:
            audio = recognizer.listen(source, timeout=3, phrase_time_limit=2)
        
        print(f"\n✅ Recording successful!")
        print(f"   Audio data size: {len(audio.get_raw_data())} bytes")
        print(f"   Sample rate: {audio.sample_rate} Hz")
        print(f"   Sample width: {audio.sample_width} bytes")
        
    except sr.WaitTimeoutError:
        print("\n⏱️ Timeout: No audio detected (microphone may be working but silent)")
    except Exception as e:
        print(f"\n❌ Recording test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)


def show_pyaudio_status():
    """Show PyAudio installation status and instructions"""
    print("=" * 60)
    print("PYAUDIO STATUS")
    print("=" * 60)
    
    if PYAUDIO_AVAILABLE:
        print("\n✅ PyAudio is installed and available")
        try:
            p = pyaudio.PyAudio()
            print(f"   Version: {pyaudio.get_portaudio_version_text()}")
            print(f"   Available devices: {p.get_device_count()}")
            p.terminate()
        except Exception as e:
            print(f"   Warning: {e}")
    else:
        print("\n❌ PyAudio is NOT installed")
        print("\n📝 Installation instructions:")
        print("\n   Raspberry Pi / Linux:")
        print("   $ sudo apt-get install portaudio19-dev python3-pyaudio")
        print("   $ pip install pyaudio")
        print("\n   macOS:")
        print("   $ brew install portaudio")
        print("   $ pip install pyaudio")
        print("\n   Windows:")
        print("   $ pip install pipwin")
        print("   $ pipwin install pyaudio")
        print("   (or download wheel from https://www.lfd.uci.edu/~gohlke/pythonlibs/)")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    # Show PyAudio status first
    show_pyaudio_status()
    
    # Run all tests
    test_device_discovery()
    test_microphone_initialization()
    test_microphone_recording()
    
    print("\n✨ All tests completed!")
    
    if not PYAUDIO_AVAILABLE:
        print("\n💡 Note: Most tests were skipped due to missing PyAudio")
        print("   This is normal on Windows. Tests will run on Raspberry Pi.")

