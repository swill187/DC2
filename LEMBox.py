import ctypes
import os
import subprocess
from typing import Optional
import logging
from datetime import datetime
from collections import deque
import time

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
        self.output_thread = None
        self.stop_flag = False
        self.csv_file = None
        self.last_data_time = None
        self.data_timeout = 2.0  # seconds
        self.restart_attempts = 0
        self.max_restarts = 3
        self.buffer = deque(maxlen=1000)  # Circular buffer for last 1000 readings
        
        # Setup logging
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger('LEMBox')
        
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
            
    def _monitor_process(self):
        """Monitor process health and restart if necessary."""
        while not self.stop_flag and self.process:
            time.sleep(0.5)  # Check every 500ms
            
            current_time = time.time()
            if self.last_data_time and (current_time - self.last_data_time) > self.data_timeout:
                self.logger.warning(f"No data received for {self.data_timeout} seconds")
                if self.restart_attempts < self.max_restarts:
                    self.logger.info("Attempting to restart data collection")
                    self._restart_collection()
                else:
                    self.logger.error("Max restart attempts reached")
                    self.stop_flag = True
                    break
                    
    def _restart_collection(self):
        """Restart the data collection process."""
        self.restart_attempts += 1
        self.logger.info(f"Restart attempt {self.restart_attempts}")
        
        # Store current file and process
        old_file = self.csv_file
        old_process = self.process
        
        # Start new process
        self.process = subprocess.Popen(
            [self.executable, "--collect", old_file.name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        # Clean up old process
        if old_process:
            try:
                old_process.terminate()
                old_process.wait(timeout=1)
            except:
                old_process.kill()
                
    def _handle_process_output(self):
        """Handle subprocess output in a separate thread."""
        if not self.csv_file:
            return
            
        while not self.stop_flag and self.process:
            try:
                output = self.process.stdout.readline()
                if not output:
                    continue
                    
                # Update last data time
                self.last_data_time = time.time()
                
                # Store in circular buffer
                self.buffer.append(output)
                
                # Write to file with timestamp
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
                self.csv_file.write(f"{output.strip()},{timestamp}\n")
                self.csv_file.flush()
                
                # Force write every 100 lines
                if len(self.buffer) % 100 == 0:
                    os.fsync(self.csv_file.fileno())
                    
            except Exception as e:
                self.logger.error(f"Error reading output: {e}")
                break
                
    def start_recording(self, filename):
        """Start data collection."""
        try:
            abs_filename = os.path.abspath(filename)
            self.stop_flag = False
            self.restart_attempts = 0
            self.last_data_time = time.time()
            
            # Open file in append mode
            self.csv_file = open(abs_filename, 'a', buffering=1024*1024)
            
            # Create process
            self.process = subprocess.Popen(
                [self.executable, "--collect", abs_filename],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Start monitoring and output handling threads
            import threading
            self.output_thread = threading.Thread(target=self._handle_process_output)
            self.monitor_thread = threading.Thread(target=self._monitor_process)
            
            self.output_thread.daemon = True
            self.monitor_thread.daemon = True
            
            self.output_thread.start()
            self.monitor_thread.start()
            
            return True
        except Exception as e:
            self.logger.error(f"Error starting recording: {e}")
            if self.csv_file:
                self.csv_file.close()
                self.csv_file = None
            return False
            
    def stop_recording(self):
        """Stop data collection."""
        if self.process:
            try:
                self.stop_flag = True
                
                # Gentle termination first
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    
                # Clean up output handling thread
                if self.output_thread and self.output_thread.is_alive():
                    self.output_thread.join(timeout=2)
                    
                if self.monitor_thread and self.monitor_thread.is_alive():
                    self.monitor_thread.join(timeout=2)
                    
                # Ensure all data is written
                if self.csv_file:
                    self.csv_file.flush()
                    os.fsync(self.csv_file.fileno())
                    self.csv_file.close()
                    self.csv_file = None
                    
                # Close pipes explicitly
                self.process.stdout.close()
                self.process.stderr.close()
                
                self.process = None
                self.output_thread = None
                self.monitor_thread = None
                
            except Exception as e:
                print(f"Error stopping LEM Box: {e}")