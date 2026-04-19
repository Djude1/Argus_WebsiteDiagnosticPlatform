# auth.py
# 後台管理認證模組：JWT 登入 + SQLite 使用者/聯絡人 CRUD + 系統統計
# 前端 UI 已在 templates/index.html 中實作，此模組提供對應 API

import os
import time
import sqlite3
import hashlib
import hmac
import json
import base64
import logging
from datetime import datetime
from contextlib import contextmanager
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

# ── 設定 ──────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("AUTH_DB_PATH", "data/admin.db")
JWT_SECRET = os.getenv("JWT_SECRET", "aiglass-default-secret-change-me")
JWT_EXPIRE_SEC = int(os.getenv("JWT_EXPIRE_SEC", "86400"))  # 預設 24 小時

router = APIRouter()

# ── SQLite 工具 ──────────────────────────────────────────────────────────

_db_initialized: bool = False  # 建表只跑一次，避免每次 get_db() 都重跑 DDL

@contextmanager
def get_db():
    """取得資料庫連線（自動建表、自動關閉）"""
    global _db_initialized
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    if not _db_initialized:
        _ensure_tables(conn)
        _db_initialized = True
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_tables(conn: sqlite3.Connection):
    """建表（冪等）"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            detail TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # 確保預設 admin 帳號存在
    cur = conn.execute("SELECT id FROM users WHERE username = 'admin'")
    if cur.fetchone() is None:
        pw_hash = _hash_password("admin123")
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", pw_hash, "admin")
        )
        conn.commit()
        logger.info("已建立預設管理員帳號 admin / admin123")


# ── 密碼雜湊 ─────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    """SHA-256 雜湊密碼（生產環境建議改用 bcrypt）"""
    return hashlib.sha256(password.encode()).hexdigest()


# ── 簡易 JWT（不需額外套件）────────────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def create_jwt(payload: dict) -> str:
    """建立 JWT token"""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {**payload, "exp": int(time.time()) + JWT_EXPIRE_SEC}
    h = _b64url_encode(json.dumps(header).encode())
    p = _b64url_encode(json.dumps(payload).encode())
    sig = hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url_encode(sig)}"


def verify_jwt(token: str) -> dict:
    """驗證 JWT token，回傳 payload"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("格式錯誤")
        h, p, s = parts
        expected_sig = hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        actual_sig = _b64url_decode(s)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("簽名不符")
        payload = json.loads(_b64url_decode(p))
        if payload.get("exp", 0) < time.time():
            raise ValueError("Token 已過期")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token 驗證失敗: {e}")


# ── 依賴注入：驗證 JWT ──────────────────────────────────────────────────

