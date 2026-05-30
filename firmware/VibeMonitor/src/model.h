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
};

struct StateModel {
    Usage claude;
    Usage codex;
    Session sessions[MAX_SESSIONS];
    uint8_t count;          // sessions filled
    uint16_t total;         // total reported (for "+more")
    bool valid;             // last fetch succeeded
};
