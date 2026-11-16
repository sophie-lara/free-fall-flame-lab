# Space Apps 2026 submission text (draft)

Paste-ready text for the submission form. Check the form for character limits.

## Project name

Combustion Atlas (team Freefall Flame Lab)

## High-level project summary

Combustion Atlas is a public web dashboard that makes decades of NASA microgravity-combustion
experiments searchable and comparable. It combines BASS, BASS-II, Saffire and FLEX experiment
tables with 29 NASA reports. Researchers can ask questions and get answers that quote NASA pages
verbatim, look up exact test conditions in reviewed tables, and see on coverage heatmaps which
oxygen and pressure conditions were tested, only planned, or never tested. Every value links back
to its source, and uncertain values are flagged, never guessed. That gives fire-safety
researchers and spacecraft designers a trustworthy starting point for planning the next
experiment.

## Link to project demo

Use the 7-slide deck `combustion_atlas_slides_final.pptx`, uploaded to a public link with no sign-in.

## Link to final project

- Live site: https://combustion-atlas.azurewebsites.net
- Code: https://github.com/sophie-lara/free-fall-flame-lab

## Detailed project description

**What it does.** Combustion Atlas has four public pages:

- **Ask:** a chat over 29 indexed NASA reports and PSI tables. Every claim cites a numbered NASA source
  and the quotes and numbers are checked against the source. With AI off it is a free keyword search, and typing two or more exact
  values returns the matching reviewed table rows with their notes and a link to the source page.
- **Experiment coverage:** heatmaps of runs by test condition (for FLEX, ambient oxygen against
  pressure). They separate performed runs, tests that were only planned in NASA's FLEX test
  matrices, and conditions that were never tested, and list the possible experimental gaps.
- **Evidence landscape:** a 2-D and 3-D topic map of every passage, figure and table, with topics
  found automatically.
- **Sources:** every indexed document, with links to the original NASA files.

**How it works.** The data takes two paths:

- **Structured tables.** Each PSI table's columns are mapped to one run schema. The raw cells,
  units and provenance are kept. An AI model proposes the mappings and transcribes PDF tables,
  deterministic checks verify every number against the source, and a person reviews flagged
  values using recorded rules.
- **Reports.** These are split into page-bounded passages and indexed for keyword and embedding
  search.

Ambiguous values keep a visible note instead of a guessed number. Planned tests are never counted
as results.

**Benefits.** Researchers can check what has already been tested before proposing new
microgravity experiments. They can find exact values with their sources and see under-tested
regions, such as high-oxygen, high-pressure droplet combustion. Elevated-oxygen conditions matter
because spacecraft exploration atmospheres use more oxygen at lower pressure than the ISS.

**Tools.**

- **Back end:** Python 3.12 with FastAPI, Uvicorn and Pydantic; pypdf and pdfplumber; NumPy and
  scikit-learn (t-SNE, HDBSCAN).
- **Storage:** SQLite (FTS5), with vectors held in memory and cached, gzipped responses.
- **Front end:** React + TypeScript, built with Vite (SVG and canvas charts).
- **Models:** OpenAI gpt-6-luna and text-embedding-3-small, with an optional Azure OpenAI backup.
- **Hosting:** Azure App Service, defined in Terraform.
- **Build:** GitHub Actions running ruff, mypy, pytest and Vitest on Linux and Windows.

## NASA data

- NASA Physical Sciences Informatics (PSI) repository: BASS (PSI-26), BASS-II (PSI-25),
  FLEX (PSI-69, including the test matrices in the FLEX requirements document, EIRD), and
  Saffire I–III (PSI-98, PSI-99, PSI-100). https://psi.nasa.gov
- NASA Technical Reports Server (NTRS): technical reports on these investigations, including
  the BASS-II Summary Report (NASA/TM-20210011385). https://ntrs.nasa.gov
- NASA images: ISS photograph iss071e439624 (orbital sunrise, site background); NASA Glenn
  Research Center photo GRC-1998-C-00485 (candle flames in normal gravity and microgravity);
  ISS photograph ISS040-E-021546 (BASS-II experiment aboard the ISS).

## Space agency partner data and other references

No partner-agency data. Software and services:

- **Back-end libraries:** openai-python (Apache-2.0), FastAPI (MIT), Uvicorn (BSD-3-Clause),
  Pydantic (MIT), pypdf (BSD-3-Clause), pdfplumber (MIT), python-dotenv (BSD-3-Clause),
  NumPy (BSD-3-Clause) and scikit-learn (BSD-3-Clause).
- **Front-end libraries:** React and React Router (MIT), Vite and Vitest (MIT), TypeScript
  (Apache-2.0).
- **Developer tools:** pytest, ruff and mypy (all MIT).
- **Services:** OpenAI API and Microsoft Azure.

The project is MIT-licensed. The full list is in the README.

## Use of SI (Super Intelligence)

**In the product,** OpenAI models do the following:

- write answers that must quote NASA text (the quotes are checked);
- embed passages for search;
- describe report figures (labelled as AI-generated on the site);
- name topics;
- transcribe and map PDF tables. Every number is checked against the source and flagged values
  are reviewed by a person;
- suggest extra search queries for broad questions.

An Azure OpenAI model is a backup for answers if OpenAI is unavailable, with the same checks.

**In development,** AI coding assistants helped write code, tests and documentation. The team chose
the problem and the approach and made all scientific review decisions.

No AI image, video or audio generators were used. Photos are NASA's; the flame logo and the
illustrated flames are vector graphics drawn in code, written with the help of an AI coding
assistant.
