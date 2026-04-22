"""
Test cases for NekoAgent module
Run from project root: python modules/neko_agent/test_neko_agent.py
"""
import os
import sys
from pathlib import Path

# Add project root to path and change working directory
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)  # Change to project root for config files

from modules.neko_agent import NekoAgent
import time


def test_basic_chat():
    """Test basic chat functionality"""
    print("\n=== Test 1: Basic Chat ===")
    agent = NekoAgent()
    
    # Test greeting
    response, emotion = agent.chat("hello")
    print(f"User: hello")
    print(f"Neko: {response}")
    print(f"Emotion: {emotion}")
    assert response is not None and len(response) > 0
    
    # Test name question
    response, emotion = agent.chat("what's your name?")
    print(f"User: what's your name?")
    print(f"Neko: {response}")
    assert response is not None and len(response) > 0
    
    print("[PASS] Basic chat test passed\n")


def test_owner_personalization():
    """Test personalization with owner name"""
    print("\n=== Test 2: Owner Personalization ===")
    agent = NekoAgent(owner_name="Alice")
    
    # Check system prompt contains owner name
    system_prompt = agent.get_system_prompt()
    print(f"System prompt preview: {system_prompt[:100]}...")
    assert "Alice" in system_prompt
    
    # Change owner name
    agent.set_owner_name("Bob")
    system_prompt = agent.get_system_prompt()
    assert "Bob" in system_prompt
    assert "Alice" not in system_prompt
    
    print("[PASS] Personalization test passed\n")


def test_history_management():
    """Test conversation history trimming"""
    print("\n=== Test 3: History Management ===")
    agent = NekoAgent()
    
    # Add 8 turns (16 messages)
    for i in range(8):
        response, emotion = agent.chat(f"Message {i}")
    
    history = agent.get_history()
    # Should have: 1 system + 10 messages (5 turns max)
    non_system = [m for m in history if m["role"] != "system"]
    print(f"History size: {len(history)} total, {len(non_system)} non-system")
    assert len(non_system) <= 10, f"Expected ≤10 messages, got {len(non_system)}"
    
    print("[PASS] History management test passed\n")


def test_soft_clear_recovery():
    """Test soft clear and answer detection"""
    print("\n=== Test 4: Soft Clear Recovery ===")
    agent = NekoAgent(silence_timeout=2)
    
    # Simulate conversation
    response, emotion = agent.chat("How are you?")
    print("User: How are you?")
    
    # Wait for silence timeout
    time.sleep(2.5)
    timeout_triggered = agent.check_silence_timeout()
    print(f"Silence timeout triggered: {timeout_triggered}")
    assert timeout_triggered
    
    # User answers (should detect as likely answer)
    is_answer = agent._is_likely_answer("I'm good")
    print(f"'I'm good' detected as answer: {is_answer}")
    assert is_answer
    
    # Chat with answer - should restore context
    response, emotion = agent.chat("I'm good")
    print(f"User: I'm good")
    print(f"Neko: {response}")
    
    print("[PASS] Soft clear recovery test passed\n")


def test_answer_detection():
    """Test _is_likely_answer heuristic"""
    print("\n=== Test 5: Answer Detection ===")
    agent = NekoAgent()
    
    test_cases = [
        ("I'm fine", True),
        ("yes", True),
        ("no", True),
        ("I am happy", True),
        ("feeling good", True),
        ("sure", True),
        ("hello there", False),
        ("what time is it", False),
        ("", False),
        ("   ", False),
    ]
    
    for text, expected in test_cases:
        result = agent._is_likely_answer(text)
        status = "[PASS]" if result == expected else "[FAIL]"
        print(f"{status} '{text}' -> {result} (expected {expected})")
        assert result == expected, f"Failed for '{text}'"
    
    print("[PASS] Answer detection test passed\n")


def test_history_clear():
    """Test manual history clearing"""
    print("\n=== Test 6: History Clear ===")
    agent = NekoAgent()
    
    # Build some history
    response, emotion = agent.chat("hello")
    response, emotion = agent.chat("how are you")
    
    history_before = len(agent.get_history())
    print(f"History before clear: {history_before} messages")
    
    # Clear history
    agent.clear_history(reason="test")
    
    history_after = agent.get_history()
    non_system_after = [m for m in history_after if m["role"] != "system"]
    print(f"History after clear: {len(history_after)} messages ({len(non_system_after)} non-system)")
    
    # Should only have system message
    assert len(non_system_after) == 0
    
    print("[PASS] History clear test passed\n")


