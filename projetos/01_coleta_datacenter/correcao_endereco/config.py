"""Configuração da sub-etapa de correção de endereço (etapa 1, pós-coleta).

Mesmo padrão das demais etapas de `projetos/` (ver `02_extracao_imagem/config.py`): config própria
por etapa, carregada de variáveis de ambiente (`.env` na raiz do repo) + `DATA_ROOT`. Não existe
config compartilhada entre etapas de propósito.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# .../01_coleta_datacenter/correcao_endereco/config.py -> .../pipeline-dados
REPO_ROOT = Path(__file__).resolve().parents[3]

load_dotenv(REPO_ROOT / ".env")


class ConfigError(RuntimeError):
    """Erro de configuração com mensagem acionável (não é pra virar traceback cru)."""


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(
            f"Variável de ambiente '{name}' não definida. Copie .env.example para .env "
            f"e preencha '{name}' (precisa da Geocoding API habilitada + faturamento ativo "
            f"no projeto do Google Cloud)."
        )
    return value


class Settings:
    """Acesso preguiçoso e com mensagem clara às configurações desta sub-etapa."""

    def __init__(self) -> None:
        self.data_root = Path(os.environ.get("DATA_ROOT", REPO_ROOT / "dados")).resolve()

    @property
    def google_maps_api_key(self) -> str:
        return _require_env("GOOGLE_MAPS_API_KEY")

    @property
    def csv_bronze(self) -> Path:
        """Entrada: o CSV bruto do scraping (step6_build_csv.py)."""
        return self.data_root / "bronze" / "datacentermap" / "datacentermap_datacenters.csv"

    @property
    def csv_silver(self) -> Path:
        """Saída: mesmas linhas, endereço/município/estado/país/CEP padronizados pela Geocoding API."""
        return self.data_root / "silver" / "datacentermap_enderecos_corrigidos.csv"


SETTINGS = Settings()
