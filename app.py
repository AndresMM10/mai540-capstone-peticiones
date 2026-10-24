"""Interfaz web local de la alerta de vencimiento de derechos de petición.

Uso:
    python app.py              # abre http://127.0.0.1:7860
    python app.py --compartir  # además crea un enlace público temporal de Gradio (72 horas máximo)
"""
import argparse
from datetime import datetime

import gradio as gr
import pandas as pd

from src.alerta import LIMITACIONES, PLAZOS, cargar_modelo, evaluar
from src.datos import cargar_preparado

DATOS = cargar_preparado()
RECIENTES = DATOS[DATOS["anio"] >= 2024]
LOCALIDADES = sorted(DATOS["localidad"].unique())
MEDIOS = list(RECIENTES["medio_recepcion"].value_counts().index)
SUBTEMAS = list(RECIENTES["subtema"].value_counts().loc[lambda s: s >= 30].index)
CARGA_TIPICA = RECIENTES.groupby("localidad")["carga_7d"].median().round().astype(int).to_dict()
MODELO = cargar_modelo()


def carga_sugerida(localidad: str) -> int:
    return CARGA_TIPICA.get(localidad, 20)


def responder(tipo, medio, localidad, subtema, fecha_texto, carga):
    try:
        fecha = datetime.strptime(fecha_texto.strip(), "%d/%m/%Y %H:%M")
    except (AttributeError, ValueError):
        return "Escribe la fecha de radicación con el formato dd/mm/aaaa hh:mm, por ejemplo 19/12/2025 15:30."
    try:
        r = evaluar(tipo, medio, localidad, subtema, fecha, int(carga))
    except (ValueError, TypeError) as error:
        return f"No se pudo evaluar: {error}"
    lineas = [
        f"## {r['nivel']}",
        f"Probabilidad estimada de responder fuera de término: **{r['probabilidad']:.0%}**",
        f"(umbral de revisión prioritaria: {MODELO['umbral']:.0%})",
        "",
        f"Término legal: {r['plazo_habiles']} días hábiles. Vence el **{r['fecha_vencimiento']:%d/%m/%Y}**.",
        f"Respuestas tardías de esta localidad en los 180 días anteriores: {r['tasa_localidad_180d']:.1%}",
    ]
    if r["avisos"]:
        lineas += ["", "Cuidado con esta predicción:"] + [f"- {a}" for a in r["avisos"]]
    lineas += ["", "_La probabilidad ordena la revisión. No dice si la respuesta va a vencer._"]
    return "\n".join(lineas)


demo = gr.Interface(
    fn=responder,
    inputs=[
        gr.Dropdown(list(PLAZOS), value="DERECHO DE PETICION EN INTERES GENERAL", label="Tipo de petición"),
        gr.Dropdown(MEDIOS, value="SDQS", label="Medio de recepción"),
        gr.Dropdown(LOCALIDADES, value="ALCALDIA LOCAL DE KENNEDY", label="Localidad o nivel central"),
        gr.Dropdown(SUBTEMAS, value=SUBTEMAS[0], label="Subtema"),
        gr.Textbox(value="19/12/2025 15:30", label="Fecha y hora de radicación (dd/mm/aaaa hh:mm)"),
        gr.Number(value=carga_sugerida("ALCALDIA LOCAL DE KENNEDY"), precision=0,
                  label="Peticiones radicadas en esa localidad en los 7 días anteriores"),
    ],
    outputs=gr.Markdown(label="Resultado"),
    title="Alerta de vencimiento de derechos de petición",
    description=f"**Antes de usarla:** {LIMITACIONES}",
    examples=[
        ["DERECHO DE PETICION DE INFORMACIONES", "SDQS", "ALCALDIA LOCAL DE KENNEDY",
         "INFORMACIÓN DE TRÁMITES Y SERVICIOS", "19/12/2025 15:30", carga_sugerida("ALCALDIA LOCAL DE KENNEDY")],
        ["DERECHO DE PETICION EN INTERES GENERAL", "Ventanilla CDI", "ALCALDIA LOCAL DE USAQUEN",
         "MANTENIMIENTO DE VÍAS INTERNAS DE LA LOCALIDAD POR DONDE NO TRANSITA EL SITP", "03/03/2025 09:00",
         carga_sugerida("ALCALDIA LOCAL DE USAQUEN")],
    ],
    flagging_mode="never",
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compartir", action="store_true")
    demo.launch(share=parser.parse_args().compartir)
