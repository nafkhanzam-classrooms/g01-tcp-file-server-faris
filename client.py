#!/usr/bin/env python3
import os
import socket
import sys
import threading


def ensure_download_dir() -> str:
    download_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)
    return download_dir


def recv_exact(conn_file, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining > 0:
        data = conn_file.read(remaining)
        if not data:
            raise ConnectionError("Disconnected during file transfer")
        chunks.append(data)
        remaining -= len(data)
    return b"".join(chunks)


def receiver_loop(conn: socket.socket, download_dir: str) -> None:
    conn_file = conn.makefile("rb")
    try:
        while True:
            line = conn_file.readline()
            if not line:
                print("Disconnected from server.")
                return
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            if text.startswith("FILE "):
                parts = text.split(maxsplit=2)
                if len(parts) < 3:
                    print("Invalid FILE header.")
                    continue
                filename = os.path.basename(parts[1])
                try:
                    size = int(parts[2])
                except ValueError:
                    print("Invalid file size.")
                    continue
                data = recv_exact(conn_file, size)
                path = os.path.join(download_dir, filename)
                with open(path, "wb") as f:
                    f.write(data)
                print(f"Downloaded {filename} ({size} bytes)")
            elif text.startswith("LIST "):
                try:
                    count = int(text.split()[1])
                except (IndexError, ValueError):
                    print(text)
                    continue
                items = []
                for _ in range(count):
                    item_line = conn_file.readline()
                    if not item_line:
                        break
                    item_text = item_line.decode("utf-8", errors="replace").strip()
                    if item_text.startswith("ITEM "):
                        items.append(item_text[5:])
                end_line = conn_file.readline()
                if items:
                    print("Files on server:")
                    for name in items:
                        print(f"- {name}")
                else:
                    print("No files on server.")
                if end_line:
                    _ = end_line
            else:
                print(text)
    except (ConnectionError, OSError):
        print("Connection closed.")


def send_upload(conn: socket.socket, filepath: str) -> None:
    if not os.path.isfile(filepath):
        print("File not found.")
        return
    filename = os.path.basename(filepath)
    size = os.path.getsize(filepath)
    header = f"/upload {filename} {size}\n".encode("utf-8")
    conn.sendall(header)
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(4096)
            if not chunk:
                break
            conn.sendall(chunk)


def main() -> None:
    host = "127.0.0.1"
    port = 9000
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])
    download_dir = ensure_download_dir()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
        conn.connect((host, port))
        receiver = threading.Thread(target=receiver_loop, args=(conn, download_dir), daemon=True)
        receiver.start()
        print("Type /list, /upload <file>, /download <file>, or /quit")
        try:
            while True:
                line = input("> ").strip()
                if not line:
                    continue
                if line == "/quit":
                    break
                if line.startswith("/upload "):
                    parts = line.split(maxsplit=1)
                    if len(parts) < 2:
                        print("Usage: /upload <path>")
                        continue
                    send_upload(conn, parts[1])
                    continue
                conn.sendall((line + "\n").encode("utf-8"))
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    main()
