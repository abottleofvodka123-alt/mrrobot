#!/usr/bin/env python3
import os, sys, base64, threading, time, re
from io import BytesIO
from PIL import ImageGrab, Image
from pynput import keyboard, mouse
import tkinter as tk
from groq import Groq  # pip install groq

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY    = os.environ.get("GROQ_API_KEY", "")
# Free models on OpenRouter — ranked by coding ability:
#   deepseek/deepseek-chat-v3-0324:free   ← best for code (recommended)
#   meta-llama/llama-3.3-70b-instruct:free
#   qwen/qwen3-235b-a22b:free
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # vision + text
TEXT_MODEL   = "llama-3.3-70b-versatile"  # fast text
mouse_ctrl = mouse.Controller()

client = None
if API_KEY:
    client = Groq(api_key=API_KEY)


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
                    prev_frame.resize((32, 32)).tobytes(),
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

    w       = frames[0].width
    crop_h  = int(frames[0].height * 0.75)
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
    target_w = 1600
    new_h = int(img.height * target_w / img.width)
    img = img.resize((target_w, new_h), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return base64.b64encode(buf.getvalue()).decode()


EXTRACT_PROMPT = """\
You are reading a screenshot of a coding assignment or problem.

Step 1 — Extract everything visible:
- The exact problem statement
- All requirements and constraints
- Any sample input/output
- The programming language and framework/libraries mentioned or implied
- Any starter code shown

Step 2 — Output a structured summary in this format:
LANGUAGE: <language>
FRAMEWORK: <framework or "none">
LIBRARIES: <comma-separated list or "none">
PROBLEM:
<full problem statement, word for word>
REQUIREMENTS:
<bullet list of every requirement>
SAMPLE_IO:
<sample input/output if shown, else "none">
STARTER_CODE:
<starter code if shown, else "none">

If there is no coding question in the screenshot, output exactly: NONE
"""

SOLVE_PROMPT = """
You are a senior software engineer with 15+ years of experience producing production-quality, well-architected code.

{extracted}

Your task is to produce a COMPLETE, CORRECT, and MAXIMALLY DETAILED solution — as if you are submitting it for professional code review.

Follow these steps:
1. Carefully read every single requirement before writing any code.
2. At the very top of your response, write a brief PLAN comment block:
   - The technology stack
   - The full folder/file structure you will produce
   - Key design decisions

3. Then write ALL files in full. For each file:
   - Start with the full file path as a comment header (e.g. // src/App.tsx)
   - Write complete, runnable code — zero TODOs, zero stubs, zero placeholders
   - Preserve all existing function signatures and starter code exactly
   - Add clear inline comments explaining WHY decisions were made, not just what the code does
   - Handle edge cases and errors properly

4. At the very end, write an EXPLANATION block:
   - What the solution does overall
   - How each major piece works
   - How to install dependencies and run it
   - Any important caveats or assumptions

Quality rules:
- Follow best practices and idioms for the given language/framework
- Write clean, readable, well-named variables and functions
- Make it correct first, then clean — never sacrifice correctness
"""

CLASSIFY_PROMPT = """\
Classify this assignment.

Return exactly one word, nothing else:

REACT
JAVA
PYTHON
CPP
DSA
DATABASE
BACKEND
MACHINE_LEARNING
OTHER

Assignment:

{extracted}
"""

TASK_RULES = {
    "REACT": """
- Use modern React.
- Use TypeScript if specified.
- Follow requested folder structure.
""",
    "DSA": """
- Preserve function signature.
- Use optimal algorithm.
- Include time and space complexity as a comment.
""",
    "JAVA": """
- Produce compilable Java code.
- Include all imports.
""",
    "PYTHON": """
- Produce runnable Python code.
- Include all imports.
""",
    "CPP": """
- Produce compilable C++ code.
- Include all headers.
""",
    "DATABASE": """
- Write valid SQL.
- Include CREATE TABLE statements if schema is not provided.
""",
    "BACKEND": """
- Include all routes and handlers.
- Include any required middleware.
""",
}

VERIFY_PROMPT = """
You are a meticulous senior code reviewer. Your job is to catch every possible mistake before the code ships.

Original Requirements:
{extracted}

Generated Solution:
{solution}

Go through the requirements ONE BY ONE and verify each is fully implemented.
Then check for:
- Missing files, imports, headers, or dependencies
- Syntax errors or typos anywhere
- Logic bugs or off-by-one errors
- Unhandled edge cases or missing error handling
- Anything that would prevent the code from running correctly end-to-end

Return the FULLY CORRECTED, COMPLETE solution with all issues fixed.
- Do NOT truncate or summarize — output every file in full
- Keep all helpful comments
- Add comments where logic was fixed so it is clear what changed
"""


def _chat(system: str, user: str) -> str:
    """Single-turn text-only call."""
    resp = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return resp.choices[0].message.content.strip()


def _vision(prompt: str, b64: str) -> str:
    """Single-turn vision call (image + text)."""
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}"
                        },
                    },
                ],
            }
        ],
    )
    return resp.choices[0].message.content.strip()


