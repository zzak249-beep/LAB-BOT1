"""Seguimiento de resultados de cada senal (win rate) y backtest rapido del historico.

Criterio: primer toque entre SL y TP de la senal (si ambos caen en la misma vela, cuenta
SL). Sin comisiones ni parciales: es la medida de calidad de la SENAL, no el PnL real.
"""
import numpy as np


def resolve(side, entry, sl, tp, t_sig, d, timeout_bars):
    """-> (resultado, R). resultado: win | loss | expired | open."""
    risk = abs(entry - sl)
    if risk <= 0:
        return "open", 0.0
    sgn = 1.0 if side == "LONG" else -1.0
    t = d["t"]
    start = int(np.searchsorted(t, t_sig, side="right"))
    for j in range(start, len(t)):
        if side == "LONG":
            if d["l"][j] <= sl:
                return "loss", -1.0
            if d["h"][j] >= tp:
                return "win", (tp - entry) / risk
        else:
            if d["h"][j] >= sl:
                return "loss", -1.0
            if d["l"][j] <= tp:
                return "win", (entry - tp) / risk
        if j - start + 1 >= timeout_bars:
            return "expired", (d["c"][j] - entry) * sgn / risk
    return "open", 0.0


def _pct(w, l):
    return None if (w + l) == 0 else 100.0 * w / (w + l)


def fmt_wr(w, l):
    p = _pct(w, l)
    return "s/d" if p is None else f"{p:.1f}% ({w}/{w + l})"


class Stats:
    KINDS = ("BO", "RV", "SW")

    def __init__(self, state):
        self.state = state
        s = state.get("stats", {})
        s.setdefault("open", {})
        for k in ("wins", "losses", "expired"):
            s.setdefault(k, 0)
        s.setdefault("total_r", 0.0)
        s.setdefault("by_kind", {})
        for k in self.KINDS:
            s["by_kind"].setdefault(k, {"w": 0, "l": 0})
        self.s = s

    def _save(self):
        self.state.put("stats", self.s)

    def add_open(self, sym, sig):
        self.s["open"][f"{sym}|{sig.time}"] = {"sym": sym, "side": sig.side, "kind": sig.kind, "entry": sig.entry,
                                               "sl": sig.sl, "tp": sig.tp, "t": sig.time}
        self._save()

    def open_symbols(self):
        return {o["sym"] for o in self.s["open"].values()}

    def update(self, sym, d, timeout_bars):
        events = []
        if d is None:
            return events
        for key, o in list(self.s["open"].items()):
            if o["sym"] != sym:
                continue
            res, r = resolve(o["side"], o["entry"], o["sl"], o["tp"], o["t"], d, timeout_bars)
            if res == "open":
                continue
            del self.s["open"][key]
            if res == "win":
                self.s["wins"] += 1
                self.s["by_kind"][o["kind"]]["w"] += 1
                self.s["total_r"] += r
            elif res == "loss":
                self.s["losses"] += 1
                self.s["by_kind"][o["kind"]]["l"] += 1
                self.s["total_r"] += r
            else:
                self.s["expired"] += 1
            events.append(dict(o, result=res, r=r))
        if events:
            self._save()
        return events

    def summary(self):
        s = self.s
        kinds = " · ".join(f"{k} {fmt_wr(s['by_kind'][k]['w'], s['by_kind'][k]['l'])}" for k in self.KINDS
                           if s["by_kind"][k]["w"] + s["by_kind"][k]["l"] > 0)
        return (f"Win rate: {fmt_wr(s['wins'], s['losses'])} · R total {s['total_r']:+.1f}"
                f" · abiertas {len(s['open'])} · expiradas {s['expired']}" + (f"\n{kinds}" if kinds else ""))


class History:
    """Backtest rapido sobre las velas descargadas (senales pasadas ya resueltas)."""

    def __init__(self):
        self.w = self.l = 0
        self.rw = self.rl = 0.0
        self.by = {k: [0, 0] for k in Stats.KINDS}

    def add(self, sig, d, an_n, timeout_bars):
        if sig.idx == an_n - 1:
            return
        res, r = resolve(sig.side, sig.entry, sig.sl, sig.tp, sig.time, d, timeout_bars)
        if res == "win":
            self.w += 1
            self.rw += r
            self.by[sig.kind][0] += 1
        elif res == "loss":
            self.l += 1
            self.rl += 1.0
            self.by[sig.kind][1] += 1

    def text(self, days, nsym):
        n = self.w + self.l
        if n == 0:
            return f"📊 Backtest rápido (~{days:.1f} días, {nsym} símbolos): sin señales cerradas."
        pf = self.rw / self.rl if self.rl > 0 else float("inf")
        kinds = " · ".join(f"{k} {fmt_wr(*self.by[k])}" for k in Stats.KINDS if sum(self.by[k]) > 0)
        return (f"📊 <b>Backtest rápido</b> (~{days:.1f} días, {nsym} símbolos)\n"
                f"Win rate {fmt_wr(self.w, self.l)} · R total {self.rw - self.rl:+.1f} · PF {pf:.2f}\n{kinds}")
