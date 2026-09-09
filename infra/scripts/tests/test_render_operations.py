"""T3.50 — o gráfico de uma operação não pode ver o futuro dela.

Roda sem rede e sem banco: ``FIXTURE`` é **uma operação real** exportada da VPS
por ``render_operations.py export`` (``session_orb v1``, XRPUSDT, 23/08/2026
11:30 BRT, saída no stop, −1,06 R), com as 101 barras de 15 min que ela carrega.
Congelada aqui de propósito: os números esperados abaixo foram medidos sobre
estes bytes.

    uv run --with matplotlib pytest infra/scripts/tests/test_render_operations.py -q

Sem matplotlib os dois testes de desenho são pulados (`importorskip`) e os de
geometria e de nota continuam valendo — matplotlib não está no `pyproject.toml`
desta árvore (T3.34) e o CI não o instala.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from render_operations import build_note, table_row  # noqa: E402
from render_operations_chart import (  # noqa: E402
    PARAMS,
    Operation,
    decision_index,
    geometry,
    parse_operation,
)

from hunter_core.domain.enums import Timeframe  # noqa: E402
from hunter_core.strategies.tl_scan import TlScan, tl_scan  # noqa: E402

FIXTURE = r"""{"signal_id":"a61fe738-74d1-5951-a84d-fcc579eae573","symbol":"XRPUSDT","exchange":"binance","strategy":"session_orb","version":"v1","code_ref":"hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba","cohort":"replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19","coorte":"replay","direction":"long","observation_ts":"2026-08-23T14:30:00+00:00","decision_at":"2026-08-23T14:30:02+00:00","decision_bar_open":"2026-08-23T14:15:00+00:00","decision_bar_close":"2026-08-23T14:30:00+00:00","reason":"Session ORB 15m: sessão us (abertura 13:00Z), fechamento 1.5262 acima da máxima 1.5248 da faixa das 4 primeiras barras, 6 barras após a abertura; stop na mínima da faixa (1.493), risco 2.06 ATR, volume relativo 2.22x da mediana de 96 barras, ATR% 1.06%","signal_targets":["1.5926000000","1.6590000000"],"invalidations":[],"supporting_features":{"atr":{"seed":"0.01954285714285714285714285714","value":"0.01611369944957333824155372601","method":"wilder_v1","origin":"rolling_window_v1","period":"14","percent":"0.01055805231920674763566618137","bars_used":"97","timeframe":"15m","window_end":"2026-08-23T14:30:00Z","seed_anchor":"2026-08-22T17:45:00Z","window_start":"2026-08-22T14:15:00Z"},"cohort":"replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19","purpose":"research_only","eligible":true,"features":[{"name":"session","value":"us","window":null,"available":true,"source_ts":null,"unavailable_reason":null},{"name":"session_model","value":"declared_utc_sessions_v1","window":null,"available":true,"source_ts":null,"unavailable_reason":null},{"name":"session_open","value":null,"window":null,"available":true,"source_ts":"2026-08-23T13:00:00Z","unavailable_reason":null},{"name":"bars_since_open","value":"6","window":null,"available":true,"source_ts":null,"unavailable_reason":null},{"name":"range_high","value":"1.5248","window":"4","available":true,"source_ts":null,"unavailable_reason":null},{"name":"range_low","value":"1.493","window":"4","available":true,"source_ts":null,"unavailable_reason":null},{"name":"range_risk_atr","value":"2.060358647242801605280195297","window":null,"available":true,"source_ts":null,"unavailable_reason":null},{"name":"open_15m","value":"1.5496","window":null,"available":true,"source_ts":"2026-08-23T14:15:00Z","unavailable_reason":null},{"name":"high_15m","value":"1.5501","window":null,"available":true,"source_ts":null,"unavailable_reason":null},{"name":"low_15m","value":"1.5254","window":null,"available":true,"source_ts":null,"unavailable_reason":null},{"name":"volume_15m","value":"27964938.3","window":null,"available":true,"source_ts":null,"unavailable_reason":null},{"name":"close_15m","value":"1.5262","window":null,"available":true,"source_ts":"2026-08-23T14:30:00Z","unavailable_reason":null},{"name":"relative_volume_15m","value":"2.218261518713234777497745275","window":"96","available":true,"source_ts":null,"unavailable_reason":null},{"name":"volume_median_15m","value":"12606691.35","window":"96","available":true,"source_ts":null,"unavailable_reason":null},{"name":"atr_pct_15m","value":"0.01055805231920674763566618137","window":"97","available":true,"source_ts":null,"unavailable_reason":null}],"timeframe":"15m","provenance":{"code_ref":"hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba","producer":"strategy-worker.shadow","regime_id":null,"funding_ts":"2026-08-23T08:00:00Z","params_hash":"cdb9516b293276095f4a8c2210d60ade0a4448cac46cce827f58bc3f8908d5e0","regime_reason":"no_regime_asof","funding_reason":null,"funding_source":"durable","bars_in_context":"1560","newest_bar_open":"2026-08-23T14:29:00Z","open_interest_ts":null,"available_through":"2026-09-08T05:10:57.875284Z","strategy_version_id":"01a08284-6f7b-701d-abf0-bd07ad58d52a","open_interest_reason":"no_data","open_interest_source":null,"eligibility_observed_at":"2026-09-08T19:47:10.571544Z"},"decision_at":"2026-08-23T14:30:02Z","strategy_key":"session_orb_v1","assumed_costs":{"fee_bps":"4","spread_bps":"2","slippage_bps":"5","max_entry_delay_s":"120"},"params_format":"1","observation_ts":"2026-08-23T14:30:00Z","strategy_version":"v1","confidence_method":"constant_uncalibrated_v1","eligibility_reason":null},"virtual_entry":1.52961722,"virtual_stop":1.493,"virtual_targets":["1.5926000000","1.6590000000"],"entry_ts":"2026-08-23T14:31:00+00:00","exit_price":1.4921042,"exit_ts":"2026-08-23T14:43:00+00:00","mfe":0.01298278,"mae":null,"r_multiple":-1.0574726472,"result":"stop","tracking_state":"terminal","no_entry_reason":null,"censored_reason":null,"outcome_meta":{"cohort":"replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19","funding":{"notes":[],"reason":null,"per_unit":"0","charged_at":[],"interval_s":"28800","settlements":"0"},"purpose":"research_only","progress":{"entry":"1.52961722000000","result":"stop","exit_ts":"2026-08-23T14:43:00+00:00","entry_ts":"2026-08-23T14:31:00+00:00","exit_base":"1.4930000000","complete_low":"1.5264000000","exit_at_open":false,"exit_bar_low":"1.4567000000","complete_high":"1.5426000000","exit_bar_high":"1.5332000000","exit_bar_open":"2026-08-23T14:42:00+00:00","exit_observed":"1.4930000000","last_bar_open":"2026-08-23T14:42:00+00:00","first_bar_open":"2026-08-23T14:31:00+00:00","tracking_state":"terminal","censored_reason":null,"complete_low_ts":"2026-08-23T14:32:00+00:00","no_entry_reason":null,"bars_in_position":"12","complete_high_ts":"2026-08-23T14:39:00+00:00","window_last_open":"2026-08-23T14:42:00+00:00","pending_invalidation":false},"horizon_s":"14400","entry_plan":{"delay_s":"60","decision_at":"2026-08-23T14:30:02+00:00","late_reason":null,"confirmed_at":"2026-08-23T14:30:02+00:00","entry_bar_open":"2026-08-23T14:31:00+00:00","source_bar_close":"2026-08-23T14:30:00+00:00","max_entry_delay_s":"120"},"excursions":{"mae":null,"mfe":"0.01298278","unit":"price","bounds":{"mae":["0.03661722","0.07291722"],"mfe":["0.01298278","0.01298278"]},"mae_ts":null,"method":"ohlc_complete_bars_v1","mfe_ts":null,"mae_bar":"2026-08-23T14:32:00Z","mfe_bar":"2026-08-23T14:39:00Z","coverage":{"bars_known":"12","bars_total":"12"},"ambiguous":true,"available":true,"bar_windows":{"last_open":"2026-08-23T14:42:00Z","first_open":"2026-08-23T14:31:00Z","exit_bar_open":"2026-08-23T14:42:00Z"},"initial_risk":"0.03661722","reference_price":"1.5262","mae_complete_bars":"0.00321722","mfe_complete_bars":"0.01298278"},"invalidation":null,"r_ex_funding":"-1.057472647240833684261120861","r_net_reason":null,"assumed_costs":{"fee_bps":"4","spread_bps":"2","slippage_bps":"5","max_entry_delay_s":"120"},"reference_price":"1.5262"},"bars":[["2026-08-22T14:30:00Z",1.4829,1.4846,1.4506,1.4566,35037733.3,15],["2026-08-22T14:45:00Z",1.4567,1.4601,1.4354,1.452,38665353.5,15],["2026-08-22T15:00:00Z",1.452,1.4543,1.4351,1.4371,26770642.6,15],["2026-08-22T15:15:00Z",1.4371,1.4561,1.4354,1.4519,22300226.7,15],["2026-08-22T15:30:00Z",1.4518,1.453,1.4286,1.4405,27382203.3,15],["2026-08-22T15:45:00Z",1.4405,1.4445,1.4322,1.4399,11607082.3,15],["2026-08-22T16:00:00Z",1.4398,1.4521,1.4343,1.4469,17537422.6,15],["2026-08-22T16:15:00Z",1.4469,1.4741,1.446,1.4699,25410043.8,15],["2026-08-22T16:30:00Z",1.4699,1.4867,1.4622,1.4838,22693405.5,15],["2026-08-22T16:45:00Z",1.4839,1.4897,1.4767,1.4805,18961355.9,15],["2026-08-22T17:00:00Z",1.4806,1.4833,1.467,1.4722,15119291.4,15],["2026-08-22T17:15:00Z",1.4722,1.4799,1.4645,1.4681,10712063.5,15],["2026-08-22T17:30:00Z",1.4681,1.4787,1.4681,1.476,6589984.2,15],["2026-08-22T17:45:00Z",1.4759,1.486,1.4734,1.4801,8568482.3,15],["2026-08-22T18:00:00Z",1.4802,1.4872,1.4773,1.4814,8367345.7,15],["2026-08-22T18:15:00Z",1.4814,1.4983,1.4814,1.4908,15412897.2,15],["2026-08-22T18:30:00Z",1.4908,1.4953,1.4838,1.4848,7969982.9,15],["2026-08-22T18:45:00Z",1.4848,1.4904,1.4775,1.4888,11401316.6,15],["2026-08-22T19:00:00Z",1.4888,1.4947,1.4827,1.4928,9566148.1,15],["2026-08-22T19:15:00Z",1.4928,1.4973,1.4846,1.4893,6917787.7,15],["2026-08-22T19:30:00Z",1.4894,1.4999,1.4893,1.4996,6589867.5,15],["2026-08-22T19:45:00Z",1.4996,1.5057,1.4974,1.5004,11416015.7,15],["2026-08-22T20:00:00Z",1.5005,1.5157,1.4936,1.5099,17275723.0,15],["2026-08-22T20:15:00Z",1.5098,1.5126,1.5021,1.5028,10731882.0,15],["2026-08-22T20:30:00Z",1.5028,1.5119,1.4967,1.5101,9218501.0,15],["2026-08-22T20:45:00Z",1.5101,1.5105,1.4976,1.5011,7638778.7,15],["2026-08-22T21:00:00Z",1.5012,1.5012,1.4788,1.4803,19334293.5,15],["2026-08-22T21:15:00Z",1.4804,1.4896,1.4803,1.4837,7647526.7,15],["2026-08-22T21:30:00Z",1.4838,1.4851,1.4516,1.4663,26662377.0,15],["2026-08-22T21:45:00Z",1.4662,1.4688,1.4523,1.4545,10468385.6,15],["2026-08-22T22:00:00Z",1.4545,1.4723,1.4457,1.4706,20786338.2,15],["2026-08-22T22:15:00Z",1.4705,1.4744,1.4635,1.4709,10471488.8,15],["2026-08-22T22:30:00Z",1.4709,1.4756,1.4619,1.4676,10529864.3,15],["2026-08-22T22:45:00Z",1.4676,1.4741,1.4656,1.468,6010082.3,15],["2026-08-22T23:00:00Z",1.468,1.4702,1.459,1.4613,6641077.8,15],["2026-08-22T23:15:00Z",1.4612,1.4655,1.4595,1.4606,4835929.1,15],["2026-08-22T23:30:00Z",1.4606,1.4643,1.4503,1.4609,10936583.9,15],["2026-08-22T23:45:00Z",1.4609,1.4677,1.4592,1.4617,5286698.1,15],["2026-08-23T00:00:00Z",1.4618,1.4762,1.4615,1.4745,12640224.2,15],["2026-08-23T00:15:00Z",1.4746,1.4996,1.4728,1.4918,21240901.6,15],["2026-08-23T00:30:00Z",1.4918,1.4989,1.4807,1.4814,18208844.0,15],["2026-08-23T00:45:00Z",1.4815,1.519,1.476,1.513,26168918.6,15],["2026-08-23T01:00:00Z",1.5129,1.5136,1.4892,1.5021,25238172.4,15],["2026-08-23T01:15:00Z",1.5021,1.5025,1.4924,1.4954,10605425.6,15],["2026-08-23T01:30:00Z",1.4954,1.5035,1.4847,1.4959,14342193.8,15],["2026-08-23T01:45:00Z",1.4959,1.5009,1.486,1.4907,7394557.5,15],["2026-08-23T02:00:00Z",1.4906,1.4942,1.478,1.4787,12942363.0,15],["2026-08-23T02:15:00Z",1.4787,1.4891,1.4709,1.4789,16738516.9,15],["2026-08-23T02:30:00Z",1.4789,1.4928,1.4769,1.4849,8239275.0,15],["2026-08-23T02:45:00Z",1.4848,1.4936,1.4803,1.484,9695446.4,15],["2026-08-23T03:00:00Z",1.484,1.487,1.4733,1.4808,8196568.7,15],["2026-08-23T03:15:00Z",1.4807,1.4935,1.4724,1.4746,11064537.6,15],["2026-08-23T03:30:00Z",1.4745,1.4751,1.4612,1.4645,17727834.6,15],["2026-08-23T03:45:00Z",1.4646,1.4795,1.4646,1.4742,10121501.8,15],["2026-08-23T04:00:00Z",1.4742,1.4882,1.466,1.4865,18905061.4,15],["2026-08-23T04:15:00Z",1.4864,1.4895,1.4623,1.4759,21070185.1,15],["2026-08-23T04:30:00Z",1.4759,1.4772,1.4586,1.4626,15744346.6,15],["2026-08-23T04:45:00Z",1.4626,1.4648,1.4451,1.454,31157543.1,15],["2026-08-23T05:00:00Z",1.4541,1.471,1.4505,1.4546,30596199.6,15],["2026-08-23T05:15:00Z",1.4546,1.4784,1.4386,1.469,38424513.1,15],["2026-08-23T05:30:00Z",1.469,1.4756,1.4527,1.4572,23211648.1,15],["2026-08-23T05:45:00Z",1.4573,1.4596,1.4441,1.4464,15856847.8,15],["2026-08-23T06:00:00Z",1.4465,1.4503,1.4337,1.448,23219717.8,15],["2026-08-23T06:15:00Z",1.448,1.4625,1.4469,1.4518,16450508.3,15],["2026-08-23T06:30:00Z",1.4517,1.4618,1.4515,1.4551,9440059.5,15],["2026-08-23T06:45:00Z",1.4551,1.4571,1.4381,1.4444,14072285.3,15],["2026-08-23T07:00:00Z",1.4444,1.4639,1.4394,1.4631,12573158.5,15],["2026-08-23T07:15:00Z",1.4631,1.4737,1.4541,1.4551,18472477.5,15],["2026-08-23T07:30:00Z",1.455,1.4571,1.447,1.4541,10990007.2,15],["2026-08-23T07:45:00Z",1.4541,1.4661,1.4529,1.4616,12380860.3,15],["2026-08-23T08:00:00Z",1.4616,1.4754,1.4576,1.4721,19730843.9,15],["2026-08-23T08:15:00Z",1.472,1.482,1.4704,1.4786,14023599.5,15],["2026-08-23T08:30:00Z",1.4787,1.4853,1.4753,1.4813,12858941.0,15],["2026-08-23T08:45:00Z",1.4813,1.4826,1.4712,1.4753,11222076.9,15],["2026-08-23T09:00:00Z",1.4754,1.4867,1.4725,1.4795,8363204.4,15],["2026-08-23T09:15:00Z",1.4796,1.4813,1.4745,1.4772,7571618.2,15],["2026-08-23T09:30:00Z",1.4772,1.4776,1.4674,1.4747,8682359.3,15],["2026-08-23T09:45:00Z",1.4746,1.4791,1.4683,1.4775,7649462.6,15],["2026-08-23T10:00:00Z",1.4774,1.4893,1.4769,1.4822,11739660.5,15],["2026-08-23T10:15:00Z",1.4822,1.5056,1.4822,1.491,19531980.6,15],["2026-08-23T10:30:00Z",1.4911,1.4935,1.484,1.4853,10962722.4,15],["2026-08-23T10:45:00Z",1.4852,1.4857,1.4752,1.4756,9313523.8,15],["2026-08-23T11:00:00Z",1.4757,1.4843,1.4756,1.48,8910943.1,15],["2026-08-23T11:15:00Z",1.48,1.5019,1.479,1.4927,21903456.4,15],["2026-08-23T11:30:00Z",1.4928,1.5037,1.491,1.4986,13964240.4,15],["2026-08-23T11:45:00Z",1.4987,1.501,1.4932,1.4943,10370368.9,15],["2026-08-23T12:00:00Z",1.4943,1.4966,1.4827,1.4906,14533171.8,15],["2026-08-23T12:15:00Z",1.4905,1.4949,1.4857,1.4889,9108673.7,15],["2026-08-23T12:30:00Z",1.489,1.4991,1.489,1.4985,6315044.9,15],["2026-08-23T12:45:00Z",1.4985,1.4985,1.49,1.4942,5032090.7,15],["2026-08-23T13:00:00Z",1.4942,1.5029,1.493,1.5014,10727277.9,15],["2026-08-23T13:15:00Z",1.5014,1.5248,1.4974,1.5048,44702673.0,15],["2026-08-23T13:30:00Z",1.5048,1.5174,1.5021,1.515,16080056.7,15],["2026-08-23T13:45:00Z",1.5151,1.5245,1.5101,1.5198,17868027.0,15],["2026-08-23T14:00:00Z",1.5198,1.5504,1.5178,1.5496,34041089.1,15],["2026-08-23T14:15:00Z",1.5496,1.5501,1.5254,1.5262,27964938.3,15],["2026-08-23T14:30:00Z",1.5263,1.5426,1.4548,1.4975,80075257.5,15],["2026-08-23T14:45:00Z",1.4975,1.5219,1.4967,1.5152,42089978.5,15],["2026-08-23T15:00:00Z",1.5153,1.5172,1.4964,1.4987,29722289.0,15],["2026-08-23T15:15:00Z",1.4987,1.5067,1.4864,1.5038,29179273.3,15],["2026-08-23T15:30:00Z",1.5037,1.5117,1.4964,1.5082,13794911.6,15]]}"""

MAX_PNG_BYTES = 120 * 1024
"""Teto do brief T3.50 por imagem."""


@pytest.fixture
def op() -> Operation:
    return parse_operation(json.loads(FIXTURE, parse_float=Decimal))


def _fingerprint(scan: TlScan) -> tuple[Any, ...]:
    """Tudo o que o desenho lê da varredura, num valor comparável."""
    return (
        scan.as_of,
        tuple((line.line_id, line.touches, line.violations, line.first_idx) for line in scan.lines),
        tuple(str(line.projected(scan.as_of)) for line in scan.lines),
        tuple((event.kind.value, event.index, event.line_id) for event in scan.events),
        tuple((pivot.kind.value, pivot.index) for pivot in scan.pivots),
    )


def _tamper_after_the_decision(op: Operation) -> Operation:
    """As velas **depois** da barra da decisão, violentamente alteradas."""
    cut = decision_index(op)
    bars = list(op.bars)
    for index in range(cut + 1, len(bars)):
        bar = bars[index]
        bars[index] = replace(
            bar,
            high=bar.high * Decimal("1.30"),
            low=bar.low * Decimal("0.70"),
            close=bar.high * Decimal("1.29"),
        )
    return replace(op, bars=tuple(bars))


def test_the_fixture_is_the_operation_it_claims_to_be(op: Operation) -> None:
    assert op.symbol == "XRPUSDT"
    assert op.label == "session_orb v1"
    assert op.result == "stop"
    assert len(op.bars) == 101
    # 96 barras de padrão terminando na decisão -> o corte é o índice 95, e as
    # cinco barras seguintes são o que aconteceu depois.
    assert decision_index(op) == 95
    assert op.decision_bar_close == datetime(2026, 8, 23, 14, 30, tzinfo=UTC)
    assert op.filename() == "20260823-1430Z-XRPUSDT-stop.png"


def test_the_lines_drawn_are_the_ones_the_frozen_scanner_reports_at_the_cut(op: Operation) -> None:
    """A varredura do desenho é, byte a byte, ``tl_scan`` cortado na decisão."""
    scan, offset = geometry(op)
    assert scan is not None
    cut = decision_index(op)
    expected = tl_scan(op.bars[: cut + 1], timeframe=Timeframe.M15, params=PARAMS, as_of=cut)
    assert offset == 0
    assert _fingerprint(scan) == _fingerprint(expected)
    assert [line.line_id for line in scan.lines] == [
        "66253d3fa89aa7e3",
        "059f5798a6b54292",
        "8c949057dbb95d0a",
    ]


def test_a_candle_after_the_decision_cannot_move_a_line(op: Operation) -> None:
    """Não-antecipação, e a trapaça que prova que a afirmação tem dentes.

    Alterar em ±30 % as cinco velas posteriores à decisão **não pode** mudar
    nada do que é desenhado. A mesma alteração, lida por uma varredura que corta
    na última barra em vez de na barra da decisão — a trapaça deliberada —,
    muda a lista de eventos: é exatamente essa diferença que o corte impede de
    chegar ao gráfico.
    """
    honest_before, _ = geometry(op)
    honest_after, _ = geometry(_tamper_after_the_decision(op))
    assert honest_before is not None and honest_after is not None
    assert _fingerprint(honest_before) == _fingerprint(honest_after)

    cheat_before = tl_scan(op.bars, timeframe=Timeframe.M15, params=PARAMS, as_of=len(op.bars) - 1)
    tampered = _tamper_after_the_decision(op)
    cheat_after = tl_scan(
        tampered.bars, timeframe=Timeframe.M15, params=PARAMS, as_of=len(tampered.bars) - 1
    )
    assert _fingerprint(cheat_before) != _fingerprint(cheat_after)


def test_render_writes_one_png_under_the_budget_and_skips_it_next_time(
    op: Operation, tmp_path: Path
) -> None:
    pytest.importorskip("matplotlib", reason="rodar com `uv run --with matplotlib`")
    from render_operations_draw import render

    path, written = render(op, tmp_path)
    assert written is True
    assert path.name == "20260823-1430Z-XRPUSDT-stop.png"
    assert path.exists()
    assert path.stat().st_size <= MAX_PNG_BYTES
    stamp = path.stat().st_mtime_ns

    again, written_again = render(op, tmp_path)
    assert written_again is False
    assert again.stat().st_mtime_ns == stamp

    forced, written_forced = render(op, tmp_path, force=True)
    assert written_forced is True
    assert forced.exists()


def test_the_title_names_market_version_brasilia_time_and_result(op: Operation) -> None:
    pytest.importorskip("matplotlib", reason="rodar com `uv run --with matplotlib`")
    from render_operations_draw import chart_title

    scan, _ = geometry(op)
    title = chart_title(op, scan)
    assert "XRPUSDT" in title
    assert "session_orb v1" in title
    assert "23/08/2026 11:30 BRT" in title  # 14:30Z - 3 h
    assert "(14:30Z)" in title
    assert "-1.06 R" in title
    assert "saída por stop" in title
    assert "3 linha(s) no corte" in title


def test_the_note_row_carries_the_levels_the_lines_and_the_image(op: Operation) -> None:
    row = table_row(7, op, "session_orb-v1")
    assert row.startswith("| 007 | 23/08 11:30 | 14:30Z | XRPUSDT | replay |")
    assert "| stop | -1.06 | 3 |" in row
    assert "`—`" in row  # session_orb não lê linha: não há line_id no envelope
    assert "(../../attachments/operacoes/session_orb-v1/20260823-1430Z-XRPUSDT-stop.png)" in row


def test_the_note_says_plainly_that_this_version_does_not_read_lines(op: Operation) -> None:
    note = build_note([op], "session_orb-v1", datetime(2026, 9, 8, 23, 30, tzinfo=UTC))
    front = note.split("---")[1].splitlines()
    assert "strategy: session_orb" in front
    assert "version: v1" in front
    assert "n: 1" in front
    assert "expectancy: -1.0575" in front
    assert "owner: quant-engineer" in front
    assert "**não lê**" in note
    assert "contexto, nunca entrada da decisão" in note
    assert "![XRPUSDT session_orb v1 23/08 11:30 BRT]" in note
    assert "# session_orb v1 — operações traçadas" in note


def test_an_envelope_drawn_with_other_pattern_params_is_refused_not_redrawn(op: Operation) -> None:
    """Review of T3.50 (HIGH): the renderer must never redraw a decision with
    thresholds other than the ones the envelope recorded."""
    features = {**op.features, "pattern_params": '{"pivot_k": 99}'}
    with pytest.raises(ValueError, match="pattern_params"):
        geometry(replace(op, features=features))


def test_two_operations_mapping_to_one_file_name_fail_loud(op: Operation, tmp_path: Path) -> None:
    """Review of T3.50 (MEDIUM): a second operation behind the same PNG name
    must not vanish silently behind the first one's idempotent skip."""
    from render_operations import render

    twin = replace(op, signal_id="another-signal")
    jsonl = tmp_path / "ops.jsonl"
    payload = json.loads(FIXTURE, parse_float=Decimal)
    twin_payload = {**payload, "signal_id": "another-signal"}
    jsonl.write_text(
        json.dumps(payload, default=str) + "\n" + json.dumps(twin_payload, default=str) + "\n",
        encoding="utf-8",
    )
    assert twin.filename() == op.filename()
    args = type(
        "Args", (), {"jsonl": str(jsonl), "out": str(tmp_path / "png"), "max": 10, "force": False}
    )()
    with pytest.raises(SystemExit, match="colisão"):
        render(args)
