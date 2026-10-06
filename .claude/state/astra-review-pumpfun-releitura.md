**RESUMO**

**REQUEST_CHANGES no texto e nas condições de uso pelo H-030.** A releitura é útil e os códigos HTTP conferem. Os principais problemas são transformar observações pontuais em garantias, misturar descoberta com mudança do serviço e deixar algumas escolhas estatísticas implícitas.

Como `quant-engineer`, minha resposta às quatro implicações é: **(a) sim, condicionalmente; (b) exige emenda prévia; (c) serve como reconciliação parcial; (d) registraria prospectivamente como comparação descritiva, sem poder confirmar o H-030.**

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit, acesso a `.env` ou leitura fora do repositório. Revisei os registros locais; não revalidei o site ao vivo.

**TESTES**

Conferência em PowerShell das linhas de API do log:

```text
Linhas API no log: 49
200: 43
201: 2
400: 1
401: 3

frontend-api-v3: 41
profile-api: 3
swap-api: 3
advanced-indexer: 2
```

A soma declarada fecha: 49 API + 6 páginas + 5 conexões WS = 60 unidades do orçamento. **Não são 60 requisições totais:** os 101 chunks estão excluídos, e o REA é outra coleta. Os agregados de 300 carteiras e 800 trades constam nas notas, mas não foram reproduzidos a partir de respostas sanitizadas nesta revisão. [Notas:20](C:/dev/project-hunter/.claude/state/notes-pumpfun-releitura-2026-10-06.md:20)

Não executei testes de aplicação: a revisão é documental.

**MUST-FIX**

1. **Separar estado observado, contrato do bundle e ausência de teste.**

   - “Continuam mortas” precisa virar **“404 em 12/09; não re-testadas em 06/10”**. Ausência no registro não prova indisponibilidade. [Mapa:710](C:/dev/project-hunter/docs/PUMPFUN.md:710)
   - O `404` de `/nats/token` vem da descrição da flag no bundle, não de uma chamada registrada. Não pode aparecer como HTTP medido hoje. Os `auth_required` dos três handshakes são outra evidência, válida. [Mapa:707](C:/dev/project-hunter/docs/PUMPFUN.md:707), [Notas:49](C:/dev/project-hunter/.claude/state/notes-pumpfun-releitura-2026-10-06.md:49)
   - “Sumiu **do registro**; não re-testada” está honesto. Porém, a segunda captura REA registra `/kols` e `/livestream*` no **livestream-api**: incorporar isso como “chamada pelo navegador em outro host; resposta não verificada”. [REA:39](C:/dev/project-hunter/.claude/state/rea-pumpfun-capture-2026-10-06.md:39)

   **Cenário de falha:** descartar uma fonte ainda utilizada ou implementar tratamento de um HTTP que nunca foi observado.

2. **“Nova” e “mudou” não demonstram novidade desde setembro.**

   `/following/v3/*/count`, `/mint-positions` e `/pnl-leaderboard/positions` já estavam no inventário do bundle de 12/09. São **agora testadas**, não comprovadamente novas. `sort?` já aparecia no ranking; agora seus valores foram caracterizados. Mayhem com os mesmos campos e números diferentes é atualização do conteúdo, não necessariamente mudança da interface. [Mapa:58](C:/dev/project-hunter/docs/PUMPFUN.md:58), [Mapa:75](C:/dev/project-hunter/docs/PUMPFUN.md:75), [Mapa:683](C:/dev/project-hunter/docs/PUMPFUN.md:683)

   Também escreveria **“cinco campos antes não registrados foram observados”** para `Coin`. A referência antiga mistura quatro rotas; a nova amostra usa `/coins`, e seis campos antigos não apareceram. Isso não estabelece um diff completo de schema. [Mapa:87](C:/dev/project-hunter/docs/PUMPFUN.md:87), [Notas:148](C:/dev/project-hunter/.claude/state/notes-pumpfun-releitura-2026-10-06.md:148)

   **Cenário de falha:** atribuir mudanças ao upgrade de 02/10 ou remover suporte a campos opcionais usando amostras não comparáveis.

