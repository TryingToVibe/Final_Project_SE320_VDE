# Verified Disposal Event (VDE) — SE 320

Turns a station processing-cycle report into a trusted Verified Disposal Event.
Design: `docs/STATE_MODEL.md`. Developer guide: *VDE_Package_Guide.docx*.

## Quick start

```bash
pip install -r requirements.txt
python -m pytest                     # or: python -m unittest discover -s tests -t .
uvicorn vde.api:app --reload         # once Teammate C finishes the API
```

## Who owns what

| Area | Files | Owner |
|---|---|---|
| Contract: states, schema, IDs | `enums.py`, `models.py`, `state.py`, `identity.py`, `errors.py`, `config.py` | Team lead |
| Rules engine (step 2) | `vde/rules.py`, `tests/test_rules.py` | Teammate A |
| Scenarios (step 3) | `scenarios/*.json`, `tests/test_scenarios.py` | Teammate B |
| Storage, service, API (steps 4–5) | `store.py`, `service.py`, `api.py`, `tests/test_store.py`, `test_service.py`, `test_api.py` | Teammate C |
| Integration guide (step 6), reviews | `docs/` | Team lead |

Stubs raise `NotImplementedError("<owner>")`. Search for that to find your work.

## Interfaces (do not change without telling the team lead)

```python
rules.evaluate(report, now, config=DEFAULT_CONFIG) -> DisposalEvent
store.get(event_id) -> DisposalEvent | None
store.insert(event) -> None        # raises DuplicateEventError
service.submit_report(report, store, now, evaluator=None) -> (event, created)
```

Until `rules.evaluate` is finished, use `vde.testing.fake_evaluate`.

## Workflow

1. Create a branch: `git checkout -b <name>/<feature>` (e.g. `alex/rules-r2-r5`).
2. Commit small, working pieces. Add tests with your code.
3. Run the whole test suite before pushing. **Nothing merges with failing tests.**
4. Open a pull request; the team lead reviews and merges.
5. **Contract files** (`models.py`, `enums.py`, `identity.py`) are shared with six
   other teams. Propose changes to the team lead; don't edit them directly.
