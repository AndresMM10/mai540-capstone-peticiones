"""Pruebas del modelo: supera la línea base, es estable y la partición respeta el tiempo."""
import json
from pathlib import Path

import numpy as np

from src.datos import OBJETIVO, cargar_preparado, particion_temporal
from src.modelo import candidatos, recall_en_alerta, validar

RES = Path(__file__).resolve().parent.parent / "resultados"


def test_supera_la_linea_base_en_validacion_temporal():
    tabla = json.loads((RES / "metricas_prueba.json").read_text())
    elegido = tabla["validacion_temporal"]["ap_media"]
    df = cargar_preparado()
    desarrollo, _ = particion_temporal(df)
    base, _ = validar(candidatos()["Línea base"][0], desarrollo)
    assert elegido > base["ap_media"]


def test_supera_el_azar_en_2025():
    prueba = json.loads((RES / "metricas_prueba.json").read_text())["prueba_2025"]
    # Con la alerta al azar se encontraría cerca del 20 % de las vencidas y la AP sería la tasa base.
    assert prueba["recall_alerta"] > 0.30
    assert prueba["ap"] > 2 * prueba["tasa_vencidas"]


def test_resultado_estable_entre_pliegues():
    # La AP decide la elección: su desviación no debe pasar del 30 % de su media.
    # El recall del 20 % con más riesgo se tolera hasta 0,06 de desviación entre pliegues.
    resumen = json.loads((RES / "metricas_prueba.json").read_text())["validacion_temporal"]
    assert resumen["ap_desv"] / resumen["ap_media"] < 0.30
    assert resumen["recall_alerta_desv"] < 0.06


def test_particion_temporal_sin_mezcla():
    desarrollo, prueba = particion_temporal(cargar_preparado())
    assert desarrollo["fecha_radicacion"].max() < prueba["fecha_radicacion"].min()
    assert set(desarrollo["radicado"]).isdisjoint(prueba["radicado"])
    assert prueba["anio"].eq(2025).all()


def test_recall_en_alerta_de_un_modelo_constante_es_el_azar():
    rng = np.random.default_rng(0)
    y = (rng.random(5000) < 0.1).astype(int)
    assert abs(recall_en_alerta(y, np.zeros(5000)) - 0.20) < 0.03
