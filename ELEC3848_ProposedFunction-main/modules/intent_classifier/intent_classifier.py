"""
Intent Classifier - Distinguishes between Commands and Chat
Parses voice input to determine if user wants robot control or conversation
"""

import re
from typing import Tuple, Optional, Dict


class IntentClassifier:
    """
    Classifies user voice input into two categories:
    1. COMMAND - Robot control instructions
    2. CHAT - Conversational interaction
    """
    
    def __init__(self):
        # Define command keywords and patterns
        self.command_patterns = {
            # Movement commands
            'follow_me': [
                r'\b(follow|chase|track)\s*(me|owner)\b',
                r'\bcome\s*(here|with me)\b',
            ],
            'follow_person': [
                r'\b(follow|track)\s*(that person|them|him|her)\b',
            ],
            'wander': [
                r'\b(wander|explore|roam|walk around)\b',
                r'\b(free mode|autonomous)\b',
            ],
            'stop': [
                r'\b(stop|halt|wait|stay|freeze)\b',
                r'\b(don\'t move|stand still)\b',
            ],
            
            # Action commands
            'spray': [
                r'\b(spray|water|squirt|attack)\b',
                r'\b(spray mode|water mode)\b',
            ],
            'return': [
                r'\b(come back|return|go home)\b',
            ],
            
            # Status commands
            'battery': [
                r'\b(battery|power|charge)\s*(status|level|percentage)?\b',
            ],
            'status': [
                r'\b(status|state|mode|what.*doing)\b',
            ],
            'forward': [
                r'\b(forward|go forward|move forward|go ahead)\b',
            ],
            'backward': [
                r'\b(backward|go backward|move backward|go back)\b',
            ],
            'left': [
                r'\b(move left|turn left)\b',
            ],
            'right': [
                r'\b(move right|turn right)\b',
            ],
            'rotate_left': [
                r'\b(rotate left)\b',
            ],
            'rotate_right': [
                r'\b(rotate right)\b',
            ],
        }
        
        # Chat/conversation trigger patterns (explicit conversational phrases)
        self.chat_indicators = [
            r'\b(how are you|what\'s up|wassup)\b',
            r'\b(tell me|say something|talk to me)\b',
            r'\b(what is your name|who are you)\b',
            r'\b(joke|story|sing)\b',
            r'\b(i love you|you\'re cute|good (girl|cat))\b',
            r'\bwhat do you (think|like|want)\b',
            r'\b(hello|hi|hey|greetings)(?!\s*neko)\b',  # Greeting not followed by wake word
        ]
        
    def classify(self, text: str) -> Tuple[str, Optional[str], Dict]:
        """
        Classify the intent of the voice input
        
        Args:
            text: Transcribed speech text
            
        Returns:
            Tuple of (intent_type, command_name, metadata)
            - intent_type: 'COMMAND' or 'CHAT'
            - command_name: Specific command if COMMAND, None if CHAT
            - metadata: Additional info like confidence, matched pattern
        """
        text_lower = text.lower().strip()
        
        # Empty input handling
        if not text_lower:
            return ('UNKNOWN', None, {'confidence': 0.0, 'text': text})
        
        # Step 1: Check for explicit command patterns
        command_match = self._match_command(text_lower)
        if command_match:
            return ('COMMAND', command_match['command'], {
                'confidence': command_match['confidence'],
                'text': text,
                'pattern': command_match['pattern']
            })
        
        # Step 2: Check for explicit chat indicators
        chat_match = self._match_chat_indicator(text_lower)
        if chat_match:
            return ('CHAT', None, {
                'confidence': chat_match['confidence'],
                'text': text,
                'pattern': chat_match['pattern']
            })
        
        # Step 3: Heuristic-based classification
        # If input is a question, likely chat
        if self._is_question(text_lower):
            return ('CHAT', None, {
                'confidence': 0.7,
                'text': text,
                'reason': 'question_detected'
            })
        
        # If very short (1-2 words), likely command
        word_count = len(text_lower.split())
        if word_count <= 2:
            return ('COMMAND', 'unknown', {
                'confidence': 0.5,
                'text': text,
                'reason': 'short_utterance'
            })
        
        # Default: Treat as chat if uncertain
        return ('CHAT', None, {
            'confidence': 0.6,
            'text': text,
            'reason': 'default_chat'
        })
    
    def _match_command(self, text: str) -> Optional[Dict]:
        """Check if text matches any command pattern"""
        for command_name, patterns in self.command_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return {
                        'command': command_name,
                        'confidence': 0.95,
                        'pattern': pattern
                    }
        return None
    
    def _match_chat_indicator(self, text: str) -> Optional[Dict]:
        """Check if text matches chat indicator patterns"""
        for pattern in self.chat_indicators:
            if re.search(pattern, text, re.IGNORECASE):
                return {
                    'confidence': 0.9,
                    'pattern': pattern
                }
        return None
    
    def _is_question(self, text: str) -> bool:
        """Detect if text is a question"""
        question_words = ['what', 'why', 'how', 'when', 'where', 'who', 'which', 'whose', 'whom']
        
        # Check for question mark
        if '?' in text:
            return True
        
        # Check if starts with question word
        words = text.split()
        if words and words[0] in question_words:
            return True
        
        # Check for question patterns
        question_patterns = [
            r'\b(can you|could you|will you|would you|do you|are you|is it)\b',
            r'\b(have you|did you|does it)\b',
        ]
        
        for pattern in question_patterns:
            if re.search(pattern, text):
                return True
        
        return False
    
    def add_custom_command(self, command_name: str, patterns: list):
        """
        Add custom command patterns dynamically
        
        Args:
            command_name: Name of the command
            patterns: List of regex patterns to match
        """
        if command_name in self.command_patterns:
            self.command_patterns[command_name].extend(patterns)
        else:
            self.command_patterns[command_name] = patterns
    
    def get_all_commands(self) -> list:
        """Return list of all available command names"""
        return list(self.command_patterns.keys())
