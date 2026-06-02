"""
ASTUM ML - Dashboard Utilidad Vendedores MercadoLibre
=====================================================
Version SaaS multi-cliente para Streamlit Cloud.

COMO CORRER:
    pip install -r requirements.txt
    streamlit run app_saas.py

QUE HACE:
    - Login / Registro por empresa
    - Conexion MercadoLibre (OAuth) por usuario
    - Sincronizacion automatica de productos y ventas desde ML
    - Carga de CSV con costos del negocio (con plantilla descargable)
    - Dashboard de utilidad real por producto
"""

import streamlit as st
import pandas as pd
import requests
import os
import sys
import io
import time
import re
from datetime import datetime, timedelta

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
    crear_tablas_ml,
    crear_usuario,
    verificar_login,
    obtener_token_ml,
    guardar_token_ml,
    guardar_costos,
    obtener_costos_usuario,
    guardar_productos_ml,
    obtener_productos_ml,
    guardar_ventas_ml,
    obtener_ventas_ml,
    ultima_sincronizacion,
    admin_listar_usuarios,
    admin_eliminar_usuario,
    admin_resetear_intentos,
    admin_obtener_stats,
)

crear_tablas()
crear_tablas_ml()

# ============================================================
# CONFIGURACION MERCADOLIBRE APP
# ============================================================
ML_CLIENT_ID = "1879547931760449"
ML_CLIENT_SECRET = "z1icamOFSIagMoEusORZ9cA2nud10pq2"
ML_REDIRECT_URI = "https://raistudillo25.github.io/astum-ml-auth/"

# ============================================================
# FUNCIONES DE TOKEN ML
# ============================================================
def generar_url_autorizacion():
    return (
        f"https://auth.mercadolibre.cl/authorization"
        f"?response_type=code"
        f"&client_id={ML_CLIENT_ID}"
        f"&redirect_uri={ML_REDIRECT_URI}"
    )

def canjear_codigo_por_token(codigo):
    try:
        r = requests.post("https://api.mercadolibre.com/oauth/token", data={
            "grant_type": "authorization_code",
            "client_id": ML_CLIENT_ID,
            "client_secret": ML_CLIENT_SECRET,
            "code": codigo,
            "redirect_uri": ML_REDIRECT_URI,
        }, timeout=15)
        datos = r.json()
        if "access_token" in datos:
            return {"ok": True, "datos": datos}
        return {"ok": False, "error": datos.get("message", str(datos))}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def refrescar_token(refresh_token_actual):
    try:
        r = requests.post("https://api.mercadolibre.com/oauth/token", data={
            "grant_type": "refresh_token",
            "client_id": ML_CLIENT_ID,
            "client_secret": ML_CLIENT_SECRET,
            "refresh_token": refresh_token_actual,
        }, timeout=15)
        datos = r.json()
        if "access_token" in datos:
            return {"ok": True, "datos": datos}
        return {"ok": False, "error": datos.get("message", str(datos))}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def verificar_y_renovar_token(user_id):
    db = get_db()
    token = obtener_token_ml(db, user_id)
    if not token:
        db.close()
        return None
    
    ahora = datetime.now().timestamp()
    expira_en = float(token.get("expires_at", 0))
    
    if expira_en - ahora < 300:
        resultado = refrescar_token(token["refresh_token"])
        if resultado["ok"]:
            datos = resultado["datos"]
            nuevo = ahora + datos.get("expires_in", 21600)
            guardar_token_ml(db, user_id,
                access_token=datos["access_token"],
                refresh_token=datos.get("refresh_token", token["refresh_token"]),
                ml_user_id=token.get("ml_user_id", ""),
                expires_at=str(nuevo),
            )
            token["access_token"] = datos["access_token"]
            token["expires_at"] = str(nuevo)
    
    db.close()
    return token

def token_expira_en_texto(expires_at_str):
    try:
        s = float(expires_at_str) - datetime.now().timestamp()
        if s <= 0: return "EXPIRADO"
        if s < 3600: return f"en {int(s/60)} min"
        if s < 86400: return f"en {int(s/3600)} hrs"
        return f"en {int(s/86400)} días"
    except:
        return "desconocido"


# ============================================================
# FUNCIONES DE SINCRONIZACION ML
# ============================================================
def llamar_api_ml(token, url, params=None):
    """Llama a la API de ML con el token del usuario."""
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, params=params or {}, timeout=20)
    if r.status_code == 200:
        return {"ok": True, "datos": r.json()}
    elif r.status_code == 401:
        return {"ok": False, "error": "Token expirado. Reconecta MercadoLibre."}
    else:
        return {"ok": False, "error": f"Error {r.status_code}: {r.text[:200]}"}

