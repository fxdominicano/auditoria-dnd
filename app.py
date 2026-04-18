import streamlit as st
import pandas as pd
import time
import datetime
import json
import io
import re
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload
import google.generativeai as genai

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
ID_CONFIG_DIR = "15OPQmuf0CpD4MxYHFgD6Nv307Fd7POWt"
SCOPES = ['https://www.googleapis.com/auth/drive']

# Configuración de Gemini 2.5 Flash
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

def obtener_servicio_drive():
    try:
        info_llave = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = service_account.Credentials.from_service_account_info(info_llave).with_scopes(SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception:
        return None

# --- 2. FUNCIONES DE DRIVE Y ARCHIVOS ---
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
        return [data] if isinstance(data, dict) else (data if isinstance(data, list) else [])
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
        return False
    except Exception: return False

# --- 3. MOTOR DE INTELIGENCIA ARTIFICIAL (GEMINI 2.5 FLASH) ---
def analizar_poliza_gemini(servicio, file_id, file_name):
    try:
        # 1. Descargar el PDF en memoria
        request = servicio.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        pdf_bytes = fh.getvalue()

        # 2. Configurar el modelo
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # 3. Prompt de extracción y tasación
        prompt = f"""
        Actúa como un experto ajustador de seguros de vehículos en República Dominicana.
        Lee detenidamente esta póliza de seguros. Extrae la información y realiza un cálculo de mercado.
        Considera el mercado local dominicano para estimar el valor actual basado en una media de 5 a 8 vehículos similares.
        
        Devuelve el resultado ESTRICTAMENTE en este formato JSON, sin texto adicional:
        {{
            "Archivo": "{file_name}",
            "Fecha_Auditoria": "({datetime.datetime.now().strftime('%d/%m/%Y')})",
            "Marca": "Extraer marca",
            "Modelo": "Extraer modelo",
            "Sub_Modelo": "Extraer sub-modelo si existe (Ej: XLE, SE, LE, Limited. Si no hay, pon 'N/A')",
            "Anio": "Extraer año de fabricación",
            "Suma_Asegurada_Actual_RD": "Número entero, sin comas ni símbolos",
            "Valor_Mercado_Estimado_RD": "Número entero estimando la media actual del vehículo en RD",
            "Brecha_Infraseguro_RD": "Calcula: Valor_Mercado_Estimado_RD - Suma_Asegurada_Actual_RD",
            "Estatus_Auditoria": "Si la brecha es mayor a 0 pon 'Requiere Aumento', de lo contrario 'Correcto'"
        }}
        """
        
        # 4. Enviar a Gemini
        response = model.generate_content([
            {'mime_type': 'application/pdf', 'data': pdf_bytes},
            prompt
        ])
        
        # 5. Limpiar y parsear el JSON
        texto_limpio = response.text.strip()
        if texto_limpio.startswith("```json"):
            texto_limpio = texto_limpio[7:-3] # Quitar etiquetas markdown
        elif texto_limpio.startswith("```"):
            texto_limpio = texto_limpio[3:-3]
            
        return json.loads(texto_limpio)
        
    except Exception as e:
        # Si falla, no rompe la cadena, devuelve un error controlado
        return {
            "Archivo": file_name,
            "Fecha_Auditoria": f"({datetime.datetime.now().strftime('%d/%m/%Y')})",
            "Estatus_Auditoria": f"Error en lectura de IA: {str(e)[:50]}"
        }

# --- 4. INTERFAZ ---
st.set_page_config(page_title="D&D Asesores IA", layout="wide", page_icon="🛡️")
st.title("🛡️ Motor de Auditoría v6.0 (Gemini 2.5 Flash)")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.sidebar:
    st.header("⚙️ Configuración")
    root_id = st.text_input("ID Carpeta Pólizas", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")
    tasa_usd = st.number_input("Tasa USD", value=60.15)
    st.info(f"📍 Santiago, RD\n📅 ({datetime.datetime.now().strftime('%d/%m/%Y')})")

c1, c2 = st.columns(2)
anio_sel = c1.selectbox("Año Fiscal", ["2025", "2026", "2027"], index=1)
mes_idx = c2.selectbox("Mes", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
mes_nombre = MESES_DICT[str(mes_idx)]

nombre_reporte = f"job_{anio_sel}_{str(mes_idx).zfill(2)}.json"
tabs = st.tabs(["🚀 Ejecución IA", "📊 Monitor", "🏆 Reporte Final"])

# --- TAB 1: LANZAMIENTO ---
with tabs[0]:
    if st.button("🔍 ESCANEAR PÓLIZAS PARA IA"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner("Analizando..."):
                id_mes_orig = buscar_o_crear_carpeta(servicio, mes_nombre, buscar_o_crear_carpeta(servicio, anio_sel, root_id))
                historial = leer_reporte_consolidado(servicio, ID_CONFIG_DIR, nombre_reporte)
                
                nombres_auditados = [r.get('Archivo', '') for r in historial if isinstance(r, dict)]
                
                res = servicio.files().list(q=f"'{id_mes_orig}' in parents and mimeType='application/pdf' and trashed=false", fields="files(id, name)", supportsAllDrives=True).execute()
                pdf_en_drive = res.get('files', [])
                
                pendientes = [f for f in pdf_en_drive if f['name'] not in nombres_auditados]
                
                st.session_state['lote_historial'] = historial
                st.session_state['pendientes'] = pendientes
                st.session_state['total_pdfs'] = len(pdf_en_drive)
                st.success(f"Listo para procesar con IA. {len(pendientes)} pólizas pendientes.")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        if st.button("🚀 INICIAR LECTURA CON GEMINI 2.5 FLASH"):
            servicio = obtener_servicio_drive()
            progreso = st.progress(0)
            status_text = st.empty()
            resultados_actuales = st.session_state.get('lote_historial', [])
            
            for i, file in enumerate(st.session_state['pendientes']):
                status_text.markdown(f"**🧠 Extrayendo datos y calculando valor de mercado:** `{file['name']}`")
                
                # --- LLAMADA REAL A GEMINI ---
                resultado_ia = analizar_poliza_gemini(servicio, file['id'], file['name'])
                resultados_actuales.append(resultado_ia)
                # -----------------------------
                
                progreso.progress((i + 1) / len(st.session_state['pendientes']))
            
            exito = guardar_reporte_consolidado(servicio, resultados_actuales, nombre_reporte, ID_CONFIG_DIR)
            st.session_state['lote_historial'] = resultados_actuales
            st.session_state['pendientes'] = []
            
            if exito: st.success("🎉 Datos guardados. Revisa la pestaña de Reporte Final para ver el análisis.")
            else: st.warning("⚠️ Descargue el archivo en la pestaña Reporte y súbalo a Drive.")

# --- TAB 2: MONITOR ---
with tabs[1]:
    st.subheader(f"Estatus del Lote: `{nombre_reporte}`")
    total = st.session_state.get('total_pdfs', 0)
    auditados = len(st.session_state.get('lote_historial', []))
    if total > 0:
        porcentaje = int((auditados / total) * 100)
        m1, m2, m3 = st.columns(3)
        m1.metric("Total en QNAP", total)
        m2.metric("Auditados", auditados)
        m3.metric("Progreso", f"{porcentaje}%")
        st.progress(porcentaje / 100)
    else:
        st.info("Escanee primero en la pestaña de Ejecución.")

# --- TAB 3: REPORTE FINAL ---
with tabs[2]:
    datos_reporte = st.session_state.get('lote_historial', [])
    if isinstance(datos_reporte, dict): datos_reporte = [datos_reporte]
    
    if datos_reporte:
        df = pd.DataFrame(datos_reporte)
        st.dataframe(df, use_container_width=True)
        c1, c2 = st.columns(2)
        c1.download_button("📥 Descargar JSON", json.dumps(datos_reporte, indent=4), nombre_reporte, "application/json")
        c2.download_button("📥 Descargar Excel de Infraseguro (CSV)", df.to_csv(index=False), nombre_reporte.replace(".json", ".csv"), "text/csv")
    else:
        st.warning("No hay datos auditados para mostrar.")
