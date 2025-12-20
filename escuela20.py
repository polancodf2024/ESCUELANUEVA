"""
escuela10.py - Sistema de Gestión Escuela de Enfermería
Versión actualizada para usar SQLite con BCRYPT y estructura unificada
CONFIGURACIÓN MEDIANTE SECRETS.TOML - USANDO db_escuela
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from io import StringIO, BytesIO
import time
import hashlib
import base64
import warnings
import sqlite3
from contextlib import contextmanager
import logging
import bcrypt
warnings.filterwarnings('ignore')

# =============================================
# CONFIGURACIÓN MEDIANTE SECRETS.TOML
# =============================================
# Lee las configuraciones del archivo secrets.toml

# Configuración de logging primero para poder registrar
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Verificar si estamos en modo supervisor (servidor remoto)
try:
    SUPERVISOR_MODE = st.secrets.get("supervisor_mode", False)
    DEBUG_MODE = st.secrets.get("debug_mode", False)
    
    # Configuración SSH para servidor remoto (solo en supervisor_mode)
    REMOTE_HOST = st.secrets.get("remote_host", "")
    REMOTE_PORT = st.secrets.get("remote_port", 22)
    REMOTE_USER = st.secrets.get("remote_user", "")
    REMOTE_PASSWORD = st.secrets.get("remote_password", "")
    REMOTE_DIR = st.secrets.get("remote_dir", "")
    
    # Obtener rutas específicas del secrets.toml
    # USAR db_escuela DEL SECRETS.TOML COMO SOLICITASTE
    PATHS = st.secrets.get("paths", {})
    BASE_PATH = PATHS.get("base_path", "")
    DB_ESCUELA = PATHS.get("db_escuela", "")  # Esta es la variable clave
    DB_INSCRITOS = PATHS.get("db_inscritos", "")
    UPLOADS_PATH = PATHS.get("uploads_path", "")
    
    # Configuración de correo
    SMTP_SERVER = st.secrets.get("smtp_server", "")
    SMTP_PORT = st.secrets.get("smtp_port")
    EMAIL_USER = st.secrets.get("email_user", "")
    EMAIL_PASSWORD = st.secrets.get("email_password", "")
    NOTIFICATION_EMAIL = st.secrets.get("notification_email", "")
    
    # Determinar el entorno basado en supervisor_mode
    if SUPERVISOR_MODE:
        ENTORNO = "servidor"
        logger.info("✅ Modo supervisor activado - Usando configuración de servidor remoto")
        
        # Validar que db_escuela esté configurado
        if not DB_ESCUELA:
            logger.warning("⚠️ db_escuela no está configurado en secrets.toml")
            DB_ESCUELA = "escuela.db"  # Nombre simple por defecto
            logger.info(f"Usando valor por defecto: {DB_ESCUELA}")
        else:
            logger.info(f"📁 Base de datos configurada (db_escuela): {DB_ESCUELA}")
    else:
        ENTORNO = "laptop"
        logger.info("💻 Modo local activado")
        
except Exception as e:
    # Valores por defecto si no hay secrets.toml
    logger.warning(f"No se pudo cargar secrets.toml: {e}")
    SUPERVISOR_MODE = False
    ENTORNO = "laptop"  # Por defecto modo laptop
    DB_ESCUELA = "escuela.db"  # Nombre por defecto local

# Configuraciones por entorno usando las variables de secrets
CONFIG_PATHS = {
    "servidor": {
        "base_path": BASE_PATH if BASE_PATH else ".",
        "db_path": DB_ESCUELA,  # USAR DB_ESCUELA DEL SECRETS.TOML
        "uploads_path": UPLOADS_PATH if UPLOADS_PATH else "uploads"
    },
    "laptop": {
        "base_path": ".",
        "db_path": "escuela.db",
        "uploads_path": "uploads"
    }
}

# Configuración activa basada en ENTORNO
CONFIG = CONFIG_PATHS[ENTORNO]

# Configuración de página
st.set_page_config(
    page_title="Sistema Escuela Enfermería",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# FUNCIÓN PARA MOSTRAR INFORMACIÓN DE CONFIGURACIÓN EN EL SIDEBAR
# =============================================================================

def mostrar_info_configuracion():
    """Muestra información de configuración en el sidebar"""
    st.sidebar.title("⚙️ Configuración")
    
    # Mostrar entorno actual
    entorno_display = "🌍 Servidor Remoto" if ENTORNO == "servidor" else "💻 Laptop Local"
    st.sidebar.info(f"**{entorno_display}**")
    
    # Mostrar información de la base de datos
    with st.sidebar.expander("📊 Base de Datos"):
        db_name = os.path.basename(CONFIG["db_path"])
        st.info(f"**Archivo:** {db_name}")
        
        # Mostrar ruta de forma segura
        if ENTORNO == "servidor":
            st.success("✅ Conectado a base de datos remota")
            # Solo mostrar el nombre del archivo, no la ruta completa
            st.info("**Configuración:** Desde secrets.toml")
    
    # Mostrar información del sistema
    with st.sidebar.expander("📋 Información del Sistema"):
        st.info("**Versión:** 10.0 (SQLite + BCRYPT + Secrets)")
        st.info(f"**Supervisor Mode:** {'✅ Activado' if SUPERVISOR_MODE else '❌ Desactivado'}")
        st.info(f"**Debug Mode:** {'✅ Activado' if DEBUG_MODE else '❌ Desactivado'}")
        
        # Mostrar información de correo si está configurado
        if 'EMAIL_USER' in globals() and EMAIL_USER:
            email_name = EMAIL_USER.split('@')[0] if '@' in EMAIL_USER else EMAIL_USER
            st.info(f"**Email Notificaciones:** {email_name}@...")
    
    st.sidebar.markdown("---")
    st.sidebar.info("**Características:**")
    st.sidebar.info("✅ Autenticación BCRYPT")
    st.sidebar.info("✅ Base de datos SQLite")
    st.sidebar.info("✅ Configuración por secrets.toml")
    st.sidebar.info("✅ Gestión completa")

# =============================================================================
# SISTEMA DE BASE DE DATOS SQLITE - ACTUALIZADO CON SECRETS.TOML
# =============================================================================

class SistemaBaseDatos:
    def __init__(self, db_path=None):
        # Usar la ruta configurada por entorno o la proporcionada
        if db_path is None:
            self.db_path = CONFIG["db_path"]
            logger.info(f"Base de datos configurada: {self.db_path}")
            
            # Información adicional
            if ENTORNO == "servidor":
                logger.info(f"Usando db_escuela del secrets.toml")
        else:
            self.db_path = db_path
        
        # Si estamos en modo servidor y la ruta es remota, mostrar información
        if ENTORNO == "servidor":
            logger.info(f"🔗 Modo servidor activado")
            if SUPERVISOR_MODE:
                logger.info("📡 Supervisor mode: Conectando a servidor remoto")
        
        logger.info(f"Base de datos escuela inicializada")
        
        # Crear directorio si no existe (solo en modo local para archivos relativos)
        if ENTORNO == "laptop":
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                try:
                    os.makedirs(db_dir, exist_ok=True)
                    logger.info(f"Directorio creado para base de datos")
                except Exception as e:
                    logger.warning(f"No se pudo crear directorio: {e}")
                    # Usar directorio actual como fallback
                    self.db_path = "escuela.db"
        
        # Inicializar tablas con manejo de errores
        try:
            self.init_tablas()
        except Exception as e:
            logger.error(f"Error inicializando tablas: {e}")
            # Intentar crear una base de datos mínima
            try:
                conn = sqlite3.connect(self.db_path)
                conn.close()
                logger.info(f"Base de datos básica creada")
                # Reintentar inicialización
                self.init_tablas()
            except Exception as db_error:
                logger.error(f"Error crítico: {db_error}")
                # Si estamos en modo servidor, podría ser un problema de conexión
                if ENTORNO == "servidor":
                    st.warning(f"⚠️ Posible problema de conexión con la base de datos remota")
                raise
    
    @contextmanager
    def get_connection(self):
        """Context manager para manejar conexiones a la base de datos"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            yield conn
            if conn:
                conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error en transacción de base de datos: {e}")
            
            # Mostrar mensaje más informativo según el entorno
            if ENTORNO == "servidor":
                st.warning(f"⚠️ Error conectando a la base de datos remota. Verifique la configuración en secrets.toml")
            raise e
        finally:
            if conn:
                conn.close()
    
    def init_tablas(self):
        """Inicializar tablas de la base de datos si no existen"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabla de usuarios - COMPATIBLE CON MIGRACION10
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT,
                    rol TEXT NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT,
                    matricula TEXT UNIQUE,
                    activo INTEGER DEFAULT 1,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Intentar agregar columna 'nombre' si se necesita para compatibilidad
            try:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN nombre TEXT")
            except sqlite3.OperationalError:
                pass  # La columna ya existe o no se puede agregar
            
            # Tabla de inscritos - COMPATIBLE CON MIGRACION10
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS inscritos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT NOT NULL,
                    telefono TEXT,
                    programa_interes TEXT,
                    fecha_registro TIMESTAMP NOT NULL,
                    estatus TEXT DEFAULT 'Pre-inscrito',
                    folio TEXT UNIQUE,
                    fecha_nacimiento DATE,
                    como_se_entero TEXT,
                    documentos_subidos INTEGER DEFAULT 0,
                    documentos_guardados TEXT,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla de estudiantes - COMPATIBLE CON MIGRACION10
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS estudiantes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    programa TEXT NOT NULL,
                    email TEXT,
                    telefono TEXT,
                    fecha_nacimiento DATE,
                    genero TEXT,
                    fecha_inscripcion TIMESTAMP,
                    estatus TEXT,
                    documentos_subidos TEXT,
                    fecha_registro TIMESTAMP,
                    programa_interes TEXT,
                    folio TEXT,
                    como_se_entero TEXT,
                    fecha_ingreso DATE,
                    usuario TEXT
                )
            ''')
            
            # Tabla de egresados - COMPATIBLE CON MIGRACION10
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS egresados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    programa_original TEXT,
                    fecha_graduacion DATE,
                    nivel_academico TEXT,
                    email TEXT,
                    telefono TEXT,
                    estado_laboral TEXT,
                    fecha_actualizacion DATE,
                    documentos_subidos TEXT
                )
            ''')
            
            # Tabla de contratados - COMPATIBLE CON MIGRACION10
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS contratados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    fecha_contratacion DATE,
                    puesto TEXT,
                    departamento TEXT,
                    estatus TEXT,
                    salario TEXT,
                    tipo_contrato TEXT,
                    fecha_inicio DATE,
                    fecha_fin DATE,
                    documentos_subidos TEXT
                )
            ''')
            
            # Tabla de bitácora - COMPATIBLE CON MIGRACION10
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bitacora (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usuario TEXT NOT NULL,
                    accion TEXT NOT NULL,
                    detalles TEXT,
                    ip TEXT
                )
            ''')
            
            # Tabla adicional para seguimiento de documentos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS documentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT NOT NULL,
                    tipo_documento TEXT NOT NULL,
                    nombre_archivo TEXT NOT NULL,
                    ruta_archivo TEXT,
                    fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    estado TEXT DEFAULT 'Pendiente',
                    observaciones TEXT
                )
            ''')
            
            # Tabla para cursos/programas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS programas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT UNIQUE NOT NULL,
                    nombre TEXT NOT NULL,
                    descripcion TEXT,
                    duracion_meses INTEGER,
                    costo DECIMAL(10,2),
                    modalidad TEXT,
                    estatus TEXT DEFAULT 'Activo',
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Índices para mejorar rendimiento
            indices = [
                ('idx_usuarios_usuario', 'usuarios(usuario)'),
                ('idx_usuarios_matricula', 'usuarios(matricula)'),
                ('idx_usuarios_rol', 'usuarios(rol)'),
                ('idx_inscritos_matricula', 'inscritos(matricula)'),
                ('idx_inscritos_estatus', 'inscritos(estatus)'),
                ('idx_estudiantes_matricula', 'estudiantes(matricula)'),
                ('idx_egresados_matricula', 'egresados(matricula)'),
                ('idx_contratados_matricula', 'contratados(matricula)'),
                ('idx_bitacora_fecha', 'bitacora(timestamp)'),
                ('idx_documentos_matricula', 'documentos(matricula)')
            ]
            
            for nombre_idx, definicion in indices:
                try:
                    cursor.execute(f'CREATE INDEX IF NOT EXISTS {nombre_idx} ON {definicion}')
                except:
                    pass  # Ignorar errores de índice
            
            # Verificar si ya existe un usuario admin antes de intentar insertarlo
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE usuario = 'admin'")
            admin_exists = cursor.fetchone()[0] > 0
            
            if not admin_exists:
                # Insertar usuario administrador por defecto si no existe - USANDO BCRYPT
                password = "Admin123!"  # Contraseña por defecto
                password_hash_str, salt_hex = self.hash_password(password)
                
                try:
                    cursor.execute('''
                        INSERT INTO usuarios 
                        (usuario, password_hash, salt, rol, nombre_completo, nombre, email, matricula)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        'admin',
                        password_hash_str,
                        salt_hex,
                        'administrador',
                        'Administrador del Sistema',
                        'Administrador del Sistema',
                        'admin@escuela.edu.mx',
                        'ADMIN-001'
                    ))
                    logger.info("✅ Usuario administrador por defecto creado con BCRYPT")
                except sqlite3.IntegrityError as e:
                    if "usuarios.matricula" in str(e):
                        # Intentar con una matrícula diferente
                        cursor.execute('''
                            INSERT INTO usuarios 
                            (usuario, password_hash, salt, rol, nombre_completo, nombre, email, matricula)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            'admin',
                            password_hash_str,
                            salt_hex,
                            'administrador',
                            'Administrador del Sistema',
                            'Administrador del Sistema',
                            'admin@escuela.edu.mx',
                            f'ADMIN-{int(time.time())}'
                        ))
                        logger.info("✅ Usuario administrador creado con matrícula única (BCRYPT)")
                    else:
                        raise e
            
            # Verificar si existen programas de ejemplo
            cursor.execute("SELECT COUNT(*) FROM programas")
            programas_count = cursor.fetchone()[0]
            
            if programas_count == 0:
                programas_ejemplo = [
                    ('ESP-CARDIO', 'Especialidad en Enfermería Cardiovascular', 
                     'Formación especializada en cuidados cardíacos', 24, 85000.00, 'Presencial'),
                    ('LIC-ENF', 'Licenciatura en Enfermería', 
                     'Formación integral en enfermería general', 48, 120000.00, 'Presencial'),
                    ('DIP-URG', 'Diplomado en Enfermería en Urgencias', 
                     'Capacitación en atención de emergencias', 6, 25000.00, 'Mixta'),
                    ('MAE-GER', 'Maestría en Gerontología en Enfermería', 
                     'Especialización en cuidados geriátricos', 24, 95000.00, 'Virtual')
                ]
                
                for programa in programas_ejemplo:
                    cursor.execute('''
                        INSERT INTO programas (codigo, nombre, descripcion, duracion_meses, costo, modalidad)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', programa)
            
            logger.info("✅ Tablas de base de datos inicializadas correctamente")
    
    def hash_password(self, password):
        """Crear hash de contraseña con BCRYPT"""
        try:
            # Generar hash BCRYPT
            password_hash_bytes = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))
            password_hash_str = password_hash_bytes.decode('utf-8')
            
            # Para BCRYPT, el salt está incluido en el hash
            # Pero mantenemos un valor en la columna salt por compatibilidad
            salt_hex = password_hash_str  # Usamos el mismo hash como salt
            
            return password_hash_str, salt_hex
        except Exception as e:
            logger.error(f"Error al crear hash BCRYPT: {e}")
            # Fallback a PBKDF2 si bcrypt falla
            salt = os.urandom(32)
            key = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt,
                100000
            )
            return key.hex(), salt.hex()
    
    def verify_password(self, stored_hash, stored_salt, provided_password):
        """Verificar contraseña con soporte para BCRYPT y PBKDF2"""
        try:
            # Primero intentar con BCRYPT (el hash comienza con $2)
            if stored_hash.startswith('$2b$') or stored_hash.startswith('$2a$') or stored_hash.startswith('$2y$'):
                # Verificar con bcrypt
                return bcrypt.checkpw(provided_password.encode('utf-8'), stored_hash.encode('utf-8'))
            else:
                # Fallback a PBKDF2 para compatibilidad
                try:
                    salt = bytes.fromhex(stored_salt)
                    new_hash = hashlib.pbkdf2_hmac(
                        'sha256',
                        provided_password.encode('utf-8'),
                        salt,
                        100000
                    )
                    return new_hash.hex() == stored_hash
                except:
                    # Si falla PBKDF2, intentar verificar directo (para hashes antiguos)
                    return stored_hash == hashlib.sha256(provided_password.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Error al verificar password: {e}")
            return False
    
    def obtener_usuario(self, usuario):
        """Obtener usuario por nombre de usuario o matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM usuarios 
                    WHERE usuario = ? OR matricula = ?
                ''', (usuario, usuario))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error obteniendo usuario {usuario}: {e}")
            return None
    
    def verificar_login(self, usuario, password):
        """Verificar credenciales de login con soporte BCRYPT"""
        try:
            usuario_data = self.obtener_usuario(usuario)
            if not usuario_data:
                logger.warning(f"Intento de login fallido - Usuario no encontrado: {usuario}")
                return None
            
            # Obtener hash y salt
            password_hash = usuario_data.get('password_hash', '')
            salt = usuario_data.get('salt', '')
            
            es_valido = self.verify_password(password_hash, salt, password)
            
            if es_valido:
                logger.info(f"Login exitoso: {usuario}")
                return usuario_data
            else:
                logger.warning(f"Intento de login fallido - Password incorrecto: {usuario}")
                return None
                
        except Exception as e:
            logger.error(f"Error verificando login: {e}")
            return None
    
    # =============================================================================
    # MÉTODOS PARA OBTENER DATOS
    # =============================================================================
    
    def obtener_inscritos(self):
        """Obtener todos los inscritos"""
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query("SELECT * FROM inscritos ORDER BY fecha_registro DESC", conn)
        except Exception as e:
            logger.error(f"Error obteniendo inscritos: {e}")
            return pd.DataFrame()
    
    def obtener_estudiantes(self):
        """Obtener todos los estudiantes"""
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query("SELECT * FROM estudiantes ORDER BY fecha_ingreso DESC", conn)
        except Exception as e:
            logger.error(f"Error obteniendo estudiantes: {e}")
            return pd.DataFrame()
    
    def obtener_egresados(self):
        """Obtener todos los egresados"""
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query("SELECT * FROM egresados ORDER BY fecha_graduacion DESC", conn)
        except Exception as e:
            logger.error(f"Error obteniendo egresados: {e}")
            return pd.DataFrame()
    
    def obtener_contratados(self):
        """Obtener todos los contratados"""
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query("SELECT * FROM contratados ORDER BY fecha_contratacion DESC", conn)
        except Exception as e:
            logger.error(f"Error obteniendo contratados: {e}")
            return pd.DataFrame()
    
    def obtener_usuarios(self):
        """Obtener todos los usuarios"""
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query("SELECT * FROM usuarios ORDER BY fecha_creacion DESC", conn)
        except Exception as e:
            logger.error(f"Error obteniendo usuarios: {e}")
            return pd.DataFrame()
    
    def obtener_programas(self):
        """Obtener todos los programas"""
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query("SELECT * FROM programas ORDER BY nombre", conn)
        except Exception as e:
            logger.error(f"Error obteniendo programas: {e}")
            return pd.DataFrame()
    
    def obtener_documentos_por_matricula(self, matricula):
        """Obtener documentos de una matrícula"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM documentos WHERE matricula = ? ORDER BY fecha_subida DESC"
                return pd.read_sql_query(query, conn, params=(matricula,))
        except Exception as e:
            logger.error(f"Error obteniendo documentos: {e}")
            return pd.DataFrame()
    
    # =============================================================================
    # MÉTODOS PARA AGREGAR DATOS
    # =============================================================================
    
    def agregar_inscrito(self, inscrito_data):
        """Agregar nuevo inscrito"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Generar matrícula automática si no se proporciona
                if not inscrito_data.get('matricula'):
                    fecha_actual = datetime.now()
                    matricula = f"MAT-INS-{fecha_actual.strftime('%y%m%d%H%M%S')}"
                    inscrito_data['matricula'] = matricula
                
                cursor.execute('''
                    INSERT INTO inscritos (
                        matricula, nombre_completo, email, telefono,
                        programa_interes, fecha_registro, estatus, folio,
                        fecha_nacimiento, como_se_entero, documentos_subidos,
                        documentos_guardados
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    inscrito_data.get('matricula', ''),
                    inscrito_data.get('nombre_completo', ''),
                    inscrito_data.get('email', ''),
                    inscrito_data.get('telefono', ''),
                    inscrito_data.get('programa_interes', ''),
                    inscrito_data.get('fecha_registro', datetime.now()),
                    inscrito_data.get('estatus', 'Pre-inscrito'),
                    inscrito_data.get('folio', f"FOL-{datetime.now().strftime('%Y%m%d-%H%M%S')}"),
                    inscrito_data.get('fecha_nacimiento'),
                    inscrito_data.get('como_se_entero', ''),
                    inscrito_data.get('documentos_subidos', 0),
                    inscrito_data.get('documentos_guardados', '')
                ))
                
                # Crear usuario automáticamente
                usuario_id = self.crear_usuario_desde_inscrito(inscrito_data, cursor.lastrowid)
                
                return cursor.lastrowid, inscrito_data['matricula']
        except Exception as e:
            logger.error(f"Error agregando inscrito: {e}")
            return None, None
    
    def crear_usuario_desde_inscrito(self, inscrito_data, inscrito_id):
        """Crear usuario automáticamente para un inscrito"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                matricula = inscrito_data.get('matricula', '')
                nombre = inscrito_data.get('nombre_completo', '')
                email = inscrito_data.get('email', '')
                
                # Generar contraseña temporal
                password_temp = matricula[:6] + "123"  # Ejemplo: MAT-INS-231201123
                password_hash_str, salt_hex = self.hash_password(password_temp)
                
                cursor.execute('''
                    INSERT INTO usuarios (
                        usuario, password_hash, salt, rol, nombre_completo,
                        nombre, email, matricula
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    matricula,  # Usuario = matrícula
                    password_hash_str,
                    salt_hex,
                    'inscrito',  # Rol inicial
                    nombre,
                    nombre,
                    email,
                    matricula
                ))
                
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error creando usuario desde inscrito: {e}")
            return None
    
    def agregar_estudiante(self, estudiante_data):
        """Agregar nuevo estudiante"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO estudiantes (
                        matricula, nombre_completo, programa, email, telefono,
                        fecha_nacimiento, genero, fecha_inscripcion, estatus,
                        documentos_subidos, fecha_registro, programa_interes,
                        folio, como_se_entero, fecha_ingreso, usuario
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    estudiante_data.get('matricula', ''),
                    estudiante_data.get('nombre_completo', ''),
                    estudiante_data.get('programa', ''),
                    estudiante_data.get('email', ''),
                    estudiante_data.get('telefono', ''),
                    estudiante_data.get('fecha_nacimiento'),
                    estudiante_data.get('genero', ''),
                    estudiante_data.get('fecha_inscripcion', datetime.now()),
                    estudiante_data.get('estatus', 'ACTIVO'),
                    estudiante_data.get('documentos_subidos', ''),
                    estudiante_data.get('fecha_registro', datetime.now()),
                    estudiante_data.get('programa_interes', ''),
                    estudiante_data.get('folio', ''),
                    estudiante_data.get('como_se_entero', ''),
                    estudiante_data.get('fecha_ingreso', datetime.now()),
                    estudiante_data.get('usuario', estudiante_data.get('matricula', ''))
                ))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error agregando estudiante: {e}")
            return None
    
    def agregar_egresado(self, egresado_data):
        """Agregar nuevo egresado"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO egresados (
                        matricula, nombre_completo, programa_original, fecha_graduacion,
                        nivel_academico, email, telefono, estado_laboral,
                        fecha_actualizacion, documentos_subidos
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    egresado_data.get('matricula', ''),
                    egresado_data.get('nombre_completo', ''),
                    egresado_data.get('programa_original', ''),
                    egresado_data.get('fecha_graduacion', datetime.now()),
                    egresado_data.get('nivel_academico', ''),
                    egresado_data.get('email', ''),
                    egresado_data.get('telefono', ''),
                    egresado_data.get('estado_laboral', ''),
                    egresado_data.get('fecha_actualizacion', datetime.now()),
                    egresado_data.get('documentos_subidos', '')
                ))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error agregando egresado: {e}")
            return None
    
    def agregar_contratado(self, contratado_data):
        """Agregar nuevo contratado"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO contratados (
                        matricula, fecha_contratacion, puesto, departamento,
                        estatus, salario, tipo_contrato, fecha_inicio,
                        fecha_fin, documentos_subidos
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    contratado_data.get('matricula', ''),
                    contratado_data.get('fecha_contratacion', datetime.now()),
                    contratado_data.get('puesto', ''),
                    contratado_data.get('departamento', ''),
                    contratado_data.get('estatus', ''),
                    contratado_data.get('salario', ''),
                    contratado_data.get('tipo_contrato', ''),
                    contratado_data.get('fecha_inicio', datetime.now()),
                    contratado_data.get('fecha_fin', datetime.now()),
                    contratado_data.get('documentos_subidos', '')
                ))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error agregando contratado: {e}")
            return None
    
    def agregar_documento(self, documento_data):
        """Agregar nuevo documento"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO documentos (
                        matricula, tipo_documento, nombre_archivo, ruta_archivo,
                        estado, observaciones
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    documento_data.get('matricula', ''),
                    documento_data.get('tipo_documento', ''),
                    documento_data.get('nombre_archivo', ''),
                    documento_data.get('ruta_archivo', ''),
                    documento_data.get('estado', 'Pendiente'),
                    documento_data.get('observaciones', '')
                ))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error agregando documento: {e}")
            return None
    
    def agregar_programa(self, programa_data):
        """Agregar nuevo programa"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO programas (
                        codigo, nombre, descripcion, duracion_meses,
                        costo, modalidad, estatus
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    programa_data.get('codigo', ''),
                    programa_data.get('nombre', ''),
                    programa_data.get('descripcion', ''),
                    programa_data.get('duracion_meses', 0),
                    programa_data.get('costo', 0.0),
                    programa_data.get('modalidad', 'Presencial'),
                    programa_data.get('estatus', 'Activo')
                ))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error agregando programa: {e}")
            return None
    
    # =============================================================================
    # MÉTODOS PARA ACTUALIZAR DATOS
    # =============================================================================
    
    def actualizar_inscrito(self, matricula, datos_actualizados):
        """Actualizar datos de un inscrito"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Construir query dinámico
                campos = []
                valores = []
                
                for campo, valor in datos_actualizados.items():
                    if campo != 'matricula':
                        campos.append(f"{campo} = ?")
                        valores.append(valor)
                
                valores.append(matricula)
                
                query = f'''
                    UPDATE inscritos 
                    SET {', '.join(campos)}, fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE matricula = ?
                '''
                
                cursor.execute(query, valores)
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error actualizando inscrito {matricula}: {e}")
            return False
    
    def actualizar_estudiante(self, matricula, datos_actualizados):
        """Actualizar datos de un estudiante"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Construir query dinámico
                campos = []
                valores = []
                
                for campo, valor in datos_actualizados.items():
                    if campo != 'matricula':
                        campos.append(f"{campo} = ?")
                        valores.append(valor)
                
                valores.append(matricula)
                
                query = f'''
                    UPDATE estudiantes 
                    SET {', '.join(campos)}
                    WHERE matricula = ?
                '''
                
                cursor.execute(query, valores)
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error actualizando estudiante {matricula}: {e}")
            return False
    
    def actualizar_usuario(self, usuario_id, datos_actualizados):
        """Actualizar datos de un usuario"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Construir query dinámico
                campos = []
                valores = []
                
                for campo, valor in datos_actualizados.items():
                    if campo not in ['id', 'fecha_creacion']:
                        campos.append(f"{campo} = ?")
                        valores.append(valor)
                
                valores.append(usuario_id)
                
                query = f'''
                    UPDATE usuarios 
                    SET {', '.join(campos)}, fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE id = ?
                '''
                
                cursor.execute(query, valores)
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error actualizando usuario {usuario_id}: {e}")
            return False
    
    # =============================================================================
    # MÉTODOS PARA ELIMINAR DATOS
    # =============================================================================
    
    def eliminar_inscrito(self, matricula):
        """Eliminar inscrito por matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM inscritos WHERE matricula = ?", (matricula,))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error eliminando inscrito {matricula}: {e}")
            return False
    
    def eliminar_estudiante(self, matricula):
        """Eliminar estudiante por matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM estudiantes WHERE matricula = ?", (matricula,))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error eliminando estudiante {matricula}: {e}")
            return False
    
    def eliminar_egresado(self, matricula):
        """Eliminar egresado por matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM egresados WHERE matricula = ?", (matricula,))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error eliminando egresado {matricula}: {e}")
            return False
    
    # =============================================================================
    # MÉTODOS DE BÚSQUEDA
    # =============================================================================
    
    def buscar_inscrito_por_matricula(self, matricula):
        """Buscar inscrito por matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM inscritos WHERE matricula = ?", (matricula,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error buscando inscrito {matricula}: {e}")
            return None
    
    def buscar_estudiante_por_matricula(self, matricula):
        """Buscar estudiante por matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM estudiantes WHERE matricula = ?", (matricula,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error buscando estudiante {matricula}: {e}")
            return None
    
    def buscar_egresado_por_matricula(self, matricula):
        """Buscar egresado por matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM egresados WHERE matricula = ?", (matricula,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error buscando egresado {matricula}: {e}")
            return None
    
    def buscar_contratado_por_matricula(self, matricula):
        """Buscar contratado por matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM contratados WHERE matricula = ?", (matricula,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error buscando contratado {matricula}: {e}")
            return None
    
    # =============================================================================
    # MÉTODOS DE REPORTES Y ESTADÍSTICAS
    # =============================================================================
    
    def obtener_estadisticas_generales(self):
        """Obtener estadísticas generales del sistema"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                estadisticas = {}
                
                # Contar inscritos
                cursor.execute("SELECT COUNT(*) FROM inscritos")
                estadisticas['total_inscritos'] = cursor.fetchone()[0]
                
                # Contar estudiantes
                cursor.execute("SELECT COUNT(*) FROM estudiantes")
                estadisticas['total_estudiantes'] = cursor.fetchone()[0]
                
                # Contar egresados
                cursor.execute("SELECT COUNT(*) FROM egresados")
                estadisticas['total_egresados'] = cursor.fetchone()[0]
                
                # Contar contratados
                cursor.execute("SELECT COUNT(*) FROM contratados")
                estadisticas['total_contratados'] = cursor.fetchone()[0]
                
                # Contar usuarios
                cursor.execute("SELECT COUNT(*) FROM usuarios")
                estadisticas['total_usuarios'] = cursor.fetchone()[0]
                
                # Inscritos por programa
                cursor.execute('''
                    SELECT programa_interes, COUNT(*) as cantidad 
                    FROM inscritos 
                    GROUP BY programa_interes 
                    ORDER BY cantidad DESC
                ''')
                estadisticas['inscritos_por_programa'] = cursor.fetchall()
                
                # Estudiantes por estatus
                cursor.execute('''
                    SELECT estatus, COUNT(*) as cantidad 
                    FROM estudiantes 
                    GROUP BY estatus 
                    ORDER BY cantidad DESC
                ''')
                estadisticas['estudiantes_por_estatus'] = cursor.fetchall()
                
                # Egresados por nivel académico
                cursor.execute('''
                    SELECT nivel_academico, COUNT(*) as cantidad 
                    FROM egresados 
                    GROUP BY nivel_academico 
                    ORDER BY cantidad DESC
                ''')
                estadisticas['egresados_por_nivel'] = cursor.fetchall()
                
                return estadisticas
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {}
    
    def obtener_inscritos_recientes(self, limite=10):
        """Obtener inscritos más recientes"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM inscritos ORDER BY fecha_registro DESC LIMIT ?"
                return pd.read_sql_query(query, conn, params=(limite,))
        except Exception as e:
            logger.error(f"Error obteniendo inscritos recientes: {e}")
            return pd.DataFrame()
    
    def registrar_bitacora(self, usuario, accion, detalles, ip='localhost'):
        """Registrar actividad en bitácora"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO bitacora (usuario, accion, detalles, ip)
                    VALUES (?, ?, ?, ?)
                ''', (usuario, accion, detalles, ip))
                return True
        except Exception as e:
            logger.error(f"Error registrando en bitácora: {e}")
            return False

# =============================================================================
# INSTANCIA DE BASE DE DATOS
# =============================================================================

# Crear una instancia global de la base de datos
db = None

try:
    db = SistemaBaseDatos()
    logger.info("✅ Base de datos inicializada exitosamente")
    
    # Mostrar información sobre la base de datos cargada
    if ENTORNO == "servidor":
        logger.info("📡 Conectado a base de datos remota")
        st.info("🔗 Configuración desde secrets.toml")
    else:
        logger.info("💻 Conectado a base de datos local")
        
except Exception as e:
    logger.error(f"❌ Error crítico inicializando base de datos: {e}")
    
    # Mostrar mensaje según el entorno
    if ENTORNO == "servidor":
        st.error(f"⚠️ Error conectando a la base de datos remota. Verifique la configuración en secrets.toml")
    else:
        st.error(f"⚠️ Error inicializando base de datos local")
    
    # Crear una clase dummy para continuar
    class DummyDB:
        def __init__(self):
            self.inscritos = pd.DataFrame()
            self.estudiantes = pd.DataFrame()
            self.egresados = pd.DataFrame()
            self.contratados = pd.DataFrame()
            self.usuarios = pd.DataFrame()
            self.programas = pd.DataFrame()
        
        def obtener_inscritos(self):
            return pd.DataFrame()
        
        def obtener_estudiantes(self):
            return pd.DataFrame()
        
        def obtener_egresados(self):
            return pd.DataFrame()
        
        def obtener_contratados(self):
            return pd.DataFrame()
        
        def obtener_usuarios(self):
            return pd.DataFrame()
        
        def obtener_programas(self):
            return pd.DataFrame()
        
        def verificar_login(self, usuario, password):
            if usuario == "admin" and password == "Admin123!":
                return {
                    'usuario': 'admin',
                    'nombre_completo': 'Administrador Demo',
                    'rol': 'administrador',
                    'matricula': 'ADMIN-DEMO'
                }
            return None
        
        def registrar_bitacora(self, *args, **kwargs):
            return True
    
    db = DummyDB()

# =============================================================================
# SISTEMA DE AUTENTICACIÓN
# =============================================================================

class SistemaAutenticacion:
    def __init__(self):
        self.sesion_activa = False
        self.usuario_actual = None
        
    def verificar_login(self, usuario, password):
        """Verificar credenciales de usuario desde SQLite"""
        try:
            if not usuario or not password:
                st.error("❌ Usuario y contraseña son obligatorios")
                return False
            
            with st.spinner("🔐 Verificando credenciales..."):
                if db is None:
                    st.error("❌ Base de datos no disponible")
                    return False
                
                usuario_data = db.verificar_login(usuario, password)
                
                if usuario_data:
                    # Usar 'nombre' si existe, sino 'nombre_completo', sino 'usuario'
                    nombre_real = usuario_data.get('nombre', 
                                   usuario_data.get('nombre_completo', 
                                   usuario_data.get('usuario', 'Usuario')))
                    
                    st.success(f"✅ ¡Bienvenido(a), {nombre_real}!")
                    st.session_state.login_exitoso = True
                    st.session_state.usuario_actual = usuario_data
                    st.session_state.rol_usuario = usuario_data.get('rol', 'usuario')
                    self.sesion_activa = True
                    self.usuario_actual = usuario_data
                    
                    # Registrar en bitácora
                    try:
                        db.registrar_bitacora(
                            usuario_data['usuario'],
                            'LOGIN',
                            f'Usuario {usuario_data["usuario"]} inició sesión'
                        )
                    except:
                        pass  # Ignorar error de bitácora
                    
                    return True
                else:
                    st.error("❌ Usuario o contraseña incorrectos")
                    return False
                    
        except Exception as e:
            st.error(f"❌ Error en el proceso de login: {e}")
            return False
    
    def cerrar_sesion(self):
        """Cerrar sesión del usuario"""
        try:
            if self.sesion_activa and self.usuario_actual:
                try:
                    db.registrar_bitacora(
                        self.usuario_actual.get('usuario', ''),
                        'LOGOUT',
                        f'Usuario {self.usuario_actual.get("usuario", "")} cerró sesión'
                    )
                except:
                    pass  # Ignorar error de bitácora
                
            self.sesion_activa = False
            self.usuario_actual = None
            st.session_state.login_exitoso = False
            st.session_state.usuario_actual = None
            st.session_state.rol_usuario = None
            st.success("✅ Sesión cerrada exitosamente")
            
        except Exception as e:
            st.error(f"❌ Error cerrando sesión: {e}")

# Instancia global del sistema de autenticación
auth = SistemaAutenticacion()

# =============================================================================
# FUNCIONES DE CARGA DE DATOS
# =============================================================================

@st.cache_data(ttl=300)
def cargar_datos_completos():
    """Cargar todos los datos desde SQLite"""
    with st.spinner("📊 Cargando datos desde base de datos SQLite..."):
        try:
            datos = {
                'inscritos': db.obtener_inscritos(),
                'estudiantes': db.obtener_estudiantes(),
                'egresados': db.obtener_egresados(),
                'contratados': db.obtener_contratados(),
                'usuarios': db.obtener_usuarios(),
                'programas': db.obtener_programas()
            }
            
            # Mostrar estado de carga
            if not datos['inscritos'].empty:
                st.success("✅ Datos cargados exitosamente desde SQLite")
            
            return datos
        except Exception as e:
            st.error(f"❌ Error cargando datos: {e}")
            # Devolver DataFrames vacíos
            return {
                'inscritos': pd.DataFrame(),
                'estudiantes': pd.DataFrame(),
                'egresados': pd.DataFrame(),
                'contratados': pd.DataFrame(),
                'usuarios': pd.DataFrame(),
                'programas': pd.DataFrame()
            }

# =============================================================================
# INTERFAZ DE LOGIN ACTUALIZADA
# =============================================================================

def mostrar_login():
    """Interfaz de login"""
    st.title("🏥 Sistema Escuela de Enfermería")
    st.markdown("---")
    
    # Mostrar entorno actual
    entorno_display = "🌍 Servidor Remoto" if ENTORNO == "servidor" else "💻 Laptop Local"
    st.info(f"**{entorno_display}**")
    
    # Mostrar información de la base de datos de forma segura
    db_name = os.path.basename(CONFIG['db_path'])
    st.info(f"**Base de datos:** {db_name}")
    
    # Mostrar si se está usando secrets.toml
    try:
        if st.secrets:
            st.success("✅ Configuración cargada desde secrets.toml")
    except:
        st.warning("⚠️ No se encontró archivo secrets.toml")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            st.subheader("🔐 Inicio de Sesión")
            
            usuario = st.text_input("👤 Usuario", placeholder="admin")
            password = st.text_input("🔒 Contraseña", type="password", placeholder="Admin123!")
            
            login_button = st.form_submit_button("🚀 Ingresar al Sistema")

            if login_button:
                if usuario and password:
                    with st.spinner("🔐 Verificando credenciales..."):
                        if auth.verificar_login(usuario, password):
                            st.rerun()
                        else:
                            st.error("❌ No se pudo iniciar sesión. Verifique sus credenciales.")
                else:
                    st.warning("⚠️ Complete todos los campos")
    
    # Información de credenciales por defecto
    with st.expander("📋 Información de Acceso"):
        st.info("**Credenciales por defecto para administrador:**")
        st.info("👤 Usuario: admin")
        st.info("🔒 Contraseña: Admin123!")
        st.warning("⚠️ **Nota:** Cambie estas credenciales en producción")

# =============================================================================
# INTERFAZ PRINCIPAL ACTUALIZADA
# =============================================================================

def mostrar_interfaz_principal():
    """Interfaz principal del sistema"""
    st.title("🏥 Sistema Escuela de Enfermería")
    
    # Barra superior
    usuario_actual = st.session_state.usuario_actual
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        entorno_display = "🌍 Servidor Remoto" if ENTORNO == "servidor" else "💻 Laptop Local"
        st.write(f"**{entorno_display}**")
        
        nombre_usuario = "Usuario"
        if usuario_actual:
            nombre_usuario = usuario_actual.get('nombre', 
                           usuario_actual.get('nombre_completo', 
                           usuario_actual.get('usuario', 'Usuario')))
        st.write(f"**Usuario:** {nombre_usuario}")
    
    with col2:
        if usuario_actual:
            rol_usuario = usuario_actual.get('rol', 'usuario')
            st.write(f"**Rol:** {rol_usuario.title()}")
    
    with col3:
        if st.button("🚪 Cerrar Sesión"):
            auth.cerrar_sesion()
            st.rerun()
    
    st.markdown("---")
    
    # Cargar datos
    datos = cargar_datos_completos()
    df_inscritos = datos.get('inscritos', pd.DataFrame())
    df_estudiantes = datos.get('estudiantes', pd.DataFrame())
    df_egresados = datos.get('egresados', pd.DataFrame())
    df_contratados = datos.get('contratados', pd.DataFrame())
    df_usuarios = datos.get('usuarios', pd.DataFrame())
    df_programas = datos.get('programas', pd.DataFrame())
    
    # Menú lateral
    mostrar_info_configuracion()
    
    # Menú principal debajo del sidebar
    opcion_menu = st.sidebar.selectbox(
        "📊 Menú Principal",
        [
            "🏠 Dashboard",
            "📝 Inscripciones",
            "🎓 Estudiantes",
            "🎓 Egresados",
            "💼 Contratados",
            "👥 Usuarios",
            "📊 Reportes",
            "⚙️ Configuración"
        ]
    )
    
    # Instanciar sistemas
    sistema_inscripciones = SistemaInscripciones()
    sistema_estudiantes = SistemaEstudiantes()
    sistema_egresados = SistemaEgresados()
    sistema_contratados = SistemaContratados()
    sistema_usuarios = SistemaUsuarios()
    sistema_reportes = SistemaReportes()
    
    # Mostrar contenido según opción seleccionada
    if opcion_menu == "🏠 Dashboard":
        mostrar_dashboard(datos, sistema_reportes)
    
    elif opcion_menu == "📝 Inscripciones":
        st.header("📝 Gestión de Inscripciones")
        
        tab1, tab2, tab3 = st.tabs(["📋 Lista de Inscritos", "➕ Nueva Inscripción", "📊 Estadísticas"])
        
        with tab1:
            if 'editar_inscrito' in st.session_state:
                sistema_inscripciones.editar_inscrito(st.session_state.editar_inscrito, df_inscritos)
            else:
                sistema_inscripciones.mostrar_lista_inscritos(df_inscritos)
        
        with tab2:
            inscrito_data = sistema_inscripciones.mostrar_formulario_inscripcion()
            if inscrito_data:
                sistema_inscripciones.procesar_inscripcion(inscrito_data)
        
        with tab3:
            sistema_reportes.mostrar_reporte_inscripciones(df_inscritos)
    
    elif opcion_menu == "🎓 Estudiantes":
        st.header("🎓 Gestión de Estudiantes")
        sistema_estudiantes.mostrar_lista_estudiantes(df_estudiantes)
    
    elif opcion_menu == "🎓 Egresados":
        st.header("🎓 Gestión de Egresados")
        sistema_egresados.mostrar_lista_egresados(df_egresados)
    
    elif opcion_menu == "💼 Contratados":
        st.header("💼 Gestión de Contratados")
        sistema_contratados.mostrar_lista_contratados(df_contratados)
    
    elif opcion_menu == "👥 Usuarios":
        st.header("👥 Gestión de Usuarios")
        sistema_usuarios.mostrar_lista_usuarios(df_usuarios)
    
    elif opcion_menu == "📊 Reportes":
        st.header("📊 Reportes y Estadísticas")
        sistema_reportes.mostrar_estadisticas_generales(datos)
    
    elif opcion_menu == "⚙️ Configuración":
        st.header("⚙️ Configuración del Sistema")
        
        with st.expander("🌍 Configuración de Entorno"):
            st.info(f"**Entorno actual:** {ENTORNO.upper()}")
            
            # Mostrar información de forma segura
            st.subheader("🔐 Configuración desde secrets.toml")
            st.info(f"**Supervisor Mode:** {SUPERVISOR_MODE}")
            st.info(f"**Debug Mode:** {DEBUG_MODE}")
            
            # Mostrar nombres de archivos, no rutas completas
            db_name = os.path.basename(CONFIG['db_path'])
            st.info(f"**Base de datos:** {db_name}")
            
            # Mostrar correo de forma segura
            if 'EMAIL_USER' in globals() and EMAIL_USER:
                email_display = f"{EMAIL_USER.split('@')[0]}@..." if '@' in EMAIL_USER else "Configurado"
                st.info(f"**Email notificaciones:** {email_display}")
        
        with st.expander("🗄️ Base de Datos"):
            st.info("**Tablas disponibles:**")
            st.info("- usuarios (BCRYPT)")
            st.info("- inscritos")
            st.info("- estudiantes")
            st.info("- egresados")
            st.info("- contratados")
            st.info("- programas")
            st.info("- documentos")
            st.info("- bitacora")
            
            if st.button("🔄 Verificar Conexión BD"):
                try:
                    with db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tablas = cursor.fetchall()
                        st.success(f"✅ Conexión exitosa. Tablas: {len(tablas)}")
                        
                        # Mostrar lista de tablas
                        if tablas:
                            st.write("**Lista de tablas:**")
                            for tabla in tablas:
                                st.write(f"- {tabla[0]}")
                except Exception as e:
                    st.error(f"❌ Error: {e}")

# =============================================================================
# DASHBOARD
# =============================================================================

def mostrar_dashboard(datos, sistema_reportes):
    """Mostrar dashboard principal"""
    st.header("🏠 Dashboard Principal")
    
    # Métricas rápidas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_inscritos = len(datos['inscritos']) if not datos['inscritos'].empty else 0
        st.metric("📝 Inscritos", total_inscritos)
    
    with col2:
        total_estudiantes = len(datos['estudiantes']) if not datos['estudiantes'].empty else 0
        st.metric("🎓 Estudiantes", total_estudiantes)
    
    with col3:
        total_egresados = len(datos['egresados']) if not datos['egresados'].empty else 0
        st.metric("🎓 Egresados", total_egresados)
    
    with col4:
        total_contratados = len(datos['contratados']) if not datos['contratados'].empty else 0
        st.metric("💼 Contratados", total_contratados)
    
    st.markdown("---")
    
    # Gráficos principales
    col_graf1, col_graf2 = st.columns(2)
    
    with col_graf1:
        st.subheader("📈 Inscripciones Recientes")
        if not datos['inscritos'].empty:
            # Últimos 30 días
            df_inscritos = datos['inscritos'].copy()
            df_inscritos['fecha_registro'] = pd.to_datetime(df_inscritos['fecha_registro'])
            df_recientes = df_inscritos.nlargest(10, 'fecha_registro')
            st.dataframe(
                df_recientes[['matricula', 'nombre_completo', 'programa_interes', 'fecha_registro']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No hay inscripciones recientes")
    
    with col_graf2:
        st.subheader("📊 Distribución de Estudiantes")
        if not datos['estudiantes'].empty:
            df_estudiantes = datos['estudiantes'].copy()
            conteo_estatus = df_estudiantes['estatus'].value_counts()
            st.bar_chart(conteo_estatus)
        else:
            st.info("No hay estudiantes registrados")
    
    st.markdown("---")
    
    # Acciones rápidas
    st.subheader("🚀 Acciones Rápidas")
    
    col_acc1, col_acc2, col_acc3 = st.columns(3)
    
    with col_acc1:
        if st.button("➕ Nueva Inscripción", use_container_width=True):
            st.session_state.menu_opcion = "📝 Inscripciones"
            st.rerun()
    
    with col_acc2:
        if st.button("📊 Ver Reportes", use_container_width=True):
            st.session_state.menu_opcion = "📊 Reportes"
            st.rerun()
    
    with col_acc3:
        if st.button("👥 Gestionar Usuarios", use_container_width=True):
            st.session_state.menu_opcion = "👥 Usuarios"
            st.rerun()
    
    # Estadísticas generales
    sistema_reportes.mostrar_estadisticas_generales(datos)

# =============================================================================
# EJECUCIÓN PRINCIPAL
# =============================================================================

def main():
    # Inicializar estado de sesión
    if 'login_exitoso' not in st.session_state:
        st.session_state.login_exitoso = False
    if 'usuario_actual' not in st.session_state:
        st.session_state.usuario_actual = None
    if 'rol_usuario' not in st.session_state:
        st.session_state.rol_usuario = None
    if 'editar_inscrito' not in st.session_state:
        st.session_state.editar_inscrito = None
    if 'menu_opcion' not in st.session_state:
        st.session_state.menu_opcion = "🏠 Dashboard"
    
    # Mostrar interfaz según estado de autenticación
    if not st.session_state.login_exitoso:
        mostrar_login()
    else:
        mostrar_interfaz_principal()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"❌ Error crítico en la aplicación: {e}")
        st.info("Por favor, recarga la página o contacta al administrador.")
        logger.error(f"Error crítico: {e}", exc_info=True)
