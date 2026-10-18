"""Pre-PR cleanup: control characters in the document review package, and the reproducibility
metadata of the stage 2F API evaluation report."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


review = _load("doc_review_package", ROOT / "scripts/doc_review_package.py")
api_metrics = _load("api_metrics", ROOT / "eval/api_metrics.py")
PACKAGE = ROOT / "docs/acquisition/docs-01/REVIEW_PACKAGE.md"


# --- review package: control characters ---------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("lR;eso\x00t;rs", "lR;eso\\x00t;rs"),  # NUL from a legacy (non-Unicode) font
        ("a\x07b\x1bc", "a\\x07b\\x1bc"),  # other C0 controls
        ("zero\u200bwidth", "zero\\u200bwidth"),  # invisible format character
        ("pua\ue000x", "pua\\ue000x"),  # private use (legacy-font glyph slots)
    ],
)
def test_control_and_invisible_characters_become_visible_escapes(raw, shown):
    assert review.visible(raw) == shown


@pytest.mark.parametrize(
    "text", ["ROAD ACCIDENTS IN INDIA \u2013 2019", "सत्यमेव जयते", r"C:\path \x00 typed", "é ü"]
)
def test_ordinary_text_is_unchanged(text):
    assert review.visible(text) == text


def _page_file(tmp_path: Path, pages: list[str]) -> str:
    path = tmp_path / "pages.jsonl"
    path.write_text(
        "".join(json.dumps({"page": n, "text": t}) + "\n" for n, t in enumerate(pages, 1)),
        encoding="utf-8",
    )
    return "pages.jsonl"


def test_excerpt_escapes_and_reports_it(tmp_path):
    rel = _page_file(tmp_path, ["short", "ROAD ACCIDENTS IN INDIA 2019 lR;eso\x00t;rs extra"])
    lines, escaped = review._excerpt(tmp_path, rel)
    assert escaped and lines == ["p2: ROAD ACCIDENTS IN INDIA 2019 lR;eso\\x00t;rs extra"]
    assert "\x00" not in "".join(lines)


def test_clean_excerpt_reports_nothing_escaped(tmp_path):
    rel = _page_file(tmp_path, ["Road Accidents in India 2023, Government of India"])
    assert review._excerpt(tmp_path, rel) == (
        ["p1: Road Accidents in India 2023, Government of India"],
        False,
    )


def test_excerpt_cuts_the_source_text_before_escaping(tmp_path):
    # The same source characters are quoted; escapes only lengthen what is shown.
    text = "x" * (review.EXCERPT_CHARS - 1) + "\x00" + "tail"
    lines, escaped = review._excerpt(tmp_path, _page_file(tmp_path, [text]))
    assert escaped and lines[0].endswith("x\\x00") and "tail" not in lines[0]


def test_an_excerpt_cut_after_a_space_has_no_trailing_whitespace(tmp_path):
    # The 240-character cut can land just after a space (RA2019 p3 did): it is not kept.
    text = "w" * (review.EXCERPT_CHARS - 1) + " " + "next words"
    lines, _ = review._excerpt(tmp_path, _page_file(tmp_path, [text]))
    assert lines == ["p1: " + "w" * (review.EXCERPT_CHARS - 1)]
    assert len(lines[0]) <= len("p1: ") + review.EXCERPT_CHARS


def test_committed_review_package_is_plain_text():
    data = PACKAGE.read_bytes()
    text = data.decode("utf-8")
    assert b"\x00" not in data
    assert not [c for c in text if c != "\n" and review.visible(c) != c]
    assert not [n for n, line in enumerate(text.splitlines(), 1) if line != line.rstrip()]
    assert "lR;eso\\x00t;rs" in text and review.ESCAPE_NOTE in text  # evidence kept, visibly


def test_committed_review_package_matches_the_generator():
    manifests = [ROOT / "data/doc_manifests" / f"{d}.yaml" for d in ("DOC-MORTH-RA2019",)]
    page_files = list((ROOT / "data/processed/rag/extracted").glob("*/*.jsonl"))
    if not all(p.is_file() for p in manifests) or not page_files:
        pytest.skip("git-ignored page files not present")
    assert review.build("docs-01") == PACKAGE.read_text(encoding="utf-8")


# --- API evaluation: reproducibility metadata -------------------------------------------------


def _tree(root: Path, files: dict[str, bytes]) -> Path:
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    return root


def test_source_fingerprint_covers_code_and_scripts_only(tmp_path):
    root = _tree(tmp_path, {
        "src/civicmind/a.py": b"x = 1\n",
        "src/civicmind/sub/b.py": b"y = 2\n",
        "src/civicmind/__pycache__/a.cpython-313.pyc": b"\x00",
        "eval/api_metrics.py": b"# eval\n",
        "eval/rag_metrics.py": b"# rag\n",
        "eval/route_metrics.py": b"# route\n",
        "eval/reports/api.v1.results.json": b"{}",
        "eval/reports/api.v1.results.md": b"# report\n",
    })  # fmt: skip
    fp = api_metrics.source_fingerprint(root)
    assert sorted(fp["file_sha256"]) == [
        "eval/api_metrics.py", "eval/rag_metrics.py", "eval/route_metrics.py",
        "src/civicmind/a.py", "src/civicmind/sub/b.py",
    ]  # fmt: skip
    assert fp["files"] == 5 and len(fp["sha256"]) == 64
    (root / "eval/reports/api.v1.results.json").write_bytes(b'{"changed": true}')
    assert api_metrics.source_fingerprint(root)["sha256"] == fp["sha256"]  # reports excluded


def test_source_fingerprint_ignores_line_endings_but_not_content(tmp_path):
    lf = api_metrics.source_fingerprint(_tree(tmp_path / "lf", {"src/civicmind/a.py": b"a\nb\n"}))
    crlf = api_metrics.source_fingerprint(
        _tree(tmp_path / "crlf", {"src/civicmind/a.py": b"a\r\nb\r\n"})
    )
    other = api_metrics.source_fingerprint(
        _tree(tmp_path / "other", {"src/civicmind/a.py": b"a\nc\n"})
    )
    assert lf["sha256"] == crlf["sha256"] != other["sha256"]


def test_runtime_versions_are_read_not_guessed():
    import fastapi
    import numpy
    import yaml

    v = api_metrics.runtime_versions()
    assert v["fastapi"] == fastapi.__version__ and v["numpy"] == numpy.__version__
    assert v["PyYAML"] == yaml.__version__
    assert v["python"] == ".".join(map(str, sys.version_info[:3]))
    for name in api_metrics.RUNTIME_DISTRIBUTIONS:
        assert v[name]  # a version, or "unavailable: not installed"


def test_reproducibility_reads_the_live_router_and_index(tmp_path):
    pytest.importorskip("pypdf", reason="needs the optional 'rag' extra (pypdf)")
    from civicmind.api.retrieval import DocumentRetrieval
    from civicmind.orchestrator.router import Router
    from civicmind.rag.index import build_index
    from civicmind.respond.compose import Answer
    from rag_fixtures import add_document

    text = ("Definitions used in this report. A grievous injury accident is one in which a "
            "victim is admitted to hospital as an in patient for serious injuries.")  # fmt: skip
    add_document(tmp_path, "DOC-R23", [text], "2023")
    add_document(tmp_path, "DOC-Q", [text + " Quarantined copy."], "2022", decision="quarantine")
    (tmp_path / "data/manifests").mkdir(parents=True)
    build_index(tmp_path, None)
    for rel in api_metrics.INPUT_FILES:  # stand-in input files
        _tree(tmp_path, {rel: b"input\n"})
    retrieval = DocumentRetrieval(
        tmp_path,
        lambda q, r: Answer("refused", q, "t", code="query.period_missing"),
        router=Router(tmp_path, index_spec=None),
    )
    meta = api_metrics.reproducibility(tmp_path, retrieval)
    index = retrieval.router.index
    assert meta["index"]["index_id"] == index.index_id
    assert meta["index"]["corpus_digest"] == index.corpus.digest()
    assert meta["retrieval"]["gate"] == "bm25"
    assert meta["retrieval"]["threshold"] == retrieval.router.config.retrieval.bm25_min_score
    docs = {d["document_id"]: d for d in meta["documents"]}
    assert docs["DOC-R23"]["eligible"] and not docs["DOC-Q"]["eligible"]
    assert docs["DOC-Q"]["status"] == "quarantined"
    assert docs["DOC-R23"]["sha256"] == index.corpus.document("DOC-R23").sha256
    assert set(meta["inputs"]) == set(api_metrics.INPUT_FILES)
    assert json.loads(json.dumps(meta)) == meta  # JSON-serialisable, no timestamps inside
    assert "generated_at_utc" not in json.dumps(meta)
