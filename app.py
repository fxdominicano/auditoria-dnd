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
        return None

# --- 2. FUNCIONES DE APOYO ---
def buscar_o_crear_carpeta(servicio, nombre, id_padre):
    query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    items = res.get('files', [])
    return items[0]['id'] if items else None

def leer_reporte_consolidado(servicio, id_carpeta_destino, nombre_archivo):
    try:
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
    except Exception: return []

def guardar_reporte_consolidado(servicio, datos, nombre_archivo, id_carpeta_destino):
    try:
        media = MediaInMemoryUpload(json.dumps(datos, indent=4).encode('utf-8'), mimetype='application/json')
        query = f"name = '{nombre_archivo}' and '{id_carpeta_destino}' in parents and trashed = false"
        res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        items = res.get('files', [])
        if items:
            servicio.files().update(fileId=items[0]['id'], media_body=media, supportsAllDrives=True).execute()
            return True
        return False
    except Exception: return False

# --- 3. INTERFAZ ---
st.set_page_config(page_title="D&D Asesores - Auditoría Pro", layout="wide", page_icon="🛡️")
st.title("🛡️ Sistema de Auditoría v5.4")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.sidebar:
    st.header("⚙️ Configuración")
    root_id = st.text_input("ID Carpeta Pólizas (QNAP)", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    tasa_usd = st.number_input("Tasa USD", value=60.15)
    st.info(f"📍 Santiago, RD\n📅 ({datetime.datetime.now().strftime('%d/%m/%Y')})")

c1, c2 = st.columns(2)
anio_sel = c1.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
mes_idx = c2.selectbox("Mes", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
mes_nombre = MESES_DICT[str(mes_idx)]

nombre_reporte = f"job_{anio_sel}_{str(mes_idx).zfill(2)}.json"
tabs = st.tabs(["🚀 Ejecución", "📊 Monitor de Lote", "🏆 Reporte Final"])

# --- TAB 1: LANZAMIENTO ---
with tabs[0]:
    if st.button("🔍 ESCANEAR PÓLIZAS"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner("Analizando carpetas..."):
                id_mes_orig = buscar_o_crear_carpeta(servicio, mes_nombre, buscar_o_crear_carpeta(servicio, anio_sel, root_id))
                historial = leer_reporte_consolidado(servicio, ID_CONFIG_DIR, nombre_reporte)
                nombres_auditados = [r['poliza'] for r in historial]
                
                res = servicio.files().list(q=f"'{id_mes_orig}' in parents and mimeType='application/pdf' and trashed=false", fields="files(name)", supportsAllDrives=True).execute()
                pdf_en_drive = res.get('files', [])
                
                pendientes = [f for f in pdf_en_drive if f['name'] not in nombres_auditados]
                
                st.session_state['lote_historial'] = historial
                st.session_state['pendientes'] = pendientes
                st.session_state['total_pdfs'] = len(pdf_en_drive)
                st.success(f"Escaneo listo. {len(pendientes)} pólizas nuevas detectadas.")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        if st.button("🚀 INICIAR PROCESAMIENTO"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            status_text = st.empty()
            resultados_actuales = st.session_state.get('lote_historial', [])
            
            for i, file in enumerate(st.session_state['pendientes']):
                status_text.markdown(f"**Auditando:** `{file['name']}`")
                time.sleep(1.2)
                
                nuevo_dato = {
                    "poliza": file['name'], 
                    "status": "Finalizado", 
                    "fecha": f"({datetime.datetime.now().strftime('%d/%m/%Y')})"
                }
                resultados_actuales.append(nuevo_dato)
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
            
            # Intento de guardado
            exito = guardar_reporte_consolidado(servicio, resultados_actuales, nombre_reporte, ID_CONFIG_DIR)
            st.session_state['lote_historial'] = resultados_actuales
            st.session_state['pendientes'] = []
            
            if exito: st.success("🎉 Datos guardados en Drive.")
            else: st.warning("⚠️ Guardado en memoria. Descargue el archivo en la pestaña Reporte.")

# --- TAB 2: MONITOR DE PRODUCTIVIDAD ---
with tabs[1]:
    st.subheader(f"Estatus del Lote: `{nombre_reporte}`")
    
    total = st.session_state.get('total_pdfs', 0)
    auditados = len(st.session_state.get('lote_historial', []))
    
    if total > 0:
        porcentaje = int((auditados / total) * 100)
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total en QNAP", total)
        m2.metric("Auditados", auditados)
        m3.metric("Progreso", f"{porcentaje}%")
        
        st.write("### Nivel de Avance")
        st.progress(porcentaje / 100)
        
        if porcentaje == 100:
            st.balloons()
            st.success("¡Mes completado al 100%!")
    else:
        st.info("Escanee las pólizas en la primera pestaña para ver las métricas.")

# --- TAB 3: REPORTE ---
with tabs[2]:
    if 'lote_historial' in st.session_state and st.session_state['lote_historial']:
        df = pd.DataFrame(st.session_state['lote_historial'])
        st.dataframe(df, use_container_width=True)
        
        c1, c2 = st.columns(2)
        c1.download_button("📥 Descargar JSON", json.dumps(st.session_state['lote_historial'], indent=4), nombre_reporte, "application/json")
        c2.download_button("📥 Descargar CSV (Excel)", df.to_csv(index=False), nombre_reporte.replace(".json", ".csv"), "text/csv")
    else:
        st.warning("No hay datos auditados para mostrar.")
