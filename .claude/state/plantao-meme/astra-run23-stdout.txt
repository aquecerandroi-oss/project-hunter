## RESUMO

**Parecer: DONE_WITH_CONCERNS — papel `quant-engineer`, modo OPINIÃO.**

**Eu inverteria os dois primeiros: M-D17 → composição HR → M-P27.** A régua do desfecho precisa estar correta antes de avaliar ganho incremental de HR. A coleta temporal de HR e Jito pode começar em paralelo; essa ordem é de validação.

| Proposta | Destino recomendado |
|---|---|
| **M-D17** | Adenda de instrumento a **M-P18b/M-P39**, com dependência de M-D1/M-D2 e ligação a M-D3. Pode ter identificador próprio para acompanhamento, sem virar hipótese econômica independente. |
| **M-P46** | Por enquanto, **bloco de covariáveis e análise de sensibilidade** de M-P42/M-P39. “Ferramenta de lançamento identificada” ainda excede a evidência. |
| **M-P27** | Manter a linha existente; acrescentar os dois payloads e os requisitos de validade temporal. |

Há uma distinção importante: **M-P18b já define retenção pelo preço do pool após migração**. Substituí-la por mcap atual dividido pelo limiar teórico da curva mudaria o desfecho, não apenas corrigiria sua medição. [Hipóteses:113](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:113)

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

Revisei o rascunho, os agregados e brutos relevantes, a fila, KB-0096/0097 e os contratos do projeto.

## TESTES

Sem testes de software: revisão documental e conferência dos JSONs, somente leitura.

Recontagem com PowerShell (`Get-Content | ConvertFrom-Json`, filtros por `c`, `pg` e `hr`), saída real:

```text
RAW=150; SOLANA=149; PUMP_SOLANA=127
HR=True n=22 nonpump_suffix=13 desc_tool=3 kol=20 bundled=20
HR=False n=105 nonpump_suffix=20 desc_tool=1 kol=44 bundled=49
PUMP_QUOTE_NON_SOL=7; HR=4; NON_HR=3
```

A conferência por mint, com comparação ordinal, encontrou **150 mints distintos nos brutos**. A passagem para 149 ocorre pelo filtro de chain, não por duplicação.

## MUST-FIX

### 1. Corrigir a contabilidade 150 → 149 e 106 → 105

O excluído é **PFORGE**, `pg=pump`, HR false, sem `c=solana:mainnet`. Ele está nos brutos, mas fora da população Solana do agregado. Portanto:

- Universo: **150 entradas distintas; 149 com chain Solana identificada; 1 excluída por chain**.
- Dentro de pump/Solana: **22 HR + 105 não-HR**.
- Sufixo: **13/22 × 20/105 sem `pump`**; com sufixo, **9/22 × 85/105**.
- Descrição j7tracker: **3/22 × 1/105**.
- Recalcular também os demais números que usaram 106.

**Falha concreta:** misturar universos entre covariáveis altera os contrastes e atribui a perda de uma linha à paginação duplicada. [Bruto PFORGE:2370](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane23/10_boards_graduated_p1.json:2370), [rascunho:10](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1848-lane3.md:10), [rascunho:41](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1848-lane3.md:41).

### 2. Retirar o agregado “retenção 0,06” como medida validada

A proxy clássica foi aplicada às 127 pump-nativas, incluindo **sete com quote diferente de SOL: quatro HR e três controles**. `pg=pump` não comprova curva clássica SOL. Ap u já fornece um contraexemplo explícito no próprio rascunho. [Rascunho:43](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1848-lane3.md:43), [agregado:1412](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane23/_analysis.json:1412).

Separaria:

1. **Retenção pós-migração:** preço do pool em horizonte fixo ÷ referência inicial do mesmo pool, com orientação e quote congeladas.
2. **Múltiplo sobre limiar teórico de conclusão:** diagnóstico separado, condicionado à validação de reservas, supply, quote e versão por mint.

Mcap só substitui preço quando supply e convenção de capitalização são comparáveis. Em USD, é preciso também definir como entra a variação da quote.

**Falha concreta:** uma mudança no preço de PUMP ou parâmetros custom produz aparente perda/ganho do token. Excluir esses sete ainda não valida automaticamente os outros 120.

Também retirar “45–75 min coincide com a hora pós-graduação”: a janela pode começar antes ou depois do evento. A semelhança com o run 19 é **compatível com efeito de idade**, não demonstra que era “a mesma forma na mesma idade”. [Rascunho:57](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1848-lane3.md:57).

### 3. Separar fotografia atual, previsão e explicação causal em M-P46

Os dados sustentam **associação descritiva entre HR e marcadores atuais**. Não demonstram `kol_5m`, prioridade nos primeiros 60 segundos ou ferramenta identificada. As cinco HR foram lidas depois desses marcos. [Rascunho:18](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1848-lane3.md:18), [rascunho:40](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1848-lane3.md:40).

**Falha concreta:** uma moeda recebe atenção após graduar; o KOL acumulado entra retrospectivamente como preditor da graduação.

Regras necessárias:

- Aos 60 s, somente dados recebidos até 60 s; `kol_5m` pertence ao marco de cinco minutos.
- Para **graduação no slot da criação**, KOL/taxas posteriores são caracterização posterior, não controles prévios.
- KOL e taxas podem ser consequência de HR ou do sucesso. Ajustá-los muda a pergunta; não prova que “HR não importa”.
- Sufixo, descrição e post antigo são marcadores candidatos, copiáveis. Snowflake data o post, não a associação do post à moeda.
- Controlar dependência por clone/criador/financiador e verificar sobreposição entre braços.

