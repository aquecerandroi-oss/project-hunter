**RESUMO**

**Testaria primeiro M-P29, depois M-P30. Fomo/BAM entram como contexto monitorado.** M-P29 pergunta algo disponível na criação e diretamente ligado ao funil: um símbolo repetido com referência previamente observada no board acrescenta informação sobre conclusão da curva? M-P30 só fica disponível depois da migração e da janela de observação.

Isso **não valida o exemplo Frontier**: ele é motivação exploratória. O snapshot posterior não demonstra exposição anterior, e os dois tokens Solana apresentados são StonkFun, fora da população `pg=pump` atualmente definida em [M-P29](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:124).

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, papel `quant-engineer`.

**TESTES**

Não executei testes de software. Fiz leitura dos arquivos e conferência dos JSONs com `ConvertFrom-Json`:

- Comparação de `totalDataChart`: **Fomo > pump nos oito dias**, com `fomo_gt_pump=True` em cada data.
- Diferença entre as idades reportadas de FRONTIER e Frontier: **941 − 815 = 126 segundos**.
- Consultei as fontes primárias do DEX Screener e BAM. A tentativa de delegar a conferência falhou por indisponibilidade da ferramenta; fiz a verificação diretamente.

**MUST-FIX**

1. **Trocar “driver datado” por “referência temática datada”.**

   A carta existe, o site apresenta julho de 2026 e 1.386 signatários; a publicação de 29/07 relata lançamento no dia anterior e 1.224 assinaturas. Isso sustenta a cronologia da carta, **não a origem comprovada dos tokens nem o gatilho de hoje**. [Carta](https://www.pacingthefrontier.com/), [publicação de 29/07](https://thezvi.substack.com/p/frontier-lab-employee-open-letter).

   **Cenário de falha:** o Radar transforma uma coincidência temática identificada depois da alta em notícia que supostamente antecipou a alta. Corrigir também “pai canônico” para “candidato a referência, mais antigo entre os observados”. O salto aparece no [rascunho](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1116-lane2.md:17).

2. **M-P29: separar intervalo de criação, exposição no board e identificação do pai.**

   Os horários foram **inferidos de `serverTs − age`**, não validados on-chain. A redação honesta é: “intervalo estimado de 126 s entre criações reportadas dos dois tokens observados”. Não “tempo até o primeiro clone Solana”: o top-20 não cobre todas as criações. [Método e tabela](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1116-lane2.md:35).

   **É observável entre chains, prospectivamente**, com:

   - Identidade composta por chain e endereço; regra versionada para candidatos, empates e campos indisponíveis.
   - Snapshot recebido antes da criação do filho, com validade máxima e cobertura registradas.
   - Relógios distintos para criação validada e primeira recepção própria no board.
   - Descoberta dos filhos fora do ranking; sem cobertura suficiente, escrever “primeiro observado”.

   **Cenário de falha:** usar os US$ 3,93 milhões vistos às 11:17 para caracterizar o pai às 11:04. Hoje, `parent_on_board_at_create` é **desconhecido**, inclusive para NTDA; ausência no snapshot posterior não autoriza `false`. [Afirmação sobre NTDA](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1116-lane2.md:68).

   Há duas incompatibilidades adicionais: **PTF não coincide com FRONTIER pela regra atual de símbolo**, e StonkFun não integra a coorte pump. Incluir similaridade de nomes ou ampliar a população exige versão prospectiva própria; aceitar apenas um pai externo não exige ampliar a população dos filhos. [Contrato de M-P29](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:124).

3. **M-P30: `token-profiles/latest` não comprova pagamento.**

   A referência oficial descreve perfis recentes; seu esquema não fornece recibo, valor ou pagador. Existe um endpoint específico, `/orders/v1/{chainId}/{tokenAddress}`, para consultar pedidos pagos, com tipo, status e `paymentTimestamp`. Eu usaria esse caminho para validar a semântica, preservando estados distintos e o instante em que recebemos a resposta. [API oficial](https://docs.dexscreener.com/api/reference).

   **Cenário de falha:** classificar todo perfil como compra de US$ 299 e atribuir intenção ao criador. O marketplace anuncia **preço a partir de US$ 299**, não comprova o desembolso daquela moeda nem quem pagou. [Produto oficial](https://marketplace.dexscreener.com/product/token-info).

   Separar `perfil_observado`, `pedido_pago_observado` e `boost_observado`. Tampouco converter `totalAmount` automaticamente em dólares ou boosts ativos: Golden Ticker exige **500 ativos**. [Boosting](https://docs.dexscreener.com/boosting).

4. **M-P30: fixar a decisão em +30 minutos e tornar explícito o que é predito.**

   Minha proposta: migração on-chain em `t0`; decisão comum em `L=t0+30 min`, somente se a migração já era conhecida em `L`; exposição congelada com informações recebidas até `L`; desfecho em `t0+24 h`. Pagamento conhecido previamente e sinal que apareceu durante a janela devem ser distinguíveis.

   **Cenário de falha:** uma moeda sobe durante 29 minutos, recebe boost e o replay usa esse boost para justificar entrada em `t0`. Chamar o teste de preditivo não elimina esse vazamento.

   **Seleção por intenção não invalida uma previsão**, mas também não demonstra informação incremental. Compararia o modelo-base com e sem o sinal, incluindo atividade, liquidez e trajetória de preço conhecidas até `L`. Caso contrário, o pagamento pode apenas repetir “já estava subindo”.

   A razão `mcap24h/mcap0` pode permanecer como desfecho descritivo, mas parte da trajetória já ocorreu quando decidimos. Para utilidade operacional, medir também resultado **depois de `L`**, com execução e custos próprios.

5. **M-P30: cobertura do poll não é cobertura do universo.**

   A documentação consultada não promete enumeração completa por `latest`. Polls pontuais sem erros podem perder registros entre chamadas. Além disso, o processamento do perfil pode levar até 12 horas: a janela de 30 minutos mede também rapidez de publicação e descoberta. [API](https://docs.dexscreener.com/api/reference), [prazo oficial](https://marketplace.dexscreener.com/product/token-info).

   **Cenário de falha:** moedas menos visíveis desaparecem do feed e entram no controle; o resultado passa a medir visibilidade do endpoint.

   Manter denominador independente de migradas; registrar consultas previstas/realizadas, falhas, lacunas, repetição e quantidade retornada; auditar uma amostra por token. Separar **não observado sob cobertura operacional** de **cobertura insuficiente**. Sem estimativa de completude, a hipótese é sobre **sinal detectado pelo protocolo**, não sobre todas as moedas que pagaram.

6. **M-P30: fechar a definição de market cap, perdas de seguimento e aprovação.**

   Fixar pool, preço de referência, supply, conversão USD e tolerância temporal. O próprio produto permite informar carteiras com supply bloqueado para ajustar o market cap exibido. [Enhanced Token Info](https://marketplace.dexscreener.com/product/token-info).

   **Cenário de falha:** a compra do produto muda o denominador de supply reportado e parece mudar retenção econômica. Outro: pools desaparecidos são excluídos e deixam apenas sobreviventes.

   Publicar elegíveis, avaliáveis e desconhecidos por braço, com limites de sensibilidade. **100 por braço e 30 dias são piso, não potência garantida.** Para uma diferença de 10 pp, dimensionar pela taxa-base e dependência; congelar multiplicidade e confirmação posterior. IC que exclui zero não comprova, sozinho, ganho mínimo de 10 pp.

7. **Fomo/BAM: retirar as conclusões que excedem as métricas.**

   **Fomo:** os oito comparativos estão corretos nos JSONs arquivados. Trocar “segundo venue maior no fluxo de swap de meme” por **“maior `dailyFees` reportado nessas duas séries”**. Não há ali medição de fluxo exclusivamente meme, usuários, volume nem migração de demanda. [Trecho a corrigir](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1116-lane2.md:177).

   **BAM:** o anúncio primário confirma 09/09 e mais de 34% do stake naquela publicação. Os 5–10 ms são vantagem p50 em testes iniciais contra os streams de shreds dos parceiros; **preconf não é finalidade nem garantia de inclusão**. [Anúncio oficial](https://bam.dev/blog/bam-preconfirmations-are-live/).

   **Cenário de falha:** descontar 10 ms da execução simulada de toda transação ou atribuir mudanças de tip ao BAM. Registrar evento e disponibilidade da informação é válido; o indicador antes/depois **não demonstra quebra estrutural nem torna os períodos comparáveis sozinho**. Com controles completos por dia, esse indicador diário também não identifica efeito independente.

**NICE-TO-HAVE**

- Na próxima versão de M-P25, incluir `frontier` com regras de contexto; evitar `pace/carta` isolados. A alteração vale para coortes futuras, conforme o [contrato do dicionário](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:119).
- Separar perfil, boost e ambos na análise secundária de M-P30, com multiplicidade declarada.
- Na latência entre chains, publicar incerteza dos timestamps. A implementação do board converte `age` em horário estimado e consolida observações por minuto; isso limita reconstruções finas. [boards.py](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/boards.py:64).

**O QUE EU FARIA DIFERENTE**

Começaria pelo **teste do instrumento de M-P29**: conseguimos demonstrar a referência previamente recebida para cada criação, sem preencher lacunas retrospectivamente? Depois mediria ganho incremental sobre M-P3/M-P25/M-P26.

M-P30 ficaria pré-registrada para decisão em +30 minutos, após validar pedidos e cobertura. Coletaria Fomo/BAM junto, sem tratá-los como sinais de seleção de moedas.

**CONCORDO COM**

O dado é: carta publicada, nomes e campos observados no board, diferenças de idades reportadas, produtos documentados, séries de fees e anúncio do BAM. O hype começa ao converter isso em **gatilho de alta, genealogia comprovada, compromisso do criador, fluxo de dinheiro ou vantagem executável**.

Concordo em não abrir outra linha para Frontier, manter a população condicional às migradas em M-P30 e declarar “não observado” e “não causal”. Essas escolhas são necessárias; os ajustes acima tornam o teste defensável.

**OBSIDIAN**

- **Hipóteses do plantão** — versionar M-P29/M-P25 e registrar M-P30 com decisão fixa, semântica validada e cobertura.
- **Plantão MEME — 2026-09-12** — anexar as correções de proveniência, horários estimados e limites das conclusões.
- **Terminal do pump.fun** — distinguir perfil, pedido pago, boost ativo, preço anunciado e pagador desconhecido.
- **KB-0093, proposta** — documentar o que os produtos e endpoints efetivamente medem.
- **Revisões Astra — plantão MEME run 10, proposta** — preservar prioridade e cenários de falha deste parecer.