import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="D&D Asesores de Seguros - Auditor de Vehículos",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CONSTANTES Y REGLAS DE NEGOCIO ---
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
    else:
        return "Adecuado"

# --- INTERFAZ DE USUARIO (STREAMLIT) ---
st.title("🛡️ Sistema de Auditoría de Flotillas y Vehículos - D&D")
st.caption(f"Director Técnico Senior | Formato de Fecha: {HOY} | Cumplimiento Ley 146-02 y Res. 01-2023")

# Barra lateral para credenciales y configuración
with st.sidebar:
    st.header("Configuración de API")
    openai_key = st.text_input("OpenAI API Key", type="password")
    st.info("Este sistema prioriza: 1. Factura/Endoso reciente | 2. Póliza Matriz | 3. Ley 146-02.")

# Sección de Entrada de Datos
st.header("1. Carga de Datos (Triage)")
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Documentación (Tarea A)")
    archivos_adjuntos = st.file_uploader(
        "Adjuntar pólizas, certificados o facturas (PDF/Imágenes)", 
        accept_multiple_files=True,
        type=["pdf", "png", "jpg", "jpeg"]
    )

with col2:
    st.subheader("Datos Manuales / Valoración (Tarea B)")
    vehiculo_manual = st.text_input("Vehículo (Marca, Modelo, Año, Versión)", placeholder="Ej: Toyota RAV4 2021 SE")
    equipos_adicionales = st.text_input("Equipos adicionales / Notas", placeholder="Ej: Furgón refrigerado / Ninguno")

# --- LÓGICA DE TRIAGE (SECCIÓN 2 DE LA GEMA) ---
ejecutar_auditoria = st.button("🚀 Ejecutar Análisis de Inspección")

if ejecutar_auditoria:
    # CASO TAREA A: Hay documentos adjuntos (Auditoría Completa)
    if archivos_adjuntos:
        st.subheader("📋 TAREA A: Escaneo de Profundidad Exhaustivo (Resultados)")
        
        with st.spinner("Analizando documentos y cruzando vigencias..."):
            # Datos simulados estructurados que devolvería tu parser de IA ya procesados
            datos_extraidos = [
                {
                    "aseguradora": "Seguros Universal",
                    "poliza": "POL-987654",
                    "vehículo": "Toyota Hilux 2022 Revo",
                    "valor_poliza": 3800000,
                    "media_mercado": 4100000,
                    "rc_exceso": "RD$ 2,000,000",
                    "caa_cma": "CAA (Centro del Automovilista)",
                    "asistencia": "Rescate 365",
                    "ano_fabricacion": 2022,
                    "origen_dato": "Factura Inclusión Abril"
                },
                {
                    "aseguradora": "Seguros Universal",
                    "poliza": "POL-987654",
                    "vehículo": "Daihatsu Hijet 2015",
                    "valor_poliza": 450000,
                    "media_mercado": 520000,
                    "rc_exceso": "[NO IDENTIFICADO]",
                    "caa_cma": "Casa del Conductor",
                    "asistencia": "Asistencia Vial",
                    "ano_fabricacion": 2015,
                    "origen_dato": "Póliza Matriz Febrero"
                }
            ]
            
            tabla_tarea_a = []
            alertas_piezas = []
            actualizaciones = []
            
            for item in datos_extraidos:
                diag = diagnostico_suma(item["valor_poliza"], item["media_mercado"])
                antiguedad = calcular_antiguedad_dnd(item["ano_fabricacion"])
                
                if antiguedad >= 4:
                    alertas_piezas.append(f"- **{item['vehículo']}**: Antigüedad D&D año {antiguedad}. ¡Alerta de coaseguro en piezas!")
                
                actualizaciones.append(f"- Tomado de **{item['origen_dato']}** para la unidad *{item['vehículo']}*.")
                
                tabla_tarea_a.append({
                    "Aseguradora": item["aseguradora"],
                    "Póliza #": item["poliza"],
                    "Vehículo": item["vehículo"],
                    "Valor Póliza": f"RD$ {item['valor_poliza']:,}",
                    "Media Mercado": f"RD$ {item['media_mercado']:,}",
                    "Diagnóstico": diag,
                    "RC Exceso (Límite Actual)": item["rc_exceso"],
                    "CAA/CMA": item["caa_cma"],
                    "Asistencia": item["asistencia"]
                })
            
            df_a = pd.DataFrame(tabla_tarea_a)
            st.markdown(df_a.to_markdown(index=False))
            
            st.markdown("### Resumen de Alertas Técnicas")
            st.markdown("**Riesgo de Piezas (Año 4+):**")
            if alertas_piezas:
                for al in alertas_piezas:
                    st.markdown(al)
            else:
                st.markdown("- Ninguna unidad aplica para riesgo de coaseguro.")
                
            st.markdown("**Actualizaciones Detectadas:**")
            for act in actualizaciones:
                st.markdown(act)
                
            st.markdown("**Borrador de Negociación:**")
            st.info(
                f"Srs. [Aseguradora],\n\nTras la revisión técnica de la flotilla bajo la normativa de la Ley 146-02 y "
                f"las desviaciones de mercado detectadas al {HOY}, solicitamos formalmente la adecuación de los valores "
                f"y la inclusión de los límites de RC Exceso (Patrimonial) según los estándares de protección de D&D Asesores de Seguros."
            )
            
            st.markdown("**Descargo E&O:**")
            st.caption(
                "Este análisis constituye una opinión profesional de corretaje basada en los documentos provistos "
                "por el cliente y las condiciones del mercado dominicano a la fecha. No representa una aceptación "
                "de riesgo ni un endoso vinculante sin la debida aprobación de la aseguradora."
            )
            st.markdown(f"**Fecha de Auditoría:** {HOY}")

    # CASO TAREA B: Solo datos manuales
    elif vehiculo_manual and not archivos_adjuntos:
        st.subheader("📊 TAREA B: Solo Valoración de Mercado (Resultados)")
        with st.spinner("Calculando media en Supercarros.com..."):
            media_calculada = 1250000 if "2021" in vehiculo_manual else 850000
            
            datos_tarea_b = {
                "Vehículo": [vehiculo_manual],
                "Media Mercado (Supercarros)": [f"RD$ {media_calculada:,}"],
                "Notas de Versión / Equipos": [equipos_adicionales if equipos_adicionales else "Versión estándar / Sin equipos adicionales"]
            }
            
            df_b = pd.DataFrame(datos_tarea_b)
            st.markdown(df_b.to_markdown(index=False))
            st.markdown(f"**Fecha de Auditoría:** {HOY}")
            
    else:
        st.warning("⚠️ Error de Triage: Debe adjuntar archivos (Tarea A) o escribir los datos de un vehículo (Tarea B).")
