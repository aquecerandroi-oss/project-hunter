**RESUMO**

**REQUEST_CHANGES.** TypeScript e ESLint passaram, mas confirmei bugs de paginação, filtros e apresentação de dados. As quatro reconciliações anteriores estão apenas parcialmente resolvidas.

O parser acompanha a estrutura principal do Python, mas **não preserva exatamente sua semântica**. A edição cirúrgica do dashboard é aceitável como integração da entrega já pedida.

**ARQUIVOS**

Revisei os arquivos modificados e novos da T2.7, confrontando-os com os contratos Python/API. Não criei nem modifiquei arquivos e não fiz commit.

**TESTES**

Executados em `apps/web`:

| Comando | Resultado real |
|---|---|
| `npx.cmd tsc --noEmit` | código 0; saída vazia |
| `npx.cmd eslint .` | código 0; saída vazia |

O atalho `npx.ps1` foi bloqueado pela política do PowerShell; usei `npx.cmd`.

Também executei reproduções em memória, carregando o código real com React e dependências simuladas. Saída:

```text
race refresh then old loadMore: {"ids":["C","A","C","D"],"cursor":null}
next periodic refresh: {"ids":["C","A"],"cursor":"new-after-A"}
503 reconciliation: {"loadError":null,"asOf":"new"}
opportunities after HOT props: ["old-WATCHING"]
parser: {"recognized":true,"agreement":"0","contribution":"0","weight":"0","eligible":true}
invalid vector: {"recognized":true,"features":[],"source":"vector"}
```

Não executei a suíte Vitest; os 472 testes são o resultado informado por você.

**MUST-FIX**

1. **HIGH — A reconciliação quebra a paginação do Radar.**  
   `reconcile()` substitui toda a lista pela primeira página; `loadMore()` acrescenta sua resposta ao estado que existir quando terminar. Não há geração de consulta nem coordenação entre as duas operações. [useRadarPage.ts:50](C:/dev/project-hunter/apps/web/hooks/useRadarPage.ts:50), [useRadarPage.ts:75](C:/dev/project-hunter/apps/web/hooks/useRadarPage.ts:75).

   **Cenário:** primeira página `A,B`; segunda página pendente `C,D`; ranking atualizado retorna `C,A`. Resolvida a atualização antes da paginação, surge `C,A,C,D`, com cursor encerrado. Na atualização seguinte, desaparecem as páginas adicionais. Mesmo sem concorrência, navegar além da primeira página dura no máximo até a próxima reconciliação. Uma resposta anterior também pode sobrescrever resultados de filtros novos.

   **Correção:** descartar respostas de gerações antigas, coordenar paginação/reconciliação e preservar explicitamente a profundidade carregada. Deduplicar por `opportunity_id` ajuda, mas sozinho não resolve perda de linhas nem cursores incompatíveis.

2. **HIGH — Os filtros de `/opportunities` não atualizam as linhas já montadas.**  
   `items` e `cursor` recebem as props somente na inicialização. A página atualiza as props sem fornecer uma chave que reinicie o componente. [opportunities-table.tsx:43](C:/dev/project-hunter/apps/web/components/opportunities/opportunities-table.tsx:43), [page.tsx:85](C:/dev/project-hunter/apps/web/app/(app)/[orgSlug]/opportunities/page.tsx:85).

   **Cenário confirmado:** aplicar HOT recebe uma nova lista HOT, mas continua mostrando a linha WATCHING anterior. “Carregar mais” pode combinar filtros novos com cursor antigo. O `AutoRefresh` também não atualiza esse estado.

   **Correção:** sincronizar a lista por identidade da consulta, invalidando requisições anteriores e reiniciando o cursor quando os filtros mudarem.

