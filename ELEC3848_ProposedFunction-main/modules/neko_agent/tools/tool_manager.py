"""
Tool Manager
============

Manages multiple tools for LLM function calling.
"""

from typing import List, Dict, Any
from langchain_core.tools import BaseTool


class ToolManager:
    """
    Manages collection of tools for LLM function calling
    
    Handles:
    - Tool registration
    - Schema generation for LLM
    - Tool execution routing
    - Auto-discovery and initialization
    """
    
    def __init__(self, auto_init: bool = True):
        """
        Initialize tool manager
        
        Args:
            auto_init: Automatically discover and register available tools
        """
        self._tools: Dict[str, BaseTool] = {}
        
        if auto_init:
            self.initialize_tools()
    
    def initialize_tools(self):
        """
        Discover and register available tools
        
        Automatically imports and registers all available tool modules.
        Silently skips tools that fail to initialize.
        """
        try:
            from modules.neko_agent.tools.weather import WeatherAPI
            weather_tool = WeatherAPI()
            self.register_tool(weather_tool)
        except Exception as e:
            print(f"⚠️ Failed to initialize weather tool: {e}")
        
        try:
            from modules.neko_agent.tools.location import LocationAPI
            location_tool = LocationAPI(default_location="Hong Kong")
            self.register_tool(location_tool)
        except Exception as e:
            print(f"⚠️ Failed to initialize location tool: {e}")
    
    def register_tool(self, tool: BaseTool):
        """
        Register a tool
        
        Args:
            tool: Tool instance implementing BaseTool interface
        """
        self._tools[tool.name] = tool
        print(f"[OK] Registered tool: {tool.name}")
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Get all tool definitions for LLM function calling
        
        Returns:
            List of tool definition dicts (OpenAI format)
        """
        definitions = []
        for tool in self._tools.values():
            # Use tool's schema if available (from LangChain)
            try:
                tool_schema = self._convert_tool_to_openai_format(tool)
                definitions.append(tool_schema)
            except Exception as e:
                print(f"⚠️ Failed to convert tool {tool.name}: {e}")
        return definitions
    
    def _convert_tool_to_openai_format(self, tool: BaseTool) -> Dict[str, Any]:
        """
        Convert LangChain BaseTool to OpenAI function format
        
        Args:
            tool: BaseTool instance
            
        Returns:
            OpenAI function schema dict
        """
        # Get tool's input schema from args_schema if available
        parameters = {"type": "object", "properties": {}, "required": []}
        
        # Map common tool parameters based on tool name
        if tool.name == "get_weather":
            parameters = {
                "type": "object",
                "properties": {
                    "city_name": {
                        "type": "string",
                        "description": (
                            "City name in any language (English, Chinese, etc.). "
                            "Examples: 'Beijing', '北京', 'Hong Kong', '香港', 'New York', 'Tokyo'. "
                            "If user asks 'here' or 'my location', use the current location from context."
                        )
                    },
                    "forecast": {
                        "type": "boolean",
                        "description": (
                            "Set to false for current/real-time weather (default). "
                            "Set to true for 3-day weather forecast. "
                            "Use false when user asks about: current weather, temperature now, how's the weather. "
                            "Use true when user asks about: forecast, tomorrow, next few days, will it rain."
                        )
                    }
                },
                "required": ["city_name"]
            }
        elif tool.name == "get_location":
            parameters = {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional query (not used, exists for compatibility)"
                    }
                },
                "required": []
            }
        
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": parameters
            }
        }
    
    def execute_tool(self, tool_name: str, **kwargs) -> str:
        """
        Execute a tool by name
        
        Args:
            tool_name: Name of tool to execute
            **kwargs: Tool-specific parameters
            
        Returns:
            Tool execution result as string
        """
        tool = self._tools.get(tool_name)
        
        if tool is None:
            return f"Error: Unknown tool '{tool_name}'"
        
        try:
            # Use LangChain's invoke method
            return tool.invoke(kwargs)
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"
    
    def has_tools(self) -> bool:
        """Check if any tools are registered"""
        return len(self._tools) > 0
    
    def get_tool_names(self) -> List[str]:
        """Get list of registered tool names"""
        return list(self._tools.keys())
    
    def handle_tool_calls(self, tool_calls: list, history: list) -> list:
        """
        Execute tool calls and add results to conversation history
        
        Args:
            tool_calls: List of tool call dicts with 'id', 'name', 'input'
            history: Conversation history (will be modified in place)
            
        Returns:
            Updated history with tool calls and results added
        """
        for tool_call in tool_calls:
            tool_id = tool_call.get('id', '')
            tool_name = tool_call.get('name')
            tool_input = tool_call.get('input', {})
            
            print(f"🔧 Calling tool: {tool_name} with {tool_input}")
            
            # Execute tool
            tool_result = self.execute_tool(tool_name, **tool_input)
            
            print(f"✓ Tool result: {tool_result[:100]}...")
            
            # Add assistant's tool call to history
            history.append({
                'role': 'assistant',
                'content': None,
                'tool_calls': [{
                    'id': tool_id,
                    'type': 'function',
                    'function': {
                        'name': tool_name,
                        'arguments': str(tool_input)
                    }
                }]
            })
            
            # Add tool result to history
            history.append({
                'role': 'tool',
                'tool_call_id': tool_id,
                'content': tool_result
            })
        
        return history
