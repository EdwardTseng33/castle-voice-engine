# breeze_poc/register_eagle_speaker.py
# Day 5 task · Picovoice Eagle 聲紋註冊 Edward
#
# 用法:
#   1. 取得 Picovoice ACCESS KEY (個人版免費 / PoC OK): https://picovoice.ai/
#   2. 設定環境變數: $env:PV_ACCESS_KEY="..."
#   3. 先用 app_breeze.py /breeze/audio/preprocess 把 m4a 轉成 WAV 16kHz mono
#      (或本地 ffmpeg、看 Day 1 哪條路通)
#   4. py breeze_poc/register_eagle_speaker.py edward_for_eagle.wav
#
# 輸出:
#   - edward_speaker_profile.bin (Eagle 聲紋指紋檔、~kB)
#   - 給 /breeze/eagle/verify endpoint 認 Edward 用
#
# Day 1 stub: 先寫框架、Day 5 開啟實際 enroll 邏輯
# (Day 1 不執行此檔、僅放著)

import sys
from pathlib import Path


def main(wav_path: str) -> int:
    wav = Path(wav_path)
    if not wav.exists():
        print(f"[eagle] FAIL: {wav} 不存在")
        return 1

    print(f"[eagle] Day 5 將在此 enroll: {wav}")
    print("[eagle] Day 1 stub - 實際邏輯等 Day 5 開啟 pveagle 套件後接上")
    print("[eagle] 預計流程:")
    print("        1. pveagle.create_profiler(access_key=PV_ACCESS_KEY)")
    print("        2. profiler.enroll(audio_frames)  # need ~25s of speech")
    print("        3. profile_bytes = profiler.export()")
    print("        4. write to edward_speaker_profile.bin")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: py register_eagle_speaker.py <wav_path>")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
