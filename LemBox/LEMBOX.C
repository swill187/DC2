#include <windows.h>     
#include <stdlib.h>     
#include <stdio.h>     
#include <olmem.h>         
#include <olerrors.h>         
#include <oldaapi.h>
#include <time.h>
#include <conio.h>
#include "contadc.h"
#include <sys/timeb.h>
#include <process.h>
#pragma comment(linker, "/subsystem:console")

#define STRLEN 80        /* string size for general text manipulation   */
char str[STRLEN];        /* global string for general text manipulation */

/* Error handling macros */
#define SHOW_ERROR(ecode) MessageBox(HWND_DESKTOP,olDaGetErrorString(ecode,\
                  str,STRLEN),"Error", MB_ICONEXCLAMATION | MB_OK);

#define CHECKERROR(ecode) if ((board.status = (ecode)) != OLNOERROR)\
                  {\
                  SHOW_ERROR(board.status);\
                  olDaReleaseDASS(board.hdass);\
                  olDaTerminate(board.hdrvr);\
                  return ((UINT)NULL);}

/* Board structure definition - must come before other structures */
typedef struct tag_board {
   HDEV  hdrvr;        /* device handle            */
   HDASS hdass;        /* sub system handle        */
   ECODE status;       /* board error status       */
   char name[MAX_BOARD_NAME_LENGTH];  /* string for board name    */
   char entry[MAX_BOARD_NAME_LENGTH]; /* string for board name    */
} BOARD;

typedef BOARD* LPBOARD;

// Configuration constants
#define NUM_BUFFERS 240          // Double from 120
#define SAMPLES_PER_BUFFER 4000  // Double from 2000
#define NUM_CHANNELS 2
#define VOLTAGE_CHANNEL 0
#define CURRENT_CHANNEL 1
#define FILE_BUFFER_SIZE 32768  // Increased from 16384
#define QUEUE_SIZE 400000        // Double from 200000  // Size of sample queue
#define MAX_SAMPLES_PER_WRITE 10000

typedef struct {
    ULNG sampleNumber;
    double perfTime;
    WORD voltageRaw;
    DBL voltage;
    WORD currentRaw;
    DBL current;
} SAMPLE_DATA;

typedef struct {
    ULNG sampleCount;
    FILE* dataFile;
    BOOL isRunning;
    LARGE_INTEGER startTime;
    LARGE_INTEGER frequency;
    double samplePeriod;
    DWORD lastDisplayUpdate;
    char writeBuffer[FILE_BUFFER_SIZE];
    size_t writeBufferPos;
    SYSTEMTIME baseTime;      // System time when acquisition started
    HANDLE writerThread;
    HANDLE queueMutex;
    HANDLE queueNotEmpty;
    HANDLE queueNotFull;
    BOOL writerRunning;
    SAMPLE_DATA* sampleQueue;
    size_t queueHead;
    size_t queueTail;
    size_t queueCount;
} ACQUISITION_STATE;

// Global variables
static BOARD board;
static ACQUISITION_STATE acqState = {0};
static HBUF* buffers = NULL;

// Function prototypes
BOOL CALLBACK GetDriver(LPSTR lpszName, LPSTR lpszEntry, LPARAM lParam);
static void InitializeAcquisitionState(void);
static BOOL OpenDataFile(const char* filename);
static void CloseDataFile(void);
static void WriteBufferedSample(WORD voltageRaw, DBL voltage, WORD currentRaw, DBL current);
static void FlushWriteBuffer(void);
BOOL InitializeBoard(void);
BOOL ConfigureADC(void);
BOOL ProcessAcquisition(void);
DBL ConvertToVolts(WORD rawValue, UINT resolution, UINT encoding, DBL max, DBL min);
static unsigned __stdcall WriterThreadFunc(void* arg);
static BOOL QueueSample(SAMPLE_DATA* sample);
static BOOL DequeueSample(SAMPLE_DATA* sample);

