#!/usr/bin/env python3
"""Quantitative stats over drafts/my-prompts.jsonl."""
import json, re, collections
from pathlib import Path

rows = [json.loads(l) for l in open(Path(__file__).resolve().parent.parent / "drafts" / "my-prompts.jsonl", encoding="utf-8")]
n = len(rows)
words = [len(r["text"].split()) for r in rows]
ws = sorted(words)
def pct(p): return ws[int(p/100*(n-1))]

print("COUNT:", n)
print(f"words: min {min(words)} median {pct(50)} p75 {pct(75)} p90 {pct(90)} max {max(words)} mean {round(sum(words)/n,1)}")
print(f"one-liners (<=12 words): {sum(1 for w in words if w<=12)} ({round(100*sum(1 for w in words if w<=12)/n)}%)")
print(f"medium (13-59): {sum(1 for w in words if 13<=w<=59)}")
print(f"long (>=60 words): {sum(1 for w in words if w>=60)}")

slash = [r["text"] for r in rows if r["text"].startswith("/")]
print(f"\nSLASH COMMAND MSGS: {len(slash)} ({round(100*len(slash)/n)}%)")
for c, k in collections.Counter(re.match(r"(/\S+)", s).group(1) for s in slash).most_common(25):
    print(f"   {c}  {k}")

print("\nPROJECT (cwd basename):")
def base(p):
    p = p.replace("\\", "/").rstrip("/")
    return p.split("/")[-1] if p else "?"
for p, k in collections.Counter(base(r["cwd"]) for r in rows).most_common(15):
    print(f"   {p}  {k}")

print("\nFIRST WORD (lowercased, non-slash):")
fw = collections.Counter(r["text"].split()[0].lower().strip(",.:") for r in rows if not r["text"].startswith("/") and r["text"].split())
for w, k in fw.most_common(30):
    print(f"   {w}  {k}")

print("\nENDS WITH '?':", sum(1 for r in rows if r["text"].rstrip().endswith("?")))

# politeness / hedging / directive markers
def count_contains(pat):
    rx = re.compile(pat, re.I)
    return sum(1 for r in rows if rx.search(r["text"]))
markers = {
    "please": r"\bplease\b",
    "can you / could you": r"\b(can|could) you\b",
    "thanks/thank you": r"\bthank",
    "let's": r"\blet'?s\b",
    "don't / do not": r"\bdon'?t\b|\bdo not\b",
    "make sure / ensure": r"\bmake sure\b|\bensure\b",
    "should": r"\bshould\b",
    "actually": r"\bactually\b",
    "wait": r"\bwait\b",
    "no, / nope / wrong": r"^\s*(no|nope|wrong)\b|\bthat'?s wrong\b",
    "why": r"\bwhy\b",
    "explain": r"\bexplain\b",
    "ultrathink/think": r"\b(ultrathink|think hard|think deeply|keep thinking)\b",
    "step back": r"\bstep back\b",
    "I want / I'd like": r"\bI want\b|\bI'?d like\b|\bI need\b",
    "first / then / finally (seq)": r"\bfirst,?\b.*\bthen\b",
    "for each / every": r"\bfor each\b|\bfor every\b",
    "ALLCAPS emphasis word": r"\b[A-Z]{4,}\b",
    "code/backtick block": r"`",
    "@file mention": r"(?:^|\s)@[\w./\\-]+",
    "url": r"https?://",
}
print("\nMARKERS (msgs containing):")
for name, pat in markers.items():
    print(f"   {name}: {count_contains(pat)}")
