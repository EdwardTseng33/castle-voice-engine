# Day 3 Complete (Voice Path v2.0 Breeze PoC)

> calcifer auto-ship 5/22 - real deploy + Stage 1-4 executed

## Artifacts (4 shipped)

| # | path | status |
|---|---|---|
| 1 | breeze_poc/phase1-poc/audio/t01-t10.wav | 10/10 |
| 2 | breeze_poc/phase1-poc/results/round-trip-cer.csv | 10/10 |
| 3 | breeze_poc/phase1-poc/results/edward-voice-spotcheck.md | OK |
| 4 | breeze_poc/phase1-poc/results/latency.csv | OK |

## Key metrics

| metric | value | NO-GO |
|---|---|---|
| CER mean | 85.86% | < 5% same-stack |
| CER median | 95.0% | |
| CER max | 107.14% | |
| TTS latency | P50=7349.0ms P95=9860.0ms | P95 < 3000ms |
| ASR latency | P50=289.0ms P95=997.0ms | P95 < 3000ms |

## NO-GO escalate triggers

TRIGGERED escalate to Sophie:

- CER mean 85.86% > 5%
- TTS P95 9860.0ms > 3000ms

## Day 4 plan

- Llama-Breeze2 + Sophie persona
- Day 5 Picovoice Eagle
- Day 6 Claude function calling demo
- Day 7-8 E2E + measurements

## Gate 5 privacy status

- Condition 1: OK via health JSON isolation_check.modal_volume_attached false
- Condition 5: OK via X-Breeze-Token check
- Ref wav uses test_outputs/p1_NATF1.wav = non-Edward, no Phase 2 voice clone
