"""Step 4 — Consolida os datacenters encontrados em cada região (step 3) numa
lista única de links, sem duplicar quem aparece perto da divisa de duas
regiões.

Não acessa a internet: só lê os JSONs de data/raw/regioes/*.json.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from comum.cache_store import STATUS_OK, carregar

CAMPOS = [
    "slug", "nome", "regiao", "operadora_link", "operadora_nome",
    "cidade", "endereco", "latitude", "longitude",
    "listingtype", "capacitytype", "url",
]


def montar_lista() -> list:
    vistos = {}
    regioes_sem_cache_ok = []

    for arquivo in sorted(config.RAW_DATA_REGIOES.glob("*.json")):
        slug_regiao = arquivo.stem
        registro = carregar(config.RAW_DATA_REGIOES, slug_regiao)
        if not registro or registro.get("status") != STATUS_OK:
            regioes_sem_cache_ok.append(slug_regiao)
            continue

        for dc in (registro["dados"] or {}).get("dcs") or []:
            slug = dc.get("link")
            if not slug or slug in vistos:
                continue
            vistos[slug] = {
                "slug": slug,
                "nome": dc.get("name"),
                "regiao": slug_regiao,
                "operadora_link": dc.get("companylink"),
                "operadora_nome": dc.get("companyname"),
                "cidade": dc.get("city"),
                "endereco": dc.get("address"),
                "latitude": dc.get("latitude"),
                "longitude": dc.get("longitude"),
                "listingtype": dc.get("listingtype"),
                "capacitytype": dc.get("capacitytype"),
                "url": f"{config.BASE_URL}{dc['url']}" if dc.get("url") else None,
            }

    if regioes_sem_cache_ok:
        print(f"Aviso: {len(regioes_sem_cache_ok)} região(ões) ainda sem cache ok, "
              f"rode o step 3 antes de considerar essa lista completa: {regioes_sem_cache_ok}")

    return sorted(vistos.values(), key=lambda d: d["slug"])


def main():
    linhas = montar_lista()
    if not linhas:
        print("Nenhum datacenter encontrado — rode o step 3 primeiro.")
        return

    with open(config.CSV_LINKS_DATACENTERS, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(linhas)

    print(f"{len(linhas)} datacenters únicos -> {config.CSV_LINKS_DATACENTERS}")


if __name__ == "__main__":
    main()
