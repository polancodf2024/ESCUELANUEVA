"""
escuela10.py - Sistema de Gestión Escuela de Enfermería
Versión actualizada para usar SQLite con BCRYPT y estructura unificada
CONECTADO A SERVIDOR REMOTO VIA SECRETS.TOML
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
import paramiko  # Para conexión SSH
from pathlib import Path
warnings.filterwarnings('ignore')

# =============================================
# CONFIGURACIÓN DESDE SECRETS.TOML
# =============================================
try:
    # Leer configuración de secrets.toml
    SUPERVISOR_MODE = st.secrets.get("supervisor_mode", False)
    DEBUG_MODE = st.secrets.get("debug_mode", False)
    
    # Configuración de email
    SMTP_SERVER = st.secrets.get("smtp_server", "smtp.gmail.com")
    SMTP_PORT = st.secrets.get("smtp_port", 587)
    EMAIL_USER = st.secrets.get("email_user", "")
    EMAIL_PASSWORD = st.secrets.get("email_password", "")
    
    # Configuración SSH para servidor remoto
    REMOTE_HOST = st.secrets.get("remote_host", "localhost")
    REMOTE_PORT = st.secrets.get("remote_port", 22)
    REMOTE_USER = st.secrets.get("remote_user", "")
    REMOTE_PASSWORD = st.secrets.get("remote_password", "")
    REMOTE_DIR = st.secrets.get("remote_dir", "")
    
    # Rutas desde secrets.toml
    PATHS = st.secrets.get("paths", {})
    
    # Determinar entorno basado en supervisor_mode
    if SUPERVISOR_MODE:
        ENTORNO = "servidor"
        # Usar rutas del servidor remoto
        BASE_PATH = PATHS.get("base_path", "/home/POLANCO6/ESCUELANUEVA")
        DB_PATH = PATHS.get("db_escuela", "/home/POLANCO6/ESCUELANUEVA/datos/escuela.db")
        UPLOADS_PATH = PATHS.get("uploads_path", "/home/POLANCO6/ESCUELANUEVA/uploads")
    else:
        ENTORNO = "laptop"
        BASE_PATH = os.getcwd()
        DB_PATH = os.path.join(BASE_PATH, "escuela.db")
        UPLOADS_PATH = os.path.join(BASE_PATH, "uploads")
    
    CONFIG = {
        "base_path": BASE_PATH,
        "db_path": DB_PATH,
        "uploads_path": UPLOADS_PATH
    }
    
except Exception as e:
    st.error(f"❌ Error cargando configuración: {e}")
    # Valores por defecto
    ENTORNO = "laptop"
    CONFIG = {
        "base_path": os.getcwd(),
        "db_path": os.path.join(os.getcwd(), "escuela.db"),
        "uploads_path": os.path.join(os.getcwd(), "uploads")
    }

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de página
st.set_page_config(
    page_title="Sistema Escuela Enfermería",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# CLIENTE SSH PARA ACCESO REMOTO
# =============================================================================

class ClienteSSH:
    """Cliente para conexión SSH al servidor remoto"""
    
    def __init__(self):
        self.host = REMOTE_HOST
        self.port = REMOTE_PORT
        self.username = REMOTE_USER
        self.password = REMOTE_PASSWORD
        self.remote_dir = REMOTE_DIR
        self.client = None
        self.sftp = None
    
    def conectar(self):
        """Establecer conexión SSH"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10
            )
            self.sftp = self.client.open_sftp()
            logger.info(f"✅ Conexión SSH establecida a {self.host}")
            return True
        except Exception as e:
            logger.error(f"❌ Error conectando SSH: {e}")
            return False
    
    def desconectar(self):
        """Cerrar conexión SSH"""
        try:
            if self.sftp:
                self.sftp.close()
            if self.client:
                self.client.close()
            logger.info("🔌 Conexión SSH cerrada")
        except Exception as e:
            logger.error(f"Error cerrando conexión SSH: {e}")
    
    def descargar_archivo(self, remote_path, local_path):
        """Descargar archivo del servidor remoto"""
        try:
            if not self.sftp:
                if not self.conectar():
                    return False
            
            # Crear directorio local si no existe
            local_dir = os.path.dirname(local_path)
            os.makedirs(local_dir, exist_ok=True)
            
            # Descargar archivo
            self.sftp.get(remote_path, local_path)
            logger.info(f"📥 Archivo descargado: {remote_path} -> {local_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Error descargando archivo {remote_path}: {e}")
            return False
    
    def subir_archivo(self, local_path, remote_path):
        """Subir archivo al servidor remoto"""
        try:
            if not self.sftp:
                if not self.conectar():
                    return False
            
            # Subir archivo
            self.sftp.put(local_path, remote_path)
            logger.info(f"📤 Archivo subido: {local_path} -> {remote_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Error subiendo archivo {local_path}: {e}")
            return False
    
    def ejecutar_comando(self, comando):
        """Ejecutar comando en servidor remoto"""
        try:
            if not self.client:
                if not self.conectar():
                    return None
            
            stdin, stdout, stderr = self.client.exec_command(comando)
            salida = stdout.read().decode()
            error = stderr.read().decode()
            
            if error:
                logger.warning(f"Comando generó error: {error}")
            
            return salida
        except Exception as e:
            logger.error(f"❌ Error ejecutando comando: {e}")
            return None

# =============================================================================
# SISTEMA DE BASE DE DATOS SQLITE CON SOPORTE REMOTO
# =============================================================================

