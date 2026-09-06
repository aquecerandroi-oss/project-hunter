**P1 — (b):** [evaluate.py:241](C:/dev/project-hunter/packages/risk-core/hunter_risk/evaluate.py:241) verifica apenas se a posição existe na carteira; [evaluate.py:248](C:/dev/project-hunter/packages/risk-core/hunter_risk/evaluate.py:248) limita pela quantidade do argumento separado.

Cenário: após saída parcial de 6 unidades, `portfolio` contém a posição com 4, mas `position` ainda contém 10, com mesmo ID e mercado. Pedido de saída de 10 recebe aprovação de 10. A divergência está nos próprios argumentos e pode ser detectada pelo núcleo puro. Validar a consistência ou limitar também pela quantidade presente na carteira.

**OBSIDIAN**

- **Risk Engine** — registrar a necessidade de reconciliar a posição recebida com o estado opcional da carteira.