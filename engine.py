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
        # 1. Limpiar el ID del nodo: De 3.0 (float) -> 3 (int) -> "3" (str)
        # Esto elimina el ".0" que genera el error de búsqueda
        nid = str(int(float(nodo_id))) 

        # 2. Limpiar la tabla de conectividad (I-End y J-End)
        # Convertimos a float primero, luego a int y luego a str para asegurar formato "3"
        for col_name in ['I-End Point', 'J-End Point']:
            df_conn[col_name] = pd.to_numeric(df_conn[col_name], errors='coerce').fillna(0).astype(int).astype(str)

        # 3. Buscar el nodo en la conectividad
        row_conn = df_conn[(df_conn['I-End Point'] == nid) | (df_conn['J-End Point'] == nid)]
        
        if row_conn.empty:
            return None
        
        col_label = str(row_conn['Column'].values[0]).strip()
        
        # 4. Buscar en Summary (limpiando espacios)
        df_sum['Label'] = df_sum['Label'].astype(str).str.strip()
        row_sum = df_sum[df_sum['Label'] == col_label].iloc[0]
        nombre_seccion = str(row_sum['Analysis Section']).strip()
        
        # 5. Buscar en Sections (limpiando espacios)
        df_sec['Name'] = df_sec['Name'].astype(str).str.strip()
        row_sec = df_sec[df_sec['Name'] == nombre_seccion].iloc[0]
        
        return {
            'label': col_label,
            'seccion': nombre_seccion,
            't3': row_sec['t3'] / 1000, # m
            't2': row_sec['t2'] / 1000  # m
        }
    except Exception as e:
        return None

# --- 2. TRANSFORMACIÓN Y GEOMETRÍA ---
def rotar_momentos(mx_global, my_global, angle):
    m_long = mx_global * np.cos(angle) + my_global * np.sin(angle)
    m_trans = -mx_global * np.sin(angle) + my_global * np.cos(angle)
    return m_long, m_trans

def procesar_geometria_y_cargas(p1, p2, reac1, reac2):
    vector_z = p2 - p1
    L_ejes = np.linalg.norm(vector_z)
    alpha = np.arctan2(vector_z[1], vector_z[0])
    
    ml_1, mt_1 = rotar_momentos(reac1['MX'], reac1['MY'], alpha)
    ml_2, mt_2 = rotar_momentos(reac2['MX'], reac2['MY'], alpha)
    
    R = reac1['FZ'] + reac2['FZ']
    x_res = (reac2['FZ'] * L_ejes + mt_1 + mt_2) / R
    return {
        'L_ejes': L_ejes, 'R_total': R, 'x_resultante': x_res,
        'alpha': alpha, 'm_trans_total': ml_1 + ml_2 
    }

# --- 3. DISEÑO Y VERIFICACIONES ---
def calcular_presiones_4_esquinas(L, B, P, M_long, M_trans):
    A = L * B
    Ix, Iy = (B * L**3) / 12, (L * B**3) / 12
    esquinas = [(L/2, B/2), (L/2, -B/2), (-L/2, B/2), (-L/2, -B/2)]
    presiones = [ (P/A) + (M_long * x / Ix) + (M_trans * y / Iy) for x, y in esquinas ]
    return max(presiones), min(presiones)

def optimizar_ancho_B(L, P_total, M_trans, q_neto, B_min_fisico):
    B = B_min_fisico
    while B < 10.0:
        s_max, s_min = calcular_presiones_4_esquinas(L, B, P_total, 0, M_trans)
        if s_max <= q_neto and s_min >= 0:
            return round(B, 2)
        B += 0.05
    return B

def calcular_secciones_criticas(dist_ejes, g1, g2, H, b1, b2):
    d = H - 0.075
    def bo_calc(t3, t2, d_val, borde):
        return (2*(t3+d_val) + t2+d_val) if borde else 2*(t3+d_val + t2+d_val)
    return {
        'd': d, 'bo1': bo_calc(g1['t3'], g1['t2'], d, b1),
        'bo2': bo_calc(g2['t3'], g2['t2'], d, b2)
    }

def analizar_combinaciones_diseno(df_r, nodos, combs, col_nodo, col_comb, col_fz, L, B, g1, g2, H, b1, b2):
    res = {'vu_1d_max': 0, 'vu_2d_c1_max': 0, 'vu_2d_c2_max': 0, 'comb_critica_1d': '', 'comb_critica_2d': ''}
    d = H - 0.075
    for c in combs:
        r1 = df_r[(df_r[col_nodo] == nodos[0]) & (df_r[col_comb] == c)].iloc[0]
        r2 = df_r[(df_r[col_nodo] == nodos[1]) & (df_r[col_comb] == c)].iloc[0]
        qu = (r1[col_fz] + r2[col_fz]) / (L * B)
        v1d = abs(qu * B * ( (L/2) - (g1['t3']/2) - d ))
        
        a1 = (g1['t3']+d)*(g1['t2']+d) if not b1 else (g1['t3']+d/2)*(g1['t2']+d)
        a2 = (g2['t3']+d)*(g2['t2']+d) if not b2 else (g2['t3']+d/2)*(g2['t2']+d)
        v2d1, v2d2 = r1[col_fz] - (qu * a1), r2[col_fz] - (qu * a2)

        if v1d > res['vu_1d_max']: res['vu_1d_max'], res['comb_critica_1d'] = v1d, c
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
