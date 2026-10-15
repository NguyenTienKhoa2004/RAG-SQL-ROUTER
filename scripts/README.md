# BEIR subset downloader

From the project root, run:

```powershell
uv run --with pyarrow --with requests python scripts/download_beir_subset.py --dataset fiqa --queries 100
uv run --with pyarrow --with requests python scripts/download_beir_subset.py --dataset arguana --queries 100
uv run --with pyarrow --with requests python scripts/download_beir_subset.py --dataset nq --queries 500
```

Change `--dataset` to a name from the [official public BEIR dataset catalog](https://github.com/beir-cellar/beir/wiki/Datasets-available), such as `hotpotqa`, `nfcorpus`, `scidocs`, `quora` or `scifact`.

- `--split test`: label split; `dev` and `train` are accepted when present in the archive.
- `--queries 100`: select 100 query IDs in natural order with positive qrels, then collect all positively labeled documents for them. Document count can exceed query count.
- `--output datasets/my-corpus`: destination; generated files with the same names are overwritten.
- `--archive path/to/dataset.zip`: use a local ZIP offline.

The default destination is `datasets/<dataset>-<split>-<queries>/`. The script exports `corpus.md`, `corpus.parquet`, `queries.parquet`, `qrels.parquet`, `sample-questions.md`, `README.md` and `manifest.json`. Only upload `corpus.md` to the project's documents API.

The remote ZIP is read through HTTP byte ranges, including its ZIP directory. The script stops reading the corpus after finding all selected references. Selecting a few queries can still require scanning a large portion of a corpus if their documents are near the end.

Archives must contain one `corpus.jsonl`, one `queries.jsonl` and `qrels/<split>.tsv`, with an optional directory prefix. A bundle of multiple subdatasets (such as the combined CQADupStack archive) requires a separate standard ZIP for one subdataset. Restricted datasets are not downloaded automatically. Unknown dataset names, unavailable splits and missing referenced IDs produce explicit errors.

Original document IDs and text are preserved; metadata is stored as a JSON string in Parquet. Markdown headings use ASCII `-` to avoid PowerShell encoding issues. Source Markdown may cause the upload parser to split a document into additional nodes.

This subset contains relevant documents only, without additional distractors; it is for RAG exploration rather than a full BEIR benchmark. Query tasks differ between datasets: for example, Quora's corpus contains questions rather than answer passages. Use the source dataset's attribution and license.

