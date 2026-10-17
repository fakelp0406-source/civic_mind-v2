"""Tests for manifest-driven ingestion. All fixtures are synthetic (no real records)."""

from __future__ import annotations

import csv

import pandas as pd
import pytest

from civicmind.catalog.fingerprint import fingerprint
from civicmind.catalog.ingest import IngestionRefused, UseNotPermitted, ingest, require_use
from civicmind.catalog.manifest import Manifest
from civicmind.catalog.schemas import detect_schema, get_schema
from civicmind.catalog.validators import census_ward_profile, morth_city_table, swm_gcp

BWSSB = get_schema("bwssb_monthly/v1").columns
RA2019 = get_schema("morth_city_a47/ra2019").columns
RA2024 = get_schema("morth_city_a47/ra2024").columns
SWM = get_schema("swm_gcp/v1").columns
CENSUS = get_schema("census_ward_profile/v1").columns


def _csv(header, rows, newline="\r\n") -> bytes:
    def cell(v):
        v = str(v)
        return f'"{v}"' if ("," in v or '"' in v) else v

    lines = [",".join(cell(h) for h in header)] + [",".join(cell(v) for v in r) for r in rows]
    return (newline.join(lines) + newline).encode("utf-8")


def _bwssb_rows():
    # ward 2 repeated (left unresolved) and one zero consumption: both are warnings
    return [[1, "Alpha", 10, "1.5"], [2, "Beta", 20, "0"], [2, "Beta East", 5, "2.25"]]


def _morth_rows(header, cities=("City A", "City B")):
    # Every count is i for city i, except "Total Injured" = grievous + minor = 2i, so the
    # fixture satisfies both published checksums (Total row and injury identity).
    serial = header[0] == "Sl. No."

    def cell(col, i):
        return 2 * i if col.endswith("Total Injured") else i

    rows = []
    for i, city in enumerate(cities, start=1):
        rows.append(([i] if serial else []) + [city] + [cell(c, i) for c in header[1 + serial :]])
    total = (["NA"] if serial else []) + ["Total"]
    for col in header[1 + serial :]:
        if col.endswith("- Rank"):
            total.append("NA")
        else:
            total.append(sum(cell(col, i) for i in range(1, len(cities) + 1)))
    return rows + [total]


def _swm_rows():
    rows = []
    for ward, base in ((1, 100.0), (2, 200.0), (3, 300.0)):
        g16 = base * 1.052632
        c17 = g16 * 1.052632
        rows.append(
            ["Bengaluru", "EAST", f"Ward {ward}", ward, base, g16, 50.0, base, g16, c17]
            + [round(base * 0.60, 6), round(g16 * 0.65, 6), round(c17 * 0.70, 6)]
        )
    return rows


def _manifest(tmp_path, data: bytes, *, mode="trusted", domain="water", **overrides) -> Manifest:
    if mode == "trusted":
        rel = f"data/raw/{domain}/f.csv"
    else:
        rel = f"data/external/verify_test/{domain}/f.csv"
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    fp = fingerprint(path)
    header = data.decode("utf-8").splitlines()[0]

    names = next(csv.reader([header]))
    review = {
        "decision": "accept" if mode == "trusted" else "keep_profiled",
        "reviewed_by": "tester",
        "reviewed_on": "2026-01-01",
        "sha256": fp.sha256,
        "accepted_caveats": ["ward.duplicated", "consumption_ml.zero"],
        "permitted_uses": [] if mode == "trusted" else ["exploratory"],
    }
    m = {
        "dataset_id": "TEST-1",
        "title": "Synthetic",
        "publisher": "Nobody",
        "host_portal": "example.invalid",
        "source_class": "official",
        "resource_page": "https://example.invalid/r",
        "download_url": "https://example.invalid/f.csv",
        "licence": {
            "name": "L",
            "url": None,
            "evidence": "t",
            "attribution": "t",
            "exemptions_checked": True,
        },
        "retrieval": {
            "retrieved_at": None,
            "retrieved_by": None,
            "method": "t",
            "original_filename": "f.csv",
            "local_path": rel if mode != "trusted" else f"data/external/v/{domain}/f.csv",
        },
        "integrity": {
            "bytes": fp.bytes,
            "portal_stated_bytes": fp.bytes,
            "size_matches_portal": True,
            "sha256": fp.sha256,
            "format": "csv",
            "encoding": fp.encoding,
            "bom": fp.bom,
            "newline": fp.newline,
            "delimiter": fp.delimiter,
            "passed": True,
        },
        "schema": [{"name": n, "type": "text (unparsed)"} for n in names],
        "period": {"start": None, "end": None, "granularity": "month"},
        "geography": {"level": "ward"},
        "ward_scheme": "UNKNOWN",
        "sensitivity": "public",
        "contains_personal_data": False,
        "semantic_checks": {"validator": "bwssb@v1", "errors": 0},
        "human_review": "accepted" if mode == "trusted" else "pending",
        "review": review,
        "status": "promoted" if mode == "trusted" else "integrity_passed",
        "promoted_to": rel if mode == "trusted" else None,
        "value_nature": "unknown" if mode == "trusted" else "modelled",
    }
    m.update(overrides)
    return Manifest.model_validate(m)


