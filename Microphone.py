import pyaudio
import numpy as np
import time

import sensors
import DC2_helpers

logger = DC2_helpers.init_logger(__name__)

class Microphone(sensors.BaseSensor):

    def __init__(self, mic_name = '485B39', api_id = 1):

        super(Microphone, self).__init__()

        self.name = 'Microphone'
        self.acquisition_rate = 48e3
        self.shape = (1,)
        self.dtype = np.float64

        self.pyaudio = pyaudio.PyAudio()
        self.mic_name = mic_name
        self.api_id   = 1

        self.mic_index = None

    def detect(self):

        for i in range(self.pyaudio.get_device_count()):

            mic = self.pyaudio.get_device_info_by_index(i)

            if mic.get('MaxInputChannels') is not None and self.mic_name.lower in mic.get('name', '').lower() and mic.get('hostApi') == self.api_id:
                self.mic_index = i

        if self.mic_index is None:
            raise DC2_helpers.SensorNotConnectedError(sensor = self.name)

    def initialize(self, zarr_group):

        super(Microphone, self).initialize(zarr_group)

        self.sample       = np.zeros((self.buffer_len, 1), dtype = self.dtype) # sample actually holds a pyaudio buffer, not a single data sample
        self.sample_time  = np.zeros((self.buffer_len, 1), dtype = np.uint64)

        self.audio_stream = self.pyaudio.open(
            format = pyaudio.paFloat64,
            channels = 1,
            rate = self.acquisition_rate,
            input = True,
            frames_per_buffer = self.buffer_len,
            input_device_index=self.mic_index,
            stream_callback = self.sample_sensor
        )

        self.flag_initialized = True

    def collection_thread(self):

        with self.lock:
            flag_is_collecting = self.flag_is_collecting

        self.audio_stream.start_stream() # _audio_callback handles buffer stuff

        while flag_is_collecting:

            time.sleep(.5)

            with self.lock:
                flag_is_collecting = self.flag_is_collecting

        self.audio_stream.stop_stream()

    def sample_sensor(self, in_data, frame_count, time_info, status):
        """Callback function for audio stream."""

        if status:
            logger.error(f"Status: {status}")

        with self.lock:
            flag_is_collecting = self.flag_is_collecting

        if flag_is_collecting:
            try:
                sample_time = np.astype(((np.arange(self.len_buffer) * (1 / self.acquisition_rate)) + time_info['inputBufferAdcTime']) * 1e9, np.uint64) # construct timestamps for time based on time that the first sample in a buffer was recieved
                sample      = np.frombuffer(in_data, dtype=np.float64)

                if self.group is not None:

                    self.buffers.put(sample)
                    self.buffer_times.put(sample_time)
                        
            except Exception as e:
                print(f"Error in {self.name} audio callback: {e}")
                
        return (None, pyaudio.paContinue)

if __name__ == '__main__': 

    DC2_helpers.single_sensor_display(Microphone)