async def require_admin(request: Request) -> dict:
    """從 Authorization header 取得並驗證 JWT，要求 admin 角色"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供 Token")
    token = auth_header[7:]
    payload = verify_jwt(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理員權限")
    return payload


# ── Pydantic Models ──────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"

class UpdateUserRequest(BaseModel):
    enabled: Optional[bool] = None

class CreateContactRequest(BaseModel):
    name: str
    phone: str


# ── API 路由 ─────────────────────────────────────────────────────────────

@router.post("/api/login")
async def api_login(req: LoginRequest):
    """後台管理登入"""
    with get_db() as db:
        row = db.execute(
            "SELECT id, username, password_hash, role, enabled FROM users WHERE username = ?",
            (req.username,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    if row["password_hash"] != _hash_password(req.password):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    if not row["enabled"]:
        raise HTTPException(status_code=403, detail="帳號已停用")
    token = create_jwt({"uid": row["id"], "username": row["username"], "role": row["role"]})
    _log_event("login", f"使用者 {row['username']} 登入")
    return {"access_token": token, "role": row["role"]}


# ── 使用者管理 ────────────────────────────────────────────────────────────

@router.get("/api/users")
async def api_list_users(_admin=Depends(require_admin)):
    """列出所有使用者"""
    with get_db() as db:
        rows = db.execute("SELECT id, username, role, enabled, created_at FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@router.post("/api/users")
async def api_create_user(req: CreateUserRequest, _admin=Depends(require_admin)):
    """新增使用者"""
    with get_db() as db:
        existing = db.execute("SELECT id FROM users WHERE username = ?", (req.username,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="帳號已存在")
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (req.username, _hash_password(req.password), req.role)
        )
    _log_event("create_user", f"新增使用者 {req.username}")
    return {"ok": True}


@router.put("/api/users/{uid}")
async def api_update_user(uid: int, req: UpdateUserRequest, _admin=Depends(require_admin)):
    """更新使用者（啟用/停用）"""
    with get_db() as db:
        if req.enabled is not None:
            db.execute("UPDATE users SET enabled = ? WHERE id = ?", (1 if req.enabled else 0, uid))
    return {"ok": True}


@router.delete("/api/users/{uid}")
async def api_delete_user(uid: int, _admin=Depends(require_admin)):
    """刪除使用者"""
    with get_db() as db:
        db.execute("DELETE FROM contacts WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM users WHERE id = ?", (uid,))
    _log_event("delete_user", f"刪除使用者 ID={uid}")
    return {"ok": True}


# ── 聯絡人管理（管理員代管）─────────────────────────────────────────────

@router.get("/api/admin/users/{uid}/contacts")
async def api_list_contacts(uid: int, _admin=Depends(require_admin)):
    """列出指定使用者的聯絡人"""
    with get_db() as db:
        rows = db.execute(
            "SELECT id, name, phone, created_at FROM contacts WHERE user_id = ? ORDER BY id",
            (uid,)
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/admin/users/{uid}/contacts")
async def api_create_contact(uid: int, req: CreateContactRequest, _admin=Depends(require_admin)):
    """為指定使用者新增聯絡人"""
    with get_db() as db:
        db.execute(
            "INSERT INTO contacts (user_id, name, phone) VALUES (?, ?, ?)",
            (uid, req.name, req.phone)
        )
    return {"ok": True}


@router.delete("/api/admin/contacts/{cid}")
async def api_delete_contact(cid: int, _admin=Depends(require_admin)):
    """刪除聯絡人"""
    with get_db() as db:
        db.execute("DELETE FROM contacts WHERE id = ?", (cid,))
    return {"ok": True}


# ── 系統統計（管理員 Dashboard）──────────────────────────────────────────

@router.get("/api/admin/stats")
async def api_admin_stats(_admin=Depends(require_admin)):
    """管理員統計資訊"""
    try:
        import psutil
        _has_psutil = True
    except ImportError:
        _has_psutil = False

    with get_db() as db:
        user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        contact_count = db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        recent_logs = db.execute(
            "SELECT event, detail, created_at FROM system_logs ORDER BY id DESC LIMIT 20"
        ).fetchall()

    # 系統資源
    if _has_psutil:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
    else:
        cpu_percent = 0
        mem = type('', (), {'used': 0, 'total': 0, 'percent': 0})()
        disk = type('', (), {'used': 0, 'total': 0})()

    # GPU 資訊（如果有 CUDA）
    gpu_info = None
    try:
        import torch
        if torch.cuda.is_available():
            gpu_info = {
                "name": torch.cuda.get_device_name(0),
                "memory_used_mb": round(torch.cuda.memory_allocated(0) / 1024 / 1024, 1),
                "memory_total_mb": round(torch.cuda.get_device_properties(0).total_mem / 1024 / 1024, 1),
            }
    except Exception:
        pass

    return {
        "users": user_count,
        "contacts": contact_count,
        "system": {
            "cpu_percent": cpu_percent,
            "memory_used_gb": round(mem.used / 1024**3, 1),
            "memory_total_gb": round(mem.total / 1024**3, 1),
            "memory_percent": mem.percent,
            "disk_used_gb": round(disk.used / 1024**3, 1),
            "disk_total_gb": round(disk.total / 1024**3, 1),
        },
        "gpu": gpu_info,
        "recent_logs": [dict(r) for r in recent_logs],
    }


# ── 系統日誌工具 ──────────────────────────────────────────────────────────

def _log_event(event: str, detail: str = ""):
    """寫入系統日誌（供後台統計使用）"""
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO system_logs (event, detail) VALUES (?, ?)",
                (event, detail)
            )
    except Exception as e:
        logger.error(f"寫入系統日誌失敗: {e}")


def log_navigation_event(event: str, detail: str = ""):
    """供外部模組呼叫，記錄導航相關事件"""
    _log_event(event, detail)
