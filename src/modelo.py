"""Modelos candidatos, validación cruzada temporal y elección del modelo.

Criterio de elección, fijado antes de mirar la prueba de 2025:
1. Gana la mayor precisión promedio (average precision, AP) media en la validación cruzada temporal.
2. Si la diferencia con el siguiente es menor que una desviación estándar, gana el más simple
   (regresión logística antes que árboles), porque se puede explicar a un jefe jurídico.

AP mide qué tan arriba quedan las peticiones vencidas en la lista ordenada por riesgo. No depende
de un umbral, y eso importa porque la proporción de vencidas cambia mucho de un año a otro.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedKFold, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from .datos import CATEGORICAS, NUMERICAS, OBJETIVO, VARIABLES

SEMILLA = 42
N_PLIEGUES = 5
FRACCION_ALERTA = 0.20  # la oficina revisa a mano el 20 % de peticiones con más riesgo
ORDEN_SIMPLICIDAD = ["Siempre a tiempo", "Línea base", "Regresión logística", "Random Forest", "Gradient boosting"]


def _onehot() -> ColumnTransformer:
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=30), CATEGORICAS),
        ("num", StandardScaler(), NUMERICAS),
    ])


def _ordinal() -> ColumnTransformer:
    return ColumnTransformer(
        [("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1,
                                encoded_missing_value=-1), CATEGORICAS)],
        remainder="passthrough",
    )


def linea_base() -> Pipeline:
    """Lo que haría una persona con una regla sencilla: riesgo según tipo de petición y canal."""
    prep = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), ["tipo_peticion", "medio_recepcion"])])
    return Pipeline([("prep", prep), ("modelo", LogisticRegression(class_weight="balanced", max_iter=2000))])


def candidatos() -> dict[str, list[Pipeline]]:
    """Cada candidato con su rejilla corta de hiperparámetros. Todo el preprocesamiento va dentro."""
    logisticas = [
        Pipeline([("prep", _onehot()),
                  ("modelo", LogisticRegression(C=c, class_weight="balanced", max_iter=3000))])
        for c in (0.01, 0.1, 1.0)
    ]
    bosques = [
        Pipeline([("prep", _ordinal()),
                  ("modelo", RandomForestClassifier(n_estimators=300, min_samples_leaf=hoja,
                                                    class_weight="balanced_subsample",
                                                    n_jobs=-1, random_state=SEMILLA))])
        for hoja in (5, 50)
    ]
    boosting = [
        Pipeline([("prep", _ordinal()),
                  ("modelo", HistGradientBoostingClassifier(
                      categorical_features=list(range(len(CATEGORICAS))), class_weight="balanced",
                      max_iter=200, learning_rate=0.03, max_depth=prof, min_samples_leaf=100,
                      l2_regularization=1.0, random_state=SEMILLA))])
        for prof in (3, 6)
    ]
    return {
        "Siempre a tiempo": [Pipeline([("prep", _onehot()), ("modelo", DummyClassifier(strategy="prior"))])],
        "Línea base": [linea_base()],
        "Regresión logística": logisticas,
        "Random Forest": bosques,
        "Gradient boosting": boosting,
    }


def describir(pipe: Pipeline) -> str:
    m = pipe.named_steps["modelo"]
    if isinstance(m, LogisticRegression):
        return f"C={m.C}"
    if isinstance(m, RandomForestClassifier):
        return f"min_samples_leaf={m.min_samples_leaf}"
    if isinstance(m, HistGradientBoostingClassifier):
        return f"max_depth={m.max_depth}"
    return "-"


def recall_en_alerta(y, p, fraccion: float = FRACCION_ALERTA, semilla: int = SEMILLA) -> float:
    """Qué parte de las vencidas cae en el `fraccion` de peticiones con más riesgo.

    Los empates se rompen al azar con semilla fija, para que un modelo constante dé lo que
    daría revisar peticiones al azar (cerca del 20 %).
    """
    y = np.asarray(y)
    p = np.asarray(p, dtype=float)
    if y.sum() == 0:
        return float("nan")
    desempate = np.random.default_rng(semilla).random(len(p))
    orden = np.lexsort((desempate, -p))
    k = int(round(len(p) * fraccion))
    return float(y[orden[:k]].sum() / y.sum())


def metricas(y, p, umbral: float) -> dict:
    y = np.asarray(y)
    pred = (np.asarray(p) >= umbral).astype(int)
    return {
        "ap": average_precision_score(y, p) if y.sum() else float("nan"),
        "recall_alerta": recall_en_alerta(y, p),
        "f1": f1_score(y, pred, zero_division=0),
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
    }


def pliegues(df: pd.DataFrame, temporal: bool = True):
    """Validación cruzada. Temporal: cada pliegue entrena con el pasado y valida con lo que sigue.

    `df` debe venir ordenado por fecha de radicación.
    """
    if temporal:
        return list(TimeSeriesSplit(n_splits=N_PLIEGUES).split(df))
    return list(StratifiedKFold(N_PLIEGUES, shuffle=True, random_state=SEMILLA).split(df, df[OBJETIVO]))


def validar(pipe: Pipeline, df: pd.DataFrame, temporal: bool = True) -> tuple[dict, np.ndarray]:
    """Media y desviación de las métricas en los pliegues, y las predicciones fuera de pliegue."""
    X, y = df[VARIABLES], df[OBJETIVO]
    por_pliegue = []
    fuera = np.full(len(df), np.nan)
    for ent, val in pliegues(df, temporal):
        m = clone(pipe).fit(X.iloc[ent], y.iloc[ent])
        p = m.predict_proba(X.iloc[val])[:, 1]
        fuera[val] = p
        por_pliegue.append(metricas(y.iloc[val], p, umbral=0.5))
    tabla = pd.DataFrame(por_pliegue)
    resumen = {f"{k}_media": tabla[k].mean() for k in tabla} | {f"{k}_desv": tabla[k].std(ddof=0) for k in tabla}
    return resumen, fuera


def comparar(df: pd.DataFrame, temporal: bool = True) -> pd.DataFrame:
    """Valida todos los candidatos y deja la mejor configuración de cada familia."""
    filas = []
    for familia, opciones in candidatos().items():
        for pipe in opciones:
            resumen, _ = validar(pipe, df, temporal)
            filas.append({"modelo": familia, "hiperparametros": describir(pipe), **resumen})
    todas = pd.DataFrame(filas)
    todas["simplicidad"] = todas["modelo"].map(ORDEN_SIMPLICIDAD.index)
    return todas


def elegir(tabla: pd.DataFrame) -> pd.Series:
    """Aplica el criterio del encabezado del módulo sobre la tabla de `comparar`."""
    reales = tabla[~tabla["modelo"].isin(["Siempre a tiempo", "Línea base"])]
    mejor = reales.loc[reales["ap_media"].idxmax()]
    cercanos = reales[reales["ap_media"] >= mejor["ap_media"] - mejor["ap_desv"]]
    return cercanos.sort_values(["simplicidad", "ap_media"], ascending=[True, False]).iloc[0]


def construir(modelo: str, hiperparametros: str) -> Pipeline:
    for pipe in candidatos()[modelo]:
        if describir(pipe) == hiperparametros:
            return pipe
    raise ValueError(f"No existe el candidato {modelo} con {hiperparametros}")


def umbral_alerta(p_fuera: np.ndarray, fraccion: float = FRACCION_ALERTA) -> float:
    """Puntaje a partir del cual una petición entra en el grupo de revisión prioritaria.

    Se calcula con las predicciones fuera de pliegue del periodo de desarrollo, nunca con 2025.
    """
    validas = p_fuera[~np.isnan(p_fuera)]
    return float(np.quantile(validas, 1 - fraccion))
