# notes-T3.55a — literatura sobre padrões de candlestick (parte (a) do brief T3.55)

Agente: general-purpose (literatura, com acesso web). Início 2026-09-08 23:55 Brasília (02:55Z);
fim 2026-09-09 ~00:30 Brasília (03:30Z). **Nada commitado.** Só dois arquivos escritos no repositório:
`.claude/state/exp-drafts/KB-0080-candlestick-evidencia.md` e este.

## O que foi feito, em ordem

1. Lidos `brief-T3.55-candlestick.md`, `_TEMPLATE-NOTE.md`, `KB-0003` e `KB-0077` (forma, tom,
   frontmatter, regra do `confiança: "?"` para evidência mista).
2. Busca web (WebSearch) para cada grupo pedido: Marshall/Young/Rose 2006; Caginalp/Laurent 1998;
   Park/Irwin 2007; estudos cripto 2019–2025 com dado intradiário.
3. Abertura das fontes. **WebFetch devolveu 403 em ScienceDirect, SSRN, Wiley, ResearchGate, MDPI e
   Springer (redirect de autenticação)**; Semantic Scholar deu 429 em metade das chamadas. Saída:
   `curl` com user-agent de navegador para PDFs em hosts abertos + `pdftotext` (mingw). O `pdftotext`
   não abre caminho maior que ~260 caracteres — o scratchpad da sessão é longo demais; resolvido com o
   nome curto 8.3 (`C:/Users/evert/AppData/Local/Temp/claude/C--USE~2/9229A2~1/SCRATC~1`). Python não
   está no PATH desta máquina (alias da Microsoft Store) — não foi necessário.
4. Um comando de grep num HTML de 1,2 MB estourou o timeout de 60 s e o harness o moveu sozinho para
   background (não foi pedido; o output foi lido e era vazio). Nenhum outro comando em background.
5. Escrita da nota (§1–§8 + Fontes) e deste registro.

## Fontes abertas de verdade (URL → o que foi lido)

- Marshall, Young & Rose, working paper "Market Timing with Candlestick Technical Analysis"
  (mesmos autores/dados do JBF 2006; o texto remete ao JBF para detalhes):
  https://c.mql5.com/forextsd/forum/211/Market%20Timing%20with%20Candlestick%20Technical%20Analysis.pdf
  → 18 páginas lidas inteiras, Tabelas 1 (t-test) e 2 (bootstrap).
- Marshall, Young & Rose (2006) JBF: https://www.sciencedirect.com/science/article/abs/pii/S0378426605002116
  → **403**. Entrada bibliográfica aberta em
  https://econpapers.repec.org/RePEc:eee:jbfina:v:30:y:2006:i:8:p:2303-2323 (sem resumo).
- Caginalp & Laurent (1998): https://tradingwithrayner.com/wp-content/uploads/2014/11/The-Predictive-Power-of-Price-Patterns.pdf
  → 25 páginas lidas inteiras (definições dos 8 padrões, Definição 3.1 de tendência, Tabelas 1–5,
  lucros antes/depois de custos, conclusões). Resumo confirmado em
  https://econpapers.repec.org/RePEc:taf:apmtfi:v:5:y:1998:i:3-4:p:181-205.
- Park & Irwin (2004) AgMAS 2004-04: https://farmdoc.illinois.edu/assets/marketing/agmas/AgMAS04_04.pdf
  → resumo, trechos sobre padrões gráficos/Caginalp (linhas ~2159 e ~2426 do texto extraído),
  "Summary and Conclusion".
- Park & Irwin (2007) JES: https://experts.illinois.edu/en/publications/what-do-we-know-about-the-profitability-of-technical-analysis/
  → resumo (95 estudos: 56/20/19).
- Ho, Chan, Pan & Li (2021) IEEE Big Data:
  https://api.semanticscholar.org/graph/v1/paper/DOI:10.1109/bigdata52589.2021.9671826?fields=title,abstract,authors,year,venue
  → resumo. Metadados no Crossref. Texto não lido.
- Cohen (2021) RQFA: https://link.springer.com/article/10.1007/s11156-021-00973-6 (via curl)
  → `dc.description` = resumo completo + metadados. Texto não lido.
- Kuna (2025), tese Charles University:
  https://dspace.cuni.cz/bitstream/handle/20.500.11956/197060/130412926.pdf?sequence=1&isAllowed=y
  → §2.3, §3.1–3.6, cap. 4, §5.2–5.5, cap. 6.
