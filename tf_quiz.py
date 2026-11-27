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
from streamlit_theme import st_theme


# Drop a file path or a URL into any of these. Empty means no picture.
CORRECT_IMAGE = "img/kevsmile.png"
INCORRECT_IMAGE = "img/sadcat.jpeg"
SON_IMAGE = "img/menon_son.png"
FAIL_IMAGE = "img/kena.jpeg"
PASS_IMAGE = "img/kevsmile.png"
WELLDONE_IMAGE = "img/kevproud.png"
SUPER_IMAGE = "img/manifest.jpeg"
SON_SOUND = "sound/spongebob_cooked.mp3"
FAIL_SOUND = "sound/spongebob_clown.mp3"
PASS_SOUND = "sound/majulah.mp3"
WELLDONE_SOUND = "sound/majulah.mp3"
SUPER_SOUND = "sound/kanye.mp3"



TF_CSV_PATH = Path(__file__).resolve().parent / "csv" / "tf_questions.csv"
FC_CSV_PATH = Path(__file__).resolve().parent / "csv" / "flashcards.csv"

COLOURS = {
    "light": {
        "correct": "#DCE8C5",
        "correct_button": "#B8CB91",
        "correct_hover": "#A4BA78",
        "incorrect": "#F5D0CD",
        "incorrect_button": "#E5ABA6",
        "incorrect_hover": "#D9958F",
        "text": "#262730",
    },
    "dark": {
        "correct": "#4C5D24",
        "correct_button": "#354218",
        "correct_hover": "#283310",
        "incorrect": "#621E1A",
        "incorrect_button": "#481310",
        "incorrect_hover": "#350D0B",
        "text": "#FAFAFA",
    },
}


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
                    "type": "tf",
                    "number": (row.get("S/N") or "").strip(),
                    "question": question,
                    "answer": verdict == "T",
                    "explanation": (row.get("Explanation") or "").strip(),
                }
            )
    if not bank:
        raise SystemExit(f"No true/false questions found in {path}")
    return bank


def load_flashcards(path: Path) -> list[dict]:
    """Read and validate flashcards from the CSV."""
    bank: list[dict] = []

    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            chapter = (row.get("chap") or "").strip()
            front = (row.get("Front") or "").strip()
            back = (row.get("Back") or "").strip()

            try:
                chap_no = int(row.get("chap_no") or "")
            except ValueError:
                continue

            if not chapter or not front or not back:
                continue

            bank.append(
                {
                    "type": "fc",
                    "chap_no": chap_no,
                    "chap": chapter,
                    "question": front,
                    "answer": back,
                }
            )

    if not bank:
        raise ValueError(f"No valid flashcards found in {path}")

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


def play_sound(reference: str) -> None:
    """Play the soundtrack associated with a quiz result."""
    reference = (reference or "").strip()

    if not reference:
        return

    if "://" in reference:
        st.audio(
            reference,
            format="audio/mpeg",
            autoplay=True,
            loop=False,
        )
        return

    path = Path(reference)

    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path

    if path.is_file():
        st.audio(
            str(path),
            format="audio/mpeg",
            autoplay=True,
            loop=False,
        )


def fetch_theme() -> None:
    """Retrieve and store the current browser theme."""
    theme = st_theme(key="quiz_theme")

    if theme and theme.get("base") in COLOURS:
        st.session_state.theme_base = theme["base"]


