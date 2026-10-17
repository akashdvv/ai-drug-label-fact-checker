"""
Load FDA structured product labels (openFDA JSON) and extract the facts the checker needs:
the boxed warning, the contraindications section, and every pharmacogenomic gene mentioned.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL_DIR = ROOT / "data" / "labels"

# Pharmacogenomic / biomarker genes, with the aliases labels actually use.
# A gene counts as "on the label" only if its symbol or an explicit protein/variant name appears.
# Disease names alone (e.g. "sickle cell disease") deliberately do NOT count as a gene mention.
GENE_ALIASES: dict[str, list[str]] = {
    "CYP2D6": ["CYP2D6", "P450 2D6", "P450IID6"], "CYP2C19": ["CYP2C19", "P450 2C19"],
    "CYP2C9": ["CYP2C9", "P450 2C9"], "CYP1A2": ["CYP1A2", "P450 1A2"],
    "CYP3A5": ["CYP3A5"], "UGT1A1": ["UGT1A1"], "UGT2B17": ["UGT2B17"], "TPMT": ["TPMT"],
    "NUDT15": ["NUDT15"], "DPYD": ["DPYD", "dihydropyrimidine dehydrogenase"],
    "G6PD": ["G6PD", "glucose-6-phosphate dehydrogenase", "glucose 6-phosphate dehydrogenase"],
    "CYB5R3": ["CYB5R", "cytochrome b5 reductase", "cytochrome-b5 reductase", "cytochrome b 5 reductase"],
    "HLA-B": ["HLA-B"], "HLA-A": ["HLA-A"], "NAT2": ["NAT2"],
    "SLCO1B1": ["SLCO1B1", "OATP1B1"], "ABCG2": ["ABCG2", "BCRP"], "ABCB11": ["ABCB11", "BSEP"],
    "VKORC1": ["VKORC1"], "APOE": ["APOE", "ApoE", "apolipoprotein E"],
    "F5": ["factor V Leiden"], "F2": ["prothrombin G20210A", "prothrombin mutation", "prothrombin gene"],
    "BCR-ABL1": ["BCR-ABL", "BCR::ABL", "Philadelphia chromosome"],
    "EGFR": ["EGFR"], "ALK": ["ALK"], "BRAF": ["BRAF"], "KRAS": ["KRAS"], "NRAS": ["NRAS"],
    "RET": ["RET fusion", "RET-mutant", "RET mutation", "RET gene", "RET-altered"],
    "ERBB2": ["ERBB2", "HER2"], "ESR1": ["ESR1"], "PIK3CA": ["PIK3CA"],
    "PIK3CD": ["PIK3CD"], "PIK3R1": ["PIK3R1"], "SF3B1": ["SF3B1"], "VHL": ["VHL", "von Hippel-Lindau"],
    "ROS1": ["ROS1"], "MET": ["MET exon"], "KIT": ["KIT"], "FLT3": ["FLT3"], "IDH1": ["IDH1"],
    "IDH2": ["IDH2"], "BRCA1": ["BRCA1"], "BRCA2": ["BRCA2"], "NTRK": ["NTRK"],
    "TTR": ["transthyretin"],  # bare "TTR" also means "time to response"
    "AQP4": ["AQP4", "aquaporin-4", "aquaporin 4"],
    "GAA": ["GAA", "acid alpha-glucosidase", "acid α-glucosidase"],
    "GALNS": ["GALNS", "N-acetylgalactosamine-6-sulfatase"],
    "NAGS": ["NAGS", "N-acetylglutamate synthase"], "NLRP3": ["NLRP3", "CIAS1"],
    "IL1RN": ["IL1RN", "IL-1 receptor antagonist deficiency", "DIRA"],
    "HBB": ["HBB", "beta-globin", "β-globin"], "F8": ["F8", "factor VIII"],
    "VWF": ["VWF", "von Willebrand factor"], "MS4A1": ["MS4A1", "CD20"], "CD19": ["CD19"], "TNFRSF17": ["TNFRSF17", "BCMA"],
    "CD274": ["CD274", "PD-L1"], "POLG": ["POLG"], "CFTR": ["CFTR"], "OTC": ["ornithine transcarbamylase"],
    "RYR1": ["RYR1"], "IFNL3": ["IFNL3", "IL28B"],
}

LABEL_TEXT_FIELDS_SKIP = {"openfda", "set_id", "id", "version", "effective_time", "spl_product_data_elements",
                          "package_label_principal_display_panel"}


@dataclass
class Label:
    drug: str
    brand: str
    source_file: str
    effective_time: str
    boxed_warning: str
    contraindications: str
    full_text: str
    genes: dict[str, str] = field(default_factory=dict)   # gene -> evidence sentence

    @property
    def has_boxed_warning(self) -> bool:
        return bool(self.boxed_warning.strip())


def _join(value) -> str:
    if isinstance(value, list):
        return "\n".join(_join(v) for v in value)
    return str(value)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;:])\s+(?=[A-Z(•])|\n+", text) if len(s.strip()) > 3]


def _alias_pattern(alias: str) -> re.Pattern:
    # case-sensitive for short symbols (avoid "ret" in "interpret"), insensitive for long names
    flags = 0 if (alias.isupper() and len(alias) <= 8) or "-" in alias and alias.split("-")[0].isupper() else re.I
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![a-z0-9])", flags)


_GENE_PATTERNS = {g: [_alias_pattern(a) for a in aliases] for g, aliases in GENE_ALIASES.items()}


def find_genes(text: str) -> dict[str, str]:
    found = {}
    sents = sentences(text)
    for gene, pats in _GENE_PATTERNS.items():
        for s in sents:
            if any(p.search(s) for p in pats):
                found[gene] = s[:300]
                break
    return found


def load_label(path: Path) -> Label:
    raw = json.loads(Path(path).read_text())["results"][0]
    o = raw.get("openfda", {})
    full = "\n".join(_join(v) for k, v in raw.items() if k not in LABEL_TEXT_FIELDS_SKIP and not k.endswith("_table"))
    return Label(
        drug=(o.get("generic_name") or ["?"])[0].strip().title(),
        brand=(o.get("brand_name") or ["?"])[0].strip(),
        source_file=Path(path).name,
        effective_time=raw.get("effective_time", ""),
        boxed_warning=_join(raw.get("boxed_warning", "")),
        contraindications=_join(raw.get("contraindications", "")),
        full_text=full,
        genes=find_genes(full),
    )


def load_all(label_dir: Path = LABEL_DIR) -> dict[str, Label]:
    labels = {}
    for p in sorted(label_dir.glob("*.json")):
        lab = load_label(p)
        labels[lab.drug.lower()] = lab
    return labels
