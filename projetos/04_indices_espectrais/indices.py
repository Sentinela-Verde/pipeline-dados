"""Índices espectrais / stack de features (SV-08).

Processamento 100% local (sem Earth Engine) sobre os `.tif` já baixados por SV-06/SV-06b:

    dados/bronze/imagens_satelite/sentinel2/{site_id}/{ano}.tif       -- 6 bandas harmonizadas, int16 x10000, 10 m
    dados/bronze/imagens_satelite/landsat/{site_id}/{ano}.tif  -- 6 bandas harmonizadas, int16 x10000, 30 m

Para cada raster de entrada, gera `dados/silver/features/{sensor}/{site_id}/{ano}.tif` com
**13 bandas float32** (as 6 bandas harmonizadas convertidas para reflectância + 7 índices
espectrais), na mesma grade/CRS/transform do raster de origem. O mesmo código roda para as duas
eras — não ramifica por sensor — porque opera só sobre os nomes canônicos de banda
(`bandas.bandas_harmonizadas()`), que já são idênticos nas duas eras.

Fórmulas (todas sobre reflectância float [0, 1] — ver docs/tarefas/SV-08-indices-espectrais.md):

    NDVI   = (nir - red) / (nir + red)
    EVI    = 2.5 * (nir - red) / (nir + 6*red - 7.5*blue + 1)
    NDWI   = (green - nir) / (green + nir)
    MNDWI  = (green - swir1) / (green + swir1)
    NDBI   = (swir1 - nir) / (swir1 + nir)
    BSI    = ((swir1 + red) - (nir + blue)) / ((swir1 + red) + (nir + blue))
    NDMI   = (nir - swir1) / (nir + swir1)

Tratamento numérico (nunca produz NaN/inf):
  - Denominador com |valor| < EPS -> o resultado daquela divisão vira 0.0 e o pixel entra na
    máscara de inválidos (então acaba virando nodata em TODAS as 13 bandas de saída — mantém a
    máscara conjunta, ver `calcular_indices`).
  - Qualquer banda de entrada nodata em um pixel -> nodata nas 13 bandas de saída naquele pixel.
  - Índices clipados ao intervalo teórico [-1, 1] (EVI: [-1, 2.5]).

Rode com: python indices.py --sensor <s2|landsat|all> --site <id|all> --ano <ano|all> [--force]

Manifest auditável em `dados/manifests/features_{sensor}_{site_id}_{ano}.json` (commitado, o .tif
não é) — os nomes das 13 bandas viram o contrato de coluna do dataset de modelagem (SV-11) e
precisam ser idênticos nas duas eras (testado em `tests/test_indices.py`).

**Formato de gravação (SV-26, controle de disco):** o cálculo interno (`calcular_indices`/
`montar_stack`) continua em float32 (reflectância/índice "de verdade") — só a **escrita em disco**
muda: `_escrever_tif` converte o stack float para **int16 com `FATOR_ESCALA=10000`** (mesmo padrão
já usado pelas bandas brutas de SV-06/SV-06b), em vez de float32. Índices vivem em [-1, 2.5]; int16
escalado por 10000 cobre essa faixa com folga (±3.27) e é metade do tamanho de float32 — este era o
maior diretório de disco do repo (`dados/silver/features`), então o ganho é o dobro da capacidade
para o mesmo espaço. `NODATA` (-9999) é gravado sem escalar (não é `-9999 * FATOR_ESCALA`, que
estouraria int16) — é um sentinel fora de qualquer faixa física possível nas duas representações.
a etapa de dataset (que monta o treino) reverte a escala usando o
`fator_escala` do manifest antes de montar as colunas de feature.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import rasterio

from config import REPO_ROOT, SETTINGS, SITES_PATH
from bandas import bandas_harmonizadas

# --------------------------------------------------------------------------------------------
# Constantes / contrato
# --------------------------------------------------------------------------------------------

NODATA = -9999  # sentinel de saída — usado tanto no stack float32 interno quanto no int16 gravado
                 # em disco (nunca escalado por FATOR_ESCALA — ver docstring do módulo)
EPS = 1e-6  # abaixo disso, denominador é tratado como "zero" -> nodata, nunca NaN/inf
FATOR_ESCALA = 10000  # int16 gravado em disco = round(valor_float * FATOR_ESCALA); ver docstring

# token de CLI/diretório ("s2"/"landsat", mesma convenção de dados/bronze/imagens_satelite/) -> nome completo do sensor
# gravado dentro do manifest (mesma convenção de sensor usada nos manifests de SV-06/SV-06b e em
# ADR-003, "sensor (landsat/sentinel2)" como feature explícita de SV-12).
_SENSOR_TOKEN_PARA_NOME: dict[str, str] = {"s2": "sentinel2", "landsat": "landsat"}

_INDICES: tuple[str, ...] = ("ndvi", "evi", "ndwi", "mndwi", "ndbi", "bsi", "ndmi")

_CLIP: dict[str, tuple[float, float]] = {
    "ndvi": (-1.0, 1.0),
    "evi": (-1.0, 2.5),
    "ndwi": (-1.0, 1.0),
    "mndwi": (-1.0, 1.0),
    "ndbi": (-1.0, 1.0),
    "bsi": (-1.0, 1.0),
    "ndmi": (-1.0, 1.0),
}

FORMULAS: dict[str, str] = {
    "ndvi": "(nir - red) / (nir + red)",
    "evi": "2.5 * (nir - red) / (nir + 6*red - 7.5*blue + 1)",
    "ndwi": "(green - nir) / (green + nir)",
    "mndwi": "(green - swir1) / (green + swir1)",
    "ndbi": "(swir1 - nir) / (swir1 + nir)",
    "bsi": "((swir1 + red) - (nir + blue)) / ((swir1 + red) + (nir + blue))",
    "ndmi": "(nir - swir1) / (nir + swir1)",
}


def bandas_features() -> list[str]:
    """13 nomes de banda de saída, ordem fixa: 6 harmonizadas + 7 índices.

    Contrato para SV-11 — idêntico nas duas eras (não depende de sensor)."""
    return list(bandas_harmonizadas()) + list(_INDICES)


# --------------------------------------------------------------------------------------------
# Cálculo puro (sem I/O) — o núcleo testável de SV-08
# --------------------------------------------------------------------------------------------


def _dividir_seguro(num: np.ndarray, den: np.ndarray, invalido: np.ndarray) -> np.ndarray:
    """`num / den` elemento a elemento; denominador com |den| < EPS vira 0.0 no resultado (nunca
    NaN/inf) e marca o pixel em `invalido` (mutado in-place, OR lógico)."""
    seguro = np.abs(den) >= EPS
    resultado = np.zeros_like(num, dtype=np.float32)
    np.divide(num, den, out=resultado, where=seguro)
    invalido |= ~seguro
    return resultado


def calcular_indices(bandas: dict[str, np.ndarray]) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Calcula os 7 índices a partir de um dict {nome_canônico: array float32 reflectância}.

    Não assume nada sobre sensor/resolução — só sobre os nomes canônicos de banda (é justamente
    esse o ganho da harmonização: o mesmo código roda nas duas eras).

    Devolve `(indices, pixels_invalidos)`: `indices` já vem clipado ao intervalo teórico de cada
    um; `pixels_invalidos` é a máscara (True = descartar) de pixels que bateram em algum
    denominador ~0 em qualquer um dos 7 índices — quem chama deve unir essa máscara com a máscara
    de nodata das bandas de entrada antes de gravar (mantém a invariante de máscara conjunta nas
    13 bandas de saída).
    """
    blue, green, red = bandas["blue"], bandas["green"], bandas["red"]
    nir, swir1, swir2 = bandas["nir"], bandas["swir1"], bandas["swir2"]
    del swir2  # não entra em nenhuma fórmula de SV-08; mantido no dict só por simetria com a entrada

    invalido = np.zeros(red.shape, dtype=bool)

    indices = {
        "ndvi": _dividir_seguro(nir - red, nir + red, invalido),
        "evi": 2.5 * _dividir_seguro(nir - red, nir + 6 * red - 7.5 * blue + 1, invalido),
        "ndwi": _dividir_seguro(green - nir, green + nir, invalido),
        "mndwi": _dividir_seguro(green - swir1, green + swir1, invalido),
        "ndbi": _dividir_seguro(swir1 - nir, swir1 + nir, invalido),
        "bsi": _dividir_seguro((swir1 + red) - (nir + blue), (swir1 + red) + (nir + blue), invalido),
        "ndmi": _dividir_seguro(nir - swir1, nir + swir1, invalido),
    }

    for nome, arr in indices.items():
        lo, hi = _CLIP[nome]
        indices[nome] = np.clip(arr, lo, hi).astype(np.float32)

    return indices, invalido


