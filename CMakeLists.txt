cmake_minimum_required(VERSION 3.15...3.27)
project(DC2)

if (CMAKE_VERSION VERSION_LESS 3.18)
  set(DEV_MODULE Development)
else()
  set(DEV_MODULE Development.Module)
endif()

message(STATUS "C++ Compiler ID: ${CMAKE_CXX_COMPILER_ID}")
message(STATUS "C++ Compiler Version: ${CMAKE_CXX_COMPILER_VERSION}")

if (NOT DataAcqSDK_ROOT)
    message(FATAL_ERROR
        "DataAcqSDK_ROOT is not set. Pass -DDataAcqSDK_ROOT=<sdk root> "
        "or set it in CMakeUserPresets.json.")
endif()

if (NOT EXISTS "${DataAcqSDK_ROOT}/Include/oldaapi.h")
    message(FATAL_ERROR "oldaapi.h not found under ${DataAcqSDK_ROOT}")
endif()

find_package(Python 3.12 COMPONENTS Interpreter ${DEV_MODULE} REQUIRED)

if (NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Choose the type of build." FORCE)
  set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS "Debug" "Release" "MinSizeRel" "RelWithDebInfo")
endif()

# Detect the installed nanobind package and import it into CMake
execute_process(
  COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
  OUTPUT_STRIP_TRAILING_WHITESPACE OUTPUT_VARIABLE nanobind_ROOT)
find_package(nanobind CONFIG REQUIRED)

add_library(OLDAAPI SHARED IMPORTED)
set_target_properties(OLDAAPI PROPERTIES
    IMPORTED_IMPLIB     "${DataAcqSDK_ROOT}/lib64/oldaapi64.lib"
    IMPORTED_LOCATION   "C:/Windows/System32/oldaapi64.dll"
    INTERFACE_INCLUDE_DIRECTORIES "${DataAcqSDK_ROOT}/Include"
)

add_library(OLMEM SHARED IMPORTED)
set_target_properties(OLMEM PROPERTIES
    IMPORTED_IMPLIB     "${DataAcqSDK_ROOT}/lib64/OLMEM64.lib"
    IMPORTED_LOCATION   "C:/Windows/System32/olmem64.dll.dll"
    INTERFACE_INCLUDE_DIRECTORIES "${DataAcqSDK_ROOT}/Include"
)

nanobind_add_module(lembox STABLE_ABI NB_STATIC lembox.cpp)
target_link_libraries(lembox PRIVATE OLDAAPI OLMEM)