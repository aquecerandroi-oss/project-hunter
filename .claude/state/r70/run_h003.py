"""R70 / H-003 — os 5 preditores congelados do R68 em h ∈ {60, 120, 240}, pelo moinho.

Reusa **sem alterar** `load68.py` e `signals68.py` do R68: `Bars.take` é o único acesso
a histórico e levanta `LookAheadError` se alguma fonte fechar depois da decisão.

O que o moinho **não** reproduz do desenho do R68, e que fica dito no relatório:
walk-forward de várias dobras (treino 14 d / teste 7 d, passo 7 d) e o baseline
"sempre dentro". Aqui há bootstrap de blocos de 3 dias, purga, limiares congelados e
uma fronteira única treino/teste — nada mais.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "r68"))

import numpy as np  # noqa: E402

from infra.research.protocol import run_hypothesis  # noqa: E402
from infra.research.report import render  # noqa: E402
from infra.research.spec import (  # noqa: E402
    DecisionPolicy,
    HypothesisSpec,
    InferencePlan,
    ObservabilityColumns,
    PreRegistration,
    Split,
)
from load68 import bars_for, load_csv_gz  # noqa: E402
from signals68 import PREDICTORS, compute  # noqa: E402

HERE = Path(__file__).resolve().parent
COST = 0.0014
"""Custo medido de ida-e-volta do lado à vista (R68 E1.9): 0,14 % por operação."""
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
BLOCK_DAYS = 3
_RAW: dict | None = None


def _raw() -> dict:
    global _RAW
    if _RAW is None:
        _RAW = load_csv_gz(HERE / "deep.csv.gz")
    return _RAW


def _instant(minute: int) -> datetime:
    return EPOCH + timedelta(minutes=int(minute))


def panel(h: int, predictor: str) -> list[dict[str, object]]:
    """Pontos de decisão do horizonte `h`, com o preditor como variável 0/1.

    A decisão acontece no fecho da barra `i` (`close_time[i]`); o desfecho é o retorno
    da barra seguinte, líquido do custo. Só barras contíguas na grelha entram.
    """
    rows: list[dict[str, object]] = []
    for symbol, bars in sorted(bars_for(_raw(), h).items()):
        n = len(bars)
        if n < 3:
            continue
        sig = compute(bars)
        i = np.arange(n - 1)
        contiguous = bars.bucket_start[i + 1] == bars.bucket_start[i] + h
        i = i[contiguous & sig["eligible"][i]]
        if i.size == 0:
            continue
        # o desfecho lê a barra i+1, que fecha DEPOIS da decisão: é o rótulo, não uma
        # feature, e por isso não passa (nem pode passar) por `Bars.take`.
        ret = bars.close[i + 1] / bars.close[i] - 1.0 - COST
        flag = sig[predictor][i].astype(float)
        close_time = bars.close_time[i]
        for k in range(i.size):
            when = _instant(close_time[k])
            rows.append(
                {
                    "mercado": symbol,
                    "t": when,
                    "dia": when.date().isoformat(),
                    "bloco3d": f"b{(when - EPOCH) // timedelta(days=BLOCK_DAYS):05d}",
                    "ret": float(ret[k]),
                    "sinal": float(flag[k]),
                    "as_of": when,
                    "computed_at": when,
                    "tape_as_of": when,
                }
            )
    return rows


def spec_for(h: int, predictor: str) -> HypothesisSpec:
    return HypothesisSpec(
        name=f"H-003 — {predictor} em h = {h} min (lado à vista, universo U2)",
        origin=(
            "R68 parte B — h=240 ficou inconclusivo em 5 células (partb_U2.txt 28–32: IC "
            "atravessando zero em todas) · KB-0149 §7"
        ),
        loader=lambda h=h, p=predictor: panel(h, p),
        decision_instant="t",
        outcome="ret",
        variable="sinal",
        direction="high",
        observability=ObservabilityColumns("as_of", "computed_at", "tape_as_of", strict=True),
        inference=InferencePlan(
            cluster="mercado",
            stratum="dia",
            block="bloco3d",
            thresholds=(),
            reps=5_000,
            seed=68,
        ),
        policy=DecisionPolicy(
            frozen_threshold=0.5,
            minimum_effect=0.0010,
            require_plateau=False,
        ),
        pre_registration=PreRegistration(
            prediction=(
                "pelo menos uma célula rende ≥ +0,10 % líquido por operação com Holm < 0,05 "
                "ao custo medido de 0,14 %"
            ),
            refutation="limite superior do IC 95 % abaixo do MRE de +0,10 % em todas as células",
            decision_rule=(
                "CONFIRMA com D>0, D≥MRE, IC 95 % inferior>0, p de permutação<0,05, braço "
                "selecionado lucrativo em nível e a fatia de teste a repetir o sinal. "
                "PLANALTO DESLIGADO NO PRÉ-REGISTO: o preditor é booleano (entra/não entra), "
                "um degrau real, e não há limiar contínuo para varrer — varrer 0,4/0,5/0,6 "
                "sobre 0 e 1 devolveria a mesma partição e fingiria um planalto. "
                "LIMITE DO MOINHO: o walk-forward de várias dobras do R68 (treino 14 d / "
                "teste 7 d, passo 7 d) e o baseline 'sempre dentro' NÃO são reproduzíveis "
                "aqui; corre uma fronteira única treino/teste com purga de 1 bloco."
            ),
            registered_on="2026-09-23",
            threshold_policy=(
                "preditor booleano: limiar 0,5 separa 1 de 0, sem escolha nenhuma nos dados; "
                "os parâmetros internos dos 5 preditores são os do pré-registo do R68"
            ),
        ),
        split=Split(column="bloco3d", train_until="b06899", purge=1),
        assumptions=(
            "custo de ida-e-volta 0,14 % por operação, já subtraído do desfecho",
            "desfecho = fecho da barra seguinte ÷ fecho da barra da decisão − 1 − custo",
            "a guarda que vale aqui é `Bars.take`/`assert_causal` do R68, dentro do loader: "
            "nenhuma feature lê barra que feche depois da decisão",
            "universo U2 do R68 (16 perpétuos), velas de 1 min `is_final` de 2026-07-25 em diante",
        ),
    )


if __name__ == "__main__":
    h, predictor = int(sys.argv[1]), sys.argv[2]
    print(render(run_hypothesis(spec_for(h, predictor))))
