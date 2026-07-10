# Career KB vault layout (reference)

Checked-in reference for `agentic/hermes/.kb/` structure. The live vault is
gitignored; see the live `README.md` inside your vault after bootstrap.

```
agentic/hermes/.kb/
├── inbox/                 drop zone
├── public/                curated markdown (agents read first)
├── private/               goals, comp, flags, prompts, imports
├── _index/                catalog, extracted text, chunks.jsonl
└── index_db/              ChromaDB RAG (Ollama embeddings)
```

Full hierarchy: copy of live `agentic/hermes/.kb/README.md` maintained when
vault is populated. Run `kb-scan` after adding files.

See also:

- [kb/README.md](README.md) — scaffold & bootstrap
- [working_agreements_kb.md](../working_agreements_kb.md) — ingestion
- [working_agreements_generated.md](../working_agreements_generated.md) — outputs
