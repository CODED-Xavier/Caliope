import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, streamPost } from "./api.js";
import Sidebar from "./components/Sidebar.jsx";
import Chat from "./components/Chat.jsx";
import SidePanel from "./components/SidePanel.jsx";
import SettingsModal from "./components/SettingsModal.jsx";
import SkillsModal from "./components/SkillsModal.jsx";
import ScenarioModal from "./components/ScenarioModal.jsx";
import { KIND_LABELS, MODE_LABELS } from "./utils.js";

const VIEW_DEFAULTS = { fontSize: 16, wide: false, compact: false, follow: false, panelWidth: 372 };
function loadView() {
  try { return { ...VIEW_DEFAULTS, ...JSON.parse(localStorage.getItem("view") || "{}") }; } catch { return { ...VIEW_DEFAULTS }; }
}

/** "Aa" menu: how the story looks and behaves. Saved in this browser. */
function ViewMenu({ view, setView, onClose }) {
  const set = (k, v) => setView({ ...view, [k]: v });
  useEffect(() => {
    const off = (e) => { if (!e.target.closest(".view-menu, .view-btn")) onClose(); };
    window.addEventListener("mousedown", off);
    return () => window.removeEventListener("mousedown", off);
  }, [onClose]);
  return (
    <div className="view-menu">
      <div className="row gap center">
        <span className="grow small">Text size</span>
        <button className="btn small" onClick={() => set("fontSize", Math.max(13, view.fontSize - 1))}>A−</button>
        <span className="small">{view.fontSize}px</span>
        <button className="btn small" onClick={() => set("fontSize", Math.min(24, view.fontSize + 1))}>A+</button>
      </div>
      <label className="check small"><input type="checkbox" checked={view.wide} onChange={(e) => set("wide", e.target.checked)} />Wider story column</label>
      <label className="check small"><input type="checkbox" checked={view.compact} onChange={(e) => set("compact", e.target.checked)} />Compact (less spacing)</label>
      <label className="check small"><input type="checkbox" checked={view.follow} onChange={(e) => set("follow", e.target.checked)} />Follow the text while it is written</label>
      <div className="muted tiny">Off: the view stops at the start of each new reply so you can read at your pace.</div>
      <button className="btn small" onClick={() => setView({ ...VIEW_DEFAULTS, panelWidth: view.panelWidth })}>Reset</button>
    </div>
  );
}

