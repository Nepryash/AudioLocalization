"""Live three-microphone FFT-phase direction dashboard.

Usage: python tools/angle_visualizer.py --port COM7
       python tools/angle_visualizer.py --demo
Requires pyserial only for a live port; the GUI uses Python's Tkinter.
"""

from __future__ import annotations

import argparse
import math
import queue
import random
import re
import threading
import time
import tkinter as tk
from collections import deque

COLORS = ("#45caff", "#f6bd60", "#a88cff")
BG = "#0d1424"
PANEL = "#172238"
GRID = "#34435e"
TEXT = "#eaf1ff"
MUTED = "#8fa1c0"
GOOD = "#58dcaa"
BAD = "#ff777d"
PROVISIONAL = "#f6bd60"


def parse_line(line: str):
    """Parse firmware telemetry; unknown/log lines are ignored."""
    if line.startswith("SYNC3 "):
        values = {}
        for key, value in re.findall(r"([a-zA-Z][a-zA-Z0-9_]*)=([^\s]+)", line):
            try:
                values[key] = float(value)
            except ValueError:
                pass
        return ("sync", values) if "f" in values else None
    match = re.fullmatch(r">mic([123]):(-?\d+)", line.strip())
    if match:
        return "mic", (int(match.group(1)) - 1, int(match.group(2)))
    return None


def angle_status(s: dict, fresh: bool, mode: str = "calibrated") -> tuple[bool, str]:
    """Decide whether to draw a front-hemisphere phase estimate."""
    if not fresh:
        return False, "No recent SYNC3 telemetry; check COM port and firmware"
    state = int(s.get("state", -1))
    if state == 0:
        return False, "DMA warmup in progress"
    if state == 1:
        return False, (f"CAL collecting stable tone windows "
                       f"{int(s.get('cal_n', 0))}/20; hold the tone steady")
    if s.get("phase_n", 0) < 1 or s.get("f", 0) <= 0:
        return False, "No accepted 80–200 Hz FFT phase; check tone and all 3 microphones"
    if mode == "uncalibrated":
        if "raw_az" not in s or "raw_el" not in s or "raw_r" not in s:
            return False, "Raw angle telemetry missing; upload the updated firmware"
        if s["phase_n"] < 3:
            return False, "Band activity detected; need 3 accepted windows for a bearing"
        if "coh" in s and s["coh"] < 0.90:
            return False, f"Band activity detected; phase coherence {s['coh']:.3f} < 0.900"
        if s["raw_r"] > 1.05:
            return False, f"Raw phase exceeds 20 cm geometry: projection {s['raw_r']:.2f}"
        return True, "PROVISIONAL raw FFT direction · uncalibrated"
    if s.get("cal", 0) < 1:
        return False, f"CAL needed at {s['f']:.2f} Hz; co-locate all 3 microphones first"
    if "coh" in s and s["coh"] < 0.95:
        return False, f"Phase unstable: coherence {s['coh']:.3f} < 0.950"
    if s.get("closure", 0) >= 5:
        return False, f"Phase pairs disagree: closure {s['closure']:.1f}°"
    if s.get("r", 0) > 1.05:
        return False, f"Phase exceeds 20 cm geometry: projection {s['r']:.2f}"
    if s.get("valid", 0) < 1:
        return False, "Firmware rejected the angle; inspect SYNC3 and DMA counters"
    return True, "Calibrated FFT phase direction"


def reader(port: str, baud: int, events: queue.Queue, commands: queue.Queue,
           stop: threading.Event):
    try:
        import serial

        stream = serial.Serial(port=None, baudrate=baud, timeout=0.2)
        stream.port = port
        stream.dtr = False
        stream.rts = False
        with stream:
            events.put(("connection", f"Connected to {port} @ {baud}"))
            while not stop.is_set():
                try:
                    command = commands.get_nowait()
                    stream.write((command + "\n").encode("ascii"))
                    events.put(("connection", f"Sent {command} · {port} @ {baud}"))
                except queue.Empty:
                    pass
                raw = stream.readline()
                item = parse_line(raw.decode("ascii", errors="replace").strip())
                if item is not None:
                    events.put(item)
    except Exception as exc:
        events.put(("connection", f"Serial error: {exc}"))


