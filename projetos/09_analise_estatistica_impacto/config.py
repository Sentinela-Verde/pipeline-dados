"""Configurações do modelo de impacto. Mude aqui, não dentro dos steps."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# raiz do repo (pipeline-dados/), dois níveis acima de projetos/09_analise_estatistica_impacto/
RAIZ_PROJETO = BASE_DIR.parent.parent

# --- Entrada -----------------------------------------------------------
# Painel consolidado (uma linha por área x horizonte) — ver guia_estrutura_dados_modelo_impacto.md.
# NOTA: ainda não existe um step neste repositório que gere esse CSV a partir de
# modelos/modelo_1_classificacao_imagem (cobertura do solo) + IBGE (socioeconômico)
# + LST + modelos/modelo_2_grupo_controle (pareamento) — hoje ele é um insumo externo. Ver
# "Lacuna conhecida" no README desta pasta.
# ATENÇÃO: já foi "data/silver" (nomenclatura em inglês, de um repo anterior) — corrigido pra
# bater com a árvore real deste repo (pasta "dados", em português, e o CSV vive em "gold",
# não em "silver", porque já é um produto de outros modelos, não dado bruto). Com o caminho
# antigo, `CONSOLIDADO_CSV.exists()` dava False e o step1 quebrava na leitura do CSV.
CONSOLIDADO_CSV = RAIZ_PROJETO / "dados" / "gold" / "consolidado_impacto_modelo.csv"

# --- Saída -----------------------------------------------------------------
# Mesma pasta onde os artefatos do step1 já estão versionados (dados/gold/efeito_liquido/).
OUTPUT_DIR = RAIZ_PROJETO / "dados" / "gold" / "efeito_liquido"
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

# --- Step 1b (análise de consequências / significância) --------------------
ALPHA = 0.05  # nível de significância, aplicado DEPOIS da correção por comparações múltiplas
MIN_PARES_TESTE = 5  # abaixo disso, reporta "amostra insuficiente" em vez de um p-valor
N_BOOTSTRAP = 10_000  # reamostragens pro IC95% (bootstrap percentil) da média do efeito líquido
N_PERMUTACOES_MONTE_CARLO = 20_000  # usado só quando n_pares > LIMITE_PERMUTACAO_EXATA
LIMITE_PERMUTACAO_EXATA = 20  # até esse nº de pares, enumera os 2^n sinais possíveis (teste exato)
# Preditores da mediação física de LST — mudanças de cobertura do solo que, fisicamente,
# reduzem evapotranspiração/sombra e por isso são candidatas a "explicar" o aquecimento.
VARS_MEDIACAO_LST = ["prop_vegetacao_densa", "prop_solo_exposto_obras", "prop_construida_urbana"]
CONSEQUENCIAS_RESUMO_CSV_NAME = "consequencias_terreno_resumo.csv"
CONSEQUENCIAS_MEDIACAO_CSV_NAME = "consequencias_terreno_mediacao_lst.csv"
CONSEQUENCIAS_RELATORIO_HTML_NAME = "relatorio_consequencias_terreno.html"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FIGURAS_DIR.mkdir(parents=True, exist_ok=True)
