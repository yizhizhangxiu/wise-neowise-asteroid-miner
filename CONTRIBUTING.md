# Contributing

Contributions are welcome, especially improvements to reproducibility, tests, documentation, service compatibility, and independent candidate-validation tooling.

## Development setup

```bash
python -m venv .venv
# activate the environment for your platform
python -m pip install --upgrade pip
python -m pip install -e .
```

Run the regression suite before opening a pull request:

```bash
python -m unittest discover -s tests -v
python -m compileall -q wise_miner tests run.py
python -m wise_miner --version
```

## Scientific changes

Changes to thresholds, classification rules, photometric assumptions, contamination handling, or thermal modeling are scientific changes rather than simple refactors. Please:

- describe the rationale and expected effect;
- update `docs/CONFIGURATION.md` and `docs/SCIENTIFIC_SCOPE.md` when applicable;
- add or update regression tests for the affected decision path;
- record the change in `CHANGELOG.md`;
- avoid presenting exploratory tuning as predeclared significance.

## Code and comments

Keep functions focused and place domain logic in the corresponding module. Prefer comments that explain *why* a calculation or guardrail exists, particularly when it encodes a scientific assumption or upstream-service quirk. Avoid comments that only paraphrase the next line of code.

Generated results, FITS downloads, virtual environments, caches, and local editor files should not be committed.
