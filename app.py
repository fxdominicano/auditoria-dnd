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

# --- 1. CONFIGURACIÓN Y CREDENCIALES ---
ID_CONFIG_DIR = "15OPQmuf0CpD4MxYHFgD6Nv307Fd7POWt"
SCOPES = ['https://www.googleapis.com/auth/drive']

# Configuración de Gemini
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

def obtener_servicio_drive():
    """Establece conexión con Google Drive usando el Token de usuario personal."""
    try:
        if "GOOGLE_USER_TOKEN" not in st.secrets:
            st.error("Falta el secreto 'GOOGLE_USER_TOKEN' en la configuración de Streamlit.")
            return None
            
        info_token = json.loads(st.secrets["GOOGLE_USER_TOKEN"])
        creds = Credentials.from_authorized_user_info(info_token, SCOPES)
        
        # Refrescar el token automáticamente si ha expirado
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error crítico de autenticación: {e}")
        return None

# --- 2. GESTIÓN DE ARCHIVOS ---
def buscar_carpeta(servicio, nombre, id_padre):
    query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    items = res.get('files', [])
    return items[0]['id'] if items else None

def leer_job_file(servicio, nombre_archivo):
    try:
        query = f"name = '{nombre_archivo}' and '{ID_CONFIG_DIR}' in parents and trashed = false"
        res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        items = res.get('files', [])
        if not items: return []
        
        request = servicio.files().get_media(fileId=items[0]['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        
        data = json.loads(fh.getvalue().decode('utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def guardar_job_file(servicio, datos, nombre_archivo):
    try:
        media = MediaInMemoryUpload(json.dumps(datos, indent=4).encode('utf-8'), mimetype='application/json')
        query = f"name = '{nombre_archivo}' and '{ID_CONFIG_DIR}' in parents"
        res = servicio.files().list(q=query, supportsAllDrives=True).execute().get('files', [])
        
        if res:
            servicio.files().update(fileId=res[0]['id'], media_body=media, supportsAllDrives=True).execute()
        else:
            meta = {'name': nombre_archivo, 'parents': [ID_CONFIG_DIR]}
            servicio.files().create(body=meta, media_body=media, supportsAllDrives=True).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar en Drive: {e}")
        return False 

# --- 3. MOTOR IA (EXTRACCIÓN CON GEMINI 2.5 FLASH) ---
def analizar_con_gemini(servicio, file_id, file_name):
    try:
        request = servicio.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        Actúa como un Auditor Senior de Seguros en República Dominicana para D&D Asesores.
        
        CRITERIOS TÉCNICOS:
        1. VEHÍCULOS: Verifica si tiene cobertura de 'Daños Propios' (Seguro Full).
           - Si NO tiene, marca Estatus: "Omitir - Solo Ley".
           - Si ES FULL: Extrae Marca, Modelo, Año y SUB-MODELO (XLE, LE, SE, Platinum, etc). 
             Estima valor de mercado en RD (media de 5-8 vehículos similares).
        2. OTROS RAMOS: Para Incendio, RC, Maquinaria, Fidelidad, extrae Suma Asegurada y Límites. Evalúa coherencia.
        
        RESPONDE ESTRICTAMENTE EN FORMATO JSON:
        {{
            "Archivo": "{file_name}",
            "Ramo": "Vehículos / Incendio / RC / Otros",
            "Detalle_Objeto": "Marca/Modelo/Año o Riesgo principal",
            "Sub_Modelo": "Sólo para vehículos",
            "Suma_Asegurada_RD": 0,
            "Valor_Mercado_o_Limite": 0,
            "Brecha": 0,
            "Estatus": "Requiere Aumento / Correcto / Omitir - Solo Ley",
            "Nota_Auditoria": "Explicación breve",
            "Fecha_Analisis": "{datetime.datetime.now().strftime('%d/%m/%Y')}"
        }}
        """
        response = model.generate_content([{'mime_type': 'application/pdf', 'data': fh.getvalue()}, prompt])
        
        # Extraer JSON de la respuesta
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            return {"Archivo": file_name, "Estatus": "Error: IA no generó JSON válido"}
            
    except Exception as e:
        return {"Archivo": file_name, "Estatus": f"Error IA: {str(e)[:50]}"}

# --- 4. INTERFAZ STREAMLIT ---
st.set_page_config(page_title="D&D Auditoría IA", layout="wide", page_icon="🛡️")
st.title("🛡️ Auditoría Integral v7.5")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.container(border=True):
    st.subheader("📅 Selección de Periodo")
    col1, col2 = st.columns(2)
    anio_sel = col1.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
    mes_idx = col2.selectbox("Mes de Auditoría", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
    
    mes_nombre = MESES_DICT[str(mes_idx)]
    nombre_reporte = f"job_{anio_sel}_{str(mes_idx).zfill(2)}.json"
    st.info(f"📂 Procesando: `{mes_nombre} {anio_sel}` | Reporte: `{nombre_reporte}`")

with st.sidebar:
    st.header("⚙️ Configuración NAS")
    root_id = st.text_input("ID Carpeta Pólizas QNAP", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    st.caption("Asegúrate de que el Token en Secrets sea el de tu cuenta personal.")

tabs = st.tabs(["🚀 Ejecución Batch", "📊 Monitor de Estatus", "🏆 Reporte de Mercado"])

# --- TAB 1: EJECUCIÓN ---
with tabs[0]:
    if st.button("🔍 ESCANEAR CARPETA"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner(f"Escaneando {mes_nombre}..."):
                id_anio = buscar_carpeta(servicio, anio_sel, root_id)
                if not id_anio:
                    st.error(f"❌ La carpeta '{anio_sel}' no existe.")
                    st.stop()
                    
                id_mes = buscar_carpeta(servicio, mes_nombre, id_anio)
                if not id_mes:
                    st.error(f"❌ La carpeta '{mes_nombre}' no existe dentro de {anio_sel}.")
                    st.stop()
                
                historial = leer_job_file(servicio, nombre_reporte)
                auditados = [r.get('Archivo', '') for r in historial if isinstance(r, dict)]
                
                res = servicio.files().list(q=f"'{id_mes}' in parents and mimeType='application/pdf' and trashed=false", 
                                            fields="files(id, name)", supportsAllDrives=True).execute()
                pdfs_nas = res.get('files', [])
                
                st.session_state['lote_historial'] = historial
                st.session_state['pendientes'] = [f for f in pdfs_nas if f['name'] not in auditados]
                st.session_state['total_pdfs'] = len(pdfs_nas)
                st.success(f"✅ {len(st.session_state['pendientes'])} pólizas nuevas detectadas.")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        st.write("### 📄 Vista Previa de la Cola")
        df_p = pd.DataFrame([{"Archivo": f['name']} for f in st.session_state['pendientes']])
        st.dataframe(df_p, use_container_width=True)
        
        if st.button("🚀 INICIAR AUDITORÍA CON GEMINI"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            status_text = st.empty()
            lote_completo = st.session_state['lote_historial']
            
            for i, f in enumerate(st.session_state['pendientes']):
                status_text.markdown(f"**Analizando:** `{f['name']}`")
                resultado = analizar_con_gemini(servicio, f['id'], f['name'])
                
                if "Omitir" not in str(resultado.get('Estatus', '')):
                    lote_completo.append(resultado)
                
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
            
            if guardar_job_file(servicio, lote_completo, nombre_reporte):
                st.session_state['lote_historial'] = lote_completo
                st.session_state['pendientes'] = []
                st.success("✅ Auditoría guardada en Drive.")
            else:
                st.error("⚠️ Error al guardar. Descarga el CSV manualmente.")

# --- TAB 2: MONITOR ---
with tabs[1]:
    if 'total_pdfs' in st.session_state:
        total = st.session_state['total_pdfs']
        hechos = len(st.session_state.get('lote_historial', []))
        prog_v = min(1.0, hechos / total) if total > 0 else 0.0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total en NAS", total)
        c2.metric("Auditados", hechos)
        c3.metric("Cobertura", f"{int(prog_v * 100)}%")
        st.progress(prog_v)

# --- TAB 3: REPORTE ---
with tabs[2]:
    datos = st.session_state.get('lote_historial', [])
    if datos:
        df = pd.DataFrame(datos)
        st.write(f"### Análisis Técnico: {mes_nombre}")
        st.dataframe(df, use_container_width=True)
        
        c1, c2 = st.columns(2)
        c1.download_button("📥 Descargar Reporte CSV", df.to_csv(index=False), f"{nombre_reporte}.csv", "text/csv")
        c2.download_button("📥 Descargar JSON Original", json.dumps(datos, indent=4, ensure_ascii=False), nombre_reporte, "application/json")
    else:
        st.warning("Sin datos para este periodo.")
