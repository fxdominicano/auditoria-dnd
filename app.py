import streamlit as st
import pandas as pd
import time
import datetime
import json
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaInMemoryUpload

# --- 1. CONFIGURACIÓN Y CREDENCIALES ---
ID_CONFIG_DIR = "15OPQmuf0CpD4MxYHFgD6Nv307Fd7POWt"

def obtener_servicio_drive():
    try:
        info_llave = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = service_account.Credentials.from_service_account_info(info_llave)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error de acceso a Drive: {e}")
        return None

# --- 2. FUNCIONES DE CARPETAS Y ARCHIVOS ---
def buscar_o_crear_carpeta(servicio, nombre, id_padre):
    query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)").execute()
    items = res.get('files', [])
    if items:
        return items[0]['id']
    else:
        meta = {'name': nombre, 'parents': [id_padre], 'mimeType': 'application/vnd.google-apps.folder'}
        folder = servicio.files().create(body=meta, fields='id').execute()
        return folder.get('id')

def archivo_ya_auditado(servicio, nombre_pdf, id_carpeta_mes):
    """Verifica si ya existe un .json con el nombre de la póliza"""
    nombre_json = nombre_pdf.replace(".pdf", ".json")
    query = f"name = '{nombre_json}' and '{id_carpeta_mes}' in parents and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)").execute()
    return len(res.get('files', [])) > 0

def guardar_json_auditado(servicio, datos, nombre_pdf, id_carpeta_mes):
    nombre_json = nombre_pdf.replace(".pdf", ".json")
    media = MediaInMemoryUpload(json.dumps(datos, indent=4).encode('utf-8'), mimetype='application/json')
    meta = {'name': nombre_json, 'parents': [id_carpeta_mes]}
    servicio.files().create(body=meta, media_body=media).execute()

# --- 3. INTERFAZ ---
st.set_page_config(page_title="D&D Asesores - Auditoría Inteligente", layout="wide")
st.title("🛡️ Auditoría v4.8: Control de Duplicados")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.sidebar:
    st.header("⚙️ Configuración")
    root_id = st.text_input("ID Carpeta Pólizas (QNAP)", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    tasa_usd = st.number_input("Tasa USD", value=60.15)
    st.info("Estatus: Resiliente")

c1, c2 = st.columns(2)
anio_sel = c1.selectbox("Año", ["2025", "2026", "2027"], index=1)
mes_idx = c2.selectbox("Mes", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
mes_nombre = MESES_DICT[str(mes_idx)]

tabs = st.tabs(["🚀 Auditoría", "📊 Monitor", "🏆 Reporte"])

with tabs[0]:
    if st.button("🔍 ESCANEAR PÓLIZAS"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            # 1. Navegar a carpetas de origen (QNAP)
            id_anio = buscar_o_crear_carpeta(servicio, anio_sel, root_id) # Uso buscar_o_crear por seguridad
            id_mes = buscar_o_crear_carpeta(servicio, mes_nombre, id_anio)
            
            # 2. Navegar/Crear carpetas de destino (Config_Auditoria_DyD)
            id_dest_anio = buscar_o_crear_carpeta(servicio, anio_sel, ID_CONFIG_DIR)
            id_dest_mes = buscar_o_crear_carpeta(servicio, mes_nombre, id_dest_anio)
            
            # 3. Listar archivos
            query = f"'{id_mes}' in parents and mimeType = 'application/pdf' and trashed = false"
            res = servicio.files().list(q=query, fields="files(id, name)").execute()
            lista_raw = res.get('files', [])
            
            # 4. Filtrar solo los que NO han sido auditados
            pendientes = []
            for f in lista_raw:
                if not archivo_ya_auditado(servicio, f['name'], id_dest_mes):
                    pendientes.append(f)
            
            st.session_state['pendientes'] = pendientes
            st.session_state['id_destino'] = id_dest_mes
            st.success(f"Escaneo listo. Total: {len(lista_raw)} | Pendientes: {len(pendientes)}")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        st.write("### Pólizas nuevas por procesar")
        st.dataframe(pd.DataFrame(st.session_state['pendientes'])[['name']])
        
        if st.button("🚀 PROCESAR PENDIENTES"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            status = st.empty()
            
            for i, file in enumerate(st.session_state['pendientes']):
                status.markdown(f"**Analizando:** `{file['name']}`")
                
                # --- Simulación de Análisis de IA ---
                time.sleep(1)
                resultado_ficticio = {"poliza": file['name'], "status": "Auditado", "fecha": str(datetime.datetime.now())}
                # ------------------------------------
                
                # Guardar el JSON en la carpeta correspondiente
                guardar_json_auditado(servicio, resultado_ficticio, file['name'], st.session_state['id_destino'])
                
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
            
            st.success("Lote completado. Todos los reportes guardados en Config_Auditoria_DyD.")
            st.session_state['pendientes'] = [] # Limpiar lista tras éxito
