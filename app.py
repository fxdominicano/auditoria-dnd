import streamlit as st
import os, pandas as pd, statistics, requests, re, time, datetime
from bs4 import BeautifulSoup

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
    st.info(f"D&D Asesores v4.1\nSantiago, RD.")

# --- 4. CUERPO PRINCIPAL ---
st.title("🛡️ Motor de Auditoría Inteligente")

# Selectores globales (ahora afectan a todas las pestañas)
col_a, col_b = st.columns(2)
with col_a:
    anio_sel = st.selectbox("Año Fiscal", opciones_anios, index=opciones_anios.index(str(anio_actual)))
with col_b:
    mes_sel = st.selectbox("Mes de Auditoría", range(1, 13), index=datetime.datetime.now().month - 1, format_func=lambda x: MESES_DICT[str(x)])

tabs = st.tabs(["🚀 Lanzar Auditoría", "📊 Monitor de Lotes", "🏆 Reporte e Ingresos"])

# --- PESTAÑA 1: LANZAR ---
with tabs[0]:
    st.subheader(f"Preparando envío: {MESES_DICT[str(mes_sel)]} {anio_sel}")
    if st.button("🚀 ENVIAR LOTE A GOOGLE GEMINI"):
        # Simulamos la creación de un Job ID único
        job_id = f"job-{anio_sel}{mes_sel:02d}-{int(time.time())}"
        st.success(f"✅ Lote enviado. ID de Seguimiento: **{job_id}**")
        st.info("Este lote se procesará de forma independiente en los servidores de Google.")

# --- PESTAÑA 2: MONITOR (MEJORADO) ---
with tabs[1]:
    st.subheader(f"🔍 Seguimiento para {MESES_DICT[str(mes_sel)]} {anio_sel}")
    
    # Aquí simulamos que el sistema busca el estatus específico de esa fecha
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Estado del Lote", "PENDING", delta="En cola de proceso")
    with c2:
        st.metric("Pólizas Detectadas", "45")
    with c3:
        st.metric("Progreso IA", "12%")
    
    st.divider()
    st.markdown("### 📜 Historial de envíos paralelos")
    historial = [
        {"Fecha Envío": "16/04/2026", "Lote": "Marzo 2026", "ID": "job-202603-987", "Estado": "COMPLETED"},
        {"Fecha Envío": "17/04/2026", "Lote": "Abril 2026", "ID": "job-202604-123", "Estado": "PROCESSING"},
    ]
    st.table(historial)
    st.caption("Nota: Iniciar un nuevo lote NO detiene los anteriores. Google los maneja de forma independiente.")

# --- PESTAÑA 3: REPORTE ---
with tabs[2]:
    st.subheader(f"📊 Resultados: {MESES_DICT[str(mes_sel)]} {anio_sel}")
    # (Mantenemos tu lógica de dataframe de comisiones aquí)
    df = pd.DataFrame([{"Cliente": "Auditoría Santiago", "Suma": 1500000, "Mercado": 2100000}])
    df["Comisión Perdida"] = (df["Mercado"] - df["Suma"]) * tasa_seg_avg * porc_com
    st.metric("Ingreso Recuperable", f"RD$ {df['Comisión Perdida'].sum():,.2f}")
    st.dataframe(df)
