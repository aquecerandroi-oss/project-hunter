## RESUMO

**Recomendo corrigir a persistência da saída, mas não considero demonstrado o ganho de +0,011 SOL dessa correção nem mudaria o padrão da escada para 2 com esta medição.** São decisões separadas.

O defeito está confirmado: `_manage_locked` retorna quando `decide_exit` não produz motivo, antes de consultar a tentativa pendente e seu backoff. Isso explica o mecanismo descrito em GAMON. [exits.py:160](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:160)

Quanto a AIRAA, **os números apresentados sustentam que ampliar a tolerância não teria evitado a perda principal**. Não sustentam atribuí-la aos 6,4 segundos de espera.

Revisão como `risk-engine-guardian`, em modo OPINIÃO. Os números da VPS são evidência fornecida por você; não os reproduzi nesta sessão.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executei testes nem consultas à VPS. Fiz leitura estática do código, contratos, memória dos módulos e notas R62/R64.

## MUST-FIX

**1. Separar o ganho de “pânico na primeira tentativa” do ganho de “retentar no horário devido”.**

Os +0,011037 de GAMON pertencem ao primeiro contrafactual apresentado. O ponto 1 conserva os 500 bps e envia **outra tentativa, em outro instante, com outra cotação**. Seu benefício ainda precisa ser calculado.

**Cenário de falha:** a retentativa pontual a 500 bps também falha; o relatório promete recuperar +0,011 SOL que só seria obtido aceitando a primeira venda a 1500 bps. O mesmo GAMON sustenta os +0,0030 da escada, portanto os benefícios também **não podem ser somados automaticamente**.

A correção continua justificada pelo defeito de execução, independentemente desse valor.

**2. Não definir “saída pendente” apenas por `exit_intent.failed`.**

A falha imediata grava `failed` e `next_attempt_at`; a reconciliação trata o resultado confirmado, mas não faz essa mesma transição da intenção quando descobre uma falha. [exits.py:319](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:319), [exit_settle.py:44](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exit_settle.py:44)

**Cenário de falha:** envio fica `submitted_unconfirmed`; depois, a reconciliação descobre 6003 ou expiração. O preço está na banda morta. Como não existe `exit_intent.failed`, a correção proposta continua abandonando a saída. Uma queda do processo entre registrar a falha da ordem e atualizar a intenção produz problema semelhante.

O contrato deve reconstruir a pendência pela **intenção e pelo estado durável da ordem**, preservar o motivo original e reconciliar uma tentativa incerta antes de autorizar outra. O bloqueio atual contra novas tentativas enquanto há ordem pendente deve ser preservado. [exits.py:211](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:211)

**3. O teto precisa impedir envios por todos os caminhos e sobreviver ao reinício.**

`mark_blocked` grava um motivo e atualiza o contador, mas `route_exit` não consulta esse bloqueio antes de enviar. A rota migrada também sai para PumpSwap antes dos controles locais de tentativa. [exit_common.py:108](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exit_common.py:108), [exits.py:205](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:205)

**Cenário de falha:** o tick atinge o teto e marca bloqueado; o próximo evento dispara uma regra e envia novamente. Ou o reinício perde um bloqueio mantido apenas em memória.

Definir antes de implementar: contagem durável, teto comum às rotas, reconciliação permitida mesmo após o teto e procedimento explícito de retomada. **Bloqueado significa ainda exposto**, não saída concluída.

**4. Corrigir a atribuição contábil e a narrativa de AIRAA.**

“Esperar deu +0,0014 pela recuperação” não pode permanecer como explicação se essa diferença veio de comparar um fluxo com reembolso de rent contra outro sem reembolso. O valor corrigido informado, **+0,000078 para sair antes**, é positivo pontualmente, mas pequeno demais para estabelecer um efeito diante da incerteza temporal.

**Cenário de falha:** uma diferença de transferência de rent vira evidência de recuperação de preço e orienta a política de saída no sentido errado.

A ficha atual ainda diz que os 6,4 segundos custaram a maior parte da perda e descreve uma escada de pânico. [Ficha:58](C:/dev/project-hunter/obsidian/03-TRADING/Meme/Ficha-2026-09-23-mesa-real.md:58), [Ficha:26](C:/dev/project-hunter/obsidian/03-TRADING/Meme/Ficha-2026-09-23-mesa-real.md:26) No código consultado, a tolerância depende somente do motivo. [send_tuning.py:88](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/send_tuning.py:88)

## NICE-TO-HAVE

Persistir, por tentativa: motivo original, horário da decisão original, horário e slot da cotação, líquido cotado, piso enviado, tolerância aplicada, início real do envio, resultado e próximo horário elegível.

Isso permitiria decompor a perda entre **movimento anterior à decisão, envelhecimento da cotação, execução e espera indevida**, sem depender de aproximações posteriores.

## O QUE EU FARIA DIFERENTE

**(a) O viés temporal não invalida tudo, mas impede tratar o resultado como fill garantido.**

