**RESUMO**

Concordo com **H NÃO CONFIRMA, P NÃO CONFIRMA e família NÃO CONFIRMA**. Não encontrei defeito que altere esses rótulos nesta amostra. Há ressalvas metodológicas a registrar antes de fechar a KB.

**ARQUIVOS**

Nenhum criado ou modificado; nenhum commit.

**TESTES**

- `uv run pytest .claude/state/r91/test_stats91.py -q -p no:cacheprovider`: **17 passed, 1 warning** — aviso de `asyncio_mode`, com plugins automáticos desabilitados.
- Reexecução em memória, sem nova consulta ao banco: `h034.txt REPRODUCED=True`; `sec.txt REPRODUCED=True`.
- Hashes do pré-registro, unidades e lista elegível conferem.

**MUST-FIX**

1. **Ressalvar o Holm composto.** [run91.py:129](C:/dev/project-hunter/.claude/state/r91/run91.py:129) calcula Holm separadamente e depois toma o máximo. Isso implementa “passar nos dois cenários”, mas não garante, em geral, controle familiar para hipóteses compostas quando o cenário nulo difere entre medidas. Cenário sintético executado: p primário `{H:0,04; P:0,001}`, S1 invertido → método atual **0,04 para ambas**; Holm aplicado ao máximo por medida → **0,08 para ambas**. Declarar essa limitação; não reescrever retroativamente o protocolo. **Não muda R91.**

2. **Não publicar P-eventos como contraste com suporte suficiente.** [sec91.py:75](C:/dev/project-hunter/.claude/state/r91/sec91.py:75) recorta a pista sem reaplicar ≥5 por braço. Os **26/2 medidos** produzem um número, mas nenhum estrato dessa pista satisfaz o suporte congelado. Cenário: apresentar esse resultado como comparação válida entre pistas atribuiria evidência a uma célula sem suporte. Marcar como descritivo sem suporte; o contraste de **15 s mantém suporte**.

3. **Publicar também Holm S1 de P: 0,3524.** Citar somente 0,1490 omite o cenário exigido pelo protocolo; ambos constam em [h034.txt:28](C:/dev/project-hunter/.claude/state/r91/h034.txt:28).

**NICE-TO-HAVE**

- Metades não recalculam explicitamente o suporte ≥5 ([run91.py:65](C:/dev/project-hunter/.claude/state/r91/run91.py:65)). Conferi com suporte recalculado: **nenhum valor mudou**. Corrigir antes de reutilizar.
- S1 imputa −1 mesmo com numerário ausente ([run91.py:45](C:/dev/project-hunter/.claude/state/r91/run91.py:45)), contrariando a censura da emenda. Há **zero casos** no cache.
- A réplica SQL omite as janelas de transição; o congelamento registra **zero exclusões**, portanto sem impacto aqui ([q_replica.sql:16](C:/dev/project-hunter/.claude/state/r91/q_replica.sql:16), [freeze.txt:4](C:/dev/project-hunter/.claude/state/r91/freeze.txt:4)).

**O QUE EU FARIA DIFERENTE**

Publicaria todas as secundárias juntas: estavam previstas, portanto sua execução não constitui seleção pós-resultado. **Destacar só a vencedora constituiria leitura seletiva.** P-15 s tem IC nominal positivo; reais incluem zero e ambos os braços perdem; `comprou_no_topo` **1,19× fica abaixo da previsão 1,5×**, inclusive no limite superior 1,37. Nada disso resgata a família ([sec.txt:4](C:/dev/project-hunter/.claude/state/r91/sec.txt:4), [sec.txt:20](C:/dev/project-hunter/.claude/state/r91/sec.txt:20), [sec.txt:25](C:/dev/project-hunter/.claude/state/r91/sec.txt:25)).

**CONCORDO COM**

Estimador ponderado, multiplicidades do bootstrap, renormalização e deixa-um-fora estão coerentes com a emenda ([stats91.py:83](C:/dev/project-hunter/.claude/state/r91/stats91.py:83)). O congelamento precede a leitura registrada; não identifiquei antecipação nos artefatos examinados. Isso não certifica integralmente a pista de eventos, cuja limitação já foi declarada.

**NÃO CONFIRMA ≠ REFUTA; associação entre admitidas ≠ efeito causal de retirar filtros. Nada muda na mesa.**

**OBSIDIAN**

- **Fila de Hipóteses — H-034:** registrar os três rótulos, ambos os cenários e as ressalvas.
- **Nota de resultado H-034/R91:** preservar números, proveniência e todas as secundárias; não dizer “filtro funciona”, “não funciona” ou “vantagem confirmada”.
- **Mapa de Estratégias / comprou_no_topo:** resultado não confirmado; secundárias apenas como pistas para eventual pré-registro em dados novos.
- **Revisões-Astra — H-034:** registrar este parecer e a ausência de revisão independente do defensor, cuja ferramenta falhou.