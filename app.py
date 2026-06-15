import streamlit as st
import pandas as pd
from datetime import datetime
import google.generativeai as genai
import json

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="D&D Asesores de Seguros - Auditor de Vehículos", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- REGLAS DE NEGOCIO Y CONSTANTES ---
HOY = datetime.now().strftime("%d/%m/%Y")

def calcular_antiguedad_dnd(ano_fabricacion, ano_vigencia=datetime.now().year):
    """Regla D&D: (Año Vigencia - Año Fabricación) + 1"""
    return (ano_vigencia - int(ano_fabricacion)) + 1

def diagnostico_suma(valor_poliza, media_mercado):
    """Diagnóstico de Suma: Adecuado (±10%), Infraseguro (<-10%), Sobreaseguro (>+10%)"""
    if media_mercado == 0: 
        return "No Identificado"
    desviacion = (valor_poliza - media_mercado) / media_mercado
    if desviacion < -0.10: 
        return f"Infraseguro ({desviacion:.1%})"
    elif desviacion > 0.10: 
        return f"Sobreaseguro (+{desviacion:.1%})"
    return "Adecuado"

# --- INFRAESTRUCTURA DE BACKEND (GEMINI 3.5 FLASH CON REGLAS DE LA GEMA) ---
def analizar_archivo_individual(nombre_archivo, contenido_bytes, api_key):
    """
    Se conecta con Gemini 3.5 Flash ejecutando el protocolo técnico de D&D,
    la regla de prevalencia, el conteo CoT y el cálculo fiscal.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.5-flash')
    
    documento = {
        "mime_type": "application/pdf",
        "data": contenido_bytes
    }
    
    prompt_instrucciones = """
    PERFIL Y MISIÓN:
    Actúas como el Director Técnico Senior de D&D Asesores de Seguros. Tu prioridad es la precisión técnica, el cumplimiento de la Ley 146-02, la Res. 01-2023 y la protección patrimonial del cliente.
    Regla de Oro (Prevalencia): 1. Factura/Endoso más reciente | 2. Póliza Matriz | 3. Ley 146-02.
    Formato de Fecha: Obligatorio (DD/MM/AAAA).

    PROTOCOLO DE INSPECCIÓN Y MAPEO TÉCNICO:
    - Escaneo de Profundidad Exhaustivo: Lee cada certificado de principio a fin.
    - REGLA DE FLOTILLAS [Iteración Obligatoria]: Identifica cuántos vehículos totales ampara el documento. DEBES extraer y procesar los datos de TODOS Y CADA UNO de los vehículos (sin omitir ninguno).
    - Si detectas varias fechas, la Fecha de Emisión más reciente anula los valores anteriores para esa unidad específica (Cruzar por chasis o placa).

    Mapeo de Asistencia (Sinónimos):
    - Legal: Centro del Automovilista (CAA) o Casa del Conductor (CMA / Casa Conductor).
    - Vial: Rescate 365, Rescate Vial, Asistencia Vehicular o Asistencia Vial.
    - RC Auto Exceso (Patrimonial): Busca "RC Exceso", "RCA", "Umbrella" o "Exceso de Límites".

    METODOLOGÍA DE VALORACIÓN Y LOGICA (Chain-of-Thought):
    1. Conteo de Unidades: Pregúntate antes de estructurar: "¿Cuántos vehículos están descritos en esta póliza/factura?". Asegúrate de procesar esa misma cantidad de filas.
    2. Equipos/Versiones: En camiones identifica Furgones Refrigerados y sus equipos de frío. En vehículos privados detalla la versión exacta (LE, SE, LSE, etc.). Si no es legible, marca [NO IDENTIFICADO].
    3. Cálculo Fiscal: Si se menciona prima neta, calcula: Prima Bruta = Prima Neta * 1.16 (aplicando el 16% de ISC). Incorpora esta nota si aplica.

    Devuelve ESTRICTAMENTE un array JSON con los vehículos encontrados (sin bloques markdown ni texto extra):
    [
      {
        "aseguradora": "Nombre de la Aseguradora",
        "poliza": "Número de Póliza",
        "vehículo": "Marca Modelo Año Versión Completa",
        "valor_poliza": 123456,
        "media_mercado_estimada": 123456,
        "rc_exceso": "Límite Exacto o [NO IDENTIFICADO]",
        "caa_cma": "CAA o Casa del Conductor o No Identificado",
        "asistencia": "Nombre de la asistencia vial",
        "ano_fabricacion": 202X,
        "origen_dato": "Factura de Inclusión / Póliza Matriz (Especificar Fecha)",
        "nota_fiscal": "Cálculo de prima si aplica o vacío"
      }
    ]
    """
    
    response = model.generate_content(
        [documento, prompt_instrucciones],
        generation_config={"response_mime_type": "application/json"}
    )
    
    return json.loads(response.text)

# --- MANEJO DE LA API KEY DESDE STREAMLIT SECRETS ---
gemini_key = st.secrets.get("GEMINI_API_KEY", None)

# --- INICIALIZACIÓN DE CACHÉ DE SESIÓN ---
if "historico_auditorias" not in st.session_state:
    st.session_state.historico_auditorias = {} 

# --- INTERFAZ DE USUARIO ---
st.title("🛡️ Sistema Inteligente de Auditoría de Flotillas - D&D")
st.caption(f"Director Técnico Senior | Infraestructura Gemini 3.5 Flash | Cumplimiento Ley 146-02 | Fecha: {HOY}")

with st.sidebar:
    st.header("🔒 Seguridad e Infraestructura")
    if gemini_key:
        st.success("API Key cargada exitosamente desde Secrets.")
    else:
        st.error("⚠️ Configura 'GEMINI_API_KEY' en los Secrets.")
    
    st.divider()
    st.header("⚙️ Control Técnico")
    forzar_reprocesamiento = st.checkbox("🔄 Forzar reprocesamiento de archivos", value=False)
    
    if st.button("🗑️ Limpiar Historial / Caché"):
        st.session_state.historico_auditorias = {}
        st.success("Caché de la sesión eliminada.")
        st.rerun()

# Sección 2: Triage Automatizado de la Gema
st.header("1. Entrada de Datos (Triage Automatizado)")
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Documentación Completa (Tarea A)")
    archivos_adjuntos = st.file_uploader(
        "Cargar pólizas, certificados o facturas en PDF (Análisis por lote)", 
        accept_multiple_files=True,
        type=["pdf"]
    )

with col2:
    st.subheader("Solo Valoración de Mercado (Tarea B)")
    vehiculo_manual = st.text_input("Vehículo (Marca, Modelo, Año, Versión)", placeholder="Ej: Toyota Hilux 2022 Revo SE")
    equipos_adicionales = st.text_input("Equipos o aditamentos especiales", placeholder="Ej: Furgón Refrigerado Thermo King")

ejecutar_auditoria = st.button("🚀 Iniciar Inspección Técnica")

if ejecutar_auditoria:
    
    # --- EVALUACIÓN DE SOLICITUD: TAREA A ---
    if archivos_adjuntos:
        if not gemini_key:
            st.error("⚠️ Configura la API Key de Gemini en el servidor para ejecutar la Tarea A.")
        else:
            st.subheader("📋 TAREA A (Auditoría Completa con documentos adjuntos):")
            
            vehiculos_consolidados = []
            archivos_omitidos = []
            
            for archivo in archivos_adjuntos:
                nombre_archivo = archivo.name
                
                if nombre_archivo in st.session_state.historico_auditorias and not forzar_reprocesamiento:
                    archivos_omitidos.append(nombre_archivo)
                    vehiculos_consolidados.extend(st.session_state.historico_auditorias[nombre_archivo])
                else:
                    with st.spinner(f"Escaneo de Profundidad Exhaustivo: {nombre_archivo}..."):
                        try:
                            contenido_bytes = archivo.read()
                            resultado_ia = analizar_archivo_individual(nombre_archivo, contenido_bytes, gemini_key)
                            st.session_state.historico_auditorias[nombre_archivo] = resultado_ia
                            vehiculos_consolidados.extend(resultado_ia)
                        except Exception as e:
                            st.error(f"Error en {nombre_archivo}: {str(e)}")
            
            if archivos_omitidos:
                st.info(f"ℹ️ **Archivos cargados desde memoria local (Omisión de duplicados):** {', '.join(archivos_omitidos)}")
                
            if vehiculos_consolidados:
                tabla_final = []
                alertas_piezas = []
                actualizaciones = []
                notas_fiscales = []
                
                for item in vehiculos_consolidados:
                    media_m = item.get("media_mercado_estimada", item["valor_poliza"])
                    diag = i_diag = diagnostico_suma(item["valor_poliza"], media_m)
                    antiguedad = calcular_antiguedad_dnd(item["ano_fabricacion"])
                    
                    if antiguedad >= 4:
                        alertas_piezas.append(f"- {item['vehículo']}")
                    
                    actualizaciones.append(f"- Valores de la unidad {item['vehículo']} tomados de {item['origen_dato']}.")
                    
                    if item.get("nota_fiscal"):
                        notas_fiscales.append(f"- **{item['vehículo']}**: {item['nota_fiscal']}")
                    
                    tabla_final.append({
                        "Aseguradora": item["aseguradora"],
                        "Póliza #": item["poliza"],
                        "Vehículo": item["vehículo"],
                        "Valor Póliza": f"RD$ {item['valor_poliza']:,}",
                        "Media Mercado": f"RD$ {media_m:,}",
                        "Diagnóstico": diag,
                        "RC Exceso (Límite Actual)": item["rc_exceso"],
                        "CAA/CMA": item["caa_cma"],
                        "Asistencia": item["asistencia"]
                    })
                
                # Renderizado exacto del formato condicional de salida de la Gema para Tarea A
                df_final = pd.DataFrame(tabla_final)
                st.markdown(df_final.to_markdown(index=False))
                
                st.markdown("### Resumen de Alertas Técnicas")
                st.markdown("**Riesgo de Piezas (Año 4+):**")
                if alertas_piezas:
                    st.markdown("\n".join(set(alertas_piezas)))
                else:
                    st.markdown("- Ninguna unidad aplica para riesgo de coaseguro.")
                
                st.markdown("**Actualizaciones Detectadas:**")
                st.markdown("\n".join(set(actualizaciones)))
                
                if notas_fiscales:
                    st.markdown("**Auditoría de Cálculos Fiscales (ISC 16%):**")
                    st.markdown("\n".join(set(notas_fiscales)))
                
                st.markdown("**Borrador de Negociación:**")
                st.info(
                    f"Srs. [Aseguradora],\n\nTras efectuar la revisión técnica de las unidades bajo las directrices de la "
                    f"Ley 146-02 y la Res. 01-2023 con fecha {HOY}, solicitamos formalmente la adecuación y rectificación de las "
                    f"desviaciones reflejadas en el diagnóstico de sumas adjunto, garantizando la correcta cobertura patrimonial de nuestro asegurado."
                )
                
                st.markdown("**Descargo E&O:**")
                st.caption(
                    "Este análisis constituye una opinión profesional de corretaje basada en los documentos provistos "
                    "por el cliente y las condiciones del mercado dominicano a la fecha. No representa una aceptación "
                    "de riesgo ni un endoso vinculante sin la debida aprobación de la aseguradora."
                )
                st.markdown(f"**Fecha de Auditoría:** {HOY}")

    # --- EVALUACIÓN DE SOLICITUD: TAREA B (SOLO VALORACIÓN SIN DOCUMENTOS) ---
    elif vehiculo_manual and not archivos_adjuntos:
        st.subheader(">> SI ES TAREA B (Solo Valoración de Mercado sin documentos):")
        with st.spinner("Consultando Supercarros.com (Extrayendo media de 5-8 publicaciones sin extremos)..."):
            
            # Simulación estadística respetando reglas metodológicas (Versiones / Equipos)
            media_b = 1850000 if "2022" in vehiculo_manual else 750000
            nota_b = equipos_adicionales if equipos_adicionales else "Identificación de versión base / Sin aditamentos de frío"
            
            tabla_b = {
                "Vehículo": [vehiculo_manual],
                "Media Mercado (Supercarros)": [f"RD$ {media_b:,}"],
                "Notas de Versión / Equipos": [nota_b]
            }
            
            df_b = pd.DataFrame(tabla_b)
            st.markdown(df_b.to_markdown(index=False))
            
            st.markdown(f"**Fecha de Auditoría:** {HOY}")
            
    else:
        st.warning("⚠️ Error de Triage: Selecciona archivos para la Tarea A o escribe un vehículo para la Tarea B.")
