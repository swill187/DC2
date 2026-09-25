import sys

sys.path.insert(0, r"C:\Users\wwerner4\Documents\code\DC2\.out\build\def\Release")

import os
os.add_dll_directory(r"C:\Program Files\Xiris Automation Inc\Xiris WeldSDK 2\bin")
import xiris

print(xiris.__file__)

ip = xiris.detectCamera()

print(ip)