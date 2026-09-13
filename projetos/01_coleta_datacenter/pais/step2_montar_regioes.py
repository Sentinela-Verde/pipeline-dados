"""Step 2 — Lê o cache do país (step 1) e gera a lista de regiões em CSV.

Não acessa a internet: só lê data/raw/pais/<pais>.json.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from comum.cache_store import STATUS_OK, carregar


def montar_regioes() -> list:
    registro = carregar(config.RAW_DATA_PAIS, config.PAIS)
    if not registro or registro.get("status") != STATUS_OK:
        raise RuntimeError(
            f"Sem cache ok para '{config.PAIS}' em data/raw/pais/ — rode o step 1 primeiro."
        )

    geos = (registro["dados"] or {}).get("geos") or []
    regioes = [
        {
            "regiao": g.get("link"),
            "nome": g.get("name"),
            "qtd_datacenters_informada": g.get("datacenters"),
            "latitude": g.get("latitude"),
            "longitude": g.get("longitude"),
            "url": f"{config.BASE_URL}/{config.PAIS}/{g.get('link')}/",
        }
        for g in geos
        if g.get("link")
    ]
    regioes.sort(key=lambda r: r["regiao"])
    return regioes


def main():
    regioes = montar_regioes()

    with open(config.CSV_REGIOES, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(regioes[0].keys()))
        writer.writeheader()
        writer.writerows(regioes)

    print(f"{len(regioes)} regiões de '{config.PAIS}' -> {config.CSV_REGIOES}")


if __name__ == "__main__":
    main()
