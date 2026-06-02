"""
BASE DE DATOS SAAS - Vendedores MercadoLibre
============================================
PostgreSQL (Supabase) - datos persistentes en la nube.
Cada cliente tiene sus datos aislados por user_id.

USO:
    from database import get_db, crear_usuario, verificar_login
    
    db = get_db()
    crear_usuario(db, email, password, empresa, nombre)
    usuario = verificar_login(db, email, password)
"""

import os
import hashlib
import base64
from datetime import datetime
import psycopg2

# ============================================================
# CONEXION A POSTGRESQL (Supabase)
# ============================================================
# Vienen de las variables de entorno en Streamlit Cloud
# o de un archivo .env en desarrollo local.

def _build_conn_string():
    """Construye parametros de conexión."""
    host = os.environ.get("NEON_HOST", "")
    port = os.environ.get("NEON_PORT", "5432")
    dbname = os.environ.get("NEON_DB", "")
    user = os.environ.get("NEON_USER", "")
    password = os.environ.get("NEON_PASSWORD", "")

    # Si hay variables de entorno (Streamlit Cloud), usarlas
    if host:
        return {"host": host, "port": port, "dbname": dbname, "user": user, "password": password}

    # Fallback: Neon para desarrollo local (parametros separados)
    return {
        "host": "ep-empty-wave-acte1y5q.sa-east-1.aws.neon.tech",
        "port": "5432",
        "dbname": "neondb",
        "user": "neondb_owner",
        "password": "npg_hYvVGW4M8zFq"
    }

import bcrypt

# ============================================================
# CLAVE PARA ENCRIPTAR TOKENS ML EN LA BD
# ============================================================
# Clave fija derivada del proyecto. Los tokens se guardan cifrados.
_FERNET_KEY = None

def _get_fernet():
    """Obtiene el objeto Fernet para encriptar/desencriptar tokens."""
    global _FERNET_KEY
    if _FERNET_KEY is None:
        from cryptography.fernet import Fernet
        seed = "z1icamOFSIagMoEusORZ9cA2nud10pq2_ASTUM_2026"
        key_bytes = hashlib.sha256(seed.encode()).digest()  # 32 bytes
        _FERNET_KEY = Fernet(base64.urlsafe_b64encode(key_bytes))
    return _FERNET_KEY


def encrypt_token(plain_text):
    if not plain_text:
        return ""
    return _get_fernet().encrypt(plain_text.encode()).decode()


def decrypt_token(encrypted_text):
    if not encrypted_text:
        return ""
    try:
        return _get_fernet().decrypt(encrypted_text.encode()).decode()
    except Exception:
        return ""

import psycopg2
from psycopg2.extras import RealDictCursor

# ============================================================
# POOL DE CONEXIONES SIMPLE
# ============================================================
_db_conn = None

def _get_cached_conn():
    """Reutiliza la conexión a BD abierta para evitar reconexiones lentas."""
    global _db_conn
    if _db_conn is None or _db_conn.closed:
        params = _build_conn_string()
        _db_conn = psycopg2.connect(
            **params,
            cursor_factory=RealDictCursor,
            sslmode="require",
            connect_timeout=15
        )
    return _db_conn


def get_db():
    """Obtiene conexión a PostgreSQL (con caché para evitar reconexiones)."""
    return _get_cached_conn()


def close_db():
    """Cierra la conexión global (llamar al cerrar sesión)."""
    global _db_conn
    if _db_conn and not _db_conn.closed:
        _db_conn.close()
        _db_conn = None


