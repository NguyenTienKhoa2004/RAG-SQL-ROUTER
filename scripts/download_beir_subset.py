"""Download a BEIR subset and export a Markdown corpus for the RAG upload API."""

import argparse
from collections import OrderedDict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets"
CATALOG_URL = "https://github.com/beir-cellar/beir/wiki/Datasets-available"


class HTTPRangeReader(io.RawIOBase):
    """Seek through a remote ZIP without downloading the entire archive."""

    def __init__(self, url, block_size=256 * 1024):
        super().__init__()
        self.url = url
        self.block_size = block_size
        self.position = 0
        self.downloaded = 0
        self.blocks = OrderedDict()
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        try:
            with self.session.get(url, headers={"Range": "bytes=0-0"}, stream=True, timeout=(15, 90)) as response:
                response.raise_for_status()
                match = re.fullmatch(r"bytes 0-0/(\d+)", response.headers.get("Content-Range", ""))
                if response.status_code != 206 or not match:
                    raise ValueError("Server does not support byte ranges; use --archive with a local BEIR ZIP.")
                self.size = int(match[1])
                if len(response.content) != 1:
                    raise ValueError("Invalid archive range response.")
                self.downloaded = 1
        except Exception:
            self.session.close()
            raise

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        position = offset + (0 if whence == 0 else self.position if whence == 1 else self.size)
        if whence not in (0, 1, 2) or position < 0:
            raise ValueError("Invalid seek position.")
        self.position = position
        return position

    def read(self, size=-1):
        stop = self.size if size < 0 else min(self.size, self.position + size)
        parts = []
        while self.position < stop:
            start = self.position // self.block_size * self.block_size
            if start not in self.blocks:
                end = min(start + self.block_size, self.size) - 1
                with self.session.get(self.url, headers={"Range": f"bytes={start}-{end}"}, stream=True, timeout=(15, 90)) as response:
                    response.raise_for_status()
                    expected = f"bytes {start}-{end}/{self.size}"
                    if response.status_code != 206 or response.headers.get("Content-Range") != expected:
                        raise ValueError("Unexpected byte range from archive server.")
                    content = response.content
                    if len(content) != end - start + 1:
                        raise ValueError("Incomplete archive range response.")
                self.downloaded += len(content)
                self.blocks[start] = content
                if len(self.blocks) > 16:
                    self.blocks.popitem(last=False)
            self.blocks.move_to_end(start)
            block = self.blocks[start]
            length = min(stop - self.position, len(block) - (self.position - start))
            parts.append(block[self.position - start:self.position - start + length])
            self.position += length
        return b"".join(parts)

    def close(self):
        self.session.close()
        super().close()


def member(archive, suffix):
    matches = [name for name in archive.namelist() if name == suffix or name.endswith("/" + suffix)]
    if len(matches) != 1:
        if not matches:
            raise ValueError(f"Archive has no {suffix}. Check --split or use a standard BEIR archive.")
        raise ValueError(f"Archive contains multiple {suffix} files; provide a ZIP for one dataset/subdataset.")
    return matches[0]


def natural_key(value):
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value))


def collect_rows(archive, name, wanted):
    rows = {}
    with archive.open(name) as source, io.TextIOWrapper(source, encoding="utf-8-sig") as text:
        for line in text:
            if not line.strip():
                continue
            row = json.loads(line)
            identifier = row.get("_id")
            if not isinstance(identifier, str):
                raise ValueError(f"{name}: IDs must be strings.")
            if identifier in wanted:
                if identifier in rows:
                    raise ValueError(f"Duplicate selected ID {identifier} in {name}.")
                rows[identifier] = row
                if len(rows) == len(wanted):
                    break
    missing = wanted - rows.keys()
    if missing:
        raise ValueError(f"{name}: {len(missing)} referenced IDs missing, e.g. {sorted(missing)[:3]}.")
    return [rows[identifier] for identifier in sorted(wanted, key=natural_key)]


def load_subset(archive, split, query_count):
    corpus_name = member(archive, "corpus.jsonl")
    query_name = member(archive, "queries.jsonl")
    qrels_name = member(archive, f"qrels/{split}.tsv")
    labels = {}
    with archive.open(qrels_name) as source, io.TextIOWrapper(source, encoding="utf-8-sig", newline="") as text:
        reader = csv.DictReader(text, delimiter="\t")
        if not {"query-id", "corpus-id", "score"}.issubset(reader.fieldnames or []):
            raise ValueError("Qrels must have query-id, corpus-id and score columns.")
        for row in reader:
            score = int(row["score"])
            if score > 0:
                pair = (row["query-id"], row["corpus-id"])
                labels[pair] = max(score, labels.get(pair, 0))
    eligible = sorted({query_id for query_id, _ in labels}, key=natural_key)
    if not eligible:
        raise ValueError(f"No positively labeled queries in split {split}.")
    if query_count > len(eligible):
        raise ValueError(f"Split {split} has only {len(eligible)} labeled queries; use --queries {len(eligible)} or fewer.")
    selected = set(eligible[:query_count])
    qrels = [
        {"query_id": query_id, "corpus_id": corpus_id, "score": score, "split": split}
        for (query_id, corpus_id), score in sorted(labels.items(), key=lambda item: (natural_key(item[0][0]), natural_key(item[0][1])))
        if query_id in selected
    ]
    wanted = {row["corpus_id"] for row in qrels}
    print(f"Selected {len(selected)} queries and {len(wanted)} relevant documents.", flush=True)
    queries = collect_rows(archive, query_name, selected)
    corpus = collect_rows(archive, corpus_name, wanted)
    if any(not (row.get("text", "").strip() or row.get("title", "").strip()) for row in corpus):
        raise ValueError("A selected corpus document has no readable title or text.")
    return corpus, queries, qrels


