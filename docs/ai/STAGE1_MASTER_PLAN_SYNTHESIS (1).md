# STAGE1_MASTER_PLAN_SYNTHESIS

## 1. Executive summary
Goal: make Stage 1 look and behave like a real local AI chat assistant for YouTrack exports, while staying lightweight, grounded, and demo-ready.

Chosen direction:
- chat-first UI
- one active dataset at a time
- two user-facing modes only:
  - AI Answer
  - Precise Mode
- retrieval-first architecture
- LLM only as a narrow synthesis layer
- no public deep/thinking/streaming/reranker/critic surface in Stage 1

Why this is the best path:
- it makes the demo stronger for management
- it shows real LLM value without fake intelligence
- it keeps the laptop usable
- it avoids mixing old and new datasets
- it creates a clean base for Stage 2 and Stage 3

## 2. Ruthless Stage 1 de-scope
Remove or hide:
- public exact/auto/llm/deep selector
- prefix-based mode routing in web UI
- public deep analysis mode
- token streaming as default UI behavior
- reranker ON by default
- critic pass ON by default
- dashboard-first layout
- flat request history as the main UX

Keep:
- exact + lexical + semantic + RRF retrieval
- deterministic filters and counts
- strict grounding rules
- evidence / limitations / used issue IDs
- export and suggestions
- FastAPI + Jinja + lightweight frontend

## 3. Target Stage 1 architecture
Core principles:
1. Retrieval-first always.
2. One active dataset at a time.
3. Each chat must be bound to dataset_id.
4. Chat memory only works inside the same chat_id and dataset_id.
5. Old chats become archive/read-only after dataset replacement.
6. LLM is for synthesis, not for facts where deterministic logic is better.
7. Heavy features stay OFF by default.

## 4. Two user-facing modes
### AI Answer
Use for:
- summary
- compare
- similar tasks
- analyze new task against existing tasks
- grounded free-form questions

### Precise Mode
Use for:
- task by ID
- counts
- statistics
- overdue / deadlines
- approval status
- by customer / by responsible
- filtered lists

Rule:
- the user sees only these 2 modes
- internal routing stays hidden

## 5. Dataset and index lifecycle
Stage 1 must support exactly one active dataset.

Required file:
- `active_dataset.json`

It should contain:
- dataset_id
- source_files
- source_hashes
- created_at
- prepared_at
- indexed_at
- rows_raw_total
- tasks_total

Required behavior:
1. User replaces current dataset.
2. Old raw / processed / index artifacts are cleared.
3. New files are prepared.
4. Index is rebuilt.
5. New dataset metadata is written.
6. Existing chats from old dataset become archive/read-only.

## 6. Chat model
Required entities:
- chats
- messages

Each chat:
- chat_id
- title
- dataset_id
- created_at
- updated_at
- archived flag

Each message:
- message_id
- chat_id
- role
- content
- metadata
- created_at

Memory rule:
- lightweight only
- use short digest of recent exchanges
- do not carry context across dataset changes

## 7. UI/UX target
Left:
- collapsible sidebar
- new chat button
- active dataset badge
- chat list
- delete chat
- archive marker for stale chats

Right:
- chat thread
- top header with mode and dataset badge
- composer
- assistant cards
- evidence / limitations / used IDs
- found tasks accordion

Admin/service controls:
- not in the main canvas
- place in drawer or modal

## 8. Performance rules
Do not enable by default:
- deep mode
- thinking mode
- token streaming
- reranker
- critic pass
- multi-agent chains
- OCR / attachment pipeline
- heavy orchestration

## 9. Five implementation phases inside Stage 1
### Phase 1 — cleanup and simplification
- remove public multi-mode surface
- keep only AI Answer / Precise Mode
- remove prefix-based routing from web path
- hide streaming and deep surface

### Phase 2 — dataset control
- add active_dataset.json
- add replace dataset flow
- clear old raw / processed / index artifacts
- show dataset badge and status in UI

### Phase 3 — chat UX
- add chats/messages
- add sidebar
- create/open/delete chats
- archive stale chats

### Phase 4 — mode refinement and memory
- add quick actions for Precise Mode
- add lightweight chat memory
- tighten LLM gating
- keep deterministic flows exact

### Phase 5 — answer trust and future scaffolding
- improve evidence presentation
- add retrieval_reason / confidence policy
- finalize docs
- leave API / attachments / stronger model as future scaffold only

## 10. Final rule
A strong Stage 1 is:
- simple
- grounded
- visibly useful
- chat-like
- dataset-aware
- LLM-valuable without hallucinations
