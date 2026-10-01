**RESUMO**

O lint está limpo, mas a base tem contradições de estado e índices incompletos. O problema recorrente é: a avaliação nova foi acrescentada, porém o resumo, o frontmatter e o índice continuam descrevendo a abertura.

Abaixo estão **12 achados**, com correções propostas por acréscimo. Nenhuma delas implica alterar protocolos ou avaliações congeladas.

**ARQUIVOS**

Nenhum arquivo criado ou modificado por mim. Nenhum commit. Não consultei produção nem li `.env`.

**TESTES**

Comando executado:

```text
uv run --no-sync python infra/scripts/obsidian_lint.py

LINT DA BASE OBSIDIAN — 509 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0, Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0, Reescrita de experimentos (append-only): 0.

RESULTADO: base limpa
```

Exit code: `0`. Isso comprova integridade estrutural; as contradições abaixo passaram pelo lint.

**MUST-FIX**

**1. KB-0165: proteção da carteira descrita como inerte**

- **Erro:** [KB-0165:129](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0165-staking-do-sol-parado.md:129) e a correção histórica na linha 210 dizem que nenhuma entrada alimenta `unrecognized`. A abertura, na linha 29, também apresenta saldo e ausência de posições como “hoje”.
- **Prova:** os três caminhos agora passam `holdings.unrecognized`: [entries.py:184](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/entries.py:184), [launch_entries.py:217](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/launch_entries.py:217) e [spot_entries.py:211](/C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entries.py:211). O [Diário 30/09:20](/C:/dev/project-hunter/obsidian/09-OPERATIONS/Diario/2026-09-30.md:20) registra a checagem no ar; a [decisão, linha 31](/C:/dev/project-hunter/obsidian/06-DECISIONS/2026-09-28-excecao-auditada-token-golpe.md:31) registra posição UNI preservada naquele corte.
- **Falha possível:** avaliar a introdução de outro ativo supondo que ele não bloquearia entradas ou que todo saldo estivesse ocioso.
- **Append proposto:**

> Atualização operacional — 30/09/2026: a descrição de proteção inerte foi superada. Os três caminhos de entrada alimentam a checagem, implantada em `a72296a0`, com estado válido na leitura registrada. “Sem posições” e o saldo inicial pertencem ao corte histórico citado; houve posição UNI da `spot/1` em 30/09. Esta nota não constitui leitura atual da carteira.

**2. HOME apresenta um estado operacional antigo como porta de entrada atual**

- **Erro:** [HOME:18](/C:/dev/project-hunter/obsidian/00-HOME.md:18) abre “Onde estamos agora” com 08/09; a linha 31 anuncia quatro furos de replicação abertos; a linha 169 chama a revisão de 08/09 de “mais recente”.
- **Prova:** [Open Bugs:536](</C:/dev/project-hunter/obsidian/07-BUGS/Open Bugs.md:536>) registra os quatro fechados; o [índice de revisões:91](/C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/Index.md:91) contém revisões de 27–28/09; o [Diário 30/09:33](/C:/dev/project-hunter/obsidian/09-OPERATIONS/Diario/2026-09-30.md:33) distingue mesa meme pausada e operações spot.
- **Falha possível:** priorizar bloqueios resolvidos e interpretar paper, memes e spot como uma única operação parada.
- **Append proposto:**

> Estado que substitui o resumo de 07–08/09: consultar [[Diario/2026-09-30]]. A mesa meme real segue pausada; a `spot/1` registrou operações. Os quatro defeitos de replicação T3.18c estão fechados. Pesquisa vigente: [[Fila de Hipoteses]], [[KB-0149-o-que-a-mesa-real-ensinou]] e [[Revisoes-Astra/Index]]. Os números anteriores são históricos.

**3. Open Bugs: token-golpe encerrado, mas ainda apresentado como bloqueio aguardando Everton**

