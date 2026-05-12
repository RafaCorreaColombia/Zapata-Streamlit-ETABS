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

import pandas as pd
import numpy as np



# --- 2. LÓGICA DE TRANSFORMACIÓN DE COORDENADAS ---

def obtener_angulo_zapata(p1, p2):
    """
    Calcula el ángulo de inclinación del eje longitudinal (Nodo1 -> Nodo2)
    respecto al eje X global.
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return np.arctan2(dy, dx)

def transformar_momentos_a_local(mx_global, my_global, alpha):
    """
    Transforma momentos globales de ETABS a ejes locales de la zapata.
    
    CONVENCIÓN ADOPTADA:
    - M_long: Momento que actúa ALREDEDOR del eje longitudinal. 
              Produce flexión en el sentido TRANSVERSAL (hacia el ancho B).
    - M_trans: Momento que actúa ALREDEDOR del eje transversal. 
               Produce flexión en el sentido LONGITUDINAL (hacia el largo L).
               
    Regla de la mano derecha: 
    Rotamos los vectores momento (Mx, My) como vectores posición.
    """
    # Rotación de vectores:
    # M_eje_L = Mx * cos(a) + My * sin(a)
    # M_eje_T = -Mx * sin(a) + My * cos(a)
    
    m_eje_long = mx_global * np.cos(alpha) + my_global * np.sin(alpha)
    m_eje_trans = -mx_global * np.sin(alpha) + my_global * np.cos(alpha)
    
    # Para el diseño:
    # El momento que nos importa para centrar la zapata (X_res) es el que 
    # hace girar la zapata en su sentido largo. Ese es el m_eje_trans.
    
    return m_eje_long, m_eje_trans

# --- 3. LÓGICA DE PRESIONES Y ESTABILIDAD ---

def calcular_presiones_4_esquinas(L, B, P, M_alrededor_T, M_alrededor_L):
    """
    Calcula presiones considerando:
    M_alrededor_T: Momento que genera excentricidad en la longitud L.
    M_alrededor_L: Momento que genera excentricidad en el ancho B.
    """
    if L <= 0 or B <= 0: return 0.0, 0.0
    A = L * B
    # Inercias respecto a los ejes que pasan por el centroide
    # I_alrededor_T (eje transversal) = B * L^3 / 12
    # I_alrededor_L (eje longitudinal) = L * B^3 / 12
    It = (B * L**3) / 12
    Il = (L * B**3) / 12
    
    # Esquinas (x_local, y_local)
    esquinas = [(L/2, B/2), (L/2, -B/2), (-L/2, B/2), (-L/2, -B/2)]
    presiones = []
    for x, y in esquinas:
        # P/A + M_T * x / It + M_L * y / Il
        s = (abs(P)/A) + (abs(M_alrededor_T) * abs(x) / It) + (abs(M_alrededor_L) * abs(y) / Il)
        presiones.append(s)
        
    # s_min considerando resta de efectos para verificar tracción
    s_min = (abs(P)/A) - (abs(M_alrededor_T) * (L/2) / It) - (abs(M_alrededor_L) * (B/2) / Il)
    
    return max(presiones), s_min

# --- 4. INTEGRACIÓN EN GEOMETRÍA Y CARGAS ---

def procesar_geometria_y_cargas(p1, p2, reac1, reac2):
    """
    Calcula la distancia entre ejes, ángulo de rotación y momentos locales.
    """
    vector_z = p2 - p1
    L_ejes = np.linalg.norm(vector_z)
    alpha = obtener_angulo_zapata(p1, p2)
    
    # Transformar momentos de ambos nodos
    ml_1, mt_1 = transformar_momentos_a_local(reac1['MX'], reac1['MY'], alpha)
    ml_2, mt_2 = transformar_momentos_a_local(reac2['MX'], reac2['MY'], alpha)
    
    R = abs(reac1['FZ']) + abs(reac2['FZ'])
    
    # CENTROIDE (X_res):
    # Sumatoria de momentos respecto al Nodo 1 en el eje transversal local.
    # El momento mt_1 y mt_2 (alrededor del eje T) inclinan la zapata en sentido L.
    x_res = (abs(reac2['FZ']) * L_ejes + mt_1 + mt_2) / R
    
    return {
        'L_ejes': L_ejes, 
        'R_total': R, 
        'x_resultante': x_res,
        'alpha_deg': np.degrees(alpha),
        'm_long_total': ml_1 + ml_2, # Momento total alrededor del eje L (vuelco en B)
        'm_trans_total': mt_1 + mt_2  # Momento total alrededor del eje T (vuelco en L)
    }



# --- 5. VERIFICACIONES DE DISEÑO ---

def calcular_secciones_criticas(dist_ejes, g1, g2, H, b1, b2):
    d = H - 0.075
    def bo_calc(t3, t2, d_val, borde):
        if borde: return (2*(t3 + d_val/2)) + (t2 + d_val)
        return 2*(t3 + d_val) + 2*(t2 + d_val)
    
    return {
        'd': d,
        'bo1': bo_calc(g1['t3'], g1['t2'], d, b1),
        'bo2': bo_calc(g2['t3'], g2['t2'], d, b2)
    }

def analizar_combinaciones_diseno(df_r, nodos, combs, col_nodo, col_comb, col_fz, L, B, g1, g2, H, b1, b2):
    res = {'vu_1d_max': 0.0, 'vu_2d_c1_max': 0.0, 'vu_2d_c2_max': 0.0, 'comb_critica_1d': '', 'comb_critica_2d': ''}
    d = H - 0.075
    df_temp = df_r.copy()
    df_temp[col_nodo] = df_temp[col_nodo].astype(str).str.replace('.0', '', regex=False).str.strip()
    n1_id, n2_id = str(nodos[0]).replace('.0', ''), str(nodos[1]).replace('.0', '')

    for c in combs:
        f1 = df_temp[(df_temp[col_nodo] == n1_id) & (df_temp[col_comb] == c)]
        f2 = df_temp[(df_temp[col_nodo] == n2_id) & (df_temp[col_comb] == c)]
        if f1.empty or f2.empty: continue
            
        r1, r2 = f1.iloc[0], f2.iloc[0]
        qu = (abs(r1[col_fz]) + abs(r2[col_fz])) / (L * B)
        v1d = abs(qu * B * ( (L/2) - (g1['t3']/2) - d ))
        
        a1 = (g1['t3']+d)*(g1['t2']+d) if not b1 else (g1['t3']+d/2)*(g1['t2']+d)
        a2 = (g2['t3']+d)*(g2['t2']+d) if not b2 else (g2['t3']+d/2)*(g2['t2']+d)
        v2d1, v2d2 = abs(r1[col_fz]) - (qu * a1), abs(r2[col_fz]) - (qu * a2)

        if v1d > res['vu_1d_max']:
            res['vu_1d_max'], res['comb_critica_1d'] = v1d, c
        if max(v2d1, v2d2) > max(res['vu_2d_c1_max'], res['vu_2d_c2_max']):
            res['vu_2d_c1_max'], res['vu_2d_c2_max'], res['comb_critica_2d'] = v2d1, v2d2, c
    return res

def diseno_refuerzo(Mu, d, B, fc, fy=420):
    phi, b, d_mm = 0.9, B * 1000, d * 1000
    Mu_nm = Mu * 1e6
    as_min = 0.0018 * b * (d_mm + 75)
    Rn = Mu_nm / (phi * b * d_mm**2)
    m = fy / (0.85 * fc)
    rho = (1/m) * (1 - np.sqrt(max(0, 1 - 2*m*Rn/fy)))
    return round(max(rho * b * d_mm, as_min), 1)