def _refused(manifest, tmp_path, code, mode="trusted"):
    with pytest.raises(IngestionRefused) as exc:
        ingest(manifest, tmp_path, mode)
    assert exc.value.code == code, exc.value
    return exc.value


# --- valid ingestion --------------------------------------------------------------------


def test_trusted_bwssb_ingestion_preserves_bytes_header_and_anomalies(tmp_path):
    data = _csv(BWSSB, _bwssb_rows())
    m = _manifest(tmp_path, data)
    ds = ingest(m, tmp_path)
    assert (ds.mode, ds.family, ds.schema_version) == (
        "trusted",
        "bwssb_monthly",
        "bwssb_monthly/v1",
    )
    assert ds.header[0] == "Ward number "  # trailing space kept
    assert len(ds.raw) == 3 and ds.raw["Ward number "].tolist() == ["1", "2", "2"]  # no dedup
    assert ds.raw["Consumption in ML"].tolist() == ["1.5", "0", "2.25"]  # text as published
    assert ds.values["Consumption in ML"].tolist() == [1.5, 0.0, 2.25]
    assert ds.values["Ward Name"].tolist() == ["Alpha", "Beta", "Beta East"]
    assert {f.code for f in ds.findings} >= {"ward.duplicated", "consumption_ml.zero"}
    assert "no_cross_dataset_join" in ds.restrictions
    assert (tmp_path / m.promoted_to).read_bytes() == data
    assert ingest(m, tmp_path).summary() == ds.summary()  # reproducible


def test_bare_cr_file_is_read_in_memory_and_left_unchanged(tmp_path):
    data = _csv(BWSSB, _bwssb_rows(), newline="\r")
    m = _manifest(tmp_path, data)
    assert m.integrity.newline == "CR"
    assert len(ingest(m, tmp_path).raw) == 3
    assert (tmp_path / m.promoted_to).read_bytes() == data


# --- integrity --------------------------------------------------------------------------


def test_hash_mismatch_with_same_size_is_refused(tmp_path):
    data = _csv(BWSSB, _bwssb_rows())
    m = _manifest(tmp_path, data)
    (tmp_path / m.promoted_to).write_bytes(data.replace(b"Alpha", b"Alphb"))
    _refused(m, tmp_path, "integrity.hash_mismatch")


def test_size_mismatch_is_refused(tmp_path):
    m = _manifest(tmp_path, _csv(BWSSB, _bwssb_rows()))
    (tmp_path / m.promoted_to).write_bytes(_csv(BWSSB, _bwssb_rows()[:2]))
    _refused(m, tmp_path, "integrity.size_mismatch")


def test_missing_file_is_refused(tmp_path):
    m = _manifest(tmp_path, _csv(BWSSB, _bwssb_rows()))
    (tmp_path / m.promoted_to).unlink()
    _refused(m, tmp_path, "file.missing")


def test_line_ending_style_must_match_manifest(tmp_path):
    m = _manifest(tmp_path, _csv(BWSSB, _bwssb_rows()))
    integrity = m.integrity.model_copy(update={"newline": "LF"})
    _refused(m.model_copy(update={"integrity": integrity}), tmp_path, "integrity.newline_mismatch")


def test_unsafe_path_is_refused(tmp_path):
    m = _manifest(tmp_path, _csv(BWSSB, _bwssb_rows()))
    _refused(m.model_copy(update={"promoted_to": "data/raw/../../x.csv"}), tmp_path, "path.unsafe")


# --- CSV structure and schema -----------------------------------------------------------


def test_duplicate_header_names_are_refused(tmp_path):
    m = _manifest(tmp_path, b"Ward Name,Ward Name\r\nA,B\r\n")
    exc = _refused(m, tmp_path, "schema.duplicate_columns")
    assert exc.details == ["Ward Name"]


