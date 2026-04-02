# 0DTE Iron Condor Calculator (SPX / QQQ)

A self-contained tool for **same-day (0DTE) iron condors** on **SPX** (^GSPC) and **QQQ**: intraday expected-move suggestions, payoff chart, metrics, and an optional **trade log**.

This is **not financial advice**. All probabilities and Yahoo prices are approximations—verify strikes and P&amp;L with your broker.

---

## What you need

| Goal | Requirement |
|------|----------------|
| **Recommended (full app)** | [Node.js](https://nodejs.org/) **18+** |
| **Calculator only (no trade file on disk)** | Any static server, e.g. Python 3 |

---

## Quick start (recommended)

From the folder that contains `package.json` and `index.html`:

```bash
cd path/to/Iron-Condor
npm start
```

Your browser should open to **http://127.0.0.1:5173/** (or check the terminal for the exact URL).

- **Refresh Price** pulls a spot from Yahoo (with fallbacks). Use **Override spot** for your broker’s mark when needed.
- **Trade log** saves to **`data/trades.json`** on your machine (created on first save).

### Port already in use?

If you see `EADDRINUSE` on port **5173**, stop the other terminal running `npm start`, or use another port:

```powershell
# PowerShell
$env:PORT=5174; npm start
```

```cmd
REM CMD
set PORT=5174 && npm start
```

---

## Alternative: Python static server

If you only want the HTML/CSS/JS **without** saving trades to a file:

```bash
cd path/to/Iron-Condor
python -m http.server 8000
```

Open **http://localhost:8000/** (use the folder that contains `index.html`).

**Limits:**

- No **`/api/trades`** endpoint → trades are stored in the **browser only** (`localStorage`), not `data/trades.json`.
- Clearing site data removes those saves.

---

## Trade log

| How you run the app | Where trades are stored |
|---------------------|-------------------------|
| `npm start` (Node server) | `data/trades.json` on disk |
| `python -m http.server` | This browser’s `localStorage` |

You can **filter** saved trades (today, yesterday, last 7 days, past 30 days, all) and **delete** entries from the UI.

---

## Project layout

```
Iron Condor/
├── index.html          # Main page
├── css/styles.css      # Styles
├── js/app.js           # Calculator + trade UI
├── dev-server.mjs      # Static server + REST API for trades
├── package.json        # npm start → node dev-server.mjs
├── data/
│   └── .gitkeep        # Keeps data/ in git; trades file is optional
└── README.md
```

---

## GitHub: clone on a new machine

```bash
git clone https://github.com/praneethR5/Simple-Iron-Condor-Frame.git
cd Simple-Iron-Condor-Frame
npm start
```

First time you **Save trade** with `npm start`, **`data/trades.json`** is created locally (it is **gitignored** so your personal trades are not pushed by default).

---

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| **Blank trade saves / “Save failed”** (old behavior) | Use **`npm start`**, or rely on **browser storage** when using Python only (current app supports both). |
| **Yahoo price looks wrong** | Use **Override spot**; free index data can lag or differ from TOS. |
| **CORS / price fetch errors** | Prefer **`npm start`** or Python from **localhost** (not `file://`). |
| **`iron-condor-0dte.html` 404** | That single-file name was removed; use **`/`** or **`index.html`**. |

---

## License

jajajajajaja
