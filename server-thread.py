#!/usr/bin/env python3
import os
import socket
import threading
from typing import Dict, List


def safe_filename(name: str) -> str:
    return os.path.basename(name.strip())


def ensure_storage_dir() -> str:
    storage_dir = os.path.join(os.getcwd(), "server_files")
    os.makedirs(storage_dir, exist_ok=True)
    return storage_dir


def send_list(conn: socket.socket, storage_dir: str) -> None:
    files = sorted([f for f in os.listdir(storage_dir) if os.path.isfile(os.path.join(storage_dir, f))])
    conn.sendall(f"LIST {len(files)}\n".encode("utf-8"))
    for name in files:
        conn.sendall(f"ITEM {name}\n".encode("utf-8"))
    conn.sendall(b"END\n")


def recv_exact(conn_file, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining > 0:
        data = conn_file.read(remaining)
        if not data:
            raise ConnectionError("Client disconnected during file transfer")
        chunks.append(data)
        remaining -= len(data)
    return b"".join(chunks)


class ClientRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: List[socket.socket] = []

    def add(self, conn: socket.socket) -> None:
        with self._lock:
            self._clients.append(conn)

    def remove(self, conn: socket.socket) -> None:
        with self._lock:
            if conn in self._clients:
                self._clients.remove(conn)

    def broadcast(self, message: str) -> None:
        data = f"INFO {message}\n".encode("utf-8")
        with self._lock:
            for client in list(self._clients):
                try:
                    client.sendall(data)
                except OSError:
                    pass


def handle_client(conn: socket.socket, addr, storage_dir: str, registry: ClientRegistry) -> None:
    with conn:
        registry.add(conn)
        registry.broadcast(f"client connected: {addr}")
        conn_file = conn.makefile("rb")
        conn.sendall(b"INFO Connected. Commands: /list, /upload <file>, /download <file>\n")
        try:
            while True:
                line = conn_file.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                parts = text.split()
                cmd = parts[0]
                if cmd == "/list":
                    send_list(conn, storage_dir)
                elif cmd == "/upload":
                    if len(parts) < 3:
                        conn.sendall(b"ERR usage: /upload <filename> <size>\n")
                        continue
                    filename = safe_filename(parts[1])
                    try:
                        size = int(parts[2])
                    except ValueError:
                        conn.sendall(b"ERR invalid size\n")
                        continue
                    if size < 0 or not filename:
                        conn.sendall(b"ERR invalid upload\n")
                        continue
                    data = recv_exact(conn_file, size)
                    path = os.path.join(storage_dir, filename)
                    with open(path, "wb") as f:
                        f.write(data)
                    conn.sendall(b"OK upload complete\n")
                    registry.broadcast(f"uploaded {filename} from {addr}")
                elif cmd == "/download":
                    if len(parts) < 2:
                        conn.sendall(b"ERR usage: /download <filename>\n")
                        continue
                    filename = safe_filename(parts[1])
                    path = os.path.join(storage_dir, filename)
                    if not os.path.isfile(path):
                        conn.sendall(b"ERR not_found\n")
                        continue
                    size = os.path.getsize(path)
                    conn.sendall(f"FILE {filename} {size}\n".encode("utf-8"))
                    with open(path, "rb") as f:
                        while True:
                            chunk = f.read(4096)
                            if not chunk:
                                break
                            conn.sendall(chunk)
                else:
                    conn.sendall(b"ERR unknown command\n")
        finally:
            registry.remove(conn)
            registry.broadcast(f"client disconnected: {addr}")


def main() -> None:
    host = "0.0.0.0"
    port = 9000
    storage_dir = ensure_storage_dir()
    registry = ClientRegistry()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(50)
        print(f"server-thread listening on {host}:{port}")
        while True:
            conn, addr = server.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr, storage_dir, registry), daemon=True)
            thread.start()


if __name__ == "__main__":
    main()
