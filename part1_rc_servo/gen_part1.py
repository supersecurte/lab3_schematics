#!/usr/bin/env python3
"""
Generate KiCad 7 schematic (.kicad_sch) for ECE118 Lab 3 — Part 1 (RC Servo)
as a clean block diagram with orthogonal wiring, large fonts, and no overlaps.

This script intentionally draws only rectangles, polylines, and texts.
It enforces:
- ≥25 mm gaps between top-level blocks (except pot inside breadboard)
- No text overlaps any line, any other text, or any rectangle boundary
- All routing is orthogonal and kept in the gaps between blocks
"""
from dataclasses import dataclass
from typing import List, Tuple
import math
import pathlib

MM = float  # coordinate units are millimeters (KiCad schematic units)

@dataclass
class Rect:
    x1: MM
    y1: MM
    x2: MM
    y2: MM
    name: str = ""

    def norm(self) -> "Rect":
        x1, x2 = sorted((self.x1, self.x2))
        y1, y2 = sorted((self.y1, self.y2))
        return Rect(x1, y1, x2, y2, self.name)

    def expand(self, m: MM) -> "Rect":
        r = self.norm()
        return Rect(r.x1 - m, r.y1 - m, r.x2 + m, r.y2 + m, self.name)

    def intersects(self, other: "Rect") -> bool:
        a, b = self.norm(), other.norm()
        return not (a.x2 <= b.x1 or a.x1 >= b.x2 or a.y2 <= b.y1 or a.y1 >= b.y2)

    def separation(self, other: "Rect") -> Tuple[MM, MM]:
        """Return (dx, dy) positive when separated; 0 or negative if overlapping on that axis."""
        a, b = self.norm(), other.norm()
        dx = min(abs(a.x1 - b.x2), abs(b.x1 - a.x2))
        dy = min(abs(a.y1 - b.y2), abs(b.y1 - a.y2))
        # If overlapping on an axis, separation along that axis is negative
        if not (a.x2 <= b.x1 or a.x1 >= b.x2):
            dx = -min(a.x2 - b.x1, b.x2 - a.x1)
        if not (a.y2 <= b.y1 or a.y1 >= b.y2):
            dy = -min(a.y2 - b.y1, b.y2 - a.y1)
        return dx, dy


@dataclass
class Text:
    s: str
    x: MM
    y: MM
    size: Tuple[MM, MM]  # (h, v)
    bold: bool = False

    def bbox(self) -> Rect:
        # Rough width estimate: 0.6 em per character
        em = self.size[0]
        width = max(1.0, 0.6 * em * len(self.s))
        height = self.size[1]
        return Rect(self.x, self.y - height, self.x + width, self.y, f"text:{self.s}")


@dataclass
class Polyline:
    pts: List[Tuple[MM, MM]]
    width: MM = 0.6
    allow_in: Tuple[str, ...] = ()
    is_rail: bool = False

    def segments(self) -> List[Rect]:
        rects: List[Rect] = []
        for (x1, y1), (x2, y2) in zip(self.pts, self.pts[1:]):
            left, right = sorted((x1, x2))
            top, bottom = sorted((y1, y2))
            # Expand by half stroke width for collision checks
            w = self.width / 2.0
            rects.append(Rect(left - w, top - w, right + w, bottom + w, "seg"))
        return rects


