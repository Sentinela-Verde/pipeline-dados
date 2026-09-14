"""Step 2 — monta os pontos candidatos a grupo de controle ao redor das cidades mais similares
de cada AOI (área de estudo, `dados/silver/datacenter_filtrado.csv` — 1 linha por AOI, não mais
por facility, ver `projetos/01_coleta_datacenter/filtro_elegibilidade/step9_consolida_aoi.py`).

Para cada AOI:
1. Acha o município da AOI e as `config.N_SIMILARES_PARA_CONTROLE` (2) cidades mais similares
   a ele (`id_municipio_similar_1`, `id_municipio_similar_2`, geradas pelo step1).
2. Calcula distância e azimute entre o município da AOI e a AOI em si (o data center) — o quão
   longe e em que direção o data center fica do "centro" da sua cidade.
3. Aplica essa MESMA distância e um leque de `config.N_PONTOS_CONTROLE` (6) direções ao redor de
   CADA uma das 2 cidades similares — 2 × 6 = 12 pontos candidatos por AOI.

Antes (versão original, pré-2026-09-14) usava só a cidade mais similar (rank 1), gerando 6 pontos
por data center/facility. A mudança pra 2 cidades × 6 pontos dá margem de escolha maior — e reduz
o risco de todo o grupo de controle de uma AOI depender de uma coincidência de layout de uma única
cidade "parecida no papel" (ex.: um rio ou rodovia bem no meio dela).

Uso:
    python step2_grupo_controle.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

import pandas as pd


def calcular_distancia_e_inclinacao(lat_cidade, lon_cidade, lat_aoi, lon_aoi):
    """Calcula distância (km, Haversine) e inclinação/azimute (0-360°, Norte = 0°)
    entre o centro do município e a AOI (o data center)."""
    if pd.isna(lat_cidade) or pd.isna(lon_cidade) or pd.isna(lat_aoi) or pd.isna(lon_aoi):
        return None, None

    phi1, phi2 = math.radians(lat_cidade), math.radians(lat_aoi)
    d_phi = math.radians(lat_aoi - lat_cidade)
    d_lam = math.radians(lon_aoi - lon_cidade)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    distancia_km = 6371.0 * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

    y = math.sin(d_lam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lam)
    inclinacao_graus = (math.degrees(math.atan2(y, x)) + 360) % 360

    return round(distancia_km, 2), round(inclinacao_graus, 2)


def calcular_pontos_em_volta(lat_origem, lon_origem, distancia_km, inclinacao_inicial=0.0,
                              n_pontos=config.N_PONTOS_CONTROLE):
    """Gera `n_pontos` em círculo ao redor da origem, espaçados em 360/n_pontos graus."""
    if pd.isna(lat_origem) or pd.isna(lon_origem) or pd.isna(distancia_km):
        return []

    RAIO_TERRA_KM = 6371.0
    passo_graus = 360.0 / n_pontos
    pontos = []

    lat1 = math.radians(lat_origem)
    lon1 = math.radians(lon_origem)
    d_r = distancia_km / RAIO_TERRA_KM

    for i in range(n_pontos):
        azimute_graus = (inclinacao_inicial + (i * passo_graus)) % 360.0
        azimute = math.radians(azimute_graus)

        lat2 = math.asin(
            math.sin(lat1) * math.cos(d_r) + math.cos(lat1) * math.sin(d_r) * math.cos(azimute)
        )
        lon2 = lon1 + math.atan2(
            math.sin(azimute) * math.sin(d_r) * math.cos(lat1),
            math.cos(d_r) - math.sin(lat1) * math.sin(lat2),
        )

        pontos.append({
            "ponto_num": i + 1,
            "ponto_inclinacao_graus": round(azimute_graus, 2),
            "ponto_latitude": round(math.degrees(lat2), 6),
            "ponto_longitude": round(math.degrees(lon2), 6),
        })

    return pontos


def carrega_aois() -> pd.DataFrame:
    """`dados/silver/datacenter_filtrado.csv` — 1 linha por AOI (aoi_id), pós step9."""
    df = pd.read_csv(config.DATACENTER_FILTRADO_CSV, sep=";", encoding="utf-8-sig")
    df["cidade"] = df["cidade"].map(config.MAPA_NOMES_CIDADE).fillna(df["cidade"])
    return df[["aoi_id", "operadora", "cidade", "latitude", "longitude"]].copy()


def carrega_municipios_similares() -> pd.DataFrame:
    df_similar = pd.read_csv(config.MUNICIPIOS_SIMILARES_CSV)
    colunas = ["nome_municipio", "id_municipio"]
    for rank in range(1, config.N_SIMILARES_PARA_CONTROLE + 1):
        colunas += [f"id_municipio_similar_{rank}", f"municipio_similar_{rank}"]
    faltando = [c for c in colunas if c not in df_similar.columns]
    if faltando:
        raise SystemExit(
            f"{config.MUNICIPIOS_SIMILARES_CSV} não tem a(s) coluna(s) {faltando} — rode "
            f"step1_cidades_similares.py com config.N_SIMILARES >= "
            f"{config.N_SIMILARES_PARA_CONTROLE} antes."
        )
    return df_similar[colunas]


def carrega_lat_long_municipios() -> pd.DataFrame:
    municipios = pd.read_csv(config.IBGE_CSV)
    return (
        municipios[["nome_municipio", "id_municipio", "latitude", "longitude"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _desambigua_por_proximidade(aois: pd.DataFrame, municipios: pd.DataFrame) -> pd.DataFrame:
    """`nome_municipio` sozinho não é chave única no Brasil — ex.: existe 'Palmas' em TO (capital)
    E em PR. Casar só por nome geraria 2 municípios por AOI nesse caso (candidatos em dobro,
    inclusive alguns a milhares de km da AOI de verdade). Desambigua escolhendo, para cada AOI, o
    `id_municipio` cujo (latitude, longitude) do IBGE fica mais perto da própria AOI — a AOI já tem
    coordenada confiável (geocodificada em `correcao_endereco/`), então "município mais perto do
    ponto" é um desempate mais robusto que assumir que o primeiro nome batido está certo."""
    candidatos = aois[["aoi_id", "cidade", "latitude", "longitude"]].merge(
        municipios, left_on="cidade", right_on="nome_municipio", how="left"
    )
    ambiguos = candidatos.groupby("aoi_id").filter(lambda g: len(g) > 1)
    if len(ambiguos):
        for aoi_id, grupo in ambiguos.groupby("aoi_id"):
            ufs = ", ".join(f"{r.nome_municipio}/{r.id_municipio}" for r in grupo.itertuples())
            print(
                f"AVISO: '{grupo.iloc[0]['cidade']}' (AOI {aoi_id}) casa com {len(grupo)} "
                f"municípios de mesmo nome no IBGE ({ufs}) — desambiguado pelo mais próximo da AOI.",
                file=sys.stderr,
            )

    candidatos["_dist_km"] = candidatos.apply(
        lambda r: _haversine_km(r["latitude_x"], r["longitude_x"], r["latitude_y"], r["longitude_y"])
        if pd.notna(r.get("latitude_y")) else float("inf"),
        axis=1,
    )
    escolhidos = candidatos.sort_values("_dist_km").groupby("aoi_id", as_index=False).first()
    return escolhidos[["aoi_id", "id_municipio"]]


