"""SV-15 — output para a frente de Indicadores (etapa 05): transforma os rasters classificados
(SV-14, `dados/silver/classificado/{sensor}/{site}/{ano}.tif`) em artefatos estáveis,
documentados e regeneráveis que quem não é de ML consegue consumir sem entender o modelo.

Rode com:

    python export_indicadores.py --modelo-versao rf_v1.0

**Único ponto de contato desta frente (Modelagem) com a frente de Indicadores** — ver
`docs/decisoes/ADR-002-contrato-indicadores.md` (schema ACORDADO em 2026-08-27, sem contraproposta)
e `docs/tarefas/SV-15-output-indicadores.md` (enunciado vinculante, inclusive a seção de risco).

**Este módulo nomeia empresas reais** (`site_id`/`parametros/sites.geojson` — Ascenty, Odata, Scala,
AngoNAP, ClickIP, Equinix, Everest, HostDime) via `dados/gold/area_por_classe.csv`. Ler
`docs/schema-indicadores.md`, seção "Limitações que quem consome precisa saber", antes de tratar
qualquer número daqui como afirmação factual sobre uma empresa.

Artefatos gerados:

  1. `dados/gold/area_por_classe.csv` — uma linha por site x ano x sensor x classe, sem
     lacuna (`area_m2 = 0` explícito quando a classe não ocorre). Fonte única de verdade dos pixels:
     o próprio array de classe lido do `.tif` (não o `distribuicao_classes` do manifest de SV-14) —
     evita depender de um manifest que, em teoria, poderia estar desatualizado em relação ao raster.
  2. `dados/gold/classes_{site_id}_{ano}_{sensor}.geojson` — polígonos vetorizados por
     classe (`rasterio.features.shapes`, filtro de área ANTES do dissolve, depois dissolve por
     classe), EPSG:4326. Polígonos < 0.1 ha descartados; área descartada registrada em
     `dados/gold/geojson_poligonos_descartados.csv`.
  3. Os rasters de SV-14 em si (`dados/silver/classificado/`, gitignored) — Artefato 3 é só
     referência + instrução de regeneração, documentada em `docs/schema-indicadores.md`.

`fator_correcao_sensor` e a coluna `faixa_serie` refletem o resultado de SV-20
(`src/sentinela/validacao_sensores.py`, `reports/validacao_sensores.md`), lido de
`data/manifests/fator_correcao_sensor_sv20.json` quando esse arquivo existe (gerado por
`a validação de sensores`). SV-20 mediu o viés entre sensores separadamente por
classe crítica (3 = solo_exposto_obras, 4 = construida_urbana) e decidiu tratamento DIFERENTE por
classe, a partir da estabilidade do fator dentro de cada site E da heterogeneidade entre os 16
sites (não só entre anos):

  - **Classe 4 (construida_urbana): tratamento (b)** — fator multiplicativo POR SITE (não um
    número nacional único), aplicado só aos anos 2013-2018 (era exclusivamente Landsat; os anos de
    sobreposição 2019-2021 já têm o valor real do Sentinel-2 na própria linha do CSV e não precisam
    de correção). `area_ha`/`area_m2`/`pct_area_valida` continuam CRUS (não corrigidos in-place) —
    quem consome aplica `area_corrigida_ha = area_ha * fator_correcao_sensor` explicitamente. Sem
    o JSON de SV-20, `fator_correcao_sensor = 1.0` (comportamento anterior, sem correção).
  - **Classe 3 (solo_exposto_obras): tratamento (c)** — SV-20 mediu que o fator, embora estável
    ano a ano DENTRO de cada site, varia de 3,5x a 23x DE SITE PARA SITE (CV entre sites 0.42,
    acima do limiar de 0.35 adotado) — aplicar um número único seria chute, não correção.
    `fator_correcao_sensor` continua `1.0` para classe 3; a série fica publicada em faixas
    separadas (coluna `faixa_serie`), sem emendar Landsat com Sentinel-2.
  - **Classes 1, 2, 5:** fora do escopo medido por SV-20 (o enunciado da tarefa foca nas classes 3
    e 4) — `fator_correcao_sensor = 1.0`, sem correção.

A compensação de viés entre sensores adotada pelo projeto (ADR-003, Plano B opção 1) continua
acontecendo **dentro do modelo** também, via a feature `sensor_landsat` do `rf_v1.0` — o fator de
SV-20 é um ajuste complementar, pós-hoc, aplicado só onde a estabilidade foi demonstrada.

Determinismo: todas as colunas vêm de dado estático (pixels do raster + `parametros/sites.geojson` +
`o contrato de grade da etapa 2`) exceto `gerado_em`, que é um único timestamp por execução do comando (não um
timestamp por linha) — dois runs produzem CSV idêntico exceto essa coluna.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.features
import shapely.geometry
import shapely.ops

import classes
from config import (
    FATOR_CORRECAO_PATH,
    caminho_fator_correcao,
    REPO_ROOT,
    RESOLUCAO_M,
    SITES_PATH,
    SETTINGS,
)

# --------------------------------------------------------------------------------------------
# Contrato / constantes
# --------------------------------------------------------------------------------------------

CLASS_IDS = [1, 2, 3, 4, 5]  # 0 (nodata) nunca vira linha do CSV nem polígono do GeoJSON

# Token físico usado nos caminhos de arquivo (SV-06/SV-08/SV-14, ver predict.py) -> valor
# canônico do contrato de output (ADR-002: `sentinel2` | `landsat`). NUNCA usar o token de
# caminho como valor da coluna `sensor` do CSV — é a troca mais fácil de escorregar aqui.
SENSOR_TOKEN_TO_CANONICO = {"s2": "sentinel2", "landsat": "landsat"}

# fator_correcao_sensor: fixo em 1.0 quando SV-20 não rodou (ou não elegeu uma classe/site para
# correção). Ver docstring do módulo e docs/schema-indicadores.md.
FATOR_CORRECAO_SENSOR_PADRAO = 1.0

FATOR_CORRECAO_SV20_PATH = FATOR_CORRECAO_PATH

# Anos de sobreposição (Faixa A) — replicado de o contrato de grade da etapa 2 pra não fazer I/O extra só pra
# isso; SE params.yml mudar essa lista, este módulo precisa mudar junto (mesmo risco que qualquer
# outra constante replicada no repo — ver ANOS_SOBREPOSICAO em validacao_sensores.py).
ANOS_SOBREPOSICAO = [2019, 2020, 2021]

AREA_MINIMA_POLIGONO_M2 = 1000.0  # 0.1 ha — item 3 do escopo de SV-15

# Prefixo de manifest/diretório da classificação de PRODUÇÃO. Ver --token.
TOKEN_PADRAO = "classificado"

OUTPUTS_DIR = SETTINGS.gold_dir
CSV_PATH = OUTPUTS_DIR / "area_por_classe.csv"
DESCARTE_LOG_PATH = OUTPUTS_DIR / "geojson_poligonos_descartados.csv"

COLUNAS_CSV = [
    "site_id",
    "ano",
    "sensor",
    "resolucao_m",
    "classe_id",
    "classe_nome",
    "area_m2",
    "area_ha",
    "pct_area_valida",
    "pixels_validos",
    "fator_correcao_sensor",
    "modelo_versao",
    "gerado_em",
    "tipo",
    "pareado_com",
    "tier",
    "precisao_coordenada",
    "faixa_serie",
]


class ExportError(RuntimeError):
    """Erro de exportação com mensagem acionável."""


# --------------------------------------------------------------------------------------------
# Sites (tier, precisao_coordenada — revisão de 31/08 do enunciado)
# --------------------------------------------------------------------------------------------


def carregar_metadados_sites() -> dict[str, dict[str, Any]]:
    """`site_id` -> `{tier, precisao_coordenada}`, lido direto de `parametros/sites.geojson`.

    Lido como JSON puro (não via geopandas) — só precisamos de duas propriedades escalares por
    site, não de geometria; evita reprojeção desnecessária.
    """
    path = SITES_PATH
    if not path.exists():
        raise ExportError(f"{path} não existe.")
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for feat in data["features"]:
        props = feat["properties"]
        site_id = props["site_id"]
        if "tier" not in props or "precisao_coordenada" not in props:
            raise ExportError(
                f"site '{site_id}' em parametros/sites.geojson não tem 'tier' e/ou "
                "'precisao_coordenada' — propagação obrigatória (revisão de 31/08 de SV-15)."
            )
        out[site_id] = {
            "tier": int(props["tier"]),
            "precisao_coordenada": props["precisao_coordenada"],
        }
    return out


def carregar_resolucoes() -> dict[str, int]:
    """`sensor_token` (`s2`/`landsat`) -> resolução nominal em metros."""
    return dict(RESOLUCAO_M)


def carregar_fator_correcao_sv20(modelo_versao: str) -> dict[int, dict[str, Any]]:
    """Lê `data/manifests/fator_correcao_sensor_sv20.json` (gerado por
    `a validação de sensores`) e retorna `{classe_id: {"tratamento": "b"|"c",
    "fator_por_site": {site_id: float}}}`. Se o arquivo não existir, retorna `{}` — todo
    `fator_correcao_sensor` fica `1.0` (comportamento anterior a SV-20, sem quebrar quem roda
    `export_indicadores` sem ter rodado `validacao_sensores` antes)."""
    caminho = caminho_fator_correcao(modelo_versao)
    if not caminho.exists():
        return {}
    payload = json.loads(caminho.read_text(encoding="utf-8"))
    # O fator é calibrado sobre UMA classificação; aplicá-lo a outra é erro silencioso.
    calibrado_em = payload.get("modelo_versao")
    if calibrado_em != modelo_versao:
        raise ExportError(
            f"{caminho} foi calibrado sobre '{calibrado_em}', mas a exportação é de "
            f"'{modelo_versao}' — o fator de correção de sensor não é transferível entre "
            "classificações. Rode a validação de sensores para este modelo antes."
        )
    out: dict[int, dict[str, Any]] = {}
    for classe_id_str, info in payload.get("classes", {}).items():
        out[int(classe_id_str)] = {
            "tratamento": info["tratamento"],
            "fator_por_site": {k: float(v) for k, v in info.get("fator_por_site", {}).items()},
        }
    return out


def _fator_e_faixa(
    sensor: str, ano: int, classe_id: int, site_id: str, fator_sv20: dict[int, dict[str, Any]]
) -> tuple[float, str]:
    """`(fator_correcao_sensor, faixa_serie)` para uma linha do CSV — regra combinada de SV-20
    (docstring do módulo tem o raciocínio completo por classe)."""
    if sensor == "sentinel2":
        return FATOR_CORRECAO_SENSOR_PADRAO, "sentinel2_oficial_2019_2025"
    # sensor == "landsat" daqui em diante
    if ano in ANOS_SOBREPOSICAO:
        return FATOR_CORRECAO_SENSOR_PADRAO, "landsat_overlap_referencia"
    # landsat, ano <= 2018 (era exclusivamente Landsat) — aqui é onde uma correção (b) importa
    info_classe = fator_sv20.get(classe_id)
    if info_classe and info_classe["tratamento"] == "b" and site_id in info_classe["fator_por_site"]:
        return info_classe["fator_por_site"][site_id], "landsat_pre2019_corrigido_sv20"
    return FATOR_CORRECAO_SENSOR_PADRAO, "landsat_pre2019_nao_corrigido"


# --------------------------------------------------------------------------------------------
# Localização dos rasters classificados (SV-14) elegíveis para esta versão de modelo
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemRaster:
    sensor_token: str  # "s2" | "landsat" (token de caminho)
    sensor: str  # "sentinel2" | "landsat" (valor canônico do contrato)
    site_id: str
    ano: int
    tif_path: Path
    manifest_path: Path
    manifest: dict[str, Any]


def localizar_rasters(
    modelo_versao: str, site_filtro: str | None = None, token: str = TOKEN_PADRAO
) -> list[ItemRaster]:
    """Varre `dados/manifests/{token}_{sensor}_{site}_{ano}.json` e retorna os itens cujo
    `modelo_versao` bate com o pedido, ordenados de forma determinística (site, ano, sensor).

    O `token` existe porque a inferência do Modelo 1 escreve num prefixo versionado quando roda um
    classificador que não é o de produção (`--saida-token`): `classificado` é a produção, mas
    `classificado-rf_v2.0-dw` é uma avaliação paralela, com manifests de nome diferente. A versão
    original deste módulo tinha o prefixo fixo em `classificado_*`, e por isso NÃO conseguia
    exportar nenhuma classificação alternativa — ela existia no disco e ficava invisível aqui.

    Falha explicitamente (não ignora silenciosamente) se algum manifest tiver `modelo_versao`
    diferente do pedido MAS o `.tif` correspondente também existir — isso indicaria uma mistura de
    versões no diretório de saída de SV-14 que precisa de atenção humana antes de exportar
    (ver risco "frente de Indicadores usa versão antiga do CSV sem perceber", SV-15).
    """
    manifests_dir = SETTINGS.manifests_dir
    itens: list[ItemRaster] = []
    versoes_encontradas: set[str] = set()

    for manifest_path in sorted(manifests_dir.glob(f"{token}_*.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        versoes_encontradas.add(manifest.get("modelo_versao", "desconhecido"))
        if manifest.get("modelo_versao") != modelo_versao:
            continue
        site_id = manifest["site_id"]
        if site_filtro and site_id != site_filtro:
            continue
        sensor_token = manifest["sensor"]
        if sensor_token not in SENSOR_TOKEN_TO_CANONICO:
            raise ExportError(
                f"{manifest_path}: sensor '{sensor_token}' desconhecido "
                f"(esperado um de {sorted(SENSOR_TOKEN_TO_CANONICO)})."
            )
        # O campo `tif` do manifest é um caminho relativo ao repositório que RODOU a inferência,
        # e os manifests migrados carregam o caminho do repo de origem. O raster é localizado pelo
        # token + sensor + site + ano, que é a convenção estável, em vez do path gravado.
        tif_path = (
            SETTINGS.classificado_dir(token) / sensor_token / site_id / f"{manifest['ano']}.tif"
        )
        if not tif_path.exists():
            raise ExportError(
                f"{manifest_path} aponta para {tif_path}, que não existe — rode a inferência do "
                f"Modelo 1 (token {token!r}) antes, ou confira --token."
            )
        itens.append(
            ItemRaster(
                sensor_token=sensor_token,
                sensor=SENSOR_TOKEN_TO_CANONICO[sensor_token],
                site_id=site_id,
                ano=int(manifest["ano"]),
                tif_path=tif_path,
                manifest_path=manifest_path,
                manifest=manifest,
            )
        )

    if not itens:
        disponiveis = sorted(versoes_encontradas)
        raise ExportError(
            f"nenhum raster classificado com modelo_versao='{modelo_versao}' encontrado em "
            f"{manifests_dir}. Versões disponíveis nos manifests: {disponiveis}. "
            "Rode a inferência do Modelo 1 antes, ou confira --modelo-versao/--token."
        )

    itens.sort(key=lambda i: (i.site_id, i.ano, i.sensor_token))
    return itens


# --------------------------------------------------------------------------------------------
# Artefato 1 — area_por_classe.csv
# --------------------------------------------------------------------------------------------


def _ler_classe_array(tif_path: Path) -> tuple[np.ndarray, Any, Any]:
    """Lê a banda única de classe (uint8, nodata=0) inteira — os rasters de SV-14 são pequenos
    o bastante (maior AOI desta rodada, ~1000x1000 px) para caber em memória de uma vez; não
    precisa do processamento em janelas que `predict.py` usa para o stack de features (13 bandas
    float, ordens de grandeza maior)."""
    with rasterio.open(tif_path) as src:
        arr = src.read(1)
        return arr, src.crs, src.transform


def _distribuicao_classes(arr: np.ndarray) -> dict[int, int]:
    """Contagem de pixels por classe 1-5, lida diretamente do array — fonte única de verdade
    desta exportação (não o `distribuicao_classes` do manifest de SV-14, que é redundante e
    poderia, em teoria, ficar desatualizado em relação ao `.tif`)."""
    valores, contagens = np.unique(arr, return_counts=True)
    contagem_por_valor = dict(zip(valores.tolist(), contagens.tolist(), strict=True))
    return {cid: int(contagem_por_valor.get(cid, 0)) for cid in CLASS_IDS}


def gerar_area_por_classe(
    itens: list[ItemRaster],
    sites_meta: dict[str, dict[str, Any]],
    resolucoes: dict[str, int],
    modelo_versao: str,
    gerado_em: str,
    fator_sv20: dict[int, dict[str, Any]] | None = None,
) -> pd.DataFrame:
    fator_sv20 = fator_sv20 or {}
    linhas: list[dict[str, Any]] = []

    for item in itens:
        if item.site_id not in sites_meta:
            raise ExportError(
                f"site_id '{item.site_id}' tem raster classificado mas não existe em "
                "parametros/sites.geojson — não dá para propagar tier/precisao_coordenada."
            )
        meta_site = sites_meta[item.site_id]
        resolucao_m = resolucoes[item.sensor_token]

        arr, _, _ = _ler_classe_array(item.tif_path)
        distribuicao = _distribuicao_classes(arr)
        pixels_validos_total = sum(distribuicao.values())

        for classe_id in CLASS_IDS:
            n_pixels = distribuicao[classe_id]
            area_m2 = float(n_pixels * resolucao_m * resolucao_m)
            pct_area_valida = (
                round(100.0 * n_pixels / pixels_validos_total, 4) if pixels_validos_total else 0.0
            )
            fator, faixa_serie = _fator_e_faixa(item.sensor, item.ano, classe_id, item.site_id, fator_sv20)
            linhas.append(
                {
                    "site_id": item.site_id,
                    "ano": item.ano,
                    "sensor": item.sensor,
                    "resolucao_m": resolucao_m,
                    "classe_id": classe_id,
                    "classe_nome": classes.ID_TO_SLUG[classe_id],
                    "area_m2": area_m2,
                    "area_ha": round(area_m2 / 10000.0, 6),
                    "pct_area_valida": pct_area_valida,
                    "pixels_validos": pixels_validos_total,
                    "fator_correcao_sensor": fator,
                    "modelo_versao": modelo_versao,
                    "gerado_em": gerado_em,
                    "tipo": "tratamento",  # SV-29 (grupo de controle) ainda não rodou
                    "pareado_com": "",
                    "tier": meta_site["tier"],
                    "precisao_coordenada": meta_site["precisao_coordenada"],
                    "faixa_serie": faixa_serie,
                }
            )

    df = pd.DataFrame(linhas, columns=COLUNAS_CSV)
    df = df.sort_values(["site_id", "ano", "sensor", "classe_id"]).reset_index(drop=True)
    return df


# --------------------------------------------------------------------------------------------
# Artefato 2 — classes_{site_id}_{ano}_{sensor}.geojson
# --------------------------------------------------------------------------------------------


def _vetorizar_classe(
    arr: np.ndarray, transform: Any, crs: Any
) -> tuple[gpd.GeoDataFrame, dict[int, dict[str, float]]]:
    """rasterio.features.shapes -> filtro de área (< 0.1 ha descartado) ANTES do dissolve -> um
    GeoDataFrame com 1 linha por classe presente (geometria dissolvida), na CRS nativa do raster
    (metros — EPSG:31983). Retorna também o log de descarte por classe
    (`{classe_id: {"n": int, "area_m2": float}}`).

    Filtrar ANTES do dissolve (não depois) é deliberado: o critério "polígono < 0.1 ha" precisa
    valer por mancha contígua original, não pelo resultado já fundido por classe — senão duas
    manchas minúsculas adjacentes de mesma classe poderiam sobreviver ao corte só por terem sido
    somadas antes do teste."""
    mask = arr != 0
    geoms_por_classe: dict[int, list[shapely.geometry.base.BaseGeometry]] = {c: [] for c in CLASS_IDS}
    descarte: dict[int, dict[str, float]] = {c: {"n": 0, "area_m2": 0.0} for c in CLASS_IDS}

    if mask.any():
        for geom_dict, valor in rasterio.features.shapes(arr, mask=mask, transform=transform):
            classe_id = int(valor)
            if classe_id not in CLASS_IDS:
                continue  # defensivo — não deveria ocorrer, arr só tem 0-5
            geom = shapely.geometry.shape(geom_dict)
            area_m2 = geom.area
            if area_m2 < AREA_MINIMA_POLIGONO_M2:
                descarte[classe_id]["n"] += 1
                descarte[classe_id]["area_m2"] += area_m2
                continue
            geoms_por_classe[classe_id].append(geom)

    registros = []
    for classe_id in CLASS_IDS:
        geoms = geoms_por_classe[classe_id]
        if not geoms:
            continue
        uniao = shapely.ops.unary_union(geoms)
        registros.append({"classe_id": classe_id, "geometry": uniao, "area_m2": uniao.area})

    if registros:
        gdf = gpd.GeoDataFrame(registros, geometry="geometry", crs=crs)
    else:
        gdf = gpd.GeoDataFrame(
            {"classe_id": pd.Series(dtype=int), "area_m2": pd.Series(dtype=float)},
            geometry=gpd.GeoSeries([], crs=crs),
            crs=crs,
        )
    return gdf, descarte


def gerar_geojson_por_item(
    item: ItemRaster, resolucao_m: int, out_dir: Path
) -> tuple[Path, list[dict[str, Any]]]:
    arr, crs, transform = _ler_classe_array(item.tif_path)
    gdf, descarte = _vetorizar_classe(arr, transform, crs)

    gdf["site_id"] = item.site_id
    gdf["ano"] = item.ano
    gdf["sensor"] = item.sensor
    gdf["resolucao_m"] = resolucao_m
    gdf["classe_nome"] = gdf["classe_id"].map(classes.ID_TO_SLUG) if len(gdf) else []
    gdf = gdf[["site_id", "ano", "sensor", "resolucao_m", "classe_id", "classe_nome", "area_m2", "geometry"]]
    gdf = gdf.sort_values("classe_id").reset_index(drop=True)

    gdf_4326 = gdf.to_crs("EPSG:4326") if len(gdf) else gdf.set_crs("EPSG:4326", allow_override=True)

    out_path = out_dir / f"classes_{item.site_id}_{item.ano}_{item.sensor}.geojson"
    out_dir.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()  # geopandas GeoJSON driver não sobrescreve por padrão
    gdf_4326.to_file(out_path, driver="GeoJSON")

    linhas_descarte = []
    for classe_id in CLASS_IDS:
        info = descarte[classe_id]
        if info["n"] == 0:
            continue
        linhas_descarte.append(
            {
                "site_id": item.site_id,
                "ano": item.ano,
                "sensor": item.sensor,
                "classe_id": classe_id,
                "classe_nome": classes.ID_TO_SLUG[classe_id],
                "n_poligonos_descartados": info["n"],
                "area_descartada_m2": round(info["area_m2"], 2),
                "area_descartada_ha": round(info["area_m2"] / 10000.0, 6),
            }
        )
    return out_path, linhas_descarte


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Output para a frente de Indicadores (SV-15) — CSV de área por classe + "
        "GeoJSON de polígonos, a partir dos rasters classificados de SV-14."
    )
    parser.add_argument(
        "--modelo-versao",
        required=True,
        help="versão do modelo cujos rasters classificados (SV-14) exportar, ex.: rf_v1.0 "
        "(tem que bater com o 'modelo_versao' já gravado nos manifests de "
        "data/manifests/classificado_*.json — este comando não roda inferência, só exporta "
        "o que já foi classificado).",
    )
    parser.add_argument(
        "--site", default=None, help="restringe a um site_id só (default: todos os sites com raster)."
    )
    parser.add_argument(
        "--token",
        default=TOKEN_PADRAO,
        help=f"prefixo dos manifests/rasters de classificação (default: {TOKEN_PADRAO!r}, a "
        "produção). Use o mesmo token que a inferência usou em --saida-token para exportar uma "
        "classificação alternativa, ex.: 'classificado-rf_v2.0-dw'.",
    )
    parser.add_argument(
        "--pular-geojson",
        action="store_true",
        help="gera só o CSV (artefato 1) — útil para iterar rápido; o GeoJSON (artefato 2) é "
        "vetorização por raster e é a parte mais lenta do comando.",
    )
    args = parser.parse_args(argv)

    gerado_em = datetime.now(UTC).isoformat()

    print(f"[export_indicadores] modelo_versao={args.modelo_versao} | token={args.token} | gerado_em={gerado_em}")

    sites_meta = carregar_metadados_sites()
    resolucoes = carregar_resolucoes()
    itens = localizar_rasters(args.modelo_versao, site_filtro=args.site, token=args.token)
    print(f"[export_indicadores] {len(itens)} rasters classificados encontrados para exportar.")

    fator_sv20 = carregar_fator_correcao_sv20(args.modelo_versao)
    if fator_sv20:
        resumo = {c: info["tratamento"] for c, info in fator_sv20.items()}
        print(f"[export_indicadores] fator de correção SV-20 carregado de {caminho_fator_correcao(args.modelo_versao)} — tratamento por classe: {resumo}")
    else:
        print(f"[export_indicadores] {caminho_fator_correcao(args.modelo_versao)} não encontrado — fator_correcao_sensor=1.0 em toda linha (rode `a validação de sensores` antes para propagar SV-20).")

    # --- Artefato 1 -----------------------------------------------------------------------
    df = gerar_area_por_classe(itens, sites_meta, resolucoes, args.modelo_versao, gerado_em, fator_sv20)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False)
    print(f"[export_indicadores] Artefato 1 escrito: {CSV_PATH} ({len(df)} linhas).")

    # Checagem de sanidade imediata (item 6 do enunciado — nunca publicar um CSV que falha o
    # próprio critério de aceite dele).
    somas_pct = df.groupby(["site_id", "ano", "sensor"])["pct_area_valida"].sum()
    fora_da_tolerancia = somas_pct[(somas_pct - 100.0).abs() > 0.01]
    if len(fora_da_tolerancia):
        raise ExportError(
            f"soma de pct_area_valida fora da tolerância (±0.01) em {len(fora_da_tolerancia)} "
            f"grupo(s) site x ano x sensor — ex.: {fora_da_tolerancia.head().to_dict()}"
        )

    # --- Artefato 2 -------------------------------------------------------------------------
    if not args.pular_geojson:
        todas_linhas_descarte: list[dict[str, Any]] = []
        for i, item in enumerate(itens, start=1):
            resolucao_m = resolucoes[item.sensor_token]
            out_path, linhas_descarte = gerar_geojson_por_item(item, resolucao_m, OUTPUTS_DIR)
            todas_linhas_descarte.extend(linhas_descarte)
            if i % 25 == 0 or i == len(itens):
                print(f"[export_indicadores] GeoJSON {i}/{len(itens)} — último: {out_path.name}")

        if todas_linhas_descarte:
            df_descarte = pd.DataFrame(todas_linhas_descarte)
            df_descarte = df_descarte.sort_values(["site_id", "ano", "sensor", "classe_id"]).reset_index(drop=True)
        else:
            df_descarte = pd.DataFrame(
                columns=[
                    "site_id", "ano", "sensor", "classe_id", "classe_nome",
                    "n_poligonos_descartados", "area_descartada_m2", "area_descartada_ha",
                ]
            )
        df_descarte.to_csv(DESCARTE_LOG_PATH, index=False)
        print(
            f"[export_indicadores] Artefato 2 escrito: {len(itens)} GeoJSON em {OUTPUTS_DIR} | "
            f"log de descarte: {DESCARTE_LOG_PATH} ({len(df_descarte)} linhas)."
        )
    else:
        print("[export_indicadores] --pular-geojson: artefato 2 não gerado nesta execução.")

    print("[export_indicadores] CONCLUÍDO.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
