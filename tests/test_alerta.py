"""Pruebas de la función que usa la interfaz: entrada válida, entradas inválidas y avisos."""
from datetime import datetime

import pytest

from src.alerta import LIMITACIONES, evaluar

VALIDA = dict(tipo_peticion="DERECHO DE PETICION DE INFORMACIONES", medio_recepcion="SDQS",
              localidad="ALCALDIA LOCAL DE KENNEDY", subtema="INFORMACIÓN DE TRÁMITES Y SERVICIOS",
              fecha_radicacion=datetime(2025, 12, 19, 15), carga_7d=40)


def test_evaluar_devuelve_probabilidad_y_vencimiento():
    r = evaluar(**VALIDA)
    assert 0.0 <= r["probabilidad"] <= 1.0
    assert r["plazo_habiles"] == 10
    assert str(r["fecha_vencimiento"]) == "2026-01-06"


@pytest.mark.parametrize("cambio", [
    {"tipo_peticion": "ACCION DE TUTELA"},
    {"fecha_radicacion": datetime(2022, 4, 1)},
    {"carga_7d": -3},
])
def test_rechaza_entrada_invalida(cambio):
    with pytest.raises(ValueError):
        evaluar(**(VALIDA | cambio))


def test_avisa_en_localidades_donde_la_alerta_falla():
    r = evaluar(**(VALIDA | {"localidad": "ALCALDIA LOCAL DE USAQUEN"}))
    assert any("USAQUEN" in a for a in r["avisos"])


def test_las_limitaciones_dicen_para_que_no_se_usa():
    assert "No decide" in LIMITACIONES and "funcionarios" in LIMITACIONES


def test_avisa_cuando_el_historial_no_cubre_la_fecha():
    r = evaluar(**(VALIDA | {"fecha_radicacion": datetime(2026, 12, 1, 10)}))
    assert any("historial" in a for a in r["avisos"])
