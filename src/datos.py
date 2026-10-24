"""Preparación de los datos de PQRS de la Secretaría Distrital de Gobierno (Bogotá).

Todo lo que sale de aquí debe poder conocerse en el momento de radicar la petición.
Lo que se registra después (dependencia actual, observaciones, usuario que la tiene,
fecha de respuesta) solo sirve para construir la etiqueta, nunca como variable del modelo.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

URL_FUENTE = (
    "https://datosabiertos.bogota.gov.co/dataset/db9d7291-0308-475e-bd81-cd222c13fca4/"
    "resource/10f7c48f-91ca-4705-a652-af4ff12ef24a/download/pqrs_sdg_2022_2026.csv"
)
RAIZ = Path(__file__).resolve().parent.parent
RUTA_CRUDA = RAIZ / "datos" / "pqrs_sdg_2022_2026.csv"
RUTA_PREPARADA = RAIZ / "datos" / "peticiones_preparadas.csv"

# La Ley 2207 del 17 de mayo de 2022 derogó la ampliación de términos del Decreto 491 de 2020.
# Desde el día siguiente rigen otra vez los términos de la Ley 1755 de 2015.
INICIO_LEY_1755 = pd.Timestamp("2022-05-18")

# Columnas que existen en el momento de radicar. Son las únicas que el modelo puede ver.
CATEGORICAS = ["tipo_peticion", "medio_recepcion", "localidad", "subtema"]
NUMERICAS = ["plazo_habiles", "dias_calendario_plazo", "carga_7d", "mes", "dia_semana", "hora"]
VARIABLES = CATEGORICAS + NUMERICAS
OBJETIVO = "vencida"

# Columnas del archivo original que se llenan después de radicar o que identifican personas.
# No entran al archivo preparado.
COLUMNAS_POSTERIORES = [
    "ESTADO_ORFEO", "OBSERVACION_GENERAL", "OBSERVACION_SAC", "USUARIO_ACTUAL",
    "DEPENDENCIA_ACTUAL", "ULTIMA_DEPENDENCIA", "RADICADO_RESPUESTA", "FECHA_RESPUESTA",
    "FECHA_SEGUIMIENTO", "FECHA_ASIGNACION",
]


@lru_cache(maxsize=1)
def festivos_colombia() -> np.ndarray:
    """Festivos de Colombia 2021 a 2028 como fechas de numpy, para np.busday_count."""
    dias = holidays.Colombia(years=range(2021, 2029)).keys()
    return np.array(sorted(dias), dtype="datetime64[D]")


def dias_habiles(desde, hasta) -> np.ndarray:
    """Días hábiles transcurridos entre la radicación y la respuesta.

    El término corre desde el día siguiente a la radicación (art. 14 de la Ley 1437 de 2011,
    sustituido por la Ley 1755 de 2015) y cuenta el día de la respuesta. Excluye sábados,
    domingos y festivos. Si la respuesta es anterior a la radicación el resultado es negativo,
    y eso es un error de registro que se filtra en `preparar`.
    """
    d = pd.to_datetime(pd.Series(desde)).values.astype("datetime64[D]")
    h = pd.to_datetime(pd.Series(hasta)).values.astype("datetime64[D]")
    uno = np.timedelta64(1, "D")
    return np.busday_count(d + uno, h + uno, holidays=festivos_colombia())


def fecha_vencimiento(radicacion, plazo_habiles: int) -> pd.Timestamp:
    """Último día hábil para responder, contado desde el día siguiente a la radicación."""
    dia = np.datetime64(pd.Timestamp(radicacion).date(), "D")
    return pd.Timestamp(np.busday_offset(dia, int(plazo_habiles), roll="forward",
                                         holidays=festivos_colombia()))


def leer_crudo(ruta: Path = RUTA_CRUDA) -> pd.DataFrame:
    """Lee el CSV tal como lo publica el portal (separador ;, UTF-8 con BOM)."""
    if not Path(ruta).exists():
        raise FileNotFoundError(
            f"No encuentro {ruta}. Descárgalo con: python preparar_datos.py --descargar"
        )
    return pd.read_csv(ruta, sep=";", encoding="utf-8-sig", dtype=str)


def carga_previa(fechas: pd.Series, grupos: pd.Series, dias: int = 7) -> pd.Series:
    """Cuántas peticiones radicó el mismo grupo en los `dias` anteriores, sin contar la actual.

    Solo mira hacia atrás. Una petición futura no puede cambiar este número, y la prueba
    test_carga_no_mira_el_futuro lo comprueba.
    """
    tabla = pd.DataFrame({"f": pd.to_datetime(fechas).values, "g": grupos.values}, index=fechas.index)
    tabla = tabla.sort_values("f", kind="mergesort")
    resultado = pd.Series(0, index=tabla.index, dtype=int)
    ventana = pd.Timedelta(days=dias)
    for _, bloque in tabla.groupby("g", sort=False):
        f = bloque["f"].values
        inicio = np.searchsorted(f, f - ventana, side="left")
        actual = np.searchsorted(f, f, side="left")
        resultado.loc[bloque.index] = actual - inicio
    return resultado.reindex(fechas.index)


def preparar(crudo: pd.DataFrame) -> pd.DataFrame:
    """Del archivo del portal al conjunto de modelado. Devuelve una fila por radicado cerrado.

    Reglas, en orden:
    1. Solo radicados desde el 18 de mayo de 2022 (términos de la Ley 1755).
    2. Solo peticiones con tipo y plazo legal registrados (plazo mayor que cero).
    3. Solo radicados con fecha de respuesta. Los que siguen en gestión no tienen etiqueta.
    4. Se descartan respuestas con fecha anterior a la radicación (error de registro).
    """
    df = pd.DataFrame({
        "radicado": crudo["RADICADO"].str.strip(),
        "fecha_radicacion": pd.to_datetime(crudo["RADI_FECH_RADI"], format="%d/%m/%Y %H:%M:%S", errors="coerce"),
        "fecha_respuesta": pd.to_datetime(crudo["FECHA_RESPUESTA"], format="%d/%m/%Y %H:%M:%S", errors="coerce"),
        "tipo_peticion": crudo["TIPO_PETICION"].str.strip(),
        "plazo_habiles": pd.to_numeric(crudo["TIEMPO_TRAMITE"], errors="coerce"),
        "medio_recepcion": crudo["MEDIO_RECEPCION"].str.strip(),
        "localidad": crudo["NOMBRE_LOCALIDAD"].fillna("SIN LOCALIDAD").str.strip(),
        "subtema": crudo["SUBTEMA"].str.strip(),
    })
    # La carga se mide sobre todos los radicados del archivo, también los que luego se filtran,
    # porque en la oficina todos ocupan tiempo.
    df["carga_7d"] = carga_previa(df["fecha_radicacion"], df["localidad"])

    df = df[df["fecha_radicacion"] >= INICIO_LEY_1755]
    df = df[df["tipo_peticion"].notna() & df["plazo_habiles"].gt(0)]
    df = df[df["fecha_respuesta"].notna()]
    df = df.assign(dias_habiles=dias_habiles(df["fecha_radicacion"], df["fecha_respuesta"]))
    df = df[df["dias_habiles"] >= 0].copy()

    df["plazo_habiles"] = df["plazo_habiles"].astype(int)
    df[OBJETIVO] = (df["dias_habiles"] > df["plazo_habiles"]).astype(int)
    df["dias_calendario_plazo"] = [
        (fecha_vencimiento(f, p) - f.normalize()).days
        for f, p in zip(df["fecha_radicacion"], df["plazo_habiles"])
    ]
    df["mes"] = df["fecha_radicacion"].dt.month
    df["dia_semana"] = df["fecha_radicacion"].dt.dayofweek
    df["hora"] = df["fecha_radicacion"].dt.hour
    df["anio"] = df["fecha_radicacion"].dt.year
    columnas = ["radicado", "fecha_radicacion", "fecha_respuesta", "anio", *VARIABLES, "dias_habiles", OBJETIVO]
    return df[columnas].sort_values("fecha_radicacion").reset_index(drop=True)


def cargar_preparado(ruta: Path = RUTA_PREPARADA) -> pd.DataFrame:
    """Lee el archivo preparado que vive en el repositorio."""
    df = pd.read_csv(ruta, parse_dates=["fecha_radicacion", "fecha_respuesta"], dtype={"radicado": str})
    return df


def particion_temporal(df: pd.DataFrame, anio_corte: int = 2025):
    """Desarrollo: radicados antes de `anio_corte`. Prueba final: el año `anio_corte`.

    Los radicados posteriores (2026) quedan fuera porque muchos siguen abiertos y los que ya
    se cerraron son, por construcción, los más rápidos. Usarlos subestimaría el vencimiento.
    """
    desarrollo = df[df["anio"] < anio_corte]
    prueba = df[df["anio"] == anio_corte]
    return desarrollo, prueba

