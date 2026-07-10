# Example

`sample_records.jsonl` holds three DataCite-shaped records with the usual mess:
`"NSF"` / `"N.S.F."` / `"National Science Foundation (NSF)"`, `"Stanford Univ."`
vs `"Stanford University, CA, USA"`, an LLM `"The publisher is …"` preamble, and a
junk `"The authors"` publisher.

Install with the clustering extra (`pip install "fairly-synonyms[cluster]"`), then:

```bash
# normalize funders (build + review + apply); add --ror-index to enable ROR split
fairly normalize \
  --input sample_records.jsonl \
  --field-path 'fundingReferences[].funderName' \
  --preset funderName \
  --review funder_review.tsv \
  --output out.jsonl \
  --dry-run                       # drop --dry-run to write out.jsonl

# clean + normalize publishers (the "The authors" junk falls back to Zenodo)
fairly normalize --input sample_records.jsonl --field-path publisher.name \
  --preset publisher --fallback Zenodo --output out.jsonl
```

Inspect `funder_review.tsv` to see which variants merged before trusting the
apply. Tune the threshold first with a gold set:

```bash
fairly validate --gold funder_gold.tsv --preset funderName --field funderName
```