def test_llm_integration():
    """Test actual LLM chat (if available)"""
    print("\n=== Test 7: LLM Integration ===")
    agent = NekoAgent(owner_name="TestUser")
    
    # Try a conversation that requires LLM
    response, emotion = agent.chat("I'm feeling a bit anxious today")
    print(f"User: I'm feeling a bit anxious today")
    print(f"Neko: {response}")
    print(f"Emotion: {emotion}")
    
    # LLM response should be more than fallback
    llm_available = False
    if "That's interesting, nya~!" not in response:
        print("[PASS] LLM responded (not fallback)")
        llm_available = True
        # Check if emotion was extracted
        if emotion is not None and 'emotion' in emotion:
            print(f"[PASS] Emotion extracted: {emotion.get('emotion')}")
    else:
        print("[WARN] Using fallback response (LLM not available)")
    
    print("[PASS] LLM integration test passed\n")
    return llm_available


def test_emotion_system_context():
    """Test emotion tagging instruction"""
    print("\n=== Test 8: Emotion System Context ===")
    agent = NekoAgent()
    
    emotion_context = agent._get_emotion_system_context()
    print(f"Emotion context preview: {emotion_context[:150]}...")
    
    # Check required emotions are listed
    required_emotions = ["neutral", "happy", "calm", "sad"]
    for emotion in required_emotions:
        assert emotion in emotion_context
    
    # Check JSON example is present
    assert "emotion" in emotion_context
    assert "JSON" in emotion_context
    
    print("[PASS] Emotion system context test passed\n")


def test_emotion_extraction():
    """Test emotion extraction from LLM responses"""
    print("\n=== Test 9: Emotion Extraction ===")
    agent = NekoAgent()
    
    # Test 1: Response with valid emotion JSON
    print("\nSubtest 1: Valid emotion JSON")
    def mock_llm_with_emotion():
        return "Hello! I'm so happy to see you! {\"emotion\":\"happy\",\"emoji\":\"😊\"}"
    
    agent._call_llm = mock_llm_with_emotion
    response, emotion = agent.chat("test")
    
    print(f"  Response: {response}")
    print(f"  Emotion: {emotion}")
    
    assert "{" not in response, "Response should not contain JSON braces"
    assert "Hello! I'm so happy to see you!" in response
    assert emotion is not None, "Emotion should be extracted"
    assert emotion.get('emotion') == 'happy'
    assert emotion.get('emoji') == '😊'
    print("  [PASS] Valid emotion JSON extracted correctly")
    
    # Test 2: Response without emotion JSON
    print("\nSubtest 2: No emotion JSON")
    agent.clear_history()
    def mock_llm_no_emotion():
        return "Just a simple response"
    
    agent._call_llm = mock_llm_no_emotion
    response, emotion = agent.chat("test")
    
    print(f"  Response: {response}")
    print(f"  Emotion: {emotion}")
    
    assert response == "Just a simple response"
    assert emotion is None, "Emotion should be None when not present"
    print("  [PASS] No emotion JSON handled correctly")
    
    # Test 3: Response with markdown formatting
    print("\nSubtest 3: Markdown removal")
    agent.clear_history()
    def mock_llm_markdown():
        return "**Bold** text with `code` and [link](url) {\"emotion\":\"neutral\"}"
    
    agent._call_llm = mock_llm_markdown
    response, emotion = agent.chat("test")
    
    print(f"  Response: {response}")
    print(f"  Emotion: {emotion}")
    
    assert "**" not in response, "Should remove bold markers"
    assert "`" not in response, "Should remove code markers"
    assert "[" not in response and "]" not in response, "Should remove link syntax"
    assert "Bold text with code and link" in response
    assert emotion.get('emotion') == 'neutral'
    print("  [PASS] Markdown removed correctly")
    
    # Test 4: Invalid emotion JSON (should be ignored)
    print("\nSubtest 4: Invalid emotion JSON")
    agent.clear_history()
    def mock_llm_invalid_json():
        return "Response with broken JSON {invalid}"
    
    agent._call_llm = mock_llm_invalid_json
    response, emotion = agent.chat("test")
    
    print(f"  Response: {response}")
    print(f"  Emotion: {emotion}")
    
    assert emotion is None, "Invalid JSON should result in None emotion"
    print("  [PASS] Invalid JSON handled gracefully")
    
    # Test 5: Emotion JSON without required 'emotion' key
    print("\nSubtest 5: JSON without emotion key")
    agent.clear_history()
    def mock_llm_no_emotion_key():
        return "Response {\"emoji\":\"😊\",\"other\":\"data\"}"
    
    agent._call_llm = mock_llm_no_emotion_key
    response, emotion = agent.chat("test")
    
    print(f"  Response: {response}")
    print(f"  Emotion: {emotion}")
    
    assert emotion is None, "JSON without 'emotion' key should be ignored"
    print("  [PASS] Missing emotion key handled correctly")
    
    # Test 6: Multiple spaces and newlines collapse
    print("\nSubtest 6: Whitespace normalization")
    agent.clear_history()
    def mock_llm_whitespace():
        return "Multiple    spaces\n\nand\n\nnewlines {\"emotion\":\"calm\"}"
    
    agent._call_llm = mock_llm_whitespace
    response, emotion = agent.chat("test")
    
    print(f"  Response: {response}")
    print(f"  Emotion: {emotion}")
    
    assert "    " not in response, "Multiple spaces should be collapsed"
    assert "\n" not in response, "Newlines should be replaced with space"
    assert "Multiple spaces and newlines" in response
    print("  [PASS] Whitespace normalized correctly")
    
    print("\n[PASS] All emotion extraction tests passed\n")


