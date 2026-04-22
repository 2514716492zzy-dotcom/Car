"""
Test suite for Neko Agent Tools
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from modules.neko_agent.tools import ToolManager, WeatherAPI


def test_weather_tool():
    """Test weather tool functionality"""
    print("\n" + "=" * 60)
    print("TEST 1: Weather Tool")
    print("=" * 60)
    
    tool = WeatherAPI()
    
    # Test tool properties
    print(f"\nTool name: {tool.name}")
    print(f"Description: {tool.description}")
    
    # Test LangChain's invoke method
    print("\n--- Test: Current Weather (via invoke) ---")
    result = tool.invoke({"city_name": "Beijing", "forecast": False})
    print(result)
    
    # Test forecast
    print("\n--- Test: Forecast (via invoke) ---")
    result = tool.invoke({"city_name": "Shanghai", "forecast": True})
    print(result)
    
    print("\n✓ Weather tool test passed\n")
    return True


def test_tool_manager():
    """Test tool manager functionality"""
    print("=" * 60)
    print("TEST 2: Tool Manager")
    print("=" * 60)
    
    manager = ToolManager()
    
    # Register weather tool
    weather_tool = WeatherAPI()
    manager.register_tool(weather_tool)
    
    # Test tool registration
    print(f"\nRegistered tools: {manager.get_tool_names()}")
    print(f"Has tools: {manager.has_tools()}")
    
    # Test tool definitions
    definitions = manager.get_tool_definitions()
    print(f"\nTool definitions count: {len(definitions)}")
    if definitions:
        print(f"First tool: {definitions[0]['name']}")
    
    # Test tool execution
    print("\n--- Test: Execute via Manager ---")
    result = manager.execute_tool(
        "get_weather",
        city_name="Guangzhou",
        forecast=False
    )
    print(result)
    
    # Test unknown tool
    print("\n--- Test: Unknown Tool ---")
    result = manager.execute_tool("unknown_tool")
    print(result)
    
    print("\n✓ Tool manager test passed\n")
    return True


def run_all_tests():
    """Run all tool tests"""
    print("\n" + "=" * 60)
    print("NEKO AGENT TOOLS TEST SUITE")
    print("=" * 60)
    
    try:
        if not test_weather_tool():
            return False
        
        if not test_tool_manager():
            return False
        
        print("=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n✗ Test Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
