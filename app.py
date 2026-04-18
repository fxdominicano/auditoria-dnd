import streamlit as st
import os, pandas as pd, time, datetime

# --- 1. CARGA DE CREDENCIALES ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    drive_id = st.secrets["DRIVE_FOLDER_ID"]
except:
    api_key = ""
    drive_id = ""

# --- 2. CONFIGURACIÓN ---
st.set_page_config(page_title="D&D Asesores - Auditoría Insurtech", layout="wide", page_icon="🛡️")

MESES_DICT = {
    "1": "01- Enero", "2": "02- Febrero", "3": "03- Marzo", "4": "04- Abril",
    "5": "05- Mayo", "6": "06- Junio", "7": "07- Julio", "8": "08- Agosto",
    "9": "09- Septiembre", "10": "10- Octubre", "11": "11- Noviembre", "12": "12- Diciembre"
}

anio_actual = datetime.datetime.now().year
opciones_anios = [str(a) for a in range(2025, anio_actual + 2)]

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configuración")
    api_input = st.text_input("Gemini API Key", value=api_key, type="password")
    drive_input = st.text_input("ID Carpeta Drive", value=drive_id)
    tasa_usd = st.number_input("Tasa USD a RD$", value=60.15)
    st.divider()
    tasa_seg_avg = st.slider("% Tasa Seguro", 1.0, 5.0, 2.5) / 100
    porc_com = st.slider("% Tu Comisión", 5.0, 25.0, 15.0) / 100
    st.info("D&D Asesores v4.3\nSantiago, RD.")

# --- 4. CUERPO PRINCIPAL ---
st.title("🛡️ Motor de Auditoría Inteligente")

col_a, col_b = st.columns(2)
with col_a:
    anio_sel = st.selectbox("Año Fiscal", opciones_anios, index=opciones_anios.index(str(anio_actual)))
with col_b:
    mes_sel = st.selectbox("Mes de Auditoría", range(1, 13), index=datetime.datetime.now().month - 1, format_func=lambda x: MESES_DICT[str(x)])

mes_nombre_full = MESES_DICT[str(mes_sel)]
tabs = st.tabs(["🚀 Lanzar Auditoría", "📊 Monitor de Lotes", "🏆 Reporte e Ingresos"])

# --- PESTAÑA 1: LANZAR (CON PROGRESO REAL) ---
with tabs[0]:
    st.subheader(f"Preparando envío: {mes_nombre_full} {anio_sel}")
    
    if st.button("🚀 INICIAR SUBIDA Y PROCESAMIENTO"):
        # 1. Lista simulada de archivos encontrados en el Drive
        # (Esto se sustituye por la lista real de nombres de archivos PDF en tu Drive)
        archivos_encontrados = [
            f"Poliza_H_Diaz_{mes_sel}.pdf", 
            f"Poliza_J_Santiago_{mes_sel}.pdf", 
            f"Flotilla_Empresa_A_{mes_sel}.pdf",
            f"Renovacion_S_Cabrera_{mes_sel}.pdf"
        ]
        
        total = len(archivos_encontrados)
        st.write(f"📂 Se detectaron **{total}** archivos para procesar.")
        
        # 2. Barra de progreso y estado
        progreso_bar = st.progress(0)
        status_text = st.empty()
        log_lista = st.empty()
        
        registros_procesados = []

        # 3. Ciclo de carga archivo por archivo
        for i, nombre_archivo in enumerate(archivos_encontrados):
            # Actualizamos texto de estado
            status_text.markdown(f"**Procesando:** `{nombre_archivo}`...")
            
            # Simulamos la subida y análisis de Gemini
            time.sleep(1.5) 
            
            # Actualizamos la barra
            porcentaje = (i + 1) / total
            progreso_bar.progress(porcentaje)
            
            # Guardamos para la lista visual
            registros_procesados.append({"Archivo": nombre_archivo, "Estatus": "✅ Enviado a IA"})
            
            # Mostramos la lista que crece en vivo
            log_lista.table(pd.DataFrame(registros_procesados))

        st.success(f"🎊 ¡Lote de {mes_nombre_full} completado con éxito!")

# --- PESTAÑA 2: MONITOR ---
with tabs[1]:
    st.subheader(f"🔍 Estatus Global {mes_nombre_full} {anio_sel}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Estado", "PROCESSING")
    c2.metric("Pólizas en Cola", "4 archivos")
    c3.metric("Última Carga", datetime.datetime.now().strftime("%H:%M"))

# --- PESTAÑA 3: REPORTE ---
with tabs[2]:
    st.info("Aquí aparecerán los resultados una vez Gemini termine el análisis profundo.")
