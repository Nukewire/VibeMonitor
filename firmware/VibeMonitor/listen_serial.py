import sys, time
import serial

# Listen-only: do NOT toggle DTR/RTS (don't reset the board) — we want to watch
# the live captive-portal session while the user submits the form.
PORT = "COM3"
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0

s = serial.Serial()
s.port = PORT
s.baudrate = 115200
s.timeout = 1
s.dsrdtr = False
s.rtscts = False
try:
    s.open()
except Exception as e:
    print("OPEN_FAIL:", e)
    sys.exit(1)
# leave control lines released = run mode, no reset
s.setDTR(False)
s.setRTS(False)

end = time.time() + DUR
got = 0
while time.time() < end:
    chunk = s.read(256)
    if chunk:
        got += len(chunk)
        sys.stdout.write(chunk.decode("utf-8", "replace"))
        sys.stdout.flush()
s.close()
print("\n=== listened %.0fs, %d bytes ===" % (DUR, got))
