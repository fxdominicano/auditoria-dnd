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

# --- 1. CONFIGURACIÓN ---
ID_CONFIG_DIR = "15OPQmuf0CpD4MxYHFgD6Nv307Fd7POWt"
SCOPES = ['https://www.googleapis.com/auth/drive']

# Configuración del motor solicitado: Gemini 2.5 Flash
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

def obtener_servicio_drive():
    try:
        info_llave = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = service_account.Credentials.from_service_account_info(info_llave).with_scopes(SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception: return None

# --- 2. FUNCIONES DE DRIVE ---
def buscar_o_crear_carpeta(servicio, nombre, id_padre):
    query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    items = res.get('files', [])
    if items: return items[0]['id']
    meta = {'name': nombre, 'parents': [id_padre], 'mimeType': 'application/vnd.google-apps.folder'}
    return servicio.files().create(body=meta, fields='id', supportsAllDrives=True).execute().get('id')

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
        while not done: _, done = downloader.next_chunk()
        data = json.loads(fh.getvalue().decode('utf-8'))
        return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
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
        else:
            meta = {'name': nombre_archivo, 'parents': [id_carpeta_destino]}
            servicio.files().create(body=meta, media_body=media, supportsAllDrives=True).execute()
            return True
    except Exception: return False

# --- 3. ANALISIS IA CON GEMINI 2.5 FLASH ---
def analizar_con_gemini(servicio, file_id, file_name):
    try:
        request = servicio.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        
        # Uso de Gemini 2.5 Flash
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"""
        Auditoría para D&D Asesores (Santiago, RD). 
        Analiza este PDF y extrae: Marca, Modelo, Año y SUB-MODELO (XLE, LE, SE, Platinum, etc).
        Busca el valor de mercado actual en RD (media de 5-8 modelos similares) y compáralo con la Suma Asegurada.
        
        RESPUESTA JSON ESTRICTO:
        {{
            "Archivo": "{file_name}",
            "Marca": "...", "Modelo": "...", "Sub_Modelo": "...", "Anio": "...",
            "Suma_Asegurada_RD": 0, "Valor_Mercado_RD": 0, "Brecha": 0,
            "Recomendacion": "Requiere Aumento / Correcto",
            "Fecha": "({datetime.datetime.now().strftime('%d/%m/%Y')})"
        }}
        """
        response = model.generate_content([{'mime_type': 'application/pdf', 'data': fh.getvalue()}, prompt])
        return json.loads(response.text.strip().replace("```json", "").replace("```", ""))
    except Exception as e:
        return {"Archivo": file_name, "Recomendacion": f"Error: {str(e)[:40]}"}

# --- 4. INTERFAZ ---
st.set_page_config(page_title="D&D Auditoría v6.3", layout="wide")
st.title("🛡️ Auditoría v6.3 (Gemini 2.5 Flash)")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.sidebar:
    st.header("⚙️ Configuración")
    root_id = st.text_input("ID Raíz QNAP", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    st.info(f"📍 Santiago, RD\n📅 ({datetime.datetime.now().strftime('%d/%m/%Y')})")

c1, c2 = st.columns(2)
anio_sel = c1.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
mes_idx = c2.selectbox("Mes", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
nombre_reporte = f"job_{anio_sel}_{str(mes_idx).zfill(2)}.json"

tabs = st.tabs(["🚀 Ejecución", "📊 Monitor", "🏆 Reporte Mercado"])

with tabs[0]:
    if st.button("🔍 ESCANEAR QNAP"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner("Sincronizando..."):
                id_mes = buscar_o_crear_carpeta(servicio, MESES_DICT[str(mes_idx)], buscar_o_crear_carpeta(servicio, anio_sel, root_id))
                historial = leer_reporte_consolidado(servicio, ID_CONFIG_DIR, nombre_reporte)
                auditados = [r.get('Archivo', '') for r in historial]
                res = servicio.files().list(q=f"'{id_mes}' in parents and mimeType='application/pdf'", fields="files(id, name)", supportsAllDrives=True).execute()
                pdfs = res.get('files', [])
                st.session_state['lote_historial'] = historial
                st.session_state['pendientes'] = [f for f in pdfs if f['name'] not in auditados]
                st.session_state['total_lote'] = len(pdfs)
                st.success(f"Escaneo listo. {len(st.session_state['pendientes'])} nuevos.")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        if st.button("🚀 INICIAR GEMINI 2.5 FLASH"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            lote = st.session_state.get('lote_historial', [])
            for i, f in enumerate(st.session_state['pendientes']):
                st.write(f"Analizando: {f['name']}")
                lote.append(analizar_con_gemini(servicio, f['id'], f['name']))
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
            guardar_reporte_consolidado(servicio, lote, nombre_reporte, ID_CONFIG_DIR)
            st.session_state['lote_historial'] = lote
            st.session_state['pendientes'] = []
            st.success("✅ ¡Proceso terminado!")

with tabs[1]:
    if 'total_lote' in st.session_state:
        total = st.session_state['total_lote']
        hechos = len(st.session_state.get('lote_historial', []))
        # BLINDAJE: El valor para st.progress debe estar entre 0.0 y 1.0
        progreso_valor = min(1.0, hechos / total) if total > 0 else 0.0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("En QNAP", total)
        c2.metric("Auditados", hechos)
        c3.metric("Progreso", f"{int(progreso_valor * 100)}%")
        st.progress(progreso_valor)
    else:
        st.info("Escanee primero.")

with tabs[2]:
    datos = st.session_state.get('lote_historial', [])
    if datos:
        df = pd.DataFrame(datos)
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Descargar Excel (CSV)", df.to_csv(index=False).encode('utf-8'), f"{nombre_reporte}.csv", "text/csv")
