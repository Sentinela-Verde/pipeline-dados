"""Configuração da etapa 3 (extração de rótulos): variáveis de ambiente + YAML de parametros/.

Escopo restrito ao que esta etapa lê. Cada etapa de `projetos/` carrega a sua própria config.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# .../pipeline-dados/projetos/03_extracao_labels/config.py -> .../pipeline-dados
REPO_ROOT = Path(__file__).resolve().parents[2]

PARAMS_DIR = Path(__file__).resolve().parent / "parametros"
SITES_PATH = PARAMS_DIR / "sites.geojson"

load_dotenv(REPO_ROOT / ".env")

# Token de manifest -> nome da fonte no disco. O token (`labels`/`labels-dw`) é o que já está
# gravado nos 494 manifests existentes e por isso não muda; o diretório usa o nome da fonte,
# que é o que a árvore de `dados/` do README pede e é legível para quem abre a pasta.
FONTE_POR_TOKEN = {"labels": "mapbiomas", "labels-dw": "dynamic_world"}


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
    def manifests_dir(self) -> Path:
        """`dados/manifests/` — inclui os manifests da etapa 2, de onde esta etapa herda a grade."""
        return self.data_root / "manifests"

    def labels_dir(self, token: str) -> Path:
        """`dados/bronze/labels/{mapbiomas|dynamic_world}/` — rótulo é bruto de fonte externa."""
        return self.data_root / "bronze" / "labels" / FONTE_POR_TOKEN.get(token, token)

    def params(self) -> dict:
        return _load_yaml("params.yml")

    def token_labels(self) -> str:
        """Token que separa os rótulos por fonte, no disco e nos manifests.

        MapBiomas e Dynamic World descrevem os MESMOS pixels com definições diferentes de classe.
        Guardar os dois no mesmo caminho faria a troca de fonte sobrescrever silenciosamente os
        tifs da outra — e com eles a capacidade de reproduzir o modelo treinado sobre ela.

        MapBiomas mantém `labels` (legado intacto); o Dynamic World usa `labels-dw`.
        """
        fonte = (self.params().get("labels") or {}).get("fonte_principal", "mapbiomas")
        return "labels-dw" if fonte == "dynamic_world" else "labels"

    def classes(self) -> dict:
        return _load_yaml("classes.yml")


SETTINGS = Settings()
