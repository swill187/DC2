import ctypes
import os
import subprocess
from typing import Optional

class LEMBox:
    def __init__(self):
        try:
            # Load the compiled C library (assuming it's named 'dt9816s.dll' for Windows)
            # Change path as needed
            lib_path = os.path.join(os.path.dirname(__file__), 'dt9816s.dll')
            self._lib = ctypes.CDLL(lib_path)
            self.device_handle = None
            self.initialized = False
        except Exception as e:
            raise RuntimeError(f"Failed to load DT9816-S library: {str(e)}")

    def initialize(self) -> bool:
        """Initialize the DT9816-S device"""
        if hasattr(self._lib, 'dt9816s_init'):
            self.device_handle = self._lib.dt9816s_init()
            self.initialized = self.device_handle is not None
            return self.initialized
        return False

    def read_voltage(self, channel: int) -> Optional[float]:
        """Read voltage from specified channel"""
        if not self.initialized:
            return None
        
        if hasattr(self._lib, 'dt9816s_read_voltage'):
            voltage = ctypes.c_double()
            result = self._lib.dt9816s_read_voltage(
                self.device_handle,
                ctypes.c_int(channel),
                ctypes.byref(voltage)
            )
            if result == 0:  # Assuming 0 is success
                return voltage.value
        return None

    def close(self):
        """Close the device connection"""
        if self.initialized and hasattr(self._lib, 'dt9816s_close'):
            self._lib.dt9816s_close(self.device_handle)
            self.initialized = False
            self.device_handle = None

class LEMBoxCollector:
    def __init__(self):
        self.process = None
        self.executable = os.path.join(os.path.dirname(__file__), "LEMBOX.exe")
        
    def check_connection(self):
        """Check if DT9816-S is accessible."""
        try:
            # Run with output capture and timeout
            result = subprocess.run(
                [self.executable, "--check"], 
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Print the actual output from LEMBOX.exe
            if result.stdout:
                print(result.stdout.strip())
            
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            print("Warning: Board check timed out - this might indicate a driver issue")
            return False
        except FileNotFoundError:
            print(f"Error: Could not find {self.executable}")
            return False
        except Exception as e:
            print(f"Error checking board: {str(e)}")
            return False
            
    def start_recording(self, filename):
        """Start data collection."""
        try:
            # Use absolute path for filename
            abs_filename = os.path.abspath(filename)
            self.process = subprocess.Popen(
                [self.executable, "--collect", abs_filename],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return True
        except Exception as e:
            print(f"Error starting LEM Box: {e}")
            return False
            
    def stop_recording(self):
        """Stop data collection."""
        if self.process:
            try:
                self.process.terminate()
                # Wait for process to terminate
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                self.process = None
            except Exception as e:
                print(f"Error stopping LEM Box: {e}")