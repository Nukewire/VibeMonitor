#include "net.h"
#include "config.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <string.h>

static char g_host[64] = {0};
static uint16_t g_port = 5151;
static char g_token[96] = {0};

void net_config(const char* host, uint16_t port, const char* token) {
    strlcpy(g_host, host, sizeof(g_host));
    g_port = port;
    strlcpy(g_token, token, sizeof(g_token));
}

static SessStatus parse_status(const char* s) {
    if (strcmp(s, "waiting") == 0) return ST_WAITING;
    if (strcmp(s, "working") == 0) return ST_WORKING;
    return ST_IDLE;
}

static void parse_usage(JsonObjectConst u, Usage* out) {
    out->ok = u["ok"] | false;
    if (out->ok && !u["pct"].isNull()) out->pct = (float)(u["pct"] | 0.0);
    else out->pct = -1.0f;
    out->resetSec = u["resetSec"] | 0;
    out->weekPct = u["weekPct"].isNull() ? -1.0f : (float)(u["weekPct"] | 0.0);

    // --- projection fields (all null-safe) -------------------------------
    out->burnPerHr   = (float)(u["burnPerHr"] | -1.0);
    out->willExhaust = u["willExhaustBeforeReset"] | false;
    if (!u["etaClock"].isNull())
        strlcpy(out->etaClock, u["etaClock"] | "", sizeof(out->etaClock));
    else
        out->etaClock[0] = 0;
    out->leftoverPct   = u["leftoverPct"].isNull() ? -1.0f : (float)(u["leftoverPct"] | 0.0);
    out->weekResetSec  = u["weekResetSec"] | -1;

    out->sparkLen = 0;
    JsonArrayConst sp = u["spark"].as<JsonArrayConst>();
    if (!sp.isNull()) {
        for (JsonVariantConst v : sp) {
            if (out->sparkLen >= 24) break;
            int iv = v | 0;
            if (iv < 0)   iv = 0;
            if (iv > 100) iv = 100;
            out->spark[out->sparkLen++] = (uint8_t)iv;
        }
    }
}

bool net_fetch_state(StateModel* out) {
    out->valid = false; out->count = 0; out->total = 0;
    if (WiFi.status() != WL_CONNECTED) return false;

    HTTPClient http;
    char url[160];
    snprintf(url, sizeof(url), "http://%s:%u/state", g_host, g_port);
    if (!http.begin(url)) return false;
    http.addHeader("X-VibeMonitor-Token", g_token);
    http.setTimeout(HTTP_TIMEOUT_MS);
    int code = http.GET();
    if (code != 200) { http.end(); return false; }

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, http.getStream());
    http.end();
    if (err) return false;

    parse_usage(doc["usage"]["claude"], &out->claude);
    parse_usage(doc["usage"]["codex"], &out->codex);

    JsonArrayConst arr = doc["sessions"].as<JsonArrayConst>();
    out->total = (uint16_t)arr.size();
    for (JsonObjectConst s : arr) {
        if (out->count >= MAX_SESSIONS) break;
        Session* d = &out->sessions[out->count++];
        strlcpy(d->id, s["id"] | "", sizeof(d->id));
        strlcpy(d->project, s["project"] | "?", sizeof(d->project));
        strlcpy(d->tool, s["tool"] | "", sizeof(d->tool));
        d->status = parse_status(s["status"] | "idle");
        d->ageSec = s["ageSec"] | 0;
        d->waiting = s["waiting"] | false;
    }
    out->valid = true;
    return true;
}

bool net_ack(const char* id) {
    if (WiFi.status() != WL_CONNECTED) return false;
    HTTPClient http;
    char url[160];
    snprintf(url, sizeof(url), "http://%s:%u/ack", g_host, g_port);
    if (!http.begin(url)) return false;
    http.addHeader("X-VibeMonitor-Token", g_token);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(HTTP_TIMEOUT_MS);
    char body[80];
    snprintf(body, sizeof(body), "{\"id\":\"%s\"}", id);
    int code = http.POST((uint8_t*)body, strlen(body));
    http.end();
    return code == 200;
}
