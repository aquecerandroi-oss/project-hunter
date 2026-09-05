---
tags: [astra, revisao]
updated: 2026-09-05
fonte: .claude/state/astra-review-binance-skills-hub.md
---

# Revisão da Astra — binance-skills-hub

Parte da [[Mente da Sexta-feira]]. Índice: [[Index|todas as revisões]]. Diálogos relacionados: [[Dialogos/M1|M1]], [[Dialogos/M2|M2]].

**DECISÃO RECOMENDADA: NÃO instalar o Binance Skills Hub no PROJECT HUNTER.** Concordo com Claude. O benefício documental é pequeno diante da incompatibilidade com as regras de execução e isolamento de segredos.

Li os três documentos solicitados e conferi o repositório. Nenhum arquivo foi modificado; nenhum `.env` foi acessado.

**Riscos com cenário**

- **Execução fora dos controles:** uma instrução maliciosa em conteúdo externo induz o agente a chamar o CLI autenticado. A ordem vai diretamente à Binance, sem Risk Engine, auditoria ou kill switch do HUNTER. O skill pede `CONFIRM` para transações em produção, mas isso é uma instrução textual, não uma barreira técnica. Também permite requisições arbitrárias assinadas. [Skill principal](https://github.com/binance/binance-skills-hub/blob/main/skills/binance/binance/SKILL.md).
- **Exposição de credenciais:** durante um diagnóstico, o agente recebe orientação para carregar ou exibir segredos. O README admite inclusive fornecê-los pelo chat. Isso conflita diretamente com o isolamento exigido pelo projeto. Uma chave sem permissão de saque ainda pode permitir operações com perdas. [README](https://github.com/binance/binance-skills-hub).
- **Confusão entre ambientes:** um teste herda perfil ou credenciais reais e usa produção. O CLI documenta `prod` como padrão e permite sobrescrever URLs; selecionar testnet apenas por variável não constitui isolamento suficiente. [CLI oficial](https://github.com/binance/binance-cli).
- **Cadeia de fornecimento:** o instalador apontado para `latest`, executado por `curl | sh`, pode mudar entre revisão e instalação. Um artefato comprometido executaria com os privilégios do processo. Não constatei comprometimento; constatei esse mecanismo de instalação. [Instalação](https://github.com/binance/binance-cli#installation).
- **Score contaminado:** incorporar sinais externos sem fórmula e entradas reproduzíveis impede explicar o resultado. Usar retrospectivamente `maxGain` como informação disponível no disparo introduziria vazamento de futuro no backtest. Esse campo aparece no skill de sinais. [Trading Signal](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/trading-signal/SKILL.md).

**Uso legítimo, se houver**

Sim: consulta documental passiva e, havendo necessidade concreta, **CLI isolado para capturar fixtures**, sem instalar o hub nos agentes.

Para fixtures autenticadas: execução por humano ou rotina determinística controlada; credenciais exclusivamente de testnet inacessíveis aos agentes; ambiente descartável sem segredos de produção; rede permitindo somente os destinos de teste necessários; versão fixada e artefato revisado. Agentes receberiam apenas resultados sanitizados. **Testnet não abre exceção para agente executar ordens.**

As fixtures devem registrar origem, ambiente, instante UTC e versão, permanecer rotuladas em testes e preservar valores monetários como strings/`Decimal`. Dados de testnet servem para contratos e tratamento de respostas, não para validar rentabilidade ou liquidez real.

**Concordâncias e discordâncias**

Concordo com a rejeição da instalação e com consultar referências USDS-M quando úteis.

Faço duas ressalvas: instalar Markdown sozinho não concede acesso à conta; o risco se concretiza ao combinar instruções, execução e credenciais. E os sinais consultados não estão demonstrados como “gerados por LLM”: são dados externos cuja metodologia não está suficientemente exposta no skill. Isso já basta para rejeitá-los como fundamento reproduzível do Opportunity Score, sem atribuir uma tecnologia não comprovada.