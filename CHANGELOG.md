# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-10-23

### Fixed
- **A frequent generic name no longer absorbs specific ones.** The canonical of a
  cluster is its most frequent variant, so a short, common name took over longer ones
  that mean something else. In the posters.science affiliation map, about half of the
  remaps changed which organization was meant: "Library & Researcher Information
  Services" became "Library", "The Hockaday School" became "The Hotchkiss School", and
  "Wroclaw University" became "Wroclaw University of Economics and Business".

### Added
- **Identity guard** (`fairly.identity`). `changes_identity(variant, canonical,
  place_words)` is True when a remap drops or adds an identifying word. Stopwords,
  legal suffixes, address words, numbers, single letters, acronyms in parentheses and
  place names don't count; plurals fold and abbreviations match.
- `synonym_lustre(..., identity_guard=...)` emits each cluster in rounds: members
  compatible with the most frequent one map to it, the rest form the next round with
  their own canonical. `SynonymMap.meta["n_guarded"]` counts members kept off a
  cluster's top canonical.
- `FieldConfig.identity_guard`, on in the `publisher`, `funderName` and `affiliation`
  presets.
- `RorIndex.place_words`, built from the ROR dump's country, region and city names
  (city words common in organization names are left out). Older pickled indexes load
  with an empty set; rebuild them with `fairly build-ror-index` to get place words.

## [0.4.0] - 2026-08-27

### Added
- **Automated ROR dump download.** `fairly build-ror-index --latest` fetches the
  newest ROR v2 data dump from Zenodo (community `ror-data`), extracts it, and
  builds the `.pickle` index in one step — no manual download. Caches the dump in
  `--cache-dir` (default `.ror_cache/`); `--force` re-downloads.
- `fairly normalize --ror-latest` auto-builds the ROR index on the fly for presets
  that use ROR splitting, so no prebuilt `--ror-index` is required.
- Python API: `RorIndex.from_latest()` and `fairly.authorities.ror.fetch_latest_ror_dump()`.
- New optional extra `[ror]` (pulls in `requests` for a faster/retry-friendly
  download); the fetcher falls back to the standard library when it is absent.

## [0.3.0] - 2026-08-27

### Changed
- **First public PyPI release.** Distribution name is `fair-ly-accurate`
  (`pip install fair-ly-accurate`); the import name remains `fairly`.

### Added
- Automated publishing via **PyPI Trusted Publishing (OIDC)** on GitHub Release
  (`.github/workflows/publish.yml`), a CI workflow running the test suite on
  Python 3.9/3.12 (`.github/workflows/ci.yml`), and a `RELEASING.md` runbook.

## [0.2.1] - 2026-07-16

### Added
- Licenses: parse Creative Commons `rightsUri` values and spelled-out CC names.

## [0.2.0] - 2026-07-14

### Added
- **Controlled-vocabulary normalization** (`fairly.controlled.ControlledVocabulary`): a
  deterministic normalizer for fixed-vocabulary fields (license ids, country codes, units,
  resource types). Folds surface strings (`fold_key`: strip diacritics/case/punctuation) and
  resolves them against the canonical set + an alias map to a single canonical id — never
  merging two distinct ids (`CC-BY-SA-4.0` vs `CC-BY-NC-4.0`), which embedding clustering
  cannot guarantee. New `strategy="controlled"` for `FieldConfig`/`Normalizer`.
- **`fairly.licenses`**: a ready SPDX/CC license `ControlledVocabulary` + `classify()`
  (allowed/blocked/unknown) policy. The `rights` preset now uses it instead of clustering.
- Documented in `docs/methods.md` §6.5. On the posters.science corpus this approach
  reclassified ~6,100 license values a plain whitelist match had missed.

## [0.1.1] - 2026-07-10

### Added
- **Reference gold sets** (`gold/`) for `affiliation`, `funderName`, `publisher`,
  `subject`, `rights` — true synonym groups plus adversarial near-misses.
- **V-measure validation of the default presets.** A sweep (eps 0.05–1.0) against
  the gold sets confirms every preset `eps` sits on its field's optimal plateau
  (funder/subject V=1.00, publisher 0.99, affiliation 0.96, rights 0.82) and
  documents the per-field over-merge cliff. Results and interpretation added to
  `docs/methods.md` §8.

### Changed
- Docs and preset docstrings now describe the `eps` values as V-measure validated
  (not "proposed"). No `eps` values changed — validation confirmed the existing
  settings. `rights` flagged as better served by a controlled vocabulary.

## [0.1.0] - 2026-07-10

Initial release. A generalizable, authority-aware synonym-normalization tool for
FAIR / DataCite metadata fields, distilled from the methods proven on the
posters.science corpus.

### Added
- **Synonym-lustre engine** (`fairly.cluster`): gte-large embeddings + HDBSCAN
  (`min_cluster_size=2, min_samples=1, cluster_selection_epsilon, leaf`) with a
  most-frequent-canonical (centroid tie-break) rule; disk-cached embeddings keyed
  on model id + cache version.
- **Abbreviation / short-token holdout** (`fairly.holdout`): `< 4`-char and
  all-caps single-token terms are held out of clustering (map to themselves) to
  prevent short-string over-merges (`ZHAW → Z`).
- **ROR authority split** (`fairly.authorities.ror`): build a `name → ROR id`
  index from a ROR v2 dump (ambiguous names dropped) and split semantic clusters
  that span two or more institutions.
- **Geocoding normalization** (`fairly.authorities.geocode`): geocode place
  fields (Nominatim, cached, rate-limited) and group by `(country, city)` →
  `"City, Country"`; pluggable resolver.
- **Deterministic cleaners** (`fairly.cleaners`): composable steps + `ORG`,
  `SUBJECT`, `MINIMAL` presets (balanced quote-unwrap, preamble strip, placeholder
  / generic / hedge / citation drop, word-boundary-safe).
- **V-measure validation** (`fairly.validate`): gold-set homogeneity /
  completeness / V-measure across an `eps` sweep, with explicit noise handling, to
  tune `cluster_selection_epsilon` per field.
- **DataCite field presets** (`fairly.presets`): `publisher`, `funderName`,
  `affiliation`, `subject`, `rights`, `geoLocationPlace`.
- **Field-path I/O** (`fairly.io`): CSV/TSV columns and dotted JSON/JSONL paths
  through nested dicts and lists (`creators[].affiliation[].name`).
- **CLI** (`fairly`): `presets`, `build-ror-index`, `validate`, `normalize`.
- Packaging (`fairly-synonyms`), optional `cluster` / `geo` / `all` extras, MIT
  license, and a test suite (30 tests) covering the pure-logic and clustering paths.

[0.2.0]: https://github.com/fairdataihub/fair-ly-accurate-text-synonyms-for-data-cleaning/releases/tag/v0.2.0
[0.1.1]: https://github.com/fairdataihub/fair-ly-accurate-text-synonyms-for-data-cleaning/releases/tag/v0.1.1
[0.1.0]: https://github.com/fairdataihub/fair-ly-accurate-text-synonyms-for-data-cleaning/releases/tag/v0.1.0
