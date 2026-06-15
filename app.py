"""Streamlit meeting scheduler MVP."""

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from db import create_share_token, get_connection, init_db


st.set_page_config(
    page_title="Meeting Scheduler",
    page_icon="📅",
    layout="wide",
)


def create_poll_page() -> None:
    """Create a new meeting poll."""
    st.header("Create Meeting Poll")

    with st.form("create_poll_form"):
        title = st.text_input("Meeting title")
        description = st.text_area("Description")
        organizer_name = st.text_input("Your name")
        organizer_email = st.text_input("Your email")

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
                share_token
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                title,
                description,
                organizer_name,
                organizer_email,
                token,
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

        conn.close()

        st.success("Poll created.")
        st.code(f"?poll={token}")


def response_page(token: str) -> None:
    """Allow participants to respond to a poll."""
    conn = get_connection()

    poll = conn.execute(
        """
        SELECT id, title, description
        FROM polls
        WHERE share_token = ?
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

        for slot_id, start_time, end_time in slots:
            label = format_slot(start_time, end_time)
            is_available = st.checkbox(label, key=f"slot_{slot_id}")

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
            "Create Poll",
            "Results",
        ],
    )

    if page == "Create Poll":
        create_poll_page()
    else:
        results_page()


if __name__ == "__main__":
    main()