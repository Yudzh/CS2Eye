# Iteration 9 LLM quality regression report

Dataset: `llm_quality_dataset.v1` (20 cases). Ollama runs used `temperature=0`
and `think=false`. Run date: 2026-08-28.

## Prompt comparison (`qwen3:8b`)

| Metric | prompt v3 | prompt v4 |
| --- | ---: | ---: |
| Completed / cases | 20 / 20 | 20 / 20 |
| Valid | 15 | 15 |
| Grounding pass | 100% | 100% |
| Coverage average | 100% | 100% |
| Repetition average | 100% | 100% |
| Specificity average | 64.5% | 62.5% |
| Conciseness average | 99.05% | 99.93% |
| Language pass | 100% | 100% |
| Format pass | 75% | 75% |
| Average quality | 95.1045 | 94.993 |

v3 failures were concentrated in numeric restatements (5 cases), with one
specificity and two conciseness flags. v4 removed the v3 conciseness failures,
but still produced numeric restatements in 5 different cases and slightly
reduced measured specificity. Since v4 did not improve the valid count or
quality score, it is not promoted to the production default.

## Model comparison (`match_analysis_prompt.v4`)

| Metric | qwen3:8b | qwen3:14b |
| --- | ---: | ---: |
| Completed / cases | 20 / 20 | 20 / 20 |
| Valid | 15 | 20 |
| Grounding pass | 100% | 100% |
| Coverage average | 100% | 100% |
| Repetition average | 100% | 100% |
| Specificity average | 62.5% | 68.0% |
| Conciseness average | 99.93% | 97.15% |
| Language pass | 100% | 100% |
| Format pass | 75% | 100% |
| Average quality | 94.993 | 96.515 |

The 14B model performed better on this deterministic regression set, while
being slightly less concise and substantially slower locally. No manual reviews
were recorded, so these results alone do not establish superior prose quality.
