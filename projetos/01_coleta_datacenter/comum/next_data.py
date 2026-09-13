"""Extração do __NEXT_DATA__ (Next.js) embutido nas páginas do datacentermap.com.

Em vez de guardar o HTML inteiro e depois vasculhar `<div class="header">` etc.,
usamos esse JSON pra pegar só os campos que interessam: é mais leve, mais
rápido de reprocessar e não depende de seletores CSS que quebram a cada
mudança de layout do site.
"""
import json
from typing import Optional

from bs4 import BeautifulSoup

TITULO_BLOQUEIO = "Page View Limit Reached"
PAGE_ID_BLOQUEIO = "rate-limited"


def extrair_page_props(html: str) -> Optional[dict]:
    """Retorna props.pageProps do __NEXT_DATA__, ou None se não encontrar/parsear."""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag is None or not tag.string:
        return None
    try:
        data = json.loads(tag.string)
    except json.JSONDecodeError:
        return None
    return data.get("props", {}).get("pageProps")


def esta_bloqueado(page_props: Optional[dict]) -> bool:
    """Detecta a página de rate limit ("Page View Limit Reached"). Quando o
    site bloqueia, o __NEXT_DATA__ ainda existe, mas com pageId/pageTitle de
    bloqueio em vez do conteúdo real — sem essa checagem a página bloqueada
    seria salva no cache como se fosse um resultado válido."""
    if not page_props:
        return False
    return (
        page_props.get("pageId") == PAGE_ID_BLOQUEIO
        or page_props.get("pageTitle") == TITULO_BLOQUEIO
    )


def extrair_features_com_coords(features: Optional[list]) -> list:
    """Converte uma lista de GeoJSON Features (mapdata.dcs / mapdata.geos) em
    dicts simples, com latitude/longitude já achatados nas properties."""
    resultado = []
    for feature in features or []:
        prop = dict(feature.get("properties") or {})
        coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
        lon, lat = coords[0], coords[1]
        prop["latitude"] = lat
        prop["longitude"] = lon
        resultado.append(prop)
    return resultado