3. **Corrigir limites e projeções apresentados com força excessiva.**

   - `/fees/holder-rewards`: a nota registra **três moedas com `limit=3`**. Os 91 KB e os totais globais não demonstram que o parâmetro foi ignorado. Retirar essa conclusão. [Notas:143](C:/dev/project-hunter/.claude/state/notes-pumpfun-releitura-2026-10-06.md:143), [Mapa:791](C:/dev/project-hunter/docs/PUMPFUN.md:791)
   - “Grupo próprio” de rate limit não está demonstrado; o próprio §10.5 reconhece agrupamento desconhecido. **50/min é cabeçalho observado**, não capacidade operacional garantida. [Mapa:690](C:/dev/project-hunter/docs/PUMPFUN.md:690), [Mapa:789](C:/dev/project-hunter/docs/PUMPFUN.md:789)
   - **15 B** é o tamanho daquela resposta de seguidores, não constante do endpoint: o log da contagem de seguindo mostra 11 B. [Notas:209](C:/dev/project-hunter/.claude/state/notes-pumpfun-releitura-2026-10-06.md:209)
   - **300 distintas** é a união daquela rodada, não previsão de 300 candidatas novas por dia. As mesmas carteiras podem reaparecer.
   - “Ancorado às 02:00 UTC” deve ser “os três `windowStartSec` observados terminavam em 02:00 UTC”; uma leitura não distingue âncora fixa de janela móvel arredondada. [Mapa:719](C:/dev/project-hunter/docs/PUMPFUN.md:719)

   **Cenário de falha:** dimensionar o job para terminar em 60 minutos e produzir uma amostra diária de tamanho fixo, quando cota compartilhada, repetição de carteiras e chamadas adicionais impedem ambos.

4. **Retirar interpretações causais que os campos não demonstram.**

   `buySpendSol ≈ 0` não prova “tokens recebidos”: pode haver compra anterior à janela, custo ausente ou outra convenção contábil. `isVerified` também não estabelece equivalência com o selo KOL estudado no R61. São hipóteses de interpretação. [Mapa:732](C:/dev/project-hunter/docs/PUMPFUN.md:732)

   Da mesma forma, um mint sem sufixo `pump` retornando `null` não prova a regra “fora do programa pump retorna null”. A ausência do sufixo não foi validada como classificador de venue. [Notas:155](C:/dev/project-hunter/.claude/state/notes-pumpfun-releitura-2026-10-06.md:155)

   **Cenário de falha:** excluir traders como recebedores de tokens, equiparar verificados a influenciadores ou apagar moedas elegíveis por uma classificação não comprovada.

5. **H-030(a): `known_at` evita antecipação apenas se o universo e os cortes forem preservados.**

   **Sim:** os seis quadros podem gerar uma lista prospectiva de observação. Guardaria fonte, período, ordenação e recepção de cada resposta; entradas, saídas e desaparecimentos posteriores não apagam candidatas já observadas.

   Mas o desenho diz que **toda carteira vista na fita entra no ranking**. Se só as descobertas pelo site passam a concorrer ao top-30, o experimento passa a medir “C-PnL dentro da seleção da pump.fun”. É outra população, mesmo sem olhar o futuro. Manter controles da fita inteira não corrige essa mudança sozinho. [Desenho:234](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:234), [Mapa:765](C:/dev/project-hunter/docs/PUMPFUN.md:765)

   Além disso, uma candidata descoberta às 02:25 não estava disponível para o corte econômico de 00:00. `known_at` anterior à aposta é necessário, mas precisa respeitar também o corte do retrato que a selecionou. [Desenho:125](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:125)

   **Cenário de falha:** usar a lista das 02:25 para compor retroativamente o retrato de 00:00, ou substituir silenciosamente o universo completo por sobreviventes do ranking.

