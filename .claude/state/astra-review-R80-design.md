**RESUMO**

**Ainda não aprovaria o desenho para emitir CONFIRMA/REFUTA.** A hipótese é testável, mas faltam garantias sobre a identidade observada, o significado de “zero reusos” e a definição de golpe usada no veredito. Revisão como `quant-engineer`, sem consultar desfechos.

Respostas às cinco perguntas:

1. **Concordo condicionalmente com a premissa de imutabilidade.** A própria pump.fun informa que os links sociais declarados na criação não podem ser alterados, adicionados ou removidos. Isso sustenta uma reconstrução retrospectiva do atributo de criação; **o `COALESCE` local, sozinho, não a demonstra**. Também não demonstra que a mesa tinha o atributo disponível em T. [Documentação da pump.fun](https://intercom.help/pumpfun-web/en/articles/11002198-how-to-edit-coin-image-description-and-socials).

2. **Manteria sem-link explicitamente observado em B na primária.** É um zero estrutural coerente com o filtro proposto: não existe link para reutilizar. “Só moedas com link” fica como sensibilidade obrigatória. Campo não observado ou resposta incompleta continua ausente.

3. **As 871 resolvidas são um denominador defensável**, desde que o alvo declarado seja a população resolvida, a primeira decisão seja escolhida antes dessa seleção e o corte da extração fique fixo. Manter períodos sem coleta evita esconder a indisponibilidade. Porém, **60% é um piso operacional de cobertura, não uma garantia de que o reuso está identificado**. Publicaria também cobertura das 895 primeiras decisões, separando as 24 não resolvidas. Os números são os relatados nas [notas:26](C:/dev/project-hunter/.claude/state/notes-R80.md:26), não recontados nesta revisão.

4. **Congelaria diagnósticos de concentração e tipo, sem excluir nomes da primária.** Perfil/post/comunidade/outro; participação das maiores chaves; sensibilidade removendo cada chave dominante por uma regra definida sem desfechos. `usepaid` pode ser uma exclusão descritiva nominal, registrada agora. Não escolheria o recorte vencedor depois. Reuso de link não identifica, por si, um lançador comum.

5. **Há problemas concretos**, sobretudo na proveniência temporal, na cobertura de `known_only` e no reconhecimento de comunidades. Detalho abaixo.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei pytest nesta revisão somente leitura, evitando gravações de caches ou alterações do ambiente. O “21/21” pertence às [notas:39](C:/dev/project-hunter/.claude/state/notes-R80.md:39); não é resultado verificado por mim.

Os testes existentes cobrem a exclusão de moedas criadas em T ou depois, mas não mudanças posteriores da identidade de moedas antigas. O teste da guarda usa instantes construídos manualmente, sem integrar `TokenIndex` ao cálculo de proveniência. [test_r80.py:80](C:/dev/project-hunter/.claude/state/r80/test_r80.py:80), [test_r80.py:115](C:/dev/project-hunter/.claude/state/r80/test_r80.py:115).

**MUST-FIX**

1. **Não tratar a primeira leitura social como horário garantido do link atual.**

   O upsert aplica `COALESCE` separadamente ao link e ao horário. Uma leitura REST recebe `social_observed_at` mesmo quando o link está nulo; o parser também transforma campo omitido em `None`. [repo_token_sql.py:85](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo_token_sql.py:85), [curve_rows.py:97](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/curve_rows.py:97), [normalize.py:276](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/normalize.py:276).

   **Cenário:** às 11h o REST omite `twitter`; às 12h ocorre a decisão; às 13h chega o link. A linha pode terminar com link preenchido e horário 11h. `known_only` aceita esse link como conhecido antes da decisão porque verifica apenas aquele horário. [r80.py:118](C:/dev/project-hunter/.claude/state/r80/r80.py:118).

   **Correção necessária:** distinguir ausência explicitamente observada de resposta incompleta e comprovar o instante do valor utilizado. Sem isso, `known_only` não certifica disponibilidade histórica. Se o REST puder refletir uma atualização posterior, uma moeda antiga ganha retroativamente o link compartilhado e altera A/B; a imutabilidade documentada precisa ser aplicável à fonte efetivamente extraída.

2. **Separar “nenhum reuso observado” de “reuso inexistente”; recalcular cobertura em `known_only`.**

   `reuse()` retorna zero quando não encontra correspondências, enquanto `coverage()` considera observada qualquer identidade disponível na extração, independentemente de quando foi observada. Não existe parâmetro temporal equivalente a `known_only` em `coverage()`. [r80.py:124](C:/dev/project-hunter/.claude/state/r80/r80.py:124), [r80.py:144](C:/dev/project-hunter/.claude/state/r80/r80.py:144).

   **Cenário:** 60 de 100 moedas têm identidade observada. Uma das 40 desconhecidas compartilha o link da candidata. O estudo aceita a janela e coloca a candidata em B, embora seu reuso verdadeiro seja ≥1. Outro cenário: 100 identidades observadas amanhã fazem a cobertura histórica parecer 100%, embora somente dez fossem conhecidas em T.

   **Correção necessária:** declarar a variável como **contagem de reusos detectados no universo observado**, com incerteza de classificação, ou manter como desconhecido o zero não demonstrável. Na sensibilidade operacional, própria identidade, pares e cobertura precisam usar o mesmo corte temporal. Não basta trocar apenas a chamada a `reuse()`.

   O piso de 60% pode permanecer congelado, mas não deve justificar a afirmação “ausência de reuso comprovada”.

3. **Usar a definição congelada de golpe para a condição de confirmação.**

   A H-020 descreve perda com `creator_dump` ou vendedores em bloco; o desenho privilegia a classe da ficha, que primeiro retira `comprou_no_topo`. [Fila:240](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:240>), [notas:35](C:/dev/project-hunter/.claude/state/notes-R80.md:35).

   **Cenário:** uma moeda perde por `creator_dump` sem jamais superar o custo. `golpe_raw` conta; `golpe_ficha` não. O próprio teste explicita essa divergência. Isso pode inverter a condição “taxa A ≥ 2× B”. [test_r80.py:149](C:/dev/project-hunter/.claude/state/r80/test_r80.py:149).

   **Correção necessária:** evento literal como medida confirmatória; classe exclusiva da ficha como descrição secundária. Também congelar o tratamento de fita incompleta: vendedor desconhecido não comprova ausência de golpe. Hoje esse caso pode terminar em `False`. [r80.py:174](C:/dev/project-hunter/.claude/state/r80/r80.py:174).

   Definir ainda o caso de ambas as taxas serem zero: `0 ≥ 2×0` não é evidência de duplicação.

4. **Explicitar como Holm participa do veredito.**

   O desenho anuncia Holm, mas a regra de CONFIRMA não exige seu resultado. [notas:34](C:/dev/project-hunter/.claude/state/notes-R80.md:34), [notas:37](C:/dev/project-hunter/.claude/state/notes-R80.md:37).

   **Cenário:** p bruto de reuso = 0,04 e p secundário = 0,50; Holm produz 0,08 para reuso. Um IC nominal abaixo de zero ainda permitiria CONFIRMA pela regra escrita.

   **Correção necessária:** congelar agora se a confirmação exige p ajustado <0,05. Minha recomendação é exigir; qualquer interpretação diferente precisa aparecer expressamente, sem apresentar Holm como proteção efetiva do rótulo.

5. **Fechar a correspondência parcial de comunidades.**

   `_COMMUNITY` aceita qualquer caminho começando por `i/communities/` seguido de dígitos, sem exigir fim do segmento. [r80.py:24](C:/dev/project-hunter/.claude/state/r80/r80.py:24).

   **Cenário:** `x.com/i/communities/123abc` e `x.com/i/communities/123` tornam-se `community:123`. Duas entradas distintas criam um falso reuso e mudam B para A.

   **Correção necessária:** validar o limite do identificador e definir quais sufixos são equivalentes antes da análise.

**NICE-TO-HAVE**

- **Bootstrap adicional por chave social.** Uma linha por mint elimina repetição do mint, mas várias moedas ligadas ao mesmo post viral podem ter desfechos dependentes. Congelaria essa sensibilidade agora; o IC por mint permanece o registrado.
- **Endurecer entradas do índice:** rejeitar duplicatas de mint e candidata criada em T ou depois. Atualmente o dicionário sobrescreve duplicatas, mas os índices acumulam linhas; a restrição `created_at < T` é aplicada aos pares, não à candidata. [r80.py:87](C:/dev/project-hunter/.claude/state/r80/r80.py:87), [r80.py:115](C:/dev/project-hunter/.claude/state/r80/r80.py:115).
- **Calcular a razão com Decimal antes de converter para estatística.** `r_of()` converte os dois valores monetários diretamente para float. Preferiria `float(Decimal(pnl) / Decimal(size))`; somas e contrafactual em SOL devem permanecer Decimal. Também validar tamanho positivo numericamente: `"0.0000000000"` passa pelo filtro textual atual. [r80.py:203](C:/dev/project-hunter/.claude/state/r80/r80.py:203).
- **Acertar a cronologia documental:** 12:40 BRT corresponde a 15:40Z, posterior ao congelamento indicado como ~15:30Z. Registrar a sequência real, sem reescrever o bloco congelado. [notas:6](C:/dev/project-hunter/.claude/state/notes-R80.md:6), [notas:29](C:/dev/project-hunter/.claude/state/notes-R80.md:29).

**O QUE EU FARIA DIFERENTE**

Registraria um adendo antes dos desfechos distinguindo dois objetivos: **associação retrospectiva com metadado de criação** e **filtro que a mesa poderia executar em T**. O primeiro pode usar observação posterior sob a premissa documentada; o segundo exige proveniência temporal efetiva.

Manteria B com ausência explícita de link, separando sua contribuição daquelas moedas com link sem repetição detectada. Congelaria os diagnósticos de concentração sem mudar o limiar ≥1. Descreveria ΔSOL como a soma contábil das posições removidas, sem presumir que representa uma carteira reexecutada com novas oportunidades.

**CONCORDO COM**

O intervalo `[T−24h,T)`, a exclusão da própria moeda e o descarte de identidades próprias não observadas estão claros na implementação. A conversão de timestamps rejeita datas sem fuso e normaliza para UTC. [r80.py:55](C:/dev/project-hunter/.claude/state/r80/r80.py:55), [r80.py:112](C:/dev/project-hunter/.claude/state/r80/r80.py:112).

Também concordo em manter o limiar literal, publicar sensibilidades como descritivas e conservar os períodos de indisponibilidade no denominador.

**OBSIDIAN**

- **Fila de Hipóteses** — acrescentar referência ao adendo metodológico da H-020, preservando o bloco congelado.
- **Dicionário de Variáveis** — distinguir identidade declarada, horário de observação do valor e reuso detectado sob cobertura parcial.
- **`golpe_do_criador`** — explicitar a diferença entre evento de golpe e classe exclusiva da ficha.
- **Revisões Astra / R80 — desenho da H-020** — registrar condicionantes de proveniência, cobertura, Holm e normalização, sem veredito sobre desfechos.