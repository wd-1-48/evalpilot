# Workflow v2

Scope: compare existing predictions with human references; no source-model
training or re-extraction. Knowledge-base construction and user-configurable
policies remain deferred.

New runs use a LangGraph strict-compare / difference-diagnose flow. One-sided
differences and exact cross-field type moves are resolved in code. Other
differences use one combined field judgment + entity diagnosis request. The
legacy field judge remains for compatibility but is not called by the new worker.
Three field workers execute concurrently; SQLite writes stay serialized in the
coordinator. 429 and selected transient server failures receive at most three
attempts with bounded backoff. Timeouts/invalid responses remain pending.

Strict sets and counts never change after semantic or entity review. Entity
review has its own audit records and requires complete difference coverage and
verbatim evidence; field-level review remains independent. Existing runs retain
their old results and tags. Main error categories group detailed tags for reports;
acceptable aliases are separated from errors. Manual diagnosis review does not
assert causal knowledge of the original model.

Event-level metrics and combined human review are implemented. No speedup is
claimed without a controlled runtime comparison. Cache and dedicated LLM report
synthesis remain future work.
