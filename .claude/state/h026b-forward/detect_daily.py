"""H-026 B coorte prospectiva (H-028) — detector diário, idempotente e só-de-acréscimo (pesquisa; nada de ordem, nada
de banco, nenhum retorno calculado).

    uv run --no-sync python .claude/state/h026b-forward/detect_daily.py --freeze      # uma vez: grava frozen.json
    uv run --no-sync python .claude/state/h026b-forward/detect_daily.py               # até o último dia UTC fechado
    uv run --no-sync python .claude/state/h026b-forward/detect_daily.py --through 2026-09-30
    ... --accept-gap SÍMBOLO:AAAA-MM-DD   # ausência de vela aceita à mão (gravada no log)

Para cada dia de sinal D ainda fora do log (de 2026-09-28 a 2030-09-27, sem buracos), com D já fechado
(D + 1 00:10Z ≤ agora): monta o painel só com velas de abertura ≤ D, o universo ponto-no-tempo do R84/R85 na abertura
de D + 1 e, para cada uma das 20 moedas, as bandeiras de D — B e A da H-026 (geometria congelada `r85/geom85.py`,
tolerância 0,25 ATR), o controle da LTA do R85, o rompimento simples (`brk.py`) e se houve toque A nas últimas 21
velas reais (`a20`, a janela que arma um B). Acrescenta UMA linha por dia em `log.jsonl` com o carimbo `as_of`.

Fonte: velas diárias à vista da Binance. Até 2026-09-27, o artefato congelado e auditado do R84
(`r84/cache/candles_1d.csv`, com deslistados); de 2026-09-28 em diante, `GET /api/v3/klines` público (sem chave),
guardado por primeira observação em `klines_fwd.csv` (`archive.py`). A nossa base não serve: `candles_1d` tem 0 linhas
e `candles_1m` só cobre perpétuos desde ~30/08 (consulta só-leitura de 01/10/2026, `q_cov.sql`).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "r85"))
sys.path.insert(0, str(HERE.parent / "r84"))

from archive import append_archive, exchange_usdt, fetch_all, read_archive  # noqa: E402
from brk import plain_breakout  # noqa: E402
from config import CACHE, EXCLUDED, LINKS, trading_symbols  # noqa: E402  (r84)
from data85 import Row, apply_links_hl, build_hl_panel, load_rows_hl, universe  # noqa: E402
from engine import listed  # noqa: E402
from geom85 import lta_scan, wilder_atr  # noqa: E402
from guards import (  # noqa: E402
    FORWARD_END,
    FORWARD_START,
    CoverageError,
    FrozenMismatchError,
    append_record,
    assert_closed,
    check_frozen,
    coverage_gaps,
    day_of,
    iso,
    load_classified,
    read_log,
    run_lock,
    sha,
)

TOL = 0.25
B_WINDOW = 20  # um B só nasce até 20 velas depois de um toque ≥ 3 (geom85, b_window)
CLOSE_MARGIN_S = 600  # a vela de D só é lida a partir de D + 1 00:10Z
LOG, KLINES, REVISIONS = HERE / "log.jsonl", HERE / "klines_fwd.csv", HERE / "revisions.csv"
CLASSIFIED = HERE / "classified_bases.jsonl"  # {"base", "excluded", "reason"} por linha, só acréscimo
PREREG, FROZEN = HERE / "PREREG.md", HERE / "frozen.json"
TRADED_AS = {old: new for old, new, _ in LINKS}  # todas as continuidades do R84 são anteriores a 2026-09-28
CODE = [HERE / f for f in ("brk.py", "archive.py", "guards.py", "detect_daily.py")]
CODE += [HERE.parent / "r85" / f for f in ("geom85.py", "data85.py")]
CODE += [HERE.parent / "r84" / f for f in ("panel.py", "engine.py", "config.py", "gaps.py")]


class UnclassifiedBaseError(RuntimeError):
    """Base nova (fora do artefato do R84), já elegível por idade, sem classificação de desenho (paridade/alavancado)."""


def a20_of(a_events: np.ndarray) -> bool:
    """Toque A em alguma das últimas B_WINDOW + 1 velas reais, inclusive a de hoje (ainda pode armar um B)."""
    return bool(a_events[-(B_WINDOW + 1):].any())


def groups_of(members: list[dict]) -> dict[str, list[str]]:
    def pick(test: Callable[[dict], bool]) -> list[str]:
        return [m["symbol"] for m in members if test(m["flags"])]

    return {
        "event_B": pick(lambda f: f["B"]),  # contraste R (réplica do R85)
        "ctrl_lta": pick(lambda f: f["ctrl_lta"]),
        "event_B_brk": pick(lambda f: f["B"] and f["brk"]),  # contraste P (gatilho comum, Astra #1)
        "cmp_brk_sem_teste": pick(lambda f: f["brk"] and not f["a20"]),  # sem toque ≥ 3 nas 21 velas ⇒ sem B
        "event_A": pick(lambda f: f["A"]),
    }


def detect_day(rows: list[Row], day: int, trading: set[str], known_bases: set[str],
               classified: dict[str, bool]) -> dict:
    """Bandeiras do dia de sinal `day` só com velas de abertura ≤ day. `classified` = base nova → fora por desenho."""
    cut = [r for r in rows if r[1] <= day]
    hp = build_hl_panel(cut, trading, excluded=EXCLUDED | {b for b, ex in classified.items() if ex}, today=day + 1)
    p = hp.p
    d = day - p.day0
    e = d + 1
    unknown = sorted({p.base[i] for i in np.flatnonzero(listed(p, e))} - known_bases - set(classified))
    if unknown:
        raise UnclassifiedBaseError(f"{iso(day)}: classificar em {CLASSIFIED.name} antes: {unknown}")
    members = []
    for rank, i in enumerate(universe(p, e), start=1):
        cols = np.flatnonzero(~np.isnan(p.close[i]))
        flags = {"B": False, "A": False, "brk": False, "ctrl_lta": False, "a20": False}
        close = None
        if cols.size and cols[-1] == d:  # sem vela em D a moeda não tem bandeira (como no R85)
            h, lo, c = hp.high[i, cols], hp.low[i, cols], p.close[i, cols]
            s = lta_scan(h, lo, c, wilder_atr(h, lo, c), tol=TOL)
            flags = {"B": bool(s.b_events[-1]), "A": bool(s.a_events[-1]), "brk": bool(plain_breakout(h, c)[-1]),
                     "ctrl_lta": bool(s.ctrl[-1]), "a20": a20_of(s.a_events)}
            close = float(c[-1])
        sym = p.ids[i].split("#")[0]
        vol = float(np.nansum(p.qvol[i, max(e - 30, 0) : e]))
        members.append({"rank": rank, "symbol": sym, "segment_start": iso(p.day0 + int(p.first[i])),
                        "traded_as": TRADED_AS.get(sym, sym), "vol30_usdt": round(vol, 2), "close": close, "flags": flags})
    return {"signal_day": iso(day), "universe": members, "groups": groups_of(members), "n_series": len(p.ids)}


def lookahead_divergences(detect: Callable[..., dict], rows: list[Row], days: list[int]) -> list[int]:
    """Dias em que o registro com TODAS as linhas difere do registro com só as velas de abertura ≤ dia."""
    return [d for d in days if detect(rows, d) != detect([r for r in rows if r[1] <= d], d)]


def static_shas() -> dict[str, str]:
    return {"code_sha256": sha(b"".join(f.read_bytes() for f in CODE)),
            "base_sha256": sha((CACHE / "candles_1d.csv").read_bytes())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--through", help="último dia de sinal (AAAA-MM-DD); padrão: o último dia UTC fechado")
    ap.add_argument("--freeze", action="store_true", help="grava frozen.json (texto + código + base), só se não existir")
    ap.add_argument("--accept-gap", action="append", default=[], help="SÍMBOLO:AAAA-MM-DD sem vela, aceito à mão")
    args = ap.parse_args(argv)
    shas = static_shas()
    if args.freeze:
        print(f"congelado: PREREG {check_frozen(PREREG, FROZEN, shas, freeze=True)} · {shas}")
        return 0
    if not FROZEN.exists():
        raise FrozenMismatchError("sem frozen.json: congelar (--freeze) antes do primeiro dia")
    prereg_sha = check_frozen(PREREG, FROZEN, shas)
    now = dt.datetime.now(dt.UTC)
    with run_lock(LOG):
        log = read_log(LOG)
        start = day_of(log[-1]["signal_day"]) + 1 if log else FORWARD_START
        last_closed = day_of((now - dt.timedelta(seconds=CLOSE_MARGIN_S)).date().isoformat()) - 1
        through = min(day_of(args.through) if args.through else last_closed, FORWARD_END)
        if start > through:
            print(f"nada a fazer: log até {iso(start - 1)}, pedido até {iso(through)} (coorte termina em {iso(FORWARD_END)})")
            return 0
        assert_closed(through, now, CLOSE_MARGIN_S)
        base_rows = load_rows_hl(CACHE / "candles_1d.csv", as_of_day=FORWARD_START)
        status_now = exchange_usdt()
        api_trading = {s for s, st in status_now.items() if st == "TRADING"}
        recent = {r[0] for r in base_rows if r[1] >= FORWARD_START - 45}
        asked = sorted(recent | set(status_now) | {r[0] for r in read_archive(KLINES)})
        fetched, missing = fetch_all(asked, FORWARD_START, through)
        n_new, n_rev = append_archive(KLINES, REVISIONS, fetched, now.isoformat(timespec="seconds"))
        fwd = read_archive(KLINES)  # primeira observação de cada (símbolo, dia)
        raw = base_rows + fwd
        rows, trading = apply_links_hl(raw, set(trading_symbols()) | api_trading)
        known = {r[0][:-4] for r in base_rows}
        prev = log[-1] if log else {}
        classified, cls_len, cls_sha = load_classified(CLASSIFIED, prev.get("classified_len", 0), prev.get("classified_sha256"))
        stamp = {"as_of": now.isoformat(timespec="seconds"), "prereg_sha256": prereg_sha, **shas,
                 "source": "r84/cache/candles_1d.csv (< 2026-09-28) + api.binance.com/api/v3/klines 1d, 1.ª observação (≥ 2026-09-28)",
                 "classified_len": cls_len, "classified_sha256": cls_sha, "api_missing": sorted(missing)}
        print(f"as_of {stamp['as_of']}; símbolos pedidos {len(asked)}; velas novas no arquivo {n_new}, revisões {n_rev}; "
              f"-1121: {len(missing)} ({sorted(set(missing) & recent) or 'nenhum com vela nos 45 d antes do início'})")
        accepted = set(args.accept_gap)
        for d in range(start, through + 1):
            gaps, excused = coverage_gaps(raw, d, status_now, accepted)
            if gaps:
                raise CoverageError(f"{iso(d)} sem vela para {gaps} (negociáveis agora): esperar ou --accept-gap")
            rec = detect_day(rows, d, trading, known, classified)
            fwd_d = sorted(r for r in fwd if r[1] <= d)
            lag = (now - dt.datetime(1970, 1, 1, tzinfo=dt.UTC)).total_seconds() / 3600 - (d + 1) * 24
            rec |= stamp | {"lag_h": round(lag, 2), "reconstructed": lag > 24, "n_fwd_rows": len(fwd_d),
                            "input_fwd_sha256": sha(repr(fwd_d).encode()),
                            "excused_gaps": excused}
            added = append_record(LOG, rec)
            g = rec["groups"]
            print(f"{rec['signal_day']} {'acrescentado' if added else 'já no log'} (atraso {rec['lag_h']} h): "
                  f"universo {len(rec['universe'])}; B {g['event_B']}; B∩rompimento {g['event_B_brk']}; "
                  f"comparação P {g['cmp_brk_sem_teste']}; controle R {len(g['ctrl_lta'])}; A {g['event_A']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
