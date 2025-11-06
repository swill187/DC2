import pyaudio
import sounddevice as sd
import numpy as np
import csv
from datetime import datetime, timedelta
import threading
import time
import os

# Update recording parameters to match Microphone_csv_mod.py
FORMAT = pyaudio.paFloat32  # Changed from paInt16
CHANNELS = 1
RATE = 48000  # Changed from 44100
CHUNK = 1024

def find_microphone_by_name_and_api(name_pattern, api_id):
    """Find microphone that matches both the name pattern and API ID."""
    try:
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            dev_info = p.get_device_info_by_index(i)
            if (dev_info.get('maxInputChannels') > 0 and
                name_pattern.lower() in dev_info.get('name', '').lower() and
                dev_info.get('hostApi') == api_id):
                p.terminate()
                return i, dev_info
        p.terminate()
        return None, None
    except Exception as e:
        print(f"Error: {str(e)}")
        return None, None

def check_microphone():
    """Verify that the specific USB microphone is connected."""
    try:
        index, dev_info = find_microphone_by_name_and_api("485B39", 1)  # 1 for DirectSound
        return index is not None
    except Exception as e:
        print(f"Error checking microphone: {e}")
        return False

class MicrophoneRecorder:
    def __init__(self):
        """Initialize microphone recorder."""
        self.is_recording = False
        self.audio = pyaudio.PyAudio()
        self.device_index, self.device_info = find_microphone_by_name_and_api("485B39", 1)
        if self.device_index is None:
            raise ValueError("Specific microphone (485B39) not found")
        
        self.buffer_lock = threading.Lock()
        self.audio_buffer = []
        self.expected_samples = 0
        self.sample_count = 0
        self.last_callback_time = 0
        
    def start_recording(self, filename):
        """Start recording audio to specified file."""
        if self.is_recording:
            return False
            
        self.output_filename = filename
        self.audio_buffer = []
        self.is_recording = True
        self.start_time = datetime.now()
        self.sample_count = 0
        self.last_callback_time = time.perf_counter()
        
        def record_thread():
            try:
                self.stream = self.audio.open(
                    format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK,
                    input_device_index=self.device_index,
                    stream_callback=self._audio_callback
                )
                self.stream.start_stream()
                
                while self.is_recording:
                    current_time = time.perf_counter()
                    self.expected_samples = int((current_time - self.last_callback_time) * RATE)
                    time.sleep(0.1)
                    
            except Exception as e:
                print(f"Error in recording thread: {e}")
            finally:
                if self.stream:
                    self.stream.stop_stream()
                    self.stream.close()
                self._save_data()
                
        self.record_thread = threading.Thread(target=record_thread)
        self.record_thread.start()
        return True
        
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback function for audio stream."""
        if status:
            print(f"Status: {status}")
            
        if self.is_recording:
            try:
                current_time = time.perf_counter()
                data = np.frombuffer(in_data, dtype=np.float32)
                
                with self.buffer_lock:
                    # Only append if we haven't exceeded expected samples
                    if self.sample_count < self.expected_samples + RATE:  # Allow 1 second buffer
                        self.audio_buffer.append((data, current_time))
                        self.sample_count += len(data)
                    else:
                        print(f"Warning: Dropping samples, buffer full at {self.sample_count} samples")
                        
            except Exception as e:
                print(f"Error in audio callback: {e}")
                
        return (None, pyaudio.paContinue)
        
    def _save_data(self):
        """Process and save all recorded data with interpolated timestamps."""
        if not self.audio_buffer:
            return
            
        # Process audio data silently
        all_audio = []
        chunk_timestamps = []
        
        with self.buffer_lock:
            for data, ts in self.audio_buffer:
                all_audio.extend(data)
                chunk_timestamps.extend([ts] * len(data))
        
        # Trim to expected length if necessary
        if len(all_audio) > self.expected_samples:
            all_audio = all_audio[:self.expected_samples]
            chunk_timestamps = chunk_timestamps[:self.expected_samples]
        
        # Normalize audio data
        audio_array = np.array(all_audio)
        max_amplitude = np.max(np.abs(audio_array))
        if max_amplitude > 0:
            audio_array = audio_array / max_amplitude * 0.9
            
        # Create interpolated timestamps
        start_time = chunk_timestamps[0]
        sample_duration = 1.0 / RATE  # Time between individual samples
        
        # Generate proper interpolated timestamps
        interpolated_times = []
        current_chunk_start = 0
        
        while current_chunk_start < len(chunk_timestamps):
            # Find the end of the current chunk (where timestamp changes)
            current_ts = chunk_timestamps[current_chunk_start]
            chunk_end = current_chunk_start
            while (chunk_end < len(chunk_timestamps) and 
                   chunk_timestamps[chunk_end] == current_ts):
                chunk_end += 1
            
            # Calculate interpolated timestamps for this chunk
            chunk_size = chunk_end - current_chunk_start
            chunk_times = np.linspace(
                current_ts,
                current_ts + (chunk_size - 1) * sample_duration,
                chunk_size
            )
            interpolated_times.extend(chunk_times)
            current_chunk_start = chunk_end
        
        # Ensure we have the same number of timestamps as samples
        interpolated_times = interpolated_times[:len(audio_array)]
        relative_times = [t - start_time for t in interpolated_times]
        
        # Save to CSV
        with open(self.output_filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Recording Start Time', self.start_time.strftime('%Y-%m-%d %H:%M:%S.%f')])
            writer.writerow(['Relative Time (s)', 'Absolute Time', 'Amplitude'])
            
            for i, (rel_time, amplitude) in enumerate(zip(relative_times, audio_array)):
                abs_time = self.start_time + timedelta(seconds=rel_time)
                writer.writerow([f"{rel_time:.6f}", 
                               abs_time.strftime('%Y-%m-%d %H:%M:%S.%f'),
                               f"{amplitude:.6f}"])
        
        print("Audio data saved successfully")

    def stop_recording(self):
        """Stop recording."""
        if not self.is_recording:
            return False
        
        print("Stopping recording...")
        self.is_recording = False
        self.record_thread.join()
        return True