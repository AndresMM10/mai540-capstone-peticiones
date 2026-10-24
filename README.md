# Alerta de vencimiento de derechos de petición

Estima, en el momento de radicar un derecho de petición en la Secretaría Distrital de Gobierno de Bogotá o en una alcaldía local, la probabilidad de que la respuesta salga después del término legal. Sirve para que la oficina de atención a la ciudadanía revise primero las peticiones con más riesgo.

Proyecto capstone de MAI 540 Machine Learning, Atlantis University. Autor: Andrés Moreno.

## Problema

La Ley 1755 de 2015 da 15 días hábiles para responder una petición, 10 si pide documentos o información y 30 si es una consulta. Cuando el término vence sin respuesta de fondo, la persona puede presentar una acción de tutela y la entidad queda expuesta a una investigación disciplinaria. Entre mayo de 2022 y diciembre de 2024, el 9,3 % de las peticiones de esta base se respondió tarde.

La herramienta apoya una sola decisión: en qué orden revisar las peticiones recién radicadas. La usaría quien coordina la atención a la ciudadanía o el área jurídica de una alcaldía local. No decide nada sobre la petición ni sobre quien la presentó.

## Datos

- **Fuente:** [PQRS 2022-2026 de la Secretaría Distrital de Gobierno](https://datosabiertos.bogota.gov.co/dataset/informes-de-peticiones-quejas-reclamos-y-soluciones-pqrs-sdg), portal Datos Abiertos Bogotá. Descargado el 23 de octubre de 2026.
- **Permiso de uso:** Creative Commons Atribución-CompartirIgual 4.0. El archivo preparado de este repositorio es obra derivada y se comparte con la misma licencia.
- **Descripción:** el archivo original tiene 75.613 radicados y 22 columnas. Después de los filtros quedan 53.870. La variable objetivo `vencida` vale 1 cuando los días hábiles entre la radicación y la respuesta superan el término legal registrado por el sistema. Los días hábiles se cuentan desde el día siguiente a la radicación y excluyen sábados, domingos y festivos de Colombia.

Filtros, en orden:

1. Solo radicados desde el 18 de mayo de 2022 (se excluyen 3.053). Antes regía la ampliación de términos del Decreto 491 de 2020, derogada por la Ley 2207 del 17 de mayo de 2022.
2. Solo peticiones con tipo y término legal registrados (se excluyen 16.153).
3. Solo radicados con fecha de respuesta (se excluyen 2.369 que siguen en gestión).
4. Se descartan 168 respuestas con fecha anterior a la radicación, que son errores de registro.

El modelo solo usa lo que se sabe al radicar: tipo de petición, término, medio de recepción, localidad, subtema, carga de la localidad en los 7 días anteriores, días de calendario hasta el vencimiento, mes, día de la semana, hora y dos tasas recientes:

- `tasa_localidad_180d`: proporción de respuestas tardías de la misma localidad entre las emitidas en los 180 días anteriores a la radicación.
- `tasa_tipo_180d`: lo mismo para el tipo de petición.

Las dos tasas solo cuentan respuestas con fecha anterior a la radicación, que es lo que la oficina ya sabe ese día. Se suavizan hacia 10 % con el peso de 10 respuestas para que un grupo pequeño no salte a 0 % o a 100 %. Las columnas que se llenan después de radicar (dependencia actual, observaciones, estado) y la que trae nombres de funcionarios no están en el archivo preparado. El detalle está en [datos/FUENTE.md](datos/FUENTE.md).

## Cómo funciona

```
CSV del portal ──> preparar_datos.py ──> datos/peticiones_preparadas.csv
                                              │
                                              ├──> entrenar.py ──> modelos/modelo.joblib + resultados/
                                              ├──> auditoria.py ──> resultados/auditoria.md
                                              └──> app.py (Gradio) ──> probabilidad, fecha de vencimiento y avisos
```

`src/datos.py` calcula días hábiles, la etiqueta y las variables. `src/modelo.py` define los candidatos y la validación. `src/alerta.py` evalúa una petición nueva: calcula el término, la fecha de vencimiento y las tasas recientes a partir del historial, y aplica el modelo. La usan la interfaz, el cuaderno y las pruebas.

La validación es temporal: los datos de 2022 a 2024 se ordenan por fecha y cada uno de los 5 pliegues entrena con el pasado y valida con el periodo siguiente. 2025 queda aparte como prueba final y no se usó para elegir nada. 2026 se reporta como monitoreo, con cautela, porque muchos radicados de ese año siguen abiertos.

## Resultados

Métrica principal: precisión promedio (AP), que mide qué tan arriba quedan las peticiones vencidas en la lista ordenada por riesgo. También se reporta qué parte de las vencidas cae en el 20 % de peticiones con más riesgo.

| Modelo | AP (media ± desviación) | Vencidas en el 20 % con más riesgo | Observación |
|---|---|---|---|
| Siempre a tiempo | 0,083 ± 0,020 | 19,9 % | Equivale a revisar al azar |
| Línea base: tipo y canal | 0,135 ± 0,033 | 33,1 % | Regresión logística con dos variables |
| Regresión logística, C=0,01 | **0,195 ± 0,045** | 40,7 % | **Elegido** |
| Random Forest, hoja mínima 50 | 0,190 ± 0,042 | 42,7 % | Dentro de una desviación del elegido |
| Gradient boosting, profundidad 3 | 0,168 ± 0,038 | 39,8 % | Dentro de una desviación del elegido |

Criterio de elección, fijado antes de mirar 2025: gana la mayor AP media. Si otro candidato está a menos de una desviación, gana el más simple, porque sus coeficientes se pueden explicar a un jefe jurídico. La tabla completa con las nueve configuraciones está en `resultados/comparacion_modelos.csv`. Las dos tasas recientes subieron la AP de la regresión logística de 0,175 a 0,195 en la validación temporal y de 0,090 a 0,100 en 2025.

Con el umbral de la alerta, en el periodo de desarrollo el modelo encuentra el 40,4 % de las vencidas y el 16,8 % de sus alertas son peticiones que sí se vencieron.

Prueba final en 2025 (17.206 radicados, 1,87 % vencidos). El umbral de alerta se fijó con 2022-2024 para marcar el 20 % de peticiones con más riesgo:

| Medida | Valor |
|---|---|
| AP | 0,100 (revisar al azar daría 0,019) |
| Peticiones alertadas | 10,3 % (1.772) |
| Vencidas detectadas (recall) | 42,4 %, 136 de 321 |
| Alertas que sí se vencieron (precisión) | 7,7 % |
| Vencidas en el 20 % con más riesgo de 2025 | 63,2 % |

El umbral marcó el 10,3 % de las peticiones en 2025 y no el 20 %. No se ajustó con datos de 2025 porque eso sería elegir con la prueba. Ese porcentaje es una señal de deriva: si se aleja del 20 %, la población cambió.

Errores por categoría en 2025 (`resultados/errores_por_categoria.csv`):

- Las peticiones de información son el grupo con más vencimiento (14,4 %) y la alerta encuentra 30 de 35.
- En interés particular, el grupo más grande (10.535 casos), encuentra 62 de 145. En interés general, 36 de 132.
- Por localidad: Antonio Nariño 18 de 19, Kennedy 19 de 23, Bosa 15 de 24, Suba 15 de 29. En Usaquén encuentra 1 de 15, en Fontibón 4 de 26 y en Puente Aranda 4 de 16. La interfaz muestra un aviso cuando se evalúa una de las localidades o canales débiles.
- 18 grupos tienen menos de 100 casos o menos de 10 vencidas. Sus cifras no se interpretan.

## Instalación

Requiere Python 3.10 a 3.13 y git.

```bash
git clone https://github.com/AndresMM10/mai540-capstone-peticiones.git
cd mai540-capstone-peticiones
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell no deja activar el entorno, ejecuta antes `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

El modelo entrenado y el archivo preparado ya vienen en el repositorio. No hace falta descargar nada más para usar la herramienta.

## Cómo ejecutar

La interfaz:

```bash
python app.py
```

Debe aparecer `Running on local URL: http://127.0.0.1:7860`. Abre esa dirección en el navegador. Verás el texto de limitaciones, seis campos y dos ejemplos al final. Pulsa uno de los ejemplos y luego Submit. El resultado dice si la petición va a revisión prioritaria, la probabilidad, el término legal, la fecha de vencimiento y la tasa reciente de respuestas tardías de la localidad.

Sin instalar nada: abre [demo_colab.ipynb en Colab](https://colab.research.google.com/github/AndresMM10/mai540-capstone-peticiones/blob/main/demo_colab.ipynb) y ejecuta todo (Entorno de ejecución, Ejecutar todo). La última celda muestra un enlace público temporal que termina en `gradio.live`.

Para repetir el trabajo completo desde los datos originales:

```bash
python preparar_datos.py --descargar   # baja el CSV del portal (34 MB) y lo prepara
python entrenar.py                     # compara 9 configuraciones, elige y evalúa 2025 (unos 2 minutos)
python auditoria.py                    # fuga, partición y subgrupos -> resultados/auditoria.md
```

## Pruebas

```bash
pytest -v
```

Son 18 pruebas en tres archivos. `tests/test_datos.py` comprueba el conteo de días hábiles con festivos, el límite exacto del término, los filtros de registros inválidos, que el modelo no vea columnas posteriores ni nombres de funcionarios y que la carga y las tasas recientes no usen información del futuro. `tests/test_modelo.py` comprueba que el modelo supera la línea base y el azar, que el resultado es estable entre pliegues y que la partición no mezcla fechas. `tests/test_alerta.py` comprueba la evaluación de una petición, el rechazo de entradas inválidas y el aviso por localidad. Se espera `18 passed`.

Para que las pruebas corran antes de cada commit:

```bash
python instalar_hook.py
```

## Limitaciones

- **No debe usarse** para decidir sobre una petición, para evaluar el desempeño de funcionarios o dependencias, ni para reemplazar el control de términos del gestor documental. La probabilidad ordena la revisión y nada más.
- **Precisión baja.** En 2025, de cada 100 alertas unas 8 fueron peticiones que sí se vencieron, y la alerta encontró 4 de cada 10 vencidas.
- **El mundo ya cambió.** La proporción de vencidas pasó de 12,0 % en 2022 a 1,9 % en 2025. Las tasas recientes ayudan a seguir el cambio, pero el modelo se entrenó con el periodo anterior y sigue fallando en localidades como Usaquén y Fontibón.
- **Historial.** Las tasas recientes necesitan las respuestas de los últimos 180 días. En esta versión salen del archivo preparado, que llega hasta agosto de 2026. Para fechas posteriores la tasa se queda con la última ventana disponible.
- **Etiqueta del sistema.** El término legal es el que registra el sistema de la Secretaría. No revisa suspensiones, ampliaciones del artículo 14 de la Ley 1755 ni traslados por competencia, y la fecha de respuesta puede no ser la de notificación.
- **Sin texto.** El modelo no lee la petición, solo sus metadatos. Peticiones distintas con el mismo subtema reciben un riesgo parecido.
- **Cuándo revisarlo:** cada trimestre, comparando la AP y el recall de la alerta con los radicados ya cerrados. Hay que reentrenar si el recall baja de 35 %, si el porcentaje alertado se aleja del 20 % por más de 10 puntos, si cambia la clasificación de tipos o subtemas en el sistema, o si una norma cambia los términos.

## Estructura del repositorio

```
.
├── README.md
├── requirements.txt
├── preparar_datos.py        descarga y prepara los datos
├── entrenar.py              compara, elige, evalúa y guarda el modelo
├── auditoria.py             fuga, partición y subgrupos
├── app.py                   interfaz Gradio
├── demo_colab.ipynb         demo en Colab
├── instalar_hook.py
├── hooks/pre-commit         ejecuta pytest antes de cada commit
├── datos/                   archivo preparado y FUENTE.md
├── modelos/modelo.joblib    modelo elegido y umbral
├── resultados/              tablas, gráfico de degradación y auditoría
├── evidencia/               capturas y salidas guardadas
├── src/                     datos.py, modelo.py, evaluacion.py, alerta.py
└── tests/                   18 pruebas con pytest
```

## Autor

Andrés Moreno. MAI 540 Machine Learning, profesor Kevin A. García Gallardo. Atlantis University, octubre de 2026.
