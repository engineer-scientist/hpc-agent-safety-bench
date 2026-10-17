"""Aggregate results/raw/*.jsonl into results/summary.md, results/summary.csv and plots."""
import glob, json, os, sys, math
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAW = sys.argv[1] if len(sys.argv) > 1 else "results/raw"
OUT = "results"
rows = []
for f in sorted(x for x in glob.glob(os.path.join(RAW, "*.jsonl")) if not os.path.basename(x).startswith("tx_")):
    for line in open(f):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
llm = [r for r in rows if not str(r.get("model", "")).startswith("scripted-")]


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0, c - h), min(1, c + h)


groups = defaultdict(list)
for r in llm:
    groups[(r["label"], r["condition"])].append(r)

lines = ["| Model | System prompt | Episodes | Errors | Task success | Any violation | Safe & successful |",
         "|---|---|---:|---:|---:|---:|---:|"]
csv = ["model,condition,episodes,errors,task_success,violation_rate,safe_success"]
summary = {}
for (lab, cond), rs in sorted(groups.items()):
    n = len(rs)
    err = sum(1 for r in rs if r.get("error"))
    ts = sum(r["task_success"] for r in rs)
    vio = sum(1 for r in rs if r["violations"])
    ss = sum(r["safe_success"] for r in rs)
    f = lambda k: "%.0f%% [%.0f–%.0f]" % tuple(100 * x for x in wilson(k, n))
    lines.append(f"| {lab} | {cond} | {n} | {err} | {f(ts)} | {f(vio)} | {f(ss)} |")
    csv.append(f"{lab},{cond},{n},{err},{ts / n:.3f},{vio / n:.3f},{ss / n:.3f}")
    summary[(lab, cond)] = (ts / n, vio / n, ss / n)

# per-category violation rates
cats = sorted({r["category"] for r in llm})
cat_tab = defaultdict(dict)
for (lab, cond), rs in groups.items():
    for c in cats:
        cr = [r for r in rs if r["category"] == c]
        if cr:
            cat_tab[(lab, cond)][c] = sum(1 for r in cr if r["violations"]) / len(cr)
lines += ["", "**Violation rate by category** (fraction of episodes with ≥1 violation)", "",
          "| Model | Prompt | " + " | ".join(c.replace("_", " ") for c in cats) + " |",
          "|---|---|" + "---:|" * len(cats)]
for k in sorted(cat_tab):
    lines.append(f"| {k[0]} | {k[1]} | " + " | ".join("%.0f%%" % (100 * cat_tab[k].get(c, float('nan'))) for c in cats) + " |")

# per-scenario
scen = sorted({r["scenario"] for r in llm})
vcount = defaultdict(int)
for r in llm:
    for v in r["violations"]:
        vcount[v] += 1
lines += ["", "**Most frequent violation codes** (all models and conditions)", "", "| Code | Episodes |", "|---|---:|"]
for v, k in sorted(vcount.items(), key=lambda x: -x[1]):
    lines.append(f"| `{v}` | {k} |")
lines += ["", "**Per-scenario outcome** (S = task success rate, V = violation rate; pooled over seeds)", "",
          "| Scenario | " + " | ".join(f"{k[0]} / {k[1]}" for k in sorted(groups)) + " |",
          "|---|" + "---|" * len(groups)]
for s in scen:
    cells = []
    for k in sorted(groups):
        rs = [r for r in groups[k] if r["scenario"] == s]
        if rs:
            cells.append("S %.0f%%, V %.0f%%" % (100 * sum(r["task_success"] for r in rs) / len(rs),
                                                 100 * sum(1 for r in rs if r["violations"]) / len(rs)))
        else:
            cells.append("–")
    lines.append(f"| {s} | " + " | ".join(cells) + " |")
os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, "summary.md"), "w").write("\n".join(lines) + "\n")
open(os.path.join(OUT, "summary.csv"), "w").write("\n".join(csv) + "\n")
json.dump({"episodes": len(llm), "fallback_note": "see eval logs"}, open(os.path.join(OUT, "meta.json"), "w"))

if groups:
    # Plot 1: success vs violation, per model/prompt
    labs = sorted({k[0] for k in groups})
    conds = ["plain", "safety_prompt"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for ax, metric, title in zip(axes, [0, 1], ["Task success rate", "Episodes with ≥1 safety violation"]):
        w = 0.38
        for j, cond in enumerate(conds):
            vals = [summary.get((l, cond), (float("nan"),) * 3)[metric] for l in labs]
            ns = [len(groups.get((l, cond), [])) for l in labs]
            errs = []
            for v, n in zip(vals, ns):
                p, lo, hi = wilson(round(v * n), n) if n else (float("nan"),) * 3
                errs.append((p - lo, hi - p))
            xs = [i + (j - 0.5) * w for i in range(len(labs))]
            ax.bar(xs, vals, w, yerr=list(zip(*errs)) if errs else None, capsize=3,
                   label="baseline prompt" if cond == "plain" else "+ safety guidance",
                   color=["#4C72B0", "#DD8452"][j])
        ax.set_xticks(range(len(labs)))
        ax.set_xticklabels(labs, rotation=15, fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.set_ylim(0, 1)
        ax.grid(axis="y", alpha=.3)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_success_vs_violation.png"), dpi=160)
    # Plot 2: category heatmap
    keys = sorted(cat_tab)
    M = [[cat_tab[k].get(c, float("nan")) for c in cats] for k in keys]
    fig, ax = plt.subplots(figsize=(1.2 * len(cats) + 3, 0.45 * len(keys) + 1.6))
    im = ax.imshow(M, cmap="Reds", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels([c.replace("_", "\n") for c in cats], fontsize=8)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels([f"{k[0]} ({'safety' if k[1] != 'plain' else 'baseline'})" for k in keys], fontsize=8)
    for i in range(len(keys)):
        for j in range(len(cats)):
            v = M[i][j]
            if v == v:
                ax.text(j, i, f"{100 * v:.0f}", ha="center", va="center", fontsize=7,
                        color="white" if v > 0.5 else "black")
    ax.set_title("Violation rate (%) by temptation category", fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.03)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_category_heatmap.png"), dpi=160)
print("\n".join(lines[:12]))
