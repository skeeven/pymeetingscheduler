"""Streamlit meeting scheduler MVP."""

from datetime import datetime, timedelta

import bcrypt
import pandas as pd
import streamlit as st

from db import create_share_token, get_connection, init_db


st.set_page_config(
    page_title="Meeting Scheduler",
    page_icon="📅",
    layout="wide",
)


def hash_password(password: str) -> str:
    """Hash a password."""
    password_bytes = password.encode("utf-8")
    return bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt()
    ).decode("utf-8")


def check_password(
    password: str,
    password_hash: str,
) -> bool:
    """Validate a password."""
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


def login_page() -> None:
    """Register or log in an organizer."""
    st.header("Organizer Login")

    if "user" in st.session_state:
        user = st.session_state["user"]
        st.success(f"Logged in as {user['name']}")

        if st.button("Logout"):
            del st.session_state["user"]
            st.rerun()

        return

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        email = st.text_input("Email", key="login_email")
        password = st.text_input(
            "Password",
            type="password",
            key="login_password",
        )

        if st.button("Login"):
            if not email or not password:
                st.error("Email and password are required.")
                return

            conn = get_connection()
            user = conn.execute(
                """
                SELECT id, name, email, password_hash
                FROM users
                WHERE email = ?
                """,
                (email,),
            ).fetchone()
            conn.close()

            if not user:
                st.error("User not found.")
                return

            user_id, name, user_email, password_hash = user

            if not check_password(password, password_hash):
                st.error("Incorrect password.")
                return

            st.session_state["user"] = {
                "id": user_id,
                "name": name,
                "email": user_email,
            }

            st.success("Logged in.")
            st.rerun()

    with tab_register:
        name = st.text_input("Name", key="register_name")
        email = st.text_input("Email", key="register_email")
        password = st.text_input(
            "Password",
            type="password",
            key="register_password",
        )

        if st.button("Create account"):
            if not name or not email or not password:
                st.error("Name, email, and password are required.")
                return

            conn = get_connection()

            existing_user = conn.execute(
                """
                SELECT id
                FROM users
                WHERE email = ?
                """,
                (email,),
            ).fetchone()

            if existing_user:
                conn.close()
                st.error("An account with that email already exists.")
                return

            conn.execute(
                """
                INSERT INTO users (
                    name,
                    email,
                    password_hash
                )
                VALUES (?, ?, ?)
                """,
                (name, email, hash_password(password)),
            )

            conn.commit()
            conn.close()

            st.success("Account created. Please log in.")


