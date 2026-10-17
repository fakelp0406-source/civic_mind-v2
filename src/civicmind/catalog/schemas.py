"""Registered source schemas: the exact, verbatim headers each dataset family may have.

A file is assigned a schema version only when its raw header equals a registered header
exactly (order, case, spacing and spelling included). Nothing is renamed or aliased: the
MoRTH Annexure 47 editions of 2019 and 2024 are two distinct schema versions, and a header
with a publisher typo (e.g. ``Number of Connectionss``) matches no schema at all.

Column names are copied from the official batch-01 and batch-02 downloads (see
data/manifests/).
"""

from __future__ import annotations

from dataclasses import dataclass

_BWSSB_V1 = (
    "Ward number ",
    "Ward Name",
    "Number of Connections",
    "Consumption in ML",
)
_CENSUS_V1 = (
    "City Name",
    "Zone Name",
    "Ward Name",
    "Ward No.",
    "Area (in sq km)",
    "Total Population (in thousands)",
    "Population - Male (in thousands)",
    "Population - female (in thousands)",
    "population - children aged 0-14 (in thousands)",
    "Population - youth aged 15-24 (in thousands)",
    "Population - adults aged 25-60 (in thousands)",
    "Population - Senior citizens aged 60+ (in thousands)",
)
_SWM_GCP_V1 = (
    "City_Name",
    "Zone_Name",
    "Ward_Name",
    "Ward_No.",
    "Total_quantum_of_MSW_generated_in_the_city_(in_Metric_tonnes)_-_2015-16",
    "Total_quantum_of_MSW_generated_in_the_city_(in_Metric_tonnes)_-_2016-17",
    "Total_quantum_of_MSW_generated_in_the_city_(in_Metric_tonnes)_-_2017-18",
    "Total_quantum_of_MSW_collected_by_the_ULB_or_private_operator_(in_Metric_tonnes)_-_2015-16",
    "Total_quantum_of_MSW_collected_by_the_ULB_or_private_operator_(in_Metric_tonnes)_-_2016-17",
    "Total_quantum_of_MSW_collected_by_the_ULB_or_private_operator_(in_Metric_tonnes)_-_2017-18",
    "Average_quantum_of_MSW_that_is_processed_or_recycled_(in_Metric_tonnes)_-_2015-16",
    "Average_quantum_of_MSW_that_is_processed_or_recycled_(in_Metric_tonnes)_-_2016-17",
    "Average_quantum_of_MSW_that_is_processed_or_recycled_(in_Metric_tonnes)_-_2017-18",
)
_MORTH_A47_RA2019 = (
    "States/UTs",
    "Over-Speeding - Number of Accidents - Number",
    "Over-Speeding - Number of Accidents - Rank",
    "Over-Speeding - Persons Killed - Number",
    "Over-Speeding - Persons Killed - Rank",
    "Over-Speeding - Persons Injured - Greviously Injured",
    "Over-Speeding - Persons Injured - Minor Injury",
    "Over-Speeding - Persons Injured - Total Injured",
    "Drunken Driving/ Consumption of alcohol and drug  - Number of Accidents",
    "Drunken Driving/ Consumption of alcohol and drug  - Persons Killed",
    "Drunken Driving/ Consumption of alcohol and drug  - Persons Injured - Greviously Injured",
    "Drunken Driving/ Consumption of alcohol and drug  - Persons Injured - Minor Injury",
    "Drunken Driving/ Consumption of alcohol and drug  - Persons Injured - Total Injured",
    "Driving on Wrong side - Number of Accidents",
    "Driving on Wrong side - Persons Killed",
    "Driving on Wrong side - Persons Injured - Greviously Injured",
    "Driving on Wrong side - Persons Injured - Minor Injury",
    "Driving on Wrong side - Persons Injured - Total Injured",
    "Jumping Red Light - Number of Accidents",
    "Jumping Red Light - Persons Killed",
    "Jumping Red Light - Persons Injured - Greviously Injured",
    "Jumping Red Light - Persons Injured - Minor Injury",
    "Jumping Red Light - Persons Injured - Total Injured",
    "Use of Mobile Phone - Number of Accidents",
    "Use of Mobile Phone - Persons Killed",
    "Use of Mobile Phone - Persons Injured - Greviously Injured",
    "Use of Mobile Phone - Persons Injured - Minor Injury",
    "Use of Mobile Phone - Persons Injured - Total Injured",
    "Others - Number of Accidents",
    "Others - Persons Killed",
    "Others - Persons Injured - Greviously Injured",
    "Others - Persons Injured - Minor Injury",
    "Others - Persons Injured - Total Injured",
)
_MORTH_A47_RA2024 = (
    "Sl. No.",
    "Million Plus Cities",
    "Over-Speeding - Number of Accidents - Number",
    "Over-Speeding - Number of Accidents - Rank",
    "Over-Speeding - Persons Killed - Number",
    "Over-Speeding - Persons Killed - Rank",
    "Over-Speeding - Persons Injured - Grievously Injured",
    "Over-Speeding - Persons Injured - Minor Injury",
    "Over-Speeding - Persons Injured - Total Injured",
    "Drunken Driving/Consumption of Alcohol and Drug - Number of Accidents",
    "Drunken Driving/Consumption of Alcohol and Drug - Persons Killed",
    "Drunken Driving/Consumption of Alcohol and Drug - Persons Injured - Grievously Injured",
    "Drunken Driving/Consumption of Alcohol and Drug - Persons Injured - Minor Injury",
    "Drunken Driving/Consumption of Alcohol and Drug - Persons Injured - Total Injured",
    "Driving on Wrong Side - Number of Accidents",
    "Driving on Wrong Side - Persons Killed",
    "Driving on Wrong Side - Persons Injured - Grievously Injured",
    "Driving on Wrong Side - Persons Injured - Minor Injury",
    "Driving on Wrong Side - Persons Injured - Total Injured",
    "Jumping Red Light - Number of Accidents",
    "Jumping Red Light - Persons Killed",
    "Jumping Red Light - Persons Injured - Grievously Injured",
    "Jumping Red Light - Persons Injured - Minor Injury",
    "Jumping Red Light - Persons Injured - Total Injured",
    "Use of Mobile Phone - Number of Accidents",
    "Use of Mobile Phone - Persons Killed",
    "Use of Mobile Phone - Persons Injured - Grievously Injured",
    "Use of Mobile Phone - Persons Injured - Minor Injury",
    "Use of Mobile Phone - Persons Injured - Total Injured",
    "Others - Number of Accidents",
    "Others - Persons Killed",
    "Others - Persons Injured - Grievously Injured",
    "Others - Persons Injured - Minor Injury",
    "Others - Persons Injured - Total Injured",
)

