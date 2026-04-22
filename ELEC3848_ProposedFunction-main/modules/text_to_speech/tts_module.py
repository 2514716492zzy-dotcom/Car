"""
TTS Module
Text-to-speech synthesis with multiple voice options
"""

import os
import time
import tempfile
from pathlib import Path
from gtts import gTTS
from modules.common_tools import load_config


class TextToSpeech:
    """
    Text-to-Speech engine with configurable voice options
    
    Supports:
    - Normal voice (Google TTS)
    - Cute voice with sox pitch shifting
    """
    
    def __init__(self, voice: str = None, language: str = None, speed: str = None):
        """
        Initialize TTS engine
        
        Args:
            voice: Voice type ('normal' or 'cute_sox'), defaults to config.ini value
            language: Language code (e.g., 'en'), defaults to config.ini value
            speed: Speed setting ('normal' or 'slow'), defaults to config.ini value
        """
        config = load_config()
        
        # All parameters default to config values
        self.voice = voice or config.get('tts', 'voice', fallback='cute_sox')
        self.language = language or config.get('tts', 'language', fallback='en')
        self.speed = speed or config.get('tts', 'speed', fallback='normal')
        
        # Create temp directory for audio files (works on all platforms including RPi)
        self.temp_dir = Path(tempfile.gettempdir()) / "neko_tts"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Validate voice option
        if self.voice not in ['normal', 'cute_sox']:
            print(f"⚠️ Unknown voice '{self.voice}', falling back to 'cute_sox'")
            self.voice = 'cute_sox'
    
    def speak(self, text: str):
        """
        Speak text using configured voice
        
        Args:
            text: Text to synthesize
        """
        if self.voice == 'normal':
            self._speak_normal(text)
        elif self.voice == 'cute_sox':
            self._speak_cute_sox(text)
    
    def _speak_normal(self, text: str):
        """Speak text using Google TTS (normal voice)"""
        temp_file = None
        try:
            print(f"🔊 Speaking (normal): {text}")
            slow = (self.speed == 'slow')
            tts = gTTS(text=text, lang=self.language, slow=slow)
            
            # Save to temp directory
            temp_file = self.temp_dir / "temp_response.mp3"
            tts.save(str(temp_file))
            
            # macOS - play slightly faster for snappier responses
            # os.system(f"afplay -r 1.30 '{temp_file}'")
            
            # For Raspberry Pi and Linux, use mpg123
            os.system(f"mpg123 '{temp_file}'")
            
        except Exception as e:
            print(f"❌ TTS error: {e}")
            time.sleep(1)
        finally:
            # Cleanup
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
    
    def _speak_cute_sox(self, text: str):
        """Speak with high-pitched cute voice using sox"""
        temp_normal = None
        temp_cute = None
        try:
            print(f"🎀 Speaking (cute - sox): {text}")
            slow = (self.speed == 'slow')
            tts = gTTS(text=text, lang=self.language, slow=slow)
            
            # Save to temp directory
            temp_normal = self.temp_dir / "temp_normal.mp3"
            temp_cute = self.temp_dir / "temp_cute.mp3"
            
            tts.save(str(temp_normal))
            
            # Pitch shift with sox (300 = sweet cat-girl voice)
            os.system(f"sox '{temp_normal}' '{temp_cute}' pitch 300 2>/dev/null")

            # macOS (play slightly faster)
            # os.system(f"afplay -r 1.15 '{temp_cute}'")

            # For Raspberry Pi and Linux, use mpg123
            os.system(f"mpg123 '{temp_cute}'")

        except Exception as e:
            print(f"❌ Sox TTS error (falling back to normal): {e}")
            self._speak_normal(text)
        finally:
            # Cleanup both temp files
            if temp_normal and temp_normal.exists():
                try:
                    temp_normal.unlink()
                except Exception:
                    pass
            if temp_cute and temp_cute.exists():
                try:
                    temp_cute.unlink()
                except Exception:
                    pass


# Legacy function wrappers for backward compatibility
def speak_normal(text):
    """Legacy wrapper: Speak text using normal voice"""
    tts = TextToSpeech(voice='normal')
    tts.speak(text)


def speak_cute_sox(text):
    """Legacy wrapper: Speak with cute voice using sox"""
    tts = TextToSpeech(voice='cute_sox')
    tts.speak(text)

