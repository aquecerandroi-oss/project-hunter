"""H-026 B coorte prospectiva — guardas do detector: dia fechado, janela da coorte, log só-de-acréscimo, trava,
manifesto congelado (texto + código + base), classificação que só cresce e cobertura de velas do dia.

Pesquisa em arquivos; em produção cada guarda vira restrição de banco (ver o relatório da tarefa).
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path

EPOCH = dt.date(1970, 1, 1)
FORWARD_START = (dt.date(2026, 9, 28) - EPOCH).days
FORWARD_END = (dt.date(2030, 9, 27) - EPOCH).days  # último dia de sinal da coorte (parada dura do pré-registro)
LISTED_LOOKBACK = 14  # "listado" = vela real em [d − 14, d − 1] (r84/engine.ALIVE_LOOKBACK)


class NotClosedError(RuntimeError):
    """O dia pedido ainda não fechou em UTC (a vela dele ainda está em formação)."""


class LogOrderError(RuntimeError):
    """O log só cresce do início da coorte para a frente, um dia de cada vez, sem buraco."""


class CohortClosedError(RuntimeError):
    """Dia de sinal depois da parada dura: não entra nesta coorte (prolongar = registro novo)."""


class LockedError(RuntimeError):
    """Outra execução segura o log (ou caiu deixando a trava — conferir e apagar à mão)."""


class FrozenMismatchError(RuntimeError):
    """Texto, código, base ou classificação diferente do congelado: emenda explícita, nunca silenciosa."""


class CoverageError(RuntimeError):
    """Moeda negociável e listada sem vela no dia: o dia não fecha até a vela chegar ou a ausência ser aceita."""


def iso(day: int) -> str:
    return (EPOCH + dt.timedelta(days=int(day))).isoformat()


def day_of(text: str) -> int:
    return (dt.date.fromisoformat(text) - EPOCH).days


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assert_closed(day: int, now: dt.datetime, margin_s: int = 0) -> None:
    ready = dt.datetime(1970, 1, 1, tzinfo=dt.UTC) + dt.timedelta(days=day + 1, seconds=margin_s)
    if now < ready:
        raise NotClosedError(f"{iso(day)} só pode ser lido a partir de {ready.isoformat()} (agora {now.isoformat()})")


def coverage_gaps(rows: list[tuple], day: int, status_now: dict[str, str],
                  accepted: set[str]) -> tuple[list[str], list[dict[str, str]]]:
    """(faltas, dispensas) das moedas com vela em [day − 14, day − 1] e sem vela em `day`. Falta = `TRADING` agora e
    não aceita à mão ("SÍMBOLO:AAAA-MM-DD") → o dia espera. Dispensa = aceita à mão, ou fora de `TRADING` / fora do
    exchangeInfo na execução — cada uma com o motivo, para o registro do dia (Astra, rodada 3, #2)."""
    recent, today = set(), set()
    for r in rows:
        if r[1] == day:
            today.add(r[0])
        elif day - LISTED_LOOKBACK <= r[1] < day:
            recent.add(r[0])
    gaps, excused = [], []
    for s in sorted(recent - today):
        st = status_now.get(s)
        if f"{s}:{iso(day)}" in accepted:
            reason = "aceita à mão (--accept-gap)"
        elif st == "TRADING":
            gaps.append(s)
            continue
        else:
            reason = f"status {st} na execução" if st else "fora do exchangeInfo na execução"
        excused.append({"symbol": s, "day": iso(day), "reason": reason})
    return gaps, excused


# ------------------------------------------------------------------------------ log só-de-acréscimo


def read_log(log: Path) -> list[dict]:
    if not log.exists():
        return []
    out = []
    for n, line in enumerate(log.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            rec = json.loads(line)
            day_of(rec["signal_day"])
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            raise LogOrderError(f"linha {n} do log inválida (queda no meio da escrita?) — reparar à mão: {exc}") from exc
        out.append(rec)
    return out


def append_record(log: Path, rec: dict, first_day: int = FORWARD_START, last_day: int = FORWARD_END) -> bool:
    days = [day_of(r["signal_day"]) for r in read_log(log)]
    day = day_of(rec["signal_day"])
    if day in days:
        return False
    if day > last_day:
        raise CohortClosedError(f"{rec['signal_day']} depois da parada dura {iso(last_day)}")
    expected = days[-1] + 1 if days else first_day
    if day != expected:
        raise LogOrderError(f"{rec['signal_day']} fora de ordem: o próximo dia do log é {iso(expected)}")
    with log.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
    return True


@contextlib.contextmanager
def run_lock(log: Path) -> Iterator[None]:
    lock = log.with_name(log.name + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise LockedError(f"trava presente: {lock}") from exc
    try:
        os.write(fd, dt.datetime.now(dt.UTC).isoformat().encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


# ------------------------------------------------------------------------------ congelamento


def check_frozen(prereg: Path, frozen: Path, shas: dict[str, str], freeze: bool = False) -> str:
    """Confere (ou grava, uma vez) o sha256 do PREREG.md e os `shas` estáticos (código, base). Devolve o do texto."""
    now = {"prereg_sha256": sha(prereg.read_bytes()), **shas}
    if frozen.exists():
        want = json.loads(frozen.read_text(encoding="utf-8"))
        bad = [k for k in now if want.get(k) != now[k]]
        if bad:
            raise FrozenMismatchError(f"diferente do congelado: {bad} — emenda datada, nunca edição")
    elif freeze:
        body = now | {"frozen_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
        frozen.write_text(json.dumps(body, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return now["prereg_sha256"]


def load_classified(path: Path, prev_len: int, prev_sha: str | None) -> tuple[dict[str, bool], int, str | None]:
    """Classificações de bases novas (JSONL só-de-acréscimo). Os primeiros `prev_len` bytes têm de ser os mesmos da
    última execução (`prev_sha`): acrescentar pode, reescrever não."""
    raw = path.read_bytes() if path.exists() else b""
    if prev_len and (len(raw) < prev_len or sha(raw[:prev_len]) != prev_sha):
        raise FrozenMismatchError(f"{path.name} reescrito: só se pode acrescentar classificações")
    cls: dict[str, bool] = {}
    for d in (json.loads(x) for x in raw.decode("utf-8").splitlines() if x):
        if d["base"] in cls:  # uma classificação por base: acrescentar outra seria reescrever (Astra, rodada 3, #1)
            raise FrozenMismatchError(f"{path.name}: base {d['base']} classificada duas vezes")
        cls[d["base"]] = bool(d["excluded"])
    return cls, len(raw), (sha(raw) if raw else None)
