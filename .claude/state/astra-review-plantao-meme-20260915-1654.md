## RESUMO

**Testaria primeiro M-D14, depois M-P40 e por último M-P41 — com correções antes de entrarem na fila.** Papel assumido: `quant-engineer`, em modo OPINIÃO.

M-D14 melhora a confiabilidade de todas as próximas lições. M-P40 responde à pergunta operacional da EXP-M7, mas suas referências externas não sustentam os “tetos” propostos. M-P41 depende de validar exposição, pagamentos e elegibilidade; o desenho atual ainda não identifica causalmente o mecanismo.

**O erro mais concreto encontrado:** no Radar, progresso é a fração dos **tokens reais vendidos**, não SOL captado dividido por 85. Portanto, “10–30% ≈ 8,5–25,5 SOL” está errado para a porta da EXP-M7. [curve.py:123](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/curve.py:123)

## ARQUIVOS

Nenhum arquivo criado ou modificado. Rascunho completo lido; nenhum commit.

## TESTES

Não executei testes, fechamento diário ou consultas ao banco. Conferi código, memória, brutos e fontes públicas; fiz duas contas em memória no PowerShell:

```text
M-L3 14/09, usando somas arredondadas do diário:
R das demais = -0,1557963
Δ alto contra demais = -0,1040037

Curva padrão idealizada:
10% dos tokens reais vendidos → 2,3944087 SOL
30% dos tokens reais vendidos → 8,5476667 SOL
```

A primeira conta **não fornece IC**. A segunda usa 30 SOL virtuais, 1,073 bilhão de tokens virtuais e 793,1 milhões de tokens reais iniciais; não inclui taxas nem particularidades de outras parametrizações. [curve.py:67](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/curve.py:67), [DATABASE.md:6232](C:/dev/project-hunter/docs/DATABASE.md:6232)

Os percentuais das 4.356 chamadas foram conferidos no resumo preservado, **não recalculados do JSONL original nesta revisão**.

## MUST-FIX

### 1. M-D14 — manter a prioridade; reformular os portões

**a) Congelar o contraste inteiro, não apenas os cortes.**

Hoje o código recalcula os tercis e escolhe a célula cuja média mais se distancia da média do dia; o comparador inclui todas as demais apostas, inclusive desconhecidos. [meme_close_lessons.py:180](C:/dev/project-hunter/infra/scripts/meme_close_lessons.py:180), [meme_close_lesson_kit.py:156](C:/dev/project-hunter/infra/scripts/meme_close_lesson_kit.py:156), [meme_close_lesson_kit.py:169](C:/dev/project-hunter/infra/scripts/meme_close_lesson_kit.py:169)

O registro precisa congelar: limites com precisão original, inclusividade, comparador, desconhecidos, versão da feature, conjuntos participantes, unidade de análise e maturação dos desfechos.

**Cenário de falha:** mudar a proporção de desconhecidos ou de conjuntos muda Δ sem mudar a associação dentro de cada conjunto. Publicaria também uma sensibilidade com composição fixa por conjunto e dependência por mint/criador.

**b) Corrigir a narrativa de 14/09.**

−0,2598 R é a média dos snipers altos, não seu contraste. Pelas somas publicadas, o contraste contra as demais é aproximadamente **−0,1040 R**. Há inversão **pontual**, mas falta o IC desse contraste e a célula tem apenas nove apostas. M-L4 continua **não avaliada nos cortes de origem**. [Diário 14/09:171](C:/dev/project-hunter/obsidian/09-OPERATIONS/Diario-Meme/2026-09-14.md:171)

**Cenário de falha:** uma célula perde dinheiro, mas perde menos que o controle; chamar isso de inversão do efeito leva ao descarte errado.

A retração de Kamat está confirmada. Ela documenta falha daquele modelo e daquele processo de observação; não estabelece que nosso Lab sofreu o mesmo mecanismo. [Kamat v4](https://arxiv.org/html/2607.02823v4)

**c) G2 “metade do delta” não serve como portão científico.**

A origem foi selecionada pelo destaque observado. Usar metade desse valor herda seu exagero amostral. G2 pode aparecer como **razão descritiva de retenção**, não como limite de relevância. Fixaria um efeito mínimo `δ*` em R, justificado antes da validação.

**Cenário de falha:** um efeito real de +0,15 R é rejeitado porque o dia selecionado marcou +0,53 R.

**d) Retirar “dois dias consecutivos → descartada”.**

