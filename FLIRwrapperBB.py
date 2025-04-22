"""
Author: Brett Brady
Email: brettbrady15@outlook.com

Description:
This script provides classes and methods for handling frames and calibration data from a FLIR thermal camera using the PySpin API. 
It includes functionalities for converting image data to temperature values, retrieving and setting calibration and environmental parameters, 
and managing camera acquisition and settings. The script also supports saving and loading calibration details and environmental variables to and from JSON files.
"""

import PySpin
import logging
import numpy as np
import json

logger=logging.getLogger()

class FrameHandler_BB:
    # @staticmethod
    # def save_frame(image_result, filename):
    #     """
    #     Saves the image frame to a file.

    #     Parameters:
    #         image_result: The image result to save.
    #         filename: The filename to save the image to.

    #     Returns:
    #         True if saving is successful, False otherwise.
    #     """
    #     try:
    #         image_result.Save(filename)
    #         return True
    #     except Exception as e:
    #         print(f"Error saving frame: {e}")
    #         return False
    
    # @staticmethod
    # def release_frame(image_result):
    #     """
    #     Releases the frame resources.

    #     Parameters:
    #         image_result: The image result to release.
    #     """
    #     image_result.Release()

    @staticmethod
    def convert_to_C(image_data, calibration, env):
        # Transforming the data array into a pseudo radiance array, if streaming mode is set to Radiometric.
        # and then calculating the temperature array (degrees Celsius) with the full thermography 
        
        B =  calibration.B,
        R =  calibration.R,
        J0 = calibration.J0,
        J1 = calibration.J1,
        F =  calibration.F,
        Tau = env.Tau,
        Emiss = env.Emiss,
        K2 = env.K2
        
        image_Radiance = (image_data - J0) / J1
        image_Temp = (B / np.log(R / ((image_Radiance / Emiss / Tau) - K2) + F)) - 273.15
        return image_Temp


class Calibrate_BB:
    @staticmethod
    def get_calibration_details(calibration, nodemap):
        """
        Retrieves calibration details and populates the provided calibration object. Cam must be in Acquistion mode.

        Parameters:
           calibration: An object to store calibration details.
           nodemap: The nodemap containing calibration nodes.

        Returns:
            None
        """
        CalibrationQueryR_node = PySpin.CFloatPtr(nodemap.GetNode('R'))
        calibration.R = CalibrationQueryR_node.GetValue()

        CalibrationQueryB_node = PySpin.CFloatPtr(nodemap.GetNode('B'))
        calibration.B = CalibrationQueryB_node.GetValue()

        CalibrationQueryF_node = PySpin.CFloatPtr(nodemap.GetNode('F'))
        calibration.F = CalibrationQueryF_node.GetValue()

        CalibrationQueryX_node = PySpin.CFloatPtr(nodemap.GetNode('X'))
        calibration.X = CalibrationQueryX_node.GetValue()

        CalibrationQueryA1_node = PySpin.CFloatPtr(nodemap.GetNode('alpha1'))
        calibration.A1 = CalibrationQueryA1_node.GetValue()

        CalibrationQueryA2_node = PySpin.CFloatPtr(nodemap.GetNode('alpha2'))
        calibration.A2 = CalibrationQueryA2_node.GetValue()

        CalibrationQueryB1_node = PySpin.CFloatPtr(nodemap.GetNode('beta1'))
        calibration.B1 = CalibrationQueryB1_node.GetValue()

        CalibrationQueryB2_node = PySpin.CFloatPtr(nodemap.GetNode('beta2'))
        calibration.B2 = CalibrationQueryB2_node.GetValue()

        CalibrationQueryJ1_node = PySpin.CFloatPtr(nodemap.GetNode('J1'))    # Gain
        calibration.J1 = CalibrationQueryJ1_node.GetValue()

        CalibrationQueryJ0_node = PySpin.CIntegerPtr(nodemap.GetNode('J0'))   # Offset
        calibration.J0 = CalibrationQueryJ0_node.GetValue()

