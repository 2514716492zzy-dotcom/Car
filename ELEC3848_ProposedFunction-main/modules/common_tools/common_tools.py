"""Common utility functions for loading configuration and environment variables"""

import os
from dotenv import load_dotenv
from pathlib import Path
import configparser


def load_env_variables() -> None:
    """
    Load environment variables from .env file
    Prints warning if file not found.
    """
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)
    else:
        print("Warning: .env file not found")


def load_config() -> configparser.ConfigParser:
    """
    Load configuration from config.ini file
    
    Returns:
        ConfigParser object with loaded configuration, or empty ConfigParser on error
    """
    try:
        config_path = Path("config.ini")
        if not config_path.exists():
            raise FileNotFoundError("config.ini not found")
        
        config = configparser.ConfigParser()
        config.read(config_path, encoding="utf-8")
        return config
        
    except Exception as e:
        print(f"Config loading failed: {str(e)}")
        return configparser.ConfigParser()