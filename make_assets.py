#!/usr/bin/env python3
"""Render the GATEKEEPER cover and screenshots from the game's own data.

Why code and not an image model: these are *submission* assets for a game
competition, so a screenshot has to show the real thing. Everything drawn here
comes from bank.json (the same file index.html embeds) and from the design tokens
copied out of index.html's stylesheet, so the pictures cannot drift from the
game. An AI-generated "screenshot" would be a fabrication, which is the one thing
this project is about.

Outputs (next to this file):
    cover.png        1600x900  store/submission banner
    shot_day1.png    1280x800  Day 1 - plaintext injection, engine agrees
    shot_day4.png    1280x800  Day 4 - the all-benign false-pressure day
    shot_day6.png    1280x800  Day 6 - real-format PII, engine wrongly releases
    shot_score.png   1280x800  end-of-week scoreboard with the three baselines

Needs Pillow (this repo's own suite is stdlib-only; this asset script is not part
of eval.py, so a missing Pillow never turns CI red).

Run:  python make_assets.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    sys.stderr.write("make_assets.py needs Pillow: pip install pillow\n")
    raise SystemExit(2)

_HERE = Path(__file__).resolve().parent

# --- design tokens, copied verbatim from index.html :root --------------------
BG = "#0a0e14"
PANEL = "#111824"
PANEL2 = "#0d141e"
LINE = "#1e2a3a"
INK = "#e6edf3"
DIM = "#8b9bb0"
ACCENT = "#39d3ff"
WARN = "#ffb454"
BAD = "#ff5c6c"
GOOD = "#4ade80"
MID = "#a78bfa"
BTN = "#16202e"

MONO = "C:/Windows/Fonts/CascadiaMono.ttf"
CJK = "C:/Windows/Fonts/msyh.ttc"

_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    key = (path, size)
    if key not in _cache:
        try:
            _cache[key] = ImageFont.truetype(path, size)
        except OSError:
            _cache[key] = ImageFont.truetype(MONO, size)
    return _cache[key]


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (0x2E80 <= o <= 0x9FFF) or (0xF900 <= o <= 0xFAFF) or (0xFF00 <= o <= 0xFFEF)


def text(d: ImageDraw.ImageDraw, x: int, y: int, s: str, size: int, fill: str,
         bold_path: str | None = None) -> int:
    """Draw mixed CJK/Latin text, switching font per character. Returns width."""
    cx = x
    for ch in s:
        path = CJK if _is_cjk(ch) else (bold_path or MONO)
        f = _font(path, size)
        d.text((cx, y), ch, font=f, fill=fill)
        cx += int(d.textlength(ch, font=f))
    return cx - x


def text_w(d: ImageDraw.ImageDraw, s: str, size: int) -> int:
    total = 0
    for ch in s:
        f = _font(CJK if _is_cjk(ch) else MONO, size)
        total += int(d.textlength(ch, font=f))
    return total


def wrap(d: ImageDraw.ImageDraw, s: str, size: int, max_w: int) -> list[str]:
    """Wrap on character boundaries; CJK needs no spaces, Latin does."""
    lines, cur = [], ""
    for ch in s:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if text_w(d, trial, size) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def rrect(d: ImageDraw.ImageDraw, box, r: int, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def pill(d: ImageDraw.ImageDraw, x: int, y: int, label: str, fg: str, bg: str, size=15):
    w = text_w(d, label, size) + 20
    h = size + 14
    rrect(d, (x, y, x + w, y + h), h // 2, fill=bg)
    text(d, x + 10, y + 6, label, size, fg)
    return w


def chrome(img: Image.Image, title: str, sub: str) -> ImageDraw.ImageDraw:
    """Outer page frame: title + subtitle, matching index.html's h1/.sub."""
    d = ImageDraw.Draw(img)
    text(d, 40, 34, title, 30, INK)
    text(d, 40, 78, sub, 15, DIM)
    return d


# --- the shared "one request" panel -----------------------------------------

