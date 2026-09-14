"""Configuração da sub-etapa de filtro de elegibilidade (etapa 1, pós-coleta).

Mesmo padrão das demais etapas de `projetos/` (ver `02_extracao_imagem/config.py` e
`correcao_endereco/config.py`): config própria por etapa, carregada de variáveis de ambiente
(`.env` na raiz do repo) + `DATA_ROOT`. Não existe config compartilhada entre etapas de propósito.

Readaptado de `data-extraction/transform/filtra_datacenter/config.py` — mesmos critérios de
elegibilidade, só os caminhos de entrada/saída mudaram pra a estrutura deste repositório.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# .../01_coleta_datacenter/filtro_elegibilidade/config.py -> .../pipeline-dados
REPO_ROOT = Path(__file__).resolve().parents[3]

load_dotenv(REPO_ROOT / ".env")

# --- Critérios de elegibilidade ---------------------------------------------
# Ver "Definição do Range de dados do facility" no notebook original de data-extraction:
# considera-se uma janela móvel de anos ao redor da abertura do data center, por isso os limites
# abaixo (ano_operacional > MIN e < MAX, ambos exclusivos -> janela efetiva 2018-2024).
STATUS_ATIVO = 1          # coluna `status` do datacentermap: 1 = em operação
STAGE_ALVO = 2             # coluna `stage` do datacentermap: 2 = facility já construído/operacional
ANO_OPERACIONAL_MIN = 2017  # exclusivo — amostra ficaria muito distante do período de estudo antes disso
ANO_OPERACIONAL_MAX = 2025  # exclusivo — precisa sobrar pelo menos 2026 como ano de referência pós-obra
TIPO_LISTAGEM_ALVO = "Facility"  # exclui "Campus" e "Multi-Tenant Building" (agregam vários facilities)

# Colunas mantidas no CSV final (identificação + porte — sem certificação/segurança, não usadas
# nas etapas seguintes). Sem `estado`: a versão corrigida por geocoding fica em
# `correcao_endereco/`, mas esta sub-etapa preserva o schema original do filtro pra não quebrar
# quem já consome `datacenter_filtrado.csv` (ex.: Modelo 2).
COLUNAS_FINAIS = [
    "nome_datacenter", "endereco", "cidade", "latitude", "longitude", "tags",
    "mw_construido", "whitespace_construido_m",
    "ano_operacional", "tipo_construcao",
]


class Settings:
    """Acesso preguiçoso e com mensagem clara às configurações desta sub-etapa."""

    def __init__(self) -> None:
        self.data_root = Path(os.environ.get("DATA_ROOT", REPO_ROOT / "dados")).resolve()

    @property
    def csv_bronze(self) -> Path:
        """Entrada: o CSV bruto do scraping (step6_build_csv.py)."""
        return self.data_root / "bronze" / "datacentermap" / "datacentermap_datacenters.csv"

    @property
    def csv_silver(self) -> Path:
        """Saída: só os data centers elegíveis pro estudo, com o schema reduzido de porte."""
        return self.data_root / "silver" / "datacenter_filtrado.csv"


SETTINGS = Settings()
