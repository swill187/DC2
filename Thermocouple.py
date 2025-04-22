import nidaqmx
from nidaqmx.constants import ThermocoupleType, TemperatureUnits, AcquisitionType
import csv
from datetime import datetime
import time
import os
import keyboard

class ThermocoupleDAQ:
    def __init__(self, device_name="cDAQ1Mod1", sample_rate=3.5):
        self.device_name = device_name
        self.sample_rate = sample_rate
        self.task = None
        self.is_initialized = False
        
    def initialize(self):
        """Initialize the DAQ system."""
        try:
            self.task = nidaqmx.Task()
            for i in range(4):
                channel = f"{self.device_name}/ai{i}"
                self.task.ai_channels.add_ai_thrmcpl_chan(
                    channel,
                    name_to_assign_to_channel=f"Thermocouple_{i}",
                    thermocouple_type=ThermocoupleType.K,
                    units=TemperatureUnits.DEG_C
                )
            
            self.task.timing.cfg_samp_clk_timing(
                rate=self.sample_rate,
                sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=1
            )
            self.is_initialized = True
            return True
        except Exception as e:
            print(f"Error initializing thermocouple DAQ: {e}")
            return False

    def read(self):
        """Read current temperature values"""
        if not self.is_initialized:
            return None, None
            
        try:
            temperatures = self.task.read()
            timestamp = time.time()
            return temperatures, timestamp
        except nidaqmx.errors.Error as e:
            print(f"Error reading thermocouple: {e}")
            return None, None

    def close(self):
        """Cleanup DAQ resources"""
        if self.task:
            self.task.close()
            self.task = None
        self.is_initialized = False

def check_daq_connection(device_name="cDAQ1Mod1"):
    """Verify DAQ connection."""
    try:
        daq = ThermocoupleDAQ(device_name)
        result = daq.initialize()
        daq.close()
        return result
    except Exception:
        return False

def write_to_csv(temperatures, timestamp, filename="thermocouple_data.csv"):
    """Write temperature data to CSV file with timestamp."""
    if temperatures is None:
        return False
        
    try:
        file_exists = os.path.isfile(filename)
        
        # Get or create start time
        if not hasattr(write_to_csv, 'start_time'):
            write_to_csv.start_time = timestamp
            
        # Calculate relative timestamp in seconds with microsecond precision
        relative_time = timestamp - write_to_csv.start_time
        
        with open(filename, mode='a', newline='') as file:
            writer = csv.writer(file)
            
            if not file_exists:
                writer.writerow(['Timestamp', 'Relative Time (s)', 'Channel 0 (°C)', 
                               'Channel 1 (°C)', 'Channel 2 (°C)', 'Channel 3 (°C)'])
            
            # Use same datetime format as terminal output
            current_time = datetime.fromtimestamp(timestamp)
            formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.%f')
            
            writer.writerow([formatted_time, f"{relative_time:.6f}"] + 
                          [f"{temp:.2f}" for temp in temperatures])
                
        return True
    except Exception as e:
        print(f"Error writing to CSV: {e}")
        return False

def print_temperature(temperatures, timestamp):
    """Print the temperature readings in a formatted way."""
    if temperatures is None:
        return
        
    # Format time with microsecond precision
    current_time = datetime.fromtimestamp(timestamp)
    formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S.%f')
    print(f"\nData received at {formatted_time}")
    
    # Handle the data as a flat list of temperatures
    if isinstance(temperatures[0], (int, float)):
        for i, temp in enumerate(temperatures):
            print(f"Channel {i}: {temp:.2f}°C", end="  ")
        print()
    else:
        print("Error: Unexpected temperature data format")

if __name__ == "__main__":
    # Configuration
    DEVICE_NAME = "cDAQ1Mod1"
    SAMPLE_RATE = 3.5  # Max sample rate of the DAQ

    print("Thermocouple DAQ Test Script")
    print("----------------------------")
    print(f"Device: {DEVICE_NAME}")
    print(f"Sample Rate: {SAMPLE_RATE} Hz")
    print("\nPress 'Q' to stop recording")
    
    daq = ThermocoupleDAQ(DEVICE_NAME, SAMPLE_RATE)
    if daq.initialize():
        print(f"\nSuccessfully connected to {DEVICE_NAME}")
        running = True
        
        try:
            sleep_time = max(0.001, (1.0 / SAMPLE_RATE) * 0.9)
            while running:
                temperature, timestamp = daq.read()
                if temperature is not None:
                    print_temperature(temperature, timestamp)
                    write_to_csv(temperature, timestamp)
                
                if keyboard.is_pressed('q'):
                    print("\nStopping data collection...")
                    running = False
                
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            print("\nData collection interrupted")
        finally:
            daq.close()
            print("Data collection complete")
    else:
        print(f"Could not connect to {DEVICE_NAME}")