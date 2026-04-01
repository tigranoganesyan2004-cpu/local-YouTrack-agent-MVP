# IMPLEMENTATION_SEQUENCE

## Important distinction
There are:
- 3 overall product stages
- 5 implementation phases for improving Stage 1

## 3 overall product stages
### Stage 1
- CSV/XLSX YouTrack export
- local web UI
- grounded answers
- LLM mode and non-LLM mode
- lightweight architecture

### Stage 2
- YouTrack API
- Word/PDF and attachments
- stronger retrieval inputs

### Stage 3
- stronger model
- stronger hardware
- possible adaptation / advanced quality upgrades

## 5 implementation phases inside Stage 1
### Phase 1 — cleanup and simplification
Goal:
- remove public complexity

Do:
- only two user-facing modes
- no public exact/auto/llm/deep
- remove prefix routing from web path
- hide streaming/deep surface

Tool:
- Cursor first

### Phase 2 — dataset control
Goal:
- one active dataset
- clear lifecycle

Do:
- active_dataset.json
- replace dataset flow
- clear old raw/processed/index
- dataset badge and status

Tool:
- Codex first, then manual test

### Phase 3 — chat UX
Goal:
- make the app feel like a real chat

Do:
- chats/messages
- left sidebar
- new/open/delete chat
- collapsible history

Tool:
- Cursor first, then manual test

### Phase 4 — mode refinement and memory
Goal:
- make both modes strong

Do:
- quick actions for Precise Mode
- lightweight chat memory
- tighter LLM gating

Tool:
- Codex for backend, Cursor for UI polish

### Phase 5 — trust polish and future scaffold
Goal:
- improve trust and demo strength

Do:
- evidence presentation
- limitations block
- used IDs
- retrieval reason
- docs and benchmark pack
- keep Stage 2/3 scaffolds OFF

Tool:
- Cursor + Codex depending on slice size

## Exact order you should follow
1. Add project docs and Cursor rules.
2. Make a snapshot commit.
3. Cursor Ask mode for Slice 1.
4. Cursor Agent mode for Slice 1.
5. Run the project locally and test manually.
6. Commit.
7. Codex for active dataset lifecycle.
8. Run the project locally and test dataset replacement.
9. Commit.
10. Cursor Ask mode for chat sidebar slice.
11. Cursor Agent mode for chat sidebar slice.
12. Test manually.
13. Commit.
14. Codex for chat-to-dataset binding and stale archive behavior.
15. Test manually.
16. Commit.
17. Cursor for Precise Mode quick actions.
18. Codex for lightweight chat memory and LLM gating.
19. Cursor for answer card polish.
20. Final docs, benchmark, and demo prep.

## How to act on each slice
Always use the same discipline:
1. Plan
2. Implement
3. Run locally
4. Test manually
5. Commit
6. Only then move to next slice

## What not to do
- do not ask either tool to implement the whole Stage 1 at once
- do not mix UI redesign with dataset lifecycle in the same task
- do not enable heavy features for demo
- do not skip manual testing after each slice
- do not continue if the current slice is unstable

## Recommended commit sequence
1. chore: snapshot before stage1 simplification
2. feat: simplify public ui to ai and precise modes
3. feat: add active dataset lifecycle
4. feat: add chat sessions and sidebar
5. feat: bind chats to dataset and archive stale chats
6. feat: add precise mode quick actions
7. feat: add lightweight chat memory and llm gating
8. feat: improve answer trust blocks and demo readiness

## What you should do right now
Start with Phase 1 only:
- add the docs
- add the Cursor rules
- use Cursor Ask mode
- use Cursor Agent mode
- test
- commit

Only after that move to Phase 2 with Codex.
