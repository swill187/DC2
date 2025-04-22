import socket
import csv
import xml.etree.ElementTree as ET
from datetime import datetime
import platform
import subprocess
import os
import signal
import sys
import time
import argparse
import queue
from typing import List, Dict, Tuple

# Global variables
running = True
data_queue = queue.Queue()

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    global running
    print("\nClosing program...")
    running = False

def ping_robot(ip_address="192.168.1.25"):
    """Check if the robot is reachable via ping with a short timeout."""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
    command = ['ping', param, '1', timeout_param, '1', ip_address]  # 1 second timeout
    
    try:
        output = subprocess.run(command, capture_output=True, text=True)
        return output.returncode == 0
    except subprocess.SubprocessError:
        return False

def verify_connection(ip="192.168.1.25", port=59152):
    """Verify robot connection using ping."""
    try:
        if ping_robot(ip):
            return True, "Robot is reachable"
        return False, "Robot is not reachable"
    except Exception as e:
        return False, f"Connection error: {str(e)}"

def collect_raw_data(ip="192.168.1.25", port=59152, stop_flag=None) -> List[Tuple[str, float, float]]:
    """Collect raw XML data and timestamps until stopped."""
    raw_data = []
    start_time = time.time()
    
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((ip, port))
        s.settimeout(0.1)  # Reduced timeout for more responsive collection
        print(f"Listening on {ip}:{port}")
        last_report = time.time()
        
        # Print immediate feedback
        print("Waiting for first data point...")
        
        while not (stop_flag and stop_flag.is_set()) and running:
            try:
                data, _ = s.recvfrom(1024)
                current_time = time.time()
                
                # Print immediate feedback for first data point
                if not raw_data:
                    print("First data point received! Collection started.")
                
                elapsed_ms = (current_time - start_time) * 1000
                raw_data.append((data.decode('utf-8'), current_time, elapsed_ms))
                
                # Report progress every 2 seconds instead of 5
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

def parse_xml_data(xml_str: str) -> Dict:
    """Parse XML string into dictionary of values."""
    root = ET.fromstring(xml_str)
    
    RIst = root.find('RIst')
    RSol = root.find('RSol')
    Tech = root.find('Tech')
    Status = root.find('Status')
    
    row = {
        'X_RIst': RIst.attrib['X'], 'Y_RIst': RIst.attrib['Y'], 'Z_RIst': RIst.attrib['Z'],
        'A_RIst': RIst.attrib['A'], 'B_RIst': RIst.attrib['B'], 'C_RIst': RIst.attrib['C'],
        'X_RSol': RSol.attrib['X'], 'Y_RSol': RSol.attrib['Y'], 'Z_RSol': RSol.attrib['Z'],
        'A_RSol': RSol.attrib['A'], 'B_RSol': RSol.attrib['B'], 'C_RSol': RSol.attrib['C'],
        'Delay': root.find('Delay').attrib['D'],
        'WeldVolt': root.find('WeldVolt').text,
        'WeldAmps': root.find('WeldAmps').text,
        'MotorAmps': root.find('MotorAmps').text,
        'WFS': root.find('WFS').text,
        'IPOC': root.find('IPOC').text,
        'ErrorNum': root.find('ErrorNum').text
    }
    
    # Add Tech data
    for i in range(1, 11):
        key = f'C1{i}'
        row[key] = Tech.attrib.get(key, '0.0')
    
    # Add Status data
    for i in range(1, 5):
        key = f'i{i}'
        row[key] = Status.attrib.get(key, '0')
    
    return row

