"""Descarga el archivo de PQRS del portal de Datos Abiertos Bogotá y genera el conjunto preparado.

Uso:
    python preparar_datos.py --descargar   # baja el CSV original (34 MB) y prepara
    python preparar_datos.py               # solo prepara, si el CSV ya está en datos/
"""
import argparse
import urllib.request

from src.datos import RUTA_CRUDA, RUTA_PREPARADA, URL_FUENTE, leer_crudo, preparar


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--descargar", action="store_true", help="descarga el CSV original antes de preparar")
    args = parser.parse_args()
    if args.descargar:
        RUTA_CRUDA.parent.mkdir(exist_ok=True)
        print(f"Descargando {URL_FUENTE}")
        urllib.request.urlretrieve(URL_FUENTE, RUTA_CRUDA)
    crudo = leer_crudo()
    df = preparar(crudo)
    df.to_csv(RUTA_PREPARADA, index=False)
    print(f"Filas en el archivo original: {len(crudo):,}")
    print(f"Filas preparadas:             {len(df):,}")
    print(f"Proporción vencidas:          {df['vencida'].mean():.4f}")
    print(df.groupby("anio")["vencida"].agg(["size", "mean"]).round(4).to_string())
    print(f"Guardado en {RUTA_PREPARADA}")


if __name__ == "__main__":
    main()
