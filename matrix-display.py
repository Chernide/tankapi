#!/usr/bin/env python3
"""Tankbook LED matrix display: a 64x32 HUB75 panel on an Adafruit RGB Matrix Bonnet.

On the Pi:            sudo python3 matrix_display.py
Preview (any computer): python3 matrix_display.py --preview [--demo]
"""
import argparse
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from PIL import BdfFontFile, Image, ImageDraw, ImageFont

# ------------------------------ settings -------------------------------------
DB_PATH = os.environ.get("TANKBOOK_DB", "tankapi.db")
FONT_DIR = Path(os.environ.get("MATRIX_FONT_DIR", Path.home() / "rpi-rgb-led-matrix" / "fonts"))
FONT_CACHE = Path(__file__).with_name("font_cache")

WATER_CHANGE_DAYS = 10      # warn when the last water change is this old
TEST_DUE_DAYS = 5           # nudge when the last test is this old
NITRATE_WARN = 40           # ppm
ROTATE_SECONDS = 8          # time on each screen
REFRESH_SECONDS = 60        # how often to re-read the database
NIGHT_START, NIGHT_END = 20, 7   # panel is blank from 10 pm to 7 am

W, H = 64, 32
HARDWARE_MAPPING = "adafruit-hat-pwm"   # use "adafruit-hat" if you did not add the GPIO4-GPIO18 jumper
GPIO_SLOWDOWN = 4
BRIGHTNESS = 40
# ------------------------------------------------------------------------------

GREEN, RED, AMBER = (60, 200, 120), (230, 60, 60), (240, 160, 30)
BLUE, GREY, WHITE = (80, 150, 230), (130, 130, 130), (230, 230, 230)
DARK_RED, TRACK = (110, 25, 25), (30, 30, 30)

FONT_W = {"4x6": 4, "5x7": 5, "6x10": 6}      # character widths in pixels
_fonts = {}


def font(name):
    """Load a BDF font from the matrix library as a Pillow bitmap font (converted once, then cached)."""
    if name not in _fonts:
        FONT_CACHE.mkdir(exist_ok=True)
        cached = FONT_CACHE / f"{name}.pil"
        if not cached.exists():
            with open(FONT_DIR / f"{name}.bdf", "rb") as fp:
                BdfFontFile.BdfFontFile(fp).save(str(FONT_CACHE / name))
        _fonts[name] = ImageFont.load(str(cached))
    return _fonts[name]


def text(d, x, y, s, f, color, align="left"):
    width = len(s) * FONT_W[f]
    if align == "center":
        x -= width // 2
    elif align == "right":
        x -= width
    d.text((x, y), s, font=font(f), fill=color)


def fmt(v):
    return "-" if v is None else f"{v:g}"


def parse(ts):
    """Accepts '2026-10-16 15:26' and '2026-10-16T15:29' alike."""
    return datetime.fromisoformat(str(ts).replace(" ", "T")[:19])


# ------------------------------ data -----------------------------------------
def load_snapshot():
    now = datetime.now()
    out = []
    with closing(sqlite3.connect(DB_PATH)) as con:
        con.row_factory = sqlite3.Row
        for tank in con.execute("SELECT id, name FROM tanks ORDER BY name").fetchall():
            rows = con.execute(
                """SELECT created_at, ammonia, nitrite, nitrate, alkalinity, ph, temperature
                   FROM tankdata WHERE tank_id = ? ORDER BY created_at DESC LIMIT 40""",
                (tank["id"],)).fetchall()
            tests = sorted(({**dict(r), "when": parse(r["created_at"])} for r in rows),
                           key=lambda t: t["when"], reverse=True)[:8]
            changes = sorted((parse(r["created_at"]) for r in con.execute(
                "SELECT created_at FROM tankevents WHERE tank_id = ? AND event_type = 'water_change'",
                (tank["id"],))), reverse=True)
            out.append(make_snap(tank["name"], tests, changes, now))
    return out


def make_snap(name, tests, changes, now):
    def days(dt):
        return None if dt is None else (now - dt).total_seconds() / 86400
    return {"name": name, "tests": tests, "water_changes": changes,
            "test_days": days(tests[0]["when"] if tests else None),
            "wc_days": days(changes[0] if changes else None)}


