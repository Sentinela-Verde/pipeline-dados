"""Enriquece a base 32 — contexto geográfico, LST e qualidade do pareamento do lado americano.

Cada coluna vazia tem um análogo americano, e cada análogo tem um custo de fidelidade diferente.
O que dá para preencher com honestidade está aqui; o que não dá fica vazio e documentado.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO = Path(r"C:\Users\gabri\IdeaProjects\modelo-imagens-satelite")
PIPE = Path(r"C:\Users\gabri\IdeaProjects\pipeline-dados")
BASE = PIPE / "dados" / "gold" / "base_final_32_dc_br_eua.csv"

BUFFER_KM = 5
CLASSES = ("vegetacao_densa", "vegetacao_rala", "solo_exposto_obras", "construida_urbana", "agua")

# Divisões censitárias dos EUA — análogo da região do IBGE.
REGIAO = {
    "Northeast": {"CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"},
    "Midwest": {"IL", "IN", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD"},
    "South": {"DE", "FL", "GA", "MD", "NC", "SC", "VA", "DC", "WV", "AL", "KY", "MS", "TN",
              "AR", "LA", "OK", "TX"},
    "West": {"AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY", "AK", "CA", "HI", "OR", "WA"},
}
UF_POR_ESTADO = {}  # preenchido do retorno do geocoder (nome -> sigla) via tabela abaixo
SIGLA = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


def ler(p: Path) -> list[dict]:
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- geografia (Census Geocoder)
def geocodificar(lat: float, lon: float) -> dict:
    """lat/lon -> condado, estado e FIPS. Sem chave: o Geocoder do Census é aberto."""
    url = ("https://geocoding.geo.census.gov/geocoder/geographies/coordinates?"
           + urllib.parse.urlencode({
               "x": lon, "y": lat, "benchmark": "Public_AR_Current",
               "vintage": "Current_Current", "layers": "Counties", "format": "json"}))
    with urllib.request.urlopen(url, timeout=30) as r:
        d = json.load(r)
    cond = (d.get("result", {}).get("geographies", {}).get("Counties") or [{}])[0]
    if not cond:
        return {}
    estado = cond.get("BASENAME_1") or cond.get("STATE_NAME") or ""
    return {
        "municipio": cond.get("BASENAME", ""),
        "estado_nome": estado,
        "fips": f"{cond.get('STATE','')}{cond.get('COUNTY','')}",
    }


def populacao_acs(fips: str) -> str:
    """População do condado (ACS 5-year, B01003_001E). Sem chave — volume baixo é permitido."""
    if len(fips) != 5:
        return ""
    url = ("https://api.census.gov/data/2022/acs/acs5?"
           + urllib.parse.urlencode({
               "get": "B01003_001E", "for": f"county:{fips[2:]}", "in": f"state:{fips[:2]}"}))
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.load(r)
        return d[1][0]
    except Exception as e:  # noqa: BLE001
        print(f"    ACS falhou para {fips}: {e}")
        return ""


# ------------------------------------------------------------------------------ Earth Engine
def contexto_ee(pontos: list[dict], anos_por_ponto: dict[str, list[int]]) -> dict:
    """LST anual (MODIS) e bioma (RESOLVE Ecoregions) por ponto."""
    sys.path.insert(0, str(REPO / "src"))
    from sentinela.gee.auth import init_ee
    import ee

    init_ee()
    feats = [ee.Feature(ee.Geometry.Point([p["lon"], p["lat"]]).buffer(BUFFER_KM * 1000),
                        {"sid": p["site_id"]}) for p in pontos]
    fc = ee.FeatureCollection(feats)

    print("  bioma (RESOLVE Ecoregions 2017)...")
    eco = ee.Image().byte().paint(ee.FeatureCollection("RESOLVE/ECOREGIONS/2017"), "BIOME_NUM")
    res = eco.reduceRegions(collection=fc, reducer=ee.Reducer.mode(), scale=500).getInfo()
    bioma_num = {f["properties"]["sid"]: f["properties"].get("mode") for f in res["features"]}

    print("  LST (MODIS MOD11A2)...")
    anos = sorted({a for v in anos_por_ponto.values() for a in v})
    lst: dict[tuple[str, int], float] = {}
    for ano in anos:
        img = (ee.ImageCollection("MODIS/061/MOD11A2")
               .select("LST_Day_1km")
               .filterDate(f"{ano}-01-01", f"{ano+1}-01-01")
               .mean()
               .multiply(0.02).subtract(273.15))
        res = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=1000).getInfo()
        for f in res["features"]:
            v = f["properties"].get("mean")
            if v is not None:
                lst[(f["properties"]["sid"], ano)] = round(float(v), 4)
        print(f"    {ano}: ok", flush=True)
    return {"bioma_num": bioma_num, "lst": lst}


# RESOLVE BIOME_NUM -> nome (só os que ocorrem nos EUA continentais)
BIOMA_NOME = {
    1: "Floresta tropical úmida", 2: "Floresta tropical seca", 4: "Floresta temperada decídua",
    5: "Floresta temperada de coníferas", 6: "Taiga", 7: "Savana tropical",
    8: "Campos temperados", 9: "Campos alagáveis", 10: "Campos montanos",
    11: "Tundra", 12: "Mata mediterrânea", 13: "Deserto e arbustal xérico", 14: "Manguezal",
}


def qualidade_l1(l1: float) -> str:
    """Mesmos limiares de SV-29 usados no lado brasileiro, não afrouxados."""
    return "bom" if l1 <= 0.10 else ("aceitavel" if l1 <= 0.20 else "ruim")


def main() -> int:
    linhas = ler(BASE)
    eua = [r for r in linhas if r["pais"] == "EUA"]

    # --- 1. L1 e qualidade do par, a partir das proporções do período pré -------------------
    pre = defaultdict(list)
    for r in eua:
        if int(r["ano_relativo_ao_inicio_obra"]) < 0:
            chave = r["pareado_com"] or r["site_id"]
            pre[(chave, r["tipo"])].append([float(r[f"prop_{c}"]) for c in CLASSES])
    l1_por_par = {}
    for (par, _tipo) in list(pre):
        t, c = pre.get((par, "tratamento")), pre.get((par, "controle"))
        if not t or not c:
            continue
        mt = [statistics.mean(x[i] for x in t) for i in range(5)]
        mc = [statistics.mean(x[i] for x in c) for i in range(5)]
        l1_por_par[par] = round(sum(abs(a - b) for a, b in zip(mt, mc)), 6)
    print(f"L1 calculado para {len(l1_por_par)} pares")

    # --- 2. geografia por ponto (1 chamada por ponto, não por linha) ------------------------
    pontos = {}
    for r in eua:
        pontos.setdefault(r["site_id"], {"site_id": r["site_id"],
                                         "lat": float(r["lat"]), "lon": float(r["lon"])})
    geo = {}
    print(f"geocodificando {len(pontos)} pontos...")
    for i, (sid, p) in enumerate(pontos.items(), 1):
        try:
            g = geocodificar(p["lat"], p["lon"])
        except Exception as e:  # noqa: BLE001
            print(f"  {sid}: geocoder falhou ({e})")
            g = {}
        if g:
            g["uf"] = SIGLA.get(g.get("estado_nome", ""), "")
            g["regiao"] = next((k for k, v in REGIAO.items() if g["uf"] in v), "")
            g["populacao"] = populacao_acs(g.get("fips", ""))
        geo[sid] = g
        if i % 8 == 0:
            print(f"  {i}/{len(pontos)}", flush=True)
        time.sleep(0.2)

    # --- 3. LST e bioma via Earth Engine ----------------------------------------------------
    anos_por_ponto = defaultdict(list)
    for r in eua:
        anos_por_ponto[r["site_id"]].append(int(r["ano"]))
    ctx = contexto_ee(list(pontos.values()), anos_por_ponto)

    # --- 4. aplica ---------------------------------------------------------------------------
    preenchidos = defaultdict(int)
    for r in linhas:
        if r["pais"] != "EUA":
            continue
        sid, par = r["site_id"], (r["pareado_com"] or r["site_id"])
        g = geo.get(sid) or {}
        for col, val in (("municipio", g.get("municipio", "")),
                         ("uf", g.get("uf", "")),
                         ("codigo_ibge", g.get("fips", "")),
                         ("regiao", g.get("regiao", "")),
                         ("populacao", g.get("populacao", ""))):
            if val:
                r[col] = val
                preenchidos[col] += 1
        num = ctx["bioma_num"].get(sid)
        if num:
            r["bioma"] = BIOMA_NOME.get(int(num), f"RESOLVE biome {int(num)}")
            preenchidos["bioma"] += 1
        v = ctx["lst"].get((sid, int(r["ano"])))
        if v is not None:
            r["lst_media_celsius"] = v
            preenchidos["lst_media_celsius"] += 1
        if par in l1_por_par:
            r["l1_rf"] = l1_por_par[par]
            r["qualidade_par"] = qualidade_l1(l1_por_par[par])
            preenchidos["l1_rf"] += 1
            preenchidos["qualidade_par"] += 1

    # --- 5. completa o lado brasileiro: controle herda contexto do seu tratamento ------------
    ctx_br = {r["site_id"]: r for r in linhas if r["pais"] == "BR" and r["tipo"] == "tratamento"}
    for r in linhas:
        if r["pais"] != "BR" or r["tipo"] != "controle":
            continue
        t = ctx_br.get(r["pareado_com"])
        if not t:
            continue
        for col in ("tier", "regiao", "bioma"):
            if not (r.get(col) or "").strip() and (t.get(col) or "").strip():
                r[col] = t[col]
                preenchidos[f"BR:{col}"] += 1

    with BASE.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    print("\npreenchido:")
    for k, v in sorted(preenchidos.items()):
        print(f"  {k}: {v} linhas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
