# AGENTS.md

## Project goal
Local retrieval-first YouTrack AI agent for Stage 1.

## Stage 1 priorities
- chat-first UI
- one active dataset at a time
- grounded answers
- AI Answer and Precise Mode only
- lightweight implementation
- no mixed old/new dataset context

## Hard rules
- do not implement the whole Stage 1 in one task
- do not enable reranker, critic, deep mode, or public streaming
- do not introduce heavy dependencies without strong need
- do not refactor unrelated files
- preserve retrieval-first architecture
- keep patches small and reviewable
- always explain changed files and verification steps

## Dataset rules
- exactly one active dataset
- dataset replacement must clear old raw/processed/index artifacts
- chats must eventually be bound to dataset_id
- old chats must not remain live against a new dataset

## UI rules
- user sees only:
  - AI Answer
  - Precise Mode
- no public exact/auto/llm/deep selector
- no prefix-based routing in web UI