def demo_snapshot():
    now = datetime.now()
    nitrate = [40, 20, 15, 10, 40, 30, 25, 20]          # newest first
    ago = [2, 6, 9, 13, 16, 20, 23, 27]
    tests = [{"when": now - timedelta(days=a), "ammonia": 0, "nitrite": 0, "nitrate": n,
              "alkalinity": 40, "ph": 7.6 if i == 0 else 7.0, "temperature": 82 if i == 0 else 80}
             for i, (a, n) in enumerate(zip(ago, nitrate))]
    changes = [now - timedelta(days=9), now - timedelta(days=14.5)]
    return [make_snap("Main 55g", tests, changes, now)]


# ------------------------------ drawing --------------------------------------
def blank():
    img = Image.new("RGB", (W, H))
    return img, ImageDraw.Draw(img)


def header(d, snap):
    text(d, 1, 0, snap["name"].upper()[:8], "5x7", WHITE)
    if snap["test_days"] is not None:
        text(d, W - 1, 0, f"T {int(snap['test_days'])}D", "4x6", GREY, "right")


def water_change_bar(d, snap):
    days = snap["wc_days"]
    frac = 1 if days is None else min(days / WATER_CHANGE_DAYS, 1)
    color = RED if frac >= 1 else AMBER if frac >= 0.7 else GREEN
    d.rectangle((0, 30, W - 1, 31), fill=TRACK)
    n = round(frac * W)
    if n:
        d.rectangle((0, 30, n - 1, 31), fill=color)


def value_color(key, v):
    if v is None:
        return GREY
    if key in ("ammonia", "nitrite"):
        return GREEN if v == 0 else RED
    if key == "nitrate":
        return GREEN if v < 20 else AMBER if v < NITRATE_WARN else RED
    return WHITE


def delta_info(key, new, old):
    if new is None or old is None or round(new - old, 2) == 0:
        return "-", GREY
    d = round(new - old, 2)
    if key in ("ammonia", "nitrite", "nitrate"):
        return f"{d:+g}", RED if d > 0 else GREEN
    return f"{d:+g}", BLUE


NITROGEN = [("NH3", "ammonia"), ("NO2", "nitrite"), ("NO3", "nitrate")]
CHEMISTRY = [("KH", "alkalinity"), ("PH", "ph"), ("TEMP", "temperature")]


def value_page(snap, columns):
    img, d = blank()
    header(d, snap)
    latest = snap["tests"][0]
    previous = snap["tests"][1] if len(snap["tests"]) > 1 else {}
    for cx, (label, key) in zip((11, 32, 53), columns):
        text(d, cx, 8, label, "5x7", GREY, "center")
        text(d, cx, 16, fmt(latest[key]), "5x7", value_color(key, latest[key]), "center")
        s, color = delta_info(key, latest[key], previous.get(key))
        text(d, cx, 24, s, "4x6", color, "center")
    water_change_bar(d, snap)
    return img


def nitrate_points(snap):
    return [(t["when"], t["nitrate"]) for t in reversed(snap["tests"]) if t["nitrate"] is not None]


def trend_screen(snap):
    img, d = blank()
    pts = nitrate_points(snap)
    text(d, 1, 0, "NO3", "5x7", WHITE)
    text(d, W - 1, 0, f"{len(pts)} TESTS", "4x6", GREY, "right")
    latest = pts[-1][1]
    s, color = delta_info("nitrate", latest, pts[-2][1])
    text(d, 1, 10, fmt(latest), "5x7", value_color("nitrate", latest))
    text(d, 1, 18, s, "4x6", color)

    x0, x1, y_top, y_bot = 24, 61, 9, 28
    t0, t1 = pts[0][0], pts[-1][0]
    span = max((t1 - t0).total_seconds(), 1)
    y_max = max(max(v for _, v in pts), NITRATE_WARN)

    def px(t):
        return x0 + round((t - t0).total_seconds() / span * (x1 - x0))

    def py(v):
        return y_bot - round(v / y_max * (y_bot - y_top))

    for x in range(x0, x1 + 1, 3):                      # dashed warning level
        d.point((x, py(NITRATE_WARN)), fill=DARK_RED)
    for change in snap["water_changes"]:                # blue tick per water change
        if t0 <= change <= t1:
            d.line((px(change), y_top, px(change), y_bot), fill=BLUE)
    coords = [(px(t), py(v)) for t, v in pts]
    d.line(coords, fill=AMBER, width=1)
    lx, ly = coords[-1]
    d.rectangle((lx - 1, ly - 1, lx, ly), fill=value_color("nitrate", latest))
    return img


