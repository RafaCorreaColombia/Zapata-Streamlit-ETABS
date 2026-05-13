import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches



# --- 1. PROCESAMIENTO DE DATOS ---
def procesar_csv_etabs(file):
    try:
        df = pd.read_csv(file, skiprows=1)
    except UnicodeDecodeError:
        file.seek(0)
        df = pd.read_csv(file, skiprows=1, encoding='latin-1')
    
    unidades = df.iloc[0].to_dict()
    unidades = {str(k).strip(): str(v).strip() for k, v in unidades.items()}
    df = df.drop(0).reset_index(drop=True)
    df.columns = df.columns.str.strip()
    
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            continue
    return df, unidades

def obtener_geometria_columna(nodo_id, df_conn, df_sum, df_sec):
    try:
        nid = str(int(float(nodo_id))) 
        for col_name in ['I-End Point', 'J-End Point']:
            df_conn[col_name] = pd.to_numeric(df_conn[col_name], errors='coerce').fillna(0).astype(int).astype(str)

        row_conn = df_conn[(df_conn['I-End Point'] == nid) | (df_conn['J-End Point'] == nid)]
        if row_conn.empty: return None
        
        col_label = str(row_conn['Column'].values[0]).strip()
        df_sum['Label'] = df_sum['Label'].astype(str).str.strip()
        row_sum = df_sum[df_sum['Label'] == col_label].iloc[0]
        nombre_seccion = str(row_sum['Analysis Section']).strip()
        
        df_sec['Name'] = df_sec['Name'].astype(str).str.strip()
        row_sec = df_sec[df_sec['Name'] == nombre_seccion].iloc[0]
        
        return {
            'label': col_label,
            'seccion': nombre_seccion,
            't3': row_sec['t3'] / 1000, 
            't2': row_sec['t2'] / 1000  
        }
    except:
        return None

# --- 2. TRANSFORMACIÓN DE COORDENADAS ---

def obtener_angulo_zapata(p1, p2):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return np.arctan2(dy, dx)

def transformar_momentos_a_local(mx_global, my_global, alpha):
    m_eje_long = mx_global * np.cos(alpha) + my_global * np.sin(alpha)
    m_eje_trans = -mx_global * np.sin(alpha) + my_global * np.cos(alpha)
    return m_eje_long, m_eje_trans

# --- 3. LÓGICA MULTICOLUMNA Y RESULTANTES ---

def procesar_geometria_multicolumna(lista_nodos, key_reac='reac'):
    p_ref = lista_nodos[0]['coords']
    p_fin = lista_nodos[-1]['coords']
    alpha = obtener_angulo_zapata(p_ref, p_fin)
    
    r_total = 0
    m_l_total = 0 
    m_t_total = 0 
    
    for nodo in lista_nodos:
        dist_rel = np.linalg.norm(nodo['coords'] - p_ref)
        reac = nodo[key_reac]
        ml, mt = transformar_momentos_a_local(reac['MX'], reac['MY'], alpha)
        
        fz = abs(reac['FZ'])
        r_total += fz
        m_l_total += (fz * dist_rel + mt)
        m_t_total += ml
        
    x_res = m_l_total / r_total
    y_resultante_carga = m_t_total / r_total
    
    return {
        'L_ejes': np.linalg.norm(p_fin - p_ref),
        'dist_max_ejes': np.linalg.norm(p_fin - p_ref),
        'R_total': r_total,
        'x_resultante': x_res,
        'y_resultante': y_resultante_carga,
        'm_trans_total': m_t_total, 
        'alpha': alpha
    }

# --- 4. PRESIONES Y OPTIMIZACIÓN ---