def demo(events: queue.Queue, stop: threading.Event):
    random.seed(3)
    start = time.monotonic()
    phase = 0.0
    last_report = start
    while not stop.is_set():
        now = time.monotonic()
        az = 35 + 24 * math.sin((now - start) / 8)
        el = 28 + 8 * math.sin((now - start) / 6)
        az_rad, el_rad = math.radians(az), math.radians(el)
        ux = math.cos(el_rad) * math.cos(az_rad)
        uy = math.cos(el_rad) * math.sin(az_rad)
        uz = math.sin(el_rad)
        f = 187.5
        d = 0.2
        c = 343.0
        phi21 = 360 * f * d * ux / c
        phi31 = 360 * f * d * (ux / 2 + math.sqrt(3) * uy / 2) / c
        phi32 = phi31 - phi21
        phase += 2 * math.pi * f / 500
        for i, offset in enumerate((0, math.radians(phi21), math.radians(phi31))):
            value = int(32000 * math.sin(phase + offset) + random.gauss(0, 550))
            events.put(("mic", (i, value)))
        if now - last_report >= 0.5:
            events.put(("sync", {
                "f": f, "az": az % 360, "el": el, "ux": ux, "uy": uy, "uz": uz,
                "valid": 1, "r": math.hypot(ux, uy),
                "raw_az": az % 360, "raw_el": el,
                "raw_ux": ux, "raw_uy": uy,
                "raw_uz": uz, "raw_r": math.hypot(ux, uy),
                "phi21": phi21, "phi31": phi31, "phi32": phi32,
                "raw21": phi21, "raw31": phi31, "raw32": phi32,
                "closure": 0, "cal": 1, "state": 2, "coh": 0.99,
                "mag1": 23000, "mag2": 22500, "mag3": 23500,
                "dma0": int((now-start)*500/7.5), "dma1": int((now-start)*500/7.5),
                "ovf0": 0, "ovf1": 0, "lost0": 0, "lost1": 0,
                "backlog0": 0, "backlog1": 0, "fft": 31, "phase_n": 31,
            }))
            last_report = now
        time.sleep(0.002)


