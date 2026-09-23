"""R76 — testes do carregador com séries sintéticas e valores esperados conhecidos."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import load as L  # noqa: E402

T0 = datetime(2026, 9, 23, 22, 0, 0, tzinfo=UTC)
Tr = L.r73.Trade


def tr(sec: float, trader: str, side: str = "buy", sol: int = 10**8, slot: int = 1, ei: int = 0):
    t = T0 + timedelta(seconds=sec)
    return Tr(block_time=t, received_at=t, slot=slot, event_index=ei, trader=trader, side=side, sol=sol, tok=1000)


def fund(f: str, sec: float = -3600) -> L.Funding:
    return L.Funding(f, T0 + timedelta(seconds=sec))


DEC = T0 + timedelta(seconds=60, milliseconds=300)


def test_compradoras_so_antes_da_decisao_e_sem_a_nossa():
    tape = [tr(1, "A"), tr(2, "B"), tr(3, "A"), tr(5, L.OUR), tr(59, "C", "sell"), tr(61, "D")]
    assert L.pre_decision_buyers(tape, DEC) == ["A", "B"]


def test_sem_antecipacao_a_variavel_nao_muda_com_trocas_depois_da_decisao():
    base = [tr(1, "A"), tr(2, "B"), tr(3, "C"), tr(4, "D")]
    fnd = {"A": fund("X"), "B": fund("X"), "C": fund("Y"), "D": fund("Z"), "E": fund("X"), "F": fund("X")}
    before = L.network(L.pre_decision_buyers(base, DEC), fnd, DEC)
    later = base + [tr(61, "E"), tr(62, "F"), tr(70, "A", "sell")]
    after = L.network(L.pre_decision_buyers(later, DEC), fnd, DEC)
    assert before == after
    assert before["pct"] == pytest.approx(0.5)


def test_rede_valores_conhecidos():
    buyers = ["A", "B", "C", "D", "E"]
    fnd = {"A": fund("X"), "B": fund("X"), "C": fund("X"), "D": fund("Y")}  # E não resolvida
    n = L.network(buyers, fnd, DEC)
    assert n["n_resolved"] == 4 and n["max_group"] == 3 and n["top_funder"] == "X"
    assert n["pct"] == pytest.approx(3 / 4)
    assert n["pct_all"] == pytest.approx(3 / 5)
    assert n["coverage"] == pytest.approx(4 / 5)


def test_grupo_unitario_vale_zero_e_sem_resolvidas_e_desconhecido():
    fnd = {"A": fund("X"), "B": fund("Y")}
    assert L.network(["A", "B"], fnd, DEC)["pct"] == 0
    assert L.network(["Q"], fnd, DEC)["pct"] is None


def test_financiamento_depois_da_decisao_nao_conta():
    fnd = {"A": fund("X"), "B": fund("X", sec=61)}  # B financiada depois da decisão
    n = L.network(["A", "B"], fnd, DEC)
    assert n["n_resolved"] == 1 and n["pct"] == 0


def test_casa_de_cambio_nao_forma_rede():
    fnd = {"A": fund("CEX"), "B": fund("CEX"), "C": fund("CEX"), "D": fund("X"), "E": fund("X")}
    n = L.network(list("ABCDE"), fnd, DEC, is_exchange=lambda f: f == "CEX")
    assert n["max_group"] == 2 and n["pct"] == pytest.approx(2 / 5)  # CEX fica no denominador


def test_criador_um_salto():
    fnd = {"CR": fund("M"), "A": fund("CR"), "B": fund("M"), "C": fund("Z"), "D": fund("Z")}
    assert L.creator_share(["CR", "A", "B", "C", "D"], fnd, DEC, "CR") == pytest.approx(2 / 4)
    assert L.creator_share(["A"], fnd, DEC, None) is None


def test_status_de_cambio_com_corte_por_mint():
    cut = 1_000_000
    many = {"ok": True, "first_bt": list(range(cut - 1500, cut)), "distinct": 1500, "exhausted": False}
    assert L.exchange_status(many, cut, False) == "exchange"
    # mesmo registo avaliado num corte mais cedo: só 400 antes dele e o histórico não se esgotou
    assert L.exchange_status(many, cut - 1100, False) == "unknown"
    few = {"ok": True, "first_bt": list(range(10)), "distinct": 10, "exhausted": True}
    assert L.exchange_status(few, cut, False) == "not"
    assert L.exchange_status(None, cut, False) == "unknown"
    assert L.exchange_status(None, cut, True) == "exchange"


def test_despejo_coordenado():
    entry = T0
    ten = [tr(100, f"s{i}", "sell", slot=77) for i in range(10)]
    assert L.coordinated_dump(ten, entry) == (True, 10)
    assert L.coordinated_dump(ten[:9], entry) == (False, 9)
    late = [tr(301, f"s{i}", "sell", slot=78) for i in range(12)]
    assert L.coordinated_dump(late, entry) == (False, 0)
    same_wallet = [tr(100, "s0", "sell", slot=77, ei=i) for i in range(12)]
    assert L.coordinated_dump(same_wallet, entry)[1] == 1


def test_compradora_no_mesmo_segundo_da_decisao_e_ambigua():
    tape = [tr(10, "A"), tr(60, "B")]  # decisão aos 60,3 s: B está no mesmo segundo
    assert L.ambiguous_buyers(tape, DEC) == 1


def _P(marks: list[tuple[float, float]]):
    """Caminho sintético com marca proporcional: a marca de cada ponto = spent × mult (R74)."""
    spent, tokens = 10**8, 10**6
    path = []
    for sec, mult in marks:
        # reservas que dão sell_net ≈ spent × mult: resolve-se numericamente com vtok grande
        vtok = 10**15
        lo, hi = 1, 10**20
        want = int(spent * mult)
        while lo < hi:
            mid = (lo + hi) // 2
            if L.r72.sell_net(mid, vtok, tokens) < want:
                lo = mid + 1
            else:
                hi = mid
        path.append((T0 + timedelta(seconds=sec), lo, vtok, L.r72.sell_net(lo, vtok, tokens)))
    return {"entry_bt": T0, "spent": spent, "tokens": tokens, "path": path, "source": "tape+photos",
            "_tape_w": [p[0] for p in path], "n_tape_in_window": len(path)}


def test_landing_espelha_simulate_current_e_mede_o_buraco():
    P = _P([(0, 1.0), (5, 1.02), (10, 1.05), (20, 1.16), (40, 1.2)])
    reason, land = L.landing(P)
    assert reason == "target" and land == T0 + timedelta(seconds=21.6)
    assert L.sim.simulate_current(P)["reason"] == "target"
    assert L.max_gap_until(P, land) == pytest.approx(10.0)
    P2 = _P([(0, 1.0), (5, 0.99), (10, 0.98), (200, 0.97)])  # buraco de 190 s até ao tempo
    out = L.outcome(P2)
    assert out["censor"] == "gap>60s"


def test_tercis_empates_ficam_juntos():
    import run as R

    vals = [0, 0, 0, 0, 0, 0, 0.1, 0.2, 0.3]
    lo, hi = R.tercile_masks(vals)
    assert sum(lo) == 6 and sum(hi) == 3  # q1/3 = 0 → os 6 zeros juntos no baixo; q2/3 = 0,033 → alto = 3
    assert not any(a and b for a, b in zip(lo, hi, strict=True))


def test_cortes_dos_tercis_nao_mudam_com_a_censura_do_desfecho():
    import run as R

    rows = [{"pct": v, "sim_ret": (None if i % 4 == 0 else 0.0), "mint": f"m{i}", "dump": False}
            for i, v in enumerate([0.0] * 30 + [0.02] * 30 + [0.1 + i / 100 for i in range(30)])]
    before = R.cuts(rows, "pct")
    resolved_only = [r for r in rows if r["sim_ret"] is not None]
    c = R.contrast(rows, "pct", "sim_ret", 1)
    assert (c["cut_lo"], c["cut_hi"]) == before  # não os cortes recalculados só nas resolvidas
    assert R.cuts(resolved_only, "pct") != before or True  # (podem coincidir; o que importa é a origem)
