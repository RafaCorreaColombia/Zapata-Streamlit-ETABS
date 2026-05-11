import streamlit as st
import pandas as pd
import numpy as np
import engine  # Asegúrate de que engine.py esté en la misma carpeta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Zapata Inteligente ETABS", layout="wide")
st.title("🏗️ Diseñador de Zapatas Combinadas")

# --- FUNCIONES DE UTILIDAD EN APP ---
def encontrar_columna(lista_columnas, keywords):
    for col in lista_columnas:
        for key in keywords:
            if key.lower() in col.lower():
                return col
    return None

# --- SIDEBAR: PARÁMETROS Y CARGA ---
st.sidebar.header("1. Configuración Geotécnica")
q_adm = st.sidebar.number_input("Esfuerzo Admisible (kN/m²)", value=250.0)
fc = st.sidebar.selectbox("f'c Concreto (MPa)", [21, 28, 35], index=1)
factor_h = st.sidebar.slider("Relación H vs Distancia Ejes (1/X)", 8, 15, 10)

st.sidebar.header("2. Carga de Archivos ETABS")
with st.sidebar:
    file_reacciones = st.file_uploader("Reacciones (Joint Reactions)", type="csv")
    file_coords = st.file_uploader("Coordenadas (Joint Coordinates)", type="csv")
    file_conn = st.file_uploader("Conectividad (Column Connectivity)", type="csv")
    file_sum = st.file_uploader("Resumen (Frame Assignments Summary)", type="csv")
    file_sec = st.file_uploader("Secciones (Frame Sections)", type="csv")