def create_poll_page() -> None:
    """Create a new meeting poll."""
    user = st.session_state.get("user")

    if not user:
        st.warning("Please log in first.")
        return

    st.header("Create Meeting Poll")

    with st.form("create_poll_form"):
        title = st.text_input("Meeting title")
        description = st.text_area("Description")
        # organizer_name = st.text_input("Your name")
        # organizer_email = st.text_input("Your email")

        st.subheader("Possible meeting times")

        slot_count = st.number_input(
            "How many time options?",
            min_value=1,
            max_value=20,
            value=3,
        )

        slots = []

        for index in range(slot_count):
            col1, col2, col3 = st.columns(3)

            with col1:
                date_value = st.date_input(
                    f"Date {index + 1}",
                    key=f"date_{index}",
                )

            with col2:
                start_value = st.time_input(
                    f"Start time {index + 1}",
                    key=f"start_{index}",
                )

            with col3:
                duration = st.number_input(
                    f"Minutes {index + 1}",
                    min_value=15,
                    max_value=240,
                    value=60,
                    step=15,
                    key=f"duration_{index}",
                )

            start_dt = datetime.combine(date_value, start_value)
            end_dt = start_dt + timedelta(minutes=duration)
            slots.append((start_dt.isoformat(), end_dt.isoformat()))

        submitted = st.form_submit_button("Create poll")

    if submitted:
        if not title:
            st.error("Meeting title is required.")
            return

        token = create_share_token()
        conn = get_connection()

        cursor = conn.execute(
            """
            INSERT INTO polls (
                title,
                description,
                organizer_name,
                organizer_email,
                share_token,
                user_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                description,
                user["name"],
                user["email"],
                token,
                user["id"]
            ),
        )

        poll_id = cursor.lastrowid

        for start_time, end_time in slots:
            conn.execute(
                """
                INSERT INTO time_slots (
                    poll_id,
                    start_time,
                    end_time
                )
                VALUES (?, ?, ?)
                """,
                (poll_id, start_time, end_time),
            )

        conn.commit()
        conn.close()

        base_url = st.secrets.get("APP_BASE_CLOUD", "").rstrip("/")
        participant_link = f"{base_url}/?poll={token}"

        st.success("Poll created.")
        st.write("Send this link to attendees:")
        st.code(participant_link)


def response_page(token: str) -> None:
    """Allow participants to respond to a poll."""
    conn = get_connection()

    poll = conn.execute(
        """
        SELECT id, title, description
        FROM polls
        WHERE share_token = ?
            AND status = 'open'
        """,
        (token,),
    ).fetchone()

    if not poll:
        st.error("Poll not found.")
        conn.close()
        return

    poll_id, title, description = poll

    st.header(title)

    if description:
        st.write(description)

    slots = conn.execute(
        """
        SELECT id, start_time, end_time
        FROM time_slots
        WHERE poll_id = ?
        ORDER BY start_time
        """,
        (poll_id,),
    ).fetchall()

    with st.form("availability_form"):
        name = st.text_input("Your name")
        email = st.text_input("Your email")

        selected_slots = []

        slots_by_date = {}

        for slot_id, start_time, end_time in slots:
            start_dt = datetime.fromisoformat(start_time)
            date_key = start_dt.date()
            slots_by_date.setdefault(date_key, []).append(
                (slot_id, start_time, end_time)
            )

        date_columns = st.columns(len(slots_by_date))

        for column, date_key in zip(date_columns, sorted(slots_by_date)):
            day_slots = slots_by_date[date_key]

            with column:
                st.markdown(f"### {date_key.strftime('%a, %b %d')}")

                for slot_id, start_time, end_time in day_slots:
                    start_dt = datetime.fromisoformat(start_time)
                    end_dt = datetime.fromisoformat(end_time)

                    label = (
                        f"{start_dt.strftime('%I:%M %p')} - "
                        f"{end_dt.strftime('%I:%M %p')}"
                    )

                    is_available = st.checkbox(
                        label,
                        key=f"slot_{slot_id}",
                    )

                    if is_available:
                        selected_slots.append(slot_id)

        submitted = st.form_submit_button("Submit availability")

    if submitted:
        if not name:
            st.error("Name is required.")
            conn.close()
            return

        cursor = conn.execute(
            """
            INSERT INTO participants (
                poll_id,
                name,
                email
            )
            VALUES (?, ?, ?)
            """,
            (poll_id, name, email),
        )

        participant_id = cursor.lastrowid

        for slot_id, _, _ in slots:
            status = "available" if slot_id in selected_slots else "unavailable"

            conn.execute(
                """
                INSERT INTO responses (
                    participant_id,
                    time_slot_id,
                    availability_status
                )
                VALUES (?, ?, ?)
                """,
                (participant_id, slot_id, status),
            )

        st.success("Your availability was saved.")

    conn.commit()
    conn.close()


def results_page() -> None:
    """Show poll results."""
    st.header("Poll Results")

    token = st.text_input("Enter poll token")

    if not token:
        return

    conn = get_connection()

    poll = conn.execute(
        """
        SELECT id, title
        FROM polls
        WHERE share_token = ?
        """,
        (token,),
    ).fetchone()

    if not poll:
        st.error("Poll not found.")
        conn.close()
        return

    poll_id, title = poll
    st.subheader(title)

    rows = conn.execute(
        """
        SELECT
            ts.start_time,
            ts.end_time,
            SUM(
                CASE
                    WHEN r.availability_status = 'available' THEN 1
                    ELSE 0
                END
            ) AS available_count,
            COUNT(r.id) AS total_responses
        FROM time_slots ts
        LEFT JOIN responses r
            ON r.time_slot_id = ts.id
        WHERE ts.poll_id = ?
        GROUP BY ts.id
        ORDER BY available_count DESC, ts.start_time ASC
        """,
        (poll_id,),
    ).fetchall()

    conn.close()

    data = []

    for start_time, end_time, available_count, total_responses in rows:
        data.append(
            {
                "Time": format_slot(start_time, end_time),
                "Available": available_count or 0,
                "Total Responses": total_responses or 0,
            }
        )

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)


def get_poll_results(poll_id: int) -> pd.DataFrame:
    """Get availability results for one poll."""
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            ts.start_time,
            ts.end_time,
            SUM(
                CASE
                    WHEN r.availability_status = 'available' THEN 1
                    ELSE 0
                END
            ) AS available_count,
            COUNT(r.id) AS total_responses
        FROM time_slots ts
        LEFT JOIN responses r
            ON r.time_slot_id = ts.id
        WHERE ts.poll_id = ?
        GROUP BY ts.id
        ORDER BY available_count DESC, ts.start_time ASC
        """,
        (poll_id,),
    ).fetchall()

    conn.close()

    data = []

    for start_time, end_time, available_count, total_responses in rows:
        data.append(
            {
                "Time": format_slot(start_time, end_time),
                "Available": available_count or 0,
                "Total Responses": total_responses or 0,
            }
        )

    return pd.DataFrame(data)


