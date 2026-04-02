import http from "http";
import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";
import { spawn } from "child_process";
import { randomUUID } from "crypto";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = __dirname;
const PORT = Number(process.env.PORT) || 5173;
const TRADES_PATH = path.join(ROOT, "data", "trades.json");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json",
  ".ico": "image/x-icon",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
};

function resolvePublicPath(urlPath) {
  let p = decodeURIComponent((urlPath || "/").split("?")[0]);
  if (p === "/" || p === "") p = "index.html";
  p = p.replace(/^\/+/, "");
  const full = path.resolve(ROOT, p);
  const rootR = path.resolve(ROOT);
  if (!full.startsWith(rootR + path.sep) && full !== rootR) return null;
  return full;
}

async function readTrades() {
  try {
    const raw = await fs.readFile(TRADES_PATH, "utf8");
    const j = JSON.parse(raw);
    return Array.isArray(j) ? j : [];
  } catch (e) {
    if (e && e.code === "ENOENT") return [];
    throw e;
  }
}

async function writeTrades(arr) {
  await fs.mkdir(path.dirname(TRADES_PATH), { recursive: true });
  const tmp = TRADES_PATH + ".tmp";
  await fs.writeFile(tmp, JSON.stringify(arr, null, 2), "utf8");
  await fs.rename(tmp, TRADES_PATH);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.writeHead(status);
  res.end(body);
}

function parseUrl(u) {
  try {
    return new URL(u, "http://127.0.0.1");
  } catch {
    return { pathname: "/", searchParams: new URLSearchParams() };
  }
}

const server = http.createServer(async (req, res) => {
  const url = parseUrl(req.url || "/");
  const pathname = url.pathname;

  if (pathname.startsWith("/api/")) {
    try {
      if (req.method === "OPTIONS") {
        res.writeHead(204, {
          "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
        });
        res.end();
        return;
      }

      if (pathname === "/api/trades" && req.method === "GET") {
        const trades = await readTrades();
        trades.sort((a, b) => String(b.savedAt).localeCompare(String(a.savedAt)));
        sendJson(res, 200, { trades });
        return;
      }

      if (pathname === "/api/trades" && req.method === "POST") {
        const raw = await readBody(req);
        let body;
        try {
          body = JSON.parse(raw || "{}");
        } catch {
          sendJson(res, 400, { error: "Invalid JSON" });
          return;
        }

        const legs = body.legs;
        if (!Array.isArray(legs) || legs.length !== 4) {
          sendJson(res, 400, { error: "Exactly four legs are required (strike + CALL or PUT each)." });
          return;
        }
        for (const leg of legs) {
          if (
            leg == null ||
            typeof leg.strike !== "number" ||
            !isFinite(leg.strike) ||
            (leg.right !== "CALL" && leg.right !== "PUT")
          ) {
            sendJson(res, 400, { error: "Each leg needs numeric strike and right CALL or PUT." });
            return;
          }
        }

        const qty = Number(body.contractsQty);
        if (!isFinite(qty) || qty < 1 || !Number.isInteger(qty)) {
          sendJson(res, 400, { error: "contractsQty must be a positive integer." });
          return;
        }

        const sym = String(body.contractsSymbol || "").trim().slice(0, 32);
        if (!sym) {
          sendJson(res, 400, { error: "contractsSymbol is required (e.g. SPX)." });
          return;
        }

        const toNum = (v) => {
          if (v === "" || v == null) return null;
          const n = Number(v);
          return isFinite(n) ? n : null;
        };

        const trade = {
          id: randomUUID(),
          savedAt: new Date().toISOString(),
          legsText: String(body.legsText || "").slice(0, 2000),
          legs,
          breakEvenLower: toNum(body.breakEvenLower),
          breakEvenUpper: toNum(body.breakEvenUpper),
          maxProfit: toNum(body.maxProfit),
          maxLoss: toNum(body.maxLoss),
          contractsQty: qty,
          contractsSymbol: sym,
          notes: String(body.notes || "").slice(0, 4000),
        };

        const trades = await readTrades();
        trades.push(trade);
        await writeTrades(trades);
        sendJson(res, 201, { trade });
        return;
      }

      if (pathname === "/api/trades" && req.method === "DELETE") {
        const id = url.searchParams.get("id");
        if (!id) {
          sendJson(res, 400, { error: "Missing id query parameter." });
          return;
        }
        const trades = await readTrades();
        const next = trades.filter((t) => t.id !== id);
        if (next.length === trades.length) {
          sendJson(res, 404, { error: "Trade not found." });
          return;
        }
        await writeTrades(next);
        sendJson(res, 200, { ok: true });
        return;
      }

      sendJson(res, 404, { error: "Unknown API route" });
    } catch (e) {
      console.error(e);
      sendJson(res, 500, { error: "Server error" });
    }
    return;
  }

  try {
    const filePath = resolvePublicPath(req.url);
    if (!filePath) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }
    const data = await fs.readFile(filePath);
    const ext = path.extname(filePath).toLowerCase();
    res.setHeader("Content-Type", MIME[ext] || "application/octet-stream");
    res.setHeader("Cache-Control", "no-store");
    res.writeHead(200);
    res.end(data);
  } catch (e) {
    if (e && e.code === "ENOENT") {
      res.writeHead(404);
      res.end("Not found");
      return;
    }
    res.writeHead(500);
    res.end("Server error");
  }
});

server.on("error", (err) => {
  if (err && err.code === "EADDRINUSE") {
    console.error(
      `\nPort ${PORT} is already in use (another npm start / dev-server is probably still running).\n` +
        "Fix: go to that terminal and press Ctrl+C, or use a different port:\n" +
        `  PowerShell:  $env:PORT=5174; npm start\n` +
        `  CMD:         set PORT=5174 && npm start\n` +
        "Find PID on Windows: netstat -ano | findstr :5173\n"
    );
    process.exit(1);
  }
  throw err;
});

server.listen(PORT, "127.0.0.1", () => {
  const url = `http://127.0.0.1:${PORT}/`;
  console.log(`0DTE Iron Condor → ${url}`);
  console.log(`Trade log file: ${TRADES_PATH}`);
  console.log("Press Ctrl+C to stop.");
  if (process.env.NO_OPEN === "1") return;
  if (process.platform === "win32") {
    spawn("cmd", ["/c", "start", "", url], { detached: true, stdio: "ignore" }).unref();
  } else if (process.platform === "darwin") {
    spawn("open", [url], { detached: true, stdio: "ignore" }).unref();
  } else {
    spawn("xdg-open", [url], { detached: true, stdio: "ignore" }).unref();
  }
});
