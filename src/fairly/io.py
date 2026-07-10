"""Reading field values out of tabular / JSON records and writing them back.

Supports:
  * CSV / TSV  -- a named column of scalar strings.
  * JSON array / JSON-Lines of records -- a dotted FIELD PATH that may traverse
    nested dicts and lists, e.g. ``publisher.name``, ``fundingReferences[].funderName``,
    ``creators[].affiliation[].name``, ``subjects[].subject``.

A path segment ending in ``[]`` iterates a list. Leaves are strings.
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter
from typing import Callable, Dict, Iterable, Iterator, List, Optional


# --- path walking -----------------------------------------------------------

def _parse_path(path: str) -> List[tuple]:
    segs = []
    for seg in path.split("."):
        is_list = seg.endswith("[]")
        segs.append((seg[:-2] if is_list else seg, is_list))
    return segs


def iter_values(record, path: str) -> Iterator[str]:
    """Yield every leaf string value at ``path`` in ``record``."""
    def walk(node, segs):
        if not segs:
            if isinstance(node, str):
                yield node
            return
        (key, is_list), rest = segs[0], segs[1:]
        if not isinstance(node, dict) or key not in node:
            return
        val = node[key]
        if is_list:
            if isinstance(val, list):
                for item in val:
                    yield from walk(item, rest)
        else:
            yield from walk(val, rest)
    yield from walk(record, _parse_path(path))


def map_values(record, path: str, fn: Callable[[str], Optional[str]]) -> bool:
    """Apply ``fn`` to each leaf string at ``path`` in place. ``fn`` returning None
    drops that leaf: a list item is removed; a scalar leaf is set to None (caller's
    fallback should already be baked into ``fn``). Returns True if anything changed."""
    changed = [False]

    def walk(node, segs, parent, parent_key):
        if not segs:
            return
        (key, is_list), rest = segs[0], segs[1:]
        if not isinstance(node, dict) or key not in node:
            return
        val = node[key]
        if is_list and isinstance(val, list):
            if rest:
                for item in val:
                    walk(item, rest, None, None)
            else:  # leaf list of strings
                new = []
                for item in val:
                    if isinstance(item, str):
                        r = fn(item)
                        if r is None:
                            changed[0] = True
                            continue
                        if r != item:
                            changed[0] = True
                        new.append(r)
                    else:
                        new.append(item)
                node[key] = new
        elif not is_list:
            if rest:
                walk(val, rest, node, key)
            elif isinstance(val, str):  # scalar leaf
                r = fn(val)
                if r != val:
                    changed[0] = True
                    node[key] = r

    walk(record, _parse_path(path), None, None)
    return changed[0]


# --- record readers / writers ----------------------------------------------

def read_records(path: str, column: Optional[str] = None) -> List[dict]:
    """Load records from ``.csv`` / ``.tsv`` / ``.json`` (array) / ``.jsonl``."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".tsv"):
        delim = "\t" if ext == ".tsv" else ","
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh, delimiter=delim))
    if ext == ".jsonl":
        out = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else [data]


def write_records(records: List[dict], path: str) -> None:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".tsv"):
        delim = "\t" if ext == ".tsv" else ","
        fields = list(records[0].keys()) if records else []
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, delimiter=delim)
            w.writeheader()
            w.writerows(records)
    elif ext == ".jsonl":
        with open(path, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    else:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)


def collect_counts(records: Iterable[dict], path: str) -> Counter:
    """Frequency Counter of distinct leaf values at ``path`` across ``records``."""
    c: Counter = Counter()
    for rec in records:
        for v in iter_values(rec, path):
            if isinstance(v, str) and v.strip():
                c[v.strip()] += 1
    return c
