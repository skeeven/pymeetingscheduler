"""Test SQLite Cloud connection."""

import streamlit as st
import sqlitecloud


def main() -> None:
    """Connect to SQLite Cloud and test the polls table."""
    connection_string = st.secrets["SQLITECLOUD_CONNECTION_STRING"]

    conn = sqlitecloud.connect(connection_string)
    cursor = conn.execute("SELECT * FROM polls;")
    result = cursor.fetchone()

    print(result)

    conn.close()


if __name__ == "__main__":
    main()