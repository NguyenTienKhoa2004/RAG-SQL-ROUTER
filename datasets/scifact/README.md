# BEIR SciFact (Parquet)

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip
BEIR: https://github.com/beir-cellar/beir

| File | Columns |
| --- | --- |
| corpus.parquet | _id, title, text, metadata |
| queries.parquet | _id, text, metadata |
| qrels.parquet | query_id, corpus_id, score, split |

IDs remain strings; score is int64; split is train or test. Files use Zstandard compression. The original metadata objects are stored as JSON strings to preserve empty objects and variable keys; decode with json.loads if needed.

Read with pandas.read_parquet or pyarrow.parquet.read_table. Only the corpus is indexed. For test evaluation, filter qrels to split == "test" and join query_id to queries._id. Preserve corpus._id in retrieval results to compare with qrels.corpus_id.

All source rows are retained, including queries without train/test relevance judgments. manifest.json records source checksum, row counts, file hashes, and validation results. Every Parquet file was read back and compared with the source, including decoded metadata. No embeddings or Milvus collection have been created.
