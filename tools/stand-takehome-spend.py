"""Estimate daily Claude Code spend on the stand-takehome repo, May 14-17 (EDT)."""
import json
import glob
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import matplotlib.pyplot as plt

PRICING = {
    "opus":   {"in": 15.00, "out": 75.00, "cache_5m": 18.75, "cache_1h": 30.00, "cache_read": 1.50},
    "sonnet": {"in":  3.00, "out": 15.00, "cache_5m":  3.75, "cache_1h":  6.00, "cache_read": 0.30},
    "haiku":  {"in":  1.00, "out":  5.00, "cache_5m":  1.25, "cache_1h":  2.00, "cache_read": 0.10},
}
LONG_CTX_MULTIPLIER = 2.0
LONG_CTX_THRESHOLD = 200_000

# EDT is UTC-4 (DST in effect on May 14-17, 2026 / 2025).
EDT = timezone(timedelta(hours=-4))
PROJECT_DIR = "c--Users-HongM-Code-Projects-stand-takehome"


def family(model: str) -> str | None:
    if not model:
        return None
    m = model.lower()
    if "opus" in m:
        return "opus"
    if "sonnet" in m:
        return "sonnet"
    if "haiku" in m:
        return "haiku"
    return None


def cost_for(model: str, usage: dict) -> float:
    fam = family(model)
    if fam is None:
        return 0.0
    p = PRICING[fam]
    inp = usage.get("input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    cr = usage.get("cache_read_input_tokens", 0) or 0
    cc = usage.get("cache_creation_input_tokens", 0) or 0
    cc_detail = usage.get("cache_creation", {}) or {}
    cc_5m = cc_detail.get("ephemeral_5m_input_tokens", 0) or 0
    cc_1h = cc_detail.get("ephemeral_1h_input_tokens", 0) or 0
    if cc_5m + cc_1h == 0:
        cc_5m = cc

    total_ctx = inp + cr + cc
    mult = LONG_CTX_MULTIPLIER if total_ctx > LONG_CTX_THRESHOLD else 1.0

    cost = 0.0
    cost += inp   * p["in"]        * mult / 1_000_000
    cost += out   * p["out"]       * mult / 1_000_000
    cost += cc_5m * p["cache_5m"]  * mult / 1_000_000
    cost += cc_1h * p["cache_1h"]  * mult / 1_000_000
    cost += cr    * p["cache_read"]        / 1_000_000
    return cost


def main():
    log_root = os.path.expanduser("~/.claude/projects")
    project_path = os.path.join(log_root, PROJECT_DIR)
    files = glob.glob(os.path.join(project_path, "*.jsonl"))
    print(f"Scanning {len(files)} session files in {PROJECT_DIR}...")

    # Target days: May 14, 15, 16, 17 in EDT.
    days = [datetime(2026, 5, 14, tzinfo=EDT) + timedelta(days=i) for i in range(4)]
    day_keys = [d.date() for d in days]
    day_set = set(day_keys)

    spend = defaultdict(lambda: defaultdict(float))
    tokens = defaultdict(lambda: defaultdict(int))

    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    msg = d.get("message") or {}
                    model = msg.get("model")
                    usage = msg.get("usage")
                    if not (model and usage):
                        continue
                    fam = family(model)
                    if fam is None:
                        continue
                    ts = d.get("timestamp")
                    if not ts:
                        continue
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except Exception:
                        continue
                    local = dt.astimezone(EDT)
                    day = local.date()
                    if day not in day_set:
                        continue
                    spend[day][fam] += cost_for(model, usage)
                    tokens[day][fam] += (
                        (usage.get("input_tokens") or 0)
                        + (usage.get("output_tokens") or 0)
                        + (usage.get("cache_read_input_tokens") or 0)
                        + (usage.get("cache_creation_input_tokens") or 0)
                    )
        except Exception as e:
            print(f"skip {path}: {e}")

    families = ["opus", "sonnet", "haiku"]
    print(f"\n{'Date (EDT)':<12} " + " ".join(f"{f:>10}" for f in families) + f" {'total':>10}")
    print("-" * 56)
    grand = 0.0
    for day in day_keys:
        row = [spend[day][f] for f in families]
        total = sum(row)
        grand += total
        print(f"{day.isoformat():<12} " + " ".join(f"${v:>9.2f}" for v in row) + f" ${total:>9.2f}")
    print("-" * 56)
    print(f"{'4-day total':<12} " + " " * (11 * 3) + f" ${grand:>9.2f}")

    fig, ax = plt.subplots(figsize=(10, 6))
    labels = [d.strftime("%a %b %d") for d in day_keys]
    colors = {"opus": "#7B61FF", "sonnet": "#F5A623", "haiku": "#4A90E2"}
    bottoms = [0.0] * len(day_keys)
    for fam in families:
        values = [spend[day][fam] for day in day_keys]
        ax.bar(labels, values, bottom=bottoms, label=fam.capitalize(),
               color=colors[fam], edgecolor="white", linewidth=0.5)
        bottoms = [b + v for b, v in zip(bottoms, values)]

    for i, total in enumerate(bottoms):
        ax.text(i, total, f"${total:.2f}", ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax.set_ylabel("Estimated cost (USD)")
    ax.set_xlabel("Day (EDT)")
    ax.set_title("Claude Code spend on stand-takehome — May 14-17 (EDT)")
    ax.legend(title="Model family", loc="upper left")
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    if max(bottoms) > 0:
        ax.set_ylim(top=max(bottoms) * 1.15)
    plt.tight_layout()

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stand-takehome-spend.png")
    out = os.path.abspath(out)
    plt.savefig(out, dpi=120)
    print(f"\nChart written to {out}")


if __name__ == "__main__":
    main()
