import React, { useEffect, useState } from "react";
import Modal from "./Modal.jsx";
import HelpTip from "./HelpTip.jsx";
import KindPicker from "./KindPicker.jsx";
import { api } from "../api.js";

function Row({ label, help, hint, children }) {
  return (
    <div className="set-row">
      <div className="set-label">
        {label} {help && <HelpTip id={help} />}
        {hint && <div className="muted tiny">{hint}</div>}
      </div>
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
  const int = (v) => parseInt(v, 10);
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

      <h3>Play style <HelpTip id="default_card_kind" /></h3>
      <KindPicker value={s.default_card_kind} onChange={(k) => set("default_card_kind", k)} />
      <p className="muted tiny">The type new cards start with. Every card can change its own type and details in the card editor.</p>

      <h3>Model</h3>
      <Row label="Server address" help="llm_base_url" hint="LM Studio default: http://localhost:1234/v1">
        <input className="field" value={s.llm_base_url} onChange={(e) => set("llm_base_url", e.target.value)} />
      </Row>
      <Row label="Chat model" help="model">
        <select className="field" value={s.model} onChange={(e) => set("model", e.target.value)}>
          <option value="">(first available)</option>
          {modelOptions(s.model).map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </Row>
      <Row label="Embedding model" help="embedding_model">
        <select className="field" value={s.embedding_model} onChange={(e) => set("embedding_model", e.target.value)}>
          <option value="">(none, keyword search only)</option>
          {modelOptions(s.embedding_model).map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </Row>
      <Row label="Context window" help="context_window">
        <input className="field num" value={s.context_window} onChange={num("context_window", int)} />
      </Row>
      <Row label={`Creativity: ${Number(s.temperature).toFixed(2)}`} help="temperature">
        <input type="range" min="0.2" max="1.5" step="0.05" value={s.temperature} onChange={num("temperature")} />
      </Row>

      <h3>Speed and memory</h3>
      <Row label="Reply length" help="reply_length">
        <select className="field" value={s.reply_length} onChange={(e) => set("reply_length", e.target.value)}>
          <option value="short">Short (fastest)</option>
          <option value="medium">Medium</option>
          <option value="long">Long (slowest)</option>
        </select>
      </Row>
      <Row label="Rounds kept word for word" help="recent_rounds">
        <input className="field num" value={s.recent_rounds} onChange={num("recent_rounds", int)} />
      </Row>
      <Row label="Track the sheet automatically" help="state_tracking">
        <input type="checkbox" checked={s.state_tracking} onChange={(e) => set("state_tracking", e.target.checked)} />
      </Row>
      <Row label="Summarize old messages" help="auto_summary">
        <input type="checkbox" checked={s.auto_summary} onChange={(e) => set("auto_summary", e.target.checked)} />
      </Row>
      <Row label="Show timing under replies" help="show_timing">
        <input type="checkbox" checked={s.show_timing} onChange={(e) => set("show_timing", e.target.checked)} />
      </Row>

      <h3>Game</h3>
      <Row label="Language of the story" help="response_language">
        <select className="field" value={s.response_language} onChange={(e) => set("response_language", e.target.value)}>
          <option value="en">English</option>
          <option value="pt-BR">Português (Brasil)</option>
          <option value="auto">Same as I write</option>
        </select>
      </Row>
      <Row label="Extra instructions" help="extra_instructions">
        <textarea className="field" rows={3} value={s.extra_instructions} onChange={(e) => set("extra_instructions", e.target.value)} placeholder="e.g. Use gritty, noir descriptions." />
      </Row>

      <button className="btn ghost" onClick={() => setAdvanced(!advanced)}>{advanced ? "▾" : "▸"} Advanced</button>
      {advanced && (
        <div>
          <Row label="Hard cap on a reply (tokens)" help="max_tokens"><input className="field num" value={s.max_tokens} onChange={num("max_tokens", int)} /></Row>
          <Row label="Fold block size (rounds)" help="fold_block_rounds"><input className="field num" value={s.fold_block_rounds} onChange={num("fold_block_rounds", int)} /></Row>
          <Row label="Summary size (characters)" help="summary_char_budget"><input className="field num" value={s.summary_char_budget} onChange={num("summary_char_budget", int)} /></Row>
          <Row label="Facts recalled per turn" help="memory_top_k"><input className="field num" value={s.memory_top_k} onChange={num("memory_top_k", int)} /></Row>
          <Row label="Space for recalled facts (characters)" help="memory_char_budget"><input className="field num" value={s.memory_char_budget} onChange={num("memory_char_budget", int)} /></Row>
          <Row label="Memory box size (characters)" help="pinned_memory_limit"><input className="field num" value={s.pinned_memory_limit} onChange={num("pinned_memory_limit", int)} /></Row>
          <Row label="Max relationship change per turn" help="relationship_max_step"><input className="field num" value={s.relationship_max_step} onChange={num("relationship_max_step", int)} /></Row>
          <Row label="top_p" help="top_p"><input className="field num" value={s.top_p} onChange={num("top_p")} /></Row>
          <Row label="top_k" help="top_k"><input className="field num" value={s.top_k} onChange={num("top_k", int)} /></Row>
          <Row label="min_p" help="min_p"><input className="field num" value={s.min_p} onChange={num("min_p")} /></Row>
          <Row label="Repeat penalty" help="repeat_penalty"><input className="field num" value={s.repeat_penalty} onChange={num("repeat_penalty")} /></Row>
        </div>
      )}
    </Modal>
  );
}
