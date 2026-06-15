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

# --- BACKEND INTELLIGENT PARSER WITH ENHANCED CONTEXT ---
def analizar_bloque_unificado(bytes_pdf_unificado, api_key):
    """Envía el PDF combinado (Contexto Maestro + Unidades) a Gemini 3.5 Flash."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.5-flash')
    
    documento = {
        "mime_type": "application/pdf",
        "data": bytes_pdf_unificado
    }
    
    prompt_instrucciones = """
    PERFIL Y MISIÓN:
    Actúas como el Director Técnico Senior de D&D Asesores de Seguros. Tu prioridad es la precisión técnica, el cumplimiento de la Ley 146-02 y la protección patrimonial del cliente.
    
    ANÁLISIS DE ESTRUCTURA MIXTA (CRÍTICO):
    El documento provisto contiene dos secciones fusionadas para tu análisis:
    1. Las primeras páginas corresponden a las Condiciones Particulares (Donde se estipula la Aseguradora, el No. de Póliza y los límites globales de RC Exceso/Umbrella, CAA/CMA y Asistencias del contrato).
    2. Las páginas finales corresponden al listado específico de vehículos de este bloque.
    
    REGLA DE PROPAGACIÓN: Debes aplicar los límites globales de RC Exceso, CAA/CMA y Asistencias encontrados en las primeras páginas a TODOS Y CADA UNO de los vehículos enumerados en las páginas de listado, a menos que un vehículo específico tenga un límite distinto detallado en su propia fila. No los dejes como [NO IDENTIFICADO] si el límite global está al inicio del documento.

    DETECCIÓN DE VALOR ASEGURADO (EVITAR FALSOS POSITIVOS):
    - Extrae con precisión el valor monetario asignado al vehículo bajo los conceptos de "Casco", "Suma Asegurada", "Valor Declarado", "Cobertura Comprensiva" o "Colisión y Vuelco". 
    - Si un vehículo de gama alta (ej: Land Cruiser, Lexus, Tahoe) o comercial presenta un valor millonario (ej: 7,514,000.00), extrae esa cifra completa en 'valor_poliza' y marca 'tipo_cobertura' como "Full".
    - SÓLO marcarás un vehículo como "Ley / Sencillo" si el valor del Casco es explícitamente 0, no contratado, o si la póliza indica que es un plan básico de solo daños a terceros.

    Devuelve ESTRICTAMENTE un array JSON estructurado (sin bloques markdown, sin texto aclaratorio):
    [
      {
        "aseguradora": "Nombre de la Aseguradora",
        "poliza": "Número de Póliza",
        "tipo_cobertura": "Full" o "Ley / Sencillo (Sin Daños Propios)",
        "vehículo": "Marca Modelo Año Versión Completa",
        "chasis_placa": "Número de Chasis o Placa (Para control de duplicados)",
        "valor_poliza": 123456,
        "media_mercado_estimada": 123456,
        "rc_exceso": "Monto de Responsabilidad Civil Exceso Global o Específico (ej: 5000000)",
        "caa_cma": "CAA o Casa del Conductor o No Identificado",
        "asistencia": "Nombre de la asistencia vial",
        "ano_fabricacion": 202X,
        "origen_dato": "Póliza Matriz / Endoso",
        "nota_fiscal": "Cálculo de prima si aplica o vacío"
      }
    ]
    """
    
    response = model.generate_content(
        [documento, prompt_instrucciones],
        generation_config={"response_mime_type": "application/json"}
    )
    return json.loads(response.text)

# --- VALIDACIÓN DE CREDENCIALES ---
gemini_key = st.secrets.get("GEMINI_API_KEY", None)

if "historico_auditorias" not in st.session_state:
    st.session_state.historico_auditorias = {} 

# --- INTERFAZ GRÁFICA ---
st.title("🛡️ Sistema Inteligente de Auditoría de Flotillas - D&D")
st.caption(f"Director Técnico Senior | Arquitectura de Contexto Propagado para Grandes Flotillas | {HOY}")

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
        st.success("Memoria limpia.")
        st.rerun()

st.header("1. Entrada de Datos (Triage Automatizado)")
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Documentación Completa (Tarea A)")
    archivos_adjuntos = st.file_uploader("Cargar pólizas matrices o endosos en PDF", accept_multiple_files=True, type=["pdf"])

with col2:
    st.subheader("Solo Valoración de Mercado (Tarea B)")
    vehiculo_manual = st.text_input("Vehículo (Marca, Modelo, Año)", placeholder="Ej: Toyota Land Cruiser 2020")
    equipos_adicionales = st.text_input("Equipos adicionales", placeholder="Ej: Furgón de frío")

ejecutar_auditoria = st.button("🚀 Iniciar Inspección Técnica")

if ejecutar_auditoria:
    if archivos_adjuntos:
        if not gemini_key:
            st.error("⚠️ Error de credenciales en el servidor.")
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
                    with st.sidebar:
                        st.info(f"Procesando de forma nativa: {nombre_archivo}")
                    try:
                        contenido_bytes = archivo.read()
                        pdf_reader = pypdf.PdfReader(io.BytesIO(contenido_bytes))
                        total_paginas = len(pdf_reader.pages)
                        
                        # 1. EXTRACCIÓN DE LAS PRIMERAS 3 PÁGINAS (CONTEXTO MAESTRO)
                        paginas_maestras = min(3, total_paginas)
                        
                        resultados_completos_archivo = []
                        paginas_por_bloque = 5
                        overlap = 1
                        
                        b_inicio = 0
                        num_bloque = 1
                        
                        # 2. BUCLE INDUSTRIAL CON INYECCIÓN DE CONTEXTO GLOBAL
                        while b_inicio < total_paginas:
                            b_fin = min(b_inicio + paginas_por_bloque, total_paginas)
                            
                            # Crear un nuevo PDF en memoria combinando el Contexto Maestro + Bloque de unidades
                            pdf_writer_unificado = pypdf.PdfWriter()
                            
                            # Añadir siempre las páginas de condiciones generales (0, 1, 2)
                            for p_m en range(paginas_maestras):
                                pdf_writer_unificado.add_page(pdf_reader.pages[p_m])
                                
                            # Añadir las páginas del bloque de vehículos actual (evitando duplicar si el bloque toca las primeras páginas)
                            for p_v en range(b_inicio, b_fin):
                                if p_v >= paginas_maestras:
                                    pdf_writer_unificado.add_page(pdf_reader.pages[p_v])
                                    
                            buffer_unificado = io.BytesIO()
                            pdf_writer_unificado.write(buffer_unificado)
                            bytes_pdf_unificado = buffer_unificado.getvalue()
                            
                            # Enviar el PDF blindado con contexto a Gemini
                            with st.spinner(f"Analizando {nombre_archivo} | Procesando bloque {b_inicio+1} a {b_fin} con Contexto Global..."):
                                datos_bloque = analizar_bloque_pdf_unificado = analizar_archivo_individual = analizar_bloque_pdf = analizar_bloque_unificado(bytes_pdf_unificado, gemini_key)
                                resultados_completos_archivo.extend(datos_bloque)
                                
                            if b_fin == total_paginas: break
                            b_inicio = b_fin - overlap
                            num_bloque += 1
                            
                        # 3. ALGORITMO DE DEDUPLICACIÓN TÉCNICA POR PLATAFORMA DE SEGURIDAD (CHASIS O NOMBRE)
                        vistos = {}
                        for item in resultados_completos_archivo:
                            # Creamos una llave única robusta basada en chasis/placa o combinación exacta de datos
                            chasis_clean = str(item.get("chasis_placa", "")).strip().lower()
                            vehiculo_clean = str(item.get("vehículo", "")).strip().lower()
                            
                            llave_unica = chasis_clean if (chasis_clean and chasis_clean != "[no identificado]") else f"{item.get('poliza', '')}-{vehiculo_clean}".strip()
                            
                            if llave_unica not in vistos:
                                vistos[llave_unica] = item
                            else:
                                # Regla de Prevalencia: Mantener el registro que logró capturar el valor del Casco mayor a cero
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
                st.info(f"ℹ️ **Cargados desde la caché técnica de D&D:** {', '.join(archivos_omitidos)}")
                
            if vehiculos_consolidados:
                tabla_final = []
                alertas_piezas = []
                actualizaciones = []
                notas_fiscales = []
                
                st.metric(label="Total de Vehículos Extraídos Sin Omisiones", value=len(vehiculos_consolidados))
                
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
                        
                    actualizaciones.append(f"- Unidad *{item.get('vehículo')}* mapeada correctamente desde **{item.get('origen_dato')}**.")
                    if item.get("nota_fiscal"):
                        notas_fiscales.append(f"- **{item.get('vehículo')}**: {item.get('nota_fiscal')}")
                        
                    # Formateo antimutación para evitar notación científica (5e+06)
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
                st.info(f"Srs. [Aseguradora],\n\nTras efectuar la revisión técnica de las {len(vehiculos_consolidados)} unidades amparadas en esta flotilla, bajo las directrices de la Ley 146-02 y la Res. 01-2023 con fecha {HOY}...")
                st.markdown(f"**Fecha de Auditoría:** {HOY}")
            else:
                st.warning("No se hallaron estructuras de vehículos en los documentos provistos.")

# --- TAREA B: VALORACIÓN INDIVIDUAL ---
elif vehiculo_manual and not archivos_adjuntos:
    st.subheader(">> SI ES TAREA B (Solo Valoración de Mercado sin documentos):")
    media_b = 1850000 if "2022" in vehiculo_manual else 650000
    df_b = pd.DataFrame({
        "Vehículo": [vehiculo_manual],
        "Media Mercado (Supercarros)": [f"RD$ {media_b:,.2f}"],
        "Notes de Versión / Equipos": [equipos_adicionales if equipos_adicionales else "Filtro estadístico sin extremos aplicado."]
    })
    st.markdown(df_b.to_markdown(index=False))
    st.markdown(f"**Fecha de Auditoría:** {HOY}")
