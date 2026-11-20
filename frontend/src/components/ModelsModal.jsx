import React, { useEffect, useState } from "react";
import Modal from "./Modal.jsx";
import { api } from "../api.js";

const SUGGESTIONS = ["Stheno", "roleplay 8B", "Lunaris 8B", "Mistral Nemo 12B", "nomic embed text"];
const fmtNum = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n || 0));
const gb = (n) => `${(n / 1e9).toFixed(2)} GB`;
const size = (g) => (g >= 1 ? `${g} GB` : `${Math.max(1, Math.round(g * 1000))} MB`);
const BIG_GB = 6.5; // above this an 8B-class card cannot hold the whole model

/** LM Studio-like model manager: your models, Hugging Face search and downloads, load/unload, hide, delete. */
export default function ModelsModal({ onClose }) {
  const [tab, setTab] = useState("mine");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [confirmDel, setConfirmDel] = useState("");

  const refresh = () => api.modelLibrary().then(setData).catch((e) => setErr(e.message));
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  const act = async (fn) => {
    setErr("");
    try { await fn(); await refresh(); } catch (e) { setErr(e.message); }
  };
  const eng = data?.engine;
  const active = (data?.downloads || []).filter((d) => ["queued", "downloading", "checking"].includes(d.state)).length;

  return (
    <Modal title="Models" onClose={onClose} wide>
      <div className={`status-line ${eng?.state === "ready" ? "ok" : eng?.state === "error" ? "bad" : ""}`}>
        <span className={`dot ${eng?.state === "ready" ? "on" : "off"}`} />
        <span className="grow">
          {!eng ? "Checking…" : !eng.installed ? "The built-in engine is not downloaded yet (needed to load models here)."
            : eng.mode !== "builtin" ? "Using LM Studio. Loading a model here switches to the built-in engine."
            : eng.state === "ready" ? `Loaded: ${eng.model.split(/[\\/]/).pop()}`
            : eng.state === "starting" ? "Loading the model…" : eng.message || "No model loaded."}
        </span>
        {eng && !eng.installed && eng.state !== "downloading" && <button className="btn small" onClick={() => act(api.engineDownload)}>Download engine</button>}
        {eng?.state === "downloading" && <progress max="1" value={eng.progress || 0} />}
        {eng && ["ready", "starting"].includes(eng.state) && <button className="btn small" onClick={() => act(() => api.unloadModel("story"))}>Unload</button>}
      </div>

      <div className="tabs models-tabs">
        {[["mine", "My models"], ["find", "Find more"], ["dl", `Downloads${active ? ` (${active})` : ""}`]].map(([k, label]) => (
          <button key={k} className={`tab ${tab === k ? "active" : ""}`} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>
      {err && <div className="error-text small">{err}</div>}

      {tab === "mine" && (
        <div>
          {data && !data.models.length && <p className="muted">No models yet. Use <b>Find more</b> to download one (for example Stheno, about 4.7 GB).</p>}
          {(data?.models || []).map((m) => (
            <div key={m.path} className={`card model-row ${m.disabled ? "off" : ""}`}>
              <div className="grow">
                <div className="model-name">{m.name}</div>
                <div className="muted tiny">
                  {m.repo} · {size(m.size_gb)}{m.quant ? ` · ${m.quant}` : ""}
                  {m.embedding && " · memory-search model"}
                  {m.size_gb > BIG_GB && !m.embedding && " · larger than an 8 GB card holds: part runs on the processor (slower)"}
                </div>
                <div className="row gap model-badges">
                  {m.loaded && <span className="chip on">{m.selected === "embedding" ? "Loaded for memory search" : "Loaded"}</span>}
                  {!m.loaded && m.selected && <span className="chip">{m.selected === "embedding" ? "Memory search model" : "Selected"}</span>}
                  {m.disabled && <span className="chip">Deactivated</span>}
                </div>
              </div>
              <div className="model-actions">
                {!m.disabled && (m.embedding
                  ? (m.selected === "embedding"
                    ? <button className="btn small" onClick={() => act(() => api.unloadModel("embedding"))}>Stop using</button>
                    : <button className="btn small" onClick={() => act(() => api.loadModel(m.path, "embedding"))}>Use for memory</button>)
                  : (m.loaded
                    ? <button className="btn small" onClick={() => act(() => api.unloadModel("story"))}>Unload</button>
                    : <button className="btn small primary" onClick={() => act(() => api.loadModel(m.path, "story"))}>Load</button>))}
                <button className="btn small ghost" onClick={() => act(() => api.setModelActive(m.path, m.disabled))}>{m.disabled ? "Activate" : "Deactivate"}</button>
                {confirmDel === m.path ? (
                  <span className="row gap center">
                    <span className="tiny">Delete {size(m.size_gb)} for good?</span>
                    <button className="btn small danger" onClick={() => { setConfirmDel(""); act(() => api.deleteModel(m.path)); }}>Delete</button>
                    <button className="btn small" onClick={() => setConfirmDel("")}>Keep</button>
                  </span>
                ) : <button className="btn small ghost" onClick={() => setConfirmDel(m.path)}>🗑</button>}
              </div>
            </div>
          ))}
          {data && <p className="muted tiny">Models are kept in {data.folder} (LM Studio sees them too). Deactivated models stay on disk but leave the model lists.</p>}
        </div>
      )}

      {tab === "find" && <Finder onDownloaded={() => setTab("dl")} setErr={setErr} />}

      {tab === "dl" && (
        <div>
          {!data?.downloads?.length && <p className="muted">Nothing downloading. Pick a model in <b>Find more</b>.</p>}
          {(data?.downloads || []).map((d) => (
            <div key={d.key} className="card">
              <div className="row center gap">
                <div className="grow">
                  <div className="model-name">{d.name}</div>
                  <div className="muted tiny">
                    {d.repo} · {d.total ? `${gb(d.done)} / ${gb(d.total)}` : "…"}
                    {d.state === "downloading" && d.speed_mb ? ` · ${d.speed_mb} MB/s` : ""}
                    {d.state === "checking" && " · checking the file…"}
                    {d.state === "done" && " · done"}
                    {d.state === "cancelled" && " · paused (Download again resumes it)"}
                  </div>
                </div>
                {["queued", "downloading", "checking"].includes(d.state)
                  ? <button className="btn small" onClick={() => act(() => api.cancelDownload(d.key))}>Cancel</button>
                  : <>
                      {d.state !== "done" && <button className="btn small" onClick={() => act(() => api.downloadModel(d.repo, d.file))}>Download again</button>}
                      {d.state === "done" && <button className="btn small primary" onClick={() => act(() => api.loadModel(d.path, /embed|nomic|bge|e5-|gte/i.test(d.name) ? "embedding" : "story"))}>Load</button>}
                      <button className="btn small ghost" onClick={() => act(() => api.clearDownload(d.key))} title={d.state === "done" ? "Remove from this list" : "Remove and delete the partial file"}>✕</button>
                    </>}
              </div>
              <progress className="engine-progress" max={d.total || 1} value={d.done || 0} />
              {d.error && <div className="error-text small">{d.error}</div>}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

function Finder({ onDownloaded, setErr }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState(null);
  const [open, setOpen] = useState("");
  const [files, setFiles] = useState({});
  const [busy, setBusy] = useState(false);

  const search = async (text = q) => {
    setQ(text); setBusy(true); setErr(""); setOpen("");
    try { setResults(await api.searchModels(text)); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const toggle = async (id) => {
    if (open === id) return setOpen("");
    setOpen(id);
    if (!files[id]) {
      try { const f = await api.modelFiles(id); setFiles((x) => ({ ...x, [id]: f })); } catch (e) { setErr(e.message); }
    }
  };
  const download = async (repo, file) => {
    setErr("");
    try { await api.downloadModel(repo, file); onDownloaded(); } catch (e) { setErr(e.message); }
  };

  return (
    <div>
      <form className="row gap" onSubmit={(e) => { e.preventDefault(); search(); }}>
        <input className="field grow" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search Hugging Face (only GGUF models are shown)" />
        <button className="btn primary" disabled={busy}>{busy ? "Searching…" : "Search"}</button>
      </form>
      <div className="row gap wrap model-suggest">
        {SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => search(s)}>{s}</button>)}
      </div>
      {results && !results.length && <p className="muted">No GGUF models found.</p>}
      {(results || []).map((r) => (
        <div key={r.id} className="card">
          <button className="model-repo" onClick={() => toggle(r.id)}>
            <span className="grow">{open === r.id ? "▾" : "▸"} <b>{r.id}</b></span>
            <span className="muted tiny">⬇ {fmtNum(r.downloads)} · ♥ {fmtNum(r.likes)}</span>
          </button>
          {r.tags.length > 0 && <div className="row gap wrap">{r.tags.map((t) => <span key={t} className="chip">{t}</span>)}</div>}
          {open === r.id && (
            <div className="model-files">
              {!files[r.id] ? <p className="muted tiny">Loading the file list…</p> : !files[r.id].length ? <p className="muted tiny">No GGUF files in this repository.</p> : (
                files[r.id].map((f) => (
                  <div key={f.file} className="row center gap model-file">
                    <div className="grow">
                      <div>{f.quant || f.name}{f.parts.length > 1 ? ` (${f.parts.length} parts)` : ""} · <b>{size(f.size_gb)}</b></div>
                      <div className="muted tiny">{f.note}{f.size_gb > BIG_GB ? (f.note ? " · " : "") + "larger than an 8 GB card holds" : ""}</div>
                    </div>
                    {f.installed ? <span className="chip on">On this PC</span> : <button className="btn small" onClick={() => download(r.id, f.file)}>Download</button>}
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      ))}
      <p className="muted tiny">Downloads come from huggingface.co and are checked against the checksum it publishes. Some models need a Hugging Face login; those are skipped.</p>
    </div>
  );
}
