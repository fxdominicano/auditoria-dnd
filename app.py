import streamlit as st
import pandas as pd
import time
import datetime
import json
import io
import re
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload

# --- 1. CONFIGURACIÓN ---
ID_CONFIG_DIR = "15OPQmuf0CpD4MxYHFgD6Nv307Fd7POWt"
SCOPES = ['https://www.googleapis.com/auth/drive']

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

def obtener_servicio_drive():
    try:
        if "GOOGLE_USER_TOKEN" not in st.secrets:
            st.error("⚠️ Configura 'GOOGLE_USER_TOKEN' en los Secrets.")
            return None
        info_token = json.loads(st.secrets["GOOGLE_USER_TOKEN"])
        creds = Credentials.from_authorized_user_info(info_token, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error Drive: {e}"); return None

# --- 2. GESTIÓN DE ARCHIVOS ---
def buscar_carpeta(servicio, nombre, id_padre):
    query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    items = res.get('files', [])
    return items[0]['id'] if items else None

def leer_job_file(servicio, nombre_archivo):
    try:
        query = f"name = '{nombre_archivo}' and '{ID_CONFIG_DIR}' in parents and trashed = false"
        res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True).execute()
        items = res.get('files', [])
        if not items: return []
        request = servicio.files().get_media(fileId=items[0]['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        return json.loads(fh.getvalue().decode('utf-8'))
    except Exception: return []

def guardar_job_file(servicio, datos, nombre_archivo):
    try:
        media = MediaInMemoryUpload(json.dumps(datos, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json')
        query = f"name = '{nombre_archivo}' and '{ID_CONFIG_DIR}' in parents"
        res = servicio.files().list(q=query, supportsAllDrives=True).execute().get('files', [])
        if res:
            servicio.files().update(fileId=res[0]['id'], media_body=media, supportsAllDrives=True).execute()
        else:
            meta = {'name': nombre_archivo, 'parents': [ID_CONFIG_DIR]}
            servicio.files().create(body=meta, media_body=media, supportsAllDrives=True).execute()
        return True
    except Exception: return False 

# --- 3. MOTOR IA (REFRESCADO PARA EVITAR EXTRA DATA) ---
def analizar_con_gemini(servicio, file_id, file_name):
    try:
        request = servicio.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        
        model = genai.GenerativeModel('gemini-2.5-flash') 
        prompt = f"""
        Actúa como un Auditor Senior de Seguros en República Dominicana para D&D Asesores.
        Extrae datos técnicos del PDF. Si es Factura de Aumento, analiza los nuevos límites.
        
        ESTRUCTURA JSON:
        {{
            "Archivo": "{file_name}",
            "Ramo": "Texto",
            "Detalle_Objeto": "Texto",
            "Sub_Modelo": "Texto",
            "Suma_Asegurada_RD": 0,
            "Valor_Mercado_o_Limite": 0,
            "Brecha": 0,
            "Estatus": "Requiere Aumento / Correcto / Omitir - Solo Ley",
            "Nota_Auditoria": "Texto breve",
            "Fecha_Analisis": "({datetime.datetime.now().strftime('%d/%m/%Y')})"
        }}
        """
        response = model.generate_content(
            [{'mime_type': 'application/pdf', 'data': fh.getvalue()}, prompt],
            generation_config={"response_mime_type": "application/json"}
        )
        
        # Validación de seguridad: Nos aseguramos de que sea un diccionario
        resultado = json.loads(response.text)
        return resultado if isinstance(resultado, dict) else None
            
    except Exception:
        return {"Archivo": file_name, "Estatus": "Error en procesamiento de archivo"}

# --- 4. INTERFAZ ---
st.set_page_config(page_title="D&D Auditoría IA", layout="wide", page_icon="🛡️")
st.title("🛡️ Auditoría Integral v8.1")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.container(border=True):
    st.subheader("📅 Periodo de Auditoría")
    col1, col2 = st.columns(2)
    anio_sel = col1.selectbox("Año", ["2025", "2026", "2027"], index=1)
    mes_idx = col2.selectbox("Mes", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
    mes_nombre = MESES_DICT[str(mes_idx)]
    nombre_reporte = f"job_{anio_sel}_{str(mes_idx).zfill(2)}.json"

with st.sidebar:
    st.header("⚙️ NAS")
    root_id = st.text_input("ID Carpeta QNAP", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")

t1, t2, t3 = st.tabs(["🚀 Ejecución", "📊 Monitor", "🏆 Reporte"])

with t1:
    if st.button("🔍 ESCANEAR QNAP"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner("Sincronizando..."):
                id_anio = buscar_carpeta(servicio, anio_sel, root_id)
                id_mes = buscar_carpeta(servicio, mes_nombre, id_anio) if id_anio else None
                if not id_mes: st.error("Carpeta no encontrada."); st.stop()
                
                historial = leer_job_file(servicio, nombre_reporte)
                auditados = [r.get('Archivo', '') for r in historial if isinstance(r, dict)]
                res = servicio.files().list(q=f"'{id_mes}' in parents and mimeType='application/pdf' and trashed=false", fields="files(id, name)").execute()
                pdfs = res.get('files', [])
                
                st.session_state['lote_historial'] = historial
                st.session_state['pendientes'] = [f for f in pdfs if f['name'] not in auditados]
                st.session_state['total_pdfs'] = len(pdfs)
                st.success(f"Sincronizado: {len(st.session_state['pendientes'])} pendientes.")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        if st.button("🚀 INICIAR AUDITORÍA INCREMENTAL"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            status = st.empty()
            lote = st.session_state['lote_historial']
            
            for i, f in enumerate(st.session_state['pendientes']):
                status.markdown(f"**Analizando:** `{f['name']}`")
                res_ia = analizar_con_gemini(servicio, f['id'], f['name'])
                
                # --- FIX: VALIDACIÓN DE DICCIONARIO ---
                if res_ia and isinstance(res_ia, dict):
                    if "Omitir" not in str(res_ia.get('Estatus', '')):
                        lote.append(res_ia)
                        guardar_job_file(servicio, lote, nombre_reporte)
                else:
                    # Si falla, guardamos un registro de error para no quedarnos trabados
                    lote.append({"Archivo": f['name'], "Estatus": "Error: IA devolvió formato inválido"})
                    guardar_job_file(servicio, lote, nombre_reporte)
                
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
            
            st.session_state['pendientes'] = []
            st.success("Proceso finalizado.")

with t2:
    if 'total_pdfs' in st.session_state:
        hechos = len(st.session_state.get('lote_historial', []))
        st.metric("Auditados", f"{hechos} de {st.session_state['total_pdfs']}")
        st.progress(hechos / st.session_state['total_pdfs'])

with t3:
    if st.session_state.get('lote_historial'):
        df = pd.DataFrame(st.session_state['lote_historial'])
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Descargar CSV", df.to_csv(index=False), f"{nombre_reporte}.csv")
