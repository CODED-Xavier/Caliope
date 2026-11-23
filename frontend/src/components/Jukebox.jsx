import React, { useCallback, useEffect, useRef, useState } from "react";
import { ask } from "../dialogs.jsx";
import Modal from "./Modal.jsx";
import HelpTip from "./HelpTip.jsx";
import { api } from "../api.js";

const FADE_MS = 2000;
// When no song has the scene's mood, try these instead (in order).
const FALLBACK = {
  boss: ["combat", "epic", "tension"], combat: ["boss", "epic", "tension"], victory: ["epic", "calm"], tension: ["mystery", "horror"],
  horror: ["tension", "mystery"], mystery: ["tension", "calm"], tavern: ["town", "calm"], town: ["tavern", "calm"],
  forest: ["exploration", "calm"], dungeon: ["tension", "mystery", "exploration"], exploration: ["forest", "calm"],
  sad: ["calm", "romantic"], romantic: ["calm", "sad"], epic: ["combat", "exploration"], calm: ["exploration", "tavern"],
  academy: ["calm", "town"], festival: ["tavern", "town", "romantic"], night: ["calm", "mystery"], training: ["epic", "combat"],
};

function loadPrefs() {
  try { return { auto: true, volume: 0.5, ...JSON.parse(localStorage.getItem("jukebox") || "{}") }; } catch { return { auto: true, volume: 0.5 }; }
}

/** Songs this card may use: its own songs first; songs without a card are for every card. */
export function pickTrack(tracks, mood, cardId, avoidId) {
  const usable = tracks.filter((t) => !t.cards.length || t.cards.includes(cardId));
  for (const m of [mood, ...(FALLBACK[mood] || [])]) {
    const own = usable.filter((t) => t.tags.includes(m) && t.cards.includes(cardId));
    const pool = own.length ? own : usable.filter((t) => t.tags.includes(m));
    const choices = pool.length > 1 ? pool.filter((t) => t.id !== avoidId) : pool;
    if (choices.length) return choices[Math.floor(Math.random() * choices.length)];
  }
  return null;
}

