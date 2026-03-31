# IMPLEMENTATION_GUIDE_FOR_STAGE1

## 1. Project goal
Build a local YouTrack AI agent that helps business analysts work with exported YouTrack data (XLSX/CSV) through a lightweight web UI.

## 2. Stage 1 goal
Stage 1 is not a general-purpose agent. It is a retrieval-first, grounded analytical assistant for local exports.

Primary priorities:
1. factual correctness
2. usefulness for business analysts
3. simplicity of use
4. low CPU/RAM load on Ryzen 5 5500U / 16 GB RAM / iGPU
5. clean path to Stage 2 and Stage 3

## 3. What the agent must do in Stage 1
- answer from exported data only
- prefer deterministic filters, counts, deadlines, approval logic, and exact task lookup
- support free-form retrieval and grounded synthesis for a small subset of modes
- show source tasks and limitations clearly
- say when evidence is insufficient
- stay lightweight and predictable on local hardware

## 4. What the agent must not do in Stage 1
- must not invent missing facts
- must not pretend to know attachment contents
- must not expose raw thinking or intermediate reasoning
- must not use LLM for deterministic analytics by default
- must not enable expensive reranking by default
- must not overload the UI with technical modes
- must not become an agentic multi-step orchestration system

## 5. Mandatory architecture principles
### Retrieval-first
All answers start from retrieved task evidence, not model intuition.

### Deterministic-first
Use deterministic logic first for:
- task_by_id
- list
- count
- deadlines
- overdue
- stats
- by_customer
- by_responsible
- with_remarks
- most approval status queries

### LLM only where it adds real value
LLM is allowed by default only for:
- similar
- analyze_new_task
- general_search

Even there, retrieval happens first.

### Honest insufficiency
If evidence is weak, missing, or attachment-dependent, return a constrained answer with explicit limitations.

### Lightweight by default
Anything heavy must be off by default unless benchmarked and justified.

## 6. Internal answer paths
### Path A: deterministic analytics
Pipeline:
query_parser -> structured filters -> search/filter/aggregation -> answer_builder

Rules:
- no LLM by default
- high confidence when filters are direct and data exists
- return task cards / tables / aggregates directly

### Path B: grounded synthesis
Pipeline:
query_parser -> hybrid retrieval -> small top-k context -> single-pass LLM -> strict validation -> answer_builder

Rules:
- no answer without evidence
- if evidence or used_issue_ids are missing after validation, fall back
- prefer single pass by default
- critic pass remains disabled by default in Stage 1

## 7. Retrieval policy
### Keep now
- exact search
- lexical search
- semantic search
- hybrid RRF fusion

### Improve now
- fix parser for dotted responsible codes like SEA.1
- fix parser for multiword customers
- propagate current_approval_stage end-to-end
- enrich semantic_text with selected structured fields
- remove placeholder noise from semantic signal
- add content_quality_flag for attachment-only or generic descriptions

### Do not add now
- BM25 rewrite unless benchmark proves current lexical search is insufficient after core fixes
- multilingual reranker
- chunk retrieval for attachments
- OCR

## 8. Data preparation rules
### Fix now
- `initial_review_deadline` must not be treated as a true date if raw data contains terms like `10 дней`
- clean placeholder values in extra approval fields
- detect generic descriptions such as `Постановка во вложении`
- keep semantic_text focused on meaningful content

### semantic_text should include
- summary
- cleaned description
- doc_type
- functional_customer
- responsible_dit
- current_approval_stage
- meaningful approval lines
- meaningful decision lines

### semantic_text should exclude or de-emphasize
- raw technical metadata
- source file/path/row
- generic attachment-only descriptions
- raw dates unless directly meaningful for semantic retrieval
- placeholder strings like `Нет: ...`

## 9. Grounding and hallucination control
- every synthesis answer must list supporting issue IDs
- evidence should map to specific tasks
- if there are zero relevant tasks -> insufficient_data
- if only 1-2 weak tasks exist -> low confidence + warning
- if attachments would be needed -> limitation must say so
- remove synthetic evidence injection from validation fallback

## 10. LLM policy
### Allowed default use
- synthesize meaning across retrieved tasks
- compare similar tasks
- compare a new task formulation with previous tasks
- produce compact grounded summaries

### Forbidden default use
- counting
- filtering
- deadline computation
- approval bucket logic
- inventing causes or motivations
- using prior world knowledge outside retrieved data

### Prompt policy
- keep prompt compact
- keep JSON output contract
- require short_answer, evidence, limitations, used_issue_ids
- do not switch to long free-form templates in Stage 1

## 11. UI policy
### Public UI should show
- one main input
- one main run action
- example chips
- result summary
- evidence / confirmed facts
- source task cards
- limitations
- confidence
- simple history

### Public UI should not show
- Auto / Exact / LLM / Deep selector
- raw intermediate token stream
- raw system mechanics
- noisy service controls on the main path

### Streaming policy
- no streaming of intermediate reasoning
- no raw streaming box in default UI
- default UX should show progress states, not token-by-token partial answers
- SSE may stay in code as a disabled scaffold if needed later

### Stop policy
If the frontend only aborts the client request, label it honestly (`Прервать вывод` or equivalent). Do not imply true backend cancellation unless jobs/cancellation are implemented.

## 12. Observability policy
Keep only lightweight observability in Stage 1:
- query
- mode / answer_type
- duration_ms
- retrieved_candidates
- llm_attempted
- llm_succeeded
- error_text
- applied_filters_json

Do not add heavy tracing or telemetry stacks.

## 13. Intentionally simplified in Stage 1
- no live YouTrack API
- no attachment parsing
- no chunk retrieval
- no fine-tuning
- no agentic tool orchestration
- no complex multi-turn memory
- no production-grade infra work that does not improve Stage 1 quality

## 14. Stage 2 / Stage 3 scaffolding policy
It is acceptable to keep lightweight interfaces or stubs for:
- youtrack_api adapter
- attachment_ingest pipeline
- evidence units beyond tasks
- backend cancellation model
- reranker integration point

But these must remain disabled by default until benchmarked and needed.

Recommended future-proof fields:
- entity_type
- parent_issue_id
- source_kind
- source_ref
- content_quality_flag

Do not force a large refactor now just to support future ideas.

## 15. Release criteria for strong Stage 1
A strong Stage 1:
- answers deterministic BA questions without LLM dependency
- gives honest grounded synthesis only when evidence exists
- clearly shows source tasks and limitations
- does not confuse users with technical modes
- runs reliably on current laptop
- is easy to demo to leadership
