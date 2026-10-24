# Fuente de los datos

Conjunto: Peticiones, Quejas, Reclamos y Soluciones (PQRS) 2022-2026.
Publica: Secretaría Distrital de Gobierno de Bogotá, en el portal Datos Abiertos Bogotá.
Página: https://datosabiertos.bogota.gov.co/dataset/informes-de-peticiones-quejas-reclamos-y-soluciones-pqrs-sdg
Archivo: pqrs_sdg_2022_2026.csv, 75.613 filas y 22 columnas, descargado el 23 de octubre de 2026.
Licencia del conjunto: Creative Commons Atribución-CompartirIgual 4.0 (CC BY-SA 4.0).

`peticiones_preparadas.csv` es una obra derivada de ese archivo y se comparte con la misma licencia.
Lo genera `python preparar_datos.py --descargar`.

Qué se quitó y por qué:

| Columna original | Motivo |
|---|---|
| USUARIO_ACTUAL | Trae nombres de funcionarios. Es dato personal y no aporta al modelo. |
| OBSERVACION_GENERAL, OBSERVACION_SAC | Se escriben después de responder. Usarlas sería fuga. |
| DEPENDENCIA_ACTUAL, ULTIMA_DEPENDENCIA, ESTADO_ORFEO | Describen el trámite ya hecho. Fuga. |
| RADICADO_RESPUESTA, FECHA_SEGUIMIENTO, FECHA_ASIGNACION | Posteriores a la radicación. |
| FECHA_RESPUESTA | Solo se usa para construir la etiqueta `vencida`. No es variable del modelo. |

Columnas del archivo preparado:

| Columna | Qué es |
|---|---|
| radicado | Número de radicado de entrada (no identifica a la persona) |
| fecha_radicacion, fecha_respuesta | Fechas del sistema Orfeo |
| anio | Año de radicación |
| tipo_peticion | Modalidad del derecho de petición según el sistema |
| plazo_habiles | Término legal en días hábiles registrado por el sistema (15, 10, 30, 5, 3, 1) |
| medio_recepcion | SDQS (Bogotá te escucha), ventanilla, correo, redes, teléfono |
| localidad | Alcaldía local o nivel central |
| subtema | Asunto de la petición (137 valores) |
| carga_7d | Peticiones radicadas en la misma localidad en los 7 días anteriores |
| dias_calendario_plazo | Días de calendario entre la radicación y el vencimiento (festivos y fines de semana alargan el plazo) |
| mes, dia_semana, hora | Momento de la radicación |
| tasa_localidad_180d | Proporción de respuestas tardías de la localidad entre las emitidas en los 180 días anteriores, suavizada hacia 10 % |
| tasa_tipo_180d | Lo mismo para el tipo de petición |
| dias_habiles | Días hábiles que tardó la respuesta (solo para la etiqueta y el análisis) |
| vencida | 1 si la respuesta salió después del término legal, 0 si salió a tiempo |