def classify_problem(extracted: str) -> str:
    resp = _chat(
        system="You classify coding assignments. Reply with exactly one word.",
        user=CLASSIFY_PROMPT.format(extracted=extracted),
    )
    return resp.split()[0].upper()


def inject_watermark(code: str) -> str:
    lines  = code.split('\n')
    result = []
    for i, line in enumerate(lines):
        result.append(line)
        stripped = line.strip()
        is_component = bool(
            re.search(
                r'(?:export\s+)?const\s+[A-Z]\w*.*=>|function\s+[A-Z]\w*',
                stripped
            )
        )
        if is_component:
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
            if next_line != '// aryaman 1116':
                result.append('// aryaman 1116')
    return '\n'.join(result)


def ask_ai(b64: str) -> str:
    if not client:
        return "NO KEY"

    # ── Stage 1: extract problem from screenshot ──────────────────────────────
    extracted = _vision(EXTRACT_PROMPT, b64)

    if extracted == "NONE":
        return "NONE"

    print(f"\n[EXTRACTED]\n{extracted}\n")

    # ── Stage 2: classify ─────────────────────────────────────────────────────
    task_type   = classify_problem(extracted)
    extra_rules = TASK_RULES.get(task_type, "")
    print(f"[TASK TYPE] {task_type}\n")

    # ── Stage 3: solve ────────────────────────────────────────────────────────
    final_prompt = f"""
{SOLVE_PROMPT.format(extracted=extracted)}

Additional rules:

{extra_rules}
""".strip()

    code = _chat(system="You are an expert software engineer. Output code only.", user=final_prompt)

    # ── Stage 4: self-check / verify ──────────────────────────────────────────
    code = _chat(
        system="You are a strict code reviewer. Output corrected code only, no explanations.",
        user=VERIFY_PROMPT.format(extracted=extracted, solution=code),
    )

    # ── Stage 5: hard-inject watermark ────────────────────────────────────────
    code = inject_watermark(code)

    return code


# ── Overlay UI ────────────────────────────────────────────────────────────────

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
            self.root,
            textvariable=self.var,
            font=("Consolas", 11),
            fg="#d4d4d4",
            bg="#000001",
            padx=6,
            pady=2,
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


def on_capture():
    overlay.root.after(0, lambda: overlay.show("↻  Scrolling..."))
    try:
        img  = scroll_and_capture()
        overlay.root.after(0, lambda: overlay.show("🔍  Reading question..."))
        b64  = img_to_b64(img)
        code = ask_ai(b64)
        if code == "NONE":
            overlay.root.after(0, lambda: overlay.show("✗  No question found"))
            return
        overlay.root.after(0, lambda: overlay.show("⚙  Solving..."))
        threading.Thread(target=copy_to_clipboard, args=(code,), daemon=True).start()
        lines = code.count("\n") + 1
        overlay.root.after(0, lambda: overlay.show(f"✓  Copied  {lines} lines — Ctrl+V"))
        print(f"\n[CODE]\n{code}\n")
    except Exception as e:
        msg = str(e)[:50]
        print(f"[ERR] {e}")
        overlay.root.after(0, lambda m=msg: overlay.show(f"✗  {m}"))


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
    print("Code Solver — ↑ capture  ↓ hide  ESC quit")
    overlay = Overlay()
    l = keyboard.Listener(on_press=on_press)
    l.daemon = True
    l.start()
    overlay.run()
    l.stop()