# 0DTE Iron Condor Calculator (Desktop Python)

A native **PySide6** desktop app for planning same-day (0DTE) iron condors on **SPX** and **QQQ**.

No Node.js, no browser app required. Run locally with:

```bash
python app.py
```

## What It Does

- Pulls live Yahoo spot (or use manual spot override)
- Suggests strikes from IV-based expected move
- Shows a Thinkorswim-style 4-leg order preview
- Calculates:
  - net credit
  - max profit / max loss
  - lower and upper breakeven
  - profit-zone width
  - risk/reward
  - estimated PoP (normal approximation)
- Draws expiration P/L graph
- Saves trade journal entries to disk (`data/trades.json`)

> Educational tool only. Not financial advice.

## Setup

### 1. Create and activate venv

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Launch

```powershell
python app.py
```

## Daily Workflow

1. Select `SPX` or `QQQ`
2. Click **Refresh Price** (or enter **Override Spot**)
3. Enter IV from Thinkorswim (see section below)
4. Use aggressiveness slider for baseline strikes
5. Fine-tune suggested strikes manually (or with +/- step buttons)
6. Copy the TOS-style preview into Thinkorswim order entry
7. Enter premiums from chain/broker to evaluate metrics
8. Save the trade in the journal if desired

## Where To Find IV In Thinkorswim

Use the value shown in the option chain header row under **Net Chng %** (circled below in your screenshot).

- Open **Trade** tab
- Load the underlying (ex: SPX)
- In the option chain row for your expiry, read the **Net Chng %** value
- Enter that number as IV in this calculator

### Screenshot

Add your screenshot file to:

`docs/images/tos-iv-location.png`

Then this image will render automatically in GitHub README:

![Thinkorswim IV location](docs/images/tos-iv-location.png)

## Notes

- If your connection is slow, quote refresh may take a few seconds.
- If quote fetch fails, use **Override Spot** and continue offline.
- Trade logs are local to this machine in `data/trades.json`.

## Project Structure

```text
Iron Condor/
|-- app.py
|-- iron_condor/
|   |-- __init__.py
|   |-- config.py
|   |-- math_utils.py
|   |-- yahoo_client.py
|   |-- storage.py
|   `-- ui.py
|-- data/
|   `-- trades.json (created on first save)
|-- requirements.txt
|-- pyproject.toml
`-- README.md
```

## License

Personal use.
