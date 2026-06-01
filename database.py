"""
BASE DE DATOS SAAS - Vendedores MercadoLibre
============================================
SQLite - un solo archivo .db para todos los clientes.
Cada cliente tiene sus datos aislados por user_id.

USO:
    from database import get_db, crear_usuario, verificar_login
    
    db = get_db()
    crear_usuario(db, email, password, empresa, nombre)
    usuario = verificar_login(db, email, password)

NOTA PARA STREAMLIT CLOUD:
    SQLite en la nube es efímero — los datos se pierden cuando la app
    se reinicia (cada deploy o tras inactividad prolongada).
    Para datos persistentes reales, migrar a PostgreSQL (Supabase gratis).
"""

import sqlite3
import bcrypt
import os
import hashlib
import base64
from datetime import datetime

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

# ============================================================
# UBICACION DE LA BASE DE DATOS
# ============================================================
# En Streamlit Cloud: se crea en el mismo directorio que los scripts
DB_PATH = os.path.join(os.path.dirname(__file__), "saas_ml.db")
DB_PATH = os.path.abspath(DB_PATH)


# ============================================================
# CONEXION
# ============================================================
def get_db():
    """Abre conexion a la base de datos.
    Siempre llama a esta funcion, no crees conexiones directas."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # para acceder por nombre de columna
    conn.execute("PRAGMA journal_mode=DELETE")  # modo simple, el .db siempre tiene todos los datos
    return conn


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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    
    # --- ACTUALIZAR tabla costos: SKU opcional ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS costos_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sku TEXT DEFAULT '',
            nombre_producto TEXT NOT NULL,
            costo_unitario REAL NOT NULL,
            categoria TEXT DEFAULT '',
            proveedor TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES usuarios(id)
        )
    """)
    # Migrar datos si existen
    cursor.execute("""
        INSERT OR IGNORE INTO costos_v2 (id, user_id, sku, nombre_producto, costo_unitario, categoria, proveedor)
        SELECT id, user_id, sku, nombre_producto, costo_unitario, categoria, proveedor FROM costos
    """)
    cursor.execute("DROP TABLE IF EXISTS costos")
    cursor.execute("ALTER TABLE costos_v2 RENAME TO costos")
    
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
            "VALUES (?, ?, ?, ?, ?)",
            (email, password_hash, empresa, nombre, fecha),
        )
        db.commit()
        return dict(cursor.execute(
            "SELECT id, email, empresa, nombre, fecha_registro FROM usuarios WHERE id = ?",
            (cursor.lastrowid,)
        ).fetchone())
    except sqlite3.IntegrityError:
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
    usuario = cursor.execute(
        "SELECT * FROM usuarios WHERE email = ?", (email,)
    ).fetchone()
    
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
                "UPDATE usuarios SET password_hash = ? WHERE id = ?",
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
        cursor.execute("UPDATE usuarios SET ultimo_login = ? WHERE id = ?",
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
    
    registro = db.execute(
        "SELECT * FROM login_attempts WHERE email = ?", (email,)
    ).fetchone()
    
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
            db.execute("DELETE FROM login_attempts WHERE email = ?", (email,))
            db.commit()
            return False, 0
    except:
        return False, 0


def registrar_intento_fallido(db, email):
    """Registra un intento fallido. Si llega a 3, bloquea por 15 minutos."""
    from datetime import datetime, timedelta
    ahora = datetime.now()
    ahora_str = ahora.strftime("%Y-%m-%d %H:%M:%S")
    
    registro = db.execute(
        "SELECT * FROM login_attempts WHERE email = ?", (email,)
    ).fetchone()
    
    if registro:
        nuevos = registro["intentos"] + 1
        if nuevos >= 3:
            # Bloquear por 15 minutos
            bloqueo = (ahora + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
            db.execute("""
                UPDATE login_attempts 
                SET intentos = ?, ultimo_intento = ?, bloqueado_hasta = ?
                WHERE email = ?
            """, (nuevos, ahora_str, bloqueo, email))
        else:
            db.execute("""
                UPDATE login_attempts 
                SET intentos = ?, ultimo_intento = ?
                WHERE email = ?
            """, (nuevos, ahora_str, email))
    else:
        db.execute("""
            INSERT INTO login_attempts (email, intentos, ultimo_intento)
            VALUES (?, 1, ?)
        """, (email, ahora_str))
    
    db.commit()


def resetear_intentos(db, email):
    """Limpia los intentos fallidos tras un login exitoso."""
    db.execute("DELETE FROM login_attempts WHERE email = ?", (email,))
    db.commit()


def obtener_intentos_restantes(db, email):
    """Retorna cuántos intentos quedan antes del bloqueo."""
    registro = db.execute(
        "SELECT intentos FROM login_attempts WHERE email = ?", (email,)
    ).fetchone()
    if registro:
        return max(0, 3 - registro["intentos"])
    return 3  # Aún no ha fallado, tiene 3 intentos


def obtener_usuario_por_id(db, user_id):
    """Obtiene datos de un usuario por su ID."""
    cursor = db.cursor()
    usuario = cursor.execute(
        "SELECT id, email, empresa, nombre, fecha_registro FROM usuarios WHERE id = ?",
        (user_id,),
    ).fetchone()
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
    
    existe = cursor.execute(
        "SELECT id FROM tokens_ml WHERE user_id = ?", (user_id,)
    ).fetchone()
    
    if existe:
        cursor.execute("""
            UPDATE tokens_ml 
            SET access_token = ?, refresh_token = ?, ml_user_id = ?,
                expires_at = ?, actualizado_en = ?
            WHERE user_id = ?
        """, (enc_access, enc_refresh, ml_user_id, expires_at, ahora, user_id))
    else:
        cursor.execute("""
            INSERT INTO tokens_ml 
            (user_id, access_token, refresh_token, ml_user_id, expires_at, creado_en, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, enc_access, enc_refresh, ml_user_id, expires_at, ahora, ahora))
    
    db.commit()


def obtener_token_ml(db, user_id):
    """Obtiene el token ML de un usuario (desencriptado)."""
    cursor = db.cursor()
    token = cursor.execute(
        "SELECT * FROM tokens_ml WHERE user_id = ?", (user_id,)
    ).fetchone()
    
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
    cursor.execute("DELETE FROM costos WHERE user_id = ?", (user_id,))
    
    # Insertar nuevos
    for _, row in df_costos.iterrows():
        cursor.execute("""
            INSERT INTO costos (user_id, sku, nombre_producto, costo_unitario, categoria, proveedor)
            VALUES (?, ?, ?, ?, ?, ?)
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
    filas = cursor.execute(
        "SELECT sku, nombre_producto, costo_unitario, categoria, proveedor FROM costos WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    return [dict(f) for f in filas]


# ============================================================
# FUNCIONES DE DATOS SINCRONIZADOS DE ML
# ============================================================
def guardar_productos_ml(db, user_id, productos):
    """Guarda productos descargados de ML (reemplaza anteriores)."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.cursor()
    cursor.execute("DELETE FROM productos_ml WHERE user_id = ?", (user_id,))
    
    for p in productos:
        cursor.execute("""
            INSERT INTO productos_ml 
            (user_id, item_id, title, price, available_quantity, condition, 
             average_rating, rating_count, permalink, sincronizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    filas = cursor.execute(
        "SELECT * FROM productos_ml WHERE user_id = ? ORDER BY title",
        (user_id,),
    ).fetchall()
    return [dict(f) for f in filas]


def guardar_ventas_ml(db, user_id, ventas):
    """Guarda ventas descargadas de ML (reemplaza anteriores)."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.cursor()
    cursor.execute("DELETE FROM ventas_ml WHERE user_id = ?", (user_id,))
    
    for v in ventas:
        cursor.execute("""
            INSERT INTO ventas_ml 
            (user_id, order_id, item_id, item_title, quantity, unit_price,
             total_amount, commission, shipping_cost, date_created, status, sincronizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    filas = cursor.execute(
        "SELECT * FROM ventas_ml WHERE user_id = ? ORDER BY date_created DESC",
        (user_id,),
    ).fetchall()
    return [dict(f) for f in filas]


def ultima_sincronizacion(db, user_id):
    """Obtiene la fecha de la ultima sincronizacion."""
    cursor = db.cursor()
    result = cursor.execute(
        "SELECT MAX(sincronizado_en) as ultima FROM productos_ml WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return result["ultima"] if result and result["ultima"] else None
