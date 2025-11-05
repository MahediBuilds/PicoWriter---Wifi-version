import time
import random
import usb_hid
import wifi
import socketpool
import gc
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from secrets import secrets

keyboard = Keyboard(usb_hid.devices)
layout = KeyboardLayoutUS(keyboard)

def safe_close(conn):
    try:
        conn.close()
    except Exception:
        pass

def type_text(text):
    for c in text:
        if c == "\n":
            keyboard.send(Keycode.ENTER)
        else:
            try:
                layout.write(c)
            except Exception:
                pass
        time.sleep(random.uniform(0.04, 0.10))
    keyboard.send(Keycode.ENTER)

def url_decode(s):
    out = ""
    i = 0
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s):
            try:
                out += chr(int(s[i+1:i+3], 16))
                i += 3
                continue
            except Exception:
                pass
        elif s[i] == "+":
            out += " "
        else:
            out += s[i]
        i += 1
    return out

# === Wi-Fi connection ===
print("Connecting to Wi-Fi…")
wifi.radio.enabled = True
for attempt in range(5):
    try:
        wifi.radio.connect(secrets["ssid"], secrets["password"])
        ip = wifi.radio.ipv4_address
        print(f"Connected! IP: {ip}")
        break
    except Exception as e:
        print(f"Attempt {attempt + 1} failed: {e}")
        time.sleep(2)
else:
    print("Failed to connect after 5 attempts.")
    while True:
        pass

# === HTTP server setup ===
pool = socketpool.SocketPool(wifi.radio)
server = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
server.settimeout(None)
server.bind(("0.0.0.0", 80))
server.listen(2)
print(f"Listening on http://{wifi.radio.ipv4_address}")

# === Activity watchdog ===
last_request = time.monotonic()

# === Main loop ===
while True:
    try:
        conn, addr = server.accept()
        conn.settimeout(5)

        data = bytearray(2048)
        n = conn.recv_into(data)
        if n == 0:
            safe_close(conn)
            continue

        request = data[:n].decode("utf-8", "ignore")

        if "GET /type?" in request:
            try:
                text = request.split("text=")[1].split(" ")[0]
                text = url_decode(text)
                type_text(text)
                body = "Typed successfully"
            except Exception:
                body = "Error typing"
        else:
            body = "PicoW Keyboard Ready"

        response = (
            "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n"
            + body
        )

        try:
            conn.send(response.encode("utf-8"))
        except Exception:
            pass
        safe_close(conn)

        gc.collect()
        last_request = time.monotonic()
        time.sleep(0.1)

    except Exception:
        safe_close(conn)
        gc.collect()
        time.sleep(1)

    # --- Watchdog: restart Wi-Fi if idle for too long ---
    if time.monotonic() - last_request > 60:
        print("No requests for 60s — restarting Wi-Fi")
        try:
            wifi.radio.enabled = False
            time.sleep(1)
            wifi.radio.enabled = True
            wifi.radio.connect(secrets["ssid"], secrets["password"])
            pool = socketpool.SocketPool(wifi.radio)
            server = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
            server.settimeout(None)
            server.bind(("0.0.0.0", 80))
            server.listen(2)
            print(f"Reconnected! IP: {wifi.radio.ipv4_address}")
        except Exception as e:
            print(f"Restart failed: {e}")
        last_request = time.monotonic()
