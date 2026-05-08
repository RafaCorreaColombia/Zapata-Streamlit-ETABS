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
        # En ETABS Mx hace rotar alrededor de X. 
        # Para alinearlo con la zapata usamos la matriz de rotación:
        m_long = mx_global * np.cos(angle) + my_global * np.sin(angle)
        m_trans = -mx_global * np.sin(angle) + my_global * np.cos(angle)
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

def calcular_secciones_criticas(dist_ejes, geom_c1, geom_c2, H):
    d = H - 0.075 # Peralte efectivo (suponiendo recubrimiento de 7.5cm)
    
    # Supongamos que t3 está alineado con el eje largo de la zapata (X-local)
    # Cara de la columna 1: -t3_1/2
    # Cara de la columna 2: dist_ejes + t3_2/2
    
    # Cortante 1D: Se evalúa a 'd' de la cara
    x_critico_v1 = (geom_c1['t3']/2) + d
    x_critico_v2 = dist_ejes - (geom_c2['t3']/2) - d
    
    # Punzonamiento: Perímetro a d/2 de las caras
    bo_1 = 2 * (geom_c1['t3'] + d) + 2 * (geom_c1['t2'] + d)
    # (Aquí deberías validar si es de borde para restar un lado del perímetro)
    
    return x_critico_v1, x_critico_v2, bo_1, d





