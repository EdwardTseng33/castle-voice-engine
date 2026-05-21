# breeze_poc/cleanup_modal_volume.py
# PoC 結束驗證腳本 (Gate 5 條件 2)
#
# 給 Edward 1 行跑、確認 Modal Volume 零殘留 (本 PoC 設計上不該有任何 Volume、
# 此腳本是 belt + suspenders、跑完該回報 "No volumes named breeze*" 才算 pass)
#
# 用法 (PoC 結束、7 天內):
#   py breeze_poc/cleanup_modal_volume.py
#
# 預期輸出:
#   ✅ Pass: 沒找到 breeze-* 開頭的 Modal Volume (隱私架構符合 Gate 5 條件 1)
#
# 若意外找到:
#   ⚠ Found N volume(s) - 請手動跑 `modal volume delete <name>` 清掉

import subprocess
import sys
import re


def main() -> int:
    print("[cleanup] 列出當前帳號所有 Modal Volume...")
    result = subprocess.run(
        ["py", "-m", "modal", "volume", "list"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"[cleanup] FAIL: modal volume list 失敗")
        print(result.stderr)
        return 1

    output = result.stdout
    print(output)

    # 找 breeze 開頭的 volume
    breeze_volumes = re.findall(r"^\s*(breeze[\w\-]*)", output, re.MULTILINE)

    if not breeze_volumes:
        print()
        print("[cleanup] Pass: 沒找到 breeze-* 開頭的 Modal Volume")
        print("[cleanup] Gate 5 條件 1 (audio never persisted) 驗證通過")
        return 0
    else:
        print()
        print(f"[cleanup] Found {len(breeze_volumes)} volume(s) needing review:")
        for v in breeze_volumes:
            print(f"   - {v}")
        print()
        print("[cleanup] 建議動作:")
        print("   1. 先確認 volume 內容: py -m modal volume ls <name>")
        print("   2. 若確認非生產資料: py -m modal volume delete <name>")
        print("   3. 再跑一次本 script 確認清空")
        return 2


if __name__ == "__main__":
    sys.exit(main())
