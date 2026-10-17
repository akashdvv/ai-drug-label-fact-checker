"""
Fact-check model answers against FDA labels and write a report.

Usage:
    python src/run.py                                   # grade the saved answers
    python src/run.py --answers data/answers/other.jsonl
    python src/run.py --live --model claude-haiku-5-5   # ask a model now (needs ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from answerers import AnthropicAnswerer, load_cached
from checker import GRADERS
from labels import ROOT, load_all

RESULTS, IMAGES = ROOT / "results", ROOT / "images"
SCORE = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}
QNAMES = {"boxed_warning": "Boxed warning", "genes": "Pharmacogenomic genes", "contraindications": "Contraindications"}
VCOL = {"correct": "#1baf7a", "partial": "#eda100", "incorrect": "#e34948"}
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white", "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
    "text.color": INK, "xtick.color": INK_2, "ytick.color": INK_2, "axes.spines.top": False,
    "axes.spines.right": False, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
})


def grade(labels, answers) -> pd.DataFrame:
    rows, claims = [], []
    for key, lab in labels.items():
        if key not in answers:
            continue
        for q, fn in GRADERS.items():
            g = fn(lab, answers[key].get(q, {}))
            rows.append({"drug": lab.drug, "brand": lab.brand, "question": q, "verdict": g.verdict,
                         "score": SCORE[g.verdict], "confidence": g.confidence, "detail": g.detail,
                         "label_file": lab.source_file, "label_effective": lab.effective_time})
            for c in g.claims:
                claims.append({"drug": lab.drug, "question": q, **c})
    pd.DataFrame(claims).to_csv(RESULTS / "claims.csv", index=False)
    return pd.DataFrame(rows)


def charts(df: pd.DataFrame, claims: pd.DataFrame, model_name: str) -> None:
    IMAGES.mkdir(exist_ok=True)
    # 1. verdict mix per question type (stacked horizontal bars, 2px surface gaps)
    fig, ax = plt.subplots(figsize=(9, 3.2))
    order = list(QNAMES)
    left = np.zeros(len(order))
    for v in ["correct", "partial", "incorrect"]:
        vals = np.array([(df[df.question == q].verdict == v).sum() for q in order])
        ax.barh([QNAMES[q] for q in order], vals, left=left, color=VCOL[v], height=0.55,
                edgecolor="white", linewidth=2, label=v.capitalize())
        for i, (l, w) in enumerate(zip(left, vals)):
            if w >= 3:
                ax.text(l + w / 2, i, str(w), ha="center", va="center", color="white", fontsize=9, fontweight="bold")
        left += vals
    ax.invert_yaxis()
    ax.set_xlabel("Answers (50 drugs per question)")
    ax.set_title(f"{model_name}: verdicts against the FDA label")
    ax.legend(frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, -0.5), fontsize=9)
    fig.tight_layout()
    fig.savefig(IMAGES / "verdicts_by_question.png", dpi=150)
    plt.close(fig)

    # 2. calibration: accuracy by stated confidence
    levels = ["low", "medium", "high"]
    acc = [df[df.confidence == c].score.mean() * 100 for c in levels]
    n = [(df.confidence == c).sum() for c in levels]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.bar(levels, acc, color="#2a78d6", width=0.55)
    for i, (a, k) in enumerate(zip(acc, n)):
        ax.text(i, a + 1.5, f"{a:.0f}%  (n={k})", ha="center", fontsize=9, color=INK_2)
    ax.set_ylim(0, 112)
    ax.set_ylabel("Accuracy (%)")
    ax.set_xlabel("Model's stated confidence")
    ax.set_title("Is the model's confidence meaningful?")
    ax.yaxis.grid(True, color=GRID)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(IMAGES / "calibration.png", dpi=150)
    plt.close(fig)


def write_report(df: pd.DataFrame, claims: pd.DataFrame, model_name: str) -> str:
    lines = [f"# Fact-check report: {model_name}", "",
             f"{df.drug.nunique()} drugs × {df.question.nunique()} questions = {len(df)} answers, "
             "graded against FDA label text. Score: correct = 1, partial = 0.5, incorrect = 0.", "",
             "| Question | Correct | Partial | Incorrect | Score |", "|---|---|---|---|---|"]
    for q in QNAMES:
        d = df[df.question == q]
        lines.append(f"| {QNAMES[q]} | {(d.verdict == 'correct').sum()} | {(d.verdict == 'partial').sum()} | "
                     f"{(d.verdict == 'incorrect').sum()} | {d.score.mean():.0%} |")
    lines.append(f"| **All** | {(df.verdict == 'correct').sum()} | {(df.verdict == 'partial').sum()} | "
                 f"{(df.verdict == 'incorrect').sum()} | **{df.score.mean():.0%}** |")
    lines += ["", "## Every answer that was not fully correct", "",
              "| Drug | Question | Verdict | Confidence | What went wrong | Label evidence |", "|---|---|---|---|---|---|"]
    bad = claims[claims.status.isin(["unsupported", "partially_supported"])]
    for _, r in df[df.verdict != "correct"].iterrows():
        ev = bad[(bad.drug == r.drug) & (bad.question == r.question)]
        claim_txt = "; ".join(f"“{c}”" for c in ev.claim.head(2)) or "—"
        evidence = (ev.evidence.iloc[0] if len(ev) else "").replace("|", "/").replace("\n", " ")[:160]
        lines.append(f"| {r.drug} | {QNAMES[r.question]} | {r.verdict} | {r.confidence} | {r.detail} {claim_txt} | {evidence} |")
    text = "\n".join(lines) + "\n"
    (RESULTS / "REPORT.md").write_text(text)
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", default=str(ROOT / "data" / "answers" / "claude_closed_book.jsonl"))
    ap.add_argument("--live", action="store_true", help="ask the model now instead of loading saved answers")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    labels = load_all()
    if args.live:
        answerer = AnthropicAnswerer(args.model)
        out = ROOT / "data" / "answers" / f"{answerer.model}.jsonl"
        answers = answerer.answer_all(labels, out)
        model_name = answerer.model
        print(f"Saved live answers to {out.relative_to(ROOT)}")
    else:
        answers = load_cached(Path(args.answers))
        first = next(iter(answers.values()))
        model_name = first.get("model", "Claude (closed-book)")

    RESULTS.mkdir(exist_ok=True)
    df = grade(labels, answers)
    df.to_csv(RESULTS / "graded.csv", index=False)
    claims = pd.read_csv(RESULTS / "claims.csv")
    charts(df, claims, model_name)
    print(write_report(df, claims, model_name).split("## Every")[0])
    gene_claims = claims[(claims.question == "genes") & claims.status.isin(["supported", "unsupported"])]
    halluc = (gene_claims.status == "unsupported").mean()
    print(f"Gene claims: {len(gene_claims)} named, {halluc:.1%} not on the label (hallucinated)")
    by_conf = df.groupby("confidence").score.agg(["mean", "count"])
    print("Accuracy by stated confidence:\n", by_conf.round(3).to_string())


if __name__ == "__main__":
    main()
