"""Read Mini App media from loose files or the checked-in asset packs."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


class AssetStore:
    def __init__(self, public: Path):
        self.public = Path(public).resolve()
        self.members: dict[str, ZipFile] = {}
        packs = self.public / "asset-packs"
        manifest_path = packs / "manifest.json"
        if not manifest_path.is_file():
            if packs.exists() and list(packs.glob("*.zip")):
                raise RuntimeError("Asset packs exist without a manifest")
            return

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("version") != 1 or not manifest.get("packs"):
            raise RuntimeError("Invalid asset-pack manifest")
        for pack in manifest["packs"]:
            name = pack["name"]
            if not re.fullmatch(r"pack-\d{3}\.zip", name):
                raise RuntimeError("Invalid asset-pack filename")
            archive = ZipFile(packs / name)
            names = archive.namelist()
            if len(names) != pack["files"]:
                raise RuntimeError(f"Incomplete asset pack: {name}")
            for member in names:
                self._safe_name(member)
                if not member.startswith(("assets/models/", "assets/symbols/")) or member in self.members:
                    raise RuntimeError(f"Unexpected or duplicate packed asset: {member}")
                self.members[member] = archive
        if len(self.members) != manifest["total_files"]:
            raise RuntimeError("Incomplete asset-pack manifest")

    @staticmethod
    def _safe_name(relative: str) -> None:
        path = PurePosixPath(relative)
        if not relative or relative.startswith("/") or "\\" in relative or any(part in ("", ".", "..") for part in relative.split("/")) or path.is_absolute():
            raise FileNotFoundError(relative)

    def read(self, relative: str) -> bytes:
        self._safe_name(relative)
        loose = (self.public / relative).resolve()
        if not loose.is_relative_to(self.public):
            raise FileNotFoundError(relative)
        if loose.is_file():
            return loose.read_bytes()
        archive = self.members.get(relative)
        if archive is None:
            raise FileNotFoundError(relative)
        return archive.read(relative)

    def text(self, relative: str) -> str:
        return self.read(relative).decode("utf-8")
