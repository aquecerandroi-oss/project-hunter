## RESUMO

**REQUEST_CHANGES antes de DONE.** Não encontrei caminho concreto de tenant leak nem erro no desempate do cursor. Os bloqueios são: `WARNING` interpretado como bloqueio, contrato contraditório de `risk_blocked`, regime antigo apresentado como fresco e ausência do 503 exigido.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisão somente leitura dos arquivos do T2.6 e suas dependências.

## TESTES

Não executei testes nesta revisão. Os **85 testes passando são evidência informada por você**, não revalidada aqui. Inspecionei código, fixtures e diff.

## MUST-FIX

1. **HIGH — `WARNING` não bloqueia entradas.**  
   [radar_org_derivation.py:104](/C:/dev/project-hunter/apps/api/hunter_api/services/radar_org_derivation.py:104) e linha 110 tratam qualquer estado diferente de `ACTIVE` como bloqueio. Porém [RISK_ENGINE.md:101](/C:/dev/project-hunter/docs/RISK_ENGINE.md:101) permite entradas em `WARNING`, com tamanho × 0,5.  
   **Cenário:** organização ou portfolio entra em `WARNING`; todas as oportunidades passam a `risk_blocked=true` e aparecem no filtro `RISK_BLOCKED`, incorretamente. Usar explicitamente `TRADING_DISABLED`/`EMERGENCY`.

2. **MEDIUM — o contrato de `risk_blocked` não está coerente.**  
   [schemas/radar.py:15](/C:/dev/project-hunter/apps/api/hunter_api/schemas/radar.py:15) promete sistema/org/portfolio e “nunca false”; [radar_org_derivation.py:96](/C:/dev/project-hunter/apps/api/hunter_api/services/radar_org_derivation.py:96) consulta apenas org/portfolios e retorna `False` na linha 117.  
   **Cenário:** consumidor segue a documentação e interpreta `false` como avaliação mais ampla do que realmente ocorreu. Além disso, um portfolio bloqueado faz todas as oportunidades receberem `true`, mesmo existindo outro portfolio liberado. O significado precisa declarar essa agregação.

3. **HIGH — regime aberto pode ficar eternamente “fresco”.**  
   [services/regime.py:26](/C:/dev/project-hunter/apps/api/hunter_api/services/regime.py:26) calcula `is_stale` exclusivamente por `end_time`.  
   **Cenário:** scanner cai depois de gravar um regime com `end_time=NULL`; amanhã a API continua retornando `is_stale=false`. É necessário frescor da última avaliação/atividade, sem confundir duração legítima do regime com atualização do classificador.

4. **MEDIUM — falta o 503 de Postgres exigido pelo brief.**  
   A leitura em [repositories/radar.py:233](/C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:233) propaga a falha; [errors.py:199](/C:/dev/project-hunter/apps/api/hunter_api/errors.py:199) converte exceções não tratadas em 500.  
   **Cenário:** conexão do Postgres indisponível → 500 em vez do 503 exigido em [brief-T2.6-radar-api.md:13](/C:/dev/project-hunter/.claude/state/brief-T2.6-radar-api.md:13). A dívida do M1 não elimina o requisito explícito do T2.6.

## NICE-TO-HAVE

- **Ponto 2 — sentinelas:** não há colisão plausível com score 0–100 ou seu delta. `atr_14_pct` participa do filtro, **não da ordenação com sentinela**: [radar.py:110](/C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:110), [radar.py:194](/C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:194). Já volume relativo não tem teto: divide pelo volume histórico, recusando apenas denominador zero em [volume.py:84](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/volume.py:84). Um volume atual de 1 contra mediana `0.000000001` produz `1e9`: em ASC, o NULL sentinela aparece antes dele. É extremo; não o elevaria sozinho a bloqueio. Preferiria chave explícita de nulidade.
- **Ponto 3 — cobertura:** adicionar empate, ASC, volume e NULLs. O teste atual usa scores distintos `30/40/50`: [test_radar_api.py:341](/C:/dev/project-hunter/apps/api/tests/integration/test_radar_api.py:341).
- A lista de oportunidades busca tudo antes de paginar: [opportunities.py:174](/C:/dev/project-hunter/apps/api/hunter_api/repositories/opportunities.py:174). Episódios expirados acumulam; a quantidade de linhas não fica limitada ao universo monitorado.

## O QUE EU FARIA DIFERENTE

**Ponto 6:** manteria `false` somente para um predicado explicitamente definido como “há bloqueio conhecido de kill switch na org ou em algum portfolio”. Para “esta oportunidade está bloqueada pelo risco efetivo”, prefiro `null` sem avaliação suficiente. Não mudaria silenciosamente o significado desse campo quando chegar o M4.

**Ponto 5:** fecharia o envelope com T2.4/T2.5 e acrescentaria teste do caminho JSON de volume/volatilidade agora. A suposição documentada é razoável; ainda não equivale a contrato integrado.

## CONCORDO COM

1. **RLS/tenant:** `org_id` na query não enfraquece a autorização. A membership ativa é verificada antes da derivação ([radar_org_derivation.py:54](/C:/dev/project-hunter/apps/api/hunter_api/services/radar_org_derivation.py:54)); a leitura usa `tenant_session` e predicados explícitos de organização nas linhas 74, 88, 100 e 109. Os routers reutilizam essa validação. Sem `org_id`, os campos permanecem nulos ([services/radar.py:55](/C:/dev/project-hunter/apps/api/hunter_api/services/radar.py:55), [services/opportunities.py:49](/C:/dev/project-hunter/apps/api/hunter_api/services/opportunities.py:49)). **Nenhum leak concreto identificado.**

2. **Decimal/UTC:** o cálculo e a ordenação usam expressões numéricas, sem conversão explícita para float ([radar.py:107](/C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:107)); timestamps do modelo usam `TIMESTAMP(timezone=True)` ([base.py:37](/C:/dev/project-hunter/packages/core/hunter_core/db/base.py:37)). Nenhuma violação concreta identificada nesses caminhos.

3. **Empates:** `ORDER BY(sort_value,id)` e comparação estrita da mesma tupla estão alinhados nos dois sentidos ([radar.py:213](/C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:213)). **Empate sozinho não duplica nem pula linhas.** Não garante snapshot entre requests: score 90 já entregue que cai para 70 pode reaparecer depois do cursor 80; score 70 que sobe para 90 pode ser pulado.

4. **Mercado sem oportunidade:** confirmado. Os joins internos exigem oportunidade; o único outer join é com regime ([radar.py:171](/C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:171), [opportunities.py:136](/C:/dev/project-hunter/apps/api/hunter_api/repositories/opportunities.py:136)). Não há inversão desse relacionamento.

5. **Envelope:** não encontrei formato alternativo já decidido. `values[key].value` corresponde ao produtor; apenas corrigiria a referência: `as_wire()` ainda contém `Decimal`, enquanto `as_json()` entrega a representação JSON canônica ([vector.py:213](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/vector.py:213), linha 229). O nível externo `"features"` continua sendo a suposição registrada.

## OBSIDIAN

- **System Overview** — registrar endpoints T2.6, autorização opcional por org e limites da paginação.
- **Features** — registrar contrato acordado do envelope e serialização canônica.
- **Risk Engine** — esclarecer `WARNING`, escopo e significado de `risk_blocked` no M2.
- **Revisoes-Astra/Index** — indexar esta revisão e os quatro bloqueios antes de DONE.