3. **HIGH — A coluna de anomalias ainda pode afirmar ausência falsa e ficar congelada.**  
   O retorno antecipado “nenhuma” ignora `truncated`; a janela de 30 dias aparece no comentário, mas não na apresentação da coluna. [anomaly-count-cell.tsx:27](C:/dev/project-hunter/apps/web/components/radar/anomaly-count-cell.tsx:27).

   Além disso, o agregado é carregado pela página, perde seu próprio `as_of` e não participa da reconciliação do hook. [page.tsx:108](C:/dev/project-hunter/apps/web/app/(app)/[orgSlug]/radar/page.tsx:108), [useRadarPage.ts:54](C:/dev/project-hunter/apps/web/hooks/useRadarPage.ts:54).

   **Cenários:** a anomalia de um mercado está depois das primeiras 200 e a célula diz “nenhuma”; ou uma anomalia surge/resolve depois da abertura e a coluna permanece igual enquanto “Painel consultado” avança.

   **Correção:** mostrar janela e truncamento inclusive para mercados ausentes da página parcial; atualizar o agregado e conservar seu horário de consulta separado.

4. **MEDIUM — Falha de reconciliação fica silenciosa.**  
   O caminho `outcome.ok === false` não atualiza nenhum estado de erro; rejeições da chamada também não têm `catch` nesse método. [useRadarPage.ts:53](C:/dev/project-hunter/apps/web/hooks/useRadarPage.ts:53).

   **Cenário confirmado:** após uma carga válida, a API retorna 503 e `loadError` continua `null`. Se a lista anterior estava vazia, permanece uma afirmação de ausência sem indicação de que a verificação parou.

   **Correção:** manter os últimos dados, mas apresentar falha de atualização e última consulta bem-sucedida; limpar o erro após recuperação.

5. **MEDIUM — O parser não é fechado para formatos incompatíveis e altera um nulo legítimo.**  
   O Python distingue `agreement=None` de concordância zero; o parser converte ambos em `"0"`. [model.py:257](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/model.py:257), [decomposition-parse.ts:153](C:/dev/project-hunter/apps/web/components/opportunities/decomposition-parse.ts:153).

   Também aceita componentes incompletos e inventa peso/contribuição/confiança zero. Entradas inválidas do vetor são descartadas, produzindo uma tabela “reconhecida” vazia. [decomposition-parse.ts:75](C:/dev/project-hunter/apps/web/components/opportunities/decomposition-parse.ts:75), [decomposition-parse.ts:194](C:/dev/project-hunter/apps/web/components/opportunities/decomposition-parse.ts:194).

   **Cenário confirmado:** `{name:"momentum", available:true, normalized:"80"}` produz peso e contribuição `"0"`; um vetor com entrada escalar vira `features:[]`. Isso transforma incompatibilidade em informação aparentemente válida.

   **Correção:** preservar nulabilidade e validar os campos necessários à apresentação. Estrutura incompatível deve produzir fallback explícito, sem completar evidência com defaults numéricos.

6. **MEDIUM — O fallback prometido e parte da explicação não chegam ao usuário.**  
   A interface manda consultar “JSON bruto no rodapé técnico”, mas esse rodapé contém somente identificadores e versões. [why-components.tsx:63](C:/dev/project-hunter/apps/web/components/opportunities/why-components.tsx:63), [why-footer.tsx:10](C:/dev/project-hunter/apps/web/components/opportunities/why-footer.tsx:10).

   O resumo renderiza apenas `explanation.resumo`; as frases adicionais não são apresentadas. Assim, o aviso Python `estagio_divergente` desaparece. [why-summary.tsx:36](C:/dev/project-hunter/apps/web/components/opportunities/why-summary.tsx:36), [explanation.py:215](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/explanation.py:215).

   **Cenário:** um formato novo impede a leitura dos componentes e não existe o escape anunciado; numa avaliação com estágio e score em direções opostas, perde-se a advertência explícita do produtor.

   **Correção:** disponibilizar os objetos brutos da avaliação e apresentar as frases relevantes, além da direção/confiança por componente e `state_in/out` pedidos no brief.

7. **MEDIUM — Ordenar “Atualizado” ordena outro timestamp.**  
   O cabeçalho usa `sort=age`, que o backend implementa com `first_seen_at`; a célula mostra `last_updated_at`. [radar-table-head.tsx:23](C:/dev/project-hunter/apps/web/components/radar/radar-table-head.tsx:23), [radar.py:113](C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:113), [radar-row.tsx:81](C:/dev/project-hunter/apps/web/components/radar/radar-row.tsx:81).

   **Cenário:** episódio antigo atualizado agora aparece atrás de episódio recente desatualizado ao ordenar descendentemente “Atualizado”.

   **Correção:** alinhar rótulo, valor mostrado e chave de ordenação.

