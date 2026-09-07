**RESUMO**

**As sete correções não estão integralmente fechadas.** D e F fecham os cenários apontados; B fecha a troca das referências, inclusive a referência durável de outro dia. A, C, E e G ainda têm brechas.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Revisão estática do código e dos testes existentes. Não executei testes; os cenários abaixo são deduções dos caminhos citados.

**MUST-FIX**

- [daily.py:204](C:/dev/project-hunter/packages/core/hunter_core/risk/daily.py:204) — **ALTA — A: aceitar até 300 s antes não prova patrimônio de meia-noite.** Cenário: último snapshot às 23:55 = 19.500; patrimônio real à meia-noite = 20.000; às 00:00:30 = 19.500. A abertura aceita é 19.500, a perda diária calculada é zero e o drawdown contra pico 20.000 é 2,5%, abaixo até do aviso de drawdown. Uma perda diária real de 2,5% deixa de bloquear. Isso também contradiz a promessa de *“measurement of midnight”* em [daily.py:8](C:/dev/project-hunter/packages/core/hunter_core/risk/daily.py:8). **300 s é defensável como convenção aproximada explicitamente aprovada; não como garantia de medição da virada.** Apenas reduzir a janela não elimina a classe de erro.

- [resume.py:118](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:118) — **ALTA — C: `state=` continua contornando a comparação com a transição.** Cenário: estado às 12:00:00 = 20.000; bloqueio às 12:00:30 com 19.500; retomada às 12:00:31 entrega aquele estado. `_latched_since` é chamado, mas `blocked_at` só chega a `_from_curve`. `_anchored` aceita os 31 s de idade, reancora em abertura/pico 20.000 e permite ACTIVE sem recuperação. A promessa de provar o fim do gatilho em [resume.py:5](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:5) ainda não vale nesse caminho.

- [resume.py:273](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:273) — **ALTA — C: igualdade de timestamps é aceita; “posterior” não está implementado.** Cenário: snapshot favorável e avaliação bloqueante recebem o mesmo timestamp de ciclo, embora representem observações distintas. A retomada aceita o snapshot porque a recusa usa `<`, não `<=`. Isso contraria *“taken after the block”* em [resume.py:259](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:259).

- [resume.py:229](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:229) — **ALTA — B/E: a retomada aceita `marks_complete=False`.** Cenário: abertura/pico duráveis 20.000; carteira bloqueada; estado posterior à transição informa equity 20.000, mas contém posição sem preço atualizado e marcação incompleta. `_anchored` não recusa essa condição; [assess:97](C:/dev/project-hunter/packages/risk-core/hunter_risk/kill_switch.py:97) calcula apenas perda e drawdown, permitindo destravar. A proteção adicionada à avaliação periódica não cobre a retomada.

- [kill_switch.py:152](C:/dev/project-hunter/packages/core/hunter_core/risk/kill_switch.py:152) e [resume.py:229](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:229) — **ALTA — E: `abs` admite observações futuras dentro da tolerância.** Cenário: agora 12:00, carteira bloqueada e valendo 19.500; o chamador fornece estado carimbado 12:01 com equity 20.000. A retomada aceita a recuperação futura. Na avaliação periódica, também passa um estado até 60 s à frente. O filtro temporal de D fecha as consultas da curva, mas não esses argumentos.

- [routers/risk.py:118](C:/dev/project-hunter/apps/api/hunter_api/routers/risk.py:118) — **MÉDIA — G: referência preenchida de ontem continua sendo publicada como disponível hoje.** Cenário: worker parado durante a virada; trava ACTIVE; `equity_day_start` de ontem permanece preenchida. O GET retorna `available=true` e `blocks_entries=false`, embora não exista referência válida para hoje. Falta confrontar o início do dia persistido com o dia atual, como a retomada já faz.

**NICE-TO-HAVE**

- [resume.py:246](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:246) — **BAIXA — o docstring promete o mesmo pico na avaliação e na evidência, mas os valores podem divergir.** Cenário: pico durável 20.000, equity recuperada 21.000. A avaliação usa pico 21.000; a transição registra 20.000 em [resume.py:162](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:162). Não altera o drawdown zero nesse cenário, mas descumpre a igualdade prometida em [resume.py:222](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:222).

**O QUE EU FARIA DIFERENTE**

Aplicaria uma validação comum às duas fontes da retomada: carteira correta, marcação completa, `blocked_at < observed_at <= now`, idade máxima e referência durável do dia atual. Manteria o instante original da observação até a auditoria.

**CONCORDO COM**

| Correção | Confirmação |
|---|---|
| **A** | Fecha a adoção de amostra posterior à virada; ausência de referência preserva a trava: [daily.py:202](C:/dev/project-hunter/packages/core/hunter_core/risk/daily.py:202), [kill_switch.py:287](C:/dev/project-hunter/packages/core/hunter_core/risk/kill_switch.py:287). Resta a aproximação anterior à virada. |
| **B** | Fecha pico/abertura escolhidos pelo chamador. **Sim: referência durável de outro dia é recusada nos dois caminhos**, pois ambos passam por `_anchored`: [resume.py:117](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:117), [resume.py:239](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:239). |
| **C** | Fecha snapshot estritamente anterior no caminho da curva; restam o desvio por `state=` e a igualdade. |
| **D** | Fecha resolução divergente e timestamp futuro nas duas consultas: [curve.py:52](C:/dev/project-hunter/packages/core/hunter_core/risk/curve.py:52), [curve.py:73](C:/dev/project-hunter/packages/core/hunter_core/risk/curve.py:73). |
| **E** | Fecha estado com idade superior a 60 s ou marcação incompleta na avaliação periódica: [kill_switch.py:152](C:/dev/project-hunter/packages/core/hunter_core/risk/kill_switch.py:152). Resta futuro dentro da janela. |
| **F** | Fecha a corrida descrita: o helper adquire a mesma trava antes de escrever: [transitions.py:166](C:/dev/project-hunter/packages/core/hunter_core/risk/transitions.py:166), [scopes.py:93](C:/dev/project-hunter/packages/core/hunter_core/risk/scopes.py:93). |
| **G** | Fecha referência nula com switch ACTIVE: [routers/risk.py:127](C:/dev/project-hunter/apps/api/hunter_api/routers/risk.py:127). Resta referência preenchida de outro dia. |

**OBSIDIAN**

- **Risk Engine** — registrar as brechas temporais e de completude restantes na retomada.
- **Portfolio** — distinguir abertura medida na virada de aproximação por amostra anterior.
- **Open Bugs** — registrar os cenários remanescentes e seus testes de regressão.
- **Revisoes-Astra/Index** — indexar esta segunda rodada da T3.6.