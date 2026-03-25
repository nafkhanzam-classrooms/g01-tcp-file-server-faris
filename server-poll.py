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


def broadcast(clients: Dict[int, "ClientState"], message: str, exclude: socket.socket = None) -> None:
    data = f"INFO {message}\n".encode("utf-8")
    for state in list(clients.values()):
        if exclude is not None and state.conn is exclude:
            continue
        try:
            state.conn.sendall(data)
        except OSError:
            pass


@dataclass
class ClientState:
    conn: socket.socket
    addr: tuple
    buffer: bytearray = field(default_factory=bytearray)
    mode: str = "command"
    expected: int = 0
    upload_name: str = ""


def handle_command(state: ClientState, clients: Dict[int, ClientState], storage_dir: str, line: str) -> None:
    # if the line is not a command, broadcast it as a plain message
    if not line.startswith('/'):
        broadcast(clients, f"{state.addr}: {line}", exclude=state.conn)
        return
    parts = line.split()
    if not parts:
        return
    cmd = parts[0]
    if cmd == "/list":
        send_list(state.conn, storage_dir)
    elif cmd == "/upload":
        if len(parts) < 3:
            state.conn.sendall(b"ERR usage: /upload <filename> <size>\n")
            return
        filename = safe_filename(parts[1])
        try:
            size = int(parts[2])
        except ValueError:
            state.conn.sendall(b"ERR invalid size\n")
            return
        if size < 0 or not filename:
            state.conn.sendall(b"ERR invalid upload\n")
            return
        state.mode = "upload"
        state.expected = size
        state.upload_name = filename
    elif cmd == "/download":
        if len(parts) < 2:
            state.conn.sendall(b"ERR usage: /download <filename>\n")
            return
        filename = safe_filename(parts[1])
        path = os.path.join(storage_dir, filename)
        if not os.path.isfile(path):
            state.conn.sendall(b"ERR not_found\n")
            return
        size = os.path.getsize(path)
        state.conn.sendall(f"FILE {filename} {size}\n".encode("utf-8"))
        with open(path, "rb") as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                state.conn.sendall(chunk)
    else:
        state.conn.sendall(b"ERR unknown command\n")


def process_buffer(state: ClientState, clients: Dict[int, ClientState], storage_dir: str) -> None:
    while True:
        if state.mode == "command":
            newline_index = state.buffer.find(b"\n")
            if newline_index == -1:
                return
            raw_line = state.buffer[:newline_index]
            del state.buffer[: newline_index + 1]
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                handle_command(state, clients, storage_dir, line)
        elif state.mode == "upload":
            if len(state.buffer) < state.expected:
                return
            data = bytes(state.buffer[: state.expected])
            del state.buffer[: state.expected]
            path = os.path.join(storage_dir, state.upload_name)
            with open(path, "wb") as f:
                f.write(data)
            state.conn.sendall(b"OK upload complete\n")
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
        server_fd = server.fileno()
        poller = select.poll()
        poller.register(server, select.POLLIN)
        clients: Dict[int, ClientState] = {}
        print(f"server-poll listening on {host}:{port}")
        while True:
            events = poller.poll(1000)
            for fd, event in events:
                if fd == server_fd:
                    conn, addr = server.accept()
                    conn_fd = conn.fileno()
                    poller.register(conn, select.POLLIN)
                    clients[conn_fd] = ClientState(conn=conn, addr=addr)
                    conn.sendall(b"INFO Connected. Commands: /list, /upload <file>, /download <file>\n")
                    print(f"client connected: {addr}")
                else:
                    state = clients.get(fd)
                    if not state:
                        continue
                    try:
                        data = state.conn.recv(4096)
                    except OSError:
                        data = b""
                    if not data:
                        poller.unregister(state.conn)
                        state.conn.close()
                        clients.pop(fd, None)
                        broadcast(clients, f"client disconnected: {state.addr}")
                        continue
                    state.buffer.extend(data)
                    process_buffer(state, clients, storage_dir)


if __name__ == "__main__":
    main()
