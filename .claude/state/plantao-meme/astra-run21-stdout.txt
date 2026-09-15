## RESUMO

**Parecer como quant-engineer: DONE_WITH_CONCERNS.** Eu priorizaria **o contrato temporal proposto em M-D15 → coleta de M-P34 → teste exploratório de M-P42**.

Minha decisão editorial:

| Proposta | Destino |
|---|---|
| **M-D15** | **Adenda temporal a M-D13/M-D9**: o diagnóstico já exige observações por fonte, atraso e proibição de preencher retrospectivamente a exposição. |
| **M-P42** | **Subanálise de M-P18v2**, cruzando HR com as estruturas de M-P28. Ainda não merece linha autônoma de mecanismo. |
| **KB-0097** | **Adendo datado à KB-0096**: novos positivos e descrições ampliam o mesmo contrato observado. |

M-D13 já contém boa parte de M-D15; M-P18v2 já define todas as criações, slots comprovados e censura. [Fila:113](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:113), [Fila:147](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:147).

## ARQUIVOS

Nenhum criado ou modificado. Rascunho lido integralmente; conferidos memória, agregados e brutos relevantes.

## TESTES

Sem testes de software ou novas chamadas públicas. Conferência somente de leitura, com JavaScript executado por `node` sobre os JSON:

```text
GROUP true n 23 proxy 0 cells [ 0, 5, 11, 7, 0 ]
GROUP false n 103 proxy 63 cells [ 63, 10, 7, 17, 6 ]
UNIQUE 149 PUMP 126
LOG 28 28
```

`LOG` representa 28 chamadas registradas, todas com HTTP 200. A leitura inicial do agregado com `ConvertFrom-Json` falhou; a leitura com `JSON.parse` funcionou.

## MUST-FIX

1. **Atualizar a pendência on-chain.** “Não lido nesta run” continua correto; “continua não lido pelo projeto” ficou desatualizado. A KB-0096 já registra o byte confirmado em uma HR e um controle pela T4.8c, mantendo pendente a validação prospectiva das fontes. **Falha:** repetir trabalho e interpretar novidade da REST como nascimento do estado on-chain. [KB-0096:73](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0096-pump-fun-is-holder-reward-na-rest-e-o-segundo-deploy-de-15-09-2026.md:73).

2. **Trocar “conversão comprovada” por “HR observada em moedas antigas; conversão compatível”.** fone/baton não trazem estado anterior `false`, transação de conversão nem semântica validada do board para moedas migradas. **Falha:** uma mudança de classificação do indexer virar evento econômico fictício. Registrar `first_seen_true` por fonte; transição observada não é instante comprovado de conversão. [Rascunho:126](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1725-lane1.md:126).

3. **Separar exposição na criação de exposição aos 60 segundos.** Uma moeda pode concluir no slot da criação e converter aos 40 segundos: será HR em L, embora tenha nascido não-HR. **Falha:** declarar refutado um mecanismo de criação usando tratamento posterior ao desfecho. M-P34 preserva seu marco original; M-P39/M-P41 preservam seus próprios marcos. [Fila:134](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:134), [Rascunho:167](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1725-lane1.md:167).

4. **Manter “proxy temporal”, sem “HR exclui bundles”.** Mesmo segundo não comprova mesmo slot; mesmo slot não comprova bundle. Além disso, `0/23` não demonstra probabilidade aproximadamente zero: sob uma hipótese binomial independente, o limite superior unilateral de 95% é **12,2%** — apenas ilustração, sem corrigir seleção e dependência. **Falha:** promover ausência numa amostra condicionada a impossibilidade estrutural. [Rascunho:43](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1725-lane1.md:43).

5. **Retirar ATH > US$ 1 milhão da previsão principal.** Ausência de graduação imediata não implica ausência de valorização posterior. Fixar horizonte, cobertura e origem da cotação; não alternar “todas as criações” com “HR graduadas”. **Falha:** coorte jovem ou truncada parecer incapaz de atingir o limiar. [Rascunho:169](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1725-lane1.md:169).

