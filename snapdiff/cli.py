"""
snapdiff — snapshot and diff any directory tree over time.

Core concept:
  - A "snapshot" is a JSON record mapping relative file paths to
    (size, mtime, sha256) metadata for every file under a root directory.
  - "compare" re-walks the directory and diffs the live state against
    a saved snapshot, classifying each path as added / removed / modified.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime

# Where snapshots live: ~/.snapdiff/<name>.json
SNAPSHOT_DIR = Path.home() / ".snapdiff"

# Files/dirs we skip by default — noisy, non-meaningful, or OS cruft
DEFAULT_IGNORES = {".DS_Store", "__pycache__", "node_modules", ".git", "Thumbs.db"}


def hash_file(path: Path, chunk_size: int = 65536) -> str:
    """Compute sha256 of a file's contents, streaming in chunks to avoid
    loading huge files entirely into memory."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def walk_tree(root: Path, ignore_patterns: set) -> dict:
    """Walk every file under root and build a dict of:
       relative_path -> {size, mtime, sha256}
    Skips anything matching ignore_patterns (by name, anywhere in the tree).
    """
    root = root.resolve()
    tree = {}

    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in ignore_patterns for part in path.parts):
            continue

        rel_path = str(path.relative_to(root)).replace("\\", "/")
        stat = path.stat()
        tree[rel_path] = {
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "sha256": hash_file(path),
        }

    return tree