class EnvHandler_BB:
    @staticmethod
    def set_default_env(env):
        """
        Sets the default environmental parameters in the provided environment object.

        Parameters:
            env: The environment object to set default parameters for.

        Returns:
            The environment object with default parameters set.
        """
        env.Emiss = 0.97
        env.TRefl = 293.15
        env.TAtm = 293.15
        env.TAtmC = env.TAtm - 273.15
        env.Humidity = 0.55
        env.Dist = 2
        env.ExtOpticsTransmission = 1
        env.ExtOpticsTemp = env.TAtm
        return env

    @staticmethod
    def calc_env(env, calibration):
        """
        Calculates environment parameters using calibration details.

        Parameters:
            env: The environment object.
            calibration: An object containing calibration details.

        Returns:
            The environment object with calculated parameters.
        """
        env.H2O = env.Humidity * np.exp(1.5587 + 0.06939 * env.TAtmC - 0.00027816 * env.TAtmC * env.TAtmC + 0.00000068455 * env.TAtmC * env.TAtmC * env.TAtmC)

        env.Tau = calibration.X * np.exp(-np.sqrt(env.Dist) * (calibration.A1 + calibration.B1 * np.sqrt(env.H2O))) + (1 - calibration.X) * np.exp(-np.sqrt(env.Dist) * (calibration.A2 + calibration.B2 * np.sqrt(env.H2O)))

        # Pseudo radiance of the reflected environment
        env.r1 = ((1 - env.Emiss) / env.Emiss) * (calibration.R / (np.exp(calibration.B / env.TRefl) - calibration.F))

        # Pseudo radiance of the atmosphere
        env.r2 = ((1 - env.Tau) / (env.Emiss * env.Tau)) * (calibration.R / (np.exp(calibration.B / env.TAtm) - calibration.F))

        # Pseudo radiance of the external optics
        env.r3 = ((1 - env.ExtOpticsTransmission) / (env.Emiss * env.Tau * env.ExtOpticsTransmission)) * (calibration.R / (np.exp(calibration.B / env.ExtOpticsTemp) - calibration.F))

        env.K2 = env.r1 + env.r2 + env.r3
        return env

    @staticmethod
    def create_JSON(env, calibration, filepath):
        """
        Creates a JSON file containing FLIR variables.

        Parameters:
            env: The environment object.
            calibration: An object containing calibration details.
            filepath: The filepath to save the JSON file to.
        """
        data = {
            "B":  calibration.B,
            "R": calibration.R,
            "J0": calibration.J0,
            "J1": calibration.J1,
            "F": calibration.F,
            "H20": env.H2O,
            "Tau": env.Tau,
            "Emiss": env.Emiss,
            "r1": env.r1,
            "r2": env.r2,
            "r3": env.r3,
            "K2": env.K2
        }
        json_file_path = filepath + "\FLIR_Variables.json"
        print("Creating FLIR Variables file...")
        with open(json_file_path, "w") as json_file:
            json.dump(data, json_file)
        
        return True
    
    @staticmethod
    def load_JSON(filepath):
        """
        Loads FLIR variables from a JSON file.

        Parameters:
            filepath: The filepath to load the JSON file from.

        Returns:
            A tuple containing the environment object and the calibration object.
        """
        with open(filepath, "r") as json_file:
            data = json.load(json_file)

        env = {
            "H2O": data["H20"],
            "Tau": data["Tau"],
            "Emiss": data["Emiss"],
            "r1": data["r1"],
            "r2": data["r2"],
            "r3": data["r3"],
            "K2": data["K2"]
        }

        calibration = {
            "B": data["B"],
            "R": data["R"],
            "J0": data["J0"],
            "J1": data["J1"],
            "F": data["F"]
        }

        return env, calibration


