import time, random, usb_hid, wifi, socketpool, gc, ssl
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
import adafruit_requests
from secrets import secrets

keyboard = Keyboard(usb_hid.devices)
layout = KeyboardLayoutUS(keyboard)

print("Connecting to Wi-Fi…")
wifi.radio.connect(secrets["ssid"], secrets["password"])
print("Connected! IP:", wifi.radio.ipv4_address)

pool = socketpool.SocketPool(wifi.radio)
server = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
server.bind(("0.0.0.0", 80))
server.listen(2)
print(f"Listening on http://{wifi.radio.ipv4_address}")

session = adafruit_requests.Session(pool, ssl.create_default_context())
LAPTOP_IP = "http://10.152.136.189:5000"  # change to your laptop’s IP

def safe_close(c):
    try: c.close()
    except: pass

def type_text(txt):
    for c in txt:
        if c == "\n": keyboard.send(Keycode.ENTER)
        else:
            try: layout.write(c)
            except: pass
        time.sleep(random.uniform(0.03,0.08))

def press_combo(*keys):
    keyboard.press(*keys); time.sleep(0.1)
    keyboard.release_all(); time.sleep(0.2)

def press_enter(): keyboard.send(Keycode.ENTER); time.sleep(0.2)

def url_decode(s):
    out=""; i=0
    while i < len(s):
        if s[i]=="%" and i+2<len(s):
            try: out+=chr(int(s[i+1:i+3],16)); i+=3; continue
            except: pass
        elif s[i]=="+": out+=" "
        else: out+=s[i]
        i+=1
    return out

def parse_email_data(d):
    f={"TO":"","SUBJECT":"","BODY":"","WRITE":""}
    for p in d.split(";"):
        if ":" in p:
            k,v=p.split(":",1)
            if k.upper() in f: f[k.upper()]=v.strip()
    return f

def remote_click(k):
    try:
        r=session.get(f"{LAPTOP_IP}/click?key={k}")
        print(r.text); r.close()
    except Exception as e:
        print("Click error:",e)

def ai_write(prompt):
    try:
        r = session.get(f"{LAPTOP_IP}/ai?prompt={prompt}")
        text = r.text.strip()
        r.close()

        subj, body = "", ""
        if "Subject:" in text and "Body:" in text:
            parts = text.split("Subject:", 1)[1].split("Body:")
            subj = parts[0].strip()
            body = parts[1].strip()
        else:
            # fallback: first line = subject, rest = body
            lines = text.split("\n")
            subj = lines[0].strip()
            body = "\n".join(lines[1:]).strip()

        return subj, body
    except Exception as e:
        print("AI error:", e)
        return "", ""


def perform_email(to,subject,body,write):
    print("Starting simplified email sequence...")
    if write:
        subject,body=ai_write(write)

    press_combo(Keycode.WINDOWS,Keycode.D)
    press_combo(Keycode.WINDOWS,Keycode.R)
    type_text("msedge.exe"); keyboard.send(Keycode.ENTER)
    time.sleep(5)
    press_combo(Keycode.WINDOWS,Keycode.UP_ARROW); time.sleep(2)

    remote_click("google"); time.sleep(2)
    remote_click("gmail");  time.sleep(6)
    remote_click("compose");time.sleep(4)

    remote_click("to")
    if to: type_text(to); press_enter(); time.sleep(1)

    remote_click("subject"); type_text(subject); time.sleep(0.5)
    remote_click("body");    type_text(body);    time.sleep(0.5)
    remote_click("send");    time.sleep(2)
    press_combo(Keycode.CONTROL,Keycode.W)
    print("Email sequence completed.")

def handle_request(req):
    if "/type?text=" in req:
        try:
            raw=req.split("/type?text=")[1].split(" ")[0]
            dec=url_decode(raw)
            f=parse_email_data(dec)
            perform_email(f["TO"],f["SUBJECT"],f["BODY"],f["WRITE"])
            return "Email sent successfully!"
        except Exception as e:
            return f"Error: {e}"
    return "Pico Emailer Ready"

while True:
    try:
        conn,addr=server.accept()
        data=bytearray(2048)
        n=conn.recv_into(data)
        if n==0: safe_close(conn); continue
        req=data[:n].decode("utf-8","ignore")
        resp=handle_request(req)
        conn.send(f"HTTP/1.1 200 OK\r\nContent-Type:text/plain\r\n\r\n{resp}".encode())
        safe_close(conn); gc.collect()
    except Exception as e:
        print("Error:",e); safe_close(conn); gc.collect()

