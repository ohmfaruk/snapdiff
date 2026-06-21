# snapdiff

[![Tests](https://github.com/ohmfaruk/snapdiff/actions/workflows/tests.yml/badge.svg)](https://github.com/ohmfaruk/snapdiff/actions/workflows/tests.yml)

Snapshot and diff any directory tree over time — no git repo required.

`snapdiff` solves a simple problem: git only tracks changes *inside* a repo, but you constantly need to know "what changed in this folder since last week" for things that aren't (and shouldn't be) version controlled — config directories, Dropbox syncs, build output, scraped datasets, client deliverables, downloads folders.

Take a snapshot. Keep working. Compare later. See exactly what was added, removed, or modified.

## Install

```bash
git clone https://github.com/ohmfaruk/snapdiff.git
cd snapdiff
pip install -e .
```

## Usage

**Take a snapshot:**

```bash
snapdiff snap ~/Documents/configs --name before-cleanup
```

**Do your thing.** Edit files, delete files, add files — whatever.

**Compare against the snapshot:**

```bash
snapdiff compare ~/Documents/configs before-cleanup
```

```
Comparing '~/Documents/configs' against snapshot 'before-cleanup' (taken 2026-06-21T19:17:35)

  + added     new-config.yaml
  - removed   old-config.yaml
  ~ modified  settings.json

Summary: 1 added, 1 removed, 1 modified.
```

**Renamed files are detected automatically** — if a file's content hash matches an old hash under a different path, it's reported as a rename, not a separate add+delete:

```
> renamed   old_name.txt -> new_name.txt
```

**Export the diff as Markdown** — handy for pasting into a PR description, daily log, or sharing with a team:

```bash
snapdiff compare ~/Documents/configs before-cleanup --markdown report.md
```

**List all saved snapshots:**

```bash
snapdiff list
```

## How it works

Each snapshot walks the target directory and records a SHA-256 hash, size, and modification time for every file, keyed by its relative path. Snapshots are stored as portable JSON in `~/.snapdiff/`. Comparing re-walks the live directory and diffs the current file set against the saved one — additions, deletions, and content changes are all detected via hash comparison, so renames/edits are caught even if mtime is unreliable (e.g. after a file copy).

## Options

| Flag | Description |
|---|---|
| `--name` | Label for the snapshot (used in `snap`) |
| `--ignore` | Additional filenames/dirs to exclude, beyond the defaults (`.git`, `__pycache__`, `node_modules`, `.DS_Store`, `Thumbs.db`) |

## Why not just use git?

Git requires a repo, tracks history you may not want, and isn't designed for ad-hoc "point A vs point B" comparisons of arbitrary folders. `snapdiff` is zero-config, dependency-free, and disposable — snapshot anything, anytime, no setup.

## License

MIT
