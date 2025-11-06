cmake_minimum_required(VERSION 3.10.0)
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
include_directories("C:/Program Files/Xiris Automation Inc/Xiris WeldSDK 2/include")

add_library(WELDSDK SHARED IMPORTED)
set_target_properties(WELDSDK PROPERTIES
    IMPORTED_IMPLIB "C:/Program Files/Xiris Automation Inc/Xiris WeldSDK 2/lib/WeldSDK.lib"
    INTERFACE_INCLUDE_DIRECTORIES "C:/Program Files/Xiris Automation Inc/Xiris WeldSDK 2/include"
    INTERFACE_INCLUDE_DIRECTORIES "C:/Program Files/Xiris Automation Inc/Xiris WeldSDK 2/Samples/C++ Sample Projects/00_Common/include")

target_link_libraries(XIR1800Collection WELDSDK)

include(CTest)
enable_testing()



