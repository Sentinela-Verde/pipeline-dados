"""Configurações do pareamento de grupo controle. Mude aqui, não dentro dos steps."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# raiz do repo (pipeline-dados) — três níveis acima de
# modelos/modelo_2_grupo_controle/selecao_candidatos/.
# CORRIGIDO em 2026-09-14: era `.parent.parent` (só 2 níveis, resolvia para `modelos/`) e usava
# `data/` (convenção do data-extraction antigo) em vez de `dados/` — mesma classe de bug
# encontrada e corrigida em `projetos/06_extracao_socioeconomico/ibge/config.py` no mesmo dia.
RAIZ_PROJETO = BASE_DIR.parent.parent.parent

# --- Entradas ------------------------------------------------------------
IBGE_CSV = RAIZ_PROJETO / "dados" / "bronze" / "ibge" / "ibge_municipios.csv"
# datacenter_filtrado.csv agora é por AOI (21 linhas, chave `aoi_id`), não mais por facility
# (`nome_datacenter`) — ver projetos/01_coleta_datacenter/filtro_elegibilidade/ (step9, 2026-09-14).
DATACENTER_FILTRADO_CSV = RAIZ_PROJETO / "dados" / "silver" / "datacenter_filtrado.csv"

# Municípios cujo nome vem grafado sem acento (ou diferente) na fonte do data center e precisa
# ser normalizado antes de casar com o nome oficial do IBGE. Vazio hoje: as 16 cidades únicas dos
# 21 AOIs (pós `correcao_endereco/`, que já geocodifica com acentuação correta) batem 1:1 com
# `nome_municipio` do IBGE — conferido em 2026-09-14. Mantido como mecanismo de correção pronto
# pra quando a lista de AOIs mudar de novo e algum nome não bater.
MAPA_NOMES_CIDADE: dict[str, str] = {}

# --- step1: cidades similares ---------------------------------------------
# Média das features abaixo nesse intervalo de anos (perfil socioeconômico
# "estável" da cidade, anterior à corrida de data centers 2022+).
ANOS_ANALISE = [2016, 2017, 2018, 2019, 2020, 2021]
FEATURES_CIDADE = [
    "populacao",
    "pib_per_capita",
    "pct_va_servicos",
    "pct_va_industria",
    "pct_va_agropecuaria",
    "pct_impostos",
]
N_SIMILARES = 3          # quantos municípios similares salvar por município (pedido 2026-09-14)
MODO_REGIAO = "mesma"    # "mesma" = KNN só dentro da mesma região; outro valor = Brasil inteiro

GRUPO_CONTROLE_DIR = RAIZ_PROJETO / "dados" / "silver" / "grupo_controle"
MUNICIPIOS_SIMILARES_CSV = GRUPO_CONTROLE_DIR / "municipios_com_cidades_similares.csv"

# --- step2: grupo de controle (6 pontos ao redor de CADA um dos 2 municípios mais similares) ----
# Antes (versão original, 1 cidade só): N_SIMILARES_PARA_CONTROLE não existia — só
# `id_municipio_similar_1` era usado, gerando 6 pontos/AOI. Pedido 2026-09-14: usar as 2 cidades
# mais similares (rank 1 e 2), 6 pontos ao redor de cada uma = 12 candidatos por AOI.
N_SIMILARES_PARA_CONTROLE = 2   # ranks de cidade similar usados (1..N) — precisa ser <= N_SIMILARES
N_PONTOS_CONTROLE = 6           # pontos gerados em círculo ao redor de CADA município similar usado
INCLINACAO_INICIAL_GRAUS = 0.0  # ponto 1 no Norte (0°)

# Saída antiga (1 cidade x 6 pontos, facility-level) — mantida só de referência/histórico, não é
# mais gerada por padrão. A saída vigente é CANDIDATOS_GRUPO_CONTROLE_CSV (2 cidades x 6 pontos).
PONTOS_EXPANDIDOS_CSV = GRUPO_CONTROLE_DIR / "datacenter_expandido_6_pontos.csv"
CANDIDATOS_GRUPO_CONTROLE_CSV = GRUPO_CONTROLE_DIR / "candidatos_grupo_controle_12pontos.csv"

# --- mapa de conferência (gerar_mapa_pontos_datacenter.py) ------------------
MAPA_HTML = GRUPO_CONTROLE_DIR / "mapa_datacenters.html"
LADO_QUADRADO_KM = 3      # área de amostragem desenhada ao redor de cada ponto
KM_POR_GRAU_LAT = 111.32

GRUPO_CONTROLE_DIR.mkdir(parents=True, exist_ok=True)
