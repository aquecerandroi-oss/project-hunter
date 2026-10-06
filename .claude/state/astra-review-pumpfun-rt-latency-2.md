**RESUMO**

**REQUEST_CHANGES no texto e em pontos restantes do instrumento. As tabelas principais de latência estão reproduzidas corretamente.**

Recalculei os dois relatórios em memória: ambos coincidem integralmente com os `report.json` salvos. A evidência sustenta **“NATS chegou antes, nesta máquina, nestas duas janelas, entre os pares observados”**. Não sustenta ausência universal de informação adicional, inexistência de reprise ou irrelevância operacional da vantagem.

Assumi `code-reviewer`, considerando a rodada 1 e a memória de KB-0183, KB-0185, KB-0149 e a decisão sobre acesso anônimo.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit, leitura de `.env` ou nova chamada aos provedores.

**TESTES**

Não executei pytest, ruff ou pyright; os **68 testes passando são informação fornecida**, não uma validação minha nesta rodada. Os testes de IO escrevem arquivos. Também não executei o leitor pela entrada principal, que sobrescreve `report.json` ([leitor:166](/C:/dev/project-hunter/infra/scripts/research/2026-10-06-pumpfun-realtime-latency-read.py:166)).

Executei diagnósticos somente em memória com `.\.venv\Scripts\python.exe -B -`, importando as funções puras. Saída real:

```text
run1 recomputed_report_equal True
balance_expected 415 actual_delivered_wallet_pairs 415
multi_wallet_signatures 0

run2 recomputed_report_equal True
balance_expected 1317 actual_delivered_wallet_pairs 1315
multi_wallet_signatures 0

synthetic_two_wallets {'expected': 2, 'delivered': 1, 'share': 0.5}
synthetic_late_counterpart {'common': 0, 'only_a': 1, 'only_b': 0, ...}
```

Conferência das tabelas e números associados:

| Item da nota | Resultado |
|---|---|
| Criações: seis linhas, pares, p10/p50/p90, primeiras chegadas e cobertura | **Todos coincidem** com [run1:18](/C:/dev/project-hunter/.claude/state/pumpfun-rt-latency/run1-report.md:18) e [run2:18](/C:/dev/project-hunter/.claude/state/pumpfun-rt-latency/run2-report.md:18). |
| Trades: RPC, lite, saldo×NATS e saldo×RPC, nas duas janelas | **Todos coincidem** com [run1:37](/C:/dev/project-hunter/.claude/state/pumpfun-rt-latency/run1-report.md:37) e [run2:37](/C:/dev/project-hunter/.claude/state/pumpfun-rt-latency/run2-report.md:37). |
| Saldo: 415/415 e 1.315/1.317 | **Confirmados também por assinatura+carteira**, apesar do bug descrito abaixo. |
| Graduação: 11/12 pares; medianas 0,425/0,499 s | **Corretos**, como descrição dos pares encontrados ([run1:69](/C:/dev/project-hunter/.claude/state/pumpfun-rt-latency/run1-report.md:69), [run2:69](/C:/dev/project-hunter/.claude/state/pumpfun-rt-latency/run2-report.md:69)). |
| Totais 1.680 criações e 13.680 transações pareadas; PumpSwap 747/4.275 frames | **Corretos**. |
| KOL: 676/1.134, 18/20, n=100/369 | Transcritos corretamente, mas **com interpretação errada de “moedas” e “nasciam”**. |
| Relógio, atraso do laço e saldo−timestamp do servidor | Arredondamentos compatíveis; separar os offsets de cada janela: **0,057/0,056 s**. |
| Distâncias TCP e localização AWS | **Não constam dos relatórios**. Precisam de referência à medição separada; não as validei nesta revisão. |

**MUST-FIX**

1. **HIGH — A conclusão sobre conteúdo da NATS excede radicalmente o inventário.**

   A afirmação “não carrega informação que a cadeia não tenha”, no título e nas linhas 30/69/71 da [nota](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0186-o-tempo-real-da-pumpfun-chega-100-ms-antes-mas-nao-traz-informacao-nova.md:26), não foi demonstrada.

   São quatro amostras por grupo, e o inventário utiliza **somente o primeiro JSON válido, apenas suas chaves superiores** ([report:190](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:190)). No run1, o grupo de trades nem separava processed/lite; o inventário exibido tem 12 chaves ([run1:80](/C:/dev/project-hunter/.claude/state/pumpfun-rt-latency/run1-report.md:80)).

   **Cenário:** uma rota diferente preenche `surfaceAttribution`, ou um campo aninhado traz enriquecimento não presente nas quatro amostras. A nota já terá descartado essa possibilidade. `solPriceUsd`, `is_banned`, metadados e atribuição também precisam de proveniência demonstrada; seus nomes não provam derivação exclusiva da cadeia.

   **Correção:** “Nas amostras examinadas, não identificamos campos explícitos de KOL/PnL/thesis. A equivalência informacional com a cadeia não foi demonstrada.” Os quatro conjuntos `null/null/null/default` foram confirmados, mas não permitem generalização.

