# Combustion Atlas — Updated Hackathon Plan

## 1. Core Project Goal

Build a trustworthy evidence system for NASA's microgravity combustion archive.

The central technical problem is not simply search. It is that PSI experiments are heterogeneous:

- different investigation families use different schemas;
- variable names and units vary;
- some values are true experimental inputs;
- some are post-burn measurements;
- some columns are instrumentation metadata;
- some apparent fields are mislabeled or lose formatting during export;
- some records are incomplete, ambiguous, or not scientifically comparable.

The project therefore has two major layers:

1. **Agentic normalization** — map heterogeneous NASA source material into a common schema, preserve raw values/provenance, use deterministic validation, and quarantine ambiguous mappings.
2. **Evidence retrieval** — structured search over normalized experiments plus semantic retrieval/RAG over reports and papers.

Prediction is optional and should only be attempted where the normalized data genuinely support it.

---

## 2. Evidence Policy

> **NASA source material is the source of truth.**

Public GitHub projects are useful for finding difficult cases, relevant investigations, architecture patterns, and common failure modes. They are not authoritative scientific sources.

For every important mapping or scientific conclusion:

1. inspect the repo implementation/data rather than relying on its README;
2. trace the claim to NASA PSI/NTRS or the underlying source file;
3. decide independently whether the interpretation makes sense;
4. record whether the finding is:
   - verified in code/data,
   - verified against NASA,
   - or self-reported only.

---

## 3. Verified Lessons from Existing Projects

### Fotia — most useful reference for normalization

Verified from code:

- one loader per investigation;
- explicit source-specific cleaning;
- deliberate handling of ambiguous fields;
- strong separation between pre-ignition predictors and post-burn measurements;
- refusal to infer unsupported outcomes;
- heterogeneous investigation families require materially different parsing logic.

Useful failure cases to reproduce in our tests:

- messy material strings;
- dimensions embedded inside material descriptions;
- flow-related strings that mix settings and experimental events;
- fields whose names lose scientific formatting during export;
- failed/disrupted runs that should not be treated as physical outcome classes;
- post-burn measurements that should not become predictors.

### MicroFire Atlas — useful evidence/product concepts

Useful ideas:

- distinguish direct, analogous, mechanistic, and gap evidence;
- citation-backed retrieval;
- explicit abstention outside evidence support;
- scenario comparison;
- evidence-gap visualization.

Do not treat self-reported evaluation metrics as independently established unless reproduced.

### FIRE-X — useful structured-query architecture

Useful ideas:

- canonical database;
- SQL-style experiment filtering;
- scenario comparison;
- large normalized table.

Important caution: some values in its pipeline are hard-coded, imputed, or modeled. Our rule is:

> **Null is better than invented completeness.**

### FLARE-X / ALPINE_IBEX — validation lesson

README/model claims can disagree with serialized metrics. Any predictive model we build must be evaluated from reproducible artifacts and against appropriate baselines.

### Competitive implication

These features are already common:

- experiment browser;
- scenario sliders;
- RAG/chat;
- comparison;
- citations;
- evidence gaps;
- small predictive models;
- next-experiment suggestions.

Our strongest novelty should therefore be:

> **A scalable, provenance-preserving agentic ingestion system that can add a new PSI investigation with much less manual cleaning while keeping uncertain mappings visible and auditable.**

---

## 4. Canonical Data Model

One normalized record represents **one individual test/run**, not an entire investigation.

```text
Investigation
    ↓
Individual test/run
    ↓
Conditions
    ↓
One or more outcomes
```

Example:

```text
BASS-II
    ↓
Test B17
    ↓
Conditions
- PMMA
- 30% O2
- airflow
- pressure
- geometry
- gravity
    ↓
Outcomes
- flame spread
- flame length
- extinction
- gas measurements
```

### Proposed structure

```text
ExperimentRecord
├── identity
├── conditions
├── outcomes[]
├── instrument_settings / extra_metadata
├── provenance
├── extraction_confidence
└── validation_status
```

### Identity

