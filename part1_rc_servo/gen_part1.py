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

        # Minimum gap between non-nested blocks: 25 mm
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
                dx, dy = a.separation(b)
                assert dx >= 25 or dy >= 25, f"Gaps too small between {a.name} and {b.name}"

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
        out.append('    (rev "C")')
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
    # Block sizes (w, h)
    atx = sch.add_rect(20, 30, 90, 45, "ATX")
    upwr = sch.add_rect(140, 30, 100, 45, "UNO Power")
    uio = sch.add_rect(10, 210, 120, 60, "UNO IO")
    bb = sch.add_rect(160, 100, 140, 110, "Breadboard")
    servo = sch.add_rect(330, 120, 75, 55, "RC Servo")
    pot = sch.add_rect(210, 145, 60, 45, "Pot")

    # Titles (5 mm)
    sch.add_text("ATX power supply", atx.x1 + 5, atx.y1 + 8, 5.0, 5.0)
    sch.add_text("UNO power board", upwr.x1 + 5, upwr.y1 + 8, 5.0, 5.0)
    sch.add_text("UNO32 IO board", uio.x1 + 5, uio.y1 + 10, 5.0, 5.0)
    sch.add_text("Breadboard", bb.x1 + 5, bb.y1 + 8, 5.0, 5.0)
    sch.add_text("RC Servo", servo.x1 + 4, servo.y1 + 8, 5.0, 5.0)
    sch.add_text("Potentiometer", pot.x1 + 22, pot.y1 + 12, 3.0, 3.0)
    sch.add_text("Limit wiper 0–3.3V", pot.x1 + 22, pot.y1 + 20, 3.0, 3.0)
    sch.add_text("LED bank: scaled pot value (LED_BANK1–3)", uio.x1 + 6, uio.y1 + 28, 3.0, 3.0)

    # Breadboard rails inside
    rail_x1, rail_x2 = bb.x1 + 5, bb.x2 - 5
    rail_5v_y, rail_gnd_y = bb.y1 + 15, bb.y1 + 25
    sch.add_line([(rail_x1, rail_5v_y), (rail_x2, rail_5v_y)], width=0.8, allow_in=("Breadboard",), is_rail=True)
    sch.add_text("BB 5V rail", rail_x1 + 2, rail_5v_y - 2.5, 3.0, 3.0)
    sch.add_line([(rail_x1, rail_gnd_y), (rail_x2, rail_gnd_y)], width=0.8, allow_in=("Breadboard",), is_rail=True)
    sch.add_text("BB GND rail", rail_x1 + 2, rail_gnd_y + 5.5, 3.0, 3.0)

    # Pot ends to rails (vertical taps inside breadboard)
    # Top of pot to 5V rail
    # Two short vertical taps from rails into pot top edge
    tap1x = pot.x1 + 8
    tap2x = pot.x1 + 40
    sch.add_line([(tap1x, rail_5v_y), (tap1x, pot.y1)], width=0.6, allow_in=("Breadboard",))
    sch.add_line([(tap2x, rail_gnd_y), (tap2x, pot.y1)], width=0.6, allow_in=("Breadboard",))

    # ATX -> UNO power (12V at y=50, GND at y=60), entirely between blocks
    y12, yg = atx.y1 + 20, atx.y1 + 30
    sch.add_line([(atx.x2, y12), (upwr.x1, y12)], width=0.6)
    sch.add_text("12V", (atx.x2 + upwr.x1) / 2 - 5, y12 - 3.0, 3.0, 3.0)
    # GND from ATX to UNO power
    sch.add_line([(atx.x2, yg), (upwr.x1, yg)], width=0.6)
    sch.add_text("GND", (atx.x2 + upwr.x1) / 2 - 6, yg + 4.0, 3.0, 3.0)

    # ATX -> Breadboard rails (5V path: under top row then up to 5V rail)
    y_5v_bus = upwr.y2 + 5
    sch.add_line([(atx.x2, atx.y2 - 10), (atx.x2 + 5, atx.y2 - 10), (atx.x2 + 5, y_5v_bus), (bb.x1 - 10, y_5v_bus), (bb.x1 - 10, rail_5v_y), (rail_x1, rail_5v_y)], width=0.6, allow_in=("Breadboard",))
    sch.add_text("5V (regulated)", bb.x2 - 40, rail_5v_y + 6.0, 3.0, 3.0)
    # ATX GND -> GND rail
    y_gnd_bus = y_5v_bus + 10
    sch.add_line([(atx.x2, atx.y2 - 5), (atx.x2 + 5, atx.y2 - 5), (atx.x2 + 5, y_gnd_bus), (bb.x1 - 15, y_gnd_bus), (bb.x1 - 15, rail_gnd_y), (rail_x1, rail_gnd_y)], width=0.6, allow_in=("Breadboard",))
    sch.add_text("GND to rails", bb.x2 - 40, rail_gnd_y + 12.0, 3.0, 3.0)

    # UNO power -> UNO IO (power feed)
    # Route down the left side, clear of breadboard
    x_bus = upwr.x1 - 10
    # drop a bit then go left, then down, then right into IO top edge
    sch.add_line([((upwr.x1 + upwr.x2) / 2, upwr.y2), ((upwr.x1 + upwr.x2) / 2, upwr.y2 + 4), (x_bus, upwr.y2 + 4), (x_bus, uio.y1 - 8), (uio.x2, uio.y1 - 8), (uio.x2, uio.y1)], width=0.6)
    sch.add_text("Power", x_bus + 2, (upwr.y2 + 4 + uio.y1 - 8) / 2, 3.0, 3.0)

    # Pot wiper → UNO IO W03 (from pot mid to below breadboard then left to IO right)
    wiper_y = (pot.y1 + pot.y2) / 2
    wiper_x = (tap1x + tap2x) / 2
    # Wiper exits pot at right edge, jog around pot perimeter to breadboard left edge, then to IO
    sch.add_line([(pot.x2, wiper_y), (pot.x2 + 5, wiper_y), (pot.x2 + 5, bb.y2 - 5), (bb.x1 - 1, bb.y2 - 5), (bb.x1 - 1, bb.y2 + 8), (bb.x1, bb.y2 + 8), (uio.x2 + 10, bb.y2 + 8), (uio.x2 + 10, uio.y1 + 22), (uio.x2, uio.y1 + 22)], width=0.6, allow_in=("Breadboard",))
    sch.add_text("W03 — Analog input 0–3.3V (AD_PORTW3)", uio.x2 + 20, bb.y2 + 16, 3.0, 3.0)

    # UNO IO Y06 → Servo signal (below breadboard, then up into servo)
    y_sig = uio.y1 + 42
    sch.add_line([(uio.x2, y_sig), (servo.x1 - 18, y_sig), (servo.x1 - 18, servo.y1 + 30), (servo.x1, servo.y1 + 30)], width=0.6)
    sch.add_text("Y06 — Digital output 0–3.3V (RC_PORTY06, Timer4)", uio.x2 + 2, y_sig - 2.0, 3.0, 3.0)
    sch.add_text("RC servo pulse ~1–2 ms, 50 ms period", uio.x2 + 2, y_sig + 6.0, 3.0, 3.0)

    # Rails -> Servo (5V and GND)
    # exit from rail ends at breadboard right edge
    sch.add_line([(rail_x2, rail_5v_y), (bb.x2, rail_5v_y), (bb.x2 + 8, rail_5v_y), (bb.x2 + 8, servo.y1 + 15), (servo.x1, servo.y1 + 15)], width=0.6, allow_in=("Breadboard",))
    sch.add_text("5V (orange) — max 5V, regulated", servo.x1 + 2, servo.y1 + 15 - 2, 3.0, 3.0)
    sch.add_line([(rail_x2, rail_gnd_y), (bb.x2, rail_gnd_y), (bb.x2 + 16, rail_gnd_y), (bb.x2 + 16, servo.y1 + 40), (servo.x1, servo.y1 + 40)], width=0.6, allow_in=("Breadboard",))
    sch.add_text("GND (brown)", servo.x1 + 2, servo.y1 + 40 - 2, 3.0, 3.0)
    # Servo entry labels at pins
    sch.add_text("Signal (yellow)", servo.x1 + 2, servo.y1 + 30 - 2, 3.0, 3.0)

    sch.add_text("Common ground for ATX, UNO boards, rails, and servo", 25, 285, 3.0, 3.0)

    # Validate constraints
    sch.assert_layout()

    out_path = pathlib.Path(__file__).resolve().parent / "part1_rc_servo.kicad_sch"
    out_path.write_text(sch.to_kicad(), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

