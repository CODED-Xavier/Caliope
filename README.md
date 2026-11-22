# Calíope

**Calíope** (named after the muse of epic poetry) is a roleplay and tabletop RPG app that runs entirely on your PC.
There are no token limits and no subscription, and your stories never leave your computer.

Inside Calíope:
- the game master is **the Aedo**, the singer of the Homeric epics
- the chapters of a story are **Cantos**
- the AI that helps you write stories and cards is **the Muse**

Current version: **v2.23**. The version history is at the end of this file.

**Beta testers:** start with [BETA-TESTERS.md](BETA-TESTERS.md), a step-by-step guide to install, play and report bugs.

---

## Contents
1. [Quick start](#1-quick-start)
2. [The AI model](#2-the-ai-model)
3. [Playing a game](#3-playing-a-game)
4. [Cards](#4-cards)
5. [The Muse](#5-the-muse)
6. [Pictures, music and voice](#6-pictures-music-and-voice)
7. [How the Aedo remembers](#7-how-the-aedo-remembers)
8. [Rulebooks and skills](#8-rulebooks-and-skills)
9. [Your data, backups and privacy](#9-your-data-backups-and-privacy)
10. [The Windows program (Caliope.exe)](#10-the-windows-program-caliopeexe)
11. [Settings worth knowing](#11-settings-worth-knowing)
12. [Troubleshooting](#12-troubleshooting)
13. [For developers](#13-for-developers)
14. [Version history](#14-version-history)

---

## 1. Quick start

**You need this once:**
- [Python 3.12](https://www.python.org/) (tick "Add Python to PATH"), or run `py install 3.12` in PowerShell
- [Node.js LTS](https://nodejs.org/), used only to build the interface

**Every time you play:** double-click **`Play.bat`**. It:
1. installs the Python packages the first time (and again only when they change)
2. builds the interface when it is missing or its code changed
3. starts the app and Calíope's own AI engine (the model loads in the background)
4. opens Calíope in **its own window**: a real app window (it uses Windows' built-in WebView2). If that can't start, it uses an Edge window without tabs or address bar instead

**The desktop shortcut** (and the Start menu one) starts Calíope through `Caliope.vbs`: no black window at all, on the
screen or in the taskbar. A small **loading screen** with Calíope's icon and a progress bar shows what is happening (first
setup, an interface update, starting the engine) and closes when the game window opens. If something goes wrong, the loading
screen shows the reason, with a button to open the log (`backend\data\caliope.log`). Shortcuts made by older versions are
updated by themselves. Double-clicking `Play.bat` still works, with the black window, which is handy to see what happens.
The game window opens **maximized**; **F11** switches full screen. **Closing the game window stops everything.** Run `Play.bat --shortcut` to make the shortcuts again.

Options: `Play.bat --no-browser`.

The first time, a short **tour** shows the main functions (skip it any time; Settings > *Show the tour again*). Its first step lets you pick the language: **English** or **Português (Brasil)**, for the menus and the stories. It ends by offering to get **Stheno 8B**.

Before your first game, give it a model ([section 2](#2-the-ai-model)).

---

## 2. The AI model

Calíope works with a local roleplay model. On an 8 GB graphics card (such as the RX 580), a good choice is
**L3-8B-Stheno-v3.2** in **Q4_K_M** or **Q4_K_S** (about 5 GB).

**Which model fits your PC?** 🧠 Models > *Find more* shows **Your PC** (graphics card, its memory, RAM) and the roleplay model that fits best, with the file size to pick and a **🔍 Find it** button. If it can't read your PC, ask any AI assistant: "My PC has <graphics card> and <RAM>. What is the best GGUF roleplay model for it?"

### Calíope's own engine
Calíope runs the model itself (llama.cpp's official Vulkan build, which works on AMD cards). No other program is needed, and LM Studio is never opened.
1. Sidebar → **🧠 Models**.
2. Get a model:
   - *Find more*: search Hugging Face. Each file size has a note on quality and on whether it fits 8 GB. Downloads go to Calíope's own folder (`backend\data\models`), resume after a pause, and are checked against Hugging Face's checksums.
   - *Browse this PC*: use a `.gguf` file you already have in another folder, without downloading it again. **Browse…** opens Windows' file picker, or you can paste a folder's address.
3. *My models* → **Load**. The first time, the engine itself (about 30 MB) is downloaded first and the model loads right after. Optionally, **Use for memory** on a small embedding model (e.g. `nomic-embed-text`) for memory search by meaning.

The engine starts with the app and stops when you close it. A model that was used from LM Studio's folder (older versions) is copied into Calíope's folder by itself, in the background, and used from there on the next start.

**Why replies start fast:** the engine keeps two memory slots. One holds only the story, so its long, unchanged beginning (card, world, characters, the older messages) stays read between turns, and each reply only reads what is new. The other slot runs the helpers: the tracker, summaries, and the Aedo's answers outside the story. Calíope also reads the story ahead while you read and type (right after each reply, and when you open a game), and the oldest messages leave the window a few rounds at a time instead of one per turn, so the part already read stays valid. The two slots use about 1 GB more video memory; when a card can't hold that, the engine starts lighter by itself (one slot, then part of the model on the processor).
- If loading fails with "out of memory", lower the **Context window** to 6144 or set **GPU layers** to about 28 in Settings.

### Online services
Settings > *API key* also works with services that speak the same language (OpenRouter, for example): put their address in *Server address* and your key in *API key*. Remember that they see your story, charge per use, and may refuse dark scenes.

---

## 3. Playing a game

### Starting
Calíope opens on the **🏠 Main menu** (Settings › *Continue from the last played card* opens your last game instead): all your cards as tiles with their pictures, **▶ Play**, **✎ Edit**, **＋ New card**
and **⤒ Import a card**. The 🏠 button at the top of the left column brings you back to it from a game.

1. **▶ Play** on a card (or **＋ New game** → pick a card). 👥 shows its characters with picture, name and role.
2. If the card has several starts, choose one in **Choose your start** (for example, Lumencia's default start or another route).
3. **Create your sheet** (Adventure cards) or **Who are you?** (Roleplay cards).
   - Or choose *Let the story ask me* for cards that create your character in the chat (like Lumencia). When you answer with your sheet (name, origin, department, attributes…), the app reads it once and fills your **Sheet** tab.
   - **✨ Fill the empty fields** suggests a background, looks and personality.
   - **Your world additions**: lore of your own (a great house, a home village, a secret order). It is canon in this game, even where the card says otherwise.
   - **🎭 Personas**: pick one of your saved characters to fill this screen, or **💾 Save as persona** to reuse this one in other games (name, background, looks, personality and world additions).

### How to write
| You write | Meaning |
|---|---|
| `"Hello there."` | Your character speaks |
| `*I draw my sword*` | Your character acts |
| `'He is lying.'` | Your character thinks. Only the Aedo knows (characters never do) and may give subtle hints. |
| `/how much gold do I have?` | A question to the Aedo outside the story. He answers in a dashed box, plainly and without narrating; the question and answer are kept in the chat but not in the story he plays (`/what was my background?` gives your sheet back, for example) |
| `/roll 1d20+3` | Dice, rolled by the app (`adv`, `dis`, `4d6kh3` work too) |
| `/wait 3 days`, `/wait until morning` | Time passes, only when you choose |
| no marks | The Aedo decides |

Under the text box, **✍ Free · 🗣 Speak · ✋ Act · 💭 Think · 🗨 Ask the Aedo** pick how the whole message is sent (Free = the marks above, as you type them). Each mode says who hears it. A message that starts with `mestre,`, `GM,` or `Aedo,` is also a question to the Aedo.

Every card follows one rule from the app: the narrator and the characters never speak, act, think or decide for your character. The story's language is repeated next to every message, so the characters answer in it too.

The message box checks your spelling as you type (red underline; right-click for suggestions), in the story's language. **✨** beside the send button corrects spelling and grammar of your message with the AI, keeping your words and marks (**↶** undoes it).

### Under the replies
- **Continue ▸**: keeps writing the same reply. **↻ Regenerate**: writes it again.
- **↶ Undo**, **edit** or **re-send** a message, and **⏪ rewind** to any point. Sheet, money, HP, dice and the clock go back too.
- **⑂ Save point**: a new game from that moment; the original is not changed.
- **🎲 roll buttons** appear when the Aedo asks for a check ("DEX (Stealth), DC 13"). The app adds your sheet's bonus and rolls.
- **🛒 buy buttons** appear for prices in a reply. The app checks your money and puts the item in your bag.
- **🔊** reads the reply aloud (needs a voice, [section 6](#6-pictures-music-and-voice)).
- **🖼** paints the scene; **📌** keeps a picture in the map bag.

### At the top of the chat
- **📜 Recap**: "Previously, in…", written only when you ask and never added to the story.
- **↺ Restart** (also ↺ next to the game in the left list): the same card from its opening, with the same character at full HP; the story, items, gold, fights and scenes start over. Keep the old run (renamed *… (old run)*) or delete it.
- **🎵 Music**, **🔍 search** (Ctrl+F), **⤓ export** to Markdown.
- **Aa**: text size, wider column, compact mode, story colours (grey narration, bright speech, coloured thoughts), character picture size, follow the text as it is written.
- The **date and hour** of the story.

### The side panel
Tabs appear when the card uses them. When there are more tabs than room, the tab row scrolls sideways: use the mouse wheel over it, drag it, or click the ‹ › arrows at its ends. Drag the panel's edge to resize it. The small **‹ ›** bubbles on the chat's edges hide the games list or the panel completely, giving the story the whole window; click them again to bring the columns back.
- **Sheet**: HP, attributes, money, place, time and weather, resource bars (Mana, Aura…), powers with **Use**, short and long rest.
- **Bag**: items, quests (when a quest seems finished, you confirm it), **Pay** box.
- **People**: everyone you have met, with relationships from −100 to +100. Characters count as met only when they actually interact with you.
  **Reputation is a system:** after each reply the tracker only *names* what you did to someone (defended, helped, kept a
  promise, gift, kind words… or rude, mocked, caught lying, stole, attacked, betrayed); the app gives the value, the same
  every time (defending someone +12, saving a life +25, betraying −30). Doing the same thing to the same person counts
  half as much each time (compliments can't be farmed), and every change is capped by *Biggest relationship change per
  reply*. Each level has fixed effects the characters follow: **mortal enemy** works against you; **hostile** refuses
  help; **distrustful** helps only for a price; **neutral** is polite; **friendly** does small favours and shares
  rumours; **close** shares their own secrets and takes risks for you; **deeply bonded** would sacrifice for you. Open a
  character to see what their level means and the last few reasons it changed.
  - **Notes** under each character: yours (what you think of them, a promise, a debt), plus the Aedo's own, marked ✒, which he adds after important moments ("promised to train the player at dawn"). The Aedo keeps them in mind whenever that character is in the scene; edit or delete any line.
- **Status**: the character sheet, kept by the app. It is the card's own INFO block (cards like Lumencia), or a ready sheet picked from the library: D&D 5e, Pathfinder 2e, Tormenta20, Vampire V5, Call of Cthulhu 7e, Cyberpunk RED, magic academy, slice of life, or your own. Place, time, HP, level, attributes, items, money, quests and relationships come from the game; the other fields (Sanity, Hunger, Spell slots…) change when the story changes them. Pick it on the card (*Character sheet*) or for one game only (Status → *Change the sheet*).
- **Map**: places, plus the **🎒 map bag** of kept scene pictures.
- **⚔ Combat**: fights with a battle map ([below](#combat)).
- **Dice** and **Journal**: Cantos, the pinned memory box, summary, memories, calendar appointments, your world additions.

### Cantos (chapters)
Journal → **Close this Canto** at a natural break. The Aedo writes a short chronicle, a divider marks the new Canto in the
chat, and the chronicles of past Cantos stay in what the Aedo always knows. Rewinding into a closed Canto opens it again.

### Time and the calendar
Each card can have its own calendar (card editor > Calendar). **The app keeps the clock, not the AI.**
- Scenes move the clock by minutes or hours. **Days pass only when you choose** (`/wait`, or "I sleep until morning").
- Appointments ("the festival is on Sunday") land on the exact day.
- The weather comes from the season and the card's climate.

### The Bestiary (monster sheets)
**🐉 Bestiary** (left column, bottom) keeps monster sheets in `backend\data\bestiary`, one file per monster, in a folder per book (`bestiary\Lost Mine of Phandelver\goblin.json`; the ones you make yourself sit at the top, as *My monsters*): AC, HP,
speed, STR to CHA, skills, senses, challenge and XP, traits and attacks.
- **＋ Create monster** opens an empty sheet. **⤒ Import stat blocks** reads them from a book's appendix (Markdown, text
  or PDF, in the usual 5e layout). Importing an adventure adds the book's monsters by itself.
- In a fight, an enemy with the same name (or its plural: "Goblins") gets the sheet's numbers: the first attack with a
  to-hit bonus and damage is the one it uses. In the Combat tab the enemy name field suggests the Bestiary's monsters.

### Combat
⚔ Combat → choose **d20** (D&D 5e) or a **d10 dice pool** (Vampire 5e) → add enemies, or **✨ Suggest from the scene** → pick a map → **Start the fight**.
- The app rolls everything (initiative, attacks, damage, powers, enemy spells). The Aedo only narrates one ⚔️ card per round.
- **Turns by the rules:** enemies faster than you act as soon as the fight starts (rolled by the app, never by the Aedo). Then it is your turn.
- **Write your attack:** during a fight, *"I try to cut the goblin's head clean off"* is rolled by the app against that goblin, and the Aedo narrates the real result in your words. **/attack goblin 2** and **/dodge** work too. Speech in quotes and questions are never taken as attacks. Too far away? You walk to it with your movement, or **Dash** toward it if it is out of reach this turn.
- **Interactive grid:** on your turn, the squares you can reach light up. Click one to move (6 squares = 30 ft; mud and bushes cost double). You can't move on the enemies' turns.
- **Checks:** every roll button shows its DC before you roll (*CON check (DC 13)*), and the result says ✅ Success or ❌ Failure. If the Aedo forgot the DC, the app sets 12 and tells it. One roll per reply; in a fight, one check per round (your reaction). A named skill uses its own ability (Perception is WIS).
- **⚔ A fight!** appears under the reply when the scene's enemies attack; you start it (Settings → *Start fights by themselves* starts it without the button).
- Dropping a weapon or having it knocked away in a fight doesn't remove it from the bag; only used-up things (potions, arrows, torches…) leave it.
- Maps: generated (forest, dungeon, tavern, river…) or your own from **🗺 My maps**. Walls block, obstacles give **cover**, and mud and bushes slow you.
- **Painted maps (like Watabou):** a generated map is painted as a real battle map picture (trees, rocks, a road, stone floors) when the fight starts, with the grid already lined up. In an adventure scene that has no map, Calíope paints one that fits the scene (a road for an ambush, a cave for a hideout…) and keeps it in the card as that scene's map. **🎨 Paint a map** / **🎲 Paint another** in the Combat tab, and **🎨 Paint a map for this fight** turns a fight on a plain grid into a painted map mid-fight.
- Undo and rewind also undo the dice.

### Companions and solo play
Card editor → **👥 Companions**: up to 3 characters who travel with you, outside the card's own story. Each has a fight sheet (class, role, HP, AC, attack, damage, range, speed; healers also a heal and heals per fight), a personality, a way of talking and pictures. **✨ Write companions** has the AI draft 3 that fit the card.
- When you start a game: **👥 Play with companions** or **🧍 Play solo**. With companions, the Aedo voices them (they talk and act on their own, never for you) and they have a relationship with you like anyone else.
- **In fights** they join by themselves and Calíope plays them: a healer heals you first if you're dying, then whoever is below half HP; the others walk up and attack (archers shoot). Their HP lasts between fights; a long rest heals them fully, a short rest half.
- **Solo**: an adventure's scene enemies are scaled to one hero (the books are written for 4): 4 goblins become 1. Fights you build in the Combat tab keep your numbers.
- **Death saving throws** (5e): at 0 HP you're dying; each of your turns the app rolls a save (10+ succeeds, natural 20 = back up with 1 HP, natural 1 = two failures; 3 successes = stable, 3 failures = dead). The fight is lost only when nobody on your side is standing: then your remaining saves decide if you're left alive (waking later with 1 HP).

### Resources and powers
Card editor > **Resources and powers**: pools (Mana, Aura, Stamina…) with maximum, colour and refill (per round, rest, night, day), and powers that spend them.
- The Sheet and Combat tabs have **Use** buttons; the app pays the cost and rolls.
- When the story spends a resource without a button ("you pour your aura into the barrier"), the tracker subtracts it.

---

## 4. Cards

A card is a world to play: its rules, setting, characters and opening.
- **Roleplay** cards are simple and fast: characters, relationships, conversation.
- **Adventure** cards add rules, items, quests, maps and combat.

The AI's role:
- **Aedo · open world**: invents places and people as you go.
- **Aedo · preset cast**: runs the characters you define.
- **One character**: the AI plays a single character; the story is about your relationship.

### Making and editing cards
- **＋ New game → ✎** on a card opens the editor. **✨ Write with AI** drafts the teaser, world, rules, tone or opening from the rest of the card.
- **✨ Generate from an idea** drafts a whole card. The [Muse](#5-the-muse) goes further.
- **Characters**: description, personality, speech style, looks, pictures and moods.
  - **✨ Fill looks, personality and speech from the card**: the AI reads what the card says about each character and writes their empty boxes. What the card says is used as it is; what it doesn't say is invented **once** to fit the character. It's saved in the card, so the character stays the same in every game, and it's also written into games already using the card. Edit anything afterwards here or in the People tab.
- **Places**: locations with a fixed picture (⬆ from your PC or a link), plus other names and a short description. When the story arrives at a place, its picture appears above the reply at once (nothing is painted) and goes in the map bag. The Aedo learns the places' names.

### Importing and sharing
- **Import a card** reads Character Card V2 JSON files (the SillyTavern format), the lorebook included, and **.caliope** files.
  - Lorebook entries reach the Aedo only when their keywords come up, so 30+ characters don't fill the prompt.
  - Characters listed in the lorebook become people with portraits.
- **📦** in the card list saves a **.caliope** file: the card **with all its pictures**, to share without GitHub or the cloud.
- **⤓** saves a standard JSON card (pictures stay as links).

### Starts (routes)
A card can be entered in different ways. In the card editor, under *Opening message*, **Starts** can each have:
- their own opening
- **how the world is on this route** (the Aedo reads it every turn)
- **who the story starts with**: everyone else is met in the story
- **fixed scenes**, played one per reply in order and adapted to what you do (separate them with a line of `---`)

### Facts, secrets and the ending
In the card editor, **Facts, secrets and the ending** (all optional):
- **Known from the start:** what the player's character already knows. Anything else must be found out in play.
- **Fixed facts:** always true, never contradicted (who is alive, who hired the player, how characters look).
- **Secrets:** discovered only through play. Characters refuse, lie or truly don't know; the Aedo never hands them out when asked outside the story, and doesn't invent sudden events to dodge the question.
- **Story length** and **It ends when…:** the Aedo moves the story toward the ending and closes it with THE END. The chat then offers **📜 Write the epilogue** (what became of everyone, and the story in brief).

On the **Sheet** tab, **✨ Wishes for the story** takes your soft hints ("Kaida and I could go from rivals to lovers"). The Aedo creates chances for them when the story allows, without forcing them or bending the plot.

### Adventures (published modules)
For adventure cards that follow a book (*Lost Mine of Phandelver*, any module, your own notes). In the card editor,
**Adventure: scenes, maps and fights**:
- **Import** a PDF, a Markdown file (as exported by 5e.tools: its headings and `>>` read-aloud boxes are used exactly), or text copied from it. A whole Markdown book is split into its parts by itself. Or import one part at a time: type the chapter's name ("Part 1: Goblin Arrows"), then import. The **Parts** list shows the chapters; **⬆ Import here** adds the next text to one of them. **Maps** and **Scenes** are below. Calíope splits it by itself into
  **scenes**: numbered areas ("1. Cave Mouth") grouped under their location ("Cragmaw Hideout"), and encounters with their
  own heading ("Goblin Ambush"). Each scene keeps:
  - the **read-aloud text**, which the Aedo narrates close to word for word on the first visit;
  - hidden **GM notes** (who is there, what they do, Developments, what someone knows);
  - **checks and traps** with their DC ("Wisdom (Perception) DC 12"). The Aedo asks for the roll and waits for the dice;
  - **enemies** with their numbers (common monsters get their SRD numbers automatically), **treasure** and an **XP award**;
  - the **ways on** (the areas it leads to).
- The splitting is automatic, so check each scene once: rename, **⤴ Join to the scene above**, or remove.
- **Maps:** add the map picture (the GM version, and the player version if the book has one), then **🔍 Find the grid**:
  Calíope reads the picture and lines its squares up with the map's own 5-ft squares, like Foundry VTT or Roll20 (fine-tune
  with *Square size* and the two *Move* sliders; *Show the grid* draws it over the map). Choose a scene and click its spot.
  **Fog of war:** how many squares stay clear around each place visited (0 turns the fog off).
- "Roleplaying ..." sections become characters (not met yet), and the Background and Overview go to the Aedo's notes.
- The book stays on your PC; only the current scene is sent with each reply.

When a fight breaks out in a scene that has enemies (you attack, or they charge), a **⚔ A fight!** box under the reply starts it in one click, with the scene's enemies and its map; **Not now** hides it. The scene also moves on by itself when the story walks into the next one (its enemies appear, or its name is said).

In play, the **📕 Adventure** tab shows the scene you are in (📖 *What you see*), the map with the places you have visited,
the ways on, **🏅 Give the XP** (added to the sheet's XP), and **⚔ Fight here**: the Combat tab opens with the scene's enemies
and starts the fight on the adventure's map, square for square with the map's own grid, the enemies around the scene's spot,
and the fog hiding what you haven't explored (your side sees 4 squares around itself). The scene changes when the story
moves on (the place the tracker notes, or when you say where you go), or when you pick one in the tab.

### Character pictures from a folder
Every card has its own folder in Calíope: `Pictures\<card name>\`, next to Play.bat (made the first time you open the card's *Characters* section). In the card editor > *Characters*:
- **🔍 Search my PC for the pictures folder…** picks your folder anywhere on the PC (or paste its address and press **Copy in**). Its pictures are copied into the card's Calíope folder, then shown for a check before **Apply**.
- **Open** shows the card's folder in Windows, to drop pictures straight in; **↻ Read it** reads what it holds now.
- Finished more pictures? Search again or drop them in: files with the same name are replaced.

The layout:
```
pictures\
  Artemis\1.png 2.png 3.png 4.png 5.png 6.png
  Lilia\1.png
  Bishop Corvin.png
```
- `1` Standard, `2` Happy, `3` Sad, `4` Angry, `5` Disgusted, `6` Blushing (or the card's own mood names).
- A single `Name.png` is used as the Standard picture.
- Folder names match characters without caring about capitals, accents or a missing surname.
- A preview shows what matched. Unmatched folders get a list: pick the character by hand, or **＋ Add as a new character** (the folder's name becomes a new character of the card, also added to games already using it). Nothing changes until **Apply**.
- Missing moods use the closest one (Disgusted → Angry, Blushing → Happy, otherwise Standard).
- The pictures are copied into Calíope and also update games already using the card. Run it again whenever you finish more pictures.

### Private cloud pictures (Cloudflare R2), optional
1. Settings > *Pictures in the cloud*: R2 account ID, bucket, access key and secret.
2. Card editor → **☁ Upload this card's pictures**.

The bucket stays private: Calíope signs every download with your keys and keeps a copy on this PC. The card only holds `r2:` links that nobody else can open.

---

## 5. The Muse

**🪶 The Muse** (left sidebar) is a writer's room with the same model that plays your games.
- Brainstorm worlds, characters, a new route for a card, a twist for your campaign. Talks are saved, and long talks are summarized as they go.
- **↶ Undo last** removes her last answer so you can ask differently.
- **✨ Make it a card** turns the talk into a card. The model is asked for one piece at a time (title, pitch, world, tone, each character's sheet, the opening), so the card always comes out valid. It takes one or two minutes on an RX 580.
- The preview offers **＋ Add to Calíope** (find it in New game; ✎ to edit) or **⤓ Save file** (a JSON card to import later).
- **👥 Add characters to a card** writes sheets (description, personality, speech, looks) for the characters of the talk and adds them to one of your cards. A character with the same name already in the card (for example one created from your pictures folder) keeps its pictures and anything written; only its empty boxes are filled. Games using the card get the characters too, not met yet.

**📚 Research a work** drafts a card from an existing anime, game or book series (needs the internet):
1. Type the work's name (or paste its wiki's address) and click **Find the wiki**. Fandom wikis are found by name; any other MediaWiki wiki works by address.
2. Tick the pages to read: the biggest character pages and lore pages (places, groups, powers) come first. Up to 40 pages.
3. **✨ Draft the card**: the world comes from the work's own page, each character gets its introduction, personality and appearance from the wiki, and each lore page becomes a lorebook entry. No model is needed, so it takes about a minute.
4. **See the card** (then ＋ Add to Calíope) or **👥 Add these characters to a card** you already have. With a talk open, the Muse gets a research note, so you can keep planning the story with her.

The card comes without an opening: write one with ✨ Draft in the card editor, or ask the Muse; ✨ Fill adds speech styles. Wiki text is shared by its authors under CC BY-SA; the card is for your own games.

The Muse and your games share the model, so one waits for the other.

---

## 6. Pictures, music and voice

### Character pictures and moods
People tab or card editor → *🖼 Pictures and moods*: a main picture plus Standard, Happy, Sad, Angry, Disgusted, Blushing, and up to 12 moods of your own. Each comes from your PC (⬆) or a link (🔗).
- The Aedo narrates first, then shows the character's picture **right before they speak**. When their mood changes later in the reply, the picture appears again with the new mood. (The app moves a misplaced picture to just before the character's line.)
- If the Aedo forgets to say the mood, the app reads the next lines: *she smiles* shows Happy, *he glares* shows Angry, *she blushes* shows Blushing.
- Pictures added to a character in the **card editor** also reach the games already started with that card (unless you changed that character's pictures inside the game).
- **Click any picture in the story** to see it big (Esc closes).
- **Your own picture**: click the circle beside your name on the Sheet.

### Scene pictures and the map bag (optional, needs internet)
Settings > *Scene pictures*. When a scene starts (a new place, a fight), the Aedo first describes the place in detail (architecture, windows, light, air, weather, the people there) and a picture of it is painted above the reply. **🖼** under any reply paints *that moment* instead: the place plus each character in view with their saved looks (hair, eyes, build, clothes) and what they are doing. Names never leave your PC; people are described by their looks. Places the card has a fixed picture for use that picture instead (no painting, no internet).
- **Pollinations** (free, no account) is the default. **PixAI** can be used with your own API key and model ID.
- Only the description of the place leaves your PC: names are removed and your messages are never sent.
- **🎒 Map bag** (Map tab): the first picture of each place is kept on its own, and **📌** keeps any other. Each shows the place, in-game date and Canto.

### Jukebox
**🎵 Music** → add songs from your PC (or direct audio links) and tag them with moods (tavern, forest, dungeon, combat, boss, victory…).
With **Auto**, the music follows the scene: combat music in fights, boss music for bosses, a victory song when you win.
**🔁** loops the song that is playing (it stays even when the scene's mood changes) until you click it again.

### Narration voice
Settings > *Narration voice*:
1. Download the voice program (Piper, about 25 MB) and a voice (about 60 MB each): Lessac, Amy, Ryan (English US), Alan (English UK) or **Faber** (Português do Brasil).
2. Pick it as *Voice for 🔊*.
3. **🔊** on any reply reads it aloud (⏹ stops), or turn on *Read every new reply aloud*.

It runs on the processor, so the story model keeps the graphics card. Each reply is read once and kept.

### Themes
Black, violet and orange. The dark theme (☾) leads with violet and the light theme with orange.

---

## 7. How the Aedo remembers

The model can only read a limited amount of text at once (the **context window**, usually 8192 tokens), so Calíope layers memory:

| Layer | What it holds |
|---|---|
| Recent rounds | The last ~10 exchanges, word for word (adjustable) |
| **Cantos** | A chronicle of every closed chapter |
| Summary | A rolling summary of older events |
| Memories | Important facts, found again by keywords or by meaning when they matter |
| Pinned memory box | Up to 2,000 characters you write; always included |
| Game state | Sheet, bag, quests, relationships, clock, resources: kept by the app |
| Lorebooks | The card's and yours, added when their keywords come up |

After each reply a short second call (the **tracker**) notes what changed. On quiet turns of pure talk it is skipped and catches up later.

---

## 8. Rulebooks and skills

**📚 Rules** → import a PDF or text rulebook, then tick it in a card's *Rulebooks*.
- When a turn touches a rule (grappling, falling, frenzy…), the Aedo gets the matching section, and **📖 Rules used** shows which.
- **House rules** win over the book.
- Scanned books need the free [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki).
- A good free start: the **D&D System Reference Document 5.2**.

The monster numbers built into adventure import come from the *System Reference Document 5.1* by Wizards of the Coast LLC, available under the Creative Commons Attribution 4.0 license.

**🧩 Skills** are folders with a `SKILL.md` (style guides, genre advice). Install them in the Skills window and attach up to 3 to a card. Skill scripts are never run.

---

## 9. Your data, backups and privacy

Everything lives in `backend\data` (with Play.bat) or `Caliope\data` (with the exe):

| Item | Where |
|---|---|
| Games, cards, characters, memories, settings | `rpg.db` |
| Daily backups | `backups\rpg-<date>.db` |
| Pictures (uploads, downloads, card folders) | `portraits\`, `cardpics\` |
| Music | `music\` |
| Voice program, voices and spoken replies | `voice\` |

**Backups:** once a day everything in `rpg.db` is copied to `backups`, and the last 7 days are kept (Settings > Backups: *Back up now*, *Open folder*, how many days).
To restore:
1. Close Calíope.
2. Rename `rpg.db` (keep it).
3. Copy a backup into `data` and rename it `rpg.db`.
4. Start Calíope again.

**What goes online, and only if you turn it on:**
- scene picture descriptions (Pollinations or PixAI)
- R2 uploads and downloads
- downloads of the engine, models and voices from their official sites
- an online model, if you set one

Everything else stays on this PC. Calíope only answers on this PC (127.0.0.1) and refuses requests from other websites.

---

## 10. The Windows program (Caliope.exe)

Run **`build-exe.bat`** (after Play.bat ran once). It builds the folder `Caliope\` with **Caliope.exe**, which needs no Python or Node.js.
- Its saves are in `Caliope\data`, the engine in `Caliope\engine`, skills in `Caliope\skills`. Rebuilding replaces only the program files, never these folders.
- The first build copies your saves from `backend\data` (and from the old `LocalRPG` folder of v1.x; delete that folder afterwards).
- Copy the whole `Caliope` folder to move it. An installer is planned.

---

## 11. Settings worth knowing

| Setting | What it does |
|---|---|
| AI engine | Built-in (Calíope's own engine) or another server (an online service with your API key) |
| Context window | How much text the model reads at once; must match the model (8192) |
| Reply length | Short, medium or long replies |
| Rounds kept word for word | How many recent exchanges stay complete |
| Track the sheet automatically | The tracker after each reply (turn off for speed) |
| Skip tracking on quiet turns | Faster talk scenes |
| Summarize old messages | The rolling summary |
| Scene pictures / Painted by | Pictures for new scenes; Pollinations or PixAI |
| Narration voice | Piper voice, speed, read every reply |
| Backups | Daily copy, days to keep |
| Open in its own window | App window or a normal browser tab |
| Interface language | English or Português (Brasil) for menus, buttons and help; changes at once. The story's language is set apart (*Language of the story*) |

Every setting has a **?** with a short explanation.

---

## 12. Troubleshooting

| Problem | Try |
|---|---|
| "Cannot reach the model server" | 🧠 Models → **Load** a model (wait until it says Ready). |
| Engine: out of memory | Lower *Context window* to 6144 or set *GPU layers* to ~28. Close other programs that use the graphics card (games, LM Studio). |
| Replies are slow | *Reply length*: short. Turn on *Skip tracking on quiet turns*. Fewer *rounds kept*. |
| The game opens in an Edge window, not the app window | The app-window package could not be installed. Delete `backend\.venv\window-tried` and run Play.bat again (needs internet). Edge works the same. |
| The interface looks old after an update | Close the game window and run Play.bat again (it rebuilds the interface). |
| A picture doesn't show | Links can break; use 📂 pictures from a folder or ⬆ from your PC. |
| Something else | Open `backend\data\caliope.log` (the app's messages and errors) and copy its last lines when asking for help. If the app does not start at all, the black window shows the reason. |

---

## 13. For developers

Calíope is a FastAPI + SQLite backend (`backend/app`) that serves a React + Vite interface (`frontend`).
`AGENTS.md` explains the layout and the rules that keep the app working.

- **Development mode** (the interface reloads as you edit): `start-backend.bat` and `start-frontend.bat`, then http://localhost:5173.
- **Tests**: no GPU, network or LM Studio needed (a fake model is used).
  ```
  cd backend
  python -m unittest discover -s tests -t .
  ```
- **API**: http://127.0.0.1:8000/docs lists every endpoint. Turns stream as server-sent events (`user_message`, `token`, `assistant_message`, `state`, `done`, `error`…).
- Each feature lives on its own branch with tests and a version tag.

---

## 14. Version history

| Version | What came |
|---|---|
| 0.2 | Backend and web interface |
| 0.3 | Edit, rewind, delete and re-send messages |
| 0.4 | Speed and memory: pinned memory box, rounds window, reply length |
| 0.5 | Roleplay and Adventure cards, skills as add-ons, character looks |
| 0.6 | Character card import with lorebook, big portraits, Status tab, Continue |
| 0.7 | Start screens, writing marks, time and weather, Aa menu, search, export, save points |
| 0.8 | Pictures beside messages, moods and the mood editor |
| 0.9 | One-click `Play.bat` |
| 0.10 | Rulebooks with OCR, search and house rules |
| 0.11 | Combat with dice by code, battle maps, terrain and cover |
| 0.12 | Jukebox |
| 0.13 | Scene pictures |
| 1.0 | Built-in llama.cpp engine and the Windows program |
| 1.1 | Models window (Hugging Face search, downloads, load and unload) |
| 1.2 | Your world additions (player lorebook) |
| 1.3 | World calendar with real time |
| 1.4 | Code audit: performance, security and fixes |
| 1.5 | The app does the counting: checks, shop, INFO block, quiet turns |
| 1.6 | Resources and powers |
| 1.7 | Its own window |
| 1.8 | Story colours |
| 1.9 | Collapsible sidebars, big pictures, the "met" fix |
| 1.10 | Audit leftovers: faster memory search, re-send undoes old results, upload limits |
| 1.11 | The pixel-art icon |
| 1.12 | Browse this PC for models |
| **2.0** | **Calíope**: new name, violet and orange themes, API key, PixAI option |
| 2.1 | Card starts (routes), character preview, pictures from a folder, private R2 |
| 2.2 | The Muse |
| 2.3 | Cantos, recap, map bag |
| 2.4 | Daily backups and .caliope card files |
| 2.5 | Narration voice |
| 2.6 | Columns hide fully, no scrollbars, spell check, character notes (yours and the Aedo's), Personas, new characters from a picture folder |
| 2.7 | Character boxes filled from the card (once), sheet from your first answer, pictures right before speech and on mood changes, Places with fixed pictures |
| 2.8 | The Muse adds characters to an existing card |
| 2.9 | First-run tour, PC scan with the best model for it, Stheno offer, ✨ correct my text |
| 2.10 | A real app window (pywebview), and Calíope's own question boxes instead of the browser's "127.0.0.1 says…" popups |
| 2.11 | The interface in English and Português (Brasil), switched in Settings or in the tour |
| 2.11.1 | Audit 2 fixes (see AUDIT.md): start names, Places in .caliope files, repeated place pictures, safer imports |
| 2.12 | Beta feedback: the Aedo answers `/questions` outside the story, two memory slots for much faster replies, Load gets the engine by itself (no LM Studio), interactive tour, Calíope's icon on the window, the Sheet tab on every card, help popups stay on screen |
| 2.12.2 | The black window hides while Calíope's window is open (messages in `backend\data\caliope.log`); the desktop shortcut starts it minimized |
| 2.12.3 | Engine: unloads LM Studio's models first, and falls back to a lighter start when video memory runs out |
| 2.13 | Calíope runs its models itself (own models folder, LM Studio's copies moved in, LM Studio never opened), desktop and Start menu shortcuts, faster replies (story read ahead, card reminders read once, window moves in steps), your sheet in the chat fills the card's Status (📋 on any of your messages to read it again) |
| 2.14 | Group 1 of the playtest notes: never speaking for your character, the story language next to every message, reputation only from your actions, speaking modes under the text box (and `mestre,` questions), a first-model card on the home screen, summaries in the background, roomier card titles; each card has its own Pictures folder with 🔍 Search |
| 2.15 | Cards: what the player knows from the start, fixed facts, secrets (never handed out), story length and ending with THE END and an epilogue; ✨ Wishes for the story on the Sheet tab; the Aedo answers only what your character could know; The Hollow Crown rewritten |
| 2.16 | Pictures: a new place is described in detail first (architecture, light, air, weather, people there; no more empty white backgrounds), and 🖼 on a reply paints that exact moment with the characters' saved looks and poses |
| 2.17 | Sheet library: ready character sheets (D&D 5e, Pathfinder 2e, Tormenta20, Vampire V5, Call of Cthulhu, Cyberpunk RED, academy, slice of life) for the Status tab, per card or per game |
| 2.18 | Adventures: import a published adventure (PDF or text) as scenes with read-aloud text, GM notes, checks with DC, enemies, treasure, XP and maps; the 📕 Adventure tab; fights on the adventure's map; dark route for Lumencia |
| 2.19 | The Muse researches a work on its fan wiki (📚 Research a work); 🔁 loop a song in the music controls; adventure Parts list |
| 2.20 | Main menu with all your cards; loading screen and no black window (Caliope.vbs); 🔍 Find the grid on adventure maps (Foundry/Roll20-style), fights on the map's own squares, fog of war |
| 2.21 | Reputation as a system: the tracker names the event, the app gives fixed values (repeats count less, capped per reply); defined effects for each relationship level; the reasons in the People tab |
| 2.22 | 🐉 Bestiary (Create monster, import stat blocks, fights use the sheets); Markdown books (headings and read-aloud boxes); the Status shows from the start; the window opens maximized, F11 full screen; the icon is back on the game window |
| 2.22.1 | Big map pictures (20+ MB PNGs) are turned into WebP when uploaded |
| 2.22.2 | Fix: the app window froze at start (the F11 helper exposed the whole window to the page) |
| 2.22.3 | Fix: the Status tab blanked the screen before the first reply; an error in one part of the screen no longer blanks the whole app |
| 2.22.4 | The top bar no longer moves when the mouse is over the music controls; the game's title stays on one line (full name on hover) |
| 2.22.5 | The side panel's tab row scrolls sideways (mouse wheel, drag, or the ‹ › arrows); the open tab stays in view |
| 2.23 | Bestiary: a folder per book (imports go to bestiary/<book>/, 📂 Open folder, filter by book); adventures: the story walks into the next scene by itself, and a **⚔ A fight!** offer under the reply starts the scene's fight in one click |
| 2.23.1 | Starts on the main menu (Settings: *Continue from the last played card*); the top bar fits narrow windows instead of spilling over the side panel |
| 2.23.2 | The adventure's scene changes show under the reply (📍 Scene: Goblin Ambush) |
| 2.24 | Painted battle maps: Calíope paints a map (Watabou style, grid lined up) for scenes and fights that have none, keeps it in the card, and can repaint a plain-grid fight mid-fight |
| 2.24.1 | ↺ Restart: start a game over from the card's opening with the same character (full HP), keeping or deleting the old run |
| 2.25 | Fights by the rules: faster enemies act at once, typed attacks (and /attack, /dodge) are rolled by the app and update the fight, you move on your own turn by clicking the lit squares, checks show their DC before the roll, one roll per reply and one check per round, adventure fights start by themselves |
| 2.25.1 | The start screen's AC counts armour and shield (chain mail + shield = 18, not 10 + DEX); fights wait for the ⚔ button again by default; a sword knocked away in a fight stays in the bag |
| 2.25.2 | Enemies find their way on wide plain grids; tests skip when a test-only package is missing |
| 2.25.3 | Click a story picture to see it big; card pictures reach running games; the face follows the text when the Aedo forgets the mood |
| 2.26.0 | Companions (up to 3 per card, the Aedo voices them, Calíope plays them in fights, healers heal), Play solo with fights scaled to one hero, 5e death saving throws |
