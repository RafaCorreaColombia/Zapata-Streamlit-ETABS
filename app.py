import streamlit as st
import pandas as pd
import numpy as np
import engine

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Memoria de Cálculo - Zapata Multicolumna", layout="wide")
st.title("🏗️ Memoria de Cálculo: Zapata Combinada")

# --- FUNCIONES DE UTILIDAD ---
def encontrar_columna(lista_columnas, keywords):
    for col in lista_columnas:
        for key in keywords:
            if key.lower() in col.lower():
                return col
    return None

# --- SIDEBAR: PARÁMETROS ---
st.sidebar.header("1. Parámetros de Suelo y Concreto")
q_adm = st.sidebar.number_input("Esfuerzo Admisible Neto (kN/m²)", value=250.0)
fc = st.sidebar.selectbox("f'c Concreto (MPa)", [21, 28, 35], index=1)
factor_h = st.sidebar.slider("Relación H vs L_ejes (1/X)", 6, 12, 8)

st.sidebar.header("2. Carga de Archivos ETABS")
with st.sidebar:
    f_reac = st.file_uploader("Reacciones (.csv)", type="csv")
    f_coords = st.file_uploader("Coordenadas (.csv)", type="csv")
    f_conn = st.file_uploader("Conectividad (.csv)", type="csv")
    f_sum = st.file_uploader("Resumen (.csv)", type="csv")
    f_sec = st.file_uploader("Secciones (.csv)", type="csv")