Duas avaliações acumuladas compartilham quase todos os dados. Não são duas replicações; olhar repetidamente IC de 95% também não conserva automaticamente o erro nominal. Além disso, IC contendo zero pode representar imprecisão.

Usaria um horizonte decisório congelado — ou método sequencial explicitamente escolhido — e estados separados:

- **Não avaliável:** dados ou cobertura insuficientes.
- **Inconclusiva:** precisão insuficiente.
- **Replicada:** evidência do efeito na direção e magnitude previamente exigidas.
- **Evidência contra o efeito relevante:** intervalo incompatível com `δ*`.

**Cenário de falha:** duas leituras quase idênticas encerram uma hipótese que ainda admite efeito útil. Três dias são piso de observação, não garantia de inferência temporal confiável.

**e) G4 não está definido para uma lição isolada.**

Uma única previsão constante por célula não identifica uma inclinação de calibração. Com duas médias previstas, a inclinação essencialmente repete a comparação entre contrastes. Avaliaria erro das médias previstas por célula, com incerteza; reservaria calibração formal para um modelo congelado que produza previsões individuais.

**Cenário de falha:** G4 rejeita uma associação por deslocamento geral do mercado ou duplica G2 com aparência de evidência independente.

### 2. M-P40 — remover o teto e corrigir a população

**a) 38,8%/12,5% são referências externas, não limites superiores.**

Seleção por atenção não implica que aquela população domine as elegíveis da EXP-M7. Atenção também pode chegar depois da valorização. A propriedade “pico em 24 h ≤ pico em horizonte maior” vale para **os mesmos caminhos e referências**, não entre populações diferentes.

**Cenário de falha:** a porta orgânica seleciona uma população melhor e supera 12,5%; o protocolo declara uma surpresa contra um teto que nunca foi demonstrado.

Manteria esses números como descrição do depósito. O contraste social deve ser interno, com exposição definida e registrada até L; chamada de Telegram, post publicado e campo `kol` não são medidas intercambiáveis. O próprio schema SmugCalls descreve pico posterior, incluindo pós-migração, sem fornecer o caminho necessário ao replay. [Schema SmugCalls](https://smugcalls.com/data.html)

**b) Corrigir duas conversões diferentes.**

- **Progresso → SOL:** usar a curva e os parâmetros vigentes; não multiplicar por 85. Na parametrização ilustrativa acima, 10–30% corresponde aproximadamente a **2,39–8,55 SOL**.
- **Mcap USD → progresso:** requer preço histórico da quote, supply, reservas/parâmetros, versão e estado da curva. Mesmo conhecer SOL/USD não resolve sozinho.

**Cenário de falha:** atribuir as taxas de 10–25 SOL a uma porta que entra em outro trecho da curva. Retiraria tanto essa correspondência quanto “mcap mediano = zona da EXP-M7”.

**c) Rebaixar a comparação entre fornecedores.**

A página SmugCalls atualmente informa data, SOL captado e exclusão das últimas seis horas; reconhece que **período e janela de observação** explicam partes da diferença para Kamat. Portanto, “é ascertainment, não mercado” é categórico demais. Sua mediana de cinco minutos é **entre graduadas**, não sobrevida de todas as elegíveis. [Método SmugCalls](https://smugcalls.com/pumpfun-graduation-rate.html)

Há ainda uma reconciliação necessária: os numeradores publicados caem de 21.604 graduadas totais para 20.818 entre moedas com trade e 15.911 entre as que alcançaram 25 SOL. Antes de interpretar como coortes aninhadas completas, exigir explicação da cobertura e do tratamento de saltos.

**Cenário de falha:** transformar histórico incompleto de reservas/trades em taxa condicional econômica.

**d) Definir L, unidade, preço e acompanhamento independente da posição.**

Uma primeira elegibilidade por mint/porta; horizonte a partir desse marco; referência em unidade explícita — USD, SOL ou quote — e acompanhamento inclusive depois da saída paper. Não condicionar o denominador a conseguir fill, migrar ou permanecer coberto.

**Cenário de falha:** o coletor acompanha melhor apostas abertas e moedas bem-sucedidas, elevando artificialmente a excedência. Para lacunas, publicar sucessos comprovados e limites com desconhecidos; pico não visto não vira fracasso. Escolher um contraste primário entre os vários níveis, horizontes e estratos.

### 3. M-P41 — mecanismo ainda depende de identificação

**a) Validar a elegibilidade real antes da descontinuidade.**