6. **Reescrever “HR gradua melhor” e “é composição”.** O board não fornece a probabilidade de graduação por criação; as células mostram influência da composição, sem demonstrar que ela explica tudo. **Falha:** inferir vantagem de graduação selecionando somente graduadas, ou descartar diferenças residuais sem estimá-las. Há inclusive `kol > 0` de 10/11 contra 2/7 numa célula pequena. [Rascunho:120](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1725-lane1.md:120).

7. **Especificar quais superfícies concordam nos mesmos mints.** POO/Giveback têm concordância em lista, detalhe, imc, página **e board `new`**. Os 90/90 de `graduated` pertencem a outra interseção; esses dois mints não estão nela. **Falha:** montar validação conjunta juntando amostras diferentes. “Quatro fontes” é aceitável como quatro superfícies do operador, nunca quatro confirmações independentes. [Rascunho:111](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1725-lane1.md:111).

8. **Restringir a conclusão de fee/curva ao observado.** Dez objetos `Coin` sem campos de fee e duas reservas iguais não demonstram que HR nunca altera a dinâmica, nem que nenhuma outra rota expõe taxas. **Falha:** inferir custo idêntico apenas da igualdade do estado inicial. Escrever “campos de reservas comparados iguais; bps de HR não encontrados nos detalhes consultados”. [Rascunho:96](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1725-lane1.md:96).

## NICE-TO-HAVE

- **“IGNORE = spam”**: sobre-interpretação de intenção. O observado é uma rajada de 23 criações por um endereço; manter como covariável, sem exclusão automática.
- **“O contador não funciona”**: não demonstrado. `remaining=59` constante descreve estas chamadas; escopo do bucket e reposição continuam desconhecidos.
- **“HR deixou de ser raro”**: prefiro “há positivos suficientes para começar a coleta estratificada”. As listas sobrepostas e campanhas concentradas não estabelecem crescimento da taxa-base.

Esses limites correspondem aos recortes descritos no [rascunho:113](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1725-lane1.md:113), [150](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1725-lane1.md:150) e [157](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1725-lane1.md:157).

## O QUE EU FARIA DIFERENTE

Aplicaria o funil assim:

1. **Contrato:** observações imutáveis por mint/fonte, valor, `received_at`, tempo/slot da fonte e versão aplicável. Estado em L derivado somente do recebido até L; ausência, conflito e erro explícitos.
2. **Replay:** provar que uma resposta tardia ou conversão posterior não altera a exposição anteriormente congelada. Sem histórico suficiente, declarar não reconstruível.
3. **Estresse:** atrasos diferentes para HR/não-HR, desaparecimento de moedas rápidas, paginação viva, mudanças de versão e falta de sobreposição por quote/criador/clone.
4. **Prospectivo:** avaliar M-P34 com horizontes maduros; acrescentar HR às células de M-P18v2/M-P28. Para mecanismo de criação, exigir estado na instrução relevante e slots comprovados.

**A coleta bruta de M-P34 começa junto com a validação do contrato**, para preservar observações que depois serão irrecuperáveis. M-P42 fica exploratória; “≈ 0” exige margem quantitativa previamente definida.

## CONCORDO COM

O rótulo **“Rewards → holders” foi efetivamente encontrado nos extratos das duas páginas**, sem percentual no trecho observado. Isso fecha uma lacuna documental. Também concordo com preservar HR como observação temporal, manter conversões separadas quando identificáveis e usar todas as criações como denominador.

Publicaria esses fatos como **adendo da KB-0096**, incluindo `0/23` apenas como descrição do board e vinculando os protocolos existentes.

## OBSIDIAN

- **KB-0096 — is-holder-reward na REST e segundo deploy:** acrescentar rótulos observados, HR em moedas antigas e células descritivas, reconciliando a T4.8c.
- **Hipóteses do plantão:** ampliar M-D13 temporalmente e acrescentar a subanálise HR em M-P18v2/M-P28, preservando os marcos existentes.
- **Plantão MEME — 2026-09-15:** registrar a run 21 com as correções de causalidade, denominadores e concordância por mint.
- **Revisões Astra — run 21:** registrar este parecer e a ordem contrato → coleta de M-P34 → avaliação exploratória das células.