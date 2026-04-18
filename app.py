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
    except Exception:
        st.error("Error de credenciales en Streamlit Secrets.")
        return None

# --- 2. GESTIÓN DE CARPETAS Y REPORTE ---
def buscar_o_crear_carpeta(servicio, nombre, id_padre):
    query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    items = res.get('files', [])
    if items: return items[0]['id']
    return None # Evitamos intentar crear carpetas con el robot

def leer_reporte_consolidado(servicio, id_carpeta_destino, nombre_archivo):
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
    try:
        media = MediaInMemoryUpload(json.dumps(datos, indent=4).encode('utf-8'), mimetype='application/json')
        query = f"name = '{nombre_archivo}' and '{id_carpeta_destino}' in parents and trashed = false"
        res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        items = res.get('files', [])
        
        # Solo intenta actualizar si el archivo ya existe (creado por ti)
        if items:
            servicio.files().update(fileId=items[0]['id'], media_body=media, supportsAllDrives=True).execute()
            return True
        return False
    except Exception:
        return False

# --- 3. INTERFAZ ---
st.set_page_config(page_title="D&D Asesores - Auditoría Plana", layout="wide")
st.title("🛡️ Auditoría v5.3: Operación Táctica")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.sidebar:
    st.header("⚙️ Configuración")
    root_id = st.text_input("ID Carpeta Pólizas (QNAP)", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    st.number_input("Tasa USD", value=60.15)
    st.info(f"Fecha Actual: ({datetime.datetime.now().strftime('%d/%m/%Y')})")

c1, c2 = st.columns(2)
anio_sel = c1.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
mes_idx = c2.selectbox("Mes", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
mes_nombre = MESES_DICT[str(mes_idx)]

mes_formateado = str(mes_idx).zfill(2)
nombre_reporte = f"job_{anio_sel}_{mes_formateado}.json"

tabs = st.tabs(["🚀 Ejecución", "🏆 Reporte Generado"])

with tabs[0]:
    st.write(f"**Archivo de control:** `{nombre_reporte}`")
    
    if st.button("🔍 ESCANEAR PÓLIZAS PENDIENTES"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner("Leyendo QNAP y Drive..."):
                id_anio_orig = buscar_o_crear_carpeta(servicio, anio_sel, root_id)
                id_mes_orig = buscar_o_crear_carpeta(servicio, mes_nombre, id_anio_orig) if id_anio_orig else None
                
                if id_mes_orig:
                    historial = leer_reporte_consolidado(servicio, ID_CONFIG_DIR, nombre_reporte)
                    nombres_auditados = [r['poliza'] for r in historial]
                    
                    res = servicio.files().list(q=f"'{id_mes_orig}' in parents and mimeType='application/pdf' and trashed=false", fields="files(name)", supportsAllDrives=True).execute()
                    pdf_en_drive = res.get('files', [])
                    
                    pendientes = [f for f in pdf_en_drive if f['name'] not in nombres_auditados]
                    
                    st.session_state['lote_historial'] = historial
                    st.session_state['pendientes'] = pendientes
                    st.success(f"✅ Escaneo listo. Auditados previamente: {len(historial)} | Pendientes: {len(pendientes)}")
                else:
                    st.error("No se encontró la carpeta del mes en el origen.")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        if st.button("🚀 PROCESAR PENDIENTES"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            nuevos_resultados = []
            
            for i, file in enumerate(st.session_state['pendientes']):
                time.sleep(1.2)
                fecha_fmt = datetime.datetime.now().strftime("%d/%m/%Y")
                nuevos_resultados.append({
                    "poliza": file['name'], 
                    "status": "Auditado", 
                    "fecha_auditoria": f"({fecha_fmt})"
                })
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
            
            reporte_final = st.session_state.get('lote_historial', []) + nuevos_resultados
            
            # Intento silencioso de guardar. Si falla por cuota, no rompe la web.
            guardado_exitoso = guardar_reporte_consolidado(servicio, reporte_final, nombre_reporte, ID_CONFIG_DIR)
            
            st.session_state['pendientes'] = []
            st.session_state['lote_historial'] = reporte_final
            
            if guardado_exitoso:
                st.success("🎉 Actualizado directamente en Google Drive.")
            else:
                st.warning("⚠️ Proceso completado en memoria. Vaya a la pestaña '🏆 Reporte Generado' para descargar su archivo JSON y súbalo manualmente a Drive.")

with tabs[1]:
    if 'lote_historial' in st.session_state and st.session_state['lote_historial']:
        st.write("### Datos listos para guardar")
        json_str = json.dumps(st.session_state['lote_historial'], indent=4)
        
        st.download_button(
            label=f"📥 DESCARGAR {nombre_reporte} (JSON)", 
            data=json_str, 
            file_name=nombre_reporte, 
            mime="application/json"
        )
        st.info("💡 Instrucción: Descargue este archivo y súbalo desde su celular a la carpeta 'Config_Auditoria_DyD' en Google Drive para que el sistema no duplique estos archivos mañana.")
