# Security and privacy

Never commit API keys, PATs, real invoice text, or private output artifacts. `.secrets`, dotenv files, checkpoints and `runs/` are ignored. The GitHub credential used to publish this project is external to the repository and is not used by the application.

Offline mode processes data locally. OpenAI mode sends full document text to the provider, uses `store: false`, and never logs response bodies or authentication headers. `store: false` is not a claim about all provider retention policies; review the provider's terms before sending confidential documents.

The source text is untrusted. The AI provider has no tools; downstream values must pass schema, grounding, format and policy checks. These controls do not eliminate every prompt injection or fraud risk. The baseline instruction detector is illustrative and incomplete.

The UI binds to `127.0.0.1`, allows no external network assets, inserts document values with `textContent`, restricts write origins, and limits request size. It has no authentication, TLS, multi-user isolation or hardened production server. Do not expose its port publicly. GET access to a report assumes a trusted local user/environment. The server deliberately serves only known assets and one configured report.

Runtime reports/checkpoints include extracted values and source quotes. Protect them as sensitive records when using private inputs. Input SHA-256 is an integrity/deduplication identifier, not encryption or anonymization. SQLite files are not encrypted by this application.

For a suspected vulnerability, contact the repository owner through their GitHub profile without publicly posting credentials or private invoice contents. For improvements, add a synthetic regression test and submit a fix.
