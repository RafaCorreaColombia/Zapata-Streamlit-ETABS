import numpy as np


def obtener_geometria_columna(nodo_id, df_conn, df_sum, df_sec):
    try:
        # 1. Nodo -> Label de Columna (ej: 14 -> C1)
        # Buscamos en I-End Point o J-End Point
        row_conn = df_conn[(df_conn['I-End Point'] == nodo_id) | (df_conn['J-End Point'] == nodo_id)]
        col_label = row_conn['Column'].values[0]
        
        # 2. Label -> Nombre de Sección (ej: C1 -> C4040)
        row_sum = df_sum[df_sum['Label'] == col_label].iloc[0]
        nombre_seccion = row_sum['Analysis Section']
        
        # 3. Nombre -> Dimensiones (ej: C4040 -> t3=400, t2=400)
        row_sec = df_sec[df_sec['Name'] == nombre_seccion].iloc[0]
        return {
            'label': col_label,
            'seccion': nombre_seccion,
            't3': row_sec['t3'] / 1000, # pasar a metros
            't2': row_sec['t2'] / 1000
        }
    except:
        return None
        


def procesar_geometria_y_cargas(p1, p2, reacciones_n1, reacciones_n2):
    """
    p1, p2: arrays [x, y] de coordenadas
    reacciones_n1: dict con {'FZ': fz, 'MX': mx, 'MY': my}
    """
    # 1. Vector director de la zapata (de Col 1 a Col 2)
    vector_z = p2 - p1
    L_ejes = np.linalg.norm(vector_z)
    
    # Angulo de inclinación de la zapata respecto al eje X global
    alpha = np.arctan2(vector_z[1], vector_z[0])
    
    # 2. Transformación de Momentos a sistema local de la zapata
    # Convención: X_local alineado con el eje de la zapata
        def rotar_momentos(mx_global, my_global, angle):
        # Transformación de componentes de vector momento al sistema local de la zapata
        # m_longitudinal: momento que produce flexión en el sentido corto (eje local X)
        # m_transversal: momento que produce flexión en el sentido largo (eje local Y)
        m_long = mx_global * np.cos(angle) + my_global * np.sin(angle)
        m_trans = -mx_global * np.sin(angle) + my_global * np.cos(angle)
    
        # Si tu convención manual es antihoraria, verifica el signo resultante 
        # según cómo definas el eje Z (hacia arriba o hacia abajo).
        return m_long, m_trans

    ml_1, mt_1 = rotar_momentos(reacciones_n1['MX'], reacciones_n1['MY'], alpha)
    ml_2, mt_2 = rotar_momentos(reacciones_n2['MX'], reacciones_n2['MY'], alpha)

    # 3. Ubicación de la Resultante (Carga Permanente D+L)
    # Sumatoria de momentos respecto al punto p1 para hallar x_barra
    P1 = reacciones_n1['FZ']
    P2 = reacciones_n2['FZ']
    
    # La resultante R actúa a una distancia 'x_res' desde el Nodo 1
    # Teniendo en cuenta momentos locales y cargas verticales
    R = P1 + P2
    # Suma de Momentos en el Nodo 1 (Sentido horario/antihorario según tu convención)
    # x_res = (P2 * L_ejes + M_trans_total) / R
    x_res = (P2 * L_ejes + mt_1 + mt_2) / R
    
    return {
        'L_ejes': L_ejes,
        'R_total': R,
        'x_resultante': x_res, # Distancia desde Nodo 1 al centro de presiones
        'alpha_deg': np.degrees(alpha)
    }




# --- LÓGICA DE DISEÑO (Engine) ---

def calcular_secciones_criticas(dist_ejes, geom_c1, geom_c2, H, es_borde_1=False, es_borde_2=False):
    d = H - 0.075  # Peralte efectivo en metros
    
    # 1. Cortante 1D (a distancia 'd' de la cara de la columna)
    # Columna 1 está en x=0, Columna 2 está en x=dist_ejes
    x_crit_v1 = (geom_c1['t3'] / 2) + d
    x_crit_v2 = dist_ejes - (geom_c2['t3'] / 2) - d
    
    # 2. Punzonamiento (bo)
    def calcular_bo(t3, t2, peralte, es_borde):
        if es_borde:
            # Perímetro de 3 lados (asumiendo que el borde corta el lado t2)
            return (2 * (t3 + peralte/2)) + (t2 + peralte)
        else:
            # Perímetro completo de 4 lados
            return 2 * (t3 + peralte) + 2 * (t2 + peralte)

    bo_1 = calcular_bo(geom_c1['t3'], geom_c1['t2'], d, es_borde_1)
    bo_2 = calcular_bo(geom_c2['t3'], geom_c2['t2'], d, es_borde_2)
    
    return {
        'x_v1': x_crit_v1,
        'x_v2': x_crit_v2,
        'bo_1': bo_1,
        'bo_2': bo_2,
        'd': d
    }




def optimizar_ancho_B(L, R_total, M_trans_total, q_neto, B_min_geom):
    """
    Busca el ancho B que cumpla que la presión máxima sea menor al q_neto.
    B_min_geom: El ancho mínimo para que las columnas quepan físicamente.
    """
    # Empezamos con el ancho mínimo físico
    B = B_min_geom
    paso = 0.05 # incrementos de 5cm
    
    while True:
        area = L * B
        inercia_y = (L * B**3) / 12 # inercia transversal
        # Suponiendo excentricidad accidental o momentos transversales
        sigma_max = (R_total / area) + (abs(M_trans_total) * (B/2) / inercia_y)
        
        if sigma_max <= q_neto:
            break
        B += paso
        if B > 10.0: # Límite de seguridad para evitar bucles infinitos
            return None
            
    return round(B, 2)



