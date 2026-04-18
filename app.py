import streamlit as st
import pandas as pd
import time
import datetime
import json
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. CONEXIÓN REAL ---
def obtener_servicio_drive():
    try:
        info_llave = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = service_account.Credentials.from_service_account_info(info_llave)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error de acceso: Revise los Secrets. {e}")
        return None

def buscar_id(servicio, nombre, id_padre):
    query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)").execute()
    items = res.get('files', [])
    return items[0]['id'] if items else None

def listar_pdfs_reales(servicio, id_carpeta):
    query = f"'{id_carpeta}' in parents and mimeType = 'application/pdf' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id, name)").execute()
    return res.get('files', [])

# --- 2. CONFIGURACIÓN ---
st.set_page_config(page_title="D&D Asesores - Auditoría", layout="wide")
st.title("🛡️ Motor de Auditoría Inteligente")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.sidebar:
    st.header("⚙️ Configuración")
    root_id = st.text_input("ID Carpeta Raíz", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    tasa_usd = st.number_input("Tasa USD", value=60.15)
    st.divider()
    st.info("Santiago, RD")

col1, col2 = st.columns(2)
anio = col1.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
mes_idx = col2.selectbox("Mes de Auditoría", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
mes_nombre = MESES_DICT[str(mes_idx)]

tabs = st.tabs(["🚀 Lanzar Auditoría", "📊 Monitor de Lotes", "🏆 Reporte e Ingresos"])

# --- TAB 1: LANZAMIENTO REAL ---
with tabs[0]:
    if st.button("🔍 ESCANEAR CARPETA REAL"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            id_anio = buscar_id(servicio, anio, root_id)
            if id_anio:
                id_mes = buscar_id(servicio, mes_nombre, id_anio)
                if id_mes:
                    archivos = listar_pdfs_reales(servicio, id_mes)
                    st.session_state['lote_real'] = archivos
                    st.success(f"Conexión exitosa: {len(archivos)} pólizas encontradas.")
                else: st.error(f"No existe carpeta: {mes_nombre}")
            else: st.error(f"No existe carpeta: {anio}")

    if 'lote_real' in st.session_state and st.session_state['lote_real']:
        st.write("### Pólizas detectadas en Drive")
        st.dataframe(pd.DataFrame(st.session_state['lote_real'])[['name']], use_container_width=True)
        
        if st.button("🚀 INICIAR PROCESAMIENTO BATCH"):
            progreso = st.progress(0)
            status = st.empty()
            for i, file in enumerate(st.session_state['lote_real']):
                status.markdown(f"**Procesando:** `{file['name']}`")
                time.sleep(1) # Aquí va la lógica de Gemini
                progreso.progress((i + 1) / len(st.session_state['lote_real']))
            st.success("Auditoría finalizada.")

# --- TAB 2: MONITOR REAL (SIN EJEMPLOS) ---
with tabs[1]:
    st.subheader(f"Estatus para {mes_nombre} {anio}")
    conteo = len(st.session_state.get('lote_real', []))
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Estado", "ACTIVO" if conteo > 0 else "INACTIVO")
    m2.metric("Pólizas en Carpeta", conteo)
    m3.metric("Última Actualización", datetime.datetime.now().strftime("%H:%M"))

    if conteo == 0:
        st.info("No hay datos reales. Use el botón de 'Escanear' en la primera pestaña.")

# --- TAB 3: REPORTE REAL ---
with tabs[2]:
    if 'lote_real' in st.session_state and len(st.session_state['lote_real']) > 0:
        st.write("Aquí se mostrarán los cálculos de comisión para las pólizas detectadas.")
    else:
        st.warning("Escanee una carpeta con archivos para generar el reporte.")
