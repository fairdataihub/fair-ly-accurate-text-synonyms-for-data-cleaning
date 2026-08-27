"""``fairly`` command-line interface.

Subcommands::

    fairly presets
    fairly build-ror-index --dump ror_v2.json --out ror_index.pickle
    fairly validate --gold gold.tsv --preset affiliation [--eps 0.05,0.1,0.15,...]
    fairly normalize --input records.jsonl --field-path publisher.name \
        --preset publisher --output out.jsonl [--ror-index ror_index.pickle] \
        [--map-out map.pickle] [--review review.tsv] [--cache-dir .cache] \
        [--fallback Zenodo] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import __version__
from .io import collect_counts, map_values, read_records, write_records
from .pipeline import Normalizer
from .presets import PRESETS, get_preset

# Kept local so `fairly` CLI startup stays light (authorities.ror pulls in numpy).
DEFAULT_ROR_CACHE = ".ror_cache"


def _cmd_presets(_args) -> int:
    for name, cfg in sorted(PRESETS.items()):
        auth = cfg.authority or "-"
        print(f"{name:18s} strategy={cfg.strategy:8s} eps={cfg.eps:<4} "
              f"holdout={str(cfg.holdout):5s} authority={auth}")
        if cfg.description:
            print(f"                   {cfg.description}")
    return 0


def _cmd_build_ror(args) -> int:
    from .authorities.ror import build_ror_index, fetch_latest_ror_dump
    if args.latest:
        dump = fetch_latest_ror_dump(cache_dir=args.cache_dir, force=args.force)
    elif args.dump:
        dump = args.dump
    else:
        print("error: give --dump PATH or --latest (auto-download newest from Zenodo)",
              file=sys.stderr)
        return 2
    idx = build_ror_index(dump)
    idx.save(args.out)
    print(f"ROR index: {len(idx)} names -> {args.out}")
    return 0


def _cmd_validate(args) -> int:
    from .validate import best_eps, format_table, load_gold, sweep_eps
    cfg = get_preset(args.preset) if args.preset else None
    gold = load_gold(args.gold)
    eps_list = [float(x) for x in args.eps.split(",")] if args.eps else None
    kw = {}
    if eps_list:
        kw["eps_list"] = eps_list
    if cfg:
        kw.update(embedding_model=cfg.embedding_model, holdout=cfg.holdout)
    rows = sweep_eps(gold, cache_dir=args.cache_dir, **kw)
    print(f"V-measure sweep over {len(gold)} gold variants"
          + (f" (preset {args.preset})" if args.preset else ""))
    print(format_table(rows))
    if args.field:
        print(f"\nrecommended for {args.field}: eps={best_eps(rows)['eps']:.2f}")
    return 0


def _cmd_normalize(args) -> int:
    cfg = get_preset(args.preset)
    if args.fallback is not None:
        cfg.fallback = args.fallback
    norm = Normalizer(cfg, cache_dir=args.cache_dir)

    records = read_records(args.input)
    counts = collect_counts(records, args.field_path)
    print(f"{len(records)} records, {len(counts)} distinct values at {args.field_path}")

    build_kw = {}
    if cfg.authority == "ror":
        if args.ror_index:
            from .authorities.ror import RorIndex
            build_kw["authority"] = RorIndex.load(args.ror_index)
        elif args.ror_latest:
            from .authorities.ror import RorIndex
            build_kw["authority"] = RorIndex.from_latest(cache_dir=args.ror_cache_dir)
        else:
            print("note: preset uses ROR splitting but neither --ror-index nor --ror-latest "
                  "given; clusters will not be authority-split.", file=sys.stderr)
    if cfg.strategy == "geocode":
        from .authorities.geocode import nominatim_resolver
        build_kw["resolve"] = nominatim_resolver(cache_path=args.geo_cache)

    smap = norm.build(counts, **build_kw)
    m = smap.meta
    print(f"map: {len(smap)} variant->canonical across {m.get('n_clusters', m.get('n_places', 0))} groups"
          + (f", {m.get('n_authority_splits', 0)} authority splits" if 'n_authority_splits' in m else "")
          + (f", {m.get('n_held_out', 0)} held out" if 'n_held_out' in m else ""))

    if args.map_out:
        smap.save(args.map_out)
    if args.review:
        smap.write_review(args.review, counts)
        print(f"review: {args.review}")

    if args.dry_run:
        print("(dry-run: not applying)")
        return 0

    changed = 0
    for rec in records:
        if map_values(rec, args.field_path, lambda v: norm.normalize(v, smap)):
            changed += 1
    out = args.output or args.input
    write_records(records, out)
    print(f"applied: {changed} records changed -> {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="fairly", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"fairly {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("presets", help="list field presets").set_defaults(func=_cmd_presets)

    p = sub.add_parser("build-ror-index",
                       help="build a ROR index from a ROR v2 dump (local file or auto-downloaded)")
    p.add_argument("--dump", help="path to a local ROR v2 JSON dump")
    p.add_argument("--latest", action="store_true",
                   help="auto-download the newest ROR v2 dump from Zenodo instead of --dump")
    p.add_argument("--cache-dir", default=DEFAULT_ROR_CACHE,
                   help=f"where --latest caches the downloaded dump (default {DEFAULT_ROR_CACHE})")
    p.add_argument("--force", action="store_true", help="re-download even if a cached dump exists")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_build_ror)

    p = sub.add_parser("validate", help="V-measure eps sweep against a gold set")
    p.add_argument("--gold", required=True)
    p.add_argument("--preset", help="field preset for embedding/holdout settings")
    p.add_argument("--field", help="label for the recommendation line")
    p.add_argument("--eps", help="comma-separated eps values (default sweep otherwise)")
    p.add_argument("--cache-dir")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("normalize", help="build + apply a synonym map for a field")
    p.add_argument("--input", required=True)
    p.add_argument("--field-path", required=True,
                   help="e.g. publisher.name, fundingReferences[].funderName, creators[].affiliation[].name")
    p.add_argument("--preset", required=True, choices=sorted(PRESETS))
    p.add_argument("--output")
    p.add_argument("--ror-index", help="prebuilt ROR index pickle (see build-ror-index)")
    p.add_argument("--ror-latest", action="store_true",
                   help="auto-download + build the newest ROR index on the fly (no --ror-index needed)")
    p.add_argument("--ror-cache-dir", default=DEFAULT_ROR_CACHE,
                   help=f"cache dir for --ror-latest (default {DEFAULT_ROR_CACHE})")
    p.add_argument("--map-out")
    p.add_argument("--review")
    p.add_argument("--cache-dir")
    p.add_argument("--geo-cache")
    p.add_argument("--fallback")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=_cmd_normalize)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
