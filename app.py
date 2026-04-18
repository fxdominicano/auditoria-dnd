import streamlit as st
import pandas as pd
import time
import datetime
import json
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaInMemoryUpload

# --- 1. CONFIGURACIÓN E IDENTIDAD DIGITAL ---
# ID de la carpeta raíz de configuración en Santiago
ID_CONFIG_DIR = "15OPQmuf0CpD4MxYHFgD6Nv307Fd7POWt"
# Scope total para permitir lectura y escritura en Drive
SCOPES = ['https://www.googleapis.com/auth/drive']

def obtener_servicio_drive():
    try:
        # Carga de credenciales desde Streamlit Secrets
        info_llave = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = service_account.Credentials.from_service_account_info(
            info_llave
        ).with_scopes(SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error crítico de identidad: {e}")
        return None

# --- 2. MOTOR DE NAVEGACIÓN RESILIENTE (SOPORTE QNAP/ALL DRIVES) ---
def buscar_o_crear_carpeta(servicio, nombre, id_padre):
    try:
        # Búsqueda con soporte para todas las unidades (necesario para sincronización NAS)
        query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = servicio.files().list(
            q=query, 
            fields="files(id)", 
            supportsAllDrives=True, 
            includeItemsFromAllDrives=True
        ).execute()
        
        items = res.get('files', [])
        if items:
            return items[0]['id']
        else:
            # Creación con soporte para todas las unidades
            meta = {'name': nombre, 'parents': [id_padre], 'mimeType': 'application/vnd.google-apps.folder'}
            folder = servicio.files().create(
                body=meta, 
                fields='id', 
                supportsAllDrives=True
            ).execute()
            return folder.get('id')
    except Exception as e:
        st.error(f"⚠️ Error de acceso en carpeta '{nombre}': {e}")
        st.stop()

def archivo_ya_auditado(servicio, nombre_pdf, id_carpeta_mes):
    """Evita el reprocesamiento y duplicidad de reportes"""
    nombre_json = nombre_pdf.replace(".pdf", ".json")
    query = f"name = '{nombre_json}' and '{id_carpeta_mes}' in parents and trashed = false"
    res = servicio.files().list(
        q=query, 
        fields="files(id)", 
        supportsAllDrives=True, 
        includeItemsFromAllDrives=True
    ).execute()
    return len(res.get('files', [])) > 0

def guardar_json_auditado(servicio, datos, nombre_pdf, id_carpeta_mes):
    """Guarda el reporte técnico final en la nube"""
    try:
        nombre_json = nombre_pdf.replace(".pdf", ".json")
        media = MediaInMemoryUpload(
            json.dumps(datos, indent=4).encode('utf-8'), 
            mimetype='application/json'
        )
        meta = {'name': nombre_json, 'parents': [id_carpeta_mes]}
        servicio.files().create(
            body=meta, 
            media_body=media, 
            supportsAllDrives=True
        ).execute()
    except Exception as e:
        st.error(f"🔴 Fallo al escribir reporte: {nombre_json}. Detalle: {e}")
        st.stop()

# --- 3. INTERFAZ PROFESIONAL D&D ASESORES ---
st.set_page_config(
    page_title="D&D Asesores - Auditoría Inteligente", 
    layout="wide", 
    page_icon="🛡️"
)

# Título Principal
st.title("🛡️ Motor de Auditoría Inteligente")

# Estructura de carpetas según tu Drive
MESES_DICT = {
    "1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril",
    "5":"05- Mayo","6":"06- Junio","7":"07- Julio","8":"08- Agosto",
    "9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"
}

with st.sidebar:
    st.header("⚙️ Configuración")
    # Obtención dinámica de IDs guardados en Secrets
    root_id = st.text_input("ID Carpeta Pólizas (QNAP)", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    tasa_usd = st.number_input("Tasa USD a RD$", value=60.15)
    st.divider()
    # Fecha en formato solicitado (DD/MM/AAAA)
    fecha_hoy = datetime.datetime.now().strftime("%d/%m/%Y")
    st.info(f"📍 Santiago, RD\n📅 Hoy: {fecha_hoy}")

# Selectores de Lote
col1, col2 = st.columns(2)
anio_sel = col1.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
mes_idx = col2.selectbox(
    "Mes de Auditoría", 
    range(1, 13), 
    index=datetime.datetime.now().month-1, 
    format_func=lambda x: MESES_DICT[str(x)]
)
mes_nombre = MESES_DICT[str(mes_idx)]

tabs = st.tabs(["🚀 Ejecución", "📊 Monitor en Vivo", "🏆 Reporte de Ingresos"])

# --- PESTAÑA 1: OPERACIÓN ---
with tabs[0]:
    if st.button("🔍 ESCANEAR PÓLIZAS PENDIENTES"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner("Validando estructura en Google Drive..."):
                # 1. Navegar en Origen (QNAP Sync)
                id_anio_origen = buscar_o_crear_carpeta(servicio, anio_sel, root_id)
                id_mes_origen = buscar_o_crear_carpeta(servicio, mes_nombre, id_anio_origen)
                
                # 2. Navegar en Destino (Config_Auditoria_DyD)
                id_anio_dest = buscar_o_crear_carpeta(servicio, anio_sel, ID_CONFIG_DIR)
                id_mes_dest = buscar_o_crear_carpeta(servicio, mes_nombre, id_anio_dest)
                
                # 3. Listar archivos PDF reales
                query = f"'{id_mes_origen}' in parents and mimeType = 'application/pdf' and trashed = false"
                res = servicio.files().list(
                    q=query, 
                    fields="files(id, name)", 
                    supportsAllDrives=True, 
                    includeItemsFromAllDrives=True
                ).execute()
                lista_raw = res.get('files', [])
                
                # 4. Filtrar los que no tienen JSON en la carpeta de destino
                pendientes = [f for f in lista_raw if not archivo_ya_auditado(servicio, f['name'], id_mes_dest)]
                
                st.session_state['pendientes'] = pendientes
                st.session_state['id_destino'] = id_mes_dest
                st.success(f"✅ Escaneo completado. Pólizas totales: {len(lista_raw)} | Pendientes: {len(pendientes)}")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        st.write("### Listado de Documentos para Procesar")
        st.dataframe(
            pd.DataFrame(st.session_state['pendientes'])[['name']].rename(columns={'name':'Archivo'}), 
            use_container_width=True
        )
        
        if st.button("🚀 INICIAR AUDITORÍA DE LOTE"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            status = st.empty()
            
            for i, file in enumerate(st.session_state['pendientes']):
                status.markdown(f"**Analizando:** `{file['name']}`")
                
                # Simulación de respuesta IA (Aquí se conecta con Gemini en la v5.0)
                time.sleep(1.2)
                fecha_fmt = datetime.datetime.now().strftime("%d/%m/%Y")
                resultado = {
                    "poliza": file['name'], 
                    "status": "Auditado", 
                    "fecha_auditoria": f"({fecha_fmt})",
                    "broker": "D&D Asesores"
                }
                
                # Guardado persistente en Config_Auditoria_DyD
                guardar_json_auditado(servicio, resultado, file['name'], st.session_state['id_destino'])
                
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
            
            st.success("🎉 Auditoría finalizada. Los reportes están seguros en su carpeta de configuración.")
            st.session_state['pendientes'] = [] 

# --- PESTAÑAS 2 Y 3 (RESERVADAS PARA VISUALIZACIÓN) ---
with tabs[1]:
    st.info("Esta sección leerá los JSON generados para mostrar el estatus de la cartera.")

with tabs[2]:
    st.info("Aquí se calculará la comisión recuperable basándose en el análisis de Gemini.")
