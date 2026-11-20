import React from "react";

// Small, safe markdown renderer (no HTML injection): paragraphs, **bold**, *italic*, ~~strike~~,
// `code`, fenced code, headings, lists, quotes and rules. Enough for roleplay narration.

const INLINE = /(`[^`\n]+`|\*\*[^*\n]+?\*\*|~~[^~\n]+?~~|\*[^*\n]+?\*)/g;

function inlineBase(text, key) {
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

// Story mode: "speech" and 'thoughts' get their own colours; the rest (narration and *actions*) stays grey.
// A thought may hold apostrophes inside words ('He's hiding something,').
const VOICE = /("[^"\n]+"|\u201c[^\u201d\n]+\u201d|\u2018[^\u2019\n]+\u2019|(?<![\w'])'(?:[^'\n]|'(?=\w))+'(?!\w))/g;

function storyInline(text, key) {
  return text.split(VOICE).map((part, i) => {
    if (!part) return null;
    const k = `${key}-v${i}`;
    if (/^["\u201c]/.test(part) && part.length > 2) return <span key={k} className="say">{inline(part, k)}</span>;
    if (/^['\u2018]/.test(part) && part.length > 2) return <span key={k} className="think">{inline(part, k)}</span>;
    return <React.Fragment key={k}>{inline(part, k)}</React.Fragment>;
  });
}

const inline = inlineBase;

const isFence = (l) => /^```/.test(l);
const isHeading = (l) => /^#{1,4}\s+/.test(l);
const isRule = (l) => /^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(l);
const isQuote = (l) => /^>\s?/.test(l);
const isItem = (l) => /^\s*([-*+]|\d+\.)\s+/.test(l);
const startsBlock = (l) => isFence(l) || isHeading(l) || isRule(l) || isQuote(l) || isItem(l);

export const Markdown = React.memo(function Markdown({ text, story = false }) {
  const inline = story ? storyInline : inlineBase;
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
  return <div className={story ? "md story" : "md"}>{blocks}</div>;
});