8. **MEDIUM — A timeline perde truncamento e não se renova.**  
   O estado guarda somente `items`, descartando `next_cursor` e os carimbos da consulta; a leitura depende apenas de mudança de `marketId`. [anomaly-timeline.tsx:37](C:/dev/project-hunter/apps/web/components/anomalies/anomaly-timeline.tsx:37), [anomaly-timeline.tsx:47](C:/dev/project-hunter/apps/web/components/anomalies/anomaly-timeline.tsx:47).

   **Cenário:** mais de 200 anomalias nas 24 horas aparecem como uma timeline sem indicação de corte. Mantendo o mercado aberto, uma anomalia resolvida continua apresentada como ativa.

   **Correção:** preservar os metadados da consulta, divulgar o corte e renovar a leitura ou identificar claramente o snapshot.

9. **HIGH — Pendência de integração já registrada: volatilidade e volume leem o caminho errado no backend.**  
   O envelope real grava `vector`; a expressão SQL lê `features`. [envelope.py:45](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/envelope.py:45), [radar_common.py:117](C:/dev/project-hunter/apps/api/hunter_api/repositories/radar_common.py:117).

   **Cenário:** persistido o envelope real, `volatility_min` elimina linhas que possuem ATR válido, porque a expressão resulta em `NULL`; a ordenação por volume também perde seus valores. [radar.py:194](C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:194), [radar.py:118](C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:118).

   Isso não nasceu no diff frontend, mas precisa ser resolvido pelo responsável da integração antes do aceite funcional. O fallback do parser não corrige SQL.

**NICE-TO-HAVE**

- Mostrar data junto da hora em históricos: amostras de dias diferentes podem aparecer com o mesmo horário, pois `formatUtc` só imprime hora. [why-history.tsx:88](C:/dev/project-hunter/apps/web/components/opportunities/why-history.tsx:88), [format.ts:151](C:/dev/project-hunter/apps/web/lib/format.ts:151).
- Tirar o detalhe interno sobre o publisher `rt:radar` da mensagem principal da tela. [radar-table.tsx:130](C:/dev/project-hunter/apps/web/components/radar/radar-table.tsx:130).

**O QUE EU FARIA DIFERENTE**

Usaria identidade explícita da consulta para controlar respostas assíncronas e paginação. Acrescentaria testes com promises resolvidas fora de ordem, troca de filtros e recuperação de 503.

Para o parser, usaria fixtures serializadas pelo produtor Python, incluindo nulos legítimos e envelopes completos, mais casos incompatíveis que comprovem o fallback.

**CONCORDO COM**

- **A exceção do dashboard é aceitável:** carregar e renderizar os três tiles concretiza uma entrega expressa do brief. O diff permanece nessa integração. Basta corrigir a lista documental de arquivos; não vejo motivo técnico para desfazer a alteração. [page.tsx:82](C:/dev/project-hunter/apps/web/app/(app)/[orgSlug]/dashboard/page.tsx:82), [page.tsx:119](C:/dev/project-hunter/apps/web/app/(app)/[orgSlug]/dashboard/page.tsx:119).
- A barra indisponível agora usa apresentação distinta e motivo, sem desenhar zero observado. [why-components.tsx:25](C:/dev/project-hunter/apps/web/components/opportunities/why-components.tsx:25).
- Não identifiquei nova aritmética monetária insegura nem vazamento de tenant neste diff. A API continua verificando a organização antes da derivação específica do tenant. [radar_common.py:79](C:/dev/project-hunter/apps/api/hunter_api/routers/radar_common.py:79). Não encontrei novo cálculo com look-ahead; os problemas encontrados são de apresentação, atualização e preservação da evidência.

**OBSIDIAN**

- **System Overview** — registrar T2.7 como revisada com correções pendentes, incluindo filtros e paginação.
- **WebSockets** — documentar coordenação entre invalidação, paginação e respostas antigas.
- **Features (Feature Engine)** — registrar contrato `vector.values`, nulabilidade e reconciliação com SQL.
- **Anomalies (Anomaly Engine)** — registrar janela, truncamento e horário próprio das consultas.
- **Revisoes-Astra/Index** — vincular esta revisão e suas reproduções.
- **Open Bugs** — acompanhar os achados até correção e validação.