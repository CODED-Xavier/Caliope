import React, { useEffect, useMemo, useRef, useState } from "react";
import { ask } from "../dialogs.jsx";
import { api } from "../api.js";
import { NumberField, TextField } from "./Fields.jsx";
import HelpTip from "./HelpTip.jsx";
import MoodEditor from "./MoodEditor.jsx";
import CombatTab from "./CombatTab.jsx";
import { abilityMod, clamp, fmtMod, relationshipColor, relationshipEffect, relationshipLabel } from "../utils.js";
import { latestStatus, portraitSrc } from "../portraits.js";
import SheetPicker from "./SheetPicker.jsx";
import { GridOverlay } from "./AdventureEditor.jsx";
import PlayerLore from "./PlayerLore.jsx";
import { CalendarBox } from "./Calendar.jsx";
import { CantosBox, MapBag } from "./Cantos.jsx";

/* ----------------------------------------------------------------- Status */
function GameSheet({ convId, current, onReload, onDone }) {
  const [text, setText] = useState(current || "");
  const [error, setError] = useState("");
  const save = async (value) => {
    try { await api.setSheetTemplate(convId, value); setError(""); await onReload?.(); onDone?.(); } catch (e) { setError(e.message); }
  };
  return (
    <div className="status-edit">
      <div className="small">Choose a sheet for this game. The card itself is not changed.</div>
      <SheetPicker value={text} onChange={setText} compact />
      <div className="row gap">
        <button className="btn small primary" onClick={() => save(text)}>Use this sheet</button>
        {current && <button className="btn small" onClick={() => save("")}>Remove the sheet</button>}
        {onDone && <button className="btn small" onClick={onDone}>Cancel</button>}
      </div>
      {error && <div className="error-text small">{error}</div>}
    </div>
  );
}

