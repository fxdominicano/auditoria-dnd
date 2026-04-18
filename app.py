import streamlit as st
import pandas as pd
import time
import datetime
import json
import io
import re  # <--- IMPORTANTE: Librería para extraer el JSON de forma segura
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload

# --- 1. CONFIGURACIÓN Y CREDENCIALES ---
ID_CONFIG_DIR = "15OPQmuf0CpD4MxYHFgD6Nv307Fd7POWt"
SCOPES = ['[https://www.googleapis.com/auth/drive](https://www.googleapis.com/auth/drive)']

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

def obtener_servicio_drive():
    try:
        info_llave = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = service_account.Credentials.from_service_account_info(info_llave).with_scopes(SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception: return None

# --- 2. GESTIÓN DE ARCHIVOS (MODO LECTURA ESTRICTA) ---
def buscar_carpeta(servicio, nombre, id_padre):
    """SOLO BUSCA. Ya no intenta crear para evitar el Error 403 de cuota."""
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
        while not done: _, done = downloader.next_chunk()
        data = json.loads(fh.getvalue().decode('utf-8'))
        return data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
    except Exception: return []

def guardar_job_file(servicio, datos, nombre_archivo):
    try:
        media = MediaInMemoryUpload(json.dumps(datos, indent=4).encode('utf-8'), mimetype='application/json')
        query = f"name = '{nombre_archivo}' and '{ID_CONFIG_DIR}' in parents"
        res = servicio.files().list(q=query, supportsAllDrives=True).execute().get('files', [])
        if res:
            servicio.files().update(fileId=res[0]['id'], media_body=media, supportsAllDrives=True).execute()
            return True
        else:
            meta = {'name': nombre_archivo, 'parents': [ID_CONFIG_DIR]}
            servicio.files().create(body=meta, media_body=media, supportsAllDrives=True).execute()
            return True
    except Exception as e: 
        print(f"Error de cuota Drive: {e}") # Queda en el log del servidor
        return False # AHORA SÍ PASA EL ERROR A LA INTERFAZ

# --- 3. MOTOR IA (EXTRACCIÓN BLINDADA CON REGEX) ---
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
        
        CRITERIOS:
        1. VEHÍCULOS: Verifica si tiene cobertura de 'Daños Propios' (Seguro Full).
           - Si NO tiene, marca Estatus: "Omitir - Solo Ley".
           - Si ES FULL: Extrae Marca, Modelo, Año y SUB-MODELO (XLE, LE, SE, Platinum, etc). 
             Estima valor de mercado en RD (media 5-8 similares).
        2. OTROS RAMOS: Para Incendio, RC, Maquinaria, Fidelidad, extrae Suma Asegurada y Límites. Evalúa coherencia.
        
        RESPONDE ESTRICTAMENTE EN JSON:
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
            "Fecha_Analisis": "({datetime.datetime.now().strftime('%d/%m/%Y')})"
        }}
        """
        response = model.generate_content([{'mime_type': 'application/pdf', 'data': fh.getvalue()}, prompt])
        
        # BLINDAJE REGEX: Busca el primer corchete/llave y extrae solo lo que parezca JSON
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            return {"Archivo": file_name, "Estatus": "Error: IA no devolvió JSON reconocible"}
            
    except Exception as e:
        return {"Archivo": file_name, "Estatus": f"Error IA: {str(e)[:30]}"}

# --- 4. INTERFAZ STREAMLIT ---
st.set_page_config(page_title="D&D Auditoría IA", layout="wide", page_icon="🛡️")
st.title("🛡️ Auditoría Integral v7.1")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.container(border=True):
    st.subheader("📅 Selección de Periodo")
    col1, col2 = st.columns(2)
    anio_sel = col1.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
    mes_idx = col2.selectbox("Mes de Auditoría", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
    
    mes_nombre = MESES_DICT[str(mes_idx)]
    nombre_reporte = f"job_{anio_sel}_{str(mes_idx).zfill(2)}.json"
    st.info(f"📂 Procesando: `{mes_nombre} {anio_sel}` | Archivo: `{nombre_reporte}`")

with st.sidebar:
    st.header("⚙️ Configuración NAS")
    root_id = st.text_input("ID Carpeta Pólizas QNAP", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")

tabs = st.tabs(["🚀 Ejecución Batch", "📊 Monitor de Estatus", "🏆 Reporte de Mercado"])

# --- TAB 1: EJECUCIÓN ---
with tabs[0]:
    if st.button("🔍 ESCANEAR CARPETA"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner(f"Escaneando {mes_nombre}..."):
                # BLINDAJE DE NAVEGACIÓN
                id_anio = buscar_carpeta(servicio, anio_sel, root_id)
                if not id_anio:
                    st.error(f"❌ La carpeta del año '{anio_sel}' no existe en tu QNAP.")
                    st.stop()
                    
                id_mes = buscar_carpeta(servicio, mes_nombre, id_anio)
                if not id_mes:
                    st.error(f"❌ La carpeta del mes '{mes_nombre}' no existe dentro del año {anio_sel}.")
                    st.stop()
                
                historial = leer_job_file(servicio, nombre_reporte)
                auditados = [r.get('Archivo', '') for r in historial if isinstance(r, dict)]
                
                res = servicio.files().list(q=f"'{id_mes}' in parents and mimeType='application/pdf' and trashed=false", 
                                            fields="files(id, name)", supportsAllDrives=True).execute()
                pdfs_nas = res.get('files', [])
                
                st.session_state['lote_historial'] = historial
                st.session_state['pendientes'] = [f for f in pdfs_nas if f['name'] not in auditados]
                st.session_state['total_pdfs'] = len(pdfs_nas)
                st.success(f"Detección: {len(st.session_state['pendientes'])} pólizas nuevas pendientes de auditar.")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        if st.button("🚀 INICIAR AUDITORÍA POR LOTE"):
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
            
            # BLINDAJE DE GUARDADO
            guardado_exitoso = guardar_job_file(servicio, lote_completo, nombre_reporte)
            st.session_state['lote_historial'] = lote_completo
            st.session_state['pendientes'] = []
            
            if guardado_exitoso:
                st.success(f"✅ Batch finalizado. Reporte guardado correctamente en Drive.")
            else:
                st.error("⚠️ Drive rechazó el guardado (Posible falta de cuota/archivo no existe). ¡Ve a la pestaña Reporte y descarga el CSV AHORA MISMO para no perder los datos!")

# --- TAB 2: MONITOR ---
with tabs[1]:
    if 'total_pdfs' in st.session_state:
        total = st.session_state['total_pdfs']
        hechos = len(st.session_state.get('lote_historial', []))
        prog_v = min(1.0, hechos / total) if total > 0 else 0.0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total en NAS", total)
        c2.metric("Auditados (JOB)", hechos)
        c3.metric("Cobertura", f"{int(prog_v * 100)}%")
        st.progress(prog_v)
    else:
        st.info("Escanée la carpeta en la pestaña 'Ejecución' para ver el estatus.")

# --- TAB 3: REPORTE ---
with tabs[2]:
    datos = st.session_state.get('lote_historial', [])
    if datos:
        df = pd.DataFrame(datos)
        st.write(f"### Análisis Técnico: {mes_nombre} {anio_sel}")
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Descargar Reporte CSV", df.to_csv(index=False), f"{nombre_reporte}.csv", "text/csv")
    else:
        st.warning("No hay datos auditados para mostrar en este periodo.")
