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
4. Calíope opens in **its own window**, with a one-minute **tour** (you can skip it). The black window stays minimized; **don't close it** while playing.
   **Closing the Calíope window stops everything.**
5. It may offer a desktop shortcut. Say yes, and next time just use the shortcut.

---

## 4. Give it a brain: the AI model (once)

Calíope has its own built-in AI engine; you don't need any other program.

1. In the left sidebar click **🧠 Models**.
2. At the top, click **Download engine** (about 30 MB). Wait until it says it is ready.
3. Open the **Find more** tab. The box at the top, **Your PC**, shows your graphics card and the best model for it; **🔍 Find it** searches it for you. Or search for: `Stheno-v3.2`.
4. Open **L3-8B-Stheno-v3.2** (a GGUF version) and pick the file that fits your graphics card. The list shows a note on each size.
   - **8 GB card: `Q4_K_M`** (or `Q4_K_S`), about 5 GB. This is the recommended one: great at roleplay and fast.
   - 6 GB card: `Q3_K_M`.
   - 12 GB or more: `Q6_K` or `Q8_0` (better quality).
5. Click **Download** and wait (the **Downloads** tab shows the progress).
6. Open the **My models** tab and click **Load** on Stheno. Loading takes 10 to 60 seconds.
7. Optional, but it improves memory: search for `nomic-embed-text` (GGUF), download it, and click **Use for memory** on it.

The sidebar shows **Model server online** when it's ready.

> Already have LM Studio with models? In 🧠 Models → **Browse this PC**, pick your `.gguf` file. It is used directly, with no second download.

---

## 5. Your first game

1. Click **＋ New game** and pick a card (the app comes with example worlds).
   - **👥** on a card shows its characters.
   - If you received a **`.caliope`** file, click **Import a card** and choose it.
2. If the card has more than one start, choose one under **Choose your start**.
3. Create your character: **Who are you?** (roleplay cards) or **Create your sheet** (adventure cards).
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

### Useful buttons
- Under a reply: **Continue ▸** (keep writing), **↻** (write it again), **⏪** (rewind to there), **⑂** (start a new game from that moment).
- Top of the chat: **↶ Undo**, **📜 Recap** ("Previously, in…"), **🎵 Music**, **Aa** (text size and colours), **🔍** (search).
- 🎲 **roll buttons** appear when the Aedo asks for a check, and 🛒 **buy buttons** when something has a price.
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
| Anything else | Restore the black window from the taskbar; the error is written there. |

Your games are saved automatically, and a backup is made every day (Settings → Backups).

---

## 7. How to report what you find

This is a test, so bugs are expected and every report helps. When something breaks or feels wrong, send:

1. **What you did** (the steps), and **what you expected** vs **what happened**.
2. A **screenshot** of the Calíope window.
3. If there was an error: the **last lines of the black window** (restore it from the taskbar, select the text, right-click to copy, or take a screenshot).
4. Your **graphics card** and **model** (e.g. "RX 580 8 GB, Stheno Q4_K_M").

Things that are especially useful to test:
- Installing, downloading and loading a model on **your** PC
- A long game: does the Aedo remember earlier events? Try closing a **Canto** in the Journal.
- Fights (⚔ Combat tab), dice buttons, buying things
- The **Muse**, narration voice and scene pictures

Thank you, and have fun!
