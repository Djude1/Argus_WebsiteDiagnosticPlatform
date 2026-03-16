# auth.py
# -*- coding: utf-8 -*-
"""
使用者驗證與管理模組：JWT 認證 + SQLite 資料庫
- 使用者角色：admin（管理員）/ operator（操作員）/ user（一般用戶）
- 緊急連絡人：每位使用者可儲存多筆姓名 + 電話
"""

import os, sqlite3, hashlib, hmac, time, json, secrets
from typing import Optional

DB_PATH          = os.getenv("AUTH_DB_PATH", "auth.db")
JWT_SECRET_ENV   = os.getenv("JWT_SECRET", "")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "168"))  # 預設 7 天

_jwt_secret: Optional[str] = None


# ── 資料庫連線 ────────────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── JWT 密鑰管理（持久化到 DB，重啟後 token 仍有效）────────────────────────

def _get_secret() -> str:
    global _jwt_secret
    if _jwt_secret:
        return _jwt_secret
    if JWT_SECRET_ENV:
        _jwt_secret = JWT_SECRET_ENV
        return _jwt_secret
    # 從 DB 載入或建立
    with _get_db() as conn:
        row = conn.execute("SELECT value FROM config WHERE key='jwt_secret'").fetchone()
        if row:
            _jwt_secret = row["value"]
        else:
            _jwt_secret = secrets.token_hex(32)
            conn.execute(
                "INSERT INTO config (key, value) VALUES ('jwt_secret', ?)", (_jwt_secret,)
            )
            conn.commit()
    return _jwt_secret


# ── 資料庫初始化 ──────────────────────────────────────────────────────────────

def init_db():
    """建立資料表並確保預設 admin 帳號存在"""
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                role          TEXT    NOT NULL DEFAULT 'user',
                enabled       INTEGER NOT NULL DEFAULT 1,
                created_at    REAL    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name    TEXT    NOT NULL,
                phone   TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        # 預設 admin 帳號（admin / admin123）
        existing = conn.execute(
            "SELECT id FROM users WHERE username='admin'"
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, enabled, created_at) "
                "VALUES (?,?,?,?,?)",
                ("admin", _hash_password("1124"), "admin", 1, time.time()),
            )
        conn.commit()
    # 觸發密鑰初始化
    _get_secret()
    print("[AUTH] 資料庫初始化完成（預設帳號 admin / 1124）", flush=True)


# ── 密碼雜湊 ──────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    return hmac.compare_digest(_hash_password(password), stored_hash)


# ── JWT ───────────────────────────────────────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(s: str) -> bytes:
    import base64
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def create_token(user_id: int, role: str) -> str:
    """產生 HS256 JWT"""
    import hmac as _hmac
    header  = _b64url_encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64url_encode(json.dumps({
        "sub":  str(user_id),
        "role": role,
        "iat":  int(time.time()),
        "exp":  int(time.time()) + JWT_EXPIRE_HOURS * 3600,
    }).encode())
    sig_input = f"{header}.{payload}".encode()
    sig = _b64url_encode(
        _hmac.new(_get_secret().encode(), sig_input, "sha256").digest()
    )
    return f"{header}.{payload}.{sig}"


def verify_token(token: str) -> Optional[dict]:
    """驗證 JWT，成功回傳 payload dict，失敗回傳 None"""
    import hmac as _hmac
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        sig_input = f"{header}.{payload}".encode()
        expected  = _b64url_encode(
            _hmac.new(_get_secret().encode(), sig_input, "sha256").digest()
        )
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            return None  # 已過期
        return data
    except Exception:
        return None


# ── 使用者管理 ────────────────────────────────────────────────────────────────

def login(username: str, password: str) -> Optional[dict]:
    """登入驗證，成功回傳 token + user info，失敗回傳 None"""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND enabled=1", (username,)
        ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        token = create_token(row["id"], row["role"])
        return {
            "token":    token,
            "user_id":  row["id"],
            "role":     row["role"],
            "username": username,
        }


def list_users() -> list:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, role, enabled, created_at FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def create_user(username: str, password: str, role: str = "user") -> dict:
    with _get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, enabled, created_at) "
                "VALUES (?,?,?,?,?)",
                (username, _hash_password(password), role, 1, time.time()),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id FROM users WHERE username=?", (username,)
            ).fetchone()
            return {"ok": True, "user_id": row["id"]}
        except sqlite3.IntegrityError:
            return {"ok": False, "error": "使用者名稱已存在"}


def update_user(user_id: int, role: Optional[str] = None,
                enabled: Optional[bool] = None,
                password: Optional[str] = None) -> dict:
    updates, params = [], []
    if role is not None:
        updates.append("role=?")
        params.append(role)
    if enabled is not None:
        updates.append("enabled=?")
        params.append(1 if enabled else 0)
    if password is not None:
        updates.append("password_hash=?")
        params.append(_hash_password(password))
    if not updates:
        return {"ok": False, "error": "沒有要更新的欄位"}
    params.append(user_id)
    with _get_db() as conn:
        conn.execute(f"UPDATE users SET {','.join(updates)} WHERE id=?", params)
        conn.commit()
    return {"ok": True}


def delete_user(user_id: int) -> dict:
    with _get_db() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
    return {"ok": True}


def change_own_password(user_id: int, old_password: str, new_password: str) -> dict:
    with _get_db() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id=?", (user_id,)
        ).fetchone()
        if not row or not verify_password(old_password, row["password_hash"]):
            return {"ok": False, "error": "舊密碼錯誤"}
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (_hash_password(new_password), user_id),
        )
        conn.commit()
    return {"ok": True}


def get_user(user_id: int) -> Optional[dict]:
    with _get_db() as conn:
        row = conn.execute(
            "SELECT id, username, role, enabled FROM users WHERE id=?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


# ── 緊急連絡人管理 ────────────────────────────────────────────────────────────

def list_contacts(user_id: int) -> list:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, phone FROM contacts WHERE user_id=? ORDER BY name",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_contact(user_id: int, name: str, phone: str) -> dict:
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO contacts (user_id, name, phone) VALUES (?,?,?)",
            (user_id, name, phone),
        )
        conn.commit()
    return {"ok": True}


def update_contact(contact_id: int, user_id: int, name: str, phone: str) -> dict:
    with _get_db() as conn:
        conn.execute(
            "UPDATE contacts SET name=?, phone=? WHERE id=? AND user_id=?",
            (name, phone, contact_id, user_id),
        )
        conn.commit()
    return {"ok": True}


def delete_contact(contact_id: int, user_id: int) -> dict:
    with _get_db() as conn:
        conn.execute(
            "DELETE FROM contacts WHERE id=? AND user_id=?", (contact_id, user_id)
        )
        conn.commit()
    return {"ok": True}
