import React, { useEffect, useState } from "react";
import Modal from "./Modal.jsx";
import { api } from "../api.js";

function Row({ label, hint, children }) {
  return (
    <div className="set-row">
      <div className="set-label">{label}{hint && <div className="muted tiny">{hint}</div>}</div>
      <div className="set-control">{children}</div>
    </div>
  );
}

export default function SettingsModal({ onClose, onSaved }) {
  const [s, setS] = useState(null);
  const [models, setModels] = useState([]);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [advanced, setAdvanced] = useState(false);

  const loadModels = async () => {
    try { const h = await api.health(); setHealth(h); setModels(h.llm?.models || []); } catch (e) { setHealth({ llm: { ok: false, error: e.message } }); }
  };
  useEffect(() => { api.settings().then(setS).catch((e) => setError(e.message)); loadModels(); }, []);

  if (!s) return <Modal title="Settings" onClose={onClose}>{error ? <div className="error-text">{error}</div> : "Loading…"}</Modal>;

  const set = (k, v) => setS((prev) => ({ ...prev, [k]: v }));
  const num = (k, parse = parseFloat) => (e) => { const v = parse(e.target.value); set(k, Number.isNaN(v) ? 0 : v); };
  const save = async () => {
    setSaving(true); setError("");
    try { await api.saveSettings(s); onSaved?.(); onClose(); } catch (e) { setError(e.message); } finally { setSaving(false); }
  };
  const modelOptions = (current) => (current && !models.includes(current) ? [current, ...models] : models);

  return (
    <Modal title="Settings" onClose={onClose} wide footer={
      <>
        {error && <span className="error-text small grow">{error}</span>}
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
      </>
    }>
      <div className={`status-line ${health?.llm?.ok ? "ok" : "bad"}`}>
        <span className={`dot ${health?.llm?.ok ? "on" : "off"}`} />
        {health?.llm?.ok ? `Connected to ${health.llm.base_url}` : (health?.llm?.error || "Checking connection…")}
        <button className="btn small" onClick={loadModels}>Refresh</button>
      </div>

      <h3>Model</h3>
      <Row label="Server address" hint="LM Studio default: http://localhost:1234/v1">
        <input className="field" value={s.llm_base_url} onChange={(e) => set("llm_base_url", e.target.value)} />
      </Row>
      <Row label="Chat model" hint="The model that writes the story">
        <select className="field" value={s.model} onChange={(e) => set("model", e.target.value)}>
          <option value="">(first available)</option>
          {modelOptions(s.model).map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </Row>
      <Row label="Embedding model" hint="Optional. Makes memory and skill search smarter">
        <select className="field" value={s.embedding_model} onChange={(e) => set("embedding_model", e.target.value)}>
          <option value="">(none, keyword search only)</option>
          {modelOptions(s.embedding_model).map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </Row>
      <Row label="Context window" hint="Must match the context length loaded in LM Studio">
        <input className="field num" value={s.context_window} onChange={num("context_window", (v) => parseInt(v, 10))} />
      </Row>
      <Row label={`Creativity (temperature): ${Number(s.temperature).toFixed(2)}`} hint="Lower = more consistent, higher = more surprising">
        <input type="range" min="0.2" max="1.5" step="0.05" value={s.temperature} onChange={num("temperature")} />
      </Row>
      <Row label="Max reply length (tokens)">
        <input className="field num" value={s.max_tokens} onChange={num("max_tokens", (v) => parseInt(v, 10))} />
      </Row>

      <h3>Game</h3>
      <Row label="Language of the story">
        <select className="field" value={s.response_language} onChange={(e) => set("response_language", e.target.value)}>
          <option value="en">English</option>
          <option value="pt-BR">Português (Brasil)</option>
          <option value="auto">Same as I write</option>
        </select>
      </Row>
      <Row label="Track the sheet automatically" hint="Extra model call after each reply (HP, items, relationships, memories). Turn off for faster replies">
        <input type="checkbox" checked={s.state_tracking} onChange={(e) => set("state_tracking", e.target.checked)} />
      </Row>
      <Row label="Summarize old messages" hint="Keeps long games coherent">
        <input type="checkbox" checked={s.auto_summary} onChange={(e) => set("auto_summary", e.target.checked)} />
      </Row>
      <Row label="Extra instructions" hint="Added to every prompt: your own style rules">
        <textarea className="field" rows={3} value={s.extra_instructions} onChange={(e) => set("extra_instructions", e.target.value)} placeholder="e.g. Use gritty, noir descriptions. Keep replies under 3 paragraphs." />
      </Row>

      <button className="btn ghost" onClick={() => setAdvanced(!advanced)}>{advanced ? "▾" : "▸"} Advanced</button>
      {advanced && (
        <div>
          <Row label="top_p"><input className="field num" value={s.top_p} onChange={num("top_p")} /></Row>
          <Row label="top_k"><input className="field num" value={s.top_k} onChange={num("top_k", (v) => parseInt(v, 10))} /></Row>
          <Row label="min_p"><input className="field num" value={s.min_p} onChange={num("min_p")} /></Row>
          <Row label="Repeat penalty"><input className="field num" value={s.repeat_penalty} onChange={num("repeat_penalty")} /></Row>
          <Row label="Memories recalled per turn"><input className="field num" value={s.memory_top_k} onChange={num("memory_top_k", (v) => parseInt(v, 10))} /></Row>
          <Row label="Recent messages kept verbatim"><input className="field num" value={s.keep_recent_messages} onChange={num("keep_recent_messages", (v) => parseInt(v, 10))} /></Row>
          <Row label="Skills per turn"><input className="field num" value={s.skills_top_k} onChange={num("skills_top_k", (v) => parseInt(v, 10))} /></Row>
          <Row label="Max relationship change per turn"><input className="field num" value={s.relationship_max_step} onChange={num("relationship_max_step", (v) => parseInt(v, 10))} /></Row>
        </div>
      )}
    </Modal>
  );
}
