#Start-Process -FilePath "C:\Users\zainm\AppData\Local\Programs\Python\Python310\pythonw.exe" -ArgumentList "C:\pico_watcher\pico_watcher_bg.pyw" -Verb RunAs


"""
Pico Key Watcher + AI + Pico sender
- Start capture command:  sttcapzn
- Stop capture command:   stpcapzn
- Log file:               C:\pico_watcher\capture_log.txt
Requires: pip install keyboard openai pyserial
Run as Administrator for global keyboard hooks.
"""

import os
import time
import datetime
import io
import traceback
import keyboard
import serial
import serial.tools.list_ports
from openai import OpenAI

# === CONFIGURATION ===
START_CMD = "sttcapzn"
STOP_CMD = "stpcapzn"
LOG_DIR = r"C:\pico_watcher"
LOG_PATH = os.path.join(LOG_DIR, "capture_log.txt")
MAX_RECENT = max(len(START_CMD), len(STOP_CMD)) + 12
FORCE_PORT = "COM7"                # change if your Pico uses different COM
SERIAL_BAUD = 115200
CHUNK_SIZE = 100
CHUNK_DELAY = 0.15                 # seconds between serial chunk writes
API_MODEL = "o3-mini"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

os.makedirs(LOG_DIR, exist_ok=True)

# === SIMPLE LOGGER ===
def write_raw_log(msg):
    """Append a single timestamped line to the log."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")

def save_capture(text):
    """Save captured session to log file and return path info."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry_header = f"\n=== Capture @ {ts} ({len(text)} chars) ===\n"
    entry_footer = "\n" + ("="*60) + "\n"
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry_header)
        f.write(text + "\n")
        f.write(entry_footer)
    write_raw_log(f"Saved capture ({len(text)} chars).")
    return True

# === OPENAI CLIENT ===
def get_openai_client():
    if not OPENAI_API_KEY:
        write_raw_log("[ERROR] OPENAI_API_KEY not set in environment variables.")
        return None
    try:
        return OpenAI(api_key=OPENAI_API_KEY)
    except Exception as e:
        write_raw_log(f"[ERROR] Failed to create OpenAI client: {e}")
        return None

# Prepare system prompt (your CodeTantra assistant)
SYSTEM_PROMPT = (
    "You are a CodeTantra exam assistant that solves programming and debugging questions.\n"
    "The input may contain messy or raw extracted text, instructions, metadata, or multiple question sections.\n"
    "The pattern of questions typically follows:\n\n"
    "Easy Questions: Two Question for 5+5=10 marks (Only Programming Question (any language))\n"
    "Medium Questions: Two Question for 7.5+7.5=15 marks (Debugging Question (C only) + Programming Question (any language))\n"
    "Difficult Question: One Question for 10 marks (Programming Question (any language))\n\n"
    "From this text, your job is to:\n"
    "1. Identify the actual question or task to solve.\n"
    "2. Detect if it's a debugging or programming question.\n"
    "3. Detect the language (C, Python, Java, etc.) if mentioned, otherwise choose Python.\n"
    "4. Produce only the clean, correct source code for the detected question.\n"
    "5. Do NOT include explanations, markdown formatting, or extra commentary.\n"
    "6. Output only pure code that can be run as-is."
)

def call_openai(prompt_text):
    client = get_openai_client()
    if client is None:
        return ""
    try:
        write_raw_log("[INFO] Sending captured text to OpenAI...")
        resp = client.chat.completions.create(
            model=API_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ],
        )
        result = resp.choices[0].message.content.strip()
        write_raw_log(f"[DEBUG] --- AI OUTPUT START ({len(result)} chars) ---")
        # write AI result in the log as a block
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(result + "\n")
            f.write("[DEBUG] --- AI OUTPUT END ---\n")
        write_raw_log("[INFO] OpenAI response saved to log.")
        return result
    except Exception as e:
        write_raw_log(f"[ERROR] OpenAI call failed: {e}")
        write_raw_log(traceback.format_exc())
        return ""

