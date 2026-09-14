"""Etapa 1 (coleta de data center) — sub-etapa: filtra os facilities elegíveis pro estudo.

Roda DEPOIS de `run_pipeline.py` (etapa 1 principal), que gera
`dados/bronze/datacentermap/datacentermap_datacenters.csv`. Aplica os critérios de elegibilidade
descritos em `config.py`: data center ativo, já construído (`stage`), listado como `Facility`
(não `Campus`/`Multi-Tenant Building`, que agregam vários facilities e distorceriam a unidade de
observação do estudo), com ano de operação dentro da janela de estudo (2018-2024, pra sobrar pelo
menos 3 anos de série de satélite antes e depois da abertura).

Readaptado de `data-extraction/transform/filtra_datacenter/step1_filtra_dados.py` — mesma lógica
de filtro, lendo direto do bronze desta estrutura em vez de `data/raw/outputs_extraction/`.

Saída: `dados/silver/datacenter_filtrado.csv` (mesmo separador `;`, mesmo schema reduzido de
porte) — é o que `modelos/modelo_2_grupo_controle/` e a extração de imagem (etapa 2) esperam
como lista de data centers do estudo.

Uso:
    cd projetos/01_coleta_datacenter/filtro_elegibilidade
    pip install -r requirements.txt
    python step8_filtra_elegibilidade.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import SETTINGS
import config


def filtra_datacenters(df: pd.DataFrame) -> pd.DataFrame:
    mask_ativo = df["status"] == config.STATUS_ATIVO
    mask_ano_min = df["ano_operacional"] > config.ANO_OPERACIONAL_MIN
    mask_ano_max = df["ano_operacional"] < config.ANO_OPERACIONAL_MAX
    mask_stage = df["stage"] == config.STAGE_ALVO
    mask_listagem = df["tipo_listagem"] == config.TIPO_LISTAGEM_ALVO

    df_filtrado = df[mask_ativo & mask_ano_min & mask_ano_max & mask_stage & mask_listagem]
    df_filtrado = df_filtrado.reset_index(drop=True)
    df_filtrado["ano_operacional"] = df_filtrado["ano_operacional"].astype(int)
    return df_filtrado[config.COLUNAS_FINAIS]


def main() -> None:
    if not SETTINGS.csv_bronze.exists():
        raise SystemExit(
            f"{SETTINGS.csv_bronze} não existe — rode a coleta (run_pipeline.py, etapa 1) antes "
            f"desta sub-etapa."
        )

    df = pd.read_csv(SETTINGS.csv_bronze, sep=";", encoding="utf-8-sig", low_memory=False)
    print(f"{len(df)} data centers lidos de {SETTINGS.csv_bronze.name}")

    df_filtrado = filtra_datacenters(df)
    print(f"{len(df_filtrado)} data centers elegíveis (de {len(df)}) — status={config.STATUS_ATIVO}, "
          f"stage={config.STAGE_ALVO}, tipo_listagem={config.TIPO_LISTAGEM_ALVO!r}, "
          f"ano_operacional em ({config.ANO_OPERACIONAL_MIN}, {config.ANO_OPERACIONAL_MAX})")

    SETTINGS.csv_silver.parent.mkdir(parents=True, exist_ok=True)
    df_filtrado.to_csv(SETTINGS.csv_silver, sep=";", index=False, encoding="utf-8")
    print(f"Salvo em {SETTINGS.csv_silver}")


if __name__ == "__main__":
    main()
