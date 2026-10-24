# Auditoría: fuga de datos, partición y subgrupos

Generado por `python auditoria.py`.

## Fuga de datos: sin problemas

- Variables del modelo que se conocen después de radicar: ninguna.
- Candidatos con preprocesamiento fuera del Pipeline: ninguno. La codificación y el escalado se ajustan dentro de cada pliegue.
- Demostración: con `dias_habiles` como variable la AP sube a 1.000; sin ella es 0.122. Esa es la cifra que daría un modelo con fuga.

## Partición: sin problemas

- Radicados presentes en desarrollo y en prueba a la vez: 0.
- Último radicado de desarrollo: 31/12/2024. Primero de prueba: 02/01/2025.
- Desarrollo ordenado por fecha para la validación temporal: sí.
- Precisión promedio (AP) con validación aleatoria y con validación temporal:

| Modelo | Hiperparámetros | AP aleatoria | AP temporal | Diferencia |
|---|---|---|---|---|
| Siempre a tiempo | - | 0.093 | 0.083 | +0.010 |
| Línea base | C=1.0 | 0.162 | 0.135 | +0.026 |
| Regresión logística | C=0.01 | 0.233 | 0.169 | +0.064 |
| Regresión logística | C=0.1 | 0.239 | 0.173 | +0.067 |
| Regresión logística | C=1.0 | 0.239 | 0.175 | +0.064 |
| Random Forest | min_samples_leaf=5 | 0.314 | 0.149 | +0.165 |
| Random Forest | min_samples_leaf=50 | 0.275 | 0.165 | +0.110 |
| Gradient boosting | max_depth=3 | 0.255 | 0.167 | +0.088 |
| Gradient boosting | max_depth=6 | 0.277 | 0.158 | +0.119 |

- Con validación aleatoria ganaría Random Forest (min_samples_leaf=5).
- AP en 2025 de Random Forest (min_samples_leaf=5) entrenado con 2022-2024: 0.035. Revisar al azar daría 0.019.
- AP en 2025 de Regresión logística (C=1.0) entrenado con 2022-2024: 0.090. Revisar al azar daría 0.019.

## Subgrupos

- Recall global de la alerta en 2025: 0.523.
- Grupos con al menos 100 casos y 10 vencidas cuyo recall está 15 puntos o más por debajo: 6.
- Grupos con muestra pequeña (menos de 100 casos o menos de 10 vencidas): 18. Sus cifras no se interpretan.

| Variable | Grupo | Casos | Vencidas | Recall |
|---|---|---|---|---|
| localidad | ALCALDIA LOCAL DE USAQUEN | 640 | 15 | 0.000 |
| localidad | ALCALDIA LOCAL DE FONTIBON | 515 | 26 | 0.154 |
| localidad | ALCALDIA LOCAL DE RAFAEL URIBE URIBE | 384 | 17 | 0.294 |
| localidad | ALCALDIA LOCAL DE BOSA | 340 | 24 | 0.083 |
| medio_recepcion | Ventanilla CDI | 7056 | 44 | 0.341 |
| medio_recepcion | Correo | 1441 | 23 | 0.348 |
