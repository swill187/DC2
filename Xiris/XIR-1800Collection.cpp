#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <direct.h> 
#include "SampleCameraDetection.h"
#include "XirisCommon/XImage.h"
#include "XImageLib/Image/XImageUtil.h"
#include "WeldSDK/WeldCamera.h"
#include "XImageLib/Image/CRawImage.h" 
#include "XImageLib/Image/CXImage.h"

class XirisCollector : public SampleCamera {
private:
    bool isRecording;
    std::string outputPath;
    bool recordRaw;
    bool recordPng;
    static std::shared_ptr<XirisCollector> instance;

public:
    XirisCollector(std::string ip, WeldSDK::CameraClass type) :  
        SampleCamera(ip, type),
        isRecording(false),
        outputPath(""),     
        recordRaw(true),    
        recordPng(true)     
    { }

    void SetOutputPath(const std::string& path) {  
        outputPath = path;
    }

    void SetRecordingFormats(bool raw, bool png) {
        recordRaw = raw;
        recordPng = png;
    }

    static std::shared_ptr<XirisCollector> GetInstance() {
        if (!instance) {
            instance = std::shared_ptr<XirisCollector>(new XirisCollector("", WeldSDK::CameraClass::XVT1800));
            if (instance) {
                instance->Connect();  // Connect during initialization
                std::cout << "Camera initialized and connected" << std::endl;
            }
        }
        return instance;
    }

    bool StartRecording() {
        if (!isRecording) {
            isRecording = true;
            std::cout << "Recording started" << std::endl;
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

        // Create subdirectories for each format
        if (recordRaw) {
            std::string rawDir = outputPath + "/raw";
            _mkdir(rawDir.c_str());
            std::stringstream rawFileName;
            rawFileName << rawDir << "/frame_" << frameNumber << ".raw";
            XImageLib::CRawImage raw(*args.RawImage);
            XImageLib::CRawImage::Save(raw, rawFileName.str().c_str());
        }

        if (recordPng) {
            std::string pngDir = outputPath + "/png";
            _mkdir(pngDir.c_str());
            std::stringstream pngFileName;
            pngFileName << pngDir << "/frame_" << frameNumber << ".png";
            XImageLib::CXImage::CXImage(*args.Image);
            XImageLib::XImageUtil::Save(*args.Image, pngFileName.str().c_str());
        }
    }
};

std::shared_ptr<XirisCollector> XirisCollector::instance;

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
        auto camera = XirisCollector::GetInstance();
        return camera != nullptr ? 0 : 1;
    }
    else if (command == "--record" && argc >= 3) {
        auto camera = XirisCollector::GetInstance();
        if (camera) {
            std::string outputPath = argv[2];
            camera->SetOutputPath(outputPath);
            
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
        return 1;
    }

    PrintUsage();
    return 1;
}