class FLIRCAMERA:
    """FLIR Captured"""
    # constructor
    def __init__(self):
        """Initializer with default parameters for FLIR A50"""

        self.system = PySpin.System.GetInstance()
        self.cam_list = self.system.GetCameras()
        self.cam = self.cam_list[0] # set camera
        self.sNodemap = self.cam.GetTLStreamNodeMap()
        self.nodemap_tldevice = self.cam.GetTLDeviceNodeMap()
        self.cam.Init()
        self.nodemap = self.cam.GetNodeMap()

        # Change bufferhandling mode to NewestOnly
        self.node_bufferhandling_mode = PySpin.CEnumerationPtr(self.sNodemap.GetNode('StreamBufferHandlingMode'))

        self.node_pixel_format = PySpin.CEnumerationPtr(self.nodemap.GetNode('PixelFormat'))
        node_pixel_format_mono16 = PySpin.CEnumEntryPtr(self.node_pixel_format.GetEntryByName('Mono16'))
        pixel_format_mono16 = node_pixel_format_mono16.GetValue()
        self.node_pixel_format.SetIntValue(pixel_format_mono16)

        if not PySpin.IsAvailable(self.node_bufferhandling_mode) or not PySpin.IsWritable(self.node_bufferhandling_mode):
            logger.critical("Unable to set stream buffer handling mode.. Aborting...")
            raise Exception("Camera Error")

        # Retrieve entry node from enumeration node
        node_newestonly = self.node_bufferhandling_mode.GetEntryByName('NewestOnly')
        if not PySpin.IsAvailable(node_newestonly) or not PySpin.IsReadable(node_newestonly):
            logger.critical("Unable to set stream buffer handling mode.. Aborting...")
            raise Exception("Camera Error")

        # Retrieve integer value from entry node
        self.node_newestonly_mode = node_newestonly.GetValue()

        # Set integer value from entry node as new value of enumeration node
        self.node_bufferhandling_mode.SetIntValue(self.node_newestonly_mode)

        self.node_acquisition_mode = PySpin.CEnumerationPtr(self.nodemap.GetNode('AcquisitionMode'))
        if not PySpin.IsAvailable(self.node_acquisition_mode) or not PySpin.IsWritable(self.node_acquisition_mode):
            logger.critical("Unable to set acquisition mode to continuous (enum retrieval). Aborting...")
            raise Exception("Enum error")

        # Retrieve entry node from enumeration node
        self.node_acquisition_mode_continuous = self.node_acquisition_mode.GetEntryByName('Continuous')
        if not PySpin.IsAvailable(self.node_acquisition_mode_continuous) or not PySpin.IsReadable(
                self.node_acquisition_mode_continuous):
            print('Unable to set acquisition mode to continuous (entry retrieval). Aborting...')
            raise Exception("Enum error")

        # Retrieve integer value from entry node
        self.acquisition_mode_continuous = self.node_acquisition_mode_continuous.GetValue()

        # Set integer value from entry node as new value of enumeration node
        self.node_acquisition_mode.SetIntValue(self.acquisition_mode_continuous)

    def set_IRFormatType(self):
        """
        Sets the IR format type.
        """
        class IRFormatType:
            LINEAR_10MK = 1
            LINEAR_100MK = 2
            RADIOMETRIC = 3

        self.CHOSEN_IR_TYPE = IRFormatType.RADIOMETRIC
         # Set IR Format Type
        if self.CHOSEN_IR_TYPE == IRFormatType.LINEAR_10MK:
            # This section is to be activated only to set the streaming mode to TemperatureLinear10mK
            node_IRFormat = PySpin.CEnumerationPtr(self.nodemap.GetNode('IRFormat'))
            node_temp_linear_high = PySpin.CEnumEntryPtr(node_IRFormat.GetEntryByName('TemperatureLinear10mK'))
            node_temp_high = node_temp_linear_high.GetValue()
            self.node_IRFormat.SetIntValue(node_temp_high)
        elif self.CHOSEN_IR_TYPE == IRFormatType.LINEAR_100MK:
            # This section is to be activated only to set the streaming mode to TemperatureLinear100mK
            node_IRFormat = PySpin.CEnumerationPtr(self.nodemap.GetNode('IRFormat'))
            node_temp_linear_low = PySpin.CEnumEntryPtr(node_IRFormat.GetEntryByName('TemperatureLinear100mK'))
            node_temp_low = node_temp_linear_low.GetValue()
            self.node_IRFormat.SetIntValue(node_temp_low)
        elif self.CHOSEN_IR_TYPE == IRFormatType.RADIOMETRIC:
            # This section is to be activated only to set the streaming mode to Radiometric
            self.node_IRFormat = PySpin.CEnumerationPtr(self.nodemap.GetNode('IRFormat'))
            node_temp_radiometric = PySpin.CEnumEntryPtr(self.node_IRFormat.GetEntryByName('Radiometric'))
            node_radiometric = node_temp_radiometric.GetValue()
            self.node_IRFormat.SetIntValue(node_radiometric)

        return self

    def set_Emiss(env, value):
        """
        Sets the emissivity value in the environment and prints the value set.

        Parameters:
            env: The environment object to set the emissivity value.
            value: The value to set for emissivity.

        Returns:
            The emissivity value set.
        """
        env.Emiss = value
        print("Emiss set to: ", value)
        return env.Emiss

    def set_TRefl(env, value):
        """
        Sets the TRefl (Reflectance Temperature) value in the environment and prints the value set.

        Parameters:
            env: The environment object to set the TRefl value.
            value: The value to set for TRefl.

        Returns:
            The TRefl value set.
        """
        env.TRefl = value
        print("TRefl set to: ", value, " K")
        return env.TRefl
        
    def set_TAtm(env, value):
        """
        Sets the atmospheric temperature value in the environment, converts it to Celsius, sets the external optics temperature, and prints the values set.

        Parameters:
            env: The environment object to set the temperature values.
            value: The value to set for atmospheric temperature.

        Returns:
            Tuple containing the atmospheric temperature in Kelvin, Celsius, and external optics temperature.
        """
        env.TAtm = value
        print("TAtm set to: ", value, " K")
        env.TAtmC = value - 273.15
        print("TAtmC set to: ", value, " deg C")
        env.ExtOpticsTemp = env.TAtm
        print("ExtOpticsTemp set to: ", value, " K")
        return env.TAtm, env.TAtmC, env.ExtOpticsTemp
        
    def set_Humidity(env, value):
        """
        Sets the humidity value in the environment and prints the value set.

        Parameters:
            env: The environment object to set the humidity value.
            value: The value to set for humidity.

        Returns:
            The humidity value set.
        """
        env.Humidity = value
        print("Humidity set to: ", value)
        return env.Humidity

    def set_Dist(env, value):
        """
        Sets the distance value from the camera to the object and prints the value set.

        Parameters:
            env: The environment object to set the distance value.
            value: The value to set for distance.

        Returns:
            The distance value set.
        """    
        env.Dist = value
        print("Dist set to: ", value, " m")
        return env.Dist

    def set_ExtOpticsTransmission(env, value):
        """
        Sets the external optics transmission value in the environment and prints the value set.

        Parameters:
            env: The environment object to set the external optics transmission value.
            value: The value to set for external optics transmission.

        Returns:
            The external optics transmission value set.
        """
        env.ExtOpticsTransmission = value
        print("ExtOpticsTransmission set to: ", value)
        return env.ExtOpticsTransmission

    def uninitialize(self):
        """
        Uninitializes camera and releases resources.
        """
        cam = self.cam
        cam.EndAcquisition()
        cam.DeInit()
        self.cam_list.Clear()
        del cam
        # self.system.ReleaseInstance()

    def intializeAcquition(self):
        """
        Initializes camera acquisition.
        """
        self.cam.BeginAcquisition()  # Remove the print statement
        return True

    def get_frame(self):
        """
        Retrieves the next frame from the camera.

        Returns:
            A tuple containing the image result and the timestamp.
        """  
        image_result = self.cam.GetNextImage()
        if image_result.IsIncomplete():
                print('Image incomplete with image status %d ...' % image_result.GetImageStatus())
        image_data = image_result.GetNDArray()
        time = image_result.GetTimeStamp()
        image_result.Release()

        return image_data, time


