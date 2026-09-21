#!/usr/bin/env python3
"""Push the extracted documents and their card to the Hugging Face Hub.

What goes up is the table and the three files that explain it. What stays in
git is everything the table is made of: the PDFs, the per-document text, and
the extracted dates.

The record is flat and every field is a string or a number, so the table is the
record. The one decision is that the date kinds stay as separate columns rather
than being collapsed: 315 of the 2,249 documents that carry both a distribution
and an adoption date disagree, and which one a reader wants depends on what
they are doing.

    python3 scripts/publish.py             # dry run, prints the schema
    python3 scripts/publish.py --push      # uploads
"""
import argparse
import json
import os
import subprocess
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
REPO = "yuiseki/un-docs"

# Read as they are. Everything in this dataset is a string or a count, so
# unlike the ragged question sets there is nothing to carry as embedded JSON.
STRING_FIELDS = [
    "id", "lang", "body", "text_source", "pdf",
    "date_distributed", "date_distributed_rule", "date_distributed_raw",
    "date_adopted", "date_adopted_rule", "date_adopted_raw",
    "date_other", "date_other_rule", "date_other_raw",
]
INT_FIELDS = ["n_chars"]


BATCH = 2000


def to_parquet(jsonl, out):
    """Stream the jsonl into one Parquet file, and report what went in.

    Not datasets.Dataset.from_list: the English collection alone is 1.2 GB of
    text across 37,499 documents, and holding that as Python objects to hand to
    the Hub costs several times its own size for nothing. Parquet is the
    published form anyway.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    schema = pa.schema([(k, pa.string()) for k in STRING_FIELDS] +
                       [(k, pa.int64()) for k in INT_FIELDS])
    fields = STRING_FIELDS + INT_FIELDS
    writer = pq.ParquetWriter(out, schema, compression="zstd")
    batch = {k: [] for k in fields}
    n = chars = 0
    langs = set()
    try:
        with open(jsonl, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                for k in fields:
                    batch[k].append(r.get(k))
                n += 1
                chars += r.get("n_chars") or 0
                langs.add(r.get("lang"))
                if len(batch["id"]) >= BATCH:
                    writer.write_table(pa.Table.from_pydict(batch, schema=schema))
                    batch = {k: [] for k in fields}
        if batch["id"]:
            writer.write_table(pa.Table.from_pydict(batch, schema=schema))
    finally:
        writer.close()
    return n, chars, sorted(x for x in langs if x)


def stale(jsonl, roots):
    """Whether any resolution.txt is newer than the jsonl built from them.

    Publishing a jsonl older than the text it was built from would put out
    documents that are not the ones in git.
    """
    if not os.path.exists(jsonl):
        return True
    built = os.path.getmtime(jsonl)
    for root in roots:
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                if name == "resolution.txt" or name.startswith("date-"):
                    if os.path.getmtime(os.path.join(dirpath, name)) > built:
                        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default=os.path.join(BASE, "data/resolutions.jsonl"))
    ap.add_argument("--card", default=os.path.join(BASE, "data/README.md"))
    ap.add_argument("--extra", nargs="*", default=[
        os.path.join(BASE, "data/LICENSE"),
        os.path.join(BASE, "data/provenance.yaml")])
    ap.add_argument("--roots", nargs="*", default=[os.path.join(BASE, "en/pdfs")],
                    help="directories the jsonl was built from, for the staleness check")
    ap.add_argument("--parquet", default=None,
                    help="where to write the table; default data/documents.parquet")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--push", action="store_true", help="actually upload")
    ap.add_argument("--skip-check", action="store_true",
                    help="do not check the jsonl against the directories first")
    a = ap.parse_args()

    if not a.skip_check and stale(a.jsonl, a.roots):
        raise SystemExit("data/resolutions.jsonl is older than the text it was "
                         "built from. Run scripts/extract/build_jsonl.py")

    parquet = a.parquet or os.path.join(BASE, "data/documents.parquet")
    n, chars, langs = to_parquet(a.jsonl, parquet)
    print(f"{n:,} documents, {chars:,} characters, languages {langs}")
    print(f"  {a.jsonl.split('/')[-1]} {os.path.getsize(a.jsonl)/1e6:.0f} MB "
          f"-> {os.path.basename(parquet)} {os.path.getsize(parquet)/1e6:.0f} MB")

    for p in [a.card] + a.extra:
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")
    print(f"card {os.path.relpath(a.card, BASE)}, plus " +
          ", ".join(os.path.relpath(p, BASE) for p in a.extra))

    if not a.push:
        print("dry run. pass --push to upload")
        return 0

    from huggingface_hub import HfApi

    api = HfApi()
    # Nothing else creates it. upload_file answers 404 when it is not there.
    api.create_repo(a.repo, repo_type="dataset", exist_ok=True)

    # Data first, card last. Nothing here rewrites the card, so this ordering
    # means the repository is never in a state where the card describes files
    # that have not arrived.
    print(f"uploading {os.path.basename(parquet)} ...", flush=True)
    api.upload_file(path_or_fileobj=parquet, path_in_repo=os.path.basename(parquet),
                    repo_id=a.repo, repo_type="dataset")
    for p in a.extra:
        api.upload_file(path_or_fileobj=p, path_in_repo=os.path.basename(p),
                        repo_id=a.repo, repo_type="dataset")
    api.upload_file(path_or_fileobj=a.card, path_in_repo="README.md",
                    repo_id=a.repo, repo_type="dataset")
    print(f"pushed to https://huggingface.co/datasets/{a.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
