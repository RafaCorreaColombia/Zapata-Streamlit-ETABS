import numpy as np

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