def style_buttons() -> None:
    """Apply consistent, theme-aware button styling."""
    base = st.session_state.get("theme_base", "light")

    if base == "dark":
        button = "#262730"
        hover = "#383B46"
        text = "#FAFAFA"
    else:
        button = "#F0F2F6"
        hover = "#DFE3EB"
        text = "#262730"

    st.markdown(
        f"""
        <style>
        .stButton button:not(:disabled) {{
            background-color: {button};
            color: {text};
            border: 1px solid transparent;
            border-radius: 8px;
            font-weight: 600;
            transition: background-color 0.15s ease,
                        transform 0.15s ease;
        }}

        .stButton button:not(:disabled) p {{
            color: {text};
            font-weight: 600;
        }}

        .stButton button:not(:disabled):hover {{
            background-color: {hover};
            color: {text};
            border-color: transparent;
            transform: translateY(-2px);
        }}

        .stButton button:not(:disabled):active {{
            background-color: {hover};
            color: {text};
            border-color: transparent;
            transform: translateY(0);
        }}

        .stButton button:focus:not(:focus-visible) {{
            box-shadow: none;
            color: {text};
        }}

        .stButton button:focus-visible {{
            outline: 2px solid {text};
            outline-offset: 3px;
            box-shadow: none;
        }}

        .stButton button:disabled {{
            opacity: 0.45;
            transform: none;
            cursor: not-allowed;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def paint(right: bool) -> None:
    """Apply feedback-specific background and button colours."""
    base = st.session_state.get("theme_base", "light")
    palette = COLOURS[base]
    verdict = "correct" if right else "incorrect"

    colour = palette[verdict]
    button = palette[f"{verdict}_button"]
    hover = palette[f"{verdict}_hover"]
    text = palette["text"]

    st.markdown(
        f"""
        <style>
        .stApp,
        [data-testid="stHeader"],
        [data-testid="stToolbar"] {{
            background-color: {colour};
        }}

        .stButton button:not(:disabled) {{
            background-color: {button} !important;
            color: {text};
        }}

        .stButton button p {{
            color: {text};
        }}

        .stButton button:not(:disabled):hover {{
            background-color: {hover} !important;
            color: {text};
            border-color: transparent;
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
    """Evaluate an answer or record a self-assessment."""
    if st.session_state.phase != "question":
        return

    card = st.session_state.deck[st.session_state.index]

    if card["type"] == "tf":
        right = choice == card["answer"]

    elif card["type"] == "fc":
        right = choice

    else:
        raise ValueError(f"Unknown question type: {card['type']}")

    st.session_state.last_choice = choice
    st.session_state.last_right = right

    if right:
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
    # fetch_theme()
    st.title("Plate-SLICcers")
    st.write(
        f"somebody get these BEGGARS outta here"
    )
    st.image("img/beggars.png", width=200)

    tab_tf, tab_fc, tab_allqns = st.tabs(["True/False", "Flashcards", "...or both?"])

    with tab_tf:
        count = st.number_input(
            "How many questions do we wanna try? We have 190 true/false questions in the bank.",
            min_value=1,
            max_value=total,
            value=min(10, total),
            step=1,
        )

        short, whole = st.columns(2)
        with short:
            if st.button("Start", use_container_width=True):
                fresh_sitting(st.session_state.bank, int(count))
                st.rerun()
        with whole:
            if st.button("Take the whole quiz", use_container_width=True):
                fresh_sitting(st.session_state.bank, total)
                st.rerun()
    with tab_fc:
        render_fc_setup()
    with tab_allqns:
        render_mixed_setup()


def toggle_all_chapters(chapter_numbers: list[int]) -> None:
    """Synchronise all chapter checkboxes with Select all."""
    selected = st.session_state.fc_select_all

    for number in chapter_numbers:
        st.session_state[f"fc_chapter_{number}"] = selected


def sync_chapter_selection(chapter_numbers: list[int]) -> None:
    """Update Select all when individual chapters are toggled."""
    st.session_state.fc_select_all = all(
        st.session_state.get(f"fc_chapter_{number}", False)
        for number in chapter_numbers
    )


def render_fc_setup() -> None:
    """Configure a flashcard sitting by chapter and question count."""
    bank = st.session_state.fc_bank

    chapters = {
        card["chap_no"]: card["chap"]
        for card in bank
    }

    chapter_numbers = sorted(chapters)

    chapter_counts = {
        number: 0 for number in chapter_numbers
    }

    for card in bank:
        chapter_counts[card["chap_no"]] += 1

    st.subheader("Which chapters do we wanna revise?")

    st.checkbox(
        "Select all chapters",
        key="fc_select_all",
        on_change=toggle_all_chapters,
        args=(chapter_numbers,),
    )

    st.divider()

    # Render chapters in numerical order.
    selected = []

    for number in chapter_numbers:
        label = (
            f"{number}. {chapters[number]} "
            f"({chapter_counts[number]} cards)"
        )

        if st.checkbox(
            label,
            key=f"fc_chapter_{number}",
            on_change=sync_chapter_selection,
            args=(chapter_numbers,),
        ):
            selected.append(number)

    # Construct the bank from selected chapters.
    selected_bank = [
        card for card in bank
        if card["chap_no"] in selected
    ]

    total = len(selected_bank)

    st.caption(
        f"{len(selected)} of {len(chapter_numbers)} chapters "
        f"selected · {total} flashcards available"
    )

    st.divider()

    # Preserve the requested count where possible,
    # but ensure it never exceeds the available cards.
    if "fc_count" not in st.session_state:
        st.session_state.fc_count = min(10, max(1, total))

    st.session_state.fc_count = max(
        1,
        min(st.session_state.fc_count, max(1, total)),
    )

    count = st.number_input(
        "How many flashcards do we wanna try?",
        min_value=1,
        max_value=max(1, total),
        step=1,
        key="fc_count",
        disabled=total == 0,
    )

    short, whole = st.columns(2)

    with short:
        if st.button(
            "Start",
            key="fc_start",
            use_container_width=True,
            disabled=total == 0,
        ):
            fresh_sitting(selected_bank, int(count))
            st.rerun()

    with whole:
        if st.button(
            "Take all selected cards",
            key="fc_whole",
            use_container_width=True,
            disabled=total == 0,
        ):
            fresh_sitting(selected_bank, total)
            st.rerun()

    if total == 0:
        st.caption("Select at least one chapter to begin.")


def render_mixed_setup() -> None:
    """Configure a sitting containing both question types."""
    tf_bank = st.session_state.bank
    fc_bank = st.session_state.fc_bank

    combined_bank = tf_bank + fc_bank
    total = len(combined_bank)

    st.markdown(
        "<p style='font-size:0.9rem;'>"
        "All the chapters will be included."
        "</p>",
        unsafe_allow_html=True,
    )

    count = st.number_input(
        f"How many questions do we wanna try? "
        f"We have {total} questions in the combined bank.",
        min_value=1,
        max_value=total,
        value=min(10, total),
        step=1,
        key="mixed_count",
    )

    if st.button(
        "Start",
        key="mixed_start",
        use_container_width=True,
    ):
        fresh_sitting(combined_bank, int(count))
        st.rerun()


def render_tf_question(card: dict) -> None:
    """Render the controls for a true/false question."""
    true_col, false_col = st.columns(2)

    with true_col:
        if st.button("True", use_container_width=True):
            record_answer(True)
            st.rerun()

    with false_col:
        if st.button("False", use_container_width=True):
            record_answer(False)
            st.rerun()

def render_fc_question(card: dict) -> None:
    """Reveal the answer and collect a self-assessment."""
    with st.expander("Reveal answer", expanded=False):
        st.markdown(card["answer"])

    st.write("Have you gotten this down?")

    yes_col, no_col = st.columns(2)

    with yes_col:
        if st.button("Yes", use_container_width=True):
            record_answer(True)
            st.rerun()

    with no_col:
        if st.button("No", use_container_width=True):
            record_answer(False)
            st.rerun()


def render_question() -> None:
    """Render the current question, regardless of its type."""
    deck = st.session_state.deck
    index = st.session_state.index
    card = deck[index]
    total = len(deck)

    st.progress(index / total)
    st.caption(f"Question {index + 1} of {total}")

    if card["type"] == "fc":
        st.caption(
            f"Chapter {card['chap_no']} — {card['chap']}"
        )

    st.markdown(
        f"<p style='font-size:1.4rem; "
        f"line-height:1.45; margin-top:0.6rem;'>"
        f"{html.escape(card['question'])}</p>",
        unsafe_allow_html=True,
    )

    if card["type"] == "tf":
        render_tf_question(card)

    elif card["type"] == "fc":
        render_fc_question(card)

    st.divider()

    if st.button("Start over"):
        st.session_state.phase = "setup"
        st.rerun()


def render_feedback() -> None:
    deck = st.session_state.deck
    card = deck[st.session_state.index]
    right = st.session_state.last_right

    paint(right)

    if card["type"] == "tf":
        st.title("Correct." if right else "Wrong.")

    elif card["type"] == "fc":
        st.title(
            "Got it down." if right else "Rabak. We'll get 'em next time."
        )

        st.caption(
            f"Chapter {card['chap_no']} — {card['chap']}"
        )

    st.markdown(
        f"<p style='font-size:1.15rem; line-height:1.45;'>"
        f"{html.escape(card['question'])}</p>",
        unsafe_allow_html=True,
    )

    if card["type"] == "tf":
        said = (
            "True" if st.session_state.last_choice else "False"
        )
        answer = "True" if card["answer"] else "False"

        st.write(
            f"You said **{said}**. "
            f"The statement is **{answer}**."
        )

        if card["explanation"]:
            st.markdown("**Explanation**")
            st.write(card["explanation"])

    elif card["type"] == "fc":
        st.markdown("**Answer**")
        st.markdown(card["answer"])

    last = st.session_state.index + 1 >= len(deck)
    label = "See the score" if last else "Next question"

    if st.button(label):
        advance()
        st.rerun()


def render_results() -> None:
    total = len(st.session_state.deck)
    score = st.session_state.correct
    percent = round(100 * score / total) if total else 0

    if percent >= 85:
        show_image(SUPER_IMAGE)
        st.title("You got that dog in you.")
        sound = SUPER_SOUND
    elif percent >= 75:
        show_image(WELLDONE_IMAGE)
        st.title("Kevin is proud!")
        sound = WELLDONE_SOUND
    elif percent >= 60:
        show_image(PASS_IMAGE)
        st.title("Passed. Goodbye Kevin!")
        sound = PASS_SOUND
    elif percent >= 30:
        show_image(FAIL_IMAGE)
        st.title("Kevin will see you next semester...")
        sound = FAIL_SOUND
    else:
        show_image(SON_IMAGE)
        st.title("Cooked...")
        sound = SON_SOUND
    st.markdown(
        f"<p style='font-size:2rem; margin-bottom:0.2rem;'>"
        f"{score} / {total}</p>",
        unsafe_allow_html=True,
    )
    st.write(f"{percent} percent correct.")
    # play_sound(sound)

    if st.button("Try again"):
        st.session_state.phase = "setup"
        st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Plate-SLICcers",
        page_icon="§",
        layout="centered",
    )

    fetch_theme()
    style_buttons()

    if "bank" not in st.session_state:
        st.session_state.bank = load_bank(TF_CSV_PATH)
        st.session_state.phase = "setup"

    if "fc_bank" not in st.session_state:
        st.session_state.fc_bank = load_flashcards(FC_CSV_PATH)

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
