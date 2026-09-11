**RESUMO**

**Eu testaria primeiro a regressão de SOPH na D-P15; depois, capacidade sequencial D-P22; por último, H-P22.** SOPH oferece um teste pequeno de contabilidade. Capacidade responde à viabilidade econômica. H-P22 merece investigação, mas exige um contrafactual mais trabalhoso.

Parecer como `quant-engineer`: **DONE_WITH_CONCERNS**, somente leitura.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei pytest nem replay. Fiz inspeção estática e consultei o endpoint público `fapi/v1/fundingRate`, limitado ao corte de 11/09 09:35Z.

A consulta de SOPH esclareceu a dúvida:

```text
2026-09-10 17:00:00.003Z -0.00029063
2026-09-10 18:00:00.000Z -0.00011903
...
2026-09-11 09:00:00.004Z -0.00019423

settlements desde 18Z: 16
fora de abs(rate)<=0.00025: 0
```

São **16 settlements consecutivos dentro de ±0,025%**, precedidos por um fora. Isso é consistente com a mudança observada às 09:01Z. A [regra oficial](https://www.binance.com/en/support/announcement/detail/e4445d0389ce4defa6009021fcf6ee46) exige consecutividade, permite aproximadamente 15 minutos para atualizar a configuração e mantém os pagamentos na grade UTC de quatro horas.

Não reconfirmei independentemente o snapshot dos 782 símbolos, todos os anúncios nem as datas da Glassnode; essas partes permanecem informações do seu levantamento.

**MUST-FIX**

1. **SOPH: separar mudança de configuração, settlement e detecção pelo resolver.**

   De 08/09 12:01Z a 11/09 09:01Z são **69 horas**, não 68. O relógio relevante para a regra começou na sequência calma das 18:00Z, não na entrada em cadência horária.

   **O resolver pode, sim, produzir um `funding_missing` indevido na volta.** Cenário concreto, ainda prospectivo no corte informado: entrada às 09:05Z, saída às 10:30Z, nenhum settlement às 10:00Z porque a próxima cobrança será às 12:00Z. O histórico disponível ainda contém gaps horários; o código infere 1h e projeta uma cobrança às 10:00Z. A inferência usa os três últimos gaps e uma única grade para toda a janela: [funding.py:148](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:148), [funding.py:271](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:271). O carregamento termina na saída mais dois segundos: [settle.py:60](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:60).

   Isso é **cenário deduzido do código, não falha observada em aposta real de SOPH**. A D-P15 já registra recusas semelhantes em janelas hipotéticas de PROM: [Hipóteses:36](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:36). O teste deve verificar timestamps, cobertura e cobrança; não transformar a recusa em zero automaticamente.

2. **Capacidade: a conclusão está certa; a alegação de inexistência está forte demais.**

   Escreveria **“não encontramos estudo que calibre capacidade por mercado para nossa execução na Binance”**, em vez de “não existe paper”.

   Em Barone–Lillo, **F é o volume total do mercado durante a execução dividido pelo volume móvel de 24h**; a parcela diária da própria metaordem é `ηF`. O impacto é normalizado por volatilidade e mede deslocamento de preço até o término, não diretamente o custo médio dos fills. Portanto, `Y=0,186` não é uma tarifa em bps. Cenário de erro: aplicar essa superfície à ordem imediata e atribuir-lhe uma capacidade que depende de execução distribuída no tempo. [Paper, §§2.1–3.1](https://arxiv.org/html/2606.15715).

   A KB-0070 também **não calibra capacidade operacional**: registra apenas ask durante 11 segundos. [KB-0070:36](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0070-a-tabela-de-capacidade-quantos-mercados-suportam-cada-tamanho.md:36).

3. **H-P22: histórico de aposentadorias sozinho não identifica o efeito da política.**

   Cenário de erro: selecionar hoje quais das quatro aposentadas teríamos mantido, usando resultados posteriores, e apresentar isso como melhoria prospectiva. Mudar uma promoção altera a versão vigente, as próximas decisões e eventualmente os descendentes.

   Também separaria **substituição por desafiante** de **aposentadoria sem substituto**. Uma vantagem relativa pode apenas escolher a menos ruim entre duas versões com expectancy negativa. Falta de evidência de piora tampouco prova “não piora”: isso exige margem de não inferioridade previamente definida.

**NICE-TO-HAVE**

Para SOPH, acrescentaria casos antes do primeiro settlement de 4h, no gap de transição **09→12**, depois de dois gaps completos de 4h e com uma ausência real inserida como controle. Não reabriria toda a D-P15.

Para Glassnode, a comparação só fica útil com mesmo instrumento, tamanho, lado, referência de preço e agregação temporal. Uma estimativa de caminhada no livro não equivale a fills realizados.

**O QUE EU FARIA DIFERENTE**

**H-P22 acrescenta algo ao funil, desde que seja uma política explícita de substituição.** A replicação atual consulta o veredito prospectivo do pai; a aposentadoria tem verificações operacionais, mas esses caminhos não implementam essa comparação pareada semanal: [replication.py:257](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replication.py:257), [deprecate.py:57](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/deprecate.py:57).

Minha formulação seria:

> Comparar o funil atual com substituição por vantagem pareada contra a **versão vigente**, com margem econômica congelada, mesmo orçamento e resultados maturados; medir trocas e não inferioridade da expectancy líquida em período posterior à seleção.

Usaria dias comuns para pareamento, sem restringir aos trades coincidentes. Reportaria também frequência, ocupação e resultado por orçamento: elevar R/aposta cortando quase todas as entradas pode piorar a política. Blocos de um dia seriam uma escolha a validar, não garantia de independência.

Dutta sustenta o método, não nosso resultado econômico: a redução relativa de NLL é **0,1472% contra calendário**, **0,0755% contra promoção cega com a mesma espera** e **0,0428% contra manutenção contínua**. O segundo contraste isola melhor o valor do gate. Não importaria `τ=10⁻⁴` para R nem interpretaria menos trocas como economia equivalente de treinamento. [Paper, §§2–4](https://arxiv.org/html/2607.28577).

**SSRN:** não consegui o texto integral. Encontrei uma alternativa legítima concreta: pedir a **revisão de maio/2026** a `daniel@daru.finance`, publicado na [página de contato](https://daru.finance/contact). Não enviei mensagem. A página do [ResearchGate](https://www.researchgate.net/publication/404170098_Predictive_Value_of_Within-Strategy_Permutation_Tests_for_Forward_Selection_Evidence_from_Over_6_Billion_Strategy-Level_Permutations_Across_Three_Asset_Classes) não disponibiliza arquivo e conserva o resumo com efeito negativo que a [revisão no site do autor](https://daru.finance/research) reatribui a artefato numérico. Não a usaria como confirmação da versão revisada.

**CONCORDO COM**

- Não transferir a elasticidade de Hyperliquid para nossas ordens imediatas.
- Construir capacidade com dados próprios, dos dois lados e ao longo do tempo.
- Manter R$394/dia como **cenário de +1R em toda aposta**, não teto estrutural.
- Registrar H-P22 como hipótese de governança experimental, sem promessa de edge.

**OBSIDIAN**

- **Plantão de mercado — 2026-09-11:** acrescentar os 16 ciclos consecutivos de SOPH, corrigir 69h e separar evidência consultada de cenário.
- **Hipóteses do plantão:** extensão pontual da D-P15; H-P22 com versão vigente, avaliação posterior e não inferioridade.
- **KB-0070 — A tabela de capacidade:** distinguir fotografia do livro, capacidade sequencial e fills realizados.
- **Revisões-Astra — run 9, faixa 1:** registrar prioridades, limites de transferência e caminho legítimo para solicitar Gatto.