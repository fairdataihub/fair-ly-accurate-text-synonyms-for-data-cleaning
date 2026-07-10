# Methods & settings

How `fairly` normalizes metadata field values, what each knob does, and the
recommended settings per field type. This is the reference behind the summary in
the [README](../README.md).

## Contents
1. [Architecture](#1-architecture)
2. [The synonym-lustre method](#2-the-synonym-lustre-method)
3. [Abbreviation / short-token holdout](#3-abbreviation--short-token-holdout)
4. [ROR authority split](#4-ror-authority-split)
5. [Geocoding for place fields](#5-geocoding-for-place-fields)
6. [Deterministic cleaners](#6-deterministic-cleaners)
7. [Recommended HDBSCAN settings per use case](#7-recommended-hdbscan-settings-per-use-case)
8. [V-measure validation](#8-v-measure-validation)
9. [Field-path I/O](#9-field-path-io)
10. [Extending](#10-extending)

---

## 1. Architecture

Normalization runs in three tiers per field:

```
TIER 0  AUTHORITY INDICES (built once, reused)
        build_ror_index(dump) -> RorIndex        # name -> ROR id + display + geo
        nominatim_resolver()  -> resolve(place)  # place -> (country, city)

TIER 1  DETERMINISTIC CLEANING (per value, before any embedding)
        Cleaner([...steps]) -> cleaned string | None(drop)

TIER 2  GROUPING (per field)
        semantic:  embed -> HDBSCAN -> canonical, with holdout + optional authority split
        geocode:   resolve -> group by (country, city) -> "City, Country"
        => SynonymMap { variant -> canonical }
```

`Normalizer(FieldConfig)` orchestrates all three: `build()` cleans the value
counts, then groups them into a `SynonymMap`; `normalize(value, smap)` cleans a
raw value and maps it to its canonical (falling back if the cleaner drops it).

The two authorities (ROR, geocoding) are deliberately **not** embedding-based.
They inject real-world identity into a process an embedding gets wrong: an
embedding happily merges two different institutions that read alike, or two
different cities in the same country. The authority is the veto.

---

## 2. The synonym-lustre method

`fairly.cluster.synonym_lustre` is the semantic engine.

1. **Embed** the distinct cleaned terms with a SentenceTransformer
   (`Alibaba-NLP/gte-large-en-v1.5` by default), L2-normalized, batch size 256.
   Vectors are cached to disk keyed on `(cache_version, model_id, term_list)` — so
   a model change never silently reuses stale vectors.
2. **Cluster** the non-held-out terms with HDBSCAN:
   ```
   HDBSCAN(min_cluster_size=2, min_samples=1,
           cluster_selection_epsilon=eps,
           cluster_selection_method="leaf", metric="euclidean")
   ```
   Held-out terms (§3) keep label `-1` (noise) and map only to themselves.
3. **Split** each cluster by authority (§4) if one is configured.
4. **Choose a canonical** per (sub-)cluster: the **most frequent** variant, with
   the variant closest to the cluster centroid breaking ties among equally
   frequent ones. Frequency wins because the common surface form is the one users
   recognize; the centroid tie-break keeps the choice stable.

Only real remaps are stored (a term that is its own canonical is absent), so
applying a map is a cheap dict lookup that leaves unknown values untouched — it is
idempotent and safe to re-run.

**Why `min_cluster_size=2, min_samples=1, method="leaf"`.** We want *tight,
specific* synonym groups, not broad topical blobs. `min_cluster_size=2` lets a
pair of variants form a cluster (two spellings of one entity is the whole point);
`min_samples=1` keeps the density requirement minimal so singletons aren't
absorbed into a neighbour; `leaf` selection returns the smallest coherent leaves
of the condensed tree rather than large excess-of-mass clusters. Together they
bias toward precision — exactly what synonym collapsing needs.

**PCA** is available (`--pca-dims`) but off by default: reducing dimensions costs
the fine distinctions that keep similar-but-distinct entities apart. Use it only
when full-dimensional clustering is infeasible for a very large field, and keep
many dimensions.

---

## 3. Abbreviation / short-token holdout

A term is **held out of clustering** (mapped only to itself) when it is:

- shorter than **4 characters**, or
- an **all-caps single token** (an acronym: `ZHAW`, `MIDAS`, `UK`, `NASA`).

Short and all-caps tokens carry too little lexical signal for a sentence
embedding to place reliably, so left in the clusterer they attach to unrelated
short forms and get assigned a wrong representative — the observed failures were
`ZHAW → Z`, `LUH → HU`, `GTC → GT`. Holding them out is the single most important
precision guard for entity fields.

Held-out terms are still embedded (so an on-disk embedding cache stays valid);
they are simply masked out of the HDBSCAN input and rejoined as noise. The
threshold is configurable (`is_holdout(term, min_len=4)`).

> Trade-off: a legitimate acronym (`NASA`) will not be merged with its expansion
> (`National Aeronautics and Space Administration`). That is the intended
> precision-over-coverage stance — resolve acronyms with an authority or a
> controlled vocabulary, not with an embedding guess.

---

## 4. ROR authority split

For organization fields (`affiliation`, `funderName`, org `publisher`s), an
embedding will merge lexically-close but distinct institutions. The
[Research Organization Registry](https://ror.org) resolves the ambiguity.

**Index** (`build_ror_index`, from a ROR v2 JSON dump): every org name is
normalized (`NFKD → ASCII → lowercase → [a-z0-9 ] → collapse`) into a
`name → ROR id` map, carrying the ROR display name and GeoNames location. A
normalized name that maps to **two different RORs is ambiguous and dropped**, so
it can never trigger a false split; names `< 3` chars or with no letter are
skipped.

**Split** (`RorAuthority.split`): within one semantic cluster, resolve each member
to a ROR id. If the cluster spans `≤ 1` distinct ROR it is returned intact.
Otherwise it is **partitioned per ROR**, and any member that resolves to no ROR is
assigned to the nearest per-ROR sub-group by embedding distance. Each sub-group
then gets its own canonical. This is what keeps *University of Washington* and
*Washington University* — near-identical strings — in separate entities.

The split can only ever *separate*, never *merge*, so an incomplete ROR index
degrades gracefully (fewer splits, never a wrong merge).

---

## 5. Geocoding for place fields

Location fields must not be embedded: `"Graz, Austria"` and `"Vienna, Austria"`
are near neighbours in embedding space ("a city in Austria") and would merge.

`geocode_synonyms` instead geocodes each distinct place string (via geopy's
Nominatim by default — 1 req/sec, cached to disk, `swallow_exceptions=True`) and
**groups by the resolved `(country_code, city)`**, canonicalizing to
`"City, Country"`. Variants of one place collapse; different cities in the same
country stay apart. Strings that do not resolve to both a city and a country are
left unmapped.

You can inject any `resolve(place) -> {country, cc, city} | None` — a local
GeoNames dump, a commercial geocoder, or a test stub — instead of Nominatim.

---

## 6. Deterministic cleaners

Cleaners run **before** embedding. Each step transforms a string or returns
`None` to drop it as junk (the caller substitutes a field `fallback`, e.g. the
source repository). Compose them with `Cleaner([...])`; three presets ship:

- **`ORG_CLEANER`** (publishers/funders/affiliations): NFKC normalize → strip
  `"The publisher is …"` preambles and balanced surrounding quotes → drop URLs,
  placeholders, generic non-entities (`"a university"`), hedge phrases
  (`"not specified in the text"`, `"the authors"`) and author citations
  (`"… et al."`). No word-count cap — real institution names can be long.
- **`SUBJECT_CLEANER`** (keywords/subjects): light — keep short concepts (`AI`),
  drop only placeholders and letterless values.
- **`MINIMAL_CLEANER`** (rights/licenses): normalize whitespace, require a letter.

Notes that matter in practice:

- **Balanced-only unwrap.** Surrounding quotes are stripped only when they wrap
  the *whole* string, so `University of Campania "Luigi Vanvitelli"` (an internal
  quoted name) is left intact rather than mangled.
- **Word-boundary hedges.** Hedge phrases are anchored (`the image\b`) so a real
  name like `The IMAGEN Consortium` is not caught by `the image`.
- **Abbreviation-safe.** There is no "looks like a sentence because it has a
  period" rule — that wrongly killed `U.S. Environmental Protection Agency`. Use a
  word-count cap (`max_words`) only for known-noisy LLM output.

---

## 7. Recommended HDBSCAN settings per use case

`cluster_selection_epsilon` (`eps`) is the main dial: larger = more aggressive
merging. The fixed HDBSCAN params (`min_cluster_size=2, min_samples=1,
method="leaf"`) suit all these fields; only `eps`, `holdout` and `authority`
change. Values below are validated on the posters.science corpus — **treat them
as starting points and re-tune with §8**.

| Field type | eps | Holdout | Authority | Why |
|---|---:|:---:|:---:|---|
| **publisher** | 0.30 | yes | ROR | Diverse population (repositories, journals, universities, agencies). Distinct names sit far apart, so a *looser* eps safely collapses format variants; ROR split protects the org-name tail. |
| **funderName** | 0.07 | yes | ROR | **Homogeneous** — nearly every value is "science funder" boilerplate, so everything is close in embedding space and a loose eps cross-merges different countries' agencies. Needs a **tight** eps *and* ROR split. |
| **affiliation** | 0.07 | yes | ROR | Many near-identical institution strings; tight eps + holdout + ROR is the strongest guard against cross-institution merges. |
| **subject / keyword** | 0.10 | yes | — | Concepts, not entities, and no authority to fall back on — keep eps tight so distinct topics don't conflate; rely on holdout for acronyms (`AI`, `ML`). |
| **rights / license** | 0.08 | yes | — | Near-duplicate labels only (`CC-BY 4.0` vs `CC BY 4.0`); very tight. Consider a controlled-vocabulary map instead of clustering if you have one. |
| **geoLocationPlace** | — | — | geocode | Do **not** embed places. Geocode + group by `(country, city)`. |

Rules of thumb:

- **Homogeneous field → tighter eps + an authority.** The more alike the values
  look, the more the embedding over-merges, and the more you need ROR/geocoding.
- **Diverse field → looser eps is safe**, because distinct entities are already
  far apart.
- **Always keep holdout on for entity/keyword fields** — it is cheap insurance
  against the acronym failure mode.
- When unsure, err **tight** and let coverage come from a second pass; over-merge
  is the expensive, hard-to-detect mistake.

---

## 8. V-measure validation

Choosing `eps` by eye does not scale. `fairly.validate` turns it into a number.

Give it a **gold set** — surface variants each labelled with their true canonical
entity (`variant<TAB>true_canonical`, or a JSON `{variant: canonical}`). A few
hundred hand-labelled rows per field is plenty. `sweep_eps` embeds the variants
exactly as the normalizer would, clusters them across a range of `eps`, and scores
each clustering against the gold labels with
`sklearn.metrics.homogeneity_completeness_v_measure`:

- **homogeneity** — each predicted cluster contains only one true entity →
  penalizes **over-merge** (the costly direction here);
- **completeness** — all variants of a true entity land in one cluster →
  penalizes **under-merge**;
- **V-measure** — their harmonic mean; pick the `eps` that maximizes it.

**Noise handling.** HDBSCAN labels some points `-1`. We explode each noise point
into its own singleton cluster before scoring, so an over-cautious `eps` that
leaves many points unclustered is penalized on completeness rather than silently
ignored — matching how the normalizer treats noise (a noise term maps only to
itself).

```bash
fairly validate --gold affiliation_gold.tsv --preset affiliation --field affiliation
#    eps   homogeneity  completeness  v_measure  clusters
#   0.05      1.000         0.612        0.759       ...
#   0.10      0.994         0.803        0.888       ...
#   0.15      0.951         0.902        0.926       ...   <- best
#   0.20      0.883         0.951        0.916       ...
#   best: eps=0.15  v_measure=0.926
```

Re-run whenever the corpus, the field, or the embedding model changes, and record
the chosen `eps` in your config. A gold set also doubles as a regression guard:
watch homogeneity, not just V-measure — a drop there means new over-merges.

---

## 9. Field-path I/O

`fairly.io` reads values out of records and writes them back:

- **CSV / TSV** — the path is the column name (scalar strings).
- **JSON array / JSON-Lines** — a dotted path that traverses nested dicts and
  lists; a segment ending in `[]` iterates a list. Examples:
  `publisher.name`, `fundingReferences[].funderName`,
  `creators[].affiliation[].name`, `subjects[].subject`.

`collect_counts(records, path)` builds the frequency Counter the Normalizer needs;
`map_values(record, path, fn)` rewrites leaves in place — a list item whose `fn`
returns `None` is removed, a scalar leaf is set to the returned value.

For very large corpora, collect counts by streaming records, build the map once,
then apply it file-by-file (the map is small and reusable).

---

## 10. Extending

- **New field** — construct a `FieldConfig` (or add to `fairly.presets.PRESETS`)
  with a strategy, `eps`, cleaner, holdout and authority. Validate its `eps`.
- **New authority** — implement `.split(idxs, phrases, emb) -> list[list[int]]`
  (see `fairly.authorities.base.Authority`) — e.g. an ISNI or Wikidata resolver —
  and pass it to `Normalizer.build(authority=...)`.
- **New cleaner step** — any `str -> str | None` callable slots into a `Cleaner`.
- **Different embedding model** — set `FieldConfig.embedding_model`; the cache key
  includes the model id, so vectors won't be confused across models.
