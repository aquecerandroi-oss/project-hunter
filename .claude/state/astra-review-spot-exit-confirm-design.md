**RESUMO**

**DONE_WITH_CONCERNS — concordo com confirmar o gatilho usando a própria cotação entregue à venda. Não aprovaria ainda a garantia de “stop sem espera ilimitada”.** O contador proposto não garante isso diante de reinícios, marcas indisponíveis ou inversões repetidas entre marca e confirmação.

Parecer como `risk-engine-guardian`, em modo OPINIÃO. A distinção continua sendo a registrada em [Open Bugs:50](<C:/dev/project-hunter/obsidian/07-BUGS/Open Bugs.md:50>): revalidar a cotação é correção; forçar após várias observações acrescenta uma política de saída.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Inspeção estática dos arquivos e da memória. Não executei testes, consultas à VPS ou transações.

Para a implementação, exigiria casos determinísticos para: UNI, alvo NEAR divergente, duas cotações concordantes, confirmação indisponível, horizonte vencendo durante a confirmação, inversões nos dois sentidos, reinício e preservação de tentativa/backoff.

**MUST-FIX**

1. **HIGH — saída por tempo precisa sobreviver a qualquer resultado da confirmação.**  
   Em [spot_exit_rules.py:93](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:93), stop/alvo precedem `time`.

   **Cenário:** horizonte vencido; marca diz `target`; confirmação falha ou diz `stop`. `reason2 == 'time'` nunca acontece. Se isso se repetir, o alvo fantasma continua impedindo a saída por tempo.

   **Correção proposta:** quando o gatilho não confirmar, avaliar também a saída independente de preço: `decide_exit(position, None, now_atualizado, kill, auto_close_on_emergency=...)`. Se retornar emergência, pedido manual ou tempo, executar essa saída. Recalcular o slippage pelo **motivo final** e descartar a cotação de confirmação quando incompatível. Não esquecer o parâmetro de emergência, cujo padrão é `False` ([spot_exit_rules.py:79](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:79)).

2. **MEDIUM — não consumir a tentativa antes da confirmação.**  
   Hoje `stats.exit_attempts[position.id] = attempt` ocorre antes de calcular slippage ([spot_exits.py:210](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:210)).

   **Cenário:** dois alvos descartados pela confirmação deixam o contador em 2; a primeira venda efetivamente admitida vira tentativa 3 e ganha tolerância de pânico, pois `slippage_for` usa esse número ([spot_exit_rules.py:111](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:111)).

   **Correção proposta:** calcular `candidate_attempt` localmente; só atualizar o contador quando avançar para a tentativa de venda. Descartar confirmação não pode alterar tentativa, falhas duras ou backoff.

3. **HIGH — três ticks em memória não constituem limite de atraso.**  
   O laço dorme **depois** do trabalho, portanto sua duração soma IO ao intervalo ([main.py:116](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/main.py:116)). Além disso, `_mark` devolve `None` quando falha ([spot_exits.py:174](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:174)).

   **Cenários:** reiniciar após cada segunda divergência impede atingir 3; alternar `stop, stop, marca indisponível` também impede, se ausência zerar a sequência. E marca `target` seguida de confirmação `stop`, repetidamente, nunca alimenta um contador exclusivo da primeira marca.

   **Correção proposta:** definir explicitamente um episódio de divergência com stop e seu prazo. Ausência de dado não deve significar recuperação. Se o limite precisa sobreviver a reinícios, persistir o início/prazo do episódio. “Restart acrescenta no máximo três ticks” vale **por reinício**, não como limite global.

**NICE-TO-HAVE**

- Distinguir `disagreed`, `unavailable` e `invalid_quote`, preservando motivo inicial, resultado da confirmação, horários e tipo de erro. Um único `trigger_unconfirmed:stop` perde essa distinção.
- Validar par, quantidade e saída positiva **antes** de usar a confirmação como marca. A perna já verifica identidade, mas apenas quando é chamada ([spot_send.py:139](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:139)).
- Registrar explicitamente a cotação confirmadora no pedido admitido: hoje a inserção recebe `quote=None` ([spot_exits.py:249](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:249)).
- Extrair a confirmação para um módulo pequeno. O arquivo atual termina na linha 344 ([spot_exits.py:344](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exits.py:344)); não comprimir código para caber no teto.

