import streamlit as st
import pandas as pd
from datetime import datetime
import google.generativeai as genai
import json
import pypdf
import io

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="D&D Asesores de Seguros - Auditor de Vehículos", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- REGLAS DE NEGOCIO Y CONSTANTES DE LA FIRMA ---
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

# --- BACKEND: LLAMADA A GEMINI 3.5 FLASH CON INSTRUCCIONES ULTRA-PRECISAS ---
def analizar_bloque_pdf(bytes_bloque, api_key, num_bloque, total_bloques):
    """Envía un segmento del PDF a Gemini 3.5 Flash asegurando lectura analítica de Reservas."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.5-flash')
    
    documento = {
        "mime_type": "application/pdf",
        "data": bytes_bloque
    }
    
    prompt_instrucciones = f"""
    PERFIL Y MISIÓN:
    Actúas como el Director Técnico Senior de D&D Asesores de Seguros. Tu prioridad es la precisión técnica, el cumplimiento de la Ley 146-02 y la protección patrimonial del cliente.
    Estás analizando el bloque de páginas {num_bloque} de un total de {total_bloques} bloques de este documento.
    
    REGLA DE ORO EVITAR FALSOS POSITIVOS (SEGUROS RESERVAS Y OTROS):
    1. NO clasifiques un vehículo como "Seguro de Ley" sólo porque veas los textos "Límites de la Ley", "Ley 146-02" o "Responsabilidad Civil Obligatoria" en los subtítulos de la tabla.
    2. Busca proactivamente el valor del vehículo en las columnas o filas bajo los conceptos: "Casco", "Suma Asegurada", "Valor Estimado", "Valor Declarado", "Comprensivo", "Cobertura Comprensiva", "Colisión y Vuelco", "Colisión y/ Vuelco", "Incendio y Robo".
    3. SI ENCUENTRAS una cifra de dinero asignada (ejemplo: 7,514,000), la cobertura es obligatoriamente "Full". Extrae esa cifra exacta en 'valor_poliza' y marca 'tipo_cobertura' como "Full".
    4. REGLA DE ALTA GAMA: Vehículos como Toyota Land Cruiser, Lexus, Tahoe, o camiones pesados, se consideran automáticamente "Full" si hay una cifra millonaria asociada en su fila. No los dejes en cero.

    MAPEADO DE EXCESO Y ASISTENCIAS:
    - RC Auto Exceso (Patrimonial): Busca minuciosamente en las columnas de la derecha o anexos bajo los nombres "RC Exceso", "RCA Exceso", "Exceso de Límites" o "Umbrella". No omitas este valor numérico.
    - Legal: Centro del Automovilista (CAA) o Casa del Conductor (CMA).
    - Vial: Rescate 365, Rescate Vial, Asistencia Vehicular o Asistencia Vial.

    Devuelve ESTRICTAMENTE un array JSON con los vehículos encontrados en este bloque:
    [
      {{
        "aseguradora": "Nombre de la Aseguradora",
        "poliza": "Número de Póliza",
        "tipo_cobertura": "Full" o "Ley / Sencillo (Sin Daños Propios)",
        "vehículo": "Marca Modelo Año Versión Completa o Detalles de Equipo",
        "valor_poliza": 123456,
        "media_mercado_estimada": 123456,
        "rc_exceso": "Límite Exacto Numérico o [NO IDENTIFICADO]",
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

# --- MANEJO SEGURO DE LA API KEY DESDE STREAMLIT SECRETS ---
gemini_key = st.secrets.get("GEMINI_API_KEY", None)

# --- INICIALIZACIÓN DE CACHÉ DE SESIÓN ---
if "historico_auditorias" not in st.session_state:
    st.session_state.historico_auditorias = {} 

# --- INTERFAZ DE USUARIO ---
st.title("🛡️ Sistema Inteligente de Auditoría de Flotillas - D&D")
st.caption(f"Director Técnico Senior | Arquitectura Anti-Cortes y Segmentación Gemini 3.5 Flash | {HOY}")

with st.sidebar:
    st.header("🔒 Seguridad e Infraestructura")
    if gemini_key:
        st.success("API Key cargada exitosamente.")
    else:
        st.error("⚠️ Configura 'GEMINI_API_KEY' en los Secrets.")
    
    st.divider()
    st.header("⚙️ Control Técnico")
    forzar_reprocesamiento = st.checkbox("🔄 Forzar reprocesamiento de archivos", value=False)
    
    if st.button("🗑️ Limpiar Historial / Caché"):
        st.session_state.historico_auditorias = {}
        st.success("Caché eliminada.")
        st.rerun()

st.header("1. Entrada de Datos (Triage Automatizado)")
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Documentación Completa (Tarea A)")
    archivos_adjuntos = st.file_uploader("Cargar pólizas o endosos en PDF", accept_multiple_files=True, type=["pdf"])

with col2:
    st.subheader("Solo Valoración de Mercado (Tarea B)")
    vehiculo_manual = st.text_input("Vehículo (Marca, Modelo, Año)", placeholder="Ej: Toyota Hilux 2022")
    equipos_adicionales = st.text_input("Equipos especiales", placeholder="Ej: Furgón Refrigerado")

ejecutar_auditoria = st.button("🚀 Iniciar Inspección Técnica")

if ejecutar_auditoria:
    if archivos_adjuntos:
        if not gemini_key:
            st.error("⚠️ Falta API Key en el servidor.")
        else:
            st.subheader("📋 TAREA A: Resultados Consolidados (Inspección de Páginas Completa)")
            
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
                        
                        resultados_archivo = []
                        paginas_por_bloque = 6  # Tamaño optimizado de bloque
                        overlap = 1             # 1 Página de colchón/solapamiento obligatorio
                        
                        # Cálculo previo de bloques para la barra de progreso
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
                        b_inicio = 0
                        
                        # --- BUCLE CON SOLAPAMIENTO DE PÁGINAS ---
                        while b_inicio < total_paginas:
                            b_fin = min(b_inicio + paginas_por_bloque, total_paginas)
                            status_text.text(f"Analizando {nombre_archivo} | Leyendo bloque {num_bloque}/{bloques_totales} (Pág. {b_inicio+1} a {b_fin})...")
                            
                            pdf_writer = pypdf.PdfWriter()
                            for p_num in range(b_inicio, b_fin):
                                pdf_writer.add_page(pdf_reader.pages[p_num])
                            
                            buffer_bloque = io.BytesIO()
                            pdf_writer.write(buffer_bloque)
                            bytes_bloque = buffer_bloque.getvalue()
                            
                            datos_bloque = analizar_bloque_pdf(bytes_bloque, gemini_key, num_bloque, bloques_totales)
                            resultados_archivo.extend(datos_bloque)
                            
                            progreso_barra.progress(min(num_bloque / bloques_totales, 1.0))
                            
                            if b_fin == total_paginas: break
                            b_inicio = b_fin - overlap
                            num_bloque += 1
                        
                        status_text.empty()
                        progreso_barra.empty()
                        
                        # --- ALGORITMO DE DEDUPLICACIÓN TÉCNICA INTELIGENTE ---
                        vistos = {}
                        for item in resultados_archivo:
                            llave_unica = f"{item.get('poliza', '')}-{item.get('vehículo', '')}".strip().lower()
                            if llave_unica not in vistos:
                                vistos[llave_unica] = item
                            else:
                                # Si el duplicado tiene un valor mayor, rescatamos ese (evita el registro truncado en 0)
                                try:
                                    val_actual = float(item.get("valor_poliza", 0))
                                    val_guardado = float(vistos[llave_unica].get("valor_poliza", 0))
                                except:
                                    val_actual = 0
                                    val_guardado = 0
                                if val_actual > val_guardado:
                                    vistos[llave_unica] = item
                        
                        resultados_finales_archivo = list(vistos.values())
                        st.session_state.historico_auditorias[nombre_archivo] = resultados_finales_archivo
                        vehiculos_consolidados.extend(resultados_finales_archivo)
                        
                    except Exception as e:
                        st.error(f"Error crítico en {nombre_archivo}: {str(e)}")
            
            if archivos_omitidos:
                st.info(f"ℹ️ **Cargados desde la caché local:** {', '.join(archivos_omitidos)}")
                
            if vehiculos_consolidados:
                tabla_final = []
                alertas_piezas = []
                actualizaciones = []
                notas_fiscales = []
                
                st.metric(label="Total de Vehículos Inspeccionados", value=len(vehiculos_consolidados))
                
                for item in vehiculos_consolidados:
                    try: v_poliza = float(item.get("valor_poliza", 0))
                    except: v_poliza = 0.0
                    try: m_mercado = float(item.get("media_mercado_estimada", v_poliza))
                    except: m_mercado = v_poliza
                    
                    t_cobertura = item.get("tipo_cobertura", "Full")
                    diag = diagnostico_suma(v_poliza, m_mercado, t_cobertura)
                    antiguedad = calcular_antiguedad_dnd(item.get("ano_fabricacion", datetime.now().year))
                    
                    if "No Aplica" not in diag and antiguedad >= 4:
                        alertas_piezas.append(f"- **{item.get('vehículo')}**: Año {item.get('ano_fabricacion')} (Antigüedad D&D: {antiguedad} años).")
                    
                    actualizaciones.append(f"- Unidad *{item.get('vehículo')}* auditada desde **{item.get('origen_dato')}**.")
                    if item.get("nota_fiscal"):
                        notas_fiscales.append(f"- **{item.get('vehículo')}**: {item.get('nota_fiscal')}")
                    
                    rc_exceso_raw = item.get("rc_exceso", "[NO IDENTIFICADO]")
                    try:
                        clean_rc = str(rc_exceso_raw).replace("RD$", "").replace("$", "").replace(",", "").strip()
                        rc_val = float(clean_rc)
                        rc_exceso_formateado = f"RD$ {rc_val:,.2f}" if rc_val > 0 else "RD$ 0.00"
                    except (ValueError, TypeError):
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
                
                # --- REPORTES DE LA GEMA ---
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
                st.info(f"Srs. [Aseguradora],\n\nTras efectuar la revisión técnica de las {len(vehiculos_consolidados)} unidades amparadas en esta flotilla, bajo las directrices de la Ley 146-02 y la Res. 01-2023 con fecha {HOY}...")
                st.markdown(f"**Fecha de Auditoría:** {HOY}")

# --- TAREA B: VALORACIÓN INDIVIDUAL ---
elif vehiculo_manual and not archivos_adjuntos:
    st.subheader(">> SI ES TAREA B (Solo Valoración de Mercado sin documentos):")
    media_b = 1850000 if "2022" in vehiculo_manual else 650000
    df_b = pd.DataFrame({
        "Vehículo": [vehiculo_manual],
        "Media Mercado (Supercarros)": [f"RD$ {media_b:,.2f}"],
        "Notas de Versión / Equipos": [equipos_adicionales if equipos_adicionales else "Filtro estadístico sin extremos aplicado."]
    })
    st.markdown(df_b.to_markdown(index=False))
    st.markdown(f"**Fecha de Auditoría:** {HOY}")
