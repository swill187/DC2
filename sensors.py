import math
import threading
import zarr

import DC2_helpers

logger = DC2_helpers.init_logger(__name__)

class BaseSensor:
    """
    Virtual class representing an arbitrary sensor. The general workflow for a sensor is:
        initialize sensor variables -> detect sensor presence -> initialize sensor -> start sensor collection -> stop sensor collection
    """
    
    def __init__(self):
        
        self.name = '' # name of sensor
        self.acquisition_rate = None # expected acquisition rate. Used to determine zarr chunk size
        self.shape = (1,) # shape of a single sample. e.g. 64x64 image = (,64,64); 1D timeseries = (1,) 
        self.dtype = zarr.dtype.Float64
        
        self.flag_is_connected  = False
        self.flag_initialized   = False
        self.flag_is_collecting = False
        
        self.get_chunk_sizes()
    
    # implemented by child sensor class
    def detect(self):
        
        raise NotImplementedError
    
    def get_chunk_sizes(self):
        
        # chunk to 1 second or 2048 samples, whatever comes sooner
        self.time_chunk = (min(math.ceil(self.acquisition_rate), 2048), 1)
        
        # if we are handling one/multiple 1D timeseries columns, chunk down each column separately (allow for selective column reads)
        if len(self.shape) < 2:
            self.data_chunk = self.time_chunk[0] + (1,)
        
        # if we are handling 2D+ data, don't bother to chunk in dimensions other than time
        else:
            self.data_chunk = self.time_chunk[0] + self.shape
    
    # build empty 
    def setup_zarr(self):
        
        self.time = self.group.create_array(name = 'time', 
                                            shape = (0, 1), 
                                            chunks = self.time_chunk, 
                                            dtype = zarr.dtype.Datetime64)
        
        self.data = self.group.create_array(name = 'data', 
                                            shape = (0,) + self.shape, 
                                            chunks = self.data_chunk, 
                                            dtype = self.dtype)
    
    def initialize(self, zarr_group):
        
        self.group = zarr_group
        self.setup_zarr()
        
        self.group['acquisition_rate'] = self.acquisition_rate
        
        # implement sensor-specific initialization here. include metadata
    
    def start_collection(self):
        
        # check that collection is ready
        if not self.flag_initialized:
            
            try:
                self.initialize()
            except Exception as e:
                logger.error(e)
        
        # start threaded collection
        self.thread = threading.Thread(target=self.collection_thread)
        self.thread.start()
        
        self.flag_is_collecting = True
    
    # implemented by child sensor class
    def collection_thread(self):
        
        # do some collection, then when buffer is full write it w/ write_data()
        
        raise NotImplementedError
    
    def write_data(self, time_batch, data_batch):
        
        self.time.append(time_batch)
        self.data.append(data_batch)
    
    # stop threaded process
    def stop_collection(self):
        
        self.thread.join()
        
        self.flag_is_collecting = False
        
class ThermocoupleDAQ(BaseSensor):
    
    def __init__(self):
        
       super(ThermocoupleDAQ, self).__init__()