def monta_base(aois: pd.DataFrame, df_similar: pd.DataFrame, municipios: pd.DataFrame) -> pd.DataFrame:
    """1 linha por AOI, com lat/lon da AOI, lat/lon do MUNICÍPIO DA AOI, e o
    id/nome de cada uma das `N_SIMILARES_PARA_CONTROLE` cidades similares (sem lat/lon delas
    ainda — isso é resolvido por rank em `expande_por_similar`, pra não colidir nomes de coluna)."""
    id_municipio_por_aoi = _desambigua_por_proximidade(aois, municipios)

    df = aois.merge(id_municipio_por_aoi, on="aoi_id", how="left")
    df = df.merge(df_similar, on="id_municipio", how="left")

    sem_match = df[df["id_municipio"].isna()]
    if len(sem_match):
        raise SystemExit(
            f"{len(sem_match)} AOI(s) sem cidade correspondente em "
            f"{config.MUNICIPIOS_SIMILARES_CSV.name}: "
            f"{sem_match[['aoi_id', 'cidade']].to_dict('records')} — confira "
            f"config.MAPA_NOMES_CIDADE."
        )

    df = df.merge(
        municipios.rename(columns={"latitude": "latitude_municipio", "longitude": "longitude_municipio"}),
        on="id_municipio", how="left",
    )
    df = df.rename(columns={"latitude": "latitude_aoi", "longitude": "longitude_aoi"})
    return df


