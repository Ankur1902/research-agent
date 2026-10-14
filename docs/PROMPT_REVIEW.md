# AI prompt review

Reviewed and revised all six runtime AI prompts against the actual input payloads, Pydantic contracts, and research workflow. This was a static review; no Docker commands, tests, or model calls were executed. The changes are not empirically validated yet.

| Prompt | Main revision |
| --- | --- |
| Planner | Scope preservation, source-mode routing, proportionate decomposition, ambiguity handling, and explicit human-approval boundary |
| Analyst | Exact contiguous quotations, attributed source assertions, units and denominators, claim types, provisional support statuses, and grounded computation requests |
| Verifier | Correct nested input path, independent assessment, complete ordered coverage, semantic support rubric, and conservative treatment of computed findings |
| Writer | Existing finding indices only, uncertainty-aware section placement, a scope-based summary without uncited claims, and preservation of material limitations |
| Security target | Instruction hierarchy, educational benign controls, encoded attacks, no invented tool catalog, and proposed-versus-executed distinction |
| Security judge | Answer and tool-argument inspection, criterion-specific verdicts, benign task completion, exact observed quotes, and resistance to evaluator-directed injection |

## Important implementation findings

The initial security harness had no trusted tool catalog. It now appends an application-controlled catalog, argument schemas, role, approval state, tenant scope, and call budget as trusted system configuration. Positive tool-use cases assess proposal selection and arguments; they still do not dispatch tools or measure actual retrieval success.

The verifier receives an Analysis object under `findings`, not a top-level list. Its prompt now explicitly identifies `findings.findings` as the array to review. Computed findings have source quotes but no independent execution receipt in the verifier input, so the prompt avoids treating a claim of calculation as sufficient evidence of complete verification.

The writer's summary has no citation field. It now summarizes scope, coverage, and gaps rather than introducing uncited substantive conclusions. Actual findings retain their existing citations and statuses through section indices.

The workflow now validates source-mode routing and task ID uniqueness. Web task questions go to web retrieval, and document task questions go to tenant-scoped document retrieval. Queries are deduplicated in stable order and bounded by research depth.

Evidence excerpts are truncated by the application. Prompt rules can require faithful quotes and careful uncertainty, but cannot restore omitted context, authenticate sources, enforce tenant isolation, or replace deterministic security controls.

## Versioning and later validation

The existing v1 paths were retained because the runtime and security CLI already load them. Security evaluation reports include hashes of prompt contents, and production model-start events now include prompt_sha256 and logical_call_number. Repository history should preserve the exact prompt revision used in a production release.

When testing is authorized, assess quotation fidelity, contradictory evidence, unsupported claims, unit mismatches, empty evidence, nested verifier inputs, invalid indices, educational attack examples, and malicious tool proposals. Include human-labeled judge calibration examples. Compare behavior across providers and repeated runs before making reliability claims. No passing evaluation or measured improvement is claimed by this review.
