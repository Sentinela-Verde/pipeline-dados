"""Configuração da etapa 4 (índices espectrais): caminhos do data lake.

Esta etapa roda 100% local — não fala com o Earth Engine, não lê credencial, não precisa de
`EE_PROJECT`. Só lê o bronze produzido pela etapa 2 e escreve no silver.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# .../pipeline-dados/projetos/04_indices_espectrais/config.py -> .../pipeline-dados
REPO_ROOT = Path(__file__).resolve().parents[2]

PARAMS_DIR = Path(__file__).resolve().parent / "parametros"
SITES_PATH = PARAMS_DIR / "sites.geojson"

load_dotenv(REPO_ROOT / ".env")

# O código usa o token curto do sensor ("s2"), que é também o prefixo dos manifests da etapa 2
# (`s2_{site}_{ano}.json`). No disco, porém, o diretório do bronze usa o nome por extenso. Este
# mapa é a única ponte entre as duas convenções.
DIR_POR_SENSOR = {"s2": "sentinel2", "landsat": "landsat"}

# Subpasta de `dados/bronze/` de onde os .tif brutos são lidos — espelha
# `02_extracao_imagem.config.definir_subpasta_imagens()`. Precisa ser setada igual à subpasta que
# a etapa 2 usou pra gerar aquele site_id, senão `bronze_imagens_dir` procura no lugar errado.
# Usado em 2026-09-14 pra calcular índices dos candidatos a grupo de controle (bronze separado).
_SUBPASTA_IMAGENS_PADRAO = "imagens_satelite"
_subpasta_imagens = _SUBPASTA_IMAGENS_PADRAO


def definir_subpasta_imagens(nome: str) -> None:
    if not nome or "/" in nome or "\\" in nome or nome in (".", ".."):
        raise ValueError(f"nome de subpasta inválido: {nome!r}")
    global _subpasta_imagens
    _subpasta_imagens = nome


class Settings:
    """Caminhos do data lake para esta etapa."""

    def __init__(self) -> None:
        self.data_root = Path(os.environ.get("DATA_ROOT", REPO_ROOT / "dados")).resolve()

    @property
    def manifests_dir(self) -> Path:
        """`dados/manifests/` — os manifests da etapa 2 (entrada) e os desta etapa (saída)."""
        return self.data_root / "manifests"

    def bronze_imagens_dir(self, sensor_token: str) -> Path:
        """Entrada: `dados/bronze/{subpasta}/{sensor}/` — saída da etapa 2 (`{subpasta}` normalmente
        `imagens_satelite`; ver `definir_subpasta_imagens()`)."""
        sensor = DIR_POR_SENSOR.get(sensor_token, sensor_token)
        return self.data_root / "bronze" / _subpasta_imagens / sensor

    def silver_features_dir(self, sensor_token: str) -> Path:
        """Saída: `dados/silver/features/{sensor}/`.

        Silver, não bronze: bandas + 7 índices são dado DERIVADO do bronze, reproduzível a
        qualquer momento a partir dele mais este código.
        """
        sensor = DIR_POR_SENSOR.get(sensor_token, sensor_token)
        return self.data_root / "silver" / "features" / sensor


SETTINGS = Settings()