# ============================================================
# TABLAS
# ============================================================
def crear_tablas():
    """Crea todas las tablas si no existen.
    Llama esto UNA vez al iniciar la app."""
    db = get_db()
    cursor = db.cursor()

    # --- USUARIOS ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            empresa TEXT DEFAULT '',
            nombre TEXT DEFAULT '',
            fecha_registro TEXT NOT NULL,
            ultimo_login TEXT DEFAULT ''
        )
    """)

    # --- TOKENS DE MERCADOLIBRE (1 por usuario) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tokens_ml (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            ml_user_id TEXT DEFAULT '',
            expires_at TEXT DEFAULT '',
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES usuarios(id)
        )
    """)

    # --- COSTOS DE PRODUCTOS (muchos por usuario) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS costos (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            sku TEXT DEFAULT '',
            nombre_producto TEXT NOT NULL,
            costo_unitario REAL NOT NULL,
            categoria TEXT DEFAULT '',
            proveedor TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES usuarios(id)
        )
    """)
    
    # --- INTENTOS DE LOGIN (control anti-fuerza bruta) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            intentos INTEGER DEFAULT 0,
            ultimo_intento TEXT,
            bloqueado_hasta TEXT
        )
    """)

    db.commit()
    db.close()


def crear_tablas_ml():
    """Crea tablas para datos sincronizados de ML."""
    db = get_db()
    cursor = db.cursor()

    # --- PRODUCTOS DESCARGADOS DE ML ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos_ml (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            title TEXT NOT NULL,
            price REAL DEFAULT 0,
            available_quantity INTEGER DEFAULT 0,
            condition TEXT DEFAULT 'new',
            average_rating REAL DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            permalink TEXT DEFAULT '',
            sincronizado_en TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES usuarios(id)
        )
    """)

    # --- VENTAS DESCARGADAS DE ML ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ventas_ml (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            order_id TEXT NOT NULL,
            item_id TEXT DEFAULT '',
            item_title TEXT DEFAULT '',
            quantity INTEGER DEFAULT 0,
            unit_price REAL DEFAULT 0,
            total_amount REAL DEFAULT 0,
            commission REAL DEFAULT 0,
            shipping_cost REAL DEFAULT 0,
            date_created TEXT DEFAULT '',
            status TEXT DEFAULT '',
            sincronizado_en TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES usuarios(id)
        )
    """)

    db.commit()
    db.close()


