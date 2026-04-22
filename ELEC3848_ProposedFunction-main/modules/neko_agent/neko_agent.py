"""
Neko Agent Module
=================

A conversational AI agent for mental health support with personality and emotion tracking.

Key Features:
- Multi-turn conversation with sliding window history management
- Personalization with owner name
- Soft-clear mechanism for context recovery after silence
- Emotion tagging for hardware integration
- Fallback responses when LLM unavailable

Configuration:
- config.ini: silence_timeout, max_history_turns
- prompts.ini: system prompts and emotion labels

Usage:
    agent = NekoAgent(owner_name="Alice")
    response = agent.chat("Hello!")
    agent.check_silence_timeout()  # Auto-clear after timeout
"""

import time
import json
import re
import configparser
from pathlib import Path
from typing import Optional, Tuple
from modules.llm import LLMModule
from modules.common_tools import load_config
from modules.neko_agent.tools.tool_manager import ToolManager


# ==================== MAIN AGENT CLASS ====================

class NekoAgent:
    """
    Conversational agent with memory, personalization, and emotion tracking
    
    Manages conversation history with automatic trimming and soft-clear recovery.
    Integrates with LLM for natural responses and falls back to keywords when needed.
    """
    
    # -------------------- Initialization --------------------
    
    def __init__(self, owner_name: Optional[str] = None, 
                 silence_timeout: Optional[int] = None, 
                 max_history_turns: Optional[int] = None):
        """
        Initialize Neko Agent
        
        Args:
            owner_name: Owner's name for personalization (optional)
            silence_timeout: Seconds before clearing history (default: from config.ini or 20)
            max_history_turns: Max conversation turns to keep (default: from config.ini or 5)
        """
        # Load configurations
        config = load_config()
        prompts = self._load_prompts()
        
        # Public attributes
        self.owner_name = owner_name
        self.silence_timeout = silence_timeout if silence_timeout is not None else config.getint('neko_agent', 'silence_timeout', fallback=20)
        self.max_history_turns = max_history_turns if max_history_turns is not None else config.getint('neko_agent', 'max_history_turns', fallback=5)
        
        # Private state
        self._prompts = prompts
        self._history = None  # Lazy initialization
        self._llm_instance = None  # Lazy initialization
        self._last_interaction = None
        self._history_cleared = False
        self._saved_last_assistant = None
        
        # Tool system
        self._tool_manager = ToolManager()
        
        # Fallback responses when LLM unavailable
        self.chat_responses = {
            'greeting': "Hello! I'm Neko, nya~!",
            'how_are_you': "I'm doing great, desu~!",
            'name': "I'm Neko, your AI companion!",
            'love': "Aww, I love you too! *purrs*",
            'default': "That's interesting, nya~!"
        }
    
    def _load_prompts(self) -> dict:
        """Load prompts from prompts.ini"""
        prompt_file = Path(__file__).parent / "prompts.ini"
        config = configparser.ConfigParser()
        config.read(prompt_file, encoding="utf-8")
        
        emotions_str = config.get('emotion_instruction', 'allowed_emotions')
        allowed_emotions = [e.strip() for e in emotions_str.split(',')]
        
        return {
            'system_with_owner': config.get('system_prompt', 'with_owner'),
            'system_without_owner': config.get('system_prompt', 'without_owner'),
            'allowed_emotions': allowed_emotions,
            'emotion_template': config.get('emotion_instruction', 'template')
        }
    
    # -------------------- Public API --------------------
    
    def set_owner_name(self, name: str):
        """Set or update owner's name and regenerate system prompt"""
        self.owner_name = name
        self._history = None  # Force regeneration
    
    def chat(self, text: str) -> Tuple[str, Optional[dict]]:
        """
        Process user input and generate response
        
        Workflow:
        1. Initialize/restore conversation history
        2. Add user message
        3. Call LLM (with fallback to keywords)
        4. Extract emotion from response
        5. Clean response for TTS
        6. Add assistant response to history
        7. Trim history and update timestamp
        
        Args:
            text: User's input text
            
        Returns:
            Tuple of (spoken_text, emotion_dict)
            - spoken_text: Cleaned text for TTS (no markdown, no JSON)
            - emotion_dict: {'emotion': 'happy', 'emoji': '😊'} or None
        """
        print(f"💬 CHATTING ABOUT: {text}")
        
        self._initialize_history()
        self._handle_soft_clear_recovery(text)
        
        # Add user message
        self._history.append({"role": "user", "content": text})
        
        # Get response from LLM or fallback
        raw_response = self._call_llm()
        if raw_response is None:
            raw_response = self._fallback_response(text)
        
        # Extract emotion and clean text for TTS
        spoken_text, emotion = self._extract_emotion_and_clean(raw_response)
        
        # Add original response to history (with emotion JSON)
        self._history.append({"role": "assistant", "content": raw_response})
        
        # Maintain history and timestamp
        self._trim_history()
        self._last_interaction = time.time()
        
        return spoken_text, emotion
    
    def check_silence_timeout(self) -> bool:
        """
        Check if silence timeout exceeded and auto-clear history
        
        Returns:
            True if timeout exceeded and history was cleared
        """
        if self._last_interaction is None:
            return False
        
        if (time.time() - self._last_interaction) > self.silence_timeout:
            self.clear_history(reason="silence")
            return True
        
        return False
    
    def clear_history(self, reason: str = "manual"):
        """
        Clear conversation history with soft-clear mechanism
        
        Soft-clear saves the last assistant message for potential recovery
        if user's next input looks like an answer to that message.
        
        Args:
            reason: Reason for clearing (for logging: "manual", "silence", "command")
        """
        self._initialize_history()
        
        # Find system and last assistant messages
        system = None
        last_assistant = None
        for m in self._history:
            if m.get("role") == "system":
                system = m
            if m.get("role") == "assistant":
                last_assistant = m
        
        # Save for potential recovery
        self._saved_last_assistant = last_assistant
        
        # Reset to system message only
        self._history = [system] if system else []
        self._history_cleared = True
        self._last_interaction = None
        
        print(f"🔁 Conversation history cleared due to {reason}")
    
    def get_history(self) -> list:
        """Get copy of current conversation history"""
        if self._history is None:
            self._initialize_history()
        return self._history.copy()
    
    def get_last_interaction_time(self) -> Optional[float]:
        """Get timestamp of last interaction"""
        return self._last_interaction
    
    # -------------------- System Prompt Generation --------------------
    
    def get_system_prompt(self) -> str:
        """Generate complete system prompt with personality and emotion instructions"""
        if self.owner_name:
            system_content = self._prompts['system_with_owner'].format(owner_name=self.owner_name)
        else:
            system_content = self._prompts['system_without_owner']
        
        system_content += "\n\n" + self._get_emotion_system_context()
        return system_content
    
    def _get_emotion_system_context(self) -> str:
        """Generate emotion tagging instruction for LLM"""
        allowed_list = ",".join(f'"{e}"' for e in self._prompts['allowed_emotions'])
        return self._prompts['emotion_template'].format(allowed_emotions=allowed_list)
    
    # -------------------- History Management --------------------
    
    def _initialize_history(self):
        """Initialize conversation history with system prompt (lazy)"""
        if self._history is None:
            self._history = [{
                "role": "system",
                "content": self.get_system_prompt()
            }]
    
    def _trim_history(self, max_turns: Optional[int] = None):
        """
        Trim history to sliding window of recent turns
        
        Keeps system message + last N turns (1 turn = user + assistant message pair).
        Default max_turns from config (typically 5 turns = 10 messages).
        """
        if max_turns is None:
            max_turns = self.max_history_turns
        
        # Extract system message
        system = None
        for m in self._history:
            if m.get("role") == "system":
                system = m
                break
        
        # Keep only last N turns
        others = [m for m in self._history if m.get("role") != "system"]
        max_messages = max_turns * 2
        if len(others) > max_messages:
            others = others[-max_messages:]
        
        self._history = [system] + others if system else others
    
    def _handle_soft_clear_recovery(self, text: str):
        """
        Restore last assistant message if user input looks like an answer
        
        After soft-clear, if user's input appears to answer the last question,
        restore that question to maintain conversation flow.
        """
        if self._history_cleared:
            if self._is_likely_answer(text):
                saved = self._saved_last_assistant
                system = None
                for m in self._history:
                    if m.get("role") == "system":
                        system = m
                        break
                self._history = [system] if system else []
                if saved:
                    self._history.append(saved)
            
            self._history_cleared = False
            self._saved_last_assistant = None
    
    def _is_likely_answer(self, text: str) -> bool:
        """
        Heuristic to detect if text is an answer to a question
        
        Checks for:
        - Starts with "I'm", "I am", "I "
        - Starts with yes/no/sure/yeah
        - Contains feeling/emotion words
        """
        if not text:
            return False
        t = text.strip().lower()
        if not t:
            return False
        
        # Direct confirmations or self-references
        if t.startswith("i'm") or t.startswith("i am") or t.startswith("i "):
            return True
        words = t.split()
        if words and words[0] in ("yes", "no", "yeah", "nah", "yep", "sure"):
            return True
        
        # Contains feeling indicators
        for w in ("feeling", "good", "bad", "happy", "sad", "okay", "ok", "fine"):
            if w in t:
                return True
        
        return False
    
    # -------------------- LLM Integration --------------------
    
    def _call_llm(self) -> Optional[str]:
        """
        Call LLM with conversation history and tool support
        
        Supports function calling for tools (e.g., weather).
        Returns None if LLM unavailable or fails.
        """
        try:
            # Lazy load LLM instance
            if self._llm_instance is None:
                self._llm_instance = LLMModule()
            
            print("🔎 Using LLMModule for chat...")
            
            # Get tool definitions if available
            tools = None
            if self._tool_manager.has_tools():
                tools = self._tool_manager.get_tool_definitions()
            
            # Call LLM with messages and tools
            result = self._llm_instance.call_llm(messages=self._history, tools=tools)
            
            if isinstance(result, dict) and result.get("status") == "success":
                response = result.get("response")
                tool_calls = result.get("tool_calls")
                
                # Handle tool calls if present
                if tool_calls:
                    # Let ToolManager handle the tool execution and history updates
                    self._tool_manager.handle_tool_calls(tool_calls, self._history)
                    
                    # Call LLM again to generate final response
                    try:
                        result = self._llm_instance.call_llm(messages=self._history, tools=None)
                        if isinstance(result, dict) and result.get("status") == "success":
                            return result.get("response")
                        return None
                    except Exception as e:
                        print(f"⚠️ Failed to generate response after tool call: {e}")
                        return None
                
                return response
            else:
                print(f"⚠️ LLMModule returned failure: {result}")
                return None
        
        except Exception as e:
            print(f"⚠️ LLMModule unavailable or failed: {e}")
            return None
    
    def _fallback_response(self, text: str) -> str:
        """
        Generate fallback response using keyword matching
        
        Used when LLM is unavailable. Provides basic responses based on
        keywords in user input.
        """
        text_lower = text.lower()
        
        if 'hello' in text_lower or 'hi' in text_lower:
            return self.chat_responses['greeting']
        elif 'how are you' in text_lower:
            return self.chat_responses['how_are_you']
        elif 'name' in text_lower:
            return self.chat_responses['name']
        elif 'love you' in text_lower:
            return self.chat_responses['love']
        else:
            return self.chat_responses['default']
    
    def _extract_emotion_and_clean(self, text: str) -> Tuple[str, Optional[dict]]:
        """
        Extract emotion JSON tag from LLM response and clean text for TTS
        
        Removes markdown formatting, code blocks, HTML tags, and extracts
        emotion metadata from final-line JSON object.
        
        Args:
            text: Raw LLM response (may include emotion JSON on final line)
            
        Returns:
            Tuple of (spoken_text, emotion_dict)
            - spoken_text: Cleaned text suitable for TTS (no markdown, no JSON)
            - emotion_dict: {'emotion': 'happy', 'emoji': '😊'} or None
        """
        if not text:
            return "", None
        
        s = text
        # Remove fenced code blocks ```...``` and inline code `...`
        s = re.sub(r"```[\s\S]*?```", "", s)
        s = re.sub(r"`+", "", s)
        # Replace markdown links [text](url) -> text
        s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)
        # Remove HTML tags
        s = re.sub(r"<[^>]+>", "", s)
        # Remove common markdown emphasis characters: * _ ~ >
        s = s.replace("*", "")
        s = s.replace("_", "")
        s = s.replace("~", "")
        # Remove blockquote markers at line starts
        s = re.sub(r"^>\s*", "", s, flags=re.M)
        
        # Attempt to extract a final-line JSON object for emotion metadata
        emotion = None
        try:
            s_stripped = s.rstrip()
            # Find the last JSON-like substring by locating last '{' and last '}'
            last_open = s_stripped.rfind('{')
            last_close = s_stripped.rfind('}')
            if last_open != -1 and last_close != -1 and last_close > last_open:
                candidate = s_stripped[last_open:last_close + 1]
                try:
                    parsed = json.loads(candidate)
                    # Minimal validation: must contain 'emotion' as a string
                    if isinstance(parsed, dict) and 'emotion' in parsed and isinstance(parsed.get('emotion'), str):
                        emotion = parsed
                        # Remove the JSON substring (and any trailing whitespace/newlines)
                        s = s_stripped[:last_open].rstrip()
                except Exception:
                    # Not valid JSON — ignore and continue
                    emotion = None
        except Exception:
            emotion = None
        
        # Collapse multiple whitespace/newlines to single space for spoken text
        s = re.sub(r"\s+", " ", s)
        s = s.strip()
        
        return s, emotion
        return self._history.copy()
    
    def get_last_interaction_time(self) -> Optional[float]:
        """Get timestamp of last interaction"""
        return self._last_interaction