6. **H-030(b): congelar a troca de fonte e a função dos novos campos.**

   Guardar `is_verified` e `created_coins_count` **não cria um teste por si só**. O garfo surge ao experimentar exclusões, cortes ou interações e escolher a leitura favorável. Eu os declararia inicialmente **descritivos, sem alterar elegibilidade nem CONFIRMA**.

   Antes da coleta, fecharia:

   - Fonte por campo e eventual fallback. `followers/count` não entrega `following`, `is_pump_user`, verificação nem criação de moedas.
   - `known_at` por resposta; se combinar fontes, não atribuir ao conjunto o horário da primeira chamada.
   - Tratamento de `degraded[]`, ausências e divergência entre `verified` e `isVerified`. Falha não vira `false` ou zero.
   - Carteira-gatilho versus entidade, idade máxima da foto e ordem completa da fila — pendências já reconhecidas no desenho.
   - Nenhuma equivalência automática entre `createdCoinsCount` e a exclusão causal de criador de determinado mint.

   O `/overview` pode reduzir o número de chamadas necessárias ao conjunto de campos, mas sua equivalência precisa ser verificada. [Notas:97](C:/dev/project-hunter/.claude/state/notes-pumpfun-releitura-2026-10-06.md:97), [Desenho:501](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:501)

   **Cenário de falha:** controles recebem mais fotos ausentes ou antigas porque estão no fim da fila; depois, uma análise só de perfis completos confunde cobertura com efeito dos seguidores. A decisão já proíbe usar a secundária como outra porta para CONFIRMA. [Decisão:27](C:/dev/project-hunter/obsidian/06-DECISIONS/2026-10-05-carteiras-seguidores-como-pergunta-secundaria.md:27)

7. **H-030(c): especificar reconciliação e retenção antes de tratar `/user-trades` como auditoria contábil.**

   A formulação sustentada é: **“foram recuperados 800 trades de uma carteira, cobrindo cerca de dez dias, com cursor restante”**. Isso não demonstra janela completa, retenção mínima contratual ou cobertura uniforme de carteiras. [Notas:102](C:/dev/project-hunter/.claude/state/notes-pumpfun-releitura-2026-10-06.md:102)

   Falta estabelecer:

   - Intervalo fechado de comparação, paginação até a fronteira necessária, detecção de cursor repetido, lacunas e eventos tardios.
   - Correspondência por transação **e evento/perna**, mint, carteira, lado e quantidade. **Slot sozinho não identifica trade.**
   - Reconciliação das carteiras de cada entidade na versão conhecida no corte, incluindo transferências internas, taxas e convenções bruto/líquido.
   - Inventário e custo de abertura. Dez dias de trades não recuperam necessariamente uma compra antiga cujo lote foi vendido hoje.
   - Evidência sanitizada preservada antes da poda, junto com resultados de divergência e cobertura em seguidas, controles e fora do topo.
   - Backfill com recepção real: nunca substituir `received_at` pelo horário antigo do trade.

   O desenho já exige identidade por evento e retenção por dependência; a API precisa se subordinar a essas regras. [Desenho:109](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:109), [Desenho:465](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:465)

   **Cenário de falha:** perder uma compra anterior ao histórico disponível, transformar sua venda em lucro sem custo ou “reparar” retroativamente um retrato com informação recebida depois. A API pode conferir componentes do W-PnL; não basta para reproduzir C-PnL, reservas e execução da nossa fita.

8. **H-030(d): registrar `top-trader-trades` sem permitir confirmação alternativa.**

   Eu registraria prospectivamente **como comparação descritiva pré-declarada**. Congelaria universo de mints consultados, cadência, deduplicação, composição observada dos traders, `boardsBuiltAtMs`, `generatedAtMs` e recepção local. O endpoint é por mint; escolher os mints depois de observar sucesso introduz outra seleção. [Notas:116](C:/dev/project-hunter/.claude/state/notes-pumpfun-releitura-2026-10-06.md:116)

   Uma operação antiga retornada hoje porque a conta entrou hoje no top-50 **não era sinal disponível na hora daquela operação**. Registrar hoje não autoriza simular entrada ontem.

   **Cenário de falha:** H1/H2 falham, mas o braço do site ganha e passa a justificar “CONFIRMA”. O primário continua exigindo as condições originais; se quiser hipótese confirmatória sobre o site, ela precisa de protocolo próprio e tratamento prévio da multiplicidade. [Desenho:220](C:/dev/project-hunter/docs/design/seguir-carteiras-lucrativas.md:220)

