# Problem statement

NASA has decades of microgravity-combustion results, but their volume and heterogeneous formats make the evidence difficult to find, compare, and interpret. Combustion Atlas must provide an interactive SI/AI-powered dashboard that summarizes, ranks, and interprets those findings for human-spaceflight fire safety.

The core technical bottleneck is evidence normalization. BASS-II, FLEX, Saffire, and other investigation families use different columns, units, outcome definitions, scales, and documentation conventions. Before retrieval or prediction can be trustworthy, the system must make experiments comparable without erasing their original context.

The project therefore combines two evidence paths:

1. An auditable ingestion harness maps run-level experimental tables into a common schema, preserves raw values and provenance, applies deterministic conversions and validation, and routes ambiguity to human review.
2. A page-preserving document pipeline supports lexical and semantic retrieval of methods, caveats, mechanisms, and conclusions with citations.

Structured numerical filtering and contextual document retrieval remain separate until the product presents their results together. Prediction is a stretch goal and is only justified for a well-defined outcome with enough scientifically comparable reviewed observations.

The first bounded target is BASS-II / PSI-25. Runs B1-B5 form the first candidate batch and, after scientific review, the first gold fixtures.