- **Erro:** [Open Bugs:17](</C:/dev/project-hunter/obsidian/07-BUGS/Open Bugs.md:17>) mantém “bloqueia o deploy”; linha 20 mantém “decisão pendente”.
- **Prova:** a **própria linha 21** registra resolução em 30/09; a [decisão:16](/C:/dev/project-hunter/obsidian/06-DECISIONS/2026-09-28-excecao-auditada-token-golpe.md:16) já documenta a escolha de Everton.
- **Falha possível:** bloquear novo deploy ou pedir novamente uma decisão tomada.
- **Append proposto:**

> Encerramento: este incidente não integra a fila aberta. Everton decidiu pela exceção auditada em 28/09; em 30/09 a conta já havia sido fechada por terceiro, dispensando o cadastro. Checagem implantada e válida. Preservam-se acima o diagnóstico e a decisão originais.

**4. Open Bugs: reinício por `trailing_arm_x=1.0` ainda pede intervenção antiga**

- **Erro:** [Open Bugs:132](</C:/dev/project-hunter/obsidian/07-BUGS/Open Bugs.md:132>) mantém deploy pendente; linhas 136–143 oferecem correção manual do dado.
- **Prova:** [KB-0140:39](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0140-set-param-valida-antes-de-gravar.md:39) registra que o incidente terminou após aproximadamente 3,5 horas com T4.65. A normalização existe em [lab_params.py:61](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_params.py:61).
- **Falha possível:** executar uma correção manual desnecessária numa aposta histórica.
- **Append proposto:**

> O incidente específico de `trailing_arm_x=1.0` foi resolvido pela T4.65, conforme KB-0140. Os comandos anteriores são histórico de recuperação, não ação pendente. A dívida de isolamento T4.65b é separada e não recebe encerramento por esta evidência.

**5. Open Bugs: emergência de disco mistura fatos superados com pendências reais**

- **Erro:** [Open Bugs:148](</C:/dev/project-hunter/obsidian/07-BUGS/Open Bugs.md:148>) mantém 88%; linhas 180–191 ainda tratam retenção e redução de dados como decisões não tomadas.
- **Prova:** a [decisão de retenção:13](/C:/dev/project-hunter/obsidian/06-DECISIONS/2026-09-27-retencao-de-dados-e-backup.md:13) documenta autorização; linhas 41–43 registram execução parcial. O [Diário 30/09:33](/C:/dev/project-hunter/obsidian/09-OPERATIONS/Diario/2026-09-30.md:33) registra 41%.
- **Falha possível:** repetir ações destrutivas já executadas ou, no extremo oposto, considerar toda a prevenção resolvida.
- **Append proposto:**

> Atualização: o alerta de 88% é histórico; a leitura registrada em 30/09 foi 41%. A política foi aprovada em 27/09, e o truncamento do histórico e a poda manual da outbox foram executados em 28/09. Instalação dos crons e compactação permanecem sem comprovação posterior de conclusão nesta auditoria. Não repetir os comandos executados.

**6. EXP-0020: “replay pendente” apesar de avaliação concluída**

- **Erro:** [EXP-0020:4](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0020-regime-gate.md:4) mantém variantes não derivadas, zero avaliações e `last_eval: —`; o [índice:264](</C:/dev/project-hunter/obsidian/05-EXPERIMENTS/Experiments Index.md:264>) repete isso.
- **Prova:** [adendo:140](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0020-regime-gate.md:140) registra os dois braços executados; linhas 189–195 trazem os vereditos.
- **Falha possível:** repetir a corrida ou confundir o G2 executado com o G2 pré-registrado.
- **Append proposto:**

> Retificação do resumo: houve avaliação em 09/09, T3.52d. G1 terminou inconclusivo por população; G2 mostrou fragilidade a custos, sem promoção. O G2 executado utilizou dois rótulos de regime e não corresponde exatamente ao braço pré-registrado. “Replay pendente” descreve apenas o estado anterior ao adendo.

**7. EXP-0008: experimento “em andamento” com ambas as coortes aposentadas**

