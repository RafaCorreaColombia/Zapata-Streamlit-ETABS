import streamlit as st
import pandas as pd
import numpy as np

# --- FUNCIONES DE UTILIDAD ---
def encontrar_columna(lista_columnas, keywords):
    """Busca una columna que contenga alguna de las palabras clave."""
    for col in lista_columnas:
        for key in keywords:
            if key.lower() in col.lower():
                return col
    return None

def procesar_csv_etabs(file):
    """Lee el CSV saltando la tabla de título y manejando las unidades."""
    # ETABS suele tener: Fila 0: Título, Fila 1: Headers, Fila 2: Unidades
    df = pd.read_csv(file, skiprows=1)
    
    # Extraer fila de unidades (es la primera fila de datos tras el skip)
    unidades = df.iloc[0].to_dict()
    
    # Limpiar el dataframe: quitar la fila de unidades y convertir a números
    df = df.drop(0).reset_index(drop=True)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='ignore')
    
    return df, unidades

# --- INTERFAZ STREAMLIT ---
st.set_page_config(page_title="Zapata Inteligente ETABS", layout="wide")
st.title("🏗️ Diseñador de Zapatas Combinadas")

# Sidebar
st.sidebar.header("Configuración Geotécnica")
q_adm = st.sidebar.number_input("Esfuerzo Admisible (kN/m²)", value=250.0)
factor_h = st.sidebar.slider("Relación H vs Distancia Ejes (1/X)", 8, 15, 10)

# Carga de archivos
col_u1, col_u2 = st.columns(2)
with col_u1:
    file_reacciones = st.file_uploader("1. Reacciones (CSV de ETABS)", type="csv")
with col_u2:
    file_coords = st.file_uploader("2. Coordenadas (CSV de ETABS)", type="csv")

if file_reacciones and file_coords:
    # Procesar archivos
    df_r, unit_r = procesar_csv_etabs(file_reacciones)
    df_c, unit_c = procesar_csv_etabs(file_coords)

    # Identificar columnas automáticamente
    # Para reacciones
    col_nodo_r = encontrar_columna(df_r.columns, ['label', 'node', 'joint'])
    col_comb = encontrar_columna(df_r.columns, ['combo', 'case', 'load'])
    col_fz = encontrar_columna(df_r.columns, ['fz', 'vertical', 'p '])
    col_mx = encontrar_columna(df_r.columns, ['mx'])
    col_my = encontrar_columna(df_r.columns, ['my'])

    # Para coordenadas
    col_nodo_c = encontrar_columna(df_c.columns, ['label', 'node', 'joint'])
    col_x = encontrar_columna(df_c.columns, ['x'])
    col_y = encontrar_columna(df_c.columns, ['y'])

    st.info(f"Detectado: Nodos en col '{col_nodo_r}', Cargas en '{col_fz}', Unidades: {unit_r.get(col_fz)}")

    # --- ENTORNO DE TRABAJO ---
    st.markdown("### Configuración de la Zapata")
    
    c1, c2 = st.columns(2)
    with c1:
        nodos_sel = st.multiselect("Nodos de las 2 columnas:", df_c[col_nodo_c].unique())
    with c2:
        combs_sel = st.multiselect("Combinaciones de Servicio:", df_r[col_comb].unique())

    if len(nodos_sel) == 2 and combs_sel:
        # 1. Extraer Coordenadas
        p1 = df_c[df_c[col_nodo_c] == nodos_sel[0]][[col_x, col_y]].values[0]
        p2 = df_c[df_c[col_nodo_c] == nodos_sel[1]][[col_x, col_y]].values[0]
        
        # Calcular distancia y ángulo para transformación
        dist_ejes = np.linalg.norm(p2 - p1)
        # Si las unidades son mm, pasar a m
        if unit_c.get(col_x) == 'mm': dist_ejes /= 1000.0
            
        st.write(f"**Distancia entre ejes:** {dist_ejes:.2f} m")

        # 2. Predimensionamiento H
        H_preliminar = dist_ejes / factor_h
        q_neto = q_adm - (24.0 * H_preliminar)
        st.write(f"**H preliminar:** {H_preliminar:.2f} m | **Q neto:** {q_neto:.2f} kN/m²")

        # Aquí seguiría tu lógica de:
        # - Sumar P de ambos nodos para cada combinación
        # - Calcular excentricidad para centrar la resultante
        # - Ajustar L y B para que sigma < q_neto
