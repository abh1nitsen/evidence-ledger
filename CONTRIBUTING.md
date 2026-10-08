# Contributing

Run the test suite and offline evaluation from the root before opening a pull request:

```sh
python -m unittest discover -s tests -v
python -m docintel evaluate
```

Providers implement `name`, `identity`, and `extract(text)`. Output must conform to the shared schema and pass the same validator. Use a stable identity containing model/configuration/prompt/schema revisions, never a credential. Raise sanitized `ProviderError` values for expected external failures; preserve interrupt behavior.

For every new extraction behavior, add independently authored fixture labels and tests for its failure mode. Bump the shared schema version or baseline revision when behavior changes so old results cannot masquerade as new-policy results. Review both evidence locations and semantic binding. Do not add confidence percentages without a calibration experiment.

Use synthetic data only in public commits. Keep private inputs, API keys, databases and reports outside version control. Update the architecture, runbook, and cards when feature boundaries change.
