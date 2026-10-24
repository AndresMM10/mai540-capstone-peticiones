"""Auditoría del proyecto: fuga de datos, partición y subgrupos.

Cada revisión mide algo y deja tres datos: qué encontró, qué se corrigió y cómo se comprobó.

Uso:
    python auditoria.py        # escribe resultados/auditoria.md y termina con código 1 si algo falla
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.datos import (CATEGORICAS, COLUMNAS_POSTERIORES, NUMERICAS, OBJETIVO, VARIABLES,
                       cargar_preparado, particion_temporal)
from src.evaluacion import subgrupos_debiles
from src.modelo import candidatos, validar

RAIZ = Path(__file__).resolve().parent
RES = RAIZ / "resultados"
PROHIBIDAS = {"dias_habiles", "fecha_respuesta", "anio", "radicado", OBJETIVO} | {c.lower() for c in COLUMNAS_POSTERIORES}


def revisar_fuga(desarrollo: pd.DataFrame) -> tuple[bool, list[str]]:
    lineas, ok = [], True

    # 1. Ninguna variable del modelo se conoce después de radicar.
    cruce = PROHIBIDAS & {v.lower() for v in VARIABLES}
    ok &= not cruce
    lineas.append(f"- Variables del modelo que se conocen después de radicar: {sorted(cruce) or 'ninguna'}.")

    # 2. Todo candidato lleva el preprocesamiento dentro del Pipeline.
    sin_pipeline = [f for f, ops in candidatos().items() for p in ops
                    if not (isinstance(p, Pipeline) and "prep" in p.named_steps)]
    ok &= not sin_pipeline
    lineas.append(f"- Candidatos con preprocesamiento fuera del Pipeline: {sin_pipeline or 'ninguno'}. "
                  "La codificación y el escalado se ajustan dentro de cada pliegue.")

    # 3. Qué pasaría con fuga: se agrega dias_habiles, que solo existe cuando ya hay respuesta.
    con_fuga = Pipeline([
        ("prep", ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=30), CATEGORICAS),
            ("num", StandardScaler(), NUMERICAS + ["dias_habiles"]),
        ])),
        ("modelo", LogisticRegression(class_weight="balanced", max_iter=3000)),
    ])
    corte = int(len(desarrollo) * 0.8)
    ent, val = desarrollo.iloc[:corte], desarrollo.iloc[corte:]
    m = con_fuga.fit(ent[VARIABLES + ["dias_habiles"]], ent[OBJETIVO])
    ap_fuga = average_precision_score(val[OBJETIVO], m.predict_proba(val[VARIABLES + ["dias_habiles"]])[:, 1])
    limpio = clone(candidatos()["Regresión logística"][2]).fit(ent[VARIABLES], ent[OBJETIVO])
    ap_limpio = average_precision_score(val[OBJETIVO], limpio.predict_proba(val[VARIABLES])[:, 1])
    lineas.append(f"- Demostración: con `dias_habiles` como variable la AP sube a {ap_fuga:.3f}; "
                  f"sin ella es {ap_limpio:.3f}. Esa es la cifra que daría un modelo con fuga.")
    return ok, lineas


def revisar_particion(df: pd.DataFrame, desarrollo: pd.DataFrame, prueba: pd.DataFrame) -> tuple[bool, list[str]]:
    lineas, ok = [], True
    solapados = set(desarrollo["radicado"]) & set(prueba["radicado"])
    ok &= not solapados
    lineas.append(f"- Radicados presentes en desarrollo y en prueba a la vez: {len(solapados)}.")
    ultimo_dev, primero_prueba = desarrollo["fecha_radicacion"].max(), prueba["fecha_radicacion"].min()
    ok &= ultimo_dev < primero_prueba
    lineas.append(f"- Último radicado de desarrollo: {ultimo_dev:%d/%m/%Y}. Primero de prueba: {primero_prueba:%d/%m/%Y}.")
    ordenado = desarrollo["fecha_radicacion"].is_monotonic_increasing
    ok &= ordenado
    lineas.append(f"- Desarrollo ordenado por fecha para la validación temporal: {'sí' if ordenado else 'no'}.")

    temporal = pd.read_csv(RES / "comparacion_modelos.csv")
    aleatoria = pd.read_csv(RES / "comparacion_aleatoria.csv")
    clave = ["modelo", "hiperparametros"]
    cruce = temporal[clave + ["ap_media"]].merge(aleatoria[clave + ["ap_media"]], on=clave, suffixes=("_temporal", "_aleatoria"))
    cruce["inflacion"] = cruce["ap_media_aleatoria"] - cruce["ap_media_temporal"]
    lineas.append("- Precisión promedio (AP) con validación aleatoria y con validación temporal:")
    lineas.append("")
    lineas.append("| Modelo | Hiperparámetros | AP aleatoria | AP temporal | Diferencia |")
    lineas.append("|---|---|---|---|---|")
    for _, r in cruce.iterrows():
        lineas.append(f"| {r.modelo} | {r.hiperparametros} | {r.ap_media_aleatoria:.3f} | {r.ap_media_temporal:.3f} | {r.inflacion:+.3f} |")
    lineas.append("")
    ganador_aleatorio = cruce.loc[cruce["ap_media_aleatoria"].idxmax()]
    lineas.append(f"- Con validación aleatoria ganaría {ganador_aleatorio.modelo} ({ganador_aleatorio.hiperparametros}).")
    return ok, lineas


def revisar_subgrupos() -> tuple[bool, list[str], pd.DataFrame]:
    errores = pd.read_csv(RES / "errores_por_categoria.csv")
    import json
    global_ = json.loads((RES / "metricas_prueba.json").read_text())["prueba_2025"]["recall"]
    debiles = subgrupos_debiles(errores, global_)
    pequenos = errores[errores["muestra_pequena"]]
    lineas = [
        f"- Recall global de la alerta en 2025: {global_:.3f}.",
        f"- Grupos con al menos 100 casos y 10 vencidas cuyo recall está 15 puntos o más por debajo: {len(debiles)}.",
        f"- Grupos con muestra pequeña (menos de 100 casos o menos de 10 vencidas): {len(pequenos)}. "
        "Sus cifras no se interpretan.",
    ]
    return True, lineas, debiles


def main() -> int:
    df = cargar_preparado()
    desarrollo, prueba = particion_temporal(df)
    ok_f, fuga = revisar_fuga(desarrollo)
    ok_p, particion = revisar_particion(df, desarrollo, prueba)
    ok_s, subgrupos, debiles = revisar_subgrupos()

    texto = ["# Auditoría: fuga de datos, partición y subgrupos", "",
             "Generado por `python auditoria.py`.", "",
             f"## Fuga de datos: {'sin problemas' if ok_f else 'FALLA'}", "", *fuga, "",
             f"## Partición: {'sin problemas' if ok_p else 'FALLA'}", "", *particion, "",
             "## Subgrupos", "", *subgrupos, ""]
    if len(debiles):
        texto += ["| Variable | Grupo | Casos | Vencidas | Recall |", "|---|---|---|---|---|"]
        texto += [f"| {r.variable} | {r.grupo} | {r.casos} | {r.vencidas} | {r.recall:.3f} |" for _, r in debiles.iterrows()]
    (RES / "auditoria.md").write_text("\n".join(texto) + "\n", encoding="utf-8")
    debiles.to_csv(RES / "subgrupos_debiles.csv", index=False)
    print("\n".join(texto))
    return 0 if (ok_f and ok_p and ok_s) else 1


if __name__ == "__main__":
    sys.exit(main())
