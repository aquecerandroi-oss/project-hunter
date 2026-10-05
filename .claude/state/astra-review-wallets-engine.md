**RESUMO**

**REQUEST_CHANGES**, como `quant-engineer`. Os 69 testes passam, mas confirmei falhas de causalidade, preço e contabilidade.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

`uv run pytest packages/indicators/tests/meme -q`, sem cache: **`69 passed in 2.94s`**. Reproduções adicionais via `uv run python -`, somente em memória.

**MUST-FIX**

1. **Admissão retroativa.** Uma compra recebida 100 s atrasada, com slot anterior, transforma outra compra já recebida de `trigger` em `not_first_buy`. `run_arm` ordena por slot e `advance` consome a primeira compra mesmo recusada por atraso; `_c_pnl` repete isso. Confirmado. [follow.py:174](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/follow.py:174), [follow.py:122](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/follow.py:122), [ranking.py:76](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/ranking.py:76).

2. **Saída usa vendas ainda desconhecidas.** `_find_exit` acumula quantidades por slot antes de verificar disponibilidade. Reproduzi saída às **00:00:50**, dependendo de venda recebida às **00:02:24**: o atraso aplicado ao evento disparador não protege os eventos acumulados. [policy.py:90](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:90).

3. **Falta o estado anterior ao primeiro trade do slot.** Só entram estados pós-trade e do slot anterior. Sem evento anterior, uma compra que eleva reservas de 100 SOL/1.000 tokens para 200 SOL/500 tokens permite vender 10 tokens por **3.921.568.627**, quando o pior preço pré-trade seria **990.099.009 lamports**. [pricing.py:130](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:130).

4. **Arredondamento favorável.** Aplicar taxa fracionária e arredondar apenas o líquido retorna **977.722.772**, contra **977.722.771 lamports** arredondando bruto para baixo e taxa para cima. Taxas separadas exigem arredondamentos separados, como no cotador existente. [pricing.py:107](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:107), [quote.py:137](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/quote.py:137).

5. **Financiador futuro desfaz ligação passada.** B/C conhecidos hoje compartilham F; acrescentar A, resolvida amanhã, torna A a cabeça lexicográfica e adia todas as ligações. Confirmado: B/C deixam de estar unidos no corte anterior. [entities.py:64](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/entities.py:64).

6. **Custo desconhecido perde a marca de incompletude.** `open_with` descarta o custo preservado; o episódio entra na atividade normalmente. Reproduzi entidade elegível com 21 episódios contados, incluindo um lote `cost_lamports=None`. [episodes.py:116](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/episodes.py:116), [metrics.py:115](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/metrics.py:115).

7. **Exclusões históricas não alcançam C-PnL.** Tornar um mint criação do financiador removeu seu episódio de E, mas manteve C exatamente em **556.017.780 lamports / 20 cópias**. Esse episódio excluído ainda pode decidir o ranking. [metrics.py:112](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/metrics.py:112), [ranking.py:150](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/ranking.py:150).

**NICE-TO-HAVE**

Adicionar mutantes permanentes para ligações/criações futuras e eventos recebidos fora de ordem. Os testes atuais **têm dentes** para `received_at` errado; confirmei também detecção de mutantes de ligações e criação futuras. Porém, o teste intradiário só altera eventos com slots posteriores, deixando passar os itens 1–2. [test_wallets_leakage.py:105](/C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_leakage.py:105), [test_wallets_leakage.py:165](/C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_leakage.py:165).

**O QUE EU FARIA DIFERENTE**

Nesta onda, completaria também:

- **Contagem de incompletas e contaminação no ranking:** `_c_pnl` conserva apenas soma e número de cópias completas; perde esses diagnósticos. [ranking.py:94](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/ranking.py:94).
- **Controle 2 e suporte mínimo de H2:** o braço disponível admite apenas elegíveis fora do topo; falta representar o controle descritivo e o requisito de dez entidades comparáveis do §3.2. [follow.py:140](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/follow.py:140), [contrato:197](/C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:197).

**CONCORDO COM**

Timer contado da entrada e censura como imputação sem descontar custos novamente. [policy.py:84](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:84), [policy.py:157](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:157).

**OBSIDIAN**

- **carteiras-lucro-design** — registrar bloqueios e reproduções desta revisão.
- **KB-0182 — Quem ganha dinheiro de verdade nos memes** — incorporar as erratas de E-PnL e censura e o aceite pendente da onda 1c.