def montar_stack(
    refl: dict[str, np.ndarray], pixel_nodata_entrada: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Monta o array (13, H, W) float32 final, na ordem de `bandas_features()`.

    `refl`: dict {nome_canônico: array float32 reflectância}, com pixels nodata de entrada já
    zerados (não importa o valor exato ali, o resultado é descartado pela máscara).
    `pixel_nodata_entrada`: máscara (H, W) bool, True onde qualquer banda de entrada é nodata.

    Devolve `(stack, pct_pixels_validos)` — `stack` já com `NODATA` aplicado nas 13 bandas, de
    forma idêntica (máscara conjunta), `pct_pixels_validos` calculado sobre a máscara final.
    """
    indices, pixel_invalido_indice = calcular_indices(refl)
    invalido = pixel_nodata_entrada | pixel_invalido_indice

    bandas_out = bandas_features()
    stack = np.empty((len(bandas_out), *invalido.shape), dtype=np.float32)
    for i, nome in enumerate(bandas_harmonizadas()):
        stack[i] = refl[nome]
    for i, nome in enumerate(_INDICES, start=len(bandas_harmonizadas())):
        stack[i] = indices[nome]

    stack[:, invalido] = NODATA

    total = invalido.size
    pct_validos = 100.0 * float(np.sum(~invalido)) / total if total else 0.0
    return stack, pct_validos


# --------------------------------------------------------------------------------------------
# I/O: leitura do raster de origem + manifest, escrita do stack + manifest
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


def _caminho_relativo_ao_repo(path: Path) -> str:
    """String de caminho relativo ao repo quando possível (manifest legível/portável); cai para o
    caminho absoluto se `path` estiver fora do repo (ex.: `DATA_ROOT` sobrescrito em teste)."""
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _raw_tif_path(sensor_token: str, site_id: str, ano: int) -> Path:
    return SETTINGS.bronze_imagens_dir(sensor_token) / site_id / f"{ano}.tif"


def _raw_manifest_path(sensor_token: str, site_id: str, ano: int) -> Path:
    return SETTINGS.manifests_dir / f"{sensor_token}_{site_id}_{ano}.json"


def _out_tif_path(sensor_token: str, site_id: str, ano: int) -> Path:
    return SETTINGS.silver_features_dir(sensor_token) / site_id / f"{ano}.tif"


def _out_manifest_path(sensor_token: str, site_id: str, ano: int) -> Path:
    return SETTINGS.manifests_dir / f"features_{sensor_token}_{site_id}_{ano}.json"


def _ler_raster_origem(tif_path: Path, manifest: dict) -> tuple[dict[str, np.ndarray], np.ndarray, dict]:
    """Lê o `.tif` bruto (int16, escala fixa, nodata inteiro) e devolve
    `(refl, pixel_nodata_entrada, perfil)`.

    `refl`: dict {nome_canônico: array float32 reflectância}, com pixels nodata de entrada já
    zerados (nunca alimenta divisão com o valor sentinel bruto).
    `perfil`: crs/transform/shape do raster de origem, para copiar sem recalcular (item 3 do
    escopo — "Mesma grade/CRS/transform do input, copie do input, não recalcule").

    Não assume ordem/nome de banda — lê `ds.descriptions` e reordena pelos nomes canônicos, com
    fallback para `manifest["bandas"]` se a descrição não vier gravada no arquivo.
    """
    with rasterio.open(tif_path) as ds:
        arr_int = ds.read()
        descricoes = [d for d in ds.descriptions]
        perfil = {"crs": ds.crs, "transform": ds.transform, "width": ds.width, "height": ds.height}
        nodata_entrada = ds.nodata

    bandas_origem = descricoes if all(descricoes) else list(manifest.get("bandas", []))
    if not bandas_origem or set(bandas_origem) != set(bandas_harmonizadas()):
        raise RuntimeError(
            f"{tif_path}: bandas de origem {bandas_origem!r} não batem com as 6 bandas canônicas "
            f"{bandas_harmonizadas()!r} (nem na descrição do raster nem no manifest)."
        )
    if nodata_entrada is None:
        nodata_entrada = manifest.get("nodata")
    fator_escala = manifest.get("fator_escala", 10000)

    idx_por_nome = {nome: i for i, nome in enumerate(bandas_origem)}
    ordem = [idx_por_nome[nome] for nome in bandas_harmonizadas()]
    arr_int = arr_int[ordem]

    pixel_nodata_entrada = np.any(arr_int == int(nodata_entrada), axis=0)

    refl_arr = arr_int.astype(np.float32) / np.float32(fator_escala)
    refl_arr[:, pixel_nodata_entrada] = 0.0
    refl = {nome: refl_arr[i] for i, nome in enumerate(bandas_harmonizadas())}

    return refl, pixel_nodata_entrada, perfil


def _para_int16(stack_float: np.ndarray) -> np.ndarray:
    """float32 (reflectância/índice, com sentinel NODATA nos pixels inválidos) -> int16 escalado.

    A máscara de inválidos é conjunta entre as 13 bandas (garantida por `montar_stack`), então
    basta olhar a banda 0 para saber quais pixels são NODATA em todas — evita escalar o próprio
    sentinel (`NODATA * FATOR_ESCALA` estouraria int16 e corromperia o valor)."""
    invalido = stack_float[0] == NODATA
    escalado = np.round(stack_float.astype(np.float64) * FATOR_ESCALA)
    arr_int16 = escalado.astype(np.int16)
    arr_int16[:, invalido] = NODATA
    return arr_int16


def _escrever_tif(path: Path, stack: np.ndarray, perfil: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bandas = bandas_features()
    arr_int16 = _para_int16(stack)
    profile = {
        "driver": "GTiff",
        "dtype": "int16",
        "nodata": NODATA,
        "width": perfil["width"],
        "height": perfil["height"],
        "count": len(bandas),
        "crs": perfil["crs"],
        "transform": perfil["transform"],
        "compress": "deflate",
        "predictor": 2,  # predictor de inteiro (3 é só para ponto flutuante)
    }
    with rasterio.open(path, "w", **profile) as ds:
        ds.write(arr_int16)
        ds.descriptions = tuple(bandas)


def _escrever_manifest(
    manifest_path: Path,
    *,
    site_id: str,
    ano: int,
    sensor_token: str,
    perfil: dict,
    resolucao_m: int,
    pct_pixels_validos: float,
    tif_path: Path,
    raw_manifest_path: Path,
) -> dict:
    transform = perfil["transform"]
    raw_tif_path = SETTINGS.bronze_imagens_dir(sensor_token) / site_id / f"{ano}.tif"
    manifest = {
        "site_id": site_id,
        "ano": ano,
        "sensor": _SENSOR_TOKEN_PARA_NOME[sensor_token],
        "origem": {
            "raw_tif": _caminho_relativo_ao_repo(raw_tif_path),
            "raw_manifest": _caminho_relativo_ao_repo(raw_manifest_path),
        },
        "bandas": bandas_features(),
        "bandas_entrada": bandas_harmonizadas(),
        "indices": list(_INDICES),
        "formulas": FORMULAS,
        "clip": {nome: list(faixa) for nome, faixa in _CLIP.items()},
        "crs": str(perfil["crs"]),
        "transform": [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f],
        "shape": {"width": perfil["width"], "height": perfil["height"], "bandas": len(bandas_features())},
        "resolucao_m": resolucao_m,
        "nodata": NODATA,
        "fator_escala": FATOR_ESCALA,
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


def _ja_processado(tif_path: Path, manifest_path: Path) -> bool:
    if not (tif_path.exists() and manifest_path.exists()):
        return False
    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    return manifest.get("sha256") == _sha256_arquivo(tif_path)


def processar_site_ano(sensor_token: str, site_id: str, ano: int, *, force: bool = False) -> dict:
    """Gera (ou reaproveita, se idempotente) o stack de 13 bandas para um site/ano/sensor."""
    if sensor_token not in _SENSOR_TOKEN_PARA_NOME:
        raise ValueError(f"sensor deve ser um de {list(_SENSOR_TOKEN_PARA_NOME)}, recebido: {sensor_token!r}")

    raw_tif = _raw_tif_path(sensor_token, site_id, ano)
    raw_manifest_path = _raw_manifest_path(sensor_token, site_id, ano)
    out_tif = _out_tif_path(sensor_token, site_id, ano)
    out_manifest_path = _out_manifest_path(sensor_token, site_id, ano)

    if not force and _ja_processado(out_tif, out_manifest_path):
        print(f"[{sensor_token}/{site_id}/{ano}] já existe e confere (sha256) — pulando (use --force para regerar).")
        with out_manifest_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    if not raw_tif.exists():
        raise FileNotFoundError(f"{raw_tif} não existe — rode a ingestão (SV-06/SV-06b) antes de SV-08.")
    if not raw_manifest_path.exists():
        raise FileNotFoundError(f"{raw_manifest_path} não existe — rode a ingestão (SV-06/SV-06b) antes de SV-08.")

    with raw_manifest_path.open("r", encoding="utf-8") as f:
        raw_manifest = json.load(f)

    refl, pixel_nodata_entrada, perfil = _ler_raster_origem(raw_tif, raw_manifest)
    stack, pct_validos = montar_stack(refl, pixel_nodata_entrada)

    resolucao_m = raw_manifest.get("resolucao_m", round(perfil["transform"].a))

    _escrever_tif(out_tif, stack, perfil)
    manifest = _escrever_manifest(
        out_manifest_path,
        site_id=site_id,
        ano=ano,
        sensor_token=sensor_token,
        perfil=perfil,
        resolucao_m=resolucao_m,
        pct_pixels_validos=pct_validos,
        tif_path=out_tif,
        raw_manifest_path=raw_manifest_path,
    )
    print(f"[{sensor_token}/{site_id}/{ano}] OK — {out_tif} | pct_pixels_validos={pct_validos:.2f}%")
    return manifest


# --------------------------------------------------------------------------------------------
# Descoberta de site/ano (parametros/sites.geojson + o que já existe em dados/bronze/imagens_satelite/)
# --------------------------------------------------------------------------------------------


def _load_site_ids() -> list[str]:
    import geopandas as gpd

    gdf = gpd.read_file(SITES_PATH)
    gdf = gdf[gdf["ativo"] == True]
    return sorted(str(s) for s in gdf["site_id"])


def _validar_site(site_id: str, site_ids_validos: list[str]) -> None:
    if site_id not in site_ids_validos:
        raise SystemExit(f"site_id '{site_id}' não encontrado (ou inativo) em parametros/sites.geojson. Disponíveis: {site_ids_validos}")


def _anos_disponiveis(sensor_token: str, site_id: str) -> list[int]:
    """Anos com `.tif` bruto já ingerido para este sensor/site — evita hardcodar faixas de ano."""
    site_dir = SETTINGS.bronze_imagens_dir(sensor_token) / site_id
    if not site_dir.exists():
        return []
    return sorted(int(p.stem) for p in site_dir.glob("*.tif"))


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stack de features / índices espectrais (SV-08).")
    parser.add_argument("--sensor", required=True, choices=["s2", "landsat", "all"])
    parser.add_argument("--site", required=True, help="site_id de parametros/sites.geojson, ou 'all'")
    parser.add_argument("--ano", required=True, help="ano, ou 'all' (todo .tif já ingerido em dados/bronze/imagens_satelite/)")
    parser.add_argument("--force", action="store_true", help="regera mesmo se já existir")
    args = parser.parse_args(argv)

    sensores = ["s2", "landsat"] if args.sensor == "all" else [args.sensor]

    site_ids_validos = _load_site_ids()
    if args.site == "all":
        site_ids = site_ids_validos
    else:
        _validar_site(args.site, site_ids_validos)
        site_ids = [args.site]

    processados = 0
    falhas = 0
    for sensor_token in sensores:
        for site_id in site_ids:
            if args.ano == "all":
                anos = _anos_disponiveis(sensor_token, site_id)
                if not anos:
                    print(
                        f"AVISO: nenhum .tif em dados/bronze/imagens_satelite/{sensor_token}/{site_id}/ — nada a processar.",
                        file=sys.stderr,
                    )
                    continue
            else:
                anos = [int(args.ano)]

            for ano in anos:
                try:
                    processar_site_ano(sensor_token, site_id, ano, force=args.force)
                    processados += 1
                except Exception as e:  # noqa: BLE001 - reportar e seguir para os demais site/ano/sensor
                    falhas += 1
                    print(f"ERRO [{sensor_token}/{site_id}/{ano}]: {e}", file=sys.stderr)

    print(f"Concluído: {processados} stack(s) OK, {falhas} falha(s).")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
