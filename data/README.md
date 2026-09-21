---
license: other
license_name: united-nations-parliamentary-documentation
license_link: https://shop.un.org/rights-permissions
language:
- en
size_categories:
- 10K<n<100K
task_categories:
- text-generation
- fill-mask
tags:
- united-nations
- legal
- government
- diplomacy
pretty_name: UN Documents
configs:
- config_name: default
  data_files: documents.parquet
---

# UN Documents

The text of 39,363 United Nations General Assembly and Security Council
documents, 1945 to 2023. Every PDF the UN publishes for these symbols is here:
37,499 carry a text layer, and the remaining 1,864 are scans, read with
tesseract.

Code and provenance: https://github.com/yuiseki/undocs

## What is in it

| | |
| --- | --- |
| Documents | 39,363 |
| Characters | 1,312,301,724 |
| Median document | 8,918 characters |
| Range | 204 to 5,271,307 characters |
| Years | 1945 to 2023 |
| From the PDF text layer | 37,499 |
| Read with tesseract | 1,864 |
| Languages | en |

Every decade is represented: about 950 documents from the 1940s, 2,400 from the
1960s, 4,900 from the 1990s, 9,500 from the 2010s. The weighting towards recent
decades is the UN's own, not the collection's.

## Columns

| Column | Notes |
| --- | --- |
| `id` | the UN document symbol, e.g. `S/RES/2728 (2024)` |
| `lang` | ISO 639-1 |
| `body` | extracted text |
| `n_chars` | length of `body` |
| `text_source` | `pdf` or `ocr` |
| `pdf` | path to the source PDF in the repository, where it is kept |
| `date_distributed` | date from the `Distr.` header, ISO 8601 |
| `date_adopted` | date the body states the resolution was adopted |
| `date_other` | a date from the opening when neither of the above is found |
| `date_*_rule` | which pattern matched |
| `date_*_raw` | the text that was matched |

### Why three dates rather than one

They are different facts, and they disagree often enough that collapsing them
would be a choice made on the reader's behalf. 7,517 documents carry both a
distribution and an adoption date, and 4,575 of those, 61%, differ. The median
gap is 39 days, which is the General Assembly's ordinary rhythm: resolutions are
adopted in December and distributed in late January.

| | documents |
| --- | --- |
| `date_distributed` | 19,283 |
| `date_other` | 16,695 |
| `date_adopted` | 8,206 |
| no date found | 996 |

Every date is checked against the year the symbol implies, whether that year is
written out, as in `S/RES/2728 (2024)`, or carried by a General Assembly session
number, where session N opens in September of 1945 + N. A date more than a year
away from it comes from something the body cites rather than from the document,
and is dropped.

## The 1,864 that were read from images

These are scans with no text layer, mostly General Assembly supplements from
around 1950: `A/1251` is 76 pages, `A/10034(SUPP)` is 196. tesseract 5.5 read
them at 300 dpi, 18,811 pages in all, adding 84,235,244 characters.

`text_source` says which is which. Filter on it if the distinction matters:
what tesseract produces is a reading of an image, not something a publisher
wrote down. It is good but not perfect. In a 200-file sample, 0.6% of
characters fall outside the ordinary set of letters, digits and punctuation,
and errors cluster in document symbols and small print: `S/26347` is read as
`$/26347`. Body text and place names come through.

## What is not here

**Only English.** The other five official languages are collected by the same
scraper and are not done.

**The `pdf` column points into the repository, where most PDFs are not kept.**
4,073 of them are, from an earlier collection; the rest were left out because
English alone is 17 GB. `scripts/docs.un.org/fetch.py` and
`data/fetch-manifest.jsonl` reproduce them.

**Eight documents have a distribution date a year before their adoption date.**
`S/RES/1231 (1999)` reads as distributed 1998-03-11 and adopted 1999-03-11. Both
are within a year of the symbol's own year, so the check cannot separate them;
the document itself is probably what is wrong.

## Licence

United Nations parliamentary documentation, and material published under a UN
document symbol and not offered for sale, is excluded from United Nations
copyright. See `LICENSE` and `provenance.yaml`.

The extracted text is a mechanical transcription adding no authorship. Any
right arising from the assembly of this collection is waived.
