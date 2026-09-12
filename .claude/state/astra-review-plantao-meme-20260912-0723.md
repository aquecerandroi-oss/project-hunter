**RESUMO**
Como `quant-engineer`, testaria **criador em série → M-P25 → fees como hipótese própria**; coletaria os três prospectivamente desde já. Antes: validar relógios e conclusão, conforme [parecer anterior](/C:/dev/project-hunter/obsidian/02-MARKET/Meme/2026-09-12.md:381).
Criador em série tem definição mais objetiva e permite contraste entre criações contemporâneas; complementa [M-P5](/C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:86). Isso justifica prioridade, não pressupõe vantagem.
Definiria `creator_prior_mints_1h` por **endereço criador**, mints distintos em `[t−1h,t)`, excluindo o atual, conhecidos em `t`; histórico incompleto = desconhecido, nunca zero. Compararia modelo-base com M-P5 versus base + contagem.

**ARQUIVOS**
Nenhum criado ou modificado; nenhum commit.

**TESTES**
Não executados: parecer metodológico. Li rascunho e memória; consultei documentação oficial sobre boosts e fees. Não revalidei os números históricos externos.

**MUST-FIX**
- **Seleção:** substituir “narrativa da manhã” por “temas observados nos dois rankings às 07:26”. Misturar chains, programas e publicidade pode atribuir ao universo pump uma composição que ele não tem ([rascunho:66](/C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0723-lane2.md:66)). Boost comprado aumenta visibilidade; duas fontes não constituem replicação independente. [DEX Screener](https://docs.dexscreener.com/boosting)
- **Inferência indevida:** retirar “não demanda”, “descarta notícia” e “mesma assinatura de bundle”. Busca negativa não mede demanda; intervalo derivado de 1 s, com arredondamento e sem transações, não identifica bundle ([rascunho:54](/C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0723-lane2.md:54), [139](/C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0723-lane2.md:139)).
- **Comparabilidade:** média diária de snippet versus minutos de outro dia não demonstra sazonalidade horária; ausência de anúncio não prova curva/taxas inalteradas. Esses saltos poderiam legitimar replay incomparável ([rascunho:117](/C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0723-lane2.md:117), [137](/C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0723-lane2.md:137)).
- **Fees ≠ revenue:** `dailyFees` deve alimentar `venue_daily_fees_usd`; receita exige série correspondente. Buyback/fees não identifica política de distribuição sem reconciliar escopo e competência. [DefiLlama](https://docs.llama.fi/analysts/data-definitions)
- **Vazamento temporal:** usar somente dia UTC encerrado **e recebido antes de `t`**, preservando versões/revisões. Total final do próprio dia inclui atividade futura; além disso, variável diária não tem efeito próprio identificável com efeitos fixos completos de dia.

**NICE-TO-HAVE**
Manter `bo`, `t10` e saída das paródias do top-20 como observações datadas da fonte; não como prova de manipulação ou desaparecimento do tema.

**O QUE EU FARIA DIFERENTE**
Congelaria M-P25 agora para **coorte futura**; esta manhã serviu ao desenho e fica exploratória.
Arquivaria dicionário, hash, versão, `received_at`, `effective_from`, fontes e regras de normalização, fronteiras de palavras, aliases, sobreposição, empate e “outros”; alteração cria versão nova.
Arquivaria também os bytes de nome/símbolo/descrição disponíveis no instante da criação. Descrição recebida depois fica ausente na feature inicial; classificação em `t+60s` seria outro protocolo.
Dominância seria **estado do último snapshot disponível**, por fonte e universo definidos; nunca classificação retrospectiva do dia. Congelar periodicidade, validade máxima e indisponibilidade; nenhuma fotografia posterior preenche o passado.
Primário: conclusão da curva em 24 h sobre todas as criações elegíveis, sem exigir board/pool; separar migração e declarar perdas de seguimento, sem convertê-las em fracasso.
Testaria ganho incremental de **tema × dominância prévia**, controlando tema, dia/hora e Mayhem; exigir variação e suporte nos grupos comparados.
Régua mínima: **≥100 avaliáveis e ≥30 dias prospectivos**, conforme [memória:42](/C:/dev/project-hunter/obsidian/03-TRADING/Meme/README.md:42), com N, conclusões, criadores e dias por grupo. Esse piso não garante potência.
Dimensionaria N antes pelo risco-base, margem mínima relevante e potência ≥80%, preservando dependência por dia/criador; IC95% por blocos de dias e sensibilidade ao agrupamento por criador, Holm entre contrastes.
Confirmaria em período posterior, com fronteira protegida pelas 24 h de maturação. IC cruzando zero = inconclusivo; equivalência exige IC inteiro dentro de margem pré-fixada — não “ausência de significância”.

**CONCORDO COM**
Rotular nas criações, congelar antes e usar conclusão como desfecho são escolhas corretas; conclusão continua sem demonstrar retorno negociável.

**OBSIDIAN**
- **Meme — 2026-09-12:** acrescentar parecer do run 6, retiradas de inferência e prioridade do criador.
- **Hipoteses-do-plantao:** registrar complemento de M-P5 e protocolo prospectivo de M-P25, com disponibilidade temporal e régua de precisão.