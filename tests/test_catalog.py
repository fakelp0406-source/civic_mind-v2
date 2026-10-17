"""Unit tests for the catalogue layer. All fixtures are synthetic (no real records)."""

from __future__ import annotations

import hashlib
import io

import pandas as pd
import pytest

from civicmind.catalog import identifiers
from civicmind.catalog.fingerprint import classify_newlines, detect_encoding, fingerprint
from civicmind.catalog.manifest import Manifest, read_manifest, write_manifest
from civicmind.catalog.profile import profile_frame, read_raw_header, read_text_table
from civicmind.catalog.validators import bwssb_monthly, morth_city_table
from civicmind.catalog.validators.base import has_errors

BWSSB_HEADER = "Ward number ,Ward Name,Number of Connections,Consumption in ML"


def _write(tmp_path, name, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    return path


# --- fingerprint -------------------------------------------------------------------------


def test_fingerprint_reports_exact_bytes_and_hash(tmp_path):
    data = b"a,b\r\n1,2\r\n"
    fp = fingerprint(_write(tmp_path, "x.csv", data))
    assert fp.bytes == len(data)
    assert fp.sha256 == hashlib.sha256(data).hexdigest()
    assert (fp.encoding, fp.bom, fp.newline, fp.delimiter) == ("utf-8", False, "CRLF", ",")
    assert not fp.looks_like_html and not fp.contains_nul


def test_fingerprint_does_not_modify_the_file(tmp_path):
    data = b"a,b\r1,2\r"
    path = _write(tmp_path, "cr.csv", data)
    fingerprint(path)
    assert path.read_bytes() == data


@pytest.mark.parametrize(
    ("raw", "style"),
    [
        (b"a\r\nb\r\n", "CRLF"),
        (b"a\nb\n", "LF"),
        (b"a\rb\r", "CR"),
        (b"a\r\nb\rc", "mixed"),
        (b"a", "none"),
    ],
)
def test_classify_newlines(raw, style):
    assert classify_newlines(raw)[0] == style


def test_detect_encoding_bom_and_cp1252():
    assert detect_encoding(b"\xef\xbb\xbfa") == ("utf-8-sig", True)
    assert detect_encoding("café".encode("cp1252")) == ("cp1252", False)


def test_fingerprint_flags_html_error_pages(tmp_path):
    fp = fingerprint(_write(tmp_path, "x.csv", b"<!DOCTYPE html><html><body>403</body></html>"))
    assert fp.looks_like_html


# --- profile -----------------------------------------------------------------------------


def test_profile_reads_text_without_coercion_and_handles_bare_cr(tmp_path):
    path = _write(tmp_path, "t.csv", b"id ,code,n\r1,0012,NA\r2,0013,5\r")
    header = read_raw_header(path, "utf-8")
    frame = read_text_table(path, "utf-8")
    prof = profile_frame(frame, header)
    assert prof.rows == 2 and header == ["id ", "code", "n"]
    assert prof.names_with_outer_whitespace == ["id "]
    code = next(c for c in prof.columns_detail if c.name == "code")
    assert code.samples[0] == "0012"  # leading zeros kept
    n = next(c for c in prof.columns_detail if c.name == "n")
    assert n.non_numeric_values == ["NA"] and n.numeric == 1


def test_profile_detects_duplicate_header_names_from_raw_header(tmp_path):
    path = _write(tmp_path, "d.csv", b"a,a,b\n1,2,3\n")
    prof = profile_frame(read_text_table(path, "utf-8"), read_raw_header(path, "utf-8"))
    assert prof.duplicate_column_names == ["a"]


# --- BWSSB validator ---------------------------------------------------------------------


def _bwssb(rows: list[str]):
    text = "\n".join([BWSSB_HEADER, *rows]) + "\n"
    frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, na_values=[""])
    return frame, BWSSB_HEADER.split(",")


def test_bwssb_clean_file_has_no_errors():
    frame, header = _bwssb(["1,Alpha,10,1.5", "2,Beta,20,2.0"])
    findings = bwssb_monthly.validate(frame, header)
    assert not has_errors(findings)
    totals = {f.code: f.details for f in findings if f.code.endswith(".total")}
    assert totals["connections.total"]["total"] == 30


def test_bwssb_reports_duplicates_without_resolving_them():
    frame, header = _bwssb(["1,Alpha,10,1.5", "1,Alfa,5,0.5", "3,Gamma,0,0"])
    findings = {f.code: f for f in bwssb_monthly.validate(frame, header)}
    assert findings["ward.duplicated"].details["ward_numbers"] == {"1": ["Alpha", "Alfa"]}
    assert findings["ward.gaps"].details["missing"] == [2]
    assert "connections.zero" in findings
    assert len(frame) == 3  # nothing dropped or merged


def test_bwssb_wrong_header_is_an_error():
    frame, _ = _bwssb(["1,Alpha,10,1.5"])
    findings = bwssb_monthly.validate(frame, ["Ward", "Name", "Conn", "ML"])
    assert has_errors(findings)


