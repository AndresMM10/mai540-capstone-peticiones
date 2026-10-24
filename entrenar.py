"""Entrena, valida y evalúa el modelo de alerta de vencimiento.

Uso:
    python entrenar.py            # validación temporal, elección, prueba 2025, errores y degradación
    python entrenar.py --rapido   # solo la regresión logística elegida, sin comparar (para la demo)

Salidas:
    modelos/modelo.joblib                  el modelo elegido, su umbral y sus metadatos
    resultados/comparacion_modelos.csv     media y desviación de cada candidato (validación temporal)
    resultados/comparacion_aleatoria.csv   lo mismo con validación aleatoria (para la auditoría)
    resultados/metricas_prueba.json        resultado en 2025 y en 2026
    resultados/errores_por_categoria.csv   errores por localidad, tipo y canal en 2025
    resultados/degradacion.csv y .png      métricas por año
    resultados/coeficientes.csv            variables que más pesan en la regresión logística
"""
import argparse
import json
from datetime import date
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.datos import OBJETIVO, VARIABLES, cargar_preparado, particion_temporal
from src.evaluacion import errores_por_categoria, por_periodo, subgrupos_debiles
from src.modelo import (FRACCION_ALERTA, comparar, construir, elegir, metricas, umbral_alerta,
                        validar)

RAIZ = Path(__file__).resolve().parent
RES = RAIZ / "resultados"
RUTA_MODELO = RAIZ / "modelos" / "modelo.joblib"
ELEGIDO_POR_DEFECTO = ("Regresión logística", "C=0.01")


def coeficientes(pipe) -> pd.DataFrame:
    nombres = pipe.named_steps["prep"].get_feature_names_out()
    coef = pipe.named_steps["modelo"].coef_[0]
    tabla = pd.DataFrame({"variable": nombres, "coeficiente": coef})
    tabla["variable"] = tabla["variable"].str.replace("cat__", "").str.replace("num__", "")
    return tabla.reindex(tabla["coeficiente"].abs().sort_values(ascending=False).index)


