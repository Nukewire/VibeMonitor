#pragma once
#include "model.h"
#include <stdint.h>

void net_config(const char* host, uint16_t port, const char* token);
bool net_fetch_state(StateModel* out);   // GET /state; false on error (out->valid=false)
bool net_ack(const char* id);            // POST /ack {id}
