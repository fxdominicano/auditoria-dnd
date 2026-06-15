import streamlit as st
import pandas as pd
from datetime import datetime
from utils.parser import analizar_archivo_individual

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="D&D Asesores de Seguros - Auditor de Vehículos", layout="wide")
HOY = datetime.now().strftime("%d/%m/%Y")

# --- INICIALIZACIÓN DE CACHÉ DE SESIÓN (PERSISTENCIA DE LOTES) ---
if "historico_auditorias" not in st.session_state:
    st.session_state.historico_auditorias = {}  # Estructura: {nombre_archivo: [lista_de_vehiculos]}

def calcular_antiguedad_dnd(ano_fabricacion, ano_vigencia=datetime.now().year):
    return (ano_vigencia - int(ano_fabricacion)) + 1

def diagnostico_suma(valor_poliza, media_mercado):
    if media_mercado == 0: return "No Identificado"
    desviacion = (valor_poliza - media_mercado) / media_mercado
    if desviacion < -0.10: return f"Infraseguro ({desviacion:.1%})"
    elif desviacion > 0.10: return f"Sobreaseguro (+{desviacion:.1%})"
    return "Adecuado"

# --- INTERFAZ ---
st.title("🛡️ Sistema de Auditoría de Flotillas e Historial de Lotes - D&D")
st.caption(f"Director Técnico Senior | Gestión de Memoria Activa | {HOY}")

with st.sidebar:
    st.header("Configuración de API")
    gemini_key = st.text_input("Gemini API Key", type="password")
    
    st.divider()
    st.header("⚙️ Control de Procesamiento")
    # Control maestro para romper la restricción de reprocesamiento
    forzar_reprocesamiento = st.checkbox("🔄 Forzar reprocesamiento de archivos existentes", value=False)
    
    if st.button("🗑️ Limpiar Historial / Caché"):
        st.session_state.historico_auditorias = {}
        st.success("Historial de la sesión borrado correctamente.")
        st.rerun()

st.header("1. Carga de Lotes (Tarea A)")
archivos_adjuntos = st.file_uploader(
    "Cargar pólizas o endosos por lote (PDF)", 
    accept_multiple_files=True,
    type=["pdf"]
)

ejecutar_auditoria = st.button("🚀 Ejecutar Análisis por Lote")

if ejecutar_auditoria:
    if not archivos_adjuntos:
        st.warning("⚠️ Sube por lo menos un archivo PDF para auditar.")
    elif not gemini_key:
        st.error("🔑 Se requiere la API Key de Gemini para proceder.")
    else:
        st.subheader("📋 Resultados Consolidados del Lote Actual")
        
        # Listas globales para renderizar las alertas finales
        vehiculos_consolidados = []
        archivos_omitidos = []
        archivos_nuevos_procesados = []
        
        # Procesar lote uno por uno
        for archivo in archivos_adjuntos:
            nombre_archivo = archivo.name
            
            # CONTROL DE REPETICIÓN: Si ya existe en la caché y NO se activó forzar_reprocesamiento
            if nombre_archivo in st.session_state.historico_auditorias and not forzar_reprocesamiento:
                archivos_omitidos.append(nombre_archivo)
                # Recuperar los datos de memoria sin llamar al API
                vehiculos_consolidados.extend(st.session_state.historico_auditorias[nombre_archivo])
            else:
                # El archivo es nuevo o se solicitó explícitamente forzar la lectura
                with st.spinner(f"Analizando con Gemini 3.5 Flash: {nombre_archivo}..."):
                    try:
                        contenido_bytes = archivo.read()
                        resultado_ia = analizar_archivo_individual(nombre_archivo, contenido_bytes, gemini_key)
                        
                        # Guardar de inmediato en la caché persistente de la sesión
                        st.session_state.historico_auditorias[nombre_archivo] = resultado_ia
                        archivos_nuevos_procesados.append(nombre_archivo)
                        
                        vehiculos_consolidados.extend(resultado_ia)
                    except Exception as e:
                        st.error(f"Error procesando {nombre_archivo}: {str(e)}")

        # --- MOSTRAR LOGS DE CARGA DE CONTROL ---
        if archivos_nuevos_procesados:
            st.toast(f"✅ Se procesaron {len(archivos_nuevos_procesados)} archivo(s) nuevo(s).")
        if archivos_omitidos:
            st.info(f"ℹ️ **Archivos cargados desde la memoria local (Omitido consumo API):** {', '.join(archivos_omitidos)}")

        # --- RENDERIZADO DE TABLA FINAL UNIFICADA ---
        if vehiculos_consolidados:
            tabla_markdown = []
            alertas_piezas = []
            actualizaciones = []
            
            for item in vehiculos_consolidados:
                media_mercado = item.get("media_mercado", item["valor_poliza"]) # Lógica fallback provisional
                diag = diagnostico_suma(item["valor_poliza"], media_mercado)
                antiguedad = calcular_antiguedad_dnd(item["ano_fabricacion"])
                
                if antiguedad >= 4:
                    alertas_piezas.append(f"- **{item['vehículo']}**: Antigüedad D&D año {antiguedad}. ¡Alerta de coaseguro en piezas!")
                
                actualizaciones.append(f"- Unidad *{item['vehículo']}* extraída de **{item['origen_dato']}**.")
                
                tabla_markdown.append({
                    "Aseguradora": item["aseguradora"],
                    "Póliza #": item["poliza"],
                    "Vehículo": item["vehículo"],
                    "Valor Póliza": f"RD$ {item['valor_poliza']:,}",
                    "Media Mercado": f"RD$ {media_mercado:,}",
                    "Diagnóstico": diag,
                    "RC Exceso (Límite Actual)": item["rc_exceso"],
                    "CAA/CMA": item["caa_cma"],
                    "Asistencia": item["asistencia"]
                })
            
            # Despliegue seguro usando la dependencia de tabulate solucionada
            df_final = pd.DataFrame(tabla_markdown)
            st.markdown(df_final.to_markdown(index=False))
            
            # --- SECCIÓN DE REPORTES TÉCNICOS ---
            st.markdown("### Resumen de Alertas Técnicas")
            st.markdown("**Riesgo de Piezas (Año 4+):**")
            if alertas_piezas:
                for al in set(alertas_piezas): st.markdown(al) # Usamos set para evitar duplicados visuales
            else:
                st.markdown("- Ninguna unidad aplica para riesgo de coaseguro.")
                
            st.markdown("**Trazabilidad de Origen:**")
            for act in set(actualizaciones): st.markdown(act)
                
            st.markdown(f"**Fecha de Auditoría Dinámica:** {HOY}")
        else:
            st.warning("No se encontraron registros válidos de vehículos en los documentos procesados.")
