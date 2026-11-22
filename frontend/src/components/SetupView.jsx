import React, { useEffect, useState } from "react";
import PlayerLore from "./PlayerLore.jsx";

const NO_LORE = [];
import { api } from "../api.js";
import HelpTip from "./HelpTip.jsx";
import { CharacterPreview, StartPicker } from "./CardExtras.jsx";
import PersonaBar from "./Personas.jsx";
import { abilityMod, fmtMod } from "../utils.js";

// Hit die per class (D&D 5e). Anything else uses d8.
const HIT_DIE = { barbarian: 12, fighter: 10, paladin: 10, ranger: 10, bard: 8, cleric: 8, druid: 8, monk: 8, rogue: 8, warlock: 8, sorcerer: 6, wizard: 6 };
const CLASSES = ["Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard"];
const STANDARD = [15, 14, 13, 12, 10, 8];

const roll4d6 = () => {
  const d = Array.from({ length: 4 }, () => 1 + Math.floor(Math.random() * 6)).sort((a, b) => a - b);
  return d[1] + d[2] + d[3];
};

/**
 * The start screen of a new game.
 * Adventure cards: "Create your sheet" (name, race, class, abilities, story).
 * Roleplay cards: "Who are you?" (name, looks, personality, background).
 * Cards that run their own character creation in the story can skip it.
 */
// 5e armour: [pattern, base AC, most DEX that counts]; a shield adds 2
const ARMOR = [[/half[- ]?plate/i, 15, 2], [/\bplate\b/i, 18, 0], [/splint/i, 17, 0], [/chain ?mail|cota de malha/i, 16, 0],
  [/ring ?mail/i, 14, 0], [/breastplate|peitoral/i, 14, 2], [/scale ?mail/i, 14, 2], [/chain ?shirt|camis[aã]o de malha/i, 13, 2],
  [/\bhide\b|gibão de peles/i, 12, 2], [/studded|tachas/i, 12, 99], [/leather|couro/i, 11, 99], [/padded|acolchoad/i, 11, 99]];
function armorClass(items, dex, cardAc) {
  const names = (items || []).map((i) => String(i?.name || i || ""));
  const found = ARMOR.map((a) => [a, names.find((n) => a[0].test(n))]).find(([, n]) => n);
  const shield = names.some((n) => /shield|escudo/i.test(n));
  const cap = found ? found[0][2] : 99; // heavy armour: DEX does not count at all, not even a penalty
  let ac = found ? found[0][1] + (cap ? Math.min(dex, cap) : 0) : 10 + dex;
  let how = found ? `${found[1]} ${found[0][1]}${found[0][2] ? ` ${fmtMod(Math.min(dex, found[0][2]))} DEX` : ""}` : `10 ${fmtMod(dex)} DEX`;
  if (shield) { ac += 2; how += " + shield 2"; }
  if (!found && !shield && cardAc > ac) return { ac: cardAc, acHow: "the card's AC" };
  return { ac, acHow: how };
}