def calcular_presiones_4_esquinas(L, B, P, M_alrededor_T, M_alrededor_L):
    if L <= 0 or B <= 0: return 0.0, 0.0
    A = L * B
    It = (B * L**3) / 12
    Il = (L * B**3) / 12
    
    esquinas = [(L/2, B/2), (L/2, -B/2), (-L/2, B/2), (-L/2, -B/2)]
    presiones = []
    for x, y in esquinas:
        # P/A + M_T*x/It + M_L*y/Il
        s = (abs(P)/A) + (abs(M_alrededor_T) * abs(x) / It) + (abs(M_alrededor_L) * abs(y) / Il)
        presiones.append(s)
    
    # s_min considerando la resta para verificar tracción
    s_min = (abs(P)/A) - (abs(M_alrededor_T) * (L/2) / It) - (abs(M_alrededor_L) * (B/2) / Il)
    return max(presiones), s_min

def optimizar_ancho_B(L, P_total, M_long, M_trans, q_neto, B_min_fisico):
    B = np.ceil(B_min_fisico * 20) / 20
    while B < 15.0:
        s_max, s_min = calcular_presiones_4_esquinas(L, B, P_total, M_long, M_trans)
        if s_max <= q_neto and s_min >= 0:
            return round(B, 2)
        B += 0.05
    return round(B, 1)

def generar_planta_zapata(L, B, info_nodos, s1, Cx_real, Cy_real, xr, yr):
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # --- LÓGICA DE POSICIONAMIENTO ---
    # El centro de la zapata (en el eje X) está en Cx_real respecto al Nodo 1 (x=0)
    # Por lo tanto, el borde izquierdo de la zapata está en:
    x_inicio_zapata = Cx_real - (L / 2)
    y_inicio_zapata = Cy_real - (B / 2) # yr suele ser 0, centrado en el eje de los nodos
    
    # 1. Dibujar Contorno de la Zapata
    rect_zapata = patches.Rectangle(
        (x_inicio_zapata, y_inicio_zapata), L, B, 
        linewidth=2, edgecolor='black', facecolor='#f8f9fa', label='Zapata', zorder=1
    )
    ax.add_patch(rect_zapata)
    
    # 2. Dibujar Columnas
    for i, info in enumerate(info_nodos):
        # Distancia del nodo i respecto al Nodo 1 (x=0)
        dist_x = np.linalg.norm(info['coords'] - info_nodos[0]['coords'])
        t_long = info['geo']['t3']
        t_trans = info['geo']['t2']
        
        # El rectángulo de la columna se centra en su nodo
        rect_col = patches.Rectangle(
            (dist_x - t_long/2, -t_trans/2), t_long, t_trans, 
            linewidth=1.5, edgecolor='#800000', facecolor='#ff4b4b', alpha=0.8,
            label=f"Columnas" if i == 0 else "", zorder=3
        )
        ax.add_patch(rect_col)
        ax.text(dist_x, t_trans/2 + 0.1, f"N-{info['id']}", ha='center', fontweight='bold', fontsize=9)

    # 3. Marcar puntos de control
    # Centro Geométrico (X azul)
    ax.scatter([Cx_real], [0], color='blue', marker='x', s=120, label='Centro Geométrico (Cx)', zorder=4)
    # Resultante de Cargas (O verde)
    ax.scatter([xr], [yr], color='green', marker='o', s=120, edgecolors='white', label='Resultante (Xr)', zorder=5)
    
    # 4. Líneas de referencia (Ejes)
    ax.axhline(0, color='gray', lw=0.8, ls='--', alpha=0.5)
    
    # Configuración final
    ax.set_aspect('equal', adjustable='box')
    ax.set_title(f"Planta de Cimentación: L={L:.2f}m, B={B:.2f}m", fontsize=12, pad=15)
    ax.set_xlabel("Eje Longitudinal (m)")
    ax.set_ylabel("Eje Transversal (m)")
    
    # Leyenda y Grid
    ax.legend(loc='upper right', bbox_to_anchor=(1.25, 1))
    ax.grid(True, linestyle=':', alpha=0.4)
    
    # Ajuste dinámico de límites para que siempre se vea toda la zapata
    ax.set_xlim(x_inicio_zapata - 0.5, x_inicio_zapata + L + 0.5)
    ax.set_ylim(y_inicio_zapata - 0.5, y_inicio_zapata + B + 0.5)
    
    plt.tight_layout()
    return fig

