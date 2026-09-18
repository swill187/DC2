#include <nanobind/nanobind.h>

#include <windows.h>
#include <olmem.h>
#include <olerrors.h>
#include <oldaapi.h>

namespace np = nanobind;
using namespace np::literals;

// info about the connected board - must come before other structures
typedef struct tag_board {
   HDEV  hdrvr;        // device/driver handle
   HDASS hdass;        // data acquisition sub system handle
   ECODE status;       // board error status
   char name[MAX_BOARD_NAME_LENGTH];  // human-readable string for board name
   char entry[MAX_BOARD_NAME_LENGTH]; // non-human-readable string for board name
} BOARD;

typedef BOARD* LPBOARD;  // LPBOARD is a pointer to a board struct TODO: is this too abstract?

#define NUM_CHANNELS 2
#define VOLTAGE_CHANNEL 0
#define CURRENT_CHANNEL 1
#define NUM_BUFFERS 64

#define EPOCH_DIFF_100NS 116444736000000000ULL // number of 100NS between FILETIME and unix time starts

static BOARD board;
static HBUF* buffers = NULL;

// called for each detected board in a system. Currently, if we see a board, we stop enumeration.
// for multiple connected boards, you would need to do something different.
BOOL CALLBACK GetDriver(LPSTR lpszName, LPSTR lpszEntry, LPARAM lParam) { // enumerated human-readable board name, enumerated driver entry string (non-human-readable id), LPBOARD pointer as abstract pointer
    LPBOARD lpboard = (LPBOARD)(LPVOID)lParam; // convert board pointer back to LPBOARD pointer (must be arbitrary pointer as it passes through olDaEnumBoards)
    
    // store name, entry
    lstrcpyn(lpboard->name , lpszName , MAX_BOARD_NAME_LENGTH - 1);
    lstrcpyn(lpboard->entry, lpszEntry, MAX_BOARD_NAME_LENGTH - 1);

    lpboard->status = olDaInitialize(lpszName, &lpboard->hdrvr); // try to connect to this board

    // if board.hdrvr is not NULL, we are connected to a board and can stop enumeration
    if (lpboard->hdrvr != NULL)
        return FALSE;    // false to stop enumerating
    else                      
        return TRUE;     // true to continue
}

BOOL detectBoard() {

    // enumerate all detected boards. Each seen board is sent to the GetDriver callback. Write info of the
    // first board we successfully connect to into board.
    if (olDaEnumBoards(GetDriver, (LPARAM)(LPBOARD)&board) != OLNOERROR) {

        // if we get an enumeration error, return False
        return FALSE;
    }

    // if we didn't connect to any boards, return False
    if (board.hdrvr == NULL) {
        return FALSE;
    }

    // success
    return TRUE;
}

BOOL configureADC(DBL freq) { // default 20 kHz sample rate

    // check that A/D subsystem exists
    UINT numberADs = 0;
    if (olDaGetDevCaps(board.hdrvr, OLDC_ADELEMENTS, &numberADs) != OLNOERROR) {
        return FALSE;
    }

    // get A/D subsystem
    if (olDaGetDASS(board.hdrvr, OLSS_AD, 0, &board.hdass) != OLNOERROR) {
        return FALSE;
    }

    // Configure ADC
    ECODE status;
    
    if ((status = olDaSetRange(board.hdass, 10.0, -10.0)) != OLNOERROR ||
        (status = olDaSetDataFlow(board.hdass, OL_DF_CONTINUOUS)) != OLNOERROR ||
        (status = olDaSetWrapMode(board.hdass, OL_WRP_MULTIPLE)) != OLNOERROR ||
        (status = olDaSetClockSource(board.hdass, OL_CLK_INTERNAL)) != OLNOERROR ||
        (status = olDaSetEncoding(board.hdass, OL_ENC_BINARY)) != OLNOERROR ||
        (status = olDaSetClockFrequency(board.hdass, freq)) != OLNOERROR ||
        (status = olDaSetChannelListSize(board.hdass, NUM_CHANNELS)) != OLNOERROR || // swapped position w/ entry calls
        (status = olDaSetChannelListEntry(board.hdass, 0, VOLTAGE_CHANNEL)) != OLNOERROR ||
        (status = olDaSetChannelListEntry(board.hdass, 1, CURRENT_CHANNEL)) != OLNOERROR) {
        return FALSE;
    }

    if ((status = olDaConfig(board.hdass)) != OLNOERROR) {
        return FALSE;
    }

    return TRUE;
}

BOOL initBoard(DBL freq, UINT buffer_len) {

    if (!configureADC(freq)) {
        return FALSE;
    }

    // allocate memory for list of buffer pointers
    buffers = (HBUF*)calloc(NUM_BUFFERS, sizeof(HBUF));
    if (!buffers) {
        return FALSE;
    }

    // allocate memory for each buffer in our list
    for (HBUF &buffer : buffers) {
        if (olDmCallocBuffer(0, 0, buffer_len * NUM_CHANNELS, 2, &buffer) != OLNOERROR) {
            return FALSE;
        }
        if (olDaPutBuffer(board.hdass, buffer) != OLNOERROR) {
            return FALSE;
        }
    }

    return TRUE;
}

ULONGLONG startAcquisition() {

    FILETIME start_time;
    GetSystemTimePreciseAsFileTime(&start_time);

    if (olDaStart(board.hdass) != OLNOERROR) {
        return -1;
    }

    ULONGLONG start_time_100ns = ((ULONGLONG)start_time.dwHighDateTime << 32) | start_time.dwLowDateTime;
    ULONGLONG start_time_ns = (start_time_100ns - EPOCH_DIFF_100NS) * 100; // start time in DC2 format

    return start_time_ns;
}

VOID deleteBoard() {

    olDaTerminate(board.hdrvr);
}


NB_MODULE(lembox, m) {
    m.def("detectBoard", &detectBoard);
    m.def("deleteBoard", &deleteBoard);
    m.def("initBoard"  , &initBoard, "freq"_freq = 20000.0, "buffer_len"_buffer_len = 1024)
}
