"""
db_manager.py — Supabase Integration & Authentication Manager
Handles database operations, single-device lockout, session verification, 
activity auditing logs, and RBAC admin controls for the FMCSA Scraper app.
"""

import datetime
import hashlib
import uuid
from typing import Dict, List, Optional, Tuple
import pandas as pd
import streamlit as st

try:
    from supabase import create_client, Client
    HAS_SUPABASE_LIB = True
except ImportError:
    Client = None
    HAS_SUPABASE_LIB = False


def hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _get_supabase_client() -> Optional[Client]:
    """Initialize Supabase client if secrets are properly configured."""
    if not HAS_SUPABASE_LIB:
        return None
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    if not url or not key or "your-project-id" in url or "your-supabase" in key:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None


class DatabaseManager:
    """Unified Database interface with real Supabase + local fallback mode."""

    def __init__(self):
        self.sb = _get_supabase_client()

    @property
    def is_using_supabase(self) -> bool:
        return self.sb is not None

    def authenticate_and_login(self, username: str, password: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Validate username & password, generate new session_token UUID,
        update active_session_id in DB to enforce Single-Device Lockout,
        and log the LOGIN activity.
        """
        username = username.strip()
        hashed = hash_password(password)
        session_token = str(uuid.uuid4())

        # ── 1. Check Primary Configured Secret Admin Account ────────────────
        secrets_admin_u = st.secrets.get("ADMIN_USERNAME", "admin").strip()
        secrets_admin_p = st.secrets.get("ADMIN_PASSWORD", "admin_secret_password_123")

        if username == secrets_admin_u and password == secrets_admin_p:
            user_info = {
                "username": username,
                "is_admin": True,
                "delay_ms": int(st.secrets.get("DEFAULT_DELAY_MS", 500)),
                "session_duration_hours": float(st.secrets.get("DEFAULT_SESSION_HOURS", 3.0)),
                "session_token": session_token,
            }

            # Sync active_session_id to Supabase if connected
            if self.is_using_supabase:
                try:
                    self.sb.table("users").upsert({
                        "username": username,
                        "password_hash": hash_password(password),
                        "is_admin": True,
                        "active_session_id": session_token,
                    }, on_conflict="username").execute()
                except Exception:
                    pass

            st.session_state[f"active_token_{username}"] = session_token
            self.log_activity(username, "LOGIN", "Super Admin logged in successfully")
            return True, "Success", user_info

        # ── 2. Check Supabase Database Table ─────────────────────────────────
        if self.is_using_supabase:
            try:
                res = self.sb.table("users").select("*").eq("username", username).execute()
                if res.data:
                    user_row = res.data[0]
                    if user_row.get("password_hash") == hashed or user_row.get("password") == password:
                        self.sb.table("users").update({"active_session_id": session_token}).eq("username", username).execute()
                        user_info = {
                            "username": user_row["username"],
                            "is_admin": user_row.get("is_admin", False),
                            "delay_ms": user_row.get("delay_ms", 500),
                            "session_duration_hours": float(user_row.get("session_duration_hours", 3.0)),
                            "session_token": session_token,
                        }
                        self.log_activity(username, "LOGIN", "User logged in via Supabase")
                        return True, "Success", user_info
                    else:
                        return False, "Invalid password.", None
            except Exception:
                pass

        # ── 3. Check In-Memory Fallback Users ────────────────────────────────
        users = st.session_state.get("fallback_users", {})
        if username in users:
            u = users[username]
            if u["password_hash"] == hashed or u.get("password") == password:
                u["active_session_id"] = session_token
                user_info = {
                    "username": u["username"],
                    "is_admin": u.get("is_admin", False),
                    "delay_ms": u.get("delay_ms", 500),
                    "session_duration_hours": float(u.get("session_duration_hours", 3.0)),
                    "session_token": session_token,
                }
                self.log_activity(username, "LOGIN", "User logged in via Fallback Mode")
                return True, "Success", user_info

        return False, "User not found.", None

    def verify_active_session(self, username: str, session_token: str) -> bool:
        """
        Single-Device Lockout Check:
        Returns True if current local session_token matches active_session_id in DB.
        """
        if not username or not session_token:
            return False

        secrets_admin_u = st.secrets.get("ADMIN_USERNAME", "admin").strip()
        if username == secrets_admin_u:
            stored_token = st.session_state.get(f"active_token_{username}")
            if stored_token:
                return stored_token == session_token

        if self.is_using_supabase:
            try:
                res = self.sb.table("users").select("active_session_id").eq("username", username).execute()
                if res.data:
                    current_db_token = res.data[0].get("active_session_id")
                    return current_db_token == session_token
            except Exception:
                pass

        users = st.session_state.get("fallback_users", {})
        if username in users:
            return users[username].get("active_session_id") == session_token
        return True

    def log_activity(self, user_email: str, action_type: str, details: str = ""):
        """Record critical user action into activity_logs table."""
        now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        log_entry = {
            "timestamp": now_str,
            "user_email": user_email,
            "action_type": action_type,
            "details": details,
        }

        if self.is_using_supabase:
            try:
                self.sb.table("activity_logs").insert(log_entry).execute()
                return
            except Exception:
                pass

        if "fallback_activity_logs" not in st.session_state:
            st.session_state["fallback_activity_logs"] = []

        logs = st.session_state["fallback_activity_logs"]
        logs.insert(0, log_entry)
        st.session_state["fallback_activity_logs"] = logs[:500]

    def get_activity_logs(self, limit: int = 200) -> pd.DataFrame:
        """Retrieve latest N user activity logs for Super Admin review."""
        if self.is_using_supabase:
            try:
                res = (
                    self.sb.table("activity_logs")
                    .select("*")
                    .order("timestamp", desc=True)
                    .limit(limit)
                    .execute()
                )
                if res.data:
                    return pd.DataFrame(res.data)
            except Exception:
                pass

        logs = st.session_state.get("fallback_activity_logs", [])
        if not logs:
            return pd.DataFrame(columns=["timestamp", "user_email", "action_type", "details"])
        return pd.DataFrame(logs[:limit])

    def get_all_users(self) -> List[Dict]:
        """Fetch list of user accounts."""
        if self.is_using_supabase:
            try:
                res = self.sb.table("users").select("username, is_admin, delay_ms, session_duration_hours, created_at").execute()
                if res.data:
                    return res.data
            except Exception:
                pass

        users = st.session_state.get("fallback_users", {})
        res = []
        for u in users.values():
            res.append({
                "username": u["username"],
                "is_admin": u.get("is_admin", False),
                "delay_ms": u.get("delay_ms", 500),
                "session_duration_hours": u.get("session_duration_hours", 3.0),
                "created_at": u.get("created_at", ""),
            })
        return res

    def create_user(
        self,
        admin_username: str,
        new_username: str,
        new_password: str,
        is_admin: bool = False,
        delay_ms: int = 500,
        session_duration_hours: float = 3.0,
    ) -> Tuple[bool, str]:
        """Create a new user account (Super Admin feature)."""
        new_username = new_username.strip()
        if not new_username or not new_password:
            return False, "Username and password cannot be empty."

        hashed = hash_password(new_password)
        now_str = datetime.datetime.utcnow().isoformat()

        if self.is_using_supabase:
            try:
                check = self.sb.table("users").select("username").eq("username", new_username).execute()
                if check.data:
                    return False, f"Username '{new_username}' already exists."

                data = {
                    "username": new_username,
                    "password_hash": hashed,
                    "is_admin": is_admin,
                    "delay_ms": delay_ms,
                    "session_duration_hours": session_duration_hours,
                    "active_session_id": "",
                    "created_at": now_str,
                }
                self.sb.table("users").insert(data).execute()
                self.log_activity(
                    admin_username,
                    "CREATE_USER",
                    f"Created user {new_username} (is_admin={is_admin})",
                )
                return True, f"User '{new_username}' created successfully."
            except Exception as e:
                return False, f"Database error: {str(e)}"

        if "fallback_users" not in st.session_state:
            st.session_state["fallback_users"] = {}

        users = st.session_state["fallback_users"]
        if new_username in users:
            return False, f"Username '{new_username}' already exists."

        users[new_username] = {
            "username": new_username,
            "password_hash": hashed,
            "is_admin": is_admin,
            "delay_ms": delay_ms,
            "session_duration_hours": session_duration_hours,
            "active_session_id": "",
            "created_at": now_str,
        }
        self.log_activity(
            admin_username,
            "CREATE_USER",
            f"Created user {new_username} (is_admin={is_admin})",
        )
        return True, f"User '{new_username}' created successfully."

    def update_user_config(
        self,
        admin_username: str,
        target_username: str,
        delay_ms: int,
        session_duration_hours: float,
        is_admin: Optional[bool] = None,
    ) -> Tuple[bool, str]:
        """Update per-user rate limits and session durations."""
        if self.is_using_supabase:
            try:
                update_data = {
                    "delay_ms": delay_ms,
                    "session_duration_hours": session_duration_hours,
                }
                if is_admin is not None:
                    update_data["is_admin"] = is_admin

                self.sb.table("users").update(update_data).eq("username", target_username).execute()
                self.log_activity(
                    admin_username,
                    "UPDATE_USER",
                    f"Updated {target_username}: delay={delay_ms}ms, duration={session_duration_hours}h",
                )
                return True, f"Updated settings for '{target_username}'."
            except Exception as e:
                return False, f"Database error: {str(e)}"

        users = st.session_state.get("fallback_users", {})
        if target_username not in users:
            return False, f"User '{target_username}' not found."

        users[target_username]["delay_ms"] = delay_ms
        users[target_username]["session_duration_hours"] = session_duration_hours
        if is_admin is not None:
            users[target_username]["is_admin"] = is_admin

        self.log_activity(
            admin_username,
            "UPDATE_USER",
            f"Updated {target_username}: delay={delay_ms}ms, duration={session_duration_hours}h",
        )
        return True, f"Updated settings for '{target_username}'."


db = DatabaseManager()
