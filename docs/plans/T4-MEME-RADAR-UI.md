# Meme Radar — especificação de interface A4.3d

Data: 12/09/2026. Autoria: Astra, papel `product-designer`.
Entrega documental para o frontend e o orquestrador; não é interface implementada nem aceite de tela renderizada.
Direção visual: a vigente em `docs/DESIGN.md`, sem nova paleta ou mudança de identidade.

## 1. Escopo, referências e dependências

O radar responde: quais moedas estamos acompanhando, o que foi observado e quanto dessa observação é utilizável. As rotas `/meme` e `/meme/{mint}` são relativas à organização autenticada. Texto fixo no topo: **“Meme Radar · Só monitoramento”**. Não há execução ou recomendação de entrada nesta entrega.

Referências locais: `docs/DESIGN.md` inteiro; `docs/plans/T4-MEME-RADAR.md` §3–§6 e adendo Mayhem; `.claude/state/notes-T4.1.md`; `.claude/state/notes-A4.1b-mayhem.md` §2–§5; brief T4.2 e brief T4.3. As notas T4.2 e `docs/plans/T4-FERRAMENTAS.md` não estavam disponíveis na leitura desta especificação. Portanto, os nomes de dados abaixo são requisitos de apresentação, não um JSON congelado nem afirmação de disponibilidade da API. O frontend deverá reconciliá-los com o contrato T4.2/T4.3 antes de implementar; campo não entregue recebe estado honesto.

