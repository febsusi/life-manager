import os
import requests
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret")

FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL", "").rstrip("/")
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "")

IDENTITY_TOOLKIT = "https://identitytoolkit.googleapis.com/v1"
SECURE_TOKEN = "https://securetoken.googleapis.com/v1/token"


def firebase_auth_request(endpoint, payload):
    if not FIREBASE_API_KEY:
        raise RuntimeError("FIREBASE_API_KEY belum diatur.")
    url = f"{IDENTITY_TOOLKIT}/{endpoint}?key={FIREBASE_API_KEY}"
    r = requests.post(url, json=payload, timeout=20)
    return r


def firebase_error(response):
    try:
        msg = response.json().get("error", {}).get("message", "Unknown error")
    except Exception:
        msg = response.text or "Unknown error"

    messages = {
        "EMAIL_EXISTS": "Email sudah terdaftar.",
        "EMAIL_NOT_FOUND": "Akun tidak ditemukan.",
        "INVALID_PASSWORD": "Password salah.",
        "INVALID_LOGIN_CREDENTIALS": "Email atau password salah.",
        "USER_DISABLED": "Akun dinonaktifkan.",
        "WEAK_PASSWORD : Password should be at least 6 characters": "Password minimal 6 karakter.",
        "WEAK_PASSWORD": "Password minimal 6 karakter.",
        "INVALID_EMAIL": "Format email tidak valid.",
        "TOO_MANY_ATTEMPTS_TRY_LATER": "Terlalu banyak percobaan. Coba lagi nanti.",
    }
    return messages.get(msg, msg.replace("_", " ").title())


def current_user():
    return session.get("user")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Silakan login terlebih dahulu.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def refresh_id_token():
    user = session.get("user")
    if not user or not user.get("refreshToken"):
        return False

    try:
        r = requests.post(
            f"{SECURE_TOKEN}?key={FIREBASE_API_KEY}",
            data={
                "grant_type": "refresh_token",
                "refresh_token": user["refreshToken"],
            },
            timeout=20,
        )
        if r.ok:
            data = r.json()
            user["idToken"] = data["id_token"]
            user["localId"] = data["user_id"]
            session["user"] = user
            return True
    except requests.RequestException:
        pass

    return False


def db_request(method, path, data=None, retry=True):
    if not FIREBASE_DB_URL:
        raise RuntimeError("FIREBASE_DB_URL belum diatur.")

    user = current_user()
    token = user.get("idToken") if user else None

    url = f"{FIREBASE_DB_URL}{path}.json"
    params = {"auth": token} if token else {}

    r = requests.request(
        method,
        url,
        params=params,
        json=data,
        timeout=20,
    )

    if r.status_code == 401 and retry and user and user.get("refreshToken"):
        if refresh_id_token():
            return db_request(method, path, data, retry=False)

    r.raise_for_status()

    if not r.content:
        return None
    return r.json()


def db_get(path):
    return db_request("GET", path)


def db_post(path, data):
    return db_request("POST", path, data)


def db_patch(path, data):
    return db_request("PATCH", path, data)


def db_delete(path):
    return db_request("DELETE", path)


def send_verification_email(id_token):
    """Firebase sends the verification email directly. No SMTP."""
    r = firebase_auth_request(
        "accounts:sendOobCode",
        {
            "requestType": "VERIFY_EMAIL",
            "idToken": id_token,
        },
    )
    return r.ok, firebase_error(r) if not r.ok else None


def reload_user(id_token):
    r = firebase_auth_request(
        "accounts:lookup",
        {"idToken": id_token},
    )
    if r.ok:
        users = r.json().get("users", [])
        if users:
            return users[0]
    return None


def normalize_items(data):
    if not isinstance(data, dict):
        return []
    result = []
    for item_id, item in data.items():
        if isinstance(item, dict):
            item = dict(item)
            item["_id"] = item_id
            result.append(item)
    return result