def test_ragged_rows_are_refused(tmp_path):
    data = _csv(BWSSB, _bwssb_rows()) + b"4,Delta,1\r\n"
    exc = _refused(_manifest(tmp_path, data), tmp_path, "csv.ragged_rows")
    assert exc.details == [5]  # record number; the header is record 1


def test_unterminated_quote_is_malformed(tmp_path):
    data = _csv(BWSSB, _bwssb_rows()) + b'4,"Delta,1,2\r\n'
    _refused(_manifest(tmp_path, data), tmp_path, "csv.malformed")


def test_misspelt_header_matches_no_schema(tmp_path):
    header = ("Ward number ", "Ward Name", "Number of Connectionss", "Consumption in ML")
    _refused(_manifest(tmp_path, _csv(header, _bwssb_rows())), tmp_path, "schema.unknown")


def test_header_must_equal_manifest_schema(tmp_path):
    m = _manifest(tmp_path, _csv(BWSSB, _bwssb_rows()))
    schema = [{"name": n.strip(), "type": "text"} for n in BWSSB]
    _refused(
        Manifest.model_validate({**m.model_dump(by_alias=True), "schema": schema}),
        tmp_path,
        "schema.manifest_mismatch",
    )


# --- status and review ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("quarantined", "status.quarantined"),
        ("rejected", "status.rejected"),
        ("validated", "status.not_trusted"),
        ("planned", "status.not_trusted"),
        ("integrity_passed", "status.not_trusted"),
    ],
)
def test_untrusted_statuses_are_refused(tmp_path, status, code):
    m = _manifest(tmp_path, _csv(BWSSB, _bwssb_rows()), status=status)
    _refused(m, tmp_path, code)


def test_quarantined_is_refused_in_exploratory_mode_too(tmp_path):
    m = _manifest(tmp_path, _csv(BWSSB, _bwssb_rows()), mode="exploratory", status="quarantined")
    _refused(m, tmp_path, "status.quarantined", mode="exploratory")


def test_review_for_other_bytes_is_refused(tmp_path):
    m = _manifest(tmp_path, _csv(BWSSB, _bwssb_rows()))
    review = m.review.model_copy(update={"sha256": "0" * 64})
    _refused(m.model_copy(update={"review": review}), tmp_path, "review.stale")


def test_validator_errors_are_refused_and_negative_is_not_replaced(tmp_path):
    rows = _bwssb_rows() + [[3, "Gamma", 7, "-2.00E-06"]]
    m = _manifest(tmp_path, _csv(BWSSB, rows))
    exc = _refused(m, tmp_path, "validation.errors")
    assert "consumption_ml.negative" in exc.details
    assert b"-2.00E-06" in (tmp_path / m.promoted_to).read_bytes()


def test_unaccepted_warning_is_refused(tmp_path):
    m = _manifest(tmp_path, _csv(BWSSB, _bwssb_rows()))
    review = m.review.model_copy(update={"accepted_caveats": ["ward.duplicated"]})
    exc = _refused(
        m.model_copy(update={"review": review}), tmp_path, "validation.unaccepted_warnings"
    )
    assert exc.details == ["consumption_ml.zero"]


# --- modelled data ----------------------------------------------------------------------


def _swm(tmp_path, mode="exploratory", **kw):
    return _manifest(
        tmp_path,
        _csv(SWM, _swm_rows()),
        mode=mode,
        domain="waste",
        semantic_checks={"validator": None},
        **kw,
    )


def test_modelled_data_is_never_trusted(tmp_path):
    m = _swm(tmp_path, mode="trusted", value_nature="modelled")
    _refused(m, tmp_path, "modelled.not_trusted")


def test_exploratory_needs_explicit_permission(tmp_path):
    m = _swm(tmp_path)
    review = m.review.model_copy(update={"permitted_uses": []})
    _refused(
        m.model_copy(update={"review": review}),
        tmp_path,
        "exploratory.not_permitted",
        mode="exploratory",
    )


def test_exploratory_modelled_output_is_labelled_and_restricted(tmp_path):
    ds = ingest(_swm(tmp_path), tmp_path, "exploratory")
    assert ds.mode == "exploratory" and ds.value_nature == "modelled"
    assert ds.caveats[0].startswith("EXPLORATORY")
    assert "values.modelled_signature" in {f.code for f in ds.findings}
    for use in (
        "ward_efficiency_ranking",
        "measured_performance",
        "trusted_analytics",
        "ward_ranking",
        "cross_dataset_join",
    ):
        with pytest.raises(UseNotPermitted):
            require_use(ds, use)
    with pytest.raises(ValueError):
        require_use(ds, "anything_else")