def main():
    aois = carrega_aois()
    df_similar = carrega_municipios_similares()
    municipios = carrega_lat_long_municipios()

    base = monta_base(aois, df_similar, municipios)

    base[["distancia_km", "inclinacao_graus"]] = base.apply(
        lambda row: pd.Series(calcular_distancia_e_inclinacao(
            row["latitude_municipio"], row["longitude_municipio"],
            row["latitude_aoi"], row["longitude_aoi"],
        )),
        axis=1,
    )

    novas_linhas = []
    for _, row in base.iterrows():
        for rank in range(1, config.N_SIMILARES_PARA_CONTROLE + 1):
            id_similar = row.get(f"id_municipio_similar_{rank}")
            if pd.isna(id_similar):
                continue
            m_similar = municipios.loc[municipios["id_municipio"] == id_similar]
            if m_similar.empty:
                continue
            lat_similar = m_similar.iloc[0]["latitude"]
            lon_similar = m_similar.iloc[0]["longitude"]

            pontos_gerados = calcular_pontos_em_volta(
                lat_origem=lat_similar,
                lon_origem=lon_similar,
                distancia_km=row["distancia_km"],
                inclinacao_inicial=config.INCLINACAO_INICIAL_GRAUS,
            )
            for ponto in pontos_gerados:
                novas_linhas.append({
                    "aoi_id": row["aoi_id"],
                    "operadora": row["operadora"],
                    "cidade": row["cidade"],
                    "latitude_aoi": row["latitude_aoi"],
                    "longitude_aoi": row["longitude_aoi"],
                    "latitude_municipio": row["latitude_municipio"],
                    "longitude_municipio": row["longitude_municipio"],
                    "distancia_km": row["distancia_km"],
                    "inclinacao_graus": row["inclinacao_graus"],
                    "similar_rank": rank,
                    "id_municipio_similar": int(id_similar),
                    "municipio_similar": row[f"municipio_similar_{rank}"],
                    "latitude_similar": lat_similar,
                    "longitude_similar": lon_similar,
                    **ponto,
                })

    df_candidatos = pd.DataFrame(novas_linhas)
    df_candidatos["candidato_id"] = (
        df_candidatos["aoi_id"] + "_sim" + df_candidatos["similar_rank"].astype(str)
        + "_p" + df_candidatos["ponto_num"].astype(str)
    )

    n_aois = df_candidatos["aoi_id"].nunique()
    esperado = n_aois * config.N_SIMILARES_PARA_CONTROLE * config.N_PONTOS_CONTROLE
    print(
        f"{n_aois} AOIs x {config.N_SIMILARES_PARA_CONTROLE} cidades similares x "
        f"{config.N_PONTOS_CONTROLE} pontos = {len(df_candidatos)} candidatos "
        f"(esperado: {esperado})"
    )
    if len(df_candidatos) != esperado:
        print(
            f"AVISO: {esperado - len(df_candidatos)} candidato(s) a menos que o esperado — "
            f"provavelmente alguma cidade similar não tinha lat/lon no IBGE.",
            file=sys.stderr,
        )

    df_candidatos.to_csv(config.CANDIDATOS_GRUPO_CONTROLE_CSV, sep=";", index=False, encoding="utf-8-sig")
    print(f"Salvo em {config.CANDIDATOS_GRUPO_CONTROLE_CSV}")


if __name__ == "__main__":
    main()
