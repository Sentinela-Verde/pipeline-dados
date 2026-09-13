"""Configurações centrais do pipeline. Mude aqui, não dentro dos steps."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# raiz de data-extraction/ — onde fica a pasta data/ (compartilhada entre
# coletores), dois níveis acima de extract/scraping_datacentermap/
RAIZ_PROJETO = BASE_DIR.parent.parent

FONTE = "datacentermap"  # nome dessa coleta, usado nas pastas/arquivos compartilhados

# --- Entrada -----------------------------------------------------------
# Slug do país no datacentermap.com — dá a URL https://www.datacentermap.com/{PAIS}/
# de onde o step 1 tira a lista de regiões. Trocar aqui roda o pipeline pra
# outro país (ex.: "united-states", "germany"), sem mudar nenhum step.
PAIS = "brazil"

# --- Raw data (cache) -----------------------------------------------------
# Compartilhado entre coletores: data-extraction/data/raw/<fonte>/... Cada país /
# região / página de datacenter vira um .json pequeno aqui (só os dados que
# importam, não o HTML inteiro) — é o dado bruto extraído, e também serve de
# cache: rodar os steps de novo pula tudo que já está com status "ok".
RAW_DATA_DIR = RAIZ_PROJETO / "data" / "raw" / FONTE
RAW_DATA_PAIS = RAW_DATA_DIR / "pais"
RAW_DATA_REGIOES = RAW_DATA_DIR / "regioes"
RAW_DATA_DATACENTERS = RAW_DATA_DIR / "datacenters"

# --- Saídas ----------------------------------------------------------------
# CSVs intermediários (regiões, links) ficam só dentro desse coletor — não
# interessam a outras coletas, então não precisam ser compartilhados.
OUTPUT_DIR = BASE_DIR / "output"
CSV_REGIOES = OUTPUT_DIR / "regioes.csv"
CSV_LINKS_DATACENTERS = OUTPUT_DIR / "datacenters_links.csv"

# O CSV final é o "produto" dessa coleta e vai pra pasta compartilhada
# data/raw/outputs_extraction/, junto com o resultado de outras coletas (ex.: IBGE).
OUTPUTS_COMPARTILHADOS = RAIZ_PROJETO / "data" / "raw" / "outputs_extraction"
CSV_FINAL = OUTPUTS_COMPARTILHADOS / f"{FONTE}_datacenters.csv"

BASE_URL = "https://www.datacentermap.com"

# --- Comportamento do Selenium ---------------------------------------------
TAMANHO_BLOCO = 11           # reinicia o driver a cada N páginas (evita fingerprint/rate limit)
DELAY_MIN_REGIAO = 20
DELAY_MAX_REGIAO = 40
DELAY_MIN_DATACENTER = 15
DELAY_MAX_DATACENTER = 30
ESPERA_BLOQUEIO = 5 * 60      # 5 min quando toma rate limit ("Page View Limit Reached")
MAX_TENTATIVAS = 5           # depois disso marca como "bloqueado" e segue pro próximo

# --- Modo de teste (--teste no run_pipeline.py) -----------------------------
# Roda o pipeline inteiro (país -> região -> datacenter) gastando só um
# punhado de requisições, pra validar a sequência completa de extração sem
# esperar todas as regiões/datacenters reais.
TESTE_LIMITE_REGIOES = 1
TESTE_LIMITE_DATACENTERS = 3

for _dir in (RAW_DATA_PAIS, RAW_DATA_REGIOES, RAW_DATA_DATACENTERS, OUTPUT_DIR, OUTPUTS_COMPARTILHADOS):
    _dir.mkdir(parents=True, exist_ok=True)