2. **HIGH — “Não reprisou histórico” e “0% com folga 0/2/4 s” estão incorretos.**

   A [nota:59](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0186-o-tempo-real-da-pumpfun-chega-100-ms-antes-mas-nao-traz-informacao-nova.md:59) confunde estabilidade dos pares com estabilidade da classificação.

   Recontagem dos frames classificados:

   | Folga | Run1 | Run2 |
   |---|---:|---:|
   | 0 s | **90/3.951 = 2,28%** anteriores | **187/15.685 = 1,19%** anteriores |
   | 2 s | 0 | 0 |
   | 4 s | 0 | 0 |

   A sensibilidade publicada guarda somente `common` e p50, não a parcela anterior para cada folga ([trades:164](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_trades.py:164)).

   **Cenário:** eventos próximos da assinatura mudam de classe, mas estão fora da coorte interior; os pares permanecem iguais e o texto declara, indevidamente, ausência de histórico.

   **Correção:** publicar ambas as sensibilidades e escrever “nenhum frame classificado como anterior com folga de 2/4 s; classificação temporal não comprova reprise nem sua ausência”.

3. **MEDIUM — A população do KOL está descrita erradamente.**

   `_kol()` conta eventos `add`, incluindo readições, e conserva o último horário por mint ([report:114](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:114)). A [nota:63](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0186-o-tempo-real-da-pumpfun-chega-100-ms-antes-mas-nao-traz-informacao-nova.md:63) os chama de moedas que “nasciam”.

   Recontagem:

   | Medida | Run1 | Run2 |
   |---|---:|---:|
   | Eventos `add` | 676 | 1.134 |
   | Mints distintos nesses eventos | **587** | **1.111** |
   | Eventos `add` com KOL positivo | 18 | 20 |
   | Mints positivos na primeira adição observada nessa janela | **2** | **12** |

   **Cenário real:** uma moeda retorna ao board já com KOL e passa a contar como se tivesse nascido com KOL.

   As medianas **0,999/1,062 s**, com n=100/369, permanecem reproduzíveis; não encontrei efeito das readições nesses pares específicos. Mas medir `add→update positivo` não mede antecipação de preço nem prova cadência fixa de um segundo. Separar a observação desta sonda da conclusão econômica do KB-0142.

4. **MEDIUM — O saldo perde novamente a carteira depois do casamento.**

   `expected` preserva `(assinatura, carteira)`, mas `bal_c` usa somente a assinatura como chave ([trades:155](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_trades.py:155)).

   **Cenário reproduzido:** duas carteiras esperadas na mesma transação, ambas entregues. Resultado: **2 esperadas, 1 entregue, 50%**. O timestamp sobrevivente depende da carteira que sobrescreve o dicionário, não da primeira entrega.

   **Impacto atual:** nenhum nos totais publicados: não houve assinatura com duas carteiras esperadas nessas capturas. A correção, porém, ainda não está completa. Preservar a chave composta no numerador e definir explicitamente a unidade da distribuição de latência. Aqui, “entregue” também significa **alguma atualização de saldo da carteira**, não comprovação de todas as pernas SOL/token.

5. **MEDIUM — A contraparte NATS ainda não é procurada simetricamente na captura inteira.**

   `_core()` constrói `nats_all` depois de `_live()`, que limita a chegada ao intervalo mais cinco segundos ([trades:86](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_trades.py:86), [trades:103](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_trades.py:103)).

   **Cenário reproduzido:** exposição `[100,200]`, RPC chega em 196, NATS em 206, timestamp do evento 195. O RPC torna a transação elegível; embora a contraparte esteja gravada, o relatório devolve **RPC exclusivo**, sem par.

   Separar elegibilidade da coorte da busca de contraparte. Isso pode transformar atraso NATS em ausência e retirar sua cauda da distribuição. Não demonstrou alteração dos pares atuais, cuja cobertura RPC×NATS foi 100%.

   Há também fechamento incompleto de exposição: `BREAKS` não inclui `send_failed`, `crashed` nem recusas de subject registradas como `err`; o `sub` é gravado antes do envio ([trades:37](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_trades.py:37), [feeds:103](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_feeds.py:103)). **Cenário:** assinatura recusada continua contando como exposição saudável. Não encontrei esses eventos nos segmentos analisados.

