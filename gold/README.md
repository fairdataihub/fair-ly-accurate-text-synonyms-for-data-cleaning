# Reference gold sets

Small, hand-curated `surface_variant<TAB>true_canonical` sets used to V-measure
validate the default per-field `eps` presets. Each mixes **true synonym groups**
(variants of one entity) with **adversarial near-misses** (distinct entities that
look alike) — the near-misses are what make the sweep discriminating:

- `affiliation.tsv` — e.g. *University of Washington* vs *Washington University in St. Louis*; the three UC campuses.
- `funderName.tsv` — US *NSF* vs China *NSFC* vs Swiss *SNSF*; *NIH* vs UK *NIHR*.
- `publisher.tsv` — *PLOS ONE* vs *PLOS Biology*; *ACS* vs *APS* vs *AAS*.
- `subject.tsv` — *machine / deep / reinforcement learning*; *genetics / genomics / epigenetics*.
- `rights.tsv` — *CC-BY 4.0* vs *CC-BY-SA 4.0* vs *CC-BY-NC 4.0* vs *CC-BY 3.0*.

Reproduce the sweep (needs the `cluster` extra + a downloaded embedding model):

```bash
for f in affiliation funderName publisher subject rights; do
  fairly validate --gold gold/$f.tsv --preset $f --field $f
done
```

Results and interpretation: [docs/methods.md §8](../docs/methods.md#8-v-measure-validation).
These are *reference* sets sized to validate the presets; build a larger,
domain-specific gold set to tune `eps` for your own corpus.
