# Research engine provenance

This directory vendors the Basketball in-class research engine so production does not depend on `references/`.

- Upstream version: `2.0.7`
- Upstream commit: `9836a12`
- Upstream repository: <https://github.com/jxk6575/Basketball_inclass_system>
- Productization changes: environment-selected model/data roots, strict runtime failures, automatic 1–6 person sequential enrollment, and `product_runner.py`.

No repository-level license file was present at the vendored commit. Confirm the right to copy, modify, and distribute this engine before any distribution beyond the authorized local research deployment. Model and third-party library licenses are separate; in particular, InsightFace model and Ultralytics commercial-use terms must be reviewed independently.

The research-only diagnostics and internal identifiers remain available in runtime output, but they are never serialized by the public product API.