# ============================================================
# FUNCIONES DE USUARIO
# ============================================================
def _hash_password(password):
    """Encripta password con bcrypt (estándar seguro)."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _es_hash_sha256(hash_str):
    """Detecta si un hash es SHA-256 (64 caracteres hex) para migración."""
    import hashlib
    return len(hash_str) == 64 and all(c in '0123456789abcdef' for c in hash_str.lower())


def crear_usuario(db, email, password, empresa="", nombre=""):
    """Crea un usuario nuevo.
    Retorna el usuario creado o None si el email ya existe."""
    password_hash = _hash_password(password)
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO usuarios (email, password_hash, empresa, nombre, fecha_registro) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (email, password_hash, empresa, nombre, fecha),
        )
        user_id = cursor.fetchone()["id"]
        db.commit()
        cursor.execute(
            "SELECT id, email, empresa, nombre, fecha_registro FROM usuarios WHERE id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    except psycopg2.IntegrityError:
        return None  # email ya existe


def verificar_login(db, email, password):
    """Verifica email y password con bcrypt.
    Controla intentos fallidos: 3 fallos = bloqueo 15 min.
    Migra automáticamente usuarios con hash SHA-256 antiguo."""
    import hashlib
    
    # 1. Verificar si está bloqueado
    bloqueado, minutos = verificar_bloqueo(db, email)
    if bloqueado:
        return {"error": "bloqueado", "minutos": minutos}
    
    cursor = db.cursor()
    
    # 2. Buscar usuario por email
    cursor.execute(
        "SELECT * FROM usuarios WHERE email = %s", (email,)
    )
    usuario = cursor.fetchone()
    
    if not usuario:
        # Email no existe → registrar intento fallido igual
        registrar_intento_fallido(db, email)
        return None
    
    stored_hash = usuario["password_hash"]
    password_bytes = password.encode()
    login_ok = False
    
    # 3. Verificar password
    if _es_hash_sha256(stored_hash):
        if hashlib.sha256(password_bytes).hexdigest() == stored_hash:
            login_ok = True
            # Migrar a bcrypt
            nuevo_hash = _hash_password(password)
            cursor.execute(
                "UPDATE usuarios SET password_hash = %s WHERE id = %s",
                (nuevo_hash, usuario["id"]),
            )
            db.commit()
    else:
        if bcrypt.checkpw(password_bytes, stored_hash.encode()):
            login_ok = True
    
    # 4. Gestionar intentos
    if login_ok:
        resetear_intentos(db, email)
        # Guardar última conexión
        ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE usuarios SET ultimo_login = %s WHERE id = %s",
                       (ahora_str, usuario["id"]))
        db.commit()
        usuario = dict(usuario)
        usuario["ultimo_login"] = ahora_str
        return usuario
    else:
        registrar_intento_fallido(db, email)
        # Verificar si con este fallo se bloqueó
        bloqueado, minutos = verificar_bloqueo(db, email)
        if bloqueado:
            return {"error": "bloqueado", "minutos": minutos}
        return None


# ============================================================
# CONTROL DE INTENTOS DE LOGIN (anti-fuerza bruta)
# ============================================================
def verificar_bloqueo(db, email):
    """Revisa si un email está bloqueado por muchos intentos fallidos.
    Retorna (bloqueado: bool, minutos_restantes: int)."""
    from datetime import datetime
    ahora = datetime.now()
    
    cur = db.cursor()
    cur.execute(
        "SELECT * FROM login_attempts WHERE email = %s", (email,)
    )
    registro = cur.fetchone()
    
    if not registro:
        return False, 0  # Nunca ha intentado, no hay bloqueo
    
    bloqueado_hasta = registro["bloqueado_hasta"]
    if not bloqueado_hasta:
        return False, 0  # No está bloqueado
    
    try:
        hasta = datetime.strptime(bloqueado_hasta, "%Y-%m-%d %H:%M:%S")
        if ahora < hasta:
            minutos = int((hasta - ahora).total_seconds() / 60)
            return True, minutos + 1
        else:
            # Ya pasó el bloqueo, limpiar
            db.cursor().execute("DELETE FROM login_attempts WHERE email = %s", (email,))
            db.commit()
            return False, 0
    except:
        return False, 0


def registrar_intento_fallido(db, email):
    """Registra un intento fallido. Si llega a 3, bloquea por 15 minutos."""
    from datetime import datetime, timedelta
    ahora = datetime.now()
    ahora_str = ahora.strftime("%Y-%m-%d %H:%M:%S")
    
    cur = db.cursor()
    cur.execute(
        "SELECT * FROM login_attempts WHERE email = %s", (email,)
    )
    registro = cur.fetchone()
    
    if registro:
        nuevos = registro["intentos"] + 1
        if nuevos >= 3:
            # Bloquear por 15 minutos
            bloqueo = (ahora + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
            db.cursor().execute("""
                UPDATE login_attempts 
                SET intentos = %s, ultimo_intento = %s, bloqueado_hasta = %s
                WHERE email = %s
            """, (nuevos, ahora_str, bloqueo, email))
        else:
            db.cursor().execute("""
                UPDATE login_attempts 
                SET intentos = %s, ultimo_intento = %s
                WHERE email = %s
            """, (nuevos, ahora_str, email))
    else:
        db.cursor().execute("""
            INSERT INTO login_attempts (email, intentos, ultimo_intento)
            VALUES (%s, 1, %s)
        """, (email, ahora_str))
    
    db.commit()


def resetear_intentos(db, email):
    """Limpia los intentos fallidos tras un login exitoso."""
    db.cursor().execute("DELETE FROM login_attempts WHERE email = %s", (email,))
    db.commit()


def obtener_intentos_restantes(db, email):
    """Retorna cuántos intentos quedan antes del bloqueo."""
    cur = db.cursor()
    cur.execute(
        "SELECT intentos FROM login_attempts WHERE email = %s", (email,)
    )
    registro = cur.fetchone()
    if registro:
        return max(0, 3 - registro["intentos"])
    return 3  # Aún no ha fallado, tiene 3 intentos


def obtener_usuario_por_id(db, user_id):
    """Obtiene datos de un usuario por su ID."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT id, email, empresa, nombre, fecha_registro FROM usuarios WHERE id = %s",
        (user_id,),
    )
    usuario = cursor.fetchone()
    return dict(usuario) if usuario else None