def test_weather_tool():
    """Test weather tool via LLM conversation"""
    print("\n=== Test 10: Weather Tool (LLM Conversation) ===")
    agent = NekoAgent(owner_name="TestUser")
    
    # Verify tool is registered
    assert agent._tool_manager.has_tools()
    tool_names = agent._tool_manager.get_tool_names()
    print(f"[OK] Registered tools: {tool_names}")
    assert "get_weather" in tool_names
    
    # Ask about current location weather
    print("User: What's the weather like?")
    response, emotion = agent.chat("User: What's the weather like?")
    print(f"Neko: {response}")
    print(f"Emotion: {emotion}")
    
    assert response is not None and len(response) > 0
    print("\n[PASS] Weather tool conversation test passed\n")


def test_location_tool():
    """Test location tool via LLM conversation"""
    print("\n=== Test 11: Location Tool (LLM Conversation) ===")
    agent = NekoAgent(owner_name="TestUser")
    
    # Verify tool is registered
    assert agent._tool_manager.has_tools()
    tool_names = agent._tool_manager.get_tool_names()
    print(f"[OK] Registered tools: {tool_names}")
    assert "get_location" in tool_names
    
    # Test: Ask about current location
    print("\n--- Location Query ---")
    print("User: Where am I now?")
    response, emotion = agent.chat("Where am I now?")
    print(f"Neko: {response}")
    print(f"Emotion: {emotion}")
    
    # LLM should call tool and provide location info
    assert response is not None and len(response) > 0
    is_location_response = any(keyword in response.lower() for keyword in 
                               ['hong kong', 'location', 'where', '香港', '位置', '在'])
    if is_location_response:
        print("  [PASS] LLM provided location-related response")
    else:
        print("  [WARN] LLM may not have called location tool")
    
    print("\n[PASS] Location tool conversation test passed\n")


def run_all_tests():
    """Run all test cases"""
    print("=" * 60)
    print("NEKO AGENT TEST SUITE")
    print("=" * 60)
    
    try:
        test_basic_chat()
        test_owner_personalization()
        test_history_management()
        test_soft_clear_recovery()
        test_answer_detection()
        test_history_clear()
        llm_available = test_llm_integration()
        test_emotion_system_context()
        test_emotion_extraction()
        test_weather_tool()
        test_location_tool()
        
        print("=" * 60)
        print("🎉 ALL TESTS PASSED!")
        if not llm_available:
            print("[WARN]  WARNING: LLM was not available, fallback responses used")
            print("    Check config.ini, ai_config.ini, and .env files")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n[FAIL] UNEXPECTED ERROR: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()