```text
investigation_id
test_id
sample_id
optional descriptive name
```

### Conditions

Possible canonical fields:

```text
material
fuel_type
geometry
dimensions
gravity_regime
gravity_g
oxygen_pct
pressure_kpa
airflow_cm_s
temperature
ignition_method
suppressant
```

Only populate fields supported by source evidence.

### Outcomes

Use a flexible list:

```text
OutcomeMeasurement
├── outcome_type
├── value
├── unit
├── original_value
├── original_unit
├── qualifier
├── uncertainty
└── provenance
```

This allows one test to produce many measurements without duplicating the test record.

---

## 5. Scientific Classification Rules

The normalization system must distinguish:

### Experimental inputs / conditions
Examples:
- initial O2;
- airflow;
- pressure;
- fuel/material;
- geometry.

### Instrument/control settings
Examples:
- fan display;
- radiometer gain;
- camera settings;
- flow restrictor settings.

Do not automatically convert these into physical variables unless NASA documentation establishes the calibration.

### Post-burn / measured outputs
Examples:
- final O2;
- final CO2;
- final CO;
- flame spread;
- flame length;
- extinction;
- temperature measurements.

### Context-only / mechanistic evidence
Examples:
- discussion text;
- explanations;
- theoretical mechanisms;
- limitations.

This separation is essential before any predictive modeling.

---

## 6. Normalization Pipeline

```text
NASA source
    ↓
raw capture
    ↓
parser
    ↓
agent proposes mappings
    ↓
deterministic unit conversion
    ↓
deterministic validation
    ↓
provenance attachment
    ↓
ACCEPT / REVIEW_REQUIRED / REJECT
```

### Raw capture

Always preserve:

- original column names;
- original strings;
- original units;
- missing values;
- NASA source URL;
- file/page/table/test identifier.

### Agent responsibilities

The agent may:

- identify candidate fields;
- map synonyms to canonical concepts;
- classify outcomes;
- extract raw values and units;
- propose confidence scores;
- identify ambiguous fields.

The agent should **not**:

- invent missing values;
- silently infer unsupported physical meaning;
- silently convert units;
- treat unusual values as errors merely because they look odd.

### Deterministic code responsibilities

Use normal code for:

- unit conversion;
- allowed-range checks;
- required-field checks;
- known-unit validation;
- source/provenance requirements;
- anomaly flags.

---

## 7. Validation Philosophy

Statuses:

```text
pending
validated
review_required
rejected
```

### Valid but unusual

If a row says:

```text
Initial O2 = 22.2
Final O2 = 1.6
```

do not overwrite or reject it. Preserve the value and flag `review_required`.

### Missing field

Use `null`. Do not infer from neighboring rows.

### Ambiguous field

If the source says:

```text
Fan display = 62
```

keep the raw setting. Do not convert it to airflow unless NASA documentation supports that mapping.

---

## 8. Gold-Standard Review Workflow

The human role is **validation**, not transcription.

```text
NASA source
    ↓
automated extraction
    ↓
candidate normalized record
    ↓
manual confirmation/correction
    ↓
gold fixture
```

Start with:

- BASS-II B1-B5;
- then one or two FLEX records;
- then one or two Saffire records.

Gold fixtures should capture:

- correct field mapping;
- raw value;
- normalized value;
- unit;
- provenance;
- ambiguity;
- expected validation status.

They become few-shot examples, unit tests, regression tests, and evaluation data.

---

## 9. First Real Data Task: BASS-II / PSI-25

Start with the BASS-II experimental table.

Known columns include:

```text
PI
Test #
Date
GMT
Sample #
Fuel Sample Material
Flow restrictor
Fan display
Air display
Radiometer gain
Total Frames Shot
Calibrated initial O2 % by vol
Calibrated final O2 % by vol
Initial CO2 % by vol
Final CO2 % by vol
Initial CO (ppm)
Final CO (ppm)
```

### Initial safe mappings

Identity:

```text
Test # -> test_id
Sample # -> sample_id
Investigation -> PSI-25
```

