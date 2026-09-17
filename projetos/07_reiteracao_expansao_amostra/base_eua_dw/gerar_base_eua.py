"""Base final com EUA: classes por ano para campi americanos + ponto de controle pareado.

Instrumento: Dynamic World (global, 2016+), remapeado para as 5 classes do projeto pelo
`classes.yml`. Não é o Random Forest que gerou a base brasileira — está marcado em `instrumento`
em toda linha, e a comparação BR x EUA precisa levar isso em conta.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

REPO = Path(r"C:\Users\gabri\IdeaProjects\modelo-imagens-satelite")
PIPE = Path(r"C:\Users\gabri\IdeaProjects\pipeline-dados")
CTRL = REPO / "modelo-impacto" / "raw" / "controles-rf"
OUT = PIPE / "dados" / "gold"

N_TRAT = 16
ANOS_PRE, ANOS_POS = 3, 3          # obra-3 .. obra+3 = 7 anos
BUFFER_KM = 5                      # mesmo da base brasileira
ESCALA_M = 20
DIST_CONTROLE_KM = 15              # mesmo anel da metodologia brasileira
DIST_MIN_DE_OUTRO_DC_KM = 10
DW_COL = "GOOGLE/DYNAMICWORLD/V1"

# classes.yml -> remaps.dynamic_world
REMAP_DW = {0: 5, 1: 1, 2: 2, 3: 5, 4: 2, 5: 2, 6: 4, 7: 3, 8: 5}
SLUG = {1: "vegetacao_densa", 2: "vegetacao_rala", 3: "solo_exposto_obras",
        4: "construida_urbana", 5: "agua"}


def dist_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def ponto_por_azimute(lat: float, lon: float, az_graus: float, dist: float) -> tuple[float, float]:
    r = 6371.0
    ang, az = dist / r, math.radians(az_graus)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(ang) + math.cos(p1) * math.sin(ang) * math.cos(az))
    l2 = l1 + math.atan2(math.sin(az) * math.sin(ang) * math.cos(p1),
                         math.cos(ang) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), math.degrees(l2)


def ler_csv(p: Path) -> list[dict]:
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def escolher_tratamentos() -> list[dict]:
    """16 campi americanos datados, com janela obra±3 dentro da cobertura do DW (2016-2025).

    Duas fontes de data, nesta ordem: a do Dynamic World (validada contra fração construída
    dentro do footprint) e, quando falta, a do degrau de NDBI no Landsat. A fonte fica gravada
    em cada linha — a do Landsat tem erro mediano de -2 anos, e quem usar a base precisa saber.
    """
    campi = {c["campus_id"]: c for c in ler_csv(CTRL / "eua_campi.csv")}
    datas: dict[str, tuple[int, str]] = {}
    for d in ler_csv(CTRL / "landsat_datas_derivadas.csv"):
        if d.get("status") == "datado" and d.get("ano_obra_landsat"):
            datas[d["campus_id"]] = (int(float(d["ano_obra_landsat"])), "landsat_ndbi")
    for d in ler_csv(CTRL / "eua_datas_derivadas.csv"):
        if d.get("status") == "datado" and d.get("ano_obra_dw"):
            datas[d["campus_id"]] = (int(float(d["ano_obra_dw"])), "dynamic_world")

    cands = []
    for cid, (ano, fonte) in datas.items():
        if not (2019 <= ano <= 2022):          # obra-3 >= 2016 e obra+3 <= 2025
            continue
        base = campi.get(cid)
        if not base:
            continue
        cands.append({
            "campus_id": cid,
            "lat": float(base["lat"]), "lon": float(base["lon"]),
            "ano_obra": ano, "fonte_data": fonte,
            "nome": (base.get("nome") or "").strip(),
            "operadora": (base.get("operadora") or "").strip(),
            "n_predios": int(float(base.get("n_predios") or 1)),
        })
    # prioriza data validada pelo DW, campus maior, e determinismo no desempate
    cands.sort(key=lambda c: (c["fonte_data"] != "dynamic_world", -c["n_predios"], c["campus_id"]))
    escolhidos, usados = [], []
    for c in cands:
        if len(escolhidos) == N_TRAT:
            break
        if any(dist_km((c["lat"], c["lon"]), u) < 30 for u in usados):
            continue                            # não pegar dois campi do mesmo cluster urbano
        escolhidos.append(c)
        usados.append((c["lat"], c["lon"]))
    return escolhidos


def gerar_controle(trat: dict, todos_dc: list[tuple[float, float]]) -> dict:
    """Ponto de controle a 15 km, no primeiro azimute que não cai perto de outro data center."""
    for az in range(0, 360, 15):
        lat, lon = ponto_por_azimute(trat["lat"], trat["lon"], az, DIST_CONTROLE_KM)
        if all(dist_km((lat, lon), dc) >= DIST_MIN_DE_OUTRO_DC_KM for dc in todos_dc):
            return {"site_id": f"ctrl-{trat['campus_id']}", "lat": lat, "lon": lon,
                    "azimute": az, "dist_km": DIST_CONTROLE_KM}
    lat, lon = ponto_por_azimute(trat["lat"], trat["lon"], 0, DIST_CONTROLE_KM)
    return {"site_id": f"ctrl-{trat['campus_id']}", "lat": lat, "lon": lon,
            "azimute": 0, "dist_km": DIST_CONTROLE_KM, "aviso": "sem azimute livre"}


def extrair_dw(pontos: list[dict], anos: list[int]) -> dict[tuple[str, int], dict[int, int]]:
    """{(site_id, ano): {classe: n_pixels}} — moda anual do DW dentro do buffer."""
    sys.path.insert(0, str(REPO / "src"))
    from sentinela.gee.auth import init_ee
    import ee

    init_ee()
    feats = [ee.Feature(ee.Geometry.Point([p["lon"], p["lat"]]).buffer(BUFFER_KM * 1000),
                        {"sid": p["site_id"]}) for p in pontos]
    fc = ee.FeatureCollection(feats)
    out: dict[tuple[str, int], dict[int, int]] = {}
    for ano in anos:
        img = (ee.ImageCollection(DW_COL)
               .filterDate(f"{ano}-01-01", f"{ano+1}-01-01")
               .select("label")
               .mode())
        res = img.reduceRegions(collection=fc, reducer=ee.Reducer.frequencyHistogram(),
                                scale=ESCALA_M).getInfo()
        for f in res["features"]:
            hist = f["properties"].get("histogram") or {}
            contagem: dict[int, int] = {}
            for k, v in hist.items():
                alvo = REMAP_DW.get(int(float(k)))
                if alvo:
                    contagem[alvo] = contagem.get(alvo, 0) + int(round(float(v)))
            out[(f["properties"]["sid"], ano)] = contagem
        print(f"  {ano}: {len(res['features'])} pontos lidos", flush=True)
    return out


def main() -> int:
    trats = escolher_tratamentos()
    print(f"{len(trats)} campi americanos selecionados (obra 2019-2022)")
    todos_dc = [(float(c["lat"]), float(c["lon"])) for c in ler_csv(CTRL / "eua_campi.csv")]

    pontos, meta = [], {}
    for t in trats:
        c = gerar_controle(t, todos_dc)
        pontos += [{"site_id": t["campus_id"], "lat": t["lat"], "lon": t["lon"]},
                   {"site_id": c["site_id"], "lat": c["lat"], "lon": c["lon"]}]
        meta[t["campus_id"]] = ("tratamento", t, c)
        meta[c["site_id"]] = ("controle", t, c)

    anos = sorted({a for t in trats for a in range(t["ano_obra"] - ANOS_PRE, t["ano_obra"] + ANOS_POS + 1)})
    print(f"anos a extrair: {anos[0]}-{anos[-1]} ({len(anos)}) | {len(pontos)} pontos")
    hist = extrair_dw(pontos, anos)

    area_px_ha = (ESCALA_M ** 2) / 10_000
    linhas = []
    for sid, (tipo, t, c) in meta.items():
        for ano in range(t["ano_obra"] - ANOS_PRE, t["ano_obra"] + ANOS_POS + 1):
            cont = hist.get((sid, ano), {})
            total = sum(cont.values())
            if not total:
                continue
            rel = ano - t["ano_obra"]
            linha = {
                "site_id": sid, "pais": "EUA", "tipo": tipo,
                "pareado_com": t["campus_id"] if tipo == "controle" else "",
                "nome": t["nome"] if tipo == "tratamento" else "",
                "operadora": t["operadora"] if tipo == "tratamento" else "",
                "n_predios_no_campus": t["n_predios"] if tipo == "tratamento" else 0,
                "lat": round(t["lat"] if tipo == "tratamento" else c["lat"], 6),
                "lon": round(t["lon"] if tipo == "tratamento" else c["lon"], 6),
                "buffer_km": BUFFER_KM, "ano": ano,
                "ano_inicio_obra": t["ano_obra"], "fonte_data_obra": t["fonte_data"],
                "ano_relativo_ao_inicio_obra": rel,
                "fase": "pre" if rel < 0 else ("durante" if rel <= 1 else "pos"),
                "dist_tratamento_controle_km": DIST_CONTROLE_KM,
                "instrumento": "dynamic_world", "resolucao_m": ESCALA_M,
                "pixels_validos": total,
            }
            for cid, slug in SLUG.items():
                n = cont.get(cid, 0)
                linha[f"area_ha_{slug}"] = round(n * area_px_ha, 2)
                linha[f"prop_{slug}"] = round(n / total, 6)
            linhas.append(linha)

    linhas.sort(key=lambda r: (r["pareado_com"] or r["site_id"], r["tipo"], r["ano"]))
    OUT.mkdir(parents=True, exist_ok=True)
    destino = OUT / "base_eua_classes_por_ano.csv"
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    print(f"\n{destino}: {len(linhas)} linhas, {len({l['site_id'] for l in linhas})} pontos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
