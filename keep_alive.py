"""Keep SQLiteCloud database awake."""

import os

import sqlitecloud
from dotenv import load_dotenv


def main() -> None:
    """Ping SQLiteCloud with a simple query."""
    load_dotenv()

    connection_string = os.environ["SQLITECLOUD_CONNECTION_STRING"]

    conn = sqlitecloud.connect(connection_string)
    conn.execute("SELECT * from polls;")
    conn.close()

    print("SQLiteCloud keep-alive successful.")


if __name__ == "__main__":
    main()