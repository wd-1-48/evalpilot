# Verification

Public release preparation, 2026-10-14:

- `python -m pytest -q`: **58 passed** in the local Windows virtual environment.
- Tests use synthetic inputs and mocked provider responses; they do not establish provider accuracy.
- `python scripts/benchmark.py`: 20 authored cases, 13 correctly rule-resolved and 7 abstentions.

Reproduce from the repository root after installing `requirements.txt`:

```bash
python -m pytest -q
python scripts/benchmark.py
python scripts/check_judge_benchmark.py
```

The candidate benchmark measures agreement with development expectations, not independent human gold standards. Its default is offline. Live provider runs require explicit opt-in and local credentials.

Private business-data validation and exports are not published. No production accuracy, RAG gain, or concurrency speedup is claimed. GitHub Actions runs tests and the rule benchmark on Python 3.13; local success does not establish hosted CI success.
