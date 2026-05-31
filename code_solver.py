#!/usr/bin/env python3
"""
Code Solver — captures screen, reads coding question, copies solution to clipboard
----------------------------------------------------------------------------------
Controls:
  ↑  = capture screen & solve coding question
  ↓  = hide overlay
  ESC = quit
"""

import os, sys, base64, threading, subprocess
from io import BytesIO
from PIL import ImageGrab, Image
from pynput import keyboard
from groq import Groq
import tkinter as tk

API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL   = "meta-llama/llama-4-scout-17b-16e-instruct"
client  = Groq(api_key=API_KEY) if API_KEY else None

def copy_to_clipboard(text):
    r = tk.Tk()
    r.withdraw()
    r.clipboard_clear()
    r.clipboard_append(text)
    r.update()
    r.after(3000, r.destroy)  # keep alive 3s so clipboard doesn't clear
    r.mainloop()

def speak(text):
    text = text.replace('"', '').replace("'", "")
    subprocess.Popen(
        ["powershell", "-Command",
         f'Add-Type -AssemblyName System.Speech; '
         f'$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
         f'$s.Rate = 2; $s.Speak("{text}")'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def screenshot_to_b64():
    img = ImageGrab.grab()
    img = img.resize((1280, 720), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()

def ask_groq(b64):
    if not client:
        return "NO KEY"
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role":"user","content":[
            {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}},
            {"type":"text","text":(
                "Look at this screenshot. Find the coding question/problem visible on screen.\n"
                "Write a complete, working solution in the most appropriate language.\n"
                "Reply with ONLY the raw code, no explanation, no markdown, no backticks.\n"
                "If no coding question found, reply: NONE"
            )}
        ]}],
        max_tokens=1024,
    )
    return r.choices[0].message.content.strip()

# ── Overlay ───────────────────────────────────────────────────────────────────
class Overlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.configure(bg="#0d0d0d")

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.W = 380
        self.root.geometry(f"{self.W}x32+{sw-400}+{sh-60}")

        self.var = tk.StringVar(value="")
        tk.Label(
            self.root, textvariable=self.var,
            font=("Segoe UI", 11, "bold"),
            fg="#1E90FF", bg="#0d0d0d",
            padx=8, pady=4
        ).pack()
        self.root.withdraw()

    def show(self, text):
        self.var.set(text)
        self.root.deiconify()

    def hide(self):
        self.root.withdraw()

    def run(self):
        self.root.mainloop()

overlay = None

def on_capture():
    overlay.root.after(0, lambda: overlay.show("⏳ Solving..."))
    speak("solving")
    try:
        b64  = screenshot_to_b64()
        code = ask_groq(b64)

        if code == "NONE":
            overlay.root.after(0, lambda: overlay.show("No coding question found"))
            speak("no question found")
            return

        # copy to clipboard
        threading.Thread(target=copy_to_clipboard, args=(code,), daemon=True).start()

        lines = code.count("\n") + 1
        overlay.root.after(0, lambda: overlay.show(f"✓ Copied! ({lines} lines) — Ctrl+V to paste"))
        speak("done, paste now")
        print(f"\n[CODE]\n{code}\n")

    except Exception as e:
        print(f"[ERR] {e}")
        overlay.root.after(0, lambda: overlay.show("Error"))
        speak("error")

def on_press(key):
    try:
        if key == keyboard.Key.up:
            threading.Thread(target=on_capture, daemon=True).start()
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
    print("Code Solver running")
    print("  ↑  = capture & solve")
    print("  ↓  = hide")
    print("  ESC = quit")
    speak("ready")
    overlay = Overlay()
    l = keyboard.Listener(on_press=on_press)
    l.daemon = True
    l.start()
    overlay.run()
    l.stop()