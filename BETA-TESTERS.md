# Calíope: guide for beta testers

Thank you for testing! Calíope is a roleplay and tabletop RPG app that runs **entirely on your PC**: an AI game
master (the **Aedo**) plays stories with you. There are no accounts and no subscriptions, and your games never
leave your computer.

This guide takes about 20 minutes the first time, most of it waiting for downloads.

---

## 1. What you need

- **Windows 10 or 11**.
- **A graphics card with 8 GB of memory** is ideal (e.g. RX 580 8 GB, GTX 1070, RTX 3060). AMD and NVIDIA both work.
  - With 6 GB or less, use a smaller model (step 4 explains).
  - With no graphics card it works, but slowly.
- **About 10 GB of free disk space** (the AI model is about 5 GB).
- Internet for the first setup only.

---

## 2. Install the two helpers (once)

1. **Python 3.12**: download it from <https://www.python.org/downloads/> (version 3.12.x).
   On the first install screen, **tick "Add python.exe to PATH"**, then *Install Now*.
2. **Node.js LTS**: download it from <https://nodejs.org/> (the button that says **LTS**) and install it with the defaults.

If you already have them, skip this.

---

## 3. Get Calíope and start it

1. On the GitHub page of the project, click the green **Code** button → **Download ZIP**.
2. Unzip it somewhere simple, for example `C:\Users\<you>\Desktop\caliope`. Avoid folders inside OneDrive if you can.
3. Open the folder and **double-click `Play.bat`**.
   - The first time it installs what it needs. This takes **3 to 8 minutes**, and a black window shows the progress. Let it finish.
   - If Windows shows "Windows protected your PC", click **More info → Run anyway**. The file is just a script from this project.
4. Calíope opens in **its own window**, with a one-minute **tour** (you can skip it). On its first step pick **English** or **Português (Brasil)**: menus and stories switch to that language (Settings can change each one later). In Portuguese, the fight cards and the lines under each reply are in Portuguese too; if you see English anywhere, send a screenshot. The black window hides itself while Calíope is open. To stop, just close the Calíope window.
   **Closing the Calíope window stops everything.**
5. It may offer a desktop shortcut. Say yes, and next time just use the shortcut.

---

## 4. Give it a brain: the AI model (once)

Calíope has its own built-in AI engine; you don't need any other program.

1. In the left sidebar click **🧠 Models**.
2. Open the **Find more** tab. The box at the top, **Your PC**, shows your graphics card and the best model for it; **🔍 Find it** searches it for you. Or search for: `Stheno-v3.2`.
3. Open **L3-8B-Stheno-v3.2** (a GGUF version) and pick the file that fits your graphics card. The list shows a note on each size.
   - **8 GB card: `Q4_K_M`** (or `Q4_K_S`), about 5 GB. This is the recommended one: great at roleplay and fast.
   - 6 GB card: `Q3_K_M`.
   - 12 GB or more: `Q6_K` or `Q8_0` (better quality).
4. Click **Download** and wait (the **Downloads** tab shows the progress).
5. Open the **My models** tab and click **Load** on Stheno. The first time, the engine (about 30 MB) is downloaded before it; then loading takes 10 to 60 seconds. LM Studio is not needed and is not opened.
6. Optional, but it improves memory: search for `nomic-embed-text` (GGUF), download it, and click **Use for memory** on it.

The sidebar shows **Model server online** when it's ready.

> Already have a `.gguf` model somewhere on your PC? In 🧠 Models → **Browse this PC**, pick the file. It is used directly, with no second download. LM Studio is not needed.

---

## 5. Your first game

1. Click **＋ New game** and pick a card (the app comes with example worlds).
   - **👥** on a card shows its characters.
   - If you received a **`.caliope`** file, click **Import a card** and choose it.
