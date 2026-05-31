#!/usr/bin/env python3
import os, sys, base64, threading, time
from io import BytesIO
from PIL import ImageGrab, Image
from pynput import keyboard, mouse
from groq import Groq
import tkinter as tk
from tkinter import font as tkfont

API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL   = "meta-llama/llama-4-scout-17b-16e-instruct"
client  = Groq(api_key=API_KEY) if API_KEY else None
mouse_ctrl = mouse.Controller()

# ── Shared custom instruction ─────────────────────────────────────────────────
custom_instruction = {"text": ""}

def copy_to_clipboard(text):
    r = tk.Tk()
    r.withdraw()
    r.clipboard_clear()
    r.clipboard_append(text)
    r.update()
    r.after(5000, r.destroy)
    r.mainloop()

def screenshot():
    return ImageGrab.grab()

def scroll_and_capture():
    frames = []
    mouse_ctrl.scroll(0, 50)
    time.sleep(0.5)
    prev_frame = None
    for _ in range(8):
        img = screenshot()
        if prev_frame is not None:
            diff = sum(
                abs(a - b)
                for a, b in zip(
                    img.resize((32, 32)).tobytes(),
                    prev_frame.resize((32, 32)).tobytes()
                )
            )
            if diff < 1000:
                break
        frames.append(img)
        prev_frame = img
        mouse_ctrl.scroll(0, -5)
        time.sleep(0.4)

    if not frames:
        return screenshot()

    w      = frames[0].width
    crop_h = int(frames[0].height * 0.75)
    total_h = crop_h * len(frames) + (frames[0].height - crop_h)
    stitched = Image.new("RGB", (w, total_h))
    y = 0
    for i, frame in enumerate(frames):
        if i < len(frames) - 1:
            region = frame.crop((0, 0, w, crop_h))
            stitched.paste(region, (0, y))
            y += crop_h
        else:
            stitched.paste(frame, (0, y))

    max_h = 2000
    if stitched.height > max_h:
        ratio = max_h / stitched.height
        stitched = stitched.resize((int(w * ratio), max_h), Image.LANCZOS)
    return stitched

def img_to_b64(img):
    img = img.resize((1280, int(img.height * 1280 / img.width)), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()

def ask_groq(b64):
    if not client:
        return "NO KEY"
    extra = f"\n\nAdditional instruction: {custom_instruction['text']}" if custom_instruction['text'].strip() else ""
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role":"user","content":[
            {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}},
            {"type":"text","text":(
                "Look at this screenshot. It contains a coding assignment or problem.\n\n"
                "Your job is to produce a COMPLETE, DETAILED, PRODUCTION-READY solution.\n\n"
                "Rules:\n"
                "- Output ALL files needed to run the project\n"
                "- For each file, start with: // ===== filename.js =====\n"
                "- Write FULL code for every file, no placeholders, no '...' shortcuts\n"
                "- Include folder structure as comments at the top\n"
                "- Make UI look decent with inline styles or tailwind\n"
                "- All logic fully implemented as described\n"
                "- No explanations outside the code\n"
                + extra +
                "\n\nIf no coding question found, reply: NONE"
            )}
        ]}],
        max_tokens=8000,
    )
    return r.choices[0].message.content.strip()


# ── Input popup — VSCode style ────────────────────────────────────────────────
class InputPopup:
    def __init__(self, on_submit):
        self.on_submit = on_submit
        self.win = None

    def open(self):
        if self.win and self.win.winfo_exists():
            self.win.lift()
            return

        self.win = tk.Toplevel()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.88)
        self.win.configure(bg="#1e1e1e")

        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        W, H = 480, 80
        x = (sw - W) // 2
        y = sh // 3
        self.win.geometry(f"{W}x{H}+{x}+{y}")

        # top bar — mimics VSCode command palette
        top = tk.Frame(self.win, bg="#2d2d2d", height=24)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(
            top, text="⚡ Code Solver — Custom Instruction",
            font=("Consolas", 9), fg="#9d9d9d", bg="#2d2d2d",
            padx=8
        ).pack(side="left", pady=3)

        tk.Label(
            top, text="↵ confirm   Esc cancel",
            font=("Consolas", 8), fg="#555", bg="#2d2d2d",
            padx=8
        ).pack(side="right", pady=3)

        # input area
        input_frame = tk.Frame(self.win, bg="#1e1e1e", padx=10, pady=8)
        input_frame.pack(fill="both", expand=True)

        # blinking cursor label
        tk.Label(
            input_frame, text=">",
            font=("Consolas", 12), fg="#569cd6", bg="#1e1e1e"
        ).pack(side="left", padx=(0, 6))

        self.entry = tk.Entry(
            input_frame,
            font=("Consolas", 12),
            fg="#d4d4d4",
            bg="#1e1e1e",
            insertbackground="#d4d4d4",
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.insert(0, custom_instruction["text"])
        self.entry.focus_set()
        self.entry.select_range(0, tk.END)

        self.entry.bind("<Return>", self._submit)
        self.entry.bind("<Escape>", self._cancel)

        # bottom border like VSCode
        tk.Frame(self.win, bg="#007acc", height=2).pack(fill="x", side="bottom")

    def _submit(self, e=None):
        custom_instruction["text"] = self.entry.get()
        self.win.destroy()
        self.on_submit()

    def _cancel(self, e=None):
        self.win.destroy()


# ── Status overlay ────────────────────────────────────────────────────────────
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

        self.input_popup = InputPopup(on_submit=self._after_input)

    def _after_input(self):
        threading.Thread(target=on_capture, daemon=True).start()

    def show(self, text):
        self.var.set(text)
        self.root.attributes("-alpha", 0.90)
        self.root.deiconify()

    def hide(self):
        self.root.withdraw()
        self.root.attributes("-alpha", 0.0)

    def open_input(self):
        self.root.after(0, self.input_popup.open)

    def run(self):
        self.root.mainloop()

overlay = None

def on_capture():
    overlay.root.after(0, lambda: overlay.show("↻  Scrolling..."))
    try:
        img  = scroll_and_capture()
        overlay.root.after(0, lambda: overlay.show("⚙  Solving..."))
        b64  = img_to_b64(img)
        code = ask_groq(b64)
        if code == "NONE":
            overlay.root.after(0, lambda: overlay.show("✗  No question found"))
            return
        threading.Thread(target=copy_to_clipboard, args=(code,), daemon=True).start()
        lines = code.count("\n") + 1
        overlay.root.after(0, lambda: overlay.show(f"✓  Copied  {lines} lines — Ctrl+V"))
        print(f"\n[CODE]\n{code}\n")
    except Exception as e:
        print(f"[ERR] {e}")
        overlay.root.after(0, lambda: overlay.show(f"✗  {str(e)[:50]}"))

def on_press(key):
    try:
        if key == keyboard.Key.up:
            # open input popup first, capture runs after submit
            overlay.open_input()
        elif key == keyboard.Key.down:
            overlay.root.after(0, overlay.hide)
        elif key == keyboard.Key.esc:
            overlay.root.after(0, overlay.root.quit)
            return False
    except:
        pass

if __name__ == "__main__":
    if not API_KEY:
        print("[!] GROQ_API_KEY not set.")
        sys.exit(1)
    print("Code Solver — ↑ open prompt  ↓ hide  ESC quit")
    overlay = Overlay()
    l = keyboard.Listener(on_press=on_press)
    l.daemon = True
    l.start()
    overlay.run()
    l.stop()