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

## What is kept in git, and what is not

The PDFs are not. 4,073 of them were committed by the earlier scraper and stay
where they are, but nothing fetched since is tracked: the English collection
alone projects to 11.6 GB at 287 KB per document, and six official languages to
roughly 70 GB.

So the tree is asymmetric on purpose. Documents from roughly 2020 to 2023 have
their PDF beside them; everything else has only the extracted text. The PDFs
are reproducible from `scripts/docs.un.org/fetch.py`, the symbol list, and
`data/fetch-manifest.jsonl`.

The extracted text is kept, at 16.9 KB per document against 287 KB for the PDF.
It is also the part that cannot simply be fetched again: the site moved once
already, and it took a day to work out where it had gone.
