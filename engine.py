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




def calcular_vu_1d(qu, B, L, dist_ejes, g1, g2, d):
    """
    Calcula el Vu a una distancia d de las caras internas de las columnas.
    """
    # Cara interna de Col 1 (ubicada en x=0)
    cara_interna_c1 = g1['t3'] / 2
    # Cara interna de Col 2 (ubicada en x=dist_ejes)
    cara_interna_c2 = dist_ejes - (g2['t3'] / 2)
    
    # Secciones críticas
    seccion_v1 = cara_interna_c1 + d
    seccion_v2 = cara_interna_c2 - d
    
    # El cortante 1D es la presión acumulada en el voladizo o entre apoyos
    # Simplificación: qu * Area de la zona tributaria
    # Vu = qu * B * (distancia_al_punto_de_cero_cortante)
    
    # Para una zapata combinada, el Vu 1D máximo suele ser:
    Vu_max = qu * B * (dist_ejes / 2 - cara_interna_c1 - d) 
    
    return abs(Vu_max)




def calcular_vu_punzonamiento(P_u_columna, qu, t3, t2, d, es_borde):
    """
    P_u_columna: Carga última de la columna (FZ de ETABS con combo de diseño)
    """
    if es_borde:
        # Área dentro del perímetro crítico (3 lados)
        area_critica = (t3 + d/2) * (t2 + d)
    else:
        # Área dentro del perímetro crítico (4 lados)
        area_critica = (t3 + d) * (t2 + d)
        
    # Vu es la carga que "intenta" atravesar la zapata
    Vu_punzon = P_u_columna - (qu * area_critica)
    
    return Vu_punzon



# --- En app.py, dentro del botón de diseño ---

st.subheader("🛡️ Verificación de Cortante (Peor Caso de Diseño)")

# Ejecutar el bucle de todas las combinaciones de diseño
res_diseno = engine.analizar_combinaciones_diseno(
    df_r, nodos_sel, combs_sel, col_nodo_r, col_comb, col_fz, 
    L_zapata, B_optimo, g1, g2, H_calc, es_borde_1, es_borde_2
)

# Capacidades Nominales (Phi * Vn)
phi_v = 0.75
lambda_c = 1.0
vn_1d = (0.17 * lambda_c * np.sqrt(fc) * (B_optimo * 1000) * (d * 1000)) / 1000 # kN

# Punzonamiento (La más restrictiva de las 3 fórmulas ACI)
vn_2d_c1 = (0.33 * lambda_c * np.sqrt(fc) * (criticos['bo_1'] * 1000) * (d * 1000)) / 1000 # kN

# Crear Tabla de Resultados
data_check = {
    "Chequeo": ["Cortante 1D", f"Punzonamiento {g1['label']}", f"Punzonamiento {g2['label']}"],
    "Demanda (Vu)": [f"{res_diseno['vu_1d_max']:.1f} kN", f"{res_diseno['vu_2d_c1_max']:.1f} kN", f"{res_diseno['vu_2d_c2_max']:.1f} kN"],
    "Capacidad (φVn)": [f"{phi_v*vn_1d:.1f} kN", f"{phi_v*vn_2d_c1:.1f} kN", f"{phi_v*vn_2d_c1:.1f} kN"],
    "Estado": [
        "✅ OK" if res_diseno['vu_1d_max'] < phi_v*vn_1d else "❌ FALLA",
        "✅ OK" if res_diseno['vu_2d_c1_max'] < phi_v*vn_2d_c1 else "❌ FALLA",
        "✅ OK" if res_diseno['vu_2d_c2_max'] < phi_v*vn_2d_c1 else "❌ FALLA"
    ]
}

st.table(pd.DataFrame(data_check))
st.caption(f"Combinación crítica para 1D: {res_diseno['comb_critica_1d']}")
st.caption(f"Combinación crítica para Punzonamiento: {res_diseno['comb_critica_2d']}")




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
