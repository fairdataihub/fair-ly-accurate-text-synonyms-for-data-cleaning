# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-10-30

### Added
- **`fairly.repair`: repairs for text a PDF extraction damaged**, with no model. Found
  in an audit of the posters.science corpus, where poster text is extracted from PDFs:
  - `repair_ligatures(text, vocab)`: a font that draws "ti", "tt" or "ft" as one glyph
    without a Unicode mapping leaves U+FFFD ("es\ufffdma\ufffdon", "Federa\ufffdon
    University"). Each U+FFFD inside a word is filled with the ligature letters that make
    a known word, the most frequent in a vocabulary of typed text (`word_counts`), in
    the case of the word around it. Glyphs in formulas and words split across a line
    are left alone.
  - `repair_from_reference(text, references)`: when a reference (the repository record's
    own title or description) holds the same words, only the damaged words change: lost
    accents come back ("Analise" -> "Análise"), U+FFFD takes the reference's letters,
    each in the text's own case; text extracted twice ("VIAS VIAS AEREAS AEREAS") reads
    once; a whole text with scrambled capitals ("AnalisE EpidemiolÓgica ... SÃo Paulo")
    takes the reference. Clean text is never restyled after the reference: case,
    punctuation and spacing differences are left alone ("King's" stays, "healthcare"
    stays).
  - `has_word(s)`: a real word in any script, for name checks that must not drop
    Chinese, Japanese, Cyrillic or Devanagari names ("李, 杰" counts, "M., A" does not).

## [0.5.0] - 2026-10-26

### Fixed
- **A frequent generic name no longer absorbs specific ones.** The canonical of a
  cluster is its most frequent variant, so a short, common name took over longer ones
  that mean something else. In the posters.science affiliation map, about half of the
  remaps changed which organization was meant: "Library & Researcher Information
  Services" became "Library", "The Hockaday School" became "The Hotchkiss School", and
  "Wroclaw University" became "Wroclaw University of Economics and Business".
- **Geocoding no longer takes the geocoder's guess as is.** Nominatim answers every
  query with its best match, and the first version used it unchecked: "Conference
  Location" became a social centre in Russia, "CERN" the Russian town of Chern, "Ithaca,
  NY, U.S.A." a road in Sydney, and a place without a city fell back to its region
  ("Pisa, Italy" -> "Tuscany, Italy"). A result now counts only when it is a place (not
  a street, building or venue), one of its names appears in the text, and any country or
  US state the text names agrees with it (a venue counts as its city when the text names
  that city too); a foreign-language name, or a village or other
  small place, counts only when the text also names the country. The canonical is the
  place's own English name and country ("Milano" -> "Milan, Italy"), never a containing
  region; an area keeps the name the text used ("Padova" -> "Padova, Italy"). Names match
  without administrative wrappers ("City of Rochester") and in German transliteration
  ("Goettingen"). A text that names no country stays as written when another country has
  a place of that name ranked nearly as high ("Cambridge", "Valencia"; the resolver asks
  Nominatim for its top five answers for such texts). Purely virtual locations ("Online",
  "Zoom") are never geocoded. Anything that fails stays as written.
- Names equal letter for letter, ignoring spacing, punctuation and case, are the same name
  ("PolitecnicodiTorino" = "Politecnico di Torino").
- The identity guard treats a word that is itself a place word as a place even when it
  folds to a generic word: "States" in "United States" (the generic "state" stays
  generic), so "Harvard University, United States" -> "Harvard University" is harmless.
- Install hints said `pip install fairly-synonyms[...]`; the package is
  `fair-ly-accurate`.

### Added
- **Identity guard** (`fairly.identity`). `changes_identity(variant, canonical,
  place_words, generic_words)` is True when a remap names a different entity:
  - it drops or adds an identifying word;
  - it swaps a place word, number or single letter ("Ohio State University" -> "Iowa
    State University", "Paris 1" -> "Paris 8"); dropping one is fine;
  - one side reduces to generic words only while the other has an identifying or place
    word ("Columbia University" -> "University").

  Stopwords in several languages, legal suffixes, address words and an acronym in
  parentheses don't count. Words match after folding ae/oe/ue, -re/-er, plurals, common
  endings (-ical, -ics, -ic, -ine, -al, -y) and generic words across languages
  ("Universitat" = "University"). Contractions match ("Dept.", "Lab"), and so does a
  prefix abbreviation written with a period or of at least 4 letters cut before a
  vowel; stopwords and place words never act as abbreviations.
- `identity_guard(place_words, generic_words)` returns an `IdentityGuard` that
  tokenizes each phrase once and caches pair results. A cluster of 3,000 mutually
  incompatible names takes about 4 s instead of 81 s.
- `synonym_lustre(..., identity_guard=...)` emits each cluster in rounds: members
  compatible with the most frequent one map to it, the rest form the next round with
  their own canonical. `SynonymMap.meta["n_guarded"]` counts members kept off a
  cluster's top canonical.
- `FieldConfig.identity_guard`, on in the `publisher`, `funderName` and `affiliation`
  presets. `Normalizer.build` warns when the guard runs without place words (stricter,
  place suffixes will not merge) and when `place_words` or `generic_words` are passed to
  a field whose guard is off.
- `RorIndex.place_words` and `RorIndex.generic_words`, built from the ROR dump. A place
  word comes from a city, region or country name, is in fewer than 500 organization
  names, and at least 30% of the organizations named with it are located there
  ("Antwerp" yes, "Harvard" and "National" no). Country words located there at least
  80% of the time have no frequency cap. Generic words are in at least 0.5% of
  organization names. On ROR v2.15 the share of active organizations the guard lets
  merge with another one fell from 30.7% to 6.1%. Older pickled indexes load with empty
  word sets; rebuild them with `fairly build-ror-index`.
- `fairly.authorities.ror.identity_words_from_dump(path)` and
  `identity_words_from_orgs(orgs)` return `(place_words, generic_words)` for use
  without a full index.
- `fairly.authorities.geocode.verify_place(text, raw)` checks one Nominatim answer
  (requested with `addressdetails` and `namedetails`), with `named_countries(text)` and
  `is_virtual(text)`. `nominatim_resolver` caches the raw answers and asks again for
  entries cached by earlier versions, which kept only the city and country.

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