export default function SetupView({ scenarioId, onBack, onStart }) {
  const [card, setCard] = useState(null);
  const [p, setP] = useState(null);
  const [way, setWay] = useState("app");
  const [busy, setBusy] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [error, setError] = useState("");
  const [lore, setLore] = useState([]);
  const [startId, setStartId] = useState("default");
  const [showCast, setShowCast] = useState(false);

  useEffect(() => {
    api.scenario(scenarioId).then((s) => {
      const d = s.data;
      setCard({ ...d, name: s.name });
      const tpl = d.player || {};
      setP({
        name: "", race: tpl.race || "", class: tpl.class || "", level: tpl.level || 1,
        stats: { ...(tpl.stats || { STR: 10, DEX: 10, CON: 10, INT: 10, WIS: 10, CHA: 10 }) },
        background: "", description: "", traits: "", // your own story, not the card's example
      });
      // Imported cards usually create the character inside the story: offer that first.
      if ((d.information?.description || "").trim()) setWay("card");
    }).catch((e) => setError(e.message));
  }, [scenarioId]);

  if (!card || !p) return <div className="muted small">{error || "Loading…"}</div>;

  const adventure = card.kind === "adventure";
  const set = (k, v) => setP((x) => ({ ...x, [k]: v }));
  const setStat = (k, v) => setP((x) => ({ ...x, stats: { ...x.stats, [k]: Math.max(1, Math.min(30, parseInt(v, 10) || 0)) } }));
  const statKeys = Object.keys(p.stats);
  const fill = (values) => setP((x) => ({ ...x, stats: Object.fromEntries(statKeys.map((k, i) => [k, values[i] ?? 10])) }));

  const die = HIT_DIE[(p.class || "").trim().toLowerCase()] || 8;
  const con = abilityMod(p.stats.CON ?? 10);
  const dex = abilityMod(p.stats.DEX ?? 10);
  const hp = Math.max(1, die + con);
  const { ac, acHow } = armorClass(card.player?.inventory || card.inventory || [], dex, card.player?.ac);

  const help = async () => {
    setDrafting(true); setError("");
    try {
      const got = await api.draftPlayer(scenarioId, p);
      setP((x) => {
        const next = { ...x };
        for (const [k, v] of Object.entries(got)) if (!String(x[k] || "").trim()) next[k] = v; // never overwrite what you wrote
        return next;
      });
    } catch (e) { setError(e.message); } finally { setDrafting(false); }
  };

  const start = async () => {
    setBusy(true); setError("");
    try {
      if (way === "card") {
        await onStart(scenarioId, { setup: "card", player_name: p.name.trim() || undefined, player_lore: lore, start: startId });
      } else {
        if (!p.name.trim()) { setError("Give your character a name."); setBusy(false); return; }
        const player = { ...p, name: p.name.trim() };
        if (adventure) { player.hp = { current: hp, max: hp }; player.ac = ac; }
        else delete player.stats;
        await onStart(scenarioId, { setup: "app", player, player_lore: lore, start: startId });
      }
    } catch (e) { setError(e.message); setBusy(false); }
  };

  return (
    <div className="setup">
      <h3 className="setup-title">{adventure ? "Create your sheet" : "Who are you?"} <span className="muted small">· {card.name}</span>
        {(card.npcs || []).length > 0 && <button type="button" className="btn small ghost" style={{ marginLeft: 8 }} onClick={() => setShowCast((v) => !v)}>👥 {showCast ? "Hide characters" : "Characters"}</button>}</h3>
      {showCast && <CharacterPreview npcs={card.npcs} />}
      <StartPicker card={card} value={startId} onChange={setStartId} />

      <div className="section-title">Your character</div>
      <PersonaBar player={p} lore={lore} onLoad={(persona) => {
        // the card's own sheet shape stays (stats, class list); the persona fills in who you are
        setP((x) => ({ ...x, ...Object.fromEntries(Object.entries(persona.player || {}).filter(([k, v]) => v !== "" && v != null && !(k === "stats" && !Object.keys(v || {}).length))) }));
        if ((persona.lore || []).length) setLore(persona.lore);
      }} />
      <div className="way-pick">
        <label className={`way ${way === "app" ? "active" : ""}`}>
          <input type="radio" checked={way === "app"} onChange={() => setWay("app")} />
          <span><strong>Create my character here</strong><br /><span className="muted tiny">Fill in the form below. The story starts with your character ready.</span></span>
        </label>
        <label className={`way ${way === "card" ? "active" : ""}`}>
          <input type="radio" checked={way === "card"} onChange={() => setWay("card")} />
          <span><strong>Let the story ask me</strong><br /><span className="muted tiny">The card creates your character in the chat, its own way.</span></span>
        </label>
      </div>

      {way === "card" ? (
        <>
          <label className="lbl">Your character's name (optional)</label>
          <input className="field" value={p.name} onChange={(e) => set("name", e.target.value)} placeholder="Leave empty to decide in the story" />
        </>
      ) : (
        <>
          <div className="row gap">
            <div className="grow"><label className="lbl">Name</label><input className="field" value={p.name} onChange={(e) => set("name", e.target.value)} autoFocus /></div>
            {adventure && <div className="grow"><label className="lbl">Race</label>
              <input className="field" list="setup-races" value={p.race} onChange={(e) => set("race", e.target.value)} />
              <datalist id="setup-races">{(card.species || []).map((r) => <option key={r} value={r} />)}</datalist></div>}
            {adventure && <div className="grow"><label className="lbl">Class</label>
              <input className="field" list="setup-classes" value={p.class} onChange={(e) => set("class", e.target.value)} />
              <datalist id="setup-classes">{CLASSES.map((c) => <option key={c} value={c} />)}</datalist></div>}
          </div>

          {adventure && (
            <>
              <div className="section-title">Abilities <HelpTip id="setup_abilities" /></div>
              <div className="row gap">
                <button type="button" className="btn small" onClick={() => fill(STANDARD)}>Standard array</button>
                <button type="button" className="btn small" onClick={() => fill(statKeys.map(roll4d6))}>🎲 Roll 4d6</button>
                <button type="button" className="btn small" onClick={() => fill(statKeys.map(() => 10))}>All 10</button>
              </div>
              <div className="stats-grid setup-stats">
                {statKeys.map((k) => (
                  <div className="stat" key={k}>
                    <div className="stat-name">{k}</div>
                    <div className="stat-mod">{fmtMod(abilityMod(p.stats[k]))}</div>
                    <input className="field num" style={{ width: 52 }} value={p.stats[k]} onChange={(e) => setStat(k, e.target.value)} />
                  </div>
                ))}
              </div>
              <div className="muted small">{`Starting HP ${hp} (d${die} ${fmtMod(con)} CON) · AC ${ac} (${acHow}). You can change them on the sheet later.`}</div>
            </>
          )}

          <div className="row gap center setup-help">
            <div className="section-title grow">{adventure ? "Story" : "About you"}</div>
            <button type="button" className="btn small" onClick={help} disabled={drafting}>{drafting ? "Writing…" : "✨ Fill the empty fields"}</button>
          </div>
          <label className="lbl">Background</label>
          <textarea className="field" rows={3} value={p.background} onChange={(e) => set("background", e.target.value)} placeholder="Where you come from, what you want" />
          <label className="lbl">Appearance</label>
          <textarea className="field" rows={2} value={p.description} onChange={(e) => set("description", e.target.value)} placeholder="Hair, eyes, build, clothes" />
          <label className="lbl">Personality</label>
          <input className="field" value={p.traits} onChange={(e) => set("traits", e.target.value)} placeholder="Two or three words are enough" />
        </>
      )}

      <PlayerLore entries={NO_LORE} onChange={setLore} />

      {error && <div className="error-text small">{error}</div>}
      <div className="row gap end">
        <button className="btn" onClick={onBack}>Back</button>
        <button className="btn primary" onClick={start} disabled={busy}>{busy ? "Starting…" : "Start the story"}</button>
      </div>
    </div>
  );
}
