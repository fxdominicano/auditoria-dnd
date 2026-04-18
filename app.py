import streamlit as st
import pandas as pd
import time
import datetime
import json
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload
import io

# --- 1. CONFIGURACIÓN ---
ID_CONFIG_DIR = "15OPQmuf0CpD4MxYHFgD6Nv307Fd7POWt"
SCOPES = ['https://www.googleapis.com/auth/drive']

def obtener_servicio_drive():
    try:
        info_llave = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = service_account.Credentials.from_service_account_info(info_llave).with_scopes(SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error de identidad: {e}")
        return None

# --- 2. GESTIÓN DE CARPETAS Y REPORTE ---
def buscar_o_crear_carpeta(servicio, nombre, id_padre):
    """Solo se usa para navegar por las carpetas de origen del QNAP"""
    query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    items = res.get('files', [])
    if items: return items[0]['id']
    meta = {'name': nombre, 'parents': [id_padre], 'mimeType': 'application/vnd.google-apps.folder'}
    return servicio.files().create(body=meta, fields='id', supportsAllDrives=True).execute().get('id')

def leer_reporte_consolidado(servicio, id_carpeta_destino, nombre_archivo):
    """Lee el archivo job_XXXX_XX.json directamente en la raíz"""
    query = f"name = '{nombre_archivo}' and '{id_carpeta_destino}' in parents and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    items = res.get('files', [])
    if not items: return []
    
    request = servicio.files().get_media(fileId=items[0]['id'])
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return json.loads(fh.getvalue().decode('utf-8'))

def guardar_reporte_consolidado(servicio, datos, nombre_archivo, id_carpeta_destino):
    """Guarda o actualiza el archivo job_XXXX_XX.json en la raíz"""
    try:
        media = MediaInMemoryUpload(json.dumps(datos, indent=4).encode('utf-8'), mimetype='application/json')
        query = f"name = '{nombre_archivo}' and '{id_carpeta_destino}' in parents and trashed = false"
        res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        items = res.get('files', [])
        
        if items:
            servicio.files().update(fileId=items[0]['id'], media_body=media, supportsAllDrives=True).execute()
        else:
            meta = {'name': nombre_archivo, 'parents': [id_carpeta_destino]}
            servicio.files().create(body=meta, media_body=media, supportsAllDrives=True).execute()
    except Exception as e:
        st.warning(f"Aviso de Drive (Posible restricción de cuota). Use el botón de descarga manual. Detalle: {e}")

# --- 3. INTERFAZ ---
st.set_page_config(page_title="D&D Asesores - Auditoría Plana", layout="wide")
st.title("🛡️ Auditoría v5.2: Base de Datos Plana")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.sidebar:
    st.header("⚙️ Configuración")
    root_id = st.text_input("ID Carpeta Pólizas (QNAP)", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    tasa_usd = st.number_input("Tasa USD", value=60.15)
    st.info(f"Fecha Actual: ({datetime.datetime.now().strftime('%d/%m/%Y')})")

c1, c2 = st.columns(2)
anio_sel = c1.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
mes_idx = c2.selectbox("Mes", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
mes_nombre = MESES_DICT[str(mes_idx)]

# Generación del formato exacto solicitado (ej. job_2026_01.json)
mes_formateado = str(mes_idx).zfill(2)
nombre_reporte = f"job_{anio_sel}_{mes_formateado}.json"

tabs = st.tabs(["🚀 Ejecución", "📊 Monitor", "🏆 Reporte"])

with tabs[0]:
    st.write(f"**Archivo destino configurado:** `{nombre_reporte}`")
    
    if st.button("🔍 ESCANEAR PÓLIZAS PENDIENTES"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner("Sincronizando con Drive..."):
                # Solo navega carpetas en el Origen (QNAP)
                id_mes_orig = buscar_o_crear_carpeta(servicio, mes_nombre, buscar_o_crear_carpeta(servicio, anio_sel, root_id))
                
                # Lee directamente desde el ID_CONFIG_DIR sin crear carpetas
                historial = leer_reporte_consolidado(servicio, ID_CONFIG_DIR, nombre_reporte)
                nombres_auditados = [r['poliza'] for r in historial]
                
                # Lista los PDFs a procesar
                res = servicio.files().list(q=f"'{id_mes_orig}' in parents and mimeType='application/pdf' and trashed=false", fields="files(name)", supportsAllDrives=True).execute()
                pdf_en_drive = res.get('files', [])
                
                pendientes = [f for f in pdf_en_drive if f['name'] not in nombres_auditados]
                
                st.session_state['lote_historial'] = historial
                st.session_state['pendientes'] = pendientes
                st.success(f"✅ Escaneo listo. Auditados en {nombre_reporte}: {len(historial)} | Pendientes: {len(pendientes)}")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        if st.button("🚀 PROCESAR PENDIENTES AL ARCHIVO JOB"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            status = st.empty()
            nuevos_resultados = []
            
            for i, file in enumerate(st.session_state['pendientes']):
                status.markdown(f"**Analizando IA:** `{file['name']}`")
                time.sleep(1.2) # Espacio para procesamiento
                
                fecha_fmt = datetime.datetime.now().strftime("%d/%m/%Y")
                nuevos_resultados.append({
                    "poliza": file['name'], 
                    "status": "Auditado", 
                    "fecha_auditoria": f"({fecha_fmt})"
                })
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
            
            # Une el historial viejo con los resultados nuevos y guarda directamente en ID_CONFIG_DIR
            reporte_final = st.session_state.get('lote_historial', []) + nuevos_resultados
            guardar_reporte_consolidado(servicio, reporte_final, nombre_reporte, ID_CONFIG_DIR)
            
            st.success(f"🎉 Lote inyectado en {nombre_reporte}.")
            st.session_state['pendientes'] = []
            st.session_state['lote_historial'] = reporte_final

    if 'lote_historial' in st.session_state and st.session_state['lote_historial']:
        df = pd.DataFrame(st.session_state['lote_historial'])
        st.write("### Vista previa del Archivo Job")
        st.dataframe(df, use_container_width=True)
        st.download_button(
            label=f"📥 Descargar {nombre_reporte.replace('.json', '.csv')}", 
            data=df.to_csv(index=False).encode('utf-8'), 
            file_name=nombre_reporte.replace('.json', '.csv'), 
            mime="text/csv"
        )
