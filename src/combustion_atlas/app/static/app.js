"use strict";

const escapeText = (value) => String(value ?? "");

async function loadExperiments() {
  const response = await fetch("/api/experiments");
  const payload = await response.json();
  const target = document.querySelector("#experiments");
  document.querySelector("#experiment-status").textContent = payload.records.length
    ? `${payload.records.length} candidate records. Scientific acceptance is a separate review decision.`
    : "No candidate batch exists yet.";
  target.replaceChildren(...payload.records.map((record) => {
    const card = document.createElement("article");
    card.className = "card";
    const title = document.createElement("h3");
    title.textContent = `${escapeText(record.investigation_id)} / ${escapeText(record.test_id)}`;
    const body = document.createElement("p");
    body.textContent = `${escapeText(record.conditions.material || "Unknown material")} · ${escapeText(record.validation_status)}`;
    card.append(title, body);
    return card;
  }));
}

document.querySelector("#search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = document.querySelector("#question").value;
  const response = await fetch(`/api/search?q=${encodeURIComponent(question)}`);
  const payload = await response.json();
  document.querySelector("#search-status").textContent = payload.notice || `${payload.results.length} cited chunks found.`;
  document.querySelector("#results").replaceChildren(...payload.results.map((result) => {
    const card = document.createElement("article");
    card.className = "card";
    const title = document.createElement("h3");
    title.textContent = `${escapeText(result.filename)} · page ${escapeText(result.physical_page)}`;
    const body = document.createElement("p");
    body.textContent = escapeText(result.text);
    const citation = document.createElement("code");
    citation.textContent = escapeText(result.chunk_id);
    card.append(title, body, citation);
    return card;
  }));
});

loadExperiments().catch((error) => {
  document.querySelector("#experiment-status").textContent = `Could not load candidates: ${error.message}`;
});
