import streamlit as st
import pandas as pd
import time
import datetime
import json
import io
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload

# --- 1. CONFIGURACIÓN Y CREDENCIALES ---
ID_CONFIG_DIR = "15OPQmuf0CpD4MxYHFgD6Nv307Fd7POWt"
SCOPES = ['https://www.googleapis.com/auth/drive']

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

def obtener_servicio_drive():
    try:
        info_llave = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = service_account.Credentials.from_service_account_info(info_llave).with_scopes(SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception: return None

# --- 2. GESTIÓN DE DRIVE (NAVEGACIÓN Y LECTURA) ---
def buscar_o_crear_carpeta(servicio, nombre, id_padre):
    query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    items = res.get('files', [])
    if items: return items[0]['id']
    meta = {'name': nombre, 'parents': [id_padre], 'mimeType': 'application/vnd.google-apps.folder'}
    return servicio.files().create(body=meta, fields='id', supportsAllDrives=True).execute().get('id')

def leer_job_file(servicio, nombre_archivo):
    """Lee el reporte consolidado directamente de la raíz de configuración"""
    try:
        query = f"name = '{nombre_archivo}' and '{ID_CONFIG_DIR}' in parents and trashed = false"
        res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        items = res.get('files', [])
        if not items: return []
        
        request = servicio.files().get_media(fileId=items[0]['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        data = json.loads(fh.getvalue().decode('utf-8'))
        return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
    except Exception: return []

# --- 3. MOTOR DE AUDITORÍA (GEMINI 2.5 FLASH) ---
def analizar_poda_ia(servicio, file_id, file_name):
    try:
        request = servicio.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        Auditor Senior D&D Asesores (Santiago, RD). Analiza esta póliza:
        1. VEHÍCULOS: Verifica si es "Seguro Full" (Daños Propios). Si es Ley o solo RC, pon Estatus: "Omitir".
           Para Full: Extrae Marca, Modelo, Año, Sub-Modelo (XLE, SE, etc) y estima valor mercado RD.
        2. OTROS: Para Incendio, RC, Maquinaria, Fidelidad, verifica montos y límites vs riesgo descrito.
        
        JSON:
        {{
            "Archivo": "{file_name}",
            "Ramo": "...", "Detalle": "...", "Suma_RD": 0, "Mercado_RD": 0,
            "Estatus": "Requiere Aumento / Correcto / Omitir", "Nota": "..."
        }}
        """
        response = model.generate_content([{'mime_type': 'application/pdf', 'data': fh.getvalue()}, prompt])
        return json.loads(response.text.strip().replace("```json", "").replace("```", ""))
    except Exception:
        return {"Archivo": file_name, "Estatus": "Error IA"}

# --- 4. INTERFAZ Y FLUJO ---
st.set_page_config(page_title="D&D Auditoría v6.8", layout="wide", page_icon="🛡️")
st.title("🛡️ Auditoría v6.8: Control Total")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.sidebar:
    st.header("⚙️ Configuración")
    root_id = st.text_input("ID Carpeta QNAP", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    st.divider()
    # RESTAURADOS: Selectores de Año y Mes
    anio_sel = st.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
    mes_idx = st.selectbox("Mes de Auditoría", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
    mes_nombre = MESES_DICT[str(mes_idx)]
    nombre_reporte = f"job_{anio_sel}_{str(mes_idx).zfill(2)}.json"
    st.info(f"📂 Archivo: {nombre_reporte}")

tabs = st.tabs(["🚀 Ejecución", "📊 Monitor de Estatus", "🏆 Reporte Final"])

# --- TAB 1: ESCANEO Y PROCESAMIENTO ---
with tabs[0]:
    if st.button("🔍 ESCANEAR PÓLIZAS PENDIENTES"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner(f"Escaneando {mes_nombre} {anio_sel}..."):
                # Navegación en QNAP
                id_anio = buscar_o_crear_carpeta(servicio, anio_sel, root_id)
                id_mes = buscar_o_crear_carpeta(servicio, mes_nombre, id_anio)
                
                # Cargar historial del archivo JOB
                historial = leer_job_file(servicio, nombre_reporte)
                auditados = [r.get('Archivo', '') for r in historial if isinstance(r, dict)]
                
                # Listar archivos actuales en el NAS
                res = servicio.files().list(q=f"'{id_mes}' in parents and mimeType='application/pdf' and trashed=false", 
                                            fields="files(id, name)", supportsAllDrives=True).execute()
                pdfs_nas = res.get('files', [])
                
                pendientes = [f for f in pdfs_nas if f['name'] not in auditados]
                
                st.session_state['historial'] = historial
                st.session_state['pendientes'] = pendientes
                st.session_state['total_pdfs'] = len(pdfs_nas)
                st.success(f"Detección exitosa: {len(pendientes)} pólizas nuevas por analizar.")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        if st.button("🚀 INICIAR PROCESAMIENTO BATCH"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            status_text = st.empty()
            lote_completo = st.session_state['historial']
            
            for i, file in enumerate(st.session_state['pendientes']):
                status_text.markdown(f"**Auditando:** `{file['name']}`")
                res_ia = analizar_con_gemini(servicio, file['id'], file['name'])
                
                if res_ia.get("Estatus") != "Omitir":
                    lote_completo.append(res_ia)
                
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
                
            # Guardado único al finalizar el lote
            media = MediaInMemoryUpload(json.dumps(lote_completo, indent=4).encode('utf-8'), mimetype='application/json')
            query = f"name = '{nombre_reporte}' and '{ID_CONFIG_DIR}' in parents"
            existentes = servicio.files().list(q=query, supportsAllDrives=True).execute().get('files', [])
            
            if existentes:
                servicio.files().update(fileId=existentes[0]['id'], media_body=media, supportsAllDrives=True).execute()
            else:
                meta = {'name': nombre_reporte, 'parents': [ID_CONFIG_DIR]}
                servicio.files().create(body=meta, media_body=media, supportsAllDrives=True).execute()
            
            st.session_state['historial'] = lote_completo
            st.session_state['pendientes'] = []
            st.success("🎉 Auditoría de lote completada.")

# --- TAB 2: MONITOR DE ESTATUS ---
with tabs[1]:
    st.subheader("Verificación de Auditoría")
    if 'total_pdfs' in st.session_state:
        total = st.session_state['total_pdfs']
        analizados = len(st.session_state.get('historial', []))
        prog_v = min(1.0, analizados / total) if total > 0 else 0.0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total en NAS", total)
        c2.metric("Auditados (Job)", analizados)
        c3.metric("Estatus", f"{int(prog_v * 100)}%")
        st.progress(prog_v)
        
        if prog_v == 1.0: st.success("✅ Este mes ya está totalmente auditado.")
    else:
        st.info("Utilice la pestaña 'Ejecución' para escanear los archivos del mes.")

# --- TAB 3: REPORTE ---
with tabs[2]:
    datos = st.session_state.get('historial', [])
    if datos:
        df = pd.DataFrame(datos)
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Descargar Reporte CSV", df.to_csv(index=False), f"{nombre_reporte}.csv", "text/csv")
    else:
        st.warning("No hay datos auditados para mostrar en este periodo.")
