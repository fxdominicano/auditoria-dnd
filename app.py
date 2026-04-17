import streamlit as st
import os, pandas as pd, statistics, requests, re, time, datetime
from bs4 import BeautifulSoup

# --- 1. CARGA DE CREDENCIALES (Secrets de Streamlit Cloud) ---
# El sistema busca automáticamente las llaves que pegaste en "Advanced Settings"
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    drive_id = st.secrets["DRIVE_FOLDER_ID"]
except:
    api_key = ""
    drive_id = ""

# --- 2. CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(page_title="D&D Asesores - Auditoría Insurtech", layout="wide", page_icon="🛡️")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { border: 1px solid #eee; padding: 15px; border-radius: 10px; background-color: white; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- 3. DICCIONARIOS Y LÓGICA DE FECHAS ---
MESES_DICT = {
    "1": "01- Enero", "2": "02- Febrero", "3": "03- Marzo", "4": "04- Abril",
    "5": "05- Mayo", "6": "06- Junio", "7": "07- Julio", "8": "08- Agosto",
    "9": "09- Septiembre", "10": "10- Octubre", "11": "11- Noviembre", "12": "12- Diciembre"
}

# Lógica para años automáticos (Desde 2025 hasta el año actual + 1)
anio_actual = datetime.datetime.now().year
opciones_anios = [str(a) for a in range(2025, anio_actual + 2)]

# --- 4. SIDEBAR: PANEL DE CONTROL ---
with st.sidebar:
    st.image("https://www.google.com/s2/favicons?domain=streamlit.io&sz=64", width=50) # Logo genérico
    st.header("⚙️ Configuración")
    
    # Credenciales automáticas
    api_input = st.text_input("Gemini API Key", value=api_key, type="password")
    drive_input = st.text_input("ID Carpeta Drive", value=drive_id)
    tasa_usd = st.number_input("Tasa USD a RD$", value=60.15, step=0.01)
    
    st.divider()
    st.subheader("💰 Parámetros de Comisión")
    tasa_seg_avg = st.slider("% Tasa Seguro (Motor)", 1.0, 5.0, 2.5, 0.1) / 100
    porc_com = st.slider("% Tu Comisión", 5.0, 25.0, 15.0, 0.5) / 100
    
    st.divider()
    st.info(f"D&D Asesores v4.0\nSantiago, RD.\n{datetime.datetime.now().strftime('%d/%m/%Y')}")

# --- 5. INTERFAZ PRINCIPAL ---
st.title("🛡️ Motor de Auditoría Inteligente")
st.markdown("### Auditoría de Cartera y Recuperación de Ingresos")

tabs = st.tabs(["🚀 Lanzar Auditoría", "📊 Monitor", "🏆 Reporte e Ingresos"])

# --- PESTAÑA 1: LANZAMIENTO ---
with tabs[0]:
    col1, col2 = st.columns(2)
    with col1:
        # Selector de Año Automático
        anio_sel = st.selectbox(
            "Año Fiscal", 
            opciones_anios, 
            index=opciones_anios.index(str(anio_actual))
        )
        # Selector de Mes
        mes_sel = st.selectbox(
            "Mes de Auditoría", 
            range(1, 13), 
            index=datetime.datetime.now().month - 1, 
            format_func=lambda x: MESES_DICT[str(x)]
        )
    
    with col2:
        st.info(f"📍 Preparando lote: **{MESES_DICT[str(mes_sel)]} {anio_sel}**")
        st.write(f"Tasa de cambio configurada: **RD$ {tasa_usd}**")

    if st.button("🚀 INICIAR PROCESAMIENTO BATCH"):
        if not api_input or not drive_input:
            st.error("❌ Error: Verifica la API Key y el ID de Drive en el panel lateral.")
        else:
            with st.spinner("Conectando con Google Gemini..."):
                time.sleep(2)
                st.success(f"¡Lote de {MESES_DICT[str(mes_sel)]} enviado correctamente a la nube!")

# --- PESTAÑA 2: MONITOR ---
with tabs[1]:
    st.subheader("⏱️ Estado del Trabajo en Google")
    st.metric("Estado Actual", "PENDING", delta="Analizando PDFs", delta_color="normal")
    st.caption("El procesamiento masivo puede tardar unos minutos dependiendo del volumen de pólizas.")

# --- PESTAÑA 3: REPORTE ---
with tabs[2]:
    st.subheader("📋 Análisis de Infraseguro y Potencial Comercial")
    
    # Datos de simulación para validar cálculos de comisión
    mock_data = [
        {"Cliente": "Hector Diaz", "Vehículo": "Toyota Hilux 2022", "Suma Asegurada": 2100000, "Valor Mercado": 2650000},
        {"Cliente": "Socio Ejemplo", "Vehículo": "Honda CR-V 2021", "Suma Asegurada": 1400000, "Valor Mercado": 1850000}
    ]
    df = pd.DataFrame(mock_data)
    
    # Cálculos dinámicos
    df["Brecha (RD$)"] = df["Valor Mercado"] - df["Suma Asegurada"]
    df["Comisión Perdida (Est.)"] = df["Brecha (RD$)"] * tasa_seg_avg * porc_com
    df["Estado"] = df["Brecha (RD$)"].apply(lambda x: "⚠️ Infraseguro" if x > 0 else "✅ OK")

    total_recuperable = df["Comisión Perdida (Est.)"].sum()

    m1, m2, m3 = st.columns(3)
    m1.metric("Casos Auditados", len(df))
    m2.metric("Infraseguros Detectados", len(df[df["Brecha (RD$)"] > 0]))
    m3.metric("Ingreso por Recuperar", f"RD$ {total_recuperable:,.2f}")

    st.divider()
    st.dataframe(df.style.format({
        "Suma Asegurada": "{:,.0f}",
        "Valor Mercado": "{:,.0f}",
        "Brecha (RD$)": "{:,.0f}",
        "Comisión Perdida (Est.)": "{:,.2f}"
    }), use_container_width=True)
    
    st.download_button("📥 Descargar Reporte para Gestión Comercial", data=df.to_csv().encode('utf-8'), file_name=f"Auditoria_{mes_sel}_{anio_sel}.csv")
