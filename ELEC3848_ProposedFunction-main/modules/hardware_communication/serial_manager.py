"""
Serial Manager - Hardware Communication Handler
Manages serial port communication with Arduino/hardware
"""

import time
from typing import Optional
from modules.common_tools import load_config
from .command_mapper import CommandMapper

# Try to import pyserial
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    serial = None
    SERIAL_AVAILABLE = False


class SerialManager:
    """
    Manages serial communication with hardware (Arduino, motor controller, etc.)
    
    Simplified for sending commands only
    """
    
    def __init__(self, port: str = None, baudrate: int = None):
        """
        Initialize serial manager
        
        Args:
            port: Serial port path (default: from config.ini)
            baudrate: Baud rate (default: from config.ini)
        """
        # Check if pyserial is available
        if not SERIAL_AVAILABLE:
            print("⚠️ pyserial not installed - hardware control disabled")
        
        # Load config
        config = load_config()
        self.port = port or config.get('hardware', 'port', fallback='/dev/ttyUSB0')
        self.baudrate = baudrate or config.getint('hardware', 'baudrate', fallback=115200)
        
        # Serial connection
        self._connection = None
        self._is_connected = False
        
        # Command mapper
        self.command_mapper = CommandMapper()
        
        # Auto-connect if serial is available
        if SERIAL_AVAILABLE:
            self.connect()
    
    def connect(self) -> bool:
        """Establish serial connection"""
        if not SERIAL_AVAILABLE or self._is_connected:
            return self._is_connected
        
        try:
            self._connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1.0
            )
            self._is_connected = True
            print(f"✅ Serial connected: {self.port} @ {self.baudrate} baud")
            
            time.sleep(2)  # Wait for Arduino reset
            self._connection.reset_input_buffer()
            self._connection.reset_output_buffer()
            return True
            
        except Exception as e:
            print(f"⚠️ Serial connection failed: {e}")
            print(f"   Running in software-only mode")
            self._is_connected = False
            return False
    
    def send_command(self, command: bytes) -> bool:
        """
        Send command to hardware
        
        Args:
            command: Command bytes to send
            
        Returns:
            True if sent successfully
        """
        if not self._is_connected:
            print(f"   [Hardware disabled - command not sent: {command}]")
            return False
        
        try:
            self._connection.write(command)
            self._connection.flush()
            return True
        except Exception as e:
            print(f"⚠️ Send error: {e}")
            return False
    
    def send_mapped_command(self, command: str) -> bool:
        """
        Send a high-level command using the command mapper
        
        Args:
            command: Command name (e.g., 'forward', 'follow_me')
            
        Returns:
            True if sent successfully
        """
        code = self.command_mapper.get_command_code(command)
        if code is None:
            print(f"⚠️ Unknown command: {command}")
            return False
        
        return self.send_command(code)
    
    def disconnect(self):
        """Close serial connection"""
        if self._connection and self._is_connected:
            try:
                self._connection.close()
                print("✅ Serial disconnected")
            except Exception as e:
                print(f"⚠️ Disconnect error: {e}")
            finally:
                self._is_connected = False
                self._connection = None
    
    def __del__(self):
        """Cleanup on deletion"""
        self.disconnect()