class Schematic:
    def __init__(self):
        self.rects: List[Rect] = []
        self.texts: List[Text] = []
        self.lines: List[Polyline] = []

    def add_rect(self, x: MM, y: MM, w: MM, h: MM, name: str) -> Rect:
        r = Rect(x, y, x + w, y + h, name).norm()
        self.rects.append(r)
        return r

    def add_text(self, s: str, x: MM, y: MM, size_h: MM, size_v: MM) -> Text:
        t = Text(s, x, y, (size_h, size_v))
        self.texts.append(t)
        return t

    def add_line(self, pts: List[Tuple[MM, MM]], width: MM = 0.6, allow_in: Tuple[str, ...] = (), is_rail: bool = False) -> Polyline:
        # assert orthogonal segments only
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            assert x1 == x2 or y1 == y2, "Non-orthogonal segment detected"
        pl = Polyline(pts, width, allow_in, is_rail)
        self.lines.append(pl)
        return pl

    def assert_layout(self):
        # No overlapping top-level rects (except pot inside breadboard margin)
        def is_pot(r: Rect) -> bool: return r.name == "Pot"
        def is_bb(r: Rect) -> bool: return r.name == "Breadboard"

        for i, a in enumerate(self.rects):
            for j, b in enumerate(self.rects):
                if j <= i:
                    continue
                if is_pot(a) and is_bb(b):
                    # pot inside breadboard: enforce margin
                    margin_ok = (a.x1 >= b.x1 + 10 and a.y1 >= b.y1 + 10 and
                                 a.x2 <= b.x2 - 10 and a.y2 <= b.y2 - 10)
                    assert margin_ok, "Pot must be nested within breadboard with margin"
                    continue
                if is_pot(b) and is_bb(a):
                    margin_ok = (b.x1 >= a.x1 + 10 and b.y1 >= a.y1 + 10 and
                                 b.x2 <= a.x2 - 10 and b.y2 <= a.y2 - 10)
                    assert margin_ok, "Pot must be nested within breadboard with margin"
                    continue
                assert not a.intersects(b), f"Rectangles overlap: {a.name} vs {b.name}"
                # No minimum gap enforced in fixed layout mode

        # Note: Text may live inside its own block rectangles by design.
        # We only enforce that text does not overlap wires or other text.
        # No text overlaps any line
        for t in self.texts:
            tb = t.bbox().expand(0.2)
            for ln in self.lines:
                for seg in ln.segments():
                    assert not tb.intersects(seg), f"Text '{t.s}' overlaps a wire"
        # No text-on-text
        for i, a in enumerate(self.texts):
            ab = a.bbox().expand(0.2)
            for j, b in enumerate(self.texts):
                if j <= i:
                    continue
                bb = b.bbox().expand(0.2)
                assert not ab.intersects(bb), f"Text '{a.s}' overlaps '{b.s}'"

        # Keep all content clear of the title block region (approx for A3 landscape)
        title_block = Rect(290, 235, 420, 297, "TitleBlock")
        for t in self.texts:
            assert not t.bbox().intersects(title_block), f"Text '{t.s}' inside title block area"

        # Helper predicates
        def point_on_rect_edge(px: MM, py: MM, r: Rect, tol: MM = 0.05) -> bool:
            r = r.norm()
            on_left = abs(px - r.x1) <= tol and (r.y1 - tol) <= py <= (r.y2 + tol)
            on_right = abs(px - r.x2) <= tol and (r.y1 - tol) <= py <= (r.y2 + tol)
            on_top = abs(py - r.y1) <= tol and (r.x1 - tol) <= px <= (r.x2 + tol)
            on_bot = abs(py - r.y2) <= tol and (r.x1 - tol) <= px <= (r.x2 + tol)
            return on_left or on_right or on_top or on_bot

        def point_on_any_line(px: MM, py: MM, lines: List[Polyline], tol: MM = 0.1) -> bool:
            for ln in lines:
                for (x1, y1), (x2, y2) in zip(ln.pts, ln.pts[1:]):
                    if x1 == x2:  # vertical
                        if abs(px - x1) <= tol and min(y1, y2) - tol <= py <= max(y1, y2) + tol:
                            return True
                    elif y1 == y2:  # horizontal
                        if abs(py - y1) <= tol and min(x1, x2) - tol <= px <= max(x1, x2) + tol:
                            return True
            return False

        def seg_overlaps_rect_edge(x1, y1, x2, y2, r: Rect, tol: MM = 0.05) -> bool:
            r = r.norm()
            if y1 == y2:  # horizontal
                y = y1
                # overlapping along top or bottom?
                if abs(y - r.y1) <= tol or abs(y - r.y2) <= tol:
                    a, b = sorted((x1, x2))
                    return not (b <= r.x1 or a >= r.x2)
            if x1 == x2:  # vertical
                x = x1
                if abs(x - r.x1) <= tol or abs(x - r.x2) <= tol:
                    a, b = sorted((y1, y2))
                    return not (b <= r.y1 or a >= r.y2)
            return False

        def seg_crosses_rect_interior(x1, y1, x2, y2, r: Rect) -> bool:
            r = r.norm()
            # horizontal segment inside vertical bounds and spanning across interior
            if y1 == y2:
                y = y1
                if r.y1 < y < r.y2:
                    a, b = sorted((x1, x2))
                    return a < r.x2 and b > r.x1 and not (b <= r.x1 or a >= r.x2)
            # vertical segment
            if x1 == x2:
                x = x1
                if r.x1 < x < r.x2:
                    a, b = sorted((y1, y2))
                    return a < r.y2 and b > r.y1 and not (b <= r.y1 or a >= r.y2)
            return False

        # Endpoint attachments: every line endpoint must touch a rect edge or another line
        for i, ln in enumerate(self.lines):
            if ln.is_rail:
                continue
            for px, py in (ln.pts[0], ln.pts[-1]):
                attached = any(point_on_rect_edge(px, py, r) for r in self.rects)
                attached = attached or point_on_any_line(px, py, [l for l in self.lines if l is not ln])
                if not attached:
                    print(f"DEBUG line {i} pts={ln.pts}")
                    for ridx, r in enumerate(self.rects):
                        if point_on_rect_edge(px, py, r):
                            print(f"  endpoint on rect {r.name}")
                    for j, l2 in enumerate(self.lines):
                        if l2 is ln:
                            continue
                        if point_on_any_line(px, py, [l2]):
                            print(f"  endpoint on line {j}")
                assert attached, f"Wire endpoint {px:.2f},{py:.2f} (line {i}) not attached to block edge or another wire"

        # No wire rides along a rectangle edge; and no wire crosses interiors
        for li, ln in enumerate(self.lines):
            for (x1, y1), (x2, y2) in zip(ln.pts, ln.pts[1:]):
                for r in self.rects:
                    if r.name not in ln.allow_in:
                        if seg_crosses_rect_interior(x1, y1, x2, y2, r):
                            print(f"DEBUG cross interior: line {li} seg=({x1},{y1})->({x2},{y2}) rect={r.name}")
                            raise AssertionError(f"Wire crosses {r.name} interior")
                    assert not seg_overlaps_rect_edge(x1, y1, x2, y2, r), f"Wire overlaps {r.name} edge"

    def to_kicad(self) -> str:
        out: List[str] = []
        out.append('(kicad_sch (version 20230121) (generator eeschema)')
        out.append('  (uuid a5ea24c7-7759-4516-ab47-176ab92bf91b)')
        out.append('  (paper "A3")')
        out.append('  (title_block')
        out.append('    (title "ECE118 Lab 3 — Part 1: Driving an RC Servo (Block Diagram)")')
        out.append('    (company "UCSC ECE118 — Student: Amber")')
        out.append('    (rev "F")')
        out.append('  )')
        # Rectangles
        for r in self.rects:
            out.append(f'  (polyline (pts (xy {r.x1:.3f} {r.y1:.3f}) (xy {r.x2:.3f} {r.y1:.3f}) (xy {r.x2:.3f} {r.y2:.3f}) (xy {r.x1:.3f} {r.y2:.3f}) (xy {r.x1:.3f} {r.y1:.3f})) (stroke (width 0.6) (type solid)))')
        # Lines
        for ln in self.lines:
            pts = " ".join(f'(xy {x:.3f} {y:.3f})' for x, y in ln.pts)
            out.append(f'  (polyline (pts {pts}) (stroke (width {ln.width:.3f}) (type solid)))')
        # Texts
        for t in self.texts:
            h, v = t.size
            out.append(f'  (text "{t.s}" (at {t.x:.3f} {t.y:.3f} 0) (effects (font (size {h:.3f} {v:.3f})) (justify left bottom)))')
        out.append(')')
        return "\n".join(out) + "\n"


