# Contributing

Run the test suite and offline evaluation from the root before opening a pull request:

```sh
python -m unittest discover -s tests -v
python -m docintel evaluate
```

Providers implement `name`, `identity`, and `extract(text)`. Output must conform to the shared schema and pass the same validator. Use a stable identity containing model/configuration/prompt/schema revisions, never a credential. Raise sanitized `ProviderError` values for expected external failures; preserve interrupt behavior.

Image-capable providers also implement `supports_images`, `image_identity`, `model`, and `extract_image(prepared)`. The prepared object contains a metadata-stripped data URL plus integrity/quality metadata. Return the exact image schema; shared validation forces review and labels evidence as model transcription. Keep image prompts/configuration in the cache fingerprint. Run the full suite after installing `.[vision]`; the dependency-free suite explicitly skips image-decoding tests.

For every new extraction behavior, add independently authored fixture labels and tests for its failure mode. Bump the shared schema version or baseline revision when behavior changes so old results cannot masquerade as new-policy results. Review both evidence locations and semantic binding. Do not add confidence percentages without a calibration experiment.

Use synthetic data only in public commits. Keep private inputs, API keys, databases and reports outside version control. Update the architecture, runbook, and cards when feature boundaries change.
