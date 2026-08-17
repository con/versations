"""Tests for versations.client.split_to_budget.

Run with `pytest` or directly with `python tests/test_client.py`. Importing
versations.client pulls in markdown/nio, so run this inside the versations env.
"""
from versations.client import split_to_budget, MAX_BODY_BYTES


def _within_budget(chunks, max_bytes):
    return all(len(c.encode()) <= max_bytes for c in chunks)


def test_short_text_returned_unchanged():
    # Anything already under budget is passed through as a single piece.
    assert split_to_budget("hello", max_bytes=100) == ["hello"]


def test_at_budget_boundary_not_split():
    text = "a" * 100
    assert split_to_budget(text, max_bytes=100) == [text]


def test_semicolon_line_splits_and_preserves_content():
    # The failing real-world case: one long line of "; "-joined items.
    line = "; ".join(f"item-{n}" for n in range(200))
    assert len(line.encode()) > 100
    chunks = split_to_budget(line, max_bytes=100)
    assert len(chunks) > 1
    assert _within_budget(chunks, 100)
    # Splitting only drops the separator at chunk boundaries, so rejoining on
    # "; " reconstructs the original exactly.
    assert "; ".join(chunks) == line


def test_newline_splits_and_preserves_content():
    text = "\n".join(f"line number {n}" for n in range(100))
    assert len(text.encode()) > 100
    chunks = split_to_budget(text, max_bytes=100)
    assert len(chunks) > 1
    assert _within_budget(chunks, 100)
    assert "\n".join(chunks) == text


def test_unbreakable_run_hard_split():
    # No newline or "; " to break on: still must get under budget.
    blob = "x" * 350
    chunks = split_to_budget(blob, max_bytes=100)
    assert len(chunks) > 1
    assert _within_budget(chunks, 100)
    assert "".join(chunks) == blob  # hard split loses nothing


def test_heading_plus_long_line_recurses():
    # Mirrors a report section: a heading line then one oversized line, which
    # forces the newline split first, then the "; " split on the big part.
    section = "##### Covered projects\n" + "; ".join(
        f"[repo-{n}](https://example.com/{n})" for n in range(500)
    )
    chunks = split_to_budget(section)  # real MAX_BODY_BYTES
    assert len(chunks) > 1
    assert _within_budget(chunks, MAX_BODY_BYTES)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok: {name}")
    print("all tests passed")
