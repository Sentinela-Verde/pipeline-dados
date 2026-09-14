"""Preenche `populacao` (condado) do lado americano pelo ACS 5-year do Census Bureau.

A chave vem da variável de ambiente CENSUS_API_KEY — nunca escrita em arquivo nem no CSV.
"""
from __future__ import annotations
import csv, json, os, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = Path(r"C:\Users\gabri\IdeaProjects\pipeline-dados\dados\gold\base_final_32_dc_br_eua.csv")
ANO_ACS = 2022
VAR_POP = "B01003_001E"

def pop_condado(fips: str, chave: str) -> str:
    url = (f"https://api.census.gov/data/{ANO_ACS}/acs/acs5?"
           + urllib.parse.urlencode({"get": VAR_POP, "for": f"county:{fips[2:]}",
                                     "in": f"state:{fips[:2]}", "key": chave}))
    with urllib.request.urlopen(url, timeout=30) as r:
        d = json.load(r)
    return d[1][0]

def main() -> int:
    chave = os.environ.get("CENSUS_API_KEY")
    if not chave:
        sys.exit("CENSUS_API_KEY nao definida no ambiente")
    with BASE.open(encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    cols = list(linhas[0].keys())

    fips = sorted({r["codigo_ibge"] for r in linhas
                   if r["pais"] == "EUA" and len(r.get("codigo_ibge") or "") == 5})
    print(f"{len(fips)} condados distintos a consultar (ACS {ANO_ACS} 5-year)")
    pop = {}
    for i, f5 in enumerate(fips, 1):
        try:
            pop[f5] = pop_condado(f5, chave)
        except Exception as e:  # noqa: BLE001
            print(f"  {f5}: falhou ({e})")
        time.sleep(0.15)
        if i % 10 == 0:
            print(f"  {i}/{len(fips)}", flush=True)

    # coluna nova: diz de onde veio a populacao de cada linha
    if "populacao_tipo_estimativa" not in cols:
        cols.insert(cols.index("populacao") + 1, "populacao_tipo_estimativa")
    origem_br = {}
    consolidado = BASE.parent / "consolidado_impacto_modelo.csv"
    if consolidado.exists():
        with consolidado.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("populacao_tipo_estimativa") or "").strip():
                    origem_br[(r["site_id"], r["ano"])] = r["populacao_tipo_estimativa"]

    n = 0
    for r in linhas:
        r.setdefault("populacao_tipo_estimativa", "")
        if r["pais"] == "EUA":
            v = pop.get(r.get("codigo_ibge", ""))
            if v:
                r["populacao"] = v
                r["populacao_tipo_estimativa"] = f"ACS {ANO_ACS} 5-year (condado)"
                n += 1
        elif (r.get("populacao") or "").strip():
            r["populacao_tipo_estimativa"] = origem_br.get((r["site_id"], r["ano"]), "IBGE (municipio)")

    with BASE.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(linhas)
    print(f"populacao preenchida em {n} linhas ({len(pop)} condados resolvidos)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
