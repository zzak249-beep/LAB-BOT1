# LCE Bot — BingX perpetuos + Telegram (Railway)

Port a Python de la estrategia **LCE v8** (núcleo **LCE v2**: zonas de oferta/demanda por pivotes,
nube EMA 9/21, rupturas BO + rechazos RV, filtro HTF sin repintado, R:R mínimo hasta el siguiente nivel).
Escanea cada vela cerrada de 5m, envía la señal a Telegram y, según `TRADE_MODE`, opera en BingX.

## Telegram: señales completas + win rate
Cada señal incluye tipo (BO/RV/SW), hora UTC, entrada, SL, TP (y TP1), R:R, ATR, tendencia HTF, volumen relativo, ADX,
riesgo y el **win rate acumulado** (total y por tipo) más el del backtest rápido.
- Cada señal se sigue hasta que toca SL (❌) o TP (✅); se avisa por Telegram con el R obtenido y el win rate actualizado.
- Sin resolver tras `SIGNAL_TIMEOUT_BARS` velas (288 = 24 h) pasa a *expirada* y no cuenta en el win rate.
- Al arrancar envía un **backtest rápido** con las últimas ~3.5 días de velas de todos los símbolos (win rate, R total, PF).
- Criterio: primer toque SL/TP de la señal (misma vela = SL), sin comisiones ni parciales. Mide la calidad de la señal,
  no el PnL real de la cuenta. Las estadísticas se guardan en `/data` y sobreviven a redeploys.
- Resumen periódico (`HEARTBEAT_HOURS`, 6 h por defecto) con win rate y embudo de filtros.

## Modos
| TRADE_MODE | Qué hace |
|---|---|
| `signals` | Solo envía señales a Telegram. No necesita claves de BingX. **Empieza aquí.** |
| `demo` | Opera en el sandbox VST (`open-api-vst.bingx.com`). Necesita claves VST. |
| `live` | Opera con dinero real. |

## Despliegue
1. Sube este repo a GitHub.
2. Telegram: crea el bot con @BotFather (token) y obtén tu `chat_id` (escríbele al bot y abre `https://api.telegram.org/bot<TOKEN>/getUpdates`).
3. Railway → New Project → Deploy from GitHub repo. Railway usa el `Procfile` (`worker: python -m lce_bot.main`).
   **No definas `startCommand` en railway.toml** (choca con el Procfile y provoca crash-loop).
4. **Añade un Volume montado en `/data`** (si no, se pierde el estado en cada redeploy).
5. Pega las variables de `RAILWAY_VARIABLES.env`.
6. Secuencia recomendada: `signals` (días) → `demo` → `live` con `RISK_PCT` bajo.

## API key de BingX
Permisos: **lectura + trading de futuros. Sin retiros.** Cuenta en **modo hedge** (el bot lo comprueba al arrancar).

## Lógica de ejecución
- Entrada a mercado; confirma que la orden está `FILLED` (no acepta cancelaciones como fills).
- SL y TP como órdenes separadas `STOP_MARKET` / `TAKE_PROFIT_MARKET` (MARK_PRICE) con `positionSide`.
  Si no se puede colocar el SL → cierra la posición al instante.
- Apalancamiento fijado en LONG **y** SHORT, margen aislado. Tamaño = `RISK_PCT` del equity / distancia al SL, tope `MAX_LEV`×equity.
- Reconciliación al arrancar contra las posiciones reales. Estado en JSON atómico (`/data/lce_state.json`).
- Opcional: parcial en TP1, BE, trailing ATR, stop por tiempo, límites diarios, pausa por pérdidas seguidas.
- Firma HMAC: `urlencode(sorted(params))`, el mismo string que se envía.

## Fidelidad con el Pine LCE v8 (script completo portado)
Portado línea a línea: zonas (con caducidad), nube EMA, HTF sin repintado, BO/RV/SW, kernel KDE (CDF logística
como el Pine), ADX, flow, squeeze, EMA200 (dirección/extensión/estiramiento/TP), divergencia RSI, estructura BOS/CHoCH,
barridos (día anterior, N velas y sesión de referencia), **modo puntuación**, **tamaño por puntuación**,
parcial + BE + trailing (`hh3/ll3 ∓ ATR×trailATR` por vela cerrada), TP final = entrada ± `RR_TRAIL_CAP`×R con trailing,
stop por tiempo y salida por estructura.

Diferencias a tener en cuenta:
- **Operación virtual:** en Pine `canSignal` exige no tener posición. El bot simula SL/TP/parcial/BE/trailing sobre el
  histórico para reproducir ese bloqueo (si SL y TP caen en la misma vela asume que salta el SL).
- **Límites de riesgo a nivel de cartera:** `MAX_DAY_LOSS`, `MAX_TRADES_DAY`, `MAX_CONS_LOSS` (pérdida > 0.3R) se
  aplican en vivo sobre el equity real de la cuenta, no por símbolo como en el backtest.
- **Sesiones en UTC** (`SESSION_UTC`, `SESS_LVL_UTC`); en Pine van en la hora del gráfico.
- Entrada a mercado al cierre de la vela de señal: el precio real puede diferir (slippage); se rechaza si R:R real < `MIN_LIVE_RR`.
- El Pine usa un solo símbolo; el bot escanea todos y aplica `MAX_POSITIONS`.

## Tests
`pip install -r requirements-dev.txt && pytest -q`
