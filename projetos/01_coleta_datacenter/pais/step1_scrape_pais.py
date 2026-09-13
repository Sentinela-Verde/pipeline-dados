"""Step 1 — Abre a página do país no Selenium e extrai a lista de regiões.

Entrada: o slug do país em config.PAIS (ex.: "brazil"), com o qual é montada
a URL https://www.datacentermap.com/{pais}/. A lista de regiões (e a
contagem de datacenters de cada uma, segundo o site) já vem pronta dentro do
__NEXT_DATA__ dessa página, em pageProps.mapdata.geos — a mesma estrutura
usada pelas páginas de região (step 3), só que com "geos" no lugar de "dcs".

Só uma página, mas ainda assim cacheada em data/raw/pais/<pais>.json — se
"ok", rodar de novo não bate no site à toa. É a primeira etapa da árvore:

.
├── https://www.datacentermap.com/brazil/                     <- este step
│   ├── https://www.datacentermap.com/brazil/porto-alegre/    <- step 3/4
│   │   └── .../porto-alegre/elea-digital-poa1/                <- step 5/6
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from comum.cache_store import STATUS_BLOQUEADO, STATUS_ERRO, STATUS_OK, carregar, precisa_buscar, salvar
from comum.next_data import esta_bloqueado, extrair_features_com_coords, extrair_page_props

from selenium import webdriver


def url_pais() -> str:
    return f"{config.BASE_URL}/{config.PAIS}/"


def extrair_dados_pais(page_props: dict) -> dict:
    mapdata = page_props.get("mapdata") or {}
    return {
        "geodata": page_props.get("geodata"),
        "geos": extrair_features_com_coords(mapdata.get("geos")),
    }


def buscar_pais(driver, url: str):
    """Retorna (status, dados). `dados` é None quando não deu certo."""
    for tentativa in range(1, config.MAX_TENTATIVAS + 1):
        print(f"  tentativa {tentativa}: {url}")
        driver.get(url)
        props = extrair_page_props(driver.page_source)

        if props is None:
            print("    __NEXT_DATA__ não encontrado, tratando como erro.")
            return STATUS_ERRO, None

        if esta_bloqueado(props):
            print(f"    Bloqueado (rate limit). Aguardando {config.ESPERA_BLOQUEIO}s...")
            time.sleep(config.ESPERA_BLOQUEIO)
            continue

        return STATUS_OK, extrair_dados_pais(props)

    print(f"    Desistindo de {url} após {config.MAX_TENTATIVAS} tentativas.")
    return STATUS_BLOQUEADO, None


def main(forcar: bool = False):
    if not precisa_buscar(config.RAW_DATA_PAIS, config.PAIS, forcar):
        print(f"'{config.PAIS}' já está em cache (ok) — nada a fazer (use --forcar pra buscar de novo).")
        return

    registro_anterior = carregar(config.RAW_DATA_PAIS, config.PAIS)
    tentativas_antes = (registro_anterior or {}).get("tentativas", 0)

    print(f"Buscando regiões de '{config.PAIS}'...")
    driver = webdriver.Chrome()
    try:
        status, dados = buscar_pais(driver, url_pais())
    finally:
        driver.quit()

    salvar(config.RAW_DATA_PAIS, config.PAIS, status, dados, tentativas_antes + 1)
    print(f"Status: {status} -> data/raw/pais/{config.PAIS}.json")


if __name__ == "__main__":
    main()
