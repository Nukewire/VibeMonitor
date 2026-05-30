#pragma once
#include <stdint.h>

struct Provision {
    char ssid[33];
    char pass[64];
    char host[64];
    uint16_t port;
    char token[96];
    bool complete;
};

void prov_load(Provision* p);      // read NVS
void prov_save(const Provision* p);// write NVS
bool prov_portal(Provision* p);    // blocking captive portal until /save submitted
void prov_clear();                 // factory reset (clear NVS)
