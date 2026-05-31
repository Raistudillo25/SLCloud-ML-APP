"""
ASTUM ML - Dashboard Utilidad Vendedores MercadoLibre
=====================================================
Version SaaS multi-cliente para Streamlit Cloud.

COMO CORRER LOCAL:
    pip install -r requirements.txt
    streamlit run app_saas.py

QUE HACE:
    - Login / Registro de usuarios
    - Cada usuario conecta SU cuenta de MercadoLibre
    - Dashboard con datos reales de ventas y utilidad
"""

import streamlit as st
import pandas as pd
import requests
import os
import sys
from datetime import datetime

# ============================================================
# CONFIGURACION INICIAL
# ============================================================
st.set_page_config(
    page_title="ASTUM ML - Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# IMPORTAR BASE DE DATOS
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
)

crear_tablas()

# ============================================================
# CONFIGURACION MERCADOLIBRE APP
# ============================================================
ML_CLIENT_ID = "1879547931760449"
ML_CLIENT_SECRET = "z1icamOFSIagMoEusORZ9cA2nud10pq2"
ML_REDIRECT_URI = "https://grupoastum.netlify.app/"


# ============================================================
# FUNCIONES DE CONEXION ML
# ============================================================
def generar_url_autorizacion():
    """Genera el link que el vendedor debe abrir para autorizar."""
    return (
        f"https://auth.mercadolibre.cl/authorization"
        f"?response_type=code"
        f"&client_id={ML_CLIENT_ID}"
        f"&redirect_uri={ML_REDIRECT_URI}"
    )


