# UN documents, extracted text

`resolutions.jsonl` holds the text of United Nations General Assembly and
Security Council documents, one line per document per language.

Built 2026-09-17. English only so far; the other five official languages are
being collected.

## What is in it

| | |
| --- | --- |
| Records | 4,024 |
| Languages | en |
| Characters | 69,281,547 |
| Median document | 6,929 characters |
| Range | 345 to 5,203,969 characters |
| Date range | 1945 to 2023 |
| General Assembly (`A/`) | 977 |
| Security Council (`S/`) | 3,047 |

## Columns

| Column | Notes |
| --- | --- |
| `id` | the UN document symbol, e.g. `S/RES/2728(2024)` |
| `lang` | ISO 639-1. One of ar, en, es, fr, ru, zh |
| `body` | extracted text |
| `n_chars` | length of `body` |
| `pdf` | path to the source PDF in this repository |
| `date_distributed` | date from the `Distr.` header, ISO 8601 |
| `date_adopted` | date the body states the resolution was adopted |
| `date_other` | a date from the opening when neither of the above is found |
| `date_*_rule` | which pattern matched |
| `date_*_raw` | the text that was matched |

### Why three dates

They are different facts. 2,249 documents carry both a distribution and an
adoption date and 315 of them, 14%, disagree: Security Council documents by a
day or two, General Assembly resolutions by months. `A/RES/66/165` was
distributed on 2012-03-22 and adopted on 2011-12-19.

Coverage:

| Kind | Records | Rules |
| --- | --- | --- |
| `date_distributed` | 3,014 | `distr` 3,014 |
| `date_adopted` | 2,595 | `meeting` 1,887, `resolution_of` 329, `resolution_adopted` 274, `adopted_by` 105 |
| `date_other` | 641 | `any` 641 |
| none | 23 | |

`date_other` is the weak one and says so. It takes the first plausible date in
the opening 4,000 characters, which is as likely to be a citation of an older
resolution as it is to be this document's own date. It is only written when
neither of the other two is found.

Every date is checked against the year in the document symbol. That is what
caught `S/RES/1139(1997)`, whose adoption line reads 1987-11-21 because OCR
misread a digit; the distribution date is 1997-11-21.

## How it was made

1. PDFs fetched from `docs.un.org`. See `../docs/findings/2026-09-17-fetching.md`
   for how that works now, which is not how the older scraper assumed.
2. `scripts/extract/pdf_to_text.py` runs `pdftotext` without `-layout` and
   writes `resolution.txt` beside each PDF.
3. `scripts/extract/extract_date.py` writes `date-distributed.txt`,
   `date-adopted.txt` and `date-other.txt` beside that.
4. `scripts/extract/build_jsonl.py` collects them here.

Form feeds, which `pdftotext` emits at page breaks and which appear in 75% of
documents, are replaced with blank lines. `NO COVER (1)` lines, which are the
scanner noting a missing cover page, are removed.

## Known limitations

**English only, for now.** The crawl for ar, es, fr, ru and zh is running.
`lang` is in the schema so those drop in without a change.

**Skewed towards 2020 to 2023.** The scraper that gathered these PDFs had a
hardcoded year filter, which is why 4,073 of 41,942 known document symbols are
present. Every decade from the 1940s is represented, but the 2020s are
over-represented.

**49 PDFs yield no text.** 47 are scans that produce only page furniture and 2
fail outright. They have no `resolution.txt` and no record here, rather than an
empty one.

**The largest records are compilations.** `A/74/49(VOL.I)` at 5.2 M characters
and `S/INF/71` at 3.0 M are annual collections of resolutions, not single
documents. They are left whole; splitting them is a decision for the user.

**Extraction quality is high but not perfect.** Measured as the share of
characters that are letters, digits, spaces or ordinary punctuation, 4,022 of
the 4,024 sit at 1.0. One, `A/RES/981(X)`, falls to 0.24.

## Licence

The documents are in the public domain. See `LICENSE` in this directory.