# --- 5. MÉTRICAS PARA MEMORIA DE CÁLCULO ---

def _metricas_memoria(L, B, res_s, q_limite, comb_nombre, comb_maestra, e_L, e_T):
    """
    Calcula excentricidades y deltas de presión para la memoria.
    e_L y e_T vienen calculados desde app.py incluyendo los Deltas del usuario.
    """
    # 1. Porcentajes de excentricidad
    ratio_eL = (e_L / L) * 100
    ratio_eT = (e_T / B) * 100
    
    # 2. Presiones finales (Incluyendo momentos de excentricidad y momentos locales rotados)
    # M_alrededor_T (longitudinal) = P * e_L
    # M_alrededor_L (transversal) = Momento local rotado + P * e_T
    s_max, s_min = _presiones_4_esquinas(
        L, B, res_s['R_total'], 
        e_L * res_s['R_total'], 
        abs(res_s['m_trans_total']) + (e_T * res_s['R_total'])
    )
    
    # 3. Diferencia de presiones
    diff_p = ((s_max - s_min) / s_min * 100) if s_min > 0 else 999.0
    
    # 4. Criterios según tipo de combinación
    es_m = (comb_nombre == comb_maestra)
    c_e = 5.0 if es_m else 10.0
    c_p = 15.0 if es_m else 90.0
    
    return {
        "Combinación": comb_nombre,
        "P (kN)": round(res_s['R_total'], 1),
        "e_L (%)": round(ratio_eL, 2),
        "e_T (%)": round(ratio_eT, 2),
        "σ_max": round(s_max, 2),
        "σ_min": round(s_min, 2),
        "ΔP (%)": round(diff_p, 2),
        "Criterio E": "✅" if (ratio_eL <= c_e and ratio_eT <= c_e) else "⚠️",
        "Criterio P": "✅" if (not es_m or diff_p <= c_p) else "⚠️"
    }

# --- 6. VERIFICACIONES DE DISEÑO ---
def calcular_q_en_punto(x, y, L, B, Cx_real, Cy_real, P, M_long, M_trans):
    A = L * B
    It = (B * L**3) / 12
    Il = (L * B**3) / 12
    # x_rel es la distancia del punto al centro de la zapata (Cx_real)
    x_rel = x - Cx_real
    y_rel = y - Cy_real
    
    q = (abs(P)/A) + (M_long * x_rel / It) + (abs(M_trans) * y_rel / Il)
    return max(0, q) # No permitimos presiones negativas (tracción) en el diseño

