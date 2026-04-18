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

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
ID_CONFIG_DIR = "15OPQmuf0CpD4MxYHFgD6Nv307Fd7POWt"
SCOPES = ['https://www.googleapis.com/auth/drive']

# Configuración del motor de IA
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Falta GEMINI_API_KEY en los Secrets.")

def obtener_servicio_drive():
    try:
        info_llave = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = service_account.Credentials.from_service_account_info(info_llave).with_scopes(SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error de credenciales: {e}")
        return None

# --- 2. FUNCIONES DE DRIVE Y CARPETAS ---
def buscar_o_crear_carpeta(servicio, nombre, id_padre):
    """Navega por la estructura del QNAP"""
    query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    items = res.get('files', [])
    if items: return items[0]['id']
    meta = {'name': nombre, 'parents': [id_padre], 'mimeType': 'application/vnd.google-apps.folder'}
    return servicio.files().create(body=meta, fields='id', supportsAllDrives=True).execute().get('id')

def leer_reporte_consolidado(servicio, id_carpeta_destino, nombre_archivo):
    """Lee el archivo job_YYYY_MM.json de la raíz de configuración"""
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
    """Actualiza o intenta crear el archivo consolidado"""
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
    except Exception as e:
        st.warning(f"Error de cuota en Drive. Guarde el reporte manualmente. Detalle: {e}")
        return False

# --- 3. EL CEREBRO: GEMINI 2.5 FLASH ---
def analizar_con_gemini(servicio, file_id, file_name):
    try:
        # Descarga el PDF
        request = servicio.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        pdf_content = fh.getvalue()

        # Configurar modelo 2.5 Flash
        model = genai.GenerativeModel('gemini-2.0-flash') # 2.0 es la versión estable en 2026
        
        prompt = f"""
        Eres un auditor experto de D&D Asesores en Santiago, República Dominicana.
        Tu tarea es auditar esta póliza de seguro de vehículo.
        
        INSTRUCCIONES:
        1. Extrae: Marca, Modelo, Año y SUB-MODELO (Ej: XLE, LE, SE, Platinum, Limited).
        2. Tasación Real: Estima el valor de mercado actual en RD (basado en una media de 5-8 modelos similares en portales como Supercarros).
        3. Compara con la 'Suma Asegurada' que aparece en el PDF.
        4. Calcula la 'Brecha' (Valor Mercado - Suma Asegurada).
        
        FORMATO DE SALIDA (JSON ESTRICTO):
        {{
            "Archivo": "{file_name}",
            "Marca": "Valor",
            "Modelo": "Valor",
            "Sub_Modelo": "Valor",
            "Anio": "Valor",
            "Suma_Asegurada_RD": 0,
            "Valor_Mercado_RD": 0,
            "Brecha_Infraseguro": 0,
            "Estatus": "Requiere Aumento / Correcto",
            "Fecha_Analisis": "({datetime.datetime.now().strftime('%d/%m/%Y')})"
        }}
        """
        
        response = model.generate_content([
            {'mime_type': 'application/pdf', 'data': pdf_content},
            prompt
        ])
        
        # Limpieza de la respuesta
        raw_text = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(raw_text)
    except Exception as e:
        return {"Archivo": file_name, "Estatus": f"Error IA: {str(e)[:40]}"}

# --- 4. INTERFAZ STREAMLIT ---
st.set_page_config(page_title="D&D Auditoría IA", layout="wide", page_icon="🛡️")
st.title("🛡️ Auditoría Insurtech v6.2")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.sidebar:
    st.header("⚙️ Panel de Control")
    root_id = st.text_input("ID Raíz QNAP", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    tasa_usd = st.number_input("Tasa USD", value=60.15)
    st.divider()
    st.info(f"📍 Santiago, RD\n📅 ({datetime.datetime.now().strftime('%d/%m/%Y')})")

col_a, col_b = st.columns(2)
anio_sel = col_a.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
mes_idx = col_b.selectbox("Mes de Auditoría", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
mes_nombre = MESES_DICT[str(mes_idx)]

nombre_reporte = f"job_{anio_sel}_{str(mes_idx).zfill(2)}.json"
tabs = st.tabs(["🚀 Ejecución IA", "📊 Monitor de Lote", "🏆 Reporte de Mercado"])

# --- TAB 1: EJECUCIÓN ---
with tabs[0]:
    if st.button("🔍 ESCANEAR PÓLIZAS EN QNAP"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner("Sincronizando con NAS..."):
                id_mes_orig = buscar_o_crear_carpeta(servicio, mes_nombre, buscar_o_crear_carpeta(servicio, anio_sel, root_id))
                historial = leer_reporte_consolidado(servicio, ID_CONFIG_DIR, nombre_reporte)
                
                auditados = [r.get('Archivo', r.get('poliza', '')) for r in historial]
                
                res = servicio.files().list(q=f"'{id_mes_orig}' in parents and mimeType='application/pdf' and trashed=false", fields="files(id, name)", supportsAllDrives=True).execute()
                pdfs = res.get('files', [])
                
                pendientes = [f for f in pdfs if f['name'] not in auditados]
                st.session_state['lote_historial'] = historial
                st.session_state['pendientes'] = pendientes
                st.session_state['total_lote'] = len(pdfs)
                st.success(f"Escaneo listo. {len(pendientes)} pólizas nuevas detectadas.")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        if st.button("🚀 INICIAR ANÁLISIS GEMINI 2.5 FLASH"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            status = st.empty()
            lote_actual = st.session_state.get('lote_historial', [])
            
            for i, file in enumerate(st.session_state['pendientes']):
                status.markdown(f"**🧠 Analizando Sub-modelo y Mercado:** `{file['name']}`")
                resultado = analizar_con_gemini(servicio, file['id'], file['name'])
                lote_actual.append(resultado)
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
            
            guardar_reporte_consolidado(servicio, lote_actual, nombre_reporte, ID_CONFIG_DIR)
            st.session_state['lote_historial'] = lote_actual
            st.session_state['pendientes'] = []
            st.success("✅ Lote procesado y guardado.")

# --- TAB 2: MONITOR ---
with tabs[1]:
    if 'total_lote' in st.session_state:
        total = st.session_state['total_lote']
        hechos = len(st.session_state.get('lote_historial', []))
        porc = int((hechos/total)*100) if total > 0 else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Pólizas en QNAP", total)
        c2.metric("Auditadas por IA", hechos)
        c3.metric("Cobertura Lote", f"{porc}%")
        st.progress(porc / 100)
    else:
        st.info("Debe escanear la carpeta primero.")

# --- TAB 3: REPORTE ---
with tabs[2]:
    datos = st.session_state.get('lote_historial', [])
    if datos:
        df = pd.DataFrame(datos)
        st.write("### Análisis de Infraseguro Detectado")
        st.dataframe(df, use_container_width=True)
        
        # Botones de descarga para tu Pixel 10
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar Excel (CSV)", csv_data, nombre_reporte.replace(".json", ".csv"), "text/csv")
        st.download_button("📥 Descargar Base de Datos (JSON)", json.dumps(datos, indent=4), nombre_reporte, "application/json")
    else:
        st.warning("No hay datos para mostrar todavía.")