// Replace GetSystemTimeString with this higher precision version
static void GetPreciseTimeString(char* buffer, size_t bufferSize, double offsetSeconds) {
    // Get the base time and add the precise offset
    SYSTEMTIME time = acqState.baseTime;
    FILETIME fileTime;
    SystemTimeToFileTime(&time, &fileTime);
    ULONGLONG baseTime100ns = ((ULONGLONG)fileTime.dwHighDateTime << 32) | fileTime.dwLowDateTime;
    
    // Add offset (convert to 100-nanosecond intervals)
    ULONGLONG offsetTime100ns = (ULONGLONG)(offsetSeconds * 10000000);
    ULONGLONG totalTime100ns = baseTime100ns + offsetTime100ns;
    
    // Convert back to FILETIME/SYSTEMTIME
    fileTime.dwLowDateTime = (DWORD)totalTime100ns;
    fileTime.dwHighDateTime = (DWORD)(totalTime100ns >> 32);
    FileTimeToSystemTime(&fileTime, &time);
    
    // Format with microsecond precision
    snprintf(buffer, bufferSize,
             "%04d-%02d-%02d %02d:%02d:%02d.%06.3f",
             time.wYear,
             time.wMonth,
             time.wDay,
             time.wHour,
             time.wMinute,
             time.wSecond,
             (offsetSeconds - (ULONGLONG)offsetSeconds) * 1000000);
}

// Initialize acquisition state
static void InitializeAcquisitionState(void) {
    memset(&acqState, 0, sizeof(ACQUISITION_STATE));
    QueryPerformanceFrequency(&acqState.frequency);
    acqState.lastDisplayUpdate = GetTickCount();
    acqState.isRunning = TRUE;
    GetSystemTime(&acqState.baseTime);
    
    // Initialize thread synchronization
    acqState.queueMutex = CreateMutex(NULL, FALSE, NULL);
    acqState.queueNotEmpty = CreateEvent(NULL, TRUE, FALSE, NULL);
    acqState.queueNotFull = CreateEvent(NULL, TRUE, TRUE, NULL);
    
    // Allocate sample queue
    acqState.sampleQueue = (SAMPLE_DATA*)malloc(QUEUE_SIZE * sizeof(SAMPLE_DATA));
    acqState.writerRunning = TRUE;
    
    // Create writer thread
    acqState.writerThread = (HANDLE)_beginthreadex(NULL, 0, WriterThreadFunc, NULL, 0, NULL);
}

// Open single data file
static BOOL OpenDataFile(const char* filename) {
    acqState.dataFile = fopen(filename, "w");
    if (!acqState.dataFile) {
        printf("\nERROR: Could not create file %s\n", filename);
        return FALSE;
    }
    
    // Updated CSV header without system relative time
    fprintf(acqState.dataFile, 
            "Sample,PerfTime(s),Timestamp,VoltageRaw,Voltage(V),CurrentRaw,Current(A)\n");
    printf("\nCreated file: %s\n", filename);
    return TRUE;
}

// Close data file
static void CloseDataFile(void) {
    if (acqState.dataFile) {
        FlushWriteBuffer();
        fflush(acqState.dataFile);
        fclose(acqState.dataFile);
        acqState.dataFile = NULL;
    }
}

// Buffered write for better performance
static void WriteBufferedSample(WORD voltageRaw, DBL voltage, WORD currentRaw, DBL current) {
    // Get performance counter time
    LARGE_INTEGER currentPerfTime;
    QueryPerformanceCounter(&currentPerfTime);
    double perfElapsedTime = (double)(currentPerfTime.QuadPart - acqState.startTime.QuadPart) / 
                            acqState.frequency.QuadPart;
    
    // Get precise timestamp
    char timeStamp[32];
    GetPreciseTimeString(timeStamp, sizeof(timeStamp), perfElapsedTime);
    
    int written = snprintf(acqState.writeBuffer + acqState.writeBufferPos,
                          FILE_BUFFER_SIZE - acqState.writeBufferPos,
                          "%lu,%.6f,%s,%04X,%.6f,%04X,%.6f\n",
                          acqState.sampleCount++, 
                          perfElapsedTime,    // High-precision relative time
                          timeStamp,          // High-precision absolute timestamp
                          voltageRaw, voltage,
                          currentRaw, current);
    
    if (written > 0) {
        acqState.writeBufferPos += written;
        
        // Flush if buffer is nearly full
        if (acqState.writeBufferPos > (FILE_BUFFER_SIZE - 256)) {
            FlushWriteBuffer();
        }
    }
}

