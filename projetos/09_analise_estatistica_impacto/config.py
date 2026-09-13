"""Configurações do modelo de impacto. Mude aqui, não dentro dos steps."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# raiz de data-extraction/, dois níveis acima de modeling/modelo_impacto/
RAIZ_PROJETO = BASE_DIR.parent.parent

# --- Entrada -----------------------------------------------------------
# Painel consolidado (uma linha por área x horizonte) — ver guia_estrutura_dados_modelo_impacto.md.
# NOTA: ainda não existe um step neste repositório que gere esse CSV a partir de
# modeling/modelo_classifica_imagem (cobertura do solo) + extract/bigquery_ibge (socioeconômico)
# + LST + modeling/modelo_grupo_controle (pareamento) — hoje ele é um insumo externo. Ver
# "Lacuna conhecida" no README desta pasta.
CONSOLIDADO_CSV = RAIZ_PROJETO / "data" / "silver" / "consolidado_impacto_modelo.csv"

# --- Saída -----------------------------------------------------------------
OUTPUT_DIR = RAIZ_PROJETO / "data" / "gold" / "modelo_impacto"
FIGURAS_DIR = OUTPUT_DIR / "figuras"
# Relatório único (HTML autocontido, com tabelas e gráficos embutidos) do step1.
RELATORIO_EXPLORATORIA_HTML = OUTPUT_DIR / "relatorio_analise_exploratoria.html"

# --- Variáveis-alvo ----------------------------------------------------
VARS_SATELITE = [
    "prop_vegetacao_densa", "prop_vegetacao_rala",
    "prop_solo_exposto_obras", "prop_construida_urbana", "prop_agua",
]
VARS_CLIMA = ["lst_media_celsius"]
VARS_SOCIO = ["populacao", "emprego_formal_total", "pib_mil_reais", "numero_empresas"]
VARS_ALVO = VARS_SATELITE + VARS_CLIMA + VARS_SOCIO

# --- Estágio 2 (aprender o efeito) ------------------------------------------
HORIZONTES_ALVO = [0, 1, 2]  # abertura, +1 ano, +2 anos (ver proposta_projeto.md)
VARS_MODELO = ["prop_vegetacao_densa", "prop_construida_urbana", "lst_media_celsius"]

COLS_PORTE = [
    "mw_construido_total", "tier", "tier_projetado_max",
    "n_predios_no_campus", "whitespace_construido_sqm_total", "n_predios_datacentermap",
]
COLS_CONTEXTO_NUM = ["dist_tratamento_controle_km"]
COLS_CONTEXTO_CAT = ["bioma", "regiao"]

# Modelo intencionalmente raso — amostra pequena (ver "Limitações" no README).
RF_MAX_DEPTH = 3
RF_MIN_SAMPLES_LEAF = 2
RF_N_ESTIMATORS = 200
RANDOM_STATE = 42

# Só para o gráfico de curva de efeito líquido: intervalo de horizontes comum a todos
# os pares hoje disponíveis (evita que 1 par com dado isolado num horizonte distorça a curva).
HORIZONTE_GRAFICO_MIN, HORIZONTE_GRAFICO_MAX = -3, 3

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FIGURAS_DIR.mkdir(parents=True, exist_ok=True)
