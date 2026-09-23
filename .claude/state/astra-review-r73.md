**RESUMO**

**Eu não rodaria o R73 ainda.** A guarda protege o cálculo, mas a cobertura não prova completude e o numerador não mede estoque vendável. Revisão como `quant-engineer`, somente leitura.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executei testes nem o estudo. Pela leitura, há uma falha determinística em [test_load.py:128](C:/dev/project-hunter/.claude/state/r73/test_load.py:128): em `T0+6s`, a fixture soma **21 SOL**, e nada muda até `+7s`; comparar com **16 SOL** retorna falso. O comentário também antecipa uma venda que ocorre em `+8s`.

**MUST-FIX**

1. **Antecipação pela seleção — pergunta 1.** Com `guard=True`, não encontrei caminho de informação futura para `pct`: ambas as condições precedem as somas ([load.py:123](C:/dev/project-hunter/.claude/state/r73/load.py:123)). Porém, a cobertura ignora `received_at` e aceita eventos até a foto **+1 segundo** ([load.py:158](C:/dev/project-hunter/.claude/state/r73/load.py:158)).

   **Cenário:** foto conhecida de 20 SOL, fita disponível soma 10; depois chega uma compra antiga de 10. A decisão passa de excluída para incluída, embora seu conhecimento histórico não tenha mudado. Isso **não altera diretamente a feature**, mas torna a população dependente de informação posterior. É defensável como auditoria retrospectiva, explicitamente condicionada à qualidade recuperada; não como prova de elegibilidade observável na decisão. Separe diagnóstico retrospectivo de cobertura disponível naquele instante.

2. **Líquido em SOL não é estoque — pergunta 3.** A soma implementada é fluxo financeiro líquido ([load.py:131](C:/dev/project-hunter/.claude/state/r73/load.py:131)).

   **Cenários sintéticos:** compra 1 milhão de tokens por 9 SOL, vende metade por 9: líquido zero, **500 mil tokens ainda vendáveis**. Compra por 9 e vende tudo por 4: líquido +5, **estoque zero**. Portanto, nem líquido nem bruto medem diretamente “dono que pode afundar”. Bruto mede compras históricas; líquido mede contribuição líquida de SOL. Para capacidade de despejo, prefiro saldo de **tokens**, valorizado pela venda na curva, com transferências tratadas ou limitação explícita.

   Além disso, [H-010:125](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:125>) registra **soma de compras**, enquanto o carregador declara compras menos vendas. Registre a alteração antes de correr.

3. **Reservas coincidentes não provam fita completa — pergunta 4.** A certificação usa somente o saldo agregado ([load.py:238](C:/dev/project-hunter/.claude/state/r73/load.py:238)).

   **Cenário:** faltam compra de A por 10 SOL e venda de B por 10. A reserva continua exata, mas os saldos por carteira estão errados. Uma foto antiga também não detecta buracos entre ela e a decisão. A banda tem outro problema: resume dois extremos, não os estados intermediários; um salto 10→30 aceita foto de 20 mesmo sem esse estado existir. Trate isso como **reconciliação necessária, insuficiente para completude**; exija evidência independente de coleta contínua desde o nascimento.

4. **O veredito automático não reproduz a refutação de H-010.** Com direção `low`, o contraste vira baixo−alto: a refutação registrada exige **IC superior < +0,01**, enquanto o moinho compara com `minimum_effect`, que seria **+0,05** ([verdict.py:127](C:/dev/project-hunter/infra/research/verdict.py:127)).

   **Cenário:** IC `[+0,02; +0,04]` vira `REFUTA` no moinho, mas não satisfaz H-010. Não publique esse rótulo como cumprimento do pré-registro sem ajustar a regra.

**NICE-TO-HAVE**

**Testes faltantes — pergunta 6:** invariância da **inclusão e do contraste**, não apenas de `pct`, ao acrescentar compras/vendas atrasadas; igualdade exata no corte e corte +1 microssegundo; evento futuro dentro da banda; buraco após quote antiga; omissões compensatórias entre carteiras. Os testes atuais verificam antecipação do valor isolado ([test_load.py:60](C:/dev/project-hunter/.claude/state/r73/test_load.py:60)).

**O QUE EU FARIA DIFERENTE**

- **Denominador — pergunta 2:** prefiro reconstrução guardada **se houver completude demonstrada**. Ela mantém numerador e denominador no mesmo corte. Sem isso, é “saldo observado”, não reserva real: perder compras reduz o denominador; perder vendas aumenta. A quote é uma âncora independente, mas mistura instantes quando antiga. Melhor: foto comprovadamente disponível + deltas posteriores disponíveis, alinhados por slot, sem duplicação.

- **Taxas — pergunta 4:** no caminho `TradeEvent`, `sol_amount` é separado das taxas ([trade_event.py:119](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/trade_event.py:119)). Entretanto, outro caminho persiste `amountSol` da Swap API ([swap_api.py:234](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/swap_api.py:234)); isso sozinho não prova equivalência. Validaria eventos contra deltas de reservas por origem. R62/R64 partiam de reservas ancoradas, não demonstravam completude desde zero ([r64/load.py:103](C:/dev/project-hunter/.claude/state/r64/load.py:103)).

- **Contraste — pergunta 5:** retirar o meio não invalida por si só IC/permutação, com cortes definidos sem desfechos, uma decisão por mint e permutabilidade dentro dos estratos. A inferência fica condicionada aos extremos/cortes fixados; o bootstrap atual não reestima tercis ([resampling.py:98](C:/dev/project-hunter/infra/research/resampling.py:98)). **Não use vários limiares dentro do vazio central para provar planalto:** todos selecionam as mesmas pessoas, mas o detector conta limiares, podendo certificar estabilidade artificial ([stats.py:236](C:/dev/project-hunter/infra/research/stats.py:236)).

**CONCORDO COM**

Dupla guarda temporal, exclusão da nossa carteira somente do numerador e diagnóstico separado das chegadas atrasadas ([load.py:123](C:/dev/project-hunter/.claude/state/r73/load.py:123)).

**OBSIDIAN**

- **Fila de Hipóteses:** explicitar bruto/líquido/estoque, cobertura observável e regra de refutação.
- **Revisões-Astra / R73 — revisão pré-execução:** registrar os contraexemplos e testes exigidos antes da execução.