def warning_screen(snap, flash):
    img, d = blank()
    if flash:
        d.rectangle((0, 0, W - 1, H - 1), outline=RED)
    text(d, 32, 2, "WATER CHANGE", "5x7", RED, "center")
    if snap["wc_days"] is None:
        text(d, 32, 13, "NONE LOGGED", "5x7", WHITE, "center")
    else:
        text(d, 32, 11, f"{int(snap['wc_days'])} DAYS", "6x10", WHITE, "center")
    text(d, 32, 23, snap["name"].upper()[:12], "5x7", GREY, "center")
    return img


def test_due_screen(snap):
    img, d = blank()
    text(d, 32, 2, "TEST DUE", "6x10", AMBER, "center")
    msg = "NO TESTS YET" if snap["test_days"] is None else f"{int(snap['test_days'])} DAYS AGO"
    text(d, 32, 14, msg, "5x7", WHITE, "center")
    text(d, 32, 23, snap["name"].upper()[:12], "5x7", GREY, "center")
    return img


def nodata_screen():
    img, d = blank()
    text(d, 32, 13, "NO DATA", "5x7", GREY, "center")
    return img


def render(kind, snap, flash=True):
    if kind == "nitrogen":
        return value_page(snap, NITROGEN)
    if kind == "chemistry":
        return value_page(snap, CHEMISTRY)
    if kind == "trend":
        return trend_screen(snap)
    if kind == "warning":
        return warning_screen(snap, flash)
    if kind == "test_due":
        return test_due_screen(snap)
    return nodata_screen()


def build_screens(snaps):
    screens = []
    for s in snaps:
        if s["tests"]:
            screens.append(("nitrogen", s))
            if len(nitrate_points(s)) >= 2:
                screens.append(("trend", s))
            screens.append(("chemistry", s))
        if s["test_days"] is None or s["test_days"] >= TEST_DUE_DAYS:
            screens.append(("test_due", s))
        if s["wc_days"] is None or s["wc_days"] >= WATER_CHANGE_DAYS:
            screens.append(("warning", s))
    return screens or [("nodata", None)]


# ------------------------------ running --------------------------------------
def make_matrix():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions   # only exists on the Pi
    o = RGBMatrixOptions()
    o.rows, o.cols, o.chain_length, o.parallel = 32, 64, 1, 1
    o.hardware_mapping = HARDWARE_MAPPING
    o.gpio_slowdown = GPIO_SLOWDOWN
    o.brightness = BRIGHTNESS
    return RGBMatrix(options=o)


def is_night():
    hour = datetime.now().hour
    return hour >= NIGHT_START or hour < NIGHT_END


def run():
    matrix = make_matrix()
    canvas = matrix.CreateFrameCanvas()
    screens, loaded = [], 0.0
    while True:
        if is_night():
            matrix.Clear()
            time.sleep(30)
            continue
        if not screens or time.time() - loaded > REFRESH_SECONDS:
            try:
                screens = build_screens(load_snapshot())
            except (sqlite3.Error, ValueError):
                screens = [("nodata", None)]
            loaded = time.time()
        for kind, snap in screens:
            end, flash = time.time() + ROTATE_SECONDS, True
            while time.time() < end:
                canvas.SetImage(render(kind, snap, flash))
                canvas = matrix.SwapOnVSync(canvas)
                flash = not flash
                time.sleep(0.5)


def preview(demo):
    out = Path(__file__).with_name("preview")
    out.mkdir(exist_ok=True)
    for i, (kind, snap) in enumerate(build_screens(demo_snapshot() if demo else load_snapshot()), 1):
        name = snap["name"].replace(" ", "_") if snap else "none"
        path = out / f"{i:02d}-{kind}-{name}.png"
        render(kind, snap).resize((W * 10, H * 10), Image.NEAREST).save(path)
        print("saved", path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="write PNG previews instead of driving the panel")
    parser.add_argument("--demo", action="store_true", help="with --preview: use sample data, not the database")
    args = parser.parse_args()
    preview(args.demo) if args.preview else run()