**RESUMO**

Sim: **rótulo → abas → filtros → resumo por versão → sinais** é a hierarquia que recomendo. O contexto vem antes dos números; a maturidade acompanha a amostra que qualifica. Parecer como `frontend-specialist`, em modo OPINIÃO.

| Decisão | Onde mudaria o componente proposto |
|---|---|
| **Maturidade dentro do card**, junto ao funil e antes das métricas. | Em `VersionSummaryCard`, inserir `MaturityLabel` abaixo da identidade/status: **“Inconclusivo · N/100 outcomes avaliáveis · D/30 dias distintos”**. No mobile, quebrar em linhas sem ocultar. Usar `maturity` da própria versão, inclusive depreciada; a API define esse objeto por versão. [lab_summary.py:124](/C:/dev/project-hunter/apps/api/hunter_api/schemas/lab_summary.py:124) |
| **Duas linhas explícitas para PnL/drawdown**, dentro do card. | Após as cinco métricas principais, antes de `r_ex_funding`, colocar **“PnL de carteira: não aplicável”** e **“Drawdown de carteira: não aplicável”** em texto secundário. Sem título “Carteira”, caixa própria ou badge anexada a outra métrica: essa proximidade poderia fazer “não aplicável” parecer qualificar a expectancy ou a soma de R. Os dois campos têm motivos próprios no schema. [lab_summary.py:120](/C:/dev/project-hunter/apps/api/hunter_api/schemas/lab_summary.py:120) |
| **Tom neutro com leitura confortável.** | Em `MaturityLabel` e nas duas linhas, usar `fg-muted`, texto de 12–14 px e contraste AA; sem ícone de alerta, pulso ou dourado. Texto sempre exposto, tooltip apenas para explicação adicional. Compatível com [DESIGN.md:57](/C:/dev/project-hunter/docs/DESIGN.md:57). |

**ARQUIVOS**

Nenhum criado ou modificado. Os nomes de componentes acima são propostas.

**TESTES**

Não executados; análise documental e dos schemas/router, sem implementação.

**MUST-FIX**

- **Explicitar o alcance de `window`.** O resumo aceita janela; a lista de sinais não aceita `window` nem `as_of`. Cenário: selecionar “7d” e encontrar sinais antigos abaixo faz parecer que o filtro falhou. Em `LabFilters`, escrever **“Janela do resumo”**; na tabela, explicitar **“Sinais · todo o período”** enquanto esse contrato permanecer. [lab.py:130](/C:/dev/project-hunter/apps/api/hunter_api/routers/lab.py:130), [lab.py:150](/C:/dev/project-hunter/apps/api/hunter_api/routers/lab.py:150)

- **Não universalizar custos da primeira versão.** Os custos são por versão e admitem nulos. Cenário: duas versões com custos diferentes ficam sob um cabeçalho que declara apenas os da primeira. Em `ShadowHeader`, mostrar valores comuns somente quando forem iguais e conhecidos; caso contrário, **“custos assumidos: discriminados por versão”**, com os valores em cada card. [lab_summary.py:91](/C:/dev/project-hunter/apps/api/hunter_api/schemas/lab_summary.py:91), [lab_summary.py:125](/C:/dev/project-hunter/apps/api/hunter_api/schemas/lab_summary.py:125)

**NICE-TO-HAVE**

Acrescentar **“nesta janela e coorte”** ao selo para esclarecer seu alcance.

**O QUE EU FARIA DIFERENTE**

Não colocaria aviso editorial global por versão ativa. Isso separa a ressalva dos números e deixa a leitura das versões depreciadas sem o mesmo contexto. Ao superar o limiar, manteria **“Pesquisa”**, conforme o [brief:12](/C:/dev/project-hunter/.claude/state/brief-S3b-lab-page.md:12).

**CONCORDO COM**

A ordem proposta, a única aba Sombra visível e o envelope aberto sob demanda.

**OBSIDIAN**

- **Strategy Performance** — registrar maturidade junto à amostra e as duas declarações de não aplicabilidade dentro do card.
- **Revisoes-Astra/Index** — vincular este parecer de S3b, incluindo os cuidados com janela e custos por versão.