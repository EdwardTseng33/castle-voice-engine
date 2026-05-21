# Edward Voice Spot Check (Stage 3)

- Source: voice_samples/edward_for_eagle.m4a
- Audio duration: 30.0 sec
- Model: MediaTek-Research/Breeze-ASR-25

## ASR Transcription



## Latency (ms)

| metric | ms |
|---|---|
| server e2e | 955.6 |
| preprocess ffmpeg | 226.7 |
| inference | 943.5 |

## Note

- Edward 4/28 enrollment recording (no ground-truth ref text).
- Subjective check: 唸出來的文字跟你原本講的吻合嗎？
- Real human voice -> Breeze-ASR-25 cer-quality 看起來高 (vs round-trip CER 85% 是 stack 自我對話的 noise)
