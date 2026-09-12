**RESUMO**

Como **quant-engineer**, testaria **M-D10 → M-P36 → M-P35**. M-D10 deve preceder qualquer **conclusão sobre rentabilidade executável**, mas não precisa bloquear a coleta prospectiva da E2. E2 continua primeira entre estratégias; M-P36 acrescenta uma feature que não pertence às exclusões originalmente propostas ([estudo:56](C:/dev/project-hunter/obsidian/03-TRADING/Meme/Estudo-2026-09-12-21-apostas.md:56)).

**M-D10 merece linha própria, vinculada a M-D7**, compartilhando coorte e replay. Correção importante: M-D7 já mede latência operacional e replay contrafactual, não apenas demora humana ([fila:129](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:129)).

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados testes nem o pacote de reprodução de Lindsey. Parecer documental, com leitura do extrato local e conferência de fontes primárias.

**MUST-FIX**

1. **M-D10: congelar o relógio e retirar “exato por carimbo” como garantia geral.** Separar marco on-chain, recebimento, disponibilidade dos insumos, decisão e chegada simulada. Definir se cada L começa no marco ou na decisão; não somar duas vezes ingestão/envio. Carimbo em segundos não resolve ordem intrasslot: exigir ordem transacional e estado anterior à inserção hipotética; ambiguidades viram limites ou desconhecidos. **Falha:** conceder compra numa curva já concluída dentro do mesmo segundo.

2. **M-D10: fixar universo e execução.** Definir evento elegível, primeira passagem/reentradas, versão da porta, tamanho, saída, horizonte, custos, participação e cobertura necessária. Publicar todos os elegíveis, inclusive os que não geraram proposta; propostas aceitas/recusadas/expiradas são outro nível do funil. Não alcançado tem **retorno bruto zero**, mas tentativa falhada pode ter custo. Reserva reconstruída produz execução **simulada sob hipóteses**, não fill comprovado. **Falha:** um filtro elimina candidatos antes da proposta e parece executável porque seus excluídos desapareceram do denominador.

3. **M-D10: comparar composição com a mesma régua.** Publicar média e mediana do fill concedido na mesma coorte; para alcançadas versus não alcançadas, usar retorno contrafactual com preço e saída comuns. Decompor separadamente acesso, composição e reprecificação na chegada. **Falha:** atribuir à seleção uma diferença criada por comparar mediana aparente com média executável ou por mudar o preço de entrada.

4. **M-P36: congelar a feature e os dois denominadores.** Fixar N, fonte/data do ranking, lista de marcas, normalização, aliases, correspondência exata/parcial, sobreposição e tratamento de ativos oficiais. Metadata tardio permanece desconhecido no minuto zero. Conclusão: todas as criações elegíveis, até criação +24 h. Retenção: migradas validadas, referência e avaliação em migração +24 h, com pool/quote/preço/tolerância fixados. A associação entre migradas é condicional, não efeito causal do nome. **Falha:** completar nomes retrospectivamente ou usar apenas graduadas para estimar conclusão. O [rascunho:138](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1637-lane4.md:138) ainda deixa essas escolhas abertas.

5. **M-P35: decil precisa existir em L.** Congelar retorno simples/log, formação dos minutos, preço, staleness, cobertura e recebimento até L. Decis operacionais devem usar distribuição histórica disponível antes de L, com janela, empates e tamanho mínimo definidos. Decil calculado sobre a hora/dia completos serve apenas à descrição retrospectiva. **Falha:** a classificação da moeda às 10:05 depende de moedas observadas às 10:55.

6. **M-P35/M-P36: morte econômica não é automaticamente censura.** Separar retirada comprovada de liquidez, ausência de negociação, falha de coleta e término administrativo. Morte comprovada entra como desfecho adverso; valor recuperável depende da liquidação definida, sem inventar −100%. Ausência de dados exige desconhecidos e análise de sensibilidade. Aalen–Johansen serve aos eventos concorrentes, não resolve sozinho retorno ausente. **Falha:** retirar os pools mortos aumenta artificialmente a retenção e o retorno dos sobreviventes. Isso corrige diretamente [rascunho:145](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1637-lane4.md:145) e [rascunho:200](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-1637-lane4.md:200).