2. If the card has more than one start, choose one under **Choose your start**.
3. Create your character: **Who are you?** (roleplay cards) or **Create your sheet** (adventure cards).
   - Cards like Lumencia have their own sheet, and you fill it right here, like a D&D sheet: Tier, Affiliation, Attributes (1–10) and Stats (a grade like C- and its EXP, 0 / 100). Open **What the card asks for** to see the card's rules. The story then starts with your sheet ready. As you play, EXP fills each Stat's bar; a full bar raises its grade. See and correct it all in the **Sheet** tab (**✎ Edit the values**).
   - Some cards have **their own sheet** (Black Sheep's mech): pick your parts from the dropdowns; the app checks the point budget and level locks and shows the totals. It's in the Sheet tab while you play, with the card's **shop**, **bounty board**, **ranking** and **romance ladder**.
   - Add **your picture** next to the name (it shows big on your Sheet tab) and **your skills**: a name and what each one does. In the story, just write *"I use my Soul Forge"* and it happens as you described (the app pays its cost, if it has one).
   - If you chose *Let the story ask me*, answer in the chat: the Sheet tab fills in by itself. If something didn't arrive, press **📋** under your message to read it again.
   - **✨ Fill the empty fields** suggests a background, looks and personality for you.
   - **💾 Save as persona** keeps your character for other games; **🎭 Personas** loads one.
4. Read the opening scene and write what you do.

### How to write
| You write | It means |
|---|---|
| `"Hello there."` | Your character **speaks** |
| `*I draw my sword*` | Your character **acts** |
| `'He is lying.'` | Your character **thinks**. Only the Aedo knows; characters never hear it. |
| `/how much gold do I have?` | A question to the Aedo, outside the story |
| `/roll 1d20+3` | Rolls dice |
| `/wait 2 hours`, `/wait until morning` | Time passes (it only passes when you choose) |

Easier: pick a mode under the text box (**🗣 Speak · ✋ Act · 💭 Think · 🗨 Ask the Aedo**) and just type; each mode says who hears it. Starting a message with `mestre,` also asks the Aedo.

### Useful buttons
- Under a reply: **Continue ▸** (keep writing), **↻** (write it again), **⏪** (rewind to there), **⑂** (start a new game from that moment).
- Top of the chat: **↶ Undo**, **📜 Recap** ("Previously, in…"), **🎵 Music**, **Aa** (text size and colours), **🔍** (search).
- 🎲 **roll buttons** appear when the Aedo asks for a check, and 🛒 **buy buttons** when something has a price.
- **🐉 Bestiary** (bottom left): monster sheets for fights; create one or import a book's stat blocks. **F11** = full screen.
- **Relationships follow fixed rules now:** what you do (defend, help, mock, betray…) always counts the same, repeating it counts less, and each level changes how the character treats you. Open someone in the People tab to see why their value changed.
- Calíope opens on a **🏠 Main menu** with all your cards (▶ Play, ✎ Edit, ＋ New card). Start it from the desktop shortcut: no black window, just a loading screen.
- Adventure maps: **🔍 Find the grid** lines the squares up with the map; fights happen on the map with fog of war.
- No map for a fight? Calíope **paints one** that fits the scene (road, cave, dungeon, tavern…) with the grid lined up. **🎲 Paint another** in the Combat tab if you don't like it.
- **↺ Restart** (top bar, or ↺ next to the game in the list) starts the game over from the opening with the same character at full HP, handy for testing a scene again.
- **✴ Arsenal (role-play cards):** name a technique in [brackets] in your message and Calíope remembers it; characters' named moves are remembered too and come back in later fights. See the ✴ Arsenal tab.
- **Scripted default start:** in the card editor, the default start (the opening message) can now have fixed scenes too, so a card's main route can play a planned first day.
- **⟳ Update from the card** (⟳ next to the game in the list): after editing a card, bring its new characters, lore and rules into a game you already started, without losing the story.
- **Click any picture in the story** to see it big. Pictures you add to a character in the card editor now also show up in games you already started.
- **Companions**: cards can have up to 3 companions (card editor → 👥 Companions). Start a game with **Play with companions** to have them fight beside you, or **Play solo** for fights scaled to one hero. Choosing *Play with companions* opens **Set up your companions**: give each one a name, background, looks, personality and a picture for each mood (Standard, Happy, Sad, Angry…). Their Standard picture appears on their first turn in a fight, and their moods show up in the story. At 0 HP you make death saving throws instead of losing at once.
- **New look**: the icons on the left are the main menu (Games opens your list of games). Under the top bar you see your party's HP (adventures) or your card's tracker (role-play). **Library** opens the D&D 5e rules: classes, spells, feats, items.
- **New home screen:** Games, Library, Calíope settings and The Muse are four big doors; the Library is sorted by system (D&D 5e → Compendium folders, Bestiary, Rulebooks). Tell us if anything is hard to find.
- **Sharing a card:** press **📦** on a card in the main menu (or **📦 Export card** in the editor) to get a `.caliope` file with the card and all its pictures. Send it to the other player; they use **⤒ Import a card** and pick the file.
- **Describe your moves:** after each attack or spell in a fight, the *Want to describe it?* window takes a line of roleplay that shows up under that roll in the round card. Tokens on the map now show portraits.
- **Your turn in a 5e fight:** in the Combat tab you have an action, a bonus action, movement and a reaction; *Your options* lists everything you can do sorted by cost (Grapple, Dash, Second Wind, spells…). Used ones grey out. Press **⏭ End turn** when you're done: the Aedo tells your turn, then everyone else acts. Typing your turn in the chat works too.
- **Companions with 5e sheets:** under *Your companions* in the Sheet tab, 🎲 lets the system build them around your class (front-liner, healer, spellcaster, support), ✎ builds one step by step.
- **Library → 🙈 Hide from the lists** removes a repeated race or class version from the builder; **Books and rules** chooses which rules list (2014/2024) a book belongs to.
- **The builder** now has emblems; the ▸ arrow on a class, race or background shows what it gives (a class's 20 levels).
- **/correction (new):** when the Aedo gets something wrong, write `/correction` and the right version. His last reply is rewritten with it and the story continues.
- **5e level-up (new):** **⬆ Level up** now shows *What changes at level N* (slots, Rages, Sneak Attack, Lay on Hands, spells known…) and lets you pick the new cantrips and spells from your class's list. **📜 Levels** shows all 20 levels of your class. The Spells section counts how many you know or have prepared. Tell us if a number differs from your Player's Handbook.
- **5e resources (new):** the Sheet tab has a **Resources** section with your uses, Lay on Hands / Ki points and spell slots. You can also just say it in the chat (*"I use Lay on Hands for 5"*, *"I cast Cure Wounds at 2nd level"*, *"entro em fúria"*): the app spends it and shows a ✨ line under your message. In fights, spells roll by themselves and spend the slot you pick under **Cast with**; Divine Smite lights up after a melee hit; Shield and Uncanny Dodge can be taken for you on enemy turns. Tell us if something was spent that you only talked about, or not spent when you used it.
- **D&D 5e sheet** (adventures): in the Sheet tab press **Convert to a 5e sheet** or **Build with the 5e builder**. The app works out AC, HP, attacks and features. Drag spells and items onto it from **📚 Open the Library**, click a skill to roll it, press **Use** on Second Wind, and **⬆ Level up** when you have the XP. Tell us if a number looks wrong (hover AC to see how it was counted).
- **In a fight**, just write your attack (*"I swing at the goblin's neck"*) or type **/attack goblin 2**: the app rolls it and the fight updates. On your turn, click a lit square on the grid to move. Check buttons show the DC before you roll.
- **📚 Research a work** (in the Muse): type an anime/game/book name, tick the wiki pages, and get a draft card with its world, characters and lore.
- **🔁** in the music controls loops the current song.
- **Adventures:** in the card editor, *Adventure: scenes, maps and fights* imports a published adventure (PDF or pasted text). In play the **📕 Adventure** tab shows your scene, the map, XP and **⚔ Fight here**.
- The **Sheet** tab is your one character tab: on role-play cards it shows the card's own values (Lumencia's tiers…) at the top, and *Add a tracker sheet* picks a ready one (Tormenta20, Vampire, Call of Cthulhu…). The app keeps the numbers up to date.
- The **right panel** has your Sheet, Bag, People (relationships from −100 to +100, plus notes about each character: yours and the Aedo's ✒), Journal and more.
- The small **‹ ›** bubbles on the edges of the chat hide the side columns for more room.
- **🪶 The Muse** (left sidebar): brainstorm stories with the AI and turn them into new cards.
- **☾ / ☀** switches between the dark and light themes.
- **✨** beside the send button fixes the spelling and grammar of your message.

Every setting and many buttons have a **?** that explains what they do.

### Optional extras
- **Narration voice**: Settings → *Narration voice* → download a voice → 🔊 on any reply reads it aloud.
- **Scene pictures** (needs internet): Settings → *Scene pictures*.
- **Your own music**: 🎵 Music → add songs from your PC and tag them with moods.

---

## 6. If something goes wrong

| Problem | Try this |
|---|---|
| "Cannot reach the model server" | 🧠 Models → *My models* → **Load** your model again. |
| The model fails to load ("out of memory") | Settings → lower **Context window** to 6144, or set **GPU layers** to 28. Close other games and apps that use the graphics card. |
| Replies are very slow | Settings → *Reply length*: Short, and tick *Skip tracking on quiet turns*. A smaller model also helps. |
| `Play.bat` closes immediately | Python or Node.js is missing or wasn't added to PATH. Reinstall Python and tick *Add python.exe to PATH*. |
| The window doesn't open | Open <http://127.0.0.1:8000> in your browser while the black window is running. |
| Anything else | Open `backend\data\caliope.log` in the Calíope folder; the errors are written there. |

Your games are saved automatically, and a backup is made every day (Settings → Backups).

---

## 7. How to report what you find

This is a test, so bugs are expected and every report helps. When something breaks or feels wrong, send:

1. **What you did** (the steps), and **what you expected** vs **what happened**.
2. A **screenshot** of the Calíope window.
3. If there was an error: the **last lines of `backend\data\caliope.log`** (in the Calíope folder; open it with Notepad). If the app did not start at all, a screenshot of the black window.
4. Your **graphics card** and **model** (e.g. "RX 580 8 GB, Stheno Q4_K_M").

Things that are especially useful to test:
- Installing, downloading and loading a model on **your** PC
- A long game: does the Aedo remember earlier events? Try closing a **Canto** in the Journal.
- Fights (⚔ Combat tab), dice buttons, buying things
- The **Muse**, narration voice and scene pictures

Thank you, and have fun!

**Fixing the story:** if the Aedo mixes something up (a wrong name, who someone is), write **/fix** and the right fact, like *"/fix Aria is the Saintess, not Anastasia"*. Calíope keeps it for the rest of the game (📌 in the Sheet tab).

**Map tools in fights:** above the battle map, **📏 Measure** shows distances (5 ft per square), **🔥 Area** shows where a spell like Fireball lands and who's inside, and **🗺 Big map** opens the map large in the middle of the screen.

**5e character builder:** the Equipment step now gives your class's and background's starting packages (choose a or b), or the starting gold and a shop. The Spells step only shows your class's spells.
