# undocs

Fetches United Nations General Assembly and Security Council documents and
extracts their text.

- `data/resolutions.jsonl` is the extracted corpus. See `data/README.md`.
- `docs/findings/` records how the source site actually behaves.
- `scripts/docs.un.org/fetch.py` collects PDFs in the six official languages.
- `scripts/extract/` turns PDFs into text, dates and JSONL.

## Licence

The code is licensed under the [Apache License, Version 2.0](./LICENSE).

The documents it fetches are United Nations parliamentary documentation and are
in the public domain, which is a separate matter from the licence on this code.
See [data/LICENSE](./data/LICENSE).

Earlier revisions of this repository were published under the WTFPL, which the
FSF recognises as a free software licence but the OSI has never approved. It
was replaced so that this code can be used in projects that require
OSI-approved terms. yuiseki is the sole human author of every commit made
before that change; the remaining commits are dependency updates from renovate
and dependabot.
