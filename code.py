import time, random, usb_hid, usb_cdc
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode

keyboard = Keyboard(usb_hid.devices)
layout = KeyboardLayoutUS(keyboard)
serial = usb_cdc.data

# --- Behavior tuning ---
MIN_WPM, MAX_WPM = 10, 50
WORD_PAUSE_RANGE = (0.5, 1.2)     # pause after each word
PAUSE_EVERY_N_LINES = 4
PAUSE_DURATION = 5                # 5s break after every 4 lines
TYPO_PROBABILITY = 0.015          # 1.5% chance of typo per character

def delay_for_char(ch):
    """Human entropy: random realistic delay per character."""
    wpm = random.uniform(MIN_WPM, MAX_WPM)
    cps = (wpm * 5) / 60
    base = 1 / cps
    if ch in ".!?":
        return base * random.uniform(2.0, 2.8)
    if ch in ",;:":
        return base * random.uniform(1.5, 2.0)
    if ch in "()[]{}\"'":
        return base * random.uniform(1.2, 1.7)
    if ch == " ":
        return base * random.uniform(1.0, 1.4)
    return base * random.uniform(0.7, 1.1)

def read_serial_lines():
    """Fetch full text from USB serial as list of lines."""
    data = b""
    while serial.in_waiting:
        data += serial.read(serial.in_waiting)
        time.sleep(0.05)
    return data.decode("utf-8", "ignore").splitlines() if data else []

def type_code(lines):
    """Type text without indentation but with realistic entropy."""
    line_count = 0
    for line in lines:
        # Strip indentation completely
        clean_line = line.lstrip()

        word_buffer = ""
        for ch in clean_line:
            # Random typo simulation
            if random.random() < TYPO_PROBABILITY and ch.isalpha():
                wrong_char = random.choice("abcdefghijklmnopqrstuvwxyz")
                layout.write(wrong_char)
                time.sleep(random.uniform(0.05, 0.25))
                keyboard.send(Keycode.BACKSPACE)
                time.sleep(random.uniform(0.05, 0.25))

            # Type actual character
            layout.write(ch)
            word_buffer += ch
            time.sleep(delay_for_char(ch))

            # Pause after words
            if ch in [" ", "\t"]:
                if word_buffer.strip():
                    time.sleep(random.uniform(*WORD_PAUSE_RANGE))
                word_buffer = ""

        # End of line — add small space, then ENTER
        layout.write(" ")
        keyboard.send(Keycode.ENTER)
        line_count += 1

        # Short pause per line
        time.sleep(random.uniform(0.4, 1.0))

        # Long pause every few lines
        if line_count % PAUSE_EVERY_N_LINES == 0:
            time.sleep(PAUSE_DURATION)

    keyboard.send(Keycode.ENTER)

print("Plain-text human entropy typer ready.")
time.sleep(2)

while True:
    lines = read_serial_lines()
    if lines:
        type_code(lines)
    time.sleep(0.1)
