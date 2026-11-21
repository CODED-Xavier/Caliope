import React, { useEffect, useState } from "react";
import Modal from "./Modal.jsx";
import HelpTip from "./HelpTip.jsx";
import KindPicker from "./KindPicker.jsx";
import EnginePanel from "./EnginePanel.jsx";
import { api } from "../api.js";
import { UI_LANGUAGES, setUiLanguage } from "../i18n/index.js";

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

export default function SettingsModal({ onClose, onSaved, onTour }) {
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

      <Row label="Interface language" help="ui_language">
        <select className="field" value={s.ui_language || "en"} onChange={(e) => {
          const v = e.target.value; set("ui_language", v); setUiLanguage(v); api.saveSettings({ ui_language: v }).catch(() => {});
        }}>
          {UI_LANGUAGES.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
        </select>
      </Row>

      <h3>Play style <HelpTip id="default_card_kind" /></h3>
      <KindPicker value={s.default_card_kind} onChange={(k) => set("default_card_kind", k)} />
      <p className="muted tiny">The type new cards start with. Every card can change its own type and details in the card editor.</p>

      <h3>Model</h3>
      <Row label="AI engine" help="ai_engine">
        <select className="field" value={s.ai_engine} onChange={(e) => set("ai_engine", e.target.value)}>
          <option value="builtin">Built-in (on this PC)</option>
          <option value="lmstudio">Another server (advanced: an online service with your API key)</option>
        </select>
      </Row>
      {s.ai_engine === "builtin" ? <EnginePanel s={s} set={set} Row={Row} /> : (<>
      <Row label="Server address" help="llm_base_url" hint="An OpenAI-compatible address, e.g. https://openrouter.ai/api/v1">
        <input className="field" value={s.llm_base_url} onChange={(e) => set("llm_base_url", e.target.value)} />
      </Row>
      <Row label="API key" help="api_key" hint="Your key for that service.">
        <SecretField value={s.api_key ?? ""} onChange={(v) => set("api_key", v)} />
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
      </>)}
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
      {s.state_tracking && (
        <Row label="Skip tracking on quiet turns" help="tracker_skip">
          <input type="checkbox" checked={s.tracker_skip !== false} onChange={(e) => set("tracker_skip", e.target.checked)} />
        </Row>
      )}
      <Row label="Summarize old messages" help="auto_summary">
        <input type="checkbox" checked={s.auto_summary} onChange={(e) => set("auto_summary", e.target.checked)} />
      </Row>
      <Row label="Scene pictures (internet)" help="scene_pictures">
        <input type="checkbox" checked={!!s.scene_pictures} onChange={(e) => set("scene_pictures", e.target.checked)} />
      </Row>
      {s.scene_pictures && (<>
        <Row label="Picture style" help="scene_picture_style">
          <input className="field" value={s.scene_picture_style || ""} onChange={(e) => set("scene_picture_style", e.target.value)} />
        </Row>
        <Row label="Painted by" help="picture_service">
          <select className="field" value={s.picture_service || "pollinations"} onChange={(e) => set("picture_service", e.target.value)}>
            <option value="pollinations">Pollinations (free, no account)</option>
            <option value="pixai">PixAI (your own API key)</option>
          </select>
        </Row>
        {s.picture_service === "pixai" && (<>
          <Row label="PixAI API key" help="pixai_api_key">
            <SecretField value={s.pixai_api_key || ""} onChange={(v) => set("pixai_api_key", v)} />
          </Row>
          <Row label="PixAI model version ID" help="pixai_model">
            <input className="field" value={s.pixai_model || ""} placeholder="e.g. 1983308862240288769" onChange={(e) => set("pixai_model", e.target.value.trim())} />
          </Row>
        </>)}
      </>)}
      <h3>Narration voice <HelpTip id="voice" /></h3>
      <VoicePanel s={s} set={set} Row={Row} />
      {onTour && <div className="row gap center" style={{ margin: "6px 0" }}><span className="muted small grow">New here, or showing Calíope to a friend?</span><button className="btn small" onClick={onTour}>▶ Show the tour again</button></div>}
      <h3>Backups</h3>
      <Row label="Back up every day" help="backups">
        <input type="checkbox" checked={s.backups !== false} onChange={(e) => set("backups", e.target.checked)} />
      </Row>
      <Row label="Days to keep" help="backups">
        <input className="field num" style={{ width: 64 }} value={s.backups_keep ?? 7} onChange={(e) => set("backups_keep", Math.max(1, Math.min(60, parseInt(e.target.value, 10) || 7)))} />
      </Row>
      <BackupBox />
      <h3>Pictures in the cloud (optional)</h3>
      <div className="muted tiny">Your private Cloudflare R2 bucket for card pictures. Leave empty to keep pictures only on this PC.</div>
      <Row label="R2 account ID" help="r2">
        <input className="field" value={s.r2_account_id || ""} onChange={(e) => set("r2_account_id", e.target.value.trim())} />
      </Row>
      <Row label="R2 bucket name" help="r2">
        <input className="field" value={s.r2_bucket || ""} onChange={(e) => set("r2_bucket", e.target.value.trim())} />
      </Row>
      <Row label="R2 access key ID" help="r2">
        <SecretField value={s.r2_access_key_id || ""} onChange={(v) => set("r2_access_key_id", v.trim())} />
      </Row>
      <Row label="R2 secret access key" help="r2">
        <SecretField value={s.r2_secret_access_key || ""} onChange={(v) => set("r2_secret_access_key", v.trim())} />
      </Row>
      <Row label="Continue from the last played card" help="continue_last">
        <input type="checkbox" checked={!!s.continue_last} onChange={(e) => set("continue_last", e.target.checked)} />
      </Row>
      <Row label="Open in its own window" help="app_window">
        <input type="checkbox" checked={s.app_window !== false} onChange={(e) => set("app_window", e.target.checked)} />
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


/** A key or password box: hidden by default, with Show/Hide. */
function SecretField({ value, onChange }) {
  const [show, setShow] = useState(false);
  return (
    <div className="row gap center">
      <input className="field grow" type={show ? "text" : "password"} value={value} autoComplete="off" spellCheck={false}
        onChange={(e) => onChange(e.target.value)} />
      <button type="button" className="btn small" onClick={() => setShow((v) => !v)}>{show ? "Hide" : "Show"}</button>
    </div>
  );
}


function BackupBox() {
  const [info, setInfo] = useState(null);
  const [note, setNote] = useState("");
  useEffect(() => { api.backups().then(setInfo).catch(() => {}); }, []);
  const now = async () => { try { const r = await api.backupNow(); setInfo((i) => ({ ...i, backups: r.backups })); setNote("Backup saved."); } catch (e) { setNote(e.message); } };
  const open = async () => { try { await api.openBackups(); } catch (e) { setNote(e.message); } };
  const last = info?.backups?.[0];
  return (
    <div className="row gap center" style={{ margin: "4px 0 10px" }}>
      <span className="muted small grow">{last ? `Last backup: ${last.date} (${info.backups.length} kept)` : "No backup yet."}{note && ` · ${note}`}</span>
      <button className="btn small" onClick={now}>Back up now</button>
      <button className="btn small" onClick={open} title={info?.folder}>Open folder</button>
    </div>
  );
}


function VoicePanel({ s, set, Row }) {
  const [st, setSt] = useState(null);
  const [err, setErr] = useState("");
  const load = () => api.voice().then(setSt).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const busy = st && (st.engine_progress != null || st.voices.some((v) => v.progress != null));
  useEffect(() => {
    if (!busy) return undefined;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [busy]); // eslint-disable-line
  if (!st) return <div className="muted small">{err || "Loading…"}</div>;
  const installed = st.voices.filter((v) => v.installed);
  const act = async (fn) => { setErr(""); try { setSt(await fn()); } catch (e) { setErr(e.message); } };
  return (
    <>
      {!st.supported && <div className="muted small">The voice program is downloaded for Windows only.</div>}
      {st.engine_progress != null && <div className="small"><span className="spinner" /> Downloading the voice program… {Math.round(st.engine_progress * 100)}%</div>}
      {st.voices.map((v) => (
        <div key={v.id} className="row gap center voice-row">
          <span className="small grow">{v.label}</span>
          {v.progress != null ? <span className="tiny muted">{Math.round(v.progress * 100)}%</span>
            : v.installed ? (
              <>
                <span className="tiny ok-text">✓ ready</span>
                <button className="icon-btn" title="Delete this voice" onClick={() => act(() => api.voiceRemove(v.id))}>🗑</button>
              </>
            ) : <button className="btn small" disabled={busy || !st.supported} onClick={() => act(() => api.voiceInstall(v.id))}>Download (~60 MB)</button>}
          {v.error && <span className="tiny error-text" title={v.error}>failed</span>}
        </div>
      ))}
      <Row label="Voice for 🔊" help="voice">
        <select className="field" value={s.voice_name || ""} onChange={(e) => set("voice_name", e.target.value)}>
          <option value="">(off)</option>
          {installed.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
        </select>
      </Row>
      {s.voice_name && (<>
        <Row label={`Speed ${Number(s.voice_speed || 1).toFixed(2)}×`} help="voice">
          <input type="range" min="0.6" max="1.6" step="0.05" value={s.voice_speed || 1} onChange={(e) => set("voice_speed", parseFloat(e.target.value))} />
        </Row>
        <Row label="Read every new reply aloud" help="voice">
          <input type="checkbox" checked={!!s.voice_auto} onChange={(e) => set("voice_auto", e.target.checked)} />
        </Row>
      </>)}
      {err && <div className="error-text small">{err}</div>}
    </>
  );
}
