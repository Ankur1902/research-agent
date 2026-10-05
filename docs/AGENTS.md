# Research agents

These instructions document the application's agents; this file does not direct coding assistants.

| Stage | Inputs | Allowed actions | Output |
|---|---|---|---|
| Manager / planner | Question, source mode, depth | Structured model call | Validated plan; human approval |
| Web researcher | Approved task queries | Search provider, guarded fetch | Persisted unique sources and evidence |
| Knowledge agent | Question, organization | Filtered hybrid retrieval | Diverse document chunks with provenance |
| Analyst | Selected untrusted evidence | Structured model call | Typed findings with exact quotes |
| Fact checker | Findings and evidence | Structured assessment, deterministic citation/quote validation | Support / partial / unsupported / conflicting statuses |
| Writer | Assessed findings and requested sections | Structured organization of findings | Report draft and final approval |

Research jobs have a 600-second execution deadline, up to 12 model steps, 24 tool operations, bounded provider retries and a context character ceiling. Independent webpage downloads run concurrently, with at most four results per query; database writes are serialized. Every stage publishes safe operational events and usage metadata. Models never receive an unrestricted Python interpreter, shell, database connection or infrastructure secrets.

The calculator and CSV statistics tool use predefined arithmetic operations. No model-generated code is executed. Project association, job state and selected organization documents provide scoped working memory. Conversation history is not blindly replayed. Rich long-term project memory and provider-specific model routing are future extensions.

The analyst can request bounded computations. Code verifies that each input occurs in an exact quote from the cited stored source before executing the calculator. Invented inputs are rejected and a limitation is recorded. Computed results remain labeled ANALYSIS and retain their citation; units and source definitions still require review.
