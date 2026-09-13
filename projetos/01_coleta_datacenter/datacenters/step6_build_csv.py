"""Step 6 — Junta os caches de cada datacenter (overview + specs) num único
CSV final. Não acessa a internet, só lê os JSONs de data/raw/datacenters/.

`dc` do overview e `dc` do specs trazem blocos diferentes preenchidos (a API
retorna campos diferentes por aba) — por isso são mesclados campo a campo em
vez de um simplesmente sobrescrever o outro (ver deep_merge_preferindo).
`serviceplan` (colo/cloud) só vem preenchido na aba overview.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from comum.cache_store import STATUS_OK, carregar


def deep_merge_preferindo(base: dict, prioritario: dict) -> dict:
    """Mescla `prioritario` sobre `base`: valores não-nulos de `prioritario`
    ganham; dicts aninhados (ex.: meta_capacity, que tem mw_* vindo do
    overview e whitespace_* vindo do specs) são mesclados recursivamente em
    vez de um substituir o outro inteiro."""
    resultado = dict(base or {})
    for chave, valor in (prioritario or {}).items():
        anterior = resultado.get(chave)
        if isinstance(valor, dict) and isinstance(anterior, dict):
            resultado[chave] = deep_merge_preferindo(anterior, valor)
        elif valor is not None:
            resultado[chave] = valor
        elif chave not in resultado:
            resultado[chave] = valor
    return resultado


def carregar_dc(slug: str):
    """Retorna (dc_mesclado, serviceplan, status_overview, status_specs)."""
    overview = carregar(config.RAW_DATA_DATACENTERS, f"{slug}__overview")
    specs = carregar(config.RAW_DATA_DATACENTERS, f"{slug}__specs")

    status_overview = (overview or {}).get("status", "ausente")
    status_specs = (specs or {}).get("status", "ausente")

    dc_overview = ((overview or {}).get("dados") or {}).get("dc") if status_overview == STATUS_OK else None
    dc_specs = ((specs or {}).get("dados") or {}).get("dc") if status_specs == STATUS_OK else None
    dc = deep_merge_preferindo(dc_overview or {}, dc_specs or {})

    # serviceplan (colo/cloud) só vem preenchido na aba overview
    serviceplan = ((overview or {}).get("dados") or {}).get("serviceplan") if status_overview == STATUS_OK else None

    return dc, serviceplan or {}, status_overview, status_specs


def montar_linha(dc: dict, serviceplan: dict, status_overview: str, status_specs: str) -> dict:
    company = dc.get("companies") or {}
    standards = dc.get("meta_standards") or {}
    security = dc.get("meta_security") or {}
    building = dc.get("meta_building") or {}
    capacity = dc.get("meta_capacity") or {}
    power = dc.get("meta_power") or {}
    stats = dc.get("meta_stats") or {}
    references = dc.get("meta_references") or {}
    services = serviceplan.get("services") or {}
    colo = services.get("colo") or {}
    cloud = services.get("cloud") or {}

    link = None
    if dc.get("countrylink") and dc.get("marketlink") and dc.get("link"):
        link = f"{config.BASE_URL}/{dc['countrylink']}/{dc['marketlink']}/{dc['link']}/"

    return {
        "nome_datacenter": dc.get("name"),
        "operadora": company.get("name"),
        "endereco": dc.get("address"),
        "cep": dc.get("postal"),
        "cidade": dc.get("city"),
        "estado": dc.get("state"),
        "pais": dc.get("country"),
        "latitude": dc.get("latitude"),
        "longitude": dc.get("longitude"),
        "status": dc.get("status"),
        "stage": dc.get("stage"),
        "tipo_listagem": dc.get("listingtype"),
        "tipo_capacidade": dc.get("capacitytype"),
        "tags": ", ".join(dc.get("tags") or []),
        "link_datacenter": link,

        # capacidade
        "mw_construido": capacity.get("mw_builtout"),
        "mw_referenciado": capacity.get("mw_referenced"),
        "whitespace_construido_m": capacity.get("whitespace_builtout"),
        "whitespace_referenciado_m": capacity.get("whitespace_referenced"),

        # prédio
        "ano_operacional": building.get("year_operational"),
        "tipo_construcao": building.get("construction"),
        "tipo_ocupacao": building.get("tenancy_text"),
        "carga_piso_max_kg_m": building.get("floor_load"),

        # energia / refrigeração
        "redundancia_refrigeracao": power.get("cooling_redundancy"),

        # segurança
        "cctv": security.get("cctv"),
        "controle_acesso_cartao": security.get("keycard"),
        "biometria": security.get("biometric"),

        # certificações
        "tier_projetado": standards.get("tier_designed"),
        "tier_certificado": standards.get("tier_certified"),
        "pci_dss": standards.get("pci"),
        "iso9001": standards.get("iso9001"),
        "iso14001": standards.get("iso14001"),
        "iso22301": standards.get("iso22301"),
        "iso27001": standards.get("iso27001"),
        "iso45001": standards.get("iso45001"),
        "iso50001": standards.get("iso50001"),
        "soc1": standards.get("soc1"),
        "soc2": standards.get("soc2"),
        "soc3": standards.get("soc3"),

        # planos de colocation (serviceplan.services.colo — só na aba overview)
        "colo_suites": colo.get("suites"),
        "colo_cages": colo.get("cages"),
        "colo_cabinets": colo.get("cabinets"),
        "colo_partial_cabinets": colo.get("partialcabinets"),
        "colo_shared_rackspace": colo.get("sharedrackspace"),
        "colo_footprints": colo.get("footprints"),
        "colo_remote_hands": colo.get("remotehands"),
        "colo_build_to_suit": colo.get("buildtosuit"),

        # planos de cloud (serviceplan.services.cloud — só na aba overview)
        "cloud_gpu": cloud.get("gpu"),
        "cloud_managed": cloud.get("managed"),
        "cloud_baremetal": cloud.get("baremetal"),
        "cloud_public_cloud": cloud.get("publiccloud"),

        # contadores (meta_stats)
        "qtd_ixps": stats.get("ixps"),
        "qtd_clouds": stats.get("clouds"),
        "qtd_redes_presentes": stats.get("networkpresence"),
        "qtd_provedores_rede": stats.get("networkproviders"),
        "qtd_provedores_servico": stats.get("serviceproviders"),

        # referências externas (meta_references)
        "codigo_site": references.get("provider_id"),
        "peeringdb_id": references.get("peeringdb_id"),

        # diagnóstico: filtra no CSV o que ainda precisa ser re-raspado
        "cache_overview_status": status_overview,
        "cache_specs_status": status_specs,
    }


def main():
    with open(config.CSV_LINKS_DATACENTERS, encoding="utf-8") as f:
        links = list(csv.DictReader(f))

    if not links:
        print("Nenhum link de datacenter encontrado — rode os steps 1-4 primeiro.")
        return

    linhas = []
    incompletos = 0
    for item in links:
        dc, serviceplan, status_overview, status_specs = carregar_dc(item["slug"])
        if not dc:
            incompletos += 1
        linhas.append(montar_linha(dc, serviceplan, status_overview, status_specs))

    with open(config.CSV_FINAL, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(linhas[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(linhas)

    print(f"{len(linhas)} datacenters -> {config.CSV_FINAL} "
          f"({incompletos} ainda sem nenhum dado de overview/specs — rode o step 5 pra completar)")


if __name__ == "__main__":
    main()
