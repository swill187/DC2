#include <iostream>
#include <memory>
#include <sstream>
#include "SampleCameraDetection.h"

#include <string>
#include "XirisCommon/XImage.h"
#include "XImageLib/Image/XImageUtil.h"
#include "XImageLib/Image/CRawImage.h"
#include "XVideoRecorderLib/XVideoRecorder.h"
#include "WeldSDK/WeldCamera.h"

class XirisCollector : public SampleCamera {
private:
    bool isRecording;
    std::string outputPath;
    bool recordRaw;
    bool recordPng;

public:
    XirisCollector(std::string ip, WeldSDK::CameraClass type) :  // Remove outPath parameter
        SampleCamera(ip, type),
        isRecording(false),
        outputPath(""),                                          // Initialize with empty string
        recordRaw(true),    // Enable RAW recording by default
        recordPng(true)     // Enable PNG recording by default
    { }

    void SetOutputPath(const std::string& path) {               // Add this method
        outputPath = path;
    }

    void SetRecordingFormats(bool raw, bool png) {
        recordRaw = raw;
        recordPng = png;
    }

    bool StartRecording() {
        if (!isRecording) {
            isRecording = true;
            return true;
        }
        return false;
    }

    void StopRecording() {
        isRecording = false;
    }

    virtual void OnBufferReady(WeldSDK::BufferReadyEventArgs args) override {
        if (!isRecording) return;

        const int frameNumber = args.MetaData.FrameCount;

        if (recordRaw) {
            std::stringstream rawFileName;
            rawFileName << outputPath << "/frame_" << frameNumber << ".raw";
            XImageLib::CRawImage raw(*args.RawImage);
            XImageLib::CRawImage::Save(raw, rawFileName.str().c_str());
        }

        if (recordPng) {
            std::stringstream pngFileName;
            pngFileName << outputPath << "/frame_" << frameNumber << ".png";
            XImageLib::XImageUtil::Save(*args.Image, pngFileName.str().c_str());
        }
    }
};

void PrintUsage() {
    std::cout << "Usage:\n"
              << "  --check                    Check camera connection\n"
              << "  --record <path> [options]  Start recording to specified path\n"
              << "  Options:\n"
              << "    --raw                    Enable RAW format recording\n"
              << "    --png                    Enable PNG format recording\n"
              << "    (If no format options specified, both formats are enabled)\n";
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        PrintUsage();
        return 1;
    }

    std::string command = argv[1];
    
    if (command == "--check") {
        auto camera = DetectACamera<XirisCollector>();
        return camera != nullptr ? 0 : 1;
    }
    else if (command == "--record" && argc >= 3) {
        std::string outputPath = argv[2];
        auto camera = DetectACamera<XirisCollector>();          // Remove extra parameters
        if (camera) {
            camera->SetOutputPath(outputPath);                   // Set the path after creation
            
            if (camera->Connect()) {
                // Parse format options
                bool rawEnabled = false;
                bool pngEnabled = false;

                for (int i = 3; i < argc; i++) {
                    std::string arg = argv[i];
                    if (arg == "--raw") rawEnabled = true;
                    else if (arg == "--png") pngEnabled = true;
                }

                if (!rawEnabled && !pngEnabled) {
                    rawEnabled = true;
                    pngEnabled = true;
                }

                camera->SetRecordingFormats(rawEnabled, pngEnabled);
                
                if (camera->StartRecording()) {
                    std::cout << "Recording started with formats:\n"
                             << (rawEnabled ? "- RAW\n" : "")
                             << (pngEnabled ? "- PNG\n" : "")
                             << "Press Ctrl+C to stop." << std::endl;
                             
                    while (true) {
                        std::this_thread::sleep_for(std::chrono::milliseconds(100));
                    }
                }
            }
        }
        return 1;
    }

    PrintUsage();
    return 1;
}
