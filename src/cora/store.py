"""Per-entry JSON storage: one file per entry, in a directory next to the former single-file collection.

    data/records_raw.json            -> data/records_raw/<id>.json
    data/dataset/cora_dataset.jsonl  -> data/dataset/records/<id>.json   (the .jsonl stays as the download)
    data/enrich_cache.json           -> data/enrich_cache/<key>.json     ({"key": ..., "value": ...})
    data/stapfer/cases.json          -> data/stapfer/cases/<id>.json

`_order.json` in each directory keeps the original order. An entry still only in the old combined file is split
out the first time it is read (that is how opening a record on the website splits it); an entry whose combined file
is newer than its own file is refreshed from it, so a regenerated combined file never hides behind stale entries.
`split_all` splits a whole collection at once.
"""
import hashlib
import json
import os
import re
import threading
from collections.abc import MutableMapping
from pathlib import Path

ORDER = "_order.json"


def entry_dir(path: Path) -> Path:
    path = Path(path)
    return path.parent / ("records" if path.name == "cora_dataset.jsonl" else path.stem)


def file_name(key) -> str:
    key = str(key)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", key):
        return key + ".json"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", key).strip("-")[:40] or "entry"
    return f"{slug}-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}.json"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)  # atomic: a reader never sees half a file


def _read_combined(path: Path):
    if path.suffix == ".jsonl":
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return _read(path)


class Entries:
    """A collection of dict entries identified by `key` (default "id")."""

    def __init__(self, path, key: str = "id", directory: Path | None = None):
        self.combined, self.key = Path(path), key
        self.dir = Path(directory) if directory else entry_dir(self.combined)
        self._old, self._old_mtime, self._lock = None, 0.0, threading.Lock()

    def _legacy(self) -> dict:
        """Entries of the combined file (re-read when the file changes)."""
        mtime = self.combined.stat().st_mtime if self.combined.exists() else 0.0
        if self._old is None or mtime != self._old_mtime:
            items = _read_combined(self.combined) if mtime else []
            self._old, self._old_mtime = {str(e[self.key]): e for e in items}, mtime
        return self._old

    def _order(self) -> list[str]:
        p = self.dir / ORDER
        return _read(p) if p.exists() else []

    def get(self, k):
        k, p = str(k), self.dir / file_name(k)
        old = self._legacy()
        if p.exists() and not (k in old and self._old_mtime > p.stat().st_mtime):
            return _read(p)
        e = old.get(k)
        if e is not None:  # split out on first read (or refresh from a newer combined file)
            with self._lock:
                _write(p, e)
                order = self._order()
                if k not in order:
                    _write(self.dir / ORDER, order + [k])
        return e

    def ids(self) -> list[str]:
        ids = list(dict.fromkeys(self._order() + list(self._legacy())))
        if self.dir.exists():  # files written without the manifest
            known = {file_name(k) for k in ids}
            ids += [_read(p)[self.key] for p in sorted(self.dir.glob("*.json")) if p.name != ORDER and p.name not in known]
        return [str(k) for k in ids]

    def all(self) -> list[dict]:
        return [e for k in self.ids() if (e := self.get(k)) is not None]

    def put(self, entry: dict) -> None:
        k = str(entry[self.key])
        with self._lock:
            _write(self.dir / file_name(k), entry)
            order = self._order()
            if k not in order:
                _write(self.dir / ORDER, order + [k])

    def write_all(self, entries: list[dict], keep_combined: bool = False) -> None:
        """Replace the collection; the combined file is removed unless it is kept as a download."""
        keys = [str(e[self.key]) for e in entries]
        for e in entries:
            _write(self.dir / file_name(e[self.key]), e)
        _write(self.dir / ORDER, keys)
        wanted = {file_name(k) for k in keys} | {ORDER}
        for p in self.dir.glob("*.json"):
            if p.name not in wanted:
                p.unlink()
        if not keep_combined and self.combined.exists():
            self.combined.unlink()
        self._old = None

    def split_all(self, keep_combined: bool = False) -> int:
        """Split every entry of the combined file; then drop that file unless it is kept as a download."""
        old = self._legacy()
        for k, e in old.items():
            p = self.dir / file_name(k)
            if not p.exists() or self._old_mtime > p.stat().st_mtime:
                _write(p, e)
        _write(self.dir / ORDER, self.ids())
        if old and not keep_combined and all((self.dir / file_name(k)).exists() for k in old):
            self.combined.unlink()
            self._old = None
        return len(old)


class EntryDict(MutableMapping):
    """A key -> value mapping stored as one file per key (used for the lookup cache)."""

    def __init__(self, path):
        self.combined = Path(path)
        self.dir = entry_dir(self.combined)
        self._old, self._lock = None, threading.Lock()

    def _legacy(self) -> dict:
        if self._old is None:
            self._old = _read(self.combined) if self.combined.exists() else {}
        return self._old

    def __getitem__(self, k):
        p = self.dir / file_name(k)
        if p.exists():
            return _read(p)["value"]
        old = self._legacy()
        if k in old:  # split out on first read
            _write(p, {"key": k, "value": old[k]})
            return old[k]
        raise KeyError(k)

    def __contains__(self, k) -> bool:
        return (self.dir / file_name(k)).exists() or k in self._legacy()

    def __setitem__(self, k, v) -> None:
        _write(self.dir / file_name(k), {"key": k, "value": v})

    def __delitem__(self, k) -> None:
        p = self.dir / file_name(k)
        found = p.exists() or k in self._legacy()
        p.unlink(missing_ok=True)
        with self._lock:
            self._legacy().pop(k, None)
        if not found:
            raise KeyError(k)

    def __iter__(self):
        files = [_read(p)["key"] for p in sorted(self.dir.glob("*.json"))] if self.dir.exists() else []
        return iter(dict.fromkeys(files + list(self._legacy())))

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def split_all(self) -> int:
        old = self._legacy()
        for k in list(old):
            p = self.dir / file_name(k)
            if not p.exists():
                _write(p, {"key": k, "value": old[k]})
        if old and self.combined.exists():
            self.combined.unlink()
        self._old = {}
        return len(old)


def read_entries(path, key: str = "id") -> list[dict]:
    return Entries(path, key).all()


def write_entries(path, entries: list[dict], key: str = "id", keep_combined: bool = False) -> None:
    Entries(path, key).write_all(entries, keep_combined)