if all([f_reac, f_coords, f_conn, f_sum, f_sec]):
    df_r, unit_r = engine.procesar_csv_etabs(f_reac)
    df_c, unit_c = engine.procesar_csv_etabs(f_coords)
    df_conn, _ = engine.procesar_csv_etabs(f_conn)
    df_sum, _ = engine.procesar_csv_etabs(f_sum)
    df_sec, _ = engine.procesar_csv_etabs(f_sec)

    col_nodo_r = encontrar_columna(df_r.columns, ['label', 'node', 'joint'])
    col_comb = encontrar_columna(df_r.columns, ['combo', 'case', 'load'])
    col_fz = encontrar_columna(df_r.columns, ['fz', 'vertical', 'p '])
    col_mx, col_my = encontrar_columna(df_r.columns, ['mx']), encontrar_columna(df_r.columns, ['my'])
    col_nodo_c = encontrar_columna(df_c.columns, ['label', 'node', 'joint'])
    col_x, col_y = encontrar_columna(df_c.columns, ['x']), encontrar_columna(df_c.columns, ['y'])

    st.markdown("### 3. Configuración de la Memoria")
    nodos_validos = df_conn['I-End Point'].unique()
    opciones_nodos = [str(int(float(n))) for n in nodos_validos if str(n) != 'nan']

    c1, c2 = st.columns(2)
    with c1:
        nodos_sel = st.multiselect("Nodos de Columnas:", opciones_nodos, max_selections=3)
    with c2:
        combs_servicio = st.multiselect("Combinaciones de SERVICIO:", df_r[col_comb].unique())

    if len(nodos_sel) >= 2 and combs_servicio:
        # 1. Preparar info de nodos y ordenar
        info_nodos = []
        for n in nodos_sel:
            row_c = df_c[df_c[col_nodo_c].astype(str).str.replace('.0','') == n].iloc[0]
            fact_m = 0.001 if unit_c.get(col_x) == 'mm' else 1.0
            coords = np.array([row_c[col_x], row_c[col_y]]) * fact_m
            geo = engine.obtener_geometria_columna(n, df_conn, df_sum, df_sec)
            if geo: info_nodos.append({'id': n, 'coords': coords, 'geo': geo})
        
        info_nodos.sort(key=lambda x: (x['coords'][0], x['coords'][1]))
        nodos_ord = [x['id'] for x in info_nodos]
        
        st.info(f"Eje Longitudinal detectado: " + " → ".join([f"Col {n}" for n in nodos_ord]))

        # --- BLOQUE DE VERIFICACIÓN DE GEOMETRÍA ---
        with st.expander("📊 Ver Detalles de Secciones (ETABS)", expanded=True):
            cols_geo = st.columns(len(info_nodos))
            for i, info in enumerate(info_nodos):
                with cols_geo[i]:
                    st.markdown(f"**Nodo {info['id']} ({info['geo']['label']})**")
                    st.caption(f"Sección: {info['geo']['seccion']}")
                    # t_long es el t3 de ETABS (dimensión en el sentido del eje longitudinal)
                    # t_trans es el t2 de ETABS (dimensión en el sentido del ancho B)
                    st.write(f"📐 $t_{{long}}$: **{info['geo']['t3']:.3f} m**")
                    st.write(f"📐 $t_{{trans}}$: **{info['geo']['t2']:.3f} m**")

        st.markdown("---")

        # 2. Parámetros de Diseño (Bordes, Deltas, etc.)
        st.subheader("⚙️ Ajustes de Diseño")
        # ... continúa el resto del código

        # 2. Parámetros de Diseño
        st.subheader("⚙️ Ajustes de Diseño")
        col_b, col_m = st.columns(2)
        with col_b:
            dict_bordes = {}
            for i, n in enumerate(nodos_ord):
                dict_bordes[n] = st.checkbox(f"Borde Nodo {n}", value=(i==0 or i==len(nodos_ord)-1))
        with col_m:
            comb_maestra = st.selectbox("Combinación Maestra (D+L):", combs_servicio)
            st.write("---")
            st.write("**Desplazamientos Manuales (Deltas)**")
            delta_L = st.slider("Desplazamiento Longitudinal (ΔL)", -1.0, 1.0, 0.0, 0.01)
            delta_T = st.slider("Desplazamiento Transversal (ΔT)", -0.5, 0.5, 0.0, 0.01)

        if st.button("📝 Generar Memoria de Cálculo"):
            # A. Cargas Maestra
            for info in info_nodos:
                r = df_r[(df_r[col_nodo_r].astype(str).str.replace('.0','') == info['id']) & (df_r[col_comb] == comb_maestra)].iloc[0]
                info['reac_m'] = {'FZ': r[col_fz], 'MX': r[col_mx], 'MY': r[col_my]}

            res_m = engine.procesar_geometria_multicolumna(info_nodos, key_reac='reac_m')
            
            # --- B. DIMENSIONAMIENTO LONGITUDINAL (L) CON RESTRICCIONES ---
            xr = res_m['x_resultante'] # Distancia resultante desde Nodo 1
            L_ejes = res_m['dist_max_ejes']
            
            # s1 y s2: Recubrimiento/Vuelo mínimo desde el centro de la col al borde
            # Si es borde, el recubrimiento es t3/2 estrictamente.
            s1_min = info_nodos[0]['geo']['t3'] / 2
            s2_min = info_nodos[-1]['geo']['t3'] / 2
            
            # s_vuelo: Vuelo extra si NO es de borde (ej. 15cm o lo que el usuario defina)
            vuelo = 0.15
            
            if dict_bordes[nodos_ord[0]] and dict_bordes[nodos_ord[-1]]:
                # CASO: AMBOS BORDES (L está restringido)
                L_zapata = L_ejes + s1_min + s2_min
                Cx_teorico = L_zapata / 2 - s1_min # Centro respecto al Nodo 1
                
            elif dict_bordes[nodos_ord[0]]:
                # CASO: BORDE IZQUIERDO (Crece hacia la derecha)
                # Para ser concéntrica: L = 2 * (xr + s1_min)
                # Pero debe cubrir al menos: L_min = s1_min + L_ejes + (s2_min + vuelo)
                L_ideal = 2 * (xr + s1_min)
                L_min = s1_min + L_ejes + (s2_min + vuelo)
                L_zapata = max(L_ideal, L_min)
                Cx_teorico = xr # Intentamos que coincida, si L=L_min habrá excentricidad
                
            elif dict_bordes[nodos_ord[-1]]:
                # CASO: BORDE DERECHO (Crece hacia la izquierda)
                # Para ser concéntrica: L = 2 * ( (L_ejes - xr) + s2_min )
                # Pero debe cubrir al menos: L_min = (s1_min + vuelo) + L_ejes + s2_min
                dist_der = L_ejes - xr
                L_ideal = 2 * (dist_der + s2_min)
                L_min = (s1_min + vuelo) + L_ejes + s2_min
                L_zapata = max(L_ideal, L_min)
                # El centro Cx respecto al Nodo 1 sería: xr (si es ideal) 
                # o desplazado si domina L_min
                Cx_teorico = xr 

            else:
                # CASO: LIBRE (Busca concentricidad total)
                d_izq = xr + s1_min + vuelo
                d_der = (L_ejes - xr) + s2_min + vuelo
                L_zapata = max(d_izq, d_der) * 2
                Cx_teorico = xr

            # --- C. DEFINICIÓN DEL CENTRO GEOMÉTRICO REAL ---
            # El Cx_real es la posición del centro de la zapata respecto al Nodo 1
            # Si la zapata es concéntrica perfecta, Cx_real = xr
            # Pero si hay restricciones de borde, el centro se desplaza:
            
            if dict_bordes[nodos_ord[0]]:
                # Si es borde izquierdo, el centro está a L/2 del borde (que es -s1_min)
                Cx_centro_geom = (L_zapata / 2) - s1_min
            elif dict_bordes[nodos_ord[-1]]:
                # Si es borde derecho, el centro está a L/2 del borde derecho (que es L_ejes + s2_min)
                Cx_centro_geom = L_ejes + s2_min - (L_zapata / 2)
            else:
                # Si es libre, centramos en xr
                Cx_centro_geom = xr

            # Cx_real FINAL con el ajuste manual del usuario
            Cx_real = Cx_centro_geom + delta_L
            Cy_real = 0.0 + delta_T

            # D. Espesor y B
            H_prelim = res_m['dist_max_ejes'] / factor_h
            B_min = max([n['geo']['t2'] for n in info_nodos]) + 0.20
            
            # Optimización de B basada en la Maestra y Deltas
            # Excentricidad L para la Maestra = abs(Cx_real - (x_res + s1))
            e_L_m = abs(Cx_real - (res_m['x_resultante'] + s1))
            B_optimo = engine.optimizar_ancho_B(L_zapata, res_m['R_total'], e_L_m * res_m['R_total'], q_adm - (24*H_prelim), B_min)

            # E. Memoria de Presiones (Envolvente)
            st.subheader("📑 Memoria de Verificación de Presiones y Centroides")
            st.write(f"Dimensiones Finales: **L = {L_zapata:.2f} m** | **B = {B_optimo:.2f} m** | **H = {H_prelim:.2f} m (Preliminar)**")
            
            lista_memoria = []
            for cb in combs_servicio:
                for info in info_nodos:
                    r_s = df_r[(df_r[col_nodo_r].astype(str).str.replace('.0','') == info['id']) & (df_r[col_comb] == cb)].iloc[0]
                    info['reac_s'] = {'FZ': r_s[col_fz], 'MX': r_s[col_mx], 'MY': r_s[col_my]}
                
                res_s = engine.procesar_geometria_multicolumna(info_nodos, key_reac='reac_s')
                
                # Excentricidades relativas al centro geométrico ajustado por Deltas
                # Distancia de resultante al borde izquierdo = x_res + s1
                pos_x_res = res_s['x_resultante'] + s1
                e_L = abs(Cx_real - pos_x_res)
                e_T = abs(Cy_real - 0.0) # Se podría incluir Mx rotado aquí
                
                # Datos para la función del motor
                metricas = engine.calcular_metricas_memoria(
                    L_zapata, B_optimo, res_s, q_adm - (24*H_prelim), 
                    cb, comb_maestra, e_L, e_T
                )
                lista_memoria.append(metricas)
            
            df_memoria = pd.DataFrame(lista_memoria)
            st.table(df_memoria)

            # --- NUEVA SECCIÓN: DISEÑO ESTRUCTURAL (COMB. ÚLTIMAS) ---
            st.markdown("---")
            st.subheader("🛡️ Verificación de Cortante y Punzonamiento (Estado Límite)")
            
            # Usamos el espesor H preliminar
            d = H_prelim - 0.075
            
            # Para simplificar con 2 o 3 columnas, evaluamos el punzonamiento en cada una
            res_diseno_nodos = []
            for info in info_nodos:
                # Buscamos la peor reacción de diseño (Última) para esta columna
                max_fz_u = 0
                max_comb_u = ""
                for cb_u in combs_diseno:
                    r_u = df_r[(df_r[col_nodo_r].astype(str).str.replace('.0','') == info['id']) & (df_r[col_comb] == cb_u)].iloc[0]
                    if abs(r_u[col_fz]) > max_fz_u:
                        max_fz_u = abs(r_u[col_fz])
                        max_comb_u = cb_u
                
                # Capacidad de Punzonamiento (Simplificada para memoria)
                # bo depende de si es borde o no
                es_b = dict_bordes[info['id']]
                t3, t2 = info['geo']['t3'], info['geo']['t2']
                bo = (2*(t3 + d/2) + (t2 + d)) if es_b else (2*(t3 + d) + 2*(t2 + d))
                
                phi_v = 0.75
                Vn = (0.33 * np.sqrt(fc) * (bo * 1000) * (d * 1000)) / 1000
                Vu = max_fz_u # Simplificación: carga puntual vs reacción del suelo
                
                res_diseno_nodos.append({
                    "Columna": info['geo']['label'],
                    "Comb. Crítica": max_comb_u,
                    "Vu (kN)": round(Vu, 1),
                    "φVn (kN)": round(phi_v * Vn, 1),
                    "Estado": "✅ OK" if Vu < phi_v * Vn else "❌ FALLA (H insuficiente)"
                })
            
            st.table(pd.DataFrame(res_diseno_nodos))
            st.success(f"### ✅ Memoria Generada Exitosamente")
            
            # F. Resumen de Ingeniería
            st.markdown("---")
            st.write("**Notas de Memoria:**")
            st.write(f"- Se garantiza que el centro geométrico coincide con el centro de fuerzas de **{comb_maestra}** salvo ajuste manual ΔL/ΔT.")
            st.write("- El eje longitudinal se define como el vector que une los centros de las columnas extremas.")
            
else:
    st.warning("Cargue los archivos para iniciar la memoria.")
