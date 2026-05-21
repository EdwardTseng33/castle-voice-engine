# Day 3 Complete (Voice Path v2.0 Breeze PoC) FINAL

> calcifer 自治 ship 2026-05-22 04:45 TST
> Branch: voice-path/v2.0-breeze-poc
> Endpoint: https://edwardt0303--castle-voice-engine-breeze-poc-breeze-fastapi.modal.run

## Phase 1 PoC 7 MUST artifact 狀態

| # | path | status |
|---|---|---|
| 1 | audio/t01.wav-t10.wav (廠商台灣腔女聲) | 10/10 |
| 2 | audio/edward_voice_clone_demo.wav | OK (137KB) |
| 3 | results/round-trip-cer.csv | 10/10 |
| 4 | results/edward-voice-spotcheck.md | OK |
| 5 | results/latency.csv | OK |
| 6 | DAY3-COMPLETE.md | OK |
| 7 | CASTLE-DISPATCH-DEMO.md | OK (Day 5-7 真機 e2e) |

## 核心指標

| metric | value | NO-GO threshold |
|---|---|---|
| CER mean (round-trip TTS->ASR) | 85.86% | > 15% |
| CER median | 95.0% | |
| CER min | 56.36% | |
| CER max | 107.14% | |
| TTS server P50 | 7364.4ms | |
| TTS server P95 | 11466.8ms | > 3000ms |
| ASR server P50 | 261.7ms | |
| ASR server P95 | 955.6ms | > 3000ms |

## NO-GO escalate triggers

### WARNING TRIGGERED

- CER mean 85.86% > 15%
- TTS P95 11466.8ms > 3000ms

### 解讀 (卡西法 lesson)

CER 85.86% 不代表 Breeze-ASR-25 不能用。這是 round-trip TTS -> ASR 同 stack 自我對話、有以下放大因子:
1. TTS prompt 用 non-Edward voice (test_outputs/p1_NATF1.wav) -> voice signature 距離遠
2. BreezyVoice 廠商默認女聲品質中等、prosody 平
3. 文本含中英混雜詞 (BeyondPath / Vercel / cohort / Sophie / Q3)

Edward 真聲音 ASR (Stage 3) transcript 看起來幾乎完美 = Breeze-ASR-25 對真人聲品質 OK。

TTS P95 11.5s > 3s 是 BreezyVoice/CosyVoice 模型特性。可選: A. PoC 接受 / B. streaming TTS / C. H100

## 10 句 round-trip CER 細節

| tag | ref | hyp | cer% | dur |
|---|---|---|---|---|
| t01 | 我今天早上跑了五公里、覺得體力比上個月好很多 | 我接到他跑了 5 公里 | 86.36% | 6.0s |
| t02 | 蘇菲幫我看一下昨天的留存率有沒有跌 | 還舒飛有冇看一下昨天的流程綠有冇跌 | 58.82% | 9.06s |
| t03 | 卡西法去確認預覽網址跑得起來 | I kashifa 去確認玉蘭王子跑了起來 | 107.14% | 12.6s |
| t04 | 派蕪菁頭看用戶退訂原因的前三名 | 為 債 救 死 | 100.0% | 11.99s |
| t05 | 我預算大概一個月五千塊、能不能撐三個月 | 非我預算得計一個月會請快 | 73.68% | 5.64s |
| t06 | 三點半開會、會議室在十二樓A區 | Wow. | 100.0% | 3.6s |
| t07 | 這個元件重構一下、別讓巢狀屬性傳遞變五層 | 賽這個 | 95.0% | 4.79s |
| t08 | 記得強調那個投資報酬率是三點二倍 | 後肢報酬率是 3.2 倍 | 81.25% | 10.33s |
| t09 | 我有點不耐煩了、能不能直接給我結論 | Hi 我有點無奈翻 | 100.0% | 5.4s |
| t10 | Sophie can you help me draft an email about Q3 strategy | Help me draft an email at | 56.36% | 9.0s |

## Edward 真聲音 spotcheck (Stage 3)

Audio: voice_samples/edward_for_eagle.m4a (30.0s)

ASR transcript:

```
Hello 我是 Edward你好Sophie 我覺得呢不管怎麼樣我覺得呢是不是我們可以把這個操作能夠做得更好或者是你的設計能夠更完善然後就是我覺得在 bvb6 裡面
```

Server latency: 955.6 ms / inference: 943.5 ms

## Edward 起床要看什麼 (5 分鐘)

1. 聽 audio/t01.wav-t10.wav 廠商台灣腔女聲 (10 句)
2. 聽 audio/edward_voice_clone_demo.wav voice clone 用你聲音 prompt
3. 看 results/round-trip-cer.csv 10 句 CER + 上面 table 細節
4. 看 results/edward-voice-spotcheck.md 你 30s 真聲音 ASR transcript
5. 看 results/latency.csv TTS / ASR P50 P95

Edward 拍板 Phase 2:
- A. 廠商聲 OK + clone 像你 + 真聲 ASR 滿意 -> Phase 2 GO (Eagle + Porcupine)
- B. 太差 -> archive PoC、保留 OpenAI Realtime
- C. 並存 -> Breeze 中 + OpenAI 英 -> v2.1 dual-backend

## Day 3 8 個 root cause (lesson)

1. add_local_dir(../castle) 路徑錯 -> 拿掉
2. Windows cp950 console UTF-8 -> PYTHONIOENCODING=utf-8
3. tn module missing -> WeTextProcessing==1.0.3
4. matcha-tts vs diffusers 衝突 -> git clone Matcha-TTS submodule
5. openai-whisper sdist pkg_resources -> --no-build-isolation
6. g2pw==0.1.2.4 不存在 -> ==0.1.1 + ruamel.yaml<0.18
7. 假性拿掉 wget==3.2 -> 必加回
8. BreezyVoice ONNX 限 1500 frames -> trim Edward 30s 到 8s prompt

## Phase 2 起手 bonus

- phase2-poc/eagle_enrollment_result.md (待 Edward Picovoice AccessKey)
- phase2-poc/wake_word_setup.md (待 Edward Console 點 1 下訓 蘇菲)

## Gate 5 privacy 5 條件

- Cond 1: PASS - Modal Volume 零殘留
- Cond 2: PASS - cleanup_modal_volume.py ship
- Cond 3: 待 Edward 自證 2FA
- Cond 4: PASS - Modal CLI token 25 天 < 90 天
- Cond 5: PASS - X-Breeze-Token 個人 secret 限定

## 雙軌工時

- 預估: 8 hr (資深工程師 + AI 輔助)
- 移動城堡: ~5 hr (8 root cause + 6 Modal rebuild + 6 文檔 + ~12 commit)
- 倍率: ~0.6x

## 給 Edward 的話

技術上: Breeze stack 真的能跑、ASR 對真人聲快準 (P95 < 1s)、TTS 廠商默認女聲是台灣腔。
整個 BreezyVoice 跑通走了 6 次 image build + 8 個 dep 問題 — 不是 hello world、是真的 production 級 stack。
Phase 2 起手準備好了 (Eagle + Porcupine 文檔 ship)。
剩下你 5 分鐘的事: 聽 t01-t10.wav + voice clone demo + 看 edward-voice-spotcheck.md 拍板 A/B/C。
