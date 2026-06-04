#!/usr/bin/env python3
"""Ratio of user-authored tokens vs Claude-generated tokens across transcripts.

Claude side is authoritative: sum of `usage.output_tokens` per assistant turn
(this is everything Claude generated that turn — visible text + tool-call inputs
+ thinking). User side is estimated from authored prompt text via a chars/4
heuristic (Anthropic English ≈ 3.5–4 chars/token); a words*1.3 cross-check is
also printed. Dedups by uuid so resumed sessions don't double-count. Splits
main-thread sessions from subagent/workflow generation.

Usage:  py -3 tools/token-ratio.py
"""
from __future__ import annotations
import json, re
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
SYSREMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
IDE_WRAP = re.compile(r"<ide_[\w]+>.*?</ide_[\w]+>", re.DOTALL)
CMD_NAME = re.compile(r"<command-name>(.*?)</command-name>", re.DOTALL)
CMD_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)
NOISE = ("<task-notification>", "[Request interrupted")


def user_text(content):
    if isinstance(content, str):
        raw = content
    elif isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "tool_result":
                    return None
                if b.get("type") == "text" and b.get("text"):
                    parts.append(b["text"])
        raw = "\n".join(parts)
    else:
        return None
    if not raw or raw.lstrip().startswith(NOISE):
        return None
    m = CMD_NAME.search(raw)
    if m:
        a = CMD_ARGS.search(raw)
        return f"{m.group(1).strip()} {(a.group(1).strip() if a else '')}".strip()
    raw = IDE_WRAP.sub("", SYSREMINDER.sub("", raw)).strip()
    return raw or None


def assistant_text(content):
    """Visible text + tool_use input, for an apples-to-apples char estimate."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text" and b.get("text"):
            parts.append(b["text"])
        elif b.get("type") == "thinking" and b.get("thinking"):
            parts.append(b["thinking"])
        elif b.get("type") == "tool_use":
            parts.append(json.dumps(b.get("input", "")))
    return "\n".join(parts)


def acc():
    return {"user_chars": 0, "user_words": 0, "user_msgs": 0,
            "out_tokens": 0, "asst_msgs": 0, "asst_chars": 0,
            "in_tokens": 0, "cache_read": 0, "cache_create": 0}


def main():
    main_t, sub_t = acc(), acc()
    seen = set()
    for f in PROJECTS.rglob("*.jsonl"):
        is_sub = "/subagents/" in f.as_posix() or "/workflows/" in f.as_posix()
        bucket = sub_t if is_sub else main_t
        try:
            fh = f.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"user"' not in line and '"assistant"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = d.get("type")
                uuid = d.get("uuid")
                if uuid and uuid in seen:
                    continue
                msg = d.get("message")
                if not isinstance(msg, dict):
                    continue
                if t == "user":
                    # Human-authored ONLY: skip subagent/workflow files, skip
                    # sidechains (Task prompts Claude wrote), skip non-external.
                    if is_sub or d.get("isSidechain") or d.get("isMeta"):
                        continue
                    ut = d.get("userType")
                    if ut and ut != "external":
                        continue
                    txt = user_text(msg.get("content"))
                    if not txt:
                        continue
                    if uuid:
                        seen.add(uuid)
                    bucket["user_chars"] += len(txt)
                    bucket["user_words"] += len(txt.split())
                    bucket["user_msgs"] += 1
                elif t == "assistant":
                    u = msg.get("usage") or {}
                    if uuid:
                        seen.add(uuid)
                    bucket["out_tokens"] += u.get("output_tokens", 0) or 0
                    bucket["in_tokens"] += u.get("input_tokens", 0) or 0
                    bucket["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
                    bucket["cache_create"] += u.get("cache_creation_input_tokens", 0) or 0
                    bucket["asst_msgs"] += 1
                    bucket["asst_chars"] += len(assistant_text(msg.get("content")))

    def report(name, b):
        u4 = b["user_chars"] / 4
        uw = b["user_words"] * 1.3
        print(f"\n===== {name} =====")
        print(f"user prompts: {b['user_msgs']:,}   words: {b['user_words']:,}   chars: {b['user_chars']:,}")
        print(f"  user tokens (est chars/4): {u4:,.0f}   (cross-check words*1.3: {uw:,.0f})")
        print(f"assistant turns: {b['asst_msgs']:,}")
        print(f"  Claude OUTPUT tokens (authoritative usage): {b['out_tokens']:,}")
        print(f"  Claude authored chars: {b['asst_chars']:,}  (est chars/4: {b['asst_chars']/4:,.0f})")
        print(f"context processed: input={b['in_tokens']:,}  cache_read={b['cache_read']:,}  cache_create={b['cache_create']:,}")
        if u4 > 0:
            print(f"  >>> ratio user:claude(output)  = 1 : {b['out_tokens']/u4:,.1f}")
            print(f"  >>> ratio user:claude(authored text) = 1 : {b['asst_chars']/b['user_chars']:,.1f}")
        return u4

    mu = report("MAIN THREAD (your sessions)", main_t)
    _ = report("SUBAGENTS + WORKFLOWS (Claude you spawned)", sub_t)

    # Human tokens come ONLY from the main thread now (sub bucket user_* is ~0).
    human = mu  # est chars/4
    human_lo = main_t["user_words"] * 1.3
    out_main = main_t["out_tokens"]
    out_all = main_t["out_tokens"] + sub_t["out_tokens"]
    print("\n===== HEADLINE =====")
    print(f"Your typed tokens (est): {human:,.0f}  (low cross-check {human_lo:,.0f})")
    print(f"Claude output — main thread:        {out_main:,}")
    print(f"Claude output — incl. subagents:    {out_all:,}")
    if human > 0:
        print(f"\n  ratio you : Claude (main thread only)      = 1 : {out_main/human:,.0f}")
        print(f"  ratio you : Claude (incl. subagents you ran) = 1 : {out_all/human:,.0f}")
        print(f"  (using low cross-check estimate: 1 : {out_all/human_lo:,.0f} .. {out_main/human_lo:,.0f})")


if __name__ == "__main__":
    main()
