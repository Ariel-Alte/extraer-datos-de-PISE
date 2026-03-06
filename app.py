import streamlit as st
import camelot
import pdfplumber
import pandas as pd
import re, os, tempfile, io

# 🔹 Fondo personalizado
page_bg_img = f"""
<style>
[data-testid="stAppViewContainer"] {{
    background-image: url("https://raw.githubusercontent.com/Ariel-Alte/extraer-datos-de-PISE/main/0006.jpg");
    background-size: cover;
    background-repeat: no-repeat;
    background-attachment: fixed;
}}
</style>
"""
st.markdown(page_bg_img, unsafe_allow_html=True)

# 🔹 Función para extraer encabezado
def extraer_encabezado(uploaded_file):
    encabezado_info = {}
    with pdfplumber.open(uploaded_file) as pdf:
        primera_pagina = pdf.pages[0]
        texto = primera_pagina.extract_text()

        # Buscar patrones comunes
        match_fecha = re.search(r"Fecha:\s*(\d{2}/\d{2}/\d{4})", texto)
        match_informe = re.search(r"Informe N°:\s*(\d+)", texto)
        match_inspeccion = re.search(r"Inspección N°:\s*(\d+)", texto)
        match_linea = re.search(r"LÍNEA\s+([A-ZÁÉÍÓÚÑ ]+)", texto)

        encabezado_info["Fecha"] = match_fecha.group(1) if match_fecha else ""
        encabezado_info["Informe N°"] = match_informe.group(1) if match_informe else ""
        encabezado_info["Inspección N°"] = match_inspeccion.group(1) if match_inspeccion else ""
        encabezado_info["Línea"] = match_linea.group(1).strip() if match_linea else ""

    return encabezado_info

# 🔹 Función para procesar tablas
def procesar_pdf(uploaded_file):
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, uploaded_file.name)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    tablas = camelot.read_pdf(path, pages='all', flavor='lattice', strip_text='\n')
    if len(tablas) == 0:
        tablas = camelot.read_pdf(path, pages='all', flavor='stream', strip_text='\n')

    registros = []
    for tabla in tablas:
        df = tabla.df.copy()
        if df.shape[0] > 3:
            encabezado = df.iloc[:3].fillna('').agg(' '.join).str.replace(r'\s+', ' ', regex=True).str.strip()
            df.columns = encabezado
            df = df.iloc[3:].reset_index(drop=True)

        texto_tabla = tabla.df.to_string().lower()
        match_bogie = re.search(r"bogie\s*(\d)", texto_tabla)
        bogie_detectado = match_bogie.group(1) if match_bogie else "¿?"
        columnas = list(df.columns)

        for idx, fila in df.iterrows():
            if len(fila) < 2:
                continue
            item = str(fila.iloc[0]).strip()
            descripcion = str(fila.iloc[1]).strip()
            if not re.match(r"^\d+(\.\d+)*$", item):
                continue

            match_valor_esperado = re.search(r"\((.*?)\)", descripcion)
            valor_esperado = match_valor_esperado.group(1) if match_valor_esperado else ""

            if len(fila) < 3:
                continue
            for i in range(2, len(columnas)):
                valor_crudo = str(fila.iloc[i]).strip()
                if not valor_crudo:
                    continue

                nombre_col = str(columnas[i])
                match_rueda = re.search(r"RUEDA\s*(\d+)", nombre_col, re.IGNORECASE)
                match_lado = re.search(r"\((D|I)\)|LADO\s*(PAR|IMPAR)", nombre_col, re.IGNORECASE)
                lado_col = match_lado.group(1) if match_lado else (match_lado.group(2) if match_lado else "")
                rueda_col = match_rueda.group(1) if match_rueda else ""

                ubicacion_match = re.search(r"\b(INTERNO|EXTERNO|LADO\s*PAR|LADO\s*IMPAR)\b", valor_crudo, re.IGNORECASE)
                ubicacion = ubicacion_match.group(1).upper() if ubicacion_match else ""
                valor_limpio = re.sub(r"\b(INTERNO|EXTERNO|LADO\s*PAR|LADO\s*IMPAR)\b", '', valor_crudo, flags=re.IGNORECASE).strip()

                valores_separados = re.split(r"\s{2,}|\s+", valor_limpio)
                for j, subvalor in enumerate(valores_separados):
                    subvalor = subvalor.strip()
                    if not subvalor:
                        continue
                    rueda_auto = rueda_col if rueda_col else str(j + 1)
                    lado_auto = lado_col if lado_col else ("D" if j % 2 == 0 else "I")

                    registros.append({
                        "Ítem técnico": item,
                        "Descripción": descripcion,
                        "Bogie": bogie_detectado,
                        "Rueda": rueda_auto,
                        "Lado": lado_auto,
                        "Ubicación": ubicacion,
                        "Valor esperado": valor_esperado,
                        "Valor medido": subvalor
                    })

    df_final = pd.DataFrame(registros)
    return df_final

# 🔹 Interfaz principal
def main():
    st.markdown(
        """
        <h1 style='color: white; text-align: center; background-color: #333333;
                   padding: 12px; border-radius: 8px; border: 2px solid black;'>
            Extraer datos de informes estáticos PISE
        </h1>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <h3 style='color: yellow; background-color: #333333; padding: 8px;
                   border: 1px solid orange;'>
            📂 Subir solo informe del tipo preliminar
        </h3>
        """,
        unsafe_allow_html=True
    )

    uploaded_file = st.file_uploader("Subir el informe de una unidad en PDF Preliminar", type="pdf")
    if uploaded_file is not None:
        df_final = procesar_pdf(uploaded_file)

        # Extraer encabezado
        encabezado = extraer_encabezado(uploaded_file)
        for clave, valor in encabezado.items():
            df_final[clave] = valor

        # Agregar nombre del archivo
        df_final["Nombre del archivo"] = uploaded_file.name

        st.write("Vista previa de los datos extraídos:")
        st.dataframe(df_final.head())

        # Exportar a Excel en memoria
        buffer = io.BytesIO()
        df_final.to_excel(buffer, index=False, engine="openpyxl")
        buffer.seek(0)

        st.download_button(
            label="Descargar Excel",
            data=buffer,
            file_name="PISE.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if __name__ == "__main__":
    main()
