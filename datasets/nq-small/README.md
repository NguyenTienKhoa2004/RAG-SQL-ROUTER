# BEIR NQ small subset

This is a small English Wikipedia passage corpus for trying the project's RAG upload API.

- Selection: the first 500 test query IDs in numeric order (`test0` through `test499`) with positive qrels, and all passages positively labeled for them.
- Corpus: 623 unique passages. Queries: 500. Positive qrels: 623.
- Original string IDs and passage text are preserved. Metadata in Parquet is encoded as a JSON string.
- This subset contains relevant passages only, without additional distractors. It is useful for a demo, not a full NQ retrieval benchmark.

## Files

| File | Purpose |
| --- | --- |
| `corpus.md` | Upload this file through the documents API. Each passage has its own `# ID - title` heading. |
| `corpus.parquet` | Structured corpus with `_id`, `title`, `text`, `metadata`. |
| `queries.parquet` | The selected questions, with `_id`, `text`, `metadata`. |
| `qrels.parquet` | Positive labels with `query_id`, `corpus_id`, `score`, `split`. |
| `sample-questions.md` | 30 questions to try, with their relevant corpus IDs. These are source references, not answer strings. |
| `manifest.json` | Sources, selection details, file sizes and SHA-256 checksums. |

Create a fresh session if you want to search this corpus without previously uploaded files. Upload only `corpus.md`; uploading question or qrels files would mix test information into the document sources.

These are historical Wikipedia passages from the dataset snapshot. Interpret time-sensitive answers against that snapshot.

## Sources and attribution

- [Official BEIR NQ archive](https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nq.zip)
- [BEIR NQ on Hugging Face](https://huggingface.co/datasets/BeIR/nq)
- [BEIR NQ qrels on Hugging Face](https://huggingface.co/datasets/BeIR/nq-qrels)
- [Natural Questions](https://ai.google.com/research/NaturalQuestions/)

Hugging Face labels the BEIR NQ distribution CC BY-SA 4.0. This subset changes only the selection, metadata encoding and Markdown presentation, preserving source passage text and original IDs. Wikipedia titles and corpus IDs identify the source passages.
