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
REPO = "yuiseki/undocs"

# Read as they are. Everything in this dataset is a string or a count, so
# unlike the ragged question sets there is nothing to carry as embedded JSON.
STRING_FIELDS = [
    "id", "lang", "body", "pdf",
    "date_distributed", "date_distributed_rule", "date_distributed_raw",
    "date_adopted", "date_adopted_rule", "date_adopted_raw",
    "date_other", "date_other_rule", "date_other_raw",
]
INT_FIELDS = ["n_chars"]


def rows(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            row = {k: r.get(k) for k in STRING_FIELDS}
            for k in INT_FIELDS:
                row[k] = r.get(k)
            out.append(row)
    return out


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
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--push", action="store_true", help="actually upload")
    ap.add_argument("--skip-check", action="store_true",
                    help="do not check the jsonl against the directories first")
    a = ap.parse_args()

    if not a.skip_check and stale(a.jsonl, a.roots):
        raise SystemExit("data/resolutions.jsonl is older than the text it was "
                         "built from. Run scripts/extract/build_jsonl.py")

    import datasets

    table = rows(a.jsonl)
    features = datasets.Features(
        {k: datasets.Value("string") for k in STRING_FIELDS} |
        {k: datasets.Value("int64") for k in INT_FIELDS})
    ds = datasets.Dataset.from_list(table, features=features)
    print(ds)

    langs = sorted({r["lang"] for r in table})
    chars = sum(r["n_chars"] or 0 for r in table)
    print(f"{len(table):,} documents, {chars:,} characters, languages {langs}, "
          f"{os.path.getsize(a.jsonl)/1e6:.1f} MB of jsonl")

    for p in [a.card] + a.extra:
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")
    print(f"card {os.path.relpath(a.card, BASE)}, plus " +
          ", ".join(os.path.relpath(p, BASE) for p in a.extra))

    if not a.push:
        print("dry run. pass --push to upload")
        return 0

    from huggingface_hub import DatasetCard, HfApi

    api = HfApi()
    # Nothing else creates it. push_to_hub and upload_file both assume the
    # repository is already there and answer 404 when it is not.
    api.create_repo(a.repo, repo_type="dataset", exist_ok=True)

    # Card first, dataset second. push_to_hub writes a dataset_info block into
    # the card's front matter, and pushing the card afterwards would erase it.
    DatasetCard(open(a.card, encoding="utf-8").read()).push_to_hub(
        a.repo, repo_type="dataset")
    for p in a.extra:
        api.upload_file(path_or_fileobj=p, path_in_repo=os.path.basename(p),
                        repo_id=a.repo, repo_type="dataset")
    ds.push_to_hub(a.repo)
    print(f"pushed to {a.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
