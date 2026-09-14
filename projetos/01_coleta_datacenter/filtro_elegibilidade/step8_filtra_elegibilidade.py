"""Etapa 1 (coleta de data center) — sub-etapa: filtra os facilities elegíveis pro estudo.

Roda DEPOIS de `correcao_endereco/` (que roda depois de `run_pipeline.py`) e ANTES de
`step9_consolida_aoi.py` — encadeamento completo desta sub-etapa:

    run_pipeline.py            -> dados/bronze/datacentermap/datacentermap_datacenters.csv
    correcao_endereco/         -> dados/silver/datacentermap_enderecos_corrigidos.csv
    step8 (este arquivo)       -> dados/silver/datacenter_filtrado_facilities.csv (1 linha/facility)
    step9_consolida_aoi.py     -> dados/silver/datacenter_filtrado.csv (1 linha/AOI, o artefato final)

Lê o CSV já com endereço/município/estado padronizados pela Geocoding API, não o bronze cru —
assim quem consome a saída já recebe `cidade` corrigida, sem precisar rodar `correcao_endereco/`
de novo por fora.

Aplica os critérios de elegibilidade descritos em `config.py`: data center ativo, já construído
(`stage`), listado como `Facility` (não `Campus`/`Multi-Tenant Building`, que agregam vários
facilities e distorceriam a unidade de observação do estudo), com ano de operação dentro da
janela de estudo (2018-2024, pra sobrar pelo menos 3 anos de série de satélite antes e depois da
abertura).

Readaptado de `data-extraction/transform/filtra_datacenter/step1_filtra_dados.py` — mesma lógica
de filtro; lá a entrada era o bronze direto (`correcao_endereco/` não existia nesse repositório)
e a saída não tinha `operadora` (adicionada aqui — necessária pro step9 agrupar por AOI).

Saída: `dados/silver/datacenter_filtrado_facilities.csv` — 1 linha por facility elegível. **Não é
o artefato final** desta sub-etapa: várias facilities do mesmo operador podem ser o mesmo campus
(AOI) — isso só é resolvido em `step9_consolida_aoi.py`.

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
    if not SETTINGS.csv_entrada.exists():
        raise SystemExit(
            f"{SETTINGS.csv_entrada} não existe — rode a correção de endereço "
            f"(correcao_endereco/step7_corrige_endereco.py) antes desta sub-etapa."
        )

    df = pd.read_csv(SETTINGS.csv_entrada, sep=";", encoding="utf-8-sig", low_memory=False)
    print(f"{len(df)} data centers lidos de {SETTINGS.csv_entrada.name}")

    df_filtrado = filtra_datacenters(df)
    print(f"{len(df_filtrado)} data centers elegíveis (de {len(df)}) — status={config.STATUS_ATIVO}, "
          f"stage={config.STAGE_ALVO}, tipo_listagem={config.TIPO_LISTAGEM_ALVO!r}, "
          f"ano_operacional em ({config.ANO_OPERACIONAL_MIN}, {config.ANO_OPERACIONAL_MAX})")

    SETTINGS.csv_facilities.parent.mkdir(parents=True, exist_ok=True)
    df_filtrado.to_csv(SETTINGS.csv_facilities, sep=";", index=False, encoding="utf-8")
    print(f"Salvo em {SETTINGS.csv_facilities}")
    print("(lembrete: rode step9_consolida_aoi.py em seguida pra gerar o artefato final)")


if __name__ == "__main__":
    main()
