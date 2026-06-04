"""Estimate weekly Claude Code API spend from session logs in ~/.claude/projects/."""
import json
import glob
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import matplotlib.pyplot as plt

# Per-million-token prices (USD). Cache-creation 1h is treated as 2x base input.
PRICING = {
    "opus":   {"in": 15.00, "out": 75.00, "cache_5m": 18.75, "cache_1h": 30.00, "cache_read": 1.50},
    "sonnet": {"in":  3.00, "out": 15.00, "cache_5m":  3.75, "cache_1h":  6.00, "cache_read": 0.30},
    "haiku":  {"in":  1.00, "out":  5.00, "cache_5m":  1.25, "cache_1h":  2.00, "cache_read": 0.10},
}
LONG_CTX_MULTIPLIER = 2.0
LONG_CTX_THRESHOLD = 200_000


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
    # Fall back to lumping all cache creation into 5m if breakdown missing.
    if cc_5m + cc_1h == 0:
        cc_5m = cc

    # Apply long-context surcharge to non-cache-read tokens when total context > 200k.
    total_ctx = inp + cr + cc
    mult = LONG_CTX_MULTIPLIER if total_ctx > LONG_CTX_THRESHOLD else 1.0

    cost = 0.0
    cost += inp   * p["in"]        * mult / 1_000_000
    cost += out   * p["out"]       * mult / 1_000_000
    cost += cc_5m * p["cache_5m"]  * mult / 1_000_000
    cost += cc_1h * p["cache_1h"]  * mult / 1_000_000
    cost += cr    * p["cache_read"]        / 1_000_000   # cache read not surcharged
    return cost


def week_start(dt: datetime) -> datetime:
    """Monday 00:00 UTC of the week containing dt."""
    d = dt.astimezone(timezone.utc)
    monday = d - timedelta(days=d.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def main():
    log_root = os.path.expanduser("~/.claude/projects")
    files = glob.glob(os.path.join(log_root, "*", "*.jsonl"))
    print(f"Scanning {len(files)} session files...")

    # Last 5 weeks ending the current week.
    now = datetime.now(timezone.utc)
    current_week = week_start(now)
    weeks = [current_week - timedelta(weeks=i) for i in range(4, -1, -1)]
    week_set = set(weeks)

    # spend[week_start][family] = usd
    spend = defaultdict(lambda: defaultdict(float))
    tokens = defaultdict(lambda: defaultdict(int))  # raw token counts for reference

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
                    ws = week_start(dt)
                    if ws not in week_set:
                        continue
                    spend[ws][fam] += cost_for(model, usage)
                    tokens[ws][fam] += (
                        (usage.get("input_tokens") or 0)
                        + (usage.get("output_tokens") or 0)
                        + (usage.get("cache_read_input_tokens") or 0)
                        + (usage.get("cache_creation_input_tokens") or 0)
                    )
        except Exception as e:
            print(f"skip {path}: {e}")

    # Print table
    families = ["opus", "sonnet", "haiku"]
    print(f"\n{'Week starting':<14} " + " ".join(f"{f:>10}" for f in families) + f" {'total':>10}")
    print("-" * 60)
    grand = 0.0
    for w in weeks:
        row = [spend[w][f] for f in families]
        total = sum(row)
        grand += total
        print(f"{w.date().isoformat():<14} " + " ".join(f"${v:>9.2f}" for v in row) + f" ${total:>9.2f}")
    print("-" * 60)
    print(f"{'5-week total':<14} " + " " * (11 * 3) + f" ${grand:>9.2f}")

    # Plot stacked bar
    fig, ax = plt.subplots(figsize=(10, 6))
    labels = [w.date().strftime("%b %d") for w in weeks]
    colors = {"opus": "#7B61FF", "sonnet": "#F5A623", "haiku": "#4A90E2"}
    bottoms = [0.0] * len(weeks)
    for fam in families:
        values = [spend[w][fam] for w in weeks]
        ax.bar(labels, values, bottom=bottoms, label=fam.capitalize(),
               color=colors[fam], edgecolor="white", linewidth=0.5)
        bottoms = [b + v for b, v in zip(bottoms, values)]

    for i, total in enumerate(bottoms):
        ax.text(i, total, f"${total:.0f}", ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax.set_ylabel("Estimated cost (USD)")
    ax.set_xlabel("Week starting (Mon, UTC)")
    ax.set_title(f"Claude Code weekly spend by model — last 5 weeks (as of {now.date().isoformat()})")
    ax.legend(title="Model family", loc="upper left")
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.set_ylim(top=max(bottoms) * 1.15)
    plt.tight_layout()

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "weekly-spend.png")
    out = os.path.abspath(out)
    plt.savefig(out, dpi=120)
    print(f"\nChart written to {out}")


if __name__ == "__main__":
    main()
