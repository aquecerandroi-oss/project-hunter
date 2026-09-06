## RESUMO

**O CRLF explica integralmente os dois digests divergentes apresentados.** Recalculei os hashes: converter somente CRLF → LF nos arquivos locais reproduz exatamente os valores da VPS e dos blobs do commit `75fc59c`.

**Aprovo a conclusão de que o worker executou o fluxo de sombra na VPS nessa janela. Peço correções antes de apresentar a prova como validação operacional completa:** repetição do seed após ativação, transição do digest, diagnóstico do funding e algumas afirmações sobre saúde e entrega.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisão no papel de `code-reviewer`, em modo OPINIÃO.

## TESTES

Executei uma sonda com `node`, somente em memória, reproduzindo a composição ordenada `nome + NUL + conteúdo + NUL` de [code_ref.py:210](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/code_ref.py:210).

Resultados reais:

```text
momentum_v1
raw:      c012f75cdd8492d3eb46aa9abd536320220c3bf71788e47e6b6b73218b0ba823
lf:       6ccbe8b6c8ac18f32e93a6d44e71e0045155646479907b2b1944f39c3cdf4c95
git_blob: 6ccbe8b6c8ac18f32e93a6d44e71e0045155646479907b2b1944f39c3cdf4c95

volume_anomaly_v1
raw:      d8275427c958743bc23dc190b2a8744d3fbf65ea81acf091e043f5ae65410ef2
lf:       a03d18fece9e0052756aadd16a60d9af8d97de279bdf79804d2cbde098fc496a
git_blob: a03d18fece9e0052756aadd16a60d9af8d97de279bdf79804d2cbde098fc496a
```

`git ls-files --eol` confirmou os quatro arquivos com `i/lf`, `w/crlf`, apesar de `eol=lf`. O comparativo dos arquivos de digest, seed, funding e trigger contra `75fc59c` terminou com `reviewed_paths_diff_exit=0`.

Não executei pytest, seed, alterações no banco nem comandos na VPS. Os dados remotos são os registrados na prova.

## MUST-FIX

**1. HIGH — Não colocar o seed atual em todo deploy sem corrigir seu comportamento após ativação.**

[seed.py:149](C:/dev/project-hunter/infra/scripts/seed.py:149) faz upsert de `strategy_versions.v1`, substituindo `code_ref` pelo placeholder `hunter_indicators.strategies.…`. A trigger impede essa alteração depois da primeira ativação, inclusive após depreciação ([shadow.py:106](C:/dev/project-hunter/infra/migrations/ddl/shadow.py:106)).

**Cenário:** adicionar o seed ao `compose.sh update`, como propõe a memória, e executar o próximo deploy nessa VPS. A versão ativa já possui um digest; o seed tenta substituí-lo, a trigger recusa e toda a transação é revertida — ela engloba todas as tabelas ([seed.py:306](C:/dev/project-hunter/infra/scripts/seed.py:306)).

A primeira execução registrada, antes da ativação, não enfrenta esse problema. Mas “idempotente” precisa dessa ressalva. Eu faria o bootstrap preservar versões existentes, com teste específico **seed → ativação → seed**.

**2. HIGH — A normalização precisa de um plano para as versões já congeladas.**

O catálogo exige igualdade literal entre digest armazenado e calculado ([catalogue.py:238](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/catalogue.py:238)).

**Cenário:** publicar a normalização e reiniciar o ambiente Windows. Seus hashes passam de `c012…/d827…` para `6ccb…/a03d…`; as versões atualmente congeladas deixam de executar, mesmo sem mudança nas estratégias.

Nesta correção mínima, **os digests Linux apresentados permanecem iguais**. Os Windows precisam de sucessão auditada ou de uma compatibilidade legada explicitamente desenhada e verificada. Não reescreveria `code_ref` nem aceitaria divergências genericamente.

**3. HIGH — “Funding não apurado” ainda não está demonstrado; existe um falso `funding_missing` concreto.**

O cálculo trunca intervalos para segundos inteiros, projeta uma grade e exige correspondência exata de timestamp ([funding.py:73](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:73), [funding.py:126](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:126), [funding.py:136](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:136)).

**Cenário:** histórico às `02:00:00`, `03:00:00` e `04:00:00.005`; entrada às `03:30`, saída às `04:30`. A cadência calculada é 3.600 segundos, então a grade exige `04:00:00`. A liquidação real em `04:00:00.005` existe, mas a busca exata falha e produz `funding_missing:04:00:00`.

A própria prova registra funding com milissegundos ([vps-lab-proof.md:262](C:/dev/project-hunter/.claude/state/vps-lab-proof.md:262)). Isso **não prova que explica os 18 casos**, mas impede classificá-los como ausência legítima sem investigação por mercado.

É necessário cruzar os outcomes afetados com o histórico usado na liquidação, incluindo timestamps completos. Preservar `NULL` é conservador; o motivo pode estar errado. A correção deve definir a identidade da liquidação, preservando o timestamp original e a ambiguidade na fronteira da entrada/saída.

