#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <direct.h> 
#include <fstream>
#include <atomic>
#include <csignal>
#include <windows.h>  // For MAX_PATH
#include <cstring>    // For strerror
#include "SampleCameraDetection.h"
#include "XirisCommon/XImage.h"
#include "XImageLib/Image/XImageUtil.h"
#include "WeldSDK/WeldCamera.h"
#include "XImageLib/Image/CRawImage.h"
#include "XVideoRecorderLib/XVideoRecorder.h"  

// Disable CRT secure warnings
#pragma warning(disable: 4996)

// Global flag for signal handling
static std::atomic<bool> running{true};

void signal_handler(int signal) {
    running = false;
}

class XirisCollector : public SampleCamera {
private:
    std::string outputPath;
    bool recordRaw;
    bool recordPng;
    bool isReady;
    bool isRecording;
    bool isInitialized;
    std::string connectedIP;

    // Static members without inline initialization
    static std::shared_ptr<XirisCollector> instance;
    static const char* CONNECTION_FILE;

public: 
    // Add public method to check connection file
    static bool CheckConnectionFile() {
        std::ifstream test(CONNECTION_FILE);
        return test.good();
    }

    bool ConfigureCamera() {
        try {
            std::cout << "Configuring camera..." << std::endl;
            
            // Reset time stamps and frame counter first
            ResetTimeStamps();
            ResetFrameCounter();
            
            // Start with pixel depth setting
            setPixelDepth(WeldSDK::PixelDepths::Bpp14);
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            
            // Enable FFC first for better initialization
            setFFCEnabled(true);
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            
            setShutterMode(WeldSDK::ShutterModes::Global);
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            
            // Use AutoGain for testing
            setAutoGainMode(WeldSDK::AutoControlModes::Continuous);
            std::cout << "Set to AutoGain Mode mode for testing" << std::endl;
            std::this_thread::sleep_for(std::chrono::milliseconds(100));

            // Ensure frame rate is not limited
            setGSFrameRateLimitEnabled(false);
            
            // Get and print maximum frame rate
            double maxFps = getGSMaxFrameRate();
            std::cout << "Maximum frame rate: " << maxFps << " FPS" << std::endl;
            
            return true;
        }
        catch (const std::exception& e) {
            std::cerr << "Error configuring camera: " << e.what() << std::endl;
            return false;
        }
    }

    XirisCollector(std::string ip, WeldSDK::CameraClass type) :  
        SampleCamera(ip, type),
        outputPath(""),     
        recordRaw(true),    
        recordPng(true),
        isReady(false),
        isRecording(false),
        isInitialized(false),
        connectedIP(ip)
    { }

