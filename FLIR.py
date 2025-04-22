'''
Description: Modified version of FLIR.py with decoupled read/write operations
and support for future live feed implementation.
'''

import os
import numpy as np
from FLIRwrapperBB import Calibrate_BB, EnvHandler_BB, FLIRCAMERA
import PySpin
from datetime import datetime
import time
import queue
from threading import Thread, Lock

def check_flir_connection():
    """Verify FLIR camera connection."""
    try:
        system = PySpin.System.GetInstance()
        cam_list = system.GetCameras()
        
        if cam_list.GetSize() > 0:
            cam_list.Clear()
            system.ReleaseInstance()
            return True
        
        cam_list.Clear()
        system.ReleaseInstance()
        return False
    except Exception as e:
        print(f"FLIR camera connection error: {e}")
        return False

class FLIRCollector:
    def __init__(self):
        self.camera = None
        self.calibration = None
        self.env_params = None
        self.frame_count = 0
        self.is_initialized = False
        self.frame_queue = queue.Queue(maxsize=30)  # Buffer for live feed
        self.latest_frame = None
        self.frame_lock = Lock()
        self.system = None
        self.output_path = None  # Add this line

    def initialize(self, output_path):
        """Initialize FLIR camera and set up calibration."""
        self.output_path = output_path  # Store output path for later use
        try:
            # Initialize PySpin system first
            self.system = PySpin.System.GetInstance()
            cam_list = self.system.GetCameras()
            
            if cam_list.GetSize() == 0:
                print("No FLIR camera detected")
                return False
                
            print("Initializing FLIR camera...")
            
            # Initialize camera
            self.camera = FLIRCAMERA()
            time.sleep(0.5)
            self.camera = self.camera.set_IRFormatType()
            
            # Set up calibration
            self.calibration = Calibrate_BB()
            self.calibration.get_calibration_details(self.calibration, self.camera.nodemap)
            
            # Set up environmental parameters
            self.env_params = EnvHandler_BB()
            self.env_params = EnvHandler_BB.set_default_env(self.env_params)
            self.env_params = EnvHandler_BB.calc_env(self.env_params, self.calibration)

            # Create output directory and save calibration
            flir_path = os.path.join(output_path, "FLIR")
            os.makedirs(flir_path, exist_ok=True)
            
            # Save FLIR variables file during initialization
            print("Saving FLIR calibration parameters...")
            EnvHandler_BB.create_JSON(self.env_params, self.calibration, flir_path)
            
            print("FLIR camera initialization complete")
            self.is_initialized = True
            
            # Don't start acquisition yet - wait for actual collection to start
            return True

        except Exception as e:
            print(f"Error initializing FLIR camera: {e}")
            self.cleanup()
            return False

    def start_acquisition(self):
        """Start camera acquisition - called just before collecting data."""
        if not self.is_initialized:
            return False
            
        try:
            self.camera.intializeAcquition()
            time.sleep(0.5)
            return True
        except Exception as e:
            print(f"Error starting FLIR acquisition: {e}")
            return False

    def read_frame(self):
        """Capture a single frame from the FLIR camera."""
        if not self.is_initialized:
            return None, None

        try:
            image_result, _ = self.camera.get_frame()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            # Update latest frame for live view
            with self.frame_lock:
                self.latest_frame = image_result
                
            # Add to queue for saving
            self.frame_queue.put((image_result, timestamp))
            
            return image_result, timestamp
        except Exception as e:
            print(f"Error reading FLIR frame: {e}")
            return None, None

    def get_latest_frame(self):
        """Get the most recent frame for display purposes."""
        with self.frame_lock:
            return self.latest_frame

    def save_frames(self, output_path):
        """Save frames from queue to files."""
        while True:
            try:
                frame_data, timestamp = self.frame_queue.get(timeout=1)
                self.write_frame(frame_data, timestamp, output_path)
                self.frame_queue.task_done()
            except queue.Empty:
                if not self.is_initialized:
                    break

    def write_frame(self, frame_data, timestamp, output_path):
        """Save frame data with timestamp."""
        try:
            flir_path = os.path.join(output_path, "FLIR")
            filename = f"FLIR-Frame-{self.frame_count}.npy"
            filepath = os.path.join(flir_path, filename)
            
            np_data = {'frame': frame_data, 'timestamp': timestamp}
            np.save(filepath, np_data)
            self.frame_count += 1
            return True
        except Exception as e:
            print(f"Error writing FLIR frame: {e}")
            return False

    def cleanup(self):
        """Clean up FLIR camera resources."""
        if self.camera:
            try:
                if self.is_initialized:
                    self.camera.uninitialize()
                self.is_initialized = False
            except Exception as e:
                print(f"Error cleaning up FLIR camera: {e}")
        
        if self.system:
            self.system.ReleaseInstance()
            self.system = None

def start_flir_collection(output_path, stop_flag):
    """Start FLIR data collection with separate read and write threads."""
    collector = FLIRCollector()
    if not collector.initialize(output_path):
        return

    # Start acquisition explicitly before starting collection threads
    if not collector.start_acquisition():
        collector.cleanup()
        return

    # Start separate threads for reading and saving
    read_thread = Thread(target=frame_reader, args=(collector, stop_flag))
    save_thread = Thread(target=collector.save_frames, args=(output_path,))
    
    try:
        read_thread.start()
        save_thread.start()
        
        read_thread.join()
        collector.is_initialized = False
        save_thread.join()
    finally:
        collector.cleanup()

def frame_reader(collector, stop_flag):
    """Thread function to continuously read frames."""
    while not stop_flag.is_set():
        collector.read_frame()
        time.sleep(0.1)  # Adjust rate as needed

def start_flir_collection_thread(collector, stop_flag):
    """Start FLIR data collection using pre-initialized collector."""
    # Start separate threads for reading and saving
    read_thread = Thread(target=frame_reader, args=(collector, stop_flag))
    save_thread = Thread(target=collector.save_frames, args=(collector.output_path,))
    
    try:
        read_thread.start()
        save_thread.start()
        
        read_thread.join()
        collector.is_initialized = False
        save_thread.join()
    finally:
        collector.cleanup()

# For future live feed implementation:
def display_live_feed(collector):
    """Example function for future live feed implementation."""
    try:
        import cv2
        while collector.is_initialized:
            frame = collector.get_latest_frame()
            if frame is not None:
                # Convert frame to temperature values if needed
                # Display frame using cv2.imshow()
                # Add overlay information if needed
                pass
    except ImportError:
        print("OpenCV not installed. Live feed not available.")
