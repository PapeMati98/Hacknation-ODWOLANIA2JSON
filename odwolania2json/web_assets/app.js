"use strict";

(() => {
  const NEW_CLASS_TEMPLATE = `name: decyzja
description: Decyzja administracyjna wydana wobec strony.
pages: 2
classify:
  title: ["decyzja"]
  keywords:
    "decyzja": 3
    "orzekam": 3
    "pouczenie": 2
  negative:
    "wnoszę odwołanie": 4
  min_score: 4
output:
  Decyzja:
    numer:
      type: string
      validator: text
      verify_in_text: true
      desc: "Znak lub numer decyzji."
    data:
      type: string
      validator: date
      desc: "Data wydania decyzji."
`;

  const state = {
    activeTab: "cases",
    status: null,
    cases: [],
    selectedCaseName: null,
    selectedCase: null,
    selectedDocIdx: 0,
    activeSubtab: "trace",
    traceFilter: "all",
    stagedFiles: [],
    submitting: false,
    activeJob: null,
    pollTimer: null,
    lastRunAction: null,
    classes: [],
    selectedClassFilename: null,
    yamlSaving: false,
    yamlInvalid: false,
    conflictFilename: null,
    lastGlobalRetry: null,
    currentJsonText: "",
  };

  const el = (id) => document.getElementById(id);

  function pl(n, one, few, many) {
    const abs = Math.abs(Number(n) || 0);
    const mod10 = abs % 10;
    const mod100 = abs % 100;
    if (abs === 1) return `${abs} ${one}`;
    if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return `${abs} ${few}`;
    return `${abs} ${many}`;
  }

  function fmtBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
  }

  function pillClassForStatus(status) {
    if (status === "ok" || status === "naprawiono" || status === "dopasowano") return "pill pill-ok";
    if (status === "ostrzezenie") return "pill pill-warn";
    if (status === "nieczytelne" || status === "niezweryfikowane") return "pill pill-err";
    return "pill";
  }

  function fmtDuration(sec) {
    const s = Math.max(0, Math.round(Number(sec) || 0));
    if (s < 60) return `${s} s`;
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return rem ? `${m} min ${rem} s` : `${m} min`;
  }

  function fmtConfidence(p) {
    if (!p) return "";
    if (typeof p === "string") return p;
    if (typeof p === "object") {
      const parts = [];
      if (p.poziom) parts.push(String(p.poziom));
      const detail = [];
      if (typeof p.pewnosc_linii === "number") {
        detail.push(p.pewnosc_linii.toFixed(2).replace(".", ","));
      }
      if (p.inny_odczyt) detail.push(String(p.inny_odczyt));
      if (p.czytelnik_wizualny) detail.push(`wizualny: ${p.czytelnik_wizualny}`);
      if (detail.length) parts.push(`(${detail.join(" · ")})`);
      return parts.join(" ");
    }
    return String(p);
  }

  function appendFieldPath(container, path) {
    const text = String(path || "");
    const parts = text.split(/([.\]_])/);
    for (const part of parts) {
      if (!part) continue;
      container.append(document.createTextNode(part));
      if (part === "." || part === "]" || part === "_") {
        container.append(document.createElement("wbr"));
      }
    }
  }

  function countJsonLeaves(obj) {
    let total = 0;
    let filled = 0;
    function walk(node) {
      if (node === null || node === undefined) {
        total += 1;
        return;
      }
      if (Array.isArray(node)) {
        if (node.length === 0) {
          total += 1;
          return;
        }
        for (const item of node) walk(item);
        return;
      }
      if (typeof node === "object") {
        const keys = Object.keys(node);
        for (const k of keys) walk(node[k]);
        return;
      }
      total += 1;
      if (node !== "") filled += 1;
    }
    walk(obj);
    return { total, filled };
  }

  function renderJsonHighlighted(preEl, data) {
    const pretty = JSON.stringify(data, null, 2);
    state.currentJsonText = pretty;
    preEl.replaceChildren();
    const frag = document.createDocumentFragment();
    const tokenRe = /("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|[{}\[\],:])/g;
    let lastIdx = 0;
    let match;
    while ((match = tokenRe.exec(pretty)) !== null) {
      if (match.index > lastIdx) {
        frag.append(document.createTextNode(pretty.slice(lastIdx, match.index)));
      }
      const raw = match[0];
      const span = document.createElement("span");
      if (raw.startsWith('"')) {
        if (match[2]) {
          const colonIdx = raw.lastIndexOf(":");
          span.className = "jk";
          span.textContent = raw.slice(0, colonIdx);
          frag.append(span);
          const punct = document.createElement("span");
          punct.className = "jp";
          punct.textContent = raw.slice(colonIdx);
          frag.append(punct);
          lastIdx = tokenRe.lastIndex;
          continue;
        }
        span.className = "js";
      } else if (raw === "null") {
        span.className = "jnull";
      } else if (raw === "true" || raw === "false") {
        span.className = "jb";
      } else if (/^[{}\[\],:]$/.test(raw)) {
        span.className = "jp";
      } else {
        span.className = "jn";
      }
      span.textContent = raw;
      frag.append(span);
      lastIdx = tokenRe.lastIndex;
    }
    if (lastIdx < pretty.length) {
      frag.append(document.createTextNode(pretty.slice(lastIdx)));
    }
    preEl.append(frag);
  }

  function statusBucket(status) {
    if (status === "ostrzezenie") return "warn";
    if (status === "nieczytelne" || status === "niezweryfikowane") return "rejected";
    if (status === "ok" || status === "naprawiono" || status === "dopasowano") return "ok";
    return "other";
  }

  async function apiFetch(url, opts = {}) {
    const res = await fetch(url, opts);
    const text = await res.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { error: text || `Błąd HTTP ${res.status}` };
    }
    if (!res.ok) {
      const err = new Error(data.error || `Błąd serwera (${res.status}).`);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function showGlobalError(msg, retryFn = null) {
    el("global-error-text").textContent = msg;
    state.lastGlobalRetry = retryFn;
    el("btn-global-retry").hidden = !retryFn;
    el("global-error-shell").hidden = false;
  }

  function hideGlobalError() {
    el("global-error-shell").hidden = true;
    state.lastGlobalRetry = null;
  }

  // ------------------------------------------------------------------ zakładki główne i ARIA
  function wireTablist(tabs, onSelect) {
    tabs.forEach((tab, idx) => {
      tab.addEventListener("click", () => onSelect(idx));
      tab.addEventListener("keydown", (e) => {
        if (e.key === "ArrowRight") {
          e.preventDefault();
          const next = (idx + 1) % tabs.length;
          onSelect(next);
          tabs[next].focus();
        } else if (e.key === "ArrowLeft") {
          e.preventDefault();
          const prev = (idx - 1 + tabs.length) % tabs.length;
          onSelect(prev);
          tabs[prev].focus();
        }
      });
    });
  }

  function setTopTab(idx) {
    const tabs = [el("tab-cases"), el("tab-classes")];
    const panels = [el("panel-cases"), el("panel-classes")];
    state.activeTab = idx === 0 ? "cases" : "classes";
    tabs.forEach((t, i) => t.setAttribute("aria-selected", i === idx ? "true" : "false"));
    panels.forEach((p, i) => { p.hidden = i !== idx; });
  }

  function setSubtab(idx) {
    const keys = ["trace", "review", "classify"];
    const tabs = [el("subtab-trace"), el("subtab-review"), el("subtab-classify")];
    const panels = [el("panel-trace"), el("panel-review"), el("panel-classify")];
    state.activeSubtab = keys[idx];
    tabs.forEach((t, i) => t.setAttribute("aria-selected", i === idx ? "true" : "false"));
    panels.forEach((p, i) => { p.hidden = i !== idx; });
  }

  // ------------------------------------------------------------------ upload i start zadania
  function showUploadError(msg) {
    el("upload-error-text").textContent = msg;
    el("upload-error").hidden = false;
  }

  function clearUploadError() {
    el("upload-error").hidden = true;
  }

  function isJobActive() {
    return Boolean(state.activeJob && (state.activeJob.status === "queued" || state.activeJob.status === "running"));
  }

  function syncStartButton() {
    const btn = el("btn-start-extract");
    const clearBtn = el("btn-clear-files");
    const active = isJobActive();
    clearBtn.disabled = state.stagedFiles.length === 0 || state.submitting || active;
    if (state.submitting) {
      btn.disabled = true;
      btn.setAttribute("aria-busy", "true");
      btn.textContent = "Wysyłanie…";
      return;
    }
    if (active) {
      btn.disabled = true;
      btn.setAttribute("aria-busy", "true");
      const done = state.activeJob.processed_files || 0;
      const total = state.activeJob.total_files || 1;
      btn.textContent = `Przetwarzanie ${Math.min(done + 1, total)}/${total}…`;
      return;
    }
    btn.removeAttribute("aria-busy");
    btn.disabled = state.stagedFiles.length === 0;
    btn.textContent = state.stagedFiles.length
      ? `Uruchom ekstrakcję (${state.stagedFiles.length} PDF)`
      : "Uruchom ekstrakcję";
  }

  function renderFileChips() {
    const box = el("file-chips");
    box.replaceChildren();
    state.stagedFiles.forEach((file, idx) => {
      const chip = document.createElement("div");
      chip.className = "file-chip";
      const left = document.createElement("span");
      left.textContent = file.name;
      const right = document.createElement("span");
      right.style.display = "inline-flex";
      right.style.alignItems = "center";
      right.style.gap = "6px";
      const size = document.createElement("span");
      size.textContent = fmtBytes(file.size);
      const rm = document.createElement("button");
      rm.type = "button";
      rm.className = "file-chip-remove";
      rm.setAttribute("aria-label", `Usuń plik ${file.name}`);
      rm.textContent = "×";
      rm.addEventListener("click", () => {
        state.stagedFiles.splice(idx, 1);
        renderFileChips();
        syncStartButton();
      });
      right.append(size, rm);
      chip.append(left, right);
      box.append(chip);
    });
    syncStartButton();
  }

  function addFiles(fileList) {
    clearUploadError();
    const rejected = [];
    for (const file of Array.from(fileList || [])) {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        rejected.push(file.name);
        continue;
      }
      if (!state.stagedFiles.some((f) => f.name === file.name && f.size === file.size)) {
        state.stagedFiles.push(file);
      }
    }
    if (rejected.length) {
      showUploadError(`Pominięto pliki niebędące PDF: ${rejected.join(", ")}.`);
    }
    renderFileChips();
  }

  function renderJobBanner() {
    const shell = el("job-shell");
    const box = el("job-banner");
    const job = state.activeJob;
    if (!job) {
      shell.hidden = true;
      syncStartButton();
      return;
    }
    shell.hidden = false;
    box.className = "progress-bar-box"
      + (job.status === "error" ? " is-error" : "")
      + (job.status === "done" ? " is-done" : "");

    el("job-case").textContent = job.case_name;
    const total = Math.max(1, job.total_files || 1);
    const done = job.processed_files || 0;
    const pct = job.status === "done" ? 1 : Math.min(0.95, done / total);
    el("job-fill").style.transform = `scaleX(${pct})`;
    const active = job.status === "queued" || job.status === "running";
    const etaPart = active && typeof job.eta_s === "number" && job.eta_s > 0
      ? ` · pozostało ok. ${fmtDuration(job.eta_s)}`
      : "";
    el("job-elapsed").textContent = `${fmtDuration(job.elapsed_s || 0)}${etaPart}`;

    el("btn-job-cancel").hidden = !active;
    el("btn-job-cancel").disabled = Boolean(job.cancel_requested);
    el("btn-job-retry").hidden = !(job.status === "error" && state.lastRunAction);
    el("btn-job-close").hidden = active;

    if (job.status === "queued") {
      el("job-title").textContent = "Zadanie w kolejce:";
      el("job-stage").textContent = "oczekiwanie na uruchomienie";
    } else if (job.status === "running") {
      el("job-title").textContent = "Aktywne zadanie:";
      const filePart = job.current_file ? `${job.current_file} · ` : "";
      el("job-stage").textContent = `etap: ${job.stage} (${filePart}${Math.min(done + 1, total)}/${total})`;
    } else if (job.status === "done") {
      el("job-title").textContent = "Zakończono:";
      el("job-stage").textContent = `przetworzono ${done}/${total} plików · do sprawdzenia: ${job.review_count}`;
    } else if (job.status === "cancelled") {
      el("job-title").textContent = "Anulowano:";
      el("job-stage").textContent = job.stage || "zadanie przerwane przez użytkownika";
    } else {
      el("job-title").textContent = "Błąd przetwarzania:";
      el("job-stage").textContent = job.error || "nieznany błąd silnika";
    }
    syncStartButton();
  }

  async function pollJob(jobId) {
    if (state.pollTimer) {
      clearTimeout(state.pollTimer);
      state.pollTimer = null;
    }
    try {
      const job = await apiFetch(`/api/jobs/${encodeURIComponent(jobId)}`);
      state.activeJob = job;
      renderJobBanner();
      if (job.status === "queued" || job.status === "running") {
        state.pollTimer = setTimeout(() => pollJob(jobId), 1000);
        return;
      }
      if (job.status === "done") {
        setTopTab(0);
        await loadCases(job.case_name, { autoPostJob: true });
      }
    } catch (err) {
      showGlobalError(`Nie udało się pobrać statusu zadania: ${err.message}`, () => pollJob(jobId));
    }
  }

  async function submitUpload(e) {
    if (e) e.preventDefault();
    if (state.submitting || isJobActive()) return;
    clearUploadError();
    if (!state.stagedFiles.length) {
      showUploadError("Dodaj co najmniej jeden plik PDF.");
      return;
    }
    const fd = new FormData();
    const caseName = el("case-name").value.trim();
    const checksum = el("checksum-mode").value;
    const visualReader = el("visual-reader-mode").value;
    if (caseName) fd.append("case_name", caseName);
    fd.append("ocr_checksum", checksum);
    fd.append("visual_reader", visualReader);
    for (const file of state.stagedFiles) {
      fd.append("files", file, file.name);
    }

    state.submitting = true;
    state.lastRunAction = () => submitUpload(null);
    syncStartButton();
    try {
      const job = await apiFetch("/api/cases/run", { method: "POST", body: fd });
      state.activeJob = job;
      state.submitting = false;
      renderJobBanner();
      el("env-checksum").textContent = `Tryb: ${checksum}`;
      pollJob(job.job_id);
    } catch (err) {
      state.submitting = false;
      syncStartButton();
      showUploadError(err.message);
    }
  }

  async function runExistingCase(caseName) {
    if (state.submitting || isJobActive()) return;
    hideGlobalError();
    const checksum = el("checksum-mode").value;
    const visualReader = el("visual-reader-mode").value;
    state.submitting = true;
    state.lastRunAction = () => runExistingCase(caseName);
    syncStartButton();
    try {
      const job = await apiFetch("/api/cases/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_name: caseName, ocr_checksum: checksum, visual_reader: visualReader }),
      });
      state.activeJob = job;
      state.submitting = false;
      renderJobBanner();
      el("env-checksum").textContent = `Tryb: ${checksum}`;
      pollJob(job.job_id);
    } catch (err) {
      state.submitting = false;
      syncStartButton();
      showGlobalError(`Nie udało się uruchomić sprawy ${caseName}: ${err.message}`, () => runExistingCase(caseName));
    }
  }

  // ------------------------------------------------------------------ sprawy i inspektor
  function renderCasesList() {
    const list = el("cases-list");
    el("cases-count").textContent = pl(state.cases.length, "sprawa", "sprawy", "spraw");
    list.replaceChildren();
    if (!state.cases.length) {
      const empty = document.createElement("div");
      empty.className = "panel-body case-meta";
      empty.textContent = "Brak spraw w input/ lub output/. Wgraj pliki PDF powyżej.";
      list.append(empty);
      return;
    }
    for (const item of state.cases) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "case-item";
      btn.setAttribute("aria-pressed", item.name === state.selectedCaseName ? "true" : "false");

      const left = document.createElement("div");
      const title = document.createElement("div");
      title.className = "case-name";
      title.textContent = item.name + (item.has_scan ? " (skan)" : "");
      const meta = document.createElement("div");
      meta.className = "case-meta";
      meta.textContent = item.has_output
        ? `${item.json_count} JSON · ${item.skipped_count} spoza klas ({}) · ${pl(item.review_count, "uwaga", "uwagi", "uwag")}`
        : `${item.input_pdf_count} PDF w input/ (do przetworzenia)`;
      left.append(title, meta);

      const badge = document.createElement("span");
      if (!item.has_output) {
        badge.className = "pill";
        badge.textContent = "nowa";
      } else if (item.review_count > 0) {
        badge.className = "pill pill-warn";
        badge.textContent = pl(item.review_count, "uwaga", "uwagi", "uwag");
      } else {
        badge.className = "pill pill-ok";
        badge.textContent = "OK";
      }
      btn.append(left, badge);
      btn.addEventListener("click", () => selectCase(item.name));
      list.append(btn);
    }
  }

  async function loadCases(selectName = null, opts = {}) {
    el("cases-list").setAttribute("aria-busy", "true");
    try {
      const data = await apiFetch("/api/cases");
      state.cases = data.cases || [];
      renderCasesList();
      const target = selectName
        || (state.selectedCaseName && state.cases.some((c) => c.name === state.selectedCaseName)
          ? state.selectedCaseName
          : (state.cases[0] ? state.cases[0].name : null));
      if (target) {
        await selectCase(target, opts);
      } else {
        state.selectedCaseName = null;
        state.selectedCase = null;
        el("case-empty").hidden = false;
        el("case-workspace").hidden = true;
      }
    } catch (err) {
      showGlobalError(`Nie udało się wczytać listy spraw: ${err.message}`, () => loadCases(selectName, opts));
    } finally {
      el("cases-list").setAttribute("aria-busy", "false");
    }
  }

  async function selectCase(caseName, opts = {}) {
    state.selectedCaseName = caseName;
    renderCasesList();
    try {
      const detail = await apiFetch(`/api/cases/${encodeURIComponent(caseName)}`);
      state.selectedCase = detail;
      const docs = detail.documents || [];
      let initialIdx = 0;
      if (opts.autoPostJob && docs.length) {
        const firstClassified = docs.findIndex((d) => !d.skipped);
        initialIdx = firstClassified >= 0 ? firstClassified : 0;
      }
      state.selectedDocIdx = Math.min(initialIdx, Math.max(0, docs.length - 1));
      state.traceFilter = "all";
      renderCaseWorkspace();
    } catch (err) {
      showGlobalError(`Nie udało się otworzyć sprawy ${caseName}: ${err.message}`, () => selectCase(caseName, opts));
    }
  }

  function renderCaseWorkspace() {
    const detail = state.selectedCase;
    if (!detail) {
      el("case-empty").hidden = false;
      el("case-workspace").hidden = true;
      return;
    }
    el("case-empty").hidden = true;
    el("case-workspace").hidden = false;

    const docs = detail.documents || [];
    const classifiedCount = docs.filter((d) => !d.skipped).length;
    const skippedCount = docs.filter((d) => d.skipped).length;
    const anyScan = docs.some((d) => d.skan);
    const reviewItems = (detail.do_sprawdzenia && detail.do_sprawdzenia.pozycje) || [];

    el("ws-case-name").textContent = detail.name;
    el("ws-doc-stats").textContent = `Dokumenty: ${docs.length} (${pl(classifiedCount, "sklasyfikowany", "sklasyfikowane", "sklasyfikowanych")}, ${skippedCount} spoza klas → {})`;
    el("ws-source-stats").textContent = docs.length ? `Źródło: ${anyScan ? "OCR (skan)" : "warstwa tekstowa"}` : "";

    const revBadge = el("ws-review-badge");
    revBadge.className = reviewItems.length > 0 ? "pill pill-warn" : "pill pill-ok";
    revBadge.textContent = `Do sprawdzenia: ${reviewItems.length}`;

    const rerunBtn = el("btn-rerun-case");
    rerunBtn.hidden = !(detail.input_files && detail.input_files.length > 0);
    rerunBtn.disabled = isJobActive() || state.submitting;

    const zipLink = el("btn-download-zip");
    const hasAnyJsonFile = docs.some((d) => d.has_json_file !== false);
    if (hasAnyJsonFile || classifiedCount > 0) {
      zipLink.hidden = false;
      zipLink.href = `/api/cases/${encodeURIComponent(detail.name)}/download.zip`;
      zipLink.setAttribute("download", `${detail.name}.zip`);
    } else {
      zipLink.hidden = true;
    }

    if (!docs.length) {
      el("case-no-output").hidden = false;
      el("case-results-wrap").hidden = true;
      return;
    }
    el("case-no-output").hidden = true;
    el("case-results-wrap").hidden = false;

    // Pasek dokumentów (role="tablist")
    const strip = el("doc-strip");
    strip.replaceChildren();
    const docTabEls = [];
    docs.forEach((doc, idx) => {
      const b = document.createElement("button");
      b.id = `doc-tab-${idx}`;
      b.type = "button";
      b.className = "doc-pill";
      b.setAttribute("role", "tab");
      b.setAttribute("aria-controls", "doc-tabpanel");
      b.setAttribute("aria-selected", idx === state.selectedDocIdx ? "true" : "false");
      const nameSpan = document.createElement("span");
      nameSpan.textContent = doc.pdf_name;
      const tag = document.createElement("span");
      tag.className = doc.skipped ? "doc-tag doc-tag-foreign" : "doc-tag";
      tag.textContent = doc.skipped ? "spoza klas → {}" : (doc.klasa || "json");
      b.append(nameSpan, tag);
      strip.append(b);
      docTabEls.push(b);
    });
    wireTablist(docTabEls, (idx) => {
      state.selectedDocIdx = idx;
      state.traceFilter = "all";
      renderSelectedDocument();
    });

    renderSelectedDocument();
  }

  function renderSelectedDocument() {
    const detail = state.selectedCase;
    const docs = (detail && detail.documents) || [];
    const doc = docs[state.selectedDocIdx];
    if (!doc) return;

    // Aktualizacja aria-selected i aria-labelledby na #doc-tabpanel
    docs.forEach((_, i) => {
      const t = el(`doc-tab-${i}`);
      if (t) t.setAttribute("aria-selected", i === state.selectedDocIdx ? "true" : "false");
    });
    el("doc-tabpanel").setAttribute("aria-labelledby", `doc-tab-${state.selectedDocIdx}`);

    const copyBtn = el("btn-copy-json");
    const dlBtn = el("btn-dl-json");
    const jsonView = el("json-view");
    const statsPill = el("json-field-stats");
    const foreignNote = el("json-foreign-note");

    if (doc.skipped) {
      el("json-pane-title").textContent = `Wynikowy JSON (${doc.json_name || doc.stem + ".json"})`;
      statsPill.hidden = false;
      statsPill.className = "pill";
      statsPill.textContent = "pusty obiekt {}";
      foreignNote.hidden = false;
      foreignNote.textContent = "Dokument nie pasuje do żadnej zdefiniowanej klasy YAML. Zgodnie z kontraktem UZP zapisano pusty obiekt JSON {}. Sprawdź punktację słów kluczowych w zakładce „Klasyfikacja”.";
      const payload = doc.data && typeof doc.data === "object" ? doc.data : {};
      renderJsonHighlighted(jsonView, payload);
      copyBtn.disabled = false;
      dlBtn.disabled = doc.has_json_file === false;
    } else if (!doc.data) {
      el("json-pane-title").textContent = "Brak pliku JSON";
      statsPill.hidden = true;
      foreignNote.hidden = true;
      state.currentJsonText = "";
      copyBtn.disabled = true;
      dlBtn.disabled = true;
      jsonView.textContent = "Brak wygenerowanego pliku JSON dla tego dokumentu.";
    } else {
      el("json-pane-title").textContent = `Wynikowy JSON (${doc.json_name || doc.stem + ".json"})`;
      foreignNote.hidden = true;
      const counts = countJsonLeaves(doc.data);
      statsPill.hidden = false;
      statsPill.className = "pill pill-ok";
      statsPill.textContent = `wypełnione ${counts.filled}/${counts.total} pól`;
      copyBtn.disabled = false;
      dlBtn.disabled = doc.has_json_file === false;
      renderJsonHighlighted(jsonView, doc.data);
    }

    const tLoad = doc.czas_wczytania_s != null ? `wczytanie ${doc.czas_wczytania_s} s` : "";
    const tExt = doc.czas_ekstrakcji_s != null ? `ekstrakcja ${doc.czas_ekstrakcji_s} s` : "";
    el("doc-timing").textContent = [tLoad, tExt].filter(Boolean).join(" · ");

    const trace = doc.trace || [];
    const reviewItems = (detail.do_sprawdzenia && detail.do_sprawdzenia.pozycje) || [];
    el("subtab-trace").textContent = `Ślad ekstrakcji (${trace.length})`;
    el("subtab-review").textContent = `Do sprawdzenia (${reviewItems.length})`;

    renderTracePanel(doc, trace);
    renderReviewPanel(reviewItems);
    renderClassifyPanel(doc);

    // Dla dokumentu pominiętego automatycznie otwieramy Klasyfikację; dla sklasyfikowanego Ślad
    setSubtab(doc.skipped ? 2 : 0);
  }

  function renderTracePanel(doc, trace) {
    const counts = { all: trace.length, warn: 0, rejected: 0, ok: 0 };
    for (const row of trace) {
      const b = statusBucket(row.status);
      if (counts[b] !== undefined) counts[b] += 1;
    }

    const filterBtns = el("trace-filter-strip").querySelectorAll(".filter-btn");
    filterBtns.forEach((b) => {
      const f = b.dataset.filter;
      const labels = { all: "Wszystkie", warn: "Ostrzeżenia", rejected: "Odrzucone", ok: "OK" };
      b.textContent = `${labels[f]} (${counts[f]})`;
      b.setAttribute("aria-pressed", state.traceFilter === f ? "true" : "false");
    });

    const callout = el("doc-review-callout");
    const docAlerts = trace.filter((t) => t.status === "nieczytelne" || t.status === "niezweryfikowane" || t.status === "ostrzezenie");
    if (docAlerts.length > 0) {
      callout.hidden = false;
      callout.replaceChildren();
      const strong = document.createElement("strong");
      strong.textContent = `Wymaga uwagi (${docAlerts.length} ${docAlerts.length === 1 ? "pole" : "pól"} w tym dokumencie): `;
      const summary = document.createElement("span");
      summary.textContent = docAlerts.slice(0, 3).map((a) => `${a.pole} (${a.status})`).join(", ")
        + (docAlerts.length > 3 ? "…" : "");
      callout.append(strong, summary);
    } else {
      callout.hidden = true;
    }

    const tbody = el("trace-tbody");
    tbody.replaceChildren();
    if (doc.skipped) {
      el("trace-filter-strip").hidden = true;
      el("trace-table-wrap").hidden = true;
      el("trace-empty").hidden = false;
      el("trace-empty").textContent = "Dokument spoza zdefiniowanych klas YAML (pusty JSON {}) — brak śladu ekstrakcji pól.";
      return;
    }

    el("trace-filter-strip").hidden = false;
    const filtered = trace.filter((row) => state.traceFilter === "all" || statusBucket(row.status) === state.traceFilter);
    if (!filtered.length) {
      el("trace-table-wrap").hidden = true;
      el("trace-empty").hidden = false;
      el("trace-empty").textContent = "Brak pól spełniających wybrany filtr statusu.";
      return;
    }

    el("trace-table-wrap").hidden = false;
    el("trace-empty").hidden = true;
    for (const row of filtered) {
      const tr = document.createElement("tr");

      const tdField = document.createElement("td");
      tdField.className = "mono trace-field";
      appendFieldPath(tdField, row.pole || "");

      const tdVal = document.createElement("td");
      const valSpan = document.createElement("div");
      const isNull = row.wartosc === null || row.wartosc === undefined;
      valSpan.className = isNull ? "mono val-null" : "mono val-filled";
      valSpan.textContent = isNull ? "null" : String(row.wartosc);
      tdVal.append(valSpan);
      if (row.uwaga) {
        const note = document.createElement("div");
        note.className = "note-line";
        note.textContent = row.uwaga;
        tdVal.append(note);
      }

      const tdSrc = document.createElement("td");
      const parts = [];
      if (row.zrodlo) parts.push(row.zrodlo === "ocr" ? "OCR" : "tekst");
      const confText = fmtConfidence(row.pewnosc);
      if (confText) parts.push(confText);
      tdSrc.textContent = parts.join(" · ") || "—";

      const tdStatus = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = pillClassForStatus(row.status);
      badge.textContent = row.status || "—";
      tdStatus.append(badge);

      tr.append(tdField, tdVal, tdSrc, tdStatus);
      tbody.append(tr);
    }
  }

  function renderReviewPanel(items) {
    const list = el("review-list");
    const empty = el("review-empty");
    list.replaceChildren();
    if (!items.length) {
      list.hidden = true;
      empty.hidden = false;
      return;
    }
    list.hidden = false;
    empty.hidden = true;
    for (const item of items) {
      const card = document.createElement("div");
      card.className = "review-card" + (item.typ === "pole_odrzucone" ? " is-rejected" : "");
      const title = document.createElement("strong");
      if (item.typ === "kontrola_krzyzowa") {
        title.textContent = `Kontrola krzyżowa · ${item.regula || "reguła"}`;
      } else if (item.typ === "pole_odrzucone") {
        title.textContent = `Pole odrzucone · ${item.plik || ""}`;
      } else {
        title.textContent = `Ostrzeżenie · ${item.plik || ""}`;
      }
      const line1 = document.createElement("div");
      if (item.typ === "kontrola_krzyzowa") {
        line1.textContent = `${item.opis || ""} — ${item.szczegoly || ""}`;
      } else {
        line1.className = "mono";
        const proposed = item.proponowana_wartosc != null
          ? `proponowana: ${item.proponowana_wartosc}`
          : (item.wartosc != null ? `wartość: ${item.wartosc}` : "wartość: null");
        line1.textContent = `${item.pole || ""} · ${proposed}`;
      }
      const line2 = document.createElement("div");
      line2.className = "note-line";
      line2.textContent = item.powod || "";
      card.append(title, line1);
      if (line2.textContent) card.append(line2);
      list.append(card);
    }
  }

  function renderClassifyPanel(doc) {
    const tbody = el("classify-tbody");
    tbody.replaceChildren();
    const scores = doc.punkty_klas || {};
    const names = Object.keys(scores);
    if (!names.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 4;
      td.className = "case-meta";
      td.textContent = "Brak zapisanej punktacji klasyfikatora dla tego dokumentu.";
      tr.append(td);
      tbody.append(tr);
      return;
    }
    const minByClass = new Map(state.classes.map((c) => [c.name, c.min_score]));
    for (const clsName of names) {
      const tr = document.createElement("tr");
      const tdName = document.createElement("td");
      tdName.className = "mono";
      tdName.textContent = clsName;
      const tdScore = document.createElement("td");
      tdScore.className = "mono";
      tdScore.textContent = String(scores[clsName]);
      const tdMin = document.createElement("td");
      tdMin.className = "mono";
      tdMin.textContent = minByClass.has(clsName) ? String(minByClass.get(clsName)) : "4";
      const tdVerdict = document.createElement("td");
      const p = document.createElement("span");
      if (doc.klasa === clsName) {
        p.className = "pill pill-ok";
        p.textContent = "wybrana";
      } else {
        p.className = "pill";
        p.textContent = Number(scores[clsName]) < (minByClass.get(clsName) ?? 4) ? "poniżej progu" : "inna klasa";
      }
      tdVerdict.append(p);
      tr.append(tdName, tdScore, tdMin, tdVerdict);
      tbody.append(tr);
    }
  }

  // ------------------------------------------------------------------ klasy YAML
  function syncYamlButtons() {
    const fnVal = el("yaml-filename").value;
    const editorVal = el("yaml-editor").value;
    const hasConflict = Boolean(state.conflictFilename) && fnVal === state.conflictFilename;
    const alertBox = el("yaml-alert");
    const retryBtn = el("btn-retry-overwrite");
    const saveBtn = el("btn-save-yaml");

    retryBtn.hidden = !hasConflict;
    retryBtn.disabled = state.yamlSaving || !hasConflict;
    saveBtn.disabled = state.yamlSaving || !editorVal.trim() || state.yamlInvalid;
    saveBtn.textContent = state.yamlSaving ? "Zapisywanie…" : "Zapisz klasę YAML";
    if (!hasConflict && alertBox.dataset.kind === "conflict") {
      alertBox.hidden = true;
    }
  }

  function showYamlError(msg, isConflict = false, conflictName = null) {
    el("yaml-success").hidden = true;
    const pill = el("yaml-valid-pill");
    pill.className = "pill pill-err";
    pill.textContent = isConflict ? "Konflikt nazwy (409)" : "Błąd YAML";
    const alertBox = el("yaml-alert");
    alertBox.dataset.kind = isConflict ? "conflict" : "error";
    el("yaml-alert-text").textContent = msg;
    alertBox.hidden = false;
    state.conflictFilename = isConflict ? conflictName : null;
    syncYamlButtons();
  }

  function clearYamlAlerts() {
    el("yaml-alert").hidden = true;
    el("yaml-success").hidden = true;
    state.conflictFilename = null;
    syncYamlButtons();
  }

  function renderClassPreview(summary) {
    const box = el("yaml-preview-box");
    const content = el("yaml-preview-content");
    if (!summary) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    const totalFields = (summary.sections || []).reduce((acc, s) => acc + s.fields.length, 0);
    content.replaceChildren();
    const line1 = document.createElement("div");
    line1.textContent = `Klasa: ${summary.name} · strony: ${summary.pages} · próg: ${summary.min_score} · słów kluczowych: ${summary.keywords_count}`;
    const line2 = document.createElement("div");
    line2.style.marginTop = "4px";
    line2.textContent = `Sekcje (${summary.sections.length}), pola (${totalFields}): `
      + summary.sections.map((s) => `${s.name}${s.is_list ? "[]" : ""} (${s.fields.length})`).join(", ");
    content.append(line1, line2);
    const rulesUsed = Array.from(
      new Set(
        (summary.sections || []).flatMap((s) => (s.fields || []).flatMap((f) => f.rules || []))
      )
    );
    if (rulesUsed.length) {
      const line3 = document.createElement("div");
      line3.style.marginTop = "4px";
      line3.className = "mono";
      line3.textContent = `Reguły walidacji YAML: ${rulesUsed.join(", ")}`;
      content.append(line3);
    }
  }

  function renderClassList() {
    const list = el("class-list");
    el("nav-class-count").textContent = String(state.classes.length);
    list.replaceChildren();
    for (const cls of state.classes) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "case-item";
      b.setAttribute("aria-pressed", cls.filename === state.selectedClassFilename ? "true" : "false");
      const name = document.createElement("span");
      name.className = "mono";
      name.textContent = cls.filename;
      const tag = document.createElement("span");
      tag.className = cls.builtin ? "doc-tag" : "pill pill-ok";
      tag.textContent = cls.builtin ? "wbudowana" : "własna";
      b.append(name, tag);
      b.addEventListener("click", () => {
        state.selectedClassFilename = cls.filename;
        state.yamlInvalid = false;
        clearYamlAlerts();
        el("yaml-filename").value = cls.filename;
        el("yaml-editor").value = cls.yaml || "";
        const totalFields = (cls.sections || []).reduce((acc, s) => acc + s.fields.length, 0);
        el("yaml-valid-pill").className = "pill pill-ok";
        el("yaml-valid-pill").textContent = `${pl(cls.sections.length, "sekcja", "sekcje", "sekcji")} · ${pl(totalFields, "pole", "pola", "pól")}`;
        renderClassPreview(cls);
        renderClassList();
        syncYamlButtons();
      });
      list.append(b);
    }
  }

  async function loadClasses() {
    try {
      const data = await apiFetch("/api/classes");
      state.classes = data.classes || [];
      renderClassList();
      if (!state.selectedClassFilename && state.classes.length) {
        const first = state.classes[0];
        state.selectedClassFilename = first.filename;
        el("yaml-filename").value = first.filename;
        el("yaml-editor").value = first.yaml || "";
        renderClassPreview(first);
        renderClassList();
        syncYamlButtons();
      }
    } catch (err) {
      showGlobalError(`Nie udało się wczytać klas YAML: ${err.message}`, loadClasses);
    }
  }

  async function validateYaml() {
    clearYamlAlerts();
    const yamlText = el("yaml-editor").value;
    try {
      const res = await apiFetch("/api/classes/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ yaml: yamlText }),
      });
      state.yamlInvalid = false;
      const s = res.summary;
      const totalFields = (s.sections || []).reduce((acc, sec) => acc + sec.fields.length, 0);
      el("yaml-valid-pill").className = "pill pill-ok";
      el("yaml-valid-pill").textContent = `Poprawny YAML: ${pl(s.sections.length, "sekcja", "sekcje", "sekcji")} · ${pl(totalFields, "pole", "pola", "pól")}`;
      renderClassPreview(s);
      syncYamlButtons();
    } catch (err) {
      state.yamlInvalid = true;
      el("yaml-valid-pill").className = "pill pill-err";
      el("yaml-valid-pill").textContent = "Błąd walidacji YAML";
      renderClassPreview(null);
      showYamlError(err.message, false);
    }
  }

  async function saveYaml(overwrite = false) {
    if (state.yamlSaving) return;
    const filename = el("yaml-filename").value;
    if (overwrite && filename !== state.conflictFilename) return;
    const yamlText = el("yaml-editor").value;
    state.yamlSaving = true;
    syncYamlButtons();
    try {
      const res = await apiFetch("/api/classes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: filename.trim(), yaml: yamlText, overwrite }),
      });
      state.classes = res.classes || state.classes;
      state.selectedClassFilename = res.saved.filename;
      state.yamlInvalid = false;
      state.conflictFilename = null;
      state.yamlSaving = false;
      el("yaml-filename").value = res.saved.filename;
      el("yaml-alert").hidden = true;
      el("yaml-success").textContent = `Zapisano klasę ${res.saved.filename} — aktywna od razu bez restartu.`;
      el("yaml-success").hidden = false;
      el("yaml-valid-pill").className = "pill pill-ok";
      el("yaml-valid-pill").textContent = `Zapisano: ${res.saved.filename}`;
      renderClassPreview(res.saved);
      renderClassList();
      syncYamlButtons();
    } catch (err) {
      state.yamlSaving = false;
      if (err.status === 409) {
        showYamlError(
          `Konflikt (409): ${err.message} Zmień nazwę pliku albo kliknij „Ponów z nadpisaniem” dla ${filename}.`,
          true,
          filename
        );
      } else {
        state.yamlInvalid = err.status === 400;
        showYamlError(err.message, false);
      }
    }
  }

  // ------------------------------------------------------------------ inicjalizacja i zdarzenia
  async function loadStatus() {
    try {
      const st = await apiFetch("/api/status");
      state.status = st;
      el("env-backend").textContent = st.backend ? st.backend.label : "CPU";
      el("env-checksum").textContent = `Tryb: ${st.checksum_policy || "confidence"}`;
      el("nav-class-count").textContent = String(st.classes_count || 0);
      const vrSelect = el("visual-reader-mode");
      const vrNote = el("visual-reader-note");
      const onOpt = vrSelect.querySelector('option[value="on"]');
      if (st.visual_reader_available) {
        if (onOpt) onOpt.disabled = false;
        vrSelect.value = st.visual_reader_default === "on" ? "on" : "off";
        vrNote.hidden = false;
        vrNote.textContent = `Dostępny projektor ${st.mmproj_name || "mmproj-F16.gguf"} (tylko dla skanów, max 12 wycinków/dokument).`;
      } else {
        if (onOpt) onOpt.disabled = true;
        vrSelect.value = "off";
        vrNote.hidden = false;
        vrNote.textContent = st.backend && st.backend.mode === "cpu"
          ? `Opcja „włączony” wymaga pliku models/${st.mmproj_name || "mmproj-F16.gguf"} (python tools/download_models.py --vision).`
          : "Czytelnik wizualny działa wyłącznie w lokalnym trybie CPU (GGUF + mmproj).";
      }
    } catch (err) {
      el("env-backend").className = "pill pill-err";
      el("env-backend").textContent = "Brak połączenia";
      showGlobalError(`Brak połączenia z backendem Web UI: ${err.message}`, loadStatus);
    }
  }

  function initEvents() {
    wireTablist([el("tab-cases"), el("tab-classes")], setTopTab);
    wireTablist([el("subtab-trace"), el("subtab-review"), el("subtab-classify")], setSubtab);

    const dropzone = el("dropzone");
    const fileInput = el("pdf-files");
    fileInput.addEventListener("change", () => {
      addFiles(fileInput.files);
      fileInput.value = "";
    });
    ["dragenter", "dragover"].forEach((ev) => {
      dropzone.addEventListener(ev, (e) => {
        e.preventDefault();
        dropzone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach((ev) => {
      dropzone.addEventListener(ev, (e) => {
        e.preventDefault();
        dropzone.classList.remove("is-dragover");
      });
    });
    dropzone.addEventListener("drop", (e) => {
      addFiles(e.dataTransfer && e.dataTransfer.files);
    });

    el("upload-form").addEventListener("submit", submitUpload);
    el("btn-clear-files").addEventListener("click", () => {
      state.stagedFiles = [];
      clearUploadError();
      renderFileChips();
    });
    el("btn-upload-err-close").addEventListener("click", clearUploadError);
    el("btn-refresh-cases").addEventListener("click", () => loadCases());
    el("btn-rerun-case").addEventListener("click", () => {
      if (state.selectedCaseName) runExistingCase(state.selectedCaseName);
    });

    el("btn-copy-json").addEventListener("click", async () => {
      const btn = el("btn-copy-json");
      const text = state.currentJsonText || el("json-view").textContent || "";
      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = "Skopiowano";
        setTimeout(() => { btn.textContent = "Kopiuj JSON"; }, 1800);
      } catch {
        btn.textContent = "Błąd schowka";
        setTimeout(() => { btn.textContent = "Kopiuj JSON"; }, 1800);
      }
    });

    el("btn-dl-json").addEventListener("click", () => {
      const detail = state.selectedCase;
      const doc = detail && detail.documents && detail.documents[state.selectedDocIdx];
      if (!detail || !doc || !doc.json_name) return;
      window.location.href = `/api/cases/${encodeURIComponent(detail.name)}/files/${encodeURIComponent(doc.json_name)}/json`;
    });

    el("trace-filter-strip").querySelectorAll(".filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.traceFilter = btn.dataset.filter;
        const doc = state.selectedCase && state.selectedCase.documents[state.selectedDocIdx];
        if (doc) renderTracePanel(doc, doc.trace || []);
      });
    });

    el("btn-job-cancel").addEventListener("click", async () => {
      if (!state.activeJob) return;
      try {
        const updated = await apiFetch(`/api/jobs/${encodeURIComponent(state.activeJob.job_id)}/cancel`, { method: "POST" });
        state.activeJob = updated;
        renderJobBanner();
      } catch (err) {
        showGlobalError(`Nie udało się anulować zadania: ${err.message}`);
      }
    });
    el("btn-job-retry").addEventListener("click", () => {
      if (state.lastRunAction) state.lastRunAction();
    });
    el("btn-job-close").addEventListener("click", () => {
      state.activeJob = null;
      renderJobBanner();
    });

    el("btn-global-retry").addEventListener("click", () => {
      const fn = state.lastGlobalRetry;
      hideGlobalError();
      if (fn) fn();
    });
    el("btn-global-dismiss").addEventListener("click", hideGlobalError);

    el("btn-new-class").addEventListener("click", () => {
      state.selectedClassFilename = null;
      state.yamlInvalid = false;
      clearYamlAlerts();
      el("yaml-filename").value = "decyzja.yaml";
      el("yaml-editor").value = NEW_CLASS_TEMPLATE;
      el("yaml-valid-pill").className = "pill";
      el("yaml-valid-pill").textContent = "Nowy szablon YAML";
      renderClassPreview(null);
      renderClassList();
      syncYamlButtons();
      el("yaml-filename").focus();
    });

    // Każda edycja pola nazwy pliku bezwarunkowo wygasza konflikt 409
    el("yaml-filename").addEventListener("input", () => {
      if (state.conflictFilename) {
        el("yaml-valid-pill").className = "pill";
        el("yaml-valid-pill").textContent = "Gotowy do zapisu";
      }
      state.conflictFilename = null;
      syncYamlButtons();
    });
    el("yaml-editor").addEventListener("input", () => {
      state.yamlInvalid = false;
      el("yaml-success").hidden = true;
      syncYamlButtons();
    });
    el("btn-validate-yaml").addEventListener("click", validateYaml);
    el("btn-save-yaml").addEventListener("click", () => saveYaml(false));
    el("btn-retry-overwrite").addEventListener("click", () => saveYaml(true));
    el("btn-yaml-alert-close").addEventListener("click", clearYamlAlerts);
  }

  initEvents();
  syncStartButton();
  syncYamlButtons();
  loadStatus();
  loadClasses();
  loadCases();
})();
