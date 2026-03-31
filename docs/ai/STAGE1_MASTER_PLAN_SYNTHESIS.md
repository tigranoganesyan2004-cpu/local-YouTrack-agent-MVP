# STAGE1_MASTER_PLAN_SYNTHESIS

## Chosen direction
A lightweight, deterministic-first, retrieval-first Stage 1.
LLM is a narrow synthesis layer, not the center of the product.

## Immediate priorities
1. remove unnecessary LLM usage from deterministic modes
2. fix used_llm honesty and validation fallback behavior
3. fix parser/filter correctness for real BA language
4. disable reranker and critic by default
5. simplify UI to one main flow
6. improve semantic_text quality without heavy infrastructure
7. build a benchmark set before adding new complexity

## Core de-scope
- no public mode selector
- no raw token streaming UI
- no always-on reranker
- no default critic pass
- no heavy tracing
- no model swap as first move
- no BM25 rewrite as first move
- no attachment/chunk work now

## Stage 1 definition of done
- deterministic BA queries are accurate and fast
- LLM synthesis is used rarely and honestly
- source tasks and limitations are visible
- the laptop load is lower, not higher
- the demo focuses on reliable use cases, not broad intelligence theater
