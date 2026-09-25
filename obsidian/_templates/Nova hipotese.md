<%*
/* Modelo Templater para um bloco de hipótese em Fila de Hipoteses.md.
   Como usar: abrir Fila de Hipoteses.md, ir até o fim do arquivo, inserir este
   modelo (Templater: Insert Template), depois:
   1. Trocar H-0XX pelo próximo id livre (olhar o último "## H-0nn —" do arquivo
      e somar 1 — o moinho recusa id repetido, infra/research/queue.py).
   2. Preencher o título depois do "—" e todos os seis comentários abaixo.
   3. Apagar os comentários <!-- --> depois de preencher (eles só orientam).
   O carregador (infra/research/queue.py) exige exatamente estes seis campos —
   origem, variável, população, previsão, refutação, status — e recusa o bloco
   inteiro se faltar um. "registro" não é exigido pelo carregador, mas é
   convenção da casa: carimba a hora em que a previsão foi congelada, antes de
   olhar qualquer resultado (Fila de Hipoteses.md, regra 3).
*/
-%>
## H-0XX — <título curto da ideia>

- **origem:** <!-- de onde veio: nota (KB-00xx), estudo (EXP-00xx/EXP-Mnn), conversa com o Everton -->
- **variável:** <!-- a variável candidata, como é calculada, e a direção (high/low) -->
- **população:** <!-- que linhas entram na medição, e o que fica de fora -->
- **previsão:** <!-- o que a hipótese afirma, com sinal e tamanho do efeito -->
- **refutação:** <!-- o que faz abandonar a hipótese (limite do IC, forma da curva, amostra mínima) -->
- **registro:** <% tp.date.now("DD/MM/YYYY HH:mm") %> BRT, antes de <!-- o que ainda não foi olhado -->
- **status:** aberta
