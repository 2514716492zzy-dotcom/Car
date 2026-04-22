"""
Test suite for QWeather API
Run from project root: python modules/weather/test_weather.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from modules.neko_agent.tools.weather import WeatherAPI


def test_city_search():
    """Test city search"""
    print("\n" + "=" * 60)
    print("TEST 1: City Search")
    print("=" * 60)
    
    api = WeatherAPI()
    
    # Test Beijing
    print("\n✓ Searching: Beijing")
    city = api.search_city("北京")
    if city:
        print(f"  City: {city['name']}")
        print(f"  Location ID: {city['id']}")
        print(f"  Coordinates: {city['lat']}, {city['lon']}")
        print(f"  Region: {city['country']} > {city['adm1']} > {city['adm2']}")
    else:
        print("  ✗ Search failed")
        return False
    
    # Test Hong Kong
    print("\n✓ Searching: Hong Kong")
    city = api.search_city("香港")
    if city:
        print(f"  City: {city['name']}")
        print(f"  Location ID: {city['id']}")
    else:
        print("  ✗ Search failed")
    
    print("\n✓ City search test passed\n")
    return True


def test_weather_now():
    """Test current weather"""
    print("=" * 60)
    print("TEST 2: Current Weather")
    print("=" * 60)
    
    api = WeatherAPI()
    
    # Search city
    city = api.search_city("北京")
    if not city:
        print("✗ City search failed")
        return False
    
    # Get current weather
    print(f"\n✓ Getting current weather for {city['name']}...")
    weather = api.get_weather_now(city['id'])
    
    if weather:
        print(f"  Temperature: {weather['temp']}°C")
        print(f"  Feels like: {weather['feelsLike']}°C")
        print(f"  Condition: {weather['text']}")
        print(f"  Wind: {weather['windDir']} Scale {weather['windScale']}")
        print(f"  Humidity: {weather['humidity']}%")
        print(f"  Pressure: {weather['pressure']} hPa")
        print(f"  Visibility: {weather['vis']} km")
        print(f"  Observed: {weather['obsTime']}")
    else:
        print("  ✗ Weather query failed")
        return False
    
    print("\n✓ Current weather test passed\n")
    return True


def test_weather_forecast():
    """Test weather forecast"""
    print("=" * 60)
    print("TEST 3: Weather Forecast")
    print("=" * 60)
    
    api = WeatherAPI()
    
    # Search city
    city = api.search_city("上海")
    if not city:
        print("✗ City search failed")
        return False
    
    # Get 3-day forecast
    print(f"\n✓ Getting 3-day forecast for {city['name']}...")
    forecast = api.get_weather_forecast_3d(city['id'])
    
    if forecast:
        for i, day in enumerate(forecast, 1):
            print(f"\n  Day {i} ({day['fxDate']}):")
            print(f"    Daytime: {day['textDay']}, {day['tempMax']}°C")
            print(f"    Nighttime: {day['textNight']}, {day['tempMin']}°C")
            print(f"    Wind: {day['windDirDay']}")
    else:
        print("  ✗ Forecast query failed")
        return False
    
    print("\n✓ Weather forecast test passed\n")
    return True


def test_weather_by_city():
    """Test convenience method for LLM"""
    print("=" * 60)
    print("TEST 4: Weather By City Name (LLM Tool)")
    print("=" * 60)
    
    api = WeatherAPI()
    
    # Test current weather
    print("\n✓ Test: get_weather_by_city('广州', forecast=False)")
    result = api.get_weather_by_city("广州", forecast=False)
    if result:
        print(result)
    else:
        print("  ✗ Query failed")
        return False
    
    # Test 3-day forecast
    print("\n✓ Test: get_weather_by_city('深圳', forecast=True)")
    result = api.get_weather_by_city("深圳", forecast=True)
    if result:
        print(result)
    else:
        print("  ✗ Query failed")
    
    print("\n✓ Convenience method test passed\n")
    return True


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("QWEATHER API TEST SUITE")
    print("=" * 60)
    
    try:
        # Run tests sequentially
        if not test_city_search():
            return False
        
        if not test_weather_now():
            return False
        
        if not test_weather_forecast():
            return False
        
        if not test_weather_by_city():
            return False
        
        print("=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
        return True
        
    except ValueError as e:
        print(f"\n✗ Configuration Error: {e}")
        print("   Please configure [qweather] section in config.ini")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
