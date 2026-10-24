"""Pruebas de la preparación de datos: días hábiles, etiqueta, fuga y datos personales."""
import pandas as pd

from src.datos import (COLUMNAS_POSTERIORES, VARIABLES, carga_previa, cargar_preparado, dias_habiles,
                       fecha_vencimiento, preparar)


def _crudo(radicacion, respuesta, tipo="DERECHO DE PETICION EN INTERES GENERAL", plazo="15"):
    """Una fila con el formato exacto del archivo del portal."""
    fila = {c: "x" for c in ["RADICADO", "MEDIO_RECEPCION", "NOMBRE_LOCALIDAD", "SUBTEMA", *COLUMNAS_POSTERIORES]}
    fila.update({"RADICADO": "1", "RADI_FECH_RADI": radicacion, "FECHA_RESPUESTA": respuesta,
                 "TIPO_PETICION": tipo, "TIEMPO_TRAMITE": plazo, "USUARIO_ACTUAL": "NOMBRE DE UN FUNCIONARIO"})
    return pd.DataFrame([fila])


def test_dias_habiles_excluye_fines_de_semana_y_festivos():
    # Radicada el viernes 2 de enero de 2026. El lunes 12 es festivo (Reyes, trasladado).
    # Del lunes 5 al martes 13 hay 6 días hábiles: 5, 6, 7, 8, 9 y 13.
    assert dias_habiles(["2026-01-02"], ["2026-01-13"])[0] == 6


def test_fecha_vencimiento_salta_festivos_de_fin_de_anio():
    # 10 días hábiles desde el viernes 19 de diciembre de 2025: el 25 y el 1 de enero no cuentan.
    assert fecha_vencimiento(pd.Timestamp("2025-12-19 15:00"), 10) == pd.Timestamp("2026-01-06")


def test_respuesta_el_ultimo_dia_no_esta_vencida():
    # 15 días hábiles exactos no es vencimiento. 16 sí.
    a_tiempo = preparar(_crudo("01/07/2024 09:00:00", "22/07/2024 16:00:00"))
    tarde = preparar(_crudo("01/07/2024 09:00:00", "23/07/2024 16:00:00"))
    assert a_tiempo.loc[0, "dias_habiles"] == 15 and a_tiempo.loc[0, "vencida"] == 0
    assert tarde.loc[0, "dias_habiles"] == 16 and tarde.loc[0, "vencida"] == 1


def test_descarta_registros_invalidos_y_anteriores_a_la_ley_2207():
    casos = pd.concat([
        _crudo("01/07/2024 09:00:00", "28/06/2024 10:00:00"),              # respuesta antes de radicar
        _crudo("02/05/2022 09:00:00", "30/05/2022 10:00:00"),              # Decreto 491 aún vigente
        _crudo("01/07/2024 09:00:00", "", ),                               # sin respuesta todavía
        _crudo("01/07/2024 09:00:00", "05/07/2024 10:00:00", plazo="0"),   # sin plazo legal
    ], ignore_index=True)
    assert preparar(casos).empty


def test_el_modelo_no_ve_columnas_posteriores_ni_datos_personales():
    df = cargar_preparado()
    # fecha_respuesta se conserva solo para construir la etiqueta. Las demás posteriores no están.
    for columna in COLUMNAS_POSTERIORES:
        if columna != "FECHA_RESPUESTA":
            assert columna.lower() not in df.columns
    assert "dias_habiles" not in VARIABLES and "fecha_respuesta" not in VARIABLES
    salida = preparar(_crudo("01/07/2024 09:00:00", "05/07/2024 10:00:00"))
    assert "NOMBRE DE UN FUNCIONARIO" not in salida.astype(str).to_numpy()


def test_carga_no_mira_el_futuro():
    fechas = pd.Series(pd.to_datetime(["2024-03-01", "2024-03-03", "2024-03-05"]))
    grupos = pd.Series(["A", "A", "A"])
    antes = carga_previa(fechas, grupos)
    # Agregar peticiones posteriores no cambia la carga de las anteriores.
    mas = pd.Series(pd.to_datetime(["2024-03-01", "2024-03-03", "2024-03-05", "2024-03-06", "2024-03-06"]))
    despues = carga_previa(mas, pd.Series(["A"] * 5))
    assert list(antes) == [0, 1, 2]
    assert list(despues[:3]) == [0, 1, 2]


def test_tasa_reciente_solo_usa_respuestas_anteriores_a_la_radicacion():
    from src.datos import tasa_reciente
    historial = pd.DataFrame({
        "fecha_respuesta": pd.to_datetime(["2024-03-01", "2024-03-02", "2024-03-10"]),
        "localidad": ["A", "A", "A"],
        "vencida": [1, 1, 1],
    })
    # El 5 de marzo solo se conocen dos respuestas, ambas tardías: (2 + 10 x 0,10) / (2 + 10) = 0,25.
    # La respuesta del 10 de marzo todavía no existe y no debe contar.
    tasa = tasa_reciente(pd.Series(pd.to_datetime(["2024-03-05"])), pd.Series(["A"]), historial, "localidad")
    assert abs(tasa[0] - 0.25) < 1e-9
    # Una localidad sin historial queda en la tasa previa del 10 %.
    sin_historial = tasa_reciente(pd.Series(pd.to_datetime(["2024-03-05"])), pd.Series(["B"]), historial, "localidad")
    assert abs(sin_historial[0] - 0.10) < 1e-9
