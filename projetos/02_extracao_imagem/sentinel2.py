"""Ingestão Sentinel-2 (SV-06): era moderna da série, 2019-2025.

Rode com: python sentinel2.py --site <site_id|all> --ano <ano|all> [--force]

Gera `dados/bronze/imagens_satelite/sentinel2/{site_id}/{ano}.tif` para cada site ativo x ano Sentinel-2 da Faixa A
(`parametros/params.yml`, `sensor_por_ano`): 6 bandas harmonizadas (SV-02b, `harmonizacao.py`),
mascaradas de nuvem (Cloud Score+, `cs_cdf >= 0.60`), agregadas por mediana anual, reprojetadas
para EPSG:31983 a 10 m. Grava reflectância como int16 (fator de escala 10000, nodata -9999).

Grade: a origem (canto superior-esquerdo) é sempre múltiplo de 30 m nos dois eixos, calculada
SÓ a partir de `parametros/sites.geojson` (não depende de nenhuma imagem do Earth Engine) — ver
`calcular_grade()`. Isso garante que a grade de 10 m daqui seja um refinamento exato da grade de
30 m produzida por SV-06b (Landsat), mesmo que as duas tarefas rodem sem coordenação ao vivo (a
mesma fórmula determinística foi passada para as duas). `docs/tarefas/SV-06-ingestao-sentinel2.md`
tem a fórmula completa.

Manifest auditável em `dados/manifests/s2_{site_id}_{ano}.json` (commitado, o .tif não é).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ee
import rasterio
import requests
from pyproj import Transformer

from config import REPO_ROOT, SETTINGS, SITES_PATH, ConfigError
from auth import init_ee
from harmonizacao import bandas_harmonizadas, harmonizar_s2, mascara_nuvem

FATOR_ESCALA = 10000
NODATA = -9999
RESOLUCAO_M = 10
CRS = "EPSG:31983"
CRS_CONFIG = "EPSG:4326"
COLECAO_S2 = "COPERNICUS/S2_SR_HARMONIZED"
COLECAO_CLOUD_SCORE = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
LIMIAR_CS_CDF = 0.60
PCT_VALIDOS_MINIMO = 90.0
MULTIPLO_GRADE_M = 30  # 30 é divisível por 10 (S2) e é a resolução nativa do Landsat (SV-06b)

_MAX_TENTATIVAS_REDE = 5
_ESPERA_INICIAL_S = 5.0


# --------------------------------------------------------------------------------------------
# Rede com backoff — Earth Engine tem quota; erros transientes não devem desistir silenciosamente.
# --------------------------------------------------------------------------------------------


def _retry(fn, *, descricao: str, tentativas: int = _MAX_TENTATIVAS_REDE, espera_inicial: float = _ESPERA_INICIAL_S):
    ultimo_erro: Exception | None = None
    for tentativa in range(tentativas):
        try:
            return fn()
        except (ee.EEException, requests.RequestException) as e:
            ultimo_erro = e
            mensagem = str(e).lower()
            transiente = any(
                p in mensagem
                for p in ("quota", "rate limit", "429", "500", "503", "timeout", "temporarily", "too many requests")
            )
            if not transiente or tentativa == tentativas - 1:
                raise
            espera = espera_inicial * (2**tentativa)
            print(
                f"AVISO: {descricao} falhou ({e}); tentando de novo em {espera:.0f}s "
                f"({tentativa + 1}/{tentativas})...",
                file=sys.stderr,
            )
            time.sleep(espera)
    raise ultimo_erro  # pragma: no cover — inatingível (loop sempre retorna ou levanta acima)


# --------------------------------------------------------------------------------------------
# Grade determinística (regra de coordenação com SV-06b — ver docstring do módulo).
# --------------------------------------------------------------------------------------------


def calcular_grade(lon: float, lat: float, buffer_km: float, resolucao_m: int = RESOLUCAO_M) -> dict[str, Any]:
    """Grade fixa por site: origem (canto superior-esquerdo) múltipla de `MULTIPLO_GRADE_M` (30 m).

    Depende só de `(lon, lat, buffer_km)` — nunca do bounding box de uma imagem do Earth Engine —
    para que SV-06 (10 m) e SV-06b (30 m) cheguem à mesma origem de forma independente, sem
    precisar combinar ao vivo. A origem não depende de `resolucao_m`: só a largura/altura em
    pixels muda entre uma grade de 10 m e uma de 30 m; a origem em metros é idêntica nas duas.
    """
    transformer = Transformer.from_crs(CRS_CONFIG, CRS, always_xy=True)
    x0, y0 = transformer.transform(lon, lat)
    buffer_m = buffer_km * 1000.0
    minx, miny, maxx, maxy = x0 - buffer_m, y0 - buffer_m, x0 + buffer_m, y0 + buffer_m

    m = float(MULTIPLO_GRADE_M)
    origin_x = math.floor(minx / m) * m
    origin_y = math.ceil(maxy / m) * m
    largura_m = math.ceil((maxx - origin_x) / m) * m
    altura_m = math.ceil((origin_y - miny) / m) * m

    if largura_m % resolucao_m != 0 or altura_m % resolucao_m != 0:
        raise AssertionError(
            f"largura/altura da grade ({largura_m}, {altura_m}) não são múltiplas de "
            f"resolucao_m={resolucao_m} — não deveria acontecer, MULTIPLO_GRADE_M={MULTIPLO_GRADE_M}."
        )
    width = int(largura_m / resolucao_m)
    height = int(altura_m / resolucao_m)

    return {
        "origin_x": origin_x,
        "origin_y": origin_y,
        "largura_m": largura_m,
        "altura_m": altura_m,
        "width": width,
        "height": height,
        "resolucao_m": resolucao_m,
        "crs_transform": [float(resolucao_m), 0.0, origin_x, 0.0, -float(resolucao_m), origin_y],
    }


def _grade_geometry(grade: dict[str, Any]) -> ee.Geometry:
    minx = grade["origin_x"]
    maxy = grade["origin_y"]
    maxx = minx + grade["largura_m"]
    miny = maxy - grade["altura_m"]
    return ee.Geometry.Rectangle([minx, miny, maxx, maxy], proj=CRS, geodesic=False)


# --------------------------------------------------------------------------------------------
# Config / sites
# --------------------------------------------------------------------------------------------


def _sites_ativos() -> list[dict]:
    import geopandas as gpd

    gdf = gpd.read_file(SITES_PATH)
    gdf = gdf[gdf["ativo"] == True]
    return [
        {
            "site_id": r["site_id"],
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
            "buffer_km": float(r["buffer_km"]),
        }
        for _, r in gdf.iterrows()
    ]


def _site_por_id(site_id: str) -> dict:
    for s in _sites_ativos():
        if s["site_id"] == site_id:
            return s
    raise SystemExit(f"site_id '{site_id}' não encontrado (ou não ativo) em parametros/sites.geojson.")


def _anos_sentinel2() -> list[int]:
    faixa_a = SETTINGS.params()["faixa_a"]
    return [ano for ano in faixa_a["anos"] if faixa_a["sensor_por_ano"].get(ano) == "sentinel2"]


# --------------------------------------------------------------------------------------------
# Composição EE
# --------------------------------------------------------------------------------------------


def _colecao_filtrada(aoi: ee.Geometry, ano: int, mes_ini: int, mes_fim: int) -> ee.ImageCollection:
    def _prep(img: ee.Image) -> ee.Image:
        return harmonizar_s2(mascara_nuvem(img, "sentinel2"))

    return (
        ee.ImageCollection(COLECAO_S2)
        .filterBounds(aoi)
        .filterDate(f"{ano}-01-01", f"{ano}-12-31")
        .filter(ee.Filter.calendarRange(mes_ini, mes_fim, "month"))
        .map(_prep)
    )


def _compor_ano(
    grade_geom: ee.Geometry, grade: dict, ano: int, mes_ini: int, mes_fim: int
) -> tuple[ee.Image, int, float]:
    colecao = _colecao_filtrada(grade_geom, ano, mes_ini, mes_fim)
    n_imagens = _retry(lambda: colecao.size().getInfo(), descricao=f"contar imagens {ano}")
    composto = colecao.median()

    total_px = grade["width"] * grade["height"]
    if n_imagens == 0 or total_px == 0:
        return composto, int(n_imagens), 0.0

    validos = _retry(
        lambda: composto.select("blue")
        .reduceRegion(
            reducer=ee.Reducer.count(),
            geometry=grade_geom,
            crs=CRS,
            crsTransform=grade["crs_transform"],
            maxPixels=int(1e9),
        )
        .get("blue")
        .getInfo(),
        descricao=f"contar pixels válidos {ano}",
    )
    validos = validos or 0
    pct = 100.0 * validos / total_px
    return composto, int(n_imagens), pct


def _compor_com_retentativa(
    grade_geom: ee.Geometry, grade: dict, ano: int, mes_ini: int, mes_fim: int
) -> tuple[ee.Image, int, float, tuple[int, int], bool]:
    composto, n_imagens, pct = _compor_ano(grade_geom, grade, ano, mes_ini, mes_fim)
    janela_usada = (mes_ini, mes_fim)
    ampliada = False

    if pct < PCT_VALIDOS_MINIMO:
        mes_ini2, mes_fim2 = max(1, mes_ini - 1), min(12, mes_fim + 1)
        if (mes_ini2, mes_fim2) != janela_usada:
            print(
                f"  {ano}: pct_pixels_validos={pct:.1f}% < {PCT_VALIDOS_MINIMO}% na janela "
                f"{mes_ini}-{mes_fim}; tentando ampliar para {mes_ini2}-{mes_fim2}...",
                file=sys.stderr,
            )
            composto2, n_imagens2, pct2 = _compor_ano(grade_geom, grade, ano, mes_ini2, mes_fim2)
            if pct2 > pct:
                composto, n_imagens, pct = composto2, n_imagens2, pct2
                janela_usada = (mes_ini2, mes_fim2)
                ampliada = True

    return composto, n_imagens, pct, janela_usada, ampliada


def _sanidade_fisica(composto_float: ee.Image, grade_geom: ee.Geometry, grade: dict) -> dict[str, float | None]:
    """Mediana de red/nir sobre pixels prováveis de vegetação (ndvi > 0.5) — teste de faixa física."""
    ndvi = composto_float.normalizedDifference(["nir", "red"])
    vegetacao = composto_float.updateMask(ndvi.gt(0.5))
    stats = _retry(
        lambda: vegetacao.select(["red", "nir"])
        .reduceRegion(
            reducer=ee.Reducer.median(),
            geometry=grade_geom,
            crs=CRS,
            crsTransform=grade["crs_transform"],
            maxPixels=int(1e9),
        )
        .getInfo(),
        descricao="sanidade física (red/nir sobre vegetação)",
    )
    return {"red_mediana_vegetacao": stats.get("red"), "nir_mediana_vegetacao": stats.get("nir")}


def _preparar_para_download(composto: ee.Image) -> ee.Image:
    bandas = bandas_harmonizadas()
    return composto.select(bandas).multiply(FATOR_ESCALA).round().toInt16().unmask(NODATA)


# --------------------------------------------------------------------------------------------
# Download + pós-processamento (nodata/descrições de banda — GEE não grava a tag nodata que
# pedimos, grava o mínimo do dtype; reescrevemos com rasterio para corrigir isso).
# --------------------------------------------------------------------------------------------


def _baixar_tif(imagem_int16: ee.Image, grade: dict, destino: Path) -> None:
    params = {
        "crs": CRS,
        "crs_transform": grade["crs_transform"],
        "dimensions": f"{grade['width']}x{grade['height']}",
        "format": "GEO_TIFF",
    }
    url = _retry(lambda: imagem_int16.getDownloadURL(params), descricao="gerar URL de download")
    resp = _retry(lambda: requests.get(url, timeout=180), descricao="baixar GeoTIFF")
    resp.raise_for_status()
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(resp.content)


def _finalizar_tif(bruto_path: Path, destino: Path, grade: dict, bandas: list[str]) -> None:
    with rasterio.open(bruto_path) as src:
        perfil = src.profile.copy()
        dados = src.read()

    transform = rasterio.Affine(*grade["crs_transform"])
    perfil.update(nodata=NODATA, dtype="int16", crs=CRS, transform=transform, count=len(bandas))

    with rasterio.open(destino, "w", **perfil) as dst:
        dst.write(dados)
        for i, nome in enumerate(bandas, start=1):
            dst.set_band_description(i, nome)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:  # noqa: BLE001 - git ausente, repo raso, etc: manifest não pode falhar por isso
        return "desconhecido"


# --------------------------------------------------------------------------------------------
# Orquestração por site/ano
# --------------------------------------------------------------------------------------------


def processar_site_ano(site: dict, ano: int, *, force: bool = False) -> dict:
    site_id = site["site_id"]
    tif_path = SETTINGS.imagens_dir / "sentinel2" / site_id / f"{ano}.tif"
    manifest_path = SETTINGS.manifests_dir / f"s2_{site_id}_{ano}.json"

    if tif_path.exists() and manifest_path.exists() and not force:
        print(f"{site_id}/{ano}: já existe ({tif_path}), pulando.")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    params = SETTINGS.params()
    mes_ini, mes_fim = params["mes_inicio"], params["mes_fim"]

    grade = calcular_grade(site["lon"], site["lat"], site["buffer_km"])
    grade_geom = _grade_geometry(grade)

    composto, n_imagens, pct, janela_usada, ampliada = _compor_com_retentativa(
        grade_geom, grade, ano, mes_ini, mes_fim
    )

    if pct < PCT_VALIDOS_MINIMO:
        print(
            f"ACHADO: {site_id}/{ano}: pct_pixels_validos={pct:.1f}% < {PCT_VALIDOS_MINIMO}% "
            f"mesmo após tentar ampliar a janela sazonal (janela final usada: {janela_usada}). "
            f"Gravando mesmo assim — reportar como desvio conhecido, não forçar resultado.",
            file=sys.stderr,
        )

    sanidade = _sanidade_fisica(composto, grade_geom, grade)

    imagem_int16 = _preparar_para_download(composto)
    raw_path = tif_path.with_suffix(".raw.tif")
    _baixar_tif(imagem_int16, grade, raw_path)
    _finalizar_tif(raw_path, tif_path, grade, bandas_harmonizadas())
    raw_path.unlink(missing_ok=True)

    tamanho_mb = tif_path.stat().st_size / (1024 * 1024)
    sha256 = _sha256(tif_path)

    manifest = {
        "site_id": site_id,
        "ano": ano,
        "sensor": "sentinel2",
        "colecao": COLECAO_S2,
        "janela": {"mes_inicio": janela_usada[0], "mes_fim": janela_usada[1], "ampliada": ampliada},
        "mascara": {
            "metodo": "cloud_score_plus",
            "colecao": COLECAO_CLOUD_SCORE,
            "banda": "cs_cdf",
            "limiar": LIMIAR_CS_CDF,
        },
        "bandas": bandas_harmonizadas(),
        "harmonizacao": {
            "funcao": "harmonizacao.harmonizar_s2",
            "aplicar_bandpass": True,
            "metodo": "bandpass linear Claverie (Sentinel-2A MSI -> pseudo-OLI)",
            "fonte": "docs/decisoes/ADR-003-harmonizacao-multissensor.md",
        },
        "crs": CRS,
        "transform": grade["crs_transform"],
        "shape": {"width": grade["width"], "height": grade["height"], "bandas": len(bandas_harmonizadas())},
        "resolucao_m": RESOLUCAO_M,
        "nodata": NODATA,
        "fator_escala": FATOR_ESCALA,
        "n_imagens_usadas": int(n_imagens),
        "pct_pixels_validos": round(pct, 2),
        "sanidade_fisica": sanidade,
        "grade": {
            "origin_x": grade["origin_x"],
            "origin_y": grade["origin_y"],
            "regra": (
                "origem = (floor(minx/30)*30, ceil(maxy/30)*30) em EPSG:31983, a partir do buffer "
                "do site em parametros/sites.geojson — regra de coordenação com SV-06b, ver "
                "docs/tarefas/SV-06-ingestao-sentinel2.md"
            ),
        },
        "sha256": sha256,
        "git_sha": _git_sha(),
        "gerado_em": datetime.now(UTC).isoformat(),
        "tamanho_mb": round(tamanho_mb, 3),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"{site_id}/{ano}: OK — {n_imagens} imagens, {pct:.1f}% válidos, "
        f"{tamanho_mb:.2f} MB -> {tif_path}"
    )
    return manifest


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingestão Sentinel-2 (SV-06, era 2019-2025).")
    parser.add_argument("--site", required=True, help="site_id de parametros/sites.geojson, ou 'all'")
    parser.add_argument("--ano", required=True, help="ano (ex.: 2024), ou 'all' (todos os anos S2 da Faixa A)")
    parser.add_argument("--force", action="store_true", help="reprocessa mesmo se .tif/manifest já existirem")
    args = parser.parse_args()

    try:
        init_ee()
    except ConfigError as e:
        print(f"ERRO DE CONFIGURAÇÃO:\n{e}", file=sys.stderr)
        return 1

    sites = _sites_ativos() if args.site == "all" else [_site_por_id(args.site)]
    anos_validos = _anos_sentinel2()
    if args.ano == "all":
        anos = anos_validos
    else:
        ano_int = int(args.ano)
        if ano_int not in anos_validos:
            print(
                f"ERRO: ano {ano_int} não é Sentinel-2 na Faixa A (parametros/params.yml). "
                f"Anos Sentinel-2 válidos: {anos_validos}. (Anos Landsat são SV-06b.)",
                file=sys.stderr,
            )
            return 1
        anos = [ano_int]

    resultados: list[dict] = []
    houve_erro = False
    for site in sites:
        for ano in anos:
            try:
                resultados.append(processar_site_ano(site, ano, force=args.force))
            except Exception as e:  # noqa: BLE001 - um site/ano falhar nao pode derrubar o lote inteiro
                houve_erro = True
                print(f"ERRO ao processar {site['site_id']}/{ano}: {e}", file=sys.stderr)

    print()
    print("site | ano | n_imagens | pct_pixels_validos | tamanho_mb")
    print("-----|-----|-----------|---------------------|----------")
    for m in resultados:
        print(
            f"{m['site_id']} | {m['ano']} | {m['n_imagens_usadas']} | "
            f"{m['pct_pixels_validos']:.1f}% | {m.get('tamanho_mb', '?')}"
        )

    print()
    print("grade por site (conferir contra o manifest do Landsat de SV-06b):")
    for site in sites:
        grade = calcular_grade(site["lon"], site["lat"], site["buffer_km"])
        print(
            f"{site['site_id']}: origin_x={grade['origin_x']}, origin_y={grade['origin_y']} "
            f"(EPSG:31983)"
        )

    return 1 if houve_erro else 0


if __name__ == "__main__":
    sys.exit(main())
