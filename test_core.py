import hashlib
import hmac
from urllib.parse import urlencode

import numpy as np
import pytest

from lce_bot import indicators as ind
from lce_bot import strategy
from lce_bot.bingx import sign_query
from lce_bot.config import Config
from lce_bot.risk import fmt_num, round_down, size_position
from lce_bot.state import State
from helpers import synth, synth_htf


def test_sign_sorted_and_same_string():
    params = {"symbol": "BTC-USDT", "side": "BUY", "timestamp": 1, "quantity": "0.001"}
    qs = sign_query(params, "secret")
    body, sig = qs.rsplit("&signature=", 1)
    assert body == "quantity=0.001&side=BUY&symbol=BTC-USDT&timestamp=1"
    assert sig == hmac.new(b"secret", body.encode(), hashlib.sha256).hexdigest()


def test_ema_rma_seed_and_values():
    x = np.arange(1, 31, dtype=float)
    e = ind.ema(x, 5)
    assert np.isnan(e[3]) and e[4] == pytest.approx(3.0)
    assert e[5] == pytest.approx(2 / 6 * 6 + 4 / 6 * 3.0)
    r = ind.rma(x, 5)
    assert r[5] == pytest.approx(1 / 5 * 6 + 4 / 5 * 3.0)


def test_pivots():
    h = np.array([1, 2, 3, 9, 3, 2, 1, 2, 3], float)
    p = ind.pivot_high(h, 3, 3)
    assert p[6] == 9 and np.isnan(p[5])


def test_fmt_num_no_scientific():
    assert fmt_num(0.00000123, 8) == "0.00000123"
    assert "e" not in fmt_num(1e-7, 9).lower()
    assert round_down(1.2399, 2) == 1.23


def test_size_position_caps_leverage():
    s = size_position(1000, 100, 99.9, 1.0, 5, 3)         # riesgo pide 100 uds (10x) -> tope 5x
    assert s["qty"] == 50.0 and s["notional"] <= 5000
    s = size_position(1000, 100, 90, 1.0, 5, 3)
    assert s["qty"] == 1.0 and s["risk_usdt"] == pytest.approx(10.0)
    assert size_position(1000, 100, 90, 1.0, 5, 0, min_qty=5) is None


def test_state_requires_dict(tmp_path):
    st = State(str(tmp_path))
    st.put("risk", {"a": 1})
    assert State(str(tmp_path)).get("risk") == {"a": 1}
    with pytest.raises(TypeError):
        st.put("trades", [1, 2])


@pytest.mark.parametrize("seed", range(8))
def test_strategy_invariants(seed):
    cfg = Config()
    d = synth(seed=seed)
    an = strategy.run(cfg, d, synth_htf(d))
    for s in an.signals:
        if s.side == "LONG":
            assert s.sl < s.entry < s.tp
        else:
            assert s.tp < s.entry < s.sl
        assert s.rr > 0
    idx = [s.idx for s in an.signals]
    assert all(b - a > cfg.cooldown for a, b in zip(idx, idx[1:]))


def test_strategy_produces_signals_somewhere():
    cfg = Config()
    cfg.use_htf = False
    cfg.use_vol = False
    total = 0
    for seed in range(8):
        total += len(strategy.run(cfg, synth(seed=seed)).signals)
    assert total > 0


def test_breakout_scenario():
    """Zona de oferta creada por un pivote y ruptura alcista con cuerpo y volumen."""
    cfg = Config()
    cfg.use_htf = False
    cfg.use_slope = False
    n = 160
    t = 1_700_000_000_000 + np.arange(n) * 300_000
    c = np.full(n, 100.0) + np.linspace(0, 6, n)         # tendencia alcista suave
    o = np.concatenate([[100.0], c[:-1]])
    h = np.maximum(o, c) + 0.2
    l = np.minimum(o, c) - 0.2
    v = np.full(n, 100.0)
    h[100] = 110.0                                       # pivote alto -> zona de oferta
    c[140:] = c[140:]                                    # (precio por debajo)
    k = 150                                              # vela de ruptura fuerte
    o[k], c[k], h[k], l[k], v[k] = 105.0, 112.0, 112.3, 104.9, 500.0
    for j in range(k + 1, n):
        o[j], c[j], h[j], l[j] = c[j - 1], c[j - 1] + 0.1, c[j - 1] + 0.4, c[j - 1] - 0.2
    an = strategy.run(cfg, {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    longs = [s for s in an.signals if s.side == "LONG" and s.kind == "BO"]
    assert longs and longs[0].idx == k


def _cfg(**kw):
    cfg = Config()
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


ALL_ON = dict(use_adx=True, use_flow=True, use_sqz=True, use_e200_dir=True, use_e200_ext=True, use_e200_rv=True,
              use_e200_tp=True, rev_need_div=True, rev_need_sweep=True, use_struct_bo=True, use_struct_exit=True,
              use_sweep_sig=True, use_sess_lvl=True, vol_mode="kernel", use_partial=True, use_be=True,
              use_trail=True, max_bars=50, zone_max_age=200)


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("variant", ["score", "all_on", "sizing"])
def test_all_modules_run_and_invariants(seed, variant):
    kw = {"score": dict(use_score=True, min_score_bo=4, min_score_rv=2, size_by_score=True),
          "all_on": dict(ALL_ON, use_htf=False),
          "sizing": dict(size_by_score=True, use_sweep_sig=True, use_htf=False, use_vol=False)}[variant]
    cfg = _cfg(**kw)
    d = synth(seed=seed)
    an = strategy.run(cfg, d, synth_htf(d))
    for s in an.signals:
        if s.side == "LONG":
            assert s.sl < s.entry < s.tp
        else:
            assert s.tp < s.entry < s.sl
        assert s.risk_mult > 0
        if cfg.size_by_score:
            assert cfg.size_min - 1e-9 <= s.risk_mult <= cfg.size_max + 1e-9
        if cfg.use_trail:
            assert abs(s.tp - s.entry) == pytest.approx(abs(s.entry - s.sl) * cfg.rr_trail_cap)
        if cfg.use_partial:
            assert s.tp1 is not None


def test_no_new_signal_while_virtual_trade_open():
    """Mientras la operacion virtual siga abierta no puede haber otra senal (position_size == 0 en Pine)."""
    cfg = _cfg(use_htf=False, use_vol=False, cooldown=0)
    for seed in range(8):
        d = synth(seed=seed)
        an = strategy.run(cfg, d)
        for a_, b_ in zip(an.signals, an.signals[1:]):
            seg_h, seg_l = d["h"][a_.idx + 1:b_.idx + 1], d["l"][a_.idx + 1:b_.idx + 1]
            if a_.side == "LONG":
                assert (seg_l <= a_.sl).any() or (seg_h >= a_.tp).any()
            else:
                assert (seg_h >= a_.sl).any() or (seg_l <= a_.tp).any()


def test_kde_prob_logistic():
    assert strategy.kde_prob([1.0], 1.0) is None
    p_hi = strategy.kde_prob([1.0, 1.2, 0.9, 1.1, 1.0], 3.0)
    p_lo = strategy.kde_prob([1.0, 1.2, 0.9, 1.1, 1.0], 0.1)
    assert p_hi > 0.99 and p_lo < 0.05


def test_session_window():
    assert strategy._in_window("0000-0800", 3 * 3_600_000)
    assert not strategy._in_window("0000-0800", 9 * 3_600_000)
    assert strategy._in_window("2200-0600", 23 * 3_600_000) and strategy._in_window("2200-0600", 3 * 3_600_000)