- **Erro:** [EXP-0008:4](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0008-breakout-compressao-de-volatilidade.md:4); o [índice:248](</C:/dev/project-hunter/obsidian/05-EXPERIMENTS/Experiments Index.md:248>) ainda diz aposentadoria não executada.
- **Prova:** [avaliação:474](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0008-breakout-compressao-de-volatilidade.md:474) registra as duas aposentadorias auditadas.
- **Falha possível:** esperar novas observações de versões retiradas.
- **Append proposto:**

> Estado consolidado: ambas as coortes foram encerradas em 08/09, às 19:35:34Z e 19:35:36Z. Resultado permanece inconclusivo por insuficiência de população; encerramento das parametrizações não refuta toda a hipótese de compressão.

**8. EXP-M1/M3: pré-registros apresentados como se ainda não tivessem rodado**

- **Erro:** [EXP-M1:4](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M1-comprar-cedo-na-curva.md:4) e [EXP-M3:4](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M3-sonda-de-hype.md:4) mantêm `pre-registrado`; o [índice:349](</C:/dev/project-hunter/obsidian/05-EXPERIMENTS/Experiments Index.md:349>) ainda apresenta M3 como `nao-iniciado`.
- **Prova:** [M1:221](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M1-comprar-cedo-na-curva.md:221) e [M3:160](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M3-sonda-de-hype.md:160) documentam avaliação e aposentadoria.
- **Falha possível:** repetir hipóteses descartadas ou interpretar descarte operacional como refutação estatística suficiente.
- **Append proposto, em cada página:**

> Este experimento foi executado e seu conjunto aposentado em 12/09. A decisão foi descartar o desenho; a população permaneceu insuficiente para conclusão estatística. O estado inicial de pré-registro não representa o ciclo atual.

**9. EXP-M2: “não iniciado” esconde uma execução sem propostas**

- **Erro:** [EXP-M2:4](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M2-a-linha-manda.md:4) mantém `pre-registrado`, `nao-iniciado` e avaliação vazia.
- **Prova:** [avaliação de 26/09:163](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M2-a-linha-manda.md:163) registra conjunto ativo entre 12 e 20/09 e reconstrói o funil.
- **Falha possível:** confundir ausência de propostas com ausência de operação ou refutação da linha.
- **Append proposto:**

> O conjunto operou entre 12/09 e 20/09, sem propostas. A avaliação de 26/09 encontrou limitação de instrumento; a hipótese da linha não foi julgada por desfechos. Resultado inconclusivo, não “não iniciado”. Continuação de pesquisa: EXP-M26.

**10. EXP-M4/M5/M10/M14: `nao-iniciado` contradiz observações registradas**

- **Erro:** frontmatter de [M4:9](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M4-moonshot.md:9), [M5:9](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M5-fluxo-e-holders.md:9), [M10:9](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M10-compradores-25.md:9) e [M14:9](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M14-razao-vendas-compras.md:9).
- **Prova:** [M4:179](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M4-moonshot.md:179) e [M5:178](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M5-fluxo-e-holders.md:178) contêm fechamentos; o [índice:448](</C:/dev/project-hunter/obsidian/05-EXPERIMENTS/Experiments Index.md:448>) registra M10 vivo e a linha 463 registra M14 com apostas fechadas.
- **Falha possível:** excluir experimentos já executados do acompanhamento e duplicar braços.
- **Append proposto:**

> Retificação: este experimento iniciou coleta e possui observações registradas; `nao-iniciado` é um resumo obsoleto. Não há aqui novo julgamento nem nova contagem. Para M4/M5, os números anteriores a 16/09 permanecem históricos e sujeitos à reclassificação Mayhem; não devem ser promovidos a contagem atual sem nova extração.

**11. Índice do EXP-M24 conserva o controle antigo e omite o julgamento R82**

- **Erro:** [Experiments Index:491](</C:/dev/project-hunter/obsidian/05-EXPERIMENTS/Experiments Index.md:491>) ainda descreve comparação com a sombra de `operator/5` e julgamento futuro.
- **Prova:** [EXP-M24:154](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M24-entrada-no-recuo.md:154) explica a substituição pelo EXP-M25; linhas 159–165 registram 151 pares e `NÃO CONFIRMA`.
- **Falha possível:** avaliar com o controle errado ou pedir novamente um julgamento concluído.
- **Append proposto no índice:**

