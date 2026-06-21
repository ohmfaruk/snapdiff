"""
Tests for snapdiff core engine.

Uses pytest's tmp_path fixture to create isolated, throwaway directories
for each test — no risk of touching real files, no cleanup needed.
"""

import json
from pathlib import Path

import pytest

from snapdiff.cli import walk_tree, hash_file, DEFAULT_IGNORES


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