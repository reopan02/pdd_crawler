
import socket
import time

def test_connection(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            print(f"✅ Successfully connected to {host}:{port}")
            return True
        else:
            print(f"❌ Failed to connect to {host}:{port} (error code: {result})")
            return False
    except Exception as e:
        print(f"❌ Error connecting to {host}:{port}: {e}")
        return False
    finally:
        sock.close()

if __name__ == "__main__":
    print("Testing connection to chrome-shop1:9222...")
    test_connection("chrome-shop1", 9222)
    print("\nTesting connection to localhost:9222...")
    test_connection("localhost", 9222)
