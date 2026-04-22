"""
Command Mapper - Hardware Communication Helper
Maps high-level commands to hardware control codes
"""

import json
from pathlib import Path
from typing import Optional


class CommandMapper:
    """
    Maps semantic commands to hardware-specific control codes
    
    Loads mappings from command_map.json for easy configuration
    """
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize command mappings from JSON file
        
        Args:
            config_file: Path to JSON config file (default: command_map.json in module dir)
        """
        # Load command map from JSON
        if config_file is None:
            config_file = Path(__file__).parent / "command_map.json"
        else:
            config_file = Path(config_file)
        
        self.command_map = {}
        self._load_from_json(config_file)
    
    def _load_from_json(self, json_path: Path):
        """Load command mappings from JSON file"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Flatten all categories into single map
            for category, commands in data.items():
                for cmd, code in commands.items():
                    # Convert string to bytes
                    self.command_map[cmd.lower()] = code.encode() if isinstance(code, str) else code
            
            print(f"✅ Loaded {len(self.command_map)} commands from {json_path.name}")
            
        except FileNotFoundError:
            print(f"⚠️ Command map not found: {json_path}")
        except json.JSONDecodeError as e:
            print(f"⚠️ Invalid JSON in command map: {e}")
        except Exception as e:
            print(f"⚠️ Error loading command map: {e}")
    
    def get_command_code(self, command: str) -> Optional[bytes]:
        """
        Get hardware code for a command
        
        Args:
            command: Command name (e.g., 'forward', 'follow_me')
            
        Returns:
            Command byte code, or None if command not found
        """
        return self.command_map.get(command.lower())
    
    def is_valid_command(self, command: str) -> bool:
        """Check if command is valid"""
        return command.lower() in self.command_map
    
    def get_all_commands(self) -> list:
        """Get list of all available commands"""
        return list(self.command_map.keys())
