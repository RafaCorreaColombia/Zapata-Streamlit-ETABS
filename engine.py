import pandas as pd
import numpy as np

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
    """
    Rota momentos globales al sistema local de la zapata.
    m_eje_long: Alrededor del eje longitudinal (afecta ancho B).
    m_eje_trans: Alrededor del eje transversal (afecta largo L).
    """
    m_eje_long = mx_global * np.cos(alpha) + my_global * np.sin(alpha)
    m_eje_trans = -mx_global * np.sin(alpha) + my_global * np.cos(alpha)
    return m_eje_long, m_eje_trans

# --- 3. LÓGICA MULTICOLUMNA Y RESULTANTES ---

def procesar_geometria_multicolumna(lista_nodos, key_reac='reac'):
    """
    Procesa 2 o 3 columnas. 
    lista_nodos debe estar ordenada físicamente de extremo a extremo.
    """
    p_ref = lista_nodos[0]['coords']
    p_fin = lista_nodos[-1]['coords']
    alpha = obtener_angulo_zapata(p_ref, p_fin)
    
    r_total = 0
    m_l_total = 0 # Vuelco longitudinal (alrededor del eje T)
    m_t_total = 0 # Vuelco transversal (alrededor del eje L)
    
    for nodo in lista_nodos:
        dist_rel = np.linalg.norm(nodo['coords'] - p_ref)
        reac = nodo[key_reac]
        
        # Rotación de momentos
        ml, mt = transformar_momentos_a_local(reac['MX'], reac['MY'], alpha)
        
        fz = abs(reac['FZ'])
        r_total += fz
        # Sumatoria de momentos respecto al primer nodo (p_ref)
        m_l_total += (fz * dist_rel + mt)
        m_t_total += ml
        
    x_res = m_l_total / r_total
    
    return {
        'L_ejes': np.linalg.norm(p_fin - p_ref),
        'dist_max_ejes': np.linalg.norm(p_fin - p_ref),
        'R_total': r_total,
        'x_resultante': x_res,
        'm_trans_total': m_t_total, # Momento total alrededor del eje L
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
        s = (abs(P)/A) + (abs(M_alrededor_T) * abs(x) / It) + (abs(M_alrededor_L) * abs(y) / Il)
        presiones.append(s)
    
    s_min = (abs(P)/A) - (abs(M_alrededor_T) * (L/2) / It) - (abs(M_alrededor_L) * (B/2) / Il)
    return max(presiones), s_min

def optimizar_ancho_B(L, P_total, M_trans, q_neto, B_min_fisico):
    B = B_min_fisico
    while B < 15.0:
        s_max, s_min = calcular_presiones_4_esquinas(L, B, P_total, 0, M_trans)
        if s_max <= q_neto and s_min >= 0:
            return round(B, 2)
        B += 0.05
    return round(B, 2)

# --- 5. VERIFICACIONES DE DISEÑO ---

def calcular_secciones_criticas(dist_ejes, g1, g2, H, b1, b2):
    # Nota: Esta función se mantiene para compatibilidad con el loop de 2 columnas
    d = H - 0.075
    def bo_calc(t3, t2, d_val, borde):
        if borde: return (2*(t3 + d_val/2)) + (t2 + d_val)
        return 2*(t3 + d_val) + 2*(t2 + d_val)
    return {
        'd': d,
        'bo1': bo_calc(g1['t3'], g1['t2'], d, b1),
        'bo2': bo_calc(g2['t3'], g2['t2'], d, b2)
    }

# --- 6. REFUERZO ---

def diseno_refuerzo(Mu, d, B, fc, fy=420):
    phi, b, d_mm = 0.9, B * 1000, d * 1000
    Mu_nm = Mu * 1e6
    as_min = 0.0018 * b * (d_mm + 75)
    Rn = Mu_nm / (phi * b * d_mm**2)
    m = fy / (0.85 * fc)
    rho = (1/m) * (1 - np.sqrt(max(0, 1 - 2*m*Rn/fy)))
    return round(max(rho * b * d_mm, as_min), 1)
