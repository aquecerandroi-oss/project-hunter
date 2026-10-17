"""Tela RGB em NumPy, fonte bitmap 5×7 e codificador PNG da biblioteca padrão.

Por que não matplotlib: o PNG dele carrega a versão no metadado e o texto depende do FreeType
instalado, então o hash da imagem muda de máquina para máquina. Aqui cada pixel sai de aritmética
inteira e o hash canônico é o dos pixels (o do PNG vai junto, como conveniência).
"""

from __future__ import annotations

import hashlib
import struct
import zlib

import numpy as np
from numpy.typing import NDArray

Cor = tuple[int, int, int]

_GLIFOS: dict[str, tuple[str, ...]] = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    " ": ("00000",) * 7,
}

TEXTO_PERMITIDO = frozenset(_GLIFOS)
"""Só dígitos e ``+ - . : %``: a imagem não consegue escrever data, símbolo ou nome."""


class Tela:
    def __init__(self, largura: int, altura: int, fundo: Cor) -> None:
        self.largura, self.altura = largura, altura
        self.px: NDArray[np.uint8] = np.empty((altura, largura, 3), dtype=np.uint8)
        self.px[:, :] = fundo

    def retangulo(self, x0: int, y0: int, x1: int, y1: int, cor: Cor) -> None:
        """Preenche [x0, x1] × [y0, y1] (inclusive), recortado à tela."""
        xa, xb = sorted((x0, x1))
        ya, yb = sorted((y0, y1))
        xa, ya = max(xa, 0), max(ya, 0)
        xb, yb = min(xb, self.largura - 1), min(yb, self.altura - 1)
        if xa <= xb and ya <= yb:
            self.px[ya : yb + 1, xa : xb + 1] = cor

    def tracejado_vertical(self, x: int, y0: int, y1: int, cor: Cor, passo: int = 4) -> None:
        for y in range(min(y0, y1), max(y0, y1) + 1, 2 * passo):
            self.retangulo(x, y, x, min(y + passo - 1, max(y0, y1)), cor)

    def texto(self, x: int, y: int, texto: str, cor: Cor, escala: int = 2) -> None:
        for i, ch in enumerate(texto):
            glifo = _GLIFOS.get(ch)
            if glifo is None:
                raise ValueError(f"caractere fora da fonte: {ch!r}")
            for lin, bits in enumerate(glifo):
                for col, bit in enumerate(bits):
                    if bit == "1":
                        xx = x + (i * 6 + col) * escala
                        yy = y + lin * escala
                        self.retangulo(xx, yy, xx + escala - 1, yy + escala - 1, cor)

    @staticmethod
    def largura_texto(texto: str, escala: int = 2) -> int:
        return (len(texto) * 6 - 1) * escala

    def sha256_pixels(self) -> str:
        h = hashlib.sha256()
        h.update(f"{self.largura}x{self.altura}x3|".encode())
        h.update(np.ascontiguousarray(self.px).tobytes())
        return h.hexdigest()

    def png(self) -> bytes:
        """PNG RGB 8 bits, filtro 0 em toda linha, zlib nível 6, sem metadado."""
        linhas = np.zeros((self.altura, 1 + 3 * self.largura), dtype=np.uint8)
        linhas[:, 1:] = self.px.reshape(self.altura, 3 * self.largura)
        ihdr = struct.pack(">IIBBBBB", self.largura, self.altura, 8, 2, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + _bloco(b"IHDR", ihdr)
            + _bloco(b"IDAT", zlib.compress(linhas.tobytes(), 6))
            + _bloco(b"IEND", b"")
        )


def _bloco(tipo: bytes, dados: bytes) -> bytes:
    crc = zlib.crc32(tipo + dados) & 0xFFFFFFFF
    return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", crc)
