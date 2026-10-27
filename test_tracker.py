import numpy as np

from lce_bot.state import State
from lce_bot.strategy import Signal
from lce_bot.tracker import Stats, History, resolve, fmt_wr, cost_r


def mk(h, l, c=None):
    n = len(h)
    return {"t": np.arange(n) * 300_000, "o": np.array(c or h, float), "h": np.array(h, float),
            "l": np.array(l, float), "c": np.array(c or h, float), "v": np.ones(n)}


def test_resolve_long_win_loss_open_expired():
    d = mk([100, 101, 103, 104], [99, 100, 101, 102])
    assert resolve("LONG", 100, 98, 103, 0, d, 50) == ("win", 1.5)
    d = mk([100, 101, 101, 101], [99, 100, 97, 100])
    assert resolve("LONG", 100, 98, 103, 0, d, 50) == ("loss", -1.0)
    d = mk([100, 101, 101.5], [99, 100, 99.5])
    assert resolve("LONG", 100, 98, 103, 0, d, 50)[0] == "open"
    assert resolve("LONG", 100, 98, 103, 0, d, 2)[0] == "expired"


def test_resolve_short_and_same_bar_counts_sl():
    d = mk([100, 101, 100], [99, 97, 98])
    assert resolve("SHORT", 100, 102, 97, 0, d, 50) == ("win", 1.5)
    d = mk([100, 103, 100], [99, 96, 98])                 # toca SL y TP en la misma vela
    assert resolve("SHORT", 100, 102, 97, 0, d, 50) == ("loss", -1.0)


def test_stats_flow_and_persistence(tmp_path):
    st = State(str(tmp_path))
    s = Stats(st)
    sig = Signal(idx=0, time=0, side="LONG", kind="BO", entry=100, sl=98, tp=103, rr=1.5, atr=1)
    s.add_open("AAA-USDT", sig)
    ev = s.update("AAA-USDT", mk([100, 101, 103], [99, 100, 101]), 50)
    assert ev[0]["result"] == "win" and s.s["wins"] == 1 and s.s["total_r"] == 1.5
    assert "Win rate: 100.0% (1/1)" in Stats(State(str(tmp_path))).summary()
    assert fmt_wr(0, 0) == "s/d"


def test_history_counts_only_closed():
    h = History()
    d = mk([100, 101, 103, 104], [99, 100, 101, 102])
    h.add(Signal(idx=0, time=0, side="LONG", kind="RV", entry=100, sl=98, tp=103, rr=1.5, atr=1), d, 4, 50)
    h.add(Signal(idx=3, time=900_000, side="LONG", kind="RV", entry=100, sl=98, tp=103, rr=1.5, atr=1), d, 4, 50)
    assert h.w == 1 and h.l == 0
    assert "Win rate 100.0% (1/1)" in h.text(3.5, 10)


def test_cost_r_and_net_stats(tmp_path):
    # riesgo 2% del precio, coste 0.07%/lado -> 0.14% ida y vuelta = 0.07 R
    assert cost_r(100.0, 98.0, 0.07) == __import__("pytest").approx(0.07)
    st = State(str(tmp_path))
    s = Stats(st, 0.07)
    sig = Signal(idx=0, time=0, side="LONG", kind="BO", entry=100, sl=98, tp=103, rr=1.5, atr=1)
    s.add_open("AAA-USDT", sig)
    ev = s.update("AAA-USDT", mk([100, 101, 103], [99, 100, 101]), 50)
    assert abs(ev[0]["r"] - 1.5) < 1e-9 and abs(ev[0]["r_net"] - 1.43) < 1e-9
    assert abs(s.s["total_r_net"] - 1.43) < 1e-9
    assert "R neto +1.4" in s.summary()
    h = History(0.07)
    d = mk([100, 101, 103, 104], [99, 100, 101, 102])
    h.add(Signal(idx=0, time=0, side="LONG", kind="RV", entry=100, sl=98, tp=103, rr=1.5, atr=1), d, 4, 50)
    assert abs(h.nw - 1.43) < 1e-9 and "Neto de costes" in h.text(3.5, 10)
