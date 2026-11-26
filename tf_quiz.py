#!/usr/bin/env python3
"""True / false quiz, meant to be launched with Streamlit.

    streamlit run tf_quiz.py

The bank is csv/tf_questions.csv. A sitting is a random draw of however
many statements the reader asks for, or the whole bank. The score lives
in the browser session and is shown only at the end.

Image slots are at the top of this file. Leave a string empty and that
picture is skipped. A filled-in value may be a path relative to this
file, an absolute path, or a URL.
"""

from __future__ import annotations

import csv
import html
import random
from pathlib import Path

import streamlit as st


# Drop a file path or a URL into any of these. Empty means no picture.
CORRECT_IMAGE = "img/kevsmile.png"
INCORRECT_IMAGE = "img/sadcat.jpeg"
FAIL_IMAGE = "img/kena.jpeg"
PASS_IMAGE = "img/kevsmile.png"
WELLDONE_IMAGE = "img/kevproud.png"

CSV_PATH = Path(__file__).resolve().parent / "csv" / "tf_questions.csv"

# Soft washes, so the default dark text stays readable.
COLOUR_CORRECT = "#b7e4c7"
COLOUR_INCORRECT = "#f4b6b6"


def load_bank(path: Path) -> list[dict]:
    """Read statements that actually have a T or F verdict."""
    bank: list[dict] = []
    # utf-8-sig strips the BOM that Excel leaves on the first header.
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            verdict = (row.get("T/F") or "").strip().upper()
            question = (row.get("Question") or "").strip()
            if verdict not in {"T", "F"} or not question:
                continue
            bank.append(
                {
                    "number": (row.get("S/N") or "").strip(),
                    "question": question,
                    "answer": verdict == "T",
                    "explanation": (row.get("Explanation") or "").strip(),
                }
            )
    if not bank:
        raise SystemExit(f"No true/false questions found in {path}")
    return bank


def show_image(reference: str) -> None:
    """Render a picture when a reference has been filled in."""
    reference = (reference or "").strip()
    if not reference:
        return

    # A scheme marks a remote picture. Anything else is a file.
    if "://" in reference:
        st.image(reference, width=200)
        return

    path = Path(reference)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    if path.is_file():
        st.image(str(path), width=200)


def paint(colour: str) -> None:
    """Wash the page. Streamlit redraws from the top on every click.

    The text colour is pinned to a dark ink. A dark theme would otherwise
    leave pale type on a pale wash, and the verdict would be hard to read.
    """
    st.markdown(
        f"""
        <style>
        .stApp,
        [data-testid="stHeader"],
        [data-testid="stToolbar"] {{
            background-color: {colour};
        }}
        /* The theme's own colour rules are more specific, so this has to win. */
        .stApp h1, .stApp h2, .stApp h3,
        .stApp p, .stApp li, .stApp span, .stApp label,
        .stApp [data-testid="stMarkdownContainer"] * {{
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def fresh_sitting(bank: list[dict], count: int) -> None:
    """Draw a new sitting and zero the tally. The draw is shuffled."""
    count = max(1, min(count, len(bank)))
    st.session_state.deck = random.sample(bank, count)
    st.session_state.index = 0
    st.session_state.correct = 0
    st.session_state.phase = "question"
    st.session_state.last_choice = None


def record_answer(choice: bool) -> None:
    """Score the current statement once, then move to the coloured page."""
    card = st.session_state.deck[st.session_state.index]
    st.session_state.last_choice = choice
    st.session_state.last_right = choice == card["answer"]
    if st.session_state.last_right:
        st.session_state.correct += 1
    st.session_state.phase = "feedback"


def advance() -> None:
    """Leave the coloured page for the next statement, or the tally."""
    st.session_state.index += 1
    if st.session_state.index >= len(st.session_state.deck):
        st.session_state.phase = "results"
    else:
        st.session_state.phase = "question"


def render_setup(total: int) -> None:
    st.title("Plate-SLICcers")
    st.write(
        f"somebody get these BEGGARS outta here"
    )
    st.image("img/beggars.png", width=200)

    count = st.number_input(
        "How many questions do we wanna try? We have 190 true/false questions in the bank.",
        min_value=1,
        max_value=total,
        value=min(10, total),
        step=1,
    )

    short, whole = st.columns(2)
    with short:
        if st.button("Start", type="primary", use_container_width=True):
            fresh_sitting(st.session_state.bank, int(count))
            st.rerun()
    with whole:
        if st.button("Take the whole quiz", use_container_width=True):
            fresh_sitting(st.session_state.bank, total)
            st.rerun()


def render_question() -> None:
    deck = st.session_state.deck
    index = st.session_state.index
    card = deck[index]
    total = len(deck)

    st.progress(index / total)
    st.caption(f"Question {index + 1} of {total}")
    st.markdown(
        f"<p style='font-size:1.4rem; line-height:1.45; margin-top:0.6rem;'>"
        f"{html.escape(card['question'])}</p>",
        unsafe_allow_html=True,
    )

    true_col, false_col = st.columns(2)
    with true_col:
        if st.button("True", type="primary", use_container_width=True):
            record_answer(True)
            st.rerun()
    with false_col:
        if st.button("False", use_container_width=True):
            record_answer(False)
            st.rerun()

    st.divider()
    if st.button("Start over"):
        st.session_state.phase = "setup"
        st.rerun()


def render_feedback() -> None:
    deck = st.session_state.deck
    card = deck[st.session_state.index]
    right = st.session_state.last_right
    said = "True" if st.session_state.last_choice else "False"
    answer = "True" if card["answer"] else "False"

    paint(COLOUR_CORRECT if right else COLOUR_INCORRECT)

    st.title("Correct." if right else "Wrong.")
    st.markdown(
        f"<p style='font-size:1.15rem; line-height:1.45;'>"
        f"{html.escape(card['question'])}</p>",
        unsafe_allow_html=True,
    )
    st.write(f"You said **{said}**. The statement is **{answer}**.")

    # Plenty of rows have a verdict and no extra note. Show the note
    # whenever the sheet actually has one.
    if card["explanation"]:
        st.markdown("**Explanation**")
        st.write(card["explanation"])

    last = st.session_state.index + 1 >= len(deck)
    label = "See the score" if last else "Next question"
    if st.button(label, type="primary"):
        advance()
        st.rerun()


def render_results() -> None:
    total = len(st.session_state.deck)
    score = st.session_state.correct
    percent = round(100 * score / total) if total else 0

    if percent >= 90:
        show_image(WELLDONE_IMAGE)
        st.title("Kevin is proud!!!")
    elif percent >= 60:
        show_image(PASS_IMAGE)
        st.title("Passed. Goodbye Kevin!")
    else:
        show_image(FAIL_IMAGE)
        st.title("Kevin will see you next semester...")
    st.markdown(
        f"<p style='font-size:2rem; margin-bottom:0.2rem;'>"
        f"{score} / {total}</p>",
        unsafe_allow_html=True,
    )
    st.write(f"{percent} percent correct.")

    if st.button("Try again", type="primary"):
        st.session_state.phase = "setup"
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="True or false", page_icon="§", layout="centered")

    if "bank" not in st.session_state:
        st.session_state.bank = load_bank(CSV_PATH)
        st.session_state.phase = "setup"

    phase = st.session_state.phase
    if phase == "setup":
        render_setup(len(st.session_state.bank))
    elif phase == "question":
        render_question()
    elif phase == "feedback":
        render_feedback()
    else:
        render_results()


if __name__ == "__main__":
    main()
