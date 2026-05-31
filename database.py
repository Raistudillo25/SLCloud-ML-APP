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
import hashlib
import os
from datetime import datetime

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
            fecha_registro TEXT NOT NULL
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
            sku TEXT NOT NULL,
            nombre_producto TEXT NOT NULL,
            costo_unitario REAL NOT NULL,
            categoria TEXT DEFAULT '',
            proveedor TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES usuarios(id)
        )
    """)

    db.commit()
    db.close()


# ============================================================
# FUNCIONES DE USUARIO
# ============================================================
def _hash_password(password):
    """Encripta password con SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


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
    """Verifica email y password.
    Retorna el usuario si coincide, None si no."""
    password_hash = _hash_password(password)
    cursor = db.cursor()
    usuario = cursor.execute(
        "SELECT id, email, empresa, nombre, fecha_registro FROM usuarios "
        "WHERE email = ? AND password_hash = ?",
        (email, password_hash),
    ).fetchone()
    return dict(usuario) if usuario else None


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
    """Guarda o actualiza el token ML de un usuario."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.cursor()
    
    # Ver si ya existe un token para este usuario
    existe = cursor.execute(
        "SELECT id FROM tokens_ml WHERE user_id = ?", (user_id,)
    ).fetchone()
    
    if existe:
        cursor.execute("""
            UPDATE tokens_ml 
            SET access_token = ?, refresh_token = ?, ml_user_id = ?,
                expires_at = ?, actualizado_en = ?
            WHERE user_id = ?
        """, (access_token, refresh_token, ml_user_id, expires_at, ahora, user_id))
    else:
        cursor.execute("""
            INSERT INTO tokens_ml 
            (user_id, access_token, refresh_token, ml_user_id, expires_at, creado_en, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, access_token, refresh_token, ml_user_id, expires_at, ahora, ahora))
    
    db.commit()


def obtener_token_ml(db, user_id):
    """Obtiene el token ML de un usuario."""
    cursor = db.cursor()
    token = cursor.execute(
        "SELECT * FROM tokens_ml WHERE user_id = ?", (user_id,)
    ).fetchone()
    return dict(token) if token else None


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
