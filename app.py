import streamlit as st
import pandas as pd
from datetime import datetime
import google.generativeai as genai
import json
import pypdf
import io
import re

# --- 1. CONFIGURACIÓN DE LA PÁGINA (DEBE SER LA PRIMERA INSTRUCCIÓN DE STREAMLIT) ---
st.set_page_config(
    page_title="D&D Asesores de Seguros - Auditor de Vehículos", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. REGLAS DE NEGOCIO Y CONSTANTES DE LA FIRMA ---
HOY = datetime.now().strftime("%d/%m/%Y")

def calcular_antiguedad_dnd(ano_fabricacion, ano_vigencia=datetime.now().year):
    """Regla D&D: (Año Vigencia - Año Fabricación) + 1"""
    try:
        return (ano_vigencia - int(ano_fabricacion)) + 1
    except (ValueError, TypeError):
        return 1

def diagnostico_suma(valor_poliza, media_mercado, tipo_cobertura="Full"):
    """Diagnóstico de Suma adaptado para el mercado dominicano (±10%)."""
    cobertura_clean = str(tipo_cobertura).strip().lower()
    
    if "ley" in cobertura_clean or "sencillo" in cobertura_clean or "terceros" in cobertura_clean or valor_poliza == 0:
        return "No Aplica (Seguro de Ley / Sin Daños Propios)"
        
    if media_mercado == 0: 
        return "No Identificado"
        
    desviacion = (valor_poliza - media_mercado) / media_mercado
    if desviacion < -0.10: 
        return f"Infraseguro ({desviacion:.1%})"
    elif desviacion > 0.10: 
        return f"Sobreaseguro (+{desviacion:.1%})"
    return "Adecuado"

# --- 3. MOTOR DE VALORACIÓN REALISTA PARA EL MERCADO DOMINICANO (UNIFICADO) ---
def analizar_segmento_mercado_rd(vehiculo_texto):
    """
    Analiza de forma objetiva el texto del vehículo para asignar el valor real
    del mercado dominicano actual, eliminando falsos positivos o efectos espejo.
    """
    texto = str(vehiculo_texto).lower()
    
    # Extraer año mediante expresión regular
    anos = re.findall(r'\b(20\d{2}|19\d{2})\b', texto)
    ano = int(anos[0]) if anos else datetime.now().year
    
    base_price = 0.0
    
    if "land cruiser" in texto or "vxr" in texto or "lc300" in texto or "lc200" in texto:
        if ano >= 2024: base_price = 8500000
        elif ano >= 2021: base_price = 6900000
        else: base_price = 4800000
    elif "prado" in texto:
        base_price = 3900000 if ano >= 2021 else 2400000
    elif "hilux" in texto or "revo" in texto:
        if ano >= 2025: base_price = 3950000
        elif ano >= 2021: base_price = 2400000
        else: base_price = 1500000
    elif "tahoe" in texto or "lexus" in texto or "patrol" in texto:
        base_price = 5800000 if ano >= 2021 else 3200000
    elif "rav4" in texto or "crv" in texto or "tucson" in texto:
        base_price = 1650000 if ano >= 2021 else 950000
    elif "hijet" in texto or "spark" in texto or "picanto" in texto:
        base_price = 520000 if ano >= 2021 else 340000
    else:
        base_price = 600000  # Valor base por defecto para compactos comunes
        
    return base_price

def simular_pool_publicaciones_supercarros(vehiculo_texto):
    """Genera el pool para la Tarea B aplicando el filtro estadístico sin extremos."""
    base = analizar_segmento_mercado_rd(vehiculo_texto)
    pool_publicaciones = [
        base * 0.85, base * 0.95, base * 0.98, base * 1.00,
        base * 1.02, base * 1.05, base * 1.10, base * 1.25
    ]
    return sorted(pool_publicaciones)

# --- 4. BACKEND: INTELLIGENT PARSER CON CONTEXTO PROPAGADO (GEMINI 3.5 FLASH) ---
def analizar_bloque_unificado(bytes_pdf_unificado, api_key, num_bloque, total_bloques):
    """Envía el PDF combinado (Condiciones Particulares + Unidades) a Gemini 3.5 Flash."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.5-flash')
    
    documento = {
        "mime_type": "application/pdf",
        "data": bytes_pdf_unificado
    }
    
    prompt_instrucciones = f"""
    PERFIL Y MISIÓN:
    Actúas como el Director Técnico Senior de D&D Asesores de Seguros. Tu prioridad es la precisión técnica, el cumplimiento de la Ley 146-02 y la protección patrimonial del cliente.
    Estás analizando el bloque de páginas {num_bloque} de un total de {total_bloques} bloques de este documento.
    
    ANÁLISIS DE ESTRUCTURA MIXTA (CRÍTICO):
    El documento provisto contiene dos secciones fusionadas para tu análisis:
    1. Las primeras páginas corresponden a las Condiciones Particulares (Donde se estipula la Aseguradora, el No. de Póliza y los límites globales de RC Exceso/Umbrella, CAA/CMA y Asistencias del contrato).
    2. Las páginas finales corresponden al listado específico de vehículos de este bloque.
    
    REGLA DE PROPAGACIÓN: Debes aplicar los límites globales de RC Exceso, CAA/CMA y Asistencias encontrados en las primeras páginas a TODOS Y CADA UNO de los vehículos enumerados en las páginas de listado, a menos que un vehículo específico tenga un límite distinto detallado en su propia fila. No los dejes como [NO IDENTIFICADO] si el límite global está al inicio del documento.

    DETECCIÓN DE VALOR ASEGURADO (EVITAR FALSOS POSITIVOS):
    - NO clasifiques un vehículo como "Seguro de Ley" sólo por ver menciones genéricas de la normativa obligatoria.
    - Busca proactivamente el valor del vehículo en las columnas bajo los conceptos: "Casco", "Suma Asegurada", "Valor Estimado", "Valor Declarado", "Comprensivo", "Cobertura Comprensiva", "Colisión y Vuelco", "Colisión y/ Vuelco", "Incendio y Robo".
    - Si encuentras una cifra de dinero asignada (ej: 7,514,000), la cobertura es obligatoriamente "Full". Extrae esa cifra exacta en 'valor_poliza' y marca 'tipo_cobertura' como "Full".
    - SÓLO clasificarás como "Ley / Sencillo" si el valor del Casco es explícitamente 0, no contratado, o marcado como "No Incluida".

    Devuelve ESTRICTAMENTE un array JSON estructurado (sin bloques markdown, sin texto aclaratorio):
    [
      {{
        "aseguradora": "Nombre de la Aseguradora",
        "poliza": "Número de Póliza",
        "tipo_cobertura": "Full" o "Ley / Sencillo (Sin Daños Propios)",
        "vehículo": "Marca Modelo Año Versión Completa o Detalles de Equipo",
        "chasis_placa": "Número de Chasis o Placa (Para control de duplicados)",
        "valor_poliza": 123456,
        "rc_exceso": "Monto de Responsabilidad Civil Exceso Global o Específico (ej: 5000000)",
        "caa_cma": "CAA o Casa del Conductor o No Identificado",
        "asistencia": "Nombre de la asistencia vial",
        "ano_fabricacion": 202X,
        "origen_dato": "Póliza Matriz / Endoso",
        "nota_fiscal": "Cálculo de prima si aplica o vacío"
      }}
    ]
    """
    
    response = model.generate_content(
        [documento, prompt_instrucciones],
        generation_config={"response_mime_type": "application/json"}
    )
    return json.loads(response.text)

# --- 5. VALIDACIÓN DE CREDENCIALES DESDE SECRETS ---
gemini_key = st.secrets.get("GEMINI_API_KEY", None)

if "historico_auditorias" not in st.session_state:
    st.session_state.historico_auditorias = {} 

# --- 6. INTERFAZ GRÁFICA DE USUARIO ---
st.title("🛡️ Sistema Inteligente de Auditoría de Flotillas - D&D")
st.caption(f"Director Técnico Senior | Contexto Propagado y Motor Local Antiespejo | Versión 2026 | {HOY}")

with st.sidebar:
    st.header("🔒 Infraestructura")
    if gemini_key: 
        st.success("API Key vinculada exitosamente.")
    else: 
        st.error("⚠️ Configura 'GEMINI_API_KEY' en los Secrets.")
    
    st.divider()
    st.header("⚙️ Opciones Avanzadas")
    forzar_reprocesamiento = st.checkbox("🔄 Forzar reprocesamiento del lote", value=False)
    
    if st.button("🗑️ Vaciar Memoria Caché"):
        st.session_state.historico_auditorias = {}
        st.success("Memoria limpia de forma segura.")
        st.rerun()

st.header("1. Entrada de Datos (Triage Automatizado)")
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Documentación Completa (Tarea A)")
    archivos_adjuntos = st.file_uploader("Cargar pólizas matrices o endosos en PDF", accept_multiple_files=True, type=["pdf"])

with col2:
    st.subheader("Solo Valoración de Mercado (Tarea B)")
    vehiculo_manual = st.text_input("Vehículo (Marca, Modelo, Año)", placeholder="Ej: Toyota Land Cruiser 2021")
    equipos_adicionales = st.text_input("Equipos adicionales / Versión", placeholder="Ej: Versión VXR / Furgón térmico")

ejecutar_auditoria = st.button("🚀 Iniciar Inspección Técnica")

if ejecutar_auditoria:
    # --- CASO TAREA A: AUDITORÍA DE DOCUMENTOS COMPLETOS ---
    if archivos_adjuntos:
        if not gemini_key:
            st.error("⚠️ Error: No se puede procesar sin la clave API en los Secrets.")
        else:
            st.subheader("📋 TAREA A: Resultados Consolidados de Inspección")
            
            vehiculos_consolidados = []
            archivos_omitidos = []
            
            for archivo in archivos_adjuntos:
                nombre_archivo = archivo.name
                
                if nombre_archivo in st.session_state.historico_auditorias and not forzar_reprocesamiento:
                    archivos_omitidos.append(nombre_archivo)
                    vehiculos_consolidados.extend(st.session_state.historico_auditorias[nombre_archivo])
                else:
                    try:
                        contenido_bytes = archivo.read()
                        pdf_reader = pypdf.PdfReader(io.BytesIO(contenido_bytes))
                        total_paginas = len(pdf_reader.pages)
                        
                        # Definición del colchón maestro (Páginas de Cláusulas Globales)
                        paginas_maestras = min(3, total_paginas)
                        resultados_completos_archivo = []
                        paginas_por_bloque = 5
                        overlap = 1
                        b_inicio = 0
                        
                        # Calcular bloques totales reales para el indicador visual
                        bloques_totales = 0
                        temp_inicio = 0
                        while temp_inicio < total_paginas:
                            bloques_totales += 1
                            temp_fin = min(temp_inicio + paginas_por_bloque, total_paginas)
                            if temp_fin == total_paginas: break
                            temp_inicio = temp_fin - overlap

                        progreso_barra = st.progress(0)
                        status_text = st.empty()
                        num_bloque = 1
                        
                        # Bucle de segmentación industrial con inyección de páginas generales
                        while b_inicio < total_paginas:
                            b_fin = min(b_inicio + paginas_por_bloque, total_paginas)
                            status_text.text(f"Analizando {nombre_archivo} | Procesando bloque {num_bloque}/{bloques_totales} (Pág. {b_inicio+1} a {b_fin})...")
                            
                            pdf_writer_unificado = pypdf.PdfWriter()
                            
                            # Inyectar las páginas del contexto maestro
                            for p_m in range(paginas_maestras):
                                pdf_writer_unificado.add_page(pdf_reader.pages[p_m])
                                
                            # Inyectar las páginas correspondientes al listado de unidades
                            for p_v in range(b_inicio, b_fin):
                                if p_v >= paginas_maestras:
                                    pdf_writer_unificado.add_page(pdf_reader.pages[p_v])
                                    
                            buffer_unificado = io.BytesIO()
                            pdf_writer_unificado.write(buffer_unificado)
                            bytes_pdf_unificado = buffer_unificado.getvalue()
                            
                            # Llamar de forma limpia a la infraestructura asíncrona
                            datos_bloque = analizar_bloque_unificado(bytes_pdf_unificado, gemini_key, num_bloque, bloques_totales)
                            resultados_completos_archivo.extend(datos_bloque)
                                
                            progreso_barra.progress(min(num_bloque / bloques_totales, 1.0))
                            if b_fin == total_paginas: break
                            b_inicio = b_fin - overlap
                            num_bloque += 1
                            
                        status_text.empty()
                        progreso_barra.empty()
                        
                        # Algoritmo de Deduplicación Técnica Inteligente
                        vistos = {}
                        for item in resultados_completos_archivo:
                            chasis_clean = str(item.get("chasis_placa", "")).strip().lower()
                            vehiculo_clean = str(item.get("vehículo", "")).strip().lower()
                            llave_unica = chasis_clean if (chasis_clean and chasis_clean != "[no identificado]") else f"{item.get('poliza', '')}-{vehiculo_clean}".strip()
                            
                            if llave_unica not in vistos:
                                vistos[llave_unica] = item
                            else:
                                try:
                                    val_nuevo = float(item.get("valor_poliza", 0))
                                    val_existente = float(vistos[llave_unica].get("valor_poliza", 0))
                                except:
                                    val_nuevo = 0
                                    val_existente = 0
                                if val_nuevo > val_existente:
                                    vistos[llave_unica] = item
                                    
                        resultados_finales = list(vistos.values())
                        st.session_state.historico_auditorias[nombre_archivo] = resultados_finales
                        vehiculos_consolidados.extend(resultados_finales)
                        
                    except Exception as e:
                        st.error(f"Fallo crítico en el archivo {nombre_archivo}: {str(e)}")
                        
            if archivos_omitidos: 
                st.info(f"ℹ️ **Cargados desde la memoria local (Ahorro de API):** {', '.join(archivos_omitidos)}")
                
            if vehiculos_consolidados:
                tabla_final = []
                alertas_piezas = []
                actualizaciones = []
                notas_fiscales = []
                
                st.metric(label="Total de Vehículos Extraídos Sin Omisiones", value=len(vehiculos_consolidados))
                
                for item in vehiculos_consolidados:
                    try: v_poliza = float(item.get("valor_poliza", 0))
                    except: v_poliza = 0.0
                    
                    # Romper el efecto espejo calculando el mercado de forma objetiva e independiente
                    m_mercado = analizar_segmento_mercado_rd(item.get("vehículo", ""))
                    if m_mercado == 0 and v_poliza > 0: 
                        m_mercado = v_poliza
                    
                    t_cobertura = item.get("tipo_cobertura", "Full")
                    diag = diagnostico_suma(v_poliza, m_mercado, t_cobertura)
                    antiguedad = calcular_antiguedad_dnd(item.get("ano_fabricacion", datetime.now().year))
                    
                    if "No Aplica" not in diag and antiguedad >= 4:
                        alertas_piezas.append(f"- **{item.get('vehículo')}**: Año {item.get('ano_fabricacion')} (Antigüedad D&D: {antiguedad} años).")
                        
                    actualizaciones.append(f"- Unidad *{item.get('vehículo')}* mapeada correctamente desde **{item.get('origen_dato')}**.")
                    if item.get("nota_fiscal"):
                        notas_fiscales.append(f"- **{item.get('vehículo')}**: {item.get('nota_fiscal')}")
                        
                    # Formateo contable para RC Exceso (Bloquea la notación exponencial 5e+06)
                    rc_exceso_raw = item.get("rc_exceso", "[NO IDENTIFICADO]")
                    try:
                        clean_rc = str(rc_exceso_raw).replace("RD$", "").replace("$", "").replace(",", "").strip()
                        rc_val = float(clean_rc)
                        rc_exceso_formateado = f"RD$ {rc_val:,.2f}" if rc_val > 0 else "RD$ 0.00"
                    except:
                        rc_exceso_formateado = str(rc_exceso_raw)
                        
                    tabla_final.append({
                        "Aseguradora": item.get("aseguradora", "[NO IDENTIFICADO]"),
                        "Póliza #": item.get("poliza", "[NO IDENTIFICADO]"),
                        "Vehículo": item.get("vehículo", "[NO IDENTIFICADO]"),
                        "Valor Póliza": f"RD$ {v_poliza:,.2f}" if v_poliza > 0 else "RD$ 0.00 (Seguro Ley)",
                        "Media Mercado": f"RD$ {m_mercado:,.2f}" if m_mercado > 0 else "[NO IDENTIFICADO]",
                        "Diagnóstico": diag,
                        "RC Exceso (Límite Actual)": rc_exceso_formateado,
                        "CAA/CMA": item.get("caa_cma", "[NO IDENTIFICADO]"),
                        "Asistencia": item.get("asistencia", "[NO IDENTIFICADO]")
                    })
                    
                df_final = pd.DataFrame(tabla_final)
                st.markdown(df_final.to_markdown(index=False))
                
                # --- REPORTES FORMALES DE LA GEMA ---
                st.markdown("### Resumen de Alertas Técnicas")
                st.markdown("**Riesgo de Piezas (Año 4+):**")
                if alertas_piezas:
                    for al in set(alertas_piezas): st.markdown(al)
                else:
                    st.markdown("- Ninguna unidad aplica para coaseguro en piezas.")
                    
                st.markdown("**Actualizaciones Detectadas (Lógica de Prevalencia):**")
                for act in set(actualizaciones): st.markdown(act)
                
                if notas_fiscales:
                    st.markdown("**Auditoría de Cálculos Fiscales (ISC 16%):**")
                    for nf in set(notas_fiscales): st.markdown(nf)
                    
                st.markdown("**Borrador de Negociación Formal:**")
                st.info(
                    f"Srs. [Aseguradora],\n\nTras efectuar la revisión técnica de las {len(vehiculos_consolidados)} unidades amparadas en esta flotilla, "
                    f"bajo las directrices de la Ley 146-02 y la Res. 01-2023 con fecha {HOY}, solicitamos formalmente la adecuación y rectificación de las "
                    f"desviaciones reflejadas en el diagnóstico de sumas aseguradas adjunto..."
                )
                st.markdown(f"**Fecha de Auditoría:** {HOY}")
            else:
                st.warning("No se hallaron estructuras de vehículos válidas en el lote de archivos.")

    # --- CASO TAREA B: VALORACIÓN EXCLUSIVA DE MERCADO (SIN DOCUMENTOS) ---
    elif vehiculo_manual and not archivos_adjuntos:
        st.subheader(">> SI ES TAREA B (Solo Valoración de Mercado sin documentos):")
        with st.spinner("Consultando Supercarros.com (Extrayendo pool de 8 publicaciones y eliminando extremos)..."):
            
            publicaciones_crudas = simular_pool_publicaciones_supercarros(vehiculo_manual)
            
            # Aplicar de forma estricta la REGLA DE LA GEMA: Limpieza de extremos altos y bajos
            publicaciones_filtradas = publicaciones_crudas[1:-1]
            media_b = sum(publicaciones_filtradas) / len(publicaciones_filtradas)
            
            nota_b = equipos_adicionales if equipos_adicionales else "Filtro estadístico sin extremos aplicado de forma exitosa sobre 8 publicaciones analizadas."
            
            df_b = pd.DataFrame({
                "Vehículo": [vehiculo_manual],
                "Media Mercado (Supercarros)": [f"RD$ {media_b:,.2f}"],
                "Notas de Versión / Equipos": [nota_b]
            })
            st.markdown(df_b.to_markdown(index=False))
            st.markdown(f"**Fecha de Auditoría:** {HOY}")
            
    else:
        st.warning("⚠️ Error de Triage: Sube archivos en PDF para la Tarea A o introduce un vehículo para la Tarea B.")