6. **MEDIUM — Os rótulos precisam permanecer descritivos, e “empata” não está sustentado.**

   - **NATS processed antecipa RPC e PumpPortal:** sustentado nos pares destas janelas.
   - **Lite, saldo e board new atrasam em relação à processed:** sustentado nos pares.
   - **Graduação:** “board atrasou na mediana dos poucos pares” é adequado.
   - **PumpPortal×RPC na janela 1:** mediana favorável ao PumpPortal de 22 ms, **54,4% antes, 35,4% depois e 10,2% empatados**. Isso não estabelece equivalência; eu retiraria “empata” ([run1:20](/C:/dev/project-hunter/.claude/state/pumpfun-rt-latency/run1-report.md:20)).

   **Cenário de conclusão indevida:** “sozinha não muda nenhuma decisão” ou “0,1 s não cria edge” é usado para descartar uma hipótese sem medir decisão, execução ou resultado. Substituir por **“não demonstramos benefício operacional ou econômico”** ([nota:30](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0186-o-tempo-real-da-pumpfun-chega-100-ms-antes-mas-nao-traz-informacao-nova.md:30)).

   Corrigir também “perde 10–12%” para **“não observamos 10,3%/12,5% nesta captura”**. O PumpPortal ficou desconectado por **4,837 s** na janela 2; três criações ausentes ocorreram nesse intervalo ([events:28609](/C:/dev/project-hunter/.claude/state/pumpfun-rt-latency/run2/events.jsonl:28609), [events:28978](/C:/dev/project-hunter/.claude/state/pumpfun-rt-latency/run2/events.jsonl:28978)). “Sem parada” deve significar **sem suspensão da máquina**, não fontes ininterruptas.

**NICE-TO-HAVE**

- A tolerância implementada é **≤10 ms**, embora cabeçalhos digam `<10 ms` ([stats:80](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_stats.py:80)).
- A graduação ainda recorta cada fonte separadamente, diferentemente da coorte de criações; pares atravessando a borda podem desaparecer ([report:108](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:108)).
- Publicar saúde por fonte, perdas durante desconexão e exclusões de borda. O render usa lag/recusas do `meta` completo, mesmo quando analisa só um segmento ([leitor:63](/C:/dev/project-hunter/infra/scripts/research/2026-10-06-pumpfun-realtime-latency-read.py:63)).
- Retirar “up to about a second of error” da descrição do timestamp: resolução de um segundo não demonstra esse limite total de erro ([trades:40](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_trades.py:40)).
- Documentar separadamente a medição TCP e as chamadas diagnósticas. `n=0` confirma que a checagem de bloco não foi obtida; os relatórios não comprovam, sozinhos, cada resposta HTTP/JSON-RPC das 120 chamadas.

**O QUE EU FARIA DIFERENTE**

Sobre **credencial e qualquer carteira**: não trataria automaticamente uma credencial compartilhada, entregue ao navegador anônimo, como login pessoal ou contorno de autenticação. Entretanto, **o servidor aceitar um subject não demonstra que esse subject, para qualquer carteira, pertence ao acesso normal do visitante anônimo**.

Com a autorização documentada, eu teria parado **antes de ampliar para carteiras arbitrárias**, caso não houvesse evidência de que a interface anônima faz exatamente essa assinatura. A decisão mantém “só como visitante anônimo” e “parar no primeiro bloqueio” ([decisão:23](/C:/dev/project-hunter/obsidian/06-DECISIONS/2026-10-06-rea-na-pumpfun-apesar-dos-termos.md:23)); o roster ainda proíbe chaves/autenticação contornada ([batedor:36](/C:/dev/project-hunter/.claude/agents/batedor-rea.md:36)).

Eu apresentaria a evidência do fluxo anônimo e pediria esclarecimento do escopo se ela faltasse. **Vinte carteiras funcionaram** é uma observação técnica; **qualquer carteira está autorizada** não decorre dela. A aprovação de Everton define nosso escopo, não uma permissão concedida pelo provedor.

Quanto ao RPC, a distinção HTTP recusado/WS ainda entregando está correta. O erro descoberto depois não invalida retroativamente as chegadas WS; tampouco autoriza insistir após conhecer a recusa. Nesta revisão não fiz novas chamadas.

**CONCORDO COM**

- Separar programas, preservar múltiplos intervalos e rejeitar janela vazia foram correções importantes ([trades:56](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_trades.py:56), [report:164](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_report.py:164)).
- Recusar sobrescrita, registrar crashes e rejeitar ISO sem fuso estão implementados ([io:41](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_io.py:41), [io:80](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_io.py:80), [conv:37](/C:/dev/project-hunter/infra/scripts/pumpfun_rt_probe_conv.py:37)).
- A nota acerta ao limitar a população, distinguir RPC público do baseline da VPS e declarar **chegou antes ≠ operamos antes**. Essas ressalvas devem governar também o título e o primeiro parágrafo.
- Preservaria as tabelas principais como resultado exploratório; corrigiria as conclusões e os defeitos antes de declarar a revisão encerrada.

**OBSIDIAN**

Nenhuma página alterada. Recomendo:

- **KB-0186 — O tempo real da pump.fun…** — corrigir título, reprise, população KOL, empate, indisponibilidade e limites do inventário.
- **Revisões Astra — pumpfun-rt-latency** — registrar a rodada 2, distinguindo bugs reproduzidos de impacto efetivamente encontrado nas capturas.
- **REA / Batedor REA** — esclarecer credencial pública de cliente e evidência necessária para assinatura por carteira.
- **REA na pump.fun apesar dos termos de uso** — explicitar o alcance autorizado para NATS, sem presumir autorização a partir da aceitação técnica.
- **KB-0183 — O que custa coletar o programa inteiro** — acrescentar a recusa de cota HTTP, distinguindo-a da continuidade observada do WS.