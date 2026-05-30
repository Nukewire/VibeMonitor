import sys, time
import serial

PORT = "COM3"
# Open WITHOUT letting pyserial assert control lines (which can hold EN/IO0
# and silently drop the ESP32 into bootloader/download mode on CH340 boards).
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

# Release both lines = run mode (IO0 high, EN high)
s.setDTR(False)   # IO0
s.setRTS(False)   # EN
time.sleep(0.1)
# Reset pulse: assert EN low briefly, release -> chip boots and RUNS firmware
s.setRTS(True)
time.sleep(0.15)
s.setRTS(False)

end = time.time() + 12
got = 0
buf = b""
while time.time() < end:
    chunk = s.read(256)
    if chunk:
        got += len(chunk)
        sys.stdout.write(chunk.decode("utf-8", "replace"))
        sys.stdout.flush()
s.close()
print("\n=== captured %d bytes ===" % got)
