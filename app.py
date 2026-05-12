import streamlit as st
import pandas as pd
import numpy as np
import engine

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Zapata Inteligente ETABS", layout="wide")
st.title("🏗️ Diseñador de Zapatas Multicolumna (2-3)")

# --- FUNCIONES DE UTILIDAD ---
def encontrar_columna(lista_columnas, keywords):
    for col in lista_columnas:
        for key in keywords:
            if key.lower() in col.lower():
                return col
    return None

# --- SIDEBAR ---
st.sidebar.header("1. Parámetros Geotécnicos")
q_adm = st.sidebar.number_input("Esfuerzo Admisible (kN/m²)", value=250.0)
fc = st.sidebar.selectbox("f'c Concreto (MPa)", [21, 28, 35], index=1)
factor_h = st.sidebar.slider("Relación H vs Distancia (1/X)", 8, 15, 10)

st.sidebar.header("2. Carga de Archivos")
with st.sidebar:
    f_reac = st.file_uploader("Reacciones", type="csv")
    f_coords = st.file_uploader("Coordenadas", type="csv")
    f_conn = st.file_uploader("Conectividad", type="csv")
    f_sum = st.file_uploader("Resumen Assignments", type="csv")
    f_sec = st.file_uploader("Secciones", type="csv")

if all([f_reac, f_coords, f_conn, f_sum, f_sec]):
    # Procesamiento
    df_r, unit_r = engine.procesar_csv_etabs(f_reac)
    df_c, unit_c = engine.procesar_csv_etabs(f_coords)
    df_conn, _ = engine.procesar_csv_etabs(f_conn)
    df_sum, _ = engine.procesar_csv_etabs(f_sum)
    df_sec, _ = engine.procesar_csv_etabs(f_sec)

    # Mapeos
    col_nodo_r = encontrar_columna(df_r.columns, ['label', 'node', 'joint'])
    col_comb = encontrar_columna(df_r.columns, ['combo', 'case', 'load'])
    col_fz = encontrar_columna(df_r.columns, ['fz', 'vertical', 'p '])
    col_mx = encontrar_columna(df_r.columns, ['mx'])
    col_my = encontrar_columna(df_r.columns, ['my'])
    col_nodo_c = encontrar_columna(df_c.columns, ['label', 'node', 'joint'])
    col_x, col_y = encontrar_columna(df_c.columns, ['x']), encontrar_columna(df_c.columns, ['y'])

    st.markdown("### 3. Configuración de la Zapata")
    nodos_validos = df_conn['I-End Point'].unique()
    opciones_nodos = [str(int(float(n))) for n in nodos_validos if str(n) != 'nan']

    c1, c2 = st.columns(2)
    with c1:
        nodos_sel = st.multiselect("Seleccione 2 o 3 nodos alineados:", opciones_nodos, max_selections=3)
    with c2:
        combs_servicio = st.multiselect("Comb. SERVICIO (Suelo):", df_r[col_comb].unique())
        combs_diseno = st.multiselect("Comb. DISEÑO (Estructural):", df_r[col_comb].unique())

    if len(nodos_sel) >= 2 and combs_servicio and combs_diseno:
        # 1. Obtener y ordenar información de nodos
        info_nodos = []
        for n in nodos_sel:
            row_c = df_c[df_c[col_nodo_c].astype(str).str.replace('.0','') == n].iloc[0]
            fact_m = 0.001 if unit_c.get(col_x) == 'mm' else 1.0
            coords = np.array([row_c[col_x], row_c[col_y]]) * fact_m
            geo = engine.obtener_geometria_columna(n, df_conn, df_sum, df_sec)
            if geo: info_nodos.append({'id': n, 'coords': coords, 'geo': geo})

        # Ordenar por posición real
        info_nodos.sort(key=lambda x: (x['coords'][0], x['coords'][1]))
        nodos_ord = [x['id'] for x in info_nodos]
        st.info(f"Orden detectado: " + " → ".join([f"Col {n}" for n in nodos_ord]))

        # 2. Bordes
        st.subheader("Configuración de Bordes")
        cb = st.columns(len(nodos_ord))
        dict_bordes = {}
        for i, n in enumerate(nodos_ord):
            dict_bordes[n] = cb[i].checkbox(f"Borde Nodo {n}", value=(i==0 or i==len(nodos_ord)-1))

        comb_predim = st.selectbox("Comb. para centrar zapata:", combs_servicio)

        st.subheader("🎮 Ajuste Opcional de Posición")
        col_delta_l, col_delta_t = st.columns(2)
        delta_L = col_delta_l.slider("Desplazamiento Longitudinal (ΔL)", -0.5, 0.5, 0.0, step=0.01)
        delta_T = col_delta_t.slider("Desplazamiento Transversal (ΔT)", -0.2, 0.2, 0.0, step=0.01)

        if st.button("🚀 Ejecutar Diseño Completo"):
            # Cargas para Predimensionamiento
            for info in info_nodos:
                reac = df_r[(df_r[col_nodo_r].astype(str).str.replace('.0','') == info['id']) & 
                            (df_r[col_comb] == comb_predim)].iloc[0]
                info['reac'] = {'FZ': reac[col_fz], 'MX': reac[col_mx], 'MY': reac[col_my]}

            # A. Motor: Geometría
            res_ub = engine.procesar_geometria_multicolumna(info_nodos)
            
            # Vuelos
            s1 = (info_nodos[0]['geo']['t3']/2) if dict_bordes[nodos_ord[0]] else (info_nodos[0]['geo']['t3']/2 + 0.15)
            s2 = (info_nodos[-1]['geo']['t3']/2) if dict_bordes[nodos_ord[-1]] else (info_nodos[-1]['geo']['t3']/2 + 0.15)
            
            L_min = res_ub['dist_max_ejes'] + s1 + s2
            L_eq = res_ub['x_resultante'] * 2
            L_zapata = max(L_min, L_eq)
            
            # Dimensiones
            H_calc = res_ub['dist_max_ejes'] / factor_h
            q_neto = q_adm - (24.0 * H_calc)
            B_min = max([n['geo']['t2'] for n in info_nodos]) + 0.20
            
            # Excentricidad de predim
            e_L_predim = abs((L_zapata/2) - (res_ub['x_resultante'] + s1))
            B_optimo = engine.optimizar_ancho_B(L_zapata, res_ub['R_total'], e_L_predim * res_ub['R_total'], q_neto, B_min)

            # B. Auditoría de Presiones (Envolvente)
            st.subheader("🔍 Auditoría de Presiones (Envolvente de Servicio)")
            data_p = []
            for cb_s in combs_servicio:
                for info in info_nodos:
                    r_s = df_r[(df_r[col_nodo_r].astype(str).str.replace('.0','') == info['id']) & (df_r[col_comb] == cb_s)].iloc[0]
                    info['reac_s'] = {'FZ': r_s[col_fz], 'MX': r_s[col_mx], 'MY': r_s[col_my]}
                
                res_s = engine.procesar_geometria_multicolumna(info_nodos, key_reac='reac_s')
                e_s = abs((L_zapata/2) - (res_s['x_resultante'] + s1))
                s_max, s_min = engine.calcular_presiones_4_esquinas(L_zapata, B_optimo, res_s['R_total'], e_s * res_s['R_total'], res_s['m_trans_total'])
                
                data_p.append({"Combinación": cb_s, "σ_max": f"{s_max:.2f}", "σ_min": f"{s_min:.2f}", "Estado": "✅" if s_max <= q_neto and s_min >= 0 else "❌"})
            st.table(pd.DataFrame(data_p))

            # C. Resultados
            st.success(f"**Diseño Final:** L={L_zapata:.2f}m, B={B_optimo:.2f}m, H={H_calc:.2f}m")

else:
    st.warning("Cargue los archivos para comenzar.")