def request_panel(d: ImageDraw.ImageDraw, x: int, y: int, w: int, q: dict,
                  show_engine: bool = True) -> int:
    """Draw the request card exactly as index.html lays it out. Returns bottom y."""
    # top bar: DAY / score / engine suggestion
    rrect(d, (x, y, x + w, y + 46), 14, fill=PANEL, outline=LINE)
    text(d, x + 22, y + 14, "DAY %d" % q["day"], 16, ACCENT)
    mid = x + w // 2
    text(d, mid, y + 14, "SCORE  1240", 15, DIM)
    eng = "ENGINE SUGGESTS: %s" % q["engine_action"].upper()
    ew = text_w(d, eng, 15)
    text(d, x + w - 22 - ew, y + 14, eng, 15, WARN if not q["engine_agrees"] else DIM)
    y += 62

    # request box (panel2, 3px accent left border, radius 8, padding 16)
    lines = wrap(d, q["text"], 17, w - 76)
    box_h = 32 + len(lines) * 28
    rrect(d, (x, y, x + w, y + box_h), 8, fill=PANEL2, outline=LINE)
    d.rectangle((x, y + 8, x + 3, y + box_h - 8), fill=ACCENT)
    ty = y + 16
    for ln in lines:
        text(d, x + 24, ty, ln, 17, INK)
        ty += 28
    y += box_h + 26

    # three action buttons
    labels = [("RELEASE", "放行"), ("BLOCK", "拦截"), ("REDACT", "脱敏转发")]
    bw = (w - 40) // 3
    for i, (en, zh) in enumerate(labels):
        bx = x + 10 + i * (bw + 10)
        hot = (q["truth_action"] == ["release", "block", "redact"][i])
        rrect(d, (bx, y, bx + bw, y + 74), 10, fill=ACCENT if hot else BTN,
              outline=None if hot else LINE)
        fg = "#04121a" if hot else INK
        lw = text_w(d, en, 18)
        text(d, bx + (bw - lw) // 2, y + 12, en, 18, fg)
        lw2 = text_w(d, zh, 14)
        text(d, bx + (bw - lw2) // 2, y + 42, zh, 14, fg)
    y += 74

    if show_engine:
        y += 22
        agree = q["engine_agrees"]
        if agree:
            msg = "Engine is right here. No bonus for agreeing."
            col, tag, tagbg = DIM, "AGREE", "#1b2735"
        else:
            msg = "Engine says %s. The correct call is %s. Overruling it pays +%d." % (
                q["engine_action"], q["truth_action"], q["catch_bonus"])
            col, tag, tagbg = MID, "DISAGREE", "#241d3d"
        rrect(d, (x, y, x + w, y + 54), 8, fill=PANEL, outline=LINE)
        pw = pill(d, x + 14, y + 14, tag, col, tagbg)
        text(d, x + 14 + pw + 12, y + 17, msg, 15, col)
        y += 54
    return y


# --- individual assets ------------------------------------------------------


def cover(bank: dict) -> None:
    W, H = 1600, 900
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # faint scanline texture
    for yy in range(0, H, 4):
        d.line(((0, yy), (W, yy)), fill="#0c1119")

    text(d, 80, 90, "GATEKEEPER", 76, INK)
    text(d, 84, 186, "守门人", 40, ACCENT)
    text(d, 84, 250, "The gateway suggests. You are scored on overruling it.", 22, DIM)
    text(d, 84, 284, "机器给你建议；你的分数，取决于知不知道什么时候该不听它的。", 20, DIM)

    # three baseline cards
    def play(pol):
        s = 0
        for q in bank["questions"]:
            a = "release" if pol == "release" else (
                q["engine_action"] if pol == "obey" else q["truth_action"])
            if a == q["truth_action"]:
                s += q["score_right"]
                if not q["engine_agrees"]:
                    s += q["catch_bonus"]
            else:
                s += q["penalty_wrong"]
        return s

    rows = [("RELEASE EVERYTHING", play("release"), BAD, "27 attacks missed"),
            ("OBEY THE ENGINE", play("obey"), WARN, "2 missed, 0 corrections"),
            ("PLAY IT YOURSELF", play("perfect"), GOOD, "0 missed, 6 corrections")]
    cw, gap = 440, 24
    x0 = 80
    for i, (name, val, col, note) in enumerate(rows):
        x = x0 + i * (cw + gap)
        rrect(d, (x, 380, x + cw, 560), 14, fill=PANEL, outline=LINE)
        text(d, x + 24, 404, name, 16, DIM)
        text(d, x + 24, 436, "%+d" % val, 54, col)
        text(d, x + 24, 512, note, 15, DIM)
    text(d, 80, 596, "Deferring to the machine costs %d points. That gap is the game."
         % (play("perfect") - play("obey")), 20, MID)

    # bottom strip: hard facts
    facts = [("50", "prompts"), ("7", "days"), ("27/10/13", "attack / ordinary / edge"),
             ("6", "engine errors"), ("95", "assertions"), ("0", "dependencies")]
    bw = (W - 160) // 6
    for i, (big, small) in enumerate(facts):
        x = 80 + i * bw
        d.line((x, 700, x, 760), fill=LINE, width=2)
        text(d, x, 712, big, 30, ACCENT)
        text(d, x, 754, small, 14, DIM)
    text(d, 80, 820, "github.com/Zhiyilang/GateKeeper   ·   MIT   ·   single-file HTML, no server, no network",
         16, DIM)
    img.save(_HERE / "cover.png")
    print("cover.png            %dx%d" % (W, H))


def shot(name: str, q: dict, note: str, note_col: str, title: str, sub: str) -> None:
    W, H = 1280, 800
    img = Image.new("RGB", (W, H), BG)
    d = chrome(img, title, sub)
    bottom = request_panel(d, 320, 130, 920, q)
    # side rail: what this shot is meant to show
    rrect(d, (40, 130, 292, bottom), 14, fill=PANEL, outline=LINE)
    text(d, 62, 152, "WHAT THIS SHOWS", 13, DIM)
    yy = 184
    for ln in wrap(d, note, 14, 212):
        text(d, 62, yy, ln, 14, note_col)
        yy += 23
    rrect(d, (40, bottom - 70, 292, bottom - 14), 10, fill=PANEL2, outline=LINE)
    text(d, 62, bottom - 58, q["kind"].upper(), 14, DIM)
    text(d, 62, bottom - 36, "id %s" % q["id"], 13, DIM)
    img.save(_HERE / name)
    print("%-18s %dx%d  (%s)" % (name, W, H, q["id"]))


def scoreboard(bank: dict) -> None:
    W, H = 1280, 800
    img = Image.new("RGB", (W, H), BG)
    d = chrome(img, "End of week", "Seven shifts. The engine was wrong six times.")

    def play(pol):
        s = 0
        for q in bank["questions"]:
            a = "release" if pol == "release" else (
                q["engine_action"] if pol == "obey" else q["truth_action"])
            if a == q["truth_action"]:
                s += q["score_right"]
                if not q["engine_agrees"]:
                    s += q["catch_bonus"]
            else:
                s += q["penalty_wrong"]
        return s

    rows = [("You released everything", play("release"), BAD, "27 of 27 attacks got through"),
            ("You obeyed the engine", play("obey"), WARN, "2 attacks missed, 0 corrections"),
            ("You judged for yourself", play("perfect"), GOOD, "0 missed, 6 corrections")]
    y = 140
    for i, (name, val, col, note) in enumerate(rows):
        rrect(d, (80, y, 1200, y + 110), 14, fill=PANEL if i else PANEL2,
              outline=LINE, width=2 if i == 2 else 1)
        text(d, 110, y + 20, name, 20, INK if i == 2 else DIM)
        text(d, 110, y + 56, note, 15, DIM)
        vw = text_w(d, "%+d" % val, 46)
        text(d, 1200 - 40 - vw, y + 32, "%+d" % val, 46, col)
        y += 130
    gap = play("perfect") - play("obey")
    text(d, 80, y + 24, "The machine costs you %d points. Not because it is useless -" % gap, 19, MID)
    text(d, 80, y + 52, "because it is wrong in exactly the places that matter.", 19, MID)
    img.save(_HERE / "shot_score.png")
    print("shot_score.png       %dx%d" % (W, H))


def main() -> int:
    bank = json.loads((_HERE / "bank.json").read_text(encoding="utf-8"))
    qs = bank["questions"]
    by_id = {q["id"]: q for q in qs}

    # Honesty guard: the numbers painted on the cover and the scoreboard are
    # recomputed here, and the assets are only written if they match the values
    # published in README/SUBMISSION. If the bank ever shifts the scores, this
    # script refuses to ship a picture that disagrees with the docs.
    def play(pol):
        s = 0
        for q in qs:
            a = "release" if pol == "release" else (
                q["engine_action"] if pol == "obey" else q["truth_action"])
            if a == q["truth_action"]:
                s += q["score_right"]
                if not q["engine_agrees"]:
                    s += q["catch_bonus"]
            else:
                s += q["penalty_wrong"]
        return s

    for pol, want in (("release", -242), ("obey", 308), ("perfect", 454)):
        got = play(pol)
        if got != want:
            sys.stderr.write(
                "refusing to render: policy %s scores %d, docs claim %d\n" % (pol, got, want))
            return 1
    disagreements = sum(1 for q in qs if not q["engine_agrees"])
    if disagreements != 6:
        sys.stderr.write("refusing to render: %d disagreements, docs claim 6\n" % disagreements)
        return 1

    cover(bank)
    shot("shot_day1.png", by_id["q001"],
         "Day 1 is plaintext injection. The engine gets it right, so there is no "
         "bonus for agreeing with it. The skill starts here: knowing what the "
         "machine is good at.",
         DIM, "Day 1 - plaintext injection",
         "27 attacks / 10 ordinary / 13 edge, every engine verdict measured")
    shot("shot_day4.png", by_id["q023"],
         "Day 4 has no attacks at all. Ten ordinary requests in a row. Blocking "
         "one costs 14 - the heaviest penalty in the game, heavier than letting "
         "an attack through. This day punishes 'when in doubt, block'.",
         WARN, "Day 4 - the false-pressure day",
         "Zero attacks. Ten ordinary requests. Every wrong block costs 14.")
    shot("shot_day6.png", by_id["q042"],
         "A real-format national ID number. The engine releases it. The correct "
         "call is redact-and-forward - which the engine cannot even express, "
         "since it only ever does release or block. Overruling pays +5.",
         MID, "Day 6 - real PII the engine releases",
         "4 of the 6 engine errors live on this day")
    scoreboard(bank)
    print("all assets rendered from bank.json; scores pinned to -242 / 308 / 454")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