/** The small player in the top bar. Auto mode follows the scene's mood (fights always play combat music). */
export function JukeboxPlayer({ game, tracks, onOpenLibrary }) {
  const [prefs, setPrefs] = useState(loadPrefs);
  const [current, setCurrent] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const a = useRef(null), b = useRef(null);
  const active = useRef("a");
  const fadeTimer = useRef(null);
  const lastMood = useRef("");
  const wasFighting = useRef(false);
  const victoryUntilEnd = useRef(false);

  const savePrefs = (p) => { setPrefs(p); try { localStorage.setItem("jukebox", JSON.stringify(p)); } catch { /* private mode */ } };
  const el = () => (active.current === "a" ? a.current : b.current);
  const other = () => (active.current === "a" ? b.current : a.current);

  const cardId = game?.conversation?.scenario_id;
  const combat = game?.state?.combat;
  const fighting = !!combat?.active;
  const won = combat && !combat.active && combat.combatants?.filter((c) => c.side === "enemy").every((c) => c.hp <= 0);
  let mood = fighting ? "combat" : (!prefs.auto && prefs.mood) || game?.state?.scene_mood || "calm";
  if (fighting && combat.combatants?.some((c) => c.side === "enemy" && /boss|dragon|lord|queen|king|demon/i.test(c.name))) mood = "boss";

  const play = useCallback((track) => {
    if (!track) return;
    const next = other(), prev = el();
    clearInterval(fadeTimer.current);
    next.src = track.url;
    next.volume = 0;
    next.play().then(() => {
      setBlocked(false);
      setPlaying(true);
      active.current = active.current === "a" ? "b" : "a";
      setCurrent(track);
      const start = Date.now();
      const target = prefs.volume;
      const from = prev && !prev.paused ? prev.volume : 0;
      fadeTimer.current = setInterval(() => { // crossfade
        const k = Math.min(1, (Date.now() - start) / FADE_MS);
        next.volume = target * k;
        if (prev && !prev.paused) prev.volume = from * (1 - k);
        if (k >= 1) { clearInterval(fadeTimer.current); if (prev) { prev.pause(); prev.removeAttribute("src"); } }
      }, 60);
    }).catch(() => { setBlocked(true); setCurrent(track); }); // the browser waits for a first click before playing sound
  }, [prefs.volume]); // eslint-disable-line

  // Auto mode: change song when the mood changes (a won fight plays a victory song once).
  useEffect(() => {
    if (!prefs.auto || !tracks.length || !game || (prefs.loop && current && playing)) return; // a looped song stays
    let want = mood;
    if (wasFighting.current && !fighting && won) { want = "victory"; victoryUntilEnd.current = true; }
    wasFighting.current = fighting;
    if (want === lastMood.current) return;
    lastMood.current = want;
    const t = pickTrack(tracks, want, cardId, current?.id);
    if (t && (!current || !current.tags.includes(want))) play(t);
  }, [mood, fighting, won, prefs.auto, tracks, cardId]); // eslint-disable-line

  useEffect(() => { lastMood.current = ""; }, [game?.conversation?.id]);
  useEffect(() => { const e = el(); if (e && !fadeTimer.current) e.volume = prefs.volume; else if (e) e.volume = prefs.volume; }, [prefs.volume]); // eslint-disable-line

  const ended = () => { // next song of the same mood (or back to the scene after the victory song)
    if (prefs.loop && current) { const e = el(); e.currentTime = 0; e.play().catch(() => setBlocked(true)); return; }
    const want = victoryUntilEnd.current ? mood : (prefs.auto ? mood : current?.tags[0]);
    victoryUntilEnd.current = false;
    lastMood.current = want;
    play(pickTrack(tracks, want, cardId, current?.id) || current);
  };
  const toggle = () => {
    const e = el();
    if (blocked && current) { play(current); return; }
    if (!current) { play(pickTrack(tracks, mood, cardId)); return; }
    if (e.paused) { e.play().then(() => setPlaying(true)).catch(() => setBlocked(true)); } else { e.pause(); setPlaying(false); }
  };
  const skip = () => play(pickTrack(tracks, prefs.auto ? mood : current?.tags[0] || mood, cardId, current?.id));

  if (!tracks.length) {
    return <button className="btn small" title="Background music: add songs and tag them with moods" onClick={onOpenLibrary}>🎵 Music</button>;
  }
  return (
    <div className="jukebox">
      <audio ref={a} onEnded={ended} preload="auto" />
      <audio ref={b} onEnded={ended} preload="auto" />
      <button className="icon-btn" title={playing ? "Pause" : blocked ? "Click to start the music" : "Play"} onClick={toggle}>{playing ? "⏸" : "▶"}</button>
      <button className="icon-btn" title="Next song" onClick={skip}>⏭</button>
      <button className={`icon-btn ${prefs.loop ? "on" : ""}`} title={prefs.loop ? "Looping this song (click to stop)" : "Loop this song"}
        onClick={() => savePrefs({ ...prefs, loop: !prefs.loop })}>🔁</button>
      <button className="jb-title" title={current ? `${current.name} · ${current.tags.join(", ")}` : "Music library"} onClick={onOpenLibrary}>
        {blocked ? "Click ▶ for music" : current ? current.name : "🎵 Music"}
        {prefs.auto && <span className="jb-mood"> · {mood}</span>}
      </button>
      <input type="range" min="0" max="1" step="0.05" value={prefs.volume} title="Volume" onChange={(e) => savePrefs({ ...prefs, volume: parseFloat(e.target.value) })} />
      <label className="jb-auto" title="Auto: the music follows the mood of the scene"><input type="checkbox" checked={prefs.auto} onChange={(e) => savePrefs({ ...prefs, auto: e.target.checked })} />Auto</label>
      {!prefs.auto && (
        <select className="field jb-pick" title="Play this mood" value={prefs.mood || ""} onChange={(e) => {
          const m = e.target.value; savePrefs({ ...prefs, mood: m });
          if (m) play(pickTrack(tracks, m, cardId, current?.id));
        }}>
          <option value="">Mood…</option>
          {[...new Set(tracks.flatMap((t) => t.tags))].sort().map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- library */
export function JukeboxModal({ onClose, onChanged }) {
  const [tracks, setTracks] = useState([]);
  const [moods, setMoods] = useState([]);
  const [cards, setCards] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState({ url: "", name: "" });
  const [newTags, setNewTags] = useState([]);
  const [filter, setFilter] = useState("");
  const [preview, setPreview] = useState(null);
  const [search, setSearch] = useState("");
  const [picked, setPicked] = useState({}); // songs ticked for tagging many at once
  const [note, setNote] = useState("");
  const fileRef = useRef(null);
  const audio = useRef(null);

  const load = async () => {
    try { const r = await api.music(); setTracks(r.tracks); setMoods(r.moods); onChanged?.(r.tracks); } catch (e) { setError(e.message); }
  };
  useEffect(() => { load(); api.scenarios().then(setCards).catch(() => {}); }, []); // eslint-disable-line
  useEffect(() => () => audio.current?.pause(), []);

  const upload = async (files) => {
    if (!files?.length) return;
    setBusy(true); setError("");
    try {
      for (const f of files) await api.uploadMusic(f, f.name.replace(/\.[^.]+$/, ""), newTags);
      await load();
    } catch (e) { setError(e.message); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  };
  const addLink = async () => {
    setError("");
    try { await api.addMusicLink({ ...link, tags: newTags }); setLink({ url: "", name: "" }); load(); } catch (e) { setError(e.message); }
  };
  const update = async (t, patch) => {
    try { await api.updateMusic(t.id, patch); load(); } catch (e) { setError(e.message); }
  };
  const listen = (t) => {
    if (preview === t.id) { audio.current.pause(); setPreview(null); return; }
    audio.current.src = t.url; audio.current.volume = 0.6;
    audio.current.play().then(() => setPreview(t.id)).catch((e) => setError(`Cannot play this song: ${e.message}`));
  };
  const toggleTag = (list, m) => (list.includes(m) ? list.filter((x) => x !== m) : [...list, m]);
  const shown = tracks.filter((t) => (filter === "untagged" ? !t.tags.length : !filter || t.tags.includes(filter))
    && (!search.trim() || t.name.toLowerCase().includes(search.trim().toLowerCase())));
  const pickedIds = Object.keys(picked).filter((k) => picked[k]).map(Number);
  const bulk = async (patch) => {
    try { const r = await api.bulkMusic({ ids: pickedIds, ...patch }); setTracks(r.tracks); onChanged?.(r.tracks); } catch (e) { setError(e.message); }
  };
  const autotag = async () => {
    try { const r = await api.autotagMusic(); setTracks(r.tracks); onChanged?.(r.tracks); setNote(r.tagged ? `Tagged ${r.tagged} songs by their names.` : "No untagged song has a name that says its mood."); }
    catch (e) { setError(e.message); }
  };
  const untagged = tracks.filter((t) => !t.tags.length).length;

  return (
    <Modal title="Jukebox" onClose={onClose} wide>
      <audio ref={audio} onEnded={() => setPreview(null)} />
      <p className="muted small">Add songs and tag them with moods. With <strong>Auto</strong> on, the player in the top bar follows the
        mood of each scene, plays combat music during fights and a victory song when you win. <HelpTip id="jukebox" /></p>

      <div className="card">
        <div className="small">Moods for the songs you add now <span className="muted tiny">(none picked: the song's name chooses, e.g. "Tavern Jig" → tavern)</span>:</div>
        <div className="conds">
          {moods.map((m) => <button key={m} className={`chip ${newTags.includes(m) ? "on" : ""}`} onClick={() => setNewTags(toggleTag(newTags, m))}>{m}</button>)}
        </div>
        <div className="row gap center wrap">
          <button className="btn primary" disabled={busy} onClick={() => fileRef.current?.click()}>{busy ? "Adding…" : "⇪ Add songs from this PC"}</button>
          <input ref={fileRef} type="file" hidden multiple accept="audio/*,.mp3,.ogg,.wav,.flac,.m4a,.webm" onChange={(e) => upload([...e.target.files])} />
          <span className="muted tiny">MP3, OGG, WAV, FLAC, M4A · up to 40 MB each</span>
        </div>
        <div className="row gap center">
          <input className="field grow" placeholder="…or a direct audio link (https://…/song.mp3)" value={link.url} onChange={(e) => setLink({ ...link, url: e.target.value })} />
          <input className="field" style={{ width: 150 }} placeholder="Name" value={link.name} onChange={(e) => setLink({ ...link, name: e.target.value })} />
          <button className="btn" disabled={!link.url.trim()} onClick={addLink}>Add link</button>
        </div>
        <div className="muted tiny">YouTube and Spotify pages can't be played. Free music for games: search for "royalty free fantasy music" (for example Kevin MacLeod / incompetech, Tabletop Audio, Pixabay Music).</div>
      </div>
      {error && <div className="error-text small">{error}</div>}

      <div className="row gap center wrap">
        <div className="section-title grow">Your songs ({tracks.length})</div>
        <input className="field" style={{ width: 180 }} placeholder="Search songs…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="field" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All moods</option>
          <option value="untagged">{`Untagged (${untagged})`}</option>
          {moods.map((m) => <option key={m} value={m}>{m} ({tracks.filter((t) => t.tags.includes(m)).length})</option>)}
        </select>
        {untagged > 0 && <button className="btn small" onClick={autotag} title="Give untagged songs the moods their names suggest">✨ Tag by name</button>}
      </div>
      {note && <div className="muted small">{note}</div>}
      <div className="mood-cloud">
        {moods.map((m) => { const n = tracks.filter((t) => t.tags.includes(m)).length; return (
          <button key={m} className={`chip ${filter === m ? "on" : ""} ${n ? "" : "empty"}`} title={n ? `${n} songs` : "No song has this mood yet"}
            onClick={() => setFilter(filter === m ? "" : m)}>{m} <span className="tiny">{n}</span></button>); })}
      </div>
      {pickedIds.length > 0 && (
        <div className="card bulk-bar">
          <div className="row gap center"><strong className="small grow">{`${pickedIds.length} songs ticked`}</strong>
            <button className="btn small ghost" onClick={() => setPicked({})}>Clear</button></div>
          <div className="small muted">Click a mood to add it to all of them; right-click to take it away.</div>
          <div className="conds">
            {moods.map((m) => <button key={m} className="chip" onClick={() => bulk({ add: [m] })} onContextMenu={(e) => { e.preventDefault(); bulk({ remove: [m] }); }}>{m}</button>)}
          </div>
        </div>
      )}
      {shown.length === 0 && <div className="muted small">No songs yet.</div>}
      {shown.map((t) => (
        <div className="card track" key={t.id}>
          <div className="row gap center">
            <input type="checkbox" title="Tick to tag many songs at once" checked={!!picked[t.id]} onChange={(e) => setPicked((x) => ({ ...x, [t.id]: e.target.checked }))} />
            <button className="icon-btn" title={preview === t.id ? "Stop" : "Listen"} onClick={() => listen(t)}>{preview === t.id ? "⏹" : "▶"}</button>
            <input className="field grow" defaultValue={t.name} onBlur={(e) => e.target.value.trim() && e.target.value !== t.name && update(t, { name: e.target.value })} />
            <span className="muted tiny">{t.source === "link" ? "link" : "file"}</span>
            <button className="icon-btn" title="Delete" onClick={async () => { if (await ask.confirm(`Delete "${t.name}"?`)) { await api.deleteMusic(t.id).catch((e) => setError(e.message)); load(); } }}>🗑</button>
          </div>
          {(t.suggested || []).length > 0 && (
            <div className="row gap center small"><span className="muted tiny">Its name suggests:</span>
              {t.suggested.map((m) => <button key={m} className="chip suggested" title="Add this mood" onClick={() => update(t, { tags: [...t.tags, m] })}>＋ {m}</button>)}
            </div>
          )}
          <div className="conds">
            {moods.map((m) => <button key={m} className={`chip ${t.tags.includes(m) ? "on" : ""}`} onClick={() => update(t, { tags: toggleTag(t.tags, m) })}>{m}</button>)}
          </div>
          <div className="row gap center">
            <span className="tiny muted">Only for cards:</span>
            <select className="field" value="" onChange={(e) => e.target.value && update(t, { cards: [...t.cards, parseInt(e.target.value, 10)] })}>
              <option value="">{t.cards.length ? "＋ another card" : "every card (choose to limit)"}</option>
              {cards.filter((c) => !t.cards.includes(c.id)).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            {t.cards.map((id) => (
              <span key={id} className="chip on" onClick={() => update(t, { cards: t.cards.filter((x) => x !== id) })} title="Click to remove">
                {(cards.find((c) => c.id === id) || {}).name || `card ${id}`} ✕
              </span>
            ))}
          </div>
        </div>
      ))}
    </Modal>
  );
}
