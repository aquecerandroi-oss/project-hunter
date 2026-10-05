**RESUMO**

Confirmo os mecanismos de **(1), (2) e (4)**, com ressalvas abaixo. **Não considero demonstrada a conclusão “não há segredo real” de (3).** E sim: permitir base58 pelo contexto `tokenAddress` abre exatamente o buraco da seed que você descreveu.

Há também um risco adicional: atualizar o scanner passa a ativar exceções globais antigas excessivamente amplas.

Não examinei `cand.toml`: está fora do repositório, onde você proibiu acesso. Portanto, os comentários sobre suas novas regexes são condicionais à descrição fornecida.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum `.env` lido; nenhum commit. Revisão no papel `security-reviewer`.

**TESTES**

Comandos executados e saídas:

```text
git rev-parse --short HEAD
a67c5143

git rev-list --all --count
1057

git rev-parse --is-shallow-repository
false

git rev-list --all --min-parents=2 --count
0
```

O checkout já avançou em relação aos seus 1056 commits.

Executei provas em memória com PowerShell/.NET, usando a regex local de URI e a regex oficial `generic-api-key` da versão 8.30.1:

```text
FirstCaptureIsScheme           : True
MatchContainsHost              : False
RedactSchemeLeavesPassword     : True
FakeNeighborAllowsWholeLine    : True

SyntheticInputBytes            : 32
Base58Characters               : 43
GenericRuleRegexMatches        : True
CapturedValueIsSeed            : True
EntropyAboveThreshold         : True
LooksLikePublicAddress         : True
```

**Essas provas verificam as expressões e o mecanismo; não substituem executar o Gitleaks.** O binário não está no PATH. Não reproduzi os números 579/575/0/1 nem seus controles completos.

**MUST-FIX**

