## RESUMO

**Recomendo corrigir os pontos abaixo antes de rodar o contraste.** A estrutura do estudo é defensável; o resolvedor ainda não mede exatamente a variável declarada.

| Pergunta | Parecer |
|---|---|
| **1. `asc` + maior queda de lamports** | `asc` é adequado; **maior débito líquido não identifica necessariamente o remetente da primeira transferência**. Os 12/12 validam os casos consultados, não a equivalência dos métodos. |
| **2. Rede zero para grupo unitário; denominador resolvidas** | **Sim**, como concentração compartilhada **entre resolvidas**. Sem nenhuma resolvida, o resultado é desconhecido. Compradoras financiadas por exchange permanecem no denominador, mas não formam grupo no numerador. |
| **3. Identidade Helius OU >1.000 destinatários** | Aceitável como **regra operacional de exclusão de serviços**, não como prova de identidade de exchange. Precisa de corte anterior a cada decisão e tratamento explícito de paginação incompleta. |
| **4. Simulador principal; realizado como sensibilidade** | **Concordo**, para comparar a mesma política de saída nas duas vias. A expressão “2,23%” sozinha não determina essa escolha nem garante custo total idêntico. |
| **5. SIMFTR com rede de 2,6%** | **Muda a interpretação, não autoriza mudar a hipótese congelada.** A medida não capturou o mecanismo presumido no caso de origem. |
| **6. Fita desde o nascimento também nas reais** | **Concordo.** O desfecho realizado não recupera as compradoras ausentes da variável explicativa. A conclusão ficará restrita à população com cobertura. |

Papel utilizado: `quant-engineer`. Parecer com preocupações bloqueantes, em modo OPINIÃO.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit, acesso à VPS ou chamada autenticada à Helius. Consultei os arquivos indicados, a memória relacionada e a documentação pública da API.

## TESTES

Não executei testes nem reproduzi a população. **12/12 e 2,6% são resultados registrados no piloto**, não medições independentes desta revisão: [notes-R76.md:46](C:/dev/project-hunter/.claude/state/notes-R76.md:46).

Os exemplos abaixo são **cenários hipotéticos de falha**, não dados observados.

## MUST-FIX

**1. Identificar a transferência dirigida à compradora, não o maior débito da transação.**

O resolvedor exige aumento líquido de saldo e escolhe a conta com maior redução líquida: [resolver_tpl.py:89](C:/dev/project-hunter/.claude/state/r76/resolver_tpl.py:89).

Cenário: numa transação, A envia 0,1 SOL para W e B envia 10 SOL para X. W recebe de A; o algoritmo atribui B. Um relayer que custeia várias criações de conta pode produzir o mesmo erro. **Criação de conta pelo relayer só é um erro de atribuição se ele não for a fonte efetiva dos lamports destinados a W**; quando for, a atribuição pode estar correta, mas não prova controle comum.

Também quebra quando W recebe e gasta na mesma transação: houve transferência recebida, mas o saldo final não subiu. Fechamento de conta e devolução de aluguel exigem definição explícita de inclusão.

