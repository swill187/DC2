cmake_minimum_required(VERSION 3.10)
project(XIR1800DataAcq)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# SDK paths
set(WELDSDK_ROOT "C:/Program Files/Xiris Automation Inc/Xiris WeldSDK 2")
set(WELDSDK_SAMPLES "${WELDSDK_ROOT}/Samples/C++ Sample Projects")

# Include directories
include_directories(
    ${WELDSDK_ROOT}/Include
    ${WELDSDK_ROOT}/Include/WeldSDK
    ${WELDSDK_SAMPLES}/00_Common/include
)

# Link directories
link_directories(
    ${WELDSDK_ROOT}/Lib
)

add_executable(XIR1800Collection XIR-1800Collection.cpp)

# Link libraries
target_link_libraries(XIR1800Collection
    WeldSDK
    XAudioSDK
    XVideoStream
)