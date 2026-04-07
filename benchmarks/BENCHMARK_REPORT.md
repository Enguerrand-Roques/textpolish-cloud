# TextPolish — Benchmark Report

**Date:** April 2026  
**Goal:** Identify the local Ollama model offering the best latency / quality trade-off for TextPolish on Apple M2 16 GB.

---

## Methodology

- **Corpus:** 10 representative cases (pro/casual, French/English, short/long, with typos)
- **Models tested:** gemma3:1b, gemma3:1b-it-qat, gemma3:4b, gemma3:4b-it-qat, command-r7b
- **Quality judge:** Claude Haiku 4.5 (Anthropic API), scoring 1–5 on three criteria
- **Configuration:** `num_ctx: 1024` (optimised for TextPolish), `keep_alive: 300s`

---

## Results

| Model | Median latency | Correction | Tone | Preservation | **Overall** | Size |
|-------|---------------:|----------:|-----:|-------------:|------------:|-----:|
| `gemma3:1b-it-qat` | **3.2s** | 4.3/5 | 4.1/5 | 4.0/5 | **4.13/5** | 1.0 GB |
| `gemma3:1b` | 4.2s | 4.7/5 | 4.0/5 | 4.1/5 | 4.27/5 | 0.8 GB |
| `gemma3:4b-it-qat` | 6.1s | 4.7/5 | 3.8/5 | 4.0/5 | 4.17/5 | 4.0 GB |
| `gemma3:4b` | 8.7s | 4.9/5 | 3.4/5 | 3.7/5 | 4.00/5 | 3.3 GB |
| `command-r7b` | 11.8s | 4.9/5 | 3.2/5 | 3.6/5 | 3.90/5 | 5.1 GB |
| `qwen3:4b` | — | — | — | — | timeout | 2.5 GB |

---

## Findings

**1. QAT outperforms Q4\_K\_M at equal parameter count**  
`gemma3:4b-it-qat` is 30% faster than `gemma3:4b` (6.1s vs 8.7s) with a higher overall score (+0.17). Quantization-Aware Training compensates for precision loss by incorporating it during the training phase itself.

**2. gemma3:1b-it-qat matches 4b quality at 3× the speed**  
Only a 0.04 gap in overall quality for a 3-second gain per request. The 1b notably outperforms all 4b variants on tone appropriateness (4.1 vs 3.4–3.8).

**3. Common failure: all models respond in French on English input**  
Every model tested tends to reply in French regardless of the input language. This is a prompt issue, not a model issue — to be addressed in `prompts/`.

**4. `num_ctx: 1024` has no quality impact**  
The longest case in the corpus is ~544 tokens (system + input + output). `num_ctx: 1024` provides a 480-token safety margin while reducing KV cache allocation from ~2 GB to ~16 MB.

---

## Optimisations applied

| Parameter | Before | After | Estimated gain |
|-----------|--------|-------|---------------|
| `OLLAMA_MODEL` | `gemma3:4b` | `gemma3:1b-it-qat` | −5s/request |
| `OLLAMA_KEEP_ALIVE` | `0` | `300s` | −3–5s on cold start |
| `num_ctx` | `131 072` (default) | `1 024` | −2–4s + −2 GB RAM |

**Total estimated gain: −10 to −14s per request** compared to the initial configuration.

---

## Recommendation

**Selected model: `gemma3:1b`**

Best quality/speed ratio in the test panel. Despite being 1 second slower than `gemma3:1b-it-qat` (median 4.2s vs 3.2s), it scores +0.14 overall and +0.4 on spelling correction — the primary criterion for a text polishing app. Lightweight (0.8 GB) and fast enough for interactive use. To be re-evaluated when newer models (Gemma 4, etc.) become available on Ollama.
