"""Database helpers for the meeting scheduler app."""

import secrets
from typing import Any

import sqlitecloud
import streamlit as st


def get_connection() -> Any:
    """Create a SQLite Cloud connection."""
    return sqlitecloud.connect(st.secrets["SQLITECLOUD_CONNECTION_STRING"])


def init_db() -> None:
    """Create database tables."""
    conn = get_connection()

    with open("schema.sql", "r", encoding="utf-8") as file:
        sql_script = file.read()

    for statement in sql_script.split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(statement)

    conn.close()


def create_share_token() -> str:
    """Create a safe public token for poll links."""
    return secrets.token_urlsafe(12)