**O QUE EU FARIA DIFERENTE**

**a) Cobre os incidentes?**  
Cobre o mecanismo do UNI **se a confirmação vier normal**, como a recotação histórica: cancela o gatilho antes da ordem. Para o NEAR, evita a tentativa se a segunda cotação retirar o alvo; não garante evitar uma simulação recusada quando duas cotações repetem o mesmo valor anômalo. Os relatos estão em [Perdas-spot-1:83](C:/dev/project-hunter/obsidian/03-TRADING/Spot/Perdas-spot-1.md:83).

Passar `quote=` garante que a construção use a cotação confirmadora ([spot_send.py:122](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:122)); **não garante fill nem preço líquido**. A simulação continua necessária ([spot_send.py:197](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:197)).

**b) N=3, N=2 ou tempo?**  
Prefiro **prazo explícito de 60 segundos desde a primeira divergência com stop**, como orçamento operacional proposto, sem alegar que seja ótimo. Não vejo evidência para escolher N=2.

Três observações nos instantes 0, 20 e 40 representam aproximadamente **40 segundos desde a primeira**, antes de somar IO. Um prazo é mais claro; deve ser verificado com horário atualizado após os awaits. Ainda assim, significa “tentar na primeira avaliação após o prazo”, não “venda concluída em 60 segundos”.

**c) Exceção conta?**  
**Sim, deve consumir o orçamento de espera da confirmação**, mas contabilizada como indisponibilidade, não como evidência adicional de stop. Ao esgotar o prazo, liberar uma tentativa normal de saída, mantendo suas verificações.

Se Jupiter continuar fora, a perna também falhará: isso limita o atraso introduzido pelo novo portão, não resolve indisponibilidade de execução. O caminho atual já distingue falha transitória de recusa não transitória ([spot_send.py:131](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_send.py:131)).

**d) Stop ↔ target?**  
Concordo em **não executar imediatamente pelo motivo original**. Não trataria os dois sentidos como descarte sem consequência:

- `stop → target`: há divergência; contabilizar no episódio de stop.
- `target → stop`: também há evidência de stop; não pode sumir porque a primeira marca dizia alvo.

Não trocaria automaticamente o motivo usando a mesma cotação: a tolerância pode ser diferente. Se já venceu o horizonte, aplicar o fallback independente de preço.

**e) Pânico de 300 bp desde a primeira tentativa?**  
**Manteria fora do escopo desta correção.** É a política atual de stop/emergência ([spot_exit_rules.py:111](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_exit_rules.py:111)). Reduzi-la pode aumentar recusas justamente na queda real.

Mas deixaria explícito: forçar um stop com confirmação contrária pode reproduzir o UNI após o prazo. É uma escolha entre riscos, não consequência necessária da correção.

**f) Persistir além de `set_mark`?**  
**Sim, recomendo um registro durável da decisão adiada**, sem criar `spot_orders`: posição, horário, motivo inicial, duas marcas/R quando disponíveis, resultado da confirmação e erro. Se houver garantia entre reinícios, persistir também o prazo do episódio.

`set_mark` sozinho guarda apenas o estado mais recente; o próximo tick sobrescreve o motivo ([spot_repo_positions.py:95](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_repo_positions.py:95)). Não preserva a sequência necessária para explicar por que uma venda foi adiada ou forçada. Usaria o mecanismo de auditoria existente, evitando criar uma tabela específica sem necessidade.

**CONCORDO COM**

Lote inteiro, mesmo slippage da perna, cotação confirmadora reutilizada, alvo nunca forçado e nenhuma tentativa/backoff consumidos por uma confirmação descartada. Também concordo em não usar Binance como portão e preservar fechamento manual e saídas independentes de preço.

**OBSIDIAN**

Nenhuma página foi alterada. Deveriam ser atualizadas:

- **Open Bugs** — critérios de aceite, fallback por tempo e distinção entre correção e saída forçada.
- **KB-0172 — perdas da spot/1** — alcance da confirmação e ausência de garantia contra duas cotações anômalas.
- **Mesa-spot-1** — prazo, reinícios, indisponibilidade e auditoria da política escolhida.
- **Revisões-Astra — confirmação de stop/alvo spot/1** — registrar este parecer e a decisão sobre os três must-fix.