_MORTH_A47_RA2020_2021 = (  # verbatim from RA2020_A47.csv; RA2021_A47.csv is byte-identical
    "Million Plus Cities",
    "Over-Speeding - Number of Accidents - Number",
    "Over-Speeding - Number of Accidents - Rank",
    "Over-Speeding - Persons Killed - Number",
    "Over-Speeding - Persons Killed - Rank",
    "Over-Speeding - Persons Injured - Greviously Injured",
    "Over-Speeding - Persons Injured - Minor Injury",
    "Over-Speeding - Persons Injured - Total Injured",
    "Drunken Driving/ Consumption of alcohol and drug  - Number of Accidents",
    "Drunken Driving/ Consumption of alcohol and drug  - Persons Killed",
    "Drunken Driving/ Consumption of alcohol and drug  - Persons Injured - Greviously Injured",
    "Drunken Driving/ Consumption of alcohol and drug  - Persons Injured - Minor Injury",
    "Drunken Driving/ Consumption of alcohol and drug  - Persons Injured - Total Injured",
    "Driving on Wrong side - Number of Accidents",
    "Driving on Wrong side - Persons Killed",
    "Driving on Wrong side - Persons Injured - Greviously Injured",
    "Driving on Wrong side - Persons Injured - Minor Injury",
    "Driving on Wrong side - Persons Injured - Total Injured",
    "Jumping Red Light - Number of Accidents",
    "Jumping Red Light - Persons Killed",
    "Jumping Red Light - Persons Injured - Greviously Injured",
    "Jumping Red Light - Persons Injured - Minor Injury",
    "Jumping Red Light - Persons Injured - Total Injured",
    "Use of Mobile Phone - Number of Accidents",
    "Use of Mobile Phone - Persons Killed",
    "Use of Mobile Phone - Persons Injured - Greviously Injured",
    "Use of Mobile Phone - Persons Injured - Minor Injury",
    "Use of Mobile Phone - Persons Injured - Total Injured",
    "Others - Number of Accidents",
    "Others - Persons Killed",
    "Others - Persons Injured - Greviously Injured",
    "Others - Persons Injured - Minor Injury",
    "Others - Persons Injured - Total Injured",
)
_MORTH_A47_RA2022 = (  # verbatim from Transport_2022_Annexure_47.csv
    "Sl. No.",
    "Million Plus Cities",
    "Over-Speeding - Number of Accidents - Number",
    "Over-Speeding - Number of Accidents - Rank",
    "Over-Speeding - Persons Killed - Number",
    "Over-Speeding - Persons Killed - Rank",
    "Over-Speeding - Persons Injured - Grievously Injured",
    "Over-Speeding - Persons Injured - Minor Injury",
    "Over-Speeding - Persons Injured - Total Injured",
    "Drunken Driving/ Consumption of alcohol and drug - Number of Accidents",
    "Drunken Driving/ Consumption of alcohol and drug - Persons Killed",
    "Drunken Driving/ Consumption of alcohol and drug - Persons Injured - Grievously Injured",
    "Drunken Driving/ Consumption of alcohol and drug - Persons Injured - Minor Injury",
    "Drunken Driving/ Consumption of alcohol and drug - Persons Injured - Total Injured",
    "Driving on Wrong side - Number of Accidents",
    "Driving on Wrong side - Persons Killed",
    "Driving on Wrong side - Persons Injured - Grievously Injured",
    "Driving on Wrong side - Persons Injured - Minor Injury",
    "Driving on Wrong side - Persons Injured - Total Injured",
    "Jumping Red Light - Number of Accidents",
    "Jumping Red Light - Persons Killed",
    "Jumping Red Light - Persons Injured - Grievously Injured",
    "Jumping Red Light - Persons Injured - Minor Injury",
    "Jumping Red Light - Persons Injured - Total Injured",
    "Use of Mobile Phone - Number of Accidents",
    "Use of Mobile Phone - Persons Killed",
    "Use of Mobile Phone - Persons Injured - Grievously Injured",
    "Use of Mobile Phone - Persons Injured - Minor Injury",
    "Use of Mobile Phone - Persons Injured - Total Injured",
    "Others - Number of Accidents",
    "Others - Persons Killed",
    "Others - Persons Injured - Grievously Injured",
    "Others - Persons Injured - Minor Injury",
    "Others - Persons Injured - Total Injured",
)
_MORTH_A47_RA2023 = (  # verbatim from Transport_2023_Annexure_47.csv
    "Sl. No",
    "Million Plus Cities",
    "Over-Speeding - Number of Accidents - Number",
    "Over-Speeding - Number of Accidents - Rank",
    "Over-Speeding - Persons Killed - Number",
    "Over-Speeding - Persons Killed - Rank",
    "Over-Speeding - Persons Injured - Grievously Injured",
    "Over-Speeding - Persons Injured - Minor Injury",
    "Over-Speeding - Persons Injured - Total Injured",
    "Drunken Driving/ Consumption of alcohol & drug - Number of Accidents",
    "Drunken Driving/ Consumption of alcohol & drug - Persons Killed",
    "Drunken Driving/ Consumption of alcohol & drug - Persons Injured - Grievously Injured",
    "Drunken Driving/ Consumption of alcohol & drug - Persons Injured - Minor Injury",
    "Drunken Driving/ Consumption of alcohol & drug - Persons Injured - Total Injured",
    "Driving on Wrong side - Number of Accidents",
    "Driving on Wrong side - Persons Killed",
    "Driving on Wrong side - Persons Injured - Grievously Injured",
    "Driving on Wrong side - Persons Injured - Minor Injury",
    "Driving on Wrong side - Persons Injured - Total Injured",
    "Jumping Red Light - Number of Accidents",
    "Jumping Red Light - Persons Killed",
    "Jumping Red Light - Persons Injured - Grievously Injured",
    "Jumping Red Light - Persons Injured - Minor Injury",
    "Jumping Red Light - Persons Injured - Total Injured",
    "Use of Mobile Phone - Number of Accidents",
    "Use of Mobile Phone - Persons Killed",
    "Use of Mobile Phone - Persons Injured - Grievously Injured",
    "Use of Mobile Phone - Persons Injured - Minor Injury",
    "Use of Mobile Phone - Persons Injured - Total Injured",
    "Others - Number of Accidents",
    "Others - Persons Killed",
    "Others - Persons Injured - Grievously Injured",
    "Others - Persons Injured - Minor Injury",
    "Others - Persons Injured - Total Injured",
)


