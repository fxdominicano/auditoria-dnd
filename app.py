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

# Configuración con el modelo que te funciona: Gemini 2.5 Flash
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

# --- 3. ANALISIS IA CON GEMINI 2.5 FLASH (LOGICA MULTIRRAMO) ---
def analizar_con_gemini(servicio, file_id, file_name):
    try:
        request = servicio.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        
        # Modelo especificado por el usuario
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"""
        Analiza esta póliza para D&D Asesores (Santiago, RD). 
        
        REGLAS DE AUDITORÍA:
        1. VEHÍCULOS: Solo procesa si tiene "Daños Propios" (Seguro Full). Si es solo Ley o RC, indica "Omitir - Ley".
           Extrae Marca, Modelo, Año y SUB-MODELO (XLE, LE, SE, etc). Estima valor mercado en RD (media de 5-8 similares).
        2. INCENDIO, RC, MAQUINARIA, FIDELIDAD: Verifica los montos asegurados y límites. Indica si parecen consistentes.
        
        RESPUESTA JSON ESTRICTO:
        {{
            "Archivo": "{file_name}",
            "Ramo": "Vehículos / Incendio / RC / Otros",
            "Detalle_Objeto": "Marca/Modelo/Año o Descripción del Riesgo",
            "Suma_Asegurada_RD": 0,
            "Valor_Mercado_o_Limite": 0,
            "Brecha_Detectada": 0,
            "Estatus": "Requiere Aumento / Correcto / Omitir",
            "Nota_Tecnica": "Explicación breve de la verificación del monto"
        }}
        """
        response = model.generate_content([{'mime_type': 'application/pdf', 'data': fh.getvalue()}, prompt])
        return json.loads(response.text.strip().replace("```json", "").replace("```", ""))
    except Exception as e:
        return {"Archivo": file_name, "Estatus": f"Error: {str(e)[:40]}"}

# --- 4. INTERFAZ ---
st.set_page_config(page_title="D&D Auditoría v6.5", layout="wide")
st.title("🛡️ Auditoría Integral v6.5 (Gemini 2.5)")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.sidebar:
    st.header("⚙️ Configuración")
    root_id = st.text_input("ID Raíz QNAP", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    st.info(f"📍 Santiago, RD | 📅 ({datetime.datetime.now().strftime('%d/%m/%Y')})")

c1, c2 = st.columns(2)
anio_sel = c1.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
mes_idx = c2.selectbox("Mes", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
nombre_reporte = f"job_{anio_sel}_{str(mes_idx).zfill(2)}.json"

tabs = st.tabs(["🚀 Ejecución IA", "📊 Monitor", "🏆 Reporte Mercado"])

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
                st.success(f"Listo. {len(st.session_state['pendientes'])} nuevos.")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        if st.button("🚀 INICIAR AUDITORÍA"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            lote = st.session_state.get('lote_historial', [])
            for i, f in enumerate(st.session_state['pendientes']):
                st.write(f"Analizando: {f['name']}")
                res_ia = analizar_con_gemini(servicio, f['id'], f['name'])
                if res_ia.get('Estatus') != "Omitir":
                    lote.append(res_ia)
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
            guardar_reporte_consolidado(servicio, lote, nombre_reporte, ID_CONFIG_DIR)
            st.session_state['lote_historial'] = lote
            st.session_state['pendientes'] = []
            st.success("✅ ¡Proceso terminado!")

with tabs[1]:
    if 'total_lote' in st.session_state:
        total = st.session_state['total_lote']
        hechos = len(st.session_state.get('lote_historial', []))
        prog_v = min(1.0, hechos / total) if total > 0 else 0.0
        c1, c2, c3 = st.columns(3)
        c1.metric("En QNAP", total)
        c2.metric("Auditados", hechos)
        c3.metric("Progreso", f"{int(prog_v * 100)}%")
        st.progress(prog_v)

with tabs[2]:
    datos = st.session_state.get('lote_historial', [])
    if datos:
        df = pd.DataFrame(datos)
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Excel (CSV)", df.to_csv(index=False).encode('utf-8'), f"{nombre_reporte}.csv", "text/csv")
