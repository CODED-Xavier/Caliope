import React, { useEffect, useState } from "react";
import HelpTip from "./HelpTip.jsx";
import { api } from "../api.js";

const csv = (list) => (list || []).join(", ");
const parseCsv = (t) => t.split(",").map((x) => x.trim()).filter(Boolean);

/** Card editor: the world's calendar (week days, months, year, era, starting date and hour). */
export function CalendarEditor({ value, onChange }) {
  const c = { enabled: false, weekdays: [], months: [], month_word: "month", year_word: "year", era: "", hours_per_day: 24,
    start: { year: 1, month: 1, day: 1, hour: 8, minute: 0, weekday: 0 }, ...(value || {}) };
  const [presets, setPresets] = useState(null);
  const [preview, setPreview] = useState("");
  const set = (k, v) => onChange({ ...c, [k]: v });
  const setStart = (k, v) => set("start", { ...c.start, [k]: v });
  const num = (v, d = 0) => { const n = parseInt(v, 10); return Number.isNaN(n) ? d : n; };

  useEffect(() => { api.calendarPresets().then(setPresets).catch(() => {}); }, []);
  useEffect(() => {
    if (!c.enabled) return undefined;
    const t = setTimeout(() => api.calendarPreview(c).then((r) => setPreview(`${r.starts} · a ${c.year_word || "year"} has ${r.year_days} days`)).catch((e) => setPreview(e.message)), 350);
    return () => clearTimeout(t);
  }, [JSON.stringify(c)]); // eslint-disable-line

  const usePreset = (key) => {
    const p = presets?.[key];
    if (p) onChange({ ...c, ...JSON.parse(JSON.stringify(p)), preset: key, enabled: true, start: { ...c.start, month: 1, day: 1, weekday: 0 } });
  };
  const months = c.months.length ? c.months : [];

  return (
    <details>
      <summary className="muted small">Calendar <HelpTip id="calendar" /> {c.enabled && <span className="tiny">(on)</span>}</summary>
      <label className="check small"><input type="checkbox" checked={!!c.enabled} onChange={(e) => (e.target.checked && !c.months.length ? usePreset("earth") : set("enabled", e.target.checked))} />
        The app keeps the date and the hour (days pass only when you play them or wait)</label>
      {c.enabled && (
        <div className="cal-editor">
          <div className="row gap center">
            <span className="small">Start from:</span>
            <button className="btn small" onClick={() => usePreset("earth")}>Our calendar</button>
            <button className="btn small" onClick={() => usePreset("fantasy")}>Fantasy calendar</button>
          </div>
          <label className="lbl">Week days, in order (comma separated)</label>
          <input className="field" defaultValue={csv(c.weekdays)} key={`wd-${c.preset}-${c.weekdays.length}`} onBlur={(e) => set("weekdays", parseCsv(e.target.value))} />
          <label className="lbl">Months and their days</label>
          <div className="cal-months">
            {months.map((m, i) => (
              <div key={i} className="row gap center">
                <span className="muted tiny cal-num">{i + 1}</span>
                <input className="field cal-name" value={m.name} onChange={(e) => set("months", months.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                <input className="field cal-sm" title="Days" value={m.days} onChange={(e) => set("months", months.map((x, j) => (j === i ? { ...x, days: num(e.target.value, 1) } : x)))} />
                <button className="icon-btn" title="Remove month" onClick={() => set("months", months.filter((_, j) => j !== i))}>✕</button>
              </div>
            ))}
            <button className="btn small" onClick={() => set("months", [...months, { name: `Month ${months.length + 1}`, days: 30 }])}>＋ Month</button>
          </div>
          <div className="cal-grid">
            <label className="lbl">A month is called<input className="field" value={c.month_word} onChange={(e) => set("month_word", e.target.value)} placeholder="month, moon…" /></label>
            <label className="lbl">A year is called<input className="field" value={c.year_word} onChange={(e) => set("year_word", e.target.value)} placeholder="year, cycle…" /></label>
            <label className="lbl">Era (after the year)<input className="field" value={c.era} onChange={(e) => set("era", e.target.value)} placeholder="AE, of the Crown…" /></label>
            <label className="lbl">Hours in a day<input className="field num" value={c.hours_per_day} onChange={(e) => set("hours_per_day", num(e.target.value, 24))} /></label>
            <label className="lbl">Weather (rolled by the app)
              <select className="field" value={c.climate || "temperate"} onChange={(e) => set("climate", e.target.value)}>
                <option value="temperate">Temperate (four seasons)</option>
                <option value="cold">Cold (long winters)</option>
                <option value="warm">Warm (mild winters)</option>
                <option value="tropical">Tropical (hot, heavy rains)</option>
                <option value="dry">Dry (desert, no rain)</option>
                <option value="none">Off (the AI decides)</option>
              </select>
            </label>
          </div>
          <label className="lbl">The story starts on</label>
          <div className="row gap center wrap cal-start">
            <select className="field" value={c.start.weekday} onChange={(e) => setStart("weekday", num(e.target.value))}>
              {c.weekdays.map((w, i) => <option key={i} value={i}>{w}</option>)}
            </select>
            <input className="field cal-sm" title="Day" value={c.start.day} onChange={(e) => setStart("day", num(e.target.value, 1))} />
            <select className="field" value={c.start.month} onChange={(e) => setStart("month", num(e.target.value, 1))}>
              {months.map((m, i) => <option key={i} value={i + 1}>{m.name}</option>)}
            </select>
            <input className="field cal-sm" title="Year" value={c.start.year} onChange={(e) => setStart("year", num(e.target.value, 1))} />
            <span className="small">at</span>
            <input className="field cal-sm" title="Hour" value={c.start.hour} onChange={(e) => setStart("hour", num(e.target.value, 8))} />
            <span>:</span>
            <input className="field cal-sm" title="Minute" value={String(c.start.minute).padStart(2, "0")} onChange={(e) => setStart("minute", num(e.target.value))} />
          </div>
          {preview && <div className="muted small">📅 {preview}</div>}
        </div>
      )}
    </details>
  );
}

/** Journal: today's date, appointments, and how to let time pass. */
export function CalendarBox({ convId, state, onState }) {
  const [text, setText] = useState("");
  const [when, setWhen] = useState("");
  const [err, setErr] = useState("");
  const add = async (e) => {
    e.preventDefault(); setErr("");
    try { onState(await api.addEvent(convId, text.trim(), when.trim())); setText(""); setWhen(""); } catch (x) { setErr(x.message); }
  };
  return (
    <div className="cal-box">
      <div className="section-title">Calendar <HelpTip id="calendar" /></div>
      <div className="card small">📅 {state.date_label}</div>
      {(state.events || []).length > 0 && (
        <div className="mem-list">
          {state.events.map((ev) => (
            <div className="mem" key={ev.id}>
              <div className="grow small">{ev.text}<div className="muted tiny">{ev.date || ""}</div></div>
              <button className="icon-btn" title="Remove" onClick={() => api.deleteEvent(convId, ev.id).then(onState).catch((x) => setErr(x.message))}>✕</button>
            </div>
          ))}
        </div>
      )}
      <form className="row gap" onSubmit={add}>
        <input className="field grow" placeholder="Appointment…" value={text} onChange={(e) => setText(e.target.value)} />
        <input className="field cal-when" placeholder="when (Sunday, in 3 days)" value={when} onChange={(e) => setWhen(e.target.value)} />
        <button className="btn small" type="submit" disabled={!text.trim() || !when.trim()}>Add</button>
      </form>
      {err && <div className="error-text small">{err}</div>}
      <div className="muted tiny">Time passes as you play. To skip ahead: <code>/wait 2 hours</code>, <code>/wait until Sunday</code>, or write it (“I sleep until morning”).</div>
    </div>
  );
}
