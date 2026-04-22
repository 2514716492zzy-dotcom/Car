"""
LLM Module Test - Simple Chat
Tests basic chat functionality of simplified LLM module
"""

import sys
from pathlib import Path
import time

# Add main directory to system path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.llm.llm_module import LLMModule


def test_simple_chat():
    """Test basic chat functionality"""
    print("=" * 50)
    print("LLM Module - Simple Chat Test")
    print("=" * 50)
    
    # Initialize LLM module
    llm = LLMModule()
    print("✓ Module initialized")
    print(f"✓ Default model: {llm.default_model}")
    print(f"✓ Default temperature: {llm.default_temperature}\n")
    
    # Test case 1: Simple Q&A with defaults
    print("Test 1: Default configuration")
    print("-" * 50)
    prompt = "Explain AI in one sentence"
    print(f"Prompt: {prompt}")
    
    # Start timer
    start_time = time.perf_counter()
    
    # Call LLM using defaults from config.ini
    result = llm.call_llm(prompt=prompt)
    
    # Calculate response time
    elapsed_time = time.perf_counter() - start_time
    
    if result["status"] == "success":
        print(f"Response: {result['response']}")
        print(f"⏱️  Time: {elapsed_time:.3f}s")
        print("✓ Test passed\n")
    else:
        print(f"✗ Test failed: {result['response']}")
        print(f"⏱️  Time: {elapsed_time:.3f}s\n")
    


if __name__ == "__main__":
    # Run simple chat test
    test_simple_chat()