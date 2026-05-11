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
    
    # Filtrar solo nodos que tienen columna asignada
    nodos_validos = df_conn['I-End Point'].unique()
    opciones_nodos = [str(int(float(n))) for n in nodos_validos if str(n) != 'nan']

    c1, c2 = st.columns(2)
    with c1:
        nodos_sel = st.multiselect("Nodos de las 2 columnas (Solo Apoyos):", opciones_nodos, max_selections=2)
    
    with c2:
        combs_servicio = st.multiselect("Comb. de SERVICIO (Suelo):", df_r[col_comb].unique())
        combs_diseno = st.multiselect("Comb. de DISEÑO (Acero/Cortante):", df_r[col_comb].unique())

    if len(nodos_sel) == 2 and combs_servicio and combs_diseno:
        g1 = engine.obtener_geometria_columna(nodos_sel[0], df_conn, df_sum, df_sec)
        g2 = engine.obtener_geometria_columna(nodos_sel[1], df_conn, df_sum, df_sec)

        if g1 and g2:
            st.info(f"Columnas detectadas: {g1['label']} ({g1['seccion']}) y {g2['label']} ({g2['seccion']})")
            
            st.subheader("Configuración de Bordes")
            col_b1, col_b2 = st.columns(2)
            es_borde_1 = col_b1.checkbox(f"Columna {nodos_sel[0]} es de borde (Izq)")
            es_borde_2 = col_b2.checkbox(f"Columna {nodos_sel[1]} es de borde (Der)")

            comb_ubicacion = st.selectbox("Seleccione combinación D+L para centrar zapata:", combs_servicio)

            if st.button("🚀 Ejecutar Diseño Completo"):
                # A. Preparar coordenadas
                p1 = df_c[df_c[col_nodo_c].astype(str).str.replace('.0','',regex=False) == nodos_sel[0]][[col_x, col_y]].values[0]
                p2 = df_c[df_c[col_nodo_c].astype(str).str.replace('.0','',regex=False) == nodos_sel[1]][[col_x, col_y]].values[0]
                
                fact_m = 0.001 if unit_c.get(col_x) == 'mm' else 1.0
                p1_m, p2_m = p1 * fact_m, p2 * fact_m

                reac1 = df_r[(df_r[col_nodo_r].astype(str).str.replace('.0','',regex=False) == nodos_sel[0]) & (df_r[col_comb] == comb_ubicacion)].iloc[0].to_dict()
                reac2 = df_r[(df_r[col_nodo_r].astype(str).str.replace('.0','',regex=False) == nodos_sel[1]) & (df_r[col_comb] == comb_ubicacion)].iloc[0].to_dict()

                # B. Motor: Geometría y Cargas de Control
                res_ub = engine.procesar_geometria_y_cargas(p1_m, p2_m, reac1, reac2)
                
                # --- BLOQUE DE AUDITORÍA ---
                st.markdown("---")
                st.subheader("🔍 Bloque de Verificación (Auditoría)")
                aud_1, aud_2 = st.columns(2)
                with aud_1:
                    st.write("**1. Geometría Básica**")
                    st.info(f"Distancia entre ejes: **{res_ub['L_ejes']:.3f} m**")
                    st.write(f"Col 1 ({g1['label']}): t3(long)={g1['t3']:.3f}m, t2={g1['t2']:.3f}m")
                    st.write(f"Col 2 ({g2['label']}): t3(long)={g2['t3']:.3f}m, t2={g2['t2']:.3f}m")
                with aud_2:
                    st.write(f"**2. Reacciones (Comb: {comb_ubicacion})**")
                    st.write(f"Nodo {nodos_sel[0]}: Fz={reac1[col_fz]:.1f}, Mx={reac1[col_mx]:.1f}, My={reac1[col_my]:.1f}")
                    st.write(f"Nodo {nodos_sel[1]}: Fz={reac2[col_fz]:.1f}, Mx={reac2[col_mx]:.1f}, My={reac2[col_my]:.1f}")

                # C. Centroide y Dimensionamiento
                L_equilibrio = res_ub['x_resultante'] * 2
                L_min_geom = res_ub['L_ejes'] + (g1['t3']/2) + (g2['t3']/2) + 0.20
                L_zapata = max(L_equilibrio, L_min_geom)
                H_calc = res_ub['L_ejes'] / factor_h
                q_neto = q_adm - (24.0 * H_calc)
                B_fisico = max(g1['t2'], g2['t2']) + 0.20
                B_optimo = engine.optimizar_ancho_B(L_zapata, res_ub['R_total'], res_ub['m_trans_total'], q_neto, B_fisico)

                st.write("**3. Centroide y Dimensionamiento**")
                c_a, c_b, c_c = st.columns(3)
                c_a.metric("X Resultante (desde N1)", f"{res_ub['x_resultante']:.3f} m")
                c_b.metric("L calculada (2*Xres)", f"{L_zapata:.3f} m")
                c_c.metric("Ancho B (Final)", f"{B_optimo:.2f} m")

                # D. Presiones de Servicio
                st.write("**4. Verificación de Presiones (Servicio)**")
                s_max, s_min = engine.calcular_presiones_4_esquinas(L_zapata, B_optimo, res_ub['R_total'], 0, res_ub['m_trans_total'])
                pres_data = {
                    "Punto": ["Esquina Max", "Esquina Min", "Admisible Neto"],
                    "Presión (kN/m²)": [f"{s_max:.2f}", f"{s_min:.2f}", f"{q_neto:.2f}"],
                    "Estado": ["✅" if s_max <= q_neto else "❌", "✅" if s_min >= 0 else "🚩 TRACCIÓN", "-"]
                }
                st.table(pres_data)

                # E. Secciones Críticas y Cortante de Diseño
                criticos = engine.calcular_secciones_criticas(res_ub['L_ejes'], g1, g2, H_calc, es_borde_1, es_borde_2)
                d = criticos['d']
                res_diseno = engine.analizar_combinaciones_diseno(
                    df_r, nodos_sel, combs_diseno, col_nodo_r, col_comb, col_fz, 
                    L_zapata, B_optimo, g1, g2, H_calc, es_borde_1, es_borde_2
                )

                st.write("**5. Verificación de Cortante (Diseño)**")
                phi_v = 0.75
                vn_1d = (0.17 * np.sqrt(fc) * (B_optimo * 1000) * (d * 1000)) / 1000
                vn_2d_c1 = (0.33 * np.sqrt(fc) * (criticos['bo1'] * 1000) * (d * 1000)) / 1000
                vn_2d_c2 = (0.33 * np.sqrt(fc) * (criticos['bo2'] * 1000) * (d * 1000)) / 1000

                data_check = {
                    "Chequeo": ["Cortante 1D", f"Punzonamiento {g1['label']}", f"Punzonamiento {g2['label']}"],
                    "Demanda (Vu)": [f"{res_diseno['vu_1d_max']:.1f} kN", f"{res_diseno['vu_2d_c1_max']:.1f} kN", f"{res_diseno['vu_2d_c2_max']:.1f} kN"],
                    "Capacidad (φVn)": [f"{phi_v*vn_1d:.1f} kN", f"{phi_v*vn_2d_c1:.1f} kN", f"{phi_v*vn_2d_c2:.1f} kN"],
                    "Estado": [
                        "✅ OK" if res_diseno['vu_1d_max'] < phi_v*vn_1d else "❌ FALLA",
                        "✅ OK" if res_diseno['vu_2d_c1_max'] < phi_v*vn_2d_c1 else "❌ FALLA",
                        "✅ OK" if res_diseno['vu_2d_c2_max'] < phi_v*vn_2d_c2 else "❌ FALLA"
                    ]
                }
                st.table(data_check)
                st.success("### ✅ Diseño Finalizado")
        else:
            st.error("No se encontró geometría de columnas.")
else:
    st.warning("Cargue los archivos para comenzar.")
