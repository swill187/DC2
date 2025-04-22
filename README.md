# DC2
Development Cell Data Collection (DC2) is for collecting data on WAAM system with various sensors. Each sensor has relative timestamps and absolute timestamps based on the system clock of the computer.

## Microphone.py 
Collects microphone data in a CSV format. The microphone used for this is a PCB  Piezotronics Model 378B02 ICP Microphone System. The microphone collects data at 48000 Hz. The microphone data is processed in batches due to the high sample rate, so a single timestamp is taken for each batch and then individual sample timestamps are generated through interpolation.
## Thermocouple.py
Collects thermocouple data from an NI-9171 cDAQ with an NI-9211 temperature input module installed. The documentation says the NI-9211 has a max sample rate of 14 Hz, but in the code, it is specified as 3.5 Hz per channel (3.5 Hz per channel times 4 channels is 14 Hz overall). To be able to run this script, you need to have the appropriate NIDAQmx drivers for the DAQ module installed through NI-MAX. 
## RSI.py
Collects data from a KUKA robot over ethernet using UDP. The data comes in XML format. The data contained within the data string is configured on the KUKA robot using RSI Visual. The data is collected at the rate the data is sent by the robot. The KUKA can send RSI data at either 12ms (83.3 Hz) or 4ms (250 Hz) which is set in the KRL code for the KUKA to enable the RSI by specifying the IPO mode.
## LEMBox.py
Collects welding current and voltage data from a Miller LEM Box. Very little documentation is available for this system or how to acquire it, but inside of the LEM Box, there is a DT9816-S DAQ. The DT9816-S DAQ does not have a Python SDK, so the program to interface with it (LEMBOX.exe) was written and compiled in C using the DataAcq SDK. LEMBox.py calls LEMBox.exe functions as subprocesses withing DC2.py. LEM Box data is collected at 20000 Hz for each channel. The voltage and current data are off by a factor of 10 and 100 respectively (e.g. 1.93V would be 19.3V and 1.34A would be 134A). For this to work, the drivers for the DAQ must be installed to the computer. 
## FLIR.py 
Collects image frames from a FLIR a50 thermal camera and save them in a .npy format. The FLIR can collect data in two modes which determine which temperature range that it is capturing. One mode captures temperatures from -20C to 173C while the other mode captures 173C to 1000C. To run this script, both the Spinnaker SDK and the Python wrapper for the Spinnaker SDK (PySpin) must be installed. The FLIR GigE camera drivers must also be installed.
## Xiris.py