**4. MEDIUM — Corrigir afirmações que excedem a evidência operacional.**

- **Readiness não implica restart.** A seção 10 afirma que o container entra em restart. Nesse caminho, o código apenas retorna readiness falsa ([health.py:119](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/health.py:119)); `restart: always` reage à saída do container, não apenas a `unhealthy`. **Cenário:** o operador espera recuperação automática enquanto o processo continua consumindo e recusando avaliações. [Documentação Docker](https://docs.docker.com/engine/containers/start-containers-automatically/).
- **Readiness verde não exige catálogo executável não vazio.** Zero versões também satisfaz `not roster.blind`; uma versão válida pode esconder outra recusada ([catalogue.py:105](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/catalogue.py:105)). **Cenário:** um deploy perde uma estratégia e continua verde. Nesta janela, os sinais por estratégia são evidência melhor.
- **“Nada perdido” não resulta dessas contagens.** A prova compara 109 despachos com `XLEN=41` de outro horário ([vps-lab-proof.md:235](C:/dev/project-hunter/.claude/state/vps-lab-proof.md:235)). **Cenário:** contagens iguais escondem um evento duplicado e outro ausente. Para essa afirmação, reconciliar identidades de sinais, outbox e eventos de uma população delimitada; entrega pode repetir após crash ([outbox.py:11](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/outbox.py:11)).

## NICE-TO-HAVE

- Registrar o caminho efetivamente importado **dentro do container**, identificação imutável da imagem e manifesto dos módulos digeridos. Mesmo commit e árvore limpa no host não garantem que o processo use aquele artefato; o diretório vem do pacote instalado ([code_ref.py:53](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/code_ref.py:53)). Para esta ocorrência, porém, a igualdade integral dos hashes fecha o diagnóstico.
- Acrescentar prova de retomada após restart, evolução dos checkpoints e ausência de acompanhamentos órfãos; ligar os testes existentes de falhas, gaps e `tracking_hold` ao aceite.
- Para afirmar **Lab completo acessível ao usuário**, acrescentar API autenticada e tela `/lab`. São entregas distintas do worker no plano ([SHADOW-LAB.md:28](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:28)).

## O QUE EU FARIA DIFERENTE

**Escolheria normalização mínima de quebras de linha, mantendo nomes, ordem e separadores atuais.** Sem remover espaços, comentários ou escapes literais. Python já normaliza quebras físicas, inclusive dentro de strings multilinha; isso não transforma o escape textual `\r` em outra coisa. [Referência Python](https://docs.python.org/3/reference/lexical_analysis.html#physical-lines).

Não escolheria AST/bytecode para resolver este incidente. AST exige definir uma nova representação canônica; bytecode não tem estabilidade garantida entre versões do Python. Digerir somente `co_code`, por exemplo, não cobre os valores das constantes. Ambos ampliam a mudança do contrato e a necessidade de migrar versões. [Documentação de bytecode](https://docs.python.org/3/library/dis.html).

A normalização também **não amplia o congelamento existente**: dependências fora de `hunter_core.strategies` permanecem excluídas, limitação já registrada ([code_ref.py:22](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/code_ref.py:22)).

## CONCORDO COM

**O seed manual preserva o conteúdo congelado das duas tabelas perguntadas, pelo código revisado:**

- `opportunity_weights.weights`: insere ausentes e recusa conteúdo divergente, sem sobrescrever o vetor ([seed_weights.py:94](C:/dev/project-hunter/infra/scripts/seed_weights.py:94)). Pode alterar `is_active` ao criar o perfil promovido ([seed_weights.py:44](C:/dev/project-hunter/infra/scripts/seed_weights.py:44)). Como não há contagem anterior dessa tabela na prova, não é possível afirmar que nenhuma linha preexistente mudou de estado.
- `feature_definitions`: preserva identidade publicada e recusa divergência; pode atualizar apenas a descrição ([seed.py:248](C:/dev/project-hunter/infra/scripts/seed.py:248)). A prova informa zero definições antes do seed.

Concordo também com separar as coortes por ambiente/ativação, preservar `r_ex_funding` quando o líquido é desconhecido e tratar as contagens como funcionamento, sem inferir eficácia. Os sinais e acompanhamentos registrados sustentam que **o fluxo de sombra funcionou nessa janela**.

## OBSIDIAN

- **Open Bugs** — registrar seed após ativação e possível falso `funding_missing`; retirar a classificação antecipada de ausência legítima.
- **Deployment** — distinguir bootstrap inicial de repetição do seed e corrigir readiness versus restart.
- **Strategies** — registrar a equivalência CRLF/LF comprovada e a transição dos digests congelados.
- **Experiments Index** — delimitar a prova como operação do worker; manter a cobertura de funding sob investigação.
- **Revisões da Astra — prova operacional do Lab na VPS** — acrescentar esta revisão, com os hashes reproduzidos e vínculos para os achados.