def delete_poll(poll_id: int, user_id: int) -> bool:
    """Soft delete a poll owned by the logged-in user."""
    conn = get_connection()

    cursor = conn.execute(
        """
        UPDATE polls
        SET status = 'deleted'
        WHERE id = ?
            AND user_id = ?
        """,
        (poll_id, user_id),
    )

    conn.commit()
    conn.close()

    return cursor.rowcount > 0


def my_meetings_page() -> None:
    """Show meetings created by the logged-in user."""
    st.header("My Meetings")

    user = st.session_state.get("user")

    if not user:
        st.warning("Please log in first.")
        return

    base_url = st.secrets.get("APP_BASE_CLOUD", "")

    conn = get_connection()
    polls = conn.execute(
        """
        SELECT
            id,
            title,
            share_token,
            status,
            created_at
        FROM polls
        WHERE user_id = ?
            AND status = 'open'
        ORDER BY created_at DESC
        """,
        (user["id"],),
    ).fetchall()
    conn.close()

    if not polls:
        st.info("You have not created any meetings yet.")
        return

    for poll_id, title, token, status, created_at in polls:
        participant_link = f"{base_url}?poll={token}"

        with st.container(border=True):
            col1, col2 = st.columns([4, 1])

            with col1:
                st.subheader(title)

            with col2:
                if st.button(
                        "🗑 Delete",
                        key=f"delete_{poll_id}",
                ):
                    st.session_state["confirm_delete"] = poll_id

            if st.session_state.get("confirm_delete") == poll_id:
                st.warning("Are you sure? This cannot be undone.")

                col_yes, col_no = st.columns(2)

                with col_yes:
                    if st.button(
                            "Yes, delete",
                            key=f"confirm_{poll_id}",
                    ):
                        deleted = delete_poll(poll_id, user["id"])

                        if deleted:
                            st.session_state.pop("confirm_delete", None)
                            st.success("Meeting deleted.")
                            st.rerun()
                        else:
                            st.error("Meeting could not be deleted.")

                with col_no:
                    if st.button(
                            "Cancel",
                            key=f"cancel_{poll_id}",
                    ):
                        st.session_state.pop("confirm_delete", None)
                        st.rerun()

            st.write(f"Status: {status}")
            st.write(f"Created: {created_at}")

            st.write("Send this link to attendees:")
            st.code(participant_link)

            with st.expander("View results"):
                results_df = get_poll_results(poll_id)

                if results_df.empty:
                    st.info("No time slots found for this meeting.")
                else:
                    st.dataframe(
                        results_df,
                        use_container_width=True,
                        hide_index=True,
                    )


def format_slot(start_time: str, end_time: str) -> str:
    """Format a time slot for display."""
    start_dt = datetime.fromisoformat(start_time)
    end_dt = datetime.fromisoformat(end_time)

    return (
        f"{start_dt.strftime('%a, %b %d %I:%M %p')} - "
        f"{end_dt.strftime('%I:%M %p')}"
    )


def main() -> None:
    """Run the Streamlit app."""
    ## init_db()

    query_params = st.query_params

    if "poll" in query_params:
        response_page(query_params["poll"])
        return

    st.sidebar.title("Meeting Scheduler")
    page = st.sidebar.radio(
        "Choose page",
        [
            "Login",
            "My Meetings",
            "Create Poll",
            "Results",
        ],
    )

    if page == "Login":
        login_page()

    elif page == "My Meetings":
        my_meetings_page()

    elif page == "Create Poll":
        create_poll_page()

    else:
        results_page()


if __name__ == "__main__":
    main()