Para M-P39, cabe comparar **base × base+HR**, nos mesmos mints e cortes temporais. “Sem ganho detectado” não equivale a “HR nada acrescenta”; isso exige margem e precisão suficientes. A fila já exige essa distinção. [Hipóteses:148](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:148)

### 4. Corrigir as conclusões sobre Rugcheck

“As duas com score 1 são as mais líquidas” é falso no próprio recorte: **IQD tem US$ 171.398 de liquidez e score 33**, associado a correlação de holders. [Bruto IQD:26](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane23/63_rugcheck_ctl_qLf3mz.json:26), [bruto IQD:70](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane23/63_rugcheck_ctl_qLf3mz.json:70).

Redação aceitável: **“Low Liquidity foi o risco mais frequente; o score não separou perfeitamente HR e controles.”**

Além disso:

- Ausência de menção nos relatórios consultados não prova que o serviço ignora HR.
- `detectedAt ≈ criação+1 s` não demonstra relatório disponível ao Radar nesse instante.

**Falha concreta:** tratar `detectedAt` como disponibilidade cria vantagem histórica fictícia. M-D3 já exige medir o primeiro relatório recebido pelo nosso relógio. [Hipóteses:112](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:112)

### 5. Corrigir a leitura de Jito e RPC

Retirar **“uma EMA não faz isso”**. Uma EMA pode cair assim conforme seu coeficiente e atualizações intermediárias. Dois pontos não identificam sua dinâmica.

Também trocar “dispersão intraminuto supera diferenças entre horas” por **“variação grande entre dois payloads separados por 62 s”**. Não há série suficiente para comparar variâncias.

Os payloads chegaram aproximadamente **64,7 s e 76,4 s depois de seus timestamps**. Isso importa tanto quanto a frequência do poller. [Payload A:14](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane23/50_jito_tip_floor_a.json:14), [payload B:14](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane23/50_jito_tip_floor_b.json:14)

**Falha concreta:** atribuir o segundo payload a uma decisão às 18:58 usa informação recebida somente às 18:59:04.

“Fee do programa pump” também precisa virar **“amostras RPC com o endereço informado como filtro de contas graváveis”**. O método não agrega genericamente toda execução daquele programa. [Documentação Solana](https://solana.com/docs/rpc/http/getrecentprioritizationfees)

### 6. Manter Lab e IQD como diagnóstico, sem capacidade explicativa presumida

**Lab:** dois mints escolhidos pelo resultado; os quatro conjuntos sobre LBN não são quatro observações independentes. O saldo atual de 3,53% não comprova que seja o resíduo daquela venda: pode haver movimentos posteriores. Fotografias atuais não explicam as entradas de ontem. [Rascunho:78](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1848-lane3.md:78)

**IQD:** `holders_per_tx` merece painel de anomalia, mas **não separa transferência de trade por si só**. Exige definição de holder, janela e cobertura das transações, fonte sincronizada e tratamento de denominador zero. Transferências/airdrops precisam de evidência on-chain. [Rascunho:93](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1848-lane3.md:93)

**Falha concreta:** comparar holders acumulados com trades de uma janela parcial gera uma “assinatura de airdrop” artificial.

## NICE-TO-HAVE

- Publicar cobertura por horizonte e motivo: imaturo, coleta perdida, pool sem saída e preço válido; nunca converter ausência em zero ou carregar preço antigo silenciosamente.
- Manter os runs 21 e 23 como observações sobrepostas, com interseção por mint explícita.
- Nas células sem sobreposição de quote/campanha, declarar **“contraste não identificável nesta amostra”**.

## O QUE EU FARIA DIFERENTE

**Primeiro teste: contrato de M-D17, preservando M-P18b.**

1. **Contrato:** separar conclusão da curva e migração; congelar pool, quote, referência, horizontes e tolerância de defasagem. Manter 24 h como desfecho existente; 5/15/60 min como diagnósticos secundários.
2. **Replay:** reconstruir somente onde há trajetória suficiente; incluir custom quote, troca de pool, resposta tardia e ausência de trade. Sem histórico, marcar não reconstruível.
3. **Estresse:** variar atraso, cobertura, referência inicial e seleção de pool; verificar se o resultado depende dessas escolhas.
4. **Prospectivo:** acompanhar a coorte desde criação; retenção é condicional às migrações validadas, com não migradas contabilizadas separadamente.

Depois, testaria composição HR em período posterior, congelando covariáveis e comparação incremental. **M-P46 só ganharia autonomia com pergunta distinta e verificável sobre ferramenta**, por exemplo uma classificação validada por evidência independente, não apenas pelos mesmos marcadores usados para sugeri-la.

## CONCORDO COM

- Proibir `priceChange.h1` como substituto de “retorno uma hora após migrar”.
- Preservar HR como observação temporal por fonte.
- Investigar composição antes de interpretar contrastes brutos.
- Coletar Jito com `source_time`, `received_at`, validade máxima e deduplicação — requisitos já presentes em M-P27. [Hipóteses:124](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:124)
- Não abrir nova KB apenas para repetir os achados desta noite.

## OBSIDIAN

- **Hipóteses do plantão** — incorporar M-D17 como adenda de medição; anexar as covariáveis candidatas a M-P42/M-P39 e corrigir a interpretação de M-P27.
- **Plantão MEME — 2026-09-15** — registrar os denominadores corrigidos, a contaminação da proxy por custom quotes e os limites das conclusões.
- **KB-0096 / KB-0097** — acrescentar observação datada do run 23, preservando sobreposição, temporalidade de HR e ausência de mecanismo comprovado.
- **Revisões Astra — plantão MEME run 23** — registrar este parecer e quais correções o orquestrador incorporou.