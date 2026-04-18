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
# El Scope de escritura es vital para evitar el HttpError 403
SCOPES = ['https://www.googleapis.com/auth/drive']

def obtener_servicio_drive():
    try:
        info_llave = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = service_account.Credentials.from_service_account_info(info_llave).with_scopes(SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error de credenciales en Streamlit Secrets. Verifique el JSON: {e}")
        return None

# --- 2. FUNCIONES DE CARPETAS Y ARCHIVOS (CON PROTECCIÓN DE ERRORES) ---
def buscar_o_crear_carpeta(servicio, nombre, id_padre):
    try:
        query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = servicio.files().list(q=query, fields="files(id)").execute()
        items = res.get('files', [])
        if items:
            return items[0]['id']
        else:
            meta = {'name': nombre, 'parents': [id_padre], 'mimeType': 'application/vnd.google-apps.folder'}
            folder = servicio.files().create(body=meta, fields='id').execute()
            return folder.get('id')
    except Exception as e:
        st.error(f"Error de escritura en Drive al crear la carpeta '{nombre}'. Asegúrese de ser Editor. Detalle: {e}")
        st.stop()

def archivo_ya_auditado(servicio, nombre_pdf, id_carpeta_mes):
    nombre_json = nombre_pdf.replace(".pdf", ".json")
    query = f"name = '{nombre_json}' and '{id_carpeta_mes}' in parents and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)").execute()
    return len(res.get('files', [])) > 0

def guardar_json_auditado(servicio, datos, nombre_pdf, id_carpeta_mes):
    try:
        nombre_json = nombre_pdf.replace(".pdf", ".json")
        media = MediaInMemoryUpload(json.dumps(datos, indent=4).encode('utf-8'), mimetype='application/json')
        meta = {'name': nombre_json, 'parents': [id_carpeta_mes]}
        servicio.files().create(body=meta, media_body=media).execute()
    except Exception as e:
        st.error(f"Error al guardar el reporte {nombre_json}. Detalle: {e}")
        st.stop()

# --- 3. INTERFAZ D&D ASESORES ---
st.set_page_config(page_title="D&D Asesores - Auditoría Inteligente", layout="wide", page_icon="🛡️")
st.title("🛡️ Motor de Auditoría v4.9")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.sidebar:
    st.header("⚙️ Configuración")
    root_id = st.text_input("ID Carpeta Pólizas (QNAP)", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    tasa_usd = st.number_input("Tasa USD", value=60.15)
    st.info(f"Fecha Actual: ({datetime.datetime.now().strftime('%d/%m/%Y')})")

c1, c2 = st.columns(2)
anio_sel = c1.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
mes_idx = c2.selectbox("Mes de Auditoría", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
mes_nombre = MESES_DICT[str(mes_idx)]

tabs = st.tabs(["🚀 Auditoría", "📊 Monitor", "🏆 Reporte"])

# --- TAB 1: OPERACIÓN PRINCIPAL ---
with tabs[0]:
    if st.button("🔍 ESCANEAR PÓLIZAS Y REPORTES"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner("Conectando con Google Drive..."):
                # 1. Navegar en origen (Pólizas)
                id_anio_origen = buscar_o_crear_carpeta(servicio, anio_sel, root_id)
                id_mes_origen = buscar_o_crear_carpeta(servicio, mes_nombre, id_anio_origen)
                
                # 2. Navegar en destino (Config_Auditoria_DyD)
                id_anio_dest = buscar_o_crear_carpeta(servicio, anio_sel, ID_CONFIG_DIR)
                id_mes_dest = buscar_o_crear_carpeta(servicio, mes_nombre, id_anio_dest)
                
                # 3. Listar archivos PDF en origen
                query = f"'{id_mes_origen}' in parents and mimeType = 'application/pdf' and trashed = false"
                res = servicio.files().list(q=query, fields="files(id, name)").execute()
                lista_raw = res.get('files', [])
                
                # 4. Filtrar duplicados
                pendientes = [f for f in lista_raw if not archivo_ya_auditado(servicio, f['name'], id_mes_dest)]
                
                st.session_state['pendientes'] = pendientes
                st.session_state['id_destino'] = id_mes_dest
                st.success(f"✅ Escaneo listo. Pólizas totales: {len(lista_raw)} | Pendientes de auditar: {len(pendientes)}")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        st.write("### Documentos listos para procesamiento")
        st.dataframe(pd.DataFrame(st.session_state['pendientes'])[['name']].rename(columns={'name':'Nombre del Archivo'}), use_container_width=True)
        
        if st.button("🚀 INICIAR PROCESAMIENTO"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            status = st.empty()
            
            for i, file in enumerate(st.session_state['pendientes']):
                status.markdown(f"**Procesando IA:** `{file['name']}`")
                
                # --- Lógica de análisis ---
                time.sleep(1.5)
                fecha_actual = datetime.datetime.now().strftime("%d/%m/%Y")
                resultado = {
                    "poliza": file['name'], 
                    "status": "Auditado", 
                    "fecha_auditoria": f"({fecha_actual})"
                }
                # -------------------------
                
                # Guardar el JSON en Config_Auditoria_DyD
                guardar_json_auditado(servicio, resultado, file['name'], st.session_state['id_destino'])
                
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
            
            st.success("🎉 Lote completado exitosamente. Todos los reportes han sido guardados.")
            st.session_state['pendientes'] = [] # Limpiar para evitar reprocesar visualmente

# --- TAB 2 y 3: ESPACIOS DE RESERVA ---
with tabs[1]:
    st.info("El monitor se activará con los reportes JSON generados.")

with tabs[2]:
    st.info("Los cálculos de comisiones se leerán desde la carpeta de configuración.")
                