    bool Connect() {
        std::cout << "Attempting to connect to camera..." << std::endl;
        
        // First try to disconnect any existing connections
        try {
            Disconnect();
            std::this_thread::sleep_for(std::chrono::seconds(1));
        } catch (...) { }
        
        const int CONNECTION_TIMEOUT = 30;  // seconds
        auto start_time = std::chrono::steady_clock::now();
        
        while (true) {
            if (SampleCamera::Connect()) {
                std::cout << "Base connection successful, waiting for stability..." << std::endl;
                std::this_thread::sleep_for(std::chrono::seconds(2));
                
                // Configure and start streaming
                isInitialized = ConfigureCamera();
                if (isInitialized) {
                    std::cout << "Camera configured successfully" << std::endl;
                    if (!Start()) {
                        std::cout << "Failed to start streaming" << std::endl;
                        continue;
                    }
                    
                    // Wait for streaming to stabilize
                    std::this_thread::sleep_for(std::chrono::seconds(2));
                    WriteConnectionState(connectedIP);
                    return true;
                }
            }
            
            // Check timeout
            auto current = std::chrono::steady_clock::now();
            auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(current - start_time).count();
            if (elapsed >= CONNECTION_TIMEOUT) {
                std::cerr << "Connection attempt timed out after " << CONNECTION_TIMEOUT << " seconds" << std::endl;
                break;
            }
            
            std::cout << "Retrying connection..." << std::endl;
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
        
        return false;
    }

    bool isConnected() {
        // Check if we can still communicate with the camera
        try {
            // Try to read a basic property
            getTraceFlags();
            return true;
        }
        catch (...) {
            return false;
        }
    }

    void StopRecording() {
        if (isRecording) {
            isRecording = false;
            std::cout << "Recording stopped" << std::endl;
        }
    }

    static std::shared_ptr<XirisCollector> DetectCamera() {
        //std::cout << "Starting camera detection..." << std::endl;
        auto camera = DetectACamera<XirisCollector>();
        if (camera) {
            // Store IP immediately when detected
            camera->connectedIP = camera->IPAddress();
            //std::cout << "Detected camera with IP: " << camera->connectedIP << std::endl;
            std::cout << "\nDetected camera with IP: " << camera->IPAddress() << std::endl;
            return camera;
        }
        std::cout << "No camera detected" << std::endl;
        return nullptr;
    }

    void SetOutputPath(const std::string& path) {  
        outputPath = path;
        std::cout << "Setting output path to: " << path << std::endl;
        
        // Create full path
        char fullPath[MAX_PATH];
        if (_fullpath(fullPath, path.c_str(), MAX_PATH) != nullptr) {
            outputPath = fullPath;
        }
        
        // Create base directory first
        if (_mkdir(outputPath.c_str()) != 0 && errno != EEXIST) {
            std::cerr << "Failed to create base directory: " << strerror(errno) << std::endl;
            return;
        }

        // Create subdirectories
        std::string rawDir = outputPath + "/raw";
        std::string pngDir = outputPath + "/png";
        
        if (recordRaw) {
            if (_mkdir(rawDir.c_str()) != 0 && errno != EEXIST) {
                std::cerr << "Failed to create RAW directory: " << strerror(errno) << std::endl;
            }
        }
        
        if (recordPng) {
            if (_mkdir(pngDir.c_str()) != 0 && errno != EEXIST) {
                std::cerr << "Failed to create PNG directory: " << strerror(errno) << std::endl;
            }
        }
        
        isReady = true;
        std::cout << "Ready for recording at: " << outputPath << std::endl;
    }

    void SetRecordingFormats(bool raw, bool png) {
        recordRaw = raw;
        recordPng = png;
        if (!outputPath.empty()) {
            std::string rawDir = outputPath + "/raw";
            std::string pngDir = outputPath + "/png";
            if (recordRaw) _mkdir(rawDir.c_str());
            if (recordPng) _mkdir(pngDir.c_str());
        }
    }

    bool StartRecording() {
        try {
            if (!isReady) {
                std::cout << "Camera not ready - ensure output path is set" << std::endl;
                return false;
            }

            if (!isRecording) {
                std::cout << "Starting recording on existing stream..." << std::endl;
                
                // Reset timestamps and frame counter right before recording
                ResetTimeStamps();
                ResetFrameCounter();
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                
                isRecording = true;
                std::cout << "Recording started successfully" << std::endl;
                return true;
            }
            return isRecording;
        }
        catch (const std::exception& e) {
            std::cerr << "Error in StartRecording: " << e.what() << std::endl;
            return false;
        }
    }

protected:
    static void WriteConnectionState(const std::string& ip) {
        std::ofstream file(CONNECTION_FILE);
        file << ip;
    }
    
    static void ClearConnectionState() {
        std::remove(CONNECTION_FILE);
    }

    static std::string ReadConnectionState() {
        std::ifstream file(CONNECTION_FILE);
        std::string ip;
        std::getline(file, ip);
        return ip;
    }

    virtual void OnCameraReady(WeldSDK::CameraReadyEventArgs args) override {
        if (args.IsReady) {
            std::cout << "Camera " << IPAddress() << " ready" << std::endl;
            // Let base class handle streaming start automatically
            SampleCamera::OnCameraReady(args);
        }
    }

    virtual void OnStreamingStateChanged(WeldSDK::CameraStreamingEventArgs args) override {
        std::cout << "Camera " << IPAddress() << " streaming state: " 
                  << (args.IsStreaming ? "streaming" : "stopped") << std::endl;
    }

    virtual void OnBufferReady(WeldSDK::BufferReadyEventArgs args) override {
        static auto start_time = std::chrono::steady_clock::now();
        static int frame_count = 0;
        static auto last_report_time = std::chrono::steady_clock::now();

        if (!isRecording || !args.RawImage || !args.Image) {
            return;
        }

        frame_count++;
        
        // Use microseconds for higher precision timestamps
        auto current_time = std::chrono::system_clock::now();
        auto timestamp = std::chrono::duration_cast<std::chrono::microseconds>(
            current_time.time_since_epoch()
        ).count();

        // Report frame rate and time in microseconds
        auto since_report = std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::steady_clock::now() - last_report_time).count();
        if (since_report >= 1) {
            float fps = frame_count / static_cast<float>(since_report);
            std::cout << "Frame rate: " << fps << " fps (frame " << frame_count 
                     << ", time: " << timestamp << "μs)" << std::endl;
            frame_count = 0;
            last_report_time = std::chrono::steady_clock::now();
        }

        try {
            if (recordRaw) {
                std::stringstream ss;
                ss << outputPath << "/raw/" << timestamp << ".raw";
                XImageLib::CRawImage raw(*args.RawImage);
                XImageLib::CRawImage::Save(raw, ss.str().c_str());
            }

            if (recordPng) {
                std::stringstream ss;
                ss << outputPath << "/png/" << timestamp << ".png";
                XImageLib::XImageUtil::Save(*args.Image, ss.str().c_str());
            }
        }
        catch (const std::exception& e) {
            std::cerr << "Error saving frame: " << e.what() << std::endl;
        }
    }
};

std::shared_ptr<XirisCollector> XirisCollector::instance = nullptr;
const char* XirisCollector::CONNECTION_FILE = "connection_state.txt";

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cout << "Usage: XIR1800Collection.exe [--detect | --connect <ip> <output_path>]\n";
        return 1;
    }

    std::string command = argv[1];
    
    if (command == "--detect") {
        auto camera = XirisCollector::DetectCamera();
        return camera ? 0 : 1;
    }
    
    if (command == "--connect" && argc > 3) {
        std::string ip = argv[2];
        std::string output_path = argv[3];

        std::cout << "Initializing camera..." << std::endl;
        auto camera = std::make_shared<XirisCollector>(ip, WeldSDK::CameraClass::XVT1800);
        
        if (!camera->Connect()) {
            std::cerr << "Failed to connect to camera\n";
            return 1;
        }

        // Set to record RAW only
        camera->SetRecordingFormats(true, false);  // RAW=true, PNG=false
        camera->SetOutputPath(output_path);
        
        if (!camera->StartRecording()) {
            std::cerr << "Failed to start recording\n";
            return 1;
        }

        signal(SIGINT, signal_handler);
        signal(SIGTERM, signal_handler);
        
        std::cout << "Recording... Press Ctrl+C to stop" << std::endl;
        
        while (running) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        
        camera->StopRecording();
        return 0;
    }

    std::cerr << "Invalid command\n";
    return 1;
}