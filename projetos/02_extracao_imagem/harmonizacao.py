"""Harmonização espectral Landsat 8/9 <-> Sentinel-2 (SV-02b).

Contrato de bandas: `harmonizar_landsat()` e `harmonizar_s2()` devolvem SEMPRE os mesmos 6 nomes
de banda, na mesma ordem (`bandas_harmonizadas()`), em reflectância float [0, 1]. SV-06, SV-06b e
SV-08 só devem chamar essas funções — nunca ler `SR_B*`/`B2`.. diretamente das coleções brutas.

Decisão de método e resíduo medido: ver `docs/decisoes/ADR-003-harmonizacao-multissensor.md`.

Landsat é o sensor de REFERÊNCIA do ajuste de bandpass (segue a mesma convenção do produto NASA
HLS, que usa OLI como alvo e ajusta MSI/Sentinel-2 até ele). Por isso `harmonizar_landsat()` só
faz conversão de escala (sem ajuste espectral) e `harmonizar_s2()` aplica, além da escala, uma
correção linear por banda que aproxima a reflectância do Sentinel-2 (MSI) da reflectância
"pseudo-OLI" equivalente.
"""

from __future__ import annotations

import ee

# Ordem canônica das bandas harmonizadas — vira contrato para SV-06/SV-06b/SV-08.
_BANDAS: tuple[str, ...] = ("blue", "green", "red", "nir", "swir1", "swir2")

# Correspondência de banda harmonizada -> banda nativa de cada sensor (ver tabela da tarefa
# SV-02b / docs/tarefas/SV-02b-spike-harmonizacao-multissensor.md, Passo 2).
# NIR usa Sentinel-2 B8A (855-875nm), não B8 (785-900nm) — B8A é a correspondência estreita
# correta com o NIR do OLI (banda 5, 851-879nm).
_LANDSAT_BANDS: dict[str, str] = {
    "blue": "SR_B2",
    "green": "SR_B3",
    "red": "SR_B4",
    "nir": "SR_B5",
    "swir1": "SR_B6",
    "swir2": "SR_B7",
}
_S2_BANDS: dict[str, str] = {
    "blue": "B2",
    "green": "B3",
    "red": "B4",
    "nir": "B8A",
    "swir1": "B11",
    "swir2": "B12",
}

# --- Coeficientes de ajuste de bandpass: Sentinel-2A MSI -> "pseudo-OLI" (Landsat 8/9) ---
#
# reflectância_pseudo_OLI = slope * reflectância_MSI + offset
#
# Fonte: página oficial de bandpass adjustment do NASA HLS, https://hls.gsfc.nasa.gov/bandpass-adjustment/
# (consultada em 2026-08-27). Essa página descreve o método como originado em Claverie, M., Ju, J.,
# Masek, J.G., et al. (2018), "The Harmonized Landsat and Sentinel-2 surface reflectance data set",
# Remote Sensing of Environment, 219, 145-161 (confirmado também no HLS ATBD v1.5, LP DAAC), mas a
# TABELA NUMÉRICA hoje publicada nessa página está atribuída por ela a uma revisão posterior,
# Claverie (2023), ISPRS Journal of Photogrammetry and Remote Sensing, 198, 210-222,
# doi:10.1016/j.isprsjprs.2023.03.011 — não foi possível abrir o PDF do artigo de 2023 para
# conferir a tabela linha a linha nesta sessão (sem acesso), então a atribuição de autoria/ano
# exata do artigo de origem fica registrada aqui como reportada pela própria página da NASA, não
# verificada contra o PDF do periódico. Os valores em si foram lidos diretamente da página da NASA
# (não estimados/inventados). Usamos os coeficientes de Sentinel-2A (a página também lista S2B;
# a maior diferença entre S2A e S2B é 0.003 no slope e 0.0004 no offset — abaixo da tolerância de
# viés de 0.02 do spike, então não distinguimos por satélite específico).
_BANDPASS_S2A_PARA_PSEUDO_OLI: dict[str, tuple[float, float]] = {
    "blue": (0.9778, -0.0040),
    "green": (1.0053, -0.0009),
    "red": (0.9765, 0.0009),
    "nir": (0.9983, -0.0001),
    "swir1": (0.9987, -0.0011),
    "swir2": (1.0030, -0.0012),
}


def bandas_harmonizadas() -> list[str]:
    """Lista ordenada canônica das 6 bandas harmonizadas — contrato de nome/ordem p/ SV-06+."""
    return list(_BANDAS)


