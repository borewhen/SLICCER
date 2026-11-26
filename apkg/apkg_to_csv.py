#!/usr/bin/env python3
"""Convert Anki .apkg packages into CSV files.

An .apkg is a zip archive. Current Anki writes the collection as
collection.anki21b (zstd-compressed SQLite). Older packages use
collection.anki21 or collection.anki2. Note fields are packed into one
string, separated by the ASCII unit separator (0x1F).

Each note becomes one CSV row. Scheduling data (ease, intervals, review
history) is left out; this is the card text, not the review log.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

# Anki packs every field of a note into notes.flds, split by this byte.
FIELD_SEPARATOR = "\x1f"

# Newest export first. collection.anki2 in a modern package is often only
# a small compatibility stub, so it must not win when anki21b is present.
COLLECTION_CANDIDATES = (
    "collection.anki21b",
    "collection.anki21",
    "collection.anki2",
)


def decompress_zstd(data: bytes) -> bytes:
    """Inflate an Anki zstd blob. Uses the zstandard module, then the zstd CLI."""
    try:
        import zstandard as zstd
    except ImportError:
        zstd = None

    if zstd is not None:
        reader = zstd.ZstdDecompressor().stream_reader(io.BytesIO(data))
        try:
            return reader.read()
        finally:
            reader.close()

    import subprocess

    result = subprocess.run(
        ["zstd", "-d", "-c"],
        input=data,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            "Could not decompress collection.anki21b. "
            "Install the zstandard package (`pip install zstandard`) "
            f"or the zstd command-line tool. {detail}"
        )
    return result.stdout


def extract_collection(apkg_path: Path, dest: Path) -> Path:
    """Pull the collection database out of an .apkg into dest."""
    with zipfile.ZipFile(apkg_path) as archive:
        names = set(archive.namelist())
        chosen = next((name for name in COLLECTION_CANDIDATES if name in names), None)
        if chosen is None:
            found = ", ".join(sorted(names)) or "(empty archive)"
            raise RuntimeError(f"{apkg_path.name} has no Anki collection. Found: {found}")

        payload = archive.read(chosen)

    if chosen.endswith("anki21b"):
        payload = decompress_zstd(payload)
        out = dest / "collection.anki21"
    else:
        out = dest / chosen

    if not payload.startswith(b"SQLite format 3\x00"):
        raise RuntimeError(f"{apkg_path.name}: {chosen} is not a SQLite database after unpacking")

    out.write_bytes(payload)
    return out


def _table_names(con: sqlite3.Connection) -> set[str]:
    return {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _legacy_models(con: sqlite3.Connection) -> dict:
    row = con.execute("SELECT models FROM col").fetchone()
    if not row or not row[0]:
        return {}
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return {}


def _legacy_decks(con: sqlite3.Connection) -> dict:
    row = con.execute("SELECT decks FROM col").fetchone()
    if not row or not row[0]:
        return {}
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return {}


def notetype_name(con: sqlite3.Connection, tables: set[str], mid: int, models: dict) -> str:
    if "notetypes" in tables:
        row = con.execute("SELECT name FROM notetypes WHERE id = ?", (mid,)).fetchone()
        if row:
            return row[0]
    model = models.get(str(mid))
    if model:
        return model.get("name") or str(mid)
    return str(mid)


def field_names_for(con: sqlite3.Connection, tables: set[str], mid: int, models: dict) -> list[str]:
    if "fields" in tables:
        rows = con.execute(
            "SELECT name FROM fields WHERE ntid = ? ORDER BY ord",
            (mid,),
        ).fetchall()
        if rows:
            return [row[0] for row in rows]
    model = models.get(str(mid))
    if model and model.get("flds"):
        fields = sorted(model["flds"], key=lambda field: field.get("ord", 0))
        return [field.get("name") or f"Field {index + 1}" for index, field in enumerate(fields)]
    return []


def deck_names_for_note(
    con: sqlite3.Connection,
    tables: set[str],
    note_id: int,
    decks: dict,
) -> str:
    card_decks = con.execute("SELECT DISTINCT did FROM cards WHERE nid = ?", (note_id,)).fetchall()
    names: list[str] = []
    for (did,) in card_decks:
        name = None
        if "decks" in tables:
            row = con.execute("SELECT name FROM decks WHERE id = ?", (did,)).fetchone()
            if row:
                name = row[0]
        if name is None:
            legacy = decks.get(str(did))
            if legacy:
                name = legacy.get("name")
        names.append(name or str(did))
    # Stable, de-duplicated, original order.
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return " | ".join(seen)


def html_to_text(value: str) -> str:
    """Turn Anki HTML into readable plain text, keeping line breaks."""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(div|p|li|tr|h[1-6]|blockquote)>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")

    lines: list[str] = []
    for line in text.split("\n"):
        collapsed = re.sub(r"[ \t]+", " ", line).strip()
        if collapsed or (lines and lines[-1]):
            lines.append(collapsed)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()


def load_notes(db_path: Path, keep_html: bool) -> tuple[list[str], list[dict[str, str]]]:
    """Return (column names, rows) for every note in the collection."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = _table_names(con)
        models = _legacy_models(con) if "notetypes" not in tables or "fields" not in tables else {}
        # Legacy deck names still matter if the decks table is absent.
        decks = _legacy_decks(con) if "decks" not in tables else {}

        notes = con.execute(
            "SELECT id, guid, mid, tags, flds FROM notes ORDER BY id"
        ).fetchall()

        # Column order follows the first note type we meet, then any later extras.
        field_columns: list[str] = []
        rows: list[dict[str, str]] = []

        for note_id, guid, mid, tags, flds in notes:
            names = field_names_for(con, tables, mid, models)
            parts = (flds or "").split(FIELD_SEPARATOR)
            if len(names) < len(parts):
                names = names + [f"Field {index + 1}" for index in range(len(names), len(parts))]

            for name in names:
                if name not in field_columns:
                    field_columns.append(name)

            values = []
            for part in parts:
                text = part if keep_html else html_to_text(part)
                values.append(text)

            tag_text = " ".join((tags or "").split())
            row = {
                "deck": deck_names_for_note(con, tables, note_id, decks),
                "note_type": notetype_name(con, tables, mid, models),
                "tags": tag_text,
                "guid": guid or "",
            }
            for index, name in enumerate(names):
                row[name] = values[index] if index < len(values) else ""
            rows.append(row)
    finally:
        con.close()

    columns = ["deck", "note_type", "tags", "guid", *field_columns]
    return columns, rows


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel opens the file as Unicode instead of misreading it.
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def iter_apkg_paths(inputs: list[Path]) -> list[Path]:
    found: list[Path] = []
    for item in inputs:
        if item.is_dir():
            found.extend(sorted(path for path in item.rglob("*.apkg") if path.is_file()))
        elif item.is_file():
            found.append(item)
        else:
            raise FileNotFoundError(f"No such file or directory: {item}")
    # De-duplicate while keeping order.
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in found:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def convert_one(apkg_path: Path, output_dir: Path, keep_html: bool) -> tuple[Path, int]:
    with tempfile.TemporaryDirectory(prefix="apkg-") as temp_name:
        db_path = extract_collection(apkg_path, Path(temp_name))
        columns, rows = load_notes(db_path, keep_html=keep_html)

    dest = output_dir / f"{apkg_path.stem}.csv"
    write_csv(dest, columns, rows)
    return dest, len(rows)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Anki .apkg packages to CSV (one row per note).",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Apkg files or directories to scan. Defaults to ./apkg.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("csv"),
        help="Directory to write CSV files into (default: ./csv).",
    )
    parser.add_argument(
        "--keep-html",
        action="store_true",
        help="Keep Anki HTML in the fields. By default tags are stripped and line breaks kept.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    inputs = args.inputs or [Path("apkg")]

    try:
        packages = iter_apkg_paths(inputs)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not packages:
        print(f"No .apkg files found in: {', '.join(str(item) for item in inputs)}", file=sys.stderr)
        return 1

    failures = 0
    for package in packages:
        try:
            dest, count = convert_one(package, args.output, keep_html=args.keep_html)
        except (RuntimeError, zipfile.BadZipFile, sqlite3.DatabaseError, OSError) as exc:
            failures += 1
            print(f"Failed  {package}: {exc}", file=sys.stderr)
            continue
        print(f"Wrote   {dest}  ({count} notes)")

    if failures:
        print(f"{failures} package(s) failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