def analizar_columna_punzonamiento(x_node, y_node, tL, tT, d, L_zap, B_zap, Cx_real, f_c):
    """
    Calcula b0, Ac, Centroide y phiVc para una columna específica.
    """
    # 1. Límites de la zapata
    x_min, x_max = Cx_real - L_zap/2, Cx_real + L_zap/2
    y_min, y_max = -B_zap/2, B_zap/2
    
    # 2. Límites teóricos de la falla (distancia d/2 de las caras)
    x1, x2 = x_node - (tL/2 + d/2), x_node + (tL/2 + d/2)
    y1, y2 = y_node - (tT/2 + d/2), y_node + (tT/2 + d/2)
    
    # 3. Verificación de bordes (Truncamiento)
    es_borde_izq = x1 < x_min
    es_borde_der = x2 > x_max
    es_borde_inf = y1 < y_min
    es_borde_sup = y2 > y_max
    
    # Recorte a los límites reales de la zapata
    x1_r, x2_r = max(x1, x_min), min(x2, x_max)
    y1_r, y2_r = max(y1, y_min), min(y2, y_max)
    
    # 4. Cálculo de b0 (Perímetro crítico real)
    # Solo sumamos los lados que NO están en contacto con el borde del aire
    b0 = 0
    lados_libres = 0
    if not es_borde_izq: b0 += (y2_r - y1_r); lados_libres += 1
    if not es_borde_der: b0 += (y2_r - y1_r); lados_libres += 1
    if not es_borde_inf: b0 += (x2_r - x1_r); lados_libres += 1
    if not es_borde_sup: b0 += (x2_r - x1_r); lados_libres += 1
    
    # 5. Identificación de Alpha_s
    # 0 bordes = Interior (40), 1 borde = Borde (30), 2 bordes = Esquina (20)
    num_bordes = sum([es_borde_izq, es_borde_der, es_borde_inf, es_borde_sup])
    alpha_s = 40 if num_bordes == 0 else (30 if num_bordes == 1 else 20)
    
    # 6. Parámetros de resistencia (NSR-10 / ACI 318)
    beta = max(tL, tT) / min(tL, tT) # Relación de aspecto de la columna
    
    # Las tres ecuaciones de Vc (en Newtons, luego pasamos a kN)
    # Suponiendo f_c en MPa, b0 y d en mm
    b0_mm = b0 * 1000
    d_mm = d * 1000
    f_c_sqrt = f_c**0.5
    
    vc1 = 0.33 * f_c_sqrt * b0_mm * d_mm
    vc2 = 0.17 * (1 + 2/beta) * f_c_sqrt * b0_mm * d_mm
    vc3 = 0.083 * (2 + (alpha_s * d_mm / b0_mm)) * f_c_sqrt * b0_mm * d_mm
    
    Vc_nominal = min(vc1, vc2, vc3) / 1000 # Pasar a kN
    phi_Vc = 0.75 * Vc_nominal
    
    return {
        'b0': b0,
        'Ac': (x2_r - x1_r) * (y2_r - y1_r),
        'xc': (x1_r + x2_r) / 2,
        'alpha_s': alpha_s,
        'phi_Vc': phi_Vc,
        'num_bordes': num_bordes
    }


def obtener_trapecio_diseno_u(L, B, Cx_real, P_total, M_long, M_trans):
    """
    Evalúa las presiones en y = ±B/4 para encontrar la franja crítica
    y retorna los esfuerzos en los extremos longitudinales (x=0 y x=L de la zapata).
    """
    # Coordenadas de los extremos de la zapata respecto al Nodo 1
    x_izq = Cx_real - L/2
    x_der = Cx_real + L/2
    y_sensor = B / 4
    
    # 1. Evaluamos en los 4 sensores (esquinas de las franjas B/2 centrales de cada mitad)
    q_norte_izq = calcular_q_en_punto(x_izq,  y_sensor, L, B, Cx_real, Cy_real, P_total, M_long, M_trans)
    q_norte_der = calcular_q_en_punto(x_der,  y_sensor, L, B, Cx_real, Cy_real, P_total, M_long, M_trans)
    q_sur_izq   = calcular_q_en_punto(x_izq, -y_sensor, L, B, Cx_real, Cy_real, P_total, M_long, M_trans)
    q_sur_der   = calcular_q_en_punto(x_der, -y_sensor, L, B, Cx_real, Cy_real, P_total, M_long, M_trans)
    
    # 2. Decisión de la franja ganadora (la que tenga mayor promedio de presión)
    if (q_norte_izq + q_norte_der) > (q_sur_izq + q_sur_der):
        qu_izq, qu_der = q_norte_izq, q_norte_der
        franja = "Norte (+B/4)"
    else:
        qu_izq, qu_der = q_sur_izq, q_sur_der
        franja = "Sur (-B/4)"
        
    return {
        'qu_izq': qu_izq, 
        'qu_der': qu_der, 
        'franja': franja
    }



def diseno_refuerzo(Mu, d, B, fc, fy=420):
    phi, b, d_mm = 0.9, B * 1000, d * 1000
    Mu_nm = Mu * 1e6
    as_min = 0.0018 * b * (d_mm + 75)
    Rn = Mu_nm / (phi * b * d_mm**2)
    m = fy / (0.85 * fc)
    rho = (1/m) * (1 - np.sqrt(max(0, 1 - 2*m*Rn/fy)))
    return round(max(rho * b * d_mm, as_min), 1)