US$20 **na compra** pode não ser a variável usada pelo distribuidor. É necessário saber saldo agregado por carteira/mint, preço de valoração, instante do snapshot, regra de duração e pagamentos efetivamente recebidos.

**Cenário de falha:** alguém compra US$19, tem valorização e recebe; outro compra US$21, cai antes do snapshot e não recebe. O corte proposto não separa tratados de controles.

Acrescentaria **M-D12**, que verifica distribuição, às dependências M-D9/M-D13.

**b) Bots no limiar podem destruir a interpretação causal.**

McCrary é diagnóstico, não certificado de validade. Ausência de rejeição também não prova ausência de seleção. Exigiria continuidade de covariáveis anteriores, suporte local, tratamento de valores arredondados e sensibilidade; havendo ordenação estratégica, o resultado principal vira descrição do comportamento no limiar. [Cattaneo e Titiunik](https://rdpackages.github.io/references/Cattaneo-Titiunik_2022_ARE.pdf)

**Cenário de falha:** bots pacientes escolhem US$20,01; o estudo atribui sua paciência ao pagamento.

**c) Corrigir identidade e relógio de exposição.**

O documento primário explica que, nas HR, `BondingCurve::creator` pode ser o destinatário controlado pela plataforma, e moedas regulares podem converter para HR. Esse campo não basta para agrupar criadores econômicos; flag observado depois não pode retroagir à compra. [Documentação Holder Rewards](https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/HOLDER_REWARDS_README.md)

**Cenário de falha:** moedas independentes parecem um único criador, ou compradores anteriores à conversão viram expostos desde o início.

**d) Definir episódio de carteira e limitar a conclusão.**

Contaria tempo desde a primeira compra elegível, com regra para saldo prévio, compras adicionais, vendas parciais e transferências. Morte sem possibilidade de venda deve ser evento concorrente; perda de coleta deve permanecer desconhecida. A razão pós-migração é análise secundária condicionada a sobreviver até migrar.

**Cenário de falha:** moeda travada produz “posse longa” e parece recompensa eficaz.

“Sem diferença detectável” depende da potência; não é previsão quantitativa nem equivalência. Pré-declarar margem de equivalência se essa for a pergunta. Pareamento sustenta associação ajustada, não prova sozinho mecanismo causal.

## NICE-TO-HAVE

- Decompor a raridade da EXP-M7 por **mints elegíveis**, cobertura e recusas; contagens repetidas de ticks não medem oportunidades independentes.
- Preservar consulta, hash, versão e cálculo reproduzível das fontes. Hash prova integridade do artefato, não completude da população.
- Reportar M-D14 sem o melhor mint/criador, além do agregado.

## O QUE EU FARIA DIFERENTE

Começaria com uma **M-D14 descritiva**, reproduzindo origem e controles congelados, sem descarte automático. Depois M-P40, com excedência local e trajetória suficiente para M-P32. M-P41 começaria por elegibilidade e pagamentos comprovados.

Também trocaria duas frases:

- “`creator_dump` custou −17 R” → **“as saídas rotuladas `creator_dump` somaram aproximadamente −17 R”**. O total não estima quanto essa proteção causou ou evitou.
- “US$4 milhões não fecha; é hype” → **“montante não reconciliado”**. Janelas, ativos, taxas destinadas aos holders e valores acumulados podem diferir. Narrativa promocional existe; contradição contábil ainda não foi demonstrada.

## CONCORDO COM

Cortes congelados; exclusão do dia de descoberta da validação; ausência de coleta diferente de não-graduação; pico diferente de R; controles contemporâneos; nenhuma promoção automática. Essas são as partes fortes das três propostas.

## OBSIDIAN

- **O modelo pré-registrado que morreu no holdout** — acrescentar a retração v4 e limitar conclusões ao modelo e ao rótulo auditados.
- **pump.fun: as taxas-base e seus denominadores** — corrigir fontes retiradas, janelas SmugCalls e conversão entre tokens vendidos e SOL captado.
- **Hipóteses do plantão** — registrar M-D14 → M-P40 → M-P41 com os must-fixes, sem teto externo ou descarte por dois dias.
- **EXP-M7 — orgânica lenta** — acrescentar avaliação metodológica datada; preservar hipótese e protocolo congelados.
- **Meme — 2026-09-15** — registrar a distinção entre inversão pontual, ausência de replicação e falta de precisão.
- **Revisões Astra / Index** — vincular este parecer e suas condições de entrada na fila.