**RESUMO**

**Ainda não aprovaria a curadoria.** Os números conferem e a prioridade de `EXEC-C/F/H` é defensável. Restam resumos excessivos, dependências omitidas e um registro incompleto das correções anteriores.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO.

**TESTES**

Conferência documental das três páginas contra KB-0036–KB-0044 e os três pareceres anteriores. Não executei SQL, coleta nem suítes.

Todos os números pedidos coincidem com as notas, respeitados os arredondamentos:

| Valores | Fonte conferida |
|---|---|
| 2,30 bps; diferença de 0,30 bps na ida e volta | [KB-0037:172](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0037-o-spread-assumido-contra-o-spread-medido.md:172) |
| 2,53 / 3,47 / 6,85 / 10,65 bps; 68/200 | [KB-0036:45](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:45) |
| Medianas absolutas 14,4 / 15,0; p90 44,1 / 49,6 | [KB-0041:79](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio.md:79) |
| 19/216 `late:delay` | [KB-0041:104](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio.md:104) |
| 6/55.709 `volume_24h` | [KB-0044:84](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0044-o-que-morre-em-dez-segundos.md:84) |
| 8/200 sinais no próprio minuto | [KB-0037:59](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0037-o-spread-assumido-contra-o-spread-medido.md:59) |

Precisão sobre o último: o SQL conta **snapshots com `spread_pct` presente**, não simplesmente qualquer snapshot.

Contas executadas em PowerShell com `[decimal]`:

```text
spread_delta_roundtrip_bps=0,30
spread_delta_percent_of_20bps=1,500
not_covering_percent=34,00
late_population=216
snapshots_in_signal_minute=8/200
```

**MUST-FIX**

1. **O backlog compara grandezas diferentes na linha “Slippage”.** Os 2,53/6,85 bps apresentados como medição de slippage são **VWAP contra mid, já incluindo meio spread**, enquanto os 5 bps assumidos excluem esse componente. [Backlog:253](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:253>), [KB-0036:90](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:90).  
   **Cenário:** alguém interpreta 6,85−5 como subestimação medida do slippage. Renomear a medida e declarar a comparação não equivalente. Na mesma tabela, “espera não modelada” também excede a nota: a espera é imposta pela arquitetura e seu deslocamento já entra no preço e no R. [Backlog:256](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:256>), [KB-0041:159](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio.md:159).

2. **“A única respondível” generaliza indevidamente o inventário da KB-0044.** O índice afirma que cinco das seis perguntas são impossíveis e somente referência→entrada é respondível. A tabela correspondente tem **quatro “não”, um “sim” e um “parcialmente”**; além disso, `EXEC-C` e `EXEC-H` também são retrospectivos. [Index:251](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Index.md:251), [KB-0044:106](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0044-o-que-morre-em-dez-segundos.md:106).  
   **Cenário:** essa síntese leva a adiar os próprios diagnósticos recomendados para agora. Restringir a frase às perguntas daquele inventário e preservar a categoria parcial.

3. **A síntese transforma uma explicação mecânica consistente em causa histórica comprovada.** “A causa é” no índice e “por disputa” no registro eliminam a ressalva explícita da KB-0044: as seis linhas não foram individualmente atribuídas ao mecanismo nem à versão executada. [Index:245](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Index.md:245), [Registro:214](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Registro de Tentativas.md:214>), [KB-0044:164](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0044-o-que-morre-em-dez-segundos.md:164).  
   **Cenário:** registrar como encerrada a investigação da cobertura histórica sem verificar os registros. Manter “mecanismo consistente com a baixa cobertura”.

4. **O carimbo sozinho não entrega os cortes por decil.** O registro propõe `D-026` por decil, mas declara apenas o carimbo como bloqueio. O item 20 guarda volume individual, sem ranking ou população congelada — insuficiente segundo a própria nota. [Registro:205](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Registro de Tentativas.md:205>), [Backlog:263](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:263>), [KB-0044:143](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0044-o-que-morre-em-dez-segundos.md:143).  
   **Cenário:** carimbo completo, mas diagnóstico estratificado continua impossível. Declarar o requisito adicional ou limitar a entrega inicial à distribuição sem decil.

