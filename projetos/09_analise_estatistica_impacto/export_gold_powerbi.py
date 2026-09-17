"""Exporta as 5 tabelas gold pro dashboard Power BI (aba 1: efeito líquido; aba 2: por data
center, com imagens raw+classificada de cada ano, tratamento e controle).

Restrito aos 15 pares originais (Brasil), que agora têm imagem+classificação completas —
ver README/histórico desta sessão. Não toca em nenhum artefato do estudo já publicado
(`dados/gold/efeito_liquido/`) — lê de lá (dim_significancia), nunca escreve lá.

Saída: dados/gold/powerbi_export/
  - dim_facility.csv
  - fact_cobertura_solo_ano.csv
  - fact_imagens.csv           (imagem em base64 direto na célula — ver README da pasta)
  - fact_efeito_par_horizonte.csv
  - dim_significancia.csv

Uso:
    cd projetos/09_analise_estatistica_impacto
    python export_gold_powerbi.py
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from comum import calcula_deltas, calcula_efeito_liquido_por_par

import numpy as np
import pandas as pd
import rasterio

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    HAS_MPL = True
except ModuleNotFoundError:
    HAS_MPL = False

OUT_DIR = config.RAIZ_PROJETO / "dados" / "gold" / "powerbi_export"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BRONZE_DIR = config.RAIZ_PROJETO / "dados" / "bronze" / "imagens_satelite"
CLASSIFICADO_DIR = config.RAIZ_PROJETO / "dados" / "silver" / "classificado" / "rf_v1.0-tuned"

THUMB_PX = 150  # "não precisa ser com qualidade muito grande" — miniatura pequena, ~10-15 KB/imagem
JPEG_QUALIDADE = 65

CORES_CLASSE = {0: "#000000", 1: "#1B5E20", 2: "#8BC34A", 3: "#F5A623", 4: "#B03A2E", 5: "#1565C0"}
NOMES_CLASSE = {
    0: "nodata", 1: "vegetacao_densa", 2: "vegetacao_rala",
    3: "solo_exposto_obras", 4: "construida_urbana", 5: "agua",
}

SITE_ID_PARA_SENSOR = {
    # NOTA: consolidado_impacto_modelo.csv marca sensor="s2" pra estes 3 tratamentos, mas o
    # bronze real (pré-existente, não gerado nesta sessão) só existe sob a pasta "landsat" —
    # inconsistência já presente nos dados originais, não alterada aqui (só usada pra achar o
    # arquivo certo). Não há raster CLASSIFICADO pra nenhum dos 3 em nenhuma das duas pastas —
    # a miniatura "raw" entra, a "classificada" fica ausente (ver aviso no log de execução).
    "angonap-fortaleza": "landsat", "ascenty-hortolandia": "landsat", "ascenty-jundiai": "landsat",
    "ascenty-maracanau": "landsat", "ascenty-osasco": "landsat", "ascenty-paulinia": "landsat",
    "ascenty-sumare": "landsat", "ascenty-vinhedo": "landsat", "clickip-manaus": "landsat",
    "equinix-santana-parnaiba": "landsat", "everest-goiania": "landsat", "hostdime-joao-pessoa": "landsat",
    "scala-sgigsm01": "landsat", "scala-spoapa01": "landsat", "scala-tambore": "landsat",
    "ctrl-angonap-fortaleza-p01": "landsat", "ctrl-ascenty-hortolandia-p01": "landsat",
    "ctrl-ascenty-jundiai-p01": "landsat", "ctrl-ascenty-maracanau-p03": "landsat",
    "ctrl-ascenty-osasco-p01": "landsat", "ctrl-ascenty-paulinia-p02": "landsat",
    "ctrl-ascenty-sumare-p01": "landsat", "ctrl-ascenty-vinhedo-p02": "landsat",
    "ctrl-clickip-manaus-p01": "s2", "ctrl-equinix-santana-parnaiba-p01": "landsat",
    "ctrl-everest-goiania-p01": "landsat", "ctrl-hostdime-joao-pessoa-p01": "landsat",
    "ctrl-scala-sgigsm01-p01": "s2", "ctrl-scala-spoapa01-p01": "s2", "ctrl-scala-tambore-p01": "landsat",
}
SITES_15_PARES = list(SITE_ID_PARA_SENSOR.keys())


def _pasta_sensor(sensor_token: str) -> str:
    return "landsat" if sensor_token == "landsat" else "sentinel2"


# --------------------------------------------------------------------------------------------
# 1) dim_facility
# --------------------------------------------------------------------------------------------


def monta_dim_facility(df: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for site_id in SITES_15_PARES:
        sub = df[df["site_id"] == site_id]
        if sub.empty:
            print(f"AVISO: {site_id} não encontrado no consolidado — pulando na dim_facility.", file=sys.stderr)
            continue
        r = sub.iloc[0]
        tipo = r["tipo"]
        par_id = site_id if tipo == "tratamento" else r["pareado_com"]
        nome_bonito = site_id.replace("ctrl-", "").replace("-p0", " (controle ").replace("-", " ").title()
        if tipo == "controle":
            nome_bonito = nome_bonito.rsplit(" (Controle ", 1)[0] + " — área controle"
        linhas.append({
            "site_id": site_id, "par_id": par_id, "papel": tipo,
            "nome": nome_bonito, "pais": "BR",
            "municipio": r.get("municipio"), "uf": r.get("uf"),
            "lat": r.get("lat"), "lon": r.get("lon"), "buffer_km": r.get("buffer_km"),
            "ano_inicio_obra": r.get("ano_inicio_obra"), "ano_fim_obra": r.get("ano_fim_obra"),
            "tier": r.get("tier"), "bioma": r.get("bioma"), "regiao": r.get("regiao"),
            "qualidade_par": r.get("qualidade_par"), "l1_rf": r.get("l1_rf"),
            "dist_tratamento_controle_km": r.get("dist_tratamento_controle_km"),
            "mw_construido_total": r.get("mw_construido_total"),
            "whitespace_construido_sqm_total": r.get("whitespace_construido_sqm_total"),
            "sensor": r.get("sensor"), "modelo_versao": r.get("modelo_versao"),
        })
    return pd.DataFrame(linhas)


# --------------------------------------------------------------------------------------------
# 2) fact_cobertura_solo_ano (formato longo)
# --------------------------------------------------------------------------------------------


def monta_fact_cobertura_solo(df: pd.DataFrame) -> pd.DataFrame:
    sub = df[df["site_id"].isin(SITES_15_PARES)].copy()
    classes = ["vegetacao_densa", "vegetacao_rala", "solo_exposto_obras", "construida_urbana", "agua"]
    id_cols = ["site_id", "tipo", "pareado_com", "ano", "ano_relativo_ao_inicio_obra", "fase"]
    valor_cols = [f"prop_{c}" for c in classes]
    longo = sub[id_cols + valor_cols].melt(id_vars=id_cols, value_vars=valor_cols, var_name="classe", value_name="percentual")
    longo["classe"] = longo["classe"].str.replace("prop_", "", regex=False)
    longo["percentual"] = longo["percentual"] * 100
    longo = longo.rename(columns={"tipo": "papel"})
    return longo.sort_values(["site_id", "ano", "classe"]).reset_index(drop=True)


# --------------------------------------------------------------------------------------------
# 3) fact_imagens — a peça da imagem, base64 embutido
# --------------------------------------------------------------------------------------------


def _thumb_raw_base64(tif_path: Path) -> str | None:
    """RGB real (bandas red/green/blue), alongamento de contraste 2-98%, JPEG pequeno."""
    if not tif_path.exists():
        return None
    with rasterio.open(tif_path) as ds:
        arr = ds.read()
        bandas = list(ds.descriptions)
    idx = {b: i for i, b in enumerate(bandas)}
    nodata = -9999
    valido = arr[idx["red"]] != nodata
    rgb = np.stack([arr[idx["red"]], arr[idx["green"]], arr[idx["blue"]]], axis=-1).astype(np.float64) / 10000.0
    for c in range(3):
        canal = rgb[..., c]
        amostra = canal[valido]
        if amostra.size == 0:
            continue
        lo, hi = np.percentile(amostra, [2, 98])
        hi = max(hi, lo + 1e-6)
        rgb[..., c] = np.clip((canal - lo) / (hi - lo), 0, 1)
    rgb[~valido] = 1.0

    fig, ax = plt.subplots(figsize=(THUMB_PX / 100, THUMB_PX / 100), dpi=100)
    ax.imshow(rgb)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    buf = io.BytesIO()
    fig.savefig(buf, format="jpeg", dpi=100, pil_kwargs={"quality": JPEG_QUALIDADE})
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _thumb_classificada_base64(tif_path: Path) -> str | None:
    if not tif_path.exists():
        return None
    with rasterio.open(tif_path) as ds:
        arr = ds.read(1)
    cmap = ListedColormap([CORES_CLASSE[i] for i in sorted(CORES_CLASSE)])
    norm = BoundaryNorm([i - 0.5 for i in sorted(CORES_CLASSE)] + [5.5], cmap.N)

    fig, ax = plt.subplots(figsize=(THUMB_PX / 100, THUMB_PX / 100), dpi=100)
    ax.imshow(arr, cmap=cmap, norm=norm)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    buf = io.BytesIO()
    fig.savefig(buf, format="jpeg", dpi=100, pil_kwargs={"quality": JPEG_QUALIDADE})
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def monta_fact_imagens(df: pd.DataFrame) -> pd.DataFrame:
    if not HAS_MPL:
        raise SystemExit("matplotlib não instalado — necessário pra gerar as miniaturas.")

    linhas = []
    for site_id, sensor_token in SITE_ID_PARA_SENSOR.items():
        pasta_sensor = _pasta_sensor(sensor_token)
        bronze_site_dir = BRONZE_DIR / pasta_sensor / site_id
        if not bronze_site_dir.exists():
            print(f"AVISO: sem bronze pra {site_id}", file=sys.stderr)
            continue
        tipo = "tratamento" if not site_id.startswith("ctrl-") else "controle"
        anos = sorted(int(p.stem) for p in bronze_site_dir.glob("*.tif"))

        for ano in anos:
            raw_path = bronze_site_dir / f"{ano}.tif"
            classe_path = CLASSIFICADO_DIR / pasta_sensor / site_id / f"{ano}.tif"

            b64_raw = _thumb_raw_base64(raw_path)
            if b64_raw:
                linhas.append({"site_id": site_id, "papel": tipo, "ano": ano, "tipo_imagem": "raw",
                                "sensor": sensor_token, "largura_px": THUMB_PX,
                                "imagem_base64": "data:image/jpeg;base64," + b64_raw})

            b64_classe = _thumb_classificada_base64(classe_path)
            if b64_classe:
                linhas.append({"site_id": site_id, "papel": tipo, "ano": ano, "tipo_imagem": "classificada",
                                "sensor": sensor_token, "largura_px": THUMB_PX,
                                "imagem_base64": "data:image/jpeg;base64," + b64_classe})
            else:
                print(f"AVISO: sem raster classificado pra {site_id}/{ano} — só a raw entrou.", file=sys.stderr)

        print(f"{site_id}: {len(anos)} anos processados")

    return pd.DataFrame(linhas)


# --------------------------------------------------------------------------------------------
# 4) fact_efeito_par_horizonte (grão fino — reaproveita comum.py, não duplica)
# --------------------------------------------------------------------------------------------


def monta_fact_efeito(df: pd.DataFrame) -> pd.DataFrame:
    df2, _ = calcula_deltas(df.copy(), config.VARS_ALVO)
    efeito = calcula_efeito_liquido_por_par(df2, config.VARS_ALVO)
    return efeito.rename(columns={"par": "par_id", "variavel": "variavel", "horizonte": "horizonte"})


# --------------------------------------------------------------------------------------------
def main() -> None:
    print(f"Lendo {config.CONSOLIDADO_CSV.name}...")
    df = pd.read_csv(config.CONSOLIDADO_CSV)

    print("\n1) dim_facility...")
    dim_facility = monta_dim_facility(df)
    dim_facility.to_csv(OUT_DIR / "dim_facility.csv", index=False, encoding="utf-8-sig")
    print(f"   {len(dim_facility)} linhas -> dim_facility.csv")

    print("\n2) fact_cobertura_solo_ano...")
    fact_cobertura = monta_fact_cobertura_solo(df)
    fact_cobertura.to_csv(OUT_DIR / "fact_cobertura_solo_ano.csv", index=False, encoding="utf-8-sig")
    print(f"   {len(fact_cobertura)} linhas -> fact_cobertura_solo_ano.csv")

    print("\n3) fact_imagens (pode demorar alguns minutos)...")
    fact_imagens = monta_fact_imagens(df)
    fact_imagens.to_csv(OUT_DIR / "fact_imagens.csv", index=False, encoding="utf-8-sig")
    tamanho_mb = (OUT_DIR / "fact_imagens.csv").stat().st_size / (1024 * 1024)
    print(f"   {len(fact_imagens)} linhas -> fact_imagens.csv ({tamanho_mb:.1f} MB)")

    print("\n4) fact_efeito_par_horizonte...")
    fact_efeito = monta_fact_efeito(df)
    fact_efeito.to_csv(OUT_DIR / "fact_efeito_par_horizonte.csv", index=False, encoding="utf-8-sig")
    print(f"   {len(fact_efeito)} linhas -> fact_efeito_par_horizonte.csv")

    print("\n5) dim_significancia (copiado do estudo já publicado, não recalculado)...")
    origem_sig = config.OUTPUT_DIR / config.CONSEQUENCIAS_RESUMO_CSV_NAME
    if origem_sig.exists():
        sig = pd.read_csv(origem_sig)
        sig.to_csv(OUT_DIR / "dim_significancia.csv", index=False, encoding="utf-8-sig")
        print(f"   {len(sig)} linhas -> dim_significancia.csv (fonte: {origem_sig})")
    else:
        print(f"   AVISO: {origem_sig} não existe — rode step1b_analise_consequencias.py antes.")

    print(f"\nTudo salvo em {OUT_DIR}")


if __name__ == "__main__":
    main()