// Flush write buffer to file
static void FlushWriteBuffer(void) {
    if (acqState.dataFile && acqState.writeBufferPos > 0) {
        fwrite(acqState.writeBuffer, 1, acqState.writeBufferPos, acqState.dataFile);
        acqState.writeBufferPos = 0;
    }
}

// Main acquisition loop function
BOOL ProcessAcquisition(void) {
    HBUF hBuffer;
    DWORD currentTime;
    LARGE_INTEGER currentPerfTime;
    BOOL bufferProcessed = FALSE;
    
    while (acqState.isRunning) {
        if (_kbhit() && toupper(_getch()) == 'Q') {
            acqState.isRunning = FALSE;
            break;
        }

        bufferProcessed = FALSE;
        // Process all available buffers before yielding
        while (olDaGetBuffer(board.hdass, &hBuffer) == OLNOERROR && hBuffer) {
            PWORD samples;
            ULNG validSamples;
            
            if (olDmGetBufferPtr(hBuffer, (LPVOID*)&samples) == OLNOERROR &&
                olDmGetValidSamples(hBuffer, &validSamples) == OLNOERROR) {

                QueryPerformanceCounter(&currentPerfTime);
                double baseTime = (double)(currentPerfTime.QuadPart - acqState.startTime.QuadPart) / 
                                acqState.frequency.QuadPart;
                
                // Process samples in batch
                for (ULNG i = 0; i < validSamples; i += NUM_CHANNELS) {
                    WORD voltageRaw = samples[i];
                    WORD currentRaw = samples[i + 1];
                    
                    DBL voltage = ConvertToVolts(voltageRaw, 16, OL_ENC_BINARY, 10.0, -10.0);
                    DBL current = ConvertToVolts(currentRaw, 16, OL_ENC_BINARY, 10.0, -10.0);
                    
                    SAMPLE_DATA sample;
                    sample.sampleNumber = acqState.sampleCount++;
                    // Calculate precise time for each sample based on its position in the buffer
                    sample.perfTime = baseTime + ((double)i / (NUM_CHANNELS * 20000.0)); // Adjust for 20kHz sample rate
                    sample.voltageRaw = voltageRaw;
                    sample.voltage = voltage;
                    sample.currentRaw = currentRaw;
                    sample.current = current;
                    
                    while (!QueueSample(&sample) && acqState.isRunning) {
                        Sleep(1); // Brief wait if queue is full
                    }
                }
                
                bufferProcessed = TRUE;
            }
            
            // Immediately requeue the buffer
            olDaPutBuffer(board.hdass, hBuffer);
        }
        
        // Update display less frequently to reduce overhead
        currentTime = GetTickCount();
        if ((currentTime - acqState.lastDisplayUpdate) >= 500) {  // Reduced from 250ms to 500ms
            printf("\rSamples: %lu, Queue: %lu", acqState.sampleCount, acqState.queueCount);
            fflush(stdout);
            acqState.lastDisplayUpdate = currentTime;
        }
        
        // Only sleep if no buffer was processed
        if (!bufferProcessed) {
            Sleep(1);
        }
    }
    
    return TRUE;
}

BOOL CALLBACK GetDriver(LPSTR lpszName, LPSTR lpszEntry, LPARAM lParam) {
    LPBOARD lpboard = (LPBOARD)(LPVOID)lParam;
    
    lstrcpyn(lpboard->name, lpszName, MAX_BOARD_NAME_LENGTH-1);
    lstrcpyn(lpboard->entry, lpszEntry, MAX_BOARD_NAME_LENGTH-1);

    lpboard->status = olDaInitialize(lpszName, &lpboard->hdrvr);
    if (lpboard->hdrvr != NULL)
        return FALSE;    // false to stop enumerating
    else                      
        return TRUE;     // true to continue
}

BOOL InitializeBoard(void) {
    printf("Searching for DT board...\n");
    
    if (olDaEnumBoards(GetDriver, (LPARAM)(LPBOARD)&board) != OLNOERROR) {
        printf("Failed to enumerate boards\n");
        return FALSE;
    }
    
    if (board.hdrvr == NULL) {
        printf("No DT boards found\n");
        return FALSE;
    }
    
    printf("Board found: %s\n", board.name);
    return TRUE;
}

