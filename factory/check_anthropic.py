"""Anthropic 連線檢查 · 驗證 .env 裡的 ANTHROPIC_API_KEY (+ optional BASE_URL) 設好沒。

用法:
    python -m factory.check_anthropic

支援:
- 標準 Anthropic API (api.anthropic.com) · 只設 ANTHROPIC_API_KEY
- Azure AI Foundry / 主辦單位代理 · 多設 ANTHROPIC_BASE_URL + ANTHROPIC_MODEL_OVERRIDE

通過會看到 ✓ + Claude 的回應 + 估算的成本(這次 ping 約 $0.005-0.02)。
"""
from __future__ import annotations
import os
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    base_url = (os.getenv("ANTHROPIC_BASE_URL") or "").strip() or None
    model = (os.getenv("ANTHROPIC_MODEL_OVERRIDE") or "claude-sonnet-4-5").strip()

    print()
    print("=" * 60)
    print("  Anthropic / Claude 連線檢查")
    print("=" * 60)

    if not api_key:
        print("✗ ANTHROPIC_API_KEY 是空的 — 打開 .env 填入 key")
        return 1

    print(f"  api_key:   ***{api_key[-6:]}  (尾 6 碼)")
    print(f"  base_url:  {base_url or 'https://api.anthropic.com (default)'}")
    print(f"  model:     {model}")
    print()

    try:
        from anthropic import Anthropic
    except ImportError:
        print("✗ anthropic SDK 沒裝 — 跑 pip install anthropic")
        return 1

    kwargs = {}
    if base_url:
        kwargs["base_url"] = base_url
    client = Anthropic(**kwargs)

    print("⏳ ping 中(送一個小 prompt 確認 endpoint 回應)...")
    t0 = time.time()
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=80,
            messages=[{"role": "user", "content": "回我「OK」兩個字就好,不要解釋。"}],
        )
    except Exception as e:
        print(f"✗ Claude 呼叫失敗: {type(e).__name__}: {e}")
        # 給點線索
        msg = str(e).lower()
        if "401" in msg or "unauthorized" in msg or "invalid" in msg:
            print("  → 401/unauthorized:檢查 API key 是不是貼對(完整、沒空白)")
        elif "404" in msg or "not_found" in msg:
            print(f"  → 404:base_url 或 model 名字可能不對")
            print(f"     base_url = {base_url}")
            print(f"     model    = {model}")
        elif "timeout" in msg:
            print("  → timeout:Azure endpoint 慢/掛了,稍後再試")
        return 1
    dt = time.time() - t0

    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    usage = getattr(resp, "usage", None)
    in_tok = getattr(usage, "input_tokens", 0) if usage else 0
    out_tok = getattr(usage, "output_tokens", 0) if usage else 0

    print(f"✓ 認證成功 · 模型回應:「{text.strip()}」")
    print()
    print(f"  耗時:       {dt:.2f} 秒")
    print(f"  input/output: {in_tok} / {out_tok} tokens")
    if "opus" in model.lower():
        est = in_tok * 15e-6 + out_tok * 75e-6
    elif "sonnet" in model.lower():
        est = in_tok * 3e-6 + out_tok * 15e-6
    else:
        est = in_tok * 0.25e-6 + out_tok * 1.25e-6
    print(f"  本次成本:   ≈ ${est:.4f} (USD)")
    print()
    print("→ 接通完成 · Factory 可以隨時切到 real 模式跑")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
