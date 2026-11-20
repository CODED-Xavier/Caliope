import React from "react";
import { portraitSrc } from "../portraits.js";

// How each terrain square looks. Keep in sync with backend/app/maps.py.
export const TILE_STYLE = {
  ".": { fill: "transparent", label: "Floor / grass" },
  ",": { fill: "#9db8b0", label: "Mud / shallow water (difficult)" },
  '"': { fill: "#8db87a", glyph: "🌿", label: "Bushes (difficult, cover)" },
  "#": { fill: "#5f5a54", label: "Wall (blocks)" },
  "~": { fill: "#4a86c5", label: "Deep water (blocks)" },
  "T": { fill: "#6f9e5f", glyph: "🌲", label: "Tree (blocks, cover)" },
  "R": { fill: "#9a958d", glyph: "🪨", label: "Rock (blocks, cover)" },
  "B": { fill: "#a77d4f", glyph: "📦", label: "Barrel / crate / table (blocks, cover)" },
  "D": { fill: "#c39a62", glyph: "🚪", label: "Door" },
};
export const SIDE_COLOR = { player: "var(--good)", ally: "#4a8fd8", enemy: "var(--bad)" };
const initials = (name) => name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

/**
 * A battle map: terrain squares (+ an optional picture underneath) and tokens.
 * onCell(x, y) is called on click; onCellEnter(x, y) while the mouse moves (used for painting and distances).
 */
export default function BattleMap({ w, h, tiles = [], background = "", tokens = [], selected, onCell, onCellEnter, onToken, onLeave, cell = 30, className = "" }) {
  const bg = background ? portraitSrc(background) : "";
  return (
    <svg viewBox={`0 0 ${w * cell} ${h * cell}`} className={`battle-grid ${className}`} onMouseLeave={onLeave}>
      {bg && <image href={bg} x="0" y="0" width={w * cell} height={h * cell} preserveAspectRatio="xMidYMid slice" opacity="0.85" />}
      {Array.from({ length: w * h }, (_, i) => {
        const x = i % w, y = Math.floor(i / w);
        const ch = tiles[y]?.[x] || ".";
        const st = TILE_STYLE[ch] || TILE_STYLE["."];
        return (
          <g key={i} onMouseDown={(e) => { e.preventDefault(); onCell?.(x, y, e); }} onMouseEnter={(e) => onCellEnter?.(x, y, e)}>
            <rect x={x * cell} y={y * cell} width={cell} height={cell} className="grid-cell"
              style={{ fill: bg && ch === "." ? "transparent" : st.fill, fillOpacity: bg && ch !== "." ? 0.75 : 1 }} />
            {st.glyph && <text x={x * cell + cell / 2} y={y * cell + cell / 2 + 5} textAnchor="middle" fontSize={cell * 0.5} pointerEvents="none">{st.glyph}</text>}
          </g>
        );
      })}
      {tokens.map((c) => (
        <g key={c.id} transform={`translate(${c.x * cell + cell / 2},${c.y * cell + cell / 2})`} className="token"
          onMouseDown={(e) => { e.stopPropagation(); onToken?.(c.id); }}>
          <circle r={cell * 0.42} fill={c.hp > 0 ? SIDE_COLOR[c.side] : "var(--muted)"} stroke={c.id === selected ? "var(--text)" : "#0006"}
            strokeWidth={c.id === selected ? 3 : 1} opacity={c.hp > 0 ? 1 : 0.45} />
          <text textAnchor="middle" dy="4" fontSize="11" fill="#fff" fontWeight="700" pointerEvents="none">{c.hp > 0 ? initials(c.name) : "✝"}</text>
        </g>
      ))}
    </svg>
  );
}