- Moser & Brauneis (2026) IREF: https://www.sciencedirect.com/science/article/pii/S1059056026002716
  → **NÃO ABERTO** (403 na página e no `pdfft`; ResearchGate 403; Semantic Scholar sem resumo;
  Crossref https://api.crossref.org/works/10.1016/j.iref.2026.105158 só metadados). Na nota, tudo
  sobre ele vem de trechos de resumo em resultados de busca e está marcado assim.
- Shanaev, Vasenin & Stepanov (2023) Heliyon: https://pmc.ncbi.nlm.nih.gov/articles/PMC10015199/
  → artigo aberto (resumo, dados, métodos, custos, conclusão).
- Jönsson (2016), Lund: https://lup.lub.lu.se/luur/download?func=downloadFile&recordOId=8877738&fileOId=8877838
  → resumos (sueco e inglês).
- Vahidpour et al. (2024): https://journals.indexcopernicus.com/api/file/viewByFileId/1938845
  → resumo e seção de dados (20 criptos Binance, 2022–23, diário e horário, 48 padrões).
- Uzun et al. (2024) Computation: https://api.crossref.org/works/10.3390/computation12070132 → resumo.
- Kapur et al. (2024) IJQRM: https://www.emerald.com/ijqrm/article-abstract/41/8/2055/1217341/ → resumo.
- TA-Lib: https://raw.githubusercontent.com/TA-Lib/ta-lib/main/src/ta_common/ta_global.c e
  `src/ta_func/ta_CDL{HAMMER,ENGULFING,MORNINGSTAR,SHOOTINGSTAR,HARAMI,3WHITESOLDIERS,MARUBOZU}.c`
  → tabela de settings e as condições `if` de cada padrão.
- Não usados: Park & Irwin 2005 (futuros, snooping-free; baixado, só cabeçalho), arXiv 2510.12911
  (regressões spot com candlesticks — outro assunto), tese de doutorado de Marshall na Massey
  (PDF corrompido, `pdftotext` falhou na xref).

## O que ficou aberto para a Sexta-feira

- **Abrir Moser & Brauneis (2026)** por outro caminho (biblioteca, autor, working paper). É a única
  evidência intradiária com correção de snooping e a nota depende dela para o item 4 do veredito.
- Decidir com a Astra: Holm vs SPA stepwise na T3.55b (§8 da nota).
- A T3.55b deve reportar frequência por rótulo/timeframe **antes** de retornos (§7 da nota).

## Veredito (cópia da §6 da nota)

1. Ações diárias: o "sim" de Caginalp & Laurent (1998) não sobreviveu ao bootstrap de Marshall,
   Young & Rose (2006: 28 regras, DJIA 1992–2002, nada acima do acaso, cinco significâncias com o
   sinal errado). Jönsson (2016) replica o "não".
2. Park & Irwin: padrões gráficos são a categoria que menos trata data snooping.
3. Cripto diário (Ho et al. 2021; Kuna 2025): nada nas grandes; um punhado nas pequenas, dois com
   sinal invertido, sem correção, sem custos. Cohen (2021) é in-sample: anedótico.
4. Cripto horário (Moser & Brauneis 2026, não lido): harami de alta/baixa, hikkake e enforcado
   sobrevivem a SPA stepwise; efeito e custos desconhecidos.
5. Prior para perps a 15 m / 1 h: efeito de poucos bps por barra, abaixo do pedágio de KB-0008; a
   única família com sustentação intradiária é harami / engolfo / martelo-enforcado em contexto de
   tendência, mais plausível a 1 h. O resto é painel.
6. Sem gap em 24/7 — definições redefinidas por não-sobreposição de corpos.

## Lista para a T3.55b (§7 da nota)

11 famílias / 18 rótulos: martelo, enforcado, estrela cadente, martelo invertido, doji, marubozu
(alta/baixa), engolfo (alta/baixa), harami (alta/baixa, sub-rótulo cruz), estrela da manhã/noite,
três soldados/corvos, três dentro para cima/baixo. Escala `atr_ref = ATR14 Wilder em t0−1`;
contexto `EMA10` + inclinação em `t0−1`; detecção no fechamento da última barra; tudo em `Decimal`
sem divisão; invalidação natural por padrão para a lente do pedágio.
