"""Configuração do modelo 1 (classificação de cobertura do solo): caminhos do data lake.

Roda 100% local — lê o stack de 13 bandas da etapa 4 (`silver/features/`) e escreve o raster
classificado + a tabela de percentuais na silver. Não fala com o Earth Engine.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# .../pipeline-dados/modelos/modelo_1_classificacao_imagem/config.py -> .../pipeline-dados
REPO_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(REPO_ROOT / ".env")

# Mesmo mapa curto<->extenso de `projetos/04_indices_espectrais/config.py` — não importado de lá
# de propósito (cada etapa/modelo carrega sua própria config, convenção do repo).
DIR_POR_SENSOR = {"s2": "sentinel2", "landsat": "landsat"}

# Sobrescrevível por SENTINELA_MODELO_IMPACTO (mesmo nome de variável usado no
# modelo-imagens-satelite, ADR-006 §4) — pra avaliar um modelo candidato sem editar código.
MODELO_VERSAO = os.environ.get("SENTINELA_MODELO_IMPACTO", "rf_v1.0-tuned")


class Settings:
    def __init__(self) -> None:
        self.data_root = Path(os.environ.get("DATA_ROOT", REPO_ROOT / "dados")).resolve()

    @property
    def artefatos_dir(self) -> Path:
        return Path(__file__).resolve().parent / "artefatos"

    @property
    def modelo_path(self) -> Path:
        return self.artefatos_dir / f"{MODELO_VERSAO}.joblib"

    def silver_features_dir(self, sensor_token: str) -> Path:
        """Entrada: `dados/silver/features/{sensor}/` — saída da etapa 4."""
        sensor = DIR_POR_SENSOR.get(sensor_token, sensor_token)
        return self.data_root / "silver" / "features" / sensor

    def classificado_dir(self, sensor_token: str) -> Path:
        """Saída: `dados/silver/classificado/{modelo_versao}/{sensor}/` — raster de 1 banda
        (classe 0-5) + raster de confiança, por site/ano. Versionado pelo modelo (`MODELO_VERSAO`)
        no path: um modelo candidato nunca sobrescreve a saída de outro."""
        sensor = DIR_POR_SENSOR.get(sensor_token, sensor_token)
        return self.data_root / "silver" / "classificado" / MODELO_VERSAO / sensor

    @property
    def manifests_dir(self) -> Path:
        return self.data_root / "manifests"


SETTINGS = Settings()
