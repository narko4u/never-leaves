# never-leaves spec

Every requirement is a row with an id. Agents build against approved rows; commits cite the ids they serve. `pullboard spec check` lints this file.

Statuses: approved = decided · draft = proposed · pending = open question · fact = true today · wont = won't build, decided and kept · retired = no longer applies, kept. Ids are permanent: never delete or renumber a row. Tiers: must · aim.

Write each requirement as one row under its section, in this format. The fence keeps the example out of the spec, so no placeholder id is ever committed; your own rows go below, outside it.

```text
- G1 [draft, must] The first thing the client needs, in one line. | gate: pytest
- K1 [draft, must] A constraint, e.g. runs locally with no account. | gate: review
```

## G · Goals: what the client asked for
- G1 [approved, must] The isolation check refuses network access while a draft runs and says so when it cannot prove it. | gate: tests/test_isolation.py
- G2 [approved, must] A skipped test carries its reason and is never counted as a pass. | gate: tests/test_isolation.py
- G3 [approved, must] Documents are drafted from local notes with no account, no upload and no API key. | gate: uv run --with pytest python -m pytest -q
- G4 [approved, must] The CLI exits non-zero when the offline guarantee cannot be established. | gate: tests/test_isolation.py

## K · Constraints
- K1 [approved, must] The package has no runtime network dependency. | gate: review
- K2 [approved, must] The suite passes on Python 3.10 and 3.12. | gate: review
