"""
Location Tool for LLM Function Calling
Provides current location information (simulated or from IP-based geolocation)
"""

import os
import requests
from typing import Optional
from langchain_core.tools import BaseTool
from pydantic import Field
from dotenv import load_dotenv


class LocationAPI(BaseTool):
    """
    Location query tool for LLM
    
    Returns current location (city/country) using IP-based geolocation
    """
    
    name: str = "get_location"
    description: str = (
        "Get current location (city and country). "
        "Use this when user asks 'where am I', 'what's my location', "
        "'current city', or similar location queries."
    )
    
    # API configuration
    default_location: str = Field(default="Hong Kong", exclude=True)
    use_real_api: bool = Field(default=False, exclude=True)
    
    def __init__(self, default_location: str = "Hong Kong", use_real_api: bool = False, **kwargs):
        """
        Initialize location tool
        
        Args:
            default_location: Default location to return (default: "Hong Kong")
            use_real_api: Use real IP geolocation API instead of default (default: False)
        """
        load_dotenv()
        
        super().__init__(
            default_location=default_location,
            use_real_api=use_real_api,
            **kwargs
        )
    
    def _run(self, query: Optional[str] = None) -> str:
        """
        Execute location query (implements BaseTool._run)
        
        Args:
            query: Optional query string (not used, for compatibility)
            
        Returns:
            Location information string
        """
        return self.get_current_location()
    
    async def _arun(self, query: Optional[str] = None) -> str:
        """Async version - delegates to sync implementation"""
        return self._run(query)
    
    def get_current_location(self) -> str:
        """
        Get current location information
        
        Returns:
            Formatted location string with city and country
        """
        if self.use_real_api:
            return self._get_location_from_api()
        else:
            return self._get_default_location()
    
    def _get_default_location(self) -> str:
        """Return configured default location"""
        return f"Current Location: {self.default_location}\nCountry: {self._get_country_from_city(self.default_location)}"
    
    def _get_location_from_api(self) -> str:
        """
        Get location from IP-based geolocation API
        
        Uses ipapi.co free API (no key required)
        Fallback to default location on error
        """
        try:
            # Use ipapi.co free tier (no authentication required)
            response = requests.get('https://ipapi.co/json/', timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                city = data.get('city', 'Unknown')
                country = data.get('country_name', 'Unknown')
                region = data.get('region', '')
                
                result = f"Current Location: {city}"
                if region and region != city:
                    result += f", {region}"
                result += f"\nCountry: {country}"
                
                # Add additional info
                if data.get('timezone'):
                    result += f"\nTimezone: {data.get('timezone')}"
                if data.get('postal'):
                    result += f"\nPostal Code: {data.get('postal')}"
                
                return result
            else:
                return self._get_default_location()
                
        except Exception as e:
            print(f"⚠️ Location API error: {e}, using default location")
            return self._get_default_location()
    
    def _get_country_from_city(self, city: str) -> str:
        """Simple mapping of common cities to countries"""
        city_map = {
            'Hong Kong': 'China (SAR)',
            'Beijing': 'China',
            'Shanghai': 'China',
            'Tokyo': 'Japan',
            'New York': 'United States',
            'London': 'United Kingdom',
            'Paris': 'France',
            'Sydney': 'Australia',
            'Singapore': 'Singapore',
            'Seoul': 'South Korea',
        }
        return city_map.get(city, 'Unknown')
