from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt

from app.database.session import Database
from app.services.audit_service import now_iso


class AuthService:
    def __init__(self, database: Database, session_expire_hours: int = 12):
        self.database = database
        self.session_expire_hours = session_expire_hours

    def create_user(self, username: str, password: str, role: str = "viewer") -> dict:
        if role not in {"viewer", "operator", "admin"}:
            raise ValueError("invalid role")
        now = now_iso()
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO users (username, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (username.strip(), password_hash, role, now, now),
            )
            user_id = cursor.lastrowid
        return self.get_user(int(user_id))

    def update_user(self, user_id: int, *, password: str | None = None, role: str | None = None, is_active: bool | None = None) -> dict:
        current = self.get_user(user_id)
        fields = []
        params: list[object] = []
        if password is not None:
            fields.append("password_hash = ?")
            params.append(bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode())
        if role is not None:
            if role not in {"viewer", "operator", "admin"}:
                raise ValueError("invalid role")
            fields.append("role = ?")
            params.append(role)
        if is_active is not None:
            fields.append("is_active = ?")
            params.append(int(is_active))
        if fields:
            fields.append("updated_at = ?")
            params.append(now_iso())
            params.append(user_id)
            with self.database.transaction() as connection:
                connection.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", tuple(params))
        return self.get_user(user_id)

    def get_user(self, user_id: int) -> dict:
        row = self.database.fetch_one("SELECT id, username, role, is_active, created_at, updated_at FROM users WHERE id = ?", (user_id,))
        if row is None:
            raise ValueError("user not found")
        return dict(row)

    def list_users(self) -> list[dict]:
        return [dict(row) for row in self.database.fetch_all("SELECT id, username, role, is_active, created_at, updated_at FROM users ORDER BY username")]

    def authenticate(self, username: str, password: str) -> dict | None:
        row = self.database.fetch_one("SELECT * FROM users WHERE username = ? AND is_active = 1", (username.strip(),))
        if row is None or not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            return None
        return {"id": row["id"], "username": row["username"], "role": row["role"]}

    def create_session(self, user_id: int) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=self.session_expire_hours)
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (_hash_token(token), user_id, now_iso(), expires.isoformat()),
            )
        return token, expires

    def get_session_user(self, token: str | None) -> dict | None:
        if not token:
            return None
        row = self.database.fetch_one(
            """SELECT u.id, u.username, u.role, u.is_active, s.expires_at
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ?""",
            (_hash_token(token),),
        )
        if row is None or not row["is_active"]:
            return None
        try:
            expires = datetime.fromisoformat(row["expires_at"])
        except ValueError:
            return None
        if expires <= datetime.now(timezone.utc):
            self.logout(token)
            return None
        return {"id": row["id"], "username": row["username"], "role": row["role"]}

    def logout(self, token: str | None) -> None:
        if token:
            with self.database.transaction() as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

