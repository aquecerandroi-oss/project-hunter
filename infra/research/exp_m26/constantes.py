"""Os números congelados da H-022 — um lugar só, coberto pela impressão digital.

Cada constante cita a sua origem no desenho (`docs/design/exp-m26-grafico-moedas-maduras.md`)
ou é uma **interpretação executável** do J, marcada `J:` e repetida em `protocolo_h022.txt`.
Mudar qualquer uma muda a impressão digital: é versão nova e hipótese nova (§4).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

EXP_REF = "EXP-M26"
RULE_SET_C = "01994d00-6c1a-7000-8000-00000000001f"  # grafico_ctrl_v1/1 (0067, DATABASE §69)
RULE_SET_L = "01994d00-6c1a-7000-8000-000000000020"  # grafico_v1/1
RULE_SET_H = "01994d00-6c1a-7000-8000-000000000021"  # grafico_v1/2
BRACOS = (RULE_SET_C, RULE_SET_L, RULE_SET_H)

# --- calendário (§4) ---------------------------------------------------------
PILOTO = timedelta(hours=48)
"""T0 = seed + 48 h. J: seed = `meme_rule_sets.created_at` de C."""
DIAS_MINIMOS = 7
DIAS_MAXIMOS = 21
META_TRUE = 150
META_FALSE = 450
LEITURA_APOS_CORTE = timedelta(hours=2)
JANELA_EXPORTACAO = timedelta(hours=1)
"""J: o export (retrato da leitura) tem de ser tirado em [L, L + 1 h]; depois disso pode
trazer informação chegada depois de L (Astra, revisão do J, must-fix 2)."""

# --- população e classes (§2.2) ----------------------------------------------
FIDEDIGNA = "faithful"
COBERTAS = frozenset({"covered", "covered_from_birth"})
FALSE_OPERACIONAL = frozenset({"flat", "out_of_range"})
EXCLUSOES_SUBSTANTIVAS = ("creator_serial", "symbol_clone")
"""Só estas excluem por regra conhecida (E); todo o resto sem proposta é instrumento (I)."""
PISO_DISTANCIA = Decimal("0")
TETO_DISTANCIA = Decimal("0.25")
TETOS_PLANALTO = (Decimal("0.10"), Decimal("0.25"), Decimal("0.50"))

# --- inferência (§3/§4) -------------------------------------------------------
BLOCO = timedelta(hours=6)
"""Estrato = dia × bloco de 6 h UTC de `evaluated_at` = o bloco do bootstrap temporal."""
MRE = 0.03
REPS = 10_000
SEMENTE = 20260926
"""A semente pré-registrada na H-022 ("10 000 cada, semente 20260926"): a mesma em todos os
procedimentos (bootstraps por mint e por blocos, permutação, estresse, p centrado). Não se
afirma números aleatórios comuns entre observado e estresse: os arrays mudam."""
ALPHA = 0.05
MAX_REPLICAS_INVALIDAS = 0.01
"""J: réplica sem estrato com os dois grupos é inválida; acima de 1 % o IC não é finito."""
MIN_REPLICAS_VALIDAS = 100
P_NAO_TESTAVEL = 1.0
"""J: hipótese não testável continua na família de Holm com p = 1."""

# --- mínimos e tetos (§3 refutação, §4 denominadores) ------------------------
MIN_ESTRATOS = 10
MIN_TRUE = 100
MIN_FALSE = 300
MIN_PARES = 100
MIN_BLOCOS_PARES = 10
TETO_DESCONHECIDA = 0.20
TETO_SEM_PROPOSTA = 0.05
TETO_FALHA = 0.20
TETO_PARES_AUSENTES = 0.20

# --- robustez (§3 previsão) ----------------------------------------------------
MIN_POR_GRUPO_TERCIL = 20
MIN_TERCIS_COM_SINAL = 2
TETO_SLOPE_AUSENTE = 0.20

# --- censura (§4) --------------------------------------------------------------
DIAGNOSTICO_CENSURA = -0.50
QUANTIL_L_AUSENTE = 0.90
QUANTIL_DIFERENCA_AMBOS = 0.10
PONTOS_GRADE = 5
"""J: grade 2D por grupo = −1, meio, média observada, meio, p90 observado."""

# --- cenário contábil "real-equivalente" (§4, descritivo) ----------------------
TAXA_ALT_PERNA = Decimal("0.01045")
"""J: (1,59 % pump.fun + 0,50 % criador) por ida-e-volta, repartido meio a meio por perna
(KB-0147); base da compra = `sol_spent`, base da venda = `curve_proceeds_sol`."""
REDE_IDA_E_VOLTA = Decimal("0.0013")
"""0,13 % de rede por ida-e-volta, sobre `size_sol`."""
RENT_SOL = (Decimal("0.00151384"), Decimal("0"))
"""Os dois cenários de rent: não devolvido e devolvido."""
