"""Etapa 5 — extração de LST (temperatura de superfície) por site e ano, via Earth Engine.

Rode com:

    python lst.py                    # todos os sites, todos os anos da janela
    python lst.py --site ascenty-vinhedo
    python lst.py --ano-inicio 2020 --ano-fim 2025

**O que sai daqui.** Três arquivos em `dados/bronze/temperatura/`:

  - `temperatura_lst.csv`   — 1 linha por site x ano: `lst_media_celsius` e `n_observacoes`. É o
                              arquivo que a consolidação (etapa 8) junta ao painel.
  - `lst_cenas_brutas.csv`  — 1 linha por cena de 8 dias: a granularidade fina, para auditar uma
                              média suspeita sem reextrair.
  - `log_extracao.json`     — avisos (cobertura baixa, site/ano sem dado, valor fora da faixa de
                              sanidade), contagens e a faixa de valores encontrada.

**Fonte: MODIS, não Landsat.** `MODIS/061/MOD11A2` — Terra, LST diurna, composto de 8 dias, 1 km.
A escolha está justificada em `METODOLOGIA.md`, e o resumo é: o MOD11A2 cobre a janela inteira com
o mesmo sensor, mesma resolução e mesmo produto, enquanto o termal do Landsat exigiria harmonizar
Landsat 8/9 (100 m reamostrado para 30 m) e deixaria 2016-2018 descoberto pelo lado do Sentinel-2,
que não tem banda termal. Para série anual por site num buffer de 5 km (~78 km²), 1 km de pixel é
suficiente — o preço, registrado como limitação, é não enxergar contraste dentro do site.

**Agregação anual.** Para cada site/ano, cada cena do composto de 8 dias vira uma média regional
(média dos pixels válidos dentro do buffer, na escala nativa de 1 km). A média anual é a média
simples dessas médias de cena — um ano tem ~46 cenas de 8 dias, o que já dá ponderação quase
uniforme ao longo do ano, sem precisar de um passo intermediário por mês. `n_observacoes` conta as
cenas com pelo menos 1 pixel válido no buffer: é por ele que se desconfia de uma média construída
sobre poucas cenas.

**Esta etapa não depende das outras.** O recorte é o buffer do site, não a grade da etapa 2 — LST
é uma frente paralela no diagrama, e roda com o `sites.geojson` e mais nada.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from auth import init_ee
from config import SETTINGS, SITES_PATH, ConfigError

import ee


def carregar_sites(path: Path, buffer_km_padrao: float) -> list[dict]:
    """Sites do `parametros/sites.geojson`, com lat/lon e raio do buffer.

    Lê com o `json` da biblioteca padrão de propósito: o arquivo é um GeoJSON de pontos e esta
    etapa não faz nenhuma operação geométrica local — quem recorta é o Earth Engine. Arrastar
    geopandas para cá seria uma dependência pesada por nada.
    """
    if not path.exists():
        raise ConfigError(f"'{path}' não existe — esta etapa precisa do sites.geojson.")
    data = json.loads(path.read_text(encoding="utf-8"))
    sites = []
    for feat in data["features"]:
        props = feat["properties"]
        lon_geom, lat_geom = feat["geometry"]["coordinates"]
        sites.append(
            {
                "site_id": props["site_id"],
                "municipio": props.get("municipio"),
                "uf": props.get("uf"),
                "lat": props.get("lat", lat_geom),
                "lon": props.get("lon", lon_geom),
                "buffer_km": props.get("buffer_km", buffer_km_padrao),
            }
        )
    return sites


def extrair_valores_ano(buffer_geom: ee.Geometry, ano: int, fonte: dict) -> list[float]:
    """Médias regionais de LST em Celsius, uma por cena MOD11A2 com pelo menos 1 pixel válido
    dentro do buffer, no ano informado.

    Cenas 100% nubladas dentro do buffer não produzem valor: o `aggregate_array` do Earth Engine
    já as omite, e o filtro de `None` do lado do cliente é redundante de propósito.
    """
    ic = (
        ee.ImageCollection(fonte["colecao_gee"])
        .select(fonte["banda"])
        .filterDate(f"{ano}-01-01", f"{ano + 1}-01-01")
        .filterBounds(buffer_geom)
    )

    def com_media_regional(img):
        celsius = img.multiply(fonte["fator_escala"]).subtract(fonte["offset_kelvin"])
        estat = celsius.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=buffer_geom,
            scale=fonte["resolucao_nativa_m"],
            maxPixels=1_000_000_000,
            bestEffort=True,
        )
        return img.set("lst_c", estat.get(fonte["banda"]))

    valores = ic.map(com_media_regional).aggregate_array("lst_c").getInfo()
    return [v for v in valores if v is not None]


def main(argv: list[str] | None = None) -> int:
    params = SETTINGS.params()
    fonte = params["fonte"]
    janela = params["janela"]
    qualidade = params["qualidade"]
    faixa_sanidade = tuple(qualidade["faixa_sanidade_celsius"])
    minimo_cenas = int(qualidade["minimo_cenas_por_ano"])

    parser = argparse.ArgumentParser(description="Etapa 5 — extração de LST por site e ano.")
    parser.add_argument("--site", default=None, help="restringe a um site_id (default: todos).")
    parser.add_argument("--ano-inicio", type=int, default=int(janela["ano_inicio"]))
    parser.add_argument("--ano-fim", type=int, default=int(janela["ano_fim"]))
    args = parser.parse_args(argv)

    print("Inicializando Google Earth Engine...")
    init_ee()

    sites = carregar_sites(SITES_PATH, float(params["buffer_km_padrao"]))
    if args.site:
        sites = [s for s in sites if s["site_id"] == args.site]
        if not sites:
            raise ConfigError(f"site_id '{args.site}' não está em {SITES_PATH}.")
    print(f"{len(sites)} site(s) carregado(s) de {SITES_PATH}")

    saida_dir = SETTINGS.lst_dir
    saida_dir.mkdir(parents=True, exist_ok=True)
    csv_serie = saida_dir / "temperatura_lst.csv"
    csv_cenas = saida_dir / "lst_cenas_brutas.csv"
    log_path = saida_dir / "log_extracao.json"

    data_extracao = datetime.now(UTC).strftime("%Y-%m-%d")
    linhas_serie: list[dict] = []
    linhas_cenas: list[dict] = []
    avisos: list[str] = []
    todos_valores: list[float] = []

    for i, site in enumerate(sites, start=1):
        site_id = site["site_id"]
        buffer_km = site["buffer_km"]
        buffer_geom = ee.Geometry.Point([site["lon"], site["lat"]]).buffer(buffer_km * 1000)
        print(
            f"\n=== [{i}/{len(sites)}] {site_id} ({site['municipio']}/{site['uf']}) "
            f"— buffer {buffer_km} km ==="
        )

        for ano in range(args.ano_inicio, args.ano_fim + 1):
            try:
                valores = extrair_valores_ano(buffer_geom, ano, fonte)
            except Exception as e:  # noqa: BLE001 — relatar e seguir para o próximo ano/site
                print(f"  {ano}: ERRO — {e}")
                avisos.append(f"{site_id}/{ano}: ERRO na extração — {e}")
                continue

            n_obs = len(valores)
            media = round(sum(valores) / n_obs, 2) if n_obs > 0 else None

            if n_obs == 0:
                print(f"  {ano}: 0 observações válidas")
                avisos.append(
                    f"{site_id}/{ano}: 0 cenas válidas (sem dado ou 100% nublado no buffer)"
                )
            else:
                baixa = " [COBERTURA BAIXA]" if n_obs < minimo_cenas else ""
                print(f"  {ano}: {media:.2f} C (n={n_obs} cenas){baixa}")
                if n_obs < minimo_cenas:
                    avisos.append(
                        f"{site_id}/{ano}: cobertura baixa, n_observacoes={n_obs} "
                        f"(esperado ~40-46 cenas/ano para {fonte['colecao_gee']})"
                    )
                if not (faixa_sanidade[0] <= media <= faixa_sanidade[1]):
                    avisos.append(
                        f"{site_id}/{ano}: media {media} C fora da faixa de sanidade "
                        f"{faixa_sanidade} — checar escala/unidade"
                    )
                todos_valores.extend(valores)

            linhas_serie.append(
                {
                    "site_id": site_id,
                    "municipio": site["municipio"],
                    "uf": site["uf"],
                    "ano": ano,
                    "lst_media_celsius": "" if media is None else media,
                    "n_observacoes": n_obs,
                    "fonte": fonte["rotulo_fonte"],
                    "colecao_gee": fonte["colecao_gee"],
                    "data_extracao": data_extracao,
                }
            )
            linhas_cenas.extend(
                {"site_id": site_id, "ano": ano, "lst_celsius": round(v, 3)} for v in valores
            )

    campos_serie = [
        "site_id",
        "municipio",
        "uf",
        "ano",
        "lst_media_celsius",
        "n_observacoes",
        "fonte",
        "colecao_gee",
        "data_extracao",
    ]
    with csv_serie.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos_serie)
        writer.writeheader()
        writer.writerows(linhas_serie)
    print(f"\nSalvo: {csv_serie} ({len(linhas_serie)} linhas)")

    with csv_cenas.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["site_id", "ano", "lst_celsius"])
        writer.writeheader()
        writer.writerows(linhas_cenas)
    print(f"Salvo: {csv_cenas} ({len(linhas_cenas)} linhas — 1 por cena de 8 dias)")

    log = {
        "data_extracao": data_extracao,
        "colecao_gee": fonte["colecao_gee"],
        "banda": fonte["banda"],
        "n_sites": len(sites),
        "anos": [args.ano_inicio, args.ano_fim],
        "n_site_ano_esperado": len(sites) * (args.ano_fim - args.ano_inicio + 1),
        "n_site_ano_com_dado": sum(1 for r in linhas_serie if r["lst_media_celsius"] != ""),
        "n_site_ano_sem_dado": sum(1 for r in linhas_serie if r["lst_media_celsius"] == ""),
        "faixa_valores_encontrada_celsius": (
            [round(min(todos_valores), 2), round(max(todos_valores), 2)] if todos_valores else None
        ),
        "faixa_sanidade_celsius": list(faixa_sanidade),
        "avisos": avisos,
    }
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Salvo: {log_path}")

    print(f"\n{len(avisos)} aviso(s) registrado(s) (cobertura baixa / sem dado / fora da faixa).")
    if todos_valores:
        print(
            f"Faixa de valores de cena encontrada: "
            f"{min(todos_valores):.2f} C a {max(todos_valores):.2f} C"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