BOOL ConfigureADC(void) {
    // Get ADC subsystem
    UINT numberADs = 0;
    if (olDaGetDevCaps(board.hdrvr, OLDC_ADELEMENTS, &numberADs) != OLNOERROR) {
        printf("Failed to get device capabilities\n");
        return FALSE;
    }

    if (olDaGetDASS(board.hdrvr, OLSS_AD, 0, &board.hdass) != OLNOERROR) {
        printf("Failed to get ADC subsystem\n");
        return FALSE;
    }

    // Configure ADC
    DBL freq = 20000.0;  // 20kHz sample rate
    ECODE status;
    
    if ((status = olDaSetRange(board.hdass, 10.0, -10.0)) != OLNOERROR ||
        (status = olDaSetDataFlow(board.hdass, OL_DF_CONTINUOUS)) != OLNOERROR ||
        (status = olDaSetWrapMode(board.hdass, OL_WRP_MULTIPLE)) != OLNOERROR ||
        (status = olDaSetClockSource(board.hdass, OL_CLK_INTERNAL)) != OLNOERROR ||
        (status = olDaSetEncoding(board.hdass, OL_ENC_BINARY)) != OLNOERROR ||
        (status = olDaSetClockFrequency(board.hdass, freq)) != OLNOERROR ||
        (status = olDaSetChannelListEntry(board.hdass, 0, VOLTAGE_CHANNEL)) != OLNOERROR ||
        (status = olDaSetChannelListEntry(board.hdass, 1, CURRENT_CHANNEL)) != OLNOERROR ||
        (status = olDaSetChannelListSize(board.hdass, NUM_CHANNELS)) != OLNOERROR) {
        printf("ADC configuration failed\n");
        return FALSE;
    }

    if ((status = olDaConfig(board.hdass)) != OLNOERROR) {
        printf("Failed to apply configuration\n");
        return FALSE;
    }

    return TRUE;
}

DBL ConvertToVolts(WORD rawValue, UINT resolution, UINT encoding, DBL max, DBL min) {
    if (encoding != OL_ENC_BINARY) {
        // Convert from two's complement to straight binary
        rawValue ^= 1L << (resolution-1);
    }
    
    return ((DBL)rawValue * (max - min)) / (1L << resolution) + min;
}

static unsigned __stdcall WriterThreadFunc(void* arg) {
    SAMPLE_DATA sample;
    char timeStamp[32];
    size_t batchCount = 0;
    const size_t BATCH_SIZE = 1000;  // Number of samples to write before flushing
    
    while (acqState.writerRunning || acqState.queueCount > 0) {
        // Don't wait if there are samples available
        if (WaitForSingleObject(acqState.queueNotEmpty, 1) == WAIT_OBJECT_0) {
            while (DequeueSample(&sample)) {
                GetPreciseTimeString(timeStamp, sizeof(timeStamp), sample.perfTime);
                
                fprintf(acqState.dataFile, "%lu,%.6f,%s,%04X,%.6f,%04X,%.6f\n",
                        sample.sampleNumber,
                        sample.perfTime,
                        timeStamp,
                        sample.voltageRaw,
                        sample.voltage,
                        sample.currentRaw,
                        sample.current);
                
                if (++batchCount >= BATCH_SIZE) {
                    fflush(acqState.dataFile);
                    batchCount = 0;
                }
            }
        }
    }
    
    return 0;
}

static BOOL QueueSample(SAMPLE_DATA* sample) {
    BOOL result = FALSE;
    
    WaitForSingleObject(acqState.queueMutex, INFINITE);
    
    if (acqState.queueCount < QUEUE_SIZE) {
        acqState.sampleQueue[acqState.queueTail] = *sample;
        acqState.queueTail = (acqState.queueTail + 1) % QUEUE_SIZE;
        acqState.queueCount++;
        
        if (acqState.queueCount == 1) {
            SetEvent(acqState.queueNotEmpty);
        }
        if (acqState.queueCount == QUEUE_SIZE) {
            ResetEvent(acqState.queueNotFull);
        }
        result = TRUE;
    }
    
    ReleaseMutex(acqState.queueMutex);
    return result;
}

