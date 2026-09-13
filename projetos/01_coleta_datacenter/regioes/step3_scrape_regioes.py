"""Step 3 — Para cada região (saída do step 2), abre a página no Selenium e
guarda só os dados que interessam: a lista de datacenters daquela região
(pageProps.mapdata.dcs) e as estatísticas do mercado (pageProps.geodata).

Produtivo: cada região vira um arquivo em data/raw/regioes/<slug>.json. Rodar
o script de novo pula toda região que já está com status "ok" — só busca o
que ainda falta ou o que foi bloqueado da última vez.
"""
import csv
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from comum.cache_store import STATUS_BLOQUEADO, STATUS_ERRO, STATUS_OK, carregar, precisa_buscar, salvar
from comum.next_data import esta_bloqueado, extrair_features_com_coords, extrair_page_props

from selenium import webdriver


def carregar_regioes() -> list:
    with open(config.CSV_REGIOES, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def extrair_dados_regiao(page_props: dict) -> dict:
    mapdata = page_props.get("mapdata") or {}
    return {
        "geodata": page_props.get("geodata"),
        "dcs": extrair_features_com_coords(mapdata.get("dcs")),
    }


def buscar_regiao(driver, url: str):
    """Retorna (status, dados). `dados` é None quando não deu certo."""
    for tentativa in range(1, config.MAX_TENTATIVAS + 1):
        print(f"    tentativa {tentativa}: {url}")
        driver.get(url)
        props = extrair_page_props(driver.page_source)

        if props is None:
            print("      __NEXT_DATA__ não encontrado, tratando como erro.")
            return STATUS_ERRO, None

        if esta_bloqueado(props):
            print(f"      Bloqueado (rate limit). Aguardando {config.ESPERA_BLOQUEIO}s...")
            time.sleep(config.ESPERA_BLOQUEIO)
            continue

        return STATUS_OK, extrair_dados_regiao(props)

    print(f"      Desistindo de {url} após {config.MAX_TENTATIVAS} tentativas.")
    return STATUS_BLOQUEADO, None


def main(forcar: bool = False, limite: int = None):
    """`limite`: só busca as N primeiras regiões pendentes (útil pra testar o
    pipeline inteiro sem esperar as 37 regiões — ver README)."""
    regioes = carregar_regioes()
    pendentes = [r for r in regioes if precisa_buscar(config.RAW_DATA_REGIOES, r["regiao"], forcar)]

    print(f"{len(regioes)} regiões no total, {len(pendentes)} pendentes de busca.")
    if limite is not None:
        pendentes = pendentes[:limite]
        print(f"--limite {limite}: buscando só {len(pendentes)} região(ões) agora.")
    if not pendentes:
        return

    for i in range(0, len(pendentes), config.TAMANHO_BLOCO):
        bloco = pendentes[i: i + config.TAMANHO_BLOCO]
        driver = webdriver.Chrome()
        try:
            for regiao in bloco:
                print(f"  [{regiao['regiao']}]")
                registro_anterior = carregar(config.RAW_DATA_REGIOES, regiao["regiao"])
                tentativas_antes = (registro_anterior or {}).get("tentativas", 0)

                status, dados = buscar_regiao(driver, regiao["url"])
                salvar(config.RAW_DATA_REGIOES, regiao["regiao"], status, dados, tentativas_antes + 1)

                espera = random.uniform(config.DELAY_MIN_REGIAO, config.DELAY_MAX_REGIAO)
                print(f"    Aguardando {espera:.1f}s antes da próxima região...")
                time.sleep(espera)
        finally:
            driver.quit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--forcar", action="store_true", help="ignora o cache e busca de novo")
    parser.add_argument("--limite", type=int, default=None, help="só busca as N primeiras regiões pendentes")
    args = parser.parse_args()
    main(forcar=args.forcar, limite=args.limite)
