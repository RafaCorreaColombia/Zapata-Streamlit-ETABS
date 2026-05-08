import pandas as pd
import numpy as np

# --- 1. PROCESAMIENTO DE DATOS ---

def procesar_csv_etabs(file):
    """
    Lector universal para cualquier tabla de ETABS (v16 a v21+).
    Salta el título, captura unidades y limpia nombres de columnas.
    """
    # 1. Leer saltando la primera fila (TABLE: XXX)
    df = pd.read_csv(file, skiprows=1)
    
    # 2. Capturar unidades (Fila 0 después del skip) y limpiar espacios
    unidades = df.iloc[0].to_dict()
    unidades = {str(k).strip(): str(v).strip() for k, v in unidades.items()}
    
    # 3. Limpiar el DataFrame
    df = df.drop(0).reset_index(drop=True)
    df.columns = df.columns.str.strip() # Quita espacios de los títulos de columnas
    
    # 4. Convertir a números lo que sea numérico
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='ignore')
        
    return df, unidades

def obtener_geometria_columna(nodo_id, df_conn, df_sum, df_sec):
    try:
        # Nodo -> Label de Columna
        row_conn = df_conn[(df_conn['I-End Point'] == nodo_id) | (df_conn['J-End Point'] == nodo_id)]
        col_label = row_conn['Column'].values[0]
        # Label -> Nombre de Sección
        row_sum = df_sum[df_sum['Label'] == col_label].iloc[0]
        nombre_seccion = row_sum['Analysis Section']
        # Nombre -> Dimensiones
        row_sec = df_sec[df_sec['Name'] == nombre_seccion].iloc[0]
        return {
            'label': col_label,
            'seccion': nombre_seccion,
            't3': row_sec['t3'] / 1000, # m (Dirección Longitudinal)
            't2': row_sec['t2'] / 1000  # m (Dirección Transversal)
        }
    except:
        return None

# --- 2. TRANSFORMACIÓN Y GEOMETRÍA ---

def rotar_momentos(mx_global, my_global, angle):
    """Transforma Mx y My globales al eje local de la zapata."""
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
    # x_res: distancia desde Nodo 1 a la resultante
    x_res = (reac2['FZ'] * L_ejes + mt_1 + mt_2) / R
    
    return {
        'L_ejes': L_ejes,
        'R_total': R,
        'x_resultante': x_res,
        'alpha': alpha,
        'm_trans_total': ml_1 + ml_2 # Momento que genera excentricidad en B
    }

# --- 3. DISEÑO Y VERIFICACIONES ---

def calcular_presiones_4_esquinas(L, B, P, M_long, M_trans):
    """Calcula presiones en las 4 esquinas para verificar estabilidad."""
    A = L * B
    Ix = (B * L**3) / 12
    Iy = (L * B**3) / 12
    
    # Coordenadas de las esquinas respecto al centro
    esquinas = [(L/2, B/2), (L/2, -B/2), (-L/2, B/2), (-L/2, -B/2)]
    presiones = []
    for x, y in esquinas:
        sigma = (P/A) + (M_long * x / Ix) + (M_trans * y / Iy)
        presiones.append(sigma)
    return max(presiones), min(presiones)

def optimizar_ancho_B(L, P_total, M_trans, q_neto, B_min_fisico):
    """Itera B para que sigma_max < q_neto y no haya tensiones."""
    B = B_min_fisico
    while B < 10.0:
        s_max, s_min = calcular_presiones_4_esquinas(L, B, P_total, 0, M_trans)
        if s_max <= q_neto and s_min >= 0:
            return round(B, 2)
        B += 0.05
    return B

def calcular_secciones_criticas(dist_ejes, g1, g2, H, es_borde1, es_borde2):
    d = H - 0.075
    # Cortante 1D a distancia 'd' de la cara de la columna
    x_v1 = (g1['t3']/2) + d
    x_v2 = dist_ejes - (g2['t3']/2) - d
    
    # Punzonamiento bo
    def bo_calc(t3, t2, d, borde):
        return (2*(t3+d) + t2+d) if borde else 2*(t3+d + t2+d)

    return {
        'd': d,
        'bo1': bo_calc(g1['t3'], g1['t2'], d, es_borde1),
        'bo2': bo_calc(g2['t3'], g2['t2'], d, es_borde2),
        'xv1': x_v1, 'xv2': x_v2
    }

def diseno_refuerzo(Mu, d, B, fc, fy=420):
    """Calcula el acero requerido por flexión (ACI 318)."""
    phi = 0.9
    b = B * 1000 # mm
    d_mm = d * 1000
    Mu_nm = Mu * 1e6 # N-mm
    
    # Cuantía mínima (0.0018 para retracción y temperatura)
    as_min = 0.0018 * b * (d_mm + 75)
    
    # Ecuación de diseño
    Rn = Mu_nm / (phi * b * d_mm**2)
    m = fy / (0.85 * fc)
    rho = (1/m) * (1 - np.sqrt(1 - 2*m*Rn/fy))
    
    as_req = max(rho * b * d_mm, as_min)
    return round(as_req, 1) # mm2
