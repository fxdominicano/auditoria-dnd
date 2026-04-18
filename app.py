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

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

def obtener_servicio_drive():
    try:
        info_llave = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = service_account.Credentials.from_service_account_info(info_llave).with_scopes(SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception: return None

# --- 2. GESTIÓN DE DRIVE ---
def buscar_o_crear_carpeta(servicio, nombre, id_padre):
    query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    items = res.get('files', [])
    return items[0]['id'] if items else None

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

# --- 3. PROCESAMIENTO POR BATCH (GEMINI 2.5 FLASH) ---
def procesar_lote_ia(servicio, lista_archivos):
    """Procesa un grupo de archivos en una sola llamada a Gemini"""
    model = genai.GenerativeModel('gemini-2.5-flash')
    batch_resultados = []
    
    for arq in lista_archivos:
        try:
            # Descargar PDF
            request = servicio.files().get_media(fileId=arq['id'])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done: _, done = downloader.next_chunk()
            
            prompt = f"""
            Auditoría D&D Asesores (Santiago, RD). Analiza esta póliza:
            1. CLASIFICACIÓN: Si es Vehículo, verifica si es "Seguro Full" (Daños Propios). Si es Ley/RC, pon Estatus: "Omitir".
            2. VEHÍCULOS FULL: Marca, Modelo, Año, Sub-Modelo (XLE, LE, SE, etc). Valor mercado RD (media 5-8 similares).
            3. OTROS RAMOS: Para Incendio, RC, Maquinaria, Fidelidad, extrae Sumas y Límites. Evalúa consistencia.
            
            RESPUESTA JSON:
            {{
                "Archivo": "{arq['name']}",
                "Ramo": "...", "Detalle": "...", "Suma_RD": 0, "Mercado_RD": 0, "Brecha": 0,
                "Estatus": "Requiere Aumento / Correcto / Omitir", "Nota": "..."
            }}
            """
            
            response = model.generate_content([{'mime_type': 'application/pdf', 'data': fh.getvalue()}, prompt])
            res_json = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
            batch_resultados.append(res_json)
        except Exception as e:
            batch_resultados.append({"Archivo": arq['name'], "Estatus": f"Error IA: {str(e)[:20]}"})
            
    return batch_resultados

# --- 4. INTERFAZ ---
st.set_page_config(page_title="D&D Batch Audit", layout="wide")
st.title("🛡️ Auditoría v6.7: Batch Processing")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.sidebar:
    st.header("⚙️ Configuración")
    root_id = st.text_input("ID Raíz QNAP", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    anio_sel = st.selectbox("Año", ["2025", "2026", "2027"], index=1)
    mes_idx = st.selectbox("Mes", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])

nombre_reporte = f"job_{anio_sel}_{str(mes_idx).zfill(2)}.json"
tabs = st.tabs(["🚀 Ejecución Batch", "📊 Dashboard", "🏆 Reporte"])

with tabs[0]:
    if st.button("🔍 ESCANEAR PENDIENTES"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner("Sincronizando..."):
                id_mes = buscar_o_crear_carpeta(servicio, MESES_DICT[str(mes_idx)], buscar_o_crear_carpeta(servicio, anio_sel, root_id))
                historial = leer_reporte_consolidado(servicio, ID_CONFIG_DIR, nombre_reporte)
                auditados = [r.get('Archivo', '') for r in historial]
                res = servicio.files().list(q=f"'{id_mes}' in parents and mimeType='application/pdf'", fields="files(id, name)", supportsAllDrives=True).execute()
                pdfs = res.get('files', [])
                st.session_state['pendientes'] = [f for f in pdfs if f['name'] not in auditados]
                st.session_state['lote_historial'] = historial
                st.session_state['total_lote'] = len(pdfs)
                st.success(f"Pendientes: {len(st.session_state['pendientes'])} pólizas.")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        tamano_batch = st.slider("Tamaño del Batch (recomendado 5)", 1, 10, 5)
        if st.button(f"🚀 PROCESAR EN BLOQUES DE {tamano_batch}"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            lista_final = st.session_state['lote_historial']
            
            # Procesamiento por Chunks (Batch)
            pendientes = st.session_state['pendientes']
            for i in range(0, len(pendientes), tamano_batch):
                batch = pendientes[i : i + tamano_batch]
                st.write(f"Procesando bloque {i//tamano_batch + 1}...")
                
                resultados_batch = procesar_lote_ia(servicio, batch)
                
                # Filtrar los que se deben omitir
                for r in resultados_batch:
                    if isinstance(r, dict) and "Omitir" not in r.get('Estatus', ''):
                        lista_final.append(r)
                
                progreso.progress(min(1.0, (i + tamano_batch) / len(pendientes)))
                
                # Guardado intermedio por seguridad
                media = MediaInMemoryUpload(json.dumps(lista_final, indent=4).encode('utf-8'), mimetype='application/json')
                query = f"name = '{nombre_reporte}' and '{ID_CONFIG_DIR}' in parents"
                check = servicio.files().list(q=query, supportsAllDrives=True).execute().get('files', [])
                if check:
                    servicio.files().update(fileId=check[0]['id'], media_body=media, supportsAllDrives=True).execute()
                else:
                    meta = {'name': nombre_reporte, 'parents': [ID_CONFIG_DIR]}
                    servicio.files().create(body=meta, media_body=media, supportsAllDrives=True).execute()

            st.session_state['pendientes'] = []
            st.session_state['lote_historial'] = lista_final
            st.success("✅ Auditoría por Batch finalizada.")

with tabs[1]:
    if 'total_lote' in st.session_state:
        total = st.session_state['total_lote']
        auditados = len(st.session_state.get('lote_historial', []))
        st.metric("Progreso del Mes", f"{auditados} de {total}")
        st.progress(min(1.0, auditados / total) if total > 0 else 0)

with tabs[2]:
    if 'lote_historial' in st.session_state and st.session_state['lote_historial']:
        df = pd.DataFrame(st.session_state['lote_historial'])
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Excel CSV", df.to_csv(index=False).encode('utf-8'), f"{nombre_reporte}.csv", "text/csv")
