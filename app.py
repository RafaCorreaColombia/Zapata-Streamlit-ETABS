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


# --- En app.py ---

st.subheader("Configuración de Ubicación (D+L)")
comb_ubicacion = st.selectbox("Seleccione la combinación para ubicar la zapata (Permanentes):", combs_sel)

if st.button("Calcular Ubicación Óptima"):
    # 1. Filtrar reacciones para los 2 nodos y la combinación elegida
    datos_c1 = df_r[(df_r[col_nodo_r] == nodos_sel[0]) & (df_r[col_comb] == comb_ubicacion)].iloc[0]
    datos_c2 = df_r[(df_r[col_nodo_r] == nodos_sel[1]) & (df_r[col_comb] == comb_ubicacion)].iloc[0]
    
    # 2. Obtener coordenadas
    coord_1 = df_c[df_c[col_nodo_c] == nodos_sel[0]][[col_x, col_y]].values[0]
    coord_2 = df_c[df_c[col_nodo_c] == nodos_sel[1]][[col_x, col_y]].values[0]
    
    # 3. Ejecutar motor de cálculo
    resultados = procesar_geometria_y_cargas(
        coord_1, coord_2, 
        {'FZ': datos_c1[col_fz], 'MX': datos_c1[col_mx], 'MY': datos_c1[col_my]},
        {'FZ': datos_c2[col_fz], 'MX': datos_c2[col_mx], 'MY': datos_c2[col_my]}
    )
    
    st.write(f"### Resultados de Ubicación")
    st.success(f"La resultante de la combinación '{comb_ubicacion}' se encuentra a **{resultados['x_resultante']:.3f} m** del Nodo {nodos_sel[0]}.")
    
    # Sugerencia de longitud de zapata para que quede centrada
    dist_al_borde = max(resultados['x_resultante'], resultados['L_ejes'] - resultados['x_resultante'])
    L_min = dist_al_borde * 2
    st.info(f"Para que la zapata esté centrada con la carga permanente, debería medir al menos **L = {L_min:.2f} m**.")     
    



st.subheader("Configuración de Bordes")
col_b1, col_b2 = st.columns(2)
with col_b1:
    es_borde_1 = st.checkbox(f"Columna {nodos_sel[0]} es de borde")
with col_b2:
    es_borde_2 = st.checkbox(f"Columna {nodos_sel[1]} es de borde")

# Si es de borde, forzamos que la distancia del nodo al extremo de la zapata 
# sea exactamente t3/2 + recubrimiento (si aplica)
if es_borde_1:
    voladizo_izq = geom_c1['t3'] / 2
    st.info(f"Límite izquierdo fijado en {voladizo_izq} m")



import engine # Importas tu lógica

# ... después de obtener los datos de ETABS ...
if st.button("Diseñar"):
    # 1. Obtener geometría de columnas
    g1 = engine.obtener_geometria_columna(nodo1, df_conn, df_sum, df_sec)
    g2 = engine.obtener_geometria_columna(nodo2, df_conn, df_sum, df_sec)
    
    # 2. Procesar cargas y ubicación
    res_ub = engine.procesar_geometria_y_cargas(p1, p2, reac1, reac2)
    
    # 3. Calcular secciones y optimizar
    L_zapata = res_ub['x_resultante'] * 2 # Para que sea centrada
    B_optimo = engine.optimizar_ancho_B(L_zapata, res_ub['R_total'], 0, q_neto, max(g1['t2'], g2['t2']))
    
    st.success(f"Dimensiones sugeridas: L={L_zapata:.2f}m, B={B_optimo:.2f}m")



