import numpy as np


def synth(n=1000, seed=0, start=100.0, bar_ms=300_000, t0=1_700_000_000_000):
    rng = np.random.default_rng(seed)
    ret = rng.normal(0, 0.004, n) + 0.02 * np.sin(np.arange(n) / 40.0) * 0.1
    c = start * np.exp(np.cumsum(ret))
    o = np.concatenate([[start], c[:-1]])
    spread = np.abs(rng.normal(0, 0.003, n)) * c
    h = np.maximum(o, c) + spread * rng.random(n)
    l = np.minimum(o, c) - spread * rng.random(n)
    v = rng.lognormal(8, 0.5, n)
    t = t0 + np.arange(n) * bar_ms
    return {"t": t.astype(np.int64), "o": o, "h": h, "l": l, "c": c, "v": v}


def synth_htf(d, ms=3_600_000):
    t = d["t"]
    buckets = t // ms
    out = {k: [] for k in "tohlcv"}
    for b in np.unique(buckets):
        m = buckets == b
        out["t"].append(int(b * ms)); out["o"].append(d["o"][m][0]); out["h"].append(d["h"][m].max())
        out["l"].append(d["l"][m].min()); out["c"].append(d["c"][m][-1]); out["v"].append(d["v"][m].sum())
    return {k: np.asarray(v) for k, v in out.items()}
