// Color confirmation: four labeled swatches. Each says its intended color in
// black text. If the label matches the swatch color, color order/inversion is correct.
#include <TFT_eSPI.h>

TFT_eSPI tft = TFT_eSPI();

void setup() {
  Serial.begin(115200);
  delay(200);
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, HIGH);

  tft.init();
  tft.setRotation(1);
  int w = tft.width(), h = tft.height();
  Serial.printf("[colortest] %dx%d\n", w, h);

  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_BLACK);
  tft.setTextSize(3);

  int bw = w / 2, bh = h / 2;
  // top-left RED, top-right GREEN, bottom-left BLUE, bottom-right WHITE
  tft.fillRect(0,    0,    bw, bh, TFT_RED);    tft.setCursor(10,    bh/2);   tft.print("RED");
  tft.fillRect(bw,   0,    bw, bh, TFT_GREEN);  tft.setCursor(bw+10, bh/2);   tft.print("GREEN");
  tft.fillRect(0,    bh,   bw, bh, TFT_BLUE);   tft.setTextColor(TFT_WHITE); tft.setCursor(10,    bh+bh/2); tft.print("BLUE");
  tft.fillRect(bw,   bh,   bw, bh, TFT_WHITE);  tft.setTextColor(TFT_BLACK); tft.setCursor(bw+10, bh+bh/2); tft.print("WHITE");

  Serial.println("[colortest] drawn");
}

void loop() { delay(1000); }
