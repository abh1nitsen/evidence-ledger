# Spending groups and smartphone access

## Receipt-level spend

Each saved reading has a suggested category, a user-saved category and up to eight tags (30 characters each). The initial categories cover groceries, dining, transport, shopping, health/personal care, travel/accommodation, utilities and office/business. A transparent keyword heuristic suggests a category only when one group matches; mixed or unclear text stays Unclassified. It does not infer a trustworthy category from a merchant brand. Confirm the category yourself. Tags such as work, holiday or household are saved for later filtering, but the current overview does not aggregate tags.

The overview groups by saved category, currency and reviewed month. Only explicitly accepted or edited totals and currencies contribute. Dates must be accepted/edited for monthly grouping; otherwise they appear under Date not reviewed. Missing totals stay excluded; BASE never becomes TOTAL. Currencies are never added together or converted. Arithmetic conflicts are excluded. The overview reports exclusion counts.

Grouping is persisted in the same SQLite database, using transactional, revision-checked append-only events. Field decisions and grouping share a revision, so concurrent stale writes return HTTP 409. JSON exports contain spending metadata/history alongside immutable original fields and effective values. Existing databases acquire the new table automatically.

Identical source bytes are deduplicated, preferring the most reviewed extraction revision. Different photos with the same complete effective merchant, identifier, date, currency and total are flagged as possible duplicates and counted once. This heuristic can merge genuinely distinct receipts with reused identifiers, and cannot identify every duplicate if identifiers or dates differ/are absent. All documents remain available as saved readings. Separate refunds, budgets, exchange rates, identity management and accounting reconciliation are future work.

Receipts without extracted items use whole-receipt groups. Mixed baskets use the reviewed item allocation workflow described below; receipt categories do not imply that every item belongs to that category.

## Taking a bill photo on a phone

The UI now has separate upload and **Take a bill photo** controls. The latter requests the rear camera through `capture="environment"`; browser behavior varies. The upload control remains available for existing photos. JPEG/PNG/WebP under 8 MB are supported; HEIC needs conversion to JPEG. This is a camera/file-picker hint, not a live camera stream. Camera behavior was not tested on physical Android/iOS hardware.

The server still binds only to `127.0.0.1`. On a smartphone that address means the smartphone itself, not this laptop. A QR code or home-screen shortcut cannot make an unreachable server reachable.

| Route | Experience | Prerequisites and tradeoffs |
| --- | --- | --- |
| Hosted mobile web app | Open an HTTPS link, take/upload a photo, review and group it. A QR code can open the link. | Best simple experience for other users. Requires a deployed backend, sign-in, per-user storage, upload limits and secure server-side API keys. |
| Private connection to your laptop | Install Tailscale on laptop and phone; access a private HTTPS URL using Tailscale Serve. | Useful for a personal prototype. Laptop/server must remain running. Requires private-network setup and an explicitly allowed proxy origin in this app. |
| Same Wi-Fi access | Phone opens the laptop LAN address. | Requires a deliberate LAN bind/firewall setup and matching allowed origins. Current loopback build does not support this directly; local Wi-Fi alone is insufficient. |
| Messaging bot or Share-to-app | Send the image to a bot or share from the camera/gallery. | Adds bot/webhook processing, authentication, queueing and data retention design. Messaging services receive a copy of the bill. More work than a web link. |

Recommended next step: a hosted authenticated mobile web app, keeping OCR/Groq keys on the backend. For personal trials, use a private HTTPS connection. Do not simply expose this demo through a public tunnel: its saved-reading/spending endpoints currently share a single unauthenticated store, and its write-origin checks accept only localhost. A proxy URL alone will not enable extraction. Network exposure and authentication are not implemented or enabled by this release.

A home-screen shortcut is a useful convenience once the URL is reachable. Full installable PWA/offline upload queues and smartphone Share Target support are future enhancements; extraction still requires the backend and Groq connection.

Sources: [MDN capture attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/capture), [MDN file inputs](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/file), [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve), [private application sharing](https://tailscale.com/docs/use-cases/application-testing/share-local-dev-server-with-team).

## Version 0.6 item allocations

When a receipt has extracted items, spending uses reviewed line categories rather than its single receipt category. Every line must have an Accept/Reject/Edit decision; final total and currency must also be reviewed. Printed line amounts are added without multiplying quantity again, discounts inherit a linked purchase category, payments are excluded, and tax is added once only when required to reconcile. Missing totals, unallocated basket discounts and mismatches exclude the receipt. With no item lines, the saved receipt category remains the fallback. See [Items and page chains](ITEMS_AND_PAGES.md).

Phone capture can add successive photos to the same active receipt using **Add next page**. This does not change backend access: the application is still loopback-only. A hosted authenticated backend or an explicitly configured private connection is required to reach it from another device; neither is implemented here. Physical-phone capture remains untested.

## Clear spending workflow (0.7)

The overview starts with confirmed totals per currency and a unique receipt count. **By category** combines all saved dates; no exchange-rate conversion occurs. **To review**, **Included**, and **All** filter a compact receipt list. Each row explains the next step: confirm a total/currency, choose a category, review items, or correct amounts. **Finish review** opens that saved receipt at the relevant field/items/grouping view. **Confirm date** places an included receipt in the right month; the current category summary shows all dates together.

Known authored offline examples (including the earlier layout stress fixture) and explicitly marked practice snapshots appear under collapsed **Demo examples**. They are excluded from personal totals even after acceptance. Other pasted text remains eligible as real input. Classification is exact source matching, not a guess from merchant names. Existing snapshots and decisions are preserved. Editing a saved practice example does not turn it into real spending.

Repeated extraction versions of the same photo contribute one representative receipt, preferring the most reviewed saved reading. Page chains are represented once for the same set of source photos; their component images stay available in saved readings but do not contribute separate spend. Possible duplicate bills photographed differently appear in a separate collapsed inspection section, retaining the existing heuristic limitations. Technical exclusion counts remain in the API rather than the main screen. Human decisions are never created by these display changes.
