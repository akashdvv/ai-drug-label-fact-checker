"""
Grade model answers against FDA label text.

Three question types, each with an explicit rule so every verdict is reproducible:

1. boxed_warning  - is there a boxed warning (exact check), and is each claimed topic
                    supported by the boxed-warning text (lexical support score)?
2. genes          - is each gene the model names actually mentioned anywhere on the label
                    (exact symbol/alias match)? Unmentioned genes = hallucinations.
3. contraindications - is each claimed contraindication supported by the label's
                    Contraindications section, and did the model say "None" correctly?

Verdicts: correct | partial | incorrect.  Every claim keeps the label sentence used as evidence.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from labels import Label, sentences

STOP = set("""a an and are as at be by for from has have in into is it its of on or that the this to
with within any all other such patients patient use used using known history drug drugs who which
when where than more less including include includes due caused cause e g eg i.e ie b x""".split())

# Normalise common clinical synonyms so wording differences aren't scored as errors.
SYNONYMS = {
    "maoi": "monoamine oxidase inhibitor", "maois": "monoamine oxidase inhibitor",
    "mi": "myocardial infarction", "cabg": "coronary artery bypass graft",
    "hbv": "hepatitis b virus", "hcv": "hepatitis c virus", "pml": "progressive multifocal leukoencephalopathy",
    "crs": "cytokine release syndrome", "icans": "immune effector cell-associated neurotoxicity syndrome",
    "aria": "amyloid related imaging abnormalities", "qtc": "qt", "cns": "central nervous system",
    "nsaids": "nsaid", "dcis": "ductal carcinoma in situ", "dvt": "deep vein thrombosis",
    "pe": "pulmonary embolism", "g6pd": "glucose-6-phosphate dehydrogenase",
    "suicidality": "suicidal thoughts behaviors", "suicidal": "suicidal",
    "neurological": "neurologic", "neurotoxicity": "neurologic toxicity",
}


def stem(tok: str) -> str:
    for suf in ("ies", "es", "s", "ing", "ed", "al", "ity"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            return tok[: -len(suf)]
    return tok


def tokens(text: str) -> list[str]:
    text = re.sub(r"\((\w+)\)(\w)", r"\1\2", text)          # "(OATP)1B1" -> "OATP1B1"
    text = text.lower().replace("‑", "-")
    words = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text)
    out = []
    for w in words:
        expanded = SYNONYMS.get(w, w)
        for part in re.split(r"[\s-]+", expanded):
            if part and part not in STOP and not part.isdigit() or (part.isdigit() and len(part) >= 2):
                out.append(stem(part))
    return out


def support(claim: str, evidence_text: str, drug_names: tuple[str, ...] = ()) -> tuple[float, str]:
    """Share of the claim's content words found in the evidence text, plus the best sentence.
    The drug's own name is ignored: labels usually say "the drug" or use the brand name instead."""
    own = {t for n in drug_names for t in tokens(n)}
    claim_toks = set(tokens(claim)) - own
    if not claim_toks:
        return 0.0, ""
    ev_toks = set(tokens(evidence_text))
    score = len(claim_toks & ev_toks) / len(claim_toks)
    best, best_overlap = "", -1
    for s in sentences(evidence_text):
        ov = len(claim_toks & set(tokens(s)))
        if ov > best_overlap:
            best, best_overlap = s, ov
    if score < 0.3:  # nothing matches well: show the start of the section instead of a random sentence
        best = re.sub(r"\s+", " ", evidence_text)[:300]
    return round(score, 2), best[:300]


def claim_verdict(score: float) -> str:
    return "supported" if score >= 0.6 else ("partially_supported" if score >= 0.3 else "unsupported")


def says_none(items: list[str]) -> bool:
    return not items or all(i.strip().lower() in {"none", "none.", "no contraindications"} for i in items)


def label_says_none(section: str) -> bool:
    body = re.sub(r"^\s*\d*\.?\s*CONTRAINDICATIONS\s*", "", section.strip(), flags=re.I)
    return bool(re.match(r"^(none|there are no contraindications)\b", body.strip(), re.I))


