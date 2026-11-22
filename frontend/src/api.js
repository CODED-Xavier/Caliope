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
  combatDefaults: (id, system) => request("GET", `/api/conversations/${id}/combat/defaults?system=${system}`),
  combatSuggest: (id, system) => request("POST", `/api/conversations/${id}/combat/suggest`, { system }),
  paintSceneMap: (id, kind = "", scene = "") => request("POST", `/api/conversations/${id}/adventure/paint-map`, { kind, scene }),
  combatPaintMap: (id, kind = "") => request("POST", `/api/conversations/${id}/combat/paint-map`, { kind }),
  combatEdit: (id, cid, patch) => request("PATCH", `/api/conversations/${id}/combat/${cid}`, patch),
  paintScene: (convId, messageId, reroll = false) => request("POST", `/api/conversations/${convId}/messages/${messageId}/scene-picture`, { reroll }),
  engine: () => request("GET", "/api/engine"),
  engineModels: () => request("GET", "/api/engine/models"),
  engineStart: () => request("POST", "/api/engine/start"),
  engineStop: () => request("POST", "/api/engine/stop"),
  engineDownload: () => request("POST", "/api/engine/download"),
  modelLibrary: () => request("GET", "/api/models/library"),
  searchModels: (q) => request("GET", `/api/models/search?q=${encodeURIComponent(q)}`),
  modelFiles: (repo) => request("GET", `/api/models/files?repo=${encodeURIComponent(repo)}`),
  downloadModel: (repo, file) => request("POST", "/api/models/download", { repo, file }),
  cancelDownload: (key) => request("POST", "/api/models/download/cancel", { key }),
  clearDownload: (key) => request("POST", "/api/models/download/clear", { key }),
  loadModel: (path, role) => request("POST", "/api/models/load", { path, role }),
  unloadModel: (role) => request("POST", "/api/models/unload", { role }),
  setModelActive: (path, active) => request("POST", "/api/models/active", { path, active }),
  deleteModel: (path) => request("POST", "/api/models/delete", { path }),
  addModelFolder: (path) => request("POST", "/api/models/folders", { path }),
  removeModelFolder: (path) => request("POST", "/api/models/folders/remove", { path }),
  browseModel: () => request("POST", "/api/models/browse"),
  cantos: (id) => request("GET", `/api/conversations/${id}/cantos`),
  closeCanto: (id, title) => request("POST", `/api/conversations/${id}/cantos/close`, { title }),
  renameCanto: (id, title) => request("PATCH", `/api/cantos/${id}`, { title }),
  recap: (id) => request("POST", `/api/conversations/${id}/recap`),
  async importAdventure(cardId, body, part = "", filename = "") {
    const qs = new URLSearchParams({ part, filename }).toString();
    const res = await fetch(`/api/scenarios/${cardId}/adventure/import?${qs}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body });
    if (!res.ok) throw new Error(await errorMessage(res));
    return res.json();
  },
  adventureScene: (id, scene) => request("POST", `/api/conversations/${id}/adventure/scene`, { scene }),
  adventureNoFight: (id, scene) => request("POST", `/api/conversations/${id}/adventure/no-fight`, { scene }),
  adventureXp: (id, scene) => request("POST", `/api/conversations/${id}/adventure/xp`, { scene }),
  bestiary: () => request("GET", "/api/bestiary"),
  bestiaryFind: (name) => request("GET", `/api/bestiary/find?name=${encodeURIComponent(name)}`),
  bestiarySave: (monster, oldId = "") => request("POST", "/api/bestiary", { monster, old_id: oldId }),
  bestiaryDelete: (id) => request("DELETE", `/api/bestiary/${id.split("/").map(encodeURIComponent).join("/")}`),
  bestiaryOpen: (book = "") => request("POST", "/api/bestiary/open", { book }),
  async bestiaryImport(body, replace = false, book = "") {
    const res = await fetch(`/api/bestiary/import?replace=${replace ? "true" : "false"}&book=${encodeURIComponent(book)}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body });
    if (!res.ok) throw new Error(await errorMessage(res));
    return res.json();
  },
  sheetTemplates: () => request("GET", "/api/sheet-templates"),
  setSheetTemplate: (id, text) => request("POST", `/api/conversations/${id}/sheet-template`, { text }),
  epilogue: (id) => request("POST", `/api/conversations/${id}/epilogue`),
  warm: (id) => request("POST", `/api/conversations/${id}/warm`),
  sheetFromMessage: (id, messageId) => request("POST", `/api/conversations/${id}/messages/${messageId}/sheet`),
  gallery: (id) => request("GET", `/api/conversations/${id}/gallery`),
  keepPicture: (id, messageId) => request("POST", `/api/conversations/${id}/gallery`, { message_id: messageId }),
  renamePicture: (id, title) => request("PATCH", `/api/gallery/${id}`, { title }),
  removePicture: (id) => request("DELETE", `/api/gallery/${id}`),
  researchFind: (query) => request("POST", "/api/research/find", { query }),
  museTalks: () => request("GET", "/api/muse"),
  museTalk: (id) => request("GET", `/api/muse/${id}`),
  museCreate: (title = "") => request("POST", "/api/muse", { title }),
  museDelete: (id) => request("DELETE", `/api/muse/${id}`),
  museUndo: (id) => request("POST", `/api/muse/${id}/undo`),
  mergeCharacters: (id, npcs) => request("POST", `/api/scenarios/${id}/npcs/merge`, { npcs }),
  cardFile: (card) => request("POST", "/api/cards/export", { card }),
  cardPicturesBrowse: (id) => request("POST", `/api/scenarios/${id}/pictures/browse`),
  cardPicturesScan: (id, folder) => request("POST", `/api/scenarios/${id}/pictures/scan`, { folder }),
  cardPicturesHome: (id) => request("GET", `/api/scenarios/${id}/pictures/home`),
  cardPicturesOpen: (id) => request("POST", `/api/scenarios/${id}/pictures/open`),
  cardPicturesImport: (id, folder = "") => request("POST", `/api/scenarios/${id}/pictures/import`, { folder }),
  cardPicturesApply: (id, folder, overrides) => request("POST", `/api/scenarios/${id}/pictures/apply`, { folder, overrides, update_games: true }),
  cardPicturesToR2: (id) => request("POST", `/api/scenarios/${id}/pictures/r2`),
  async importCaliope(file) {
    const res = await fetch("/api/cards/import-caliope", { method: "POST", headers: { "Content-Type": "application/zip" }, body: file });
    if (!res.ok) throw new Error(await errorMessage(res));
    return res.json();
  },
  hardware: () => request("GET", "/api/hardware"),
  correct: (text, language) => request("POST", "/api/correct", { text, language }),
  personas: () => request("GET", "/api/personas"),
  createPersona: (body) => request("POST", "/api/personas", body),
  updatePersona: (id, body) => request("PUT", `/api/personas/${id}`, body),
  deletePersona: (id) => request("DELETE", `/api/personas/${id}`),
  voice: () => request("GET", "/api/voice"),
  voiceInstall: (voice) => request("POST", "/api/voice/install", { voice }),
  voiceRemove: (voice) => request("POST", "/api/voice/remove", { voice }),
  backups: () => request("GET", "/api/backups"),
  backupNow: () => request("POST", "/api/backups/now"),
  openBackups: () => request("POST", "/api/backups/open"),
  music: () => request("GET", "/api/music"),
  async uploadMusic(file, name, tags = []) {
    const qs = new URLSearchParams({ name, tags: tags.join(",") });
    const res = await fetch(`/api/music/upload?${qs}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
    if (!res.ok) throw new Error(await errorMessage(res));
    return res.json();
  },
  addMusicLink: (body) => request("POST", "/api/music", body),
  updateMusic: (id, body) => request("PATCH", `/api/music/${id}`, body),
  deleteMusic: (id) => request("DELETE", `/api/music/${id}`),
  maps: () => request("GET", "/api/maps"),
  generateMap: (body) => request("POST", "/api/maps/generate", body),
  createMap: (body) => request("POST", "/api/maps", body),
  updateMap: (id, body) => request("PUT", `/api/maps/${id}`, body),
  deleteMap: (id) => request("DELETE", `/api/maps/${id}`),
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
  setPlayerLore: (convId, entries) => request("PUT", `/api/conversations/${convId}/player-lore`, { entries }),
  suggestPlayerLore: (convId, id) => request("POST", `/api/conversations/${convId}/player-lore/suggest`, { id }),
  calendarPresets: () => request("GET", "/api/calendar/presets"),
  calendarPreview: (cal) => request("POST", "/api/calendar/preview", cal),
  addEvent: (convId, text, when) => request("POST", `/api/conversations/${convId}/events`, { text, when }),
  deleteEvent: (convId, id) => request("DELETE", `/api/conversations/${convId}/events/${id}`),
  syncResources: (convId) => request("POST", `/api/conversations/${convId}/resources/sync`),
  suggestResources: (card) => request("POST", "/api/resources/suggest", { card }),
  createConversation: (body) => request("POST", "/api/conversations", body),
  renameConversation: (id, title) => request("PATCH", `/api/conversations/${id}`, { title }),
  deleteConversation: (id) => request("DELETE", `/api/conversations/${id}`),
  combatMove: (id, x, y) => request("POST", `/api/conversations/${id}/combat`, { action: "move", x, y }),
  draftCompanions: (cardId) => request("POST", `/api/scenarios/${cardId}/companions/draft`, {}),
  librarySearch: (type, q, edition, category = "", hidden = false) => request("GET", `/api/library/5e?type=${encodeURIComponent(type)}&q=${encodeURIComponent(q || "")}&edition=${edition}${category ? `&category=${category}` : ""}${hidden ? "&hidden=true" : ""}`),
  libraryChoices: () => request("GET", "/api/library/5e/choices"),
  saveLibraryChoices: (choices) => request("PUT", "/api/library/5e/choices", choices),
  libraryEntry: (type, source, name) => request("GET", `/api/library/5e/entry?type=${encodeURIComponent(type)}&source=${encodeURIComponent(source)}&name=${encodeURIComponent(name)}`),
  libraryStatus: () => request("GET", "/api/library/5e/status"),
  libraryReload: () => request("POST", "/api/library/5e/reload", {}),
  character5e: (id, who = "") => request("GET", `/api/conversations/${id}/character${who ? `?who=${encodeURIComponent(who)}` : ""}`),
  changeCharacter5e: (id, change, who = "") => request("PATCH", `/api/conversations/${id}/character${who ? `?who=${encodeURIComponent(who)}` : ""}`, { change }),
  builder5e: (id, who = "") => request("GET", `/api/conversations/${id}/character/builder${who ? `?who=${encodeURIComponent(who)}` : ""}`),
  levelUpPlan: (id, who = "") => request("GET", `/api/conversations/${id}/character/levelup${who ? `?who=${encodeURIComponent(who)}` : ""}`),
  levelUp: (id, answers, who = "") => request("POST", `/api/conversations/${id}/character/levelup${who ? `?who=${encodeURIComponent(who)}` : ""}`, { answers }),
  autoParty5e: (id, body = {}) => request("POST", `/api/conversations/${id}/character/party/auto`, body),
  libraryDetails: (type, source, name) => request("GET", `/api/library/5e/details?type=${encodeURIComponent(type)}&source=${encodeURIComponent(source)}&name=${encodeURIComponent(name)}`),
  combatOptions: (id) => request("GET", `/api/conversations/${id}/combat/options`),
  combatStep: (id, body) => request("POST", `/api/conversations/${id}/combat`, { action: "step", ...body }),
  convertCharacter5e: (id) => request("POST", `/api/conversations/${id}/character/convert`, {}),
  restartConversation: (id, keep) => request("POST", `/api/conversations/${id}/restart`, { keep }),
  undo: (id) => request("POST", `/api/conversations/${id}/undo`),
  editMessage: (messageId, content) => request("PATCH", `/api/messages/${messageId}`, { content }),
  rewind: (id, messageId, inclusive) => request("POST", `/api/conversations/${id}/rewind`, { message_id: messageId, inclusive }),

  setPinned: (id, text) => request("PUT", `/api/conversations/${id}/pinned`, { text }),

  patchState: (id, patch) => request("PATCH", `/api/conversations/${id}/state`, patch),
  state: (id) => request("GET", `/api/conversations/${id}/state`),
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