def sincronizar_productos(access_token, ml_user_id):
    """Descarga todos los productos/publicaciones del vendedor."""
    productos = []
    offset = 0
    limit = 50
    
    while True:
        resultado = llamar_api_ml(access_token,
            f"https://api.mercadolibre.com/users/{ml_user_id}/items/search",
            {"limit": limit, "offset": offset, "status": "active"}
        )
        if not resultado["ok"]:
            return {"ok": False, "error": resultado["error"]}
        
        datos = resultado["datos"]
        ids = datos.get("results", [])
        
        if not ids:
            break
        
        # Por cada ID, obtener detalles del producto
        for item_id in ids:
            detalle = llamar_api_ml(access_token,
                f"https://api.mercadolibre.com/items/{item_id}")
            if detalle["ok"]:
                item = detalle["datos"]
                productos.append({
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "price": item.get("price", 0),
                    "available_quantity": item.get("available_quantity", 0),
                    "condition": item.get("condition", "new"),
                    "average_rating": item.get("average_rating", 0),
                    "rating_count": item.get("rating_count", 0),
                    "permalink": item.get("permalink", ""),
                })
        
        offset += limit
        if offset >= datos.get("paging", {}).get("total", 0):
            break
    
    return {"ok": True, "productos": productos}

def sincronizar_ventas(access_token, ml_user_id, dias=90):
    """Descarga las ventas/ordenes de los ultimos N dias."""
    from datetime import timedelta
    desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S.000-00:00")
    hasta = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000-00:00")
    
    ventas = []
    offset = 0
    limit = 50
    
    while True:
        resultado = llamar_api_ml(access_token,
            "https://api.mercadolibre.com/orders/search",
            {
                "seller": ml_user_id,
                "order.date_created.from": desde,
                "order.date_created.to": hasta,
                "limit": limit,
                "offset": offset,
            }
        )
        if not resultado["ok"]:
            return {"ok": False, "error": resultado["error"]}
        
        datos = resultado["datos"]
        ordenes = datos.get("results", [])
        
        if not ordenes:
            break
        
        for orden in ordenes:
            for item in orden.get("order_items", []):
                item_data = item.get("item", {})
                ventas.append({
                    "order_id": orden.get("id", ""),
                    "item_id": item_data.get("id", ""),
                    "item_title": item_data.get("title", ""),
                    "quantity": item.get("quantity", 0),
                    "unit_price": item.get("unit_price", 0),
                    "total_amount": item.get("total_amount", 0) or item.get("unit_price", 0) * item.get("quantity", 1),
                    "commission": orden.get("total_amount", 0) * 0.16,  # ~16% comision ML
                    "shipping_cost": 0,  # se puede refinar despues
                    "date_created": orden.get("date_created", ""),
                    "status": orden.get("status", ""),
                })
        
        offset += limit
        if offset >= datos.get("paging", {}).get("total", 0):
            break
    
    return {"ok": True, "ventas": ventas}


# ============================================================
# FUNCION DE MATCHING: producto ML vs costos
# ============================================================
def hacer_match(productos_ml, costos_usuario):
    """Cruza productos de ML con costos por nombre (case-insensitive)."""
    costos_dict = {}
    for c in costos_usuario:
        nombre = c.get("nombre_producto", "").strip().lower()
        if nombre:
            costos_dict[nombre] = c
    
    resultado = []
    sin_costo = []
    
    for p in productos_ml:
        nombre_ml = p.get("title", "").strip().lower()
        costo_match = costos_dict.get(nombre_ml)
        
        if costo_match:
            resultado.append({
                **p,
                "costo_unitario": costo_match.get("costo_unitario", 0),
                "categoria": costo_match.get("categoria", ""),
                "proveedor": costo_match.get("proveedor", ""),
            })
        else:
            sin_costo.append(p)
    
    return resultado, sin_costo