def canjear_codigo_por_token(codigo):
    """Cambia el codigo de autorizacion por un Access Token."""
    try:
        respuesta = requests.post("https://api.mercadolibre.com/oauth/token", data={
            "grant_type": "authorization_code",
            "client_id": ML_CLIENT_ID,
            "client_secret": ML_CLIENT_SECRET,
            "code": codigo,
            "redirect_uri": ML_REDIRECT_URI,
        }, timeout=15)
        
        datos = respuesta.json()
        
        if "access_token" in datos:
            return {"ok": True, "datos": datos}
        elif "error" in datos:
            return {"ok": False, "error": datos.get("message", datos.get("error", "Error desconocido"))}
        else:
            return {"ok": False, "error": "Respuesta inesperada de MercadoLibre"}
    
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "La conexion con MercadoLibre tardó demasiado. Intenta de nuevo."}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Error de conexion: {str(e)}"}
    except Exception as e:
        return {"ok": False, "error": f"Error inesperado: {str(e)}"}


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
    /* Paso a paso */
    .paso-card {
        background-color: #1a1d27;
        border: 1px solid #2a2d3a;
        border-radius: 10px;
        padding: 1.2rem;
        margin-bottom: 1rem;
    }
    .paso-numero {
        color: #f0c040;
        font-weight: bold;
        font-size: 1.1rem;
    }
    .url-link {
        background-color: #0d1117;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 0.6rem 1rem;
        color: #58a6ff;
        font-size: 0.85rem;
        word-break: break-all;
        font-family: monospace;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# PAGINA DE LOGIN/REGISTRO
# ============================================================
def pagina_login():
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
                                       placeholder="Ej: Rin SPA")
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
# SECCION: CONEXION ML (dentro del dashboard)
# ============================================================
def seccion_conexion_ml(usuario):
    """Muestra el estado de conexion ML y permite conectar/desconectar."""
    
    db = get_db()
    token = obtener_token_ml(db, usuario["id"])
    db.close()
    
    st.subheader("🔗 Conexión MercadoLibre")
    
    if token:
        # ─── YA ESTA CONECTADO ───
        st.success("✅ Tu cuenta de MercadoLibre está conectada")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("ID Vendedor", token.get("ml_user_id", "—"))
        with col2:
            st.metric("Expira", token.get("expires_at", "—"))
        with col3:
            if st.button("🔌 Desconectar", use_container_width=True):
                db = get_db()
                cursor = db.cursor()
                cursor.execute("DELETE FROM tokens_ml WHERE user_id = ?", (usuario["id"],))
                db.commit()
                db.close()
                st.success("✅ MercadoLibre desconectado")
                st.rerun()
    
    else:
        # ─── NO CONECTADO: mostrar paso a paso ───
        st.warning("🔌 Aún no conectas tu cuenta de MercadoLibre")
        st.markdown("Sigue estos 3 pasos para conectar tu tienda:")
        
        url_ml = generar_url_autorizacion()
        
        # PASO 1
        st.markdown(f"""
        <div class="paso-card">
            <span class="paso-numero">Paso 1</span><br>
            <strong>Abre este link en una nueva pestaña:</strong>
            <div class="url-link">{url_ml}</div>
            <span style="color:#8b949e;font-size:0.85rem;">
            👉 Haz clic en el link de arriba, inicia sesión con tu cuenta de MercadoLibre 
            y haz clic en <strong>"Autorizar"</strong>
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        # PASO 2
        st.markdown(f"""
        <div class="paso-card">
            <span class="paso-numero">Paso 2</span><br>
            <strong>Te redirigirá a nuestra página</strong> y verás un código en pantalla.
            <span style="color:#8b949e;display:block;font-size:0.85rem;margin-top:0.3rem;">
            📋 <strong>Copia ese código</strong> (se ve similar a: TG-1234567890)
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        # PASO 3
        st.markdown('<div class="paso-card">', unsafe_allow_html=True)
        st.markdown('<span class="paso-numero">Paso 3</span><br>', unsafe_allow_html=True)
        st.markdown('<strong>Pega aquí el código y haz clic en "Conectar":</strong>', unsafe_allow_html=True)
        
        with st.form("form_conectar_ml"):
            codigo = st.text_input(
                "Código de autorización",
                placeholder="Ej: TG-1234567890",
                help="Pega el código que apareció en la pantalla después de autorizar"
            )
            conectar = st.form_submit_button("🔗 Conectar MercadoLibre", type="primary")
            
            if conectar:
                if not codigo or len(codigo) < 5:
                    st.error("Ingresa el código completo que apareció en pantalla")
                else:
                    with st.spinner("Conectando con MercadoLibre..."):
                        resultado = canjear_codigo_por_token(codigo.strip())
                    
                    if resultado["ok"]:
                        datos = resultado["datos"]
                        db = get_db()
                        guardar_token_ml(
                            db,
                            usuario["id"],
                            access_token=datos["access_token"],
                            refresh_token=datos.get("refresh_token", ""),
                            ml_user_id=str(datos.get("user_id", "")),
                            expires_at=datetime.now().timestamp() + datos.get("expires_in", 21600),
                        )
                        db.close()
                        st.success("✅ ¡MercadoLibre conectado correctamente!")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(f"❌ Error: {resultado['error']}")
        
        st.markdown('</div>', unsafe_allow_html=True)


# ============================================================
# DASHBOARD PRINCIPAL
# ============================================================
def pagina_dashboard():
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
    
    # ─── SECCION: CONEXION ML ───
    seccion_conexion_ml(usuario)
    
    st.divider()
    
    # ─── AREA PRINCIPAL (se expandirá después) ───
    col_izq, col_der = st.columns(2)
    
    with col_izq:
        st.subheader("📈 Resumen Rápido")
        
        db = get_db()
        token = obtener_token_ml(db, usuario["id"])
        db.close()
        
        if token:
            st.success("✅ ML conectado — los datos aparecerán aquí")
            st.caption("Próximamente: ventas, ingresos, costos y utilidad real")
        else:
            st.info("Conecta MercadoLibre (pasos arriba) para ver tus datos")
        
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Ventas", "—")
        with m2:
            st.metric("Ingresos", "—")
        with m3:
            st.metric("Costos", "—")
        with m4:
            st.metric("Utilidad", "—")
    
    with col_der:
        st.subheader("⚙️ Tu Cuenta")
        with st.expander("Ver datos", expanded=True):
            st.write(f"**Empresa:** {usuario['empresa']}")
            st.write(f"**Contacto:** {usuario['nombre']}")
            st.write(f"**Email:** {usuario['email']}")
            st.write(f"**Registrado:** {usuario['fecha_registro']}")
    
    st.divider()
    st.markdown('<div class="footer-saas">ASTUM Group © 2026 | AstumGroup.cl | contacto@astumgroup.cl</div>',
                unsafe_allow_html=True)


# ============================================================
# PUNTO DE ENTRADA
# ============================================================
if "usuario" in st.session_state and st.session_state["usuario"]:
    pagina_dashboard()
else:
    pagina_login()
