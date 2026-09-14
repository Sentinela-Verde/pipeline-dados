"""Etapa 7 (parte) — datação da obra por degrau de NDBI no Landsat.

Rode em três fases, nesta ordem:

    python datar_landsat.py --fase serie      # série anual de NDBI por campus (Earth Engine)
    python datar_landsat.py --fase validar    # confere o método contra datas conhecidas
    python datar_landsat.py --fase datar      # aplica e grava as datas derivadas

**O que este módulo resolve.** A expansão da amostra depende de saber QUANDO a obra de cada
campus começou — sem isso não existe pré/durante/pós, e sem isso não existe estudo de evento. A
datação pelo Dynamic World (feita no repositório de origem) alcança só quem começou depois de
jun/2015, quando a série do DW começa. O Landsat vai a 2013 e é global, então serve para alcançar
o resto.

**Como se data sem classificador.** O DW entrega classe; o Landsat entrega reflectância. Em vez
de classificar, mede-se um índice de construído dentro do próprio footprint do campus e procura-se
o degrau:

    NDBI = (SWIR1 - NIR) / (SWIR1 + NIR)

O NDBI sobe quando vegetação ou solo viram superfície impermeável, e **fica alto** — é degrau, não
pico. Obra em curso passa por solo exposto, que também levanta o NDBI; por isso o critério exige
que o nível se **sustente** depois, não só que suba num ano.

`t0` é o ano que maximiza (média dos anos >= t) − (média dos anos < t), exigindo pelo menos
`minimo_lado` anos de cada lado e um degrau acima de `degrau_minimo`. É detecção de ponto de
mudança padrão, e o degrau medido fica na saída para quem quiser outro limiar.

**Por que a fase `validar` vem antes da `datar`.** Um método de datação novo sem validação é chute
com decimais. A validação compara com as datas que já se conhece por outra via (Dynamic World) e
diz se o método serve — ver o README desta pasta para o veredito da execução publicada, que **não
é favorável**.

Esta parte NÃO depende do Modelo 1: não classifica nada, só lê reflectância. A outra metade da
etapa 7 — expandir a amostra rodando a inferência num raio menor — depende, e por isso não foi
migrada.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from auth import init_ee
from campi import carregar_campi
from config import SETTINGS


def _colecao_landsat(ano: int, fonte: dict):
    """Composto mediano de NDBI do ano, Landsat 8+9, com nuvem e sombra mascaradas."""
    import ee

    def _prep(img):
        qa = img.select("QA_PIXEL")
        # bits 3 e 4 do QA_PIXEL: nuvem e sombra de nuvem
        limpo = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        sr = (
            img.select(["SR_B5", "SR_B6"])
            .multiply(fonte["fator_escala"])
            .add(fonte["offset"])
        )
        return sr.updateMask(limpo).rename(["nir", "swir1"])

    col = None
    for cid in fonte["colecoes"]:
        c = (
            ee.ImageCollection(cid)
            .filterDate(f"{ano}-{fonte['mes_inicio']:02d}-01", f"{ano}-{fonte['mes_fim']:02d}-30")
            .map(_prep)
        )
        col = c if col is None else col.merge(c)
    mediana = col.median()
    return (
        mediana.select("swir1")
        .subtract(mediana.select("nir"))
        .divide(mediana.select("swir1").add(mediana.select("nir")))
        .rename("ndbi")
    )


def _features_dos_campi(params: dict):
    """Footprints como `ee.Feature`, um por campus, mais a tabela de metadados."""
    import ee

    agrupamento = params["agrupamento"]
    feats, meta = [], []
    for c in carregar_campi(
        SETTINGS.footprints_path,
        float(agrupamento["raio_campus_km"]),
        float(agrupamento["celula_grau"]),
    ):
        feats.append(
            ee.Feature(
                ee.Geometry.MultiPolygon([[a] for a in c["aneis"]], geodesic=False),
                {"campus_id": c["campus_id"]},
            )
        )
        meta.append({k: c[k] for k in ("campus_id", "lat", "lon", "nome", "operadora")})
    return feats, pd.DataFrame(meta)


def _serie_ndbi(feats, params: dict) -> pd.DataFrame:
    import ee

    fonte = params["fonte"]
    anos = list(range(int(params["janela"]["ano_inicio"]), int(params["janela"]["ano_fim"]) + 1))
    lote = int(params["lote_reduce_regions"])

    linhas = []
    for ano in anos:
        ndbi = _colecao_landsat(ano, fonte)
        for ini in range(0, len(feats), lote):
            fc = ee.FeatureCollection(feats[ini : ini + lote])
            res = ndbi.reduceRegions(
                collection=fc, reducer=ee.Reducer.mean(), scale=fonte["escala_m"]
            ).getInfo()
            for f in res["features"]:
                p = f["properties"]
                linhas.append({"campus_id": p["campus_id"], "ano": ano, "ndbi": p.get("mean")})
        print(f"    {ano}: {len(linhas)} leituras")
    return pd.DataFrame(linhas)


def detectar_degrau(
    anos: list[int], valores: list[float], minimo_lado: int, degrau_minimo: float
) -> tuple[int | None, float]:
    """Ano que maximiza (média depois) − (média antes). Devolve `(t0, degrau)`.

    Retorna `t0 = None` quando não há anos suficientes ou quando o melhor degrau fica abaixo do
    mínimo — nesses casos o degrau medido ainda volta, para quem quiser aplicar outro limiar sem
    reprocessar.
    """
    pares = [(a, v) for a, v in zip(anos, valores) if v is not None and not pd.isna(v)]
    if len(pares) < 2 * minimo_lado:
        return None, float("nan")
    aa = [a for a, _ in pares]
    vv = np.array([v for _, v in pares], dtype=float)

    melhor_t, melhor_d = None, -np.inf
    for i in range(minimo_lado, len(vv) - minimo_lado + 1):
        d = vv[i:].mean() - vv[:i].mean()
        if d > melhor_d:
            melhor_t, melhor_d = aa[i], d
    if melhor_d < degrau_minimo:
        return None, float(melhor_d)
    return melhor_t, float(melhor_d)


def _salvar(df: pd.DataFrame, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(caminho, index=False)


def _datas_por_campus(serie: pd.DataFrame, params: dict) -> pd.DataFrame:
    criterio = params["criterio_degrau"]
    minimo_lado = int(criterio["minimo_lado"])
    degrau_minimo = float(criterio["degrau_minimo"])

    linhas = []
    for cid, g in serie.groupby("campus_id"):
        g = g.sort_values("ano")
        t0, degrau = detectar_degrau(list(g.ano), list(g.ndbi), minimo_lado, degrau_minimo)
        linhas.append({"campus_id": cid, "ano_landsat": t0, "degrau_ndbi": degrau})
    return pd.DataFrame(linhas)


def fase_serie(params: dict) -> None:
    # Antes de _features_dos_campi: construir ee.Feature já exige o cliente inicializado.
    init_ee()

    feats, meta = _features_dos_campi(params)
    print(f"  {len(feats)} campi com footprint")
    df = _serie_ndbi(feats, params)
    _salvar(df, SETTINGS.saida_dir / "landsat_ndbi_serie.csv")
    _salvar(meta, SETTINGS.saida_dir / "landsat_campi_meta.csv")
    print(f"  -> {SETTINGS.saida_dir / 'landsat_ndbi_serie.csv'}")


def fase_validar(params: dict) -> None:
    """Compara a datação por NDBI com as datas já derivadas do Dynamic World."""
    caminho_serie = SETTINGS.saida_dir / "landsat_ndbi_serie.csv"
    if not caminho_serie.exists():
        sys.exit(f"{caminho_serie} não existe — rode `--fase serie` antes.")
    serie = pd.read_csv(caminho_serie)

    caminho_dw = SETTINGS.saida_dir / params["referencia_validacao"]
    if not caminho_dw.exists():
        sys.exit(
            f"{caminho_dw} não existe — é a datação pelo Dynamic World, que serve de referência. "
            f"Ela vem do repositório de origem (passo 28) e está versionada em dados/silver/."
        )
    dw = pd.read_csv(caminho_dw)
    dw = dw[dw.ano_obra_dw.notna()][["campus_id", "ano_obra_dw"]]

    est = _datas_por_campus(serie, params)
    comp = dw.merge(est, on="campus_id", how="inner")
    comp["erro_anos"] = comp.ano_landsat - comp.ano_obra_dw
    _salvar(comp, SETTINGS.saida_dir / "landsat_datacao_validacao.csv")

    ok = comp[comp.ano_landsat.notna()]
    print(f"\n--- validação contra as {len(dw)} datas do Dynamic World ---")
    print(f"  datados pelo Landsat também : {len(ok)}")
    if len(ok):
        e = ok.erro_anos.astype(float)
        print(f"  erro mediano   : {e.median():+.1f} anos")
        print(f"  erro |mediano| : {e.abs().median():.1f} anos")
        print(f"  dentro de +-1  : {100.0 * (e.abs() <= 1).mean():.0f}%")
        print(f"  dentro de +-2  : {100.0 * (e.abs() <= 2).mean():.0f}%")
    print(f"\n  -> {SETTINGS.saida_dir / 'landsat_datacao_validacao.csv'}")


def fase_datar(params: dict) -> None:
    caminho_serie = SETTINGS.saida_dir / "landsat_ndbi_serie.csv"
    if not caminho_serie.exists():
        sys.exit(f"{caminho_serie} não existe — rode `--fase serie` antes.")
    serie = pd.read_csv(caminho_serie)
    meta = pd.read_csv(SETTINGS.saida_dir / "landsat_campi_meta.csv")

    est = _datas_por_campus(serie, params)
    df = pd.DataFrame(
        {
            "campus_id": est.campus_id,
            "ano_obra_landsat": est.ano_landsat,
            "degrau_ndbi": est.degrau_ndbi.round(4),
            "status": np.where(est.ano_landsat.notna(), "datado", "sem_degrau"),
        }
    ).merge(meta, on="campus_id", how="left")
    _salvar(df, SETTINGS.saida_dir / "landsat_datas_derivadas.csv")

    dat = df[df.status == "datado"]
    print(f"\n--- datação por Landsat ({len(df)} campi) ---")
    print(f"  datados    : {len(dat)}")
    print(f"  sem degrau : {len(df) - len(dat)}")
    if len(dat):
        print("\n  por ano de obra:")
        for a, n in sorted(dat.ano_obra_landsat.value_counts().items()):
            print(f"    {int(a)}: {n}")
    print(f"\n  -> {SETTINGS.saida_dir / 'landsat_datas_derivadas.csv'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Etapa 7 — datação da obra por NDBI no Landsat.")
    ap.add_argument("--fase", choices=("serie", "validar", "datar"), required=True)
    args = ap.parse_args(argv)

    params = SETTINGS.params()
    {"serie": fase_serie, "validar": fase_validar, "datar": fase_datar}[args.fase](params)
    return 0


if __name__ == "__main__":
    sys.exit(main())
