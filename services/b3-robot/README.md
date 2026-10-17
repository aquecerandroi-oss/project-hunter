# b3-robot — robô da B3 no MetaTrader 5

Esqueleto do workspace (tarefa R0c de `docs/design/robo-b3-mt5.md`). Ainda sem lógica.

O pacote `MetaTrader5` só existe para Windows (`sys_platform == 'win32'`): o CI Linux não o instala
e o adaptador (R2) o importa sob demanda, nunca no import do módulo.
