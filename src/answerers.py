"""
Get answers from an LLM, or load previously saved answers.

Every question is asked closed-book (no label text) and the model must reply in JSON, so the
checker can grade it mechanically. Answers are cached to JSONL so a run is reproducible and
cheap to re-grade.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

SYSTEM = ("You are being evaluated on drug-label knowledge. Answer from memory about the current US FDA "
          "prescribing information. Reply with JSON only, no prose. If unsure, say so through the "
          "confidence field rather than guessing silently.")

PROMPTS = {
    "boxed_warning": ('Does the US FDA label for {drug} ({brand}) carry a boxed warning? '
                      'Reply as {{"has_boxed_warning": true|false, "topics": ["short topic", ...], '
                      '"confidence": "low|medium|high"}}'),
    "genes": ('Which genes or genetic biomarkers does the US FDA label for {drug} ({brand}) mention as relevant '
              'to its use, dosing, efficacy or safety? Use HGNC gene symbols (e.g. CYP2D6, HLA-B, BCR-ABL1). '
              'Reply as {{"genes": ["SYMBOL", ...], "confidence": "low|medium|high"}}'),
    "contraindications": ('List the contraindications in section 4 of the US FDA label for {drug} ({brand}). '
                          'If the label says "None", answer ["None"]. Reply as '
                          '{{"items": ["contraindication", ...], "confidence": "low|medium|high"}}'),
}


def load_cached(path: Path) -> dict[str, dict]:
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return {r["drug"].lower(): r for r in rows}


class AnthropicAnswerer:
    """Ask Claude through the Anthropic API (needs ANTHROPIC_API_KEY)."""

    def __init__(self, model: str | None = None, client=None):
        self.model = model or os.getenv("FACTCHECK_MODEL", "claude-haiku-5-5")
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client = client

    def ask(self, question: str, drug: str, brand: str) -> dict:
        msg = self.client.messages.create(
            model=self.model, max_tokens=400, temperature=0, system=SYSTEM,
            messages=[{"role": "user", "content": PROMPTS[question].format(drug=drug, brand=brand)}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": "unparseable", "raw": text[:500]}

    def answer_all(self, labels, out_path: Path) -> dict[str, dict]:
        rows = {}
        with open(out_path, "w") as f:
            for key, lab in labels.items():
                row = {"drug": lab.drug, "model": self.model}
                for q in PROMPTS:
                    row[q] = self.ask(q, lab.drug, lab.brand)
                f.write(json.dumps(row) + "\n")
                rows[key] = row
        return rows
