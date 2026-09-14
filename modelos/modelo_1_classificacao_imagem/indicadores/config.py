"""Configuração do export de indicadores — o CSV de área por classe.

Roda 100% local, sobre os rasters já classificados pela inferência do Modelo 1. Não chama Earth
Engine e não precisa de credencial.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# .../pipeline-dados/modelos/modelo_1_classificacao_imagem/indicadores/config.py -> repo
REPO_ROOT = Path(__file__).resolve().parents[3]

PARAMS_DIR = Path(__file__).resolve().parent / "parametros"
SITES_PATH = PARAMS_DIR / "sites.geojson"
FATOR_CORRECAO_PATH = PARAMS_DIR / "fator_correcao_sensor_sv20.json"


def caminho_fator_correcao(modelo_versao: str) -> Path:
    """Um JSON de fator por classificação: `fator_correcao_sensor_sv20_<modelo_versao>.json`.

    O fator é calibrado SOBRE uma classificação — o mesmo modelo que gerou os rasters. Aplicar
    o de outra é erro silencioso, e foi o que aconteceu na primeira versão deste CSV. O nome
    sem sufixo é o histórico (`rf_v1.0-tuned`) e só é usado se não houver o do modelo pedido;
    a guarda em `carregar_fator_correcao_sv20()` barra a aplicação cruzada."""
    versionado = PARAMS_DIR / f"fator_correcao_sensor_sv20_{modelo_versao}.json"
    return versionado if versionado.exists() else FATOR_CORRECAO_PATH

load_dotenv(REPO_ROOT / ".env")

# Resolução nominal por sensor. Espelha o contrato de grade da etapa 2 (`02_extracao_imagem`),
# onde estes valores são constantes no código — aqui são só leitura.
RESOLUCAO_M = {"s2": 10, "landsat": 30}


class ConfigError(RuntimeError):
    """Erro de configuração com mensagem acionável (não é pra virar traceback cru)."""


def _load_yaml(filename: str) -> dict:
    path = PARAMS_DIR / filename
    if not path.exists():
        raise ConfigError(f"Arquivo de parâmetros '{path}' não existe.")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Settings:
    def __init__(self) -> None:
        self.data_root = Path(os.environ.get("DATA_ROOT", REPO_ROOT / "dados")).resolve()

    @property
    def manifests_dir(self) -> Path:
        """`dados/manifests/` — os manifests de classificação são a entrada desta etapa."""
        return self.data_root / "manifests"

    def classificado_dir(self, token: str) -> Path:
        """`dados/silver/classificado[-<tag>]/` — rasters de classe da inferência do Modelo 1."""
        return self.data_root / "silver" / token

    @property
    def gold_dir(self) -> Path:
        """`dados/gold/` — onde o CSV de indicadores é publicado."""
        return self.data_root / "gold"

    def classes(self) -> dict:
        return _load_yaml("classes.yml")


SETTINGS = Settings()