class SistemaBaseDatos:
    def __init__(self, db_path=None):
        # Usar la ruta configurada
        if db_path is None:
            self.db_path = CONFIG["db_path"]
        else:
            self.db_path = db_path
        
        self.es_remoto = SUPERVISOR_MODE
        self.cliente_ssh = None
        
        if self.es_remoto:
            self.cliente_ssh = ClienteSSH()
            logger.info(f"Modo remoto activado. Base de datos en: {self.db_path}")
        else:
            logger.info(f"Modo local. Base de datos en: {self.db_path}")
        
        # Crear directorio local si no existe
        if not self.es_remoto:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                try:
                    os.makedirs(db_dir, exist_ok=True)
                    logger.info(f"Directorio creado: {db_dir}")
                except Exception as e:
                    logger.warning(f"No se pudo crear directorio {db_dir}: {e}")
        
        # Inicializar tablas con manejo de errores
        try:
            self.init_tablas()
        except Exception as e:
            logger.error(f"Error inicializando tablas: {e}")
            # Intentar crear una base de datos mínima
            try:
                if not self.es_remoto:
                    conn = sqlite3.connect(self.db_path)
                    conn.close()
                    logger.info(f"Base de datos básica creada en: {self.db_path}")
                    # Reintentar inicialización
                    self.init_tablas()
                else:
                    # En modo remoto, crear base de datos local temporal
                    local_db_path = "escuela_temp.db"
                    conn = sqlite3.connect(local_db_path)
                    conn.close()
                    logger.info("Base de datos temporal creada localmente")
            except Exception as db_error:
                logger.error(f"Error crítico: {db_error}")
                raise
    
    @contextmanager
    def get_connection(self):
        """Context manager para manejar conexiones a la base de datos"""
        conn = None
        try:
            if self.es_remoto and self.cliente_ssh:
                # En modo remoto, sincronizar la base de datos primero
                local_db_path = "escuela_remote_temp.db"
                remote_db_path = self.db_path
                
                # Descargar la base de datos remota
                if os.path.exists(local_db_path):
                    # Verificar si la remota es más reciente
                    try:
                        stat_remoto = self.cliente_ssh.sftp.stat(remote_db_path)
                        stat_local = os.path.getmtime(local_db_path)
                        
                        if stat_remoto.st_mtime > stat_local:
                            self.cliente_ssh.descargar_archivo(remote_db_path, local_db_path)
                    except:
                        # Si hay error, descargar de nuevo
                        self.cliente_ssh.descargar_archivo(remote_db_path, local_db_path)
                else:
                    # Descargar por primera vez
                    self.cliente_ssh.descargar_archivo(remote_db_path, local_db_path)
                
                # Conectar a la base de datos local temporal
                conn = sqlite3.connect(local_db_path)
            else:
                # Modo local
                conn = sqlite3.connect(self.db_path)
            
            conn.row_factory = sqlite3.Row
            yield conn
            
            if conn:
                conn.commit()
                
                # En modo remoto, subir cambios al servidor
                if self.es_remoto and self.cliente_ssh:
                    local_db_path = "escuela_remote_temp.db"
                    remote_db_path = self.db_path
                    self.cliente_ssh.subir_archivo(local_db_path, remote_db_path)
                    
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error en transacción de base de datos: {e}")
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
    if SUPERVISOR_MODE:
        logger.info("🔗 Modo remoto activo - Conectado al servidor")
    else:
        logger.info("💻 Modo local activo")
except Exception as e:
    logger.error(f"❌ Error crítico inicializando base de datos: {e}")
    st.error(f"⚠️ Error inicializando base de datos: {e}")
    
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
# SISTEMA DE GESTIÓN DE INSCRIPCIONES
# =============================================================================

