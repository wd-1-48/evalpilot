# Entity diagnostics

Fields store `entity_analysis` beside immutable strict TP/FP/FN. Normalization uses NFKC, trimming, deduplication, and reserved absence markers; company suffixes and address components are preserved.

One-sided differences are handled in code, including unambiguous exact cross-field type moves. Two-sided differences can use one LLM response for field judgment and entity diagnosis when explicitly enabled. Unknown references and conflicting descriptions require review.

Responses must cover each difference once, use allowed labels and known entities, quote verbatim evidence, and pass consistency checks. These gates do not prove semantic correctness. Rejected output remains pending.

Field-level and entity-diagnosis reviews are separate audit operations. A combined review endpoint can submit both. Original strict counts remain unchanged. The workbench exposes review controls and preserves audit records.

Reports include event metrics, strict counts, categories, and evidence. Aggregate calculations and report prose are deterministic; there is no extra LLM report-writing call. Categories can overlap; cross-field labels must not be summed as independent events.

See [workflow v2](workflow-v2.md). Historical runs are not automatically reprocessed.