7. **M-P35: chamar os braços de “alto MAX” e “baixo MAX”.** Baixo máximo não significa queda anterior; comprá-lo não demonstra reversão. Congelar controle, capital por oportunidade, custos e entradas posteriores à disponibilidade da feature; publicar resultado por elegível e por fill. Para orientar saída do EXP-M4, testar depois uma variante pareada **manter versus sair**, no mesmo marco e nas mesmas posições. **Falha:** promover uma seleção transversal de novas compras como evidência para trailing das posições existentes. M-P31/M-P32 já exigem contrastes operacionais separados ([fila:130](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:130)).

8. **Congelar inferência e multiplicidade antes da coleta confirmatória.** M-P36: contraste primário agregado ou categorias, retenção unicaudal e conclusão bicaudal explicitadas; modelo-base com M-P3/M-P29/M-P25 e controle por criador. M-P35: associação bicaudal e dois contrastes operacionais, incluindo qualquer interação com M-P32/EXP-M4 na família de testes. Fixar Holm, efeito mínimo, potência, prazo de encerramento e confirmação posterior com separação suficiente para maturar desfechos. Horas dentro de dias e dependência por mint/criador precisam aparecer na incerteza. **Falha:** escolher depois categoria, sinal ou latência vencedora. Os pisos de 7/14 dias não substituem a régua de promoção de 30 dias.

9. **Limitar explicitamente o que a literatura sustenta.**
   - **Lindsey:** transfere a decomposição, não o sinal negativo para E3. O limite depende de não retrocesso das reservas; os 98,3% são diagnóstico direcional, não verificação de todo o caminho. Dois dias não provam estabilidade. “Mais rápido compra pior” é composição observada, não causalidade ([extrato, §2–4](C:/dev/project-hunter/.claude/state/plantao-meme/raw-lane16/05_lindsey_alpha_without_access_text.txt)).
   - **Chen:** os 78 grupos passaram pelo corte **membros + tokens >50**; 62/78 não estima prevalência geral nem sensibilidade de M-P26/M-P28. A análise de nomes parte dos rugs e não demonstra risco incremental sem comparação com não-rugs. Mediana de vida entre rugs não determina horizonte ótimo da E4. [Chen, §V](https://arxiv.org/html/2603.24625v2).
   - **Chainalysis:** criador do **pool** não é automaticamente criador do **mint**; 94% não valida diretamente `creator_prior_mints_1h`. [Fonte](https://www.chainalysis.com/blog/crypto-market-manipulation-wash-trading-pump-and-dump-2025/).
   - **MAX:** os estudos usam inclusive janelas distintas para construir MAX. O diferencial semanal de 3,03% não é previsão de retorno absoluto, e alvo/trailing não pressupõe necessariamente momentum de MAX. [Ozdamar et al.](https://link.springer.com/article/10.1186/s40854-021-00291-9).

   **Falha comum:** transformar descrição externa em filtro ou regra de saída local sem medir seu ganho executável.

**NICE-TO-HAVE**

Reproduzir Lindsey com datas e hashes verificados, mantendo a réplica separada das portas locais.

**O QUE EU FARIA DIFERENTE**

Abriria M-D10 como diagnóstico irmão de M-D7, com uma tabela compartilhada. Coletaria M-P36 prospectivamente enquanto valido o instrumento; deixaria M-P35 por último.

**CONCORDO COM**

Separar observado/acessível/realizável; testar ganho incremental; preservar braços congelados; manter sinal desconhecido para MAX.

**OBSIDIAN**

- **Hipóteses do plantão** — registrar M-D10 próprio e os contratos corrigidos de M-P35/M-P36.
- **Estudo das 21 apostas** — distinguir prioridade do instrumento, ordem de estratégias e extensão M-P36.
- **EXP-M4 — Moonshot** — registrar MAX como motivação para futura variante pareada de saída.
- **Meme — 2026-09-12** — acrescentar limites de transferência, seleção dos grupos de Chen e tratamento de morte versus ausência de dados.