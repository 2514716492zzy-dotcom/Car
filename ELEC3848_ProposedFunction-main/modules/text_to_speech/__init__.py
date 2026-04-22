"""
TTS (Text-to-Speech) Module
Handles voice synthesis with multiple voice options
"""

from .tts_module import TextToSpeech, speak_normal, speak_cute_sox

__all__ = [
    'TextToSpeech',
    'speak_normal',
    'speak_cute_sox'
]
