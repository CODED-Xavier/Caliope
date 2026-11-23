import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import MainMenu from "./MainMenu.jsx";

/** One big illustrated tile (the home screen, the Library and the settings pages). */
function Tile({ art, title, text, onClick, big = false, badge }) {
  return (
    <button type="button" className={`hub-tile ${big ? "big" : ""}`} onClick={onClick}>
      <span className="hub-corner tl" aria-hidden="true" /><span className="hub-corner tr" aria-hidden="true" />
      <span className="hub-corner bl" aria-hidden="true" /><span className="hub-corner br" aria-hidden="true" />
      {art && <img className="hub-art" src={art} alt="" />}
      <span className="hub-title">{title}</span>
      {text && <span className="hub-text">{text}</span>}
      {badge && <span className="hub-badge">{badge}</span>}
    </button>
  );
}

function Crumbs({ trail, onView }) {
  return (
    <nav className="crumbs" aria-label="Where you are">
      {trail.map(([label, view], i) => (
        <React.Fragment key={label}>
          {i > 0 && <span className="crumb-sep">›</span>}
          {view && i < trail.length - 1 ? <button type="button" className="link-btn" onClick={() => onView(view)}>{label}</button> : <strong>{label}</strong>}
        </React.Fragment>
      ))}
    </nav>
  );
}

// The 5e compendium's folders: each opens the Library on that kind of entry
const FOLDERS = [
  ["class", "Classes", "/emblems/fighter.png"], ["subclass", "Subclasses", "/emblems/paladin.png"], ["race", "Races", "/emblems/race-elf.png"],
  ["background", "Backgrounds", "/emblems/bard.png"], ["spell", "Spells", "/emblems/wizard.png"], ["feat", "Feats", "/emblems/monk.png"],
  ["optionalfeature", "Options", "/emblems/ranger.png"], ["baseitem", "Weapons & armour", "/emblems/barbarian.png"],
  ["item", "Magic items", "/emblems/artificer.png"], ["classFeature", "Class features", "/emblems/rogue.png"],
];

/**
 * The home screen, as four doors: Games, Library (by system: D&D 5e's compendium, bestiary and rulebooks),
 * Calíope settings (skills, models, settings) and the Muse.
 */
export default function Home({ view, onView, menuKey, onPlay, onEdit, onCreate, onImport, onLibrary, onBestiary, onRulebooks, onSkills, onModels,
  onSettings, onMuse, onMusic, onTour, lastGame, onContinue }) {
  const [counts, setCounts] = useState({});
  useEffect(() => {
    api.scenarios().then((c) => setCounts((x) => ({ ...x, cards: c.length }))).catch(() => {});
    api.libraryStatus().then((s) => setCounts((x) => ({ ...x, library: s?.info?.entries || s?.entries }))).catch(() => {});
  }, [menuKey]);

  if (view === "games") {
    return (
      <div className="hub-page">
        <Crumbs trail={[["Home", "hub"], ["Games"]]} onView={onView} />
        <MainMenu refreshKey={menuKey} onPlay={onPlay} onEdit={onEdit} onCreate={onCreate} onImport={onImport} />
      </div>
    );
  }
  if (view === "library") {
    return (
      <div className="hub-page">
        <Crumbs trail={[["Home", "hub"], ["Library"]]} onView={onView} />
        <h2 className="hub-heading">Systems</h2>
        <section className="system-card">
          <div className="system-head">
            <img className="hub-art small" src="/emblems/sorcerer.png" alt="" />
            <div className="grow">
              <h3>Dungeons &amp; Dragons 5e</h3>
              <div className="muted small">{`2014 and 2024 rules · ${counts.library ? `${counts.library} entries` : "the SRD built in, plus your own files"}`}</div>
            </div>
          </div>
          <div className="hub-row">
            <Tile art="/emblems/wizard.png" title="Compendium" text="Classes, races, spells, items, feats…" onClick={() => onLibrary()} />
            <Tile art="/emblems/race-goblin.png" title="Bestiary" text="Monster sheets for fights" onClick={onBestiary} />
            <Tile art="/emblems/cleric.png" title="Compendium" text="Rule sets and rulebooks the Aedo reads" onClick={onRulebooks} />
          </div>
          <h4 className="hub-sub">Compendium folders</h4>
          <div className="folder-grid">
            {FOLDERS.map(([type, label, art]) => (
              <button key={type} type="button" className="folder" onClick={() => onLibrary(type)}>
                <img src={art} alt="" /><span>{label}</span>
              </button>
            ))}
          </div>
        </section>
        <section className="system-card quiet">
          <div className="system-head">
            <img className="hub-art small" src="/emblems/class.png" alt="" />
            <div className="grow">
              <h3>Other systems</h3>
              <div className="muted small">Tormenta20, Vampire, Call of Cthulhu… their rulebooks and sheets live in Rulebooks for now.</div>
            </div>
            <button type="button" className="btn small" onClick={onRulebooks}>Open Rulebooks</button>
          </div>
        </section>
      </div>
    );
  }
  if (view === "settings") {
    return (
      <div className="hub-page">
        <Crumbs trail={[["Home", "hub"], ["Calíope settings"]]} onView={onView} />
        <div className="hub-grid three">
          <Tile art="/emblems/druid.png" title="Skills" text="Extra know-how the Aedo can use" onClick={onSkills} />
          <Tile art="/emblems/artificer.png" title="Models" text="Download and manage the AI models" onClick={onModels} />
          <Tile art="/emblems/class.png" title="Settings" text="Model server, language, voice, fights…" onClick={onSettings} />
          <Tile art="/emblems/bard.png" title="Music" text="The jukebox's tracks" onClick={onMusic} />
          <Tile art="/emblems/paladin.png" title="Guided tour" text="A walk through Calíope" onClick={onTour} />
        </div>
      </div>
    );
  }
  return (
    <div className="hub-page">
      {lastGame && (
        <button type="button" className="continue-banner" onClick={onContinue}>
          <span className="muted small">Continue</span>
          <strong>{lastGame.title || "your last game"}</strong>
          <span className="continue-go">▶</span>
        </button>
      )}
      <div className="hub-grid">
        <Tile big art="/emblems/sorcerer.png" title="Games" text="Your cards: play, edit, create, import" badge={counts.cards ? `${counts.cards} cards` : ""} onClick={() => onView("games")} />
        <Tile big art="/emblems/wizard.png" title="Library" text="Systems: D&D 5e compendium, bestiary, rulebooks" onClick={() => onView("library")} />
        <Tile big art="/emblems/artificer.png" title="Calíope settings" text="Skills, models, settings, music" onClick={() => onView("settings")} />
        <Tile big art="/emblems/bard.png" title="The Muse" text="Write stories and cards together" onClick={onMuse} />
      </div>
    </div>
  );
}