1. **HIGH — corrigir a extração do segredo antes de confiar em `--redact`.**  
   [.gitleaks.toml:64](/C:/dev/project-hunter/.gitleaks.toml:64) captura o esquema primeiro e não define `secretGroup`. O scanner escolhe o primeiro grupo não vazio; a redação substitui esse valor dentro de `Match`/`Line`. **Cenário:** alguém cola uma URI real; o log mascara `postgresql+asyncpg` e preserva a senha. Confirmado no código oficial de [extração, linhas 410–428](https://github.com/gitleaks/gitleaks/blob/v8.24.3/detect/detect.go#L410) e [redação](https://github.com/gitleaks/gitleaks/blob/v8.24.3/report/finding.go). Usaria grupos estruturais não capturantes e um grupo explícito para a senha. Não estou afirmando que uma senha real já apareceu nos logs.

2. **HIGH — não ativar a exceção global “qualquer linha com FAKE” sem restringi-la.**  
   [.gitleaks.toml:38](/C:/dev/project-hunter/.gitleaks.toml:38) usa `regexTarget = "line"` com `(?i)FAKE`, sem limitar regras. **Cenário:** uma linha JSON contém um campo fictício e, ao lado, uma credencial verdadeira; ambos os achados podem ser descartados. Um comentário `# FAKE fixture` também basta. A atualização torna efetiva essa exceção anteriormente ignorada. Se `cand.toml` já a removeu, este item está atendido.

   Há uma variante na exceção de localhost, [.gitleaks.toml:70](/C:/dev/project-hunter/.gitleaks.toml:70): uma URI local e outra remota na mesma linha fazem a URI remota passar pela exceção dessa regra. O contexto permitido precisa pertencer **ao próprio achado**.

3. **HIGH, condicional à proposta — não considerar campo + formato base58 prova de publicidade.**  
   **Cenário concreto:** durante a preparação de uma fixture, alguém copia uma seed Ed25519 de 32 bytes para `tokenAddress`. Ela pode ter os mesmos 43–44 caracteres base58 de uma chave pública. Minha prova sintética satisfaz inclusive a entropia da regra genérica. Uma exceção que permita qualquer valor desse formato nesse campo o esconderia.

   `targetRules = ["generic-api-key"]` preserva outras regras, mas **não garante que outra regra reconheça essa seed sem prefixo**. Uma seed Ed25519 tem 32 bytes; o endereço Solana também representa 32 bytes. Formato e comprimento não distinguem sua função. Fontes: [RFC 8032, §5.1.5](https://www.rfc-editor.org/rfc/rfc8032#section-5.1.5), [contas Solana](https://solana.com/docs/core/accounts).

   Para essa garantia, prefiro valores públicos individualmente verificados, com campo/caminho restritos. Uma exceção aberta por formato exige aceitar explicitamente esse risco residual.

4. **MEDIUM — corrigir a profundidade do checkout junto com a configuração.**  
   [.github/workflows/ci.yml:290](/C:/dev/project-hunter/.github/workflows/ci.yml:290) não configura `fetch-depth`. **Cenário:** um push com vários commits faz a action pedir `baseRef^..headRef`, mas o pai não existe no checkout raso; o scanner pode falhar antes de analisar o intervalo. A correção dos falsos positivos não resolve isso. Recomendo `fetch-depth: 0`; ele disponibiliza o histórico, embora a action continue escolhendo um intervalo. Veja [checkout](https://github.com/actions/checkout/blob/v4/action.yml) e [action, linha 129511](https://github.com/gitleaks/gitleaks-action/blob/v2.3.9/dist/index.js#L129511).

**NICE-TO-HAVE**

- **Controles nos próprios contextos liberados:** seed sob `tokenAddress`; token opaco sob `accountKey`; segredo junto de `FAKE`; duas URIs na mesma linha; token em `files[].key`. Plantar chaves somente fora dessas exceções não testa seus buracos.
- **Limites completos nas regexes:** a exceção de endereço EVM deve exigir exatamente 40 dígitos e um delimitador final; casar apenas o prefixo pode aceitar parte de uma chave privada hexadecimal de 64 dígitos. Para Zenodo, “parece nome de arquivo” sozinho não comprova publicidade. Identificadores snake/kebab também precisam de escopo e valores bem delimitados.
- **`condition = "AND"` quando combinar caminho e conteúdo.** O comentário em [.gitleaks.toml:31](/C:/dev/project-hunter/.gitleaks.toml:31) diz que isso não é possível, mas a versão proposta suporta. Sem `AND`, adicionar um caminho pode ampliar a exceção para todo o arquivo. [Documentação oficial](https://github.com/gitleaks/gitleaks/blob/v8.30.1/README.md#configuration).
- **Auditoria independente das supressões:** registrar SHA, refs examinadas, comandos, exceções, arquivos ignorados e limites de decodificação. `--all` significa refs disponíveis localmente; não cobre automaticamente refs ausentes, artefatos e logs do Actions. Verificar também se o pickaxe usou `-G` ou `-S --pickaxe-regex` quando a intenção era procurar regexes.
- **Revisar os limites da regra customizada:** [.gitleaks.toml:64](/C:/dev/project-hunter/.gitleaks.toml:64) não cobre senha inferior a oito caracteres nem usuário vazio, como em certas URIs Redis. Logo, ausência de achado nessa regra não exclui credenciais reais.

**O QUE EU FARIA DIFERENTE**

Separaria o aceite em duas evidências: **classificação dos achados existentes** e **capacidade de detectar novos segredos dentro das exceções**. Zero achados depois de ampliar allowlists comprova apenas que as supressões funcionaram.

Para [test_risk_profile_gate.py:186](/C:/dev/project-hunter/tests/integration/paper/test_risk_profile_gate.py:186), o literal atual é claramente uma chave de teste. Ainda assim, prefiro uma exceção exata de valor/regra a `gitleaks:allow`: o comentário dispensa achados da linha inteira, inclusive uma credencial adicionada ali futuramente. [Implementação oficial](https://github.com/gitleaks/gitleaks/blob/v8.24.3/detect/detect.go#L400).

**CONCORDO COM**

1. **Clone raso:** correto para o push de um commit descrito. A condição exata da action é `baseRef == headRef`; sem override, um commit satisfaz isso. O Git trata o limite raso como raiz. **“Todo push” é amplo demais:** múltiplos commits seguem outro ramo. Fontes: [action](https://github.com/gitleaks/gitleaks-action/blob/v2.3.9/dist/index.js#L140747), [Git shallow](https://git-scm.com/docs/shallow).

2. **Versão e allowlists:** confirmado. A action fixa `8.24.3` como fallback; `[[allowlists]]` globais chegaram em 8.25.0. O workflow não define versão em [.github/workflows/ci.yml:299](/C:/dev/project-hunter/.github/workflows/ci.yml:299). A diferença de quatro achados é compatível com isso, mas não a reproduzi. Fontes: [fallback](https://github.com/gitleaks/gitleaks-action/blob/v2.3.9/dist/index.js#L140725), [mudança de configuração](https://github.com/gitleaks/gitleaks/blob/v8.30.1/README.md#configuration).

3. **575 falsos positivos:** as categorias são plausíveis; a classificação integral permanece evidência sua, não verificação minha. Publicidade exige procedência, não apenas aparência. Eu escreveria **“nenhum segredo real identificado no escopo auditado”**, informando exclusões. O histórico local tem zero merges, portanto uma lacuna de diffs de merge não explica seus resultados atuais.

4. **URI e allowlist histórica:** correto, mas há **três impedimentos independentes**: a versão antiga ignora a tabela global; o alvo padrão é o `Secret` extraído como esquema; e o `Match` termina em `@`, enquanto a exceção exige `host/db` — [.gitleaks.toml:28](/C:/dev/project-hunter/.gitleaks.toml:28), [.gitleaks.toml:64](/C:/dev/project-hunter/.gitleaks.toml:64). Portanto, trocar somente versão e `regexTarget` não basta.

**OBSIDIAN**

- **Infrastructure** — registrar versão explícita do scanner, profundidade do checkout e cobertura real do job.
- **Resolved Bugs** — complementar o registro T10: as allowlists globais eram incompatíveis com a versão usada e a redação da URI selecionava o esquema.
- **Revisoes-Astra / Segurança do Gitleaks** — nova nota com evidências, risco das exceções contextuais e limites da afirmação de ausência de segredos.