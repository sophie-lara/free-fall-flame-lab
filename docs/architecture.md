# Architecture

Combustion Atlas keeps two independent evidence paths:

1. structured, run-level experiment records for exact filtering; and
2. page-preserving NASA documents for keyword or semantic retrieval.

The ingestion pipeline is deliberately lossless: raw source cells are retained before aliases, conversions, or validation are applied. Ambiguous mappings are visible to reviewers rather than silently inferred.

The package boundaries are `ingestion`, `normalization`, `review`, `retrieval`, `rag`, `providers`, `evaluation`, and `app`. Commands and artifact locations are documented in [operations.md](operations.md).
