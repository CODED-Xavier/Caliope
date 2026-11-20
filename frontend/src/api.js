// Thin wrapper around the backend REST + streaming API. All URLs are relative (same origin).

async function errorMessage(res) {
  let detail = res.statusText || `HTTP ${res.status}`;
  try {
    const data = await res.json();
    if (data && data.detail) detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
  } catch {
    /* not JSON */
  }
  return detail;
}

async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

/** POST and read a Server-Sent-Events stream, calling onEvent for every event. */
export async function streamPost(path, body, onEvent, signal) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
    signal,
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data:")) {
          try {
            onEvent(JSON.parse(line.slice(5).trim()));
          } catch {
            /* ignore malformed event */
          }
        }
      }
    }
  }
}

export const api = {
  health: () => request("GET", "/api/health"),
  models: () => request("GET", "/api/models"),
  settings: () => request("GET", "/api/settings"),
  saveSettings: (values) => request("PUT", "/api/settings", values),

  scenarios: () => request("GET", "/api/scenarios"),
  scenario: (id) => request("GET", `/api/scenarios/${id}`),
  createScenario: (data) => request("POST", "/api/scenarios", data),
  updateScenario: (id, data) => request("PUT", `/api/scenarios/${id}`, data),
  deleteScenario: (id) => request("DELETE", `/api/scenarios/${id}`),
  generateScenario: (body) => request("POST", "/api/scenarios/generate", body),

  async uploadPicture(file) {
    const res = await fetch("/api/uploads", { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file });
    if (!res.ok) throw new Error(await errorMessage(res));
    return res.json();
  },
  rulebooks: () => request("GET", "/api/rulebooks"),
  async uploadRulebook(file, name, system) {
    const qs = new URLSearchParams({ name, system, filename: file.name });
    const res = await fetch(`/api/rulebooks?${qs}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
    if (!res.ok) throw new Error(await errorMessage(res));
    return res.json();
  },
  updateRulebook: (id, body) => request("PATCH", `/api/rulebooks/${id}`, body),
  deleteRulebook: (id) => request("DELETE", `/api/rulebooks/${id}`),
  searchRulebooks: (q, ids = []) => request("GET", `/api/rulebooks/search?${new URLSearchParams({ q, ids: ids.join(",") })}`),
  draftField: (field, card, hint = "") => request("POST", "/api/drafts/card-field", { field, card, hint }),
  draftPlayer: (scenarioId, player) => request("POST", "/api/drafts/player", { scenario_id: scenarioId, player }),
  fork: (id, messageId) => request("POST", `/api/conversations/${id}/fork`, { message_id: messageId }),
  exportChatUrl: (id) => `/api/conversations/${id}/export`,
  previewCard: (card) => request("POST", "/api/cards/preview", { card }),
  importCard: (card, skip = [], name = "") => request("POST", "/api/cards/import", { card, skip, name }),
  exportCardUrl: (id) => `/api/scenarios/${id}/export`,
  continueUrl: (id) => `/api/conversations/${id}/continue`,

  conversations: () => request("GET", "/api/conversations"),
  conversation: (id) => request("GET", `/api/conversations/${id}`),
  createConversation: (body) => request("POST", "/api/conversations", body),
  renameConversation: (id, title) => request("PATCH", `/api/conversations/${id}`, { title }),
  deleteConversation: (id) => request("DELETE", `/api/conversations/${id}`),
  undo: (id) => request("POST", `/api/conversations/${id}/undo`),
  editMessage: (messageId, content) => request("PATCH", `/api/messages/${messageId}`, { content }),
  rewind: (id, messageId, inclusive) => request("POST", `/api/conversations/${id}/rewind`, { message_id: messageId, inclusive }),

  setPinned: (id, text) => request("PUT", `/api/conversations/${id}/pinned`, { text }),

  patchState: (id, patch) => request("PATCH", `/api/conversations/${id}/state`, patch),
  addNpc: (id, body) => request("POST", `/api/conversations/${id}/npcs`, body),
  updateNpc: (npcId, body) => request("PATCH", `/api/npcs/${npcId}`, body),
  deleteNpc: (npcId) => request("DELETE", `/api/npcs/${npcId}`),

  memories: (id) => request("GET", `/api/conversations/${id}/memories`),
  addMemory: (id, text, importance = 4) => request("POST", `/api/conversations/${id}/memories`, { text, importance }),
  deleteMemory: (memId) => request("DELETE", `/api/memories/${memId}`),

  roll: (expression) => request("POST", "/api/dice/roll", { expression }),

  skills: () => request("GET", "/api/skills"),
  suggestSkills: (text, k = 3) => request("POST", "/api/skills/suggest", { text, k }),
  installSkill: (source) => request("POST", "/api/skills/install", { source }),
  toggleSkill: (name, enabled) => request("PATCH", `/api/skills/${encodeURIComponent(name)}`, { enabled }),
  deleteSkill: (name) => request("DELETE", `/api/skills/${encodeURIComponent(name)}`),
  async uploadSkillZip(file) {
    const res = await fetch("/api/skills/install-zip", {
      method: "POST",
      headers: { "Content-Type": "application/zip" },
      body: file,
    });
    if (!res.ok) throw new Error(await errorMessage(res));
    return res.json();
  },
};