static BOOL DequeueSample(SAMPLE_DATA* sample) {
    BOOL result = FALSE;
    
    WaitForSingleObject(acqState.queueMutex, INFINITE);
    
    if (acqState.queueCount > 0) {
        *sample = acqState.sampleQueue[acqState.queueHead];
        acqState.queueHead = (acqState.queueHead + 1) % QUEUE_SIZE;
        acqState.queueCount--;
        
        if (acqState.queueCount == 0) {
            ResetEvent(acqState.queueNotEmpty);
        }
        if (acqState.queueCount == QUEUE_SIZE - 1) {
            SetEvent(acqState.queueNotFull);
        }
        result = TRUE;
    }
    
    ReleaseMutex(acqState.queueMutex);
    return result;
}

int main(int argc, char* argv[]) {
    BOOL checkOnly = FALSE;
    char* outputFile = NULL;
    
    // Parse command line arguments
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--check") == 0) {
            checkOnly = TRUE;
        } else if (strcmp(argv[i], "--collect") == 0 && i + 1 < argc) {
            outputFile = argv[++i];
        } else {
            printf("Usage: %s [--check] [--collect output.csv]\n", argv[0]);
            return 1;
        }
    }
    
    // Initialize board
    if (!InitializeBoard()) {
        printf("ERROR:BOARD_INIT_FAILED\n");
        return 1;
    }

    // If just checking connection, exit after init
    if (checkOnly) {
        printf("OK:BOARD_CONNECTED\n");
        olDaTerminate(board.hdrvr);
        return 0;
    }
    
    // Verify we have an output file for collection mode
    if (!outputFile) {
        printf("ERROR:NO_OUTPUT_FILE\n");
        return 1;
    }

    // Configure ADC
    if (!ConfigureADC()) {
        printf("ERROR:ADC_CONFIG_FAILED\n");
        olDaTerminate(board.hdrvr);
        return 1;
    }

    // Allocate buffer array
    buffers = (HBUF*)calloc(NUM_BUFFERS, sizeof(HBUF));
    if (!buffers) {
        printf("ERROR:BUFFER_ALLOC_FAILED\n");
        olDaTerminate(board.hdrvr);
        return 1;
    }
    
    // Allocate and queue buffers
    for (int i = 0; i < NUM_BUFFERS; i++) {
        if (olDmCallocBuffer(0, 0, SAMPLES_PER_BUFFER * NUM_CHANNELS, 2, &buffers[i]) != OLNOERROR) {
            printf("ERROR:BUFFER_SETUP_FAILED\n");
            olDaTerminate(board.hdrvr);
            return 1;
        }
        if (olDaPutBuffer(board.hdass, buffers[i]) != OLNOERROR) {
            printf("ERROR:BUFFER_QUEUE_FAILED\n");
            olDaTerminate(board.hdrvr);
            return 1;
        }
    }
    
    // Initialize acquisition state and open file
    InitializeAcquisitionState();
    if (!OpenDataFile(outputFile)) {
        printf("ERROR:FILE_OPEN_FAILED\n");
        olDaTerminate(board.hdrvr);
        return 1;
    }
    
    // Start acquisition
    QueryPerformanceCounter(&acqState.startTime);
    if (olDaStart(board.hdass) != OLNOERROR) {
        printf("ERROR:ACQUISITION_START_FAILED\n");
        CloseDataFile();
        olDaTerminate(board.hdrvr);
        return 1;
    }
    
    printf("OK:ACQUISITION_STARTED\n");
    
    // Run acquisition loop
    ProcessAcquisition();
    
    // Cleanup
    olDaStop(board.hdass);
    olDaFlushBuffers(board.hdass);
    CloseDataFile();
    
    // Free buffers
    if (buffers) {
        for (int i = 0; i < NUM_BUFFERS; i++) {
            if (buffers[i]) {
                olDmFreeBuffer(buffers[i]);
            }
        }
        free(buffers);
    }
    
    olDaReleaseDASS(board.hdass);
    olDaTerminate(board.hdrvr);
    
    printf("OK:ACQUISITION_COMPLETE\n");
    printf("SAMPLES:%lu\n", acqState.sampleCount);
    
    return 0;
}