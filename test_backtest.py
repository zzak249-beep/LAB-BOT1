import os

import numpy as np
import pytest

from lce_bot import backtest as bt
from lce_bot import strategy
from lce_bot.bingx import BingX
from lce_bot.config import Config, PRESETS
from lce_bot.main import Bot
from helpers import synth, synth_htf


def test_klines_range_paginates_backwards(monkeypatch):
    bx = BingX()
    ms = 300_000
    allrows = [(i * ms, 1, 1, 1, 1, 1) for i in range(5000)]

    def fake(symbol, interval, limit=1000, end_time=None):
        cand = [r for r in allrows if end_time is None or r[0] <= end_time]
        return cand[-limit:]

    monkeypatch.setattr(bx, "klines", fake)
    rows = bx.klines_range("X", "5m", 1000 * ms, 4999 * ms, page=1000)
    assert rows[0][0] == 1000 * ms and rows[-1][0] == 4999 * ms and len(rows) == 4000
    # servidor que ignora endTime: corta sin bucle infinito
    monkeypatch.setattr(bx, "klines", lambda s, i, limit=1000, end_time=None: allrows[-limit:])
    assert len(bx.klines_range("X", "5m", 0, 4999 * ms, page=1000)) == 1000


def test_presets_and_env_precedence(monkeypatch):
    monkeypatch.setenv("PRESET", "calidad")
    c = Config()
    assert c.min_risk_pct == 0.8 and c.use_adx and c.min_rr == 1.5
    monkeypatch.setenv("MIN_RR", "2.5")
    assert Config().min_rr == 2.5                       # el entorno explicito gana al preset
    monkeypatch.setenv("PRESET", "inexistente")
    with pytest.raises(ValueError):
        Config()


def test_fingerprint_ignores_operational_vars(monkeypatch):
    a = Config().fingerprint()
    monkeypatch.setenv("RISK_PCT", "0.5")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    assert Config().fingerprint() == a
    monkeypatch.setenv("MIN_RR", "2")
    assert Config().fingerprint() != a


def test_new_filters_reduce_signals():
    d = synth(seed=2)
    base = Config()
    base.use_htf = False
    base.use_vol = False
    n0 = len(strategy.run(base, d).signals)
    f = bt.clone(base, {"min_risk_pct": 0.8})
    sigs = strategy.run(f, d).signals
    assert len(sigs) <= n0
    assert all(abs(s.entry - s.sl) / s.entry * 100 >= 0.8 - 1e-9 for s in sigs)
    fx = bt.clone(base, {"fixed_tp": True, "rr_fallback": 1.5})
    assert all(s.rr == pytest.approx(1.5) for s in strategy.run(fx, d).signals)


def test_eval_and_metrics_and_sweep_helpers():
    cfg = Config()
    cfg.use_htf = False
    cfg.use_vol = False
    d = synth(seed=1)
    ws = int(d["t"][-1]) - 3 * 86_400_000
    sym, out = bt._eval_symbol(("AAA", d, None, [("base", cfg), ("rv", bt.clone(cfg, {"use_breakout": False}))],
                                1e-8, 288, ws))
    assert set(out) == {"base", "rv"}
    for t, kind, win, r, c in out["base"]:
        assert t >= ws and win in (0, 1) and c > 0
    m = bt.metrics(out["base"])
    assert m["n"] == len(out["base"])
    tr, te = bt.split(out["base"], ws + 86_400_000)
    assert len(tr) + len(te) == len(out["base"])
    assert len(bt.stage1()) >= 28 and len(bt.stage2([("x", {})])) == len(bt.EXTRAS)
    assert "MIN_RR=1.5" in bt.env_text({"min_rr": 1.5, "use_adx": True}) and "USE_ADX=true" in bt.env_text({"use_adx": True})
    assert bt.passes({"n": 50, "e": .1}, {"n": 30, "e": .05, "pf": 1.3}, 30)
    assert not bt.passes({"n": 50, "e": .1}, {"n": 30, "e": -.05, "pf": 1.3}, 30)


def test_run_configs_multiprocess_matches_serial():
    cfg = Config()
    cfg.use_htf = False
    cfg.use_vol = False
    data = {f"S{i}": synth(seed=i) for i in range(3)}
    ws = int(data["S0"]["t"][-1]) - 3 * 86_400_000
    cl = [("a", cfg), ("b", bt.clone(cfg, {"min_rr": 1.5}))]
    s1 = bt.run_configs(cl, data, {}, {}, 288, ws, 1)
    s2 = bt.run_configs(cl, data, {}, {}, 288, ws, 2)
    assert {k: sorted(v) for k, v in s1.items()} == {k: sorted(v) for k, v in s2.items()}


def test_stats_reset_when_config_changes(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    b1 = Bot(Config())
    b1.stats.s["wins"] = 7
    b1.stats._save()
    b2 = Bot(Config())                                   # misma config: se conservan
    assert b2.stats.s["wins"] == 7 and b2.cfg_changed is None
    monkeypatch.setenv("MIN_RR", "2.0")
    b3 = Bot(Config())                                   # config distinta: se reinician
    assert b3.stats.s["wins"] == 0 and b3.cfg_changed and "Win rate" in b3.cfg_changed
    assert b3.state.get("stats_prev")["wins"] == 7


def test_run_sweep_and_dump_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setenv("BACKTEST_DAYS", "3")
    monkeypatch.setenv("BACKTEST_SYMBOLS", "3")
    monkeypatch.setenv("BACKTEST_WORKERS", "1")
    monkeypatch.setenv("BACKTEST_MIN_N", "1")
    monkeypatch.setenv("USE_HTF", "false")
    monkeypatch.setenv("USE_VOL", "false")
    cfg = Config()
    bot = Bot(cfg)
    sent, docs = [], []
    bot.tg.send = lambda m: sent.append(m) or True
    bot.tg.send_document = lambda n, c, cap="": docs.append((n, c)) or True
    bot.refresh_universe = lambda force=False: None
    bot.universe = ["AAA-USDT", "BBB-USDT", "CCC-USDT"]
    bot.info = {s: {"pp": 4} for s in bot.universe}
    data = {s: synth(seed=i, n=1500, t0=int(__import__("time").time() * 1000) - 1500 * 300_000)
            for i, s in enumerate(bot.universe)}
    monkeypatch.setattr(bt, "load_candles", lambda bx, c, sym, itv, days, extra_bars=0, use_cache=True: data[sym])
    bt.run_sweep(bot)
    assert any("Barrido de parámetros" in m for m in sent) and docs and docs[0][0] == "sweep.json"
    sent.clear(); docs.clear()
    bot.cfg.dump_symbol = "AAA-USDT"
    bot.cfg.dump_days = 3
    bt.run_dump(bot)
    assert any("Volcado" in m for m in sent) and docs[0][0].startswith("senales_")
