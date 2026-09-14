"""Ingestão Landsat 8/9 harmonizado — era 2013-2018 + anos de sobreposição (SV-06b).

Par de `sentinel2.py` (SV-06): produz `dados/bronze/imagens_satelite/landsat/{site_id}/{ano}.tif` com as
mesmas 6 bandas canônicas de `harmonizacao.py`, na resolução nativa do Landsat (30 m),
para que SV-11 possa unir as duas eras num único dataset de modelagem.

Rode com: python landsat.py --site <id|all> --ano <ano|all> [--force]

## Regra de origem de grade (coordenação com SV-06, sem comunicação ao vivo)

A tarefa original pedia "origem combinada com SV-06" — impraticável rodando os dois em paralelo.
Em vez disso, a origem/extensão da grade é uma função pura e determinística de
`parametros/sites.geojson` (`calcular_grade()`), que SV-06 aplica com resolução 10 m e esta tarefa
aplica com resolução 30 m. Como os dois agentes partem do mesmo arquivo fixo e da mesma fórmula,
chegam à mesma origem sem precisar se coordenar — e a grade de 10 m cai automaticamente como
refinamento exato da grade de 30 m (mesma origem, 30 divisível por 10).

Fórmula (ver docstring de `calcular_grade`):
  1. Reprojeta (lon, lat) de EPSG:4326 -> EPSG:31983 -> (x0, y0).
  2. buffer_m = buffer_km * 1000; bbox = [x0-buffer_m, y0-buffer_m, x0+buffer_m, y0+buffer_m].
  3. origin_x = floor(minx / resolucao_m) * resolucao_m (canto esquerdo).
  4. origin_y = ceil(maxy / resolucao_m) * resolucao_m (canto superior).
  5. largura/altura arredondadas para cima ao múltiplo de resolucao_m mais próximo.

## Máscara de nuvem, escala e harmonização

Delegadas inteiramente a `harmonizacao.py` (SV-02b) — este módulo nunca lê `SR_B*`
diretamente nem reimplementa o bitmask de `QA_PIXEL`/`QA_RADSAT`. Ver ADR-003 para o raciocínio.

## Pixels mascarados no arquivo final

Antes do download, a composição tem `unmask(NODATA / FATOR_ESCALA)` aplicado — ou seja, todo pixel
sem nenhuma imagem válida contribuindo (nuvem/sombra/saturação em todas as cenas da janela) já sai
do Earth Engine como exatamente `-9999 / 10000 = -0.9999` em float, um valor muito fora da faixa
física de reflectância ([-0.05, 1.2] documentado nos critérios de aceite). Isso é necessário porque
`ee.Image.getDownloadURL(format="GEO_TIFF")` não grava tag de nodata nem canal de máscara no GeoTIFF
exportado (verificado empiricamente nesta tarefa) — sem o unmask explícito, pixels mascarados
sairiam com um valor de preenchimento não documentado, indistinguível de dado real.
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
import numpy as np
import rasterio
from rasterio.transform import from_origin

from config import REPO_ROOT, SETTINGS, SITES_PATH, ConfigError
from auth import init_ee
from harmonizacao import bandas_harmonizadas, harmonizar_landsat, mascara_nuvem

RESOLUCAO_M = 30
FATOR_ESCALA = 10000
NODATA = -9999
CRS = "EPSG:31983"
PCT_VALIDOS_MINIMO = 90.0
AMPLIACOES_JANELA = (0, 1, 2)  # tentativas: padrão, +-1 mes, +-2 meses
HARMONIZACAO_VERSAO = "ADR-003 (2026-08-27) — coeficientes Claverie via NASA HLS bandpass page"

# Filtro de nuvem por CENA (metadado `CLOUD_COVER`, % da cena inteira), aplicado ANTES da
# composição — reduz quanto o Earth Engine processa por chamada (menos cenas entrando na mediana)
# e reduz a chance de precisar ampliar a janela sazonal (`AMPLIACOES_JANELA`) por nuvem residual.
# Isto é além do QA_PIXEL bitmask por pixel já aplicado em `mascara_nuvem` (esse continua rodando
# igual — o filtro aqui é grosso/rápido, o bitmask é fino/por pixel).
CLOUD_COVER_MAXIMO = 20

COLECOES_LANDSAT = {
    "LC08": "LANDSAT/LC08/C02/T1_L2",
    "LC09": "LANDSAT/LC09/C02/T1_L2",
}


# --------------------------------------------------------------------------------------------
# Grade determinística (contrato de coordenação com SV-06 — ver docstring do módulo)
# --------------------------------------------------------------------------------------------


def calcular_grade(lon: float, lat: float, buffer_km: float, resolucao_m: int = RESOLUCAO_M) -> dict[str, Any]:
    """Origem/extensão de grade determinística a partir de (lon, lat, buffer_km) de um site.

    Função pura, sem chamadas ao Earth Engine — só depende de `parametros/sites.geojson`, para que
    SV-06 (10 m) e SV-06b (30 m) cheguem à mesma origem de forma independente. Ver docstring do
    módulo para a fórmula por extenso.
    """
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    x0, y0 = transformer.transform(lon, lat)
    buffer_m = buffer_km * 1000
    minx, miny, maxx, maxy = x0 - buffer_m, y0 - buffer_m, x0 + buffer_m, y0 + buffer_m

    origin_x = math.floor(minx / resolucao_m) * resolucao_m
    origin_y = math.ceil(maxy / resolucao_m) * resolucao_m
    largura_m = math.ceil((maxx - origin_x) / resolucao_m) * resolucao_m
    altura_m = math.ceil((origin_y - miny) / resolucao_m) * resolucao_m
    width = round(largura_m / resolucao_m)
    height = round(altura_m / resolucao_m)

    return {
        "origin_x": origin_x,
        "origin_y": origin_y,
        "width": width,
        "height": height,
        "resolucao_m": resolucao_m,
    }


def _affine(grade: dict[str, Any]) -> rasterio.Affine:
    return from_origin(grade["origin_x"], grade["origin_y"], grade["resolucao_m"], grade["resolucao_m"])


# --------------------------------------------------------------------------------------------
# Config / sites
# --------------------------------------------------------------------------------------------


def _anos_alvo() -> list[int]:
    """2013-2018 (Landsat puro) + anos de sobreposição de parametros/params.yml, sem duplicar."""
    params = SETTINGS.params()
    faixa_a = params["faixa_a"]
    anos_landsat = [int(a) for a, s in faixa_a["sensor_por_ano"].items() if s == "landsat"]
    anos_sobrep = [int(a) for a in faixa_a["anos_sobreposicao"]]
    return sorted(set(anos_landsat) | set(anos_sobrep))


def _load_sites() -> list[dict]:
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


def _load_site(site_id: str) -> dict:
    sites = {s["site_id"]: s for s in _load_sites()}
    if site_id not in sites:
        raise SystemExit(
            f"site_id '{site_id}' não encontrado (ou inativo) em parametros/sites.geojson. "
            f"Disponíveis: {sorted(sites)}"
        )
    return sites[site_id]


# --------------------------------------------------------------------------------------------
# Earth Engine: composição + download, com retry para quota/rate-limit
# --------------------------------------------------------------------------------------------


def _com_retry(fn, tentativas: int = 5, espera_inicial: float = 5.0):
    ultimo_erro: Exception | None = None
    for tentativa in range(tentativas):
        try:
            return fn()
        except (ee.EEException, Exception) as e:
            msg = str(e).lower()
            eh_quota = any(termo in msg for termo in ("quota", "rate limit", "429", "too many requests"))
            if not eh_quota:
                raise
            ultimo_erro = e
            espera = espera_inicial * (2**tentativa)
            print(
                f"AVISO: erro de quota/rate limit do Earth Engine (tentativa {tentativa + 1}/{tentativas}), "
                f"esperando {espera:.0f}s: {e}",
                file=sys.stderr,
            )
            time.sleep(espera)
    raise RuntimeError(f"Excedeu {tentativas} tentativas após erro de quota do Earth Engine: {ultimo_erro}")


def _colecoes_filtradas(aoi: ee.Geometry, ano: int, mes_ini: int, mes_fim: int) -> tuple[ee.ImageCollection, ee.ImageCollection]:
    start, end = f"{ano}-01-01", f"{ano}-12-31"
    filtro_cloud = ee.Filter.lt("CLOUD_COVER", CLOUD_COVER_MAXIMO)
    l8 = (
        ee.ImageCollection(COLECOES_LANDSAT["LC08"])
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.calendarRange(mes_ini, mes_fim, "month"))
        .filter(filtro_cloud)
    )
    l9 = (
        ee.ImageCollection(COLECOES_LANDSAT["LC09"])
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.calendarRange(mes_ini, mes_fim, "month"))
        .filter(filtro_cloud)
    )
    return l8, l9


def _compor(aoi: ee.Geometry, ano: int, mes_ini: int, mes_fim: int) -> tuple[ee.Image, list[str], int]:
    """Composto mediano anual, harmonizado e mascarado. Devolve (imagem, satelites_usados, n_imagens).

    **Otimização (2026-09-14):** 1 chamada de contagem em vez de 2 — antes contava `l8`/`l9`
    separadamente (2 `getInfo()`) só para saber quais satélites entraram; agora conta a coleção já
    mesclada (1 `getInfo()`). O custo é granularidade: `satelites_usados` deixa de dizer qual dos
    dois efetivamente contribuiu e passa a listar os dois sempre que a contagem total é > 0 (ambos
    SEMPRE são consultados no filtro — a informação perdida é só "algum L8 entrou" vs "algum L9
    entrou" isoladamente, não usada em nenhum critério de aceite hoje). `pct_pixels_validos` e a
    checagem de qualidade continuam 100% locais (`_pct_pixels_validos`, pós-download) — nunca
    foram via `reduceRegion`, então não há chamada de rede a menos aí (já era o formato enxuto)."""
    l8, l9 = _colecoes_filtradas(aoi, ano, mes_ini, mes_fim)

    def _prep(img: ee.Image) -> ee.Image:
        return harmonizar_landsat(mascara_nuvem(img, "landsat"))

    colecao_merge = l8.merge(l9)
    n_total = _com_retry(lambda: colecao_merge.size().getInfo())
    satelites = ["LC08", "LC09"] if n_total > 0 else []

    composto = colecao_merge.map(_prep).median()
    return composto, satelites, n_total


def _baixar_bandas(composto: ee.Image, grade: dict[str, Any]) -> np.ndarray:
    """Baixa as 6 bandas harmonizadas como float32, já com sentinel de nodata embutido.

    Ver docstring do módulo: `unmask(NODATA / FATOR_ESCALA)` garante que todo pixel sem cobertura
    válida sai do EE como -0.9999 (fora da faixa física), em vez de um preenchimento não
    documentado — o GEO_TIFF do getDownloadURL não grava tag de nodata.
    """
    bandas = bandas_harmonizadas()
    sentinel_nodata_float = NODATA / FATOR_ESCALA
    exportavel = composto.select(bandas).unmask(sentinel_nodata_float)

    crs_transform = [
        grade["resolucao_m"], 0, grade["origin_x"],
        0, -grade["resolucao_m"], grade["origin_y"],
    ]
    region = ee.Geometry.Rectangle(
        [
            grade["origin_x"],
            grade["origin_y"] - grade["height"] * grade["resolucao_m"],
            grade["origin_x"] + grade["width"] * grade["resolucao_m"],
            grade["origin_y"],
        ],
        proj=CRS,
        evenOdd=False,
    )

    def _get_url() -> str:
        return exportavel.getDownloadURL(
            {
                "crs": CRS,
                "crsTransform": crs_transform,
                "dimensions": f"{grade['width']}x{grade['height']}",
                "region": region,
                "format": "GEO_TIFF",
            }
        )

    url = _com_retry(_get_url)

    def _fetch() -> bytes:
        import requests

        resp = requests.get(url, timeout=180)
        resp.raise_for_status()
        return resp.content

    conteudo = _com_retry(_fetch)

    with rasterio.io.MemoryFile(conteudo) as memfile, memfile.open() as ds:
        arr = ds.read()  # (6, height, width) float32

    return arr


def _para_int16(arr_float: np.ndarray) -> np.ndarray:
    """float32 (reflectância, com sentinel -0.9999 nos pixels inválidos) -> int16 * FATOR_ESCALA."""
    escalado = np.round(arr_float.astype(np.float64) * FATOR_ESCALA)
    return escalado.astype(np.int16)


def _pct_pixels_validos(arr_int16: np.ndarray) -> float:
    """Fração de pixels válidos (banda 0 != NODATA) — a máscara é uniforme entre as 6 bandas
    (ver docstring do módulo: `mascara_nuvem` mascara a imagem inteira, não banda a banda)."""
    banda0 = arr_int16[0]
    total = banda0.size
    if total == 0:
        return 0.0
    validos = int(np.sum(banda0 != NODATA))
    return 100.0 * validos / total


# --------------------------------------------------------------------------------------------
# Escrita de raster + manifest
# --------------------------------------------------------------------------------------------


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:  # noqa: BLE001 - git ausente, repo raso, etc: manifest não pode falhar por isso
        return "desconhecido"


def _sha256_arquivo(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _escrever_tif(path: Path, arr_int16: np.ndarray, grade: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bandas = bandas_harmonizadas()
    transform = _affine(grade)
    profile = {
        "driver": "GTiff",
        "dtype": "int16",
        "nodata": NODATA,
        "width": grade["width"],
        "height": grade["height"],
        "count": len(bandas),
        "crs": CRS,
        "transform": transform,
        "compress": "deflate",
        "predictor": 2,
    }
    with rasterio.open(path, "w", **profile) as ds:
        ds.write(arr_int16)
        ds.descriptions = tuple(bandas)


def _escrever_manifest(
    manifest_path: Path,
    *,
    site_id: str,
    ano: int,
    grade: dict[str, Any],
    satelites_usados: list[str],
    n_imagens_usadas: int,
    pct_pixels_validos: float,
    mes_ini_padrao: int,
    mes_fim_padrao: int,
    mes_ini_efetivo: int,
    mes_fim_efetivo: int,
    tif_path: Path,
) -> dict:
    transform = _affine(grade)
    manifest = {
        "site_id": site_id,
        "ano": ano,
        "sensor": "landsat",
        "colecoes": list(COLECOES_LANDSAT.values()),
        "satelites_usados": satelites_usados,
        "janela_padrao": f"{mes_ini_padrao:02d}-{mes_fim_padrao:02d}",
        "janela_efetiva": f"{mes_ini_efetivo:02d}-{mes_fim_efetivo:02d}",
        "janela_ampliada": (mes_ini_efetivo, mes_fim_efetivo) != (mes_ini_padrao, mes_fim_padrao),
        "mascara": {
            "metodo": "QA_PIXEL bitmask + QA_RADSAT",
            "qa_pixel_bits": {"dilated_cloud": 1, "cirrus": 2, "cloud": 3, "cloud_shadow": 4},
            "qa_radsat": "pixel removido se qualquer banda saturada (QA_RADSAT != 0)",
        },
        "harmonizacao": {
            "metodo": "harmonizacao.harmonizar_landsat (Landsat = referência do bandpass)",
            "versao": HARMONIZACAO_VERSAO,
        },
        "bandas": bandas_harmonizadas(),
        "crs": CRS,
        "transform": [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f],
        "shape": {"width": grade["width"], "height": grade["height"]},
        "resolucao_m": RESOLUCAO_M,
        "nodata": NODATA,
        "fator_escala": FATOR_ESCALA,
        "n_imagens_usadas": n_imagens_usadas,
        "pct_pixels_validos": round(pct_pixels_validos, 4),
        "sha256": _sha256_arquivo(tif_path),
        "git_sha": _git_sha(),
        "gerado_em": datetime.now(UTC).isoformat(),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")
    return manifest


# --------------------------------------------------------------------------------------------
# PNG de conferência
# --------------------------------------------------------------------------------------------


def _salvar_png_rgb(arr_int16: np.ndarray, site_id: str, ano: int) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bandas = bandas_harmonizadas()
    idx = {b: i for i, b in enumerate(bandas)}
    rgb = np.stack(
        [arr_int16[idx["red"]], arr_int16[idx["green"]], arr_int16[idx["blue"]]], axis=-1
    ).astype(np.float64)
    valido = arr_int16[idx["red"]] != NODATA
    rgb_refl = rgb / FATOR_ESCALA
    # Alongamento por percentil 2-98 sobre pixels válidos, igual à prática usual de composto RGB.
    for c in range(3):
        canal = rgb_refl[..., c]
        amostra = canal[valido]
        if amostra.size == 0:
            continue
        lo, hi = np.percentile(amostra, [2, 98])
        hi = max(hi, lo + 1e-6)
        rgb_refl[..., c] = np.clip((canal - lo) / (hi - lo), 0, 1)
    rgb_refl[~valido] = 1.0  # nodata em branco

    out_dir = Path(__file__).resolve().parent / "inspecao"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"composto_landsat_{site_id}_{ano}.png"
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.imshow(rgb_refl)
    ax.set_title(f"Landsat harmonizado — {site_id} — {ano}")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------------------------
# Orquestração por site/ano
# --------------------------------------------------------------------------------------------


def _ja_processado(tif_path: Path, manifest_path: Path) -> bool:
    if not (tif_path.exists() and manifest_path.exists()):
        return False
    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    return manifest.get("sha256") == _sha256_arquivo(tif_path)


def ingerir_site_ano(
    site: dict, ano: int, mes_ini_padrao: int, mes_fim_padrao: int, *, force: bool = False, gerar_png: bool = False
) -> dict:
    site_id = site["site_id"]
    tif_path = SETTINGS.imagens_dir / "landsat" / site_id / f"{ano}.tif"
    manifest_path = SETTINGS.manifests_dir / f"landsat_{site_id}_{ano}.json"

    if not force and _ja_processado(tif_path, manifest_path):
        print(f"[{site_id}/{ano}] já existe e confere (sha256) — pulando (use --force para regerar).")
        with manifest_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    grade = calcular_grade(site["lon"], site["lat"], site["buffer_km"])
    aoi = ee.Geometry.Point(site["lon"], site["lat"]).buffer(site["buffer_km"] * 1000)

    mes_ini, mes_fim = mes_ini_padrao, mes_fim_padrao
    arr_int16 = None
    pct_validos = 0.0
    satelites_usados: list[str] = []
    n_imagens_usadas = 0

    for passo, ampliacao in enumerate(AMPLIACOES_JANELA):
        mes_ini = max(1, mes_ini_padrao - ampliacao)
        mes_fim = min(12, mes_fim_padrao + ampliacao)
        composto, satelites_usados, n_imagens_usadas = _compor(aoi, ano, mes_ini, mes_fim)

        # BUG corrigido em 2026-09-14: com CLOUD_COVER_MAXIMO apertado (20%), é real ter 0 cenas
        # numa janela (ex.: Manaus/João Pessoa, região de nuvem alta) — `.median()` de coleção
        # vazia vira uma Image SEM bandas, e `_baixar_bandas` (`.select(bandas)`) quebrava com
        # EEException em vez de tratar como "0% válido" e deixar o laço ampliar a janela.
        if n_imagens_usadas == 0:
            pct_validos = 0.0
            print(
                f"[{site_id}/{ano}] janela {mes_ini}-{mes_fim}: 0 cenas com CLOUD_COVER<"
                f"{CLOUD_COVER_MAXIMO}%."
                + (" Tentando ampliar a janela sazonal..." if passo < len(AMPLIACOES_JANELA) - 1 else "")
            )
            continue

        arr_float = _baixar_bandas(composto, grade)
        arr_int16 = _para_int16(arr_float)
        pct_validos = _pct_pixels_validos(arr_int16)
        if pct_validos >= PCT_VALIDOS_MINIMO:
            if ampliacao > 0:
                print(
                    f"[{site_id}/{ano}] janela ampliada para {mes_ini}-{mes_fim} "
                    f"(pct_pixels_validos={pct_validos:.2f}% >= {PCT_VALIDOS_MINIMO}%)."
                )
            break
        print(
            f"[{site_id}/{ano}] janela {mes_ini}-{mes_fim}: pct_pixels_validos={pct_validos:.2f}% "
            f"< {PCT_VALIDOS_MINIMO}%."
            + (" Tentando ampliar a janela sazonal..." if passo < len(AMPLIACOES_JANELA) - 1 else "")
        )

    if arr_int16 is None:
        raise RuntimeError(
            f"[{site_id}/{ano}] 0 cenas Landsat (L8+L9) com CLOUD_COVER<{CLOUD_COVER_MAXIMO}% em "
            f"nenhuma das janelas tentadas ({[f'{max(1, mes_ini_padrao - a)}-{min(12, mes_fim_padrao + a)}' for a in AMPLIACOES_JANELA]}) "
            f"— sem imagem pra compor esse site/ano com o filtro de nuvem atual."
        )
    if pct_validos < PCT_VALIDOS_MINIMO:
        print(
            f"ACHADO [{site_id}/{ano}]: pct_pixels_validos={pct_validos:.2f}% permanece abaixo de "
            f"{PCT_VALIDOS_MINIMO}% mesmo após ampliar a janela sazonal até {mes_ini}-{mes_fim}. "
            f"Gravado mesmo assim, reportar como achado (não é bug)."
        )

    _escrever_tif(tif_path, arr_int16, grade)
    manifest = _escrever_manifest(
        manifest_path,
        site_id=site_id,
        ano=ano,
        grade=grade,
        satelites_usados=satelites_usados,
        n_imagens_usadas=n_imagens_usadas,
        pct_pixels_validos=pct_validos,
        mes_ini_padrao=mes_ini_padrao,
        mes_fim_padrao=mes_fim_padrao,
        mes_ini_efetivo=mes_ini,
        mes_fim_efetivo=mes_fim,
        tif_path=tif_path,
    )
    print(
        f"[{site_id}/{ano}] OK — {tif_path} | satelites={satelites_usados} "
        f"n_imagens={n_imagens_usadas} pct_validos={pct_validos:.2f}%"
    )

    if gerar_png:
        png_path = _salvar_png_rgb(arr_int16, site_id, ano)
        print(f"[{site_id}/{ano}] PNG de conferência: {png_path}")

    return manifest


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingestão Landsat 8/9 harmonizado (SV-06b).")
    parser.add_argument("--site", required=True, help="site_id de parametros/sites.geojson, ou 'all'")
    parser.add_argument("--ano", required=True, help="ano (2013-2018 ou sobreposição), ou 'all'")
    parser.add_argument("--force", action="store_true", help="regera mesmo se já existir")
    args = parser.parse_args(argv)

    try:
        init_ee()
    except ConfigError as e:
        print(f"ERRO DE CONFIGURAÇÃO:\n{e}", file=sys.stderr)
        return 1

    params = SETTINGS.params()
    mes_ini_padrao, mes_fim_padrao = params["mes_inicio"], params["mes_fim"]
    anos_validos = _anos_alvo()

    sites = _load_sites() if args.site == "all" else [_load_site(args.site)]
    if args.ano == "all":
        anos = anos_validos
    else:
        ano = int(args.ano)
        if ano not in anos_validos:
            raise SystemExit(
                f"ano {ano} não é 2013-2018 nem ano de sobreposição ({anos_validos})."
            )
        anos = [ano]

    # PNG de conferência só para o primeiro e o último ano da era Landsat pura (2013 e 2018),
    # por site — item 5 do escopo de SV-06b.
    anos_landsat_puros = sorted(a for a in anos_validos if a in range(2013, 2019))
    anos_png = {anos_landsat_puros[0], anos_landsat_puros[-1]} if anos_landsat_puros else set()

    falhas = 0
    for site in sites:
        for ano in anos:
            try:
                ingerir_site_ano(
                    site, ano, mes_ini_padrao, mes_fim_padrao, force=args.force, gerar_png=ano in anos_png
                )
            except Exception as e:  # noqa: BLE001 - reportar e seguir para os demais site/ano
                falhas += 1
                print(f"ERRO [{site['site_id']}/{ano}]: {e}", file=sys.stderr)

    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
