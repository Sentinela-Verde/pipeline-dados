"""Extrai dados socioeconômicos dos municípios brasileiros via BigQuery
(Base dos Dados) e salva um CSV único com PIB, população e lat/long.

Uso:
    python step0a_extract_dados_ibge.py

Precisa de:
- PROJECT_ID no `.env` da raiz do repo — projeto do Google Cloud usado só
  pra faturamento das queries (a Base dos Dados em si é pública/gratuita).
- Credenciais do Google Cloud configuradas localmente, ex.:
    gcloud auth application-default login
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

import basedosdados as bd
from dotenv import load_dotenv

QUERY_SOCIOECONOMICO = f"""
SELECT
  dir.nome AS nome_municipio,
  dir.sigla_uf,

  -- Mapeamento de Regiões
  CASE
    WHEN dir.sigla_uf IN ('PR', 'SC', 'RS') THEN 'Sul'
    WHEN dir.sigla_uf IN ('SP', 'RJ', 'MG', 'ES') THEN 'Sudeste'
    WHEN dir.sigla_uf IN ('MT', 'MS', 'GO', 'DF') THEN 'Centro-Oeste'
    WHEN dir.sigla_uf IN ('AC', 'AM', 'AP', 'PA', 'RO', 'RR', 'TO') THEN 'Norte'
    WHEN dir.sigla_uf IN ('AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE') THEN 'Nordeste'
  END AS regiao,

  p.id_municipio,
  p.ano,

  -- Demografia
  pop.populacao,

  -- Economia Geral
  p.pib,
  ROUND(SAFE_DIVIDE(p.pib, pop.populacao), 2) AS pib_per_capita,

  -- Vocações Econômicas (% do PIB)
  p.va_servicos,
  p.va_industria,
  p.va_agropecuaria,
  p.impostos_liquidos,
  ROUND(SAFE_DIVIDE(p.va_servicos, p.pib), 4) AS pct_va_servicos,
  ROUND(SAFE_DIVIDE(p.va_industria, p.pib), 4) AS pct_va_industria,
  ROUND(SAFE_DIVIDE(p.va_agropecuaria, p.pib), 4) AS pct_va_agropecuaria,
  ROUND(SAFE_DIVIDE(p.impostos_liquidos, p.pib), 4) AS pct_impostos

FROM `basedosdados.br_ibge_pib.municipio` p
LEFT JOIN `basedosdados.br_ibge_populacao.municipio` pop
  ON p.id_municipio = pop.id_municipio AND p.ano = pop.ano
LEFT JOIN `basedosdados.br_bd_diretorios_brasil.municipio` dir
  ON p.id_municipio = dir.id_municipio
-- Unindo com a tabela de mapas/geometria da Base dos Dados
LEFT JOIN `basedosdados.br_geobr_mapas.municipio` geo
  ON p.id_municipio = geo.id_municipio

WHERE p.ano >= {config.ANO_MINIMO}
ORDER BY regiao, dir.sigla_uf, dir.nome, p.ano
"""

QUERY_LAT_LONG = f"""
SELECT
  p.id_municipio,
  ROUND(ST_Y(sede.geometria), 6) AS latitude,
  ROUND(ST_X(sede.geometria), 6) AS longitude

FROM `basedosdados.br_ibge_pib.municipio` p

-- Tabela oficial de SEDE MUNICIPAL (Marco Zero da cidade) do geobr na Base dos Dados
LEFT JOIN `basedosdados.br_geobr_mapas.sede_municipal` sede
  ON p.id_municipio = sede.id_municipio

WHERE p.ano = {config.ANO_LAT_LONG}
ORDER BY p.id_municipio
"""


def carregar_project_id() -> str:
    load_dotenv(config.ENV_PATH)
    project_id = os.environ.get("PROJECT_ID")
    if not project_id:
        raise RuntimeError(
            f"PROJECT_ID não encontrado. Defina-o no arquivo {config.ENV_PATH} "
            "(veja .env.example na raiz do repo)."
        )
    return project_id


def main():
    project_id = carregar_project_id()

    print("Executando extração dos dados socioeconômicos do IBGE...")
    df_ibge = bd.read_sql(QUERY_SOCIOECONOMICO, billing_project_id=project_id)

    print("Executando extração de lat/long do IBGE...")
    df_lat_long = bd.read_sql(QUERY_LAT_LONG, billing_project_id=project_id)
    df_lat_long.drop_duplicates(subset=["id_municipio"], inplace=True)

    df_final = df_ibge.merge(df_lat_long, on="id_municipio", how="inner")
    df_final.to_csv(config.CSV_FINAL, index=False, encoding="utf-8-sig")
    print(f"Extração concluída e salva em '{config.CSV_FINAL}'.")


if __name__ == "__main__":
    main()
