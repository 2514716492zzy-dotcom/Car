"""
Weather Tool for LLM Function Calling
"""

import os
import requests
from typing import Optional, Dict, Any
from langchain_core.tools import BaseTool
from pydantic import Field
from dotenv import load_dotenv


class WeatherAPI(BaseTool):
    """
    Weather query tool for LLM
    
    Supports current weather and 3-day forecast via QWeather API
    """
    
    name: str = "get_weather"
    description: str = (
        "Get real-time weather information or 3-day forecast for any city worldwide. "
        "Use this tool when user asks about: weather, temperature, climate, humidity, "
        "pressure, wind, visibility, precipitation, forecast, or any weather-related questions. "
        "Examples: 'What's the weather?', 'How's the temperature?', 'Will it rain?', "
        "'Weather in Beijing', 'Is it hot there?', 'Current weather conditions'. "
        "Returns comprehensive weather data including temperature, humidity, pressure, wind, etc."
    )
    
    # API configuration
    api_key: str = Field(default="", exclude=True)
    api_host: str = Field(default="", exclude=True)
    geo_api: str = Field(default="", exclude=True)
    weather_api: str = Field(default="", exclude=True)
    headers: Dict[str, str] = Field(default_factory=dict, exclude=True)
    
    def __init__(self, api_key: Optional[str] = None, api_host: Optional[str] = None, **kwargs):
        """
        Initialize weather tool
        
        Args:
            api_key: API key (optional, reads from .env)
            api_host: API host (optional, reads from .env)
        """
        # Load environment variables
        load_dotenv()
        
        _api_key = api_key or os.getenv('QWEATHER_API_KEY', '')
        _api_host = api_host or os.getenv('QWEATHER_API_HOST', '')
        
        if not _api_key or not _api_host:
            raise ValueError("QWeather API key and host must be configured in .env file")
        
        # Initialize parent with all fields
        super().__init__(
            api_key=_api_key, 
            api_host=_api_host,
            geo_api=f"https://{_api_host}/geo/v2/city",
            weather_api=f"https://{_api_host}/v7/weather",
            headers={'X-QW-Api-Key': _api_key},
            **kwargs
        )
    
    def _run(self, city_name: str, forecast: bool = False) -> str:
        """Execute weather query (implements BaseTool._run)"""
        try:
            result = self.get_weather_by_city(city_name, forecast)
            return result or f"Unable to get weather for {city_name}"
        except Exception as e:
            return f"Weather service error: {str(e)}"
    
    async def _arun(self, city_name: str, forecast: bool = False) -> str:
        """Async execution (not implemented)"""
        return self._run(city_name, forecast)
    
    # ==================== Internal API Methods ====================
    
    def _make_request(self, url: str, params: Dict[str, Any]) -> Optional[Dict]:
        """
        Send API request
        
        Args:
            url: Request URL
            params: Request parameters
            
        Returns:
            API response data or None if failed
        """
        try:
            response = requests.get(
                url, 
                params=params, 
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') != '200':
                return None
            
            return data
            
        except Exception:
            return None
    
    def search_city(self, city_name: str) -> Optional[Dict]:
        """
        Search city and get LocationID
        
        Args:
            city_name: City name (supports Chinese/Pinyin/English)
            
        Returns:
            City info dict with id, name, lat, lon, etc. or None if not found
        """
        params = {
            'location': city_name,
            'number': 1,
            'lang': 'en'
        }
        
        url = f"{self.geo_api}/lookup"
        data = self._make_request(url, params)
        
        if data and data.get('location'):
            return data['location'][0]
        
        return None
    
    def get_weather_now(self, location: str) -> Optional[Dict]:
        """
        Get current weather
        
        Args:
            location: LocationID or "longitude,latitude"
            
        Returns:
            Current weather data dict or None if failed
        """
        params = {
            'location': location,
            'lang': 'en',
            'unit': 'm'
        }
        
        url = f"{self.weather_api}/now"
        data = self._make_request(url, params)
        
        if data and data.get('now'):
            return data['now']
        
        return None
    
    def get_weather_forecast_3d(self, location: str) -> Optional[list]:
        """
        Get 3-day weather forecast
        
        Args:
            location: LocationID or "longitude,latitude"
            
        Returns:
            List of daily weather data or None if failed
        """
        params = {
            'location': location,
            'lang': 'en',
            'unit': 'm'
        }
        
        url = f"{self.weather_api}/3d"
        data = self._make_request(url, params)
        
        if data and data.get('daily'):
            return data['daily']
        
        return None
    
    def get_weather_by_city(self, city_name: str, forecast: bool = False) -> Optional[str]:
        """
        Get weather information by city name (LLM-friendly method)
        
        Args:
            city_name: City name
            forecast: If True, return 3-day forecast; if False, return current weather
            
        Returns:
            Formatted weather information text or None if failed
        """
        city = self.search_city(city_name)
        if not city:
            return f"City not found: {city_name}"
        
        location_id = city['id']
        city_full_name = f"{city['adm1']} {city['name']}"
        
        if not forecast:
            # Current weather
            weather = self.get_weather_now(location_id)
            if not weather:
                return f"Unable to get weather for {city_full_name}"
            
            result = f"{city_full_name} Current Weather:\n"
            result += f"Observed Time: {weather['obsTime']}\n"
            result += f"Temperature: {weather['temp']}°C (feels like {weather['feelsLike']}°C)\n"
            result += f"Condition: {weather['text']} (icon: {weather['icon']})\n"
            result += f"Wind: {weather['windDir']} ({weather['wind360']}°) {weather['windSpeed']}km/h (Scale {weather['windScale']})\n"
            result += f"Humidity: {weather['humidity']}%\n"
            result += f"Pressure: {weather['pressure']}hPa\n"
            result += f"Visibility: {weather['vis']}km\n"
            result += f"Cloud Cover: {weather['cloud']}%\n"
            result += f"Precipitation: {weather['precip']}mm\n"
            result += f"Dew Point: {weather['dew']}°C"
        else:
            # 3-day forecast
            forecast_data = self.get_weather_forecast_3d(location_id)
            if not forecast_data:
                return f"Unable to get forecast for {city_full_name}"
            
            result = f"{city_full_name} 3-Day Forecast:\n"
            for day in forecast_data:
                result += f"\n{day['fxDate']}:\n"
                result += f"  Day: {day['textDay']}, {day['tempMax']}°C\n"
                result += f"  Night: {day['textNight']}, {day['tempMin']}°C\n"
                result += f"  Wind: {day['windDirDay']}"
        
        return result