9. **Conciliar a declaração de descarte de dados pessoais.**

   A nota diz “descartados”, mas também informa que corpos brutos ficaram em diretório temporário fora do repositório. Isso não sustenta “nenhum dado pessoal guardado”. Não acessei esse diretório e não posso afirmar se os arquivos ainda existem. [Notas:16](C:/dev/project-hunter/.claude/state/notes-pumpfun-releitura-2026-10-06.md:16)

   **Cenário de falha:** biografias e handles permanecem em arquivos enquanto o relatório certifica descarte. Para a próxima leitura, sanitizar antes de qualquer persistência. A coleta histórica também incluiu dois POST explícitos; portanto, não deve ser descrita como exclusivamente GET.

**NICE-TO-HAVE**

- Separar colunas **HTTP observado**, **schema do bundle**, **inferência** e **não testado**. Isso resolveria boa parte da ambiguidade.
- Guardar evidência reproduzível mínima, sanitizada: parâmetros, horários, contagens, conjuntos de campos e procedimento dos agregados em `Decimal`. Não é necessário guardar perfis brutos.
- Corrigir a duração: os extremos publicados correspondem a **10 dias e 71 minutos**, aproximadamente 10,05 dias. O “10,1” parece arredondamento por outra referência temporal.
- Qualificar “Taxas: nada mudou” como **“as páginas de taxas conferem; taxas on-chain não verificadas nesta leitura”**, como o próprio §10.5 reconhece. [Mapa:793](C:/dev/project-hunter/docs/PUMPFUN.md:793)

**O QUE EU FARIA DIFERENTE**

Dentro do mesmo orçamento, substituiria chamadas de menor utilidade ao H-030 — como perpétuos e changelog — por:

1. **Equivalência dos seguidores:** `/users`, `/overview` e `/followers/count` nas mesmas carteiras, incluindo uma com zero seguidores e uma sem perfil reconhecido.
2. **Paginação distribuída:** duas páginas de outra carteira, preferencialmente ativa em PumpSwap, em vez de concentrar toda a evidência em uma.
3. **Controle de repetição:** ranking com e sem `offset` em sequência curta, repetindo a primeira consulta para separar refresh de paginação.
4. **`top-trader-trades` com cursor e `to`:** verificar se o corte restringe trades enquanto a composição do top continua atual.
5. **`/candles` com `res` válido:** aproveitar o erro de validação para obter ao menos uma resposta utilizável.
6. **Uma rota antiga decisiva:** re-testar `/coins/{mint}`; para as demais, manter explicitamente “não verificado”.

Omitiria POST sob a regra atual. Não gastaria orçamento procurando credenciais ou insistindo em 401.

**CONCORDO COM**

- Separar tráfego observado pelo REA de resposta obtida pelo cliente anônimo.
- Usar o ranking como pista prospectiva e manter C-PnL como critério principal.
- Retirar `username` das fotos.
- Tratar ausência de foto como desconhecida, preservando UTC e disponibilidade real.
- Não confundir lucro marcado do titular com lucro copiável.
- Manter o controle na fita e respeitar autenticação e bloqueios.

Essas escolhas preservam a disciplina já registrada no KB-0149: antecipação e escolha posterior de limiares podem fabricar vantagem. [KB-0149:76](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md:76)

**OBSIDIAN**

Páginas que deveriam ser atualizadas, sem alteração nesta rodada:

- **KB-0185 — O que a pump.fun publica sobre carteiras lucrativas:** corrigir estados, limites, interpretações e alcance da evidência.
- **Seguidores entram no H-030 como pergunta secundária:** registrar fonte por campo, disponibilidade, ausências e função apenas descritiva dos novos atributos.
- **EXP-M15 — seguir carteiras vencedoras:** acrescentar avaliação de instrumento e explicitar que descoberta pelo site não restringe silenciosamente o universo do H-030.
- **Revisões Astra / pumpfun-releitura:** registrar este parecer, cenários de falha e resolução posterior dos pontos.