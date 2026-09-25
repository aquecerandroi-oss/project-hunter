# R78 — testes sintéticos da H-015: variável no slot real, tercis por posto com empates, despejo coordenado.
# uv run --project C:/dev/project-hunter pytest .claude/state/r78/test_h015.py -q -p no:cacheprovider
from datetime import UTC, datetime, timedelta

from h015 import coordinated_dump, sol_in_create_slot, tertiles

ES = [{"slot": 100, "sol_others": "4.93", "wallets_others": 3, "creator_sol": "1"},
      {"slot": 102, "sol_others": "0.5", "wallets_others": 1, "creator_sol": "0"}]


def test_value_is_read_at_the_real_slot_not_the_inferred_one():
    assert sol_in_create_slot({"early_slots": ES}, 100) == (4.93, "match")
    assert sol_in_create_slot({"early_slots": ES}, 102) == (0.5, "match")


def test_absent_slot_inside_or_before_the_listed_range_is_zero():
    assert sol_in_create_slot({"early_slots": ES}, 101) == (0.0, "absent_zero")
    assert sol_in_create_slot({"early_slots": ES}, 99) == (0.0, "absent_zero")


def test_slot_after_the_listed_range_is_unresolved():
    assert sol_in_create_slot({"early_slots": ES}, 103) == (None, "after_listed")
    assert sol_in_create_slot({"early_slots": []}, 100) == (None, "no_early_slots")
    assert sol_in_create_slot({"early_slots": ES}, None) == (None, "no_slot")


def test_tertiles_keep_ties_together_and_publish_effective_sizes():
    vals = [0, 0, 0, 0, 0, 1, 2, 3, 4]  # q1/3 = 0 → baixo = os cinco zeros
    low, high, (c1, c2) = tertiles(vals)
    assert c1 == 0 and low == [0, 1, 2, 3, 4]
    assert all(vals[i] > c2 for i in high) and len(high) == 3


def test_coordinated_dump_needs_ten_distinct_sellers_in_one_slot_inside_300s():
    t0 = datetime(2026, 9, 24, tzinfo=UTC)
    sells = [(t0 + timedelta(seconds=10), 5, f"w{i}") for i in range(10)]
    assert coordinated_dump(sells, t0, our="x") == (True, 10)
    sells = [(t0 + timedelta(seconds=10), 5, f"w{i % 9}") for i in range(10)] + [(t0 + timedelta(seconds=301), 6, "z")]
    assert coordinated_dump(sells, t0, our="x") == (False, 9)
    sells = [(t0 + timedelta(seconds=10), 5, f"w{i}") for i in range(9)] + [(t0 + timedelta(seconds=10), 5, "x")]
    assert coordinated_dump(sells, t0, our="x") == (False, 9)


def test_chain_sol_counts_only_non_creator_payers_that_spend_beyond_fee_and_rent():
    from h015_run import chain_sol
    c = {"others_in_slot": 3, "txs": [
        {"ok": True, "payer": "bundler", "payer_delta": -214_258_436, "fee": 9_596},  # compra 0,214 SOL
        {"ok": True, "payer": "x", "payer_delta": -730_320, "fee": 25_000},           # só aluguel/taxa: não é compra
        {"ok": True, "payer": "dev", "payer_delta": -900_000_000, "fee": 5_000}]}     # o criador não conta
    sol, n = chain_sol(c, "dev")
    assert n == 1 and abs(sol - 0.214248840) < 1e-9
    assert chain_sol({"others_in_slot": 2, "txs": [c["txs"][0]]}, "dev") == (None, 0)  # lista truncada: ilegível


def _tx(*owners, ok=True):
    return {"ok": ok, "err": False, "owners": [{"owner": o, "tok": t, "lam": lam} for o, t, lam in owners]}


def test_token_classifier_counts_other_wallets_buys_including_inside_the_create():
    from h015_tok import others_sol_in_slot
    create = _tx(("curve", 900, 3_000_000_000), ("dev", 60, -2_000_000_000), ("sniper", 40, -1_100_000_000))
    buy = _tx(("buyer", 10, -214_000_000), ("curve", -10, 210_000_000))
    rent_only = _tx(("x", 0, -2_232_600))
    sol, n = others_sol_in_slot([create, buy, rent_only], creator="dev")
    # no create: 3,0 SOL no curve × 40/(60+40) = 1,2; na compra: 0,21
    assert n == 2 and abs(sol - 1.41) < 1e-9


def test_token_classifier_zero_is_proven_only_without_other_buyers_and_unreadable_is_none():
    from h015_tok import others_sol_in_slot
    create = _tx(("curve", 900, 3_000_000_000), ("dev", 60, -2_000_000_000))
    assert others_sol_in_slot([create, _tx(("x", 0, -2_232_600))], creator="dev") == (0.0, 0)
    tiny = _tx(("buyer", 1, -1_000_000), ("curve", -1, 1_000_000))  # compra de 0,001 SOL com ATA existente conta
    assert others_sol_in_slot([create, tiny], creator="dev")[1] == 1
    assert others_sol_in_slot([create, _tx(ok=False)], creator="dev") == (None, 0)


def test_curve_is_the_lamport_receiver_even_when_the_creator_buys_most_of_the_supply():
    from h015_tok import others_sol_in_slot
    # 8NfoxP (real): o criador comprou 50,005 % da oferta no create; a curva é quem recebe os 26 SOL
    create = _tx(("dev", 500_047, -26_518_968_359), ("curve", 499_952, 26_184_001_288))
    assert others_sol_in_slot([create], creator="dev") == (0.0, 0)