5. **“Inferências retiradas” está correta nos oito itens, mas incompleta.** A lista em [Registro:220](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Registro de Tentativas.md:220>) omite correções materiais:

   - **KB-0036:** adequação dos 6 bps limitada a custo estático, instante/lado e cobertura; falsa maioria sem cobertura acima de 5 mil; execução no toque e tamanho como único determinante.
   - **KB-0037:** 0,15→0,30 na ida e volta; falsa garantia pelo p90; monotonicidade, predominância entre mercados e causalidade do filtro não demonstradas.
   - **KB-0038:** tarifas de exemplo versus efetivas; execução sintética não prova taker; 51 bps é denominador de exemplo; drift absoluto não explica expectancy.
   - **KB-0039:** MARKET/preenchimento garantido; amplitude validando simetria; stop-primeiro mais slippage como dupla penalização.
   - **KB-0040:** autoria Emilio Said; dependência da velocidade; tabela raiz quadrada versus book e limites de capacidade indevidos.
   - **KB-0041:** geometria não prova deterioração; perspectiva invertida do stop; seleção das entradas; poder da H2 e causalidade dos grupos 60/120 s; “um a três níveis”; ressalva incorreta sobre o JOIN.
   - **KB-0042:** sinal desconhecido não implica simetria; spread não limita universalmente o erro; mediana/IQR não demonstram ausência de viés; `open` fora do book não prova atraso; conversão linear de segundos em bps.
   - **KB-0043:** perspectiva passiva do markout; transporte indevido de magnitudes; retorno contra `P_entry` contaminado pelos 6 bps; seleção pelos stops; mediana zero não encerra seleção adversa; poder presumido sem cálculo.
   - **KB-0044:** TTL não é histórico; snapshots não são permanentes; carimbo não fornece ranking nem mid posterior; `EXEC-H` independe dele; observação posterior não pode reescrever o envelope.

   Essas correções estão nos [primeiro](C:/dev/project-hunter/.claude/state/astra-review-KB-0036-0038-execucao.md), [segundo](C:/dev/project-hunter/.claude/state/astra-review-KB-0039-0041-execucao.md) e [terceiro parecer](C:/dev/project-hunter/.claude/state/astra-review-KB-0042-0044-execucao.md). **Cenário:** uma sessão futura consulta o registro como memória dos erros e reintroduz critérios já rejeitados. Pode-se completar com resumos e links, sem duplicar os pareceres.

**NICE-TO-HAVE**

O backlog anuncia **uma** correção de contrato, mas lista duas: tamanho e carimbo. Harmonizar com o índice e o registro. [Backlog:243](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:243>).

**O QUE EU FARIA DIFERENTE**

Manteria a ordem proposta, escrevendo “sem nova coleta para o diagnóstico básico”, em vez de “sem pré-requisito nenhum”. `EXEC-H` exige entradas identificadas e cobertura das velas; seu corte por decil tem uma dependência adicional.

**CONCORDO COM**

- **`EXEC-C`, `EXEC-F` e `EXEC-H` primeiro:** defensável para suas versões descritivas básicas. `EXEC-D` também não exige nova coleta; deixá-lo depois se justifica pela menor informação sobre execução, não por dependências. [Backlog:270](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:270>).
- **Classificação:** tamanho e carimbo são mudanças de contrato/proveniência; os nove itens são diagnósticos. Post-only permanece explicitamente adiado. Não encontrei troca material entre candidata de estratégia e contrato. [Backlog:258](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:258>).
- As nove linhas novas da tabela de notas, o tema novo e a tabela de fontes indisponíveis preservam as qualificações das notas; não encontrei ali exagero adicional.

**OBSIDIAN**

- **Conhecimento — índice:** restringir a conclusão sobre retrospectividade e preservar a ressalva causal.
- **Strategy Backlog:** distinguir slippage de VWAP contra mid, explicitar dependências e corrigir a contagem de contratos.
- **Registro de Tentativas:** completar as inferências retiradas e registrar o requisito de ranking para decis históricos.