def save_to_csv(raw_data: List[Tuple[str, float, float]], filename: str = None):
    """Parse and save collected data to CSV."""
    if not raw_data:
        print("No data collected to save!")
        return False
        
    if not filename:
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"robot_data_{timestamp_str}.csv"
    
    # Ensure absolute path
    if not os.path.isabs(filename):
        filename = os.path.join(os.getcwd(), filename)
    
    print(f"\nProcessing {len(raw_data)} data points...")
    print(f"Saving to: {filename}")
    
    try:
        first_row = parse_xml_data(raw_data[0][0])
        fieldnames = ['Timestamp', 'Elapsed_ms'] + list(first_row.keys())
        
        with open(filename, 'w', newline='') as csvfile:
            # Configure CSV writer to quote all fields
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, 
                                  quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()
            
            for xml_str, timestamp, elapsed_ms in raw_data:
                try:
                    row = parse_xml_data(xml_str)
                    # Format timestamp with quotes to prevent Excel truncation
                    row['Timestamp'] = f'"{datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")}"'
                    row['Elapsed_ms'] = f"{elapsed_ms:.3f}"
                    writer.writerow(row)
                except ET.ParseError as e:
                    print(f"Failed to parse data point: {e}")
                    continue
        
        # Verify file was created
        if os.path.exists(filename):
            file_size = os.path.getsize(filename)
            print(f"File created successfully. Size: {file_size} bytes")
        else:
            print("Warning: File was not created!")
            
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

def single_point_test(ip="192.168.1.25"):
    """Test single point data collection."""
    raw_data = collect_raw_data(ip)
    if raw_data:
        xml_str, timestamp = raw_data[0]
        try:
            root = ET.fromstring(xml_str)
            print("\nTest Data Point:")
            print_data(root, datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S.%f'))
            return True
        except ET.ParseError as e:
            print(f"Failed to parse XML: {e}")
    return False

def print_data(root, timestamp):
    """Print the received data in a formatted way."""
    if not root:
        return
        
    print(f"\nData received at {timestamp}")
    print("Current Position (RIst):")
    RIst = root.find('RIst')
    print(f"X: {RIst.attrib['X']}, Y: {RIst.attrib['Y']}, Z: {RIst.attrib['Z']}")
    print(f"A: {RIst.attrib['A']}, B: {RIst.attrib['B']}, C: {RIst.attrib['C']}")
    
    print("\nWelding Parameters:")
    print(f"Voltage: {root.find('WeldVolt').text}V")
    print(f"Current: {root.find('WeldAmps').text}A")
    print(f"Wire Feed Speed: {root.find('WFS').text}")

def start_collection(mode='collect', ip="192.168.1.25", port=59152, 
                    output_file=None, stop_flag=None, skip_verify=False) -> List[Tuple[str, float, float]]:
    """
    Interface function for both direct use and importing.
    Args:
        mode: 'test' or 'collect'
        ip: Robot IP address
        port: UDP port
        output_file: Optional file path for saving data
        stop_flag: Threading event for stopping collection
        skip_verify: Skip connection verification if already verified
    """
    if not skip_verify:
        # Only verify connection if not already verified
        is_connected, status = verify_connection(ip, port)
        if not is_connected:
            print(f"Robot connection failed: {status}")
            return []

    if mode == 'test':
        print("Testing single point collection...")
        single_point_test(ip)
        return []
    else:
        print("Starting continuous collection...")
        raw_data = collect_raw_data(ip, port, stop_flag)
        if raw_data:
            if not output_file:
                timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_file = f"robot_data_{timestamp_str}.csv"
            save_to_csv(raw_data, filename=output_file)
        return raw_data

if __name__ == "__main__":
    try:
        # Check if arguments were provided
        if len(sys.argv) > 1:
            parser = argparse.ArgumentParser(description='KUKA Robot Data Collection')
            parser.add_argument('--mode', choices=['test', 'collect'], default='collect',
                           help='Operation mode: test (single point) or collect (continuous)')
            parser.add_argument('--ip', default='192.168.1.25', help='Robot IP address')
            args = parser.parse_args()
            start_collection(args.mode, args.ip)
        else:
            # Default behavior when run directly (e.g., via IDE run button)
            print("Starting default continuous collection...")
            print("Press Ctrl+C to stop")
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            default_file = os.path.join(os.getcwd(), f"robot_data_{timestamp_str}.csv")
            print(f"Output will be saved to:\n{default_file}")
            
            # Set up signal handler
            signal.signal(signal.SIGINT, signal_handler)
            
            # Start collection
            start_collection(output_file=default_file)
        
    except KeyboardInterrupt:
        print("\nCollection stopped by user")
    except Exception as e:
        print(f"Error: {e}")
        print(f"Current working directory: {os.getcwd()}")  # Debug info
    finally:
        print("Program finished")