# === SERIAL SENDER ===
def send_to_pico(text):
    """Send AI output to Pico via serial in chunks, logging progress."""
    try:
        payload = (text.replace("\r", "") + "\n").encode("utf-8")
        total_len = len(payload)
        write_raw_log(f"[INFO] Sending {total_len} bytes to Pico on {FORCE_PORT} ...")
        # give device time to be ready
        time.sleep(2)
        with serial.Serial(FORCE_PORT, SERIAL_BAUD, timeout=1) as s:
            s.reset_input_buffer()
            sent = 0
            buf = io.BytesIO(payload)
            while True:
                chunk = buf.read(CHUNK_SIZE)
                if not chunk:
                    break
                s.write(chunk)
                s.flush()
                sent += len(chunk)
                write_raw_log(f"[DEBUG] -> Sent {sent}/{total_len} bytes")
                time.sleep(CHUNK_DELAY)
        write_raw_log(f"[SUCCESS] Sent all {total_len} bytes to Pico.")
        return True
    except Exception as e:
        write_raw_log(f"[ERROR] Failed to send to Pico: {e}")
        write_raw_log(traceback.format_exc())
        return False

# === KEY CAPTURE (same logic as before) ===
capturing = False
capture_buffer = []
recent = []

def recent_flat_processed(rlist):
    s = []
    for x in rlist:
        if x == "\b":
            if s:
                s.pop()
        else:
            s.append(x)
    return "".join(s)

def finalize_and_process_capture():
    """Called when STOP command detected: log, call AI, send to Pico."""
    global capture_buffer
    captured_text = "".join(capture_buffer).strip()
    if not captured_text:
        write_raw_log("[WARN] Captured text was empty; skipping AI/send.")
        return

    # 1) Save raw capture to log file
    save_capture(captured_text)

    # 2) Call OpenAI
    ai_output = call_openai(captured_text)
    if not ai_output:
        write_raw_log("[ERROR] AI returned empty output; skipping send.")
        return

    # 3) Send AI output to Pico
    ok = send_to_pico(ai_output)
    if not ok:
        write_raw_log("[ERROR] Sending to Pico failed.")
    else:
        write_raw_log("[INFO] Full pipeline completed for this capture session.")

def on_key_event(event):
    global capturing, capture_buffer, recent
    if event.event_type != "down":
        return

    name = event.name
    ch = None

    if len(name) == 1:
        ch = name
    elif name == "space":
        ch = " "
    elif name == "enter":
        ch = "\n"
    elif name == "tab":
        ch = "\t"
    elif name == "backspace":
        ch = "<BACKSPACE>"
    else:
        ch = None

    if ch is not None:
        if ch == "<BACKSPACE>":
            recent.append("\b")
        else:
            recent.append(ch)
    if len(recent) > MAX_RECENT:
        del recent[: len(recent) - MAX_RECENT]

    recent_flat = recent_flat_processed(recent).lower()

    # START trigger
    if not capturing and recent_flat.endswith(START_CMD):
        capturing = True
        capture_buffer = []
        recent.clear()
        write_raw_log("START detected — capturing begins.")
        return

    if capturing:
        if ch == "<BACKSPACE>":
            if capture_buffer:
                capture_buffer.pop()
        elif ch is not None:
            capture_buffer.append(ch)

        # STOP trigger detection
        cap_flat = "".join(capture_buffer).lower()
        if cap_flat.endswith(STOP_CMD):
            # remove stop cmd tail from buffer
            for _ in range(len(STOP_CMD)):
                if capture_buffer:
                    capture_buffer.pop()
            capturing = False
            write_raw_log("STOP detected — finalizing capture.")
            # process: log, AI, send to pico
            try:
                finalize_and_process_capture()
            except Exception as e:
                write_raw_log(f"[ERROR] finalize pipeline error: {e}")
                write_raw_log(traceback.format_exc())
            capture_buffer = []
            recent.clear()

# === MAIN ===
def main():
    write_raw_log("Pico Key Watcher (with AI + Pico send) started.")
    print("Pico Key Watcher running in background.")
    print(f"Type '{START_CMD}' to start and '{STOP_CMD}' to stop.\n")
    print(f"Logs: {LOG_PATH}\n")

    keyboard.hook(on_key_event)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        write_raw_log("KeyboardInterrupt — exiting.")
    finally:
        keyboard.unhook_all()
        write_raw_log("Watcher stopped.")

if __name__ == "__main__":
    main()
