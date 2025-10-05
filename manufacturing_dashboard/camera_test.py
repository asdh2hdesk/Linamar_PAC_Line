import socket
import time

# Keyence SR-X100N IP and port (default 9004)
HOST = "192.168.100.100"
PORT = 9004

def send_command(sock, cmd):
    """Send a command and return response."""
    sock.sendall((cmd + '\r\n').encode('ascii'))
    time.sleep(0.1)
    data = sock.recv(1024).decode('ascii').strip()
    return data

def main():
    try:
        # Connect to the camera
        print(f"Connecting to {HOST}:{PORT} ...")
        # resp = send_command(sock, "QVER")
        # print("Firmware:", resp)

        with socket.create_connection((HOST, PORT), timeout=100) as sock:
            print("✅ Connected!")

            # 1️⃣ Go to manual trigger mode
            # (Disable auto read if enabled)
            resp = send_command(sock, "LON")  # Lock communication
            print("LON:", resp)

            # 2️⃣ Trigger read manually
            resp = send_command(sock, "TRG")  # Trigger command
            print("TRG response:", resp)

            # 3️⃣ Wait and read result
            time.sleep(0.5)
            resp = send_command(sock, "RD")   # Read last result
            print("Read data:", resp)

            # 4️⃣ Unlock if needed
            send_command(sock, "LOFF")

    except Exception as e:
        print("❌ Error:", e)


if __name__ == "__main__":
    main()