def harmonizar_landsat(img: ee.Image) -> ee.Image:
    """Landsat C2 L2 (`LANDSAT/LC0{8,9}/C02/T1_L2`) -> reflectância float, bandas canônicas.

    Escala: `SR_B* * 0.0000275 - 0.2` (fator de escala oficial do USGS Collection 2 Level-2
    Surface Reflectance — ver USGS Landsat Collection 2 Level-2 Science Product Guide).
    Landsat é a referência do ajuste de bandpass (ver módulo docstring) — não recebe ajuste
    espectral adicional aqui, só conversão de escala e renomeação de banda.
    """
    bandas_origem = [_LANDSAT_BANDS[b] for b in _BANDAS]
    return img.select(bandas_origem, list(_BANDAS)).multiply(0.0000275).add(-0.2).toFloat()


def harmonizar_s2(img: ee.Image, aplicar_bandpass: bool = True) -> ee.Image:
    """Sentinel-2 L2A (`COPERNICUS/S2_SR_HARMONIZED`) -> reflectância float, bandas canônicas.

    Escala: `B* / 10000` (Sentinel-2 L2A é entregue em reflectância x10000).
    Em seguida aplica o ajuste linear de bandpass (ver `_BANDPASS_S2A_PARA_PSEUDO_OLI`) para
    aproximar a reflectância do Sentinel-2 da reflectância equivalente do Landsat OLI.

    `aplicar_bandpass=False` existe só para o teste de sanidade invertida do spike SV-02b
    (cenário 5): confirma que DESLIGAR o ajuste piora o resíduo medido contra Landsat. Não deve
    ser usado em produção (SV-06/SV-06b sempre chamam com o default `True`).
    """
    bandas_origem = [_S2_BANDS[b] for b in _BANDAS]
    escalada = img.select(bandas_origem, list(_BANDAS)).divide(10000.0).toFloat()
    if not aplicar_bandpass:
        return escalada

    ajustadas = [
        escalada.select([banda])
        .multiply(_BANDPASS_S2A_PARA_PSEUDO_OLI[banda][0])
        .add(_BANDPASS_S2A_PARA_PSEUDO_OLI[banda][1])
        for banda in _BANDAS
    ]
    return ee.Image.cat(ajustadas).rename(list(_BANDAS)).toFloat()


def mascara_nuvem(img: ee.Image, sensor: str) -> ee.Image:
    """Aplica máscara de nuvem/sombra/saturação a `img` (imagem BRUTA da coleção nativa).

    Pode ser aplicada antes ou depois de `harmonizar_landsat`/`harmonizar_s2` — a máscara opera
    por posição de pixel, não por nome de banda, então a ordem de composição não importa.

    sensor:
      - `"landsat"`: bitmask de `QA_PIXEL` (dilated cloud=bit1, cirrus=bit2, cloud=bit3,
        cloud shadow=bit4) + `QA_RADSAT` (remove pixel com qualquer banda saturada).
      - `"sentinel2"`: Cloud Score+ `cs_cdf >= 0.60` (decisão D-04 do projeto), a partir da
        coleção `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`, linkada por `system:index`.
    """
    if sensor == "landsat":
        qa = img.select("QA_PIXEL")
        radsat = img.select("QA_RADSAT")
        bit_dilated_cloud = 1 << 1
        bit_cirrus = 1 << 2
        bit_cloud = 1 << 3
        bit_cloud_shadow = 1 << 4
        mascara_bits = bit_dilated_cloud | bit_cirrus | bit_cloud | bit_cloud_shadow
        nublado = qa.bitwiseAnd(mascara_bits).neq(0)
        saturado = radsat.neq(0)
        return img.updateMask(nublado.Not()).updateMask(saturado.Not())

    if sensor == "sentinel2":
        # Filtra a coleção de Cloud Score+ para uma janela de 1 dia ao redor da data da imagem
        # antes de linkar — sem isso, o linkCollection casa contra a coleção inteira (global,
        # todos os anos), o que fica visivelmente mais lento ao processar muitas imagens em lote
        # (ex.: dentro de um .map() sobre uma ImageCollection inteira, como em SV-06/SV-02b).
        data = img.date()
        cs_plus = (
            ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
            .filterDate(data.advance(-1, "day"), data.advance(1, "day"))
        )
        linkada = img.linkCollection(cs_plus, ["cs_cdf"])
        return img.updateMask(linkada.select("cs_cdf").gte(0.60))

    raise ValueError(f"sensor deve ser 'landsat' ou 'sentinel2', recebido: {sensor!r}")
