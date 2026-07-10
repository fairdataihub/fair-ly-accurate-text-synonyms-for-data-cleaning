# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/fairdataihub/fair-ly-accurate-text-synonyms-for-data-cleaning/releases/tag/v0.1.0
