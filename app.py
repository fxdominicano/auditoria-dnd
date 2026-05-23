import streamlit as st
import pandas as pd
import time
import datetime
import json
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
# SDK moderno oficial de Google GenAI
from google import genai
from google.genai import types
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload

# --- 1. CONFIGURACIÓN GLOBAL ---
ID_CONFIG_DIR = "15OPQmuf0CpD4MxYHFgD6Nv307Fd7POWt"
SCOPES = ['https://www.googleapis.com/auth/drive']

# Inicialización segura del cliente Gemini 3.5 Flash
client_gemini = None
if "GEMINI_API_KEY" in st.secrets:
    client_gemini = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

def obtener_servicio_drive():
    try:
        if "GOOGLE_USER_TOKEN" not in st.secrets:
            st.error("⚠️ Configura 'GOOGLE_USER_TOKEN' en los Secrets.")
            return None
        info_token = json.loads(st.secrets["GOOGLE_USER_TOKEN"])
        creds = Credentials.from_authorized_user_info(info_token, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error crítico de conexión con Google Drive: {e}")
        return None

# --- 2. GESTIÓN DE ARCHIVOS (I/O EN LA NUBE) ---
def buscar_carpeta(servicio, nombre, id_padre):
    query = f"name = '{nombre}' and '{id_padre}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    items = res.get('files', [])
    return items[0]['id'] if items else None

def leer_job_file(servicio, nombre_archivo):
    try:
        query = f"name = '{nombre_archivo}' and '{ID_CONFIG_DIR}' in parents and trashed = false"
        res = servicio.files().list(q=query, fields="files(id)", supportsAllDrives=True).execute()
        items = res.get('files', [])
        if not items: return []
        request = servicio.files().get_media(fileId=items[0]['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        return json.loads(fh.getvalue().decode('utf-8'))
    except Exception: 
        return []

def guardar_job_file(servicio, datos, nombre_archivo):
    try:
        media = MediaInMemoryUpload(json.dumps(datos, indent=4, ensure_ascii=False).encode('utf-8'), mimetype='application/json')
        query = f"name = '{nombre_archivo}' and '{ID_CONFIG_DIR}' in parents"
        res = servicio.files().list(q=query, supportsAllDrives=True).execute().get('files', [])
        if res:
            servicio.files().update(fileId=res[0]['id'], media_body=media, supportsAllDrives=True).execute()
        else:
            meta = {'name': nombre_archivo, 'parents': [ID_CONFIG_DIR]}
            servicio.files().create(body=meta, media_body=media, supportsAllDrives=True).execute()
        return True
    except Exception: 
        return False 

# --- 3. MOTOR DE AUDITORÍA IA ASÍNCRONO MULTI-RAMO OPTIMIZADO ---
def analizar_con_gemini_worker(token_info, file_id, file_name):
    """Descarga la póliza, pre-califica según el ramo y ejecuta las reglas técnicas de negocio."""
    try:
        # Instanciar servicio único por hilo de ejecución para evitar colisiones en la red
        creds = Credentials.from_authorized_user_info(json.loads(token_info), SCOPES)
        servicio_hilo = build('drive', 'v3', credentials=creds)
        
        request = servicio_hilo.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        
        # System Instructions con la nueva alerta de negociación para deducibles de Incendio
        system_instruction = """
        Actúa como un Auditor Senior de Seguros en República Dominicana para D&D Asesores.
        Tienes acceso a la herramienta Google Search. Úsala de forma inteligente según el ramo identificado:
        
        REGLAS DE AUDITORÍA PARA VEHÍCULOS DE MOTOR (AUTOS):
        1. Inspecciona si la póliza incluye cobertura de 'Daños Propios', 'Colisión y Vuelco' o 'Comprensivo' (Seguro Full).
        2. SI ES 'SOLO LEY' o 'RESPONSABILIDAD CIVIL': No uses Google Search. Pon los campos financieros en 0, define Estatus como "Omitir - Solo Ley" y detalla en Nota_Auditoria que es una póliza básica.
        3. SI ES 'SEGURO FULL': Usa Google Search en portales dominicanos (ej. supercarros.com) para buscar el valor de mercado promedio del vehículo (Marca, Modelo, Año). Calcula la 'Brecha' (Valor de Mercado - Suma Asegurada). Si está infra-asegurado, Estatus es "Requiere Aumento", de lo contrario "Correcto".
        
        REGLAS DE AUDITORÍA PARA INCENDIO Y ALIADOS:
        1. Si el documento corresponde al ramo de Incendio y Aliados, inspecciona rigurosamente las condiciones particulares y el cuadro de coberturas.
        2. Confirma de forma explícita si la póliza incluye la cláusula de 'Valor de Reposición' (o reemplazo) y la cobertura de 'Combustión Espontánea'.
        3. Identifica si la cobertura de Incendio y/o Rayo aplica algún deducible específico y extrae su porcentaje o monto correspondiente.
        4. REGLA CRÍTICA DE ALERTA: Si detectas que existe un deducible aplicable a la cobertura de Incendio y/o Rayo, debes definir el campo 'Estatus' obligatoriamente como "Requiere Revisión y Negociación" (en lugar de "Correcto"), indicando en la nota que se debe evaluar la eliminación o reducción del mismo con la aseguradora.
        5. En el campo 'Nota_Auditoria', redacta obligatoriamente un desglose técnico estructurado confirmando estos hallazgos junto con un listado detallado de todas las demás coberturas aliadas contratadas (Terremoto, Huracán, Inundación, Remoción de Escombros, Pérdidas Consecuenciales, etc.).
        
        REGLAS DE NEGOCIO CORPORATIVAS E INQUEBRANTABLES:
        1. Formato de Fechas: Expresa absolutamente todas las fechas detectadas en formato estricto (DD/MM/AAAA).
        2. Seguros de Salud Locales: Está terminantemente prohibido utilizar el término 'deducible'. Debes mapear y registrar estos valores bajo el concepto exclusivo de 'diferencias' (copagos, coaseguros o topes de diferencias).
        3. Seguridad de Enlaces: Por políticas de control de la firma, no extraigas ni escribas enlaces directos a pasarelas de pago de aseguradoras.
        """
        
        prompt = f"""
        Analiza detalladamente este documento técnico. Identifica el ramo correspondiente y aplica las directrices del sistema.
        Si es una póliza de Incendio y Aliados, evalúa con cuidado los deducibles para activar la alerta de revisión y negociación si aplica.
        
        ESTRUCTURA JSON REQUERIDA:
        {{
            "Archivo": "{file_name}",
            "Ramo": "Texto (ej: Vehículos de Motor / Incendio y Aliados / Salud)",
            "Detalle_Objeto": "Texto (ej: Dirección del riesgo asegurado, o Marca/Modelo/Año si es auto)",
            "Sub_Modelo": "Texto (ej: SE, XL, Sport / o Descripción del bloque edificado si aplica)",
            "Suma_Asegurada_RD": 0,
            "Valor_Market_o_Limite": 0,  
            "Brecha": 0,                  
            "Estatus": "Requiere Aumento / Correcto / Omitir - Solo Ley / Requiere Revisión y Negociación",
            "Nota_Auditoria": "Texto descriptivo detallado. Si es Incendio, detalla de forma exhaustiva: 1. ¿Incluye Valor de Reposición? 2. ¿Incluye Combustión Espontánea? 3. Deducible de Incendio y su % (marcando la necesidad de negociación si existe). 4. Detalle completo de todas las coberturas aliadas encontradas.",
            "Fecha_Analisis": "({datetime.datetime.now().strftime('%d/%m/%Y')})"
        }}
        """
        
        # Llamada a Gemini 3.5 Flash con Google Search Grounding activo
        response = client_gemini.models.generate_content(
            model='gemini-3.5-flash',
            contents=[
                types.Part.from_bytes(data=fh.getvalue(), mime_type='application/pdf'),
                prompt
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.15,
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        
        resultado = json.loads(response.text)
        return resultado if isinstance(resultado, dict) else {"Archivo": file_name, "Estatus": "Error: Formato de datos corrupto"}
            
    except Exception as e:
        return {"Archivo": file_name, "Estatus": f"Error en procesamiento: {str(e)}"}

# --- 4. INTERFAZ DE USUARIO (STREAMLIT) ---
st.set_page_config(page_title="D&D Auditoría IA", layout="wide", page_icon="🛡️")
st.title("🛡️ Auditoría Integral v9.4")

MESES_DICT = {"1":"01- Enero","2":"02- Febrero","3":"03- Marzo","4":"04- Abril","5":"05- Mayo","6":"06- Junio",
              "7":"07- Julio","8":"08- Agosto","9":"09- Septiembre","10":"10- Octubre","11":"11- Noviembre","12":"12- Diciembre"}

with st.container(border=True):
    st.subheader("📅 Periodo de Auditoría")
    col1, col2 = st.columns(2)
    anio_sel = col1.selectbox("Año", ["2025", "2026", "2027"], index=1)
    mes_idx = col2.selectbox("Mes", range(1, 13), index=datetime.datetime.now().month-1, format_func=lambda x: MESES_DICT[str(x)])
    mes_nombre = MESES_DICT[str(mes_idx)]
    nombre_reporte = f"job_{anio_sel}_{str(mes_idx).zfill(2)}.json"
    
    # --- RECUPERACIÓN HISTÓRICA INMEDIATA ---
    if st.button("📥 CARGAR REPORTE HISTÓRICO (SIN ESCANEAR QNAP)", use_container_width=True):
        servicio = obtener_servicio_drive()
        if servicio:
            with st.spinner("Buscando base de datos histórica en la nube..."):
                historial = leer_job_file(servicio, nombre_reporte)
                if historial:
                    st.session_state['lote_historial'] = historial
                    st.session_state['total_pdfs'] = len(historial)
                    st.session_state['pendientes'] = []
                    st.success(f"📦 ¡Reporte histórico recuperado exitosamente! {len(historial)} registros cargados. Dirígete a la pestaña 'Reporte' para descargar tu archivo CSV.")
                else:
                    st.warning("No se localizó ninguna auditoría guardada de manera previa para este periodo de tiempo específico.")

with st.sidebar:
    st.header("⚙️ Configuración de Almacenamiento")
    root_id = st.text_input("ID Carpeta QNAP", value=st.secrets.get("DRIVE_FOLDER_ID", ""), type="password")

t1, t2, t3 = st.tabs(["🚀 Ejecución", "📊 Monitor", "🏆 Reporte"])

with t1:
    if st.button("🔍 ESCANEAR ESTRUCTURA QNAP"):
        servicio = obtener_servicio_drive()
        if servicio and root_id:
            with st.spinner("Sincronizando el índice de carpetas físicas y digitales..."):
                id_anio = buscar_carpeta(servicio, anio_sel, root_id)
                id_mes = buscar_carpeta(servicio, mes_nombre, id_anio) if id_anio else None
                if not id_mes: 
                    st.error("No se localizó la estructura de carpetas correspondiente al mes seleccionado.")
                    st.stop()
                
                historial = leer_job_file(servicio, nombre_reporte)
                auditados = [r.get('Archivo', '') for r in historial if isinstance(r, dict)]
                
                res = servicio.files().list(
                    q=f"'{id_mes}' in parents and mimeType='application/pdf' and trashed=false", 
                    fields="files(id, name)",
                    pageSize=1000, 
                    supportsAllDrives=True
                ).execute()
                
                pdfs = res.get('files', [])
                
                st.session_state['lote_historial'] = historial
                st.session_state['pendientes'] = [f for f in pdfs if f['name'] not in auditados]
                st.session_state['total_pdfs'] = len(pdfs)
                st.success(f"Escaneo completo: {len(st.session_state['pendientes'])} pendientes detectados de un universo total de {len(pdfs)} archivos.")

    if 'pendientes' in st.session_state and st.session_state['pendientes']:
        if st.button("🚀 INICIAR AUDITORÍA EN PARALELO"):
            if not client_gemini:
                st.error("Error: Llave de API (GEMINI_API_KEY) no configurada.")
                st.stop()
                
            servicio = obtener_servicio_drive()
            token_info = st.secrets["GOOGLE_USER_TOKEN"]
            
            progreso = st.progress(0)
            status = st.empty()
            lote = st.session_state['lote_historial']
            pendientes = st.session_state['pendientes']
            total_pendientes = len(pendientes)
            
            CONCURRENT_WORKERS = 5
            st.info(f"Procesando hilos de ejecución en lotes concurrentes de {CONCURRENT_WORKERS}...")
            
            contador_completados = 0
            
            with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
                futuro_a_archivo = {
                    executor.submit(analizar_con_gemini_worker, token_info, f['id'], f['name']): f 
                    for f in pendientes
                }
                
                for futuro in as_completed(futuro_a_archivo):
                    archivo_info = futuro_a_archivo[futuro]
                    contador_completados += 1
                    
                    try:
                        res_ia = futuro.result()
                        if res_ia and isinstance(res_ia, dict):
                            lote.append(res_ia)
                        else:
                            lote.append({"Archivo": archivo_info['name'], "Estatus": "Error: Estructura corrupta"})
                    except Exception as exc:
                        lote.append({"Archivo": archivo_info['name'], "Estatus": f"Falla crítica en hilo: {exc}"})
                    
                    # Guardado periódico inteligente cada 5 archivos
                    if contador_completados % 5 == 0 or contador_completados == total_pendientes:
                        status.markdown(f"💾 Respaldando lote de progreso en Google Drive... ({contador_completados}/{total_pendientes})")
                        guardar_job_file(servicio, lote, nombre_reporte)
                    
                    status.markdown(f"**Procesando:** `{archivo_info['name']}` ({contador_completados}/{total_pendientes})")
                    progreso.progress(contador_completados / total_pendientes)
            
            st.session_state['pendientes'] = []
            st.session_state['lote_historial'] = lote
            st.success("🎉 ¡Proceso de auditoría multi-ramo finalizado con éxito!")

with t2:
    if 'total_pdfs' in st.session_state:
        hechos = len(st.session_state.get('lote_historial', []))
        total = st.session_state['total_pdfs']
        st.metric("Estatus del Lote Actual", f"{hechos} procesados de {total} totales")
        st.progress(min(1.0, hechos / total) if total > 0 else 0)

with t3:
    if st.session_state.get('lote_historial'):
        df = pd.DataFrame(st.session_state['lote_historial'])
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Descargar Reporte CSV", df.to_csv(index=False), f"{nombre_reporte}.csv", use_container_width=True)
        
