"""Segunda passada: UF/região pelo FIPS (offline) e população no buffer de 5 km (GHSL, via GEE).

`populacao` (município/condado) fica vazia do lado americano de propósito: o análogo é o ACS, que
passou a exigir chave. Em vez de encher a coluna com outra definição, entra uma coluna NOVA,
`populacao_buffer_5km`, calculada do MESMO jeito nos dois países — aí a comparação é legítima.
"""
from __future__ import annotations
import csv, sys
from pathlib import Path

REPO = Path(r"C:\Users\gabri\IdeaProjects\modelo-imagens-satelite")
BASE = Path(r"C:\Users\gabri\IdeaProjects\pipeline-dados\dados\gold\base_final_32_dc_br_eua.csv")
BUFFER_KM = 5
GHSL = "JRC/GHSL/P2023A/GHS_POP"   # 100 m, epocas de 5 em 5 anos

FIPS_UF = {"01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT","10":"DE",
 "11":"DC","12":"FL","13":"GA","15":"HI","16":"ID","17":"IL","18":"IN","19":"IA","20":"KS",
 "21":"KY","22":"LA","23":"ME","24":"MD","25":"MA","26":"MI","27":"MN","28":"MS","29":"MO",
 "30":"MT","31":"NE","32":"NV","33":"NH","34":"NJ","35":"NM","36":"NY","37":"NC","38":"ND",
 "39":"OH","40":"OK","41":"OR","42":"PA","44":"RI","45":"SC","46":"SD","47":"TN","48":"TX",
 "49":"UT","50":"VT","51":"VA","53":"WA","54":"WV","55":"WI","56":"WY"}
REGIAO = {"Northeast":{"CT","ME","MA","NH","RI","VT","NJ","NY","PA"},
 "Midwest":{"IL","IN","MI","OH","WI","IA","KS","MN","MO","NE","ND","SD"},
 "South":{"DE","FL","GA","MD","NC","SC","VA","DC","WV","AL","KY","MS","TN","AR","LA","OK","TX"},
 "West":{"AZ","CO","ID","MT","NV","NM","UT","WY","AK","CA","HI","OR","WA"}}

def main() -> int:
    with BASE.open(encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    cols = list(linhas[0].keys())
    if "populacao_buffer_5km" not in cols:
        cols.insert(cols.index("populacao") + 1, "populacao_buffer_5km")

    n_uf = 0
    for r in linhas:
        r.setdefault("populacao_buffer_5km", "")
        if r["pais"] == "EUA" and len(r.get("codigo_ibge") or "") == 5:
            uf = FIPS_UF.get(r["codigo_ibge"][:2], "")
            if uf:
                r["uf"] = uf
                r["regiao"] = next((k for k, v in REGIAO.items() if uf in v), "")
                n_uf += 1

    pontos = {}
    for r in linhas:
        pontos.setdefault(r["site_id"], (float(r["lat"]), float(r["lon"])))
    print(f"UF/regiao preenchidas: {n_uf} linhas | populacao no buffer para {len(pontos)} pontos")

    sys.path.insert(0, str(REPO / "src"))
    from sentinela.gee.auth import init_ee
    import ee
    init_ee()
    feats = [ee.Feature(ee.Geometry.Point([lon, lat]).buffer(BUFFER_KM * 1000), {"sid": sid})
             for sid, (lat, lon) in pontos.items()]
    img = ee.ImageCollection(GHSL).filter(ee.Filter.eq("system:index", "2020")).first()
    if img is None:
        img = ee.ImageCollection(GHSL).sort("system:time_start", False).first()
    res = img.reduceRegions(collection=ee.FeatureCollection(feats),
                            reducer=ee.Reducer.sum(), scale=100).getInfo()
    pop = {f["properties"]["sid"]: f["properties"].get("sum") for f in res["features"]}
    n = 0
    for r in linhas:
        v = pop.get(r["site_id"])
        if v is not None:
            r["populacao_buffer_5km"] = int(round(float(v)))
            n += 1
    print(f"populacao_buffer_5km preenchida: {n} linhas")

    with BASE.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(linhas)
    return 0

if __name__ == "__main__":
    sys.exit(main())