# ============================================================
# FUNCIONES DE TOKENS ML
# ============================================================
def guardar_token_ml(db, user_id, access_token, refresh_token, ml_user_id="", expires_at=""):
    """Guarda o actualiza el token ML de un usuario (encriptado)."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.cursor()
    
    # Encriptar tokens antes de guardar
    enc_access = encrypt_token(access_token)
    enc_refresh = encrypt_token(refresh_token)
    cursor.execute(
        "SELECT id FROM tokens_ml WHERE user_id = %s", (user_id,)
    )
    existe = cursor.fetchone()
    
    if existe:
        cursor.execute("""
            UPDATE tokens_ml 
            SET access_token = %s, refresh_token = %s, ml_user_id = %s,
                expires_at = %s, actualizado_en = %s
            WHERE user_id = %s
        """, (enc_access, enc_refresh, ml_user_id, expires_at, ahora, user_id))
    else:
        cursor.execute("""
            INSERT INTO tokens_ml 
            (user_id, access_token, refresh_token, ml_user_id, expires_at, creado_en, actualizado_en)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, enc_access, enc_refresh, ml_user_id, expires_at, ahora, ahora))
    
    db.commit()


def obtener_token_ml(db, user_id):
    """Obtiene el token ML de un usuario (desencriptado)."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM tokens_ml WHERE user_id = %s", (user_id,)
    )
    token = cursor.fetchone()
    
    if not token:
        return None
    
    token = dict(token)
    # Desencriptar tokens al leer
    token["access_token"] = decrypt_token(token.get("access_token", ""))
    token["refresh_token"] = decrypt_token(token.get("refresh_token", ""))
    return token


# ============================================================
# FUNCIONES DE COSTOS
# ============================================================
def guardar_costos(db, user_id, df_costos):
    """Guarda los costos de un usuario desde un DataFrame.
    Elimina los anteriores y pone los nuevos (reemplazo total)."""
    cursor = db.cursor()
    # Eliminar costos anteriores
    cursor.execute("DELETE FROM costos WHERE user_id = %s", (user_id,))
    
    # Insertar nuevos
    for _, row in df_costos.iterrows():
        cursor.execute("""
            INSERT INTO costos (user_id, sku, nombre_producto, costo_unitario, categoria, proveedor)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            row.get("sku_producto", ""),
            row.get("nombre_producto", ""),
            float(row.get("costo_unitario", 0)),
            row.get("categoria", ""),
            row.get("proveedor", ""),
        ))
    
    db.commit()


def obtener_costos_usuario(db, user_id):
    """Obtiene los costos de un usuario como lista de diccionarios."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT sku, nombre_producto, costo_unitario, categoria, proveedor FROM costos WHERE user_id = %s",
        (user_id,),
    )
    filas = cursor.fetchall()
    return [dict(f) for f in filas]


# ============================================================
# FUNCIONES DE DATOS SINCRONIZADOS DE ML
# ============================================================
def guardar_productos_ml(db, user_id, productos):
    """Guarda productos descargados de ML (reemplaza anteriores)."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.cursor()
    cursor.execute("DELETE FROM productos_ml WHERE user_id = %s", (user_id,))
    
    for p in productos:
        cursor.execute("""
            INSERT INTO productos_ml 
            (user_id, item_id, title, price, available_quantity, condition, 
             average_rating, rating_count, permalink, sincronizado_en)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            p.get("id", ""),
            p.get("title", ""),
            float(p.get("price", 0)),
            int(p.get("available_quantity", 0)),
            p.get("condition", "new"),
            float(p.get("average_rating", 0)),
            int(p.get("rating_count", 0)),
            p.get("permalink", ""),
            ahora,
        ))
    
    db.commit()
    return len(productos)


def obtener_productos_ml(db, user_id):
    """Obtiene los productos ML guardados de un usuario."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM productos_ml WHERE user_id = %s ORDER BY title",
        (user_id,),
    )
    filas = cursor.fetchall()
    return [dict(f) for f in filas]