> Atualização R82, 27/09: H-017 julgada como NÃO CONFIRMA, com 151 pares resolvidos. O controle utilizado foi [[EXP-M25-controle-do-recuo]], pois a sombra de `operator/5` não produziu pares nesta coorte. Ver avaliação acrescentada ao EXP-M24.

**12. Notas centrais existem, mas seus índices não as entregam**

- **Erro:** o catálogo de KB termina na [KB-0114, índice:149](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Index.md:149). A comparação dos nomes encontrou **55 das 169 KBs sem link nominal nesse índice**. O [índice de revisões:100](/C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/Index.md:100) não inclui T4.98; o índice de EXPs não contém link para EXP-M25. O [HOME:194](/C:/dev/project-hunter/obsidian/00-HOME.md:194) oferece mapas, mas não acesso direto à Fila nem à KB-0149.
- **Prova de importância:** [Fila:18](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:18>) ancora as regras na KB-0149; [T4.98:14](/C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/T4.98-fechamento-noturno.md:14) documenta o incidente do fechamento; EXP-M25 sustenta o julgamento citado acima.
- **Falha possível:** repetir pesquisas, ignorar controles e perder lições operacionais apesar de “zero órfãs”.
- **Append proposto:**

> HOME — Pesquisa e operação recentes: [[Fila de Hipoteses]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[03-TRADING/Meme/README]] · [[Diario/2026-09-30]].

> Índice de conhecimento — acrescentar catálogo KB-0115–KB-0169, com link e uma linha por nota.

> Índice de experimentos — [[EXP-M25-controle-do-recuo]]: controle de entrada imediata utilizado no R82/H-017.

> Índice de revisões — [[T4.98-fechamento-noturno]]: correção do fechamento e do denominador de capital incompleto.

**NICE-TO-HAVE**

- Acrescentar data de corte explícita aos resumos vivos; `updated` sozinho não resolve a mistura de histórico com presente.
- A T3.87 tem evidência de replay com a correção, mas **não considerei isso prova suficiente do deploy**.
- O fechamento noturno tem correção documentada, porém [Open Bugs:80](</C:/dev/project-hunter/obsidian/07-BUGS/Open Bugs.md:80>) mantém isolamento e recuperação pendentes: não fechar o incidente inteiro por inferência.

**O QUE EU FARIA DIFERENTE**

Manteria uma síntese corrente curta, apontando para os registros datados. Nos EXPs, acrescentaria a retificação sem alterar o histórico; depois reconciliaria os metadados usados pelas Bases em uma tarefa própria. **Append textual sozinho não corrige uma tabela dinâmica que lê frontmatter antigo.**

**CONCORDO COM**

Preservar avaliações, hipóteses e protocolos congelados; separar descarte operacional de refutação; exigir prova antes de declarar deploy ou recuperação concluídos.

**OBSIDIAN**

- **00-HOME** — acrescentar estado corrente e atalhos para pesquisa, operação e decisões recentes.
- **KB-0165 — Staking do SOL parado** — registrar a proteção implantada e delimitar os snapshots da carteira.
- **Open Bugs / Resolved Bugs** — consolidar encerramentos do token-golpe e T4.65; separar a emergência de disco das pendências restantes.
- **EXP-0020 e EXP-0008** — acrescentar estado consolidado conforme avaliações existentes.
- **EXP-M1/M2/M3/M4/M5/M10/M14** — corrigir por adendo a apresentação de ciclo ainda não iniciado.
- **Experiments Index** — refletir os adendos, o julgamento R82 e o controle EXP-M25.
- **Conhecimento — índice** — incorporar KB-0115–KB-0169.
- **Revisões da Astra — índice** — incluir T4.98.
- **Nova síntese desta auditoria** — registrar achados e links, sem converter esta revisão documental em nova avaliação experimental.