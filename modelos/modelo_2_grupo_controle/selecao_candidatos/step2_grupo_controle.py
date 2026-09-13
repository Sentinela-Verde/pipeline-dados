"""Step 2 — monta os pontos de controle ao redor do município similar de cada data center.

Para cada data center filtrado (`data/silver/datacenter_filtrado.csv`):
1. Acha o município similar (`id_municipio_similar_1`, gerado pelo step1).
2. Calcula distância e azimute entre o município do data center e o data center em si.
3. Aplica essa mesma distância a partir do município similar, em 6 direções (a cada 60°),
   gerando 6 pontos candidatos a grupo de controle — a ideia é comparar o data center com
   áreas que ficam tão longe do "centro" de uma cidade parecida quanto ele fica da sua.

Uso:
    python step2_grupo_controle.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

import numpy as np
import pandas as pd


def calcular_distancia_e_inclinacao(lat_cidade, lon_cidade, lat_dc, lon_dc):
    """Calcula distância (km, Haversine) e inclinação/azimute (0-360°, Norte = 0°)
    entre dois pontos."""
    if pd.isna(lat_cidade) or pd.isna(lon_cidade) or pd.isna(lat_dc) or pd.isna(lon_dc):
        return None, None

    phi1, phi2 = math.radians(lat_cidade), math.radians(lat_dc)
    d_phi = math.radians(lat_dc - lat_cidade)
    d_lam = math.radians(lon_dc - lon_cidade)

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


def carrega_datacenters():
    datacenter = pd.read_csv(config.DATACENTER_FILTRADO_CSV, sep=";", encoding="utf-8-sig")
    datacenter["cidade"] = datacenter["cidade"].map(config.MAPA_NOMES_CIDADE).fillna(datacenter["cidade"])
    return datacenter


def carrega_municipios_similares():
    df_similar = pd.read_csv(config.MUNICIPIOS_SIMILARES_CSV)
    return df_similar[["nome_municipio", "id_municipio", "id_municipio_similar_1"]]


def carrega_lat_long_municipios():
    municipios = pd.read_csv(config.IBGE_CSV)
    return (
        municipios[["nome_municipio", "id_municipio", "latitude", "longitude"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )


def monta_coordenadas(datacenter, df_similar, municipios):
    df = datacenter.merge(df_similar, left_on="cidade", right_on="nome_municipio", how="left")
    df = df.merge(municipios, on="id_municipio", how="left", suffixes=("", "_origem"))
    df = df.merge(
        municipios, left_on="id_municipio_similar_1", right_on="id_municipio",
        how="left", suffixes=("", "_similar"),
    )
    df = df.rename(columns={
        "latitude": "latitude_datacenter", "longitude": "longitude_datacenter",
        "latitude_origem": "latitude_municipio", "longitude_origem": "longitude_municipio",
    })

    colunas = [
        "nome_datacenter", "latitude_datacenter", "longitude_datacenter",
        "latitude_municipio", "longitude_municipio", "latitude_similar", "longitude_similar",
    ]
    return df[colunas].copy()


def main():
    datacenter = carrega_datacenters()
    df_similar = carrega_municipios_similares()
    municipios = carrega_lat_long_municipios()

    coordenadas = monta_coordenadas(datacenter, df_similar, municipios)

    coordenadas[["distancia_km", "inclinacao_graus"]] = coordenadas.apply(
        lambda row: pd.Series(calcular_distancia_e_inclinacao(
            row["latitude_municipio"], row["longitude_municipio"],
            row["latitude_datacenter"], row["longitude_datacenter"],
        )),
        axis=1,
    )

    novas_linhas = []
    for _, row in coordenadas.iterrows():
        pontos_gerados = calcular_pontos_em_volta(
            lat_origem=row["latitude_similar"],
            lon_origem=row["longitude_similar"],
            distancia_km=row["distancia_km"],
            inclinacao_inicial=config.INCLINACAO_INICIAL_GRAUS,
        )
        for ponto in pontos_gerados:
            dados_linha = row.to_dict()
            dados_linha.update(ponto)
            novas_linhas.append(dados_linha)

    df_expandido = pd.DataFrame(novas_linhas)
    print(f"{coordenadas['nome_datacenter'].nunique()} data centers x "
          f"{config.N_PONTOS_CONTROLE} pontos = {len(df_expandido)} linhas")

    df_expandido.to_csv(config.PONTOS_EXPANDIDOS_CSV, sep=";", index=False, encoding="utf-8-sig")
    print(f"Salvo em {config.PONTOS_EXPANDIDOS_CSV}")


if __name__ == "__main__":
    main()
