
import socket
import threading

def forward(source, destination):
    try:
        while True:
            data = source.recv(4096)
            if not data:
                break
            destination.sendall(data)
    except Exception:
        pass
    finally:
        try:
            source.close()
        except:
            pass
        try:
            destination.close()
        except:
            pass

def handle_client(client_socket):
    try:
        remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote_socket.connect(('127.0.0.1', 9222))
        
        client_to_remote = threading.Thread(target=forward, args=(client_socket, remote_socket))
        remote_to_client = threading.Thread(target=forward, args=(remote_socket, client_socket))
        
        client_to_remote.start()
        remote_to_client.start()
        
        client_to_remote.join()
        remote_to_client.join()
    except Exception as e:
        print(f"Proxy error: {e}")
    finally:
        try:
            client_socket.close()
        except:
            pass

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', 9223))
    server_socket.listen(5)
    
    print("CDP proxy listening on 0.0.0.0:9223, forwarding to 127.0.0.1:9222")
    
    while True:
        client_socket, addr = server_socket.accept()
        print(f"Accepted connection from {addr}")
        client_handler = threading.Thread(target=handle_client, args=(client_socket,))
        client_handler.daemon = True
        client_handler.start()

if __name__ == "__main__":
    main()