def cmd_snap(args):
    """Take a snapshot of a directory and save it as <name>.json"""
    root = Path(args.directory)
    if not root.is_dir():
        print(f"Error: '{root}' is not a valid directory.")
        sys.exit(1)

    ignore_patterns = DEFAULT_IGNORES | set(args.ignore or [])
    tree = walk_tree(root, ignore_patterns)

    SNAPSHOT_DIR.mkdir(exist_ok=True)
    snapshot = {
        "root": str(root.resolve()),
        "created_at": datetime.now().isoformat(),
        "file_count": len(tree),
        "files": tree,
    }

    out_path = SNAPSHOT_DIR / f"{args.name}.json"
    with open(out_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Snapshot '{args.name}' saved — {len(tree)} files tracked.")
    print(f"  -> {out_path}")

def write_markdown_report(output_path, root, snapshot_name, created_at,
                           added, removed, renamed, modified):
    """Write the diff result as a clean Markdown report — handy for pasting
    into a PR description, daily log, or sharing with a team."""
    lines = [
        f"# Diff Report: `{root}`",
        "",
        f"**Snapshot:** `{snapshot_name}` (taken {created_at})",
        f"**Generated:** {datetime.now().isoformat()}",
        "",
    ]

    if not (added or removed or renamed or modified):
        lines.append("No changes detected.")
    else:
        if added:
            lines.append(f"## Added ({len(added)})")
            lines.extend(f"- `{path}`" for path in added)
            lines.append("")
        if removed:
            lines.append(f"## Removed ({len(removed)})")
            lines.extend(f"- `{path}`" for path in removed)
            lines.append("")
        if renamed:
            lines.append(f"## Renamed ({len(renamed)})")
            lines.extend(f"- `{old}` -> `{new}`" for old, new in renamed)
            lines.append("")
        if modified:
            lines.append(f"## Modified ({len(modified)})")
            lines.extend(f"- `{path}`" for path in modified)
            lines.append("")

        lines.append(f"**Summary:** {len(added)} added, {len(removed)} removed, "
                      f"{len(renamed)} renamed, {len(modified)} modified.")

    Path(output_path).write_text("\n".join(lines))


def cmd_compare(args):
    """Compare current directory state against a saved snapshot."""
    snap_path = SNAPSHOT_DIR / f"{args.name}.json"
    if not snap_path.exists():
        print(f"Error: no snapshot named '{args.name}'. Run 'snapdiff list' to see saved snapshots.")
        sys.exit(1)

    with open(snap_path) as f:
        snapshot = json.load(f)

    root = Path(args.directory)
    ignore_patterns = DEFAULT_IGNORES | set(args.ignore or [])
    current = walk_tree(root, ignore_patterns)
    old = snapshot["files"]

    old_paths = set(old.keys())
    new_paths = set(current.keys())

    added = set(new_paths - old_paths)
    removed = set(old_paths - new_paths)
    common = old_paths & new_paths
    modified = sorted(p for p in common if old[p]["sha256"] != current[p]["sha256"])

    # Rename detection: if a "removed" file's hash matches an "added" file's
    # hash, it's the same content that moved/was renamed, not a separate
    # delete + create. Pull matching pairs out of added/removed into renamed.
    old_hash_to_path = {old[p]["sha256"]: p for p in removed}
    renamed = []
    for new_path in list(added):
        file_hash = current[new_path]["sha256"]
        if file_hash in old_hash_to_path:
            old_path = old_hash_to_path[file_hash]
            renamed.append((old_path, new_path))
            added.discard(new_path)
            removed.discard(old_path)

    added = sorted(added)
    removed = sorted(removed)
    renamed = sorted(renamed)

    # ANSI colors — work in most modern terminals including Windows Terminal/PowerShell 7+
    GREEN, RED, YELLOW, BLUE, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[94m", "\033[0m"

    if args.markdown:
        write_markdown_report(args.markdown, root, args.name, snapshot["created_at"],
                               added, removed, renamed, modified)
        print(f"Markdown report written to {args.markdown}")
        return

    print(f"\nComparing '{root}' against snapshot '{args.name}' "
          f"(taken {snapshot['created_at']})\n")

    if not (added or removed or modified or renamed):
        print("No changes detected.")
        return

    for path in added:
        print(f"  {GREEN}+ added     {RESET}{path}")
    for path in removed:
        print(f"  {RED}- removed   {RESET}{path}")
    for old_path, new_path in renamed:
        print(f"  {BLUE}> renamed   {RESET}{old_path} -> {new_path}")
    for path in modified:
        print(f"  {YELLOW}~ modified  {RESET}{path}")

    print(f"\nSummary: {len(added)} added, {len(removed)} removed, "
          f"{len(renamed)} renamed, {len(modified)} modified.")


def cmd_list(args):
    """List all saved snapshots."""
    if not SNAPSHOT_DIR.exists() or not any(SNAPSHOT_DIR.glob("*.json")):
        print("No snapshots saved yet. Run 'snapdiff snap <dir> --name <label>' to create one.")
        return

    print(f"Saved snapshots ({SNAPSHOT_DIR}):\n")
    for snap_file in sorted(SNAPSHOT_DIR.glob("*.json")):
        with open(snap_file) as f:
            data = json.load(f)
        print(f"  {snap_file.stem:20} {data['file_count']:>5} files   "
              f"root={data['root']}   created={data['created_at']}")


def main():
    parser = argparse.ArgumentParser(
        prog="snapdiff",
        description="Snapshot and diff any directory tree over time."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # snap
    snap_parser = subparsers.add_parser("snap", help="Take a snapshot of a directory")
    snap_parser.add_argument("directory", help="Path to the directory to snapshot")
    snap_parser.add_argument("--name", required=True, help="Label for this snapshot")
    snap_parser.add_argument("--ignore", nargs="*", help="Additional names to ignore")
    snap_parser.set_defaults(func=cmd_snap)

    # compare
    compare_parser = subparsers.add_parser("compare", help="Compare a directory against a saved snapshot")
    compare_parser.add_argument("directory", help="Path to the directory to compare")
    compare_parser.add_argument("name", help="Snapshot label to compare against")
    compare_parser.add_argument("--ignore", nargs="*", help="Additional names to ignore")
    compare_parser.add_argument("--markdown", metavar="OUTPUT_PATH",
                                 help="Write the diff as a Markdown report to this file path")
    compare_parser.set_defaults(func=cmd_compare)

    # list
    list_parser = subparsers.add_parser("list", help="List saved snapshots")
    list_parser.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()