---
tags: [astra, revisao]
updated: 2026-09-05
fonte: .claude/state/astra-review-design-T1.5b.md
---

# Revisão da Astra — design-T1.5b

Parte da [[Mente da Sexta-feira]]. Índice: [[Index|todas as revisões]]. Diálogos relacionados: [[Dialogos/M1|M1]], [[Dialogos/M2|M2]].

Minha opinião como Astra: **a direção tem bons fundamentos, mas o brief confunde acabamento com adicionar elementos.** A percepção de qualidade aumentará mais com hierarquia, estabilidade e clareza sobre os dados do que com mais chips, animações e gráficos.

Li os arquivos solicitados. Esta é uma avaliação do código e da proposta, sem validação visual no navegador. Não abri `.env` nem modifiquei arquivos.

**O primeiro problema é prometer uma experiência que os dados atuais não sustentam.** Em `market-detail-view.tsx`, book e trades são snapshots; o tempo real atualiza preço/bid/ask e timestamps. `derivatives-card.tsx` explicita que não há index price nem horário do próximo funding no contrato atual. Portanto, fita autoatualizada, index e countdown precisam sair deste escopo ou ter sua viabilidade demonstrada. Animar snapshots criaria aparência de atividade sem atividade real.

**Hierarquia e densidade.** O dashboard proposto começa com infraestrutura, continua com organização/membros e termina com funcionalidades futuras. Para quem quer explorar mercados, parece um console administrativo em construção. Eu colocaria acesso a Markets e cobertura disponível primeiro; saúde resumida depois; diagnóstico em System. Removeria os cards vazios de equity/PnL: “chega no M3” é honesto, mas continua ocupando espaço com ausência, contrariando a preferência de PRODUCT por estados vazios em vez de placeholders.

Concordo com 40px como densidade confortável, mantendo 32px no modo compacto. Hoje `globals.css` compacta principalmente espaçamentos externos; a tabela continua com altura fixa. Alterar apenas o CSS para 40px, deixando `ROW_HEIGHT = 32`, desalinhará a virtualização. Manteria a grade de 4px existente, usando 8px nos agrupamentos maiores. Sete tamanhos tipográficos e outra fonte para números grandes acrescentam decisões sem garantir beleza.

**Dourado e números.** O gráfico já usa candles dourados. Somar marca, seleção, filtros, foco e destaques faria o dourado dominar a tela, contrariando “dourado é raro”. Eu escolheria candles verdes/vermelhos e reservaria dourado para marca, ação principal e estado ativo. Se candles dourados forem identidade indispensável, reduziria seus outros usos.

Preço merece maior contraste; variação, segundo nível; bid/ask, funding e OI podem ficar no detalhe ou em colunas opcionais. Chips em todas as células quebram a leitura vertical. Manteria números tabulares, alinhamento à direita, precisão consistente por instrumento e unidade explícita no cabeçalho. Exemplo ruim: comparar dois ativos baratos arredondados visualmente a zero. Volume abreviado precisa oferecer valor completo por foco/toque; zero e ausência devem ser neutros — hoje a variação ausente recebe a classe verde.

**Motion e fadiga.** Vinte preços piscando, ponto pulsante, shimmer e relógio em milissegundos disputam atenção permanentemente. Eu retiraria o pulso de conexão saudável e usaria segundos nas idades. Flash apenas no fundo da célula, somente quando o valor mudar, com frequência limitada e opção de desligar. `prefers-reduced-motion` é necessário, mas não substitui uma experiência calma por padrão. Uma futura fita precisa de botão persistente “Pausar”; hover não atende toque nem teclado.

**Staleness sem alarmismo.** Preservaria as idades por componente e os limites fornecidos pela API. Mas “CONNECTED” não prova dado fresco, nem falta de verificação prova queda: hoje `topbar.tsx` transforma status ausente em indisponibilidade. Mostraria “Sem verificação” separadamente.

Cenário concreto: o preço muda, mas o book exibido continua sendo o snapshot inicial. Um badge agregado saudável pode induzir confiança no book errado. Cada painel precisa identificar sua própria atualização e natureza: “Snapshot · há 2 min”. Funding antigo também não deve receber severidade de ticker sem considerar a regra do componente. Idade permanece visível; explicações adicionais ficam em popover acessível.

**Busca, sparklines e estados.** Concordo com command palette, desde que exista botão visível “Buscar mercados”, resultados com exchange e navegação por teclado. A busca atual cobre somente os itens carregados; não pode parecer global. Também não transformaria totais globais em filtros locais sem explicitar essa diferença.

Carregamento lazy de sparklines reduz a rajada inicial, mas percorrer 200 mercados ainda pode gerar **200 chamadas a `/candles`**. Eu adiaria. Se mantidas: concorrência limitada, cancelamento, cache compartilhado e atualização compatível com candles fechados; nunca bloquear a tabela. Sessenta candles precisam indicar “1h”, para não parecerem explicar a variação de 24h.

Vazio não comprova worker parado. Separaria “Nenhum resultado”, “Nenhum mercado monitorado” e falha de carregamento, com ação pertinente.

**Acessibilidade, claro e mobile.** Concordo com foco visível, revisão nos dois temas e ausência de transições de página. Acrescentaria contraste sobre fundos realmente compostos, metadados legíveis, foco preservado na virtualização e horários acessíveis sem hover. Hoje trades usam horário local, apesar da regra UTC do brief. No celular, empilhar tudo mantém excesso: priorizaria símbolo, preço, variação e qualidade, com detalhes expansíveis e alvos confortáveis.

Minha prioridade por ganho de qualidade/custo:

1. Corrigir promessas incompatíveis com os dados atuais.
2. Diferenciar snapshot, conexão e frescor.
3. Simplificar hierarquia e retirar placeholders financeiros.
4. Padronizar precisão, unidades e alinhamento numérico.
5. Reduzir dourado e chips repetidos.
6. Remover pulso saudável e relógios em milissegundos.
7. Melhorar mensagens vazias, erros e recuperação.
8. Corrigir contraste, foco e acesso por toque.
9. Aplicar densidade coerente e colunas essenciais no mobile.
10. Adiar sparklines e priorizar busca clara e confiável.