#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/pair.h>

#include <string>
#include <mutex>

#include "WeldSDK/WeldCamera.h"
#include "WeldSDK/CameraDetector.h"

namespace nb = nanobind;
using namespace nb::literals;

class MyXirisCamera:
    // multiple inheritance. MyXirisCamera is a child of both WeldCamera and CameraEventSink
    public WeldSDK::WeldCamera,
    public WeldSDK::CameraEventSink
{

    private:
        WeldSDK::CameraClass cameraType;
        bool recordRaw;
        bool recordPng;
        bool isReady;

    public: 

        std::string ipAddress;
        bool isRecording = false;

        MyXirisCamera(const std::string ip, WeldSDK::CameraClass type = WeldSDK::CameraClass::XVT1800, bool recordRaw = true, bool recordPng = false):
            WeldSDK::WeldCamera(),
            ipAddress(ip),
            cameraType(type),
            recordRaw(recordRaw),
            recordPng(recordPng)
        {
            AttachEventSink(this);
        }

        virtual ~MyXirisCamera() {

            DetachEventSink(this);
        }

        bool ConnectCamera() {
            return Connect(ipAddress, cameraType);
        }

        virtual void OnCameraReady(WeldSDK::CameraReadyEventArgs args) override {

            isReady = true;

            return;
        }

        virtual void OnStreamingStateChanged(WeldSDK::CameraStreamingEventArgs args) override {

            if (args.IsStreaming) {
                if (args.IsPaused) {
                    std::cout << "Camera " << ipAddress << " is paused.\n";
                }
                else {
                    std::cout << "Camera " << ipAddress << " is streaming.\n";
                }
            }
            else {
                std::cout << "Camera " << ipAddress << " is stopped.\n";
            }

            return;
        }

        virtual void OnBufferReady(WeldSDK::BufferReadyEventArgs args) override {
            

            return;
        }
        
        virtual void OnTraceMessage(WeldSDK::TraceMessageEventArgs args) override {

            std::cout << "Camera " << ipAddress << " Message: " << args.Message << "\n";
            return;
        }

};

// wrapper for a CameraDetectorEventSink + function returning shared ptr to a MyXirisCamera object
class SimpleDetector: public WeldSDK::CameraDetectorEventSink {

    private:
        WeldSDK::CameraClass cameraType;            // camera model
        WeldSDK::CameraDetector* detector;           // detector obj
        std::mutex cameraMtx;                       // mutex (thread lock)
        std::condition_variable waitForCameraCv;    // condition check for mutex
        std::shared_ptr<MyXirisCamera> camera;        // discovered camera

    public:

        SimpleDetector(WeldSDK::CameraClass type = WeldSDK::CameraClass::XVT1800) {

            detector = WeldSDK::CameraDetector::GetInstance();  // we cannot call the constructor of CameraDetector directly, otherwise we would make SimpleDetector a child of CameraDetector
            cameraType = type;                                  // Class of camera we plan to detect
            detector->AttachEventSink(this);                    // link detector to this class's OnCameraDetected
        }
    
        // callback for when SDK thread enumerates a camera
        virtual void OnCameraDetected(WeldSDK::CameraEventArgs args) {

            if (args.CanConnect) {
                if (args.CameraType == cameraType) {    // if it's the camera we are looking for

                    // lock makes the main program wait while we detect cameras
                    std::lock_guard<std::mutex> lk(cameraMtx);

                    if (camera == nullptr) {
                        camera = std::make_shared<MyXirisCamera>(args.CameraIPAddress, args.CameraType);    // construct a camera object from detected camera
                        waitForCameraCv.notify_one();   // unlock main program thread
                    }

                }
            }
        }

        // callable detection function. returns ip address of camera
        std::string DetectCamera() {

            // lock forces this function to wait until a camera is detected
            std::unique_lock<std::mutex> lk(cameraMtx);

            waitForCameraCv.wait_for(lk, 
                                     std::chrono::seconds(10),
                                     [this] { return camera != nullptr; }
                                    ); // wait until lambda function returns true, or timeout is reached
            lk.unlock();

            detector->StopMonitoring();
            detector->DetachEventSink(this);
            
            // return ip address if camera was detected, else return -1
            // this way, we don't hold on to a camera object that we don't actually want.
            return camera != nullptr ? camera->ipAddress : "-1";
        }
};

// entry point (is this the right term?) for nanobind to use SimpleDetector
std::string DetectXirisCamera() {
    SimpleDetector* detector = new SimpleDetector(WeldSDK::CameraClass::XVT1800);

    std::string ip = detector->DetectCamera();

    delete detector;
    return ip;
}

std::shared_ptr<MyXirisCamera> camera;

std::pair<bool, std::string> InitXirisCamera(std::string ipAddress) {
    std::string msg = "";

    camera = std::make_shared<MyXirisCamera>(ipAddress);

    // get our camera
    if (!camera->ConnectCamera()) {

        msg = "Camera connection failed";
        return std::make_pair(false, msg);
    }

    // immediately pause the camera stream. We don't want to fill tons of buffers before real data collection starts
    if (!camera->Pause()) {

        msg = "Camera Pause on init failed";
        return std::make_pair(false, msg);
    }

    // set frame count to 0. Unclear if this will increment during the pause (same frame is still streamed). TODO: investigate
    if (!camera->ResetFrameCounter()) {

        msg = "Camera frame counter reset on init failed";
        return std::make_pair(false, msg);
    }

    return std::make_pair(true, msg);
}

std::pair<bool, std::string> XirisStartRecording() {
    std::string msg = "";

    if (camera->isRecording) {
        msg = "Camera already recording!";
        return std::make_pair(false, msg);
    } else {
        camera->isRecording = true;
        camera->Start();

    }

    return std::make_pair(true, msg);
}

NB_MODULE(xiris, m) {
    m.def("detectCamera", &DetectXirisCamera);
    m.def("initCamera", &InitXirisCamera, "ipAddress"_a);
}