def test_bwssb_renamed_header_is_an_error_but_rows_are_still_checked():
    # Same column count, misspelt name (as in the April/May 2025 publications): the header is
    # an error AND the positional row checks still run, so a negative value is also reported.
    frame, _ = _bwssb(["1,Alpha,10,-0.000002"])
    header = ["Ward number ", "Ward Name", "Number of Connectionss", "Consumption in ML"]
    codes = {f.code for f in bwssb_monthly.validate(frame, header) if f.severity == "error"}
    assert {"schema.columns", "consumption_ml.negative"} <= codes


def test_bwssb_negative_and_non_numeric_values_are_errors():
    frame, header = _bwssb(["1,Alpha,-1,1.5", "x,Beta,2,abc"])
    codes = {f.code for f in bwssb_monthly.validate(frame, header) if f.severity == "error"}
    assert {"ward.non_integer", "connections.negative", "consumption_ml.non_numeric"} <= codes


# --- MoRTH validator ---------------------------------------------------------------------


def _morth(rows: list[str], header="Sl. No.,Million Plus Cities,A - Number,A - Rank"):
    text = "\n".join([header, *rows]) + "\n"
    frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, na_values=[""])
    return frame, header.split(",")


def test_morth_total_row_consistent():
    frame, header = _morth(["1,X,5,2", "2,Y,7,1", "Total,Total,12,NA"])
    findings = {f.code: f for f in morth_city_table.validate(frame, header)}
    assert "total.consistent" in findings and "total.mismatch" not in findings
    assert findings["entities.count"].details["entities"] == ["X", "Y"]


def test_morth_total_mismatch_and_negative_are_reported_not_fixed():
    frame, header = _morth(["1,X,5,2", "2,Y,-1,1", "Total,Total,9,NA"])
    findings = {f.code: f for f in morth_city_table.validate(frame, header)}
    assert findings["total.mismatch"].details["columns"][0]["sum_of_rows"] == 4
    assert findings["cells.negative"].details == {"A - Number": ["Y"]}


def test_morth_schema_drift_is_verbatim():
    drift = morth_city_table.schema_drift(
        ["States/UTs", "A"], ["Sl. No.", "Million Plus Cities", "A"]
    )
    assert drift == {
        "only_in_old": ["States/UTs"],
        "only_in_new": ["Million Plus Cities", "Sl. No."],
        "common": ["A"],
    }


# --- identifier assessment ---------------------------------------------------------------


def test_identifier_assessment_separates_outcomes_and_never_authorises_a_join():
    left = pd.DataFrame(
        {"id": ["1", "2", "3", "3", "5"], "name": ["Alpha", "Beta", "Gamma", "Gama", "Eps"]}
    )
    right = pd.DataFrame({"no": ["1", "2", "4"], "ward": ["ALPHA ", "Bravo", "Delta"]})
    result = identifiers.assess_identifiers(
        left, right, left_id="id", left_name="name", right_id="no", right_name="ward"
    )
    assert result.matched == ["1"]
    assert result.name_conflict == [{"id": "2", "left": "Beta", "right": "Bravo"}]
    assert result.unmatched_left == ["3", "5"] and result.unmatched_right == ["4"]
    assert result.duplicated_left == {"3": 2}
    assert result.ambiguous_left == {"3": ["Gama", "Gamma"]}
    assert result.join_authorised is False


def test_names_shared_by_multiple_ids_flags_repeated_name_blocks():
    frame = pd.DataFrame(
        {"no": ["1", "2", "3", "4"], "name": ["Alpha Ward", "Beta", "ALPHA ward", "Gamma"]}
    )
    shared = identifiers.names_shared_by_multiple_ids(frame, "no", "name")
    assert shared == {"alpha ward": ["1", "3"]}


# --- manifest ----------------------------------------------------------------------------


def _manifest(**overrides) -> Manifest:
    data = {
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
            "evidence": "test",
            "attribution": "test",
            "exemptions_checked": True,
        },
        "retrieval": {
            "retrieved_at": None,
            "retrieved_by": None,
            "method": "test",
            "original_filename": "f.csv",
            "local_path": None,
        },
        "schema": [{"name": "Ward number ", "type": "int"}],
        "period": {"start": None, "end": None, "granularity": "month"},
        "geography": {"level": "ward"},
        "sensitivity": "public",
        "contains_personal_data": False,
        "status": "planned",
    }
    data.update(overrides)
    return Manifest.model_validate(data)


def test_manifest_round_trip_keeps_verbatim_column_names(tmp_path):
    path = write_manifest(_manifest(), tmp_path)
    loaded = read_manifest(path)
    assert loaded == _manifest()
    assert loaded.schema_[0].name == "Ward number "
    assert loaded.git_tracked is False and loaded.human_review == "pending"


def test_manifest_rejects_unknown_fields_and_statuses():
    with pytest.raises(ValueError):
        _manifest(unexpected="x")
    with pytest.raises(ValueError):
        _manifest(status="approved")
