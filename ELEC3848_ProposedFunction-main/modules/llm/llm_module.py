import os
from typing import Dict, Any, Optional
from pathlib import Path
import configparser
from modules.common_tools import load_env_variables, load_config


class LLMModule:
    """
    LLM Module for unified chat model calls
    Supports OpenAI-compatible API endpoints
    """

    def __init__(self):
        # Load configurations using common tools
        load_env_variables()
        self.config = load_config()
        
        # Load ai_config separately
        try:
            ai_config_path = Path("ai_config.ini")
            if not ai_config_path.exists():
                raise FileNotFoundError("ai_config.ini not found")
            self.ai_config = configparser.ConfigParser()
            self.ai_config.read(ai_config_path, encoding="utf-8")
        except Exception as e:
            print(f"AI config loading failed: {str(e)}")
            self.ai_config = configparser.ConfigParser()
        
        self.clients = {}  # Cache client instances
        
        # Load defaults from config.ini
        self.default_model = self.config["llm"]["default_model"]
        self.default_temperature = float(self.config["llm"]["default_temperature"])

    def _get_openai_client(self, model_name: str) -> Any:
        """Get or create OpenAI-compatible client"""
        if model_name in self.clients:
            return self.clients[model_name]

        if not self.ai_config[model_name]:
            raise ValueError(f"Model config not found: {model_name}")

        # Get API key
        api_key = os.getenv(self.ai_config[model_name]["api_key_env"])
        if not api_key:
            raise ValueError(
                f"API key not set: {self.ai_config[model_name]['api_key_env']}"
            )

        # Get base URL
        base_url = os.getenv(self.ai_config[model_name]["base_url_env"])
        if not base_url:
            base_url = self.ai_config[model_name].get("default_url")
            if not base_url:
                raise ValueError(
                    f"Base URL not set: {self.ai_config[model_name]['base_url_env']}"
                )

        # Remove trailing slash
        if base_url and base_url.endswith("/"):
            base_url = base_url.rstrip("/")

        # Create and cache client
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=None)
        self.clients[model_name] = client
        return client

    def call_llm(
        self,
        prompt: str = None,
        messages: list = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        response_format: Optional[Dict[str, str]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        tools: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Call LLM for chat completion
        
        Args:
            prompt: User input text (optional if messages provided)
            messages: Chat messages array (optional if prompt provided)
            model_name: Model config name (optional, uses default from config.ini)
            temperature: Sampling temperature (optional, uses default from config.ini)
            response_format: Response format specification (optional)
            extra_body: Additional parameters (optional)
            tools: Tool definitions for function calling (optional)
            
        Returns:
            Dict with 'status', 'response', and optional 'tool_calls' keys
        """
        try:
            # Use defaults if not specified
            if model_name is None:
                model_name = self.default_model
            
            if temperature is None:
                temperature = self.default_temperature
            
            # Build messages array
            if messages is None:
                if not prompt or not isinstance(prompt, str):
                    return {
                        "status": "fail",
                        "response": "Either prompt or messages must be provided"
                    }
                messages = [{"role": "user", "content": prompt}]
            
            # Validate input
            if not messages or not isinstance(messages, list):
                return {
                    "status": "fail",
                    "response": "Invalid messages format"
                }

            # Check model config
            if model_name not in self.ai_config:
                return {
                    "status": "fail",
                    "response": f"Model not configured: {model_name}"
                }

            try:
                client = self._get_openai_client(model_name)
                
                # Get actual model name from config
                actual_model_name = self.ai_config[model_name]["model"]
                
                # Prepare chat request
                params = {
                    "model": actual_model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": False,
                    "extra_body": extra_body,
                }

                if response_format:
                    params["response_format"] = response_format
                
                # Add tools if provided
                if tools:
                    params["tools"] = tools

                response = client.chat.completions.create(**params)
                message = response.choices[0].message
                result_content = message.content
                
                # Check for tool calls
                result = {
                    "status": "success",
                    "response": result_content
                }
                
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    import json
                    tool_calls = []
                    for tc in message.tool_calls:
                        tool_calls.append({
                            "id": tc.id,
                            "name": tc.function.name,
                            "input": json.loads(tc.function.arguments)
                        })
                    result["tool_calls"] = tool_calls
                
                return result

            except Exception as e:
                return {
                    "status": "fail",
                    "response": f"API call failed: {str(e)}"
                }

        except Exception as e:
            return {
                "status": "fail",
                "response": f"Module error: {str(e)}"
            }