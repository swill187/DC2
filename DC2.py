'''
This version of the data collection script changes the order of operations to initiate data collection.
Original:Run script> Press Enter > Select ouput directory > Initialize sensors > Start data collection (automatic)
This version: Run script > Press Enter > Select Output Directory > Initialize sensors > Press Enter > Start collection
'''
import os
import time
import threading
from datetime import datetime
import keyboard
from tkinter import filedialog, Tk

# Update imports
from RSI import ping_robot, start_collection, verify_connection
from Thermocouple import check_daq_connection, write_to_csv as write_thermo_csv, ThermocoupleDAQ
from Microphone import MicrophoneRecorder, check_microphone  
from LEMBox import LEMBoxCollector
from FLIR import check_flir_connection, start_flir_collection_thread, FLIRCollector
from threading import Event

class DataCollectionSystem:
    def __init__(self):
        self.output_path = None
        self.is_collecting = False
        self.active_sensors = {}
        self.threads = []
        self.stop_flag = Event()
        self.thermocouple_task = None
        self.last_status_time = 0
        self.status_interval = 5
        self.thermocouple_daq = None  
        
        # Initialize LEM Box
        try:
            self.lembox = LEMBoxCollector()
        except Exception as e:
            print(f"Error initializing LEM Box: {e}")
            self.lembox = None
            
        # Remove early microphone and FLIR checks from __init__
        self.microphone = None
        self.microphone_available = False
        self.flir_collector = None 

    def verify_sensors(self):
        """Check which sensors are connected and available."""
        print("\nVerifying connected sensors...")
        
        # Check KUKA Robot connection
        robot_ip = "192.168.1.25"
        try:
            is_connected, status = verify_connection(robot_ip)
            if is_connected:
                self.active_sensors['robot'] = True
                print("✓ KUKA Robot connected")
            else:
                self.active_sensors['robot'] = False
                print(f"✗ {status}")
        except Exception as e:
            self.active_sensors['robot'] = False
            print(f"✗ KUKA Robot connection error: {e}")
            
        # Check Microphone
        try:
            if check_microphone():
                self.microphone = MicrophoneRecorder()
                self.microphone_available = True
                self.active_sensors['microphone'] = True
                print("✓ USB Microphone connected")
            else:
                self.active_sensors['microphone'] = False
                print("✗ USB Microphone not found")
        except Exception as e:
            self.active_sensors['microphone'] = False
            print(f"✗ USB Microphone error: {e}")
            
        # Check FLIR camera
        try:
            if check_flir_connection():
                self.active_sensors['flir'] = True
                print("✓ FLIR camera connected")
            else:
                self.active_sensors['flir'] = False
                print("✗ FLIR camera not found")
        except Exception as e:
            self.active_sensors['flir'] = False
            print(f"✗ FLIR camera error: {e}")
            
        # Check Thermocouple DAQ
        if check_daq_connection():
            self.active_sensors['thermocouple'] = True
            print("✓ Thermocouple DAQ connected")
        else:
            self.active_sensors['thermocouple'] = False
            print("✗ Thermocouple DAQ not found")
            
        # Check LEM Box
        if self.lembox and self.lembox.check_connection():
            self.active_sensors['lembox'] = True
            print("✓ LEM Box connected")
        else:
            self.active_sensors['lembox'] = False
            print("✗ LEM Box not found")
            
        return any(self.active_sensors.values())

    def initialize_sensors(self):
        """Initialize all active sensors before starting collection."""
        if not hasattr(self, 'output_path'):
            print("Output path not set. Cannot initialize sensors.")
            return False
            
        print("\nInitializing sensors...")
        success = True
        
        # Initialize FLIR camera if active
        if self.active_sensors.get('flir'):
            try:
                self.flir_collector = FLIRCollector()
                if self.flir_collector.initialize(self.output_path):
                    print("FLIR camera initialized ✓")
                else:
                    print("FLIR camera initialization failed ✗")
                    success = False
            except Exception as e:
                print(f"Error initializing FLIR camera: {e}")
                success = False

        # Initialize Thermocouple DAQ if active
        if self.active_sensors.get('thermocouple'):
            try:
                self.thermocouple_daq = ThermocoupleDAQ("cDAQ1Mod1", 3.5)
                if self.thermocouple_daq.initialize():
                    print("Thermocouple initialized ✓")
                else:
                    print("Thermocouple initialization failed ✗")
                    success = False
            except Exception as e:
                print(f"Error initializing thermocouples: {e}")
                success = False

        if self.active_sensors.get('microphone'):
            if self.microphone and self.microphone_available:
                print("Microphone initialized ✓")
            else:
                print("Microphone initialization failed ✗")
                success = False

        return success

    def print_status_update(self):
        """Print periodic status updates during collection."""
        current_time = time.time()
        if current_time - self.last_status_time >= self.status_interval:
            # Only print status if we're still collecting and threads are alive
            if self.is_collecting and any(thread.is_alive() for thread in self.threads):
                print("\nStatus: Data collection active")
                if self.active_sensors.get('thermocouple'):
                    print("  - Thermocouple recording: Active")
                if self.active_sensors.get('microphone'):
                    print("  - Microphone recording: Active")
                self.last_status_time = current_time
            else:
                # If we reach here during shutdown, help clean up
                self.is_collecting = False

    def robot_collection(self):
        """Thread function for robot data collection."""
        try:
            robot_file = os.path.join(self.output_path, "robot_data.csv")
            print(f"Initializing robot data collection...")
            
            self.robot_data = start_collection(
                mode='collect',
                ip="192.168.1.25",
                output_file=robot_file,
                stop_flag=self.stop_flag,
                skip_verify=True  # Skip verification since we already checked
            )
        except Exception as e:
            print(f"Error in robot collection: {e}")
            self.stop_flag.set()  # Signal other threads to stop

    def thermocouple_collection(self):
        """Thread function for thermocouple data collection."""
        if not self.thermocouple_daq:
            return
            
        while self.is_collecting:
            temp, timestamp = self.thermocouple_daq.read()
            if temp is not None:
                write_thermo_csv(temp, timestamp, 
                               os.path.join(self.output_path, "thermocouple_data.csv"))
            time.sleep(1/self.thermocouple_daq.sample_rate)

    def microphone_collection(self):
        """Thread function for microphone data collection."""
        if not self.microphone_available or self.microphone is None:
            print("Specific USB microphone not available")
            return
            
        filename = os.path.join(self.output_path, "microphone_data.csv")
        try:
            self.microphone.start_recording(filename)
            while self.is_collecting:
                time.sleep(0.1)
        finally:
            if self.microphone.is_recording:
                self.microphone.stop_recording()

    def lembox_collection(self):
        """Thread function for LEM Box data collection."""
        filename = os.path.join(self.output_path, "lembox_data.csv")
        
        if self.lembox.start_recording(filename):
            print("Started LEM Box recording...")
            while self.is_collecting:
                time.sleep(0.1)
            
            print("Stopping LEM Box recording...")
            self.lembox.stop_recording()

    def prepare_collection(self):
        """Prepare the system for data collection."""
        # Create output directory with timestamp
        root = Tk()
        root.withdraw()
        print("\nSelect output directory...")
        base_path = filedialog.askdirectory(title='Select output directory')
        if not base_path:
            print("No directory selected. Exiting...")
            return False

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_path = os.path.join(base_path, f"data_collection_{timestamp}")
        os.makedirs(self.output_path, exist_ok=True)
        print(f"Data will be saved to: {self.output_path}")

        # Initialize sensors
        if not self.initialize_sensors():
            print("Sensor initialization failed. Aborting...")
            return False

        return True

    def start_collection(self):
        """Start data collection from all available sensors."""
        if not hasattr(self, 'output_path'):
            print("System not prepared. Run prepare_collection first.")
            return

        self.stop_flag.clear()
        
        # Start FLIR acquisition before setting collection flag
        if self.active_sensors.get('flir') and self.flir_collector:
            if not self.flir_collector.start_acquisition():
                print("Failed to start FLIR acquisition. Aborting...")
                return
                
        self.is_collecting = True
        print("\nRecording in progress. Press 'Q' to stop data collection.")
        
        # Start collection threads for active sensors
        if self.active_sensors.get('robot'):
            self.threads.append(threading.Thread(target=self.robot_collection))
        if self.active_sensors.get('thermocouple'):
            self.threads.append(threading.Thread(target=self.thermocouple_collection))
        if self.active_sensors.get('microphone'):
            self.threads.append(threading.Thread(target=self.microphone_collection))
        if self.active_sensors.get('lembox'):
            self.threads.append(threading.Thread(target=self.lembox_collection))
        if self.active_sensors.get('flir') and self.flir_collector:
            self.threads.append(threading.Thread(target=start_flir_collection_thread,
                                              args=(self.flir_collector, self.stop_flag)))

        # Start all threads
        for thread in self.threads:
            thread.start()
        
        # Wait for stop signal with status updates
        while self.is_collecting:
            if keyboard.is_pressed('q'):
                self.stop_collection()
                break  # Add explicit break to exit loop immediately
            self.print_status_update()
            time.sleep(0.1)

    def stop_collection(self):
        """Stop all data collection threads."""
        print("\nStopping data collection...")
        self.stop_flag.set()
        self.is_collecting = False
        
        for thread in self.threads:
            thread.join()
        self.threads.clear()
        
        if hasattr(self, 'audio') and self.audio:
            self.audio.terminate()
            
        # Clean up thermocouple
        if self.thermocouple_daq:
            self.thermocouple_daq.close()
            
        print(f"Data collection complete. Files saved to: {self.output_path}")

def main():
    # Initialize data collection system
    system = DataCollectionSystem()
    
    # Verify connected sensors
    if not system.verify_sensors():
        print("\nNo sensors detected. Please check connections.")
        return

    print("\nPress Enter to begin setup...")
    input()
    
    # Prepare the system
    if not system.prepare_collection():
        return
        
    # Wait for user to start collection
    print("\nSystem ready! Press Enter to start data collection...")
    input()
    
    # Start data collection
    system.start_collection()

if __name__ == "__main__":
    main()

#TODO
# 1. Fix timestamps in LEM Box data collection to match the other functions
# 2. Add Xiris camera data collection
# 3. Compile Python scripts with Cython as needed to improve performance
# 4. Add a GUI to start and stop sensors, select output directory, and display status of sensors
