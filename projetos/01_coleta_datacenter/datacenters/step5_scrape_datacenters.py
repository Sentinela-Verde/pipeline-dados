"""Step 5 — Para cada datacenter (saída do step 4), abre a aba "overview" e a
aba "specs" no Selenium e guarda o dicionário `dc` (dados do datacenter) de
cada uma — é onde ficam certificações, potência, segurança etc. — mais o
`serviceplan` (planos de colocation/cloud), que só vem preenchido na aba
overview (na specs ele vem `null`).

Cada (slug, aba) vira um arquivo data/raw/datacenters/<slug>__<aba>.json.
Rodar de novo pula tudo que já está com status "ok" — só tenta de novo o que
faltou ou tomou rate limit ("Page View Limit Reached").
"""
import csv
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from comum.cache_store import STATUS_BLOQUEADO, STATUS_ERRO, STATUS_OK, carregar, precisa_buscar, salvar
from comum.next_data import esta_bloqueado, extrair_page_props

from selenium import webdriver


def carregar_datacenters() -> list:
    with open(config.CSV_LINKS_DATACENTERS, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def montar_tarefas(datacenters: list, forcar: bool, limite: int = None) -> list:
    """Cada datacenter gera até 2 tarefas: (chave_cache, url_da_pagina, aba).

    `limite`: para depois de reunir tarefas de N datacenters distintos (não
    N tarefas soltas) — assim, com limite=1, as duas abas (overview e specs)
    daquele único datacenter saem completas, em vez de parar no meio.
    """
    tarefas = []
    datacenters_com_tarefa = 0
    for dc in datacenters:
        slug, url = dc["slug"], dc["url"]
        urls_por_aba = {
            "overview": url,
            "specs": url.rstrip("/") + "/specs/",
        }
        tarefas_do_dc = [
            (f"{slug}__{aba}", pagina_url, aba)
            for aba, pagina_url in urls_por_aba.items()
            if precisa_buscar(config.RAW_DATA_DATACENTERS, f"{slug}__{aba}", forcar)
        ]
        if not tarefas_do_dc:
            continue
        if limite is not None and datacenters_com_tarefa >= limite:
            break
        tarefas.extend(tarefas_do_dc)
        datacenters_com_tarefa += 1
    return tarefas


def buscar_pagina(driver, url: str):
    """Retorna (status, dados). `dados` é None quando não deu certo."""
    for tentativa in range(1, config.MAX_TENTATIVAS + 1):
        print(f"      tentativa {tentativa}: {url}")
        driver.get(url)
        props = extrair_page_props(driver.page_source)

        if props is None:
            return STATUS_ERRO, None
        if esta_bloqueado(props):
            print(f"        Bloqueado (rate limit). Aguardando {config.ESPERA_BLOQUEIO}s...")
            time.sleep(config.ESPERA_BLOQUEIO)
            continue
        return STATUS_OK, {"dc": props.get("dc"), "tab": props.get("tab"), "serviceplan": props.get("serviceplan")}

    return STATUS_BLOQUEADO, None


def main(forcar: bool = False, limite: int = None):
    """`limite`: só busca N datacenters pendentes (útil pra testar o pipeline
    inteiro sem esperar todos os datacenters — ver README)."""
    datacenters = carregar_datacenters()
    tarefas = montar_tarefas(datacenters, forcar, limite)
    if limite is not None:
        print(f"--limite {limite}: buscando no máximo {limite} datacenter(s) agora.")

    total = len(tarefas)
    print(f"{len(datacenters)} datacenters, {total} páginas pendentes (overview + specs).")
    if not total:
        return

    for i in range(0, total, config.TAMANHO_BLOCO):
        bloco = tarefas[i: i + config.TAMANHO_BLOCO]
        driver = webdriver.Chrome()
        try:
            for n, (chave, url, aba) in enumerate(bloco, start=i + 1):
                print(f"  [{n}/{total}] {chave}")
                registro_anterior = carregar(config.RAW_DATA_DATACENTERS, chave)
                tentativas_antes = (registro_anterior or {}).get("tentativas", 0)

                status, dados = buscar_pagina(driver, url)
                salvar(config.RAW_DATA_DATACENTERS, chave, status, dados, tentativas_antes + 1)

                espera = random.uniform(config.DELAY_MIN_DATACENTER, config.DELAY_MAX_DATACENTER)
                print(f"    Aguardando {espera:.1f}s...")
                time.sleep(espera)
        finally:
            driver.quit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--forcar", action="store_true", help="ignora o cache e busca de novo")
    parser.add_argument("--limite", type=int, default=None, help="só busca N datacenters pendentes")
    args = parser.parse_args()
    main(forcar=args.forcar, limite=args.limite)
