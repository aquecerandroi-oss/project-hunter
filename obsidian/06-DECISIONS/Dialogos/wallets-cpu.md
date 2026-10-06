---
tags: [dialogo, astra, carteiras, desempenho, h-030]
date: 2026-10-06
updated: 2026-10-06
status: registro
owner: sexta-feira
decided_on: 2026-10-06
by: sexta-feira + astra
tarefa: CPU do motor de carteiras 1c-bis (≈ 31–34 h/núcleo por noite, extrapolação sintética)
veredito: rodada 1 sem decisão conjunta; rodada 2 enviada aceitando as correções (resposta dela ainda não registrada aqui)
---

# CPU do motor de carteiras: medir antes de reescrever

**Problema:** o motor 1c-bis ([[wallets-1c-bis]]) cabe na memória. Mas, extrapolado do bench sintético, levaria ≈ 31–34 h por noite num núcleo para 200–217 M fills de janela. A VPS tem poucos núcleos e roda produção.

**Rodada 1, Astra:** ainda não é decisão conjunta. Duas correções e três must-fix.
- **Correção 1:** medir a forma do custo (perfil) antes de escolher vetorização ou paralelismo. Pontos suspeitos de trabalho repetido:
  - `_prepared` deduplica e ordena a cada uma das três passadas;
  - cada cópia varre a fita para achar o gatilho e reconstruir o líder;
  - `MintCarry.flow_of` reconstrói o dicionário a cada consulta;
  - os pares de compradores no mesmo slot são combinatórios.
- **Correção 2:** o avanço "snapshot anterior + dia novo − dia velho" não é equivalente (contraexemplo das gêmeas). Mas "impossível em geral" não está provado: índices ou fatos independentes da janela podem ser reaproveitados depois do perfil.
- **Must-fix:**
  - não cortar dependências para reduzir a população (venda pequena, carteira antes da fusão, mint não copiável);
  - reduzir os acumuladores de forma exata antes de paralelizar (conjuntos, mediana exata, teto diário global);
  - 2 núcleos sozinhos não chegam a 2 h: é preciso ≈ 8× menos trabalho por núcleo.
- **Mudar o universo** (atividade mínima, só mints compráveis) é nova versão do protocolo e decisão do Everton.
- **Rodar fora da VPS** é opção operacional válida, se o envelope medido não couber.

**Rodada 2, Sexta-feira (enviada em 06/10):** aceitou as duas correções e os três must-fix. Ordem proposta:
1. perfil (cProfile só do stream, por passada) e matriz de escala;
2. tirar o trabalho repetido do trecho dominante, um por vez, com diferencial contra uma referência congelada;
3. fusão dos acumuladores e 2 workers, se a fração paralela justificar;
4. vetorização seletiva;
5. só então rodar fora da VPS.

Aceite de ponta a ponta: < 2 h sob 2 núcleos, como meta proposta. A resposta da rodada 2 está em `.claude/state/dialogue-wallets-cpu.md`; a síntese fica pendente de leitura.

[[wallets-1c-bis]] · [[wallet-tape-storage]] · [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]] · [[EXP-M15-carteiras-vencedoras]]
