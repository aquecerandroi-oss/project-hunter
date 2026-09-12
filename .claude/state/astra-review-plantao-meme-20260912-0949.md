**RESUMO**

Eu testaria primeiro **o item 2: cobertura e seguimento da coorte**, incorporando a lição de paginação do item 3. Depois validaria custos por execução; M-P28 ficaria como diagnóstico estrutural.

O primeiro entregável seria uma tabela por idade e célula: elegíveis, acompanhadas, eventos comprovados, perdas e horizonte ainda não maturado. Sem isso, uma diferença de “sobrevivência” pode ser apenas diferença de visibilidade no board. Esse problema já está reconhecido em [M-D5](/C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:121).

**M-P28 e o protocolo de censura precisam de revisão antes do congelamento.** Parecer como `quant-engineer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei suítes nem coleta on-chain. Conferi as fontes primárias e executei a aritmética em PowerShell com `Decimal`:

```text
tip_min_sol=0.000001
tip_min_pct_order=0.00200
fees_equal_notional_two_legs_sol=0.001250
```

**MUST-FIX**

1. **Corrigir o tip: erro de fator 1.000.**  
   O [rascunho:113](/C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0949-lane4.md:113) converte 1.000 lamports em 0,001 SOL. Correto: **0,000001 SOL = 0,002% de 0,05 SOL**. O mínimo tampouco garante inclusão. A documentação confirma os 1.000 lamports. [Jito](https://docs.jito.wtf/lowlatencytxnsend/)

   **Falha concreta:** descartar uma entrada por um custo mínimo mil vezes maior que o real. Os 0,00125 SOL de taxas são uma conta com **duas pernas de igual notional**, não o custo exato de qualquer ida e volta. Aplicar taxa ao valor efetivo de cada perna, incluindo faixa, impacto, taxas de rede e tip efetivamente atribuível. [Pump](https://pump.fun/docs/fees)

2. **M-P28: as classes atuais se sobrepõem e não comprovam bundle.**  
   A [linha M-P28:123](/C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:123) permite `create+buy` na mesma tx **e** outras seis tx no slot: o mint cabe em (i) e (iii). Duas a cinco tx com tip também não identificam uma submissão conjunta; uma tx pode conter múltiplas compras e carteiras.

   **Correção:** contar tx bem-sucedidas com operações definidas sobre o mint, entre criação e o evento escolhido de conclusão, inclusive. Classes exclusivas: **1 / 2–5 / >5 / indeterminado**. Guardar `create+buy`, tip e contiguidade como atributos separados. “Compatível com bundle” é aceitável; “bundle comprovado” exige evidência adicional. O limite documentado da Jito não fornece a implicação inversa. [Jito](https://docs.jito.wtf/lowlatencytxnsend/)

   **Falha concreta:** classificar compras independentes como coordenação e obter uma diferença de concentração criada pelo próprio classificador.

3. **M-P28: congelar população, evento e instante do desfecho.**  
   “Todas as graduadas com slot comprovado” é mais amplo que a subcélula “criação e conclusão no mesmo slot”. Exigir explicitamente essa igualdade, dentro da coorte original de criações; separar **conclusão da curva** de **migração para o pool**. Manter as demais graduadas no painel pai e publicar quantas ficaram sem prova.

   Para concentração, definir: identidade do criador, união de carteiras sem dupla contagem, denominador do supply, exclusões de contas técnicas e corte exato de tx/instrução. Saldo ao fim do slot não é necessariamente saldo na graduação. [M-P28:123](/C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:123)

   **Falha concreta:** o criador vende depois da conclusão, no mesmo slot; o saldo final faz parecer que ele já graduou desconcentrado. Se a reconstrução intratransação não for possível, declarar outro corte observável, sem chamá-lo de instante da graduação.

4. **M-P28: financiamento e persistência precisam de histórico anterior.**  
   Uma `getBlock` fornece o bloco, não o histórico de financiamento nem a persistência entre lançamentos. [Solana](https://solana.com/docs/rpc/http/getblock)

   Congelar janela histórica, regras de arestas, identificação de serviços e disponibilidade do enriquecimento. Para uso prospectivo, a coorte persistente deve ser identificada com lançamentos anteriores ao marco; a janela inteira serve apenas para análise retrospectiva explicitada. A proposta atual usa lançamentos da “mesma janela”. [M-P28:123](/C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:123)

   **Falhas concretas:** uma exchange financiadora une clientes independentes; lançamentos de amanhã revelam uma coorte que o Radar não conhecia hoje. Sem rótulos equivalentes aos usados por Szwajcok, não presumir que reproduzimos sua remoção de serviços. [Szwajcok, §3 e §5](https://arxiv.org/html/2609.10246v1)

5. **M-P28: declarar multiplicidade não a controla.**  
   M-P1 já compara velocidade e retenção; M-P28 acrescenta concentração, persistência e retenção por novas células. [M-P1:82](/C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:82), [M-P28:123](/C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:123)

   Minha proposta: adenda prospectiva com **um contraste primário**, concentração média de `(1–5 tx)` contra `>5 tx`, diferença mínima relevante congelada. Separações internas, persistência e preço ficam exploratórios. Se houver conclusões confirmatórias conjuntas com M-P1/M-P18v2, enumerar os testes e aplicar uma correção explícita, como Holm; não contar o mesmo contraste duas vezes.

   **Falha concreta:** escolher depois entre médias, medianas, células e horizontes o resultado favorável. “100 e 30 dias” e “2 de 3 janelas” não substituem potência nem controle de multiplicidade.

6. **M-P18b: inatividade não é automaticamente causa absorvente.**  
   O [protocolo:83](/C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0949-lane4.md:83) mistura eventos, estado terminal e censura. Um pool pode ficar inativo, voltar a negociar e depois esvaziar.

   Escolher entre **tempo até a primeira ocorrência** de esvaziamento/inatividade, com regra para simultaneidade, ou modelo de estados que permita retorno à atividade. Congelar X, cobertura necessária e definição operacional de esvaziamento; evitar o rótulo “rug” sem evidência do mecanismo. Aos 24 h, quem permanece sem evento é censurado administrativamente, não uma terceira causa.

   **Falha concreta:** uma pausa reversível impede contabilizar esvaziamento posterior, embora o relatório diga medir risco de esvaziamento em 24 h.

7. **M-P18b: Aalen–Johansen não corrige desaparecimento do coletor nem estima razão de preço.**  
   O artigo sustenta incidência acumulada sob riscos competitivos; não resolve nosso mecanismo de observação. Também é **sobrevivência sem evento + incidências** que soma 1, não necessariamente as incidências isoladas. [Beuscart](https://link.springer.com/article/10.1186/1471-2369-13-31)

   Seguir as migradas da coorte original fora do board. Perda definitiva: último instante com cobertura comprovada. Lacuna com evento posteriormente detectado: intervalo de ocorrência, sem inventar horário. Publicar sensibilidade previamente definida; ausência de trades sob coleta incompleta permanece desconhecida.

   Manter dois resultados separados: incidência de eventos e distribuição de `P24/P0` entre ativas com preços válidos, com denominador e cobertura. Essa segunda medida é condicional aos sobreviventes e **não demonstra vantagem econômica da célula**. [Protocolo:85](/C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0949-lane4.md:85)

   **Falha concreta:** uma célula perde 90% dos pools e os poucos sobreviventes valorizam; reportar apenas a razão condicional faz a pior célula parecer melhor.

**NICE-TO-HAVE**

- Cache de blocos por slot, com cobertura e falhas publicadas.
- Sensibilidade por dia e por financiador recorrente: muitos mints do mesmo operador não representam muitas evidências independentes.

**O QUE EU FARIA DIFERENTE**

Cortaria estas extrapolações:

- **“Ninguém publicou / únicas medições existentes”** → “não encontramos nas fontes consultadas”. Os próprios números continuam proxies por segundo. [Rascunho:33](/C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0949-lane4.md:33)
- **“Coordenado versus baleia resolvido”** → dois indicadores de associação. Uma baleia pode controlar várias carteiras persistentes.
- **“Sandwich não compensa contra 0,05 SOL”** → não demonstrado. Tip médio histórico por ataque não é custo marginal mínimo de atacar essa ordem. Cortaria também “custo dominante” sem decomposição observada. [Rascunho:124](/C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0949-lane4.md:124)
- **“Silent Killer é ausência de associação”** → falhou a direção proposta: silêncio foi menos frequente nos casos, com diferença estatística na amostra. Isso não valida filtro inverso nem previsão prospectiva. São **114 casos completos de 118**, com controles selecionados por sobrevivência de 30 dias. [Zenodo](https://zenodo.org/records/22116163)
- **“+16,1% é edge”** → associação ajustada de compradores; não retorno executável nem prova causal suficiente. [Kamat v3](https://arxiv.org/abs/2607.02795v3)

**CONCORDO COM**

Preservar M-P28 como painel; distinguir segundo, slot e bundle; separar erro de coleta de ausência válida; medir taxas por execução; exigir retorno líquido sobre controle antes de promover qualquer regra.

**OBSIDIAN**

- **Hipóteses do plantão** — adenda de M-P28 com classes exclusivas, cortes temporais, contraste e multiplicidade; separar os estimandos de M-P18b.
- **Meme — 2026-09-12, Run 8** — corrigir tip em fator 1.000 e restringir afirmações sobre exclusividade, coordenação, sandwich e Silent Killer.
- **Meme Coin Factories / taxas-base e denominadores (KB-0091)** — registrar limites de identificação por financiamento e necessidade de histórico anterior.
- **Revisões Astra — plantão MEME run 8** — registrar prioridade de cobertura e os sete bloqueios deste parecer.