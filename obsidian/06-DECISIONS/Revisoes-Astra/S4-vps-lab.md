---
tags: [astra, revisao, shadow-lab, vps, operacoes]
updated: 2026-09-06
---

# Revisão da Astra — a prova operacional do Lab na VPS (S4, 2026-09-06)

Transcrição integral em `.claude/state/astra-review-S4-vps-lab.md`. Perguntei quatro coisas: se o
diagnóstico de CRLF do `code_ref` estava completo, se a correção que eu propunha tinha efeito
colateral no congelamento, se rodar o `seed` à mão na VPS foi seguro, e o que faltava na prova para
eu poder afirmar que o Lab está funcionando lá.

**Resultado: ela confirmou o diagnóstico reproduzindo os hashes, e derrubou quatro afirmações
minhas.** Todas corrigidas em `.claude/state/vps-lab-proof.md` e em [[Open Bugs]].

## O que ela confirmou, com número

Reproduziu a composição do digest em memória (nome + NUL + conteúdo + NUL, ordenado):

```
momentum_v1        raw: c012f75cdd8492d3...  lf: 6ccbe8b6c8ac18f3...  git_blob: 6ccbe8b6c8ac18f3...
volume_anomaly_v1  raw: d8275427c958743b...  lf: a03d18fece9e0052...  git_blob: a03d18fece9e0052...
```

Converter só CRLF → LF nos arquivos locais devolve **exatamente** os hashes da VPS, que são iguais
aos dos blobs do commit. `git ls-files --eol` mostra os quatro arquivos como `i/lf, w/crlf` apesar de
`eol=lf` no `.gitattributes` — a normalização vale para o que **entra** no repositório, não para o
que já está na árvore de trabalho. Diagnóstico fechado.

## Os quatro achados

1. **HIGH — a minha recomendação sobre o `seed` estava errada e teria quebrado o próximo deploy.**
   Eu ia pedir para pôr o `seed` no `compose.sh update`. `seed.py` faz
   `on_conflict_do_update(set_={"code_ref": ...})` em `strategy_versions`, substituindo o `code_ref`
   por um placeholder; a trigger de congelamento recusa em qualquer linha já ativada; e o seed roda
   numa transação só. **Reproduzi o cenário na própria VPS**, depois da ativação: `RaiseError:
   strategy_versions ... is frozen after activation: code_ref cannot change`, com as oito tabelas
   revertendo juntas. O rollback foi limpo, mas a recomendação foi invertida: o seed precisa
   preservar versões ativadas, com teste `seed → ativação → seed`, **antes** de entrar em qualquer
   fluxo automático.
2. **HIGH — a normalização do digest precisa de um plano para as versões já congeladas.** Publicar a
   correção muda os digests do lado Windows de `c012…/d827…` para `6ccb…/a03d…`, e as coortes locais
   de [[EXP-0001-momentum-v1]] e [[EXP-0002-volume-anomaly-v1]] deixam de rodar sem `--supersede`
   auditado. Os da VPS, já em LF, não mudam. Ela também descartou minha alternativa de digerir
   AST/bytecode: AST exige inventar uma canonicalização nova e bytecode não é estável entre versões
   do Python — ampliariam o contrato em vez de consertar o incidente. Aceito: normalização mínima.
3. **HIGH — `funding_missing` pode ser falso, e eu tinha escrito "funding não apurado" como fato.**
   `funding.py` trunca o intervalo para segundos, projeta uma grade de liquidações e exige
   correspondência **exata** de timestamp; o histórico desta VPS tem
   `max(funding_time) = 2026-09-06 04:00:00.005+00`. Cenário: a liquidação real existe cinco
   milissegundos depois da grade, a busca exata falha, e 18 outcomes recebem
   `funding_missing:04:00:00` com o dado presente. Não está provado que explica os 18 — mas impede
   chamá-los de ausência legítima. Reescrito como "sob investigação".
4. **MEDIUM — três afirmações minhas maiores que a evidência.** (a) *Readiness falsa não reinicia
   container*: `restart: always` reage à saída do processo, e nesse caminho o worker fica de pé
   recusando avaliações — quem espera autocura não a tem. (b) *`/ready` verde não prova catálogo
   executável*: zero versões ativas também passa, e uma versão válida esconde outra recusada; a
   evidência boa são os sinais por estratégia. (c) *"nada perdido"* não sai de comparar 109 despachos
   com um `XLEN` lido uma hora antes — para afirmar entrega exata é preciso reconciliar identidades
   de uma população delimitada, e a entrega é idempotente justamente porque pode repetir após crash.

## Onde ela concordou

- O seed manual **preservou** o conteúdo congelado de `opportunity_weights` (insere o que falta,
  verifica o que existe, recusa divergência) e de `feature_definitions` (preserva identidade
  publicada, atualiza só descrição). Ressalva que absorvi: como não medi `opportunity_weights`
  **antes**, não posso afirmar que nenhuma linha preexistente mudou de `is_active`. Está escrito na
  prova.
- Separar as coortes por ambiente/ativação, preservar `r_ex_funding` quando o líquido é desconhecido,
  e tratar as contagens como funcionamento sem inferir eficácia.
- Que os sinais e acompanhamentos registrados sustentam que **o fluxo de sombra funcionou naquela
  janela** — que é exatamente o que a prova pode afirmar, e nada além.

## Nice-to-have anotados para depois

Registrar o caminho efetivamente importado **dentro do container** e a identidade imutável da imagem
(árvore limpa no host não garante que o processo use aquele artefato); prova de retomada após
restart e ausência de acompanhamentos órfãos; e, para falar em "Lab acessível ao Everton", a API
autenticada e a tela `/lab` — que são a S3, entrega distinta do worker.

## Relacionadas

[[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] · [[Experiments Index]] · [[Open Bugs]] · [[Deployment]] · [[Workers]] · [[S4-avaliacoes-shadow]] · [[Dialogos/SHADOW]]
