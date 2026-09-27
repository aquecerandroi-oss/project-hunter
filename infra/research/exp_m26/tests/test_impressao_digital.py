"""A impressão digital congela o spec J: cobre todo o código de que a leitura depende e o
texto do protocolo, não depende do fim de linha (Windows × VPS) e muda com qualquer byte."""

from __future__ import annotations

import ast
from pathlib import Path

from infra.research.exp_m26.impressao_digital import ARQUIVOS, RAIZ, impressao, por_arquivo

_PACOTE = RAIZ / "infra" / "research" / "exp_m26"


def _importados(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("infra."):
            out.add(node.module)
            out.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            out.update(a.name for a in node.names if a.name.startswith("infra."))
    return out


def _arquivo_do_modulo(nome: str) -> Path | None:
    base = RAIZ.joinpath(*nome.split("."))
    for p in (base.with_suffix(".py"), base / "__init__.py"):
        if p.exists():
            return p
    return None


def test_cobre_o_fecho_de_importacoes_da_leitura() -> None:
    cobertos = {RAIZ / a for a in ARQUIVOS}
    fila = [p for p in _PACOTE.glob("*.py")]
    vistos: set[Path] = set()
    while fila:
        p = fila.pop()
        if p in vistos:
            continue
        vistos.add(p)
        assert p in cobertos, f"{p.relative_to(RAIZ)} fica fora da impressão digital"
        for mod in _importados(p):
            alvo = _arquivo_do_modulo(mod)
            if alvo is not None:
                fila.append(alvo)
    for extra in ("export_h022.sql", "protocolo_h022.txt"):
        assert _PACOTE / extra in cobertos


def test_testes_nao_entram() -> None:
    assert not any("/tests/" in a for a in ARQUIVOS)


def test_fim_de_linha_nao_muda_e_um_byte_muda(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_bytes(b"x = 1\ny = 2\n")
    (tmp_path / "b.txt").write_bytes(b"protocolo\n")
    lf = impressao(tmp_path, ("a.py", "b.txt"))
    (tmp_path / "a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    assert impressao(tmp_path, ("a.py", "b.txt")) == lf
    (tmp_path / "a.py").write_bytes(b"x = 1\ny = 3\n")
    assert impressao(tmp_path, ("a.py", "b.txt")) != lf
    assert len(lf) == 64


def test_por_arquivo_e_estavel() -> None:
    assert por_arquivo() == por_arquivo()
    assert impressao() == impressao()