**Correção recomendada:** ordenar eventos de transferência, incluindo instruções internas, e verificar origem e destino. Congelar como tratar `createAccount`, devoluções e múltiplas entradas na mesma transação; casos ambíguos ficam não resolvidos. A ordenação ascendente e a paginação são suportadas pela [documentação Helius](https://www.helius.dev/docs/api-reference/rpc/http/gettransactionsforaddress).

O limite de dez transações pode permanecer como orçamento **se significar busca truncada**, nunca ausência de financiamento. Hoje esse resultado é registrado como `no_incoming_in_first_10`: [resolver_tpl.py:98](C:/dev/project-hunter/.claude/state/r76/resolver_tpl.py:98).

**2. Classificação de exchange precisa ser temporal e admitir “desconhecido”.**

O desenho usa destinatários até o corte do estudo: [notes-R76.md:35](C:/dev/project-hunter/.claude/state/notes-R76.md:35). Isso introduz informação posterior às decisões.

Cenário: o financiador tinha 300 destinatários na entrada e ultrapassou 1.000 depois. Excluí-lo retroativamente muda a variável usando futuro. **Conte apenas transferências anteriores à decisão de cada mint.** Identidades Helius consultadas hoje, sem histórico verificável, devem ficar identificadas como classificação retrospectiva; não sustentam sozinhas uma versão estritamente disponível naquele instante.

Há outro problema: **1.100 transferências não equivalem a 1.100 destinatários distintos**. Onze páginas podem repetir cem destinatários, deixando milhares de outros no restante do histórico. Ao atingir o orçamento:

- Mais de 1.000 distintos: exclusão comprovada pela regra operacional.
- Histórico esgotado com até 1.000: não excede o limiar.
- Histórico ainda paginável: classificação desconhecida.

Fixe também SOL nativo versus WSOL: o padrão documentado é `solMode=merged`, que reúne os dois; há modo `separate`. [Documentação Helius](https://www.helius.dev/docs/api-reference/rpc/http/gettransfersbyaddress).

Por fim, **um distribuidor de golpe também pode ultrapassar 1.000 destinatários**. Portanto, mantenha a regra congelada, mas não chame sua classificação de prova de exchange; reporte sensibilidade excluindo somente identidades conhecidas.

**3. `simulate_current.ok` não comprova desfecho observável.**

A elegibilidade proposta exige apenas o `ok` do simulador: [notes-R76.md:22](C:/dev/project-hunter/.claude/state/notes-R76.md:22). Ele fica verdadeiro com três pontos e pode liquidar por tempo usando o último estado disponível: [sim.py:200](C:/dev/project-hunter/.claude/state/r72/sim.py:200), [sim.py:220](C:/dev/project-hunter/.claude/state/r72/sim.py:220).

Cenário: há pontos em 0, 1 e 2 segundos, depois a coleta falha. O simulador pode produzir uma saída aos 301,6 segundos baseada no estado de 2 segundos, embora o preço tenha desabado durante a lacuna.

**Correção:** exigir cobertura verificável até o pouso da saída simulada; distinguir ausência de negócios comprovada de ausência de coleta. Desfecho sem cobertura fica censurado, não recebe retorno artificialmente resolvido. O próprio carregador R72 tem uma condição adicional de resolubilidade por fita, embora ela também não prove cobertura integral: [load.py:256](C:/dev/project-hunter/.claude/state/r72/load.py:256).

**4. A cláusula de refutação confunde imprecisão com evidência contra a hipótese.**

O espelhamento algébrico feito no R76 está correto; **a regra original é que está errada como refutação estatística**: [Fila de Hipoteses.md:171](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:171>), [notes-R76.md:71](C:/dev/project-hunter/.claude/state/notes-R76.md:71).

Cenário hipotético: IC de `alto − baixo = [−0,20; +0,10]`. Seu limite superior supera −0,01, acionando a cláusula, embora o intervalo comporte um efeito fortemente favorável à hipótese.

Para excluir uma vantagem de pelo menos 0,01 do grupo baixo, seria necessário **limite inferior de `alto − baixo > −0,01`**, equivalente a **limite superior de D < +0,01**.

Não reescrever silenciosamente o congelado: registrar uma errata antes do contraste e distinguir “aciona a cláusula literal” de “refutação sustentada pelo intervalo”. Cobertura insuficiente continua sendo **limite de dado**.

**5. Congelar o comportamento quando os tercis e os limiares colapsarem por empates.**

O desenho manda empates para baixo e usa quantis vizinhos para avaliar patamar: [notes-R76.md:64](C:/dev/project-hunter/.claude/state/notes-R76.md:64).

Cenário: 80% dos mints têm rede zero. Os dois cortes de tercis podem coincidir; vários quantis da grelha também serão zero. Isso pode esvaziar grupos ou chamar a mesma divisão repetida de “patamar”.

**Correção:** valores iguais ficam juntos; reportar tamanhos efetivos; não forçar três grupos. Se não houver contraste identificável, declarar isso. Dois limiares só sustentam patamar se produzirem **partições diferentes**.

## NICE-TO-HAVE

- **Cobertura por mint deve acompanhar cada valor.** O denominador resolvidas é legítimo, mas condicionado à resolução: duas resolvidas de cem, ambas com o mesmo financiador, dão 100% entre resolvidas. Cobertura agregada alta pode esconder esse caso. Reportar também `maior grupo / todas as compradoras` e sensibilidade por cobertura, sem substituir silenciosamente a métrica congelada de [notes-R76.md:32](C:/dev/project-hunter/.claude/state/notes-R76.md:32).
- Ampliar a validação para transações com relayer, múltiplos remetentes, instruções internas e contas antigas. Comparação com `funded-by` é concordância entre métodos; inspeção dos eventos é a verificação semântica.
- Reportar resultados separados por real/papel e dia. A mistura pode produzir associação causada pela composição das coortes.
- Manter casos de fronteira temporal como ambíguos quando a resolução do `block_time` não provar precedência intrassegundo.

## O QUE EU FARIA DIFERENTE

**Manteria simulador principal e realizado como sensibilidade**, mas descreveria o estimando como “retorno da política comum, condicionado às entradas históricas”. O simulador conserva `spent` e `tokens` históricos, e cobra `cost/2` na saída: [sim.py:205](C:/dev/project-hunter/.claude/state/r72/sim.py:205), [sim.py:86](C:/dev/project-hunter/.claude/state/r72/sim.py:86). Portanto, reutilizá-lo não basta para afirmar custo total exatamente igual a 2,23% nas duas vias; reconciliaria primeiro a contabilidade das entradas, sem cobrar novamente custos já embutidos.

**Manteria a guarda de nascimento nas reais**, chamando-a de critério de cobertura, não prova de completude. Compras e vendas ausentes podem se compensar e preservar a reconciliação de reservas. Os critérios atuais constam em [notes-R76.md:19](C:/dev/project-hunter/.claude/state/notes-R76.md:19). O contrafactual das 95 reais sem essa guarda deve permanecer explicitamente exploratório.

**Não alteraria H-014 para “salvar” SIMFTR.** O piloto demonstra que financiamento inicial comum não capturou o caso: [notes-R76.md:51](C:/dev/project-hunter/.claude/state/notes-R76.md:51). Não demonstra ausência de coordenação, nem prova que vendedores simultâneos têm controlador comum. A afirmação de “demanda fabricada pela própria rede” na origem deve receber uma ressalva datada, preservando o registro original: [Fila de Hipoteses.md:165](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:165>).

## CONCORDO COM

Uma decisão por mint; resolver todas as compradoras; grupo unitário valer zero; mesma política de saída; realizado como sensibilidade; registrar o piloto desfavorável; manter o caráter retrospectivo explícito. Essas escolhas estão declaradas em [notes-R76.md:17](C:/dev/project-hunter/.claude/state/notes-R76.md:17), [notes-R76.md:34](C:/dev/project-hunter/.claude/state/notes-R76.md:34), [notes-R76.md:42](C:/dev/project-hunter/.claude/state/notes-R76.md:42) e [notes-R76.md:55](C:/dev/project-hunter/.claude/state/notes-R76.md:55).

## OBSIDIAN

- **Fila de Hipóteses — H-014:** acrescentar errata metodológica datada, tratamento de censura/empates e ressalva sobre o mecanismo de SIMFTR.
- **Ficha de 2026-09-23 — mesa real:** distinguir despejo simultâneo observado de controle comum ainda não demonstrado.
- **Revisões-Astra — R76/H-014:** registrar este parecer e as decisões tomadas sobre cada bloqueio.
- **KB-0149 — O que a mesa real ensinou:** incorporar, após validação, a distinção entre financiamento comum, coordenação e cobertura do instrumento.

Nenhuma página foi alterada nesta revisão.