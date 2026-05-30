#pragma once
#include "model.h"

typedef void (*AckCb)(const char* id);

void ui_init();                       // build tabview + widgets + flash timer
void ui_update(const StateModel* m);  // refresh sessions + usage
void ui_set_offline(bool offline);    // show/hide "hub offline" banner
void ui_set_ack_cb(AckCb cb);         // called when a waiting row is tapped