Incluir negócios posteriores do mesmo segundo é pessimista **quando eles pioram a cotação**. Compras posteriores podem melhorar a cotação e produzir um falso “teria pousado”. Portanto, o viés não tem direção garantida.

Além disso:

- `líquido ≥ piso` demonstra compatibilidade com a restrição de preço naquele estado; não demonstra inclusão e sucesso da transação.
- Uma falha na simulação não tem pouso observado. O horário hipotético precisa ser identificado separadamente.
- `settled_at` é o horário de registro do estado terminal, não uma medição direta da execução na cadeia. [journal_db.py:62](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/journal_db.py:62)
- Sensibilidade de −1/−2 segundos é útil, mas não constitui intervalo de confiança nem resolve a ordenação dentro do segundo.

Eu calcularia o resultado nas posições possíveis da transação dentro da janela ambígua: **passaria sempre, falharia sempre ou indeterminado**. Usaria a ordem real das transações quando disponível.

O defeito da banda morta independe desse viés. Já os pequenos ganhos de AIRAA/EQUITITTY são especialmente frágeis: “bater no quarto decimal” está numa escala próxima dos próprios benefícios alegados.

**(b) É honesto mudar o padrão?**

É honesto dizer: **“a amostra não estabelece retorno esperado; escolhemos priorizar liquidação e aceitar maior tolerância como política de risco”**.

Não é consistente descartar +0,0138 por insuficiência de evidência e apresentar +0,0030, concentrado em GAMON, como comprovação do novo padrão.

Minha recomendação:

- Corrigir a continuidade da intenção.
- Manter inicialmente a escada desativada (`=0`).
- Avaliar `=2` separadamente, ou adotá-la por decisão explícita sua sobre prioridade de liquidação, sem anunciar ganho comprovado.

Também deixaria explícito: **15% é tolerância contra a cotação de cada tentativa**, não limite de perda desde a entrada ou desde a primeira decisão. Recotar sucessivamente permite perdas acumuladas maiores.

**(c) Reavaliar as regras antes de reenviar?**

**Reavaliar para atualizar contexto e rota, sim; exigir novo gatilho para manter a saída, não.** Isso recriaria exatamente a banda morta.

Acima do alvo, a própria regra atual já manda vender. [exits.py:92](C:/dev/project-hunter/packages/risk-core/hunter_risk_meme/exits.py:92) O dilema verdadeiro é a recuperação **para dentro da banda**, onde nenhuma regra dispara.

Eu definiria: uma decisão de liquidar permanece válida até confirmação, cancelamento explícito ou bloqueio operacional. A cotação é renovada; a decisão original não desaparece porque a tentativa falhou. A posição estava **com saída decidida**, nunca “vendida”.

**(d) Medições que podem mudar a decisão**

A principal é um replay com quatro braços:

| Braço | Retentativa independente de novo gatilho | Escada |
|---|---|---|
| Atual | Não | Atual |
| Correção isolada | Sim | Atual |
| Escada isolada | Não | Desde a tentativa 2 |
| Combinado | Sim | Desde a tentativa 2 |

Em cada braço, recalcular cronologia e tentativas após a primeira divergência; não reaproveitar automaticamente a tentativa 2 histórica.

Também mediria:

- **Atraso excedente ao backoff:** próximo envio menos primeiro tick elegível, distinguindo espera programada, RPC e ausência de regra.
- **Todas as posições com falhas**, inclusive abertas/bloqueadas, para evitar selecionar só vendas concluídas.
- **Resultado sem GAMON e sem FOMO420**, expondo concentração e qualidade da reconstrução.
- **Erros do instrumento nos limiares:** ele reproduz os sucessos e os 6003 históricos usando os pisos reais?
- **Resultado líquido completo:** curva, taxas de rede de todas as tentativas e rent contabilizado simetricamente.
- **Idade da cotação ao simular/enviar.** A leitura da curva antecede outras chamadas de rede antes da construção; ampliar tolerância pode estar compensando envelhecimento evitável. [exits.py:108](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:108), [exits.py:234](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/exits.py:234)

## CONCORDO COM

- Priorizar a intenção abandonada: é um defeito concreto de continuidade da execução.
- Separar expiração de blockhash de falha por slippage.
- Comparar líquido da curva com líquido da curva.
- Não instituir “violento ⇒ pânico na primeira” com base nesta amostra. `creator_dump` e `rug_signal` já recebem o pânico por motivo. [send_tuning.py:58](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/send_tuning.py:58)
- Preservar backoff, cotação renovada e exclusão mútua entre tick e evento.

## OBSIDIAN

- **Ficha do dia — 23/09/2026 · mesa real de memes** — corrigir a atribuição da perda de AIRAA, distinguir motivo por tentativa e retirar a descrição de escada já existente.
- **Execution Engine** — registrar o contrato de intenção persistente, reconciliação, bloqueio durável e retomada.
- **Revisoes-Astra/T4.88 — medição e continuidade das saídas** *(nova página proposta)* — registrar os quatro contrafactuais, incerteza temporal e ausência de ganho causal demonstrado para o ponto 1.