"""Evaluar una petición nueva con el modelo guardado. La usan app.py, el cuaderno de Colab y las pruebas."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from .datos import INICIO_LEY_1755, VARIABLES, fecha_vencimiento

RAIZ = Path(__file__).resolve().parent.parent
RUTA_MODELO = RAIZ / "modelos" / "modelo.joblib"
RUTA_DEBILES = RAIZ / "resultados" / "subgrupos_debiles.csv"

# Términos de la Ley 1755 de 2015 tal como los registra el sistema de la Secretaría.
PLAZOS = {
    "DERECHO DE PETICION EN INTERES GENERAL": 15,
    "DERECHO DE PETICION EN INTERES PARTICULAR": 15,
    "DERECHO DE PETICION DE INFORMACIONES": 10,
    "DERECHO DE PETICION DE CONSULTAS": 30,
    "DERECHO DE PETICION TERMINO 5": 5,
    "DERECHO DE PETICION TERMINO 4": 4,
    "DERECHO DE PETICION TERMINO 3": 3,
    "DERECHO DE PETICION TERMINO 2": 2,
}

LIMITACIONES = (
    "Herramienta de apoyo para ordenar la revisión de peticiones. No decide nada sobre la petición "
    "ni sobre quien la presentó, y no reemplaza el control de términos del sistema de gestión documental. "
    "Se entrenó con radicados de la Secretaría Distrital de Gobierno y las alcaldías locales entre mayo de 2022 "
    "y diciembre de 2024. En 2025 la proporción de vencidas bajó a menos de una cuarta parte y el modelo "
    "perdió precisión: de cada 100 alertas, unas 6 fueron peticiones que sí se vencieron. "
    "En algunas localidades detecta muy pocas vencidas. No la uses para evaluar funcionarios ni dependencias."
)


@lru_cache(maxsize=1)
def cargar_modelo(ruta: Path = RUTA_MODELO) -> dict:
    if not Path(ruta).exists():
        raise FileNotFoundError(f"No encuentro {ruta}. Genera el modelo con: python entrenar.py")
    return joblib.load(ruta)


@lru_cache(maxsize=1)
def grupos_debiles() -> dict[str, float]:
    """Localidades y canales donde la alerta encontró pocas vencidas en 2025 (ver auditoria.md)."""
    if not RUTA_DEBILES.exists():
        return {}
    tabla = pd.read_csv(RUTA_DEBILES)
    return dict(zip(tabla["grupo"], tabla["recall"]))


def evaluar(tipo_peticion: str, medio_recepcion: str, localidad: str, subtema: str,
            fecha_radicacion: datetime, carga_7d: int) -> dict:
    """Probabilidad de que la petición se responda fuera de término y si entra en la alerta."""
    if tipo_peticion not in PLAZOS:
        raise ValueError(f"Tipo de petición no reconocido: {tipo_peticion!r}. Válidos: {sorted(PLAZOS)}")
    fecha = pd.Timestamp(fecha_radicacion)
    if pd.isna(fecha):
        raise ValueError("La fecha de radicación es obligatoria.")
    if fecha < INICIO_LEY_1755:
        raise ValueError("Solo aplica a radicados desde el 18/05/2022, cuando volvieron los términos de la Ley 1755.")
    if carga_7d is None or int(carga_7d) < 0:
        raise ValueError("La carga de los últimos 7 días debe ser un número entero mayor o igual a cero.")

    plazo = PLAZOS[tipo_peticion]
    vence = fecha_vencimiento(fecha, plazo)
    fila = pd.DataFrame([{
        "tipo_peticion": tipo_peticion,
        "medio_recepcion": medio_recepcion,
        "localidad": localidad,
        "subtema": subtema,
        "plazo_habiles": plazo,
        "dias_calendario_plazo": (vence - fecha.normalize()).days,
        "carga_7d": int(carga_7d),
        "mes": fecha.month,
        "dia_semana": fecha.day_of_week,
        "hora": fecha.hour,
    }])[VARIABLES]

    modelo = cargar_modelo()
    p = float(modelo["pipeline"].predict_proba(fila)[0, 1])
    alerta = p >= modelo["umbral"]
    avisos = [f"{g}: en 2025 la alerta detectó {r:.0%} de las vencidas." for g, r in grupos_debiles().items()
              if g in (localidad, medio_recepcion)]
    return {
        "probabilidad": p,
        "alerta": bool(alerta),
        "nivel": "Revisión prioritaria" if alerta else "Trámite normal",
        "plazo_habiles": plazo,
        "fecha_vencimiento": vence.date(),
        "avisos": avisos,
    }
