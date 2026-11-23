import React, { useEffect, useState } from "react";
import PlayerLore from "./PlayerLore.jsx";

const NO_LORE = [];
import { api } from "../api.js";
import HelpTip from "./HelpTip.jsx";
import { CharacterPreview, StartPicker } from "./CardExtras.jsx";
import PersonaBar from "./Personas.jsx";
import CardSheetForm, { startValues } from "./CardSheetForm.jsx";
import SkillsEditor from "./SkillsEditor.jsx";
import SystemsSheet from "./SystemsSheet.jsx";
import MoodEditor from "./MoodEditor.jsx";
import CompanionSetup, { companionFace, withEdits } from "./CompanionSetup.jsx";
import { portraitSrc } from "../portraits.js";
import { abilityMod, fmtMod } from "../utils.js";

// Hit die per class (D&D 5e). Anything else uses d8.
const HIT_DIE = { barbarian: 12, fighter: 10, paladin: 10, ranger: 10, bard: 8, cleric: 8, druid: 8, monk: 8, rogue: 8, warlock: 8, sorcerer: 6, wizard: 6 };
const CLASSES = ["Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard"];
const STANDARD = [15, 14, 13, 12, 10, 8];
const SKILLS_FIELD = /^(skills?|habilidades?|abilities|powers|poderes)\b/i; // the card's own Skills field: filled from "Your skills"

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
  const [partyMode, setPartyMode] = useState("companions"); // a card with companions: play with them, or solo
  const [busy, setBusy] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [error, setError] = useState("");
  const [lore, setLore] = useState([]);
  const [loreKey, setLoreKey] = useState(0); // a loaded persona redraws the world additions box with its entries
  const [startId, setStartId] = useState("default");
  const [lang, setLang] = useState(""); // this game's story language ("" = the one in Settings)
  const [showCast, setShowCast] = useState(false);
  const [sheet, setSheet] = useState(null); // the card's own sheet (Lumencia: Tier, Attributes, Stats with EXP)
  const [sheetValues, setSheetValues] = useState({});
  const [sys, setSys] = useState(null); // the card's own sheet (Black Sheep: stats and loadout), checked by the app
  const [skills, setSkills] = useState([]); // your own skills: the Aedo always sees them; name one in the story to use it
  const [compEdits, setCompEdits] = useState({}); // "Set up your companions": changes by the companion's card name
  const [keepComp, setKeepComp] = useState(true);
  const [showComp, setShowComp] = useState(false);

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
      // Imported cards usually create the character inside the story: offer that first,
      // unless the card keeps its own sheet: then it is filled here, like a D&D sheet.
      if (d.systems && (d.systems.stats || d.systems.loadout)) {
        api.trySystems(scenarioId, {}).then((r) => setSys({ ...r, error: "" })).catch(() => {});
      }
      api.startSheet(scenarioId).then((sh) => {
        if (sh?.groups?.length && d.kind !== "adventure") { setSheet(sh); setSheetValues(startValues(sh.groups)); setWay("app"); }
        else if (d.systems && (d.systems.stats || d.systems.loadout)) setWay("app");
        else if ((d.information?.description || "").trim()) setWay("card");
      }).catch(() => { if ((d.information?.description || "").trim()) setWay("card"); });
    }).catch((e) => setError(e.message));
  }, [scenarioId]);

  if (!card || !p) return <div className="muted small">{error || "Loading…"}</div>;

  const adventure = card.kind === "adventure";
  const team = (card.npcs || []).filter((n) => n.companion);
  const hasTeam = team.length > 0;
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

  const withTeam = hasTeam && partyMode === "companions";
  const sysTry = async (body) => {
    try { const r = await api.trySystems(scenarioId, { state: sys?.state, ...body }); setSys({ ...r, error: r.error || "" }); } catch (e) { setSys((x) => ({ ...x, error: e.message })); }
  };
  const sysValue = (stat, value) => {
    const next = { ...sys.state, values: { ...sys.state.values, [stat]: value } };
    setSys((x) => ({ ...x, state: next }));
    api.trySystems(scenarioId, { state: next }).then((r) => setSys({ ...r, error: "" })).catch(() => {});
  };
  const teamOpts = () => {
    const list = Object.entries(compEdits).map(([of, e]) => ({ of, ...e }));
    return withTeam && list.length ? { companions: list } : {};
  };
  const saveTeam = async (edits, keep) => {
    setCompEdits(edits); setKeepComp(keep); setShowComp(false); setError("");
    if (!keep) return;
    try { // kept on the card: next games (and the card editor) have them too
      const saved = await api.saveCompanions(scenarioId, Object.entries(edits).map(([of, e]) => ({ of, ...e })));
      setCard({ ...saved.data, name: saved.name });
      setCompEdits({});
    } catch (e) { setError(e.message); }
  };

  const start = async () => {
    setBusy(true); setError("");
    try {
      if (way === "card") {
        await onStart(scenarioId, { setup: "card", player_name: p.name.trim() || undefined, player_lore: lore, start: startId, ...(lang ? { language: lang } : {}), party: hasTeam ? partyMode : "solo", ...teamOpts() });
      } else if (way === "builder") {
        if (!p.name.trim()) { setError("Give your character a name."); setBusy(false); return; }
        await onStart(scenarioId, { setup: "app", player: { ...p, name: p.name.trim() }, player_lore: lore, start: startId, ...(lang ? { language: lang } : {}), party: hasTeam ? partyMode : "solo", open_builder: true, ...teamOpts() });
      } else {
        if (!p.name.trim()) { setError("Give your character a name."); setBusy(false); return; }
        const player = { ...p, name: p.name.trim() };
        if (adventure) { player.hp = { current: hp, max: hp }; player.ac = ac; }
        else delete player.stats;
        // only what you filled: an empty box or a stat without a grade ("- [0/100]") keeps the card's own value
        const own = sheet ? Object.fromEntries(Object.entries(sheetValues).filter(([, v]) => { const t = String(v || "").trim(); return t && !/^-?\s*\[\d+\/\d+\]$/.test(t); })) : null;
        const mySkills = skills.filter((k) => String(k.name || "").trim());
        await onStart(scenarioId, { setup: "app", player, player_lore: lore, start: startId, ...(lang ? { language: lang } : {}), party: hasTeam ? partyMode : "solo", ...(own ? { card_status: own } : {}),
          ...(mySkills.length ? { abilities: mySkills } : {}), ...(sys?.state ? { systems_state: sys.state } : {}), ...teamOpts() });
      }
    } catch (e) { setError(e.message); setBusy(false); }
  };

  return (
    <div className="setup">
      <h3 className="setup-title">{adventure ? "Create your sheet" : "Who are you?"} <span className="muted small">· {card.name}</span>
        {(card.npcs || []).length > 0 && <button type="button" className="btn small ghost" style={{ marginLeft: 8 }} onClick={() => setShowCast((v) => !v)}>👥 {showCast ? "Hide characters" : "Characters"}</button>}</h3>
      {showCast && <CharacterPreview npcs={card.npcs} />}
      <StartPicker card={card} value={startId} onChange={setStartId} />
      <div className="row gap story-lang">
        <span className="small">Language of this story</span>
        <select className="field" value={lang} onChange={(e) => setLang(e.target.value)}>
          <option value="">As in Settings</option>
          <option value="en">English</option>
          <option value="pt-BR">Português (Brasil)</option>
        </select>
        {lang === "pt-BR" && (card.language || "en") !== "pt-BR" && <span className="muted tiny">The opening is translated when the story starts (about half a minute).</span>}
      </div>

      <div className="section-title">Your character</div>
      <PersonaBar player={p} lore={lore} onLoad={(persona) => {
        // the card's own sheet shape stays (stats, class list); the persona fills in who you are
        setP((x) => ({ ...x, ...Object.fromEntries(Object.entries(persona.player || {}).filter(([k, v]) => v !== "" && v != null && !(k === "stats" && !Object.keys(v || {}).length))) }));
        if ((persona.lore || []).length) { setLore(persona.lore); setLoreKey((k) => k + 1); }
      }} />
      {hasTeam && (
        <div className="way-pick">
          <label className={`way ${partyMode === "companions" ? "active" : ""}`}>
            <input type="radio" checked={partyMode === "companions"} onChange={() => { setPartyMode("companions"); setShowComp(true); }} />
            <span><strong>👥 Play with companions</strong><br /><span className="muted tiny">{`${team.map((n) => withEdits(n, compEdits).name).join(", ")} travel and fight beside you.`}</span></span>
          </label>
          <label className={`way ${partyMode === "solo" ? "active" : ""}`}>
            <input type="radio" checked={partyMode === "solo"} onChange={() => setPartyMode("solo")} />
            <span><strong>🧍 Play solo</strong><br /><span className="muted tiny">Just you. An adventure's fights are scaled down to one hero.</span></span>
          </label>
        </div>
      )}
      {withTeam && (
        <div className="team-row">
          {team.map((n) => {
            const c = withEdits(n, compEdits);
            const face = companionFace(c);
            return (
              <span className="team-face" key={n.name} title={c.name}>
                {face ? <img src={portraitSrc(face)} alt="" /> : <span>{(c.name || "?").slice(0, 1)}</span>}
                <span className="tiny">{c.name.split(" ")[0]}</span>
              </span>
            );
          })}
          <button type="button" className="btn small" onClick={() => setShowComp(true)}>✎ Set up your companions</button>
        </div>
      )}
      {showComp && <CompanionSetup team={team} edits={compEdits} keep={keepComp} onDone={saveTeam} onClose={() => setShowComp(false)} />}
      <div className="way-pick">
        <label className={`way ${way === "app" ? "active" : ""}`}>
          <input type="radio" checked={way === "app"} onChange={() => setWay("app")} />
          <span><strong>Create my character here</strong><br /><span className="muted tiny">Fill in the form below. The story starts with your character ready.</span></span>
        </label>
        {adventure && String(card.system || "dnd5e-2014").startsWith("dnd5e") && (
          <label className={`way ${way === "builder" ? "active" : ""}`}>
            <input type="radio" checked={way === "builder"} onChange={() => setWay("builder")} />
            <span><strong>Build with the 5e builder</strong><br /><span className="muted tiny">Pick a class, race, background and equipment from the Library. The app works out every number.</span></span>
          </label>
        )}
        <label className={`way ${way === "card" ? "active" : ""}`}>
          <input type="radio" checked={way === "card"} onChange={() => setWay("card")} />
          <span><strong>Let the story ask me</strong><br /><span className="muted tiny">The card creates your character in the chat, its own way.</span></span>
        </label>
      </div>

      {way === "builder" ? (
        <>
          <label className="lbl">Your character's name</label>
          <input className="field" value={p.name} onChange={(e) => set("name", e.target.value)} autoFocus />
          <div className="muted tiny">The builder opens as soon as the game starts.</div>
        </>
      ) : way === "card" ? (
        <>
          <label className="lbl">Your character's name (optional)</label>
          <input className="field" value={p.name} onChange={(e) => set("name", e.target.value)} placeholder="Leave empty to decide in the story" />
        </>
      ) : (
        <>
          <div className="row gap center setup-me">
            <div className="setup-portrait" title="Your character's picture: it shows on your sheet">
              <MoodEditor portraits={p.portraits} mainOnly onChange={(v) => set("portraits", v)} />
            </div>
            <div className="grow muted tiny">{"Your character's picture (optional): a file from this PC or a link. It shows on your Sheet tab."}</div>
          </div>
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
          {sheet && (
            <>
              <div className="section-title">{`${card.name}'s sheet`}</div>
              <div className="muted tiny">The card's own values. The story raises them as you play: EXP fills each stat's bar, and a full bar raises its grade. They live in the Sheet tab.</div>
              {sheet.rules && (
                <details className="card-rules-box">
                  <summary className="small">What the card asks for</summary>
                  <div className="card-rules muted">{sheet.rules}</div>
                </details>
              )}
              <CardSheetForm groups={sheet.groups} values={sheetValues} onChange={setSheetValues} hide={SKILLS_FIELD} />
            </>
          )}
          {sys?.state && (
            <>
              <div className="section-title">{`${card.name}'s sheet`}</div>
              <div className="muted tiny">Kept by the app with the card's rules: pick your parts (the budget and level locks are checked) and set your starting numbers. It lives in the Sheet tab, and the Aedo sees the real numbers.</div>
              <SystemsSheet creating systems={card.systems} state={sys.state} computed={sys.computed} error={sys.error}
                onValue={sysValue} onPart={(slot, item) => sysTry({ slot, item })} />
            </>
          )}
          {!adventure && (
            <>
              <div className="section-title">Your skills</div>
              <div className="muted tiny">{(card.resources || []).length
                ? "Your special abilities, written your way. The Aedo always sees them and follows what you write. In the story, just name one (\"I use my Soul Forge\") and it happens, paying its cost. They also sit in the Sheet tab with a Use button."
                : "Your special abilities, written your way. The Aedo always sees them and follows what you write. In the story, just name one (\"I use my Soul Forge\") and it happens. They also sit in the Sheet tab with a Use button."}</div>
              <SkillsEditor skills={skills} onChange={setSkills} resources={(card.resources || []).map((r) => r.name)} />
            </>
          )}
        </>
      )}

      <PlayerLore key={loreKey} entries={loreKey ? lore : NO_LORE} onChange={setLore} />

      {error && <div className="error-text small">{error}</div>}
      <div className="row gap end">
        <button className="btn" onClick={onBack}>Back</button>
        <button className="btn primary" onClick={start} disabled={busy}>{busy ? (lang === "pt-BR" && (card.language || "en") !== "pt-BR" ? "Translating the opening…" : "Starting…") : "Start the story"}</button>
      </div>
    </div>
  );
}
