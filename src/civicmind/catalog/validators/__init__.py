"""Dataset-specific validators, one module per dataset family.

- ``bwssb_monthly``: BWSSB monthly ward water consumption (duplicates reported, not resolved).
- ``morth_city_table``: MoRTH million-plus city tables (Total row vs sum of rows).
- ``census_ward_profile``: 2011 ward demographic profile (name cycle, unit label, empty columns).
- ``swm_gcp``: solid waste generated/collected/processed (modelled-value signature).

A file that parses is not thereby valid. Validators report findings; they never rewrite data.
"""
