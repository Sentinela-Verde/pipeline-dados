"""Configurações centrais da extração. Mude aqui, não dentro do step."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# raiz do repo (pipeline-dados) — três níveis acima de projetos/06_extracao_socioeconomico/ibge/.
# CORRIGIDO em 2026-09-14: era `.parent.parent` (2 níveis), que resolvia para
# `projetos/` em vez da raiz do repo — bug herdado de quando este código vivia em
# `data-extraction/extract/bigquery_ibge/` (só 2 níveis abaixo da raiz de lá). Nunca se
# manifestou em disco (a pasta `projetos/data/` que isso geraria nunca chegou a existir aqui)
# porque `dados/bronze/ibge/ibge_municipios.csv` foi colocado diretamente na migração, sem rodar
# este script neste repo — mas o bug ficava latente pra próxima execução real.
RAIZ_PROJETO = BASE_DIR.parent.parent.parent

FONTE = "ibge"  # nome dessa coleta, usado no nome do CSV final

# --- Autenticação BigQuery / Base dos Dados --------------------------------
# PROJECT_ID = projeto do Google Cloud usado só pra faturamento das queries
# (a Base dos Dados em si é pública/gratuita até uma cota generosa; o
# projeto funciona como "conta" pro BigQuery cobrar, se passar da cota).
# Vem do .env na raiz do repo — nunca comitar esse arquivo.
ENV_PATH = RAIZ_PROJETO / ".env"

# --- Saída ------------------------------------------------------------------
# O CSV final é o "produto" dessa coleta. CORRIGIDO em 2026-09-14: era
# `data/raw/outputs_extraction/` (convenção do data-extraction antigo) — pipeline-dados usa
# `dados/` (português) com camadas bronze/silver/gold; o arquivo real já vive em
# `dados/bronze/ibge/`, então o código agora aponta pra onde o dado de fato está.
BRONZE_DIR = RAIZ_PROJETO / "dados" / "bronze" / "ibge"
CSV_FINAL = BRONZE_DIR / f"{FONTE}_municipios.csv"

# --- Recorte dos dados --------------------------------------------------
ANO_MINIMO = 2016   # primeiro ano incluído na série de PIB/população
ANO_LAT_LONG = 2020  # ano usado só pra pegar a geometria da sede municipal (não muda entre anos)

BRONZE_DIR.mkdir(parents=True, exist_ok=True)