function StatusTab({ messages, every, byApp, fields, values, onPatch, sheetOwn, picked, convId, onReload, now }) {
  const status = latestStatus(messages) || (byApp && now ? { text: now, messageId: null } : null);  // before the first reply: the sheet as it stands
  const [editing, setEditing] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const [draft, setDraft] = useState({});
  if (choosing || (!status && !byApp && !every)) {
    return <div className="tab-body"><GameSheet convId={convId} current={picked} onReload={onReload} onDone={status || byApp ? () => setChoosing(false) : null} /></div>;
  }
  if (!status) {
    return (
      <div className="tab-body">
        <div className="muted small">{byApp ? "The status appears after the first reply." : `No status yet. This card's AI writes a status block ${every ? `every ${every} replies` : "now and then"}, and it shows up here instead of in the story.`}</div>
      </div>
    );
  }
  const lines = status.text.split("\n").map((l) => l.replace(/\*\*/g, "").trim()).filter((l) => l && !/^\[?INFO\]?$/i.test(l));
  const save = async () => { await onPatch({ card_status: { ...(values || {}), ...draft } }); setEditing(false); };
  return (
    <div className="tab-body status-tab">
      {lines.map((line, i) => {
        const cells = line.split(/\s+\|\s+/);
        return (
          <div className="status-line" key={i}>
            {cells.map((c, j) => {
              const k = c.indexOf(":");
              return k > 0 && k < 40
                ? <span className="status-cell" key={j}><span className="status-key">{c.slice(0, k)}</span>{c.slice(k + 1)}</span>
                : <span className="status-cell" key={j}>{c}</span>;
            })}
          </div>
        );
      })}
      {byApp ? (
        <>
          <div className="muted tiny">Kept by the app: place, time, items and relationships come from the game; the card's own values change when the story changes them (the tracker reports it). Correct them here if needed.</div>
          <div className="row gap">
            {fields?.length > 0 && !editing && <button className="btn small" onClick={() => { setDraft({}); setEditing(true); }}>✎ Edit the values</button>}
            {!sheetOwn && !editing && <button className="btn small" onClick={() => setChoosing(true)}>🗂 Change the sheet</button>}
          </div>
          {editing && (
            <div className="status-edit">
              {fields.map((f) => (
                <label key={f} className="lbl">{f}
                  <input className="field" defaultValue={(values || {})[f] || ""} onChange={(e) => setDraft((d) => ({ ...d, [f]: e.target.value }))} />
                </label>
              ))}
              <div className="row gap"><button className="btn small primary" onClick={save}>Save</button><button className="btn small" onClick={() => setEditing(false)}>Cancel</button></div>
            </div>
          )}
        </>
      ) : <div className="muted tiny">Written by the AI{every ? ` every ${every} replies` : ""}. The app's own relationship meters are in the People tab.</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ Sheet */
/** Mana, Aura...: bars kept by the app, the powers that spend them, and rests that refill them. */
function ResourcesBox({ state, onPatch, onPower, onRest, busy, convId, onState }) {
  const pools = state.resources || {};
  const names = Object.keys(pools);
  const [err, setErr] = useState("");
  const sync = async () => { setErr(""); try { onState(await api.syncResources(convId)); } catch (e) { setErr(e.message); } };
  if (!names.length) {
    return (
      <div className="muted tiny">
        <button className="link-btn tiny" onClick={sync}>↻ Get resources and powers from the card</button> (Mana, Aura… set in the card editor)
        {err && <div className="error-text small">{err}</div>}
      </div>
    );
  }
  const inFight = !!state.combat?.active;
  return (
    <>
      <div className="section-title">Resources <HelpTip id="resources" /></div>
      {names.map((n) => {
        const p = pools[n];
        return (
          <div className="res-row" key={n}>
            <span className="res-name">{n}</span>
            <div className="res-bar"><div className="res-fill" style={{ width: `${(p.current / Math.max(1, p.max)) * 100}%`, background: p.color || undefined }} /></div>
            <button className="icon-btn" onClick={() => onPatch({ resources: { [n]: { current: Math.max(0, p.current - 1) } } })}>−</button>
            <span className="res-num">{p.current}/{p.max}</span>
            <button className="icon-btn" onClick={() => onPatch({ resources: { [n]: { current: Math.min(p.max, p.current + 1) } } })}>＋</button>
          </div>
        );
      })}
      {(state.abilities || []).length > 0 && (
        <>
          <div className="section-title">Powers</div>
          {state.abilities.map((a) => {
            const short = Object.entries(a.costs || {}).find(([k, v]) => (pools[k]?.current ?? 0) < v);
            return (
              <div className="ability-card" key={a.id}>
                <div className="grow small">
                  <strong>{a.name}</strong> <span className="muted tiny">· {Object.entries(a.costs || {}).map(([k, v]) => `${v} ${k}`).join(", ") || "free"}{a.dice ? ` · ${a.dice}` : ""}</span>
                  {a.description && <div className="muted tiny">{a.description}</div>}
                </div>
                <button className="btn small" disabled={busy || inFight || !!short} onClick={() => onPower(a.id)}
                  title={inFight ? "In a fight, use it from the Combat tab" : short ? `Not enough ${short[0]}` : "Use it now: the app pays the cost and tells the Aedo"}>Use</button>
              </div>
            );
          })}
        </>
      )}
      <div className="row gap">
        <button className="btn small grow" disabled={busy || inFight} onClick={() => onRest("short")} title="About an hour of rest">☕ Short rest</button>
        <button className="btn small grow" disabled={busy || inFight} onClick={() => onRest("long")} title="A night's sleep: refills more and heals">🛌 Long rest</button>
      </div>
      <button className="link-btn tiny" disabled={busy} onClick={sync} title="After editing the card's resources or powers">↻ Update from the card</button>
      {err && <div className="error-text small">{err}</div>}
    </>
  );
}

function SheetTab({ state, onPatch, mode, kind, onPower, onRest, busy, convId, onState }) {
  const p = state.player;
  const [picOpen, setPicOpen] = useState(false);
  const numbers = kind !== "roleplay";
  const hp = p.hp;
  const pct = clamp((hp.current / Math.max(1, hp.max)) * 100, 0, 100);
  return (
    <div className="tab-body">
      <div className="row gap center">
        <button type="button" className="player-pic" title="Your picture (shown beside your messages)" onClick={() => setPicOpen(!picOpen)}>
          {p.portraits?.default ? <img src={portraitSrc(p.portraits.default)} alt="" /> : <span>＋</span>}
        </button>
        <div className="grow"><TextField className="title-input" value={p.name} onCommit={(v) => onPatch({ player: { name: v } })} /></div>
      </div>
      {picOpen && <MoodEditor portraits={p.portraits} mainOnly onChange={(v) => onPatch({ player: { portraits: v } })} />}
      <div className="row gap">
        <TextField value={p.race} placeholder="Race" onCommit={(v) => onPatch({ player: { race: v } })} />
        <TextField value={p.class} placeholder="Class" onCommit={(v) => onPatch({ player: { class: v } })} />
      </div>
      {numbers && <div className="stat-row">
        <label>Level <NumberField value={p.level} min={1} max={30} width={56} onCommit={(v) => onPatch({ player: { level: v } })} /></label>
        <label>AC <NumberField value={p.ac} min={0} max={40} width={56} onCommit={(v) => onPatch({ player: { ac: v } })} /></label>
        <label>Gold <NumberField value={state.gold} min={0} width={80} onCommit={(v) => onPatch({ gold: v })} /></label>
      </div>}

      {numbers && <><div className="section-title">Hit points</div>
      <div className="hpbar"><div className="hpfill" style={{ width: `${pct}%`, background: pct < 30 ? "var(--bad)" : pct < 60 ? "var(--warn)" : "var(--good)" }} /></div>
      <div className="row gap center">
        <button className="btn small" onClick={() => onPatch({ player: { hp: { current: Math.max(0, hp.current - 1) } } })}>−1</button>
        <NumberField value={hp.current} min={0} max={hp.max} width={56} onCommit={(v) => onPatch({ player: { hp: { current: v } } })} />
        <span className="muted">/</span>
        <NumberField value={hp.max} min={1} width={56} onCommit={(v) => onPatch({ player: { hp: { max: v } } })} />
        <button className="btn small" onClick={() => onPatch({ player: { hp: { current: Math.min(hp.max, hp.current + 1) } } })}>+1</button>
      </div>

      <div className="section-title">Abilities</div>
      <div className="stats-grid">
        {Object.entries(p.stats || {}).map(([k, v]) => (
          <div className="stat" key={k}>
            <div className="stat-name">{k}</div>
            <div className="stat-mod">{fmtMod(abilityMod(v))}</div>
            <NumberField value={v} min={1} max={30} width={46} onCommit={(n) => onPatch({ player: { stats: { [k]: n } } })} />
          </div>
        ))}
      </div></>}

      <ResourcesBox state={state} onPatch={onPatch} onPower={onPower} onRest={onRest} busy={busy} convId={convId} onState={onState} />

      <div className="section-title">Scene</div>
      <label className="lbl">Location</label>
      <TextField value={state.location} placeholder="Where are you?" onCommit={(v) => onPatch({ location: v })} />
      <div className="row gap">
        <div className="grow"><label className="lbl">Time</label>
          <TextField value={state.time} placeholder="Time of day" onCommit={(v) => onPatch({ time: v })} /></div>
        <div className="grow"><label className="lbl">Weather</label>
          <TextField value={state.weather || ""} placeholder="Weather" onCommit={(v) => onPatch({ weather: v })} /></div>
      </div>
      {p.background !== undefined && <><label className="lbl">Background</label>
      <TextField multiline rows={2} value={p.background} placeholder="Where you come from" onCommit={(v) => onPatch({ player: { background: v } })} /></>}
      <label className="lbl">Personality</label>
      <TextField value={p.traits || ""} placeholder="Personality" onCommit={(v) => onPatch({ player: { traits: v } })} />
      <label className="lbl">Appearance</label>
      <TextField multiline rows={3} value={p.description} placeholder="Describe your character…" onCommit={(v) => onPatch({ player: { description: v } })} />
      <label className="lbl">✨ Wishes for the story <HelpTip id="wishes" /></label>
      <TextField multiline rows={3} value={state.wishes || ""} placeholder="e.g. Kaida and I could go from rivals to lovers. I'd like a duel with Artemis someday."
        onCommit={(v) => onPatch({ wishes: v })} />
      <label className="lbl">Your notes</label>
      <TextField multiline rows={3} value={state.notes} placeholder="Private notes (the AI does not see these)" onCommit={(v) => onPatch({ notes: v })} />
      {!numbers && <div className="muted small">Roleplay cards focus on characters and relationships, so the numbers (HP, abilities, gold) are hidden. Switch the card type to Adventure to use them.</div>}
    </div>
  );
}

/* -------------------------------------------------------------------- Bag */
function PayBox({ gold, currency, onPay, busy }) {
  const [amount, setAmount] = useState("");
  const [to, setTo] = useState("");
  const [why, setWhy] = useState("");
  const n = parseInt(amount, 10) || 0;
  return (
    <form className="pay-box" onSubmit={(e) => { e.preventDefault(); if (n > 0 && n <= gold) { onPay({ amount: n, to, why }); setAmount(""); setTo(""); setWhy(""); } }}>
      <div className="section-title">💰 {gold} {currency}</div>
      <div className="row gap">
        <input className="field num" style={{ width: 64 }} placeholder="0" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <input className="field grow" placeholder="to whom" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      <div className="row gap">
        <input className="field grow" placeholder="for what (optional)" value={why} onChange={(e) => setWhy(e.target.value)} />
        <button className="btn small" type="submit" disabled={busy || n <= 0 || n > gold} title="The app takes the money and tells the Aedo">Pay</button>
      </div>
    </form>
  );
}

function BagTab({ state, onPatch, onPay, busy, currency }) {
  const [name, setName] = useState("");
  const [qty, setQty] = useState(1);
  const [quest, setQuest] = useState("");
  const inv = state.inventory;
  const setInv = (next) => onPatch({ inventory: next });
  return (
    <div className="tab-body">
      {onPay && <PayBox gold={state.gold} currency={currency} onPay={onPay} busy={busy} />}
      <div className="section-title">Inventory ({inv.length})</div>
      {inv.length === 0 && <div className="muted small">Your bag is empty.</div>}
      {inv.map((it, i) => (
        <div className="item-row" key={`${it.name}-${i}`}>
          <div className="grow">{it.name}{it.notes && <div className="muted small">{it.notes}</div>}</div>
          <button className="icon-btn" onClick={() => setInv(inv.map((x, j) => (j === i ? { ...x, qty: Math.max(1, x.qty - 1) } : x)))}>−</button>
          <span className="qty">×{it.qty}</span>
          <button className="icon-btn" onClick={() => setInv(inv.map((x, j) => (j === i ? { ...x, qty: x.qty + 1 } : x)))}>＋</button>
          <button className="icon-btn" title="Remove" onClick={() => setInv(inv.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <form className="row gap" onSubmit={(e) => { e.preventDefault(); if (!name.trim()) return; setInv([...inv, { name: name.trim(), qty: Math.max(1, qty), notes: "" }]); setName(""); setQty(1); }}>
        <input className="field grow" placeholder="Add item…" value={name} onChange={(e) => setName(e.target.value)} />
        <input className="field num" style={{ width: 52 }} value={qty} onChange={(e) => setQty(parseInt(e.target.value, 10) || 1)} />
        <button className="btn small" type="submit">Add</button>
      </form>

      <div className="section-title">Quests</div>
      {state.quests.length === 0 && <div className="muted small">No quests yet.</div>}
      {state.quests.map((q) => (
        <div className="quest" key={q.id}>
          <div className="row gap center">
            <div className="grow quest-title">{q.title}</div>
            <select className="field" value={q.status} onChange={(e) => onPatch({ quests: state.quests.map((x) => (x.id === q.id ? { ...x, status: e.target.value } : x)) })}>
              <option value="active">active</option>
              <option value="completed">completed</option>
              <option value="failed">failed</option>
            </select>
            <button className="icon-btn" onClick={() => onPatch({ quests: state.quests.filter((x) => x.id !== q.id) })}>✕</button>
          </div>
          {q.notes && <div className="muted small">{q.notes}</div>}
          {q.suggested && q.status === "active" && (
            <div className="quest-suggest small">
              Looks {q.suggested}.{" "}
              <button className="btn small" onClick={() => onPatch({ quests: state.quests.map((x) => (x.id === q.id ? { ...x, status: q.suggested, suggested: "" } : x)) })}>✓ Confirm</button>{" "}
              <button className="btn small ghost" onClick={() => onPatch({ quests: state.quests.map((x) => (x.id === q.id ? { ...x, suggested: "" } : x)) })}>Not yet</button>
            </div>
          )}
        </div>
      ))}
      <form className="row gap" onSubmit={(e) => { e.preventDefault(); if (!quest.trim()) return; onPatch({ quests: [...state.quests, { id: Math.random().toString(16).slice(2, 10), title: quest.trim(), status: "active", notes: "" }] }); setQuest(""); }}>
        <input className="field grow" placeholder="Add quest…" value={quest} onChange={(e) => setQuest(e.target.value)} />
        <button className="btn small" type="submit">Add</button>
      </form>
    </div>
  );
}

/* ----------------------------------------------------------------- People */
function RelSlider({ value, onCommit }) {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);
  const commit = () => { if (v !== value) onCommit(v); };
  return (
    <input type="range" min={-100} max={100} value={v} className="rel-slider"
      onChange={(e) => setV(parseInt(e.target.value, 10))}
      onMouseUp={commit} onTouchEnd={commit} onKeyUp={commit} onBlur={commit} />
  );
}

function RelBar({ value }) {
  const w = Math.abs(value) / 2; // percent of full width, each side is 50%
  return (
    <div className="relbar">
      <div className="relmid" />
      <div className="relfill" style={{ background: relationshipColor(value), width: `${w}%`, left: value >= 0 ? "50%" : `${50 - w}%` }} />
    </div>
  );
}

const LOOKS = [["race", "Race / species"], ["hair", "Hair"], ["eyes", "Eyes"], ["build", "Build"], ["skin", "Skin"], ["outfit", "Style / outfit"], ["extra", "Other details"]];
const looksSummary = (app) => ["race", "hair", "eyes"].map((k) => (app || {})[k]).filter(Boolean).join(" · ");

function NpcCard({ npc, onUpdate, onDelete, log = [] }) {
  const [open, setOpen] = useState(false);
  const pics = npc.portraits || { default: "", moods: [] };
  const thumb = pics.moods?.[0]?.url || pics.default;
  return (
    <div className={`npc ${npc.is_main ? "main" : ""} ${npc.active ? "" : "inactive"}`}>
      <div className="row gap center" onClick={() => setOpen(!open)} style={{ cursor: "pointer" }}>
        {thumb && <img className="npc-thumb" src={portraitSrc(thumb)} alt="" loading="lazy" onError={(e) => { e.currentTarget.style.display = "none"; }} />}
        <div className="grow">
          <div className="npc-name">{npc.name}{npc.is_main && <span className="tag">main</span>}</div>
          <div className="small" style={{ color: relationshipColor(npc.relationship) }} title={relationshipEffect(npc.relationship)}>
            {relationshipLabel(npc.relationship)} ({npc.relationship > 0 ? "+" : ""}{npc.relationship})
          </div>
          {looksSummary(npc.appearance) && <div className="muted tiny">{looksSummary(npc.appearance)}</div>}
        </div>
        <span className="muted">{open ? "▾" : "▸"}</span>
      </div>
      <RelBar value={npc.relationship} />
      <RelSlider value={npc.relationship} onCommit={(v) => onUpdate(npc.id, { relationship: v })} />
      <div className="relscale muted small"><span>enemy −100</span><span>0</span><span>+100 bond</span></div>
      {!open && (npc.notes || "").trim() && (
        <ul className="npc-notes">
          {npc.notes.split("\n").filter((x) => x.trim()).slice(-4).map((x, i) => (
            <li key={i} className={x.startsWith("\u2712") ? "aedo" : ""} title={x.startsWith("\u2712") ? "Noted by the Aedo" : "Your note"}>{x.replace(/^\u2712\s*/, "")}</li>
          ))}
        </ul>
      )}
      {open && (
        <div className="npc-detail">
          <div className="small rel-effect">{relationshipEffect(npc.relationship)}</div>
          {log.length > 0 && (
            <ul className="rep-log tiny">
              {log.slice(-5).reverse().map((e, i) => (
                <li key={i}><b className={e.delta > 0 ? "good" : "bad"}>{e.delta > 0 ? `+${e.delta}` : e.delta}</b> {e.reason}</li>
              ))}
            </ul>
          )}
          <label className="lbl">Description</label>
          <TextField multiline value={npc.description} onCommit={(v) => onUpdate(npc.id, { description: v })} />
          <label className="lbl">Looks <HelpTip id="appearance" /></label>
          <div className="looks-grid">
            {LOOKS.map(([key, label]) => (
              <TextField key={key} value={(npc.appearance || {})[key] || ""} placeholder={label}
                onCommit={(v) => onUpdate(npc.id, { appearance: { ...(npc.appearance || {}), [key]: v } })} />
            ))}
          </div>
          <label className="lbl">Personality</label>
          <TextField multiline value={npc.personality} onCommit={(v) => onUpdate(npc.id, { personality: v })} />
          <label className="lbl">Speech style</label>
          <TextField value={npc.speech_style} onCommit={(v) => onUpdate(npc.id, { speech_style: v })} />
          <label className="lbl">Pictures and moods <HelpTip id="portraits" /></label>
          <MoodEditor portraits={pics} compact onChange={(v) => onUpdate(npc.id, { portraits: v })} />
          <label className="check small"><input type="checkbox" checked={npc.in_prompt !== false} onChange={(e) => onUpdate(npc.id, { in_prompt: e.target.checked })} />
            Profile always in the prompt <HelpTip id="in_prompt" /></label>
          <label className="check small"><input type="checkbox" checked={npc.met !== false} onChange={(e) => onUpdate(npc.id, { met: e.target.checked })} />
            Already met</label>
          <label className="lbl">Notes: yours, and the Aedo's (✒) <HelpTip id="npc_notes" /></label>
          <TextField multiline rows={4} value={npc.notes} placeholder="What you think of them, a promise, a debt… one per line" onCommit={(v) => onUpdate(npc.id, { notes: v })} />
          <div className="row gap">
            <button className="btn small" onClick={() => onUpdate(npc.id, { active: !npc.active })}>{npc.active ? "Hide from scene" : "Bring back"}</button>
            <button className="btn small danger" onClick={async () => { if (await ask.confirm(`Delete ${npc.name}?`)) onDelete(npc.id); }}>Delete</button>
          </div>
        </div>
      )}
    </div>
  );
}

function PeopleTab({ npcs, onUpdate, onDelete, onAdd, repLog = [] }) {
  const logOf = (n) => repLog.filter((e) => (e.npc || "").toLowerCase() === n.name.toLowerCase());
  const [name, setName] = useState("");
  const met = npcs.filter((n) => n.met !== false);
  const unmet = npcs.filter((n) => n.met === false);
  return (
    <div className="tab-body">
      <div className="section-title">Characters ({met.length})</div>
      {met.length === 0 && <div className="muted small">No characters met yet. They appear here as the story introduces them.</div>}
      {met.map((n) => <NpcCard key={n.id} npc={n} onUpdate={onUpdate} onDelete={onDelete} log={logOf(n)} />)}
      {unmet.length > 0 && (
        <details className="unmet">
          <summary className="section-title">Not met yet ({unmet.length})</summary>
          <div className="muted tiny">Characters from the card. They move up when they first show up in the story.</div>
          {unmet.map((n) => <NpcCard key={n.id} npc={n} onUpdate={onUpdate} onDelete={onDelete} />)}
        </details>
      )}
      <form className="row gap" onSubmit={(e) => { e.preventDefault(); if (!name.trim()) return; onAdd({ name: name.trim() }); setName(""); }}>
        <input className="field grow" placeholder="Add a character…" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="btn small" type="submit">Add</button>
      </form>
    </div>
  );
}

/* -------------------------------------------------------------------- Map */
function layoutNodes(locations, current) {
  const W = 340, H = 380;
  const names = locations.map((l) => l.name);
  const pos = {};
  names.forEach((n, i) => {
    const a = (i / Math.max(1, names.length)) * Math.PI * 2;
    pos[n] = { x: W / 2 + Math.cos(a) * 120, y: H / 2 + Math.sin(a) * 130, vx: 0, vy: 0 };
  });
  const edges = [];
  locations.forEach((l) => l.connections.forEach((c) => { if (pos[c] && l.name < c) edges.push([l.name, c]); }));
  for (let it = 0; it < 220; it++) {
    for (const a of names) for (const b of names) {
      if (a >= b) continue;
      let dx = pos[a].x - pos[b].x, dy = pos[a].y - pos[b].y;
      const d2 = Math.max(dx * dx + dy * dy, 25);
      const f = 9000 / d2, d = Math.sqrt(d2);
      dx = (dx / d) * f; dy = (dy / d) * f;
      pos[a].vx += dx; pos[a].vy += dy; pos[b].vx -= dx; pos[b].vy -= dy;
    }
    for (const [a, b] of edges) {
      const dx = pos[b].x - pos[a].x, dy = pos[b].y - pos[a].y;
      const d = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
      const f = (d - 115) * 0.02;
      pos[a].vx += (dx / d) * f * 10; pos[a].vy += (dy / d) * f * 10;
      pos[b].vx -= (dx / d) * f * 10; pos[b].vy -= (dy / d) * f * 10;
    }
    for (const n of names) {
      pos[n].vx += (W / 2 - pos[n].x) * 0.01; pos[n].vy += (H / 2 - pos[n].y) * 0.01;
      pos[n].x = clamp(pos[n].x + pos[n].vx * 0.05, 55, W - 55);
      pos[n].y = clamp(pos[n].y + pos[n].vy * 0.05, 30, H - 36);
      pos[n].vx *= 0.6; pos[n].vy *= 0.6;
    }
  }
  return { pos, edges, W, H };
}

function MapTab({ state, convId, refreshKey }) {
  const locs = state.locations;
  const [sel, setSel] = useState(null);
  const key = JSON.stringify(locs.map((l) => [l.name, l.connections]));
  const layout = useMemo(() => layoutNodes(locs, state.location), [key]); // eslint-disable-line
  const chosen = locs.find((l) => l.name === sel);
  return (
    <div className="tab-body">
      <div className="section-title">Known places ({locs.length})</div>
      {locs.length === 0 ? (
        <div className="muted small">The map fills in as you explore. Places appear when the story names them.</div>
      ) : (
        <svg viewBox={`0 0 ${layout.W} ${layout.H}`} className="map">
          {layout.edges.map(([a, b]) => (
            <line key={a + b} x1={layout.pos[a].x} y1={layout.pos[a].y} x2={layout.pos[b].x} y2={layout.pos[b].y} className="map-edge" />
          ))}
          {locs.map((l) => {
            const p = layout.pos[l.name];
            const here = l.name === state.location;
            return (
              <g key={l.name} transform={`translate(${p.x},${p.y})`} onClick={() => setSel(l.name)} style={{ cursor: "pointer" }}>
                <circle r={here ? 9 : 6} className={`map-node ${here ? "here" : ""} ${l.visited ? "visited" : ""}`} />
                <text y={here ? 22 : 19} textAnchor="middle" className="map-label">{l.name.length > 18 ? l.name.slice(0, 17) + "…" : l.name}</text>
              </g>
            );
          })}
        </svg>
      )}
      {state.location && <div className="small">📍 You are at <strong>{state.location}</strong></div>}
      {chosen && (
        <div className="card">
          <strong>{chosen.name}</strong> <span className="muted small">{chosen.visited ? "visited" : "heard of"}</span>
          {chosen.description && <div className="small">{chosen.description}</div>}
          {chosen.connections.length > 0 && <div className="muted small">Connects to: {chosen.connections.join(", ")}</div>}
        </div>
      )}
      <MapBag convId={convId} refreshKey={refreshKey} />
    </div>
  );
}

/* ------------------------------------------------------------------- Dice */
const DICE = [4, 6, 8, 10, 12, 20, 100];

function DiceTab({ onRollToChat, canRoll }) {
  const [mod, setMod] = useState(0);
  const [mode, setMode] = useState("normal");
  const [custom, setCustom] = useState("");
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const build = (sides) => `1d${sides}${mod > 0 ? `+${mod}` : mod < 0 ? mod : ""}${mode === "advantage" && sides === 20 ? " adv" : mode === "disadvantage" && sides === 20 ? " dis" : ""}`;
  const roll = async (expr, toChat) => {
    setError("");
    if (toChat) { onRollToChat(expr); return; }
    try { const r = await api.roll(expr); setHistory((h) => [r, ...h].slice(0, 20)); } catch (e) { setError(e.message); }
  };
  const [toChat, setToChat] = useState(true);
  return (
    <div className="tab-body">
      <div className="section-title">Dice</div>
      <div className="dice-grid">
        {DICE.map((s) => <button key={s} className="die" onClick={() => roll(build(s), toChat && canRoll)}>d{s}</button>)}
      </div>
      <div className="row gap center">
        <label className="small">Modifier</label>
        <button className="icon-btn" onClick={() => setMod(mod - 1)}>−</button>
        <span className="qty">{fmtMod(mod)}</span>
        <button className="icon-btn" onClick={() => setMod(mod + 1)}>＋</button>
        <select className="field" value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="normal">normal</option>
          <option value="advantage">advantage (d20)</option>
          <option value="disadvantage">disadvantage (d20)</option>
        </select>
      </div>
      <form className="row gap" onSubmit={(e) => { e.preventDefault(); if (custom.trim()) roll(custom.trim(), toChat && canRoll); }}>
        <input className="field grow" placeholder="Custom: 2d6+3, 4d6kh3…" value={custom} onChange={(e) => setCustom(e.target.value)} />
        <button className="btn small" type="submit">Roll</button>
      </form>
      <label className="row gap center small">
        <input type="checkbox" checked={toChat} onChange={(e) => setToChat(e.target.checked)} />
        Send roll into the story (the Aedo sees it)
      </label>
      {error && <div className="error-text small">{error}</div>}
      <div className="section-title">Private rolls</div>
      {history.length === 0 && <div className="muted small">With "send into the story" off, rolls show up here only.</div>}
      {history.map((r, i) => <div key={i} className="roll-line">{r.text.replace(/\*\*/g, "").replace(/~~/g, "")}</div>)}
    </div>
  );
}

/* ---------------------------------------------------------------- Journal */
function PinnedBox({ value, limit, onSave }) {
  const [text, setText] = useState(value || "");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => setText(value || ""), [value]);
  const dirty = text.trim() !== (value || "").trim();
  const save = async () => {
    setError(""); setSaved(false);
    const err = await onSave(text);
    if (err) setError(err); else { setSaved(true); setTimeout(() => setSaved(false), 1500); }
  };
  return (
    <>
      <div className="section-title">Remember this <HelpTip id="pinned" /></div>
      <textarea className="field" rows={6} value={text} maxLength={limit + 200} onChange={(e) => setText(e.target.value)}
        placeholder="Write what the AI must never forget: promises, secrets, personalities, rules of your world…" />
      <div className="row gap center">
        <span className={`small ${text.length > limit ? "error-text" : "muted"}`}>{text.length} / {limit}</span>
        <span className="grow" />
        {saved && <span className="ok-text small">✓ saved</span>}
        <button className="btn small primary" onClick={save} disabled={!dirty || text.length > limit}>Save</button>
      </div>
      {error && <div className="error-text small">{error}</div>}
    </>
  );
}

function JournalTab({ convId, summary, refreshKey, pinned, pinnedLimit, onPinnedSave, lore, onLoreSaved, state, onState, cantos, onCantos, busy }) {
  const [mems, setMems] = useState([]);
  const [filter, setFilter] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const load = () => api.memories(convId).then(setMems).catch(() => {});
  useEffect(() => { load(); }, [convId, refreshKey]); // eslint-disable-line
  const shown = mems.filter((m) => m.text.toLowerCase().includes(filter.toLowerCase()));
  const who = (m) => { try { return JSON.parse(m.participants || "[]").join(", "); } catch { return ""; } };
  return (
    <div className="tab-body">
      {state?.date_label && <CalendarBox convId={convId} state={state} onState={onState} />}
      <CantosBox convId={convId} cantos={cantos} onCantos={onCantos} busy={busy} />
      <PinnedBox value={pinned} limit={pinnedLimit} onSave={onPinnedSave} />
      <PlayerLore key={convId} entries={lore} convId={convId} onSaved={onLoreSaved} />
      <div className="section-title">Story so far</div>
      <div className="card small">{summary || <span className="muted">The summary appears once the conversation gets long. Older messages are condensed here so the AI never loses the plot.</span>}</div>
      <div className="section-title">Remembered facts ({mems.length})</div>
      <input className="field" placeholder="Search memories…" value={filter} onChange={(e) => setFilter(e.target.value)} />
      <div className="mem-list">
        {shown.length === 0 && <div className="muted small">Nothing here yet.</div>}
        {shown.map((m) => (
          <div className="mem" key={m.id}>
            <div className="grow small">{m.text}<div className="muted tiny">{who(m) && `${who(m)} · `}{m.kind} · importance {m.importance}</div></div>
            <button className="icon-btn" title="Forget" onClick={() => api.deleteMemory(m.id).then(load)}>✕</button>
          </div>
        ))}
      </div>
      <form className="row gap" onSubmit={async (e) => { e.preventDefault(); if (!text.trim()) return; try { await api.addMemory(convId, text.trim()); setText(""); setError(""); load(); } catch (err) { setError(err.message); } }}>
        <input className="field grow" placeholder="Add a fact to remember…" value={text} onChange={(e) => setText(e.target.value)} />
        <button className="btn small" type="submit">Save</button>
      </form>
      {error && <div className="error-text small">{error}</div>}
    </div>
  );
}

/* -------------------------------------------------------------- Adventure */
/** Fog of war over an adventure map: dark except around the places already visited. */
function FogOverlay({ map, clear }) {
  const id = React.useId().replace(/:/g, "");
  const g = map.grid?.size ? map.grid : null;
  const W = g ? g.nat_w / g.size : map.cols || 30, H = g ? g.nat_h / g.size : map.rows || 20;  // in squares
  return (
    <svg className="fog-overlay" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <defs>
        <filter id={`b${id}`}><feGaussianBlur stdDeviation="0.8" /></filter>
        <mask id={`m${id}`}>
          <rect x="0" y="0" width={W} height={H} fill="white" />
          <g filter={`url(#b${id})`}>{clear.map(([fx, fy], i) => <circle key={i} cx={fx * W} cy={fy * H} r={map.reveal} fill="black" />)}</g>
        </mask>
      </defs>
      <rect x="0" y="0" width={W} height={H} fill="#0b0912" opacity="0.9" mask={`url(#m${id})`} />
    </svg>
  );
}

function AdventureTab({ adventure, state, convId, onState, onFight, busy }) {
  const st = state.adventure || {};
  const scenes = adventure.scenes || [];
  const cur = scenes.find((s) => s.id === st.scene);
  const visited = new Set(st.visited || []);
  const [error, setError] = useState("");
  const go = async (id) => { try { const r = await api.adventureScene(convId, id); onState(r.state); setError(""); } catch (e) { setError(e.message); } };
  const xp = async () => { try { const r = await api.adventureXp(convId, cur.id); onState(r.state); } catch (e) { setError(e.message); } };
  const map = cur && (adventure.maps || []).find((m) => m.id === cur.map);
  const pic = map && (map.player_picture || map.picture);
  const leads = cur ? (cur.leads || []).map((id) => scenes.find((s) => s.id === id)).filter(Boolean) : [];
  const parts = adventure.parts || [];
  return (
    <div className="tab-body adventure-tab">
      {cur ? (
        <>
          <div className="section-title">{cur.group ? <span className="muted">{cur.group} · </span> : null}{cur.name}</div>
          {cur.read_aloud && <details className="read-aloud"><summary className="small">📖 What you see</summary><div className="small pre">{cur.read_aloud}</div></details>}
          <div className="row gap wrap">
            {cur.enemies?.length > 0 && !state.combat?.active && <button className="btn small" disabled={busy} onClick={onFight}>{`⚔ Fight here (${cur.enemies.map((e) => (e.count > 1 ? `${e.count}× ${e.name}` : e.name)).join(", ")})`}</button>}
            {cur.xp > 0 && !(st.xp_given || []).includes(cur.id) && <button className="btn small" onClick={xp}>{`🏅 Give the XP (+${cur.xp})`}</button>}
          </div>
          {pic && (
            <div className="adv-map small-map">
              <img src={portraitSrc(pic)} alt="" />
              {map.grid?.size && <GridOverlay grid={map.grid} color="rgba(255,255,255,.25)" />}
              {map.reveal > 0 && <FogOverlay map={map} clear={scenes.filter((s) => visited.has(s.id) && map.markers?.[s.id]).map((s) => map.markers[s.id])} />}
              {scenes.filter((s) => s.map === map.id && map.markers?.[s.id] && (visited.has(s.id) || leads.includes(s))).map((s) => (
                <button key={s.id} className={`adv-pin ${s.id === cur.id ? "on" : visited.has(s.id) ? "seen" : "lead"}`}
                  style={{ left: `${map.markers[s.id][0] * 100}%`, top: `${map.markers[s.id][1] * 100}%` }}
                  title={s.name} onClick={() => s.id !== cur.id && go(s.id)}>{(s.name.match(/^[A-Z]?\d+[a-z]?/) || ["•"])[0]}</button>
              ))}
            </div>
          )}
          {leads.length > 0 && (
            <>
              <div className="small muted">Ways on from here</div>
              <div className="conds">{leads.map((s) => <button key={s.id} className="chip" onClick={() => go(s.id)}>→ {s.name}</button>)}</div>
            </>
          )}
        </>
      ) : <div className="muted small">Not in a scene of the adventure yet. Pick one below.</div>}
      <details className="visited" open={!cur}>
        <summary className="small">{`Where you have been (${visited.size})`}</summary>
        {(parts.length ? parts : [{ id: "", title: "" }]).map((p) => {
          const mine = scenes.filter((s) => (s.part || "") === p.id && (visited.has(s.id) || !cur && s === scenes[0]));
          if (!mine.length) return null;
          return (
            <div key={p.id}>
              {p.title && <div className="tiny muted">{p.title}</div>}
              {mine.map((s) => (
                <button key={s.id} className={`link-btn small block ${s.id === st.scene ? "on" : ""}`} onClick={() => go(s.id)}>
                  {s.group ? `${s.group} · ` : ""}{s.name}{(st.xp_given || []).includes(s.id) ? " 🏅" : ""}
                </button>
              ))}
            </div>
          );
        })}
      </details>
      <div className="muted tiny">The Aedo follows the adventure: the read-aloud text on the first visit, the checks with their DC, the enemies here. The scene changes when the story moves on (or when you pick one here).</div>
      {error && <div className="error-text small">{error}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ Panel */
export const TABS = [
  ["adventure", "📕", "Adventure"],
  ["status", "📜", "Status"],
  ["sheet", "🧙", "Sheet"],
  ["bag", "🎒", "Bag"],
  ["people", "👥", "People"],
  ["map", "🗺", "Map"],
  ["combat", "⚔", "Combat"],
  ["dice", "🎲", "Dice"],
  ["journal", "📖", "Journal"],
];

export default function SidePanel({ game, tab, onTab, onPatch, onNpcUpdate, onNpcDelete, onNpcAdd, onRollToChat, canRoll, memoryKey, onClose, onPinnedSave, onLoreSaved, onStateLoaded, onPay, onPower, onRest, onCombat, onCombatEdit, onCantos, onReload, style }) {
  const { state, npcs, conversation } = game;
  const mode = conversation.scenario?.mode;
  const kind = game.features?.kind || (mode === "character" ? "roleplay" : "adventure");
  const allowed = [...(game.features?.panels || TABS.map(([k]) => k)), ...(state.combat?.active ? ["combat"] : []),
    "sheet", "status",  // always: your character (name, background, looks…) can be read, copied and edited there
    ...((game.messages || []).some((m) => m.meta?.scene_picture) ? ["map"] : []),
    ...(conversation.scenario?.adventure?.scenes?.length ? ["adventure", "combat"] : [])];  // the map bag lives on the map tab
  const statusFirst = (game.features?.panels || []).includes("status") || !!game.status_by_app;
  const tabs = TABS.filter(([k]) => allowed.includes(k) && (statusFirst || k !== "status"))
    .concat(statusFirst ? [] : TABS.filter(([k]) => k === "status"));  // without a sheet it waits at the end, to pick one
  const active = tabs.some(([k]) => k === tab) ? tab : tabs[0]?.[0];
  return (
    <aside className="side-panel">
      <div className="tabs">
        {tabs.map(([k, icon, label]) => (
          <button key={k} className={`tab ${active === k ? "active" : ""}`} onClick={() => onTab(k)}>
            <span>{icon}</span><span className="tab-label">{label}</span>
          </button>
        ))}
        <button className="icon-btn close-panel" onClick={onClose} title="Hide panel">✕</button>
      </div>
      <div className="tab-scroll">
        {active === "adventure" && <AdventureTab adventure={conversation.scenario.adventure} state={state} convId={conversation.id}
          onState={onStateLoaded} onFight={() => onTab("combat")} busy={!canRoll} />}
        {active === "status" && <StatusTab messages={game.messages} every={conversation.scenario?.information?.status_every}
          byApp={!!game.status_by_app} fields={game.status_fields} sheetOwn={!!game.sheet_own}
          picked={conversation.scenario?.sheet_template || ""} convId={conversation.id} onReload={onReload} now={game.status_now}
          values={state.card_status} onPatch={onPatch} />}
        {active === "sheet" && <SheetTab state={state} onPatch={onPatch} mode={mode} kind={kind} onPower={onPower} onRest={onRest} busy={!canRoll}
          convId={conversation.id} onState={onStateLoaded} />}
        {active === "bag" && <BagTab state={state} onPatch={onPatch} onPay={onPay} busy={!canRoll} currency={conversation.scenario?.currency || "gold"} />}
        {active === "people" && <PeopleTab npcs={npcs} onUpdate={onNpcUpdate} onDelete={onNpcDelete} onAdd={onNpcAdd} repLog={state.rep_log || []} />}
        {active === "map" && <MapTab state={state} convId={conversation.id} refreshKey={game.messages?.length} />}
        {active === "combat" && <CombatTab game={game} busy={!canRoll} onCombat={onCombat} onCombatEdit={onCombatEdit} />}
        {active === "dice" && <DiceTab onRollToChat={onRollToChat} canRoll={canRoll} />}
        {active === "journal" && <JournalTab convId={conversation.id} summary={conversation.summary} refreshKey={memoryKey}
          pinned={conversation.pinned_memory} pinnedLimit={game.pinned_limit || 2000} onPinnedSave={onPinnedSave}
          lore={conversation.player_lore} onLoreSaved={onLoreSaved} state={state} onState={onStateLoaded}
          cantos={game.cantos} onCantos={onCantos} busy={!canRoll} />}
      </div>
    </aside>
  );
}
