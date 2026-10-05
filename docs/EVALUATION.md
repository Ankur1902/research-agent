# Evaluation

Current report evaluation runs measure:

- **Topic coverage:** literal expected-topic occurrence in finding text.
- **Expected source recall:** expected URL/domain occurrence among report sources.
- **Citation mapping precision:** fraction of cited IDs that exist in stored sources.
- **Citation coverage:** fraction of factual findings containing citations.
- **Claim support rate:** fraction of findings assessed VERIFIED by the constrained verifier.

Empty denominators return null, not a fabricated perfect score. Demo evaluation is labeled DEMO. These metrics are deliberately named for what they measure: citation mapping is not semantic citation accuracy, and model verification is not independent truth.

Evaluation records persist report ID, expected topics/sources, method and estimated job cost. Dataset-wide live research benchmarking, labeled retrieval recall, semantic faithfulness judging, prompt-version comparisons and confidence intervals are not implemented. Do not claim those metrics from the current evaluator.

Run `make eval` (or `python scripts/evaluate.py`) for a deterministic fixture regression. The fixture output is actual computation over synthetic inputs and must not be described as live-model performance. Run pytest to cover tenant isolation, auth, retrieval ranking, document validation, approvals, source mapping and exports. Playwright verifies the real Redis-worker demo path in a running deployment.
