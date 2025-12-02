cmake_minimum_required(VERSION 3.10.0)

# Set vcpkg toolchain
set(CMAKE_TOOLCHAIN_FILE "C:/Users/wwerner4/Documents/code/vcpkg/vcpkg/scripts/buildsystems/vcpkg.cmake" CACHE STRING "")

project(DC2 VERSION 0.1.0 LANGUAGES C CXX)

add_executable(LEMBOX ./LemBox/LEMBOX.c)

add_library(OLMEM SHARED IMPORTED)
set_target_properties(OLMEM PROPERTIES
    IMPORTED_IMPLIB "C:/Program Files (x86)/Data Translation/Win32/SDK/Lib64/OLMEM64.lib"
    INTERFACE_INCLUDE_DIRECTORIES "C:/Program Files (x86)/Data Translation/Win32/SDK/Include")

add_library(OLDAAPI SHARED IMPORTED)
set_target_properties(OLDAAPI PROPERTIES
    IMPORTED_IMPLIB "C:/Program Files (x86)/Data Translation/Win32/SDK/Lib64/oldaapi64.lib"
    INTERFACE_INCLUDE_DIRECTORIES "C:/Program Files (x86)/Data Translation/Win32/SDK/Include")

target_link_libraries(LEMBOX OLMEM)
target_link_libraries(LEMBOX OLDAAPI)

add_executable(XIR1800Collection ./Xiris/XIR-1800Collection.cpp)

add_library(WELDSDK SHARED IMPORTED)
set_target_properties(WELDSDK PROPERTIES
    IMPORTED_IMPLIB "C:/Program Files/Xiris Automation Inc/Xiris WeldSDK 2/lib/WeldSDK.lib"
    INTERFACE_INCLUDE_DIRECTORIES "C:/Program Files/Xiris Automation Inc/Xiris WeldSDK 2/include;C:/Program Files/Xiris Automation Inc/Xiris WeldSDK 2/Samples/C++ Sample Projects/00_Common/include")

target_include_directories(XIR1800Collection PRIVATE 
    "C:/Program Files/Xiris Automation Inc/Xiris WeldSDK 2/include"
    "C:/Program Files/Xiris Automation Inc/Xiris WeldSDK 2/Samples/C++ Sample Projects/00_Common/include")

target_link_libraries(XIR1800Collection WELDSDK)

# FFmpeg libraries from vcpkg
set(FFMPEG_INSTALL_DIR "C:/Users/wwerner4/Documents/code/vcpkg/vcpkg/installed/x64-windows")
target_include_directories(XIR1800Collection PRIVATE "${FFMPEG_INSTALL_DIR}/include")
target_link_directories(XIR1800Collection PRIVATE "${FFMPEG_INSTALL_DIR}/lib")
target_link_libraries(XIR1800Collection avutil avcodec avformat swscale)



