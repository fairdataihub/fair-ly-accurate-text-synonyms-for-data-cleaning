# fair-ly accurate text synonyms for data cleaning

**`fairly`** collapses spelling and format variants of FAIR / DataCite metadata
field values onto a single canonical form — *fairly accurately* — so that
`Univ. of California, Berkeley`, `University of California-Berkeley` and
`UC Berkeley` all become one publisher/affiliation, while genuinely different
entities (`University of Washington` vs `Washington University`) stay apart.

It packages four cooperating strategies, each earning its place against a real
failure mode:

| Strategy | What it does | Guards against |
|---|---|---|
| **Synonym-lustre** | embed distinct values (`gte-large`) → cluster (HDBSCAN) → map each cluster to its most-frequent member | spelling/format/punctuation variants |
| **Abbreviation holdout** | keep acronyms and `< 4`-char tokens *out* of clustering | `ZHAW → Z`, `LUH → HU` over-merges |
| **ROR authority split** | split a cluster that spans two real institutions using a local ROR dump | `University of Washington` vs `Washington University` |
| **Geocoding** | for place fields, geocode and group by `(country, city)` → `"City, Country"` | `Graz` merging into `Vienna` ("city in Austria") |
| **Controlled vocab** | for fixed-vocabulary fields (licenses, codes), deterministically fold + alias-resolve to a canonical id | `CC-BY-SA` collapsing into `CC-BY-NC` — clustering can't tell them apart |

Quality is measured, not assumed: a **V-measure** harness tunes the clustering
threshold per field against a small gold set.

> Method background and per-field recommendations: **[docs/methods.md](docs/methods.md)**.

## Install

```bash
pip install fair-ly-accurate                 # core (cleaners, ROR index, I/O, V-measure math)
pip install "fair-ly-accurate[cluster]"      # + embeddings & HDBSCAN (semantic clustering)
pip install "fair-ly-accurate[geo]"          # + geopy (place geocoding)
pip install "fair-ly-accurate[all]"          # everything
```

(The distribution installs as `fair-ly-accurate`; the import name is `fairly`: `from fairly import Normalizer`.)

The heavy ML/geo dependencies are optional extras, so the deterministic cleaners,
ROR index and field-path I/O install light.

## Quickstart (CLI)

```bash
# 0. (once, for institution fields) build a ROR index from a ROR v2 dump
fairly build-ror-index --dump v2-ror-data.json --out ror_index.pickle

# 1. tune the threshold for a field against a gold set (variant<TAB>true_canonical)
fairly validate --gold affiliation_gold.tsv --preset affiliation --field affiliation

# 2. build + apply a synonym map to a DataCite-shaped field, with review + ROR split
fairly normalize \
  --input records.jsonl \
  --field-path 'creators[].affiliation[].name' \
  --preset affiliation \
  --ror-index ror_index.pickle \
  --review affiliation_review.tsv \
  --output records.normalized.jsonl
```

The `--field-path` understands dotted paths through nested dicts and lists, e.g.
`publisher.name`, `fundingReferences[].funderName`, `subjects[].subject`,
`creators[].affiliation[].name`. Tabular inputs use the column name as the path.

**Always eyeball the `--review` TSV before trusting an apply** — especially for
homogeneous fields like funders, where over-merge is easy. Add `--dry-run` to
build the map and review without writing.

## Quickstart (library)

```python
from fairly import Normalizer, get_preset
from fairly.authorities.ror import RorIndex
from fairly.io import collect_counts, read_records, map_values

records = read_records("records.jsonl")
counts  = collect_counts(records, "fundingReferences[].funderName")

norm = Normalizer(get_preset("funderName"), cache_dir=".cache")
smap = norm.build(counts, authority=RorIndex.load("ror_index.pickle"))
smap.write_review("funder_review.tsv", counts)     # review gate

for rec in records:
    map_values(rec, "fundingReferences[].funderName", lambda v: norm.normalize(v, smap))
```

## Field presets

Built-in `FieldConfig` presets for common DataCite/FAIR fields (`fairly presets`):

| Field | Strategy | eps | Holdout | Authority |
|---|---|---|---|---|
| `publisher` | semantic | 0.30 | yes | ROR |
| `funderName` | semantic | 0.07 | yes | ROR |
| `affiliation` | semantic | 0.07 | yes | ROR |
| `subject` | semantic | 0.10 | yes | — |
| `rights` | **controlled** | — | — | SPDX/CC vocab |
| `geoLocationPlace` | geocode | — | — | — |

These `eps` values are **V-measure validated** against the curated gold sets in
[`gold/`](gold/) — each sits on its field's optimal plateau (funder/subject 1.00,
publisher 0.99, affiliation 0.96; `rights` 0.82, so prefer a controlled vocabulary
for licenses). **Re-tune for your data** with `fairly validate` — see
[docs/methods.md](docs/methods.md#8-v-measure-validation) for the full sweep and why
each field wants a different threshold.

## Why these choices

- **Most-frequent canonical** gives clean, recognizable labels (the common form
  wins), with centroid-closeness only breaking ties.
- **Holdout** exists because short/all-caps tokens carry too little signal for an
  embedding to place; left in, they become spurious join keys.
- **Authority split** is what lets us cluster *aggressively* for coverage without
  paying for it in precision: the embedding proposes merges, ROR/geocoding vetoes
  the wrong ones.
- **V-measure** turns "did we over-merge?" into a number: homogeneity penalizes
  over-merge (the costly direction), completeness penalizes under-merge.

## License

MIT — see [LICENSE](LICENSE).
