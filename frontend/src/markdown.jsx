import React from "react";

// Small, safe markdown renderer (no HTML injection): paragraphs, **bold**, *italic*, ~~strike~~,
// `code`, fenced code, headings, lists, quotes and rules. Enough for roleplay narration.

const INLINE = /(`[^`\n]+`|\*\*[^*\n]+?\*\*|~~[^~\n]+?~~|\*[^*\n]+?\*)/g;

function inline(text, key) {
  return text.split(INLINE).map((part, i) => {
    if (!part) return null;
    const k = `${key}-${i}`;
    if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) return <code key={k}>{part.slice(1, -1)}</code>;
    if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) return <strong key={k}>{inline(part.slice(2, -2), k)}</strong>;
    if (part.length > 4 && part.startsWith("~~") && part.endsWith("~~")) return <del key={k}>{inline(part.slice(2, -2), k)}</del>;
    if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) return <em key={k}>{inline(part.slice(1, -1), k)}</em>;
    return <React.Fragment key={k}>{part}</React.Fragment>;
  });
}

const isFence = (l) => /^```/.test(l);
const isHeading = (l) => /^#{1,4}\s+/.test(l);
const isRule = (l) => /^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(l);
const isQuote = (l) => /^>\s?/.test(l);
const isItem = (l) => /^\s*([-*+]|\d+\.)\s+/.test(l);
const startsBlock = (l) => isFence(l) || isHeading(l) || isRule(l) || isQuote(l) || isItem(l);

export function Markdown({ text }) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  let n = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `b${n++}`;
    if (!line.trim()) {
      i++;
    } else if (isFence(line)) {
      const body = [];
      i++;
      while (i < lines.length && !isFence(lines[i])) body.push(lines[i++]);
      i++;
      blocks.push(<pre key={key}><code>{body.join("\n")}</code></pre>);
    } else if (isHeading(line)) {
      const m = line.match(/^(#{1,4})\s+(.*)$/);
      const Tag = `h${m[1].length + 2}`;
      blocks.push(<Tag key={key}>{inline(m[2], key)}</Tag>);
      i++;
    } else if (isRule(line)) {
      blocks.push(<hr key={key} />);
      i++;
    } else if (isQuote(line)) {
      const body = [];
      while (i < lines.length && isQuote(lines[i])) body.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push(<blockquote key={key}>{inline(body.join("\n"), key)}</blockquote>);
    } else if (isItem(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items = [];
      while (i < lines.length && isItem(lines[i])) items.push(lines[i++].replace(/^\s*([-*+]|\d+\.)\s+/, ""));
      const List = ordered ? "ol" : "ul";
      blocks.push(<List key={key}>{items.map((t, j) => <li key={j}>{inline(t, `${key}-${j}`)}</li>)}</List>);
    } else {
      const body = [];
      while (i < lines.length && lines[i].trim() && !(body.length && startsBlock(lines[i]))) body.push(lines[i++]);
      blocks.push(
        <p key={key}>
          {body.map((t, j) => (
            <React.Fragment key={j}>
              {j > 0 && <br />}
              {inline(t, `${key}-${j}`)}
            </React.Fragment>
          ))}
        </p>
      );
    }
  }
  return <div className="md">{blocks}</div>;
}