def guardar_ventas_ml(db, user_id, ventas):
    """Guarda ventas descargadas de ML (reemplaza anteriores)."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.cursor()
    cursor.execute("DELETE FROM ventas_ml WHERE user_id = %s", (user_id,))
    
    for v in ventas:
        cursor.execute("""
            INSERT INTO ventas_ml 
            (user_id, order_id, item_id, item_title, quantity, unit_price,
             total_amount, commission, shipping_cost, date_created, status, sincronizado_en)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            v.get("order_id", ""),
            v.get("item_id", ""),
            v.get("item_title", ""),
            int(v.get("quantity", 0)),
            float(v.get("unit_price", 0)),
            float(v.get("total_amount", 0)),
            float(v.get("commission", 0)),
            float(v.get("shipping_cost", 0)),
            v.get("date_created", ""),
            v.get("status", ""),
            ahora,
        ))
    
    db.commit()
    return len(ventas)


def obtener_ventas_ml(db, user_id):
    """Obtiene las ventas ML guardadas de un usuario."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM ventas_ml WHERE user_id = %s ORDER BY date_created DESC",
        (user_id,),
    )
    filas = cursor.fetchall()
    return [dict(f) for f in filas]


def ultima_sincronizacion(db, user_id):
    """Obtiene la fecha de la ultima sincronizacion."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT MAX(sincronizado_en) as ultima FROM productos_ml WHERE user_id = %s",
        (user_id,),
    )
    result = cursor.fetchone()
    return result["ultima"] if result and result["ultima"] else None


# ============================================================
# FUNCIONES DE ADMINISTRACIÓN
# ============================================================
def admin_listar_usuarios(db):
    """Lista todos los usuarios registrados (para panel de admin)."""
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, email, empresa, nombre, fecha_registro, ultimo_login
        FROM usuarios
        ORDER BY id
    """)
    filas = cursor.fetchall()
    return [dict(f) for f in filas]


def admin_eliminar_usuario(db, user_id):
    """Elimina un usuario y todos sus datos asociados."""
    cursor = db.cursor()
    cursor.execute("DELETE FROM login_attempts WHERE email = (SELECT email FROM usuarios WHERE id = %s)", (user_id,))
    cursor.execute("DELETE FROM tokens_ml WHERE user_id = %s", (user_id,))
    cursor.execute("DELETE FROM costos WHERE user_id = %s", (user_id,))
    cursor.execute("DELETE FROM productos_ml WHERE user_id = %s", (user_id,))
    cursor.execute("DELETE FROM ventas_ml WHERE user_id = %s", (user_id,))
    cursor.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))
    db.commit()
    return True


def admin_resetear_intentos(db, email):
    """Resetea los intentos fallidos de un usuario."""
    cursor = db.cursor()
    cursor.execute("DELETE FROM login_attempts WHERE email = %s", (email,))
    db.commit()
    return True


def admin_obtener_stats(db):
    """Obtiene estadísticas generales del sistema."""
    cursor = db.cursor()
    
    cursor.execute("SELECT COUNT(*) as total FROM usuarios")
    total_usuarios = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(*) as total FROM tokens_ml")
    total_conectados = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(*) as total FROM productos_ml")
    total_productos = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(*) as total FROM ventas_ml")
    total_ventas = cursor.fetchone()["total"]
    
    return {
        "usuarios": total_usuarios,
        "conectados": total_conectados,
        "productos": total_productos,
        "ventas": total_ventas
    }
