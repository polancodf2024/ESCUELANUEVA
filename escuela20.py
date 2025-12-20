"""
escuela20.py - Sistema de Gestión Escuela de Enfermería
Versión corregida para funcionar en Streamlit Cloud y local
CONFIGURACIÓN DUAL: Local y Streamlit Cloud
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
# DETECCIÓN AUTOMÁTICA DE ENTORNO
# =============================================

# Configuración de logging primero
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def detectar_entorno():
    """Detectar automáticamente si estamos en Streamlit Cloud o local"""
    # Variables de entorno de Streamlit Cloud
    streamlit_vars = [
        'STREAMLIT_SHARING',
        'STREAMLIT_SERVER_ADDRESS',
        'STREAMLIT_SERVER_PORT'
    ]
    
    # Verificar variables de Streamlit Cloud
    for var in streamlit_vars:
        if var in os.environ:
            logger.info(f"✅ Detectado Streamlit Cloud por variable: {var}")
            return 'streamlit_cloud'
    
    # Verificar nombre de host
    if 'HOSTNAME' in os.environ and 'streamlit' in os.environ['HOSTNAME']:
        logger.info("✅ Detectado Streamlit Cloud por HOSTNAME")
        return 'streamlit_cloud'
    
    # Si no estamos en Streamlit Cloud, verificar si hay secrets
    try:
        if hasattr(st, 'secrets') and st.secrets:
            # Leer supervisor_mode de secrets
            supervisor_mode = st.secrets.get("supervisor_mode", False)
            if supervisor_mode:
                logger.info("✅ Entorno local detectado: Modo Supervisor (servidor remoto)")
                return 'local_supervisor'
            else:
                logger.info("✅ Entorno local detectado: Modo Normal")
                return 'local_normal'
    except:
        pass
    
    # Por defecto, modo local sin secrets
    logger.info("⚠️ Entorno local detectado (sin secrets.toml)")
    return 'local_normal'

# Detectar entorno actual
ENTORNO_DETECTADO = detectar_entorno()
logger.info(f"Entorno final detectado: {ENTORNO_DETECTADO}")

# =============================================
# CONFIGURACIÓN SEGÚN ENTORNO
# =============================================

def cargar_configuracion():
    """Cargar configuración según el entorno detectado"""
    
    config = {
        'supervisor_mode': False,
        'debug_mode': True,
        'entorno': 'servidor',
        'db_escuela': '',
        'db_inscritos': '',
        'base_path': '',
        'uploads_path': '',
        'smtp_server': '',
        'smtp_port': 587,
        'email_user': '',
        'email_password': '',
        'notification_email': '',
        'remote_config': {}  # Configuración SSH si aplica
    }
    
    if ENTORNO_DETECTADO == 'streamlit_cloud':
        # STREAMLIT CLOUD - Siempre modo local
        config['supervisor_mode'] = False
        config['debug_mode'] = True
        config['entorno'] = 'servidor'
        config['base_path'] = '/mount/src/escuelanueva'
        
        # Usar base de datos local
        config['db_escuela'] = f"{config['base_path']}/datos/escuela.db"
        config['db_inscritos'] = f"{config['base_path']}/datos/inscritos.db"
        config['uploads_path'] = f"{config['base_path']}/uploads"
        
        # Crear directorios necesarios
        os.makedirs(f"{config['base_path']}/datos", exist_ok=True)
        os.makedirs(f"{config['uploads_path']}/inscritos", exist_ok=True)
        os.makedirs(f"{config['uploads_path']}/estudiantes", exist_ok=True)
        os.makedirs(f"{config['uploads_path']}/egresados", exist_ok=True)
        os.makedirs(f"{config['uploads_path']}/contratados", exist_ok=True)
        
        # Intentar cargar email config desde secrets si existe
        try:
            if hasattr(st, 'secrets'):
                config['smtp_server'] = st.secrets.get("smtp_server", "")
                config['smtp_port'] = st.secrets.get("smtp_port", 587)
                config['email_user'] = st.secrets.get("email_user", "")
                config['email_password'] = st.secrets.get("email_password", "")
                config['notification_email'] = st.secrets.get("notification_email", "")
        except:
            pass
        
        logger.info("🌐 Configuración: Streamlit Cloud (modo local)")
        
    elif ENTORNO_DETECTADO == 'local_supervisor':
        # MODO SUPERVISOR LOCAL (conexión a servidor remoto)
        config['supervisor_mode'] = True
        config['debug_mode'] = st.secrets.get("debug_mode", False)
        config['entorno'] = 'servidor'
        
        # Cargar configuración SSH/remota
        config['remote_config'] = {
            'remote_host': st.secrets.get("remote_host", ""),
            'remote_port': st.secrets.get("remote_port", 22),
            'remote_user': st.secrets.get("remote_user", ""),
            'remote_password': st.secrets.get("remote_password", ""),
            'remote_dir': st.secrets.get("remote_dir", "")
        }
        
        # Cargar rutas desde secrets
        paths = st.secrets.get("paths", {})
        config['db_escuela'] = paths.get("db_escuela", "escuela.db")
        config['db_inscritos'] = paths.get("db_inscritos", "inscritos.db")
        config['base_path'] = paths.get("base_path", ".")
        config['uploads_path'] = paths.get("uploads_path", "uploads")
        
        # Configuración de email
        config['smtp_server'] = st.secrets.get("smtp_server", "")
        config['smtp_port'] = st.secrets.get("smtp_port", 587)
        config['email_user'] = st.secrets.get("email_user", "")
        config['email_password'] = st.secrets.get("email_password", "")
        config['notification_email'] = st.secrets.get("notification_email", "")
        
        logger.info("🔗 Configuración: Modo Supervisor (servidor remoto)")
        
    else:  # local_normal
        # MODO LOCAL NORMAL (con o sin secrets)
        config['supervisor_mode'] = False
        config['debug_mode'] = True
        config['entorno'] = 'laptop'
        config['base_path'] = '.'
        
        # Rutas locales por defecto
        config['db_escuela'] = 'datos/escuela.db'
        config['db_inscritos'] = 'datos/inscritos.db'
        config['uploads_path'] = 'uploads'
        
        # Intentar cargar de secrets si existen
        try:
            if hasattr(st, 'secrets'):
                paths = st.secrets.get("paths", {})
                if paths.get("db_escuela"):
                    config['db_escuela'] = paths.get("db_escuela")
                
                # Configuración de email
                config['smtp_server'] = st.secrets.get("smtp_server", "")
                config['smtp_port'] = st.secrets.get("smtp_port", 587)
                config['email_user'] = st.secrets.get("email_user", "")
                config['email_password'] = st.secrets.get("email_password", "")
                config['notification_email'] = st.secrets.get("notification_email", "")
        except:
            pass
        
        # Crear directorios locales
        os.makedirs('datos', exist_ok=True)
        os.makedirs('uploads/inscritos', exist_ok=True)
        os.makedirs('uploads/estudiantes', exist_ok=True)
        os.makedirs('uploads/egresados', exist_ok=True)
        os.makedirs('uploads/contratados', exist_ok=True)
        
        logger.info("💻 Configuración: Modo Local Normal")
    
    return config

# Cargar configuración
CONFIG = cargar_configuracion()

# Variables globales para fácil acceso
SUPERVISOR_MODE = CONFIG['supervisor_mode']
DEBUG_MODE = CONFIG['debug_mode']
ENTORNO = CONFIG['entorno']
DB_ESCUELA = CONFIG['db_escuela']
DB_INSCRITOS = CONFIG['db_inscritos']
BASE_PATH = CONFIG['base_path']
UPLOADS_PATH = CONFIG['uploads_path']
SMTP_SERVER = CONFIG['smtp_server']
SMTP_PORT = CONFIG['smtp_port']
EMAIL_USER = CONFIG['email_user']
EMAIL_PASSWORD = CONFIG['email_password']
NOTIFICATION_EMAIL = CONFIG['notification_email']

# Mostrar configuración cargada
logger.info(f"Entorno: {ENTORNO}")
logger.info(f"Supervisor Mode: {SUPERVISOR_MODE}")
logger.info(f"Base de datos: {DB_ESCUELA}")
logger.info(f"Path base: {BASE_PATH}")

# Configuración por entorno para compatibilidad
CONFIG_PATHS = {
    "servidor": {
        "base_path": BASE_PATH,
        "db_path": DB_ESCUELA,
        "uploads_path": UPLOADS_PATH
    },
    "laptop": {
        "base_path": BASE_PATH,
        "db_path": DB_ESCUELA,
        "uploads_path": UPLOADS_PATH
    }
}

# Configuración activa
ACTIVE_CONFIG = CONFIG_PATHS[ENTORNO]

# Configuración de página
st.set_page_config(
    page_title="Sistema Escuela Enfermería",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# FUNCIÓN PARA MOSTRAR INFORMACIÓN DE CONFIGURACIÓN
# =============================================================================

def mostrar_info_configuracion():
    """Muestra información de configuración en el sidebar"""
    st.sidebar.title("⚙️ Configuración")
    
    # Mostrar entorno actual
    if ENTORNO_DETECTADO == 'streamlit_cloud':
        entorno_display = "🌐 Streamlit Cloud"
    elif ENTORNO_DETECTADO == 'local_supervisor':
        entorno_display = "🔗 Servidor Remoto"
    else:
        entorno_display = "💻 Local"
    
    st.sidebar.info(f"**{entorno_display}**")
    
    # Mostrar información de la base de datos
    with st.sidebar.expander("📊 Base de Datos"):
        db_name = os.path.basename(DB_ESCUELA)
        st.info(f"**Archivo:** {db_name}")
        
        # Mostrar modo
        if SUPERVISOR_MODE:
            st.success("✅ Modo Supervisor Activado")
            st.info("**Conexión:** Servidor Remoto")
        else:
            st.info("✅ Modo Local")
            if ENTORNO_DETECTADO == 'streamlit_cloud':
                st.info("**Ubicación:** Streamlit Cloud")
            else:
                st.info("**Ubicación:** Archivo Local")
    
    # Mostrar información del sistema
    with st.sidebar.expander("📋 Información del Sistema"):
        st.info("**Versión:** 20.0 (Configuración Dual)")
        st.info(f"**Supervisor Mode:** {'✅ Activado' if SUPERVISOR_MODE else '❌ Desactivado'}")
        st.info(f"**Debug Mode:** {'✅ Activado' if DEBUG_MODE else '❌ Desactivado'}")
        
        # Mostrar información de correo si está configurado
        if EMAIL_USER:
            email_name = EMAIL_USER.split('@')[0] if '@' in EMAIL_USER else EMAIL_USER
            st.info(f"**Email Notificaciones:** {email_name}@...")
        
        # Mostrar ruta de base de datos (solo nombre)
        st.info(f"**Base de datos:** {os.path.basename(DB_ESCUELA)}")
    
    st.sidebar.markdown("---")
    st.sidebar.info("**Características:**")
    st.sidebar.info("✅ Autenticación BCRYPT")
    st.sidebar.info("✅ Base de datos SQLite")
    st.sidebar.info("✅ Configuración Dual")
    st.sidebar.info("✅ Gestión completa")

# =============================================================================
# SISTEMA DE BASE DE DATOS SQLITE - CON SOPORTE DUAL
# =============================================================================

class SistemaBaseDatos:
    def __init__(self, db_path=None):
        # Usar la ruta configurada o la proporcionada
        if db_path is None:
            self.db_path = DB_ESCUELA
        else:
            self.db_path = db_path
        
        logger.info(f"📁 Inicializando base de datos: {self.db_path}")
        logger.info(f"📊 Entorno: {ENTORNO}")
        logger.info(f"🔗 Supervisor Mode: {SUPERVISOR_MODE}")
        
        # Si estamos en modo supervisor, mostrar advertencia
        if SUPERVISOR_MODE and ENTORNO_DETECTADO != 'local_supervisor':
            logger.warning("⚠️ Modo supervisor activado pero no en entorno local_supervisor")
            logger.warning("⚠️ La aplicación funcionará en modo local")
        
        # Crear directorio si no existe (para rutas relativas)
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"✅ Directorio creado: {db_dir}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo crear directorio: {e}")
        
        # Inicializar tablas
        try:
            self.init_tablas()
            logger.info("✅ Base de datos inicializada exitosamente")
        except Exception as e:
            logger.error(f"❌ Error inicializando base de datos: {e}")
            # Intentar crear base mínima
            try:
                conn = sqlite3.connect(self.db_path)
                conn.close()
                logger.info("✅ Base de datos mínima creada")
                self.init_tablas()
            except Exception as db_error:
                logger.error(f"❌ Error crítico: {db_error}")
                raise Exception(f"No se pudo inicializar la base de datos: {db_error}")
    
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
            logger.error(f"❌ Error en conexión a base de datos: {e}")
            
            # Mensaje amigable según el entorno
            if SUPERVISOR_MODE:
                error_msg = "Error conectando al servidor remoto. Verifique la configuración."
            else:
                error_msg = f"Error accediendo a la base de datos local: {e}"
            
            st.error(f"⚠️ {error_msg}")
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
            
            # Verificar si ya existe un usuario admin
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE usuario = 'admin'")
            admin_exists = cursor.fetchone()[0] > 0
            
            if not admin_exists:
                # Insertar usuario administrador por defecto - USANDO BCRYPT
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
                    logger.info("✅ Usuario administrador por defecto creado")
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
                        logger.info("✅ Usuario administrador creado con matrícula única")
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
                
                logger.info("✅ Programas de ejemplo creados")
            
            logger.info("✅ Todas las tablas inicializadas correctamente")
    
    def hash_password(self, password):
        """Crear hash de contraseña con BCRYPT"""
        try:
            # Generar hash BCRYPT
            password_hash_bytes = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))
            password_hash_str = password_hash_bytes.decode('utf-8')
            
            # Para BCRYPT, el salt está incluido en el hash
            salt_hex = password_hash_str  # Usamos el mismo hash como salt por compatibilidad
            
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
    
except Exception as e:
    logger.error(f"❌ Error crítico inicializando base de datos: {e}")
    
    # Mostrar mensaje según el entorno
    if ENTORNO_DETECTADO == 'streamlit_cloud':
        st.error("⚠️ Error inicializando base de datos en Streamlit Cloud")
        st.info("Se usará una base de datos demo temporal")
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
# SISTEMAS DE GESTIÓN (CLASES COMPLETAS)
# =============================================================================

class SistemaInscripciones:
    def __init__(self):
        self.db = db
    
    def mostrar_lista_inscritos(self, df_inscritos):
        """Mostrar lista de inscritos"""
        if not df_inscritos.empty:
            st.subheader("📋 Lista de Inscritos")
            
            # Opciones de filtro
            col1, col2, col3 = st.columns(3)
            with col1:
                filtro_programa = st.selectbox(
                    "Filtrar por programa",
                    ["Todos"] + list(df_inscritos['programa_interes'].unique()) if not df_inscritos.empty else ["Todos"]
                )
            
            with col2:
                filtro_estatus = st.selectbox(
                    "Filtrar por estatus",
                    ["Todos"] + list(df_inscritos['estatus'].unique()) if not df_inscritos.empty else ["Todos"]
                )
            
            with col3:
                buscar = st.text_input("🔍 Buscar por nombre o matrícula")
            
            # Aplicar filtros
            df_filtrado = df_inscritos.copy()
            
            if filtro_programa != "Todos":
                df_filtrado = df_filtrado[df_filtrado['programa_interes'] == filtro_programa]
            
            if filtro_estatus != "Todos":
                df_filtrado = df_filtrado[df_filtrado['estatus'] == filtro_estatus]
            
            if buscar:
                mask = df_filtrado['nombre_completo'].str.contains(buscar, case=False) | \
                       df_filtrado['matricula'].str.contains(buscar, case=False)
                df_filtrado = df_filtrado[mask]
            
            # Mostrar datos
            if not df_filtrado.empty:
                st.dataframe(
                    df_filtrado[['matricula', 'nombre_completo', 'programa_interes', 'estatus', 'fecha_registro']],
                    use_container_width=True,
                    hide_index=True
                )
                
                # Estadísticas
                st.info(f"📊 Mostrando {len(df_filtrado)} de {len(df_inscritos)} inscritos")
                
                # Opciones de acción
                col_act1, col_act2, col_act3 = st.columns(3)
                with col_act1:
                    if st.button("📥 Exportar a CSV", use_container_width=True):
                        csv = df_filtrado.to_csv(index=False)
                        st.download_button(
                            label="⬇️ Descargar CSV",
                            data=csv,
                            file_name=f"inscritos_filtrados_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )
            else:
                st.info("No hay inscritos que coincidan con los filtros")
        else:
            st.info("📭 No hay inscritos registrados")
    
    def mostrar_formulario_inscripcion(self):
        """Mostrar formulario para nueva inscripción"""
        with st.form("nueva_inscripcion", clear_on_submit=True):
            st.subheader("📝 Nueva Inscripción")
            
            col1, col2 = st.columns(2)
            with col1:
                nombre = st.text_input("Nombre Completo *", placeholder="Juan Pérez López")
                email = st.text_input("Email *", placeholder="juan.perez@email.com")
                telefono = st.text_input("Teléfono", placeholder="555-123-4567")
                fecha_nacimiento = st.date_input("Fecha de Nacimiento", 
                                                 min_value=datetime(1950, 1, 1),
                                                 max_value=datetime.now())
            
            with col2:
                # Obtener programas disponibles
                programas = db.obtener_programas()
                if not programas.empty:
                    opciones_programas = programas['nombre'].tolist()
                else:
                    opciones_programas = [
                        "Licenciatura en Enfermería",
                        "Especialidad en Enfermería Cardiovascular",
                        "Diplomado en Enfermería en Urgencias",
                        "Maestría en Gerontología en Enfermería"
                    ]
                
                programa = st.selectbox("Programa de Interés *", opciones_programas)
                como_se_entero = st.selectbox("¿Cómo se enteró?", 
                    ["Internet", "Recomendación", "Medios Tradicionales", "Evento", "Redes Sociales", "Otro"])
                
                # Opciones adicionales
                tiene_experiencia = st.checkbox("¿Tiene experiencia en el área?")
            
            # Observaciones
            observaciones = st.text_area("Observaciones o comentarios adicionales", 
                                        placeholder="Información adicional relevante...")
            
            submit_button = st.form_submit_button("📋 Registrar Inscripción", use_container_width=True)
            
            if submit_button:
                if not nombre or not email or not programa:
                    st.warning("⚠️ Complete los campos obligatorios (*)")
                    return None
                
                # Validar email
                if '@' not in email or '.' not in email.split('@')[-1]:
                    st.warning("⚠️ Ingrese un email válido")
                    return None
                
                inscrito_data = {
                    'nombre_completo': nombre.strip(),
                    'email': email.strip().lower(),
                    'telefono': telefono.strip() if telefono else '',
                    'programa_interes': programa,
                    'fecha_nacimiento': fecha_nacimiento,
                    'como_se_entero': como_se_entero,
                    'fecha_registro': datetime.now(),
                    'estatus': 'Pre-inscrito'
                }
                
                if observaciones:
                    inscrito_data['documentos_guardados'] = observaciones
                
                return inscrito_data
        
        return None
    
    def procesar_inscripcion(self, inscrito_data):
        """Procesar nueva inscripción"""
        try:
            with st.spinner("📝 Registrando inscripción..."):
                inscrito_id, matricula = db.agregar_inscrito(inscrito_data)
                if inscrito_id:
                    st.success(f"""
                    ✅ **Inscripción registrada exitosamente**
                    
                    **Matrícula asignada:** {matricula}
                    **Nombre:** {inscrito_data['nombre_completo']}
                    **Programa:** {inscrito_data['programa_interes']}
                    **Fecha de registro:** {inscrito_data['fecha_registro'].strftime('%d/%m/%Y %H:%M')}
                    """)
                    
                    # Mostrar información importante
                    st.info("""
                    📋 **Información importante:**
                    1. Se ha creado un usuario automático con su matrícula
                    2. La contraseña temporal es: {matricula}123
                    3. Se recomienda cambiar la contraseña en el primer acceso
                    """.format(matricula=matricula[:6]))
                    
                    return True
                else:
                    st.error("❌ Error al registrar la inscripción en la base de datos")
                    return False
        except Exception as e:
            st.error(f"❌ Error en el proceso de inscripción: {str(e)}")
            logger.error(f"Error procesando inscripción: {e}")
            return False
    
    def editar_inscrito(self, matricula):
        """Mostrar formulario para editar inscrito"""
        try:
            inscrito = db.buscar_inscrito_por_matricula(matricula)
            if inscrito:
                st.subheader(f"✏️ Editar Inscrito: {matricula}")
                
                with st.form("editar_inscrito"):
                    col1, col2 = st.columns(2)
                    with col1:
                        nombre = st.text_input("Nombre Completo", value=inscrito.get('nombre_completo', ''))
                        email = st.text_input("Email", value=inscrito.get('email', ''))
                        telefono = st.text_input("Teléfono", value=inscrito.get('telefono', ''))
                    
                    with col2:
                        estatus = st.selectbox("Estatus", 
                            ['Pre-inscrito', 'En revisión', 'Aceptado', 'Rechazado', 'Matriculado'],
                            index=['Pre-inscrito', 'En revisión', 'Aceptado', 'Rechazado', 'Matriculado'].index(
                                inscrito.get('estatus', 'Pre-inscrito')
                            ))
                        
                        programa = st.text_input("Programa de Interés", value=inscrito.get('programa_interes', ''))
                    
                    observaciones = st.text_area("Observaciones", value=inscrito.get('documentos_guardados', ''))
                    
                    if st.form_submit_button("💾 Guardar Cambios"):
                        datos_actualizados = {
                            'nombre_completo': nombre,
                            'email': email,
                            'telefono': telefono,
                            'estatus': estatus,
                            'programa_interes': programa,
                            'documentos_guardados': observaciones
                        }
                        
                        # Actualizar en base de datos
                        if db.actualizar_inscrito(matricula, datos_actualizados):
                            st.success("✅ Inscrito actualizado exitosamente")
                            st.session_state.pop('editar_inscrito', None)
                            st.rerun()
                        else:
                            st.error("❌ Error al actualizar inscrito")
            else:
                st.error(f"❌ No se encontró el inscrito con matrícula: {matricula}")
        except Exception as e:
            st.error(f"❌ Error editando inscrito: {e}")

class SistemaEstudiantes:
    def __init__(self):
        self.db = db
    
    def mostrar_lista_estudiantes(self, df_estudiantes):
        """Mostrar lista de estudiantes"""
        st.header("🎓 Gestión de Estudiantes")
        
        if not df_estudiantes.empty:
            # Filtros
            col1, col2, col3 = st.columns(3)
            with col1:
                filtro_programa = st.selectbox(
                    "Filtrar por programa",
                    ["Todos"] + list(df_estudiantes['programa'].unique())
                )
            
            with col2:
                filtro_estatus = st.selectbox(
                    "Filtrar por estatus",
                    ["Todos"] + list(df_estudiantes['estatus'].unique())
                )
            
            with col3:
                buscar = st.text_input("🔍 Buscar estudiante")
            
            # Aplicar filtros
            df_filtrado = df_estudiantes.copy()
            
            if filtro_programa != "Todos":
                df_filtrado = df_filtrado[df_filtrado['programa'] == filtro_programa]
            
            if filtro_estatus != "Todos":
                df_filtrado = df_filtrado[df_filtrado['estatus'] == filtro_estatus]
            
            if buscar:
                mask = df_filtrado['nombre_completo'].str.contains(buscar, case=False) | \
                       df_filtrado['matricula'].str.contains(buscar, case=False)
                df_filtrado = df_filtrado[mask]
            
            # Mostrar datos
            if not df_filtrado.empty:
                st.dataframe(
                    df_filtrado[['matricula', 'nombre_completo', 'programa', 'estatus', 'fecha_ingreso']],
                    use_container_width=True,
                    hide_index=True
                )
                
                # Estadísticas
                col_stat1, col_stat2, col_stat3 = st.columns(3)
                with col_stat1:
                    st.metric("Total Estudiantes", len(df_filtrado))
                with col_stat2:
                    activos = len(df_filtrado[df_filtrado['estatus'] == 'ACTIVO'])
                    st.metric("Estudiantes Activos", activos)
                with col_stat3:
                    inactivos = len(df_filtrado[df_filtrado['estatus'] == 'INACTIVO'])
                    st.metric("Estudiantes Inactivos", inactivos)
                
                # Acciones
                st.subheader("🛠️ Acciones")
                col_act1, col_act2 = st.columns(2)
                with col_act1:
                    if st.button("➕ Registrar Nuevo Estudiante", use_container_width=True):
                        self.mostrar_formulario_estudiante()
                
                with col_act2:
                    if st.button("📤 Exportar Lista", use_container_width=True):
                        csv = df_filtrado.to_csv(index=False)
                        st.download_button(
                            label="⬇️ Descargar CSV",
                            data=csv,
                            file_name=f"estudiantes_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )
            else:
                st.info("No hay estudiantes que coincidan con los filtros")
        else:
            st.info("📭 No hay estudiantes registrados")
            if st.button("➕ Registrar Primer Estudiante", use_container_width=True):
                self.mostrar_formulario_estudiante()
    
    def mostrar_formulario_estudiante(self):
        """Mostrar formulario para nuevo estudiante"""
        with st.form("nuevo_estudiante", clear_on_submit=True):
            st.subheader("🎓 Nuevo Estudiante")
            
            col1, col2 = st.columns(2)
            with col1:
                matricula = st.text_input("Matrícula *", placeholder="EST-2024-001")
                nombre = st.text_input("Nombre Completo *", placeholder="María González López")
                email = st.text_input("Email", placeholder="maria.gonzalez@email.com")
                telefono = st.text_input("Teléfono", placeholder="555-987-6543")
            
            with col2:
                programa = st.text_input("Programa *", placeholder="Licenciatura en Enfermería")
                fecha_ingreso = st.date_input("Fecha de Ingreso", value=datetime.now())
                genero = st.selectbox("Género", ["", "Femenino", "Masculino", "Otro", "Prefiero no decir"])
                estatus = st.selectbox("Estatus", ["ACTIVO", "INACTIVO", "GRADUADO", "BAJA"])
            
            fecha_nacimiento = st.date_input("Fecha de Nacimiento", 
                                             min_value=datetime(1950, 1, 1),
                                             max_value=datetime.now())
            
            submit_button = st.form_submit_button("🎓 Registrar Estudiante", use_container_width=True)
            
            if submit_button:
                if not matricula or not nombre or not programa:
                    st.warning("⚠️ Complete los campos obligatorios (*)")
                    return
                
                estudiante_data = {
                    'matricula': matricula.strip(),
                    'nombre_completo': nombre.strip(),
                    'programa': programa.strip(),
                    'email': email.strip().lower() if email else '',
                    'telefono': telefono.strip() if telefono else '',
                    'fecha_nacimiento': fecha_nacimiento,
                    'genero': genero,
                    'estatus': estatus,
                    'fecha_ingreso': fecha_ingreso,
                    'fecha_inscripcion': datetime.now()
                }
                
                try:
                    estudiante_id = db.agregar_estudiante(estudiante_data)
                    if estudiante_id:
                        st.success(f"✅ Estudiante registrado exitosamente: {matricula}")
                        st.rerun()
                    else:
                        st.error("❌ Error al registrar estudiante")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

class SistemaEgresados:
    def __init__(self):
        self.db = db
    
    def mostrar_lista_egresados(self, df_egresados):
        """Mostrar lista de egresados"""
        st.header("🎓 Gestión de Egresados")
        
        if not df_egresados.empty:
            # Filtros
            col1, col2 = st.columns(2)
            with col1:
                filtro_nivel = st.selectbox(
                    "Filtrar por nivel académico",
                    ["Todos"] + list(df_egresados['nivel_academico'].dropna().unique())
                )
            
            with col2:
                buscar = st.text_input("🔍 Buscar egresado")
            
            # Aplicar filtros
            df_filtrado = df_egresados.copy()
            
            if filtro_nivel != "Todos":
                df_filtrado = df_filtrado[df_filtrado['nivel_academico'] == filtro_nivel]
            
            if buscar:
                mask = df_filtrado['nombre_completo'].str.contains(buscar, case=False) | \
                       df_filtrado['matricula'].str.contains(buscar, case=False)
                df_filtrado = df_filtrado[mask]
            
            # Mostrar datos
            if not df_filtrado.empty:
                st.dataframe(
                    df_filtrado[['matricula', 'nombre_completo', 'programa_original', 'nivel_academico', 'fecha_graduacion']],
                    use_container_width=True,
                    hide_index=True
                )
                
                # Estadísticas
                st.info(f"📊 Total de egresados: {len(df_filtrado)}")
                
                # Distribución por nivel académico
                if 'nivel_academico' in df_filtrado.columns:
                    distribucion = df_filtrado['nivel_academico'].value_counts()
                    st.bar_chart(distribucion)
                
                # Acciones
                col_act1, col_act2 = st.columns(2)
                with col_act1:
                    if st.button("➕ Registrar Nuevo Egresado", use_container_width=True):
                        self.mostrar_formulario_egresado()
                
                with col_act2:
                    if st.button("📤 Exportar Lista", use_container_width=True):
                        csv = df_filtrado.to_csv(index=False)
                        st.download_button(
                            label="⬇️ Descargar CSV",
                            data=csv,
                            file_name=f"egresados_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )
            else:
                st.info("No hay egresados que coincidan con los filtros")
        else:
            st.info("📭 No hay egresados registrados")
            if st.button("➕ Registrar Primer Egresado", use_container_width=True):
                self.mostrar_formulario_egresado()
    
    def mostrar_formulario_egresado(self):
        """Mostrar formulario para nuevo egresado"""
        with st.form("nuevo_egresado", clear_on_submit=True):
            st.subheader("🎓 Nuevo Egresado")
            
            col1, col2 = st.columns(2)
            with col1:
                matricula = st.text_input("Matrícula *", placeholder="EGR-2024-001")
                nombre = st.text_input("Nombre Completo *", placeholder="Carlos Rodríguez")
                programa_original = st.text_input("Programa Original *", placeholder="Licenciatura en Enfermería")
                nivel_academico = st.selectbox("Nivel Académico", 
                    ["Licenciatura", "Especialidad", "Maestría", "Doctorado", "Diplomado"])
            
            with col2:
                email = st.text_input("Email", placeholder="carlos.rodriguez@email.com")
                telefono = st.text_input("Teléfono", placeholder="555-456-7890")
                estado_laboral = st.selectbox("Estado Laboral", 
                    ["Empleado", "Desempleado", "Independiente", "Estudiando", "Otro"])
                fecha_graduacion = st.date_input("Fecha de Graduación", value=datetime.now())
            
            submit_button = st.form_submit_button("🎓 Registrar Egresado", use_container_width=True)
            
            if submit_button:
                if not matricula or not nombre or not programa_original:
                    st.warning("⚠️ Complete los campos obligatorios (*)")
                    return
                
                egresado_data = {
                    'matricula': matricula.strip(),
                    'nombre_completo': nombre.strip(),
                    'programa_original': programa_original.strip(),
                    'nivel_academico': nivel_academico,
                    'email': email.strip().lower() if email else '',
                    'telefono': telefono.strip() if telefono else '',
                    'estado_laboral': estado_laboral,
                    'fecha_graduacion': fecha_graduacion,
                    'fecha_actualizacion': datetime.now()
                }
                
                try:
                    egresado_id = db.agregar_egresado(egresado_data)
                    if egresado_id:
                        st.success(f"✅ Egresado registrado exitosamente: {matricula}")
                        st.rerun()
                    else:
                        st.error("❌ Error al registrar egresado")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

class SistemaContratados:
    def __init__(self):
        self.db = db
    
    def mostrar_lista_contratados(self, df_contratados):
        """Mostrar lista de contratados"""
        st.header("💼 Gestión de Contratados")
        
        if not df_contratados.empty:
            # Filtros
            col1, col2 = st.columns(2)
            with col1:
                filtro_puesto = st.selectbox(
                    "Filtrar por puesto",
                    ["Todos"] + list(df_contratados['puesto'].dropna().unique())
                )
            
            with col2:
                buscar = st.text_input("🔍 Buscar contratado")
            
            # Aplicar filtros
            df_filtrado = df_contratados.copy()
            
            if filtro_puesto != "Todos":
                df_filtrado = df_filtrado[df_filtrado['puesto'] == filtro_puesto]
            
            if buscar:
                mask = df_filtrado['matricula'].str.contains(buscar, case=False)
                df_filtrado = df_filtrado[mask]
            
            # Mostrar datos
            if not df_filtrado.empty:
                st.dataframe(
                    df_filtrado[['matricula', 'fecha_contratacion', 'puesto', 'departamento', 'estatus']],
                    use_container_width=True,
                    hide_index=True
                )
                
                # Estadísticas
                st.info(f"📊 Total de contratados: {len(df_filtrado)}")
                
                # Acciones
                col_act1, col_act2 = st.columns(2)
                with col_act1:
                    if st.button("➕ Registrar Nueva Contratación", use_container_width=True):
                        self.mostrar_formulario_contratado()
                
                with col_act2:
                    if st.button("📤 Exportar Lista", use_container_width=True):
                        csv = df_filtrado.to_csv(index=False)
                        st.download_button(
                            label="⬇️ Descargar CSV",
                            data=csv,
                            file_name=f"contratados_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )
            else:
                st.info("No hay contratados que coincidan con los filtros")
        else:
            st.info("📭 No hay contratados registrados")
            if st.button("➕ Registrar Primera Contratación", use_container_width=True):
                self.mostrar_formulario_contratado()
    
    def mostrar_formulario_contratado(self):
        """Mostrar formulario para nuevo contratado"""
        with st.form("nuevo_contratado", clear_on_submit=True):
            st.subheader("💼 Nueva Contratación")
            
            col1, col2 = st.columns(2)
            with col1:
                matricula = st.text_input("Matrícula *", placeholder="CON-2024-001")
                puesto = st.text_input("Puesto *", placeholder="Enfermero(a) General")
                departamento = st.text_input("Departamento", placeholder="Urgencias")
                estatus = st.selectbox("Estatus", ["ACTIVO", "INACTIVO", "TERMINADO"])
            
            with col2:
                salario = st.text_input("Salario", placeholder="$15,000 MXN")
                tipo_contrato = st.selectbox("Tipo de Contrato", 
                    ["Indeterminado", "Temporal", "Por Obra", "Honorarios"])
                fecha_inicio = st.date_input("Fecha de Inicio", value=datetime.now())
                fecha_fin = st.date_input("Fecha de Fin")
            
            submit_button = st.form_submit_button("💼 Registrar Contratación", use_container_width=True)
            
            if submit_button:
                if not matricula or not puesto:
                    st.warning("⚠️ Complete los campos obligatorios (*)")
                    return
                
                contratado_data = {
                    'matricula': matricula.strip(),
                    'puesto': puesto.strip(),
                    'departamento': departamento.strip() if departamento else '',
                    'estatus': estatus,
                    'salario': salario.strip() if salario else '',
                    'tipo_contrato': tipo_contrato,
                    'fecha_inicio': fecha_inicio,
                    'fecha_fin': fecha_fin if fecha_fin else None,
                    'fecha_contratacion': datetime.now()
                }
                
                try:
                    contratado_id = db.agregar_contratado(contratado_data)
                    if contratado_id:
                        st.success(f"✅ Contratación registrada exitosamente: {matricula}")
                        st.rerun()
                    else:
                        st.error("❌ Error al registrar contratación")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

class SistemaUsuarios:
    def __init__(self):
        self.db = db
    
    def mostrar_lista_usuarios(self, df_usuarios):
        """Mostrar lista de usuarios"""
        st.header("👥 Gestión de Usuarios")
        
        if not df_usuarios.empty:
            # Filtros
            col1, col2 = st.columns(2)
            with col1:
                filtro_rol = st.selectbox(
                    "Filtrar por rol",
                    ["Todos"] + list(df_usuarios['rol'].unique())
                )
            
            with col2:
                buscar = st.text_input("🔍 Buscar usuario")
            
            # Aplicar filtros
            df_filtrado = df_usuarios.copy()
            
            if filtro_rol != "Todos":
                df_filtrado = df_filtrado[df_filtrado['rol'] == filtro_rol]
            
            if buscar:
                mask = df_filtrado['usuario'].str.contains(buscar, case=False) | \
                       df_filtrado['nombre_completo'].str.contains(buscar, case=False) | \
                       df_filtrado['matricula'].str.contains(buscar, case=False)
                df_filtrado = df_filtrado[mask]
            
            # Mostrar datos
            if not df_filtrado.empty:
                st.dataframe(
                    df_filtrado[['usuario', 'nombre_completo', 'rol', 'matricula', 'email', 'activo']],
                    use_container_width=True,
                    hide_index=True
                )
                
                # Estadísticas
                col_stat1, col_stat2, col_stat3 = st.columns(3)
                with col_stat1:
                    st.metric("Total Usuarios", len(df_filtrado))
                with col_stat2:
                    activos = len(df_filtrado[df_filtrado['activo'] == 1])
                    st.metric("Usuarios Activos", activos)
                with col_stat3:
                    admins = len(df_filtrado[df_filtrado['rol'] == 'administrador'])
                    st.metric("Administradores", admins)
                
                # Distribución por rol
                distribucion = df_filtrado['rol'].value_counts()
                st.bar_chart(distribucion)
                
                # Acciones
                st.subheader("🛠️ Acciones")
                col_act1, col_act2 = st.columns(2)
                with col_act1:
                    if st.button("👤 Crear Nuevo Usuario", use_container_width=True):
                        self.mostrar_formulario_usuario()
                
                with col_act2:
                    if st.button("📤 Exportar Lista", use_container_width=True):
                        csv = df_filtrado.to_csv(index=False)
                        st.download_button(
                            label="⬇️ Descargar CSV",
                            data=csv,
                            file_name=f"usuarios_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )
            else:
                st.info("No hay usuarios que coincidan con los filtros")
        else:
            st.info("📭 No hay usuarios registrados")
            if st.button("👤 Crear Primer Usuario", use_container_width=True):
                self.mostrar_formulario_usuario()
    
    def mostrar_formulario_usuario(self):
        """Mostrar formulario para nuevo usuario"""
        with st.form("nuevo_usuario", clear_on_submit=True):
            st.subheader("👤 Nuevo Usuario")
            
            col1, col2 = st.columns(2)
            with col1:
                usuario = st.text_input("Usuario *", placeholder="juan.perez")
                nombre_completo = st.text_input("Nombre Completo *", placeholder="Juan Pérez López")
                email = st.text_input("Email", placeholder="juan.perez@email.com")
            
            with col2:
                matricula = st.text_input("Matrícula", placeholder="USR-2024-001")
                rol = st.selectbox("Rol *", ["administrador", "coordinador", "docente", "estudiante", "inscrito"])
                activo = st.checkbox("Usuario Activo", value=True)
            
            # Campos de contraseña
            col_pass1, col_pass2 = st.columns(2)
            with col_pass1:
                password = st.text_input("Contraseña *", type="password", placeholder="Mínimo 8 caracteres")
            with col_pass2:
                password_confirm = st.text_input("Confirmar Contraseña *", type="password")
            
            submit_button = st.form_submit_button("👤 Crear Usuario", use_container_width=True)
            
            if submit_button:
                # Validaciones
                if not usuario or not nombre_completo or not rol:
                    st.warning("⚠️ Complete los campos obligatorios (*)")
                    return
                
                if not password:
                    st.warning("⚠️ La contraseña es obligatoria")
                    return
                
                if len(password) < 8:
                    st.warning("⚠️ La contraseña debe tener al menos 8 caracteres")
                    return
                
                if password != password_confirm:
                    st.warning("⚠️ Las contraseñas no coinciden")
                    return
                
                # Crear usuario
                try:
                    # Hash de la contraseña
                    password_hash_str, salt_hex = db.hash_password(password)
                    
                    usuario_data = {
                        'usuario': usuario.strip().lower(),
                        'nombre_completo': nombre_completo.strip(),
                        'nombre': nombre_completo.strip(),
                        'email': email.strip().lower() if email else '',
                        'matricula': matricula.strip() if matricula else '',
                        'rol': rol,
                        'activo': 1 if activo else 0,
                        'password_hash': password_hash_str,
                        'salt': salt_hex
                    }
                    
                    # Insertar en base de datos
                    with db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT INTO usuarios 
                            (usuario, password_hash, salt, rol, nombre_completo, nombre, email, matricula, activo)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            usuario_data['usuario'],
                            usuario_data['password_hash'],
                            usuario_data['salt'],
                            usuario_data['rol'],
                            usuario_data['nombre_completo'],
                            usuario_data['nombre'],
                            usuario_data['email'],
                            usuario_data['matricula'],
                            usuario_data['activo']
                        ))
                    
                    st.success(f"✅ Usuario creado exitosamente: {usuario}")
                    st.info(f"**Usuario:** {usuario}\n**Rol:** {rol}\n**Estado:** {'Activo' if activo else 'Inactivo'}")
                    st.rerun()
                    
                except sqlite3.IntegrityError as e:
                    if "usuarios.usuario" in str(e):
                        st.error("❌ El nombre de usuario ya existe")
                    elif "usuarios.matricula" in str(e):
                        st.error("❌ La matrícula ya está registrada")
                    else:
                        st.error(f"❌ Error de integridad: {str(e)}")
                except Exception as e:
                    st.error(f"❌ Error al crear usuario: {str(e)}")

class SistemaReportes:
    def __init__(self):
        self.db = db
    
    def mostrar_estadisticas_generales(self, datos):
        """Mostrar estadísticas generales"""
        st.header("📊 Estadísticas Generales")
        
        try:
            estadisticas = db.obtener_estadisticas_generales()
            
            # Métricas principales
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("📝 Inscritos", estadisticas.get('total_inscritos', 0))
            with col2:
                st.metric("🎓 Estudiantes", estadisticas.get('total_estudiantes', 0))
            with col3:
                st.metric("🎓 Egresados", estadisticas.get('total_egresados', 0))
            with col4:
                st.metric("💼 Contratados", estadisticas.get('total_contratados', 0))
            
            st.markdown("---")
            
            # Sección de inscritos recientes
            st.subheader("📈 Inscritos Recientes")
            inscritos_recientes = db.obtener_inscritos_recientes(10)
            if not inscritos_recientes.empty:
                st.dataframe(
                    inscritos_recientes[['matricula', 'nombre_completo', 'programa_interes', 'fecha_registro']],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No hay inscritos recientes")
            
            st.markdown("---")
            
            # Reporte de distribución
            st.subheader("📋 Distribución por Programa")
            if not datos['inscritos'].empty:
                df_inscritos = datos['inscritos'].copy()
                conteo_programas = df_inscritos['programa_interes'].value_counts()
                
                col_chart1, col_chart2 = st.columns(2)
                with col_chart1:
                    st.bar_chart(conteo_programas)
                with col_chart2:
                    st.dataframe(conteo_programas, use_container_width=True)
            
            # Reporte de estudiantes por estatus
            if not datos['estudiantes'].empty:
                st.subheader("📊 Estudiantes por Estatus")
                df_estudiantes = datos['estudiantes'].copy()
                conteo_estatus = df_estudiantes['estatus'].value_counts()
                st.bar_chart(conteo_estatus)
            
            # Botones de acción
            st.markdown("---")
            st.subheader("🛠️ Herramientas de Reporte")
            
            col_btn1, col_btn2, col_btn3 = st.columns(3)
            with col_btn1:
                if st.button("📄 Reporte Completo PDF", use_container_width=True):
                    st.info("Generando reporte PDF... (Función en desarrollo)")
            
            with col_btn2:
                if st.button("📊 Gráficos Detallados", use_container_width=True):
                    self.mostrar_graficos_detallados(datos)
            
            with col_btn3:
                if st.button("🔄 Actualizar Estadísticas", use_container_width=True):
                    st.rerun()
                    
        except Exception as e:
            st.error(f"❌ Error generando reportes: {e}")
    
    def mostrar_graficos_detallados(self, datos):
        """Mostrar gráficos detallados"""
        st.subheader("📊 Análisis Detallado")
        
        # Gráfico de inscritos por mes
        if not datos['inscritos'].empty:
            df_inscritos = datos['inscritos'].copy()
            df_inscritos['fecha_registro'] = pd.to_datetime(df_inscritos['fecha_registro'])
            df_inscritos['mes'] = df_inscritos['fecha_registro'].dt.to_period('M')
            inscritos_por_mes = df_inscritos['mes'].value_counts().sort_index()
            
            st.write("**Inscritos por Mes:**")
            st.line_chart(inscritos_por_mes)
        
        # Gráfico de estudiantes por programa
        if not datos['estudiantes'].empty:
            df_estudiantes = datos['estudiantes'].copy()
            estudiantes_por_programa = df_estudiantes['programa'].value_counts()
            
            st.write("**Estudiantes por Programa:**")
            st.bar_chart(estudiantes_por_programa)
    
    def mostrar_reporte_inscripciones(self, df_inscritos):
        """Mostrar reporte de inscripciones"""
        st.subheader("📈 Reporte de Inscripciones")
        
        if not df_inscritos.empty:
            # Métricas rápidas
            col1, col2, col3 = st.columns(3)
            with col1:
                total = len(df_inscritos)
                st.metric("Total Inscritos", total)
            with col2:
                pre_inscritos = len(df_inscritos[df_inscritos['estatus'] == 'Pre-inscrito'])
                st.metric("Pre-inscritos", pre_inscritos)
            with col3:
                aceptados = len(df_inscritos[df_inscritos['estatus'] == 'Aceptado'])
                st.metric("Aceptados", aceptados)
            
            # Gráfico de distribución por programa
            st.write("**Distribución por Programa:**")
            conteo_programas = df_inscritos['programa_interes'].value_counts()
            st.bar_chart(conteo_programas)
            
            # Gráfico de distribución por estatus
            st.write("**Distribución por Estatus:**")
            conteo_estatus = df_inscritos['estatus'].value_counts()
            st.bar_chart(conteo_estatus)
            
            # Tabla detallada
            with st.expander("📋 Ver Datos Detallados"):
                st.dataframe(df_inscritos, use_container_width=True)
        else:
            st.info("No hay datos para mostrar")

# =============================================================================
# FUNCIONES DE CARGA DE DATOS
# =============================================================================

@st.cache_data(ttl=300)
def cargar_datos_completos():
    """Cargar todos los datos desde SQLite"""
    with st.spinner("📊 Cargando datos desde base de datos..."):
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
            total_registros = sum(len(df) for df in datos.values() if isinstance(df, pd.DataFrame))
            if total_registros > 0:
                logger.info(f"✅ {total_registros} registros cargados")
            
            return datos
        except Exception as e:
            logger.error(f"❌ Error cargando datos: {e}")
            return {
                'inscritos': pd.DataFrame(),
                'estudiantes': pd.DataFrame(),
                'egresados': pd.DataFrame(),
                'contratados': pd.DataFrame(),
                'usuarios': pd.DataFrame(),
                'programas': pd.DataFrame()
            }

# =============================================================================
# INTERFAZ DE LOGIN
# =============================================================================

def mostrar_login():
    """Interfaz de login"""
    st.title("🏥 Sistema Escuela de Enfermería")
    st.markdown("---")
    
    # Mostrar entorno actual
    if ENTORNO_DETECTADO == 'streamlit_cloud':
        entorno_display = "🌐 Streamlit Cloud"
        st.success("✅ Modo: Aplicación Web Pública")
    elif ENTORNO_DETECTADO == 'local_supervisor':
        entorno_display = "🔗 Servidor Remoto"
        st.info("✅ Modo: Conexión a Servidor Remoto")
    else:
        entorno_display = "💻 Local"
        st.info("✅ Modo: Desarrollo Local")
    
    st.info(f"**{entorno_display}**")
    
    # Mostrar información de la base de datos
    db_name = os.path.basename(DB_ESCUELA)
    st.info(f"**Base de datos:** {db_name}")
    
    # Mostrar si se está usando secrets.toml
    try:
        if hasattr(st, 'secrets') and st.secrets:
            st.success("✅ Configuración cargada desde secrets.toml")
    except:
        if ENTORNO_DETECTADO != 'streamlit_cloud':
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
    
    # Estadísticas generales
    sistema_reportes.mostrar_estadisticas_generales(datos)
    
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

# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================

def mostrar_interfaz_principal():
    """Interfaz principal del sistema"""
    st.title("🏥 Sistema Escuela de Enfermería")
    
    # Barra superior
    usuario_actual = st.session_state.usuario_actual
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        if ENTORNO_DETECTADO == 'streamlit_cloud':
            entorno_display = "🌐 Streamlit Cloud"
        elif ENTORNO_DETECTADO == 'local_supervisor':
            entorno_display = "🔗 Servidor Remoto"
        else:
            entorno_display = "💻 Local"
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
                sistema_inscripciones.editar_inscrito(st.session_state.editar_inscrito)
            else:
                sistema_inscripciones.mostrar_lista_inscritos(df_inscritos)
        
        with tab2:
            inscrito_data = sistema_inscripciones.mostrar_formulario_inscripcion()
            if inscrito_data:
                if sistema_inscripciones.procesar_inscripcion(inscrito_data):
                    st.rerun()
        
        with tab3:
            sistema_reportes.mostrar_reporte_inscripciones(df_inscritos)
    
    elif opcion_menu == "🎓 Estudiantes":
        sistema_estudiantes.mostrar_lista_estudiantes(df_estudiantes)
    
    elif opcion_menu == "🎓 Egresados":
        sistema_egresados.mostrar_lista_egresados(df_egresados)
    
    elif opcion_menu == "💼 Contratados":
        sistema_contratados.mostrar_lista_contratados(df_contratados)
    
    elif opcion_menu == "👥 Usuarios":
        sistema_usuarios.mostrar_lista_usuarios(df_usuarios)
    
    elif opcion_menu == "📊 Reportes":
        sistema_reportes.mostrar_estadisticas_generales(datos)
    
    elif opcion_menu == "⚙️ Configuración":
        st.header("⚙️ Configuración del Sistema")
        
        with st.expander("🌍 Configuración de Entorno"):
            st.info(f"**Entorno detectado:** {ENTORNO_DETECTADO.upper()}")
            st.info(f"**Entorno activo:** {ENTORNO.upper()}")
            st.info(f"**Supervisor Mode:** {SUPERVISOR_MODE}")
            st.info(f"**Debug Mode:** {DEBUG_MODE}")
            
            # Mostrar nombres de archivos
            db_name = os.path.basename(DB_ESCUELA)
            st.info(f"**Base de datos:** {db_name}")
            
            # Mostrar ruta completa solo en desarrollo
            if ENTORNO_DETECTADO != 'streamlit_cloud':
                st.info(f"**Ruta BD:** {DB_ESCUELA}")
            
            # Mostrar correo de forma segura
            if EMAIL_USER:
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
            
            if st.button("🔄 Verificar Conexión BD", use_container_width=True):
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
        
        with st.expander("🛠️ Herramientas"):
            # Botón para exportar datos
            if st.button("📤 Exportar Datos de Inscritos", use_container_width=True):
                if not df_inscritos.empty:
                    csv = df_inscritos.to_csv(index=False)
                    st.download_button(
                        label="⬇️ Descargar CSV",
                        data=csv,
                        file_name=f"inscritos_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("No hay datos para exportar")
            
            # Botón para crear backup
            if st.button("💾 Crear Backup de Base de Datos", use_container_width=True):
                try:
                    backup_file = f"backup_escuela_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                    
                    # En Streamlit Cloud, usar directorio temporal
                    if ENTORNO_DETECTADO == 'streamlit_cloud':
                        backup_path = f"/tmp/{backup_file}"
                    else:
                        backup_path = backup_file
                    
                    # Copiar archivo
                    import shutil
                    shutil.copy2(DB_ESCUELA, backup_path)
                    
                    st.success(f"✅ Backup creado: {backup_file}")
                    
                    # Ofrecer descarga
                    with open(backup_path, 'rb') as f:
                        st.download_button(
                            label="⬇️ Descargar Backup",
                            data=f,
                            file_name=backup_file,
                            mime="application/x-sqlite3"
                        )
                except Exception as e:
                    st.error(f"❌ Error creando backup: {e}")

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
