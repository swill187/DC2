import os
import subprocess
import time
import signal
import threading
from typing import Optional
import traceback

class XirisCamera:
    FORMAT_DIRS = ['png', 'raw']
    
    def __init__(self):
        self.process = None
        self.record_process = None
        self.executable = os.path.join(os.path.dirname(__file__), "XIR1800Collection.exe")
        self.is_recording = False
        self.is_initialized = False
        self.output_path = None
        self.cmd_args = None
        self.recording_start_time = None
        self.process_flags = (subprocess.HIGH_PRIORITY_CLASS | 
                              subprocess.DETACHED_PROCESS | 
                              subprocess.CREATE_NO_WINDOW)
        self.camera_ip = None
        self.connected = False
        self.current_output_path = None
        self.connect_process = None
        self.connection_file = os.path.join(os.path.dirname(self.executable), "xiris_connection.tmp")
        self._status_thread = None
        self._stop_event = threading.Event()

    def initialize(self, output_path: str = None) -> bool:
        """Initialize and connect to the camera."""
        try:
            # Kill any existing processes first
            self._cleanup()
            time.sleep(2)  # Give time for complete cleanup

            if output_path:
                self.current_output_path = output_path
                os.makedirs(self.current_output_path, exist_ok=True)
                print(f"Using output path: {self.current_output_path}")

            # First detect camera
            result = subprocess.run([self.executable, "--detect"], 
                                 capture_output=True, text=True, timeout=10)
            
            # Parse camera IP and check
            for line in result.stdout.splitlines():
                if "Detected camera with IP:" in line:
                    self.camera_ip = line.split(":")[-1].strip()
                    break
                    
            if not self.camera_ip:
                print("No camera detected")
                return False

            print(f"Detected camera at {self.camera_ip}")
            
            # Use combined connect/recording command
            cmd = [
                self.executable,
                "--connect",
                self.camera_ip,
                os.path.abspath(self.current_output_path)
            ]
            
            print("Starting camera process...")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            
            # Wait for successful startup with longer timeout
            for attempt in range(60):  # Doubled timeout
                time.sleep(1.0)  # Increased delay
                
                if self.process.poll() is not None:
                    stdout = self.process.stdout.read() if self.process.stdout else ""
                    stderr = self.process.stderr.read() if self.process.stderr else ""
                    print(f"Process exited:\nstdout: {stdout}\nstderr: {stderr}")
                    return False

                # Read all available output
                while True:
                    output = self.process.stdout.readline() if self.process.stdout else ""
                    if not output:
                        break
                    if "Camera configured successfully" in output:
                        print("Camera initialization complete")
                        self.connected = True
                        self.is_initialized = True
                        self.is_recording = True
                        self.recording_start_time = time.time()
                        return True
                    print(output.strip())  # Print other messages

                if attempt % 2 == 0:  # Only print every other attempt
                    print(f"Waiting for camera configuration... attempt {attempt + 1}")

            print("Failed to initialize camera")
            self._cleanup()
            return False

        except Exception as e:
            print(f"Error initializing camera: {e}")
            traceback.print_exc()
            self._cleanup()
            return False

    def check_connection(self) -> bool:
        """Check if camera is already connected."""
        if not hasattr(self, 'is_initialized') or not self.is_initialized:
            return self.initialize()
        return self.is_initialized

    def start_streaming(self) -> bool:
        """Start camera streaming without recording."""
        if self.process:
            return True  # Already streaming

        try:
            # Connect and stream in one command
            cmd = [
                self.executable,
                "--connect",
                self.camera_ip,
                os.path.abspath(self.current_output_path)
            ]
            
            print("Starting camera stream...")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.HIGH_PRIORITY_CLASS
            )
            
            # Wait for stream to start
            for attempt in range(30):
                time.sleep(0.5)
                if self.process.poll() is not None:
                    stdout = self.process.stdout.read()
                    stderr = self.process.stderr.read()
                    print(f"Process failed:\nstdout: {stdout}\nstderr: {stderr}")
                    return False
                    
                stdout = self.process.stdout.readline() if self.process.stdout else ""
                if "Camera configured successfully" in stdout:
                    print("Camera streaming started")
                    return True
                    
                print(f"Waiting for camera configuration... attempt {attempt + 1}")
                
            return False

        except Exception as e:
            print(f"Error starting stream: {e}")
            traceback.print_exc()
            return False

    def start_recording(self, output_path: str = None) -> bool:
        """Check recording status - recording starts with initialization."""
        return self.process is not None and self.process.poll() is None and self.is_recording

    def stop_recording(self):
        """Stop recording and cleanup processes."""
        self._stop_event.set()
        self.is_recording = False
        
        if self.process:
            print("Stopping camera process...")
            try:
                # Try graceful shutdown first
                self.process.terminate()
                time.sleep(1)  # Give time for graceful shutdown
                
                if self.process.poll() is None:
                    print("Force stopping camera...")
                    self.process.kill()
                    
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Force killed camera process")
            except Exception as e:
                print(f"Error stopping camera: {e}")
            
            self.process = None
            time.sleep(2)  # Give time for complete cleanup
        
        print("Xiris recording stopped")

    def is_actually_recording(self) -> bool:
        """Check if camera is actually recording."""
        # Just check if process is running
        if not self.process or self.process.poll() is not None:
            if self.is_recording:
                print("Camera process stopped unexpectedly")
                self.is_recording = False
            return False
        return True

    def _monitor_recording(self):
        """Monitor recording process in background"""
        while not self._stop_event.is_set() and self.is_recording:
            if not self.is_actually_recording():
                print("Recording stopped")
                break
            time.sleep(0.1)

    def _cleanup(self):
        """Clean up all processes."""
        self._stop_event.set()
        
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            
        if self.record_process:
            try:
                self.record_process.terminate()
                self.record_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.record_process.kill()
            self.record_process = None
            
        if self.connect_process:
            try:
                self.connect_process.terminate()
                self.connect_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.connect_process.kill()
            self.connect_process = None
            
        # Don't remove connection file on cleanup
        self.connected = False
        self.is_initialized = False
        self.is_recording = False

