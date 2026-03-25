[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/mRmkZGKe)
# Network Programming - Assignment G01

## Anggota Kelompok
| Nama           | NRP        | Kelas     |
| ---            | ---        | ----------|
|Uwais Achmad|5025241103|D|
|Farrel Aqilla Novianto|5025241015|D|

## Link Youtube (Unlisted)
Link ditaruh di bawah ini
```

```

## Penjelasan Program

### Daftar Isi
1. [Peta Program](#1-peta-program)
2. [Protokol yang Diimplementasikan](#2-protokol-yang-diimplementasikan)
3. [Penjelasan Detail client.py](#3-penjelasan-detail-clientpy)
4. [Penjelasan Detail server-sync.py](#4-penjelasan-detail-server-syncpy)
5. [Penjelasan Detail server-thread.py](#5-penjelasan-detail-server-threadpy)
6. [Penjelasan Detail server-select.py](#6-penjelasan-detail-server-selectpy)
7. [Penjelasan Detail server-poll.py](#7-penjelasan-detail-server-pollpy)
8. [Operasi Program](#8-operasi-program)
9. [Tabel Perbedaan Implementasi](#9-tabel-perbedaan-implementasi)

### 1. Peta Program

##### 1.1 `client.py`
- Menjadi antarmuka user (CLI).
- Mengirim command ke server.
- Menerima balasan server secara paralel (thread receiver).
- Menyimpan file hasil download ke folder `downloads/`.

#### 1.2 `server-sync.py`
- Server blocking klasik.
- Melayani **satu** koneksi klien sampai selesai, baru lanjut ke klien berikutnya.

#### 1.3 `server-thread.py`
- Server concurrent berbasis thread.
- Setiap klien punya thread sendiri.
- Memiliki registry klien untuk broadcast pesan `INFO`.

#### 1.4 `server-select.py`
- Server concurrent tanpa thread-per-klien.
- Memakai event loop `select.select()`.
- Menyimpan state per klien lewat `ClientState`.

#### 1.5 `server-poll.py`
- Konsep sama dengan `server-select.py`, tapi API I/O multiplexing pakai `poll()`.
- State klien dipetakan berdasarkan file descriptor.

---

### 2. Protokol yang Diimplementasikan

Semua varian server memproses protokol yang sama, sehingga `client.py` bisa dipakai ke semua server.

#### 2.1 Request dari klien
- `/list`
- `/upload <filename> <size>` lalu payload biner sejumlah `<size>` byte
- `/download <filename>`

#### 2.2 Respons dari server
- `INFO <pesan>`
- `ERR <pesan>`
- `OK upload complete`
- `LIST <n>` + `ITEM <nama_file>` (sebanyak `n`) + `END`
- `FILE <filename> <size>` + payload biner

#### 2.3 Mengapa ada `size`
Karena TCP berbentuk stream byte, penerima perlu tahu batas akhir data file. Itulah fungsi `size` pada header `FILE` dan `/upload`.

---

### 3. Penjelasan Detail `client.py`

#### 3.1 Alur dari `main()`
1. Tentukan host/port (default `127.0.0.1:9000`, bisa dari argumen CLI).
2. Panggil `ensure_download_dir()`.
3. Buat socket dan `connect()` ke server.
4. Jalankan thread `receiver_loop()` sebagai daemon.
5. Masuk loop input user.
6. Command diproses:
   - `/upload <path>` diproses lokal oleh `send_upload()`.
   - Command lain (`/list`, `/download`) dikirim apa adanya ke server.
7. Keluar jika `/quit` atau interrupt.

#### 3.2 Fungsi penting dan perannya

##### `ensure_download_dir()`
- Membuat folder `downloads` pada working directory saat ini.
- Menjamin path simpan download selalu tersedia.

##### `recv_exact(conn_file, size)`
- Membaca stream persis `size` byte.
- Loop sampai byte terpenuhi.
- Jika koneksi putus sebelum lengkap, lempar `ConnectionError`.

##### `receiver_loop(conn, download_dir)`
- Thread penerima.
- Parsing baris header dari server (`readline()`).
- Branch berdasarkan prefix header:
  - `FILE`: parse nama & ukuran, panggil `recv_exact`, simpan file ke disk.
  - `LIST`: parse jumlah item, baca `ITEM` berulang, konsumsi `END`, tampilkan list.
  - Lainnya: tampilkan sebagai teks (`INFO`, `ERR`, dll).

##### `send_upload(conn, filepath)`
- Validasi bahwa file lokal ada.
- Ambil basename + ukuran file.
- Kirim header `/upload <filename> <size>`.
- Stream isi file per chunk 4096 byte via `sendall()`.

#### 3.3 Catatan implementasi
- Thread receiver dan thread input user dipisah supaya klien tetap responsif.
- Pemakaian `os.path.basename` pada nama file mencegah path tidak diinginkan saat simpan.

### 4. Penjelasan Detail `server-sync.py`

#### 4.1 Alur dari `main()`
1. Pastikan folder `server_files` ada (`ensure_storage_dir()`).
2. Buat server socket, `bind()`, `listen()`.
3. Loop:
   - `accept()` klien.
   - Panggil `handle_client()`.
   - Setelah klien selesai/putus, kembali `accept()` klien berikutnya.

### 4.2 Fungsi penting

##### `safe_filename(name)`
- Mengambil basename dari input user.
- Mencegah path traversal sederhana (`../../file`).

##### `send_list(conn, storage_dir)`
- Scan file regular dalam `storage_dir`.
- Urutkan nama file.
- Kirim `LIST`, lalu `ITEM` per file, lalu `END`.

##### `recv_exact(conn_file, size)`
- Dipakai saat upload.
- Memastikan server membaca payload file secara utuh sesuai `size`.

##### `handle_client(conn, addr, storage_dir)`
- Kirim pesan awal `INFO Connected...`.
- Loop baca command baris demi baris.
- Branch command:
  - `/list`: panggil `send_list`.
  - `/upload`: validasi argumen, baca payload, simpan file, kirim `OK`.
  - `/download`: cek file, kirim header `FILE`, stream file.
  - Lainnya: kirim `ERR unknown command`.

#### 4.3 Karakteristik perilaku
- Jika satu klien lambat upload/download, klien lain harus menunggu.
- Cocok sebagai baseline paling mudah untuk memahami protokol.

### 5. Penjelasan Detail `server-thread.py`

#### 5.1 Alur dari `main()`
1. Inisialisasi storage dan `ClientRegistry`.
2. Listen socket.
3. Tiap `accept()`, buat thread daemon yang menjalankan `handle_client(...)`.

#### 5.2 Komponen unik

##### Kelas `ClientRegistry`
- Menyimpan list socket klien aktif (`_clients`).
- Menjaga konsistensi data dengan `_lock`.
- `add()`/`remove()` untuk manajemen lifecycle klien.
- `broadcast(message)` mengirim `INFO <message>` ke semua klien aktif.

##### `handle_client(conn, addr, storage_dir, registry)`
- Saat koneksi masuk:
  - `registry.add(conn)`.
  - broadcast status connect.
- Command handling sama seperti `server-sync.py`.
- Tambahan: setelah upload berhasil, broadcast event upload.
- Pada `finally`: remove dari registry dan broadcast disconnect.

#### 5.3 Nilai pembelajaran
- Menunjukkan pola shared-state + lock saat banyak thread akses resource bersama.
- Menunjukkan trade-off: lebih paralel tetapi ada overhead thread.

### 6. Penjelasan Detail `server-select.py`

#### 6.1 Alur event loop
1. `inputs` berisi `server socket`.
2. Panggil `select.select(inputs, [], [], 1)` berulang.
3. Untuk setiap socket yang readable:
   - Jika server socket: terima klien baru, masukkan ke `inputs`, buat `ClientState`.
   - Jika client socket: `recv(4096)` lalu proses buffer.

#### 6.2 Struktur data `ClientState`
- `addr`: alamat klien.
- `buffer`: byte masuk yang belum diproses tuntas.
- `mode`:
  - `command` → parser menunggu newline.
  - `upload` → parser menunggu byte payload sesuai `expected`.
- `expected`: jumlah byte upload yang ditunggu.
- `upload_name`: nama target file upload.

#### 6.3 Mekanisme parser

##### `handle_command(conn, state, clients, storage_dir, line)`
- Parsing command text (header).
- Untuk `/upload`, fungsi ini **tidak langsung baca payload**.
- Fungsi hanya set state (`mode=upload`, `expected=size`, `upload_name`).

##### `process_buffer(conn, state, clients, storage_dir)`
- Loop selama buffer punya data yang bisa diproses.
- Jika mode `command`:
  - cari `\n`; jika belum ada, tunggu paket berikutnya.
  - jika ada, ambil satu command lengkap lalu kirim ke `handle_command`.
- Jika mode `upload`:
  - tunggu hingga `len(buffer) >= expected`.
  - tulis file ke disk.
  - kirim `OK upload complete`.
  - broadcast event upload.
  - reset state ke mode `command`.

#### 6.4 Poin penting implementasi
- Karena event-driven, server ini bisa melayani banyak klien tanpa membuat thread baru.
- Kompleksitas berpindah ke manajemen state parser per koneksi.

### 7. Penjelasan Detail `server-poll.py`

#### 7.1 Alur event loop
1. Daftarkan server socket ke poller (`POLLIN`).
2. `events = poller.poll(1000)` menghasilkan pasangan `(fd, event)`.
3. Jika `fd` milik server:
   - `accept()` klien baru.
   - `register(conn, POLLIN)`.
   - Simpan state ke map `clients[conn_fd]`.
4. Jika `fd` milik klien:
   - `recv()` data.
   - jika kosong → klien putus, unregister + close + remove state.
   - jika ada data → append ke buffer lalu `process_buffer(...)`.

#### 7.2 Struktur dan parser
- `ClientState` dan logika mode (`command`/`upload`) sama konsep dengan `server-select.py`.
- Perbedaan utama ada pada mekanisme pemantauan socket (`poll`) dan identifikasi klien via file descriptor.

#### 7.3 Dampak desain
- Cocok untuk skenario banyak descriptor aktif.
- Tetap membutuhkan parser stateful agar stream TCP bisa diterjemahkan menjadi command dan payload file.

### 8. Operasi Program

#### 8.1 Operasi `/list`
- Client: kirim `/list\n`.
- Server: `send_list()` kirim `LIST`, beberapa `ITEM`, lalu `END`.
- Client receiver: parse jumlah item, tampilkan nama file.

#### 8.2 Operasi `/upload`
- Client: `send_upload()` kirim header + payload biner.
- Server:
  - validasi argumen header.
  - baca payload sesuai ukuran (`recv_exact` atau mode `upload` di state machine).
  - simpan ke `server_files/`.
  - balas `OK upload complete`.

#### 8.3 Operasi `/download`
- Client: kirim `/download <nama>`.
- Server: jika file ada, kirim `FILE <nama> <size>` + payload.
- Client: `receiver_loop()` memanggil `recv_exact`, lalu simpan ke `downloads/`.

### 9. Tabel Perbedaan Implementasi

| Aspek Kode | `server-sync.py` | `server-thread.py` | `server-select.py` | `server-poll.py` |
|---|---|---|---|---|
| Model eksekusi | Blocking | Thread per klien | Event loop | Event loop |
| Cara dispatch I/O | Direct call `handle_client` | Thread start per `accept` | `select.select` | `poll.poll` |
| Key state klien | Tidak ada map klien global | List socket pada registry | Socket object | File descriptor |
| Kebutuhan lock | Tidak | Ya (`Lock`) | Tidak (single loop) | Tidak (single loop) |
| Broadcast | Tidak | Ya | Ya | Ya |
| Kompleksitas parser | Rendah | Rendah-Sedang | Sedang-Tinggi (state machine) | Sedang-Tinggi (state machine) |

## Screenshot Hasil