Material string example:

```text
100 micron PMMA film 2 cm wide
```

Candidate parsing:

```text
material = PMMA
geometry = film
thickness_um = 100
width_cm = 2
```

Preserve the original string.

### Fields to preserve but not physically interpret yet

```text
Flow restrictor
Fan display
Air display
Radiometer gain
```

Keep these under `instrument_settings / extra_metadata` until NASA documentation proves their physical mapping.

---

## 10. Repo Structure

```text
combustion-atlas/
|
|-- README.md
|-- pyproject.toml
|-- .gitignore
|-- .env.example
|
|-- docs/
|   |-- architecture.md
|   |-- schema_notes.md
|   |-- normalization_research.md
|   `-- investigation_notes.md
|
|-- src/
|   |
|   |-- ingestion/
|   |   |-- psi_client.py
|   |   |-- document_parser.py
|   |   `-- table_parser.py
|   |
|   |-- normalization/
|   |   |-- schema.py
|   |   |-- extractor.py
|   |   |-- field_mapper.py
|   |   |-- units.py
|   |   `-- validate.py
|   |
|   |-- rag/
|   |   |-- chunk.py
|   |   |-- embed.py
|   |   `-- retrieve.py
|   |
|   |-- retrieval/
|   |   |-- structured.py
|   |   |-- similarity.py
|   |   `-- hybrid.py
|   |
|   `-- app/
|
|-- tests/
|   |-- fixtures/
|   |   |-- raw/
|   |   `-- gold/
|   |-- test_normalization.py
|   `-- test_units.py
|
`-- data/
    |-- raw/
    |-- review/
    |-- processed/
    `-- embeddings/
```

---

## 11. Pre-Event Work Plan

### Phase A — Source research (~2-3 h)

- inspect representative BASS-II, FLEX, and Saffire files;
- identify important fields and outcome differences;
- record ambiguous terminology;
- find NASA documentation for confusing variables;
- use public repos only as leads/failure-case references.

### Phase B — Gold examples (~1-2 h)

- automatically extract B1-B5;
- manually confirm/correct;
- create gold fixtures.

### Phase C — Normalization harness (~3-4 h)

- parser;
- LLM schema mapper;
- deterministic units;
- validator;
- review queue.

### Phase D — Toy RAG pipeline (~2-3 h)

- generic parse -> chunk -> embed -> retrieve -> cited answer;
- test on unrelated/toy documents.

### Phase E — Deployment readiness (~1-2 h)

- working local environment;
- GitHub access;
- API keys;
- toy deployment;
- branch workflow.

---

## 12. Saturday Build Order

1. Run PSI-25/BASS-II through the real normalization harness.
2. Manually inspect ~20 records.
3. Fix aliases, schema mappings, unit rules, prompt behavior, and validation.
4. Scale to the full BASS-II table.
5. Add FLEX — without assuming FLEX variables/outcomes are directly comparable to BASS-II.
6. Add Saffire if time permits.
7. Build structured experiment search.
8. Chunk/embed relevant textual sources.
9. Implement hybrid retrieval.
10. Build scenario explorer.
11. Add evidence coverage / evidence type.
12. Only then consider prediction.

---

## 13. RAG Architecture

Documents:

- reports;
- papers;
- methods;
- conclusions;
- discussions.

Initial chunking target:

- 500-1,000 tokens;
- section-aware where possible;
- modest overlap.

Every chunk should carry:

- investigation;
- document;
- page;
- section;
- source URL / DOI;
- test IDs when known.

Hybrid retrieval:

```text
user query
    ↓
structured constraint extraction
    ↓
structured experiment search
        +
semantic vector search
    ↓
evidence bundle
    ↓
LLM synthesis
    ↓
answer + citations
```

---

## 14. Evidence Classes

Later retrieval should distinguish:

```text
DIRECT
ANALOGOUS
MECHANISTIC
GAP
```

