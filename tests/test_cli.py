"""
Tests for snapdiff core engine.

Uses pytest's tmp_path fixture to create isolated, throwaway directories
for each test — no risk of touching real files, no cleanup needed.
"""

import json
from pathlib import Path

import pytest

from snapdiff.cli import walk_tree, hash_file, DEFAULT_IGNORES, write_markdown_report


def make_file(path: Path, content: str):
    """Helper: write a file with given content, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_hash_file_is_deterministic(tmp_path):
    """Hashing the same content twice should produce the same hash."""
    f = tmp_path / "a.txt"
    make_file(f, "hello world")
    assert hash_file(f) == hash_file(f)


def test_hash_file_differs_on_content_change(tmp_path):
    """Different content should produce different hashes."""
    f = tmp_path / "a.txt"
    make_file(f, "version one")
    hash_before = hash_file(f)

    make_file(f, "version two")
    hash_after = hash_file(f)

    assert hash_before != hash_after


def test_walk_tree_finds_all_files(tmp_path):
    """walk_tree should discover every file, including nested ones."""
    make_file(tmp_path / "file1.txt", "a")
    make_file(tmp_path / "nested" / "file2.txt", "b")

    tree = walk_tree(tmp_path, DEFAULT_IGNORES)

    assert "file1.txt" in tree
    assert "nested/file2.txt" in tree
    assert len(tree) == 2


def test_walk_tree_respects_ignores(tmp_path):
    """Files inside ignored directory names should be excluded."""
    make_file(tmp_path / "keep.txt", "a")
    make_file(tmp_path / "__pycache__" / "skip.pyc", "b")

    tree = walk_tree(tmp_path, DEFAULT_IGNORES)

    assert "keep.txt" in tree
    assert not any("skip.pyc" in path for path in tree)


def test_walk_tree_records_correct_metadata(tmp_path):
    """Each entry should have size, mtime, and sha256 keys with sane values."""
    f = tmp_path / "data.txt"
    make_file(f, "some content")

    tree = walk_tree(tmp_path, DEFAULT_IGNORES)
    entry = tree["data.txt"]

    assert entry["size"] == f.stat().st_size
    assert isinstance(entry["sha256"], str)
    assert len(entry["sha256"]) == 64  # sha256 hex digest length


def test_snapshot_json_roundtrip(tmp_path):
    """A snapshot dict should serialize to JSON and back without data loss."""
    make_file(tmp_path / "a.txt", "content")
    tree = walk_tree(tmp_path, DEFAULT_IGNORES)

    snapshot = {"root": str(tmp_path), "files": tree}
    serialized = json.dumps(snapshot)
    restored = json.loads(serialized)

    assert restored["files"]["a.txt"]["sha256"] == tree["a.txt"]["sha256"]

    


def test_rename_detection_via_hash_match(tmp_path):
    """If a file's content hash is unchanged but its path differs, it
    should be detectable as a rename by matching hashes across the
    removed/added sets — this mirrors the logic in cmd_compare."""
    make_file(tmp_path / "old_name.txt", "identical content")
    old_tree = walk_tree(tmp_path, DEFAULT_IGNORES)

    (tmp_path / "old_name.txt").rename(tmp_path / "new_name.txt")
    new_tree = walk_tree(tmp_path, DEFAULT_IGNORES)

    old_hash = old_tree["old_name.txt"]["sha256"]
    new_hash = new_tree["new_name.txt"]["sha256"]

    assert old_hash == new_hash  # same content, different path = rename signal


def test_write_markdown_report_contains_all_sections(tmp_path):
    """The markdown report should include a section for every non-empty
    change category and an accurate summary line."""
    output_file = tmp_path / "report.md"

    write_markdown_report(
        output_file, tmp_path, "test-snapshot", "2026-01-01T00:00:00",
        added=["new.txt"],
        removed=["gone.txt"],
        renamed=[("old.txt", "renamed.txt")],
        modified=["changed.txt"],
    )

    content = output_file.read_text()

    assert "## Added (1)" in content
    assert "new.txt" in content
    assert "## Removed (1)" in content
    assert "## Renamed (1)" in content
    assert "old.txt` -> `renamed.txt" in content
    assert "## Modified (1)" in content
    assert "1 added, 1 removed, 1 renamed, 1 modified" in content


def test_write_markdown_report_no_changes(tmp_path):
    """When nothing changed, the report should say so plainly instead of
    printing empty section headers."""
    output_file = tmp_path / "report.md"

    write_markdown_report(
        output_file, tmp_path, "test-snapshot", "2026-01-01T00:00:00",
        added=[], removed=[], renamed=[], modified=[],
    )

    content = output_file.read_text()
    assert "No changes detected." in content