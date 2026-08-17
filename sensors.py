import math
import threading
import zarr
import numpy as np
import queue
import time

import nidaqmx

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
        self.dtype            = zarr.dtype.Float64
        self.columns          = tuple()
        
        self.flag_is_connected  = False
        self.flag_initialized   = False
        self.flag_is_collecting = False

        self.time_chunk   = None
        self.data_chunk   = None
        self.buffer_len   = None
        self.buffer_times = queue.Queue()
        self.buffers      = queue.Queue() # list of npy arrays of len buffer_len
        self.sample_time  = np.zeros((1,), dtype = np.datetime64)
        self.sample       = np.zeros(self.shape, dtype = self.dtype.to_numpy_dtype())  # holds a single sample recorded by the sensor
    
    # implemented by child sensor class
    def detect(self):
        
        raise NotImplementedError
    
    def _get_chunk_sizes(self):
        
        # chunk to 1MB chunks (recommendation of zarr docs)
        self.time_chunk = math.ceil(10 ** 6 / (math.prod(self.shape) * 8))     # TODO: what type are we using? Always float/int64?
        
        # if we are handling one/multiple 1D timeseries columns, chunk down each column separately (allow for selective column reads)
        if len(self.shape) < 2:
            self.data_chunk = self.time_chunk[0] + (1,)
        
        # if we are handling 2D+ data, don't bother to chunk in dimensions other than time
        else:
            self.data_chunk = self.time_chunk[0] + self.shape

        self.buffer_len = math.ceil(self.time_chunk / 10)
    
    def initialize(self, zarr_group):

        self._get_chunk_sizes()
        
        self.group = zarr_group
        self.time = self.group.create_array(name = 'time', 
                                            shape = (0, 1), 
                                            chunks = self.time_chunk, 
                                            dimension_names = ('time', 'timestamp'),
                                            dtype = zarr.dtype.Datetime64)
        
        self.data = self.group.create_array(name = 'data', 
                                            shape = (0,) + self.shape, 
                                            chunks = self.data_chunk, 
                                            dimension_names = ('time',) + self.columns,
                                            dtype = self.dtype)
        
        self.group['acquisition_rate'] = self.acquisition_rate
        
        # implement sensor-specific initialization here. include metadata
    
    def start_collection(self):
        
        # check that collection is ready
        if not self.flag_initialized:

            logger.warning(f"{self.name} was not initialized before collection start.")
            
            try:
                self.initialize()
            except Exception as e:
                logger.error(e)
        
        # start threaded collection
        self.collection_thread = threading.Thread(target = self.collection_thread)
        self.writer_thread     = threading.Thread(target = self.writer_thread)

        self.collection_thread.start()
        self.writer_thread.start()
        
        self.flag_is_collecting = True
    
    # implemented by child sensor class
    def collection_thread(self):

        while self.flag_is_collecting:

            buffer      = np.zeros((self.buffer_len,) + self.shape)
            buffer_time = np.zeros(self.buffer_len, 1)

            for i in range(self.buffer_len):

                self.sample_sensor()
                buffer[i]      = self.sample
                buffer_time[i] = self.sample_time

            self.buffers.put(buffer)
            self.buffer_times.put(buffer_time)

    def sample_sensor(self):
        """
        Actually get a sample from the sensor. Implemented by child classes. Should update self.sample with a new sample and self.time with a new timestamp
        """

        raise NotImplementedError
    
    def writer_thread(self):

        while self.flag_is_collecting:

            time.sleep(.5)

            while not self.buffers.empty():
        
                self.time.append(self.buffers.get())
                self.data.append(self.buffer_times.get())
    
    # stop threaded process
    def stop_collection(self):

        if self.flag_is_collecting:

            self.flag_is_collecting = False

            self.collection_thread.join()
            self.writer_thread.join()

        else:
            raise Exception(f"{self.name} is not collecting. It cannot be stopped!")
        
class ThermocoupleDAQ(BaseSensor):
    
    def __init__(self):
        
       super(ThermocoupleDAQ, self).__init__()

       self.name             = 'ThermocoupleDAQ'
       self.acquisition_rate = 3.5 # Hz
       self.shape            = (4,) # each sample of the sensor produces 4 values
       self.columns          = ('Channel 0 (C)', 'Channel 1 (C)', 'Channel 2 (C)', 'Channel 3 (C)')

       self.device = None
       self.task = None

    def detect(self):

        system = nidaqmx.system.System.local()

        if len(system.devices) > 1:
            logger.error("Multiple NI devices detected. Support for multiple devices is not implemented. Connecting to first detected device...")

        if len(system.devices) == 1:
            self.device = system.devices[0]
            return True

        else:
            raise DC2_helpers.SensorNotConnectedError(sensor = self.name)

    def initialize(self, zarr_group):

        super().initialize(zarr_group)

        try:

            self.task = nidaqmx.Task()

            for i in range(4):

                channel = f"{self.device_name}/ai{i}"

                self.task.ai_channels.add_ai_thrmcpl_chan(channel,
                                                          name_to_assign_to_channel = f"Thermocouple_{i}",
                                                          thermocouple_type = nidaqmx.constants.ThermocoupleType.K,
                                                          units = nidaqmx.constants.TemperatureUnits.DEG_C)
            
            self.task.timing.cfg_samp_clk_timing(rate = self.sample_rate,
                                                 sample_mode = nidaqmx.constants.AcquisitionType.CONTINUOUS,
                                                 samps_per_chan = 1)

            self.flag_initialized = True

        except Exception as e:

            logger.error(f"Error initializing ThermocoupleDAQ: {e}")

    def sample_sensor(self):

        try:
            self.sample[:] = self.task.read()
            self.sample_time[:] = time.time()
        except nidaqmx.errors.Error as e:
            print(f"Error reading thermocouple: {e}")


    