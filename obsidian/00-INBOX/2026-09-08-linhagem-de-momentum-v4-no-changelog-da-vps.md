---
tags: [inbox, pendencia, operacao, estrategias, catalogo]
status: aberto
owner: sexta-feira
updated: 2026-09-08
---

# Pendência operacional — a linhagem de `momentum v4` sumiu do `changelog` na VPS

**Aberta em 2026-09-08 (T3.26b).** Primeira nota de `00-INBOX/`: pendência **operacional** (uma
escrita em produção que espera decisão), não bug de código e não decisão de arquitetura. Sai daqui
quando for aplicada ou descartada — com a data e o motivo.

> [!alerta] Efeito concreto, hoje
> Quando `infra/scripts/export_strategies_to_obsidian.py` rodar, a página de catálogo
> `03-TRADING/Estrategias/momentum-v4.md` **nasce sem "Versão anterior"**: `derived_from: ""`, sem o
> link para [[momentum-v2]]. A página não fica errada — fica **muda** sobre a única coisa que
> distingue uma variante de pesquisa de uma estratégia nova.

## O que aconteceu

`infra/scripts/derive_variant.py` (T3.26) congela a linhagem no `changelog` da linha derivada, num
formato que o exportador do catálogo sabe ler:

```
variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.0089 | params_hash=46635ed2bff2 | <motivo>
```

A ativação é a **única** escrita que uma linha derivada recebe depois disso, e ela **substitui** o
`changelog`. A correção que preserva o prefixo (`keep_lineage`, em
`services/strategy-worker/hunter_strategy_worker/activate_derived.py`) foi escrita na mesma tarefa —
mas **a imagem que roda na VPS é anterior a ela**. Resultado: a linha ativada em produção hoje diz

```
T3.26: coorte de pesquisa da variante de piso de custo aberta (research_only, sem carteira)
```

e **não** contém `derived_from=v2`.

## O que **não** se perdeu

O evento `strategy_version_variant_derived` em `system_events` carrega pai, `code_ref`,
`params_hash` completo e o override — e a seção "Origem" da página de catálogo lê exatamente essa
tabela. O que falta é só o campo `derived_from` do frontmatter, que vem do `changelog`.
`params_hash`, `code_ref`, `parameters_schema`, `default_parameters` e `activated_at` continuam
congelados e corretos; nada do experimento está em risco ([[EXP-0006-momentum-piso-de-custo]]).

## Correção proposta (uma linha, e é decisão do Everton)

`changelog` **não** é campo congelado pela trigger (a trigger congela `code_ref`,
`parameters_schema`, `default_parameters`, `params_format` e `activated_at`), então a correção cabe
num `UPDATE` idempotente, na VPS:

```sql
UPDATE strategy_versions
   SET changelog = 'variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.0089 '
                || '| params_hash=46635ed2bff2 | ' || changelog
 WHERE id = '44d106b6-bb87-40a7-85e4-fa3cb80c8060'
   AND changelog NOT LIKE 'variante de v%';
```

**Por que não a apliquei:** é escrita à mão em produção, numa tabela de experimento congelado, sem
ferramenta auditada por trás — exatamente o tipo de ato que esta base exige que seja decidido por
quem responde pelo produto. O `quant-engineer` também não a aplicou, pelo mesmo motivo
(`.claude/state/notes-T3.26.md`, concern 1).

## As três saídas possíveis

| Saída | O que custa | O que fica |
|---|---|---|
| **A — aplicar o `UPDATE` acima** | uma escrita manual em produção, com o `AND` que a torna idempotente | catálogo completo hoje; o texto do `changelog` deixa de ser exatamente o que o script escreveu |
| **B — esperar o próximo deploy** | zero agora; a página de `momentum-v4` nasce muda até lá | depois do deploy, `keep_lineage` impede a repetição — mas **não** conserta a linha que já foi ativada: ela só é escrita uma vez |
| **C — não corrigir e documentar** | zero | a linhagem vive só em `system_events` e nesta nota; quem ler o catálogo precisa saber que existe esta página |

A saída B **não** conserta sozinha o caso já ativado — vale dizer isso em voz alta, porque "espera o
deploy" soa como se resolvesse.

## Quem decide

**Everton.** Escrita em produção fora de ferramenta auditada não é decisão de plantão.

## Ligações

[[EXP-0006-momentum-piso-de-custo]] · [[Strategy Backlog]] · [[Strategies]] · [[Open Bugs]] ·
[[Changelog]] · `.claude/state/notes-T3.26.md` (concern 1) · `infra/scripts/derive_variant.py` ·
`infra/scripts/export_strategies_to_obsidian.py`
