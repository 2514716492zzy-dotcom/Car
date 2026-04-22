"""
Hardware Communication Module
Handles serial communication with Arduino/hardware
"""

from .serial_manager import SerialManager
from .command_mapper import CommandMapper

__all__ = ['SerialManager', 'CommandMapper']
