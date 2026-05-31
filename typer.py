#!/usr/bin/env python3
"""
Typer — types clipboard content into active window at human speed
----------------------------------------------------------------
Controls:
  → (right arrow) = start typing clipboard content
  ESC = quit

Usage:
  1. Run code_solver first to get code into clipboard
  2. Click into VSCode editor
  3. Hit → to start typing
"""

import sys, time, random, threading
import tkinter as tk
from pynput import keyboard
from pynput.keyboard import Controller, Key

kb = Controller()

# ── Typing config ─────────────────────────────────────────────────────────────
BASE_DELAY    = 0.03   # base seconds per character
VARIANCE      = 0.02   # random variance per char
LINE_PAUSE    = 0.12   # extra pause at end of line
THINK_PAUSE   = 0.4    # occasional "thinking" pause
THINK_CHANCE  = 0.03   # 3% chance of thinking pause per char
BURST_CHANCE  = 0.15   # 15% chance of typing faster (burst mode)
BURST_SPEED   = 0.008  # burst mode speed
# ─────────────────────────────────────────────────────────────────────────────

is_typing   = False
stop_typing = False

def get_clipboard():
    r = tk.Tk()
    r.withdraw()
    try:
        text = r.clipboard_get()
    except:
        text = ""
    r.destroy()
    return text

def type_text(text):
    global is_typing, stop_typing
    is_typing   = True
    stop_typing = False

    burst = False
    burst_count = 0

    for i, char in enumerate(text):
        if stop_typing:
            break

        # type the character
        try:
            kb.type(char)
        except Exception:
            # fallback for special chars
            kb.press(char)
            kb.release(char)

        # calculate delay
        if burst:
            delay = BURST_SPEED + random.uniform(0, 0.005)
            burst_count -= 1
            if burst_count <= 0:
                burst = False
        else:
            delay = BASE_DELAY + random.uniform(-VARIANCE, VARIANCE)
            delay = max(0.005, delay)

            # thinking pause
            if random.random() < THINK_CHANCE:
                delay += random.uniform(0.2, THINK_PAUSE)

            # enter burst mode
            if random.random() < BURST_CHANCE:
                burst = True
                burst_count = random.randint(5, 20)

        # extra pause at newline
        if char == "\n":
            delay += LINE_PAUSE + random.uniform(0, 0.1)

        time.sleep(delay)

    is_typing = False

# ── Overlay ───────────────────────────────────────────────────────────────────
class Overlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.0)
        self.root.configure(bg="#000001")
        self.root.wm_attributes("-transparentcolor", "#000001")

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"460x26+{sw-480}+{sh-52}")

        self.var = tk.StringVar(value="")
        tk.Label(
            self.root, textvariable=self.var,
            font=("Consolas", 11),
            fg="#d4d4d4",
            bg="#000001",
            padx=6, pady=2
        ).pack()
        self.root.withdraw()

    def show(self, text):
        self.var.set(text)
        self.root.attributes("-alpha", 0.90)
        self.root.deiconify()

    def hide(self):
        self.root.withdraw()
        self.root.attributes("-alpha", 0.0)

    def run(self):
        self.root.mainloop()

overlay = None

def start_typing():
    global stop_typing
    text = get_clipboard()
    if not text:
        overlay.root.after(0, lambda: overlay.show("✗  Clipboard empty"))
        return

    lines = text.count("\n") + 1
    overlay.root.after(0, lambda: overlay.show(f"⌨  Typing {lines} lines...  (↓ to stop)"))

    # small delay so user can click into editor
    time.sleep(1.5)

    type_text(text)

    if not stop_typing:
        overlay.root.after(0, lambda: overlay.show("✓  Done"))
    else:
        overlay.root.after(0, lambda: overlay.show("✗  Stopped"))

def on_press(key):
    global stop_typing
    try:
        if key == keyboard.Key.right:
            if not is_typing:
                threading.Thread(target=start_typing, daemon=True).start()
        elif key == keyboard.Key.down:
            if is_typing:
                stop_typing = True
            else:
                overlay.root.after(0, overlay.hide)
        elif key == keyboard.Key.esc:
            overlay.root.after(0, overlay.root.quit)
            return False
    except:
        pass

if __name__ == "__main__":
    print("Typer running")
    print("  →  = type clipboard into active window")
    print("  ↓  = stop typing / hide")
    print("  ESC = quit")
    overlay = Overlay()
    overlay.root.after(100, lambda: overlay.show("⌨  Ready — copy code then hit →"))
    l = keyboard.Listener(on_press=on_press)
    l.daemon = True
    l.start()
    overlay.run()
    l.stop()