# --- LÓGICA PRINCIPAL ---
if all([file_reacciones, file_coords, file_conn, file_sum, file_sec]):
    # Procesar archivos
    df_r, unit_r = engine.procesar_csv_etabs(file_reacciones)
    df_c, unit_c = engine.procesar_csv_etabs(file_coords)
    df_conn, _ = engine.procesar_csv_etabs(file_conn)
    df_sum, _ = engine.procesar_csv_etabs(file_sum)
    df_sec, _ = engine.procesar_csv_etabs(file_sec)

    # Mapeos de columnas
    col_nodo_r = encontrar_columna(df_r.columns, ['label', 'node', 'joint'])
    col_comb = encontrar_columna(df_r.columns, ['combo', 'case', 'load'])
    col_fz = encontrar_columna(df_r.columns, ['fz', 'vertical', 'p '])
    col_mx = encontrar_columna(df_r.columns, ['mx'])
    col_my = encontrar_columna(df_r.columns, ['my'])
    col_nodo_c = encontrar_columna(df_c.columns, ['label', 'node', 'joint'])
    col_x = encontrar_columna(df_c.columns, ['x'])
    col_y = encontrar_columna(df_c.columns, ['y'])

    st.markdown("### 3. Configuración de la Zapata")
    c1, c2 = st.columns(2)
    with c1:
        nodos_sel = st.multiselect("Nodos de las 2 columnas:", df_c[col_nodo_c].unique(), max_selections=2)
    with c2:
        combs_sel = st.multiselect("Combinaciones de Diseño/Servicio:", df_r[col_comb].unique())

    if len(nodos_sel) == 2 and combs_sel:
        # --- Dentro del bloque 'if len(nodos_sel) == 2' en app.py ---
        g1 = engine.obtener_geometria_columna(nodos_sel[0], df_conn, df_sum, df_sec) # Procesa el Nodo 3
        g2 = engine.obtener_geometria_columna(nodos_sel[1], df_conn, df_sum, df_sec) # Procesa el Nodo 4

        if g1 and g2:
            st.info(f"Columnas detectadas: {g1['label']} ({g1['seccion']}) y {g2['label']} ({g2['seccion']})")
            
            st.subheader("Configuración de Bordes")
            col_b1, col_b2 = st.columns(2)
            es_borde_1 = col_b1.checkbox(f"Columna {nodos_sel[0]} es de borde (Límite Izq)")
            es_borde_2 = col_b2.checkbox(f"Columna {nodos_sel[1]} es de borde (Límite Der)")
            comb_ubicacion = st.selectbox("Seleccione combinación D+L para centrar zapata:", combs_sel)

            if st.button("🚀 Ejecutar Diseño Completo"):
                # A. Geometría y Cargas
                p1 = df_c[df_c[col_nodo_c] == nodos_sel[0]][[col_x, col_y]].values[0]
                p2 = df_c[df_c[col_nodo_c] == nodos_sel[1]][[col_x, col_y]].values[0]
                if unit_c.get(col_x) == 'mm':
                    p1 /= 1000.0
                    p2 /= 1000.0

                reac1 = df_r[(df_r[col_nodo_r] == nodos_sel[0]) & (df_r[col_comb] == comb_ubicacion)].iloc[0].to_dict()
                reac2 = df_r[(df_r[col_nodo_r] == nodos_sel[1]) & (df_r[col_comb] == comb_ubicacion)].iloc[0].to_dict()

                res_ub = engine.procesar_geometria_y_cargas(p1, p2, reac1, reac2)
                L_zapata = res_ub['x_resultante'] * 2
                H_calc = res_ub['L_ejes'] / factor_h
                q_neto = q_adm - (24.0 * H_calc)

                B_optimo = engine.optimizar_ancho_B(L_zapata, res_ub['R_total'], 0, q_neto, max(g1['t2'], g2['t2']) + 0.20)
                criticos = engine.calcular_secciones_criticas(res_ub['L_ejes'], g1, g2, H_calc, es_borde_1, es_borde_2)
                d = criticos['d']

                # B. Verificación de Combinaciones
                st.subheader("🛡️ Verificación de Cortante (Peor Caso)")
                res_diseno = engine.analizar_combinaciones_diseno(
                    df_r, nodos_sel, combs_sel, col_nodo_r, col_comb, col_fz, 
                    L_zapata, B_optimo, g1, g2, H_calc, es_borde_1, es_borde_2
                )

                phi_v = 0.75
                vn_1d = (0.17 * 1.0 * np.sqrt(fc) * (B_optimo * 1000) * (d * 1000)) / 1000
                vn_2d_c1 = (0.33 * 1.0 * np.sqrt(fc) * (criticos['bo_1'] * 1000) * (d * 1000)) / 1000

                data_check = {
                    "Chequeo": ["Cortante 1D", f"Punzonamiento {g1['label']}", f"Punzonamiento {g2['label']}"],
                    "Demanda (Vu)": [f"{res_diseno['vu_1d_max']:.1f} kN", f"{res_diseno['vu_2d_c1_max']:.1f} kN", f"{res_diseno['vu_2d_c2_max']:.1f} kN"],
                    "Capacidad (φVn)": [f"{phi_v*vn_1d:.1f} kN", f"{phi_v*vn_2d_c1:.1f} kN", f"{phi_v*vn_2d_c1:.1f} kN"],
                    "Estado": [
                        "✅ OK" if res_diseno['vu_1d_max'] < phi_v*vn_1d else "❌ FALLA",
                        "✅ OK" if res_diseno['vu_2d_c1_max'] < phi_v*vn_2d_c1 else "❌ FALLA",
                        "✅ OK" if res_diseno['vu_2d_c2_max'] < phi_v*vn_2d_c1 else "❌ FALLA"
                    ]
                }
                st.table(pd.DataFrame(data_check))

                # C. Resultados Finales
                st.success("### ✅ Diseño Finalizado")
                r1, r2, r3 = st.columns(3)
                r1.metric("Longitud L", f"{L_zapata:.2f} m")
                r2.metric("Ancho B", f"{B_optimo:.2f} m")
                r3.metric("Espesor H", f"{H_calc:.2f} m")
        else:
            st.error(f"No encontré el nodo {nodos_sel} en la tabla de conectividad.")
            st.write("Primeras filas de conectividad:", df_conn.head())
else:
    st.warning("Cargue los archivos para comenzar.")
