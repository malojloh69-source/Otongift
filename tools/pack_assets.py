#!/usr/bin/env python3
"""Combine model and symbol media into GitHub-friendly ZIP parts.

Use --remove after the ZIPs pass CRC checks; --extract restores editable files.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
PACKS = PUBLIC / "asset-packs"
MAX_PART = 40 * 1024 * 1024
sys.path.insert(0, str(ROOT))
from asset_store import AssetStore  # noqa: E402


def extract():
    store = AssetStore(PUBLIC)
    if not store.members:
        raise SystemExit("No asset packs to extract")
    for relative in sorted(store.members):
        target = PUBLIC / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(store.read(relative))
    print(f"Extracted {len(store.members)} assets for editing")


def pack(remove=False):
    files = sorted(p for folder in (PUBLIC / "assets/models", PUBLIC / "assets/symbols")
                   for p in folder.rglob("*") if p.is_file())
    if not files:
        raise SystemExit("No loose model/symbol files to pack; use --extract first")

    staging = PUBLIC / ".asset-packs-staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    records = []
    archive = None
    count = size = part = 0

    def finish():
        nonlocal archive, count, size, part
        if archive is None:
            return
        archive.close()
        name = f"pack-{part:03}.zip"
        path = staging / name
        if path.stat().st_size > 45 * 1024 * 1024:
            raise RuntimeError(f"Asset pack is too large: {name}")
        with ZipFile(path) as check:
            if check.testzip() is not None:
                raise RuntimeError(f"CRC check failed: {name}")
        records.append({"name": name, "files": count, "bytes": path.stat().st_size})
        part += 1
        count = size = 0
        archive = None

    for source in files:
        relative = source.relative_to(PUBLIC).as_posix()
        estimated = source.stat().st_size + 2 * len(relative) + 256
        if archive and size + estimated > MAX_PART:
            finish()
        if archive is None:
            archive = ZipFile(staging / f"pack-{part:03}.zip", "w", compression=ZIP_DEFLATED, compresslevel=6)
        info = ZipInfo(relative, date_time=(2024, 1, 1, 0, 0, 0))
        info.compress_type = ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        archive.writestr(info, source.read_bytes())
        size += estimated
        count += 1
    finish()
    (staging / "manifest.json").write_text(json.dumps({"version": 1, "total_files": len(files), "packs": records}, indent=2) + "\n")
    for item in records:
        path = staging / item["name"]
        if path.stat().st_size != item["bytes"]:
            raise RuntimeError(f"Asset pack changed during build: {path}")
        with ZipFile(path) as check:
            if len(check.namelist()) != item["files"] or check.testzip() is not None:
                raise RuntimeError(f"Asset pack failed final verification: {path}")
    if PACKS.exists():
        shutil.rmtree(PACKS)
    staging.rename(PACKS)
    AssetStore(PUBLIC)  # Ensure every archive and member is indexed before removing source files.
    if remove:
        for source in files:
            source.unlink()
        for folder in (PUBLIC / "assets/models", PUBLIC / "assets/symbols"):
            for directory in sorted(folder.rglob("*"), reverse=True):
                if directory.is_dir():
                    directory.rmdir()
            folder.rmdir()
    print(f"Packed {len(files)} assets into {len(records)} parts ({sum(p['bytes'] for p in records):,} bytes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--remove", action="store_true", help="Remove loose model/symbol files after CRC verification")
    mode.add_argument("--extract", action="store_true", help="Restore loose files for editing")
    args = parser.parse_args()
    extract() if args.extract else pack(args.remove)
