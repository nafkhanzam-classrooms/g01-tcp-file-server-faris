#!/usr/bin/env python3
import os
import select
import socket
from dataclasses import dataclass, field
from typing import Dict


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


def broadcast(clients: Dict[socket.socket, "ClientState"], message: str) -> None:
    data = f"INFO {message}\n".encode("utf-8")
    for client in list(clients.keys()):
        try:
            client.sendall(data)
        except OSError:
            pass


@dataclass
class ClientState:
    addr: tuple
    buffer: bytearray = field(default_factory=bytearray)
    mode: str = "command"
    expected: int = 0
    upload_name: str = ""


def handle_command(conn: socket.socket, state: ClientState, clients: Dict[socket.socket, ClientState], storage_dir: str, line: str) -> None:
    parts = line.split()
    if not parts:
        return
    cmd = parts[0]
    if cmd == "/list":
        send_list(conn, storage_dir)
    elif cmd == "/upload":
        if len(parts) < 3:
            conn.sendall(b"ERR usage: /upload <filename> <size>\n")
            return
        filename = safe_filename(parts[1])
        try:
            size = int(parts[2])
        except ValueError:
            conn.sendall(b"ERR invalid size\n")
            return
        if size < 0 or not filename:
            conn.sendall(b"ERR invalid upload\n")
            return
        state.mode = "upload"
        state.expected = size
        state.upload_name = filename
    elif cmd == "/download":
        if len(parts) < 2:
            conn.sendall(b"ERR usage: /download <filename>\n")
            return
        filename = safe_filename(parts[1])
        path = os.path.join(storage_dir, filename)
        if not os.path.isfile(path):
            conn.sendall(b"ERR not_found\n")
            return
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


def process_buffer(conn: socket.socket, state: ClientState, clients: Dict[socket.socket, ClientState], storage_dir: str) -> None:
    while True:
        if state.mode == "command":
            newline_index = state.buffer.find(b"\n")
            if newline_index == -1:
                return
            raw_line = state.buffer[:newline_index]
            del state.buffer[: newline_index + 1]
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                handle_command(conn, state, clients, storage_dir, line)
        elif state.mode == "upload":
            if len(state.buffer) < state.expected:
                return
            data = bytes(state.buffer[: state.expected])
            del state.buffer[: state.expected]
            path = os.path.join(storage_dir, state.upload_name)
            with open(path, "wb") as f:
                f.write(data)
            conn.sendall(b"OK upload complete\n")
            broadcast(clients, f"uploaded {state.upload_name} from {state.addr}")
            state.mode = "command"
            state.expected = 0
            state.upload_name = ""
        else:
            state.mode = "command"


def main() -> None:
    host = "0.0.0.0"
    port = 9000
    storage_dir = ensure_storage_dir()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(50)
        print(f"server-select listening on {host}:{port}")
        inputs = [server]
        clients: Dict[socket.socket, ClientState] = {}
        while True:
            readable, _, _ = select.select(inputs, [], [], 1)
            for sock in readable:
                if sock is server:
                    conn, addr = server.accept()
                    inputs.append(conn)
                    clients[conn] = ClientState(addr=addr)
                    conn.sendall(b"INFO Connected. Commands: /list, /upload <file>, /download <file>\n")
                    broadcast(clients, f"client connected: {addr}")
                else:
                    try:
                        data = sock.recv(4096)
                    except OSError:
                        data = b""
                    if not data:
                        inputs.remove(sock)
                        state = clients.pop(sock, None)
                        if state:
                            broadcast(clients, f"client disconnected: {state.addr}")
                        sock.close()
                        continue
                    state = clients.get(sock)
                    if not state:
                        continue
                    state.buffer.extend(data)
                    process_buffer(sock, state, clients, storage_dir)


if __name__ == "__main__":
    main()
