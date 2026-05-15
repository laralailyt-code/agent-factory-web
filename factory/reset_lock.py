"""factory/reset_lock.py — 緊急救援:清掉 Factory 卡住的 lock 檔 + 殘留 python 進程。

跑法:
    python -m factory.reset_lock

什麼時候用:
- Telegram bot 回覆「Factory 已經有一個 job 在跑」但你沒在跑
- 想完全重置 bot 狀態
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path


LOCK_PATH = Path("generated") / ".telegram_factory.lock"


def _utf8_stdout():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _kill_stale_pythons() -> int:
    """殺掉今天啟動的所有 python 進程(避免 zombie 抓住 lock 檔)。
    回傳殺掉幾個。
    """
    if sys.platform != "win32":
        print("  (非 Windows · 跳過 python 進程清掃)")
        return 0

    killed = 0
    try:
        # PowerShell: 找今天啟動的 python.exe 並結束
        cmd = [
            "powershell", "-NoProfile", "-Command",
            "Get-Process python -ErrorAction SilentlyContinue | "
            "Where-Object { $_.StartTime -gt (Get-Date).Date } | "
            "ForEach-Object { Write-Output $_.Id; Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                pid = int(line)
                if pid != os.getpid():  # 別殺自己
                    killed += 1
                    print(f"  ✓ 殺掉 PID {pid}")
    except Exception as e:
        print(f"  ⚠️ 殺 python 進程失敗: {type(e).__name__}: {e}")
    return killed


def main() -> int:
    _utf8_stdout()

    print()
    print("=" * 60)
    print("  Factory 緊急重置")
    print("=" * 60)

    print("\n[1/2] 殺掉今天啟動的 python 進程...")
    killed = _kill_stale_pythons()
    if killed == 0:
        print("  (沒有殘留 python 進程)")

    print("\n[2/2] 刪除 lock 檔...")
    if LOCK_PATH.exists():
        try:
            LOCK_PATH.unlink()
            print(f"  ✓ 已刪除 {LOCK_PATH}")
        except Exception as e:
            print(f"  ✗ 刪除失敗: {type(e).__name__}: {e}")
            print(f"     可能還有 python 進程抓著 · 開工作管理員手動關")
            return 1
    else:
        print(f"  (lock 檔已不存在)")

    print()
    print("=" * 60)
    print("  完成 · 可以重新啟動 bot:")
    print("    python -m factory.bot")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
