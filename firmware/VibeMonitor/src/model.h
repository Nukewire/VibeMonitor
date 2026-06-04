#pragma once
#include <stdint.h>
#include "config.h"

enum SessStatus { ST_IDLE, ST_WORKING, ST_WAITING };

struct Session {
    char id[40];
    char project[MAX_PROJ_LEN];
    char tool[8];           // "claude" / "codex"
    SessStatus status;
    uint32_t ageSec;
    bool waiting;
};

struct Usage {
    bool ok;
    float pct;              // 0..1, or -1 if unknown
    uint32_t resetSec;
    float weekPct;          // -1 if unknown

    // --- projection (bridge-computed) ------------------------------------
    float   burnPerHr;      // fraction/hr; <= 0 or -1 if unknown
    bool    willExhaust;    // true => will hit 100% before reset
    char    etaClock[12];   // e.g. "3:40 PM"; "" if unknown
    float   leftoverPct;    // fraction expected to remain at reset; -1 if unknown
    int     weekResetSec;   // seconds until weekly window resets; -1 if unknown
    uint8_t spark[24];      // recent % trend (0..100)
    uint8_t sparkLen;       // valid entries in spark[]
};

struct StateModel {
    Usage claude;
    Usage codex;
    Session sessions[MAX_SESSIONS];
    uint8_t count;          // sessions filled
    uint16_t total;         // total reported (for "+more")
    bool valid;             // last fetch succeeded
};
