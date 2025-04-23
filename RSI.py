import socket
import time
import signal
import platform
import subprocess
from datetime import datetime
import os
from threading import Event
from typing import List, Tuple

# Global flag for graceful shutdown
running = True

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    global running
    print("\nClosing program...")
    running = False

def ping_robot(ip_address="192.168.1.25"):
    """Check if robot is reachable via ping"""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
    command = ['ping', param, '1', timeout_param, '1', ip_address]
    
    try:
        output = subprocess.run(command, capture_output=True, text=True)
        return output.returncode == 0
    except subprocess.SubprocessError:
        return False

def verify_connection(ip="192.168.1.25", port=59152):
    """Verify robot connection using ping"""
    try:
        if ping_robot(ip):
            return True, "Robot is reachable"
        return False, "Robot is not reachable"
    except Exception as e:
        return False, f"Connection error: {str(e)}"

def collect_raw_data(ip="192.168.1.25", port=59152, stop_flag=None) -> List[Tuple[str, float, float]]:
    """Collect raw XML data with absolute and relative timestamps until stopped"""
    raw_data = []
    start_time = time.perf_counter() 
    
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((ip, port))
        s.settimeout(0.1)
        print(f"Listening on {ip}:{port}")
        last_report = time.perf_counter()
        
        print("Waiting for first data point...")
        
        while not (stop_flag and stop_flag.is_set()) and running:
            try:
                data, _ = s.recvfrom(1024)
                # Get timestamp immediately after receiving data
                current_time = time.perf_counter()
                relative_time = current_time - start_time
                
                if not raw_data:
                    print("First data point received! Collection started.")
                
                raw_data.append((data.decode('utf-8'), time.time(), relative_time))
                
                if current_time - last_report > 2:
                    print(f"Collected {len(raw_data)} data points...")
                    last_report = current_time
                    
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error receiving data: {e}")
                break

    print(f"Collection stopped. Total points collected: {len(raw_data)}")
    return raw_data

def save_raw_data(raw_data: List[Tuple[str, float, float]], filename: str = None) -> bool:
    """Save raw data with both timestamps to file"""
    if not raw_data:
        print("No data collected to save!")
        return False
        
    if not filename:
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"robot_raw_{timestamp_str}.txt"
    
    if not filename.endswith('.txt'):
        filename += '.txt'
    
    if not os.path.isabs(filename):
        filename = os.path.join(os.getcwd(), filename)
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("# SystemTime|RelativeTime|XML\n")
            
            # Write data with formatted system time
            for xml_str, abs_time, rel_time in raw_data:
                system_time = datetime.fromtimestamp(abs_time).strftime('%Y-%m-%d %H:%M:%S.%f')
                safe_xml = xml_str.replace('|', '&#124;')
                f.write(f"{system_time}|{rel_time:.6f}|{safe_xml}\n")
                
        print(f"\nData saved to: {filename}")
        print(f"File size: {os.path.getsize(filename)} bytes")
        return True
        
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

def start_collection(ip="192.168.1.25", port=59152, output_file=None, 
                    stop_flag=None, skip_verify=False) -> List[Tuple[str, float, float]]:
    """Main interface function for collecting robot data"""
    if not skip_verify:
        is_connected, status = verify_connection(ip, port)
        if not is_connected:
            print(f"Robot connection failed: {status}")
            return []

    print("Starting raw data collection...")
    raw_data = collect_raw_data(ip, port, stop_flag)
    
    if raw_data and output_file:
        save_raw_data(raw_data, output_file)
    
    return raw_data

if __name__ == "__main__":
    try:
        signal.signal(signal.SIGINT, signal_handler)
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_file = os.path.join(os.getcwd(), f"robot_raw_{timestamp_str}.txt")
        print(f"Output will be saved to:\n{default_file}")
        start_collection(output_file=default_file)
    except KeyboardInterrupt:
        print("\nCollection stopped by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("Program finished")
