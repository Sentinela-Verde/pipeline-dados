"""
Gera um HTML com um mapa de satélite mostrando, para cada datacenter:
  - o ponto do datacenter
  - o ponto do município onde ele está
  - o ponto de controle (município similar), em latitude_similar/longitude_similar
  - os N pontos de referência ao redor do ponto de controle (gerados pelo step2)

Ao passar o mouse em cada ponto, aparece o nome do data center, a cidade
associada e a lista dos pontos de referência.

Também desenha, sobre o datacenter e sobre cada ponto de referência, um
quadrado de `config.LADO_QUADRADO_KM` x `config.LADO_QUADRADO_KM` preenchido
com transparência (representando a área de amostragem ao redor de cada ponto).

Uso:
    python gerar_mapa_pontos_datacenter.py

Precisa que step2_grupo_controle.py já tenha rodado (gera o CSV de pontos).
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

import folium
import pandas as pd


def bounds_quadrado(lat, lon, lado_km):
    """Retorna os cantos [sudoeste, nordeste] de um quadrado de `lado_km` x `lado_km`
    centrado em (lat, lon), respeitando a distorção da longitude pela latitude."""
    meia_lado = lado_km / 2
    delta_lat = meia_lado / config.KM_POR_GRAU_LAT
    delta_lon = meia_lado / (config.KM_POR_GRAU_LAT * math.cos(math.radians(lat)))
    return [[lat - delta_lat, lon - delta_lon], [lat + delta_lat, lon + delta_lon]]


PALETA = [
    "#ff5252", "#40c4ff", "#69f0ae", "#ffd740", "#e040fb", "#ff6e40",
    "#18ffff", "#b2ff59", "#ff4081", "#eeff41", "#7c4dff", "#00e676",
]


def main():
    df = pd.read_csv(config.PONTOS_EXPANDIDOS_CSV, sep=";")

    df_dc = pd.read_csv(
        config.DATACENTER_FILTRADO_CSV, sep=";",
        usecols=["nome_datacenter", "cidade"],
    )
    df = df.merge(df_dc, on="nome_datacenter", how="left")

    lat_centro = df["latitude_datacenter"].mean()
    lon_centro = df["longitude_datacenter"].mean()

    m = folium.Map(location=[lat_centro, lon_centro], zoom_start=6, tiles=None, control_scale=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Satélite", overlay=False, control=False,
    ).add_to(m)

    for i, (nome_dc, grupo) in enumerate(df.groupby("nome_datacenter")):
        cor = PALETA[i % len(PALETA)]
        grupo = grupo.sort_values("ponto_num")
        row0 = grupo.iloc[0]

        cidade = row0["cidade"] if pd.notna(row0.get("cidade")) else "cidade não identificada"

        pontos_html = "".join(
            f"<li>Ponto {int(r.ponto_num)} ({r.ponto_inclinacao_graus:.0f}°): "
            f"{r.ponto_latitude:.5f}, {r.ponto_longitude:.5f}</li>"
            for r in grupo.itertuples()
        )
        info_html = (
            f"<b>{nome_dc}</b><br>"
            f"Cidade: {cidade}<br>"
            f"<u>Pontos de referência:</u>"
            f"<ul style='margin:4px 0 0 -18px'>{pontos_html}</ul>"
        )

        # -- marcador do datacenter --
        folium.Marker(
            [row0.latitude_datacenter, row0.longitude_datacenter],
            tooltip=folium.Tooltip(f"🏢 Datacenter<br>{info_html}", sticky=True),
            icon=folium.Icon(color="red", icon="server", prefix="fa"),
        ).add_to(m)

        folium.Rectangle(
            bounds_quadrado(row0.latitude_datacenter, row0.longitude_datacenter, config.LADO_QUADRADO_KM),
            stroke=False, fill=True, fill_color=cor, fill_opacity=0.25,
            tooltip=folium.Tooltip(
                f"⬛ Área de {config.LADO_QUADRADO_KM}km x {config.LADO_QUADRADO_KM}km — Datacenter<br>{info_html}",
                sticky=True,
            ),
        ).add_to(m)

        # -- marcador do município --
        folium.Marker(
            [row0.latitude_municipio, row0.longitude_municipio],
            tooltip=folium.Tooltip(f"🏙️ Sede do município<br>{info_html}", sticky=True),
            icon=folium.Icon(color="blue", icon="building", prefix="fa"),
        ).add_to(m)

        # -- marcador do ponto de controle (município similar) --
        folium.Marker(
            [row0.latitude_similar, row0.longitude_similar],
            tooltip=folium.Tooltip(f"🎯 Ponto de controle (município similar)<br>{info_html}", sticky=True),
            icon=folium.Icon(color="darkpurple", icon="crosshairs", prefix="fa"),
        ).add_to(m)

        # -- liga datacenter -> município e município -> ponto de controle --
        folium.PolyLine(
            [
                [row0.latitude_datacenter, row0.longitude_datacenter],
                [row0.latitude_municipio, row0.longitude_municipio],
            ],
            color=cor, weight=2, opacity=0.8,
        ).add_to(m)

        folium.PolyLine(
            [
                [row0.latitude_municipio, row0.longitude_municipio],
                [row0.latitude_similar, row0.longitude_similar],
            ],
            color=cor, weight=2, opacity=0.6, dash_array="6,6",
        ).add_to(m)

        # -- os pontos de referência ao redor do ponto de controle --
        for r in grupo.itertuples():
            folium.CircleMarker(
                [r.ponto_latitude, r.ponto_longitude],
                radius=6, color=cor, weight=2, fill=True, fill_color=cor, fill_opacity=0.9,
                tooltip=folium.Tooltip(
                    f"📌 Ponto {int(r.ponto_num)} ({r.ponto_inclinacao_graus:.0f}°)<br>{info_html}",
                    sticky=True,
                ),
            ).add_to(m)
            folium.PolyLine(
                [
                    [row0.latitude_similar, row0.longitude_similar],
                    [r.ponto_latitude, r.ponto_longitude],
                ],
                color=cor, weight=1, opacity=0.5,
            ).add_to(m)
            folium.Rectangle(
                bounds_quadrado(r.ponto_latitude, r.ponto_longitude, config.LADO_QUADRADO_KM),
                stroke=False, fill=True, fill_color=cor, fill_opacity=0.25,
                tooltip=folium.Tooltip(
                    f"⬛ Área de {config.LADO_QUADRADO_KM}km x {config.LADO_QUADRADO_KM}km — "
                    f"Ponto {int(r.ponto_num)} ({r.ponto_inclinacao_graus:.0f}°)<br>{info_html}",
                    sticky=True,
                ),
            ).add_to(m)

    m.save(config.MAPA_HTML)
    print(f"Mapa salvo em: {config.MAPA_HTML}")


if __name__ == "__main__":
    main()
