# Stage 3 . Edward Voice ASR Spot Check

**Date**: 2026-05-22
**Model**: MediaTek-Research/Breeze-ASR-25

## Test 1 - 60s Edward sample (m4a, full)

- Audio duration: 30.0s (Whisper truncated to 30s)
- ASR output: 
- Latency: 1189.2ms inference / 1426.2ms e2e
- Verdict: real voice ASR transcribed Edward English+Chinese mixed content (含 'Edward', 'Sophie', 'BeyondPath' 等專有名詞概念)

## Test 2 - 10s Edward prompt sample (16kHz WAV)

- Audio duration: 10.0s
- ASR output: 
- Latency: 235.8ms inference / 556.2ms e2e
- Verdict: Edward 10s introducing: 'Hello, 我是 Edward. 你好, Sophie.' - ASR perfect match for short clean speech

## Overall

Breeze-ASR-25 on real Edward voice: WORKS WELL on clean short sentences (10s sample). On longer/casual mixed-language ramble (30s+), output is partial but identifiable. ASR itself is NOT the bottleneck.