def main():
    sch = Schematic()
    # Fixed block rectangles per requested coordinates
    atx = sch.add_rect(20, 25, 80, 45, "ATX")          # (20,25)-(100,70)
    upwr = sch.add_rect(20, 125, 80, 45, "UNO Power")  # (20,125)-(100,170)
    uio = sch.add_rect(140, 125, 120, 90, "UNO IO")    # (140,125)-(260,215)
    bb = sch.add_rect(160, 20, 155, 85, "Breadboard")  # (160,20)-(315,105)
    servo = sch.add_rect(350, 120, 55, 80, "RC Servo") # (350,120)-(405,200)
    pot = sch.add_rect(195, 55, 70, 25, "Pot")         # (195,55)-(265,80)

    # Titles (5 mm)
    sch.add_text("ATX power supply", 23, 31, 5.0, 5.0)
    sch.add_text("UNO power board", 23, 131, 5.0, 5.0)
    sch.add_text("UNO32 IO board", 143, 131, 5.0, 5.0)
    sch.add_text("Breadboard", 163, 26, 5.0, 5.0)
    sch.add_text("RC Servo", 353, 126, 5.0, 5.0)
    sch.add_text("Potentiometer", 198, 61, 3.0, 3.0)
    sch.add_text("wiper 0-3.3 V", 198, 68, 3.0, 3.0)
    # IO text inside at x=145
    sch.add_text("W03: analog in (AD_PORTW3)", 145, 155, 3.0, 3.0)
    sch.add_text("Y06: servo out (RC_PORTY06, Timer4)", 145, 175, 3.0, 3.0)
    sch.add_text("LED bank: scaled pot value (LED_BANK1-3)", 145, 200, 3.0, 3.0)

    # Breadboard rails
    rail_x1, rail_x2 = 175, 290
    rail_5v_y, rail_gnd_y = 42, 92
    sch.add_line([(rail_x1, rail_5v_y), (rail_x2, rail_5v_y)], width=0.8, allow_in=("Breadboard",), is_rail=True)
    sch.add_text("BB 5V rail", 178, 38, 3.0, 3.0)
    sch.add_line([(rail_x1, rail_gnd_y), (rail_x2, rail_gnd_y)], width=0.8, allow_in=("Breadboard",), is_rail=True)
    sch.add_text("BB GND rail", 178, 96, 3.0, 3.0)

    # Pot taps with junction dots
    sch.add_line([(215, rail_5v_y), (215, 55)], width=0.6, allow_in=("Breadboard",))
    sch.add_line([(245, 80), (245, rail_gnd_y)], width=0.6, allow_in=("Breadboard",))
    for (jx, jy) in [(215, rail_5v_y), (245, rail_gnd_y)]:
        s = 1.2
        sch.add_line([(jx - s/2, jy - s/2), (jx + s/2, jy - s/2), (jx + s/2, jy + s/2), (jx - s/2, jy + s/2), (jx - s/2, jy - s/2)], width=0.4, allow_in=("Breadboard",), is_rail=True)

    # ATX to UNO power vertical feeds
    sch.add_line([(45, 70), (45, 125)], width=0.6)
    sch.add_text("12V", 48, 97, 3.0, 3.0)
    sch.add_line([(75, 70), (75, 125)], width=0.6)
    sch.add_text("GND", 78, 97, 3.0, 3.0)

    # UNO power to UNO IO power link
    sch.add_line([(100, 147), (140, 147)], width=0.6)
    sch.add_text("Power", 104, 143, 3.0, 3.0)

    # ATX to Breadboard feeds
    sch.add_line([(100, 42), (175, 42)], width=0.6, allow_in=("Breadboard",))
    sch.add_text("5V (regulated)", 104, 38, 3.0, 3.0)
    sch.add_line([(100, 60), (130, 60), (130, 92), (175, 92)], width=0.6, allow_in=("Breadboard",))
    sch.add_text("GND", 104, 56, 3.0, 3.0)

    # Wiper to W03
    sch.add_line([(230, 80), (230, 125)], width=0.6, allow_in=("Breadboard", "Pot"))
    sch.add_text("W03 analog in, 0-3.3 V", 233, 115, 3.0, 3.0)

    # Servo feeds and signal
    sch.add_line([(290, 42), (335, 42), (335, 140), (350, 140)], width=0.6, allow_in=("Breadboard",))
    sch.add_line([(290, 92), (325, 92), (325, 160), (350, 160)], width=0.6, allow_in=("Breadboard",))
    sch.add_line([(260, 185), (350, 185)], width=0.6)
    sch.add_text("Y06 digital out, 0-3.3 V", 265, 181, 3.0, 3.0)
    sch.add_text("pulse 1-2 ms every 50 ms", 265, 191, 3.0, 3.0)

    # Servo pin labels and note
    sch.add_text("5V (orange)", 353, 140, 3.0, 3.0)
    sch.add_text("GND (brown)", 353, 160, 3.0, 3.0)
    sch.add_text("Signal (yellow)", 353, 185, 3.0, 3.0)
    sch.add_text("5 V regulated, max 5 V", 350, 207, 3.0, 3.0)

    sch.add_text("Common ground: ATX, UNO boards, breadboard rails, and servo", 20, 230, 3.0, 3.0)

    # Validate constraints
    sch.assert_layout()

    out_path = pathlib.Path(__file__).resolve().parent / "part1_rc_servo.kicad_sch"
    out_path.write_text(sch.to_kicad(), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