@dataclass
class Graded:
    drug: str
    question: str
    verdict: str
    confidence: str
    detail: str
    claims: list[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def grade_boxed(label: Label, ans: dict) -> Graded:
    claimed = bool(ans.get("has_boxed_warning"))
    conf = ans.get("confidence", "unknown")
    if claimed != label.has_boxed_warning:
        detail = ("Model said there is a boxed warning; the label has none." if claimed
                  else "Model said no boxed warning; the label has one.")
        return Graded(label.drug, "boxed_warning", "incorrect", conf, detail)
    if not claimed:
        return Graded(label.drug, "boxed_warning", "correct", conf, "Correctly said no boxed warning.")
    claims = []
    for topic in ans.get("topics", []):
        score, ev = support(topic, label.boxed_warning, (label.drug, label.brand))
        claims.append({"claim": topic, "support": score, "status": claim_verdict(score), "evidence": ev})
    n_sup = sum(c["status"] == "supported" for c in claims)
    n_bad = sum(c["status"] == "unsupported" for c in claims)
    verdict = "correct" if claims and n_bad == 0 and n_sup >= 1 else ("partial" if n_sup or not claims else "incorrect")
    return Graded(label.drug, "boxed_warning", verdict, conf,
                  f"Boxed warning present; {n_sup}/{len(claims)} topics supported.", claims)


def grade_genes(label: Label, ans: dict) -> Graded:
    conf = ans.get("confidence", "unknown")
    named = [g.upper() for g in ans.get("genes", [])]
    claims = []
    for g in named:
        if g in label.genes:
            claims.append({"claim": g, "status": "supported", "evidence": label.genes[g]})
        else:
            claims.append({"claim": g, "status": "unsupported", "evidence": "Gene not mentioned anywhere on the label."})
    # Verdict is about hallucination (precision): labels mention dozens of genes in passing
    # ("does not inhibit CYP1A2, CYP2C9..."), so "missed" genes are reported but not penalised.
    missed = sorted(set(label.genes) - set(named))
    n_bad = sum(c["status"] == "unsupported" for c in claims)
    if not named:
        verdict, detail = "correct", "Named no genes (abstained); nothing hallucinated."
    elif n_bad == 0:
        verdict, detail = "correct", "Every named gene appears on the label."
    elif n_bad < len(named):
        verdict, detail = "partial", f"{n_bad} of {len(named)} named genes are not on the label."
    else:
        verdict, detail = "incorrect", "None of the named genes appear on the label."
    g = Graded(label.drug, "genes", verdict, conf, detail, claims)
    g.claims.extend({"claim": m, "status": "missed", "evidence": label.genes[m]} for m in missed)
    return g


def grade_contraindications(label: Label, ans: dict) -> Graded:
    conf = ans.get("confidence", "unknown")
    items = ans.get("items", [])
    section, label_none = label.contraindications, label_says_none(label.contraindications)
    if says_none(items):
        if label_none:
            return Graded(label.drug, "contraindications", "correct", conf, "Correctly said there are none.")
        return Graded(label.drug, "contraindications", "incorrect", conf,
                      "Model said none; the label lists contraindications.",
                      [{"claim": "None", "status": "unsupported", "evidence": section[:300]}])
    if label_none:
        return Graded(label.drug, "contraindications", "incorrect", conf,
                      "Model listed contraindications; the label says none.",
                      [{"claim": i, "status": "unsupported", "evidence": section[:200]} for i in items])
    claims = []
    for it in items:
        score, ev = support(it, section, (label.drug, label.brand))
        claims.append({"claim": it, "support": score, "status": claim_verdict(score), "evidence": ev})
    n_sup = sum(c["status"] == "supported" for c in claims)
    n_bad = sum(c["status"] == "unsupported" for c in claims)
    verdict = "correct" if n_bad == 0 and n_sup == len(claims) else ("incorrect" if n_sup == 0 else "partial")
    return Graded(label.drug, "contraindications", verdict, conf,
                  f"{n_sup}/{len(claims)} listed contraindications supported by the label.", claims)


GRADERS = {"boxed_warning": grade_boxed, "genes": grade_genes, "contraindications": grade_contraindications}
