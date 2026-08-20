# generic imports
import math
import threading
import zarr
import numpy as np
import queue
import time

import PySpin

# project imports
import DC2_helpers

logger = DC2_helpers.init_logger(__name__)

class BaseSensor:
    """
    Virtual class representing an arbitrary sensor. The general workflow for a sensor is:
        initialize sensor variables -> detect sensor presence -> initialize sensor -> start sensor collection -> stop sensor collection
    """
    
    def __init__(self):
        
        self.name             = '' # name of sensor
        self.acquisition_rate = None # expected acquisition rate. Used to determine zarr chunk size
        self.shape            = (1,) # shape of a single sample. e.g. 64x64 image = (,64,64); 1D timeseries = (1,) 
        self.dtype            = np.float64
        self.columns          = tuple()
        
        self.flag_initialized   = False
        self.flag_is_collecting = False
        
        self.lock = threading.Lock()

        self.zarr_group   = None
        self.time_chunk   = None
        self.data_chunk   = None
        self.buffer_len   = None
        self.buffer_times = queue.Queue()
        self.buffers      = queue.Queue() # list of npy arrays of len buffer_len
        self.sample_time  = np.zeros((1,), dtype = np.uint64)
        self.sample       = None  # holds a single sample recorded by the sensor
    
    # implemented by child sensor class
    def detect(self):
        
        raise NotImplementedError
    
    def _get_chunk_sizes(self):
        
        # chunk to 1MB chunks (recommendation of zarr docs)
        self.time_chunk = (math.ceil(10 ** 6 / (math.prod(self.shape) * 8)), 1)     # TODO: what type are we using? Always float/int64?
        
        # if we are handling one/multiple 1D timeseries columns, chunk down each column separately (allow for selective column reads)
        if len(self.shape) < 2:
            self.data_chunk = (self.time_chunk[0],) + (1,)
        
        # if we are handling 2D+ data, don't bother to chunk in dimensions other than time
        else:
            self.data_chunk = (self.time_chunk[0],) + self.shape

        self.buffer_len = min(math.ceil(self.time_chunk[0] / 10), math.ceil(self.acquisition_rate * .5)) # buffer is the lesser of: 10% of a chunk size; amount of data collected in 5 seconds
    
    def initialize(self, zarr_group):
        
        self.sample = np.zeros(self.shape, dtype = self.dtype)  # holds a single sample recorded by the sensor
        self._get_chunk_sizes() # needed even when we aren't writing data to define self.buffer_len

        # init zarr group. if zarr_group is none, don't write any data
        if zarr_group is not None:
            
            self.group = zarr_group
            self.time = self.group.create_array(name = 'time', 
                                                shape = (0, 1), 
                                                chunks = self.time_chunk, 
                                                dimension_names = ('time', 'timestamp'),
                                                dtype = np.uint64)
            
            self.data = self.group.create_array(name = 'data', 
                                                shape = (0,) + self.shape, 
                                                chunks = self.data_chunk, 
                                                dimension_names = ('time',) + self.columns,
                                                dtype = self.dtype)
            
            self.group.attrs['acquisition_rate'] = self.acquisition_rate
        
        # implement sensor-specific initialization here. include metadata
    
    def start_collection(self):
        
        # check that collection is ready
        if not self.flag_initialized:

            logger.warning(f"{self.name} was not initialized before collection start.")
            
            try:
                self.initialize()
            except Exception as e:
                logger.error(e)
        
        with self.lock:
            self.flag_is_collecting = True # we aren't really collecting until we start the threads, but we were seeing a race condition on collection_thread()'s while condition

        # only write if desired
        if self.zarr_group is not None:
            self.writer_thread = threading.Thread(target = self.writer_thread)
            self.writer_thread.start()
        
        # start threaded collection
        self.collection_thread = threading.Thread(target = self.collection_thread)
        self.collection_thread.start()
    
    # implemented by child sensor class
    def collection_thread(self):

        with self.lock:
            flag_is_collecting = self.flag_is_collecting
            
        while flag_is_collecting:

            buffer      = np.zeros((self.buffer_len,) + self.shape)
            buffer_time = np.zeros((self.buffer_len, 1))

            for i in range(self.buffer_len):

                self.sample_sensor()
                buffer[i]      = self.sample
                buffer_time[i] = self.sample_time

            if self.zarr_group is not None:
                self.buffers.put(buffer)
                self.buffer_times.put(buffer_time)
                
            with self.lock:
                flag_is_collecting = self.flag_is_collecting
                
        return

    def sample_sensor(self):
        """
        Actually get a sample from the sensor. Implemented by child classes. Should update self.sample with a new sample and self.time with a new timestamp
        """

        raise NotImplementedError
    
    def writer_thread(self):

        while self.flag_is_collecting:

            time.sleep(.5)

            while not self.buffers.empty():
        
                self.data.append(self.buffers.get())
                self.time.append(self.buffer_times.get())
    
    # stop threaded process
    def stop_collection(self):

        with self.lock:
            flag_is_collecting = self.flag_is_collecting

        if self.flag_is_collecting:

            with self.lock:
                self.flag_is_collecting = False

            self.collection_thread.join()
            
            if self.zarr_group is not None:
                self.writer_thread.join()

        else:
            raise Exception(f"{self.name} is not collecting. It cannot be stopped!")

import pyaudio

class Microphone(BaseSensor):

    def __init__(self, mic_name = '485B39', api_id = 1):

        super(Microphone, self).__init__()

        self.name = 'Microphone'
        self.acquisition_rate = 48e3
        self.shape = (1,)

        self.pyaudio = pyaudio.PyAudio()
        self.mic_name = mic_name
        self.api_id   = 1

    def detect(self):

        for i in range(self.pyaudio.get_device_count()):

            mic = self.pyaudio.get_device_info_by_index(i)

            if mic.get('MaxInputChannels') > 0 and self.mic_name.lower in mic.get('name', '').lower() and mic.get('hostApi') == self.api_id:
                self.mic       = mic
                self.mic_index = i

        if self.mic is None:
            raise DC2_helpers.SensorNotConnectedError(sensor = self.name)

    def initialize(self, zarr_group):

        super().initialize(zarr_group)

        self.audio_stream = self.pyaudio.open(
            format = pyaudio.paFloat32,
            channels = 1,
            rate = self.acquisition_rate,
            input = True,
            frames_per_buffer = self.buffer_len,
            input_device_index=self.mic_index,
            stream_callback = self._audio_callback
        )

        self.flag_initialized = True

        ### TODO: Gonna need some different handling of buffers if pyaudio is natively buffering for us...

    


