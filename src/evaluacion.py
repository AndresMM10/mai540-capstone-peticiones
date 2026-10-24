"""Errores por categoría y degradación en el tiempo."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .datos import OBJETIVO
from .modelo import metricas

MINIMO_CASOS = 100     # por debajo de esto, la cifra de un grupo es poco confiable
MINIMO_VENCIDAS = 10


def errores_por_categoria(df: pd.DataFrame, p: np.ndarray, umbral: float, columna: str) -> pd.DataFrame:
    """Para cada valor de `columna`: casos, vencidas, cuántas detectó la alerta y cuántas se le escaparon."""
    tabla = df[[columna, OBJETIVO]].copy()
    tabla["alerta"] = (np.asarray(p) >= umbral).astype(int)
    filas = []
    for valor, g in tabla.groupby(columna):
        y, a = g[OBJETIVO], g["alerta"]
        vencidas = int(y.sum())
        detectadas = int(((y == 1) & (a == 1)).sum())
        falsas = int(((y == 0) & (a == 1)).sum())
        filas.append({
            "variable": columna,
            "grupo": valor,
            "casos": len(g),
            "vencidas": vencidas,
            "tasa_vencidas": vencidas / len(g),
            "alertadas": int(a.sum()),
            "detectadas": detectadas,
            "no_detectadas": vencidas - detectadas,
            "recall": detectadas / vencidas if vencidas else np.nan,
            "precision": detectadas / (detectadas + falsas) if (detectadas + falsas) else np.nan,
            "muestra_pequena": len(g) < MINIMO_CASOS or vencidas < MINIMO_VENCIDAS,
        })
    return pd.DataFrame(filas).sort_values("casos", ascending=False).reset_index(drop=True)


def subgrupos_debiles(tabla: pd.DataFrame, recall_global: float, margen: float = 0.15) -> pd.DataFrame:
    """Grupos con muestra suficiente donde la alerta encuentra muchas menos vencidas que en el total."""
    confiables = tabla[~tabla["muestra_pequena"]]
    return confiables[confiables["recall"] < recall_global - margen]


def por_periodo(df: pd.DataFrame, p: np.ndarray, umbral: float, periodo: str = "anio") -> pd.DataFrame:
    """Métricas del modelo en cada periodo, para ver si se degrada."""
    tabla = df.assign(_p=p)
    tabla = tabla[tabla["_p"].notna()]
    filas = []
    for valor, g in tabla.groupby(periodo):
        m = metricas(g[OBJETIVO], g["_p"], umbral)
        filas.append({periodo: valor, "casos": len(g), "tasa_vencidas": g[OBJETIVO].mean(),
                      "alertadas": float((g["_p"] >= umbral).mean()), **m})
    return pd.DataFrame(filas)