# ============================================================
# ESTILOS CSS
# ============================================================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .card-login {
        background-color: #1a1d27; border: 1px solid #2a2d3a;
        border-radius: 12px; padding: 2rem; max-width: 420px; margin: 2rem auto;
    }
    .card-login h1 { color: #f0c040; text-align: center; font-size: 1.8rem; margin-bottom: 0.3rem; }
    .card-login .subtitle { color: #8899aa; text-align: center; margin-bottom: 1.5rem; font-size: 0.9rem; }
    .logo-astum {
        text-align: center; font-size: 2.2rem; font-weight: bold;
        color: #f0c040; margin-bottom: 0.2rem; letter-spacing: 4px;
    }
    .logo-astum small { color: #4a8fe0; font-size: 0.7rem; display: block; letter-spacing: 2px; }
    .stButton > button { width: 100%; border-radius: 8px; font-weight: 600; }
    .footer-saas { text-align: center; color: #444; font-size: 0.75rem; margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #222; }
    .paso-card {
        background-color: #1a1d27; border: 1px solid #2a2d3a;
        border-radius: 10px; padding: 1.2rem; margin-bottom: 1rem;
    }
    .paso-numero { color: #f0c040; font-weight: bold; font-size: 1.1rem; }
    .url-link {
        background-color: #0d1117; border: 1px solid #30363d;
        border-radius: 6px; padding: 0.6rem 1rem; color: #58a6ff;
        font-size: 0.85rem; word-break: break-all; font-family: monospace; margin: 0.5rem 0;
    }
    .metric-card {
        background-color: #1a1d27; border: 1px solid #2a2d3a;
        border-radius: 10px; padding: 1rem; text-align: center;
    }
    .metric-card .valor { font-size: 1.6rem; font-weight: bold; color: #f0c040; }
    .metric-card .label { color: #8899aa; font-size: 0.8rem; }
    .resaltado-ok { color: #3fb950; font-weight: bold; }
    .resaltado-warn { color: #d29922; font-weight: bold; }
    .resaltado-bad { color: #f85149; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# PAGINA DE LOGIN/REGISTRO
# ============================================================
def pagina_login():
    st.markdown('<div class="logo-astum">ASTUM <small>MERCADOLIBRE ANALYTICS</small></div>', unsafe_allow_html=True)
    st.markdown('<div class="card-login">', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🔑 Iniciar Sesión", "📝 Crear Cuenta"])
    
    with tab1:
        st.markdown('<h1>Bienvenido</h1><p class="subtitle">Ingresa con tu cuenta</p>', unsafe_allow_html=True)
        
        with st.form("form_login"):
            email = st.text_input("Email", placeholder="ejemplo@correo.cl")
            password = st.text_input("Contraseña", type="password", placeholder="••••••")
            submitted = st.form_submit_button("Iniciar Sesión", type="primary")
        
        if submitted:
            if not email or not password:
                st.error("Completa todos los campos")
            else:
                try:
                    db = get_db()
                    resultado = verificar_login(db, email, password)
                    if resultado is None:
                        st.error("Email o contraseña incorrectos")
                    elif isinstance(resultado, dict) and resultado.get("error") == "bloqueado":
                        mins = resultado.get("minutos", 15)
                        st.error(f"🚫 Demasiados intentos fallidos. Cuenta bloqueada por {mins} minutos.")
                        st.caption(f"Intenta de nuevo en {mins} minutos.")
                    else:
                        st.session_state["usuario"] = resultado
                        st.rerun()
                finally:
                    db.close()
    
    with tab2:
        st.markdown('<h1>Crear Cuenta</h1><p class="subtitle">Registra tu empresa para empezar</p>', unsafe_allow_html=True)
        with st.form("form_registro"):
            col1, col2 = st.columns(2)
            with col1:
                empresa = st.text_input("Nombre de tu empresa", placeholder="Ej: Rin SPA")
            with col2:
                nombre = st.text_input("Tu nombre", placeholder="Ej: Juan Pérez")
            email_reg = st.text_input("Email", placeholder="tu@correo.cl")
            pass_reg = st.text_input("Contraseña", type="password", placeholder="Mínimo 8 caracteres, 1 mayúscula, 1 número")
            pass_confirm = st.text_input("Repetir contraseña", type="password")
            submitted_reg = st.form_submit_button("Crear Cuenta", type="primary")
        
        if submitted_reg:
            if not all([empresa, nombre, email_reg, pass_reg, pass_confirm]):
                st.error("Completa todos los campos")
            elif pass_reg != pass_confirm:
                st.error("Las contraseñas no coinciden")
            elif len(pass_reg) < 8:
                st.error("La contraseña debe tener al menos 8 caracteres")
            elif not re.search(r'[A-Z]', pass_reg):
                st.error("La contraseña debe tener al menos 1 mayúscula")
            elif not re.search(r'[0-9]', pass_reg):
                st.error("La contraseña debe tener al menos 1 número")
            elif "@" not in email_reg:
                st.error("Ingresa un email válido")
            else:
                try:
                    db = get_db()
                    usuario = crear_usuario(db, email_reg, pass_reg, empresa, nombre)
                    if usuario:
                        st.success(f"✅ Cuenta creada para {empresa}! Ahora puedes iniciar sesión.")
                        st.info('👆 Haz click en la sección "Iniciar Sesión" para ingresar.')
                    else:
                        st.error("❌ Ese email ya está registrado.")
                finally:
                    db.close()
    
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="footer-saas">ASTUM Group © 2026 — AstumGroup.cl</div>', unsafe_allow_html=True)


# ============================================================
# SECCION: CONEXION ML
# ============================================================
def seccion_conexion_ml(usuario):
    db = get_db()
    token = obtener_token_ml(db, usuario["id"])
    db.close()
    
    st.subheader("🔗 Conexión MercadoLibre")
    
    if token:
        with st.spinner("Verificando conexión..."):
            token_activo = verificar_y_renovar_token(usuario["id"])
        
        if token_activo:
            expira_texto = token_expira_en_texto(token_activo.get("expires_at", "0"))
            st.success("✅ MercadoLibre conectado — renovación automática activa")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("ID Vendedor", token_activo.get("ml_user_id", "—"))
            with col2:
                st.metric("Próxima renovación", f"🔄 {expira_texto}")
            with col3:
                if st.button("🔌 Desconectar", use_container_width=True):
                    db = get_db()
                    db.execute("DELETE FROM tokens_ml WHERE user_id = ?", (usuario["id"],))
                    db.commit(); db.close()
                    st.rerun()
        else:
            st.error("❌ Token expirado. Conecta de nuevo.")
    
    if not token or not token.get("access_token"):
        st.warning("🔌 Aún no conectas tu cuenta de MercadoLibre")
        st.markdown("Sigue estos 3 pasos para conectar tu tienda:")
        url_ml = generar_url_autorizacion()
        
        st.markdown(f"""<div class="paso-card"><span class="paso-numero">Paso 1</span><br>
        <strong>Abre este link en una nueva pestaña:</strong>
        <div class="url-link">{url_ml}</div>
        <span style="color:#8b949e;font-size:0.85rem;">
        👉 Inicia sesión con tu cuenta de ML y haz clic en <strong>"Autorizar"</strong>
        </span></div>""", unsafe_allow_html=True)
        
        st.markdown(f"""<div class="paso-card"><span class="paso-numero">Paso 2</span><br>
        <strong>Te redirigirá a nuestra página</strong> y verás un código.
        <span style="color:#8b949e;display:block;font-size:0.85rem;margin-top:0.3rem;">
        📋 <strong>Copia ese código</strong> (ej: TG-1234567890)
        </span></div>""", unsafe_allow_html=True)
        
        st.markdown('<div class="paso-card"><span class="paso-numero">Paso 3</span><br>', unsafe_allow_html=True)
        st.markdown('<strong>Pega aquí el código y haz clic en "Conectar":</strong>', unsafe_allow_html=True)
        
        with st.form("form_conectar_ml"):
            codigo = st.text_input("Código de autorización",
                placeholder="Ej: TG-1234567890",
                help="Pega el código que apareció después de autorizar")
            if st.form_submit_button("🔗 Conectar MercadoLibre", type="primary"):
                if not codigo or len(codigo) < 5:
                    st.error("Ingresa el código completo")
                else:
                    with st.spinner("Conectando..."):
                        r = canjear_codigo_por_token(codigo.strip())
                    if r["ok"]:
                        d = r["datos"]
                        db = get_db()
                        guardar_token_ml(db, usuario["id"],
                            access_token=d["access_token"],
                            refresh_token=d.get("refresh_token", ""),
                            ml_user_id=str(d.get("user_id", "")),
                            expires_at=str(datetime.now().timestamp() + d.get("expires_in", 21600)),
                        )
                        db.close()
                        st.success("✅ ¡Conectado!")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(f"❌ {r['error']}")
        st.markdown('</div>', unsafe_allow_html=True)


# ============================================================
# SECCION: SINCRONIZAR DATOS
# ============================================================
def seccion_sincronizar(usuario):
    st.subheader("🔄 Sincronizar datos de MercadoLibre")
    
    token_cache = verificar_y_renovar_token(usuario["id"])
    if not token_cache:
        st.info("Primero conecta tu cuenta de MercadoLibre (sección anterior)")
        return
    
    access_token = token_cache["access_token"]
    ml_user_id = token_cache.get("ml_user_id", "")
    
    # Mostrar ultima sincro
    db = get_db()
    ultima = ultima_sincronizacion(db, usuario["id"])
    db.close()
    
    if ultima:
        st.caption(f"📅 Última sincronización: {ultima}")
    
    st.markdown("Al hacer clic, descargaremos tus **productos** y **ventas** de los últimos 90 días desde MercadoLibre.")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        if st.button("🔄 Sincronizar ahora", type="primary", use_container_width=True):
            with st.status("Descargando datos desde MercadoLibre...", expanded=True) as status:
                
                # PRODUCTOS
                st.write("📦 Descargando productos...")
                r_prod = sincronizar_productos(access_token, ml_user_id)
                
                if not r_prod["ok"]:
                    st.error(f"Error productos: {r_prod['error']}")
                    return
                
                db = get_db()
                n_prod = guardar_productos_ml(db, usuario["id"], r_prod["productos"])
                db.close()
                st.write(f"✅ {n_prod} productos descargados")
                
                # VENTAS
                st.write("📋 Descargando ventas...")
                r_ventas = sincronizar_ventas(access_token, ml_user_id)
                
                if not r_ventas["ok"]:
                    st.error(f"Error ventas: {r_ventas['error']}")
                    return
                
                db = get_db()
                n_ventas = guardar_ventas_ml(db, usuario["id"], r_ventas["ventas"])
                db.close()
                st.write(f"✅ {n_ventas} ventas descargadas")
                
                status.update(label="✅ Sincronización completada!", state="complete")
                st.balloons()
                time.sleep(1)
                st.rerun()
    
    with col2:
        # Mostrar resumen de lo que hay en BD
        db = get_db()
        prods = obtener_productos_ml(db, usuario["id"])
        vtas = obtener_ventas_ml(db, usuario["id"])
        db.close()
        
        if prods or vtas:
            m1, m2 = st.columns(2)
            with m1:
                st.metric("Productos en BD", len(prods))
            with m2:
                st.metric("Ventas en BD", len(vtas))
        else:
            st.info("Aún no hay datos. Sincroniza para empezar.")


# ============================================================
# SECCION: COSTOS (plantilla + upload)
# ============================================================
def seccion_costos(usuario):
    st.subheader("💰 Costos de tus productos")
    st.markdown("Sube un archivo CSV con los costos de tus productos para calcular la utilidad real.")
    
    # ─── PLANTILLA DESCARGABLE ───
    with st.expander("📥 Descargar plantilla CSV", expanded=False):
        st.markdown("""
        **Descarga esta plantilla**, llénala en Excel y súbela de vuelta.
        
        Columnas esperadas:
        - **nombre_producto**: El nombre exacto como aparece en MercadoLibre
        - **costo_unitario**: Lo que pagas por cada unidad (en pesos chilenos)
        - **categoria**: (opcional) Ej: Poleras, Calcetines, Camisas
        - **proveedor**: (opcional) Ej: Textil Chile, Importadora ABC
        """)
        
        # Generar CSV de ejemplo con productos textiles
        df_ejemplo = pd.DataFrame([
            ["Polera Algodón M/L", 6500, "Poleras", "Textil Chile"],
            ["Polera Algodón S", 5500, "Poleras", "Textil Chile"],
            ["Camisa Oxford Azul", 12000, "Camisas", "Importadora ABC"],
            ["Camisa Oxford Blanca", 12000, "Camisas", "Importadora ABC"],
            ["Calcetines Deporte", 2500, "Calcetines", "Textil Chile"],
            ["Calcetines Vestir", 3000, "Calcetines", "Textil Chile"],
            ["Primera Capa Térmica M", 8500, "Primeras Capas", "Thermal SA"],
            ["Primera Capa Térmica L", 9500, "Primeras Capas", "Thermal SA"],
        ], columns=["nombre_producto", "costo_unitario", "categoria", "proveedor"])
        
        csv_bytes = io.BytesIO()
        df_ejemplo.to_csv(csv_bytes, index=False, encoding="utf-8-sig")
        
        st.download_button(
            label="📥 Descargar plantilla CSV",
            data=csv_bytes.getvalue(),
            file_name="plantilla_costos_ml.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.caption("La plantilla incluye productos de ejemplo (textiles). Reemplázalos con los tuyos.")
    
    # ─── SUBIR CSV ───
    st.markdown("---")
    st.markdown("**Sube tu archivo CSV ya llenado:**")
    
    archivo = st.file_uploader(
        "Selecciona tu archivo CSV",
        type=["csv"],
        help="Debe tener las columnas: nombre_producto, costo_unitario"
    )
    
    if archivo:
        try:
            df = pd.read_csv(archivo)
            columnas = [c.strip().lower() for c in df.columns]
            
            # Validar columnas
            if "nombre_producto" not in columnas:
                st.error("❌ El archivo debe tener una columna llamada 'nombre_producto'")
                st.info("Descarga la plantilla de ejemplo para ver el formato correcto.")
                return
            
            if "costo_unitario" not in columnas:
                st.error("❌ El archivo debe tener una columna llamada 'costo_unitario'")
                return
            
            # Limpiar nombres de columnas
            df.columns = columnas
            
            # Validar datos
            n_productos = len(df)
            n_sin_costo = df["costo_unitario"].isna().sum()
            
            if n_sin_costo > 0:
                st.warning(f"⚠️ {n_sin_costo} productos sin costo asignado (se omitirán)")
                df = df.dropna(subset=["costo_unitario"])
            
            # Vista previa
            st.success(f"✅ {len(df)} productos cargados correctamente")
            with st.expander("👁️ Vista previa", expanded=False):
                st.dataframe(df.head(20), use_container_width=True)
            
            # Guardar
            if st.button("💾 Guardar costos en mi cuenta", type="primary", use_container_width=True):
                # Asegurar columnas esperadas
                for col in ["categoria", "proveedor", "sku"]:
                    if col not in df.columns:
                        df[col] = ""
                
                db = get_db()
                guardar_costos(db, usuario["id"], df)
                db.close()
                st.success(f"✅ {len(df)} costos guardados!")
                st.rerun()
        
        except Exception as e:
            st.error(f"❌ Error al leer el archivo: {str(e)}")
            st.info("Asegúrate de que sea un archivo CSV válido. Descarga la plantilla como referencia.")
    
    # Mostrar costos actuales
    db = get_db()
    costos = obtener_costos_usuario(db, usuario["id"])
    db.close()
    
    if costos:
        st.markdown("---")
        st.caption(f"📋 {len(costos)} productos con costo registrado")
        df_costos = pd.DataFrame(costos)
        with st.expander("Ver mis costos actuales"):
            cols_mostrar = [c for c in ["nombre_producto", "costo_unitario", "categoria", "proveedor"] if c in df_costos.columns]
            st.dataframe(df_costos[cols_mostrar], use_container_width=True, hide_index=True)


# ============================================================
# SECCION: DASHBOARD DE UTILIDAD
# ============================================================
def seccion_dashboard(usuario):
    st.subheader("📊 Utilidad Real")
    
    db = get_db()
    productos = obtener_productos_ml(db, usuario["id"])
    ventas = obtener_ventas_ml(db, usuario["id"])
    costos = obtener_costos_usuario(db, usuario["id"])
    db.close()
    
    if not productos or not ventas:
        st.info("📌 Para ver tu utilidad real necesitas:")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("✅ Sincronizar datos de MercadoLibre (sección anterior)")
        with col2:
            st.markdown("✅ Subir CSV con tus costos (sección anterior)")
        return
    
    if not costos:
        st.warning("⚠️ Tienes datos de ML pero **sin costos**. Sube tu CSV para calcular utilidad.")
        return
    
    # Hacer match productos ML vs costos
    productos_con_costo, productos_sin_costo = hacer_match(productos, costos)
    
    # Calcular metricas desde ventas
    df_ventas = pd.DataFrame(ventas)
    df_productos = pd.DataFrame(productos_con_costo)
    
    if df_ventas.empty:
        st.info("No hay ventas en el período sincronizado.")
        return
    
    # ─── METRICAS GLOBALES ───
    total_ingresos = df_ventas["total_amount"].sum()
    total_comisiones = df_ventas["commission"].sum()
    total_envios = df_ventas["shipping_cost"].sum()
    
    # Calcular costo de productos vendidos (match por nombre)
    costo_ventas = 0
    for _, v in df_ventas.iterrows():
        title = str(v.get("item_title", "")).strip().lower()
        for p in productos_con_costo:
            if p.get("title", "").strip().lower() == title:
                costo_ventas += float(p["costo_unitario"]) * int(v.get("quantity", 0))
                break
    
    total_costos = costo_ventas + total_comisiones + total_envios
    utilidad_neta = total_ingresos - total_costos
    margen = (utilidad_neta / total_ingresos * 100) if total_ingresos > 0 else 0
    
    # Tarjetas
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Ingresos Totales</div>
            <div class="valor">${total_ingresos:,.0f}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Costos Totales</div>
            <div class="valor" style="color:#f85149;">${total_costos:,.0f}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        color_util = "#3fb950" if utilidad_neta >= 0 else "#f85149"
        st.markdown(f"""<div class="metric-card">
            <div class="label">Utilidad Neta</div>
            <div class="valor" style="color:{color_util};">${utilidad_neta:,.0f}</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        color_marg = "#3fb950" if margen >= 0 else "#f85149"
        st.markdown(f"""<div class="metric-card">
            <div class="label">Margen</div>
            <div class="valor" style="color:{color_marg};">{margen:.1f}%</div>
        </div>""", unsafe_allow_html=True)
    
    st.caption(f"Ingresos: ${total_ingresos:,.0f} | Costo prod: ${costo_ventas:,.0f} | Comisiones ML: ${total_comisiones:,.0f} | Envíos: ${total_envios:,.0f}")
    
    st.divider()
    
    # ─── TOP PRODUCTOS ───
    col_izq, col_der = st.columns(2)
    
    with col_izq:
        st.subheader("🏆 Top 10 Más Rentables")
        utilidad_por_producto = []
        for p in productos_con_costo:
            nombre = p.get("title", "")
            ingresos_p = df_ventas[df_ventas["item_title"].str.strip().str.lower() == nombre.strip().lower()]["total_amount"].sum()
            cantidad_p = df_ventas[df_ventas["item_title"].str.strip().str.lower() == nombre.strip().lower()]["quantity"].sum()
            costo_prod_p = float(p.get("costo_unitario", 0)) * cantidad_p
            utilidad_p = ingresos_p - costo_prod_p + 1  # +1 para evitar 0
            if ingresos_p > 0:
                utilidad_por_producto.append({"producto": nombre, "utilidad": utilidad_p, "ingreso": ingresos_p})
        
        if utilidad_por_producto:
            df_top = pd.DataFrame(utilidad_por_producto).sort_values("utilidad", ascending=False).head(10)
            st.bar_chart(df_top.set_index("producto")["utilidad"], use_container_width=True)
        else:
            st.info("Sin datos suficientes")
    
    with col_der:
        st.subheader("⚠️ Alertas")
        
        # Productos sin costo
        if productos_sin_costo:
            with st.expander(f"📦 {len(productos_sin_costo)} productos sin costo asignado", expanded=True):
                for p in productos_sin_costo[:10]:
                    st.markdown(f"- {p.get('title', '')} — *sin costo*")
                if len(productos_sin_costo) > 10:
                    st.caption(f"... y {len(productos_sin_costo)-10} más")
        
        # Productos con margen negativo
        if utilidad_por_producto:
            df_malos = pd.DataFrame(utilidad_por_producto).sort_values("utilidad").head(5)
            with st.expander("📉 Productos con menor utilidad", expanded=False):
                for _, row in df_malos.iterrows():
                    st.markdown(f"- {row['producto']}: ${row['utilidad']:,.0f}")
        
        # Productos con rating bajo
        productos_con_rating = [p for p in productos if p.get("average_rating", 0) > 0]
        if productos_con_rating:
            df_rating = pd.DataFrame(productos_con_rating)
            bajos = df_rating[df_rating["average_rating"] < 3].sort_values("average_rating")
            if not bajos.empty:
                with st.expander("⭐ Productos con mal rating (< 3 estrellas)", expanded=False):
                    for _, row in bajos.iterrows():
                        st.markdown(f"- {row['title']}: ⭐ {row['average_rating']}/5 ({int(row['rating_count'])} reseñas)")
    
    st.divider()
    
    # ─── TABLA DETALLADA ───
    with st.expander("📋 Ver detalle de ventas sincronizadas", expanded=False):
        cols_show = ["date_created", "item_title", "quantity", "unit_price", "total_amount", "status"]
        cols_exist = [c for c in cols_show if c in df_ventas.columns]
        if cols_exist:
            st.dataframe(
                df_ventas[cols_exist].sort_values("date_created", ascending=False).head(100),
                use_container_width=True, hide_index=True
            )
            st.caption(f"Mostrando 100 de {len(df_ventas)} ventas")


# ============================================================
# DASHBOARD PRINCIPAL
# ============================================================
def pagina_dashboard():
    usuario = st.session_state["usuario"]
    
    # ─── AUTO-LOGOUT POR INACTIVIDAD (30 min) ───
    ahora = datetime.now()
    ultima_actividad = st.session_state.get("ultima_actividad")
    if ultima_actividad:
        if (ahora - ultima_actividad) > timedelta(minutes=30):
            del st.session_state["usuario"]
            st.warning("⏰ Sesión expirada por inactividad. Vuelve a iniciar sesión.")
            st.rerun()
    st.session_state["ultima_actividad"] = ahora
    
    # ─── BARRA SUPERIOR ───
    col_logo, col_user, col_logout = st.columns([3, 2, 1])
    with col_logo:
        st.markdown(f'<span class="logo-astum" style="font-size:1.3rem;letter-spacing:2px;">ASTUM <span style="font-size:0.7rem;color:#4a8fe0;">ML</span></span>', unsafe_allow_html=True)
    with col_user:
        st.markdown(f'<div style="text-align:right;color:#8899aa;padding-top:8px;">👤 {usuario["empresa"]} <span style="color:#555;">|</span> <span style="color:#4a8fe0;">{usuario["email"]}</span></div>', unsafe_allow_html=True)
    with col_logout:
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            del st.session_state["usuario"]
            st.rerun()
    
    st.divider()
    st.title(f"📊 {usuario['empresa']}")
    st.caption("Tu utilidad real en MercadoLibre — costos, comisiones y margen por producto")
    
    # ─── BARRA DE INFORMACION ───
    ultimo = usuario.get("ultimo_login", "")
    if ultimo:
        st.caption(f"👤 {usuario['nombre']} | 📧 {usuario['email']} | 🕐 Última conexión: {ultimo}")
    else:
        st.caption(f"👤 {usuario['nombre']} | 📧 {usuario['email']}")
    
    # ─── TABS DEL DASHBOARD ───
    tabs = ["🔗 Conectar ML", "🔄 Sincronizar", "💰 Mis Costos", "📊 Dashboard"]
    
    # Agregar pestaña de admin si el email es el admin
    ADMIN_EMAILS = ["tech@astumgroup.cl", "contacto@astumgroup.cl", "admin@astumgroup.cl"]
    if usuario.get("email", "").lower() in ADMIN_EMAILS:
        tabs.append("🔒 Admin")
    
    dashboard_tabs = st.tabs(tabs)
    tab_ml = dashboard_tabs[0]
    tab_sync = dashboard_tabs[1]
    tab_costos = dashboard_tabs[2]
    tab_dash = dashboard_tabs[3]
    tab_admin = dashboard_tabs[4] if len(dashboard_tabs) > 4 else None
    
    with tab_ml:
        seccion_conexion_ml(usuario)
    
    with tab_sync:
        seccion_sincronizar(usuario)
    
    with tab_costos:
        seccion_costos(usuario)
    
    with tab_dash:
        seccion_dashboard(usuario)
    
    if tab_admin:
        with tab_admin:
            seccion_admin(usuario)
    
    st.divider()
    st.markdown('<div class="footer-saas">ASTUM Group © 2026 | AstumGroup.cl | contacto@astumgroup.cl</div>', unsafe_allow_html=True)


# ============================================================
# SECCIÓN DE ADMINISTRACIÓN
# ============================================================
def seccion_admin(usuario):
    st.subheader("🔒 Panel de Administración")
    
    try:
        db = get_db()
        
        # ─── ESTADÍSTICAS ───
        stats = admin_obtener_stats(db)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("👥 Usuarios", stats["usuarios"])
        c2.metric("🔗 Conectados ML", stats["conectados"])
        c3.metric("📦 Productos", stats["productos"])
        c4.metric("🛒 Ventas", stats["ventas"])
        
        st.divider()
        
        # ─── LISTA DE USUARIOS ───
        st.markdown("#### 👥 Usuarios registrados")
        lista = admin_listar_usuarios(db)
        
        if not lista:
            st.info("No hay usuarios registrados.")
        else:
            for u in lista:
                cols = st.columns([3, 3, 2, 2, 1])
                cols[0].write(f"**{u['empresa']}**" if u['empresa'] else "*Sin empresa*")
                cols[1].write(u['email'])
                cols[2].write(u['fecha_registro'][:10] if u['fecha_registro'] else "-")
                ultimo = u.get("ultimo_login", "")
                cols[3].write(ultimo[:10] if ultimo else "Nunca")
                if cols[4].button("🗑️", key=f"del_{u['id']}"):
                    admin_eliminar_usuario(db, u['id'])
                    st.success(f"✅ Usuario {u['email']} eliminado.")
                    st.rerun()
        
        db.close()
    except Exception as e:
        st.error(f"Error: {e}")
        try:
            db.close()
        except:
            pass


# ============================================================
# PUNTO DE ENTRADA
# ============================================================
if "usuario" in st.session_state and st.session_state["usuario"]:
    pagina_dashboard()
else:
    pagina_login()
