"""Modelo 1 — inferência: stack de 13 bandas (etapa 4) -> raster classificado + % de classe.

Porta pra `pipeline-dados` da lógica de `modelo-imagens-satelite/src/sentinela/predict.py`
(contrato de features por NOME, nunca por posição) e de
`modelo-imagens-satelite/modelo-impacto/scripts/impacto_dc_comum.py` (`area_por_classe`,
`distancia_l1` — usadas por `modelos/modelo_2_grupo_controle/` pra escolher o controle mais
parecido com o tratamento no período pré-obra). Simplificada pra não usar janelas de leitura
(`rasterio.windows`): as AOIs deste repo (buffer 5 km) cabem inteiras em memória (~333x333 px em
Landsat), diferente do outro repo que também processa AOIs maiores.

5 classes (0=nodata, 1=vegetação densa, 2=vegetação rala, 3=solo exposto/obras, 4=área
construída/urbana, 5=água) — mesmo esquema de `projetos/03_extracao_labels/parametros/classes.yml`,
harcodado aqui (não importado de lá) pela mesma razão de `impacto_dc_comum.py`: é a MESMA decisão
fechada do time, só não vale a pena um import cross-etapa por 5 constantes.

Uso:
    python inferencia/classifica.py --sensor landsat --site <id|all> --ano <ano|all>
        [--saida-csv <caminho>] [--force]

Esta etapa nunca toca no bronze — só lê `dados/silver/features/{sensor}/{site_id}/{ano}.tif`
(saída de `04_indices_espectrais`, que já leu do bronze e resolveu subpasta lá). `--site`/`--ano`
'all' descobrem os itens varrendo o que já existe em silver/features, então cobrem tanto os 21
AOIs de tratamento quanto os candidatos a grupo de controle automaticamente — os dois vivem no
mesmo namespace de `site_id` (unicidade garantida por `aoi_id`/`candidato_id`), sem precisar de
subpasta separada aqui.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import SETTINGS, MODELO_VERSAO

CLASS_IDS: tuple[int, ...] = (1, 2, 3, 4, 5)
CLASSE_NOME: dict[int, str] = {
    1: "vegetacao_densa",
    2: "vegetacao_rala",
    3: "solo_exposto_obras",
    4: "construida_urbana",
    5: "agua",
}
SENSOR_FEATURE_COL = "sensor_landsat"  # feature DERIVADA (1.0 landsat / 0.0 sentinel2), não é banda


class ClassificaError(RuntimeError):
    """Contrato de features quebrado, artefato ausente, etc — nunca prossegue com o que der."""


# --------------------------------------------------------------------------------------------
# Modelo
# --------------------------------------------------------------------------------------------


def carregar_modelo(caminho: Path) -> dict[str, Any]:
    if not caminho.exists():
        raise ClassificaError(f"modelo ausente: {caminho}")
    pacote = joblib.load(caminho)
    for chave in ("modelo", "lista_features"):
        if chave not in pacote:
            raise ClassificaError(f"pacote do modelo {caminho} não tem a chave obrigatória '{chave}'")
    return pacote


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_arquivo(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------------------------
# Caminhos
# --------------------------------------------------------------------------------------------


def _caminho_features(sensor_token: str, site_id: str, ano: int) -> Path:
    return SETTINGS.silver_features_dir(sensor_token) / site_id / f"{ano}.tif"


def _caminho_manifest_features(sensor_token: str, site_id: str, ano: int) -> Path:
    return SETTINGS.manifests_dir / f"features_{sensor_token}_{site_id}_{ano}.json"


def _caminho_saida(sensor_token: str, site_id: str, ano: int) -> Path:
    return SETTINGS.classificado_dir(sensor_token) / site_id / f"{ano}.tif"


def _caminho_saida_confianca(sensor_token: str, site_id: str, ano: int) -> Path:
    return SETTINGS.classificado_dir(sensor_token) / site_id / f"{ano}_confianca.tif"


def _caminho_manifest_saida(sensor_token: str, site_id: str, ano: int) -> Path:
    return SETTINGS.manifests_dir / f"classificado_{MODELO_VERSAO}_{sensor_token}_{site_id}_{ano}.json"


# --------------------------------------------------------------------------------------------
# Classificação de 1 site/ano — contrato de features por NOME (nunca por posição)
# --------------------------------------------------------------------------------------------


def _validar_contrato_bandas(bandas_raster: list[str], lista_features: list[str]) -> None:
    disponiveis = set(bandas_raster)
    faltando = [f for f in lista_features if f != SENSOR_FEATURE_COL and f not in disponiveis]
    if faltando:
        raise ClassificaError(
            f"banda(s) exigida(s) pelo modelo ausente(s) no raster de features: {faltando} "
            f"(bandas disponíveis: {bandas_raster})."
        )


def classificar_site_ano(
    sensor_token: str, site_id: str, ano: int, pacote: dict[str, Any], *, force: bool = False
) -> dict[str, Any]:
    """Classifica 1 stack de features inteiro (sem janelas — AOIs cabem em memória). Idempotente:
    pula se já existe e o sha256 do modelo bate (mesmo padrão de `04_indices_espectrais`)."""
    feat_path = _caminho_features(sensor_token, site_id, ano)
    feat_manifest_path = _caminho_manifest_features(sensor_token, site_id, ano)
    out_tif = _caminho_saida(sensor_token, site_id, ano)
    out_confianca = _caminho_saida_confianca(sensor_token, site_id, ano)
    out_manifest_path = _caminho_manifest_saida(sensor_token, site_id, ano)

    modelo_sha256 = _sha256_arquivo(SETTINGS.modelo_path)

    if not force and out_manifest_path.exists() and out_tif.exists():
        manifest_existente = json.loads(out_manifest_path.read_text(encoding="utf-8"))
        if manifest_existente.get("modelo_sha256") == modelo_sha256:
            manifest_existente["_pulado"] = True
            return manifest_existente

    if not feat_path.exists():
        raise ClassificaError(f"{feat_path} não existe — rode 04_indices_espectrais antes.")
    if not feat_manifest_path.exists():
        raise ClassificaError(f"{feat_manifest_path} não existe.")

    feat_manifest = json.loads(feat_manifest_path.read_text(encoding="utf-8"))
    lista_features: list[str] = pacote["lista_features"]
    fator_escala = feat_manifest.get("fator_escala")
    valor_sensor = 1.0 if sensor_token == "landsat" else 0.0

    with rasterio.open(feat_path) as src:
        descricoes = list(src.descriptions)
        bandas_raster = descricoes if all(descricoes) else list(feat_manifest["bandas"])
        _validar_contrato_bandas(bandas_raster, lista_features)
        idx_por_nome = {nome: i for i, nome in enumerate(bandas_raster)}

        stack = src.read()  # (n_bandas, H, W)
        nodata_raw = src.nodata if src.nodata is not None else feat_manifest.get("nodata", -9999)
        crs, transform = src.crs, src.transform
        height, width = src.height, src.width

    invalido = np.any(stack == nodata_raw, axis=0)
    aplicar_escala = fator_escala is not None and np.issubdtype(stack.dtype, np.integer)

    colunas = []
    for nome in lista_features:
        if nome == SENSOR_FEATURE_COL:
            colunas.append(np.full((height, width), valor_sensor, dtype=np.float32))
        else:
            banda = stack[idx_por_nome[nome]].astype(np.float32)
            if aplicar_escala:
                banda = banda / np.float32(fator_escala)
            colunas.append(banda)
    X_full = np.stack(colunas, axis=-1)  # (H, W, n_features)

    classe_full = np.zeros((height, width), dtype=np.uint8)
    confianca_full = np.zeros((height, width), dtype=np.uint8)
    validos_mask = ~invalido
    n_validos = int(validos_mask.sum())

    if n_validos > 0:
        X_validos = X_full[validos_mask]
        modelo = pacote["modelo"]
        pred = modelo.predict(X_validos)
        proba = modelo.predict_proba(X_validos)
        conf = np.clip(np.round(proba.max(axis=1) * 100.0), 0, 100).astype(np.uint8)
        classe_full[validos_mask] = pred.astype(np.uint8)
        confianca_full[validos_mask] = conf

    # --------------------------------------------------------------------------------------
    # Escrita (classe uint8, nodata=0; confiança uint8, nodata=0)
    # --------------------------------------------------------------------------------------
    out_tif.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff", "dtype": "uint8", "nodata": 0,
        "width": width, "height": height, "count": 1,
        "crs": crs, "transform": transform, "compress": "LZW",
    }
    with rasterio.open(out_tif, "w", **profile) as dst:
        dst.write(classe_full[np.newaxis, :, :])
    with rasterio.open(out_confianca, "w", **profile) as dst:
        dst.write(confianca_full[np.newaxis, :, :])

    # --------------------------------------------------------------------------------------
    # Área/proporção por classe + manifest (mesma conta de impacto_dc_comum.area_por_classe)
    # --------------------------------------------------------------------------------------
    resolucao_m = int(feat_manifest.get("resolucao_m", 30))
    valores, contagens = np.unique(classe_full, return_counts=True)
    contagem = dict(zip(valores.tolist(), contagens.tolist(), strict=True))
    pixels = {cid: int(contagem.get(cid, 0)) for cid in CLASS_IDS}
    total = sum(pixels.values())

    proporcoes = {}
    for cid in CLASS_IDS:
        area_ha = pixels[cid] * resolucao_m * resolucao_m / 10_000.0
        proporcoes[f"area_ha_{CLASSE_NOME[cid]}"] = round(area_ha, 4)
        proporcoes[f"prop_{CLASSE_NOME[cid]}"] = round(pixels[cid] / total, 6) if total else 0.0

    manifest = {
        "site_id": site_id, "ano": ano, "sensor": sensor_token,
        "modelo_versao": MODELO_VERSAO, "modelo_sha256": modelo_sha256,
        "lista_features": lista_features,
        "crs": str(crs), "shape": {"width": width, "height": height},
        "resolucao_m": resolucao_m,
        "pixels_validos": total,
        "pct_pixels_validos": round(100.0 * total / classe_full.size, 4) if classe_full.size else 0.0,
        **proporcoes,
        "sha256_classe": _sha256_bytes(classe_full.tobytes()),
        "gerado_em": datetime.now(UTC).isoformat(),
        "tif": str(out_tif),
        "tif_confianca": str(out_confianca),
    }
    out_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    out_manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest["_pulado"] = False
    return manifest


# --------------------------------------------------------------------------------------------
# Descoberta de (sensor, site_id, ano) já processados por 04_indices_espectrais
# --------------------------------------------------------------------------------------------


def _descobrir_itens(sensor_token: str, site_filtro: str | None) -> list[tuple[str, int]]:
    base = SETTINGS.silver_features_dir(sensor_token)
    if not base.exists():
        return []
    itens = []
    for site_dir in sorted(base.iterdir()):
        if not site_dir.is_dir():
            continue
        if site_filtro and site_dir.name != site_filtro:
            continue
        for tif in sorted(site_dir.glob("*.tif")):
            itens.append((site_dir.name, int(tif.stem)))
    return itens


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classificação de cobertura do solo (modelo 1).")
    parser.add_argument("--sensor", required=True, choices=["s2", "landsat", "all"])
    parser.add_argument("--site", default="all", help="site_id, ou 'all' (todo mundo em silver/features)")
    parser.add_argument("--ano", default="all", help="ano, ou 'all'")
    parser.add_argument("--saida-csv", default=None, help="caminho do CSV agregado de percentuais (opcional)")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    print(f"Carregando modelo {SETTINGS.modelo_path.name}...")
    pacote = carregar_modelo(SETTINGS.modelo_path)
    print(f"lista_features ({len(pacote['lista_features'])}): {pacote['lista_features']}")

    sensores = ["s2", "landsat"] if args.sensor == "all" else [args.sensor]
    site_filtro = None if args.site == "all" else args.site

    linhas = []
    ok = falha = pulado = 0
    for sensor_token in sensores:
        itens = _descobrir_itens(sensor_token, site_filtro)
        if args.ano != "all":
            itens = [(s, a) for s, a in itens if a == int(args.ano)]
        for site_id, ano in itens:
            try:
                m = classificar_site_ano(sensor_token, site_id, ano, pacote, force=args.force)
                if m.get("_pulado"):
                    pulado += 1
                else:
                    ok += 1
                linha = {"sensor": sensor_token, "site_id": site_id, "ano": ano}
                for cid in CLASS_IDS:
                    linha[f"prop_{CLASSE_NOME[cid]}"] = m[f"prop_{CLASSE_NOME[cid]}"]
                linha["pct_pixels_validos"] = m["pct_pixels_validos"]
                linhas.append(linha)
                print(f"[{sensor_token}/{site_id}/{ano}] OK — pct_validos={m['pct_pixels_validos']:.1f}%")
            except Exception as e:  # noqa: BLE001 - 1 item ruim não pode abortar o lote
                falha += 1
                print(f"ERRO [{sensor_token}/{site_id}/{ano}]: {e}", file=sys.stderr)

    print(f"\nConcluído: {ok} OK, {pulado} pulado(s), {falha} falha(s).")

    if args.saida_csv and linhas:
        df = pd.DataFrame(linhas)
        out_path = Path(args.saida_csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, sep=";", index=False, encoding="utf-8-sig")
        print(f"CSV agregado salvo em {out_path} ({len(df)} linhas)")

    return 1 if falha else 0


if __name__ == "__main__":
    sys.exit(main())