class Dashboard:
    def __init__(self, root: tk.Tk, events: queue.Queue, commands: queue.Queue,
                 stop: threading.Event, source: str, is_demo: bool):
        self.root = root
        self.events = events
        self.commands = commands
        self.stop = stop
        self.samples = [deque(maxlen=650) for _ in range(3)]
        self.phase_history = deque(maxlen=120)
        self.sync = {}
        self.updated = 0.0
        self.connection = source
        self.mode = "uncalibrated"
        self.mode_buttons = {}
        root.title("Acoustic array | FFT phase direction")
        root.geometry("1320x830")
        root.minsize(1050, 690)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)

        tk.Label(root, text="ACOUSTIC ARRAY", fg=TEXT, bg=BG,
                 font=("Segoe UI", 21, "bold")).pack(anchor="w", padx=24, pady=(18, 0))
        self.status = tk.Label(root, text=source, fg=MUTED, bg=BG,
                               font=("Segoe UI", 10))
        self.status.pack(anchor="w", padx=25, pady=(0, 16))

        controls = tk.Frame(root, bg=BG)
        controls.pack(fill="x", padx=22, pady=(0, 9))
        for mode in ("uncalibrated", "calibrated"):
            button = tk.Button(controls, text=mode.upper(), width=15,
                               command=lambda value=mode: self.set_mode(value),
                               bg=PANEL, fg=TEXT, activebackground=GRID,
                               activeforeground=TEXT, relief="flat", bd=0,
                               font=("Segoe UI", 10, "bold"), cursor="hand2")
            button.pack(side="left", padx=4)
            self.mode_buttons[mode] = button
        self.set_mode(self.mode)
        for command in ("CLEAR", "CAL", "START"):
            button = tk.Button(controls, text=command, width=9,
                               command=lambda value=command: self.commands.put(value),
                               bg=PANEL, fg=TEXT, activebackground=GRID,
                               activeforeground=TEXT, relief="flat", bd=0,
                               font=("Segoe UI", 10, "bold"), cursor="hand2")
            button.pack(side="right", padx=4)
            if is_demo:
                button.configure(state="disabled")

        top = tk.Frame(root, bg=BG)
        top.pack(fill="both", expand=True, padx=20)
        self.compass = tk.Canvas(top, bg=PANEL, highlightthickness=0, height=365)
        self.compass.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.summary = tk.Canvas(top, bg=PANEL, highlightthickness=0, height=365)
        self.summary.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self.scope = tk.Canvas(root, bg=PANEL, highlightthickness=0, height=210)
        self.scope.pack(fill="x", padx=20, pady=(16, 0))
        self.phases = tk.Canvas(root, bg=PANEL, highlightthickness=0, height=155)
        self.phases.pack(fill="x", padx=20, pady=(12, 18))
        self.root.after(100, self.tick)

    def close(self):
        self.stop.set()
        self.root.destroy()

    def set_mode(self, mode: str):
        self.mode = mode
        self.phase_history.clear()
        for name, button in self.mode_buttons.items():
            selected = name == mode
            button.configure(bg=PROVISIONAL if selected and name == "uncalibrated" else
                             GOOD if selected else PANEL,
                             fg=BG if selected else TEXT)

    def field(self, stem: str) -> str:
        return "raw" + stem if self.mode == "uncalibrated" else "phi" + stem

    def tick(self):
        for _ in range(2500):
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "mic":
                index, value = data
                self.samples[index].append(value)
            elif kind == "sync":
                self.sync = data
                self.updated = time.monotonic()
                fields = tuple(self.field(pair) for pair in ("21", "31", "32"))
                if all(k in data for k in fields):
                    self.phase_history.append(tuple(data[k] for k in fields))
            elif kind == "connection":
                self.connection = data
        self.status.configure(text=self.connection)
        self.draw_compass()
        self.draw_summary()
        self.draw_scope()
        self.draw_phases()
        self.root.after(100, self.tick)

    @staticmethod
    def label(canvas, x, y, text, *, size=11, color=TEXT, anchor="nw", weight="normal"):
        canvas.create_text(x, y, text=text, fill=color, anchor=anchor,
                           font=("Segoe UI", size, weight))

    def draw_compass(self):
        c = self.compass
        c.delete("all")
        w, h = max(c.winfo_width(), 300), max(c.winfo_height(), 300)
        self.label(c, 22, 18, "AZIMUTH · ARRAY PLANE", size=12, color=MUTED, weight="bold")
        cx, cy, radius = w * 0.48, h * 0.55, min(w * 0.31, h * 0.35)
        for fraction in (0.33, 0.66, 1):
            r = radius * fraction
            c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=GRID, width=1)
        c.create_line(cx-radius-16, cy, cx+radius+16, cy, fill=GRID)
        c.create_line(cx, cy-radius-16, cx, cy+radius+16, fill=GRID)
        for a, t in ((0, "+X"), (90, "+Y"), (180, "−X"), (270, "−Y")):
            angle = math.radians(a)
            x = cx + (radius+24)*math.cos(angle)
            y = cy - (radius+24)*math.sin(angle)
            self.label(c, x, y, f"{t}  {a}°", size=9, color=MUTED, anchor="center")
        # Show the actual microphone layout, centered at the compass origin.
        side = radius * 0.9
        positions = ((-side/2, -side/(2*math.sqrt(3))),
                     (side/2, -side/(2*math.sqrt(3))),
                     (0, side/math.sqrt(3)))
        points = [(cx+x, cy-y) for x, y in positions]
        c.create_polygon(*(coordinate for point in points for coordinate in point),
                         fill="#1c2b43", outline="#7183a2", width=2)
        for i, (x, y) in enumerate(points):
            c.create_oval(x-7, y-7, x+7, y+7, fill=COLORS[i], outline="")
            self.label(c, x+11, y-10, f"M{i+1}", size=10, color=COLORS[i])
        fresh = time.monotonic() - self.updated < 3
        drawable, _ = angle_status(self.sync, fresh, self.mode)
        if drawable:
            prefix = "raw_" if self.mode == "uncalibrated" else ""
            color = PROVISIONAL if self.mode == "uncalibrated" else GOOD
            azimuth = self.sync.get(prefix + "az", 0.0)
            elevation = self.sync.get(prefix + "el", 0.0)
            horizontal_r = self.sync.get(prefix + "r", 0.0)
            if horizontal_r >= 0.02:
                angle = math.radians(azimuth)
                x = cx + radius*horizontal_r*math.cos(angle)
                y = cy - radius*horizontal_r*math.sin(angle)
                c.create_line(cx, cy, x, y, fill=color, width=4, arrow="last", arrowshape=(14, 18, 7))
            az_text = f"AZ {azimuth:.1f}°" if horizontal_r >= 0.02 else "AZ undefined"
            self.label(c, w-22, 24,
                       f"{az_text}  EL {elevation:.1f}°",
                       size=18, color=color,
                       anchor="ne", weight="bold")
            if self.mode == "uncalibrated":
                self.label(c, w-22, 58, "PROVISIONAL", size=11, color=color,
                           anchor="ne", weight="bold")
        else:
            title = "NO STABLE ESTIMATE" if self.mode == "uncalibrated" else "NO VALID ANGLE"
            self.label(c, w-22, 26, title, size=17, color=BAD,
                       anchor="ne", weight="bold")

    def draw_summary(self):
        c = self.summary
        c.delete("all")
        w, h = max(c.winfo_width(), 300), max(c.winfo_height(), 300)
        s = self.sync
        self.label(c, 22, 18, "PHASE SOLUTION", size=12, color=MUTED, weight="bold")
        fresh = time.monotonic() - self.updated < 3
        drawable, reason = angle_status(s, fresh, self.mode)
        color = (PROVISIONAL if self.mode == "uncalibrated" else GOOD) if drawable else BAD
        prefix = "raw_" if self.mode == "uncalibrated" else ""
        radius_key = "raw_r" if self.mode == "uncalibrated" else "r"
        state_names = ("WARMUP", "CALIBRATING", "RUNNING")
        state = int(s.get("state", -1))
        state_name = state_names[state] if 0 <= state < 3 else "WAITING"
        azimuth_label = (f"Az {s.get(prefix+'az', 0):.1f}°"
                         if s.get(radius_key, 0.0) >= 0.02 else "Az undefined")
        self.label(c, 24, 52,
                   f"{azimuth_label}   El {s.get(prefix+'el', 0):.1f}°",
                   size=26,
                   color=color if drawable else MUTED, weight="bold")
        self.label(c, 24, 109, "azimuth in XY · elevation above the array plane", size=10, color=MUTED)
        self.label(c, w-24, 60, state_name, size=13, color=color if drawable else BAD,
                   anchor="ne", weight="bold")
        activity = "DETECTED" if fresh and s.get("phase_n", 0) > 0 else "NONE"
        self.label(c, 24, 144,
                   f"80–200 Hz activity {activity}    ·    bin {s.get('f', 0):.2f} Hz"
                   f"    ·    accepted {int(s.get('phase_n', 0))} windows", size=11,
                   color=GOOD if activity == "DETECTED" else MUTED)
        self.label(c, 24, 168,
                   f"Phase coherence {s.get('coh', 0):.3f}    ·    projection {s.get(radius_key, 0):.3f}"
                   f"    ·    closure {s.get('closure', 0):.2f}°",
                   size=10, color=MUTED)
        self.label(c, 24, 190, "CROSS-SPECTRUM FFT PHASE", size=11, color=MUTED, weight="bold")
        for i, pair in enumerate(("21", "31", "32")):
            y = 217 + i*27
            self.label(c, 24, y, f"M{pair[0]} − M{pair[1]}", color=COLORS[i])
            phase_deg = s.get(self.field(pair), 0)
            self.label(c, 120, y, f"{phase_deg:+7.2f}°", color=TEXT)
        ovf = s.get("ovf0", 0) + s.get("ovf1", 0)
        self.label(c, 24, h-68,
                   f"DMA blocks {int(s.get('dma0',0))} / {int(s.get('dma1',0))}"
                   f"    ·    overflow {int(ovf)}", size=10, color=MUTED)
        self.label(c, 24, h-39, reason, size=11, color=color)

    def draw_scope(self):
        c = self.scope
        c.delete("all")
        w, h = max(c.winfo_width(), 300), max(c.winfo_height(), 150)
        self.label(c, 20, 14, "MICROPHONE BUFFERS  ·  latest plotted samples", size=11,
                   color=MUTED, weight="bold")
        left, right, top, bottom = 62, w-22, 44, h-16
        peak = max((abs(x) for channel in self.samples for x in channel), default=1)
        peak = max(peak, 3000)
        for i, samples in enumerate(self.samples):
            baseline = top + (i+0.5)*(bottom-top)/3
            c.create_line(left, baseline, right, baseline, fill=GRID)
            self.label(c, 18, baseline, f"M{i+1}", color=COLORS[i], anchor="w")
            data = list(samples)
            if len(data) < 2:
                continue
            span = (bottom-top)/7
            coords = []
            for j, value in enumerate(data):
                coords.extend((right - (len(data)-1-j)*(right-left)/649,
                               baseline - value/peak*span))
            c.create_line(*coords, fill=COLORS[i], width=1.5)
        self.label(c, right, 17, f"scale ±{peak:,} counts", size=9,
                   color=MUTED, anchor="ne")

    def draw_phases(self):
        c = self.phases
        c.delete("all")
        w, h = max(c.winfo_width(), 300), max(c.winfo_height(), 120)
        phase_kind = "RAW" if self.mode == "uncalibrated" else "CALIBRATED"
        self.label(c, 20, 11, f"{phase_kind} PHASE HISTORY  ·  last 120 reports", size=11,
                   color=MUTED, weight="bold")
        left, right, top, bottom = 62, w-22, 39, h-15
        for deg in (-45, 0, 45):
            y = (top+bottom)/2 - deg*(bottom-top)/110
            c.create_line(left, y, right, y, fill=GRID)
            self.label(c, 14, y, str(deg), size=8, color=MUTED, anchor="w")
        history = list(self.phase_history)
        for i in range(3):
            if len(history) < 2:
                continue
            coords = []
            for j, phases in enumerate(history):
                x = right - (len(history)-1-j)*(right-left)/119
                y = (top+bottom)/2 - max(-55, min(55, phases[i]))*(bottom-top)/110
                coords.extend((x, y))
            c.create_line(*coords, fill=COLORS[i], width=2)
        for i, pair in enumerate(("21", "31", "32")):
            self.label(c, right-160+i*54, 12, f"φ{pair}", size=10, color=COLORS[i])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="ESP32 serial port, e.g. COM7")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument("--demo", action="store_true", help="show synthetic dashboard without hardware")
    args = parser.parse_args()
    if not args.demo and not args.port:
        parser.error("specify --port COM7 or --demo")
    events = queue.Queue(maxsize=10000)
    commands = queue.Queue()
    stop = threading.Event()
    target = demo if args.demo else reader
    arguments = (events, stop) if args.demo else (args.port, args.baud, events, commands, stop)
    threading.Thread(target=target, args=arguments, daemon=True).start()
    root = tk.Tk()
    Dashboard(root, events, commands, stop,
              "Demo data" if args.demo else f"Opening {args.port}…", args.demo)
    root.mainloop()


if __name__ == "__main__":
    main()
