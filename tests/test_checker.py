import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from checker import grade_boxed, grade_contraindications, grade_genes, label_says_none, support  # noqa: E402
from labels import Label, find_genes, load_all  # noqa: E402


def make_label(**kw):
    base = dict(drug="Testamab", brand="TESTIVA", source_file="x.json", effective_time="20240101",
                boxed_warning="", contraindications="4 CONTRAINDICATIONS None. (4)", full_text="", genes={})
    base.update(kw)
    return Label(**base)


def test_gene_aliases_and_false_positives():
    found = find_genes("Reduced cytochrome P450 2D6 activity. Binds CD20. Median time to response (TTR) was 2 months.")
    assert "CYP2D6" in found and "MS4A1" in found
    assert "TTR" not in found            # "time to response" must not count as the TTR gene
    assert "RET" not in find_genes("Patients should interpret results carefully.")


def test_label_none_detection():
    assert label_says_none("4. CONTRAINDICATIONS None None. ( 4 )")
    assert label_says_none("4 CONTRAINDICATIONS None. (4)")
    assert not label_says_none("4 CONTRAINDICATIONS Active HBV infection. (4)")


def test_support_ignores_drug_name_and_handles_synonyms():
    score, _ = support("history of allergy to succimer", "should not be given to patients with a history of allergy to the drug.",
                       ("Succimer", "CHEMET"))
    assert score == 1.0
    score, _ = support("use of MAOIs", "The use of monoamine oxidase inhibitors is contraindicated.")
    assert score >= 0.6


def test_boxed_presence_is_exact():
    lab = make_label(boxed_warning="WARNING: HYPONATREMIA ...")
    assert grade_boxed(lab, {"has_boxed_warning": False}).verdict == "incorrect"
    assert grade_boxed(make_label(), {"has_boxed_warning": False}).verdict == "correct"


def test_gene_hallucination_is_flagged():
    lab = make_label(genes={"CYP2D6": "metabolized by CYP2D6"})
    assert grade_genes(lab, {"genes": ["CYP2D6"]}).verdict == "correct"
    assert grade_genes(lab, {"genes": ["CYP2D6", "HLA-B"]}).verdict == "partial"
    assert grade_genes(lab, {"genes": ["HLA-B"]}).verdict == "incorrect"


def test_contraindication_none_cases():
    assert grade_contraindications(make_label(), {"items": ["None"]}).verdict == "correct"
    assert grade_contraindications(make_label(), {"items": ["pregnancy"]}).verdict == "incorrect"
    lab = make_label(contraindications="4 CONTRAINDICATIONS Active HBV infection. (4)")
    assert grade_contraindications(lab, {"items": ["None"]}).verdict == "incorrect"
    assert grade_contraindications(lab, {"items": ["active hepatitis B virus infection"]}).verdict == "correct"


def test_every_saved_answer_has_a_label():
    labels = load_all()
    answers = [json.loads(l) for l in (ROOT / "data/answers/claude_closed_book.jsonl").read_text().splitlines()]
    assert len(labels) == 50 and all(a["drug"].lower() in labels for a in answers)


def test_live_answerer_parses_json_reply():
    from types import SimpleNamespace
    from answerers import AnthropicAnswerer

    class FakeMessages:
        def create(self, **kw):
            assert kw["temperature"] == 0 and "Rasburicase" in kw["messages"][0]["content"]
            return SimpleNamespace(content=[SimpleNamespace(type="text", text='```json\n{"genes": ["G6PD"], "confidence": "high"}\n```')])

    a = AnthropicAnswerer(model="test", client=SimpleNamespace(messages=FakeMessages()))
    assert a.ask("genes", "Rasburicase", "Elitek") == {"genes": ["G6PD"], "confidence": "high"}