Referência externa verificada em 12/09/2026: o [screener oficial Mayhem](https://pump.fun/mayhem) apresenta moeda, capitalização, volume, estado, modo e tendência, com estados ativo, pausado e encerrado. Sua documentação de interface distingue Auto de Manual: neste último o criador solicita a operação, mas direção e tamanho continuam aleatórios. Usamos a separação entre modo e estado e a prioridade mobile; não copiamos o ranking de vencedores ou as ações de negociação. A abertura de `https://pump.fun/docs/mayhem-mode` retornou 403 nesta rodada; seu conteúdo não foi revalidado. Photon, BullX, GMGN e Axiom ficam como referências para comparação futura, sem alegação de auditoria dessas telas.

## 2. Contrato de honestidade visual

Cada valor precisa de unidade, fonte, instante observado (`observed_at`), qualidade e motivo quando ausente. Quando existir instante do evento, publicação da fonte ou disponibilidade no Hunter, preservá-los separadamente. Consultar agora não torna recente um dado antigo.

- **Tempo:** “Consultado em dd/mm/aaaa hh:mm:ss” para a leitura da seção; “Atualizado há N s / N min / N h” para idade do dado; “Snapshot · há N s” para foto sem atualização automática. Brasília no texto, ISO UTC no `title` e também em detalhes acessíveis por toque/teclado. `created_at` alimenta “Idade”; `first_seen` não substitui criação desconhecida.
- **Fonte visível:** abaixo de cada KPI, na linha da moeda e na legenda do gráfico. O nome curto é legível: “pump.fun”, “PumpPortal” ou “Solana · leitura de conta”, conforme a origem real. “Ver procedência” expande instante observado, instante disponível, evento/bloco quando informado, confirmação/finalidade, versão da medida e cobertura. Sem URL com credencial ou nome de serviço interno.
- **Frescor:** qualidade por componente. Aplicar o limite de atraso informado pelo contrato; sem limite ou verificação, “Sem verificação de atualização”, neutro. Não inventar um prazo de validade na UI. A conexão saudável não valida reservas antigas nem demonstra cobertura completa.
- **Nulos:** “Sem dado: {motivo}”; na tabela de features, “Sem medição: {motivo}”. Zero só quando o contrato confirma a medida e sua cobertura. `false` só quando há observação negativa definida; ausência não vira falso.
- **Números:** SOL e tokens identificados; valores decimais preservados, sem cálculos monetários em ponto flutuante no cliente. Formatação pt-BR conforme DESIGN, números mono/tabulares à direita; abreviação só para contagens/volume secundários, com valor integral acessível. Capitalização e preço mantêm a precisão recebida.
- **Atualização:** usar o padrão AutoRefresh do produto quando suportado, com rótulo “Atualização automática”; não anunciar streaming contínuo para consulta periódica. Preservar foco, filtros, página e leitura do detalhe; atualização não deve saltar a linha sob o dedo. Falha conserva o último valor com idade e erro, sem trocar por zero.

## 3. `/meme` — hierarquia

Ordem vertical: título e contexto → visão geral → cobertura rastreada → busca/filtros/ordenação → moedas. Falha em um agregado não elimina a tabela nem o contexto de monitoramento.

### 3.1 Faixa de visão geral

| Bloco | Conteúdo | Universo e condição |
|---|---|---|
| Criações · 24 h | Total e decomposição Automático / Manual / Modo desconhecido | Identificar “Mayhem · agregado do provedor” se vier do overview Mayhem; nunca “todo pump.fun” sem essa cobertura |
| Criações · 7 d | Mesma decomposição, em bloco distinto | Janela móvel de sete dias e corte fornecidos pela fonte; não projetar uma coleta parcial |
| Agentes Mayhem ativos | Contagem do provedor ou contagem rastreada, explicitamente nomeada | Não derivar atividade de idade menor que 24 h; não confundir com conexão do Hunter |
| Graduações · 24 h | Contagem de conclusões da curva confirmadas no intervalo | Rótulo auxiliar “Curvas concluídas”; migrações para PumpSwap são eventos separados |

Cada bloco mostra sua própria fonte e “Atualizado há …”, com `observed_at` acessível. Dados de fontes ou cortes diferentes não são somados. O resto não explicado pelos modos só pode virar “Modo desconhecido” se o contrato definir uma decomposição exaustiva e coerente; caso contrário, “Decomposição parcial”. Ausência do agregado de graduações: “Sem dado: contagem de conclusões indisponível”. Uma contagem local é “Graduações entre moedas rastreadas · 24 h”, com janela efetivamente coberta e gaps; não se apresenta como total de mercado. Não criar taxa de graduação sem coorte e denominador compatíveis.

Para uma janela ainda incompleta: “Cobertura parcial da janela” e intervalo observado. Eventual número é “Eventos observados”, não total da janela. Não usar amostras históricas das notas como valores de demonstração.

### 3.2 Universo e controles

Faixa permanente: **“N de M moedas rastreadas”**, seguida de definição: N acompanhadas agora pelo Hunter; M elegíveis conhecidas no mesmo corte. Mostrar critério efetivo do coletor, limite aplicado e motivo de seleção/saída no detalhe. Se M não existir: “N moedas rastreadas · total elegível desconhecido”. M nunca vem de criações do provedor nem da quantidade de linhas da página. Sem N: “Universo rastreado indisponível”. A contagem de resultados filtrados é separada.

Busca por nome, símbolo ou mint dentro do universo anunciado. Mint é a identidade; símbolos iguais não fundem moedas. Filtros: estado da curva, elegibilidade Mayhem, modo, estado do agente e qualidade, somente conforme suporte real do contrato. “Todos” inclui desconhecidos; desconhecido pode ser filtrado explicitamente. Não oferecer controle que a API não consegue aplicar. Busca e ordenação valem sobre todo o conjunto consultável, com paginação do servidor; nunca só sobre as linhas carregadas. Filtros ativos visíveis e ação funcional “Limpar filtros”.

Ordenação inicial: criação mais recente primeiro, `created_at` decrescente, empate por mint. Data ausente por último. Alternativas quando disponíveis: capitalização SOL, progresso da curva e última observação. Nulos sempre por último nas duas direções. Cabeçalho anuncia direção (`aria-sort`). Ordenação explícita não equivale a recomendação. Volume só entra quando medido com janela e universo definidos; não ordenar por hype, influência social ou “melhor moeda”.

Na atualização automática, manter a ordem visível enquanto houver foco/interação; anunciar “Há atualizações” com ação real “Atualizar lista” que aplica a nova ordenação. Recarregar não dispara coleta paga nem passa a rastrear uma mint. Paginação indica faixa de resultados e mantém ordenação/filtros; ausência de total não vira contagem inventada.

### 3.3 Tabela de moedas rastreadas

| Coluna | Conteúdo e prioridade | Regra visual |
|---|---|---|
| Moeda | Nome, símbolo, mint abreviada; essencial | Link real ao detalhe; mint integral copiável; nome ausente “Nome não informado” |
| Idade | Desde criação; secundária em 375 px | Metadado neutro; desconhecida se só houver primeira observação |
| Capitalização teórica · SOL | Valor derivado da curva; essencial | Número em `fg`, nunca verde só por ser alto; legenda “Não representa valor resgatável” |
| Curva | Estado e progresso em %; essencial | Barra `info`, sem gradiente; desconhecido sem barra preenchida; não confundir 100% arredondado com conclusão |
| Agente Mayhem / Modo | Ativo, Em pausa, Encerrado, Não se aplica ou Desconhecido; Auto/Manual separado | Estado neutro/info ou âmbar conforme §4; nunca sinal de compra |
| Criador | Endereço abreviado; desktop e detalhe | Identidade observada, sem selo “confiável”; valor integral acessível |
| Qualidade / Fonte | Atualização e origem por componente; essencial | Idade e problema visíveis; procedência expandida acessível, não só tooltip |

Em 1440 px, uma linha de 40 px confortável ou 32 px compacta, corpo de 13 px. Detalhes longos abrem painel/linha expandida sem comprimir a linha-base. Nome e número não disputam com vários badges. Colunas monetárias à direita; cabeçalhos com unidade. Reservar espaço estável para números; nenhuma linha com gráfico decorativo. Se houver ≥ 200 linhas renderizadas, exigir virtualização com altura coerente à densidade e navegação acessível, além da paginação.

## 4. Semântica de cor e estados honestos

| Cor/tokens | Significado permitido | Não significa |
|---|---|---|
| `green` / `green-soft` | Qualidade verificada saudável; variação positiva medida com base e janela | Moeda segura, lucro realizado, agente Mayhem lucrativo |
| `red` / `red-soft` | Falha confirmada da leitura; gap identificado; variação negativa medida | Toda moeda não graduada, criador vendedor ou agente encerrado |
| `warning` / `warning-soft` | Atraso acima do limite; quota; cobertura parcial; pausa Mayhem informada | Rug confirmado ou perda inevitável |
| `info` / `info-soft` | Progresso, estado da curva, agente ativo, evento informativo | Recomendação de entrada |
| `fg-muted` / `fg-subtle` | Desconhecido, não aplicável, agente encerrado | Zero, falso ou sucesso |
| `gold` / `gold-soft` | Navegação ativa, foco, uma ação primária quando necessária | Candles, ganho ou ranking |

Cor sempre acompanhada de texto/ícone. Fundos de badges usam `-soft`, sem alfa ou opacidade para “desligado”. Usar tokens vigentes; medir contraste renderizado em ambos os temas: texto ≥ 4,5:1; controles/gráficos essenciais/foco ≥ 3:1 contra fundos adjacentes. Não presumir que o nome do token garante contraste em qualquer composição.

| Situação | Copy e comportamento |
|---|---|
| Primeiro carregamento | “Carregando moedas rastreadas…”; skeleton sem valores, animação respeita movimento reduzido |
| Nenhuma moeda rastreada | “Nenhuma moeda rastreada ainda.” + estado real da coleta, se informado; não afirmar que parou |
| Busca sem resultado | “Nenhuma moeda encontrada com estes filtros.” + “Limpar filtros” |
| Consulta falhou | “Não foi possível carregar as moedas.” + “Tentar novamente”; demais seções independentes permanecem |
| `not_subscribed` | “Sem medição: negociações não acompanhadas para esta moeda” |
| `insufficient_coverage` | “Sem medição: cobertura insuficiente neste intervalo” |
| `rate_limited` | “Sem dado: limite de consultas da fonte”; último dado, se houver, com idade e aviso |
| `unsupported_quote` | “Sem dado em SOL: moeda de cotação não suportada”; não converter USDC usando cotação implícita |
| Leitura/feature ainda não construída | “Sem medição: leitura de detentores ainda não disponível no Meme Radar”, conforme causa real |
| Motivo ou enum novo | “Sem dado: motivo não informado” / “Estado desconhecido”; não vazar enum nem assumir estado conhecido |
| Mint inválida / desconhecida / fora do conjunto | Mensagens distintas: “Endereço inválido”, “Moeda não encontrada no universo consultado”, “Moeda fora do rastreamento atual” |

Sem dado indisponível retratado como problema da moeda. Exemplo: ausência de leitura de detentores não vira concentração de 0%; indisponibilidade do feed não vira “criador não vendeu”.

## 5. `/meme/{mint}` — detalhe

Ordem: voltar ao radar preservando filtros → identidade e contexto → último estado observado → séries e eventos → medidas por minuto → área informativa paper. Em desktop, identidade/procedência podem ocupar coluna lateral; série e medidas mantêm prioridade. Em mobile tudo em uma coluna.

### 5.1 Identidade e estado

Nome/símbolo, mint integral com quebra de linha e ação “Copiar endereço”, criador, criação, origem e critério de rastreamento. Metadados são declarados pela fonte, não endosso do Hunter; renderizar texto sem HTML arbitrário. Links externos, se existirem, são validados e identificados como externos. Sem imagem disponível, usar ícone neutro, não gerar logo fictício.

Mostrar separadamente: elegibilidade Mayhem (Sim / Não / Desconhecida), modo e estado do agente; estado da curva; migração e pool quando observados. Um badge “Agente encerrado” não encerra a moeda. Uma moeda fora do rastreamento atual mantém histórico e último instante; ausência de atualização não se converte em abandono/rug.

### 5.2 Série de reservas → capitalização e progresso

Dois painéis alinhados no mesmo eixo de tempo: **“Capitalização teórica · SOL”** e **“Progresso da curva · %”**. Sem duplo eixo sobreposto. Linha `info`, fundo `bg`, grade sutil `border`, eixos legíveis; nada de área verde por padrão. Unidade ao lado do valor e do eixo. Legenda permanente: **“Derivado das reservas observadas. Não representa o valor obtido numa venda.”**

Requisitos de cálculo para o contrato, não para recálculo no navegador:

- preço marginal = reserva virtual de SOL normalizada / reserva virtual de tokens normalizada;
- capitalização teórica em SOL = preço marginal × oferta total observada para a mesma versão/instante;
- progresso percentual = 100 × (1 − reserva real de tokens / reserva real inicial de tokens da própria mint).

SOL não é lamport; tokens não são unidades cruas. Não fixar oferta em um ou dois bilhões, reserva inicial universal ou limiar em SOL/USD. Denominador ausente/zero, cotação incompatível ou insumos temporalmente incoerentes tornam a derivação indisponível, com motivo. Valor fora do domínio esperado recebe indicação de inconsistência, sem clamp silencioso. A conclusão exige evidência do estado da curva; a migração exige seu próprio evento. Não inferir conclusão de uma apresentação arredondada de 100%.

“Como foi calculado” expõe reservas virtuais e reais, oferta, denominador inicial, unidades e respectivas fontes/instantes. Cursor/toque/foco num ponto mostra valor, instante observado, instante disponível, fonte e cobertura. Acesso equivalente em tabela textual; informação essencial não depende de hover nem de SVG visual.

Janelas de consulta só quando suportadas pela API: “1 h”, “24 h”, “7 d”; exibir intervalo efetivamente coberto. Linhas unem somente observações dentro de trechos explicitamente cobertos. Gap produz ruptura e anotação “Sem observação neste intervalo”; não interpolar, suavizar, preencher com zero ou carregar último valor até o presente. Com um ponto, mostrar o ponto e “Uma observação disponível”; sem pontos, explicar a ausência. Evento da fonte e snapshot observado em outro horário não são alinhados artificialmente.

Após migração, marcar o fim da série da curva. Sem fonte de preço do pool, “Curva concluída; preço após migração não acompanhado”. Não prolongar o último valor como preço atual. Histórico preservado, separado de eventual série futura do pool.

### 5.3 Eventos

| Marca | Evidência necessária | Apresentação |
|---|---|---|
| Criação | Evento/instante de criação identificado | Ícone neutro e “Criação”; se só descobrimos depois, registrar “Primeira observação” separadamente |
| Conclusão da curva | Estado de conclusão validado | “Curva concluída”; não chamar de migração |
| Migração | Evento de migração e pool, quando conhecido | “Migração para PumpSwap”; fora da janela, só na lista de eventos |
| Pausa / retomada Mayhem | Evento ou mudança entre observações do estado | Âmbar para pausa, info para retomada; intervalo da incerteza visível |
| Encerramento Mayhem | Estado informado pela fonte | “Agente Mayhem encerrado”, neutro |

Estado observado em polling não fornece o horário exato da transição: usar “Pausa observada” e o intervalo entre a última observação ativa e a primeira pausada, se ambos existirem. Sem histórico de estados, “Histórico de pausas indisponível”; não reconstruir eventos pelo estado atual. Marcas próximas agrupadas abrem lista cronológica acessível, cada item com fonte e horário; nunca escondem a série.

### 5.4 Medidas por minuto

Título “Medidas por minuto” e intervalo de cada linha, com minuto fechado, observado/disponível, cobertura e versão no detalhe. Minuto em andamento não recebe valor final. Ordenar pelo minuto mais recente, paginação no servidor. No mobile escolher uma medida e listar minuto/valor/motivo, preservando acesso às demais sem arrastar uma tabela enorme.

| Medida | Unidade e regra de copy |
|---|---|
| Capitalização teórica | SOL, mesma definição da série |
| Progresso da curva | %, denominador identificado |
| Idade | Minutos desde criação conhecida |
| Compradores únicos | Contagem; distinguir “no minuto” de “acumulados até este minuto” conforme contrato; carteiras não equivalem a pessoas |
| Compras / vendas | Razão por contagem, janela explícita; sem vendas no denominador → “Sem medição: nenhuma venda no intervalo”, não infinito |
| Participação dos 10 maiores detentores | % por proprietário; método/denominador e exclusões da curva, pool e burn acessíveis; sem leitor → nulo |
| Venda pelo criador | “Venda observada” / “Nenhuma venda observada no intervalo coberto” / “Sem medição: …”; transferência não é venda |
| Cobertura | Fração/intervalo efetivamente observado e gaps; não porcentagem inventada a partir da conexão |

Negociações atribuídas ao agente Mayhem devem ser separadas das demais quando houver feed e atribuição confiável. Rótulo preferido: “Exclui operações identificadas do agente Mayhem”; não “volume orgânico”, que sugeriria ausência de outras manipulações. Sem separação disponível, declarar isso; não exibir números como se o filtro já estivesse aplicado. Cada nulo tem motivo na própria célula ou expansão por toque/teclado, nunca apenas traço ou tooltip. Minuto ausente no histórico é lacuna declarada, não minuto de atividade zero.

### 5.5 Área futura de aposta paper

Bloco textual ao final, sem botão desabilitado, inputs de tamanho ou saldo fictício:

> **Aposta paper · Indisponível**
> A simulação de compra e venda na curva ainda não está disponível nesta etapa do Meme Radar. É preciso validar a simulação, os custos e os controles de risco antes de liberar apostas paper.

Este é o motivo de produto, condicionado ao escopo atual do brief. Se a implementação futura chegar, o motivo deve refletir a trava real; não continuar alegando ausência de implementação. A identificação técnica dessa dependência fica no handoff: T4.4/T4.5 e aceite do orquestrador; nenhum ID de tarefa ou flag aparece na copy. Não há conectar carteira, comprar, vender, ativar, promessa de horário nem ligação com ordens do laboratório existente.

## 6. Dicionário de domínio

| Conceito normalizado | Português da interface | Limite de interpretação |
|---|---|---|
| Curva incompleta observada | Em formação | Não indica oportunidade |
| Curva concluída | Curva concluída | Não comprova migração |
| Migração observada | Migrada para PumpSwap | Não garante liquidez de saída |
| Estado da curva ausente | Estado da curva desconhecido | Não equivale a “Em formação” |
| Mayhem elegível verdadeiro/falso/nulo | Com Mayhem / Sem Mayhem / Mayhem desconhecido | Ausência de objeto HTTP não prova “Sem Mayhem” |
| Modo `auto` / `manual` | Automático / Manual | Manual é acionamento pelo criador no pump.fun, não ordem manual do Hunter |
| Agente `active` / `paused` / `ended` | Agente Mayhem ativo / Em pausa / Encerrado | Estado do agente externo, independente de curva e de conexão |
| Agente não aplicável | Não se aplica · moeda sem Mayhem | Só quando elegibilidade negativa é conhecida |
| Bundler, se medido | Indício de compras coordenadas | Sinal com método, janela, confiança e fonte; não “fraude comprovada” |
| Dev-vendeu, se medido | Venda pelo criador observada | Evidência de venda, não prova de rug |

O normalizador deve resolver aliases do provedor antes do dicionário: `completed` no contexto do agente não significa `complete` da curva. Estado novo mantém fallback neutro até revisão. Pausa pode ter a explicação geral “O provedor associa pausas a liquidez ou capitalização insuficiente”; não atribuir a causa específica a uma moeda sem observação. Sem feature de bundler, não mostrar selo “Sem bundler” nem placeholder de score de risco.

## 7. Mobile 375 primeiro e wireframes

Prioridade mobile: ler cobertura e frescor, reconhecer moeda, abrir detalhe e consultar evidência com um dedo. Rapidez aqui significa menos passos para compreender o dado. Não introduzir compra rápida, gestos destrutivos, animações urgentes ou ranking de vencedores.

- **375 px:** margens de 16 px; uma coluna; overview em pares de blocos que quebram sem truncar números; botão “Ver modos” expande a decomposição. Lista em linhas de duas/três faixas: identidade + mcap; curva + estado Mayhem; qualidade/fonte. Idade, modo e criador acessíveis no detalhe. Alvos de toque ≥ 44 × 44 px, corpo 14 px; tabela compacta de 32 px é somente desktop. Sem rolagem horizontal da página.
- **768 px:** overview em duas colunas; tabela reduzida com moeda, capitalização, curva, Mayhem e qualidade; criador no detalhe. Filtros podem abrir painel, com rótulos e foco restaurado ao fechar.
- **1440 px:** quatro blocos de overview, filtros na linha e tabela completa. No detalhe, série domina a largura; procedência lateral não diminui a legibilidade dos gráficos.
- **Todos:** título 24 px; seção 20 px; KPIs em grade 24 px, conforme escala de §2 do DESIGN; metadados 11/12 px, tabelas 13 px, destaque 16 px. Fontes UI e mono apenas. Respeitar zoom 200%, nomes extensos, quebra de mint e foco visível. Feedback de cópia anunciado; atualização com `aria-live` discreto, sem narrar cada número a cada refresh.

Wireframes abaixo são estrutura, não amostra de mercado: `{campos}` são marcadores sem valores fictícios.

```text
375 px — /meme
Meme Radar · Só monitoramento
Consultado em {data e hora}
[Criações 24 h]      [Criações 7 d]
{valor ou motivo}    {valor ou motivo}
{fonte e idade}      {fonte e idade}
[Ver modos]
[Mayhem ativos]      [Curvas concluídas 24 h]
{valor ou motivo}    {valor ou motivo}
{fonte e idade}      {fonte e idade}
N de M moedas rastreadas · {critério}
[Buscar moeda ou endereço] [Filtros]
Ordenar: Mais recentes
-------------------------------------
{símbolo / mint}      {mcap} SOL
{curva / progresso}  {estado Mayhem}
{fonte · idade · qualidade}  [Detalhe]
-------------------------------------
{paginação real}

375 px — /meme/{mint}
[Voltar ao radar]
{nome / símbolo} · Só monitoramento
{mint integral} [Copiar endereço]
{estado da curva} · {Mayhem / modo}
{fonte · idade · cobertura}
Capitalização teórica · SOL
{série real ou motivo de ausência}
Progresso da curva · %
{série real ou motivo de ausência}
{legenda de reservas e gaps}
[Ver procedência] [Ver dados em tabela]
Eventos observados
{evento · horário · fonte}
Medidas por minuto [Selecionar medida]
{minuto | valor ou motivo}
Aposta paper · Indisponível
{motivo escrito, sem controle inerte}
```

## 8. Anti-padrões proibidos

Gráfico verde por padrão; curva que fecha gaps; zeros de conveniência; mcap como dinheiro resgatável; “lucro” sem execução; preço da curva carregado após migração; dados atuais aplicados ao passado; “ativo” como sinal de segurança; conclusão e migração fundidas; atividade do Mayhem contada como demanda independente; “orgânico” sem comprovação; rug/bundler como veredito; ranking por hype; fonte escondida; universo global inferido da amostra; 24 h/7 d projetadas de poucos minutos; ordenação apenas na página; ícone/tooltip como único aviso mobile; botões de compra ou paper inertes; mockup tratado como evidência visual de produção.

## 9. Checklist de aceite visual antes do commit da implementação

O orquestrador registra rota, viewport, tema, fonte, corte dos dados e evidência de cada item. Itens abaixo estão deliberadamente desmarcados: esta tarefa entrega design, não executa T4.3. Screenshots de mockups não fecham aceite com dado real. Cenários difíceis podem ser reproduzidos em testes isolados e rotulados, sem fixture permanente na aplicação.

- [ ] `/meme` e detalhe abrem com dado real em 375/768/1440, escuro/claro: seis combinações por rota; capturas datadas e nenhuma falha de layout/zoom.
- [ ] Primeiro olhar distingue monitoramento, agregado do provedor e universo rastreado; N/M, critério, resultados e paginação não se confundem.
- [ ] Criações 24 h/7 d por modo, Mayhem ativos e conclusões 24 h têm valor ou motivo, fonte e `observed_at`; cobertura parcial e cortes diferentes são visíveis.
- [ ] Carregando, vazio operacional, filtro vazio, falha, atraso, gap, sem verificação, zero real e nulo têm tratamentos distintos; retry funciona.
- [ ] `not_subscribed`, `insufficient_coverage`, `rate_limited`, `unsupported_quote`, denominador ausente e enum novo não viram zero/falso/verde.
- [ ] Curva concluída, migração e agente encerrado coexistem sem contradição; modo Manual não sugere controle do Hunter.
- [ ] Ordenação/paginação aplicam-se ao conjunto inteiro; empates e nulos são estáveis; atualização conserva foco e não desloca alvo de toque.
- [ ] Busca por mint e símbolos repetidos mantém identidade; nomes extensos, dados parciais e fonte longa não quebram a linha.
- [ ] Série usa reservas/unidades/denominador da mint; nenhum supply fixo; gaps, ponto único, intervalo vazio e pós-migração são honestos.
- [ ] Eventos têm fonte/tempo; pausas observadas por polling mostram incerteza; tabela textual oferece a mesma informação do gráfico.
- [ ] Medidas distinguem janela de minuto/acumulado, ausência de trades, exclusão Mayhem, transferência/venda e motivo de cada nulo.
- [ ] Paper aparece como texto indisponível com motivo; nenhuma ação de ordem, carteira, gasto ou ativação.
- [ ] Contraste medido nos dois temas, foco/teclado/leitor de tela, toque ≥ 44 px e zoom 200% verificados; cor e hover não são o único canal.
- [ ] Densidade/virtualização preservam navegação; fontes/tokens corretos; `prefers-reduced-motion` respeitado; nenhum pulso urgente.
- [ ] Contrato final T4.2/T4.3 conciliado com esta especificação; features faltantes permanecem explicitamente ausentes, sem inventar enum, prazo ou dado.

Verificação desta entrega: revisão documental contra os seis itens do brief e checagem de whitespace do único arquivo. O brief A4.3d não lista suíte automatizada; TDD e testes de aplicação não se aplicam a esta entrega sem código. A execução e a auditoria visual da tela pertencem a T4.3; não foram realizadas aqui.

Comando documental executado em primeiro plano (saída real: `Whitespace: OK`, exit 0):

```bash
timeout 290 awk '/[ \t]+$/ {bad++} END {if (bad) {print bad " linhas com whitespace final"; exit 1} print "Whitespace: OK"}' docs/plans/T4-MEME-RADAR-UI.md
```

A tentativa de iniciar revisão independente falhou na ferramenta de colaboração (`collab spawn failed: no thread with id`). A autorrevisão foi realizada; não se declara segunda opinião concluída.

## 10. OBSIDIAN — atualizações recomendadas, não executadas

- **Product Designer:** registrar o handoff A4.3d e a matriz de aceite visual ainda pendente, com link a este documento.
- **Social e on-chain — a linha que não atravessamos:** acrescentar atualização datada sobre o escopo documental do Meme Radar, preservando o inventário histórico e distinguindo monitoramento de execução.
- **Diário / 2026-09-12:** registrar a especificação entregue e a reconciliação pendente com o contrato T4.2/T4.3; sem declarar tela ou paper liberados.