def export_subset(out, dataset, split, corpus, queries, qrels, source, downloaded=None):
    out.mkdir(parents=True, exist_ok=True)
    corpus_rows = [{"_id": row["_id"], "title": row.get("title", ""), "text": row.get("text", ""),
                    "metadata": json.dumps(row.get("metadata", {}), ensure_ascii=False)} for row in corpus]
    query_rows = [{"_id": row["_id"], "text": row["text"],
                   "metadata": json.dumps(row.get("metadata", {}), ensure_ascii=False)} for row in queries]
    for filename, rows in (("corpus.parquet", corpus_rows), ("queries.parquet", query_rows), ("qrels.parquet", qrels)):
        path = out / filename
        pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")
        if pq.read_table(path).to_pylist() != rows:
            raise ValueError(f"Parquet verification failed: {filename}")
    markdown = "\n\n".join(
        f"# {row['_id']} - {' '.join(row['title'].split())}\n\n{row['text']}" for row in corpus_rows
    ) + "\n"
    (out / "corpus.md").write_text(markdown, encoding="utf-8")
    references = {}
    for row in qrels:
        references.setdefault(row["query_id"], []).append(row["corpus_id"])
    samples = [f"# {dataset} sample queries", "", "Upload corpus.md. References are relevant document IDs, not answer strings.", ""]
    for query in queries[:30]:
        samples.extend([f"## {query['_id']}", query["text"], f"Relevant corpus IDs: {', '.join(references[query['_id']])}", ""])
    (out / "sample-questions.md").write_text("\n".join(samples), encoding="utf-8")
    readme = (
        f"# BEIR {dataset} small subset\n\n"
        f"Selected {len(queries)} queries from split `{split}` and all {len(corpus)} positively labeled documents.\n\n"
        "Upload only corpus.md to the RAG documents API. Use sample-questions.md for sample queries.\n"
        "Original IDs and document text are preserved; Parquet metadata is a JSON string.\n"
        "This subset contains no extra distractors and is not a full BEIR evaluation.\n"
        "Source Markdown inside documents may produce additional nodes when parsed.\n"
        "The content reflects the dataset snapshot. Check the source dataset's attribution and license.\n\n"
        f"Archive source: {source}\nBEIR catalog: {CATALOG_URL}\n"
    )
    (out / "README.md").write_text(readme, encoding="utf-8")
    filenames = ("corpus.parquet", "queries.parquet", "qrels.parquet", "corpus.md", "sample-questions.md", "README.md")
    manifest = {
        "dataset": dataset, "split": split, "source": source,
        "selection": f"First {len(queries)} positively labeled query IDs in natural order; all positive qrels documents; no extra distractors.",
        "queries": len(queries), "corpus": len(corpus), "qrels": len(qrels),
        "archive_bytes_downloaded": downloaded,
        "verified": {"parquet_round_trip": True, "qrels_references_valid": True},
        "files": {name: {"bytes": (out / name).stat().st_size, "sha256": hashlib.sha256((out / name).read_bytes()).hexdigest()}
                  for name in filenames},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(corpus)} documents and {len(queries)} queries to {out}", flush=True)
    print(f"Upload: {out / 'corpus.md'} ({len(markdown.encode('utf-8')):,} bytes)", flush=True)
    if len(markdown.encode("utf-8")) > 20 * 1024 * 1024:
        print("corpus.md exceeds the API's default 20 MiB upload limit; select fewer queries or increase MAX_UPLOAD_MB.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="BEIR name, e.g. nq, fiqa, arguana, scifact, nfcorpus, hotpotqa")
    parser.add_argument("--queries", type=int, default=500, help="Number of positively labeled queries (default: 500)")
    parser.add_argument("--split", choices=("test", "dev", "train"), default="test")
    parser.add_argument("--output", type=Path, help="Destination directory; generated files with the same names are overwritten")
    parser.add_argument("--archive", type=Path, help="Use a local BEIR ZIP instead of downloading")
    args = parser.parse_args(argv)
    if args.queries < 1:
        parser.error("--queries must be positive")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.dataset):
        parser.error("--dataset must be a BEIR name without slashes, e.g. fiqa")
    out = args.output or PROJECT_ROOT / "datasets" / f"{args.dataset}-{args.split}-{args.queries}"
    source = str(args.archive.resolve()) if args.archive else f"{BASE_URL}/{args.dataset}.zip"
    try:
        if args.archive:
            with zipfile.ZipFile(args.archive) as archive:
                corpus, queries, qrels = load_subset(archive, args.split, args.queries)
            downloaded = None
        else:
            print(f"Reading {source}", flush=True)
            with HTTPRangeReader(source) as remote, zipfile.ZipFile(remote) as archive:
                corpus, queries, qrels = load_subset(archive, args.split, args.queries)
                downloaded = remote.downloaded
            print(f"Downloaded {downloaded:,} archive bytes.", flush=True)
        export_subset(out, args.dataset, args.split, corpus, queries, qrels, source, downloaded)
    except (ValueError, OSError, zipfile.BadZipFile, requests.RequestException) as exc:
        parser.exit(1, f"Download failed: {exc}\n")


if __name__ == "__main__":
    main()
