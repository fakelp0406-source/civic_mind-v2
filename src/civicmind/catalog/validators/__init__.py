"""Dataset-specific validators, one module per dataset family (not yet implemented).

Planned examples from the discovery and audit findings:
- MoRTH tables: the ``Total`` row equals the sum of the other rows; negative counts flagged.
- BWSSB monthly ward files: duplicated ward numbers reported; schema identical across months.
- BBMP solid-waste snapshots: units (MT/year vs TPD) and ward keys checked.

A file that parses is not thereby valid. Validators report findings; they never rewrite data.
"""
