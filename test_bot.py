import time

import numpy as np

from lce_bot.config import Config
from lce_bot.main import Bot, to_dict
from helpers import synth


class FakeBX:
    base = "fake"

    def __init__(self, d):
        self.d = d

    def contracts(self):
        return [{"symbol": "AAA-USDT", "pricePrecision": 4, "quantityPrecision": 1, "tradeMinQuantity": 0.1,
                 "status": 1, "apiStateOpen": "true"},
                {"symbol": "NCSKFOO2USD-USDT", "status": 1, "apiStateOpen": "true"}]

    def tickers(self):
        return [{"symbol": "AAA-USDT", "quoteVolume": "9000000"}]

    def klines(self, sym, interval, limit):
        ms = 300_000 if interval == "5m" else 3_600_000
        now = int(time.time() * 1000)
        end = (now // ms) * ms                      # ultima vela = en formacion
        n = len(self.d["c"])
        rows = []
        for i in range(n):
            t = end - (n - i) * ms + ms
            rows.append((t, self.d["o"][i], self.d["h"][i], self.d["l"][i], self.d["c"][i], self.d["v"][i]))
        return rows


def test_to_dict_drops_forming_bar():
    now = 1_000_000
    rows = [(0, 1, 1, 1, 1, 1), (300_000, 1, 1, 1, 1, 1), (900_000, 1, 1, 1, 1, 1)]
    d = to_dict(rows, 300_000, now_ms=now + 0)
    assert list(d["t"]) == [0, 300_000]


def test_scan_cycle_signals_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    cfg = Config()
    bot = Bot(cfg)
    bot.bx = FakeBX(synth(seed=3, n=400))
    sent = []
    bot.tg.send = lambda m: sent.append(m) or True
    bot.refresh_universe(force=True)
    assert bot.universe == ["AAA-USDT"]                 # NCSK filtrado
    bot.scan()
    assert bot.cycles == 1
    assert bot.funnel_total["ok"] + bot.funnel_total["datos_viejos"] + bot.funnel_total["pocas_velas"] == 1
