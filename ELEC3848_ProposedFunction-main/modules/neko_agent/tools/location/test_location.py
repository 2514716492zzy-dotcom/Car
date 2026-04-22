"""
Test Location Tool
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from modules.neko_agent.tools.location import LocationAPI


def test_default_location():
    """Test default location (no API)"""
    print("\n=== Test 1: Default Location ===")
    location_tool = LocationAPI(default_location="Hong Kong", use_real_api=False)
    
    result = location_tool.get_current_location()
    print(f"Result: {result}")
    
    assert "Hong Kong" in result
    assert "China" in result
    print("[PASS] Default location test passed\n")


def test_real_api_location():
    """Test real API location (optional, may fail without internet)"""
    print("\n=== Test 2: Real API Location (Optional) ===")
    location_tool = LocationAPI(use_real_api=True)
    
    result = location_tool.get_current_location()
    print(f"Result: {result}")
    
    # Should contain location info or fallback to default
    assert "Location" in result or "Hong Kong" in result
    print("[PASS] Real API location test passed\n")


def test_tool_invoke():
    """Test LangChain invoke method"""
    print("\n=== Test 3: Tool Invoke Method ===")
    location_tool = LocationAPI(default_location="Tokyo")
    
    result = location_tool.invoke({})
    print(f"Result: {result}")
    
    assert "Tokyo" in result
    print("[PASS] Tool invoke test passed\n")


if __name__ == "__main__":
    print("=" * 60)
    print("LOCATION TOOL TEST SUITE")
    print("=" * 60)
    
    try:
        test_default_location()
        test_real_api_location()
        test_tool_invoke()
        
        print("=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        raise
