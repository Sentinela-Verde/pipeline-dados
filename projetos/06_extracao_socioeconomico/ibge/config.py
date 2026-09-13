"""Configurações centrais da extração. Mude aqui, não dentro do step."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# raiz do repo — onde ficam a pasta data/ (compartilhada entre coletores) e o
# .env, dois níveis acima de extract/bigquery_ibge/
RAIZ_PROJETO = BASE_DIR.parent.parent

FONTE = "ibge"  # nome dessa coleta, usado no nome do CSV final

# --- Autenticação BigQuery / Base dos Dados --------------------------------
# PROJECT_ID = projeto do Google Cloud usado só pra faturamento das queries
# (a Base dos Dados em si é pública/gratuita até uma cota generosa; o
# projeto funciona como "conta" pro BigQuery cobrar, se passar da cota).
# Vem do .env na raiz do repo — nunca comitar esse arquivo.
ENV_PATH = RAIZ_PROJETO / ".env"

# --- Saída ------------------------------------------------------------------
# O CSV final é o "produto" dessa coleta e vai pra pasta compartilhada
# data/raw/outputs_extraction/, junto com o resultado de outras coletas (ex.: datacentermap).
OUTPUTS_COMPARTILHADOS = RAIZ_PROJETO / "data" / "raw" / "outputs_extraction"
CSV_FINAL = OUTPUTS_COMPARTILHADOS / f"{FONTE}_municipios.csv"

# --- Recorte dos dados --------------------------------------------------
ANO_MINIMO = 2016   # primeiro ano incluído na série de PIB/população
ANO_LAT_LONG = 2020  # ano usado só pra pegar a geometria da sede municipal (não muda entre anos)

OUTPUTS_COMPARTILHADOS.mkdir(parents=True, exist_ok=True)
