# CLAUDE_CURSOR_RULES

## 1. Purpose
These rules govern how Claude Sonnet 4.6 should modify this project in Cursor.
The objective is to improve Stage 1 without breaking reliability, grounding, or local performance.

## 2. First read order
Before proposing changes, read in this order:
1. IMPLEMENTATION_GUIDE_FOR_STAGE1.md
2. README.md
3. PROJECT_CONTEXT.md
4. src/agent.py
5. src/query_parser.py
6. src/search_engine.py
7. src/data_prepare.py
8. web/service.py
9. web/templates/index.html
10. web/static/app.js

## 3. Default change philosophy
- prefer small, reversible changes
- prefer deterministic logic over prompt complexity
- prefer disabling a heavy feature over tuning around it
- prefer preserving working architecture over aggressive refactoring
- optimize for trustworthiness first, not novelty

## 4. What Claude must preserve
- retrieval-first architecture
- deterministic analytics for structured queries
- grounded answers only
- local CPU/RAM friendliness
- simple web UX
- compatibility with future Stage 2 / 3 scaffolding

## 5. What Claude must not do without explicit justification
- introduce new heavy frameworks
- add agentic orchestration
- enable reranker by default
- enable critic pass by default
- expose deep/LLM/exact modes in public UI
- add streaming of intermediate reasoning
- add memory-based multi-turn context to LLM calls
- replace working pipelines with speculative abstractions
- do broad refactors across many modules without benchmark evidence

## 6. Allowed default direction
### Good changes
- fix correctness bugs
- remove false LLM labels
- reduce unnecessary LLM calls
- tighten parser and filters
- improve semantic_text quality
- improve limitations and evidence display
- simplify UI
- add regression tests
- add benchmark utilities

### Future-scaffold changes
- add lightweight interfaces for Stage 2 sources
- add disabled feature flags
- add optional schema fields with no active heavy logic

## 7. Required workflow for every change
For each task:
1. identify the exact failure or improvement target
2. state why it matters for Stage 1
3. name touched files before editing
4. keep the patch minimal
5. run or describe a focused verification
6. summarize the effect on correctness, UX, and resource cost
7. avoid unrelated cleanup in the same patch

## 8. Patch granularity
Prefer commit-friendly slices:
- one bug fix
- one parser improvement
- one UI simplification
- one retrieval tweak
- one config/feature flag change

Do not combine unrelated architecture, UI, and data prep rewrites in one patch.

## 9. LLM-specific coding rules
- do not add new LLM use cases unless deterministic logic is clearly insufficient
- keep JSON output contract stable unless migration is deliberate and justified
- if validation fails, prefer honest fallback over synthetic evidence
- never let the model count or filter when code can do it exactly
- do not add longer prompts unless benchmark evidence justifies them

## 10. Retrieval-specific coding rules
- exact and lexical retrieval are first-class, not legacy
- structured filters must work before semantic retrieval is expanded
- semantic_text changes require explicit reasoning and likely reindexing
- do not add BM25, reranking, or new vector logic before fixing parser/filter correctness

## 11. UI-specific coding rules
- public UI should feel like one smart search box
- hide technical mechanics
- show sources and limitations prominently
- no raw token stream in default UX
- if stop only aborts client fetch, label it honestly

## 12. Performance rules
Any change that can affect CPU/RAM/latency must state:
- expected cost increase or reduction
- whether reindexing is required
- whether local startup changes
- whether p50/p90 latency is expected to improve or worsen

Default preference:
- lower load
- fewer background actions
- fewer model calls

## 13. Testing rules
When changing behavior, add or update targeted checks for:
- parser correctness
- filter correctness
- insufficient evidence behavior
- used_llm / llm flags honesty
- deterministic vs synthesis routing
- UI-visible contract fields if changed

## 14. When Claude should refuse a change
Claude should push back on changes that:
- mainly increase complexity without measurable Stage 1 benefit
- are only future-looking and add active load now
- weaken grounding
- hide uncertainty
- move structured analytics into LLM logic

## 15. How Claude should present proposals
Every proposal should include:
- objective
- touched files
- exact modifications
- expected benefit
- tradeoffs
- verification steps
- rollback path if relevant

## 16. Default feature-flag stance
When unsure whether to keep something active, prefer:
- hidden
- disabled by default
- scaffold only

## 17. Stage 2 / Stage 3 expansion rule
Future expansion must plug into the existing normalized pipeline instead of replacing it.
Do not build Stage 2 or Stage 3 machinery into active Stage 1 paths unless there is a current measurable benefit.