function initialTheme() {
  const saved = localStorage.getItem("theme");
  if (saved) return saved;
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export default function App() {
  const [theme, setTheme] = useState(initialTheme);
  const [convs, setConvs] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [game, setGame] = useState(null); // {conversation, messages, state, npcs, memory_count}
  const [stream, setStream] = useState(null); // {text, phase, context}
  const [lastContext, setLastContext] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [modal, setModal] = useState(null); // "new" | "settings" | "skills"
  const [panelOpen, setPanelOpen] = useState(true);
  const [tab, setTab] = useState("sheet");
  const [health, setHealth] = useState(null);
  const [memoryKey, setMemoryKey] = useState(0);
  const [view, setViewState] = useState(loadView);
  const [viewOpen, setViewOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const setView = (v) => { setViewState(v); try { localStorage.setItem("view", JSON.stringify(v)); } catch { /* private mode */ } };

  const abortRef = useRef(null);
  const activeRef = useRef(null);
  const bufferRef = useRef("");
  const rafRef = useRef(0);
  activeRef.current = activeId;

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f" && activeRef.current) { e.preventDefault(); setSearchOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  const refreshConvs = useCallback(() => api.conversations().then(setConvs).catch(() => {}), []);
  const refreshHealth = useCallback(() => api.health().then(setHealth).catch(() => setHealth({ llm: { ok: false } })), []);

  useEffect(() => {
    refreshConvs();
    refreshHealth();
    const t = setInterval(refreshHealth, 20000);
    const last = parseInt(localStorage.getItem("activeConv") || "", 10);
    if (last) openConversation(last, true);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, []);

  async function openConversation(id, quiet = false) {
    try {
      const data = await api.conversation(id);
      setActiveId(id);
      localStorage.setItem("activeConv", String(id));
      setGame(data);
      setLastContext(null);
      setError("");
    } catch (e) {
      if (!quiet) setError(e.message);
      localStorage.removeItem("activeConv");
    }
  }

  const reloadGame = useCallback(async () => {
    const id = activeRef.current;
    if (!id) return;
    try { setGame(await api.conversation(id)); } catch { /* ignore */ }
  }, []);

  // --- streaming a turn ---------------------------------------------------
  const flushTokens = () => {
    rafRef.current = 0;
    const chunk = bufferRef.current;
    bufferRef.current = "";
    if (chunk) setStream((s) => (s ? { ...s, text: s.text + chunk, phase: "writing" } : s));
  };

  const handleEvent = (ev) => {
    switch (ev.type) {
      case "user_message":
        setGame((g) => (g ? { ...g, messages: [...g.messages, ev.message] } : g));
        break;
      case "rolled_back":
        setGame((g) => {
          if (!g) return g;
          const msgs = [...g.messages];
          while (msgs.length && msgs[msgs.length - 1].role === "assistant") msgs.pop();
          return { ...g, messages: msgs };
        });
        break;
      case "context":
        setStream((s) => (s ? { ...s, context: ev } : s));
        setLastContext({ skills: ev.skills || [], memories: ev.memories || [] });
        break;
      case "token":
        bufferRef.current += ev.text;
        if (!rafRef.current) rafRef.current = requestAnimationFrame(flushTokens);
        break;
      case "assistant_message":
        if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = 0; }
        bufferRef.current = "";
        setGame((g) => (g ? { ...g, messages: [...g.messages, ev.message] } : g));
        setStream((s) => (s ? { ...s, text: "", phase: "saved" } : s));
        break;
      case "continue_start":
        setStream((s) => (s ? { ...s, continuing: true } : s));
        break;
      case "message_updated":
        if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = 0; }
        bufferRef.current = "";
        setGame((g) => (g ? { ...g, messages: g.messages.map((m) => (m.id === ev.message.id ? ev.message : m)) } : g));
        setStream((s) => (s ? { ...s, text: "", phase: "saved" } : s));
        break;
      case "analysis_start":
        setStream((s) => (s ? { ...s, phase: "updating" } : s));
        break;
      case "state":
        setGame((g) => (g ? { ...g, state: ev.state, npcs: ev.npcs } : g));
        setMemoryKey((k) => k + 1);
        break;
      case "summary":
        setGame((g) => (g ? { ...g, conversation: { ...g.conversation, summary: ev.summary } } : g));
        break;
      case "error":
        setError(ev.message);
        break;
      default:
        break;
    }
  };

  async function runTurn(path, body) {
    if (busy || !activeRef.current) return;
    setBusy(true);
    setError("");
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStream({ text: "", phase: "thinking", context: null });
    try {
      await streamPost(path, body, handleEvent, ctrl.signal);
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = 0; }
      bufferRef.current = "";
      abortRef.current = null;
      setBusy(false);
      setStream(null);
      await reloadGame();
      refreshConvs();
      refreshHealth();
    }
  }

  const send = (text) => runTurn(`/api/conversations/${activeRef.current}/chat`, { content: text });
  const regenerate = () => runTurn(`/api/conversations/${activeRef.current}/regenerate`, {});
  const continueReply = () => runTurn(`/api/conversations/${activeRef.current}/continue`, {});
  const stop = () => abortRef.current?.abort();

  const undo = async () => {
    if (busy || !activeId) return;
    if (!window.confirm("Remove the last exchange (your message and the reply)? Sheet and relationships go back to how they were.")) return;
    try { setGame(await api.undo(activeId)); refreshConvs(); } catch (e) { setError(e.message); }
  };

  // --- editing history ------------------------------------------------------
  const editMessage = async (messageId, content) => {
    try { await api.editMessage(messageId, content); await reloadGame(); return true; } catch (e) { setError(e.message); return false; }
  };
  const resendMessage = (messageId, content) => {
    // Show the edited message right away; everything after it is discarded by the backend.
    setGame((g) => {
      if (!g) return g;
      const idx = g.messages.findIndex((m) => m.id === messageId);
      if (idx < 0) return g;
      const messages = g.messages.slice(0, idx + 1);
      messages[idx] = { ...messages[idx], content, meta: { ...messages[idx].meta, edited: true } };
      return { ...g, messages };
    });
    runTurn(`/api/conversations/${activeRef.current}/messages/${messageId}/resend`, { content });
  };
  const rewindTo = async (messageId, inclusive) => {
    if (busy || !activeId) return;
    const text = inclusive
      ? "Delete this message and everything after it? The sheet, characters and memories go back to how they were before it."
      : "Delete everything after this message? The sheet, characters and memories go back to how they were at this point.";
    if (!window.confirm(text)) return;
    try { setGame(await api.rewind(activeId, messageId, inclusive)); setLastContext(null); setMemoryKey((k) => k + 1); refreshConvs(); } catch (e) { setError(e.message); }
  };

  const forkAt = async (messageId) => {
    if (busy || !activeId) return;
    if (!window.confirm("Make a save point here? A new game starts from this moment, with the sheet, characters and memories as they were. This game stays as it is.")) return;
    try {
      const data = await api.fork(activeId, messageId);
      setActiveId(data.conversation.id);
      localStorage.setItem("activeConv", String(data.conversation.id));
      setGame(data); setLastContext(null); setMemoryKey((k) => k + 1);
      refreshConvs();
    } catch (e) { setError(e.message); }
  };

  const startResize = (e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = view.panelWidth;
    let w = startW;
    const move = (ev) => {
      w = Math.max(300, Math.min(720, startW + (startX - ev.clientX)));
      document.documentElement.style.setProperty("--panel-w", `${w}px`);
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      document.body.classList.remove("resizing");
      setView({ ...view, panelWidth: w });
    };
    document.body.classList.add("resizing");
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  const savePinned = async (text) => {
    try {
      const conversation = await api.setPinned(activeId, text);
      setGame((g) => (g ? { ...g, conversation: { ...g.conversation, pinned_memory: conversation.pinned_memory } } : g));
      return "";
    } catch (e) { return e.message; }
  };

  // --- conversations -------------------------------------------------------
  const startGame = async (scenarioId, opts = {}) => {
    const data = await api.createConversation({ scenario_id: scenarioId, ...opts });
    setModal(null);
    setActiveId(data.conversation.id);
    localStorage.setItem("activeConv", String(data.conversation.id));
    setGame(data);
    setLastContext(null);
    setTab(data.features?.panels?.[0] || "sheet");
    refreshConvs();
  };

  const renameConv = async (c) => {
    const title = window.prompt("Rename this game:", c.title);
    if (title && title.trim()) { await api.renameConversation(c.id, title.trim()).catch((e) => setError(e.message)); refreshConvs(); if (c.id === activeId) reloadGame(); }
  };
  const deleteConv = async (c) => {
    if (!window.confirm(`Delete "${c.title}" permanently? Its memories are deleted too.`)) return;
    await api.deleteConversation(c.id).catch((e) => setError(e.message));
    if (c.id === activeId) { setActiveId(null); setGame(null); localStorage.removeItem("activeConv"); }
    refreshConvs();
  };

  // --- sheet / NPC editing -------------------------------------------------
  const patchState = async (patch) => {
    if (!activeId) return;
    try { const state = await api.patchState(activeId, patch); setGame((g) => (g ? { ...g, state } : g)); } catch (e) { setError(e.message); }
  };
  const refreshNpcs = async () => { await reloadGame(); };
  const npcUpdate = async (id, body) => { try { await api.updateNpc(id, body); await refreshNpcs(); } catch (e) { setError(e.message); } };
  const npcDelete = async (id) => { try { await api.deleteNpc(id); await refreshNpcs(); } catch (e) { setError(e.message); } };
  const npcAdd = async (body) => { try { await api.addNpc(activeId, body); await refreshNpcs(); } catch (e) { setError(e.message); } };

  const online = health?.llm?.ok;
  const scenario = game?.conversation?.scenario;

  return (
    <div className={`app ${view.wide ? "wide" : ""} ${view.compact ? "compact" : ""}`}
      style={{ "--story-font": `${view.fontSize}px`, "--panel-w": `${view.panelWidth}px` }}>
      <Sidebar
        convs={convs} activeId={activeId} onSelect={(id) => !busy && openConversation(id)} onNew={() => setModal("new")}
        onRename={renameConv} onDelete={deleteConv} onSkills={() => setModal("skills")} onSettings={() => setModal("settings")}
        health={health} theme={theme} onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
      />
      <main className="main">
        {game ? (
          <>
            <div className="topbar">
              <div className="grow">
                <div className="top-title">{game.conversation.title}</div>
                <div className="muted small">{scenario?.name} · {MODE_LABELS[scenario?.mode] || ""}
                  {game.features?.kind && <span className={`tag kind-${game.features.kind} kind-badge`}>{KIND_LABELS[game.features.kind]}</span>}
                </div>
              </div>
              {!online && <button className="btn small danger" onClick={() => setModal("settings")}>Model offline</button>}
              <button className="icon-btn" title="Search this story (Ctrl+F)" onClick={() => setSearchOpen(!searchOpen)}>🔍</button>
              <a className="icon-btn" title="Export this story as a text file (Markdown)" href={api.exportChatUrl(game.conversation.id)} download>⤓</a>
              <div className="view-wrap">
                <button className="btn small view-btn" title="Text size, column width, scrolling" onClick={() => setViewOpen(!viewOpen)}>Aa</button>
                {viewOpen && <ViewMenu view={view} setView={setView} onClose={() => setViewOpen(false)} />}
              </div>
              <button className="btn small" onClick={undo} disabled={busy} title="Remove the last exchange">↶ Undo</button>
              <button className="btn small" onClick={() => setPanelOpen(!panelOpen)}>{panelOpen ? "Hide panel" : "Show panel"}</button>
            </div>
            <Chat game={game} stream={stream} busy={busy} error={error} lastContext={lastContext}
              onSend={send} onStop={stop} onRegenerate={regenerate} onContinue={continueReply} onDismissError={() => setError("")}
              onEdit={editMessage} onResend={resendMessage} onRewind={rewindTo} onFork={forkAt}
              follow={view.follow} searchOpen={searchOpen} onCloseSearch={() => setSearchOpen(false)} />
          </>
        ) : (
          <div className="welcome">
            <div className="welcome-dice">🎲</div>
            <h1>Local RPG</h1>
            <p className="muted">Roleplay and tabletop adventures that run entirely on your PC.<br />No tokens, no limits, and it remembers everything.</p>
            <button className="btn primary big" onClick={() => setModal("new")}>＋ Start a new game</button>
            {!online && <p className="error-text small">The model server is offline. Start LM Studio's server, then check <a href="#" onClick={(e) => { e.preventDefault(); setModal("settings"); }}>Settings</a>.</p>}
            {error && <p className="error-text small">{error}</p>}
          </div>
        )}
      </main>
      {game && panelOpen && <div className="panel-resizer" onMouseDown={startResize} title="Drag to resize the panel" />}
      {game && panelOpen && (
        <SidePanel game={game} tab={tab} onTab={setTab} onPatch={patchState} onNpcUpdate={npcUpdate} onNpcDelete={npcDelete}
          onNpcAdd={npcAdd} onRollToChat={(expr) => send(`/roll ${expr}`)} canRoll={!busy} memoryKey={memoryKey} onClose={() => setPanelOpen(false)} onPinnedSave={savePinned} />
      )}
      {modal === "new" && <ScenarioModal onClose={() => setModal(null)} onStart={startGame} />}
      {modal === "settings" && <SettingsModal onClose={() => setModal(null)} onSaved={refreshHealth} />}
      {modal === "skills" && <SkillsModal onClose={() => setModal(null)} />}
    </div>
  );
}
