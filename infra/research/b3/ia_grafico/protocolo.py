"""Parâmetros congelados da H-042 e o texto do pedido ``ia_grafico_prompt/1``.

Tudo o que muda o resultado mora aqui, escolhido **sem** dado real (desenho §1, §5, §6). Mudar
qualquer valor depois do congelamento é outra versão — nunca edição no lugar.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal
from typing import Any

VERSAO_PROMPT = "ia_grafico_prompt/1"

# --- instantes e execução (desenho §1.1, §1.4) -------------------------------------------
INSTANTES_APOS_ABERTURA = tuple(timedelta(minutes=m) for m in range(30, 361, 30))
ATRASO_DECISAO = timedelta(minutes=1)
TOLERANCIA_ENTRADA = timedelta(minutes=5)
VALIDADE_LIMITE = timedelta(minutes=30)
HORIZONTE = timedelta(minutes=60)
HORIZONTES_PATAMAR = (timedelta(minutes=45), timedelta(minutes=75))

# --- contrato e custo (plano MERCADO-TRADICIONAL §1.4; mesmos números da H-038r) ----------
TICK = Decimal(5)
CUSTO_PERNA_PTS = Decimal("1.28")  # R$ 0,256 por perna ÷ R$ 0,20 por ponto
DESLIZE_TICKS = 1  # adverso, pelo lado, em toda perna

# --- braço direcional: geometria do arnês, simétrica e independente do lado (Astra R1) ----
ATR_BARRAS = 14
ATR_MULTIPLO = Decimal(2)

# --- estatística (desenho §6) ---------------------------------------------------------------
MRE_BP = 3.0
SEMENTE = 42042
REPLICAS = 10_000

ESQUEMA_RESPOSTA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "side",
        "entry_type",
        "entry_y",
        "stop_y",
        "target_y",
        "confidence",
        "levels",
        "rationale",
    ],
    "properties": {
        "side": {"type": "string", "enum": ["buy", "sell", "none"]},
        "entry_type": {"type": ["string", "null"], "enum": ["market", "limit", None]},
        "entry_y": {"type": ["number", "null"]},
        "stop_y": {"type": ["number", "null"]},
        "target_y": {"type": ["number", "null"]},
        "confidence": {"type": "number"},
        "levels": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "y1", "bars_ago1", "y2", "bars_ago2", "note"],
                "properties": {
                    "kind": {"type": "string", "enum": ["support", "resistance", "trendline"]},
                    "y1": {"type": "number"},
                    "bars_ago1": {"type": ["integer", "null"]},
                    "y2": {"type": ["number", "null"]},
                    "bars_ago2": {"type": ["integer", "null"]},
                    "note": {"type": "string"},
                },
            },
        },
        "rationale": {"type": "string"},
    },
}

_PEDIDO = """\
You are a discretionary intraday trader of the Brazilian mini-index future (WIN).
The image is a 5-minute candlestick chart of the last 120 bars up to the decision time {hora}
(Brasilia time). The last candle on the right closed exactly at the decision time.

Axis: the vertical axis is 100 x ln(price / last close), labelled in percent; 0.00 is the last
close. Dashed vertical lines separate trading sessions. The bottom panel is volume, scaled to the
window maximum. There is no date, no symbol and no price on purpose.

Task: like a human trader, study the chart, draw the support and resistance levels and the
trendlines you see, and decide whether to enter now, trying to anticipate the next move.

Fixed execution rules: a market order fills at the open of the next 1-minute bar; a limit order
is valid for 30 minutes and fills only if price trades through it; the position is closed at the
latest 60 minutes after the fill or at the session close; round-trip cost is about 0.6 bp plus
1 tick (5 points) of slippage per side. "none" is a valid answer.

Answer with JSON only, no other text, with exactly these keys:
- side: "buy" | "sell" | "none"
- entry_type: "market" | "limit" | null (null when side is "none")
- entry_y: the limit price in axis units, or null for market and none (buy limits below 0,
  sell limits above 0, at most 3.00 away)
- stop_y, target_y: axis units (buy: stop_y < entry < target_y; sell: the reverse; the entry is
  0 for market orders), null when side is "none"; the stop 0.05 to 3.00 and the target 0.05 to
  5.00 away from the entry
- confidence: a number from 0 to 1
- levels: up to 10 objects {{"kind": "support" | "resistance" | "trendline", "y1", "bars_ago1",
  "y2", "bars_ago2", "note"}}; support and resistance use y1 only (bars_ago1, y2 and bars_ago2
  null); trendlines use two points, bars_ago counted from the last candle (0) leftwards (max 119)
- rationale: at most 600 characters
"""


def pedido(hora_brt: str) -> str:
    """O texto enviado com a imagem; ``hora_brt`` = "HH:MM" (a hora do dia não data o período)."""
    if len(hora_brt) != 5 or hora_brt[2] != ":" or not hora_brt.replace(":", "").isdigit():
        raise ValueError("hora_brt precisa ser HH:MM")
    return _PEDIDO.format(hora=hora_brt)


SHA256_MODELO_PEDIDO = hashlib.sha256(_PEDIDO.encode()).hexdigest()
