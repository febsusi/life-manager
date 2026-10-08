# Life Manager - Flask + Firebase Authentication + Cloudflare Workers

Aplikasi gabungan Expense Tracker dan To-Do List.

## Fitur

- Register dengan Firebase Authentication
- Firebase langsung mengirim email verification
- Login hanya jika email sudah verified
- Resend verification email
- Logout
- Expense Tracker
- To-Do List
- Data terpisah berdasarkan Firebase UID
- Firebase Realtime Database REST API
- ID Token Firebase dipakai untuk request database
- Refresh ID Token otomatis jika expired
- Tanpa SMTP
- Tanpa Firebase Admin SDK
- Cocok untuk deploy Cloudflare Python Workers

## 1. Firebase Authentication

Firebase Console:
Authentication > Sign-in method > Email/Password > Enable.

Pastikan Email/Password aktif.

## 2. Ambil Web API Key

Firebase Console > Project settings > General > Your apps > Web API Key.

Masukkan sebagai:

FIREBASE_API_KEY

## 3. Realtime Database

Buat Realtime Database.

Ambil URL database, contoh:

https://project-id-default-rtdb.firebaseio.com

Jangan tambahkan `/expenses` dan jangan tambahkan `.json`.

Masukkan sebagai:

FIREBASE_DB_URL

## 4. Firebase Rules

Gunakan rules dari file `firebase.rules.json`.

Isi:

{
  "rules": {
    "users": {
      "$uid": {
        ".read": "auth != null && auth.uid === $uid",
        ".write": "auth != null && auth.uid === $uid"
      }
    }
  }
}

Rules ini membuat setiap user hanya dapat mengakses data miliknya sendiri.

## 5. Jalankan lokal

Install Python.

Buat virtual environment:

python -m venv .venv

Mac/Linux:

source .venv/bin/activate

Windows:

.venv\Scripts\activate

Install:

pip install -r requirements.txt

Copy `.env.example` menjadi `.env`, kemudian isi:

SECRET_KEY=...
FIREBASE_DB_URL=https://...
FIREBASE_API_KEY=...

Untuk local development, load environment variables sesuai terminal/editor yang digunakan.

Run:

python app.py

Buka:

http://127.0.0.1:5000

## 6. Cloudflare

Project ini menggunakan:

worker.py
wrangler.toml

Install Wrangler:

npm install -g wrangler

Login:

wrangler login

Install Python Workers dependency jika environment Cloudflare yang digunakan membutuhkan package `workers`.

Kemudian set secrets:

wrangler secret put SECRET_KEY
wrangler secret put FIREBASE_DB_URL
wrangler secret put FIREBASE_API_KEY

Untuk setiap command, paste value ketika diminta.

Deploy:

wrangler deploy

## 7. Firebase Authentication setelah deploy

Setelah mendapatkan URL Cloudflare, misalnya:

https://life-manager.example.workers.dev

Buka:

Firebase Console
> Authentication
> Settings
> Authorized domains

Tambahkan domain Cloudflare tersebut.

## 8. Email verification

Aplikasi tidak menggunakan SMTP.

Saat register:

Browser -> Flask -> Firebase Authentication -> Firebase mengirim verification email.

Firebase sendiri yang menangani email verifikasi.

Saat user klik link verifikasi, status Firebase berubah menjadi:

emailVerified = true

Aplikasi kemudian mengizinkan login.

## 9. Penting

Jangan gunakan Firebase Rules:

".read": true,
".write": true

untuk deployment production.

Aplikasi ini menggunakan Firebase ID Token sehingga rules dapat tetap private.

## 10. Struktur database

users/
  FIREBASE_UID/
    expenses/
      AUTO_ID/
        description
        amount
        category
        created_at
    todos/
      AUTO_ID/
        title
        completed
        created_at

## 11. Catatan Cloudflare

Cloudflare Workers Python dapat memiliki keterbatasan runtime/dependency dibanding Flask biasa. Project ini sengaja dibuat ringan dan tidak menggunakan:

- numpy
- scipy
- sklearn
- firebase-admin
- SMTP
- database driver berat

Tujuannya agar deployment lebih ringan.