def test_swm_validator_reports_modelled_signature_and_inconsistency():
    frame = pd.DataFrame([[str(v) for v in r] for r in _swm_rows()], columns=list(SWM))
    findings = {f.code: f for f in swm_gcp.validate(frame, list(SWM))}
    ratios = findings["values.modelled_signature"].details["constant_ratios"]
    assert ratios["generated 2016-17 / generated 2015-16"] == 1.052632
    assert "collected.equals_generated" in findings
    assert findings["collected.exceeds_generated"].details == {"year": "2017-18", "wards": 3}


def test_census_validator_flags_reused_names_and_unit_label():
    rows = []
    for ward in range(1, 7):
        name = f"Name {(ward - 1) % 3}"  # names cycle every 3 wards
        rows.append(
            [
                "Bengaluru",
                "Z",
                name,
                ward,
                "1.0",
                "50000",
                "25000",
                "25000",
                "9000",
                "NA",
                "NA",
                "NA",
            ]
        )
    frame = pd.DataFrame(rows, columns=list(CENSUS)).astype(str)
    findings = {f.code: f for f in census_ward_profile.validate(frame, list(CENSUS))}
    assert findings["ward_name.reused"].severity == "error"
    assert findings["unit.label_implausible"].severity == "warning"
    assert "population.sex_sum" not in findings


# --- MoRTH schema versions --------------------------------------------------------------


def test_ra2019_and_ra2024_are_distinct_schema_versions(tmp_path):
    out = {}
    for name, header in (("ra2019", RA2019), ("ra2024", RA2024)):
        sub = tmp_path / name
        m = _manifest(
            sub,
            _csv(header, _morth_rows(header)),
            domain="roads",
            semantic_checks={"validator": "morth_city@v1"},
        )
        out[name] = ingest(m, sub)
    a, b = out["ra2019"], out["ra2024"]
    assert (a.family, b.family) == ("morth_city_a47", "morth_city_a47")
    assert (a.schema_version, b.schema_version) == (
        "morth_city_a47/ra2019",
        "morth_city_a47/ra2024",
    )
    assert "Over-Speeding - Persons Injured - Greviously Injured" in a.header
    assert "Over-Speeding - Persons Injured - Grievously Injured" in b.header
    assert "States/UTs" in a.header and "Million Plus Cities" in b.header
    assert "Sl. No." not in a.header and b.header[0] == "Sl. No."
    assert len(a.header) == 33 and len(b.header) == 34
    assert a.raw.iloc[-1]["States/UTs"] == "Total"
    assert b.raw.iloc[-1]["Over-Speeding - Number of Accidents - Rank"] == "NA"  # kept
    assert pd.isna(b.values.iloc[-1]["Over-Speeding - Number of Accidents - Rank"])
    assert "values.unparsed" in {f.code for f in b.findings}


def test_schema_detection_is_exact_never_fuzzy():
    assert detect_schema(RA2019).version == "morth_city_a47/ra2019"
    assert detect_schema(RA2024).version == "morth_city_a47/ra2024"
    respelt = [c.replace("Greviously", "Grievously") for c in RA2019]
    assert detect_schema(respelt) is None
    assert detect_schema([c.strip() for c in BWSSB]) is None


def test_morth_file_under_a_bwssb_manifest_is_a_family_mismatch(tmp_path):
    m = _manifest(
        tmp_path,
        _csv(RA2024, _morth_rows(RA2024)),
        domain="roads",
        semantic_checks={"validator": "bwssb@v1"},
    )
    _refused(m, tmp_path, "schema.family_mismatch")


def test_injury_checksum_mismatch_is_a_warning_and_blocks_trusted_ingestion(tmp_path):
    rows = _morth_rows(RA2019)
    col = RA2019.index("Over-Speeding - Persons Injured - Total Injured")
    rows[0][col] = 99  # grievous 1 + minor 1 != 99 (Total row then disagrees too)
    rows[-1][col] = 99 + 2
    m = _manifest(
        tmp_path,
        _csv(RA2019, rows),
        domain="roads",
        semantic_checks={"validator": "morth_city@v1"},
    )
    exc = _refused(m, tmp_path, "validation.unaccepted_warnings")
    assert "injured.sum_mismatch" in exc.details
    assert b",99," in (tmp_path / m.promoted_to).read_bytes()  # published value kept


def test_injury_checksum_is_silent_when_consistent_in_both_editions():
    for header in (RA2019, RA2024):
        frame = pd.DataFrame([[str(v) for v in r] for r in _morth_rows(header)], columns=header)
        codes = {f.code for f in morth_city_table.validate(frame, list(header))}
        assert "injured.sum_mismatch" not in codes
