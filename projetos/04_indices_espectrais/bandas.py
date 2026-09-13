"""Contrato de nomes/ordem das bandas harmonizadas produzidas pela etapa 2.

Duplicado aqui de propósito, em vez de importar de `02_extracao_imagem/harmonizacao.py`: aquele
módulo importa `ee`, e esta etapa roda 100% local, sobre os .tif já baixados — arrastar o Earth
Engine para cá só por seis strings seria pior que repetir as seis strings.

A duplicação é segura porque `_ler_raster_origem()` compara esta lista contra as bandas gravadas
no raster e no manifest da etapa 2 a cada arquivo processado: se as duas divergirem, a etapa falha
no primeiro tif, alto e claro, em vez de gerar feature com banda trocada.
"""

from __future__ import annotations

_BANDAS: tuple[str, ...] = ("blue", "green", "red", "nir", "swir1", "swir2")


def bandas_harmonizadas() -> list[str]:
    """Lista ordenada canônica das 6 bandas harmonizadas — contrato com a etapa 2."""
    return list(_BANDAS)
