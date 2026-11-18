import React from "react";
import { KIND_INFO } from "../utils.js";

/** Two big selectable cards: Roleplay or Adventure. */
export default function KindPicker({ value, onChange }) {
  return (
    <div className="kind-picker">
      {["roleplay", "adventure"].map((k) => (
        <button type="button" key={k} className={`kind ${value === k ? "active" : ""}`} onClick={() => onChange(k)} aria-pressed={value === k}>
          <span className="kind-icon">{KIND_INFO[k].icon}</span>
          <span className="kind-title">{KIND_INFO[k].title}</span>
          <span className="muted small">{KIND_INFO[k].text}</span>
        </button>
      ))}
    </div>
  );
}