class SistemaInscripciones:
    def __init__(self):
        self.db = db
    
    def mostrar_formulario_inscripcion(self):
        """Mostrar formulario para nueva inscripción"""
        st.subheader("📝 Formulario de Inscripción")
        
        with st.form("formulario_inscripcion", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                nombre_completo = st.text_input("Nombre Completo*", placeholder="Ej: Juan Pérez González")
                email = st.text_input("Correo Electrónico*", placeholder="ejemplo@email.com")
                telefono = st.text_input("Teléfono*", placeholder="55 1234 5678")
                fecha_nacimiento = st.date_input("Fecha de Nacimiento*", 
                                                value=datetime.now() - timedelta(days=365*25),
                                                max_value=datetime.now())
            
            with col2:
                # Obtener programas disponibles
                programas_df = self.db.obtener_programas()
                programas_lista = []
                
                if not programas_df.empty:
                    programas_lista = programas_df['nombre'].tolist()
                
                programa_interes = st.selectbox("Programa de Interés*", 
                                              programas_lista if programas_lista else 
                                              ["Especialidad en Enfermería Cardiovascular",
                                               "Licenciatura en Enfermería",
                                               "Diplomado en Enfermería en Urgencias"])
                
                como_se_entero = st.selectbox("¿Cómo se enteró del programa?*",
                                            ["Internet", "Redes Sociales", "Amigo/Familiar", 
                                             "Publicidad", "Evento", "Otro"])
                
                # Campos opcionales
                documentos_subidos = st.number_input("Documentos Subidos", min_value=0, max_value=10, value=0)
                observaciones = st.text_area("Observaciones", placeholder="Información adicional...")
            
            submitted = st.form_submit_button("✅ Registrar Inscripción")
            
            if submitted:
                if not nombre_completo or not email or not telefono:
                    st.error("❌ Los campos marcados con * son obligatorios")
                    return None
                
                # Validar email
                if '@' not in email or '.' not in email:
                    st.error("❌ Por favor ingrese un correo electrónico válido")
                    return None
                
                # Preparar datos
                inscrito_data = {
                    'nombre_completo': nombre_completo,
                    'email': email,
                    'telefono': telefono,
                    'fecha_nacimiento': fecha_nacimiento,
                    'programa_interes': programa_interes,
                    'como_se_entero': como_se_entero,
                    'documentos_subidos': documentos_subidos,
                    'fecha_registro': datetime.now(),
                    'estatus': 'Pre-inscrito'
                }
                
                if observaciones:
                    inscrito_data['documentos_guardados'] = observaciones
                
                return inscrito_data
        
        return None
    
    def procesar_inscripcion(self, inscrito_data):
        """Procesar y guardar nueva inscripción"""
        try:
            with st.spinner("⏳ Procesando inscripción..."):
                inscrito_id, matricula = self.db.agregar_inscrito(inscrito_data)
                
                if inscrito_id and matricula:
                    # Registrar en bitácora
                    usuario_actual = st.session_state.get('usuario_actual', {})
                    usuario_nombre = usuario_actual.get('usuario', 'Sistema')
                    
                    self.db.registrar_bitacora(
                        usuario_nombre,
                        'INSCRIPCION_NUEVA',
                        f'Nueva inscripción: {inscrito_data["nombre_completo"]} - {matricula}'
                    )
                    
                    st.success(f"🎉 ¡Inscripción registrada exitosamente!")
                    st.info(f"**Matrícula asignada:** {matricula}")
                    st.info(f"**Nombre:** {inscrito_data['nombre_completo']}")
                    st.info(f"**Programa:** {inscrito_data['programa_interes']}")
                    
                    # Mostrar información de acceso
                    st.subheader("🔐 Información de Acceso")
                    st.info(f"**Usuario:** {matricula}")
                    st.info("**Contraseña temporal:** Los primeros 6 caracteres de la matrícula + '123'")
                    st.warning("⚠️ Recomendamos cambiar la contraseña en el primer acceso")
                    
                    return True
                else:
                    st.error("❌ Error al guardar la inscripción")
                    return False
                    
        except Exception as e:
            st.error(f"❌ Error procesando inscripción: {e}")
            return False
    
    def mostrar_lista_inscritos(self, df_inscritos):
        """Mostrar lista de inscritos con opciones"""
        if df_inscritos.empty:
            st.info("📭 No hay inscritos registrados")
            return
        
        st.subheader("📋 Lista de Inscritos")
        
        # Filtrar por búsqueda
        busqueda = st.text_input("🔍 Buscar por nombre o matrícula", key="buscar_inscritos")
        
        if busqueda:
            df_filtrado = df_inscritos[
                df_inscritos['nombre_completo'].str.contains(busqueda, case=False, na=False) |
                df_inscritos['matricula'].str.contains(busqueda, case=False, na=False)
            ]
        else:
            df_filtrado = df_inscritos
        
        if df_filtrado.empty:
            st.info("🔍 No se encontraron resultados")
            return
        
        # Mostrar estadísticas
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Inscritos", len(df_filtrado))
        with col2:
            preinscritos = len(df_filtrado[df_filtrado['estatus'] == 'Pre-inscrito'])
            st.metric("Pre-inscritos", preinscritos)
        with col3:
            otros = len(df_filtrado[df_filtrado['estatus'] != 'Pre-inscrito'])
            st.metric("Otros Estatus", otros)
        
        # Mostrar tabla con columnas seleccionadas
        columnas_mostrar = ['matricula', 'nombre_completo', 'email', 'telefono', 
                          'programa_interes', 'fecha_registro', 'estatus']
        
        st.dataframe(
            df_filtrado[columnas_mostrar],
            use_container_width=True,
            hide_index=True
        )
        
        # Opciones para cada inscrito
        st.subheader("⚙️ Acciones")
        inscritos_lista = df_filtrado['matricula'].tolist()
        
        if inscritos_lista:
            matricula_seleccionada = st.selectbox(
                "Seleccione una matrícula para ver detalles o acciones:",
                inscritos_lista,
                key="select_inscrito_acciones"
            )
            
            if matricula_seleccionada:
                inscrito = df_filtrado[df_filtrado['matricula'] == matricula_seleccionada].iloc[0]
                
                # Mostrar detalles
                with st.expander("📋 Ver Detalles Completos", expanded=False):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**Información Personal:**")
                        st.write(f"**Matrícula:** {inscrito.get('matricula', 'N/A')}")
                        st.write(f"**Nombre:** {inscrito.get('nombre_completo', 'N/A')}")
                        st.write(f"**Email:** {inscrito.get('email', 'N/A')}")
                        st.write(f"**Teléfono:** {inscrito.get('telefono', 'N/A')}")
                        if 'fecha_nacimiento' in inscrito and pd.notna(inscrito['fecha_nacimiento']):
                            st.write(f"**Fecha Nacimiento:** {inscrito['fecha_nacimiento']}")
                    
                    with col2:
                        st.write("**Información Académica:**")
                        st.write(f"**Programa de Interés:** {inscrito.get('programa_interes', 'N/A')}")
                        st.write(f"**Fecha Registro:** {inscrito.get('fecha_registro', 'N/A')}")
                        st.write(f"**Estatus:** {inscrito.get('estatus', 'N/A')}")
                        st.write(f"**Folio:** {inscrito.get('folio', 'N/A')}")
                        st.write(f"**Como se enteró:** {inscrito.get('como_se_entero', 'N/A')}")
                        if 'documentos_subidos' in inscrito:
                            st.write(f"**Documentos Subidos:** {inscrito['documentos_subidos']}")
                
                # Acciones
                col_acc1, col_acc2, col_acc3 = st.columns(3)
                
                with col_acc1:
                    if st.button("✏️ Editar Inscrito", key=f"editar_{matricula_seleccionada}"):
                        st.session_state.editar_inscrito = matricula_seleccionada
                        st.rerun()
                
                with col_acc2:
                    if st.button("📧 Enviar Recordatorio", key=f"recordatorio_{matricula_seleccionada}"):
                        self.enviar_recordatorio(inscrito)
                
                with col_acc3:
                    if st.button("🗑️ Eliminar Inscrito", key=f"eliminar_{matricula_seleccionada}"):
                        if self.eliminar_inscrito(matricula_seleccionada):
                            st.success(f"✅ Inscrito {matricula_seleccionada} eliminado")
                            time.sleep(2)
                            st.rerun()
    
    def editar_inscrito(self, matricula, df_inscritos):
        """Formulario para editar inscrito"""
        st.subheader(f"✏️ Editar Inscrito: {matricula}")
        
        # Buscar inscrito
        inscrito = df_inscritos[df_inscritos['matricula'] == matricula]
        
        if inscrito.empty:
            st.error("❌ Inscrito no encontrado")
            return
        
        inscrito_data = inscrito.iloc[0].to_dict()
        
        with st.form("formulario_editar_inscrito"):
            col1, col2 = st.columns(2)
            
            with col1:
                nombre_completo = st.text_input("Nombre Completo*", 
                                              value=inscrito_data.get('nombre_completo', ''))
                email = st.text_input("Correo Electrónico*", 
                                    value=inscrito_data.get('email', ''))
                telefono = st.text_input("Teléfono*", 
                                       value=inscrito_data.get('telefono', ''))
            
            with col2:
                programa_interes = st.text_input("Programa de Interés", 
                                               value=inscrito_data.get('programa_interes', ''))
                estatus = st.selectbox("Estatus", 
                                     ["Pre-inscrito", "Documentación Pendiente", "Aceptado", "Rechazado"],
                                     index=["Pre-inscrito", "Documentación Pendiente", "Aceptado", "Rechazado"]
                                     .index(inscrito_data.get('estatus', 'Pre-inscrito')))
                documentos_subidos = st.number_input("Documentos Subidos", 
                                                   value=int(inscrito_data.get('documentos_subidos', 0)),
                                                   min_value=0, max_value=10)
            
            observaciones = st.text_area("Observaciones", 
                                       value=inscrito_data.get('documentos_guardados', ''))
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                guardar = st.form_submit_button("💾 Guardar Cambios")
            with col_btn2:
                cancelar = st.form_submit_button("❌ Cancelar")
            
            if guardar:
                if not nombre_completo or not email or not telefono:
                    st.error("❌ Los campos marcados con * son obligatorios")
                    return
                
                datos_actualizados = {
                    'nombre_completo': nombre_completo,
                    'email': email,
                    'telefono': telefono,
                    'programa_interes': programa_interes,
                    'estatus': estatus,
                    'documentos_subidos': documentos_subidos,
                    'documentos_guardados': observaciones
                }
                
                if self.db.actualizar_inscrito(matricula, datos_actualizados):
                    st.success("✅ Cambios guardados exitosamente")
                    
                    # Registrar en bitácora
                    usuario_actual = st.session_state.get('usuario_actual', {})
                    usuario_nombre = usuario_actual.get('usuario', 'Sistema')
                    
                    self.db.registrar_bitacora(
                        usuario_nombre,
                        'INSCRITO_ACTUALIZADO',
                        f'Inscrito actualizado: {matricula}'
                    )
                    
                    time.sleep(2)
                    if 'editar_inscrito' in st.session_state:
                        del st.session_state.editar_inscrito
                    st.rerun()
                else:
                    st.error("❌ Error al guardar cambios")
            
            if cancelar:
                if 'editar_inscrito' in st.session_state:
                    del st.session_state.editar_inscrito
                st.rerun()
    
    def eliminar_inscrito(self, matricula):
        """Eliminar inscrito"""
        try:
            confirmacion = st.checkbox("⚠️ Confirmar eliminación permanente")
            
            if confirmacion:
                if st.button("🗑️ Sí, eliminar definitivamente", type="primary"):
                    if self.db.eliminar_inscrito(matricula):
                        # Registrar en bitácora
                        usuario_actual = st.session_state.get('usuario_actual', {})
                        usuario_nombre = usuario_actual.get('usuario', 'Sistema')
                        
                        self.db.registrar_bitacora(
                            usuario_nombre,
                            'INSCRITO_ELIMINADO',
                            f'Inscrito eliminado: {matricula}'
                        )
                        
                        return True
                    else:
                        st.error("❌ Error al eliminar inscrito")
            
            return False
        except Exception as e:
            st.error(f"❌ Error eliminando inscrito: {e}")
            return False
    
    def enviar_recordatorio(self, inscrito):
        """Enviar recordatorio por email (simulado)"""
        st.info("📧 Función de envío de recordatorios en desarrollo")
        st.info(f"Se enviaría un recordatorio a: {inscrito.get('email', '')}")
        # Aquí iría la lógica real de envío de emails

# =============================================================================
# SISTEMA DE GESTIÓN DE ESTUDIANTES
# =============================================================================

class SistemaEstudiantes:
    def __init__(self):
        self.db = db
    
    def mostrar_lista_estudiantes(self, df_estudiantes):
        """Mostrar lista de estudiantes"""
        if df_estudiantes.empty:
            st.info("🎓 No hay estudiantes registrados")
            return
        
        st.subheader("🎓 Lista de Estudiantes")
        
        # Filtrar por búsqueda
        busqueda = st.text_input("🔍 Buscar por nombre o matrícula", key="buscar_estudiantes")
        
        if busqueda:
            df_filtrado = df_estudiantes[
                df_estudiantes['nombre_completo'].str.contains(busqueda, case=False, na=False) |
                df_estudiantes['matricula'].str.contains(busqueda, case=False, na=False)
            ]
        else:
            df_filtrado = df_estudiantes
        
        if df_filtrado.empty:
            st.info("🔍 No se encontraron resultados")
            return
        
        # Mostrar estadísticas
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Estudiantes", len(df_filtrado))
        with col2:
            activos = len(df_filtrado[df_filtrado['estatus'] == 'ACTIVO'])
            st.metric("Activos", activos)
        with col3:
            inactivos = len(df_filtrado[df_filtrado['estatus'] != 'ACTIVO'])
            st.metric("Inactivos", inactivos)
        
        # Mostrar tabla con columnas seleccionadas
        columnas_mostrar = ['matricula', 'nombre_completo', 'programa', 'email', 
                          'telefono', 'fecha_ingreso', 'estatus']
        
        st.dataframe(
            df_filtrado[columnas_mostrar],
            use_container_width=True,
            hide_index=True
        )
        
        # Opciones para cada estudiante
        if st.checkbox("📋 Ver detalles de estudiante específico"):
            estudiantes_lista = df_filtrado['matricula'].tolist()
            
            if estudiantes_lista:
                matricula_seleccionada = st.selectbox(
                    "Seleccione una matrícula:",
                    estudiantes_lista,
                    key="select_estudiante_detalles"
                )
                
                if matricula_seleccionada:
                    estudiante = df_filtrado[df_filtrado['matricula'] == matricula_seleccionada].iloc[0]
                    self.mostrar_detalles_estudiante(estudiante)
    
    def mostrar_detalles_estudiante(self, estudiante):
        """Mostrar detalles completos de un estudiante"""
        st.subheader(f"📋 Detalles del Estudiante: {estudiante.get('matricula', '')}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Información Personal:**")
            st.write(f"**Matrícula:** {estudiante.get('matricula', 'N/A')}")
            st.write(f"**Nombre:** {estudiante.get('nombre_completo', 'N/A')}")
            st.write(f"**Email:** {estudiante.get('email', 'N/A')}")
            st.write(f"**Teléfono:** {estudiante.get('telefono', 'N/A')}")
            if 'fecha_nacimiento' in estudiante and pd.notna(estudiante['fecha_nacimiento']):
                st.write(f"**Fecha Nacimiento:** {estudiante['fecha_nacimiento']}")
            if 'genero' in estudiante:
                st.write(f"**Género:** {estudiante['genero']}")
        
        with col2:
            st.write("**Información Académica:**")
            st.write(f"**Programa:** {estudiante.get('programa', 'N/A')}")
            st.write(f"**Fecha Inscripción:** {estudiante.get('fecha_inscripcion', 'N/A')}")
            st.write(f"**Fecha Ingreso:** {estudiante.get('fecha_ingreso', 'N/A')}")
            st.write(f"**Estatus:** {estudiante.get('estatus', 'N/A')}")
            if 'programa_interes' in estudiante:
                st.write(f"**Programa Interés Original:** {estudiante['programa_interes']}")
            if 'folio' in estudiante:
                st.write(f"**Folio:** {estudiante['folio']}")
            if 'como_se_entero' in estudiante:
                st.write(f"**Como se enteró:** {estudiante['como_se_entero']}")

# =============================================================================
# SISTEMA DE GESTIÓN DE EGRESADOS
# =============================================================================

class SistemaEgresados:
    def __init__(self):
        self.db = db
    
    def mostrar_lista_egresados(self, df_egresados):
        """Mostrar lista de egresados"""
        if df_egresados.empty:
            st.info("🎓 No hay egresados registrados")
            return
        
        st.subheader("🎓 Lista de Egresados")
        
        # Filtrar por búsqueda
        busqueda = st.text_input("🔍 Buscar por nombre o matrícula", key="buscar_egresados")
        
        if busqueda:
            df_filtrado = df_egresados[
                df_egresados['nombre_completo'].str.contains(busqueda, case=False, na=False) |
                df_egresados['matricula'].str.contains(busqueda, case=False, na=False)
            ]
        else:
            df_filtrado = df_egresados
        
        if df_filtrado.empty:
            st.info("🔍 No se encontraron resultados")
            return
        
        # Mostrar estadísticas
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Egresados", len(df_filtrado))
        with col2:
            empleados = len(df_filtrado[df_filtrado['estado_laboral'] == 'Contratada'])
            st.metric("Empleados", empleados)
        with col3:
            buscando = len(df_filtrado[df_filtrado['estado_laboral'] == 'Buscando empleo'])
            st.metric("Buscando empleo", buscando)
        
        # Mostrar tabla con columnas seleccionadas
        columnas_mostrar = ['matricula', 'nombre_completo', 'programa_original', 
                          'nivel_academico', 'email', 'estado_laboral', 'fecha_graduacion']
        
        st.dataframe(
            df_filtrado[columnas_mostrar],
            use_container_width=True,
            hide_index=True
        )
        
        # Opciones para cada egresado
        if st.checkbox("📋 Ver detalles de egresado específico"):
            egresados_lista = df_filtrado['matricula'].tolist()
            
            if egresados_lista:
                matricula_seleccionada = st.selectbox(
                    "Seleccione una matrícula:",
                    egresados_lista,
                    key="select_egresado_detalles"
                )
                
                if matricula_seleccionada:
                    egresado = df_filtrado[df_filtrado['matricula'] == matricula_seleccionada].iloc[0]
                    self.mostrar_detalles_egresado(egresado)
    
    def mostrar_detalles_egresado(self, egresado):
        """Mostrar detalles completos de un egresado"""
        st.subheader(f"📋 Detalles del Egresado: {egresado.get('matricula', '')}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Información Personal:**")
            st.write(f"**Matrícula:** {egresado.get('matricula', 'N/A')}")
            st.write(f"**Nombre:** {egresado.get('nombre_completo', 'N/A')}")
            st.write(f"**Email:** {egresado.get('email', 'N/A')}")
            st.write(f"**Teléfono:** {egresado.get('telefono', 'N/A')}")
            st.write(f"**Estado Laboral:** {egresado.get('estado_laboral', 'N/A')}")
        
        with col2:
            st.write("**Información Académica:**")
            st.write(f"**Programa Original:** {egresado.get('programa_original', 'N/A')}")
            st.write(f"**Fecha Graduación:** {egresado.get('fecha_graduacion', 'N/A')}")
            st.write(f"**Nivel Académico:** {egresado.get('nivel_academico', 'N/A')}")
            st.write(f"**Fecha Actualización:** {egresado.get('fecha_actualizacion', 'N/A')}")
            if 'documentos_subidos' in egresado:
                st.write(f"**Documentos:** {egresado['documentos_subidos']}")

# =============================================================================
# SISTEMA DE GESTIÓN DE CONTRATADOS
# =============================================================================

class SistemaContratados:
    def __init__(self):
        self.db = db
    
    def mostrar_lista_contratados(self, df_contratados):
        """Mostrar lista de contratados"""
        if df_contratados.empty:
            st.info("💼 No hay contratados registrados")
            return
        
        st.subheader("💼 Lista de Contratados")
        
        # Filtrar por búsqueda
        busqueda = st.text_input("🔍 Buscar por matrícula", key="buscar_contratados")
        
        if busqueda:
            df_filtrado = df_contratados[
                df_contratados['matricula'].str.contains(busqueda, case=False, na=False)
            ]
        else:
            df_filtrado = df_contratados
        
        if df_filtrado.empty:
            st.info("🔍 No se encontraron resultados")
            return
        
        # Mostrar estadísticas
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Contratados", len(df_filtrado))
        with col2:
            activos = len(df_filtrado[df_filtrado['estatus'] == 'Activo'])
            st.metric("Activos", activos)
        with col3:
            inactivos = len(df_filtrado[df_filtrado['estatus'] != 'Activo'])
            st.metric("Inactivos", inactivos)
        
        # Mostrar tabla con columnas seleccionadas
        columnas_mostrar = ['matricula', 'puesto', 'departamento', 
                          'estatus', 'salario', 'tipo_contrato', 'fecha_contratacion']
        
        st.dataframe(
            df_filtrado[columnas_mostrar],
            use_container_width=True,
            hide_index=True
        )

# =============================================================================
# SISTEMA DE GESTIÓN DE USUARIOS
# =============================================================================

class SistemaUsuarios:
    def __init__(self):
        self.db = db
    
    def mostrar_lista_usuarios(self, df_usuarios):
        """Mostrar lista de usuarios"""
        if df_usuarios.empty:
            st.info("👥 No hay usuarios registrados")
            return
        
        st.subheader("👥 Lista de Usuarios")
        
        # Solo administradores pueden ver esta sección
        rol_usuario = st.session_state.get('rol_usuario', '')
        if rol_usuario != 'administrador':
            st.warning("⚠️ Solo los administradores pueden acceder a esta sección")
            return
        
        # Filtrar por búsqueda
        busqueda = st.text_input("🔍 Buscar por usuario o nombre", key="buscar_usuarios")
        
        if busqueda:
            df_filtrado = df_usuarios[
                df_usuarios['usuario'].str.contains(busqueda, case=False, na=False) |
                df_usuarios['nombre_completo'].str.contains(busqueda, case=False, na=False)
            ]
        else:
            df_filtrado = df_usuarios
        
        if df_filtrado.empty:
            st.info("🔍 No se encontraron resultados")
            return
        
        # Mostrar estadísticas
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Usuarios", len(df_filtrado))
        with col2:
            activos = len(df_filtrado[df_filtrado['activo'] == 1])
            st.metric("Activos", activos)
        with col3:
            admin = len(df_filtrado[df_filtrado['rol'] == 'administrador'])
            st.metric("Administradores", admin)
        
        # Mostrar tabla con columnas seleccionadas
        columnas_mostrar = ['usuario', 'nombre_completo', 'rol', 'matricula', 
                          'email', 'activo', 'fecha_creacion']
        
        st.dataframe(
            df_filtrado[columnas_mostrar],
            use_container_width=True,
            hide_index=True
        )
        
        # Opciones para administrador
        if st.checkbox("🛠️ Herramientas de Administrador"):
            self.mostrar_herramientas_admin(df_filtrado)
    
    def mostrar_herramientas_admin(self, df_usuarios):
        """Mostrar herramientas de administración de usuarios"""
        st.subheader("🛠️ Herramientas de Administración")
        
        tab1, tab2, tab3 = st.tabs(["➕ Nuevo Usuario", "✏️ Editar Usuario", "🔧 Configuración"])
        
        with tab1:
            self.formulario_nuevo_usuario()
        
        with tab2:
            self.formulario_editar_usuario(df_usuarios)
        
        with tab3:
            st.info("Configuración del sistema")
            if st.button("🔄 Recrear Base de Datos", type="secondary"):
                if st.checkbox("⚠️ Esta acción eliminará todos los datos existentes"):
                    if st.button("✅ Confirmar recreación", type="primary"):
                        try:
                            # En modo remoto, eliminar archivo remoto
                            if SUPERVISOR_MODE and db.cliente_ssh:
                                db.cliente_ssh.ejecutar_comando(f"rm -f {CONFIG['db_path']}")
                                st.success("✅ Base de datos remota eliminada")
                            else:
                                # Modo local
                                if os.path.exists(CONFIG['db_path']):
                                    os.remove(CONFIG['db_path'])
                                    st.success("✅ Base de datos local eliminada")
                            
                            st.info("🔄 Por favor, recarga la página para recrear la base de datos")
                        except Exception as e:
                            st.error(f"❌ Error: {e}")
    
    def formulario_nuevo_usuario(self):
        """Formulario para crear nuevo usuario"""
        with st.form("form_nuevo_usuario"):
            st.write("### ➕ Crear Nuevo Usuario")
            
            col1, col2 = st.columns(2)
            
            with col1:
                usuario = st.text_input("Usuario*", placeholder="nombre.usuario")
                nombre_completo = st.text_input("Nombre Completo*", placeholder="Nombre Apellidos")
                email = st.text_input("Email*", placeholder="usuario@escuela.edu.mx")
                matricula = st.text_input("Matrícula", placeholder="MAT-XXX-000")
            
            with col2:
                rol = st.selectbox("Rol*", ["inscrito", "estudiante", "egresado", "contratado", "administrador"])
                password = st.text_input("Contraseña*", type="password", placeholder="********")
                confirm_password = st.text_input("Confirmar Contraseña*", type="password", placeholder="********")
                activo = st.checkbox("Usuario Activo", value=True)
            
            crear = st.form_submit_button("✅ Crear Usuario")
            
            if crear:
                if not usuario or not nombre_completo or not email or not password:
                    st.error("❌ Los campos marcados con * son obligatorios")
                    return
                
                if password != confirm_password:
                    st.error("❌ Las contraseñas no coinciden")
                    return
                
                if len(password) < 8:
                    st.error("❌ La contraseña debe tener al menos 8 caracteres")
                    return
                
                # Crear usuario en la base de datos
                try:
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()
                        
                        # Verificar si el usuario ya existe
                        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE usuario = ?", (usuario,))
                        if cursor.fetchone()[0] > 0:
                            st.error("❌ El usuario ya existe")
                            return
                        
                        # Hash de la contraseña
                        password_hash_str, salt_hex = self.db.hash_password(password)
                        
                        # Insertar nuevo usuario
                        cursor.execute('''
                            INSERT INTO usuarios 
                            (usuario, password_hash, salt, rol, nombre_completo,
                             nombre, email, matricula, activo)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            usuario,
                            password_hash_str,
                            salt_hex,
                            rol,
                            nombre_completo,
                            nombre_completo,  # nombre = nombre_completo
                            email,
                            matricula if matricula else None,
                            1 if activo else 0
                        ))
                        
                        # Registrar en bitácora
                        usuario_actual = st.session_state.get('usuario_actual', {})
                        admin_nombre = usuario_actual.get('usuario', 'Sistema')
                        
                        self.db.registrar_bitacora(
                            admin_nombre,
                            'USUARIO_CREADO',
                            f'Nuevo usuario creado: {usuario} ({rol})'
                        )
                        
                        st.success(f"✅ Usuario '{usuario}' creado exitosamente")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ Error creando usuario: {e}")
    
    def formulario_editar_usuario(self, df_usuarios):
        """Formulario para editar usuario existente"""
        st.write("### ✏️ Editar Usuario Existente")
        
        usuarios_lista = df_usuarios['usuario'].tolist()
        
        if not usuarios_lista:
            st.info("No hay usuarios para editar")
            return
        
        usuario_seleccionado = st.selectbox(
            "Seleccionar usuario a editar:",
            usuarios_lista,
            key="select_usuario_editar"
        )
        
        if usuario_seleccionado:
            usuario_data = df_usuarios[df_usuarios['usuario'] == usuario_seleccionado].iloc[0]
            
            with st.form("form_editar_usuario"):
                col1, col2 = st.columns(2)
                
                with col1:
                    nuevo_usuario = st.text_input("Usuario", value=usuario_data.get('usuario', ''))
                    nuevo_nombre = st.text_input("Nombre Completo", value=usuario_data.get('nombre_completo', ''))
                    nuevo_email = st.text_input("Email", value=usuario_data.get('email', ''))
                    nueva_matricula = st.text_input("Matrícula", value=usuario_data.get('matricula', ''))
                
                with col2:
                    nuevo_rol = st.selectbox(
                        "Rol", 
                        ["inscrito", "estudiante", "egresado", "contratado", "administrador"],
                        index=["inscrito", "estudiante", "egresado", "contratado", "administrador"]
                        .index(usuario_data.get('rol', 'inscrito'))
                    )
                    nuevo_activo = st.checkbox("Usuario Activo", value=bool(usuario_data.get('activo', 1)))
                    
                    st.write("---")
                    st.write("**Cambiar Contraseña (opcional)**")
                    nueva_password = st.text_input("Nueva Contraseña", type="password", placeholder="Dejar en blanco para no cambiar")
                    confirm_password = st.text_input("Confirmar Contraseña", type="password")
                
                guardar = st.form_submit_button("💾 Guardar Cambios")
                
                if guardar:
                    if not nuevo_usuario or not nuevo_nombre or not nuevo_email:
                        st.error("❌ Los campos de usuario, nombre y email son obligatorios")
                        return
                    
                    if nueva_password and nueva_password != confirm_password:
                        st.error("❌ Las contraseñas no coinciden")
                        return
                    
                    if nueva_password and len(nueva_password) < 8:
                        st.error("❌ La contraseña debe tener al menos 8 caracteres")
                        return
                    
                    # Preparar datos para actualizar
                    datos_actualizados = {
                        'usuario': nuevo_usuario,
                        'nombre_completo': nuevo_nombre,
                        'nombre': nuevo_nombre,
                        'email': nuevo_email,
                        'matricula': nueva_matricula if nueva_matricula else None,
                        'rol': nuevo_rol,
                        'activo': 1 if nuevo_activo else 0
                    }
                    
                    # Si hay nueva contraseña, actualizarla
                    if nueva_password:
                        password_hash_str, salt_hex = self.db.hash_password(nueva_password)
                        datos_actualizados['password_hash'] = password_hash_str
                        datos_actualizados['salt'] = salt_hex
                    
                    # Actualizar usuario
                    if self.db.actualizar_usuario(usuario_data['id'], datos_actualizados):
                        # Registrar en bitácora
                        usuario_actual = st.session_state.get('usuario_actual', {})
                        admin_nombre = usuario_actual.get('usuario', 'Sistema')
                        
                        self.db.registrar_bitacora(
                            admin_nombre,
                            'USUARIO_ACTUALIZADO',
                            f'Usuario actualizado: {usuario_seleccionado} -> {nuevo_usuario}'
                        )
                        
                        st.success("✅ Usuario actualizado exitosamente")
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error("❌ Error actualizando usuario")

# =============================================================================
# SISTEMA DE REPORTES Y ESTADÍSTICAS
# =============================================================================

class SistemaReportes:
    def __init__(self):
        self.db = db
    
    def mostrar_estadisticas_generales(self, datos):
        """Mostrar estadísticas generales del sistema"""
        st.subheader("📊 Estadísticas Generales")
        
        # Obtener estadísticas de la base de datos
        estadisticas = self.db.obtener_estadisticas_generales()
        
        if not estadisticas:
            st.info("No hay estadísticas disponibles")
            return
        
        # Mostrar métricas principales
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Inscritos", estadisticas.get('total_inscritos', 0))
        with col2:
            st.metric("Estudiantes", estadisticas.get('total_estudiantes', 0))
        with col3:
            st.metric("Egresados", estadisticas.get('total_egresados', 0))
        with col4:
            st.metric("Contratados", estadisticas.get('total_contratados', 0))
        with col5:
            st.metric("Usuarios", estadisticas.get('total_usuarios', 0))
        
        # Gráficos y análisis
        col_graf1, col_graf2 = st.columns(2)
        
        with col_graf1:
            st.subheader("📈 Distribución por Programa")
            if estadisticas.get('inscritos_por_programa'):
                df_programas = pd.DataFrame(
                    estadisticas['inscritos_por_programa'],
                    columns=['programa', 'cantidad']
                )
                if not df_programas.empty:
                    st.bar_chart(df_programas.set_index('programa'))
        
        with col_graf2:
            st.subheader("🎓 Niveles Académicos")
            if estadisticas.get('egresados_por_nivel'):
                df_niveles = pd.DataFrame(
                    estadisticas['egresados_por_nivel'],
                    columns=['nivel', 'cantidad']
                )
                if not df_niveles.empty:
                    st.bar_chart(df_niveles.set_index('nivel'))
        
        # Tabla de estudiantes por estatus
        st.subheader("📋 Estudiantes por Estatus")
        if estadisticas.get('estudiantes_por_estatus'):
            df_estatus = pd.DataFrame(
                estadisticas['estudiantes_por_estatus'],
                columns=['estatus', 'cantidad']
            )
            if not df_estatus.empty:
                st.dataframe(df_estatus, use_container_width=True, hide_index=True)
    
    def mostrar_reporte_inscripciones(self, df_inscritos):
        """Mostrar reporte detallado de inscripciones"""
        st.subheader("📋 Reporte de Inscripciones")
        
        if df_inscritos.empty:
            st.info("No hay datos de inscripciones")
            return
        
        # Filtros de fecha
        col_fecha1, col_fecha2 = st.columns(2)
        with col_fecha1:
            fecha_inicio = st.date_input("Fecha inicio", 
                                        value=datetime.now() - timedelta(days=30))
        with col_fecha2:
            fecha_fin = st.date_input("Fecha fin", value=datetime.now())
        
        # Convertir fechas a datetime
        fecha_inicio_dt = datetime.combine(fecha_inicio, datetime.min.time())
        fecha_fin_dt = datetime.combine(fecha_fin, datetime.max.time())
        
        # Filtrar por fecha
        df_inscritos['fecha_registro_dt'] = pd.to_datetime(df_inscritos['fecha_registro'])
        df_filtrado = df_inscritos[
            (df_inscritos['fecha_registro_dt'] >= fecha_inicio_dt) &
            (df_inscritos['fecha_registro_dt'] <= fecha_fin_dt)
        ]
        
        if df_filtrado.empty:
            st.info(f"No hay inscripciones entre {fecha_inicio} y {fecha_fin}")
            return
        
        # Métricas del período
        col_met1, col_met2, col_met3 = st.columns(3)
        with col_met1:
            st.metric("Inscripciones totales", len(df_filtrado))
        with col_met2:
            st.metric("Inscripciones/día", round(len(df_filtrado) / 30, 1))
        with col_met3:
            programas_unicos = df_filtrado['programa_interes'].nunique()
            st.metric("Programas diferentes", programas_unicos)
        
        # Gráfico de inscripciones por día
        st.subheader("📈 Inscripciones por Día")
        df_diario = df_filtrado.copy()
        df_diario['fecha'] = df_diario['fecha_registro_dt'].dt.date
        conteo_diario = df_diario.groupby('fecha').size().reset_index(name='inscripciones')
        
        if not conteo_diario.empty:
            st.line_chart(conteo_diario.set_index('fecha'))
        
        # Tabla detallada
        st.subheader("📋 Detalle de Inscripciones")
        columnas_mostrar = ['matricula', 'nombre_completo', 'email', 'programa_interes', 
                          'fecha_registro', 'estatus']
        st.dataframe(df_filtrado[columnas_mostrar], use_container_width=True, hide_index=True)
        
        # Opción de exportación
        if st.button("📥 Exportar a CSV"):
            csv = df_filtrado[columnas_mostrar].to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Descargar CSV",
                data=csv,
                file_name=f"inscripciones_{fecha_inicio}_{fecha_fin}.csv",
                mime="text/csv"
            )

# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================

def mostrar_login():
    """Interfaz de login"""
    st.title("🏥 Sistema Escuela de Enfermería")
    st.markdown("---")
    
    # Mostrar entorno actual
    if SUPERVISOR_MODE:
        st.success(f"**🌍 MODO SERVIDOR REMOTO** - Conectado a: {REMOTE_HOST}")
    else:
        st.info(f"**💻 MODO LOCAL** - Base de datos local")
    
    st.info(f"**📁 Base de datos:** {CONFIG['db_path']}")
    
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

def mostrar_interfaz_principal():
    """Interfaz principal del sistema"""
    st.title("🏥 Sistema Escuela de Enfermería")
    
    # Barra superior
    usuario_actual = st.session_state.usuario_actual
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        if SUPERVISOR_MODE:
            st.success(f"**🌍 SERVIDOR REMOTO** - {REMOTE_HOST}")
        else:
            st.info("💻 MODO LOCAL")
        
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
    st.sidebar.title("📊 Menú Principal")
    
    opcion_menu = st.sidebar.selectbox(
        "Seleccione una opción:",
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
            if SUPERVISOR_MODE:
                st.success("✅ **MODO SERVIDOR REMOTO ACTIVO**")
                st.info(f"**Servidor:** {REMOTE_HOST}")
                st.info(f"**Usuario:** {REMOTE_USER}")
                st.info(f"**Directorio remoto:** {REMOTE_DIR}")
            else:
                st.info("💻 **MODO LOCAL ACTIVO**")
            
            st.info(f"**Ruta base de datos:** {CONFIG['db_path']}")
            st.info(f"**Ruta uploads:** {CONFIG['uploads_path']}")
            
            # Test de conexión SSH
            if SUPERVISOR_MODE:
                if st.button("🔗 Probar conexión SSH"):
                    with st.spinner("Probando conexión..."):
                        cliente = ClienteSSH()
                        if cliente.conectar():
                            st.success("✅ Conexión SSH exitosa")
                            cliente.desconectar()
                        else:
                            st.error("❌ Error de conexión SSH")
        
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
                except Exception as e:
                    st.error(f"❌ Error: {e}")

def mostrar_dashboard(datos, sistema_reportes):
    """Mostrar dashboard principal"""
    st.header("🏠 Dashboard Principal")
    
    # Mostrar modo de conexión
    if SUPERVISOR_MODE:
        st.success(f"🔗 **Conectado al servidor remoto:** {REMOTE_HOST}")
    else:
        st.info("💻 **Ejecutando en modo local**")
    
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
    
    # Configuración del sidebar
    st.sidebar.title("⚙️ Configuración")
    
    if SUPERVISOR_MODE:
        st.sidebar.success("🌍 **SERVIDOR REMOTO**")
        st.sidebar.info(f"**Host:** {REMOTE_HOST}")
    else:
        st.sidebar.info("💻 **MODO LOCAL**")
    
    st.sidebar.info(f"**Versión:** 10.0 (SQLite + BCRYPT)")
    
    st.sidebar.markdown("---")
    st.sidebar.info("**Características:**")
    st.sidebar.info("✅ Autenticación BCRYPT")
    st.sidebar.info("✅ Base de datos SQLite")
    st.sidebar.info("✅ Compatible con migracion10.py")
    if SUPERVISOR_MODE:
        st.sidebar.success("✅ Conectado a servidor remoto")
    else:
        st.sidebar.info("✅ Modo local activo")
    
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
