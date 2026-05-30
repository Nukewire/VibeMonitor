#include "provisioning.h"
#include "config.h"
#include <Arduino.h>
#include <lvgl.h>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <string.h>

static Preferences prefs;

static const char PORTAL_HTML[] PROGMEM = R"HTML(
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VibeMonitor Setup</title><style>
body{font-family:sans-serif;margin:22px auto;max-width:420px;padding:0 16px;color:#111}
h2{color:#0a7}label{display:block;margin-top:10px;font-size:14px}
input{width:100%;padding:9px;margin-top:4px;box-sizing:border-box;border:1px solid #bbb;border-radius:6px}
button{margin-top:16px;padding:11px 18px;background:#0a7;color:#fff;border:0;border-radius:6px;font-size:15px}
</style></head><body>
<h2>VibeMonitor Setup</h2>
<form method="POST" action="/save">
<label>WiFi SSID</label><input name="ssid">
<label>WiFi Password</label><input name="pass" type="password">
<label>Hub host (your PC's LAN IP)</label><input name="host" placeholder="192.168.1.50">
<label>Hub port</label><input name="port" value="5151">
<label>Hub token</label><input name="token">
<button type="submit">Save &amp; Reboot</button>
</form></body></html>
)HTML";

void prov_load(Provision* p) {
    prefs.begin("vibemonitor", true);
    String ssid  = prefs.getString("ssid", "");
    String pass  = prefs.getString("pass", "");
    String host  = prefs.getString("host", "");
    uint16_t prt = prefs.getUShort("port", 5151);
    String token = prefs.getString("token", "");
    prefs.end();

    strlcpy(p->ssid,  ssid.c_str(),  sizeof(p->ssid));
    strlcpy(p->pass,  pass.c_str(),  sizeof(p->pass));
    strlcpy(p->host,  host.c_str(),  sizeof(p->host));
    p->port = prt;
    strlcpy(p->token, token.c_str(), sizeof(p->token));
    p->complete = (ssid.length() > 0 && host.length() > 0 && token.length() > 0);
}

void prov_save(const Provision* p) {
    prefs.begin("vibemonitor", false);
    prefs.putString("ssid",  p->ssid);
    prefs.putString("pass",  p->pass);
    prefs.putString("host",  p->host);
    prefs.putUShort("port",  p->port);
    prefs.putString("token", p->token);
    prefs.end();
}

void prov_clear() {
    prefs.begin("vibemonitor", false);
    prefs.clear();
    prefs.end();
}

bool prov_portal(Provision* p) {
    WiFi.mode(WIFI_AP);
    WiFi.softAP("VibeMonitor-setup");
    IPAddress apIP = WiFi.softAPIP();

    DNSServer dns;
    dns.start(53, "*", apIP);

    WebServer server(80);
    bool done = false;

    server.on("/", HTTP_GET, [&server]() {
        server.send_P(200, "text/html", PORTAL_HTML);
    });
    server.on("/save", HTTP_POST, [&server, p, &done]() {
        strlcpy(p->ssid,  server.arg("ssid").c_str(),  sizeof(p->ssid));
        strlcpy(p->pass,  server.arg("pass").c_str(),  sizeof(p->pass));
        strlcpy(p->host,  server.arg("host").c_str(),  sizeof(p->host));
        int prt = server.arg("port").toInt();
        p->port = (prt > 0 && prt < 65536) ? (uint16_t)prt : 5151;
        strlcpy(p->token, server.arg("token").c_str(), sizeof(p->token));
        p->complete = true;
        prov_save(p);
        server.send(200, "text/html",
                    "<h2>Saved. Rebooting&hellip;</h2><p>You can close this page.</p>");
        done = true;
    });
    server.onNotFound([&server]() {            // captive-portal catch-all
        server.send_P(200, "text/html", PORTAL_HTML);
    });
    server.begin();

    uint32_t last_tick = millis();
    while (!done) {
        dns.processNextRequest();
        server.handleClient();
        uint32_t now = millis();        // keep LVGL alive so the screen finishes drawing
        lv_tick_inc(now - last_tick);
        last_tick = now;
        lv_timer_handler();
        delay(5);
    }
    delay(800);   // let the response flush before caller reboots
    server.stop();
    dns.stop();
    return true;
}
