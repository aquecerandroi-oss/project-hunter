"""``constraints.py`` fica **fora** do fecho que congela cada versão (T3.26c).

``code_ref`` é o digest do módulo da estratégia mais o fecho transitivo dos
irmãos que ela importa (``code_ref.py``). ``momentum_v1`` e ``volume_anomaly_v1``
importam ``schema``, então a tabela de faixas da A2, se tivesse ido para lá,
moveria o digest das duas — e **toda versão já ativada na VPS**, inclusive a
linha ``paper``, viraria ``code_ref_mismatch`` em ``load_version_roster``: o Lab
inteiro em silêncio atrás de um ``/ready`` verde. Foi por isso que a tabela
ganhou módulo próprio, e é isto que impede alguém de desfazer a decisão sem
perceber.

Os dois digests abaixo são os que o repositório carrega no commit da T3.26c,
medidos antes de qualquer edição desta tarefa. Não são um número mágico: são o
mesmo valor que as linhas congeladas em produção carregam, e a única razão para
mudá-los é uma mudança **deliberada** no código de uma estratégia, que exige
``--supersede``.

Run: ``uv run pytest services/strategy-worker/tests/test_constraints_outside_freeze.py -q``
"""

from __future__ import annotations

import pytest

from hunter_core.strategies.registry import DEFAULT_REGISTRY
from hunter_strategy_worker.code_ref import module_closure, strategy_module, version_code_ref

pytestmark = pytest.mark.unit

FROZEN_DIGESTS = {
    "momentum_v1": (
        "hunter_core.strategies.momentum_v1@sha256:"
        "ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c"
    ),
    "volume_anomaly_v1": (
        "hunter_core.strategies.volume_anomaly_v1@sha256:"
        "9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22"
    ),
}
"""Medidos em ``3dd8f3a`` (antes da T3.26c) com
``version_code_ref(strategy_module(s))`` para cada estratégia registrada."""


class TestTheConstraintsTableIsNotFrozenCode:
    def test_no_strategy_imports_it(self) -> None:
        for strategy in DEFAULT_REGISTRY.all():
            closure = module_closure(strategy_module(strategy))
            assert "constraints" not in closure, (
                f"{strategy.key} passou a importar constraints: o code_ref dele mudou e "
                "toda versão congelada dessa estratégia virou code_ref_mismatch"
            )

    def test_schema_is_in_the_closure_which_is_why_the_table_is_not_there(self) -> None:
        """A metade que explica a outra: ``schema`` **está** congelado."""
        for strategy in DEFAULT_REGISTRY.all():
            assert "schema" in module_closure(strategy_module(strategy))


class TestTheDigestsDidNotMove:
    @pytest.mark.parametrize("module", sorted(FROZEN_DIGESTS))
    def test_the_digest_is_the_one_the_activated_rows_carry(self, module: str) -> None:
        assert version_code_ref(module) == FROZEN_DIGESTS[module]

    def test_every_registered_strategy_is_covered(self) -> None:
        assert {strategy_module(s) for s in DEFAULT_REGISTRY.all()} == set(FROZEN_DIGESTS)
