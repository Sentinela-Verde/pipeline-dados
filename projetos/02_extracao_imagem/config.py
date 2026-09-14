"""Configuração da etapa 2 (extração de imagem): variáveis de ambiente + YAML de parametros/.

Escopo deliberadamente restrito ao que esta etapa lê. Cada etapa de `projetos/` carrega a sua
própria config — não existe um módulo de config compartilhado entre etapas, porque isso
reintroduziria o acoplamento que a separação por etapa veio desfazer.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# .../pipeline-dados/projetos/02_extracao_imagem/config.py -> .../pipeline-dados
REPO_ROOT = Path(__file__).resolve().parents[2]

# Parâmetros desta etapa ficam ao lado do código que os lê, não numa pasta global de config.
PARAMS_DIR = Path(__file__).resolve().parent / "parametros"
SITES_PATH = PARAMS_DIR / "sites.geojson"

load_dotenv(REPO_ROOT / ".env")

# Subpasta de `dados/bronze/` onde os .tif de imagem de satélite são gravados — por padrão
# `imagens_satelite` (os sites de tratamento/AOI oficiais). `definir_subpasta_imagens()` redireciona
# pra outra pasta (ex.: `imagens_satelite_candidatos_grupo_controle`) sem duplicar nenhum dos dois
# módulos de ingestão (`landsat.py`/`sentinel2.py`) — mesmo padrão de `sentinela.predict
# .definir_token_saida()` no `modelo-imagens-satelite` (ADR-006 §4: um modelo candidato escreve em
# token próprio, nunca sobrescreve a saída "oficial"). Usado em 2026-09-14 pra gerar imagem dos
# candidatos a grupo de controle sem misturar com as 21 AOIs de tratamento.
_SUBPASTA_IMAGENS_PADRAO = "imagens_satelite"
_subpasta_imagens = _SUBPASTA_IMAGENS_PADRAO


def definir_subpasta_imagens(nome: str) -> None:
    if not nome or "/" in nome or "\\" in nome or nome in (".", ".."):
        raise ValueError(f"nome de subpasta inválido: {nome!r}")
    global _subpasta_imagens
    _subpasta_imagens = nome


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
    def imagens_dir(self) -> Path:
        """`dados/bronze/{subpasta}/` — os GeoTIFF por sensor/site/ano moram aqui.

        `{subpasta}` é `imagens_satelite` por padrão; `definir_subpasta_imagens()` redireciona."""
        return self.data_root / "bronze" / _subpasta_imagens

    @property
    def manifests_dir(self) -> Path:
        """`dados/manifests/` — proveniência (sha256 + parâmetros), commitada; o .tif não é."""
        return self.data_root / "manifests"

    def params(self) -> dict:
        return _load_yaml("params.yml")


SETTINGS = Settings()
