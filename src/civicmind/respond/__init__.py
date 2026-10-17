"""Response composition and verification.

Implemented: ``compose`` (deterministic templates; every number in the text must occur in
the evidence package). No language model.

Responsibilities:
- Compose answers from an evidence package with a deterministic template: direct answer,
  geography and period, units and method, citations, caveats, and a human-review note for
  recommendations.
- Optional future language-model phrasing, accepted only if the claim verifier passes:
  every number appears in the evidence, every citation id is valid, and no causal or
  forecast language appears without support. Otherwise fall back to the template.
- Clear "cannot answer from available evidence" responses.

Boundary: depends on ``evidence``. No language-model provider is configured at this stage.
"""
