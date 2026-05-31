"""
ASTUM ML - Dashboard Utilidad Vendedores MercadoLibre
=====================================================
Version SaaS multi-cliente para Streamlit Cloud.

COMO CORRER LOCAL:
    pip install -r requirements.txt
    streamlit run app_saas.py

COMO SUBIR A STREAMLIT CLOUD:
    1. Sube estos archivos a un repositorio en GitHub
    2. Entra a https://share.streamlit.io
    3. Conecta tu repositorio → "Deploy"
    4. La app queda online en: [tu-app].streamlit.app

QUE HACE:
    - Login / Registro de usuarios
    - Cada usuario ve SOLO sus datos
    - Conexion a MercadoLibre por usuario
    - Dashboard de utilidad real
"""

import streamlit as st
import pandas as pd
import os
import sys
from datetime import datetime

# ============================================================
# CONFIGURACION INICIAL - siempre va primero
# ============================================================
st.set_page_config(
    page_title="ASTUM ML - Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# IMPORTAR BASE DE DATOS (desde el mismo directorio)
# ============================================================
sys.path.insert(0, os.path.dirname(__file__))
from database import (
    get_db,
    crear_tablas,
    crear_usuario,
    verificar_login,
    obtener_usuario_por_id,
    obtener_token_ml,
    guardar_token_ml,
    guardar_costos,
    obtener_costos_usuario,
)

# Crear tablas al iniciar (si no existen)
crear_tablas()


# ============================================================
# ESTILOS CSS
# ============================================================
st.markdown("""
<style>
    .stApp {
        background-color: #0e1117;
    }
    .card-login {
        background-color: #1a1d27;
        border: 1px solid #2a2d3a;
        border-radius: 12px;
        padding: 2rem;
        max-width: 420px;
        margin: 2rem auto;
    }
    .card-login h1 {
        color: #f0c040;
        text-align: center;
        font-size: 1.8rem;
        margin-bottom: 0.3rem;
    }
    .card-login .subtitle {
        color: #8899aa;
        text-align: center;
        margin-bottom: 1.5rem;
        font-size: 0.9rem;
    }
    .logo-astum {
        text-align: center;
        font-size: 2.2rem;
        font-weight: bold;
        color: #f0c040;
        margin-bottom: 0.2rem;
        letter-spacing: 4px;
    }
    .logo-astum small {
        color: #4a8fe0;
        font-size: 0.7rem;
        display: block;
        letter-spacing: 2px;
    }
    .stButton > button {
        width: 100%;
        border-radius: 8px;
        font-weight: 600;
    }
    .footer-saas {
        text-align: center;
        color: #444;
        font-size: 0.75rem;
        margin-top: 3rem;
        padding-top: 1rem;
        border-top: 1px solid #222;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# PAGINA DE LOGIN/REGISTRO
# ============================================================
def pagina_login():
    """Muestra pantalla de login y registro."""
    
    st.markdown('<div class="logo-astum">ASTUM <small>MERCADOLIBRE ANALYTICS</small></div>',
                unsafe_allow_html=True)
    
    st.markdown('<div class="card-login">', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🔑 Iniciar Sesión", "📝 Crear Cuenta"])
    
    with tab1:
        st.markdown('<h1>Bienvenido</h1>', unsafe_allow_html=True)
        st.markdown('<p class="subtitle">Ingresa con tu cuenta</p>', unsafe_allow_html=True)
        
        with st.form("form_login"):
            email = st.text_input("Email", placeholder="ejemplo@correo.cl")
            password = st.text_input("Contraseña", type="password", placeholder="••••••")
            submit = st.form_submit_button("Iniciar Sesión", type="primary")
            
            if submit:
                if not email or not password:
                    st.error("Completa todos los campos")
                else:
                    db = get_db()
                    usuario = verificar_login(db, email, password)
                    db.close()
                    
                    if usuario:
                        st.session_state["usuario"] = usuario
                        st.rerun()
                    else:
                        st.error("Email o contraseña incorrectos")
    
    with tab2:
        st.markdown('<h1>Crear Cuenta</h1>', unsafe_allow_html=True)
        st.markdown('<p class="subtitle">Registra tu empresa para empezar</p>', unsafe_allow_html=True)
        
        with st.form("form_registro"):
            col1, col2 = st.columns(2)
            with col1:
                empresa = st.text_input("Nombre de tu empresa",
                                       placeholder="Ej: Cosméticos Coreanos Spa")
            with col2:
                nombre = st.text_input("Tu nombre", placeholder="Ej: Juan Pérez")
            
            email_reg = st.text_input("Email", placeholder="tu@correo.cl")
            pass_reg = st.text_input("Contraseña", type="password", placeholder="Mínimo 6 caracteres")
            pass_confirm = st.text_input("Repetir contraseña", type="password")
            
            submit_reg = st.form_submit_button("Crear Cuenta", type="primary")
            
            if submit_reg:
                if not all([empresa, nombre, email_reg, pass_reg, pass_confirm]):
                    st.error("Completa todos los campos")
                elif pass_reg != pass_confirm:
                    st.error("Las contraseñas no coinciden")
                elif len(pass_reg) < 6:
                    st.error("La contraseña debe tener al menos 6 caracteres")
                elif "@" not in email_reg:
                    st.error("Ingresa un email válido")
                else:
                    db = get_db()
                    usuario = crear_usuario(db, email_reg, pass_reg, empresa, nombre)
                    db.close()
                    
                    if usuario:
                        st.success(f"✅ Cuenta creada para {empresa}! Ahora inicia sesión.")
                    else:
                        st.error("❌ Ese email ya está registrado. Usa otro o inicia sesión.")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="footer-saas">ASTUM Group © 2026 — Powered by Streamlit</div>',
                unsafe_allow_html=True)


# ============================================================
# DASHBOARD (se expandira en los siguientes pasos)
# ============================================================
def pagina_dashboard():
    """Muestra el dashboard para el usuario logueado."""
    usuario = st.session_state["usuario"]
    
    # ─── BARRA SUPERIOR ───
    col_logo, col_user, col_logout = st.columns([3, 2, 1])
    
    with col_logo:
        st.markdown(f'<span class="logo-astum" style="font-size:1.3rem;letter-spacing:2px;">ASTUM <span style="font-size:0.7rem;color:#4a8fe0;">ML</span></span>',
                    unsafe_allow_html=True)
    
    with col_user:
        st.markdown(f'<div style="text-align:right;color:#8899aa;padding-top:8px;">'
                    f'👤 {usuario["empresa"]} <span style="color:#555;">|</span> '
                    f'<span style="color:#4a8fe0;">{usuario["email"]}</span>'
                    f'</div>', unsafe_allow_html=True)
    
    with col_logout:
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            del st.session_state["usuario"]
            st.rerun()
    
    st.divider()
    
    # ─── BIENVENIDA ───
    st.title(f"📊 Dashboard {usuario['empresa']}")
    st.caption("Bienvenido, aquí verás la utilidad real de tus productos en MercadoLibre.")
    
    # ─── VERIFICAR CONEXION ML ───
    db = get_db()
    token = obtener_token_ml(db, usuario["id"])
    db.close()
    
    col_ml, col_costos, col_accion = st.columns(3)
    
    with col_ml:
        if token:
            st.success("✅ MercadoLibre conectado")
            st.caption(f"ID vendedor: {token.get('ml_user_id', '—')}")
        else:
            st.warning("🔌 MercadoLibre no conectado")
            st.caption("Conecta tu cuenta para ver datos reales")
    
    with col_costos:
        st.info("📄 Sin costos cargados aún")
        st.caption("Sube tu CSV de costos para calcular utilidad")
    
    with col_accion:
        st.info("💡 ¿Qué quieres hacer?")
        st.markdown("👉 *Próximamente: conectar tu MercadoLibre*")
    
    st.divider()
    
    # ─── AREA PRINCIPAL (placeholder) ───
    col_izq, col_der = st.columns(2)
    
    with col_izq:
        st.subheader("📈 Resumen Rápido")
        st.info("Aquí aparecerán tus métricas cuando conectes MercadoLibre")
        
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Ventas", "—", help="Conecta ML para ver datos")
        with m2:
            st.metric("Ingresos", "—")
        with m3:
            st.metric("Costos", "—")
        with m4:
            st.metric("Utilidad", "—")
    
    with col_der:
        st.subheader("⚙️ Tu Configuración")
        with st.expander("Ver datos de mi cuenta", expanded=True):
            st.write(f"**Empresa:** {usuario['empresa']}")
            st.write(f"**Contacto:** {usuario['nombre']}")
            st.write(f"**Email:** {usuario['email']}")
            st.write(f"**Registrado:** {usuario['fecha_registro']}")
        
        with st.expander("¿Cómo funciona esto?"):
            st.markdown("""
            1. **Conecta tu cuenta de MercadoLibre** (autorizas 1 vez)
            2. **Sube tu CSV de costos** (lo que pagas por cada producto)
            3. **El dashboard calcula automáticamente:**
               - Utilidad real por producto
               - Productos más rentables
               - Alertas de productos con pérdida
               - Productos mejor/peor reseñados
            """)
    
    st.divider()
    st.markdown('<div class="footer-saas">ASTUM Group © 2026</div>', unsafe_allow_html=True)


# ============================================================
# PUNTO DE ENTRADA PRINCIPAL
# ============================================================
if "usuario" in st.session_state and st.session_state["usuario"]:
    pagina_dashboard()
else:
    pagina_login()
