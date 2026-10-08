# Invoice image input and Groq vision

Version 0.2 adds JPEG/PNG/WebP intake from upload or a directory batch. Groq performs a single vision call producing a faithful transcription, seven fields with quotes, and image-quality diagnostics. API details were checked against [Groq vision](https://console.groq.com/docs/vision) and [output modes](https://console.groq.com/docs/structured-outputs). The current default, `qwen/qwen3.8-27b`, was also verified through the account's model-list API on 8 October 2026.

The integration uses JSON object mode; it **does not claim provider-enforced strict schema**. Returned JSON is checked locally for exact keys, types, quality enums and field evidence. Refusals, truncation, invalid output and provider errors cannot become successful invoice records.

## Photograph preparation

Pillow is imported only when image preparation is requested. Images are limited to 8,000,000 bytes, 20 million pixels, one frame, and at least 32 pixels on each side. Actual decoded format is checked, independent of extension or browser MIME. Corrupt and unsupported files are rejected before any API call.

Preparation applies EXIF orientation, flattens alpha onto white, resizes proportionally to a 2,000-pixel longest edge, and re-encodes RGB JPEG without EXIF/GPS metadata. Original and normalized SHA-256 hashes, dimensions, preprocessing revision and Pillow version are retained as metadata. Original bytes are not placed in the JSON result.

Local warnings use small-image dimensions and grayscale brightness/contrast heuristics. They are diagnostics, not calibrated quality scores or complete blur/glare detectors. The vision model can additionally report blur, glare, shadow, cropped content, small text, rotation, unreadability, multiple documents or non-invoice input. No automatic perspective correction is performed.

## Evidence and review

Image results always use `decision=review` and `evidence_basis=model_transcription`. Their `source_sha256` identifies original image bytes; `transcript_sha256` identifies generated text. Field quotes/spans reference that generated text. No pixel bounding boxes, independently verified OCR, or calibrated recognition confidence are produced. Model transcription can hallucinate or misread characters even when local field checks pass.

The UI displays the original local photo beside the transcript and extraction. Compare every field with the original. Blank/non-invoice or unreadable content should return null fields and quality warnings; API or malformed-schema failures return an error instead. Existing text-policy restrictions still apply: ISO dates, constrained decimal amounts, seven currencies, no inferred missing values.

## Upload, privacy and recovery

Selecting a file previews it locally. Clicking **Extract photo with Groq** sends the raw bytes to the loopback server, which sends only the normalized image to Groq. The key remains in the server environment. Original upload storage is temporary and is removed after the request. Checkpoint records persist extracted values and the generated transcript in `runs/uploads.sqlite`.

The server is single-worker and loopback-only, with bounded body size, a read timeout, origin checks and fixed endpoints. It has no production authentication or distributed scheduling. A competing checkpoint writer returns an unavailable error; retry once it finishes. Re-upload identical bytes to resume/reuse a job after a browser disconnect or server restart. If the original bytes differ (including metadata), a new source key is created. Failed uploads are explicitly retried by the next user extraction click; batch failures require `--retry-failed`.

JSON downloads use HTTP attachment responses addressed by opaque temporary tokens. The server retains at most 16 recent exports in memory; links expire after eviction or restart. Re-extract/re-upload to obtain a fresh link while reusing a completed checkpoint.

Provider requests have a 45-second timeout, two retries after the initial attempt, and a 2,500-token output cap. Rate-limit delay is numeric Retry-After, bounded to 1–60 seconds, with a 20-second fallback. Other transient errors use short exponential delays. Long invoices can exceed output budget and fail rather than returning partial fields. Remote retries/crashes can repeat paid requests; there is no exactly-once billing guarantee.

Before sending confidential images, review [Groq's data policies](https://console.groq.com/docs/your-data). Metadata stripping does not anonymize text printed in the invoice. Keep private images, databases and exports outside public commits.

## Replicate the tests

```sh
python -m pip install -e '.[vision]'
python -m unittest discover -s tests -v
python scripts/generate_image_fixtures.py
python -m docintel evaluate --images --dataset data/images --provider groq --output runs/image-evaluation.json
```

Set `GROQ_API_KEY` before the last command. Image evaluation checkpoints are reusable; use a fresh `--db` to measure fresh inference. Fixture generation is deterministic with the tested Pillow version, though font rendering/JPEG encoding can vary across library versions.

`data/images` contains an authored invoice render, simulated shadow, simulated angle, and blank image. These are synthetic software-generated images, **not natural-light camera photographs**. The committed live smoke report measures those fixtures only. A larger independent set of real consented camera photos is still needed before claiming accuracy for arbitrary invoices in natural light.
