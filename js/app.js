(function () {
  const TRADING_DAYS = 252;
  const DTE = 1;

  const $ = (id) => document.getElementById(id);
  const fmtMoney = (n) => {
    if (n == null || !isFinite(n)) return "—";
    const neg = n < 0;
    const a = Math.abs(n);
    const s = a >= 1000 ? a.toLocaleString(undefined, { maximumFractionDigits: 0 }) : a.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return (neg ? "−" : "") + "$" + s;
  };
  const fmtNum = (n, d) => (n == null || !isFinite(n) ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));

  let state = {
    ticker: "^SPX",
    name: "SPX",
    wing: 5,
    ivDefault: 20,
    price: null,
    liveOk: true,
    quoteAsOfSec: null,
    quoteSource: null,
    canvasLW: 960,
    canvasLH: 420
  };

  let resizeTimer = null;
  function debouncedResize() {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      resizeTimer = null;
      updateMetrics();
    }, 120);
  }
  window.addEventListener("resize", debouncedResize);

  function layoutCanvas() {
    const canvas = $("payoffCanvas");
    const wrap = canvas.parentElement;
    const cw = wrap && wrap.clientWidth ? wrap.clientWidth : 960;
    const logicalW = Math.max(280, Math.min(960, Math.floor(cw)));
    const logicalH = Math.round((420 / 960) * logicalW);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(logicalW * dpr));
    canvas.height = Math.max(1, Math.floor(logicalH * dpr));
    canvas.style.width = logicalW + "px";
    canvas.style.height = logicalH + "px";
    state.canvasLW = logicalW;
    state.canvasLH = logicalH;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
  }

  function clearStrikeError() {
    $("strikeError").classList.remove("show");
    $("strikeError").textContent = "";
  }

  function showStrikeError(msg) {
    $("strikeError").textContent = msg;
    $("strikeError").classList.add("show");
  }

  function strikesOrdered(lpK, spK, scK, lcK) {
    return lpK < spK && spK < scK && scK < lcK;
  }

  function syncSuggestedWingsFromShorts() {
    const w = state.wing;
    const ssp = parseFloat($("sugShortPut").value);
    const ssc = parseFloat($("sugShortCall").value);
    if (isFinite(ssp)) $("sugLongPut").value = ssp - w;
    else $("sugLongPut").value = "";
    if (isFinite(ssc)) $("sugLongCall").value = ssc + w;
    else $("sugLongCall").value = "";
  }

  function legsStrikesEmpty() {
    return ["lpStrike", "spStrike", "scStrike", "lcStrike"].every(function (id) {
      const v = $(id).value;
      if (v === "" || v == null) return true;
      return !isFinite(parseFloat(v));
    });
  }

  function applySuggestionsToLegs(fromUserClick) {
    const fields = [
      ["spStrike", "sugShortPut"],
      ["lpStrike", "sugLongPut"],
      ["scStrike", "sugShortCall"],
      ["lcStrike", "sugLongCall"]
    ];
    fields.forEach(function (pair) {
      const v = $(pair[1]).value;
      if (v !== "") $(pair[0]).value = v;
    });
    if (fromUserClick) {
      const b = $("btnApplySuggest");
      b.classList.add("just-applied");
      const prev = b.textContent;
      b.textContent = "Applied ✓";
      setTimeout(function () {
        b.classList.remove("just-applied");
        b.textContent = prev;
      }, 900);
    }
    updateMetrics();
  }

  function oneSdDollars(price, ivPct) {
    if (price == null || !isFinite(price) || ivPct == null || !isFinite(ivPct)) return null;
    return price * (ivPct / 100) / Math.sqrt(TRADING_DAYS);
  }

  function roundStrike(price, wing) {
    if (wing >= 5) return Math.round(price / 5) * 5;
    return Math.round(price);
  }

  function recomputeSuggestions() {
    const p = effectivePrice();
    const iv = parseFloat($("ivPct").value);
    const aggrRaw = parseFloat($("aggrSlider").value);
    let aggrFactor = isFinite(aggrRaw) ? aggrRaw : 1;
    aggrFactor = Math.max(0.25, Math.min(1, aggrFactor));
    $("aggrValue").textContent = aggrFactor.toFixed(2);

    if (p == null || !isFinite(p) || !isFinite(iv) || iv <= 0) {
      $("sugShortPut").value = "";
      $("sugShortCall").value = "";
      $("sugLongPut").value = "";
      $("sugLongCall").value = "";
      $("emMoveLine").innerHTML =
        'Suggested short band: <span class="range">±$—</span> → <span class="range">—</span>';
      $("sdProbLabel").textContent =
        "~68% model probability inside suggested shorts at 1.0×1SD (normal approx.). Adjust slider to change band width.";
      return;
    }
    const sd = oneSdDollars(p, iv);
    const bandAbs = sd * aggrFactor;
    const low = p - bandAbs;
    const high = p + bandAbs;
    const w = state.wing;
    const ssp = roundStrike(low, w);
    const ssc = roundStrike(high, w);
    const slp = ssp - w;
    const slc = ssc + w;
    $("sugShortPut").value = ssp;
    $("sugShortCall").value = ssc;
    $("sugLongPut").value = slp;
    $("sugLongCall").value = slc;

    const insidePct = (normalCDF(aggrFactor) - normalCDF(-aggrFactor)) * 100;
    $("sdProbLabel").textContent =
      "~" +
      insidePct.toFixed(0) +
      "% model probability of closing inside suggested short strikes (normal approx., ±" +
      aggrFactor.toFixed(2) +
      "σ intraday band). Not financial advice.";

    $("emMoveLine").innerHTML =
      'Suggested short band: <span class="range">±$' +
      fmtNum(bandAbs, 2) +
      '</span> <span style="color:var(--muted);font-size:0.92em">(' +
      aggrFactor.toFixed(2) +
      "×1SD)</span> → " +
      '<span class="range">$' +
      fmtNum(low, 2) +
      " to $" +
      fmtNum(high, 2) +
      "</span>";
  }

  function effectivePrice() {
    const o = parseFloat($("spotOverride").value);
    if (isFinite(o) && o > 0) return o;
    if (state.price != null && isFinite(state.price)) return state.price;
    return null;
  }

  function normalCDF(x) {
    const t = 1 / (1 + 0.2316419 * Math.abs(x));
    const d = 0.3989423 * Math.exp(-x * x / 2);
    let p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
    if (x > 0) p = 1 - p;
    return p;
  }

  function popProfitZone(S0, sigmaDollars, LBE, UBE) {
    if (S0 == null || sigmaDollars == null || !isFinite(sigmaDollars) || sigmaDollars <= 0) return null;
    if (LBE == null || UBE == null || !isFinite(LBE) || !isFinite(UBE) || UBE <= LBE) return null;
    const z1 = (LBE - S0) / sigmaDollars;
    const z2 = (UBE - S0) / sigmaDollars;
    return normalCDF(z2) - normalCDF(z1);
  }

  function plAtExpiryPerShare(S, lpK, spK, scK, lcK, spR, lpP, scR, lcP) {
    const putShort = Math.max(0, spK - S);
    const putLong = Math.max(0, lpK - S);
    const callShort = Math.max(0, S - scK);
    const callLong = Math.max(0, S - lcK);
    return (spR - lpP - putShort + putLong) + (scR - lcP - callShort + callLong);
  }

  function updateMetrics() {
    layoutCanvas();
    clearStrikeError();

    const spK = parseFloat($("spStrike").value);
    const lpK = parseFloat($("lpStrike").value);
    const scK = parseFloat($("scStrike").value);
    const lcK = parseFloat($("lcStrike").value);
    const spR = parseFloat($("spPrem").value);
    const lpP = parseFloat($("lpPrem").value);
    const scR = parseFloat($("scPrem").value);
    const lcP = parseFloat($("lcPrem").value);
    const n = parseInt($("contracts").value, 10);
    const p0 = effectivePrice();
    const iv = parseFloat($("ivPct").value);

    const legsOk = [spK, lpK, scK, lcK, spR, lpP, scR, lcP].every((v) => isFinite(v)) && n >= 1;

    if (!legsOk) {
      ["outNetCredit", "outMaxProfit", "outMaxLoss", "outLBE", "outUBE", "outZoneWidth", "outRR", "outPoP"].forEach((id) => {
        $(id).textContent = "—";
      });
      drawPayoff(null);
      return;
    }

    if (!strikesOrdered(lpK, spK, scK, lcK)) {
      showStrikeError(
        "Strikes must be ordered low to high: long put < short put < short call < long call. Fix the legs—metrics below are hidden until the order is valid."
      );
      ["outNetCredit", "outMaxProfit", "outMaxLoss", "outLBE", "outUBE", "outZoneWidth", "outRR", "outPoP"].forEach((id) => {
        $(id).textContent = "—";
      });
      drawPayoff(null);
      return;
    }

    const net = spR + scR - lpP - lcP;
    const putW = spK - lpK;
    const callW = lcK - scK;
    const maxLossPerShare = Math.max(putW, callW) - net;
    const maxProfit = net * 100 * n;
    const maxLoss = Math.max(0, maxLossPerShare) * 100 * n;
    const LBE = spK - net;
    const UBE = scK + net;
    const zoneW = UBE - LBE;

    $("outNetCredit").textContent = fmtMoney(net);
    $("outMaxProfit").textContent = fmtMoney(maxProfit);
    $("outMaxLoss").textContent = fmtMoney(maxLoss);
    $("outLBE").textContent = fmtNum(LBE, 2);
    $("outUBE").textContent = fmtNum(UBE, 2);
    $("outZoneWidth").textContent = fmtNum(zoneW, 2);
    $("outRR").textContent = maxProfit > 0 && isFinite(maxLoss) ? fmtNum(maxLoss / maxProfit, 2) : "—";

    const sigma = p0 != null && isFinite(iv) && iv > 0 ? oneSdDollars(p0, iv) : null;
    const pop = popProfitZone(p0, sigma, LBE, UBE);
    $("outPoP").textContent = pop != null ? (pop * 100).toFixed(1) + "%" : "—";

    drawPayoff({
      lpK, spK, scK, lcK, spR, lpP, scR, lcP, net, n, LBE, UBE, p0, sigma
    });
  }

  function drawPayoff(ctxData) {
    const canvas = $("payoffCanvas");
    const ctx = canvas.getContext("2d");
    const W = state.canvasLW || 960;
    const H = state.canvasLH || 420;
    const padL = 56;
    const padR = 18;
    const padT = 22;
    const padB = 48;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    ctx.fillStyle = "#0a0e14";
    ctx.fillRect(0, 0, W, H);

    if (!ctxData || ctxData.p0 == null || !isFinite(ctxData.p0)) {
      ctx.fillStyle = "#8b949e";
      ctx.font = "14px " + getComputedStyle(document.body).fontFamily;
      ctx.fillText("Set underlying price to draw diagram.", padL, H / 2);
      return;
    }

    const p0 = ctxData.p0;
    const xMin = p0 * 0.97;
    const xMax = p0 * 1.03;
    const xToPx = (x) => padL + ((x - xMin) / (xMax - xMin)) * plotW;
    const { lpK, spK, scK, lcK, spR, lpP, scR, lcP, net, n, LBE, UBE, sigma } = ctxData;

    const samples = 200;
    let yMin = 0;
    let yMax = 0;
    const curve = [];
    for (let i = 0; i <= samples; i++) {
      const S = xMin + (i / samples) * (xMax - xMin);
      const y = plAtExpiryPerShare(S, lpK, spK, scK, lcK, spR, lpP, scR, lcP) * 100 * n;
      curve.push({ x: S, y });
      yMin = Math.min(yMin, y);
      yMax = Math.max(yMax, y);
    }
    const padY = Math.max(80, (yMax - yMin) * 0.08);
    yMin -= padY;
    yMax += padY;
    const yToPx = (y) => padT + plotH - ((y - yMin) / (yMax - yMin)) * plotH;

    function xClip(x) {
      return Math.max(padL, Math.min(W - padR, x));
    }

    if (sigma != null && isFinite(sigma) && sigma > 0) {
      const x1 = xToPx(p0 - sigma);
      const x2 = xToPx(p0 + sigma);
      ctx.fillStyle = "rgba(88, 166, 255, 0.12)";
      ctx.fillRect(x1, padT, x2 - x1, plotH);
    }

    const lbeX = xToPx(LBE);
    const ubeX = xToPx(UBE);
    const profitLeft = Math.min(lbeX, ubeX);
    const profitRight = Math.max(lbeX, ubeX);
    ctx.fillStyle = "rgba(63, 185, 80, 0.18)";
    ctx.fillRect(profitLeft, padT, profitRight - profitLeft, plotH);
    ctx.fillStyle = "rgba(248, 81, 73, 0.12)";
    ctx.fillRect(padL, padT, profitLeft - padL, plotH);
    ctx.fillRect(profitRight, padT, padL + plotW - profitRight, plotH);

    ctx.strokeStyle = "#30363d";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, yToPx(0));
    ctx.lineTo(padL + plotW, yToPx(0));
    ctx.stroke();

    ctx.strokeStyle = "#58a6ff";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    for (let i = 0; i < curve.length; i++) {
      const px = xToPx(curve[i].x);
      const py = yToPx(curve[i].y);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();

    function vline(x, color, dash) {
      const px = xClip(xToPx(x));
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      if (dash) ctx.setLineDash(dash);
      ctx.beginPath();
      ctx.moveTo(px, padT);
      ctx.lineTo(px, padT + plotH);
      ctx.stroke();
      ctx.restore();
    }

    [lpK, spK, scK, lcK].forEach((k) => vline(k, "#6e7681", [4, 3]));
    vline(LBE, "#d29922", [2, 2]);
    vline(UBE, "#d29922", [2, 2]);
    vline(p0, "#58a6ff", null);

    ctx.fillStyle = "#8b949e";
    ctx.font = "11px " + getComputedStyle(document.body).fontFamily;
    ctx.textAlign = "center";
    for (let i = 0; i <= 6; i++) {
      const x = xMin + (i / 6) * (xMax - xMin);
      const px = xToPx(x);
      ctx.fillText(x < 1000 ? x.toFixed(2) : x.toFixed(0), px, H - 18);
    }
    ctx.textAlign = "right";
    ctx.fillText(fmtMoney(yMax).replace("$", "") + " $", padL - 6, yToPx(yMax) + 4);
    ctx.fillText(fmtMoney(yMin).replace("$", "") + " $", padL - 6, yToPx(yMin) + 4);
    ctx.fillText("0 $", padL - 6, yToPx(0) + 4);
  }

  function yahooChartUrl(ticker) {
    return (
      "https://query1.finance.yahoo.com/v8/finance/chart/" +
      encodeURIComponent(ticker) +
      "?interval=1m&range=1d&includePrePost=true&_=" +
      Date.now()
    );
  }

  function yahooQuoteUrl(ticker) {
    return (
      "https://query1.finance.yahoo.com/v7/finance/quote?symbols=" +
      encodeURIComponent(ticker) +
      "&_=" +
      Date.now()
    );
  }

  function lastFiniteIndexFromSeries(arr) {
    if (!arr || !arr.length) return -1;
    for (var i = arr.length - 1; i >= 0; i--) {
      var v = arr[i];
      if (v != null && isFinite(v)) return i;
    }
    return -1;
  }

  function parseChartQuote(j) {
    var r = j && j.chart && j.chart.result && j.chart.result[0];
    if (!r) throw new Error("No result");
    var meta = r.meta || {};
    var ts = r.timestamp;
    var q = r.indicators && r.indicators.quote && r.indicators.quote[0];
    var price = null;
    var idx = -1;
    if (q) {
      idx = lastFiniteIndexFromSeries(q.close);
      if (idx >= 0) price = q.close[idx];
      if (price == null) {
        idx = lastFiniteIndexFromSeries(q.open);
        if (idx >= 0) price = q.open[idx];
      }
    }
    var asOfSec = null;
    if (idx >= 0 && ts && ts[idx] != null && isFinite(ts[idx])) asOfSec = ts[idx];
    if (asOfSec == null && meta.regularMarketTime != null && isFinite(meta.regularMarketTime)) {
      asOfSec = meta.regularMarketTime;
    }
    if (price == null || !isFinite(price)) price = meta.regularMarketPrice;
    if (price == null || !isFinite(price)) price = meta.postMarketPrice;
    if (price == null || !isFinite(price)) price = meta.preMarketPrice;
    if (price == null || !isFinite(price)) throw new Error("No price");
    return { price: price, asOfSec: asOfSec, source: "chart" };
  }

  function parseV7Quote(j) {
    var r = j.quoteResponse && j.quoteResponse.result && j.quoteResponse.result[0];
    if (!r) throw new Error("No quote");
    var price = r.regularMarketPrice;
    if (price == null || !isFinite(price)) price = r.postMarketPrice;
    if (price == null || !isFinite(price)) price = r.preMarketPrice;
    if (price == null || !isFinite(price)) throw new Error("No price");
    var asOfSec = r.regularMarketTime;
    if (asOfSec == null || !isFinite(asOfSec)) asOfSec = r.postMarketTime;
    if (asOfSec == null || !isFinite(asOfSec)) asOfSec = r.preMarketTime;
    return { price: price, asOfSec: asOfSec, source: "quote" };
  }

  async function fetchYahooDirectChart(ticker) {
    var res = await fetch(yahooChartUrl(ticker), { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    return parseChartQuote(await res.json());
  }

  async function fetchYahooDirectQuote(ticker) {
    var res = await fetch(yahooQuoteUrl(ticker), { cache: "no-store" });
    if (!res.ok) throw new Error("quote HTTP " + res.status);
    return parseV7Quote(await res.json());
  }

  async function fetchYahooDirectBundle(ticker) {
    try {
      return await fetchYahooDirectQuote(ticker);
    } catch (a) {
      return await fetchYahooDirectChart(ticker);
    }
  }

  function fetchYahooJsonpChart(ticker) {
    return new Promise(function (resolve, reject) {
      var cb = "yfJsonp_" + Date.now() + "_" + Math.floor(Math.random() * 1e9);
      var script = document.createElement("script");
      var timer = setTimeout(function () {
        cleanup();
        reject(new Error("JSONP timeout"));
      }, 15000);
      function cleanup() {
        clearTimeout(timer);
        try {
          delete window[cb];
        } catch (e) {}
        if (script.parentNode) script.parentNode.removeChild(script);
      }
      window[cb] = function (data) {
        cleanup();
        try {
          resolve(parseChartQuote(data));
        } catch (err) {
          reject(err);
        }
      };
      script.onerror = function () {
        cleanup();
        reject(new Error("JSONP load error"));
      };
      script.src = yahooChartUrl(ticker) + "&callback=" + cb;
      document.head.appendChild(script);
    });
  }

  function fetchYahooJsonpQuote(ticker) {
    return new Promise(function (resolve, reject) {
      var cb = "yfQ_" + Date.now() + "_" + Math.floor(Math.random() * 1e9);
      var script = document.createElement("script");
      var timer = setTimeout(function () {
        cleanup();
        reject(new Error("JSONP quote timeout"));
      }, 15000);
      function cleanup() {
        clearTimeout(timer);
        try {
          delete window[cb];
        } catch (e) {}
        if (script.parentNode) script.parentNode.removeChild(script);
      }
      window[cb] = function (data) {
        cleanup();
        try {
          resolve(parseV7Quote(data));
        } catch (err) {
          reject(err);
        }
      };
      script.onerror = function () {
        cleanup();
        reject(new Error("JSONP quote load error"));
      };
      script.src = yahooQuoteUrl(ticker) + "&callback=" + cb;
      document.head.appendChild(script);
    });
  }

  async function fetchYahooJsonpBundle(ticker) {
    try {
      return await fetchYahooJsonpQuote(ticker);
    } catch (a) {
      return await fetchYahooJsonpChart(ticker);
    }
  }

  async function fetchYahooCorsProxyChart(ticker) {
    var y = yahooChartUrl(ticker);
    var proxied = "https://corsproxy.io/?" + encodeURIComponent(y);
    var res = await fetch(proxied, { cache: "no-store" });
    if (!res.ok) throw new Error("proxy HTTP " + res.status);
    return parseChartQuote(await res.json());
  }

  async function fetchYahooCorsProxyQuote(ticker) {
    var y = yahooQuoteUrl(ticker);
    var proxied = "https://corsproxy.io/?" + encodeURIComponent(y);
    var res = await fetch(proxied, { cache: "no-store" });
    if (!res.ok) throw new Error("proxy quote HTTP " + res.status);
    return parseV7Quote(await res.json());
  }

  async function fetchYahooCorsProxyBundle(ticker) {
    try {
      return await fetchYahooCorsProxyQuote(ticker);
    } catch (a) {
      return await fetchYahooCorsProxyChart(ticker);
    }
  }

  async function fetchYahooAllOriginsChart(ticker) {
    var y = yahooChartUrl(ticker);
    var u = "https://api.allorigins.win/get?url=" + encodeURIComponent(y);
    var res = await fetch(u, { cache: "no-store" });
    var body = await res.json();
    if (!body.contents) throw new Error("allorigins empty");
    return parseChartQuote(JSON.parse(body.contents));
  }

  async function fetchYahooAllOriginsQuote(ticker) {
    var y = yahooQuoteUrl(ticker);
    var u = "https://api.allorigins.win/get?url=" + encodeURIComponent(y);
    var res = await fetch(u, { cache: "no-store" });
    var body = await res.json();
    if (!body.contents) throw new Error("allorigins quote empty");
    return parseV7Quote(JSON.parse(body.contents));
  }

  async function fetchYahooAllOriginsBundle(ticker) {
    try {
      return await fetchYahooAllOriginsQuote(ticker);
    } catch (a) {
      return await fetchYahooAllOriginsChart(ticker);
    }
  }

  async function fetchYahoo(ticker) {
    var methods = [
      fetchYahooDirectBundle,
      fetchYahooJsonpBundle,
      fetchYahooCorsProxyBundle,
      fetchYahooAllOriginsBundle
    ];
    var last = null;
    for (var i = 0; i < methods.length; i++) {
      try {
        return await methods[i](ticker);
      } catch (err) {
        last = err;
      }
    }
    throw last || new Error("All quote methods failed");
  }

  function updatePriceAsOfLabel() {
    var el = $("priceAsOf");
    if (!el) return;
    var o = parseFloat($("spotOverride").value);
    if (isFinite(o) && o > 0) {
      el.textContent =
        "Using override spot below (Yahoo price is ignored for the calculator until override is cleared).";
      return;
    }
    if (state.quoteAsOfSec != null && isFinite(state.quoteAsOfSec)) {
      var d = new Date(state.quoteAsOfSec * 1000);
      var src = state.quoteSource === "quote" ? "quote snapshot" : "last 1m bar";
      el.textContent =
        "Yahoo " +
        src +
        " • as of " +
        d.toLocaleString() +
        " (local). Free index data can lag your broker or differ from another Yahoo page; use override for an exact mark.";
      return;
    }
    if (state.price != null && state.liveOk) {
      el.textContent =
        "Yahoo (time stamp unavailable). Compare to your broker; use override if you need the exact mark.";
      return;
    }
    el.textContent = "";
  }

  async function refreshPrice() {
    if ($("btnRefresh").disabled) return;
    $("btnRefresh").disabled = true;
    $("fetchWarn").classList.remove("show");
    $("priceDisplay").textContent = "…";
    try {
      try {
        var q = await fetchYahoo(state.ticker);
        state.price = q.price;
        state.quoteAsOfSec = q.asOfSec != null && isFinite(q.asOfSec) ? q.asOfSec : null;
        state.quoteSource = q.source || null;
        state.liveOk = true;
        $("priceDisplay").textContent = fmtNum(q.price, 2);
        updatePriceAsOfLabel();
      } catch (e) {
        state.liveOk = false;
        state.price = null;
        state.quoteAsOfSec = null;
        state.quoteSource = null;
        $("fetchWarn").classList.add("show");
        $("spotOverrideDetails").open = true;
        $("priceDisplay").textContent = "—";
        updatePriceAsOfLabel();
      }
      recomputeSuggestions();
      if (legsStrikesEmpty()) applySuggestionsToLegs(false);
      else updateMetrics();
    } finally {
      $("btnRefresh").disabled = false;
    }
  }

  function setTicker(btn) {
    document.querySelectorAll(".ticker-btns button").forEach((b) => b.classList.remove("active-ticker", "primary"));
    btn.classList.add("active-ticker", "primary");
    state.ticker = btn.getAttribute("data-ticker");
    state.name = btn.getAttribute("data-name");
    state.wing = parseInt(btn.getAttribute("data-wing"), 10);
    state.ivDefault = parseFloat(btn.getAttribute("data-iv-default"));
    $("ivPct").value = String(state.ivDefault);
    $("underlyingLabel").textContent = state.name + " (" + state.ticker + ")";
    refreshPrice();
  }

  $("btnSPX").addEventListener("click", function () { setTicker(this); });
  $("btnQQQ").addEventListener("click", function () { setTicker(this); });
  $("btnRefresh").addEventListener("click", refreshPrice);

  $("btnApplySuggest").addEventListener("click", function () {
    applySuggestionsToLegs(true);
  });

  ["sugShortPut", "sugShortCall"].forEach(function (id) {
    $(id).addEventListener("input", function () {
      syncSuggestedWingsFromShorts();
    });
  });

  ["ivPct", "spotOverride", "aggrSlider", "contracts", "spStrike", "lpStrike", "scStrike", "lcStrike", "spPrem", "lpPrem", "scPrem", "lcPrem"].forEach(function (id) {
    $(id).addEventListener("input", function () {
      if (id === "ivPct" || id === "spotOverride" || id === "aggrSlider") recomputeSuggestions();
      if (id === "spotOverride") updatePriceAsOfLabel();
      updateMetrics();
    });
  });

  function parseTradeLegLines(text) {
    const lines = text
      .split(/\r?\n/)
      .map(function (l) {
        return l.trim();
      })
      .filter(function (l) {
        return l.length > 0;
      });
    if (lines.length !== 4) {
      return { error: "Enter exactly four non-empty lines (strike + CALL or PUT each)." };
    }
    const legs = [];
    const re = /^(\d+(?:\.\d+)?)\s+(CALL|PUT)$/i;
    for (let i = 0; i < 4; i++) {
      const m = lines[i].match(re);
      if (!m) {
        return { error: 'Line ' + (i + 1) + ' must look like "6465 CALL" or "6390 PUT".' };
      }
      legs.push({ strike: parseFloat(m[1]), right: m[2].toUpperCase() });
    }
    return { legs: legs, legsText: lines.join("\n") };
  }

  function parseContractsLine(s) {
    const t = String(s || "").trim();
    if (!t) return { error: 'Enter contracts, e.g. "3 SPX".' };
    const m = t.match(/^(\d+)\s+(.+)$/);
    if (!m) return { error: 'Use format: number then symbol, e.g. "3 SPX".' };
    const qty = parseInt(m[1], 10);
    const symbol = m[2].trim().replace(/\s+/g, "").slice(0, 32);
    if (!isFinite(qty) || qty < 1) return { error: "Contract count must be a positive integer." };
    if (!symbol) return { error: "Symbol missing after count." };
    return { contractsQty: qty, contractsSymbol: symbol };
  }

  function localDayStart(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
  }

  function tradeMatchesFilter(savedAtIso, filter) {
    const t = new Date(savedAtIso);
    if (isNaN(t.getTime())) return false;
    const now = new Date();
    const startToday = localDayStart(now);
    const startYesterday = new Date(startToday);
    startYesterday.setDate(startYesterday.getDate() - 1);
    const start7 = new Date(startToday);
    start7.setDate(start7.getDate() - 7);
    const start30 = new Date(startToday);
    start30.setDate(start30.getDate() - 30);
    const tt = localDayStart(t).getTime();
    if (filter === "all") return true;
    if (filter === "today") return tt === startToday.getTime();
    if (filter === "yesterday") return tt === startYesterday.getTime();
    if (filter === "last7") return t >= start7;
    if (filter === "last30") return t >= start30;
    return true;
  }

  function flashTradeStatus(msg, isError) {
    const el = $("tradeJournalStatus");
    if (!el) return;
    el.textContent = msg;
    el.classList.remove("error", "ok");
    el.classList.add(isError ? "error" : "ok");
    if (!isError && msg) {
      setTimeout(function () {
        if (el.textContent === msg) {
          el.textContent = "";
          el.classList.remove("error", "ok");
        }
      }, 4000);
    }
  }

  let cachedTrades = [];
  const TRADE_STORAGE_KEY = "ironCondorTradesV1";
  let tradeStorageMode = "api";

  function loadTradesFromLocalStorage() {
    try {
      const raw = localStorage.getItem(TRADE_STORAGE_KEY);
      if (!raw) return [];
      const j = JSON.parse(raw);
      return Array.isArray(j) ? j : [];
    } catch (e) {
      return [];
    }
  }

  function saveTradesToLocalStorage(trades) {
    try {
      localStorage.setItem(TRADE_STORAGE_KEY, JSON.stringify(trades));
    } catch (e) {
      flashTradeStatus("Could not write browser storage (private mode or quota).", true);
      throw e;
    }
  }

  function newTradeId() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    return "t-" + Date.now() + "-" + Math.floor(Math.random() * 1e9);
  }

  function buildTradeRecord(body) {
    const toNum = function (v) {
      if (v === "" || v == null) return null;
      const n = Number(v);
      return isFinite(n) ? n : null;
    };
    return {
      id: newTradeId(),
      savedAt: new Date().toISOString(),
      legsText: String(body.legsText || "").slice(0, 2000),
      legs: body.legs,
      breakEvenLower: toNum(body.breakEvenLower),
      breakEvenUpper: toNum(body.breakEvenUpper),
      maxProfit: toNum(body.maxProfit),
      maxLoss: toNum(body.maxLoss),
      contractsQty: body.contractsQty,
      contractsSymbol: String(body.contractsSymbol || "").trim().slice(0, 32),
      notes: String(body.notes || "").slice(0, 4000),
    };
  }

  function fmtTradeMoney(n) {
    if (n == null || !isFinite(n)) return "—";
    const a = Math.abs(n);
    const s = a.toLocaleString(undefined, { maximumFractionDigits: 0 });
    return (n < 0 ? "−$" : "$") + s;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderTradeList() {
    const container = $("tradeList");
    const filtEl = $("tradeFilter");
    const filter = filtEl ? filtEl.value : "last7";
    if (!container) return;
    const list = cachedTrades.filter(function (x) {
      return tradeMatchesFilter(x.savedAt, filter);
    });
    if (list.length === 0) {
      container.innerHTML =
        '<p style="color:var(--muted);font-size:0.88rem;margin:0;">No trades in this view. Save one above or widen the filter.</p>';
      return;
    }
    container.innerHTML = "";
    list.forEach(function (tr) {
      const card = document.createElement("div");
      card.className = "trade-card";
      const when = new Date(tr.savedAt);
      const whenStr = when.toLocaleString(undefined, {
        weekday: "short",
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
      const legsShow = tr.legs.map(function (l) {
        return l.strike + " " + l.right;
      }).join("\n");
      const beL = tr.breakEvenLower != null ? fmtNum(tr.breakEvenLower, 2) : "—";
      const beU = tr.breakEvenUpper != null ? fmtNum(tr.breakEvenUpper, 2) : "—";
      const notesBlock = tr.notes
        ? '<p style="margin:0.35rem 0 0;color:var(--muted);font-size:0.82rem;">' +
          escapeHtml(tr.notes) +
          "</p>"
        : "";
      card.innerHTML =
        '<div class="trade-card-head">' +
        "<div><strong>" +
        escapeHtml(String(tr.contractsQty)) +
        " × " +
        escapeHtml(tr.contractsSymbol) +
        "</strong></div>" +
        '<div class="trade-card-meta">' +
        escapeHtml(whenStr) +
        "</div></div>" +
        '<div class="trade-card-legs">' +
        escapeHtml(legsShow) +
        "</div>" +
        '<div class="trade-card-stats">' +
        "<span>BE: <strong>" +
        beL +
        "</strong> – <strong>" +
        beU +
        "</strong></span>" +
        "<span>Max profit: <strong>" +
        fmtTradeMoney(tr.maxProfit) +
        "</strong></span>" +
        "<span>Max loss: <strong>" +
        fmtTradeMoney(tr.maxLoss) +
        "</strong></span>" +
        "</div>" +
        notesBlock +
        '<div class="trade-card-actions"><button type="button" class="btn-delete-trade" data-id="' +
        escapeHtml(tr.id) +
        '">Delete</button></div>';
      container.appendChild(card);
    });
    container.querySelectorAll(".btn-delete-trade").forEach(function (btn) {
      btn.addEventListener("click", function () {
        deleteTrade(btn.getAttribute("data-id"));
      });
    });
  }

  async function loadTrades() {
    const status = $("tradeJournalStatus");
    if (!$("tradeLegsInput")) return;
    try {
      const res = await fetch("/api/trades", { cache: "no-store" });
      if (res.ok) {
        tradeStorageMode = "api";
        const data = await res.json();
        cachedTrades = data.trades || [];
        if (status) {
          status.textContent = "";
          status.classList.remove("error", "ok");
        }
        renderTradeList();
        return;
      }
    } catch (e) {}
    tradeStorageMode = "local";
    cachedTrades = loadTradesFromLocalStorage();
    if (status) {
      status.textContent =
        "Trade log: browser only (python -m http.server has no API). Run npm start in this folder to save trades under data/trades.json on disk.";
      status.classList.remove("error", "ok");
    }
    renderTradeList();
  }

  async function saveTrade() {
    const parsed = parseTradeLegLines($("tradeLegsInput").value);
    if (parsed.error) {
      flashTradeStatus(parsed.error, true);
      return;
    }
    const cc = parseContractsLine($("tradeContractsLine").value);
    if (cc.error) {
      flashTradeStatus(cc.error, true);
      return;
    }
    const body = {
      legsText: parsed.legsText,
      legs: parsed.legs,
      breakEvenLower: $("tradeBreakLower").value,
      breakEvenUpper: $("tradeBreakUpper").value,
      maxProfit: $("tradeMaxProfit").value,
      maxLoss: $("tradeMaxLoss").value,
      contractsQty: cc.contractsQty,
      contractsSymbol: cc.contractsSymbol,
      notes: $("tradeNotes").value,
    };

    function clearTradeForm() {
      $("tradeLegsInput").value = "";
      $("tradeBreakLower").value = "";
      $("tradeBreakUpper").value = "";
      $("tradeMaxProfit").value = "";
      $("tradeMaxLoss").value = "";
      $("tradeContractsLine").value = "";
      $("tradeNotes").value = "";
    }

    if (tradeStorageMode === "local") {
      try {
        const trade = buildTradeRecord(body);
        cachedTrades.unshift(trade);
        saveTradesToLocalStorage(cachedTrades);
        flashTradeStatus("Trade saved in this browser.", false);
        clearTradeForm();
        renderTradeList();
      } catch (e) {
        flashTradeStatus("Could not save to browser storage.", true);
      }
      return;
    }

    try {
      const res = await fetch("/api/trades", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      let data = {};
      const ct = res.headers.get("content-type") || "";
      try {
        if (ct.indexOf("application/json") !== -1) data = await res.json();
        else data = { _text: await res.text() };
      } catch (e2) {}
      if (res.ok) {
        flashTradeStatus("Trade saved to data/trades.json.", false);
        clearTradeForm();
        await loadTrades();
        return;
      }
      if (res.status === 400 && data.error) {
        flashTradeStatus(data.error, true);
        return;
      }
      if (res.status === 404 || res.status === 405) {
        tradeStorageMode = "local";
        const trade = buildTradeRecord(body);
        cachedTrades = loadTradesFromLocalStorage();
        cachedTrades.unshift(trade);
        saveTradesToLocalStorage(cachedTrades);
        flashTradeStatus(
          "No trade API on this server — saved in this browser. Use npm start for data/trades.json on disk.",
          false
        );
        clearTradeForm();
        const st = $("tradeJournalStatus");
        if (st) {
          st.textContent =
            "Trade log: browser only. Run npm start in the Iron Condor folder for disk-backed saves.";
          st.classList.remove("error", "ok");
        }
        renderTradeList();
        return;
      }
      flashTradeStatus(
        data.error || "Save failed (HTTP " + res.status + "). Check the terminal running npm start.",
        true
      );
    } catch (e) {
      try {
        tradeStorageMode = "local";
        const trade = buildTradeRecord(body);
        cachedTrades = loadTradesFromLocalStorage();
        cachedTrades.unshift(trade);
        saveTradesToLocalStorage(cachedTrades);
        flashTradeStatus("Server unreachable — saved in this browser. Use npm start for disk files.", false);
        clearTradeForm();
        renderTradeList();
      } catch (e2) {
        flashTradeStatus("Could not save (network or server error).", true);
      }
    }
  }

  async function deleteTrade(id) {
    if (!id || !confirm("Delete this saved trade?")) return;
    if (tradeStorageMode === "local") {
      cachedTrades = cachedTrades.filter(function (t) {
        return t.id !== id;
      });
      saveTradesToLocalStorage(cachedTrades);
      renderTradeList();
      return;
    }
    try {
      const res = await fetch("/api/trades?id=" + encodeURIComponent(id), { method: "DELETE" });
      let data = {};
      try {
        data = await res.json();
      } catch (e2) {}
      if (res.ok) {
        await loadTrades();
        return;
      }
      if (res.status === 404) {
        tradeStorageMode = "local";
        cachedTrades = loadTradesFromLocalStorage().filter(function (t) {
          return t.id !== id;
        });
        saveTradesToLocalStorage(cachedTrades);
        renderTradeList();
        return;
      }
      flashTradeStatus(data.error || "Delete failed", true);
    } catch (e) {
      flashTradeStatus("Could not delete trade.", true);
    }
  }

  function initTradeJournal() {
    if (!$("tradeLegsInput")) return;
    $("btnSaveTrade").addEventListener("click", saveTrade);
    $("tradeFilter").addEventListener("change", renderTradeList);
    loadTrades();
  }

  $("underlyingLabel").textContent = "SPX (^SPX)";
  recomputeSuggestions();
  updateMetrics();
  refreshPrice();
  initTradeJournal();
})();
  