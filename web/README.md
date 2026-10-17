# Website (future)

Not started. The website is built only after the API contract (`src/civicmind/api`) is frozen.

Planned: a CivicMind AI workspace page with:
- natural-language question input and example questions limited to supported datasets;
- an answer card with citations, period and geography, method and units, caveats, and a
  "how this result was produced" summary;
- tables and charts only where the data supports them;
- a dataset/source explorer showing provenance, coverage, validation status and limitations;
- clear insufficient-data, abstention and error states;
- optional feedback controls (useful / incorrect / missing evidence).

The browser talks only to the backend API, never to data files or model providers.
Candidate stack (provisional): React + TypeScript + Vite, with a lightweight chart
library. No frontend dependencies are added yet.
