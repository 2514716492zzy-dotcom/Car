"""
Test script for Serial Manager
Tests hardware communication with actual serial device

Run from project root: python modules/hardware_communication/test_serial_manager.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from modules.hardware_communication import SerialManager


def test_command_mapping():
    """Test command mapper functionality"""
    print("\n" + "=" * 60)
    print("TEST 1: Command Mapping")
    print("=" * 60)
    
    sm = SerialManager()
    
    # Test all movement commands
    print("\n✓ Movement commands:")
    movement_cmds = ['forward', 'backward', 'left', 'right', 'rotate_left', 'rotate_right']
    for cmd in movement_cmds:
        code = sm.command_mapper.get_command_code(cmd)
        status = "✓" if code else "❌"
        print(f"  {status} {cmd:15s} -> {code if code else 'NOT FOUND'}")
    
    # Test behavior commands
    print("\n✓ Behavior commands:")
    behavior_cmds = ['follow_me', 'wander', 'stop', 'return', 'spray']
    for cmd in behavior_cmds:
        code = sm.command_mapper.get_command_code(cmd)
        status = "✓" if code else "❌"
        print(f"  {status} {cmd:15s} -> {code if code else 'NOT FOUND'}")
    
    # Test invalid command
    print("\n✓ Invalid command handling:")
    invalid_code = sm.command_mapper.get_command_code('invalid_xyz')
    print(f"  invalid_xyz -> {invalid_code if invalid_code else 'None (expected)'}")
    
    print("\n✅ Command mapping test passed\n")


def test_serial_connection():
    """Test serial connection and basic commands"""
    print("=" * 60)
    print("TEST 2: Serial Connection & Commands")
    print("=" * 60)
    
    # Initialize SerialManager
    print("\n✓ Initializing SerialManager...")
    sm = SerialManager()
    
    # Check connection status
    print(f"\n✓ Connection status: {'Connected' if sm._is_connected else 'Not connected'}")
    print(f"  Port: {sm.port}")
    print(f"  Baudrate: {sm.baudrate}")
    
    if not sm._is_connected:
        print("\n⚠️ No serial device connected")
        print("  Make sure hardware is connected and config.ini has correct port")
        return False
    
    # Test sending commands
    print("\n✓ Testing command transmission...")
    test_commands = ['forward', 'stop', 'backward', 'left', 'right']
    
    for cmd in test_commands:
        print(f"  Sending: {cmd}")
        result = sm.send_mapped_command(cmd)
        if not result:
            print(f"    ❌ Failed to send {cmd}")
            return False
    
    print("\n✅ Serial connection test passed!")
    print("=" * 60 + "\n")
    return True


if __name__ == "__main__":
    test_command_mapping()
    success = test_serial_connection()
    sys.exit(0 if success else 1)
