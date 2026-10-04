#!/usr/bin/env python3
"""Validate Mini App media without extracting the packed gift collections."""

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
sys.path.insert(0, str(ROOT))
from asset_store import AssetStore


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "img") and attrs.get("src"):
            self.paths.add(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.paths.add(attrs["href"])


def check():
    store = AssetStore(PUBLIC)
    resources = Resources()
    resources.feed((PUBLIC / "index.html").read_text())
    paths = resources.paths

    def collect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("image", "animation") and isinstance(child, str):
                    paths.add(re.sub(r"\.(tgs|json)$", ".asset.js", child) if key == "animation" else child)
                else:
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    catalog = json.loads((PUBLIC / "catalog.json").read_text())
    collect(catalog)
    paths.update(catalog.get("currency_icons", {}).values())
    for sheet in ("style.css", "theme.css", "glass.css"):
        paths.update(re.findall(r"url\(['\"]?([^)'\"]+)", (PUBLIC / sheet).read_text()))
    missing = []
    for path in sorted(paths):
        if path.startswith(("data:", "https:", "http:", "#")):
            continue
        relative = path.removeprefix("./").removeprefix("/")
        loose = PUBLIC / relative
        archive = store.members.get(relative)
        if not ((loose.is_file() and loose.stat().st_size) or (archive and archive.getinfo(relative).file_size)):
            missing.append(relative)
    if missing:
        raise SystemExit("Missing or empty media: " + ", ".join(missing))
    print(f"Checked {len(paths)} resource references; packed media stays in its archives")


if __name__ == "__main__":
    check()
