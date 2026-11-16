import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, streamPost } from "./api.js";
import Sidebar from "./components/Sidebar.jsx";
import Chat from "./components/Chat.jsx";
import SidePanel from "./components/SidePanel.jsx";
import SettingsModal from "./components/SettingsModal.jsx";
import SkillsModal from "./components/SkillsModal.jsx";
import ScenarioModal from "./components/ScenarioModal.jsx";
import { MODE_LABELS } from "./utils.js";

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

  const abortRef = useRef(null);
  const activeRef = useRef(null);
  const bufferRef = useRef("");
  const rafRef = useRef(0);
  activeRef.current = activeId;

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
  const stop = () => abortRef.current?.abort();

  const undo = async () => {
    if (busy || !activeId) return;
    if (!window.confirm("Remove the last exchange (your message and the reply)? Sheet and relationships go back to how they were.")) return;
    try { setGame(await api.undo(activeId)); refreshConvs(); } catch (e) { setError(e.message); }
  };

  // --- conversations -------------------------------------------------------
  const startGame = async (scenarioId, playerName) => {
    const data = await api.createConversation({ scenario_id: scenarioId, player_name: playerName });
    setModal(null);
    setActiveId(data.conversation.id);
    localStorage.setItem("activeConv", String(data.conversation.id));
    setGame(data);
    setLastContext(null);
    setTab("sheet");
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
    <div className="app">
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
                <div className="muted small">{scenario?.name} · {MODE_LABELS[scenario?.mode] || ""}</div>
              </div>
              {!online && <button className="btn small danger" onClick={() => setModal("settings")}>Model offline</button>}
              <button className="btn small" onClick={undo} disabled={busy} title="Remove the last exchange">↶ Undo</button>
              <button className="btn small" onClick={() => setPanelOpen(!panelOpen)}>{panelOpen ? "Hide panel" : "Show panel"}</button>
            </div>
            <Chat game={game} stream={stream} busy={busy} error={error} lastContext={lastContext}
              onSend={send} onStop={stop} onRegenerate={regenerate} onDismissError={() => setError("")} />
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
      {game && panelOpen && (
        <SidePanel game={game} tab={tab} onTab={setTab} onPatch={patchState} onNpcUpdate={npcUpdate} onNpcDelete={npcDelete}
          onNpcAdd={npcAdd} onRollToChat={(expr) => send(`/roll ${expr}`)} canRoll={!busy} memoryKey={memoryKey} onClose={() => setPanelOpen(false)} />
      )}
      {modal === "new" && <ScenarioModal onClose={() => setModal(null)} onStart={startGame} />}
      {modal === "settings" && <SettingsModal onClose={() => setModal(null)} onSaved={refreshHealth} />}
      {modal === "skills" && <SkillsModal onClose={() => setModal(null)} />}
    </div>
  );
}
