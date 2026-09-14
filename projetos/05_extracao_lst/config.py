"""Configuração da etapa 5 (extração de LST): variáveis de ambiente + YAML de parametros/.

Escopo deliberadamente restrito ao que esta etapa lê. Cada etapa de `projetos/` carrega a sua
própria config — não existe um módulo de config compartilhado entre etapas, porque isso
reintroduziria o acoplamento que a separação por etapa veio desfazer.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# .../pipeline-dados/projetos/05_extracao_lst/config.py -> .../pipeline-dados
REPO_ROOT = Path(__file__).resolve().parents[2]

# Parâmetros desta etapa ficam ao lado do código que os lê, não numa pasta global de config.
PARAMS_DIR = Path(__file__).resolve().parent / "parametros"
SITES_PATH = PARAMS_DIR / "sites.geojson"

load_dotenv(REPO_ROOT / ".env")


class ConfigError(RuntimeError):
    """Erro de configuração com mensagem acionável (não é pra virar traceback cru)."""


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(
            f"Variável de ambiente '{name}' não definida. Copie .env.example para .env "
            f"e preencha '{name}'."
        )
    return value


def _load_yaml(filename: str) -> dict:
    path = PARAMS_DIR / filename
    if not path.exists():
        raise ConfigError(f"Arquivo de parâmetros '{path}' não existe.")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Settings:
    """Acesso preguiçoso e com mensagem clara às configurações da etapa."""

    def __init__(self) -> None:
        self.data_root = Path(os.environ.get("DATA_ROOT", REPO_ROOT / "dados")).resolve()

    @property
    def ee_project(self) -> str:
        return _require_env("EE_PROJECT")

    @property
    def ee_service_account_key(self) -> Path:
        return Path(_require_env("EE_SERVICE_ACCOUNT_KEY")).expanduser().resolve()

    @property
    def lst_dir(self) -> Path:
        """`dados/bronze/temperatura/` — série anual, cenas brutas e log de extração.

        Bronze porque é dado bruto de fonte externa (MODIS via Earth Engine), como as imagens e
        os rótulos: nada aqui é derivado de outra etapa deste repositório.
        """
        return self.data_root / "bronze" / "temperatura"

    def params(self) -> dict:
        return _load_yaml("params.yml")


SETTINGS = Settings()
