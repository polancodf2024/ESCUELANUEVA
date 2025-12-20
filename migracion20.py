"""
migracion20.py - Sistema de migración con BCRYPT y SSH
Versión completa corregida - EXCLUSIVAMENTE MODO REMOTO SSH
Sistema completo de migración con base de datos SQLite remota
NO SOPORTA MODO LOCAL - SIEMPRE CONECTA AL SERVIDOR REMOTO
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
import paramiko
from io import StringIO, BytesIO
import time
import hashlib
import base64
import warnings
import sqlite3
import tempfile
import shutil
from contextlib import contextmanager
import logging
import bcrypt
import subprocess
import sys
warnings.filterwarnings('ignore')

# Intentar importar tomllib (Python 3.11+) o tomli (Python < 3.11)
try:
    import tomllib  # Python 3.11+
    HAS_TOMLLIB = True
except ImportError:
    try:
        import tomli as tomllib  # Python < 3.11
        HAS_TOMLLIB = True
    except ImportError:
        HAS_TOMLLIB = False
        st.error("❌ ERROR CRÍTICO: No se encontró tomllib o tomli. Instalar con: pip install tomli")
        st.stop()

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuración de página
st.set_page_config(
    page_title="Sistema Escuela Enfermería - Migración SSH REMOTA",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# FUNCIÓN PARA LEER SECRETS.TOML - VERSIÓN MEJORADA
# =============================================================================

def cargar_configuracion_secrets():
    """Cargar configuración desde secrets.toml - VERSIÓN EXCLUSIVA REMOTA"""
    try:
        if not HAS_TOMLLIB:
            logger.error("❌ ERROR: No se puede cargar secrets.toml sin tomllib/tomli")
            return {}
        
        # Buscar el archivo secrets.toml en posibles ubicaciones
        posibles_rutas = [
            ".streamlit/secrets.toml",          # Primera prioridad: Streamlit Cloud
            "secrets.toml",                     # Segunda prioridad: directorio actual
            "./.streamlit/secrets.toml",        # Para desarrollo
            "../.streamlit/secrets.toml",       # Para desarrollo
            "/mount/src/escuelanueva/.streamlit/secrets.toml",  # Ruta absoluta
            "config/secrets.toml",              # Subdirectorio config
            os.path.join(os.path.dirname(__file__), ".streamlit/secrets.toml")
        ]
        
        ruta_encontrada = None
        for ruta in posibles_rutas:
            if os.path.exists(ruta):
                ruta_encontrada = ruta
                logger.info(f"📁 Archivo secrets.toml encontrado en: {ruta}")
                break
        
        if not ruta_encontrada:
            logger.error("❌ ERROR CRÍTICO: No se encontró secrets.toml en ninguna ubicación")
            return {}
        
        # Leer el archivo
        with open(ruta_encontrada, 'rb') as f:
            config = tomllib.load(f)
            logger.info(f"✅ Configuración cargada desde: {ruta_encontrada}")
            return config
        
    except Exception as e:
        logger.error(f"❌ Error cargando secrets.toml: {e}")
        import traceback
        logger.error(f"❌ Detalles: {traceback.format_exc()}")
        return {}

# =============================================================================
# ARCHIVO DE ESTADO PERSISTENTE PARA MIGRACIÓN
# =============================================================================

class EstadoPersistenteMigracion:
    """Maneja el estado persistente para el sistema de migración"""
    
    def __init__(self, archivo_estado="estado_migracion.json"):
        self.archivo_estado = archivo_estado
        self.estado = self._cargar_estado()
    
    def _cargar_estado(self):
        """Cargar estado desde archivo JSON"""
        try:
            if os.path.exists(self.archivo_estado):
                with open(self.archivo_estado, 'r') as f:
                    return json.load(f)
            else:
                # Estado por defecto - SOLO MODO REMOTO
                return {
                    'db_inicializada': False,
                    'fecha_inicializacion': None,
                    'ultima_sincronizacion': None,
                    'modo_operacion': 'remoto',  # SIEMPRE REMOTO
                    'migraciones_realizadas': 0,
                    'ultima_migracion': None,
                    'ssh_conectado': False,
                    'ssh_error': None,
                    'ultima_verificacion': None
                }
        except Exception as e:
            logger.warning(f"⚠️ Error cargando estado: {e}")
            return self._estado_por_defecto()
    
    def _estado_por_defecto(self):
        """Estado por defecto - EXCLUSIVAMENTE REMOTO"""
        return {
            'db_inicializada': False,
            'fecha_inicializacion': None,
            'ultima_sincronizacion': None,
            'modo_operacion': 'remoto',  # SOLO MODO REMOTO
            'migraciones_realizadas': 0,
            'ultima_migracion': None,
            'ssh_conectado': False,
            'ssh_error': None,
            'ultima_verificacion': None
        }
    
    def guardar_estado(self):
        """Guardar estado a archivo JSON"""
        try:
            with open(self.archivo_estado, 'w') as f:
                json.dump(self.estado, f, indent=2, default=str)
            logger.info(f"✅ Estado guardado en {self.archivo_estado}")
        except Exception as e:
            logger.error(f"❌ Error guardando estado: {e}")
    
    def marcar_db_inicializada(self):
        """Marcar la base de datos como inicializada"""
        self.estado['db_inicializada'] = True
        self.estado['fecha_inicializacion'] = datetime.now().isoformat()
        self.guardar_estado()
    
    def marcar_sincronizacion(self):
        """Marcar última sincronización"""
        self.estado['ultima_sincronizacion'] = datetime.now().isoformat()
        self.guardar_estado()
    
    def registrar_migracion(self):
        """Registrar una migración exitosa"""
        self.estado['migraciones_realizadas'] = self.estado.get('migraciones_realizadas', 0) + 1
        self.estado['ultima_migracion'] = datetime.now().isoformat()
        self.guardar_estado()
    
    def set_ssh_conectado(self, conectado, error=None):
        """Establecer estado de conexión SSH"""
        self.estado['ssh_conectado'] = conectado
        self.estado['ssh_error'] = error
        self.estado['ultima_verificacion'] = datetime.now().isoformat()
        self.guardar_estado()
    
    def esta_inicializada(self):
        """Verificar si la BD está inicializada"""
        return self.estado.get('db_inicializada', False)
    
    def obtener_fecha_inicializacion(self):
        """Obtener fecha de inicialización"""
        fecha_str = self.estado.get('fecha_inicializacion')
        if fecha_str:
            try:
                return datetime.fromisoformat(fecha_str)
            except:
                return None
        return None

# Instancia global del estado persistente
estado_migracion = EstadoPersistenteMigracion()

# =============================================================================
# GESTOR DE CONEXIÓN REMOTA VIA SSH - EXCLUSIVAMENTE REMOTO
# =============================================================================

class GestorConexionRemotaMigracion:
    """Gestor de conexión SSH al servidor remoto para migración - EXCLUSIVAMENTE REMOTO"""
    
    def __init__(self):
        self.ssh = None
        self.sftp = None
        
        # Cargar configuración desde secrets.toml
        logger.info("📋 Cargando configuración desde secrets.toml...")
        self.config_completa = cargar_configuracion_secrets()
        
        if not self.config_completa:
            logger.error("❌ No se pudo cargar configuración de secrets.toml")
            return
            
        self.config = self._cargar_configuracion_completa()
        
        # Configuración de migración
        self.config_migracion = self.config_completa.get('migration', {})
        self.auto_connect = self.config_migracion.get('auto_connect', True)
        self.sync_on_start = self.config_migracion.get('sync_on_start', True)
        self.retry_attempts = self.config_migracion.get('retry_attempts', 3)
        self.retry_delay = self.config_migracion.get('retry_delay', 5)
        self.fallback_to_local = self.config_migracion.get('fallback_to_local', False)
        
        # Configuración de base de datos
        self.config_database = self.config_completa.get('database', {})
        self.sync_interval = self.config_database.get('sync_interval', 60)
        self.backup_before_migration = self.config_database.get('backup_before_migration', True)
        
        # Verificar que TENEMOS configuración SSH
        if not self.config.get('host'):
            logger.warning("⚠️ No hay configuración SSH en secrets.toml")
            return
        
        # Configurar rutas
        self.db_path_remoto = self.config.get('remote_db_escuela')
        self.uploads_path_remoto = self.config.get('remote_uploads_path')
        
        logger.info(f"🔗 Configuración SSH cargada para {self.config.get('host', 'No configurado')}")
        
        # Intentar conexión automática si está configurado
        if self.auto_connect and self.config.get('host'):
            self.probar_conexion_inicial()
    
    def _cargar_configuracion_completa(self):
        """Cargar toda la configuración necesaria"""
        config = {}
        
        try:
            # 1. Configuración SSH (OBLIGATORIA)
            ssh_config = self.config_completa.get('ssh', {})
            config.update({
                'host': ssh_config.get('host', ''),
                'port': int(ssh_config.get('port', 22)),
                'username': ssh_config.get('username', ''),
                'password': ssh_config.get('password', ''),
                'timeout': int(ssh_config.get('timeout', 30)),
                'remote_dir': ssh_config.get('remote_dir', ''),
                'enabled': bool(ssh_config.get('enabled', True))
            })
            
            # 2. Rutas (OBLIGATORIAS)
            paths_config = self.config_completa.get('paths', {})
            config.update({
                'remote_db_escuela': paths_config.get('remote_db_escuela', ''),
                'remote_db_inscritos': paths_config.get('remote_db_inscritos', ''),
                'remote_uploads_path': paths_config.get('remote_uploads_path', ''),
                'remote_uploads_inscritos': paths_config.get('remote_uploads_inscritos', ''),
                'remote_uploads_estudiantes': paths_config.get('remote_uploads_estudiantes', ''),
                'remote_uploads_egresados': paths_config.get('remote_uploads_egresados', ''),
                'remote_uploads_contratados': paths_config.get('remote_uploads_contratados', ''),
                'db_local_path': paths_config.get('db_escuela', ''),
                'uploads_path_local': paths_config.get('uploads_path', '')
            })
            
            # 3. Configuración SMTP (opcional)
            smtp_config = {
                'smtp_server': self.config_completa.get('smtp_server', ''),
                'smtp_port': self.config_completa.get('smtp_port', 587),
                'email_user': self.config_completa.get('email_user', ''),
                'email_password': self.config_completa.get('email_password', ''),
                'notification_email': self.config_completa.get('notification_email', ''),
                'supervisor_mode': bool(self.config_completa.get('supervisor_mode', False)),
                'debug_mode': bool(self.config_completa.get('debug_mode', False))
            }
            config['smtp'] = smtp_config
            
            logger.info("✅ Configuración completa cargada")
            
        except Exception as e:
            logger.error(f"❌ Error cargando configuración: {e}")
        
        return config
    
    def probar_conexion_inicial(self):
        """Probar la conexión SSH al inicio"""
        try:
            if not self.config.get('host'):
                return False
                
            logger.info(f"🔍 Probando conexión SSH a {self.config['host']}...")
            
            ssh_test = paramiko.SSHClient()
            ssh_test.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            port = self.config.get('port', 22)
            timeout = self.config.get('timeout', 30)
            
            ssh_test.connect(
                hostname=self.config['host'],
                port=port,
                username=self.config['username'],
                password=self.config['password'],
                timeout=timeout,
                banner_timeout=timeout,
                allow_agent=False,
                look_for_keys=False
            )
            
            # Ejecutar comando simple para verificar
            stdin, stdout, stderr = ssh_test.exec_command('pwd')
            output = stdout.read().decode().strip()
            
            ssh_test.close()
            
            logger.info(f"✅ Conexión SSH exitosa a {self.config['host']}")
            estado_migracion.set_ssh_conectado(True, None)
            return True
            
        except Exception as e:
            error_msg = f"Error de conexión SSH: {str(e)}"
            logger.error(f"❌ {error_msg}")
            estado_migracion.set_ssh_conectado(False, error_msg)
            return False
    
    def conectar_ssh(self):
        """Establecer conexión SSH con el servidor remoto"""
        try:
            if not self.config.get('host'):
                st.error("❌ No hay configuración SSH disponible")
                return False
                
            logger.info(f"🔗 Conectando SSH a {self.config['host']}:{self.config.get('port', 22)}...")
            
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            port = self.config.get('port', 22)
            timeout = self.config.get('timeout', 30)
            
            self.ssh.connect(
                hostname=self.config['host'],
                port=port,
                username=self.config['username'],
                password=self.config['password'],
                timeout=timeout,
                banner_timeout=timeout,
                allow_agent=False,
                look_for_keys=False
            )
            
            self.sftp = self.ssh.open_sftp()
            logger.info(f"✅ Conexión SSH establecida a {self.config['host']}")
            
            estado_migracion.set_ssh_conectado(True, None)
            return True
            
        except Exception as e:
            error_msg = f"Error de conexión SSH: {e}"
            logger.error(f"❌ {error_msg}")
            estado_migracion.set_ssh_conectado(False, error_msg)
            return False
    
    def desconectar_ssh(self):
        """Cerrar conexión SSH"""
        try:
            if self.sftp:
                self.sftp.close()
            if self.ssh:
                self.ssh.close()
            logger.info("🔌 Conexión SSH cerrada")
        except Exception as e:
            logger.warning(f"⚠️ Error cerrando conexión SSH: {e}")
    
    def descargar_db_remota(self):
        """Descargar base de datos SQLite del servidor remoto - CON REINTENTOS"""
        for attempt in range(self.retry_attempts):
            try:
                logger.info(f"📥 Intento {attempt + 1}/{self.retry_attempts} descargando DB remota...")
                
                if not self.conectar_ssh():
                    logger.error(f"❌ Falló conexión SSH en intento {attempt + 1}")
                    if attempt < self.retry_attempts - 1:
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        raise Exception("No se pudo conectar SSH después de múltiples intentos")
                
                # Crear archivo temporal local
                temp_dir = tempfile.gettempdir()
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                temp_db_path = os.path.join(temp_dir, f"migracion_temp_{timestamp}.db")
                
                # Intentar descargar archivo remoto
                try:
                    logger.info(f"📥 Descargando base de datos desde: {self.db_path_remoto}")
                    self.sftp.get(self.db_path_remoto, temp_db_path)
                    
                    # Verificar que el archivo se descargó correctamente
                    if os.path.exists(temp_db_path) and os.path.getsize(temp_db_path) > 0:
                        file_size = os.path.getsize(temp_db_path)
                        logger.info(f"✅ Base de datos descargada: {temp_db_path} ({file_size} bytes)")
                        return temp_db_path
                    else:
                        logger.warning("⚠️ Archivo descargado vacío o corrupto")
                        # Intentar crear una nueva
                        return self._crear_nueva_db_remota()
                        
                except FileNotFoundError:
                    logger.warning(f"⚠️ Base de datos remota no encontrada: {self.db_path_remoto}")
                    return self._crear_nueva_db_remota()
                    
                except Exception as e:
                    logger.error(f"❌ Error descargando archivo: {e}")
                    if attempt < self.retry_attempts - 1:
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        return self._crear_nueva_db_remota()
                        
            except Exception as e:
                logger.error(f"❌ Error en intento {attempt + 1}: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay)
                    continue
                else:
                    logger.error("❌ Todos los intentos fallaron")
                    raise Exception(f"No se pudo descargar la base de datos después de {self.retry_attempts} intentos")
            finally:
                if self.ssh:
                    self.desconectar_ssh()
        
        # Nunca debería llegar aquí
        return None
    
    def _crear_nueva_db_remota(self):
        """Crear una nueva base de datos SQLite y subirla al servidor remoto"""
        try:
            logger.info("📝 Creando nueva base de datos remota...")
            
            # Crear archivo temporal para la nueva base de datos
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_db_path = os.path.join(temp_dir, f"migracion_nueva_{timestamp}.db")
            
            logger.info(f"📝 Creando nueva base de datos en: {temp_db_path}")
            
            # Inicializar la base de datos
            self._inicializar_db_estructura(temp_db_path)
            
            # Subir al servidor remoto
            if self.conectar_ssh():
                try:
                    # Crear directorio si no existe
                    remote_dir = os.path.dirname(self.db_path_remoto)
                    try:
                        self.sftp.stat(remote_dir)
                    except:
                        # Crear directorio recursivamente
                        self._crear_directorio_remoto_recursivo(remote_dir)
                    
                    # Subir archivo
                    self.sftp.put(temp_db_path, self.db_path_remoto)
                    logger.info(f"✅ Nueva base de datos subida a servidor: {self.db_path_remoto}")
                finally:
                    self.desconectar_ssh()
            
            return temp_db_path
            
        except Exception as e:
            logger.error(f"❌ Error creando nueva base de datos remota: {e}")
            raise
    
    def _crear_directorio_remoto_recursivo(self, remote_path):
        """Crear directorio remoto recursivamente"""
        try:
            self.sftp.stat(remote_path)
            logger.info(f"📁 Directorio remoto ya existe: {remote_path}")
        except:
            try:
                # Intentar crear directorio
                self.sftp.mkdir(remote_path)
                logger.info(f"✅ Directorio remoto creado: {remote_path}")
            except:
                # Si falla, crear directorio padre primero
                parent_dir = os.path.dirname(remote_path)
                if parent_dir and parent_dir != '/':
                    self._crear_directorio_remoto_recursivo(parent_dir)
                self.sftp.mkdir(remote_path)
                logger.info(f"✅ Directorio remoto creado recursivamente: {remote_path}")
    
    def _inicializar_db_estructura(self, db_path):
        """Inicializar estructura de base de datos"""
        try:
            logger.info(f"📝 Inicializando estructura en: {db_path}")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Tabla de usuarios - CON BCRYPT
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT,  -- NULLABLE para BCRYPT
                    rol TEXT NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT,
                    matricula TEXT UNIQUE,
                    activo INTEGER DEFAULT 1,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla de inscritos
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
            
            # Tabla de estudiantes
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
            
            # Tabla de egresados
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
            
            # Tabla de contratados
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
            
            # Tabla de bitácora
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
            
            # Índices para rendimiento
            indices = [
                ('idx_usuarios_usuario', 'usuarios(usuario)'),
                ('idx_usuarios_matricula', 'usuarios(matricula)'),
                ('idx_inscritos_matricula', 'inscritos(matricula)'),
                ('idx_estudiantes_matricula', 'estudiantes(matricula)'),
                ('idx_egresados_matricula', 'egresados(matricula)'),
                ('idx_contratados_matricula', 'contratados(matricula)')
            ]
            
            for nombre_idx, definicion in indices:
                try:
                    cursor.execute(f'CREATE INDEX IF NOT EXISTS {nombre_idx} ON {definicion}')
                except Exception as e:
                    logger.warning(f"⚠️ Error creando índice {nombre_idx}: {e}")
            
            # Verificar si existe usuario admin
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE usuario = 'admin'")
            if cursor.fetchone()[0] == 0:
                # Insertar usuario administrador por defecto con BCRYPT
                password = "Admin123!"
                salt = bcrypt.gensalt()
                password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
                
                cursor.execute('''
                    INSERT INTO usuarios (usuario, password_hash, salt, rol, nombre_completo, email, matricula)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    'admin',
                    password_hash.decode('utf-8'),
                    salt.decode('utf-8'),
                    'administrador',
                    'Administrador del Sistema',
                    'admin@escuela.edu.mx',
                    'ADMIN-001'
                ))
                logger.info("✅ Usuario administrador por defecto creado con BCRYPT")
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Estructura de base de datos inicializada en {db_path}")
            
            # Marcar como inicializada en el estado persistente
            estado_migracion.marcar_db_inicializada()
            
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura: {e}")
            raise
    
    def subir_db_remota(self, ruta_local):
        """Subir base de datos local al servidor remoto (sobreescribir) - CON BACKUP"""
        try:
            logger.info(f"📤 Subiendo base de datos al servidor remoto...")
            
            if not self.conectar_ssh():
                return False
            
            # Crear backup de la base de datos remota antes de sobreescribir
            if self.backup_before_migration:
                try:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_path = f"{self.db_path_remoto}.backup_{timestamp}"
                    self.sftp.rename(self.db_path_remoto, backup_path)
                    logger.info(f"✅ Backup creado: {backup_path}")
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo crear backup: {e}")
                    # Continuar aunque no se pueda hacer backup
            
            # Subir nuevo archivo
            self.sftp.put(ruta_local, self.db_path_remoto)
            
            logger.info(f"✅ Base de datos subida a servidor: {self.db_path_remoto}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error subiendo base de datos: {e}")
            return False
        finally:
            if self.ssh:
                self.desconectar_ssh()
    
    def renombrar_archivos_pdf(self, matricula_vieja, matricula_nueva):
        """Renombrar archivos PDF en el servidor remoto"""
        try:
            logger.info(f"🔄 Renombrando archivos PDF {matricula_vieja} -> {matricula_nueva}")
            
            if not self.conectar_ssh():
                return 0
            
            archivos_renombrados = 0
            
            try:
                # Verificar si el directorio de uploads existe
                self.sftp.stat(self.uploads_path_remoto)
                archivos = self.sftp.listdir(self.uploads_path_remoto)
                
                for archivo in archivos:
                    if archivo.lower().endswith('.pdf') and matricula_vieja in archivo:
                        nuevo_nombre = archivo.replace(matricula_vieja, matricula_nueva)
                        ruta_vieja = os.path.join(self.uploads_path_remoto, archivo)
                        ruta_nueva = os.path.join(self.uploads_path_remoto, nuevo_nombre)
                        
                        try:
                            self.sftp.stat(ruta_vieja)
                            self.sftp.rename(ruta_vieja, ruta_nueva)
                            archivos_renombrados += 1
                            logger.info(f"✅ Renombrado: {archivo} -> {nuevo_nombre}")
                        except Exception as rename_error:
                            logger.error(f"❌ Error renombrando {archivo}: {rename_error}")
                
                if archivos_renombrados == 0:
                    logger.warning(f"⚠️ No se encontraron archivos PDF para renombrar: {matricula_vieja}")
                    
            except FileNotFoundError:
                logger.warning(f"📁 Directorio de uploads no encontrado: {self.uploads_path_remoto}")
            
            self.desconectar_ssh()
            return archivos_renombrados
            
        except Exception as e:
            logger.error(f"❌ Error renombrando archivos en servidor: {e}")
            return 0
    
    def verificar_conexion_ssh(self):
        """Verificar estado de conexión SSH"""
        return self.probar_conexion_inicial()

# Instancia global del gestor de conexión remota para migración
gestor_remoto_migracion = GestorConexionRemotaMigracion()

# =============================================================================
# SISTEMA DE BASE DE DATOS SQLITE PARA MIGRACIÓN - EXCLUSIVAMENTE REMOTO
# =============================================================================

class SistemaBaseDatosMigracion:
    """Sistema de base de datos SQLite para migración EXCLUSIVAMENTE REMOTO"""
    
    def __init__(self):
        self.gestor = gestor_remoto_migracion
        self.db_local_temp = None
        self.conexion_actual = None
        self.ultima_sincronizacion = None
        
        # Configuración de migración
        self.retry_attempts = self.gestor.retry_attempts
        self.retry_delay = self.gestor.retry_delay
    
    def sincronizar_desde_remoto(self):
        """Sincronizar base de datos desde el servidor remoto - CON REINTENTOS"""
        for attempt in range(self.retry_attempts):
            try:
                logger.info(f"🔄 Intento {attempt + 1}/{self.retry_attempts} sincronizando desde remoto...")
                
                # 1. Descargar base de datos remota
                self.db_local_temp = self.gestor.descargar_db_remota()
                
                if not self.db_local_temp:
                    raise Exception("No se pudo obtener base de datos remota")
                
                # 2. Verificar que el archivo existe
                if not os.path.exists(self.db_local_temp):
                    raise Exception(f"Archivo de base de datos no existe: {self.db_local_temp}")
                
                # 3. Verificar que sea una base de datos SQLite válida con tablas
                try:
                    conn = sqlite3.connect(self.db_local_temp)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tablas = cursor.fetchall()
                    conn.close()
                    
                    logger.info(f"✅ Base de datos verificada: {len(tablas)} tablas")
                    
                    if len(tablas) == 0:
                        logger.warning("⚠️ Base de datos vacía, inicializando estructura...")
                        # Inicializar estructura
                        self._inicializar_estructura_db()
                except Exception as e:
                    logger.error(f"❌ Base de datos corrupta: {e}")
                    raise Exception(f"Base de datos corrupta: {e}")
                
                self.ultima_sincronizacion = datetime.now()
                logger.info(f"✅ Sincronización exitosa: {self.db_local_temp}")
                
                # Actualizar estado de sincronización
                estado_migracion.marcar_sincronizacion()
                
                return True
                
            except Exception as e:
                logger.error(f"❌ Error en intento {attempt + 1}: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay)
                    continue
                else:
                    return False
    
    def _inicializar_estructura_db(self):
        """Inicializar estructura de la base de datos"""
        try:
            if not self.db_local_temp:
                logger.error("❌ No hay ruta de base de datos para inicializar")
                return
            
            self.gestor._inicializar_db_estructura(self.db_local_temp)
            
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura: {e}")
            raise
    
    def sincronizar_hacia_remoto(self):
        """Sincronizar base de datos local hacia el servidor remoto - CON REINTENTOS"""
        for attempt in range(self.retry_attempts):
            try:
                logger.info(f"📤 Intento {attempt + 1}/{self.retry_attempts} sincronizando hacia remoto...")
                
                if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                    raise Exception("No hay base de datos local para subir")
                
                # Subir al servidor remoto
                exito = self.gestor.subir_db_remota(self.db_local_temp)
                
                if exito:
                    self.ultima_sincronizacion = datetime.now()
                    logger.info("✅ Cambios subidos exitosamente al servidor")
                    
                    # Actualizar estado
                    estado_migracion.marcar_sincronizacion()
                    
                    return True
                else:
                    raise Exception("Error subiendo al servidor")
                    
            except Exception as e:
                logger.error(f"❌ Error en intento {attempt + 1}: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay)
                    continue
                else:
                    return False
    
    @contextmanager
    def get_connection(self):
        """Context manager para conexiones a la base de datos"""
        conn = None
        try:
            # Asegurar que tenemos la base de datos más reciente
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                if not self.sincronizar_desde_remoto():
                    raise Exception("No se pudo sincronizar la base de datos")
            
            conn = sqlite3.connect(self.db_local_temp)
            conn.row_factory = sqlite3.Row  # Para acceso por nombre de columna
            self.conexion_actual = conn
            yield conn
            
            if conn:
                conn.commit()
                
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"❌ Error en conexión a base de datos: {e}")
            raise
        finally:
            if conn:
                conn.close()
                self.conexion_actual = None
    
    def hash_password(self, password):
        """Crear hash de contraseña con BCRYPT"""
        try:
            salt = bcrypt.gensalt(rounds=12)
            password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
            return password_hash.decode('utf-8'), salt.decode('utf-8')
        except Exception as e:
            logger.error(f"Error al crear hash BCRYPT: {e}")
            # Fallback a SHA256 para compatibilidad
            salt = os.urandom(32).hex()
            hash_obj = hashlib.sha256((password + salt).encode())
            return hash_obj.hexdigest(), salt
    
    def verify_password(self, stored_hash, stored_salt, provided_password):
        """Verificar contraseña con soporte para BCRYPT"""
        try:
            # Intentar con BCRYPT primero
            if stored_hash.startswith('$2'):
                return bcrypt.checkpw(provided_password.encode('utf-8'), stored_hash.encode('utf-8'))
            else:
                # Fallback a SHA256
                hash_obj = hashlib.sha256((provided_password + stored_salt).encode())
                return hash_obj.hexdigest() == stored_hash
        except Exception as e:
            logger.error(f"Error verificando password: {e}")
            return False
    
    # =============================================================================
    # MÉTODOS DE CONSULTA PARA MIGRACIÓN
    # =============================================================================
    
    def obtener_usuario(self, usuario):
        """Obtener usuario por nombre de usuario o matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM usuarios 
                    WHERE usuario = ? OR matricula = ? OR email = ?
                ''', (usuario, usuario, usuario))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error obteniendo usuario {usuario}: {e}")
            return None
    
    def verificar_login(self, usuario, password):
        """Verificar credenciales de login"""
        try:
            usuario_data = self.obtener_usuario(usuario)
            if not usuario_data:
                logger.warning(f"Usuario no encontrado: {usuario}")
                return None
            
            password_hash = usuario_data.get('password_hash', '')
            salt = usuario_data.get('salt', '')
            
            if self.verify_password(password_hash, salt, password):
                logger.info(f"Login exitoso: {usuario}")
                return usuario_data
            else:
                logger.warning(f"Password incorrecto: {usuario}")
                return None
                
        except Exception as e:
            logger.error(f"Error verificando login: {e}")
            return None
    
    def obtener_inscritos(self):
        """Obtener todos los inscritos"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM inscritos ORDER BY fecha_registro DESC"
                df = pd.read_sql_query(query, conn)
                logger.info(f"Obtenidos {len(df)} inscritos")
                return df
        except Exception as e:
            logger.error(f"Error obteniendo inscritos: {e}")
            return pd.DataFrame()
    
    def obtener_estudiantes(self):
        """Obtener todos los estudiantes"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM estudiantes ORDER BY fecha_ingreso DESC"
                df = pd.read_sql_query(query, conn)
                logger.info(f"Obtenidos {len(df)} estudiantes")
                return df
        except Exception as e:
            logger.error(f"Error obteniendo estudiantes: {e}")
            return pd.DataFrame()
    
    def obtener_egresados(self):
        """Obtener todos los egresados"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM egresados ORDER BY fecha_graduacion DESC"
                df = pd.read_sql_query(query, conn)
                logger.info(f"Obtenidos {len(df)} egresados")
                return df
        except Exception as e:
            logger.error(f"Error obteniendo egresados: {e}")
            return pd.DataFrame()
    
    def obtener_contratados(self):
        """Obtener todos los contratados"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM contratados ORDER BY fecha_contratacion DESC"
                df = pd.read_sql_query(query, conn)
                logger.info(f"Obtenidos {len(df)} contratados")
                return df
        except Exception as e:
            logger.error(f"Error obteniendo contratados: {e}")
            return pd.DataFrame()
    
    def obtener_usuarios(self):
        """Obtener todos los usuarios"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM usuarios ORDER BY fecha_creacion DESC"
                df = pd.read_sql_query(query, conn)
                logger.info(f"Obtenidos {len(df)} usuarios")
                return df
        except Exception as e:
            logger.error(f"Error obteniendo usuarios: {e}")
            return pd.DataFrame()
    
    def obtener_inscrito_por_matricula(self, matricula):
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
    
    def obtener_estudiante_por_matricula(self, matricula):
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
    
    def obtener_egresado_por_matricula(self, matricula):
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
    
    def obtener_contratado_por_matricula(self, matricula):
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
    
    def actualizar_rol_usuario(self, usuario_id, nuevo_rol, nueva_matricula):
        """Actualizar rol y matrícula del usuario"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE usuarios 
                    SET rol = ?, matricula = ?, usuario = ?, fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (nuevo_rol, nueva_matricula, nueva_matricula, usuario_id))
                
                logger.info(f"Usuario actualizado ID {usuario_id} -> {nueva_matricula} ({nuevo_rol})")
                return True
                
        except Exception as e:
            logger.error(f"Error al actualizar usuario: {e}")
            return False
    
    def eliminar_inscrito(self, matricula):
        """Eliminar inscrito por matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM inscritos WHERE matricula = ?", (matricula,))
                eliminado = cursor.rowcount > 0
                if eliminado:
                    logger.info(f"Inscrito eliminado: {matricula}")
                return eliminado
        except Exception as e:
            logger.error(f"Error eliminando inscrito {matricula}: {e}")
            return False
    
    def eliminar_estudiante(self, matricula):
        """Eliminar estudiante por matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM estudiantes WHERE matricula = ?", (matricula,))
                eliminado = cursor.rowcount > 0
                if eliminado:
                    logger.info(f"Estudiante eliminado: {matricula}")
                return eliminado
        except Exception as e:
            logger.error(f"Error eliminando estudiante {matricula}: {e}")
            return False
    
    def eliminar_egresado(self, matricula):
        """Eliminar egresado por matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM egresados WHERE matricula = ?", (matricula,))
                eliminado = cursor.rowcount > 0
                if eliminado:
                    logger.info(f"Egresado eliminado: {matricula}")
                return eliminado
        except Exception as e:
            logger.error(f"Error eliminando egresado {matricula}: {e}")
            return False
    
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
                    estudiante_data.get('matricula', '')
                ))
                estudiante_id = cursor.lastrowid
                logger.info(f"Estudiante agregado: {estudiante_data.get('matricula', '')}")
                return estudiante_id
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
                egresado_id = cursor.lastrowid
                logger.info(f"Egresado agregado: {egresado_data.get('matricula', '')}")
                return egresado_id
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
                contratado_id = cursor.lastrowid
                logger.info(f"Contratado agregado: {contratado_data.get('matricula', '')}")
                return contratado_id
        except Exception as e:
            logger.error(f"Error agregando contratado: {e}")
            return None
    
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
# INSTANCIA DE BASE DE DATOS PARA MIGRACIÓN
# =============================================================================

db_migracion = SistemaBaseDatosMigracion()

# =============================================================================
# SISTEMA DE AUTENTICACIÓN PARA MIGRACIÓN
# =============================================================================

class SistemaAutenticacionMigracion:
    def __init__(self):
        self.sesion_activa = False
        self.usuario_actual = None
        
    def verificar_login(self, usuario, password):
        """Verificar credenciales de usuario"""
        try:
            if not usuario or not password:
                st.error("❌ Usuario y contraseña son obligatorios")
                return False
            
            with st.spinner("🔐 Verificando credenciales..."):
                # Usar base de datos de migración
                usuario_data = db_migracion.verificar_login(usuario, password)
                
                if usuario_data:
                    # Verificar que sea administrador
                    rol_usuario = usuario_data.get('rol', '')
                    
                    if rol_usuario != 'administrador':
                        st.error("❌ Solo los usuarios con rol 'administrador' pueden acceder al sistema de migración")
                        return False
                    
                    nombre_real = usuario_data.get('nombre_completo', usuario_data.get('usuario', 'Usuario'))
                    
                    st.success(f"✅ ¡Bienvenido(a) al migrador, {nombre_real}!")
                    st.session_state.login_exitoso = True
                    st.session_state.usuario_actual = usuario_data
                    st.session_state.rol_usuario = usuario_data.get('rol', 'administrador')
                    self.sesion_activa = True
                    self.usuario_actual = usuario_data
                    
                    # Registrar en bitácora
                    db_migracion.registrar_bitacora(
                        usuario_data['usuario'],
                        'LOGIN_MIGRACION',
                        f'Administrador {usuario_data["usuario"]} inició sesión en el migrador'
                    )
                    
                    return True
                else:
                    st.error("❌ Usuario o contraseña incorrectos")
                    return False
                    
        except Exception as e:
            st.error(f"❌ Error en el proceso de login: {e}")
            return False
    
    def cerrar_sesion(self):
        """Cerrar sesión del usuario en el migrador"""
        try:
            if self.sesion_activa and self.usuario_actual:
                db_migracion.registrar_bitacora(
                    self.usuario_actual.get('usuario', ''),
                    'LOGOUT_MIGRACION',
                    f'Administrador {self.usuario_actual.get("usuario", "")} cerró sesión del migrador'
                )
                
            self.sesion_activa = False
            self.usuario_actual = None
            st.session_state.login_exitoso = False
            st.session_state.usuario_actual = None
            st.session_state.rol_usuario = None
            st.success("✅ Sesión cerrada exitosamente")
            
        except Exception as e:
            st.error(f"❌ Error cerrando sesión: {e}")

# Instancia global del sistema de autenticación para migración
auth_migracion = SistemaAutenticacionMigracion()

# =============================================================================
# SISTEMA DE MIGRACIÓN DE ROLES - EXCLUSIVAMENTE REMOTO
# =============================================================================

class SistemaMigracionCompleto:
    def __init__(self):
        self.gestor = gestor_remoto_migracion
        self.db = db_migracion
        self.cargar_datos()
        
    def cargar_datos(self):
        """Cargar datos desde la base de datos de migración"""
        try:
            with st.spinner("📊 Cargando datos desde servidor remoto..."):
                self.df_inscritos = self.db.obtener_inscritos()
                self.df_estudiantes = self.db.obtener_estudiantes()
                self.df_egresados = self.db.obtener_egresados()
                self.df_contratados = self.db.obtener_contratados()
                self.df_usuarios = self.db.obtener_usuarios()
                
                logger.info(f"Datos cargados: {len(self.df_inscritos)} inscritos, {len(self.df_estudiantes)} estudiantes")
        except Exception as e:
            logger.error(f"Error cargando datos: {e}")
            self.df_inscritos = pd.DataFrame()
            self.df_estudiantes = pd.DataFrame()
            self.df_egresados = pd.DataFrame()
            self.df_contratados = pd.DataFrame()
            self.df_usuarios = pd.DataFrame()
    
    def obtener_prefijo_rol(self, rol):
        """Obtener prefijo de matrícula según el rol"""
        prefijos = {
            'inscrito': 'MAT-INS',
            'estudiante': 'MAT-EST',
            'egresado': 'MAT-EGR',
            'contratado': 'MAT-CON'
        }
        return prefijos.get(rol, 'MAT-')
    
    def generar_nueva_matricula(self, matricula_actual, rol_destino):
        """Generar nueva matrícula según el rol destino"""
        prefijo_destino = self.obtener_prefijo_rol(rol_destino)
        
        # Extraer el número de la matrícula actual
        for prefijo in ['MAT-INS', 'MAT-EST', 'MAT-EGR', 'MAT-CON']:
            if matricula_actual.startswith(prefijo):
                numero = matricula_actual.replace(prefijo, '')
                return f"{prefijo_destino}{numero}"
        
        # Si no tiene formato conocido, generar nueva
        return f"{prefijo_destino}{datetime.now().strftime('%y%m%d%H%M')}"
    
    def buscar_usuario_por_matricula(self, matricula):
        """Buscar usuario por matrícula"""
        try:
            usuario_data = self.db.obtener_usuario(matricula)
            if usuario_data:
                return usuario_data.get('id')  # Retornar ID del usuario
            st.warning(f"⚠️ Usuario con matrícula '{matricula}' no encontrado")
            return None
        except Exception as e:
            st.error(f"❌ Error en búsqueda de usuario: {e}")
            return None
    
    def actualizar_rol_usuario(self, usuario_id, nuevo_rol, nueva_matricula):
        """Actualizar rol y matrícula del usuario"""
        try:
            if self.db.actualizar_rol_usuario(usuario_id, nuevo_rol, nueva_matricula):
                st.success(f"✅ Usuario actualizado exitosamente a {nueva_matricula} ({nuevo_rol})")
                return True
            return False
        except Exception as e:
            st.error(f"❌ Error actualizando usuario: {e}")
            return False
    
    def renombrar_archivos_pdf(self, matricula_vieja, matricula_nueva):
        """Renombrar archivos PDF en el servidor remoto"""
        return self.gestor.renombrar_archivos_pdf(matricula_vieja, matricula_nueva)
    
    def migrar_inscrito_a_estudiante(self, inscrito_data):
        """Migrar de inscrito a estudiante"""
        try:
            if inscrito_data is None:
                st.error("❌ Error: No se encontraron datos del inscrito seleccionado")
                if 'inscrito_seleccionado' in st.session_state:
                    del st.session_state.inscrito_seleccionado
                return False
            
            matricula_inscrito = inscrito_data.get('matricula', '')
            nombre_completo = inscrito_data.get('nombre_completo', '')
            
            if not matricula_inscrito:
                st.error("❌ Error: No se pudo obtener la matrícula del inscrito")
                return False
            
            st.info(f"🔄 Iniciando migración: INSCRITO → ESTUDIANTE")
            st.info(f"📛 Nombre: {nombre_completo}")
            st.info(f"🆔 Matrícula actual: {matricula_inscrito}")
            
            # Generar nueva matrícula
            matricula_estudiante = self.generar_nueva_matricula(matricula_inscrito, 'estudiante')
            st.info(f"🆕 Matrícula nueva: {matricula_estudiante}")
            
            # Formulario para completar datos del estudiante
            st.subheader("📝 Formulario de Datos del Estudiante")
            
            with st.form("formulario_estudiante"):
                st.write("Complete la información requerida para el estudiante:")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    programa = st.text_input("Programa Educativo*", 
                                           value=inscrito_data.get('programa_interes', 'Especialidad en Enfermería Cardiovascular'))
                    fecha_nacimiento = st.date_input("Fecha de Nacimiento*", 
                                                   value=datetime.now() - timedelta(days=365*25))
                    genero = st.selectbox("Género*", ["Masculino", "Femenino", "Otro", "Prefiero no decir"])
                    fecha_ingreso = st.date_input("Fecha de Ingreso*", value=datetime.now())
                    programa_interes = st.text_input("Programa de Interés*", 
                                                   value=inscrito_data.get('programa_interes', 'Especialidad en Enfermería Cardiovascular'))
                
                with col2:
                    folio = st.text_input("Folio", value=f"FOL-{datetime.now().strftime('%Y%m%d')}-001")
                    como_se_entero = st.selectbox("¿Cómo se enteró del programa?*",
                                                ["Internet", "Redes Sociales", "Amigo/Familiar", 
                                                 "Publicidad", "Evento", "Otro"],
                                                index=1)
                    documentos_subidos = st.text_input("Documentos Subidos*", value="4")
                    
                    fecha_registro_str = inscrito_data.get('fecha_registro', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    try:
                        fecha_registro_default = datetime.strptime(fecha_registro_str.split()[0], '%Y-%m-%d')
                    except:
                        fecha_registro_default = datetime.now()
                    
                    fecha_registro = st.date_input("Fecha de Registro*", value=fecha_registro_default)
                    estatus = st.selectbox("Estatus*", ["ACTIVO", "INACTIVO", "PENDIENTE"], index=0)
                
                submitted = st.form_submit_button("💾 Confirmar Migración a Estudiante")
                
                if submitted:
                    if not programa or not programa_interes:
                        st.error("❌ Los campos marcados con * son obligatorios")
                        return False
                    
                    # Guardar datos en session_state
                    st.session_state.datos_formulario_inscrito = {
                        'programa': programa,
                        'fecha_nacimiento': fecha_nacimiento,
                        'genero': genero,
                        'fecha_ingreso': fecha_ingreso,
                        'programa_interes': programa_interes,
                        'folio': folio,
                        'como_se_entero': como_se_entero,
                        'documentos_subidos': documentos_subidos,
                        'fecha_registro': fecha_registro,
                        'estatus': estatus,
                        'matricula_inscrito': matricula_inscrito,
                        'matricula_estudiante': matricula_estudiante,
                        'nombre_completo': nombre_completo,
                        'inscrito_data': inscrito_data
                    }
                    
                    st.session_state.mostrar_confirmacion_inscrito = True
                    st.rerun()
            
            # CONFIRMACIÓN FINAL
            if st.session_state.get('mostrar_confirmacion_inscrito', False):
                datos_form = st.session_state.get('datos_formulario_inscrito', {})
                
                if datos_form:
                    st.subheader("📋 Resumen de la Migración")
                    st.info(f"**Matrícula actual:** {datos_form['matricula_inscrito']}")
                    st.info(f"**Nueva matrícula:** {datos_form['matricula_estudiante']}")
                    st.info(f"**Nombre:** {datos_form['nombre_completo']}")
                    st.info(f"**Programa:** {datos_form['programa']}")
                    
                    st.warning("⚠️ **¿Está seguro de proceder con la migración?** Esta acción no se puede deshacer.")
                    
                    col_confirm1, col_confirm2 = st.columns(2)
                    with col_confirm1:
                        if st.button("✅ Sí, proceder con la migración", type="primary", key="confirmar_migracion_inscrito"):
                            return self.ejecutar_migracion_inscrito_estudiante(datos_form)
                    
                    with col_confirm2:
                        if st.button("❌ Cancelar migración", key="cancelar_migracion_inscrito"):
                            st.info("Migración cancelada")
                            if 'mostrar_confirmacion_inscrito' in st.session_state:
                                del st.session_state.mostrar_confirmacion_inscrito
                            if 'datos_formulario_inscrito' in st.session_state:
                                del st.session_state.datos_formulario_inscrito
                            st.rerun()
                            return False
            
            return False
            
        except Exception as e:
            st.error(f"❌ Error en la migración: {str(e)}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return False

    def migrar_estudiante_a_egresado(self, estudiante_data):
        """Migrar de estudiante a egresado"""
        try:
            if estudiante_data is None:
                st.error("❌ Error: No se encontraron datos del estudiante seleccionado")
                if 'estudiante_seleccionado' in st.session_state:
                    del st.session_state.estudiante_seleccionado
                return False
            
            matricula_estudiante = estudiante_data.get('matricula', '')
            nombre_completo = estudiante_data.get('nombre_completo', '')
            
            if not matricula_estudiante:
                st.error("❌ Error: No se pudo obtener la matrícula del estudiante")
                return False
            
            st.info(f"🔄 Iniciando migración: ESTUDIANTE → EGRESADO")
            st.info(f"📛 Nombre: {nombre_completo}")
            st.info(f"🆔 Matrícula actual: {matricula_estudiante}")
            
            # Generar nueva matrícula
            matricula_egresado = self.generar_nueva_matricula(matricula_estudiante, 'egresado')
            st.info(f"🆕 Matrícula nueva: {matricula_egresado}")
            
            # Formulario para completar datos del egresado
            st.subheader("📝 Formulario de Datos del Egresado")
            
            with st.form("formulario_egresado"):
                st.write("Complete la información requerida para el egresado:")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    programa_original = st.text_input("Programa Original*", 
                                                    value=estudiante_data.get('programa', 'Especialidad en Enfermería Cardiovascular'))
                    fecha_graduacion = st.date_input("Fecha de Graduación*", value=datetime.now())
                    nivel_academico = st.selectbox("Nivel Académico*", 
                                                 ["Especialidad", "Maestría", "Doctorado", "Diplomado"],
                                                 index=0)
                    estado_laboral = st.selectbox("Estado Laboral*",
                                                ["Contratada", "Buscando empleo", "Empleado independiente", "Estudiando", "Otro"],
                                                index=0)
                
                with col2:
                    documentos_subidos = st.text_input("Documentos Subidos*", value="Cédula Profesional")
                    telefono = st.text_input("Teléfono", value=estudiante_data.get('telefono', ''))
                    email = st.text_input("Email*", value=estudiante_data.get('email', ''))
                
                submitted = st.form_submit_button("💾 Confirmar Migración a Egresado")
                
                if submitted:
                    if not programa_original or not nivel_academico or not estado_laboral or not email:
                        st.error("❌ Los campos marcados con * son obligatorios")
                        return False
                    
                    # Guardar datos en session_state
                    st.session_state.datos_formulario_estudiante = {
                        'programa_original': programa_original,
                        'fecha_graduacion': fecha_graduacion,
                        'nivel_academico': nivel_academico,
                        'estado_laboral': estado_laboral,
                        'documentos_subidos': documentos_subidos,
                        'telefono': telefono,
                        'email': email,
                        'matricula_estudiante': matricula_estudiante,
                        'matricula_egresado': matricula_egresado,
                        'nombre_completo': nombre_completo,
                        'estudiante_data': estudiante_data
                    }
                    
                    st.session_state.mostrar_confirmacion_estudiante = True
                    st.rerun()
            
            # CONFIRMACIÓN FINAL
            if st.session_state.get('mostrar_confirmacion_estudiante', False):
                datos_form = st.session_state.get('datos_formulario_estudiante', {})
                
                if datos_form:
                    st.subheader("📋 Resumen de la Migración")
                    st.info(f"**Matrícula actual:** {datos_form['matricula_estudiante']}")
                    st.info(f"**Nueva matrícula:** {datos_form['matricula_egresado']}")
                    st.info(f"**Nombre:** {datos_form['nombre_completo']}")
                    st.info(f"**Programa Original:** {datos_form['programa_original']}")
                    st.info(f"**Nivel Académico:** {datos_form['nivel_academico']}")
                    
                    st.warning("⚠️ **¿Está seguro de proceder con la migración?** Esta acción no se puede deshacer.")
                    
                    col_confirm1, col_confirm2 = st.columns(2)
                    with col_confirm1:
                        if st.button("✅ Sí, proceder con la migración", type="primary", key="confirmar_migracion_estudiante"):
                            return self.ejecutar_migracion_estudiante_egresado(datos_form)
                    
                    with col_confirm2:
                        if st.button("❌ Cancelar migración", key="cancelar_migracion_estudiante"):
                            st.info("Migración cancelada")
                            if 'mostrar_confirmacion_estudiante' in st.session_state:
                                del st.session_state.mostrar_confirmacion_estudiante
                            if 'datos_formulario_estudiante' in st.session_state:
                                del st.session_state.datos_formulario_estudiante
                            st.rerun()
                            return False
            
            return False
            
        except Exception as e:
            st.error(f"❌ Error en la migración: {str(e)}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return False

    def migrar_egresado_a_contratado(self, egresado_data):
        """Migrar de egresado a contratado"""
        try:
            if egresado_data is None:
                st.error("❌ Error: No se encontraron datos del egresado seleccionado")
                if 'egresado_seleccionado' in st.session_state:
                    del st.session_state.egresado_seleccionado
                return False
            
            matricula_egresado = egresado_data.get('matricula', '')
            nombre_completo = egresado_data.get('nombre_completo', '')
            
            if not matricula_egresado:
                st.error("❌ Error: No se pudo obtener la matrícula del egresado")
                return False
            
            st.info(f"🔄 Iniciando migración: EGRESADO → CONTRATADO")
            st.info(f"📛 Nombre: {nombre_completo}")
            st.info(f"🆔 Matrícula actual: {matricula_egresado}")
            
            # Generar nueva matrícula
            matricula_contratado = self.generar_nueva_matricula(matricula_egresado, 'contratado')
            st.info(f"🆕 Matrícula nueva: {matricula_contratado}")
            
            # Formulario para completar datos del contratado
            st.subheader("📝 Formulario de Datos del Contratado")
            
            with st.form("formulario_contratado"):
                st.write("Complete la información requerida para el contratado:")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    fecha_contratacion = st.date_input("Fecha de Contratación*", value=datetime.now())
                    puesto = st.text_input("Puesto*", value="Enfermera Especialista en Cardiología")
                    departamento = st.text_input("Departamento*", value="Terapia Intensiva Cardiovascular")
                    estatus = st.selectbox("Estatus*", ["Activo", "Inactivo", "Licencia", "Baja"], index=0)
                
                with col2:
                    salario = st.text_input("Salario*", value="25000 MXN")
                    tipo_contrato = st.selectbox("Tipo de Contrato*", 
                                               ["Tiempo completo", "Medio tiempo", "Por honorarios", "Temporal"],
                                               index=0)
                    fecha_inicio = st.date_input("Fecha Inicio*", value=datetime.now())
                    fecha_fin = st.date_input("Fecha Fin*", value=datetime.now() + timedelta(days=365))
                    documentos_subidos = st.text_input("Documentos Subidos*", value="Identificación Oficial")
                
                submitted = st.form_submit_button("💾 Confirmar Migración a Contratado")
                
                if submitted:
                    if not puesto or not departamento or not estatus or not salario or not tipo_contrato:
                        st.error("❌ Los campos marcados con * son obligatorios")
                        return False
                    
                    # Guardar datos en session_state
                    st.session_state.datos_formulario_egresado = {
                        'fecha_contratacion': fecha_contratacion,
                        'puesto': puesto,
                        'departamento': departamento,
                        'estatus': estatus,
                        'salario': salario,
                        'tipo_contrato': tipo_contrato,
                        'fecha_inicio': fecha_inicio,
                        'fecha_fin': fecha_fin,
                        'documentos_subidos': documentos_subidos,
                        'matricula_egresado': matricula_egresado,
                        'matricula_contratado': matricula_contratado,
                        'nombre_completo': nombre_completo,
                        'egresado_data': egresado_data
                    }
                    
                    st.session_state.mostrar_confirmacion_egresado = True
                    st.rerun()
            
            # CONFIRMACIÓN FINAL
            if st.session_state.get('mostrar_confirmacion_egresado', False):
                datos_form = st.session_state.get('datos_formulario_egresado', {})
                
                if datos_form:
                    st.subheader("📋 Resumen de la Migración")
                    st.info(f"**Matrícula actual:** {datos_form['matricula_egresado']}")
                    st.info(f"**Nueva matrícula:** {datos_form['matricula_contratado']}")
                    st.info(f"**Nombre:** {datos_form['nombre_completo']}")
                    st.info(f"**Puesto:** {datos_form['puesto']}")
                    st.info(f"**Departamento:** {datos_form['departamento']}")
                    
                    st.warning("⚠️ **¿Está seguro de proceder con la migración?** Esta acción no se puede deshacer.")
                    
                    col_confirm1, col_confirm2 = st.columns(2)
                    with col_confirm1:
                        if st.button("✅ Sí, proceder con la migración", type="primary", key="confirmar_migracion_egresado"):
                            return self.ejecutar_migracion_egresado_contratado(datos_form)
                    
                    with col_confirm2:
                        if st.button("❌ Cancelar migración", key="cancelar_migracion_egresado"):
                            st.info("Migración cancelada")
                            if 'mostrar_confirmacion_egresado' in st.session_state:
                                del st.session_state.mostrar_confirmacion_egresado
                            if 'datos_formulario_egresado' in st.session_state:
                                del st.session_state.datos_formulario_egresado
                            st.rerun()
                            return False
            
            return False
            
        except Exception as e:
            st.error(f"❌ Error en la migración: {str(e)}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return False

    def ejecutar_migracion_inscrito_estudiante(self, datos_form):
        """Ejecutar el proceso de migración inscrito → estudiante"""
        try:
            matricula_inscrito = datos_form['matricula_inscrito']
            matricula_estudiante = datos_form['matricula_estudiante']
            inscrito_data = datos_form['inscrito_data']
            
            if not inscrito_data:
                st.error("❌ Error: Datos del inscrito no disponibles")
                return False
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 1. Buscar usuario en base de datos
            status_text.text("🔍 Buscando usuario en base de datos...")
            progress_bar.progress(10)
            usuario_id = self.buscar_usuario_por_matricula(matricula_inscrito)
            
            if usuario_id:
                # Actualizar usuario en SQLite
                status_text.text("👤 Actualizando usuario en base de datos...")
                progress_bar.progress(20)
                if self.actualizar_rol_usuario(usuario_id, 'estudiante', matricula_estudiante):
                    st.success("✅ Usuario actualizado exitosamente")
                else:
                    st.warning("⚠️ No se pudo actualizar usuario, continuando con migración")
            else:
                st.warning("⚠️ Usuario no encontrado, continuando con migración de datos")
            
            # 2. Renombrar archivos PDF
            status_text.text("📁 Renombrando archivos PDF en servidor remoto...")
            progress_bar.progress(40)
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_inscrito, matricula_estudiante)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.info("ℹ️ No se encontraron archivos PDF para renombrar")
            
            # 3. Eliminar inscrito y crear estudiante
            status_text.text("🔄 Procesando migración de datos...")
            progress_bar.progress(60)
            
            # Eliminar inscrito
            if self.db.eliminar_inscrito(matricula_inscrito):
                st.success(f"✅ Inscrito eliminado: {matricula_inscrito}")
            else:
                st.error(f"❌ Error eliminando inscrito: {matricula_inscrito}")
                return False
            
            # Crear estudiante
            nuevo_estudiante = {
                'matricula': matricula_estudiante,
                'nombre_completo': inscrito_data.get('nombre_completo', ''),
                'programa': datos_form.get('programa', ''),
                'email': inscrito_data.get('email', ''),
                'telefono': inscrito_data.get('telefono', ''),
                'fecha_nacimiento': datos_form.get('fecha_nacimiento', datetime.now()),
                'genero': datos_form.get('genero', ''),
                'fecha_inscripcion': datetime.now(),
                'estatus': datos_form.get('estatus', 'ACTIVO'),
                'documentos_subidos': datos_form.get('documentos_subidos', ''),
                'fecha_registro': datos_form.get('fecha_registro', datetime.now()),
                'programa_interes': datos_form.get('programa_interes', ''),
                'folio': datos_form.get('folio', ''),
                'como_se_entero': datos_form.get('como_se_entero', ''),
                'fecha_ingreso': datos_form.get('fecha_ingreso', datetime.now()),
                'usuario': matricula_estudiante
            }
            
            estudiante_id = self.db.agregar_estudiante(nuevo_estudiante)
            if estudiante_id:
                st.success(f"✅ Estudiante creado: {matricula_estudiante}")
            else:
                st.error(f"❌ Error creando estudiante: {matricula_estudiante}")
                return False
            
            # Registrar en bitácora
            status_text.text("📝 Registrando en bitácora...")
            progress_bar.progress(80)
            self.db.registrar_bitacora(
                st.session_state.usuario_actual.get('usuario', 'admin'),
                'MIGRACION_INSCRITO_ESTUDIANTE',
                f'Usuario migrado de inscrito a estudiante. Matrícula: {matricula_inscrito} -> {matricula_estudiante}'
            )
            
            # Registrar migración exitosa
            estado_migracion.registrar_migracion()
            
            # Sincronizar cambios con servidor remoto
            status_text.text("🌐 Sincronizando cambios con servidor remoto...")
            progress_bar.progress(90)
            if self.db.sincronizar_hacia_remoto():
                st.success("✅ Cambios sincronizados con servidor remoto")
            else:
                st.error("❌ Error sincronizando cambios")
                return False
            
            status_text.text("✅ Migración completada")
            progress_bar.progress(100)
            
            st.success(f"🎉 ¡Migración completada exitosamente!")
            st.balloons()
            
            # Mostrar resumen final
            st.subheader("📊 Resumen Final de la Migración")
            st.success(f"✅ Matrícula actualizada: {matricula_inscrito} → {matricula_estudiante}")
            st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
            st.success(f"✅ Registro creado en estudiantes")
            st.success(f"✅ Registro eliminado de inscritos")
            st.success(f"✅ Cambios sincronizados con servidor remoto")
            
            # Limpiar estado de sesión
            if 'inscrito_seleccionado' in st.session_state:
                del st.session_state.inscrito_seleccionado
            if 'mostrar_confirmacion_inscrito' in st.session_state:
                del st.session_state.mostrar_confirmacion_inscrito
            if 'datos_formulario_inscrito' in st.session_state:
                del st.session_state.datos_formulario_inscrito
            
            # Recargar datos
            time.sleep(2)
            st.rerun()
            return True
                
        except Exception as e:
            st.error(f"❌ Error ejecutando la migración: {str(e)}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return False

    def ejecutar_migracion_estudiante_egresado(self, datos_form):
        """Ejecutar el proceso de migración estudiante → egresado"""
        try:
            matricula_estudiante = datos_form['matricula_estudiante']
            matricula_egresado = datos_form['matricula_egresado']
            estudiante_data = datos_form['estudiante_data']
            
            if not estudiante_data:
                st.error("❌ Error: Datos del estudiante no disponibles")
                return False
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 1. Buscar usuario en base de datos
            status_text.text("🔍 Buscando usuario en base de datos...")
            progress_bar.progress(10)
            usuario_id = self.buscar_usuario_por_matricula(matricula_estudiante)
            
            if usuario_id:
                # Actualizar usuario en SQLite
                status_text.text("👤 Actualizando usuario en base de datos...")
                progress_bar.progress(20)
                if self.actualizar_rol_usuario(usuario_id, 'egresado', matricula_egresado):
                    st.success("✅ Usuario actualizado exitosamente")
                else:
                    st.warning("⚠️ No se pudo actualizar usuario, continuando con migración")
            else:
                st.warning("⚠️ Usuario no encontrado, continuando con migración de datos")
            
            # 2. Renombrar archivos PDF
            status_text.text("📁 Renombrando archivos PDF en servidor remoto...")
            progress_bar.progress(40)
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_estudiante, matricula_egresado)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.info("ℹ️ No se encontraron archivos PDF para renombrar")
            
            # 3. Eliminar estudiante y crear egresado
            status_text.text("🔄 Procesando migración de datos...")
            progress_bar.progress(60)
            
            # Eliminar estudiante
            if self.db.eliminar_estudiante(matricula_estudiante):
                st.success(f"✅ Estudiante eliminado: {matricula_estudiante}")
            else:
                st.error(f"❌ Error eliminando estudiante: {matricula_estudiante}")
                return False
            
            # Crear egresado
            nuevo_egresado = {
                'matricula': matricula_egresado,
                'nombre_completo': estudiante_data.get('nombre_completo', ''),
                'programa_original': datos_form.get('programa_original', ''),
                'fecha_graduacion': datos_form.get('fecha_graduacion', datetime.now()),
                'nivel_academico': datos_form.get('nivel_academico', ''),
                'email': datos_form.get('email', ''),
                'telefono': datos_form.get('telefono', ''),
                'estado_laboral': datos_form.get('estado_laboral', ''),
                'fecha_actualizacion': datetime.now(),
                'documentos_subidos': datos_form.get('documentos_subidos', '')
            }
            
            egresado_id = self.db.agregar_egresado(nuevo_egresado)
            if egresado_id:
                st.success(f"✅ Egresado creado: {matricula_egresado}")
            else:
                st.error(f"❌ Error creando egresado: {matricula_egresado}")
                return False
            
            # Registrar en bitácora
            status_text.text("📝 Registrando en bitácora...")
            progress_bar.progress(80)
            self.db.registrar_bitacora(
                st.session_state.usuario_actual.get('usuario', 'admin'),
                'MIGRACION_ESTUDIANTE_EGRESADO',
                f'Usuario migrado de estudiante a egresado. Matrícula: {matricula_estudiante} -> {matricula_egresado}'
            )
            
            # Registrar migración exitosa
            estado_migracion.registrar_migracion()
            
            # Sincronizar cambios con servidor remoto
            status_text.text("🌐 Sincronizando cambios con servidor remoto...")
            progress_bar.progress(90)
            if self.db.sincronizar_hacia_remoto():
                st.success("✅ Cambios sincronizados con servidor remoto")
            else:
                st.error("❌ Error sincronizando cambios")
                return False
            
            status_text.text("✅ Migración completada")
            progress_bar.progress(100)
            
            st.success(f"🎉 ¡Migración completada exitosamente!")
            st.balloons()
            
            # Mostrar resumen final
            st.subheader("📊 Resumen Final de la Migración")
            st.success(f"✅ Matrícula actualizada: {matricula_estudiante} → {matricula_egresado}")
            st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
            st.success(f"✅ Registro creado en egresados")
            st.success(f"✅ Registro eliminado de estudiantes")
            st.success(f"✅ Cambios sincronizados con servidor remoto")
            
            # Limpiar estado de sesión
            if 'estudiante_seleccionado' in st.session_state:
                del st.session_state.estudiante_seleccionado
            if 'mostrar_confirmacion_estudiante' in st.session_state:
                del st.session_state.mostrar_confirmacion_estudiante
            if 'datos_formulario_estudiante' in st.session_state:
                del st.session_state.datos_formulario_estudiante
            
            # Recargar datos
            time.sleep(2)
            st.rerun()
            return True
                
        except Exception as e:
            st.error(f"❌ Error ejecutando la migración: {str(e)}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return False

    def ejecutar_migracion_egresado_contratado(self, datos_form):
        """Ejecutar el proceso de migración egresado → contratado"""
        try:
            matricula_egresado = datos_form['matricula_egresado']
            matricula_contratado = datos_form['matricula_contratado']
            egresado_data = datos_form['egresado_data']
            
            if not egresado_data:
                st.error("❌ Error: Datos del egresado no disponibles")
                return False
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 1. Buscar usuario en base de datos
            status_text.text("🔍 Buscando usuario en base de datos...")
            progress_bar.progress(10)
            usuario_id = self.buscar_usuario_por_matricula(matricula_egresado)
            
            if usuario_id:
                # Actualizar usuario en SQLite
                status_text.text("👤 Actualizando usuario en base de datos...")
                progress_bar.progress(20)
                if self.actualizar_rol_usuario(usuario_id, 'contratado', matricula_contratado):
                    st.success("✅ Usuario actualizado exitosamente")
                else:
                    st.warning("⚠️ No se pudo actualizar usuario, continuando con migración")
            else:
                st.warning("⚠️ Usuario no encontrado, continuando con migración de datos")
            
            # 2. Renombrar archivos PDF
            status_text.text("📁 Renombrando archivos PDF en servidor remoto...")
            progress_bar.progress(40)
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_egresado, matricula_contratado)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.info("ℹ️ No se encontraron archivos PDF para renombrar")
            
            # 3. Eliminar egresado y crear contratado
            status_text.text("🔄 Procesando migración de datos...")
            progress_bar.progress(60)
            
            # Eliminar egresado
            if self.db.eliminar_egresado(matricula_egresado):
                st.success(f"✅ Egresado eliminado: {matricula_egresado}")
            else:
                st.error(f"❌ Error eliminando egresado: {matricula_egresado}")
                return False
            
            # Crear contratado
            nuevo_contratado = {
                'matricula': matricula_contratado,
                'fecha_contratacion': datos_form.get('fecha_contratacion', datetime.now()),
                'puesto': datos_form.get('puesto', ''),
                'departamento': datos_form.get('departamento', ''),
                'estatus': datos_form.get('estatus', ''),
                'salario': datos_form.get('salario', ''),
                'tipo_contrato': datos_form.get('tipo_contrato', ''),
                'fecha_inicio': datos_form.get('fecha_inicio', datetime.now()),
                'fecha_fin': datos_form.get('fecha_fin', datetime.now()),
                'documentos_subidos': datos_form.get('documentos_subidos', '')
            }
            
            contratado_id = self.db.agregar_contratado(nuevo_contratado)
            if contratado_id:
                st.success(f"✅ Contratado creado: {matricula_contratado}")
            else:
                st.error(f"❌ Error creando contratado: {matricula_contratado}")
                return False
            
            # Registrar en bitácora
            status_text.text("📝 Registrando en bitácora...")
            progress_bar.progress(80)
            self.db.registrar_bitacora(
                st.session_state.usuario_actual.get('usuario', 'admin'),
                'MIGRACION_EGRESADO_CONTRATADO',
                f'Usuario migrado de egresado a contratado. Matrícula: {matricula_egresado} -> {matricula_contratado}'
            )
            
            # Registrar migración exitosa
            estado_migracion.registrar_migracion()
            
            # Sincronizar cambios con servidor remoto
            status_text.text("🌐 Sincronizando cambios con servidor remoto...")
            progress_bar.progress(90)
            if self.db.sincronizar_hacia_remoto():
                st.success("✅ Cambios sincronizados con servidor remoto")
            else:
                st.error("❌ Error sincronizando cambios")
                return False
            
            status_text.text("✅ Migración completada")
            progress_bar.progress(100)
            
            st.success(f"🎉 ¡Migración completada exitosamente!")
            st.balloons()
            
            # Mostrar resumen final
            st.subheader("📊 Resumen Final de la Migración")
            st.success(f"✅ Matrícula actualizada: {matricula_egresado} → {matricula_contratado}")
            st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
            st.success(f"✅ Registro creado en contratados")
            st.success(f"✅ Registro eliminado de egresados")
            st.success(f"✅ Cambios sincronizados con servidor remoto")
            
            # Limpiar estado de sesión
            if 'egresado_seleccionado' in st.session_state:
                del st.session_state.egresado_seleccionado
            if 'mostrar_confirmacion_egresado' in st.session_state:
                del st.session_state.mostrar_confirmacion_egresado
            if 'datos_formulario_egresado' in st.session_state:
                del st.session_state.datos_formulario_egresado
            
            # Recargar datos
            time.sleep(2)
            st.rerun()
            return True
                
        except Exception as e:
            st.error(f"❌ Error ejecutando la migración: {str(e)}")
            import traceback
            st.error(f"Detalles del error: {traceback.format_exc()}")
            return False

# Instancia del sistema de migración completo
migrador = SistemaMigracionCompleto()

# =============================================================================
# INTERFAZ PRINCIPAL DEL MIGRADOR - CORREGIDA
# =============================================================================

def mostrar_login_migracion():
    """Interfaz de login para el migrador - SIEMPRE MOSTRAR FORMULARIO"""
    st.title("🔄 Sistema Escuela Enfermería - Migración SSH REMOTA")
    st.markdown("---")
    
    # Mostrar estado actual
    col1, col2 = st.columns(2)
    
    with col1:
        if estado_migracion.esta_inicializada():
            st.success("✅ Base de datos inicializada")
        else:
            st.warning("⚠️ Base de datos NO inicializada")
    
    with col2:
        if estado_migracion.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
        else:
            st.error("❌ SSH Desconectado")
    
    st.markdown("---")
    
    # SIEMPRE mostrar formulario de login, independientemente del estado
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form_migracion"):
            st.subheader("Iniciar Sesión en Migrador")
            
            usuario = st.text_input("👤 Usuario", placeholder="admin", key="login_usuario_migracion")
            password = st.text_input("🔒 Contraseña", type="password", placeholder="Admin123!", key="login_password_migracion")
            
            col_a, col_b = st.columns(2)
            with col_a:
                login_button = st.form_submit_button("🚀 Iniciar Sesión", use_container_width=True)
            with col_b:
                inicializar_button = st.form_submit_button("🔄 Inicializar DB", use_container_width=True, type="secondary")

            if login_button:
                if usuario and password:
                    with st.spinner("Verificando credenciales..."):
                        if auth_migracion.verificar_login(usuario, password):
                            st.rerun()
                        else:
                            st.error("❌ Credenciales incorrectas")
                else:
                    st.warning("⚠️ Complete todos los campos")
            
            if inicializar_button:
                with st.spinner("Inicializando base de datos en servidor remoto..."):
                    if db_migracion.sincronizar_desde_remoto():
                        st.success("✅ Base de datos remota inicializada")
                        st.info("Ahora puedes iniciar sesión con:")
                        st.info("👤 Usuario: admin")
                        st.info("🔒 Contraseña: Admin123!")
                        st.rerun()
                    else:
                        st.error("❌ Error inicializando base de datos")
            
            # Información de acceso
            with st.expander("ℹ️ Información de acceso"):
                st.info("""
                **Primer uso:**
                1. Haz clic en **"Inicializar DB"** para crear la base de datos en el servidor
                2. Usa las credenciales por defecto que se crearán automáticamente
                3. Inicia sesión con esas credenciales
                
                **Credenciales por defecto (después de inicializar):**
                - 👤 Usuario: **admin**
                - 🔒 Contraseña: **Admin123!**
                """)

def mostrar_interfaz_migracion():
    """Interfaz principal después del login en el migrador"""
    # Barra superior con información del usuario
    usuario_actual = st.session_state.usuario_actual
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
    
    with col1:
        st.title("🔄 Sistema Escuela Enfermería - Migración SSH REMOTA")
        nombre_usuario = usuario_actual.get('nombre_completo', usuario_actual.get('usuario', 'Usuario'))
        st.write(f"**👤 Administrador:** {nombre_usuario}")
    
    with col2:
        if gestor_remoto_migracion.config.get('host'):
            st.write(f"**🔗 Servidor:** {gestor_remoto_migracion.config['host']}")
    
    with col3:
        if st.button("🔄 Recargar Datos", use_container_width=True):
            migrador.cargar_datos()
            st.rerun()
    
    with col4:
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            auth_migracion.cerrar_sesion()
            st.rerun()
    
    st.markdown("---")
    
    # Selección de tipo de migración
    st.subheader("🎯 Seleccionar Tipo de Migración")
    
    tipo_migracion = st.radio(
        "Seleccione el tipo de migración a realizar:",
        [
            "📝 Inscrito → Estudiante",
            "🎓 Estudiante → Egresado", 
            "💼 Egresado → Contratado"
        ],
        horizontal=True
    )
    
    st.markdown("---")
    
    # Mostrar interfaz según el tipo de migración seleccionado
    if tipo_migracion == "📝 Inscrito → Estudiante":
        mostrar_migracion_inscritos()
    elif tipo_migracion == "🎓 Estudiante → Egresado":
        mostrar_migracion_estudiantes()
    elif tipo_migracion == "💼 Egresado → Contratado":
        mostrar_migracion_egresados()

def mostrar_migracion_inscritos():
    """Interfaz para migración de inscritos a estudiantes"""
    st.header("📝 Migración: Inscrito → Estudiante")
    
    # Si no hay datos, mostrar mensaje informativo
    if migrador.df_inscritos.empty:
        st.warning("📭 No hay inscritos disponibles para migrar")
        st.info("Los inscritos aparecerán aquí después de que se registren en el sistema principal.")
        
        # Opción para sincronizar
        if st.button("🔄 Sincronizar con servidor remoto"):
            with st.spinner("Sincronizando..."):
                if db_migracion.sincronizar_desde_remoto():
                    migrador.cargar_datos()
                    st.rerun()
                else:
                    st.error("❌ Error sincronizando")
        
        return
    
    # Mostrar estadísticas
    st.subheader("📊 Inscritos Disponibles para Migración")
    st.info(f"Total de inscritos: {len(migrador.df_inscritos)}")
    
    # Crear una copia para mostrar
    df_mostrar = migrador.df_inscritos.copy()
    
    # Seleccionar inscrito
    st.subheader("🎯 Seleccionar Inscrito para Migrar")
    
    if not df_mostrar.empty:
        # Crear lista de opciones usando matrícula y nombre
        opciones_inscritos = []
        for idx, inscrito in df_mostrar.iterrows():
            matricula = inscrito.get('matricula', 'Sin matrícula')
            nombre = inscrito.get('nombre_completo', 'Sin nombre')
            email = inscrito.get('email', 'Sin email')
            
            info = f"{matricula} | {nombre} | {email}"
            opciones_inscritos.append((info, idx))
        
        seleccion = st.selectbox(
            "Seleccione el inscrito a migrar:",
            options=[op[0] for op in opciones_inscritos],
            key="select_inscrito_migracion"
        )
        
        if seleccion:
            # Obtener el índice del inscrito seleccionado
            idx_seleccionado = [op[1] for op in opciones_inscritos if op[0] == seleccion][0]
            inscrito_seleccionado = df_mostrar.iloc[idx_seleccionado].to_dict()
            
            # Mostrar datos del inscrito seleccionado
            st.subheader("📋 Datos del Inscrito Seleccionado")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**👤 Información Personal:**")
                st.write(f"**Matrícula:** {inscrito_seleccionado.get('matricula', 'No disponible')}")
                st.write(f"**Nombre:** {inscrito_seleccionado.get('nombre_completo', 'No disponible')}")
                st.write(f"**Email:** {inscrito_seleccionado.get('email', 'No disponible')}")
                st.write(f"**Teléfono:** {inscrito_seleccionado.get('telefono', 'No disponible')}")
            
            with col2:
                st.write("**🎓 Información Académica:**")
                st.write(f"**Programa de Interés:** {inscrito_seleccionado.get('programa_interes', 'No disponible')}")
                st.write(f"**Fecha Registro:** {inscrito_seleccionado.get('fecha_registro', 'No disponible')}")
                st.write(f"**Estatus:** {inscrito_seleccionado.get('estatus', 'No disponible')}")
                st.write(f"**Documentos Subidos:** {inscrito_seleccionado.get('documentos_subidos', 'No disponible')}")
            
            # Botón para proceder con la migración
            st.markdown("---")
            if st.button("🚀 Iniciar Migración a Estudiante", type="primary", key="iniciar_migracion_inscrito"):
                st.session_state.inscrito_seleccionado = inscrito_seleccionado
                st.success("✅ Inscrito seleccionado. Complete el formulario de migración.")
                st.rerun()
            
            # Si ya se seleccionó un inscrito, mostrar formulario de migración
            if 'inscrito_seleccionado' in st.session_state and st.session_state.inscrito_seleccionado is not None:
                st.markdown("---")
                inscrito_data = st.session_state.inscrito_seleccionado
                if isinstance(inscrito_data, dict) and 'matricula' in inscrito_data:
                    migrador.migrar_inscrito_a_estudiante(inscrito_data)
                else:
                    st.error("❌ Error: Datos del inscrito no válidos")
                    del st.session_state.inscrito_seleccionado
                    st.rerun()
    
    else:
        st.warning("No hay inscritos disponibles para mostrar")

def mostrar_migracion_estudiantes():
    """Interfaz para migración de estudiantes a egresados"""
    st.header("🎓 Migración: Estudiante → Egresado")
    
    if migrador.df_estudiantes.empty:
        st.warning("📭 No hay estudiantes disponibles para migrar")
        st.info("Primero necesitas migrar inscritos a estudiantes.")
        return
    
    # Mostrar estadísticas
    st.subheader("📊 Estudiantes Disponibles para Migración")
    st.info(f"Total de estudiantes: {len(migrador.df_estudiantes)}")
    
    # Crear una copia para mostrar
    df_mostrar = migrador.df_estudiantes.copy()
    
    # Seleccionar estudiante
    st.subheader("🎯 Seleccionar Estudiante para Migrar")
    
    if not df_mostrar.empty:
        # Crear lista de opciones usando matrícula y nombre
        opciones_estudiantes = []
        for idx, estudiante in df_mostrar.iterrows():
            matricula = estudiante.get('matricula', 'Sin matrícula')
            nombre = estudiante.get('nombre_completo', 'Sin nombre')
            email = estudiante.get('email', 'Sin email')
            
            info = f"{matricula} | {nombre} | {email}"
            opciones_estudiantes.append((info, idx))
        
        seleccion = st.selectbox(
            "Seleccione el estudiante a migrar:",
            options=[op[0] for op in opciones_estudiantes],
            key="select_estudiante_migracion"
        )
        
        if seleccion:
            # Obtener el índice del estudiante seleccionado
            idx_seleccionado = [op[1] for op in opciones_estudiantes if op[0] == seleccion][0]
            estudiante_seleccionado = df_mostrar.iloc[idx_seleccionado].to_dict()
            
            # Mostrar datos del estudiante seleccionado
            st.subheader("📋 Datos del Estudiante Seleccionado")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**👤 Información Personal:**")
                st.write(f"**Matrícula:** {estudiante_seleccionado.get('matricula', 'No disponible')}")
                st.write(f"**Nombre:** {estudiante_seleccionado.get('nombre_completo', 'No disponible')}")
                st.write(f"**Email:** {estudiante_seleccionado.get('email', 'No disponible')}")
                st.write(f"**Teléfono:** {estudiante_seleccionado.get('telefono', 'No disponible')}")
            
            with col2:
                st.write("**🎓 Información Académica:**")
                st.write(f"**Programa:** {estudiante_seleccionado.get('programa', 'No disponible')}")
                st.write(f"**Fecha Inscripción:** {estudiante_seleccionado.get('fecha_inscripcion', 'No disponible')}")
                st.write(f"**Estatus:** {estudiante_seleccionado.get('estatus', 'No disponible')}")
                st.write(f"**Documentos Subidos:** {estudiante_seleccionado.get('documentos_subidos', 'No disponible')}")
            
            # Botón para proceder con la migración
            st.markdown("---")
            if st.button("🚀 Iniciar Migración a Egresado", type="primary", key="iniciar_migracion_estudiante"):
                st.session_state.estudiante_seleccionado = estudiante_seleccionado
                st.success("✅ Estudiante seleccionado. Complete el formulario de migración.")
                st.rerun()
            
            # Si ya se seleccionó un estudiante, mostrar formulario de migración
            if 'estudiante_seleccionado' in st.session_state and st.session_state.estudiante_seleccionado is not None:
                st.markdown("---")
                estudiante_data = st.session_state.estudiante_seleccionado
                if isinstance(estudiante_data, dict) and 'matricula' in estudiante_data:
                    migrador.migrar_estudiante_a_egresado(estudiante_data)
                else:
                    st.error("❌ Error: Datos del estudiante no válidos")
                    del st.session_state.estudiante_seleccionado
                    st.rerun()
    
    else:
        st.warning("No hay estudiantes disponibles para mostrar")

def mostrar_migracion_egresados():
    """Interfaz para migración de egresados a contratados"""
    st.header("💼 Migración: Egresado → Contratado")
    
    if migrador.df_egresados.empty:
        st.warning("📭 No hay egresados disponibles para migrar")
        st.info("Primero necesitas migrar estudiantes a egresados.")
        return
    
    # Mostrar estadísticas
    st.subheader("📊 Egresados Disponibles para Migración")
    st.info(f"Total de egresados: {len(migrador.df_egresados)}")
    
    # Crear una copia para mostrar
    df_mostrar = migrador.df_egresados.copy()
    
    # Seleccionar egresado
    st.subheader("🎯 Seleccionar Egresado para Migrar")
    
    if not df_mostrar.empty:
        # Crear lista de opciones usando matrícula y nombre
        opciones_egresados = []
        for idx, egresado in df_mostrar.iterrows():
            matricula = egresado.get('matricula', 'Sin matrícula')
            nombre = egresado.get('nombre_completo', 'Sin nombre')
            email = egresado.get('email', 'Sin email')
            
            info = f"{matricula} | {nombre} | {email}"
            opciones_egresados.append((info, idx))
        
        seleccion = st.selectbox(
            "Seleccione el egresado a migrar:",
            options=[op[0] for op in opciones_egresados],
            key="select_egresado_migracion"
        )
        
        if seleccion:
            # Obtener el índice del egresado seleccionado
            idx_seleccionado = [op[1] for op in opciones_egresados if op[0] == seleccion][0]
            egresado_seleccionado = df_mostrar.iloc[idx_seleccionado].to_dict()
            
            # Mostrar datos del egresado seleccionado
            st.subheader("📋 Datos del Egresado Seleccionado")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**👤 Información Personal:**")
                st.write(f"**Matrícula:** {egresado_seleccionado.get('matricula', 'No disponible')}")
                st.write(f"**Nombre:** {egresado_seleccionado.get('nombre_completo', 'No disponible')}")
                st.write(f"**Email:** {egresado_seleccionado.get('email', 'No disponible')}")
                st.write(f"**Teléfono:** {egresado_seleccionado.get('telefono', 'No disponible')}")
            
            with col2:
                st.write("**🎓 Información Académica:**")
                st.write(f"**Programa Original:** {egresado_seleccionado.get('programa_original', 'No disponible')}")
                st.write(f"**Fecha Graduación:** {egresado_seleccionado.get('fecha_graduacion', 'No disponible')}")
                st.write(f"**Nivel Académico:** {egresado_seleccionado.get('nivel_academico', 'No disponible')}")
                st.write(f"**Estado Laboral:** {egresado_seleccionado.get('estado_laboral', 'No disponible')}")
            
            # Botón para proceder con la migración
            st.markdown("---")
            if st.button("🚀 Iniciar Migración a Contratado", type="primary", key="iniciar_migracion_egresado"):
                st.session_state.egresado_seleccionado = egresado_seleccionado
                st.success("✅ Egresado seleccionado. Complete el formulario de migración.")
                st.rerun()
            
            # Si ya se seleccionado un egresado, mostrar formulario de migración
            if 'egresado_seleccionado' in st.session_state and st.session_state.egresado_seleccionado is not None:
                st.markdown("---")
                egresado_data = st.session_state.egresado_seleccionado
                if isinstance(egresado_data, dict) and 'matricula' in egresado_data:
                    migrador.migrar_egresado_a_contratado(egresado_data)
                else:
                    st.error("❌ Error: Datos del egresado no válidos")
                    del st.session_state.egresado_seleccionado
                    st.rerun()
    
    else:
        st.warning("No hay egresados disponibles para mostrar")

# =============================================================================
# FUNCIÓN PRINCIPAL - CORREGIDA
# =============================================================================

def main():
    """Función principal de la aplicación de migración"""
    
    # Sidebar con estado del sistema
    with st.sidebar:
        st.title("🔧 Sistema de Migración")
        st.markdown("---")
        
        st.subheader("🔗 Estado de Conexión SSH")
        
        # Estado de inicialización
        if estado_migracion.esta_inicializada():
            st.success("✅ Base de datos remota inicializada")
            fecha_inicializacion = estado_migracion.obtener_fecha_inicializacion()
            if fecha_inicializacion:
                st.caption(f"📅 Inicializada: {fecha_inicializacion.strftime('%Y-%m-%d %H:%M')}")
        else:
            st.warning("⚠️ Base de datos NO inicializada")
        
        # Estado de conexión SSH
        if estado_migracion.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
            if gestor_remoto_migracion.config.get('host'):
                st.caption(f"🌐 Servidor: {gestor_remoto_migracion.config['host']}")
        else:
            st.error("❌ SSH Desconectado")
            error_ssh = estado_migracion.estado.get('ssh_error')
            if error_ssh:
                st.caption(f"⚠️ Error: {error_ssh}")
        
        # Información del servidor
        with st.expander("📋 Información del Servidor"):
            if gestor_remoto_migracion.config.get('host'):
                st.write(f"**Host:** {gestor_remoto_migracion.config['host']}")
                st.write(f"**Puerto:** {gestor_remoto_migracion.config.get('port', 22)}")
                st.write(f"**Usuario:** {gestor_remoto_migracion.config['username']}")
                st.write(f"**Directorio:** {gestor_remoto_migracion.config.get('remote_dir', '')}")
                st.write(f"**DB Remota:** {gestor_remoto_migracion.config.get('remote_db_escuela', '')}")
        
        st.markdown("---")
        
        # Estadísticas de migración
        st.subheader("📈 Estadísticas")
        migraciones = estado_migracion.estado.get('migraciones_realizadas', 0)
        st.metric("Migraciones realizadas", migraciones)
        
        # Última sincronización
        ultima_sync = estado_migracion.estado.get('ultima_sincronizacion')
        if ultima_sync:
            try:
                fecha_sync = datetime.fromisoformat(ultima_sync)
                st.caption(f"🔄 Última sincronización: {fecha_sync.strftime('%H:%M:%S')}")
            except:
                pass
        
        st.markdown("---")
        
        # Botones de control - SOLO SI ESTÁ LOGUEADO
        st.subheader("⚙️ Controles")
        
        if st.session_state.get('login_exitoso', False):
            if st.button("🔄 Sincronizar Ahora", use_container_width=True):
                with st.spinner("Sincronizando con servidor remoto..."):
                    if db_migracion.sincronizar_desde_remoto():
                        migrador.cargar_datos()
                        st.success("✅ Sincronización exitosa")
                        st.rerun()
                    else:
                        st.error("❌ Error sincronizando")
            
            if st.button("🔗 Probar Conexión SSH", use_container_width=True):
                with st.spinner("Probando conexión SSH..."):
                    if gestor_remoto_migracion.verificar_conexion_ssh():
                        st.success("✅ Conexión SSH exitosa")
                        st.rerun()
                    else:
                        st.error("❌ Conexión SSH fallida")
            
            if st.button("📊 Ver Tablas", use_container_width=True):
                try:
                    with db_migracion.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tablas = cursor.fetchall()
                        
                        if tablas:
                            st.success(f"✅ {len(tablas)} tablas encontradas en servidor remoto:")
                            for tabla in tablas:
                                st.write(f"- {tabla[0]}")
                        else:
                            st.error("❌ No hay tablas en la base de datos remota")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
        else:
            st.info("ℹ️ Inicia sesión para usar los controles")
    
    # Inicializar estado de sesión
    if 'login_exitoso' not in st.session_state:
        st.session_state.login_exitoso = False
    if 'usuario_actual' not in st.session_state:
        st.session_state.usuario_actual = None
    if 'rol_usuario' not in st.session_state:
        st.session_state.rol_usuario = None
    if 'mostrar_confirmacion_inscrito' not in st.session_state:
        st.session_state.mostrar_confirmacion_inscrito = False
    if 'datos_formulario_inscrito' not in st.session_state:
        st.session_state.datos_formulario_inscrito = {}
    if 'inscrito_seleccionado' not in st.session_state:
        st.session_state.inscrito_seleccionado = None
    if 'estudiante_seleccionado' not in st.session_state:
        st.session_state.estudiante_seleccionado = None
    if 'egresado_seleccionado' not in st.session_state:
        st.session_state.egresado_seleccionado = None
    if 'mostrar_confirmacion_estudiante' not in st.session_state:
        st.session_state.mostrar_confirmacion_estudiante = False
    if 'datos_formulario_estudiante' not in st.session_state:
        st.session_state.datos_formulario_estudiante = {}
    if 'mostrar_confirmacion_egresado' not in st.session_state:
        st.session_state.mostrar_confirmacion_egresado = False
    if 'datos_formulario_egresado' not in st.session_state:
        st.session_state.datos_formulario_egresado = {}
    
    # Mostrar interfaz según estado de login
    if not st.session_state.login_exitoso:
        mostrar_login_migracion()
    else:
        mostrar_interfaz_migracion()

# =============================================================================
# EJECUCIÓN PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    try:
        # Mostrar banner informativo
        st.info("""
        🔄 **SISTEMA DE MIGRACIÓN EXCLUSIVAMENTE REMOTO**
        
        Este sistema trabaja EXCLUSIVAMENTE en modo remoto SSH.
        Todos los datos se guardan y sincronizan con el servidor configurado.
        
        **Para comenzar:**
        1. Configura secrets.toml con tus credenciales SSH
        2. Haz clic en "Inicializar DB" para crear la base de datos en el servidor
        3. Inicia sesión con las credenciales por defecto
        """)
        
        main()
    except Exception as e:
        st.error(f"❌ Error crítico en la aplicación de migración: {e}")
        logger.error(f"Error crítico en migración: {e}", exc_info=True)
        
        # Información de diagnóstico
        with st.expander("🔧 Información de diagnóstico"):
            st.write("**Estado persistente:**")
            st.json(estado_migracion.estado)
            
            st.write("**Configuración SSH cargada:**")
            if gestor_remoto_migracion.config:
                st.write(f"Host: {gestor_remoto_migracion.config.get('host', 'No configurado')}")
                st.write(f"Usuario: {gestor_remoto_migracion.config.get('username', 'No configurado')}")
            else:
                st.write("No hay configuración SSH cargada")
        
        # Botón de reinicio
        if st.button("🔄 Reiniciar Sistema", use_container_width=True):
            try:
                # Eliminar archivo de estado
                if os.path.exists(estado_migracion.archivo_estado):
                    os.remove(estado_migracion.archivo_estado)
                
                # Limpiar session_state
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                
                st.success("✅ Sistema reiniciado")
                st.rerun()
            except Exception as e2:
                st.error(f"❌ Error: {e2}")
