import React from "react";

const sign = (n) => (n > 0 ? `+${n}` : `${n}`);
const modsText = (mods) => Object.entries(mods || {}).map(([k, v]) => `${k} ${sign(v)}`).join(", ");

/** One part as a dropdown label: "Hand's mace · 3 PF · Heavy · Melee +1, Handling -1 · Lv4". */
function partLabel(item, points) {
  points = points.length > 8 ? points.split(/\s+/).map((w) => w[0]).join("").toUpperCase() : points; // Frame Points -> FP
  return [item.name, `${item.cost} ${points}`, item.weight, modsText(item.mods), item.level ? `Lv${item.level}` : ""].filter(Boolean).join(" · ");
}

/**
 * A card's own sheet kept by the app (Black Sheep: Pilot Level, XP, Credits, Tier, Integrity, and the mech loadout).
 * Stats are edited in place; each slot picks a part from the card's catalog; the app checks the budget and level
 * gates and works out the totals (points used, net modifiers, speed, maximums).
 */
export default function SystemsSheet({ systems, state, computed, onValue, onPart, error, busy, creating = false }) {
  if (!systems || !state) return null;
  const lo = systems.loadout;
  const values = state.values || {};
  const got = computed || {};
  const level = lo?.level_stat ? Number(values[lo.level_stat] || 0) : 99;
  const owned = !creating && Array.isArray(state.owned) ? new Set(state.owned) : null; // in play: only parts you own
  return (
    <div className="systems-sheet">
      {(systems.stats || []).length > 0 && (
        <div className="sys-stats">
          {systems.stats.map((s) => {
            const top = got.max?.[s.key];
            return (
              <label key={s.key} className="sys-stat" title={s.note || ""}>
                <span className="lbl">{s.key}{top != null ? <span className="muted tiny">{` / ${top}`}</span> : null}</span>
                {s.kind === "choice" ? (
                  <select className="field" value={values[s.key] ?? ""} disabled={busy} onChange={(e) => onValue(s.key, e.target.value)}>
                    {(s.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input className={`field ${s.kind === "number" ? "num" : ""}`} value={values[s.key] ?? ""} disabled={busy}
                    onChange={(e) => onValue(s.key, s.kind === "number" ? e.target.value.replace(/[^\d-]/g, "") : e.target.value)} />
                )}
              </label>
            );
          })}
        </div>
      )}
      {lo && (
        <div className="sys-loadout">
          <div className="row gap center wrap">
            <strong>{lo.name || "Loadout"}</strong>
            {got.budget != null && (
              <span className={`pill ${got.used > got.budget ? "bad" : "on"}`}>{`${lo.points} ${got.used}/${got.budget}`}</span>
            )}
            {got.speed && <span className="pill">{`Speed ${got.speed} (${got.heavy} ${lo.speed?.weight || ""})`}</span>}
          </div>
          {got.budget != null && <span className="tracker-bar wide sys-bar"><span style={{ width: `${Math.min(100, Math.round((got.used / Math.max(1, got.budget)) * 100))}%` }} /></span>}
          <div className="sys-net">
            {Object.entries(got.mods || {}).map(([k, v]) => (
              <span key={k} className={`sys-mod ${v > 0 ? "up" : v < 0 ? "down" : ""}`}><span className="muted tiny">{k}</span><strong>{sign(v)}</strong></span>
            ))}
          </div>
          {(lo.slots || []).map((sl) => {
            const current = state.loadout?.[sl.key] || "";
            const item = (lo.catalog || []).find((i) => i.name === current);
            const fits = (lo.catalog || []).filter((i) => !sl.accepts?.length || sl.accepts.includes(i.kind));
            return (
              <div className="sys-slot" key={sl.key}>
                <span className="lbl">{sl.key}</span>
                <select className="field" value={current} disabled={busy} onChange={(e) => onPart(sl.key, e.target.value)}>
                  {!item && <option value="">{current || "—"}</option>}
                  {fits.map((i) => (
                    <option key={i.name} value={i.name} disabled={(!i.start && i.level > level) || (owned && !owned.has(i.name))}>
                      {partLabel(i, lo.points)}{!i.start && i.level > level ? " 🔒" : owned && !owned.has(i.name) ? " · not owned" : ""}
                    </option>
                  ))}
                </select>
                {item && (item.effect || item.source) && (
                  <div className="muted tiny">{[item.effect, item.range && `${item.range} range`, item.source, item.price].filter(Boolean).join(" · ")}</div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {error && <div className="error-text small">{error}</div>}
    </div>
  );
}


const SOLD_ONLY = /wager|reward|mission|legendar|bount|quest|apost|recompens/i;

/**
 * In play, under the sheet: the shop (parts you own, buying with the card's money), the mission board (this week's
 * jobs drafted by the Aedo; accept, done, failed; the log), the ranking (duel results) and the ladder (romance steps).
 */
export function SystemsPanels({ view, onAct, busy }) {
  const { systems: sys, state: st } = view;
  const [buyPick, setBuyPick] = React.useState("");
  const [rival, setRival] = React.useState("");
  const lo = sys.loadout;
  const owned = new Set(st.owned || []);
  const level = lo?.level_stat ? Number(st.values?.[lo.level_stat] || 0) : 99;
  const cur = sys.shop?.currency;
  const forSale = (lo?.catalog || []).filter((i) => !owned.has(i.name) && !(i.source && SOLD_ONLY.test(i.source) && !/market|shop|workshop|lise/i.test(i.source)));
  const rk = st.ranking;
  return (
    <div className="systems-panels">
      {lo && sys.shop && (
        <section className="sys-panel">
          <div className="sys-panel-head"><strong>🛒 Shop</strong><span className="muted tiny">{`${cur ? `${cur}: ${st.values?.[cur] ?? 0} · ` : ""}${owned.size} parts owned`}</span></div>
          <div className="row gap center wrap">
            <select className="field grow" value={buyPick} onChange={(e) => setBuyPick(e.target.value)} disabled={busy}>
              <option value="">Choose a part to buy…</option>
              {forSale.map((i) => (
                <option key={i.name} value={i.name} disabled={i.level > level}>
                  {`${i.name} · ${view.prices?.[i.name] != null ? `${view.prices[i.name]} ${cur || ""}` : i.price || "?"}${i.level > level ? ` · 🔒 Lv${i.level}` : ""}`}
                </option>
              ))}
            </select>
            <button type="button" className="btn small primary" disabled={busy || !buyPick} onClick={() => { onAct({ buy: buyPick }); setBuyPick(""); }}>Buy</button>
          </div>
          <div className="muted tiny">{`Owned: ${[...owned].join(", ") || "none"}. Parts from wagers and missions are won in the story, not bought.`}</div>
        </section>
      )}
      {sys.board && (
        <section className="sys-panel">
          <div className="sys-panel-head"><strong>📋 Bounty board</strong>
            <button type="button" className="btn small" disabled={busy} onClick={() => onAct({ board: "new" })}
              title="The Aedo writes this week's jobs from the card's rules">{view.board_due ? "📋 Post this week's jobs" : "↻ New jobs"}</button></div>
          {(st.board?.jobs || []).length === 0 && <div className="muted tiny">No jobs posted yet.</div>}
          {(st.board?.jobs || []).map((j) => (
            <div className={`sys-job ${j.status}`} key={j.id}>
              <div className="grow small"><strong>{j.title}</strong>
                <div className="muted tiny">{`Grade ${j.grade} · pays ${j.pay}${j.extra ? ` + ${j.extra}` : ""}${j.min_level ? ` · Level ${j.min_level}+` : ""}${j.status === "active" ? " · ACTIVE" : ""}`}</div></div>
              {j.status === "open"
                ? <button type="button" className="btn small" disabled={busy} onClick={() => onAct({ job: j.id, act: "accept" })}>Accept</button>
                : <>
                    <button type="button" className="btn small primary" disabled={busy} onClick={() => onAct({ job: j.id, act: "done" })}>Done</button>
                    <button type="button" className="btn small ghost" disabled={busy} onClick={() => onAct({ job: j.id, act: "fail" })}>Failed</button>
                  </>}
            </div>
          ))}
          {(st.board?.log || []).length > 0 && (
            <details><summary className="small">Mission log</summary>{st.board.log.map((l, i) => <div className="muted tiny" key={i}>{l}</div>)}</details>
          )}
        </section>
      )}
      {rk && (
        <section className="sys-panel">
          <div className="sys-panel-head"><strong>🏆 Ranking</strong><span className="muted tiny">{rk.player ? `You: #${rk.player}` : "You: unranked"}</span></div>
          <ol className="sys-rank">{rk.order.map((n) => <li key={n} className={n === "@you" ? "you" : ""}>{n === "@you" ? "You" : n}{rk.protected?.[n] >= view.day ? <span className="muted tiny">{` · protected until day ${rk.protected[n]}`}</span> : null}</li>)}</ol>
          <div className="row gap center wrap">
            <select className="field grow" value={rival} onChange={(e) => setRival(e.target.value)} disabled={busy}>
              <option value="">Duel result against…</option>
              {rk.order.filter((n) => n !== "@you").map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <button type="button" className="btn small primary" disabled={busy || !rival} onClick={() => { onAct({ duel: rival, won: true }); setRival(""); }}>Won</button>
            <button type="button" className="btn small" disabled={busy || !rival} onClick={() => { onAct({ duel: rival, won: false }); setRival(""); }}>Lost</button>
          </div>
          {(rk.duels || []).length > 0 && <div className="muted tiny">{`Last duels: ${rk.duels.map((d) => `day ${d.day} ${d.won ? "beat" : "lost to"} ${d.opponent}`).join(" · ")}`}</div>}
        </section>
      )}
      {sys.steps && st.steps && (
        <section className="sys-panel">
          <div className="sys-panel-head"><strong>{`💞 ${sys.steps.name}`}</strong><span className="muted tiny">{sys.steps.labels.map((l, i) => `${i + 1} ${l}`).join(" → ")}</span></div>
          {Object.entries(st.steps).map(([p, n]) => (
            <div className="row gap center sys-step" key={p}>
              <span className="grow small">{p}</span>
              <span className="muted tiny">{n ? sys.steps.labels[n - 1] : "—"}</span>
              <span className="steps-dots">{sys.steps.labels.map((_, i) => <span key={i} className={i < n ? "on" : ""} />)}</span>
              <button type="button" className="icon-btn" disabled={busy || n <= 0} onClick={() => onAct({ step: p, delta: -1 })} title="One step down">−</button>
              <button type="button" className="icon-btn" disabled={busy || n >= sys.steps.labels.length} onClick={() => onAct({ step: p, delta: 1 })} title="One step up (once a day)">＋</button>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