@dataclass(frozen=True)
class SchemaVersion:
    """One registered header and how its columns are typed when ingested.

    ``numeric_columns`` are parsed to numbers in the typed view; every other column stays
    text. ``rank_columns`` are numeric but are publisher ranks, not counts.
    """

    family: str  # bwssb_monthly | census_ward_profile | swm_gcp | morth_city_a47
    version: str
    columns: tuple[str, ...]
    level: str  # ward | million-plus city
    id_column: str | None
    label_column: str
    numeric_columns: tuple[str, ...]
    rank_columns: tuple[str, ...] = ()
    validator: str | None = None  # manifest semantic_checks.validator prefix, if any


def _ranks(columns: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(c for c in columns if c.strip().lower().endswith("- rank"))


SCHEMAS: tuple[SchemaVersion, ...] = (
    SchemaVersion(
        family="bwssb_monthly",
        version="bwssb_monthly/v1",
        columns=_BWSSB_V1,
        level="ward",
        id_column="Ward number ",
        label_column="Ward Name",
        numeric_columns=("Ward number ", "Number of Connections", "Consumption in ML"),
        validator="bwssb",
    ),
    SchemaVersion(
        family="census_ward_profile",
        version="census_ward_profile/v1",
        columns=_CENSUS_V1,
        level="ward",
        id_column="Ward No.",
        label_column="Ward Name",
        numeric_columns=_CENSUS_V1[3:],
    ),
    SchemaVersion(
        family="swm_gcp",
        version="swm_gcp/v1",
        columns=_SWM_GCP_V1,
        level="ward",
        id_column="Ward_No.",
        label_column="Ward_Name",
        numeric_columns=_SWM_GCP_V1[3:],
    ),
    SchemaVersion(
        family="morth_city_a47",
        version="morth_city_a47/ra2019",
        columns=_MORTH_A47_RA2019,
        level="million-plus city",
        id_column=None,
        label_column="States/UTs",
        numeric_columns=_MORTH_A47_RA2019[1:],
        rank_columns=_ranks(_MORTH_A47_RA2019),
        validator="morth_city",
    ),
    # Batch 02 editions. 2020 and 2021 publish byte-identical headers, so one version
    # covers both (headers must be unique); each edition stays its own dataset id and hash.
    SchemaVersion(
        family="morth_city_a47",
        version="morth_city_a47/ra2020_2021",
        columns=_MORTH_A47_RA2020_2021,
        level="million-plus city",
        id_column=None,
        label_column="Million Plus Cities",
        numeric_columns=_MORTH_A47_RA2020_2021[1:],
        rank_columns=_ranks(_MORTH_A47_RA2020_2021),
        validator="morth_city",
    ),
    SchemaVersion(
        family="morth_city_a47",
        version="morth_city_a47/ra2022",
        columns=_MORTH_A47_RA2022,
        level="million-plus city",
        id_column=None,
        label_column="Million Plus Cities",
        numeric_columns=_MORTH_A47_RA2022[2:],
        rank_columns=_ranks(_MORTH_A47_RA2022),
        validator="morth_city",
    ),
    SchemaVersion(
        family="morth_city_a47",
        version="morth_city_a47/ra2023",
        columns=_MORTH_A47_RA2023,
        level="million-plus city",
        id_column=None,
        label_column="Million Plus Cities",
        numeric_columns=_MORTH_A47_RA2023[2:],
        rank_columns=_ranks(_MORTH_A47_RA2023),
        validator="morth_city",
    ),
    SchemaVersion(
        family="morth_city_a47",
        version="morth_city_a47/ra2024",
        columns=_MORTH_A47_RA2024,
        level="million-plus city",
        id_column=None,
        label_column="Million Plus Cities",
        numeric_columns=_MORTH_A47_RA2024[2:],
        rank_columns=_ranks(_MORTH_A47_RA2024),
        validator="morth_city",
    ),
)

_BY_HEADER = {s.columns: s for s in SCHEMAS}
_BY_VERSION = {s.version: s for s in SCHEMAS}
assert len(_BY_HEADER) == len(SCHEMAS), "two registered schemas share a header"


def detect_schema(header: list[str] | tuple[str, ...]) -> SchemaVersion | None:
    """The schema whose header equals ``header`` exactly, or None. Never fuzzy."""
    return _BY_HEADER.get(tuple(header))


def get_schema(version: str) -> SchemaVersion:
    return _BY_VERSION[version]


__all__ = ["SCHEMAS", "SchemaVersion", "detect_schema", "get_schema"]
