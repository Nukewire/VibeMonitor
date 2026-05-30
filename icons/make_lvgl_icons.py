"""Convert the Claude/Codex color PNGs into an LVGL C image source for the CYD.

PNG --(Pillow)--> 18x18 RGBA --> LVGL true-color-alpha (RGB565 LE + 1 alpha
byte/pixel; matches LV_COLOR_DEPTH=16, LV_COLOR_16_SWAP=0).
Writes firmware/VibeMonitor/src/icons.c + icons.h.
"""
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent / "firmware" / "VibeMonitor" / "src"
SIZE = 18

ICONS = [
    ("claude_icon", "claudecode-color.png"),
    ("codex_icon", "codex-color-transparent.png"),
]


def to_lvgl_bytes(path: Path) -> bytes:
    im = Image.open(path).convert("RGBA").resize((SIZE, SIZE), Image.LANCZOS)
    out = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            r, g, b, a = im.getpixel((x, y))
            c = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            out += bytes((c & 0xFF, (c >> 8) & 0xFF, a))
    return bytes(out)


def emit_c(name: str, data: bytes) -> str:
    rows = [
        "    " + ", ".join(f"0x{b:02x}" for b in data[i:i + 16]) + ","
        for i in range(0, len(data), 16)
    ]
    body = "\n".join(rows)
    return f"""
static const uint8_t {name}_map[] = {{
{body}
}};

const lv_img_dsc_t {name} = {{
    .header.cf = LV_IMG_CF_TRUE_COLOR_ALPHA,
    .header.always_zero = 0,
    .header.reserved = 0,
    .header.w = {SIZE},
    .header.h = {SIZE},
    .data_size = {len(data)},
    .data = {name}_map,
}};
"""


def main():
    c_parts = ['#include "lvgl.h"\n']
    h_parts = ['#pragma once\n#include "lvgl.h"\n']
    for name, png in ICONS:
        data = to_lvgl_bytes(HERE / png)
        c_parts.append(emit_c(name, data))
        h_parts.append(f"extern const lv_img_dsc_t {name};")
    (OUT_DIR / "icons.c").write_text("\n".join(c_parts), encoding="utf-8")
    (OUT_DIR / "icons.h").write_text("\n".join(h_parts) + "\n", encoding="utf-8")
    print(f"OK wrote icons.c ({len(c_parts)} parts) + icons.h at {OUT_DIR}")


if __name__ == "__main__":
    main()