- **Direct:** same or closely matching conditions and outcome.
- **Analogous:** related experiment with meaningful but imperfect similarity.
- **Mechanistic:** useful scientific explanation, but not directly comparable test evidence.
- **Gap:** no adequate evidence.

---

## 15. Scenario Explorer

Inputs:

```text
Material
O2
Airflow
Pressure
Gravity
Geometry
```

Outputs:

1. nearest real experiments;
2. exact conditions;
3. observed outcomes;
4. largest mismatches;
5. evidence class;
6. relevant report text;
7. citations;
8. coverage / gaps.

Prediction is not required.

---

## 16. Novelty Demo

Make ingestion visible.

Example:

```text
New PSI investigation loaded

Fields discovered:          21
Automatically mapped:       15
Validated mappings:         13
Uncertain mappings:          4
Review required:             2
Tests extracted:           129
Provenance retained:       100%
```

Show examples:

```text
"XO2" -> oxygen_pct
confidence: 0.97
validated
```

and:

```text
"Burn Const" -> ?
confidence: 0.61
REVIEW REQUIRED
```

This demonstrates the core contribution better than hiding ETL behind the dashboard.

---

## 17. Predictive Modeling Rules

Prediction is a stretch goal.

Only attempt it if:

- enough comparable observations exist;
- outcome semantics are consistent;
- predictors are truly pre-outcome variables;
- missing values are not filled with arbitrary constants;
- evaluation beats appropriate baselines;
- the model can identify out-of-domain scenarios.

Do not use:

- post-burn measurements as predictors;
- modeled/imputed values as if they were observations;
- incompatible outcomes across investigation families.

Possible separate models:

```text
conditions -> flame spread rate
conditions -> ignition time
conditions -> extinction
```

Do not build a generic "fire risk" model unless scientifically justified.

---

## 18. Evaluation

### Normalization

Manually review ~20-30 records.

Measure:

```text
correct mapped fields / total reviewed fields
```

Track:

- unit correctness;
- provenance correctness;
- null behavior;
- false inference rate.

### Retrieval

Create ~10 known-answer questions.

Measure whether the correct source is in top 3 / top 5.

### RAG

Verify:

- numerical claims;
- citations;
- absence of unsupported conclusions.

### Scenario search

Construct scenarios near known experiments and verify the correct experiments rank highly.

---

## 19. Two-Person Split

### Sophie

- NASA source interpretation;
- gold record review;
- schema decisions;
- scientific validation;
- evidence classes;
- competitor research;
- retrieval evaluation;
- demo/presentation logic.

### David

- ingestion tools;
- parsing;
- normalization agent;
- validators;
- vector retrieval;
- backend/frontend;
- deployment.

### Shared

- schema revisions;
- QA;
- scenario similarity;
- architecture;
- pitch.

---

## 20. Priority Order

If time is limited:

1. schema;
2. gold fixtures;
3. normalization agent;
4. validation/provenance;
5. real standardized dataset;
6. structured search;
7. RAG + citations;
8. scenario explorer;
9. evidence coverage/classes;
10. next-experiment recommendation;
11. predictive model.

Do not sacrifice 1-9 for prediction.

---

## 21. Immediate Next Task

> **Run PSI-25 B1-B5 through the extraction harness and produce candidate normalized records plus a mapping report for manual review.**

Human review should focus on:

- scientific field meaning;
- condition vs outcome classification;
- suspicious values;
- unresolved instrument settings;
- source provenance.

Once B1-B5 are accepted, they become the first gold fixtures and the agent can scale to more BASS-II records.

---

## 22. Core Project Story

> NASA has decades of combustion experiments, but the evidence is difficult to compare because every investigation has its own structure, terminology, and measurement conventions. Combustion Atlas uses an auditable agentic ingestion system to normalize new PSI experiments into a common evidence schema, preserves source provenance and uncertainty, and combines structured retrieval with semantic RAG so researchers can search, compare, and reason across the archive without losing the scientific context.

The strongest contribution is not "AI chat."

It is:

> **making heterogeneous scientific evidence continuously ingestible, comparable, traceable, and safe to reason over.**