def grafico_degradacion(tabla: pd.DataFrame, ruta: Path):
    fig, ejes = plt.subplots(1, 2, figsize=(10, 3.8))
    anios = tabla["anio"].astype(str)
    ejes[0].bar(anios, tabla["tasa_vencidas"] * 100, color="#4a6fa5")
    ejes[0].set_title("Peticiones respondidas fuera de término (%)")
    etiquetas = [f"{a}*" if a in (2022, 2026) else str(a) for a in tabla["anio"]]
    ejes[1].plot(etiquetas, tabla["recall"] * 100, marker="o", color="#4a6fa5", label="Vencidas detectadas (recall)")
    ejes[1].plot(etiquetas, tabla["precision"] * 100, marker="s", color="#c0504d", label="Alertas correctas (precisión)")
    ejes[1].set_ylim(0, 100)
    ejes[1].set_title("Alerta con el mismo umbral, por año (%)")
    ejes[1].legend(fontsize=8)
    for eje in ejes:
        eje.spines[["top", "right"]].set_visible(False)
    fig.text(0.5, 0.01, "*2022: solo radicados con predicción fuera de pliegue.   *2026: año abierto, muchos radicados siguen en gestión.",
             ha="center", fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rapido", action="store_true")
    args = parser.parse_args()
    RES.mkdir(exist_ok=True)
    RUTA_MODELO.parent.mkdir(exist_ok=True)

    df = cargar_preparado()
    desarrollo, prueba = particion_temporal(df)
    posterior = df[df["anio"] > 2025]
    print(f"Desarrollo 2022-2024: {len(desarrollo):,} radicados, {desarrollo[OBJETIVO].mean():.2%} vencidos")
    print(f"Prueba 2025:          {len(prueba):,} radicados, {prueba[OBJETIVO].mean():.2%} vencidos")

    if args.rapido:
        modelo, hiper = ELEGIDO_POR_DEFECTO
    else:
        tabla = comparar(desarrollo, temporal=True)
        tabla.to_csv(RES / "comparacion_modelos.csv", index=False)
        comparar(desarrollo, temporal=False).to_csv(RES / "comparacion_aleatoria.csv", index=False)
        cols = ["modelo", "hiperparametros", "ap_media", "ap_desv", "recall_alerta_media", "f1_media", "f1_desv"]
        print("\nValidación cruzada temporal (5 pliegues), media y desviación:")
        print(tabla[cols].round(3).to_string(index=False))
        ganador = elegir(tabla)
        modelo, hiper = ganador["modelo"], ganador["hiperparametros"]
    print(f"\nModelo elegido: {modelo} ({hiper})")

    pipe = construir(modelo, hiper)
    resumen, fuera = validar(pipe, desarrollo, temporal=True)
    umbral = umbral_alerta(fuera)
    pipe.fit(desarrollo[VARIABLES], desarrollo[OBJETIVO])

    p_prueba = pipe.predict_proba(prueba[VARIABLES])[:, 1]
    p_post = pipe.predict_proba(posterior[VARIABLES])[:, 1]
    resultado = {
        "modelo": modelo,
        "hiperparametros": hiper,
        "umbral_alerta": umbral,
        "fraccion_alerta_objetivo": FRACCION_ALERTA,
        "validacion_temporal": resumen,
        "validacion_temporal_en_umbral": metricas(desarrollo[OBJETIVO][~np.isnan(fuera)], fuera[~np.isnan(fuera)], umbral),
        "prueba_2025": metricas(prueba[OBJETIVO], p_prueba, umbral)
        | {"casos": len(prueba), "tasa_vencidas": prueba[OBJETIVO].mean(), "alertadas": float((p_prueba >= umbral).mean())},
        "monitoreo_2026": metricas(posterior[OBJETIVO], p_post, umbral)
        | {"casos": len(posterior), "tasa_vencidas": posterior[OBJETIVO].mean(), "alertadas": float((p_post >= umbral).mean())},
    }
    (RES / "metricas_prueba.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False))
    print(json.dumps({k: resultado[k] for k in ("umbral_alerta", "prueba_2025", "monitoreo_2026")}, indent=2))

    errores = pd.concat([errores_por_categoria(prueba, p_prueba, umbral, c)
                         for c in ("localidad", "tipo_peticion", "medio_recepcion")])
    errores.to_csv(RES / "errores_por_categoria.csv", index=False)
    debiles = subgrupos_debiles(errores, resultado["prueba_2025"]["recall"])
    print(f"\nGrupos con muestra suficiente y recall 15 puntos por debajo del global: {len(debiles)}")
    print(debiles[["variable", "grupo", "casos", "vencidas", "recall"]].round(3).to_string(index=False))

    p_todo = np.concatenate([fuera, p_prueba, p_post])
    periodos = pd.concat([desarrollo, prueba, posterior])
    degr = por_periodo(periodos, p_todo, umbral)
    degr.to_csv(RES / "degradacion.csv", index=False)
    grafico_degradacion(degr, RES / "degradacion.png")
    print("\nPor año (2022-2024 fuera de pliegue, 2025 prueba, 2026 monitoreo):")
    print(degr.round(3).to_string(index=False))

    if modelo == "Regresión logística":
        coeficientes(pipe).to_csv(RES / "coeficientes.csv", index=False)

    joblib.dump({
        "pipeline": pipe, "umbral": umbral, "modelo": modelo, "hiperparametros": hiper,
        "variables": VARIABLES, "tasa_vencidas_desarrollo": float(desarrollo[OBJETIVO].mean()),
        "entrenado": date.today().isoformat(), "periodo": "radicados del 18/05/2022 al 31/12/2024",
    }, RUTA_MODELO)
    print(f"\nModelo guardado en {RUTA_MODELO}")


if __name__ == "__main__":
    main()
