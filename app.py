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
vuelo_usr = st.sidebar.number_input("Vuelo mínimo (m)", value=0.0, step=0.05)
vuelo_B_usr = st.sidebar.slider("Vuelo mín. Transversal (m)", 0.0, 1.0, 0.00, 0.025, 
                               help="Añade un vuelo extra a ambos lados del eje de las columnas (sentido B).")

st.sidebar.header("2. Carga de Archivos ETABS")
with st.sidebar:
    f_reac = st.file_uploader("Joint Reactions (.csv)", type="csv", help="Upload the 'Joint Reactions' table exported from ETABS.")
    f_coords = st.file_uploader("Joint Coordinates Data (.csv)", type="csv", help="Upload the 'Joint Coordinates Data' table exported from ETABS.")
    f_conn = st.file_uploader("Column Connectivity Data (.csv)", type="csv", help="Upload the 'Column Connectivity Data' table to identify column nodes.")
    f_sum = st.file_uploader("Frame Assignments - Summary (.csv)", type="csv", help="Upload the 'Frame Assignments - Summary' table.")
    f_sec = st.file_uploader("Frame Section (.csv)", type="csv", help="Upload the 'Frame Section' table to get column dimensions (t2, t3).")

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
        combs_ultimas = st.multiselect("Combinaciones de DISEÑO (Últimas):", df_r[col_comb].unique())

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

        # 2. Parámetros de Diseño
        st.subheader("⚙️ Ajustes de Diseño")
        col_b, col_m = st.columns(2)
        with col_b:
            dict_bordes = {}
            for i, n in enumerate(nodos_ord):
                dict_bordes[n] = st.checkbox(f"Borde Nodo {n}", value=False)
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
            
            # 1. Definir s1 y s2 de forma global para que estén disponibles en todo el bloque
            s1_min = info_nodos[0]['geo']['t3'] / 2
            s2_min = info_nodos[-1]['geo']['t3'] / 2
                        
            # s1 y s2 finales (usados para la geometría física)
            s1 = s1_min if dict_bordes[nodos_ord[0]] else (s1_min + vuelo_usr)
            s2 = s2_min if dict_bordes[nodos_ord[-1]] else (s2_min + vuelo_usr)
            
            # 2. Lógica de Longitud L (Jerarquía de bordes)
            if dict_bordes[nodos_ord[0]] and dict_bordes[nodos_ord[-1]]:
                L_zapata = np.ceil((L_ejes + s1_min + s2_min) * 10) / 10
                Cx_centro_geom = (L_zapata / 2) - s1_min
            elif dict_bordes[nodos_ord[0]]:
                L_ideal = 2 * (xr + s1_min)
                L_min_f = s1_min + L_ejes + s2
                L_zapata = np.ceil(max(L_ideal, L_min_f) * 10) / 10
                Cx_centro_geom = (L_zapata / 2) - s1_min
            elif dict_bordes[nodos_ord[-1]]:
                dist_der = L_ejes - xr
                L_ideal = 2 * (dist_der + s2_min)
                L_min_f = s1 + L_ejes + s2_min
                L_zapata = np. ceil(max(L_ideal, L_min_f) * 10) / 10
                Cx_centro_geom = L_ejes + s2_min - (L_zapata / 2)
            else:
                d_izq = xr + s1
                d_der = (L_ejes - xr) + s2
                L_zapata = np.ceil(max(d_izq, d_der) * 2 * 10) / 10
                Cx_centro_geom = xr

            
            # --- C. DEFINICIÓN DEL CENTRO GEOMÉTRICO REAL (Incluye Deltas) ---
            Cx_real = Cx_centro_geom + delta_L
            Cy_real = 0.0 + delta_T

            # --- D. ESPESOR Y ANCHO B ---
            H_prelim = np.ceil((res_m['dist_max_ejes'] / factor_h) * 20) / 20
            q_neto = q_adm - (24.0 * H_prelim)
            ancho_col_max = max([n['geo']['t2'] for n in info_nodos])
            B_min = ancho_col_max + (2 * vuelo_B_usr) # B_min para no romper lo que sigue
            
            # AHORA SÍ: e_L_m ya conoce a s1 porque lo definimos arriba
            # La excentricidad es la distancia entre el centro real de la zapata y la carga
            # Posición carga respecto a N1 = xr
            # Posición centro zapata respecto a N1 = Cx_real
            e_L_m = abs(Cx_real - xr)
            
            # --- D. DETERMINACIÓN DEL ANCHO B (ENVOLVENTE) ---
            # En lugar de optimizar solo para la maestra, buscamos el B que cumpla para TODAS
            anchos_necesarios = []
            
            for cb in combs_servicio:
                # Extraemos reacciones de esta combinación específica
                reacs_temp = {}
                for info in info_nodos:
                    r_s = df_r[(df_r[col_nodo_r].astype(str).str.replace('.0','') == info['id']) & 
                               (df_r[col_comb] == cb)].iloc[0]
                    # Guardamos temporalmente para el motor
                    info['reac_temp'] = {'FZ': r_s[col_fz], 'MX': r_s[col_mx], 'MY': r_s[col_my]}
                
                # Calculamos la estática de esta combinación
                res_s = engine.procesar_geometria_multicolumna(info_nodos, key_reac='reac_temp')
                
                # Excentricidad longitudinal de ESTA combinación respecto al centro que definimos
                e_L_s = abs(Cx_real - res_s['x_resultante'])
                M_long_s = e_L_s * res_s['R_total']
                M_trans_s = res_s['m_trans_total']
                
                # Buscamos el B necesario para esta combinación
                B_comb = engine.optimizar_ancho_B(
                    L_zapata, 
                    res_s['R_total'], 
                    M_long_s, 
                    M_trans_s, 
                    q_neto, 
                    B_min
                )
                anchos_necesarios.append(B_comb)

            # El B_optimo final es el más grande de todos los requeridos
            B_optimo = max(anchos_necesarios)

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
                # Distancia de resultante al Nodo 1 = x_res
                e_L = abs(Cx_real - res_s['x_resultante'])
                
                # e_T total = Excentricidad geométrica + Excentricidad por momentos locales
                # res_s['m_trans_total'] es el momento que calculamos en engine que hace volcar en B
                e_momento_T = abs(res_s['m_trans_total'] / res_s['R_total'])
                # e_T para la tabla de la memoria
                e_T = abs(Cy_real) + e_momento_T
                                
                # Datos para la función del motor
                metricas = engine.calcular_metricas_memoria(
                    L_zapata, B_optimo, res_s, q_adm - (24*H_prelim), 
                    cb, comb_maestra, e_L, e_T
                )
                lista_memoria.append(metricas)
            
            df_memoria = pd.DataFrame(lista_memoria)
            st.table(df_memoria)

            # --- G. REPRESENTACIÓN GRÁFICA ---
            st.markdown("---")
            st.subheader("🖼️ Visualización en Planta")
            
            # xr de la maestra para el dibujo
            xr_maestra = res_m['x_resultante']
            
            # Generar el gráfico usando la función de engine
            figura = engine.generar_planta_zapata(
                L_zapata, 
                B_optimo, 
                info_nodos, 
                s1, 
                Cx_real, 
                Cy_real, 
                xr_maestra,
                yr_maestra
            )
            
            # Mostrar en Streamlit
            st.pyplot(figura)
            
            st.caption(f"Nota: El origen (0,0) está ubicado en el centro del primer nodo seleccionado (Nodo {nodos_ord[0]}).")

            # --- F DISEÑO ESTRUCTURAL (COMB. ÚLTIMAS) ---
            st.markdown("---")
            st.subheader("🛡️ Verificación de Cortante y Punzonamiento (Estado Límite)")
            
            # Usamos el espesor H preliminar
            d = H_prelim - 0.075 - .01

            # --- F. ANÁLISIS DE COMBINACIONES ÚLTIMAS (DISEÑO) ---
            resultados_u = []

            # En app.py, antes del bucle de combinaciones últimas:     
            geometria_punzonamiento = {}
            
            for info in info_nodos:
                geo = engine.analizar_columna_punzonamiento(
                    info['coords'][0], 0, # x_node y y_node (centrado)
                    info['geo']['t3'], info['geo']['t2'], # tL y tT
                    d, L_zapata, B_optimo, Cx_real, fc
                )
                geometria_punzonamiento[info['id']] = geo
            
            for cb_u in combs_ultimas:
                # 1. ACTUALIZAR REACCIONES PARA ESTA COMBINACIÓN ESPECÍFICA
                for info_act in info_nodos:
                    r_u_act = df_r[(df_r[col_nodo_r].astype(str).str.replace('.0','') == info_act['id']) & 
                                   (df_r[col_comb] == cb_u)].iloc[0]
                    info_act['reac_u'] = {'FZ': r_u_act[col_fz], 'MX': r_u_act[col_mx], 'MY': r_u_act[col_my]}
                
                # 2. CALCULAR ESTÁTICA DE LA COMBINACIÓN
                res_u = engine.procesar_geometria_multicolumna(info_nodos, key_reac='reac_u')
                
                # 3. Obtener trapecio de diseño según tu lógica de B/4
                e_L_u = abs(Cx_real - res_u['x_resultante'])
                M_long_u = e_L_u * res_u['R_total']
                
                trapecio = engine.obtener_trapecio_diseno_u(
                    L_zapata, B_optimo, Cx_real, 
                    res_u['R_total'], M_long_u, res_u['m_trans_total']
                )
                
                # 4. Guardar todo el paquete de datos de esta combinación
                resultados_u.append({
                    'comb': cb_u,
                    'R_total': res_u['R_total'],
                    'qu_izq': trapecio['qu_izq'],
                    'qu_der': trapecio['qu_der'],
                    'franja': trapecio['franja'],
                    'x_res': res_u['x_resultante'],
                    'm_trans': res_u['m_trans_total']
                })
            
            # Convertir a DataFrame para tener una "Tabla Maestra de Diseño"
            df_diseno_u = pd.DataFrame(resultados_u)
            
            # --- G. CHEQUEO DE PUNZONAMIENTO (ENVOLVENTE POR COLUMNA) ---
            st.subheader("🛡️ Verificación de Punzonamiento ( punching shear)")
            
            resumen_punzonamiento = []
            
            # Iteramos por cada columna
            for info in info_nodos:
                col_id = info['id']
                geo_p = geometria_punzonamiento[col_id] # Recuperamos la geometría calculada antes
                
                max_vu = -1e9
                comb_critica_p = ""
                qu_en_centroide_critico = 0
                
                # Buscamos en todas las combinaciones últimas cuál es la más exigente para esta columna
                for cb_u in combs_ultimas:
                    # 1. Obtener Pu de esta columna en esta combinación
                    r_u = df_r[(df_r[col_nodo_r].astype(str).str.replace('.0','') == col_id) & 
                                 (df_r[col_comb] == cb_u)].iloc[0]
                    Pu_col = r_u[col_fz]
                    
                    # 2. Calcular presión en el centroide del área crítica (x_c, y=0)
                    # Necesitamos recuperar los datos de la combinación para evaluar q
                    res_u = engine.procesar_geometria_multicolumna(info_nodos, key_reac='reac_u') 
                    # (Asegúrate de que info['reac_u'] esté cargado para cb_u como en el bucle anterior)
                    
                    e_L_u = abs(Cx_real - res_u['x_resultante'])
                    M_long_u = e_L_u * res_u['R_total']
                    
                    q_cent = engine.calcular_q_en_punto(
                        geo_p['xc'], Cy_real, 
                        L_zapata, B_optimo, Cx_real, Cy_real, 
                        res_u['R_total'], M_long_u, res_u['m_trans_total']
                    )
                    
                    # 3. Vu = Pu - (q_contacto * Area_critica)
                    Vu_actual = Pu_col - (q_cent * geo_p['Ac'])
                    
                    if Vu_actual > max_vu:
                        max_vu = Vu_actual
                        comb_critica_p = cb_u
                        qu_en_centroide_critico = q_cent
            
                # 4. Consolidar resultados de la columna
                cumple = geo_p['phi_Vc'] > max_vu
                resumen_punzonamiento.append({
                    "Columna": col_id,
                    "Tipo": f"αs={geo_p['alpha_s']}",
                    "b0 [m]": round(geo_p['b0'], 2),
                    "Ac [m²]": round(geo_p['Ac'], 3),
                    "xc [m]": round(geo_p['xc'], 2),
                    "φVc [kN]": round(geo_p['phi_Vc'], 2),
                    "Vu Max [kN]": round(max_vu, 2),
                    "Comb. Crítica": comb_critica_p,
                    "Estado": "✅ OK" if cumple else "❌ FALLA"
                })
            
            # Mostrar Tabla de Resultados
            df_punz = pd.DataFrame(resumen_punzonamiento)
            st.table(df_punz)

            st.success(f"### ✅ Memoria Generada Exitosamente")
            
            # F. Resumen de Ingeniería
            st.markdown("---")
            st.write("**Notas de Memoria:**")
            st.write(f"- Se garantiza que el centro geométrico coincide con el centro de fuerzas de **{comb_maestra}** salvo ajuste manual ΔL/ΔT.")
            st.write("- El eje longitudinal se define como el vector que une los centros de las columnas extremas.")
            
else:
    st.warning("Cargue los archivos para iniciar la memoria.")
