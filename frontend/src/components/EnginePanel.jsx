import React, { useEffect, useState } from "react";
import HelpTip from "./HelpTip.jsx";
import { api } from "../api.js";

const STATE_LABEL = { ready: "Running", starting: "Loading the model…", stopped: "Stopped", error: "Problem", downloading: "Downloading…" };

/** The built-in llama.cpp engine: download it, pick the model files, start/stop, read its log. */
export default function EnginePanel({ s, set, Row }) {
  const [st, setSt] = useState(null);
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    const tick = () => api.engine().then((x) => alive && setSt(x)).catch(() => {});
    tick();
    const t = setInterval(tick, 1500);
    api.engineModels().then((m) => alive && setFiles(m)).catch(() => {});
    return () => { alive = false; clearInterval(t); };
  }, []);

  const act = async (fn) => {
    setBusy(true); setErr("");
    try { setSt(await fn()); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const chat = files.filter((f) => !f.embedding);
  const embed = files.filter((f) => f.embedding);
  const withCurrent = (list, cur) => (cur && !list.some((f) => f.path === cur) ? [{ path: cur, name: cur.split(/[\\/]/).pop(), size_gb: 0 }, ...list] : list);
  const state = st?.state || "stopped";

  return (
    <div className="engine-panel">
      <div className={`status-line ${state === "ready" ? "ok" : state === "error" ? "bad" : ""}`}>
        <span className={`dot ${state === "ready" ? "on" : "off"}`} />
        <span className="grow">
          {!st ? "Checking…" : !st.installed && state !== "downloading" ? "The engine is not downloaded yet." : `${STATE_LABEL[state] || state}${st.message && st.message !== "Ready" ? ` — ${st.message}` : ""}`}
        </span>
        {st && state !== "downloading" && (
          <button className="btn small" disabled={busy} onClick={() => act(api.engineDownload)}>{st.installed ? "Update engine" : "Download engine"}</button>
        )}
      </div>
      {state === "downloading" && <progress className="engine-progress" max="1" value={st?.progress || 0} />}

      <Row label="Story model (.gguf)" help="engine_model_path">
        <select className="field" value={s.engine_model_path} onChange={(e) => set("engine_model_path", e.target.value)}>
          <option value="">(choose a model)</option>
          {withCurrent(chat, s.engine_model_path).map((f) => <option key={f.path} value={f.path}>{f.name}{f.size_gb ? ` · ${f.size_gb} GB` : ""}</option>)}
        </select>
      </Row>
      <Row label="Or a file path" hint="Any .gguf file on this PC">
        <input className="field" value={s.engine_model_path} onChange={(e) => set("engine_model_path", e.target.value.replace(/^"|"$/g, ""))} placeholder="C:\models\my-model.gguf" />
      </Row>
      <Row label="Memory search model" help="engine_embedding_path">
        <select className="field" value={s.engine_embedding_path} onChange={(e) => set("engine_embedding_path", e.target.value)}>
          <option value="">(none, keyword search only)</option>
          {withCurrent(embed, s.engine_embedding_path).map((f) => <option key={f.path} value={f.path}>{f.name}</option>)}
        </select>
      </Row>
      <Row label="GPU layers" help="engine_gpu_layers">
        <input className="field num" value={s.engine_gpu_layers} onChange={(e) => set("engine_gpu_layers", e.target.value)} />
      </Row>
      <div className="row gap">
        <button className="btn small" disabled={busy || !st?.installed || state === "downloading"} onClick={() => act(api.engineStart)}>{state === "ready" ? "Restart" : "Start"}</button>
        <button className="btn small" disabled={busy || state === "stopped"} onClick={() => act(api.engineStop)}>Stop</button>
        <span className="muted tiny">Saving these settings reloads the engine by itself.</span>
      </div>
      {err && <div className="error-text small">{err}</div>}
      {st?.log && (
        <details className="engine-log"><summary className="muted tiny">Engine log</summary><pre>{st.log}</pre></details>
      )}
    </div>
  );
}