@app.route("/")
@login_required
def index():
    uid = current_user()["localId"]
    try:
        expenses = normalize_items(db_get(f"/users/{uid}/expenses"))
        todos = normalize_items(db_get(f"/users/{uid}/todos"))
        firebase_ok = True
        firebase_error_message = None
    except Exception as e:
        expenses = []
        todos = []
        firebase_ok = False
        firebase_error_message = str(e)

    total_expense = sum(float(x.get("amount", 0) or 0) for x in expenses)
    completed = sum(1 for x in todos if x.get("completed"))
    pending = len(todos) - completed

    return render_template(
        "index.html",
        user=current_user(),
        expenses=expenses,
        todos=todos,
        total_expense=total_expense,
        completed=completed,
        pending=pending,
        firebase_ok=firebase_ok,
        firebase_error_message=firebase_error_message,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email dan password wajib diisi.", "error")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password minimal 6 karakter.", "error")
            return render_template("register.html")

        r = firebase_auth_request(
            "accounts:signUp",
            {
                "email": email,
                "password": password,
                "returnSecureToken": True,
            },
        )

        if not r.ok:
            flash(firebase_error(r), "error")
            return render_template("register.html")

        data = r.json()
        ok, err = send_verification_email(data["idToken"])

        if not ok:
            flash(
                "Akun berhasil dibuat, tetapi email verifikasi gagal dikirim: "
                + (err or "Unknown error"),
                "error",
            )
            return redirect(url_for("login"))

        flash(
            "Registrasi berhasil. Firebase telah mengirim email verifikasi ke "
            + email
            + ". Silakan verifikasi sebelum login.",
            "success",
        )
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        r = firebase_auth_request(
            "accounts:signInWithPassword",
            {
                "email": email,
                "password": password,
                "returnSecureToken": True,
            },
        )

        if not r.ok:
            flash(firebase_error(r), "error")
            return render_template("login.html")

        data = r.json()
        profile = reload_user(data["idToken"])

        if not profile:
            flash("Tidak dapat memeriksa status akun Firebase.", "error")
            return render_template("login.html")

        if not profile.get("emailVerified", False):
            flash(
                "Email belum diverifikasi. Silakan cek inbox dan klik link "
                "verifikasi dari Firebase.",
                "error",
            )
            return render_template(
                "login.html",
                show_resend=True,
                email_for_resend=email,
            )

        session["user"] = {
            "localId": data["localId"],
            "email": data["email"],
            "idToken": data["idToken"],
            "refreshToken": data["refreshToken"],
        }
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/resend-verification", methods=["POST"])
def resend_verification():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email or not password:
        flash("Untuk keamanan, masukkan email dan password untuk mengirim ulang verifikasi.", "error")
        return redirect(url_for("login"))

    r = firebase_auth_request(
        "accounts:signInWithPassword",
        {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        },
    )

    if not r.ok:
        flash(firebase_error(r), "error")
        return redirect(url_for("login"))

    data = r.json()
    profile = reload_user(data["idToken"])

    if profile and profile.get("emailVerified"):
        flash("Email sudah terverifikasi. Silakan login.", "success")
        return redirect(url_for("login"))

    ok, err = send_verification_email(data["idToken"])
    if ok:
        flash("Email verifikasi Firebase berhasil dikirim ulang.", "success")
    else:
        flash("Gagal mengirim ulang verifikasi: " + (err or "Unknown error"), "error")

    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Anda berhasil logout.", "success")
    return redirect(url_for("login"))


@app.route("/expenses/add", methods=["POST"])
@login_required
def add_expense():
    uid = current_user()["localId"]
    try:
        description = request.form.get("description", "").strip()
        amount = float(request.form.get("amount", "0") or 0)
        category = request.form.get("category", "Lainnya").strip() or "Lainnya"

        if not description or amount <= 0:
            flash("Deskripsi dan nominal harus diisi dengan benar.", "error")
            return redirect(url_for("index"))

        db_post(
            f"/users/{uid}/expenses",
            {
                "description": description,
                "amount": amount,
                "category": category,
                "created_at": __import__("datetime").datetime.utcnow().isoformat(),
            },
        )
        flash("Pengeluaran berhasil ditambahkan.", "success")
    except Exception as e:
        flash("Gagal menyimpan pengeluaran: " + str(e), "error")
    return redirect(url_for("index"))


@app.route("/expenses/delete/<item_id>", methods=["POST"])
@login_required
def delete_expense(item_id):
    try:
        uid = current_user()["localId"]
        db_delete(f"/users/{uid}/expenses/{item_id}")
        flash("Pengeluaran berhasil dihapus.", "success")
    except Exception as e:
        flash("Gagal menghapus pengeluaran: " + str(e), "error")
    return redirect(url_for("index"))


@app.route("/todos/add", methods=["POST"])
@login_required
def add_todo():
    uid = current_user()["localId"]
    try:
        title = request.form.get("title", "").strip()
        if not title:
            flash("Tugas wajib diisi.", "error")
            return redirect(url_for("index"))

        db_post(
            f"/users/{uid}/todos",
            {
                "title": title,
                "completed": False,
                "created_at": __import__("datetime").datetime.utcnow().isoformat(),
            },
        )
        flash("Tugas berhasil ditambahkan.", "success")
    except Exception as e:
        flash("Gagal menyimpan tugas: " + str(e), "error")
    return redirect(url_for("index"))


@app.route("/todos/toggle/<item_id>", methods=["POST"])
@login_required
def toggle_todo(item_id):
    try:
        uid = current_user()["localId"]
        item = db_get(f"/users/{uid}/todos/{item_id}") or {}
        db_patch(
            f"/users/{uid}/todos/{item_id}",
            {"completed": not bool(item.get("completed", False))},
        )
        flash("Status tugas diperbarui.", "success")
    except Exception as e:
        flash("Gagal memperbarui tugas: " + str(e), "error")
    return redirect(url_for("index"))


@app.route("/todos/delete/<item_id>", methods=["POST"])
@login_required
def delete_todo(item_id):
    try:
        uid = current_user()["localId"]
        db_delete(f"/users/{uid}/todos/{item_id}")
        flash("Tugas berhasil dihapus.", "success")
    except Exception as e:
        flash("Gagal menghapus tugas: " + str(e), "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
