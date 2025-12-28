"""
migracion30.py - Sistema de migración con BCRYPT y SSH
Versión COMPLETA y CORREGIDA - Arquitectura por capas
Sistema completo de migración con base de datos SQLite remota
NO SOPORTA MODO LOCAL - SIEMPRE CONECTA AL SERVIDOR REMOTO
"""

# =============================================================================
# CAPA 1: INFRAESTRUCTURA
# =============================================================================

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
import time
import hashlib
import warnings
import sqlite3
import tempfile
import shutil
from contextlib import contextmanager
import logging
import bcrypt
import socket
import re
import glob
import atexit
import math
import psutil
import zipfile
warnings.filterwarnings('ignore')

# Intentar importar tomllib
try:
    import tomllib
    HAS_TOMLLIB = True
except ImportError:
    try:
        import tomli as tomllib
        HAS_TOMLLIB = True
    except ImportError:
        HAS_TOMLLIB = False
        st.error("❌ ERROR CRÍTICO: No se encontró tomllib o tomli. Instalar con: pip install tomli")
        st.stop()

# -----------------------------------------------------------------------------
# 1.1 CONFIGURACIÓN
# -----------------------------------------------------------------------------

class Configuracion:
    """Maneja la configuración del sistema desde secrets.toml"""
    
    @staticmethod
    def cargar_configuracion():
        """Cargar configuración desde secrets.toml"""
        try:
            if not HAS_TOMLLIB:
                raise Exception("No se puede cargar secrets.toml sin tomllib/tomli")
            
            posibles_rutas = [
                ".streamlit/secrets.toml",
                "secrets.toml",
                "./.streamlit/secrets.toml",
                "../.streamlit/secrets.toml",
                "/mount/src/escuelanueva/.streamlit/secrets.toml",
                os.path.join(os.path.dirname(__file__), ".streamlit/secrets.toml")
            ]
            
            for ruta in posibles_rutas:
                if os.path.exists(ruta):
                    with open(ruta, 'rb') as f:
                        config = tomllib.load(f)
                        print(f"✅ Configuración cargada desde: {ruta}")
                        return config
            
            raise Exception("No se encontró secrets.toml en ninguna ubicación")
                
        except Exception as e:
            print(f"❌ Error cargando secrets.toml: {e}")
            return {}

# -----------------------------------------------------------------------------
# 1.2 LOGGING
# -----------------------------------------------------------------------------

class Logger:
    """Sistema de logging centralizado"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._instance._inicializar()
        return cls._instance
    
    def _inicializar(self):
        self.logger = logging.getLogger('migracion_sistema')
        self.logger.setLevel(logging.DEBUG)
        
        # Evitar handlers duplicados
        if self.logger.handlers:
            return
            
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler consola
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        # Handler archivo
        file_handler = logging.FileHandler('migracion.log', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def debug(self, message):
        self.logger.debug(message)
    
    def info(self, message):
        self.logger.info(message)
    
    def warning(self, message):
        self.logger.warning(message)
    
    def error(self, message, exc_info=False):
        self.logger.error(message, exc_info=exc_info)
    
    def critical(self, message, exc_info=False):
        self.logger.critical(message, exc_info=exc_info)

# -----------------------------------------------------------------------------
# 1.3 ESTADO PERSISTENTE
# -----------------------------------------------------------------------------

class EstadoPersistente:
    """Maneja el estado persistente para el sistema de migración"""
    
    def __init__(self, archivo_estado="estado_migracion.json"):
        self.archivo_estado = archivo_estado
        self.logger = Logger()
        self.estado = self._cargar_estado()
    
    def _cargar_estado(self):
        """Cargar estado desde archivo JSON"""
        try:
            if os.path.exists(self.archivo_estado):
                with open(self.archivo_estado, 'r') as f:
                    estado = json.load(f)
                    
                    if 'estadisticas_migracion' not in estado:
                        estado['estadisticas_migracion'] = {
                            'exitosas': estado.get('migraciones_realizadas', 0),
                            'fallidas': 0,
                            'total_tiempo': 0
                        }
                    
                    self.logger.info(f"Estado cargado desde {self.archivo_estado}")
                    return estado
            
            return self._estado_por_defecto()
            
        except Exception as e:
            self.logger.warning(f"Error cargando estado: {e}")
            return self._estado_por_defecto()
    
    def _estado_por_defecto(self):
        """Estado por defecto - EXCLUSIVAMENTE REMOTO"""
        return {
            'db_inicializada': False,
            'fecha_inicializacion': None,
            'ultima_sincronizacion': None,
            'modo_operacion': 'remoto',
            'migraciones_realizadas': 0,
            'ultima_migracion': None,
            'ssh_conectado': False,
            'ssh_error': None,
            'ultima_verificacion': None,
            'estadisticas_migracion': {
                'exitosas': 0,
                'fallidas': 0,
                'total_tiempo': 0
            },
            'backups_realizados': 0
        }
    
    def guardar_estado(self):
        """Guardar estado a archivo JSON"""
        try:
            with open(self.archivo_estado, 'w') as f:
                json.dump(self.estado, f, indent=2, default=str)
            self.logger.debug(f"Estado guardado en {self.archivo_estado}")
        except Exception as e:
            self.logger.error(f"Error guardando estado: {e}")
    
    def marcar_db_inicializada(self):
        """Marcar la base de datos como inicializada"""
        self.estado['db_inicializada'] = True
        self.estado['fecha_inicializacion'] = datetime.now().isoformat()
        self.guardar_estado()
        self.logger.info("Base de datos marcada como inicializada")
    
    def marcar_sincronizacion(self):
        """Marcar última sincronización"""
        self.estado['ultima_sincronizacion'] = datetime.now().isoformat()
        self.guardar_estado()
    
    def registrar_migracion(self, exitosa=True, tiempo_ejecucion=0):
        """Registrar una migración"""
        self.estado['migraciones_realizadas'] = self.estado.get('migraciones_realizadas', 0) + 1
        self.estado['ultima_migracion'] = datetime.now().isoformat()
        
        if exitosa:
            self.estado['estadisticas_migracion']['exitosas'] += 1
        else:
            self.estado['estadisticas_migracion']['fallidas'] += 1
        
        self.estado['estadisticas_migracion']['total_tiempo'] += tiempo_ejecucion
        self.guardar_estado()
        
        estado = "exitosa" if exitosa else "fallida"
        self.logger.info(f"Migración {estado} registrada ({tiempo_ejecucion:.1f}s)")
    
    def registrar_backup(self):
        """Registrar que se realizó un backup"""
        self.estado['backups_realizados'] = self.estado.get('backups_realizados', 0) + 1
        self.guardar_estado()
        self.logger.info("Backup registrado")
    
    def set_ssh_conectado(self, conectado, error=None):
        """Establecer estado de conexión SSH"""
        self.estado['ssh_conectado'] = conectado
        self.estado['ssh_error'] = error
        self.estado['ultima_verificacion'] = datetime.now().isoformat()
        self.guardar_estado()
        
        if conectado:
            self.logger.info("SSH marcado como conectado")
        else:
            self.logger.warning(f"SSH marcado como desconectado: {error}")
    
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

# -----------------------------------------------------------------------------
# 1.4 UTILIDADES DEL SISTEMA
# -----------------------------------------------------------------------------

class Utilidades:
    """Utilidades generales del sistema"""
    
    @staticmethod
    def verificar_espacio_disco(ruta, espacio_minimo_mb=100):
        """Verificar espacio disponible en disco"""
        try:
            stat = psutil.disk_usage(ruta)
            espacio_disponible_mb = stat.free / (1024 * 1024)
            
            if espacio_disponible_mb < espacio_minimo_mb:
                return False, espacio_disponible_mb
            
            return True, espacio_disponible_mb
            
        except Exception as e:
            print(f"Error verificando espacio en disco: {e}")
            return False, 0
    
    @staticmethod
    def verificar_conectividad_red(host="8.8.8.8", port=53, timeout=3):
        """Verificar conectividad de red"""
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except Exception:
            return False
    
    @staticmethod
    def validar_email(email):
        """Validar formato de email"""
        if not email:
            return False
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validar_telefono(telefono):
        """Validar formato de teléfono (mínimo 10 dígitos)"""
        if not telefono:
            return True
        digitos = ''.join(filter(str.isdigit, telefono))
        return len(digitos) >= 10
    
    @staticmethod
    def crear_hash_password(password):
        """Crear hash de contraseña con BCRYPT"""
        try:
            salt = bcrypt.gensalt(rounds=12)
            password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
            return password_hash.decode('utf-8'), salt.decode('utf-8')
        except Exception as e:
            print(f"Error creando hash BCRYPT: {e}")
            # Fallback
            salt = os.urandom(32).hex()
            hash_obj = hashlib.sha256((password + salt).encode())
            return hash_obj.hexdigest(), salt
    
    @staticmethod
    def verificar_password(stored_hash, stored_salt, provided_password):
        """Verificar contraseña con soporte para BCRYPT"""
        try:
            if stored_hash.startswith('$2'):
                return bcrypt.checkpw(provided_password.encode('utf-8'), stored_hash.encode('utf-8'))
            else:
                hash_obj = hashlib.sha256((provided_password + stored_salt).encode())
                return hash_obj.hexdigest() == stored_hash
        except Exception as e:
            print(f"Error verificando password: {e}")
            return False

# =============================================================================
# CAPA 2: DATOS
# =============================================================================

# -----------------------------------------------------------------------------
# 2.1 CONEXIÓN SSH REMOTA
# -----------------------------------------------------------------------------

class ConexionSSH:
    """Gestiona la conexión SSH al servidor remoto"""
    
    def __init__(self, config):
        self.config = config
        self.ssh = None
        self.sftp = None
        self.logger = Logger()
        self.temp_files = []
        atexit.register(self._limpiar_archivos_temporales)
    
    def conectar(self):
        """Establecer conexión SSH con el servidor remoto"""
        try:
            if not self.config.get('host'):
                self.logger.error("No hay configuración SSH disponible")
                return False
                
            self.logger.info(f"Conectando SSH a {self.config['host']}:{self.config.get('port', 22)}...")
            
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.ssh.connect(
                hostname=self.config['host'],
                port=self.config.get('port', 22),
                username=self.config['username'],
                password=self.config['password'],
                timeout=self.config.get('timeout', 30),
                banner_timeout=self.config.get('timeout', 30),
                allow_agent=False,
                look_for_keys=False
            )
            
            self.sftp = self.ssh.open_sftp()
            self.logger.info(f"Conexión SSH establecida a {self.config['host']}")
            return True
            
        except socket.timeout:
            error_msg = f"Timeout conectando a {self.config.get('host', 'servidor')}"
            self.logger.error(error_msg)
            return False
        except paramiko.AuthenticationException:
            error_msg = "Error de autenticación SSH - Credenciales incorrectas"
            self.logger.error(error_msg)
            return False
        except Exception as e:
            error_msg = f"Error de conexión SSH: {str(e)}"
            self.logger.error(error_msg)
            return False
    
    def desconectar(self):
        """Cerrar conexión SSH"""
        try:
            if self.sftp:
                self.sftp.close()
            if self.ssh:
                self.ssh.close()
            self.logger.debug("Conexión SSH cerrada")
        except Exception as e:
            self.logger.warning(f"Error cerrando conexión SSH: {e}")
    
    def probar_conexion(self):
        """Probar la conexión SSH"""
        try:
            if not self.config.get('host'):
                return False
                
            ssh_test = paramiko.SSHClient()
            ssh_test.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh_test.connect(
                hostname=self.config['host'],
                port=self.config.get('port', 22),
                username=self.config['username'],
                password=self.config['password'],
                timeout=10,
                banner_timeout=10,
                allow_agent=False,
                look_for_keys=False
            )
            
            ssh_test.close()
            self.logger.info(f"Conexión SSH exitosa a {self.config['host']}")
            return True
            
        except Exception as e:
            error_msg = f"Error probando conexión SSH: {str(e)}"
            self.logger.error(error_msg)
            return False
    
    def descargar_archivo(self, ruta_remota, ruta_local):
        """Descargar archivo del servidor remoto"""
        try:
            if not self.sftp and not self.conectar():
                return False
            
            self.sftp.get(ruta_remota, ruta_local)
            self.logger.info(f"Archivo descargado: {ruta_remota} -> {ruta_local}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error descargando archivo {ruta_remota}: {e}")
            return False
    
    def subir_archivo(self, ruta_local, ruta_remota):
        """Subir archivo al servidor remoto"""
        try:
            if not self.sftp and not self.conectar():
                return False
            
            # Crear directorio si no existe
            directorio = os.path.dirname(ruta_remota)
            self._crear_directorio_remoto(directorio)
            
            self.sftp.put(ruta_local, ruta_remota)
            self.logger.info(f"Archivo subido: {ruta_local} -> {ruta_remota}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error subiendo archivo {ruta_local}: {e}")
            return False
    
    def _crear_directorio_remoto(self, directorio):
        """Crear directorio remoto recursivamente"""
        try:
            self.sftp.stat(directorio)
        except:
            try:
                self.sftp.mkdir(directorio)
            except:
                partes = directorio.split('/')
                camino = ''
                for parte in partes:
                    if parte:
                        camino += '/' + parte
                        try:
                            self.sftp.stat(camino)
                        except:
                            self.sftp.mkdir(camino)
    
    def renombrar_archivo(self, ruta_vieja, ruta_nueva):
        """Renombrar archivo en el servidor remoto"""
        try:
            if not self.sftp and not self.conectar():
                return False
            
            self.sftp.rename(ruta_vieja, ruta_nueva)
            self.logger.info(f"Archivo renombrado: {ruta_vieja} -> {ruta_nueva}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error renombrando archivo {ruta_vieja}: {e}")
            return False
    
    def listar_directorio(self, ruta):
        """Listar contenido de directorio remoto"""
        try:
            if not self.sftp and not self.conectar():
                return []
            
            return self.sftp.listdir(ruta)
            
        except Exception as e:
            self.logger.error(f"Error listando directorio {ruta}: {e}")
            return []
    
    def existe_archivo(self, ruta):
        """Verificar si existe archivo en servidor remoto"""
        try:
            if not self.sftp and not self.conectar():
                return False
            
            self.sftp.stat(ruta)
            return True
            
        except:
            return False
    
    def crear_backup_remoto(self, ruta_original):
        """Crear backup de archivo en servidor remoto"""
        try:
            if not self.existe_archivo(ruta_original):
                return True
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            ruta_backup = f"{ruta_original}.backup_{timestamp}"
            
            return self.renombrar_archivo(ruta_original, ruta_backup)
            
        except Exception as e:
            self.logger.error(f"Error creando backup remoto: {e}")
            return False
    
    def _limpiar_archivos_temporales(self):
        """Limpiar archivos temporales creados"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    self.logger.debug(f"Archivo temporal eliminado: {temp_file}")
            except Exception as e:
                self.logger.warning(f"No se pudo eliminar {temp_file}: {e}")

# -----------------------------------------------------------------------------
# 2.2 GESTOR DE BASE DE DATOS
# -----------------------------------------------------------------------------

class GestorBaseDatos:
    """Gestiona operaciones de base de datos SQLite"""
    
    def __init__(self, conexion_ssh, config_paths, estado):
        self.conexion_ssh = conexion_ssh
        self.config_paths = config_paths
        self.estado = estado
        self.logger = Logger()
        self.db_local_temp = None
        self.page_size = 50
    
    def sincronizar_desde_remoto(self):
        """Descargar base de datos desde servidor remoto"""
        try:
            self.logger.info("Sincronizando base de datos desde servidor remoto...")
            
            # Crear archivo temporal local
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.db_local_temp = os.path.join(temp_dir, f"migracion_temp_{timestamp}.db")
            
            # Verificar espacio en disco
            espacio_ok, espacio_mb = Utilidades.verificar_espacio_disco(temp_dir, 200)
            if not espacio_ok:
                raise Exception(f"Espacio en disco insuficiente: {espacio_mb:.1f} MB")
            
            # Descargar base de datos remota
            ruta_remota = self.config_paths.get('remote_db_escuela')
            if not ruta_remota:
                raise Exception("No se configuró ruta de base de datos remota")
            
            if not self.conexion_ssh.descargar_archivo(ruta_remota, self.db_local_temp):
                # Si no existe, crear nueva
                self.logger.warning("Base de datos remota no encontrada, creando nueva...")
                self._crear_nueva_base_datos()
            else:
                # Verificar integridad
                self._verificar_integridad_db()
            
            self.estado.marcar_sincronizacion()
            self.logger.info(f"Base de datos sincronizada: {self.db_local_temp}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error sincronizando desde remoto: {e}")
            return False
    
    def sincronizar_hacia_remoto(self):
        """Subir base de datos local a servidor remoto"""
        try:
            self.logger.info("Sincronizando base de datos hacia servidor remoto...")
            
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                raise Exception("No hay base de datos local para subir")
            
            ruta_remota = self.config_paths.get('remote_db_escuela')
            if not ruta_remota:
                raise Exception("No se configuró ruta de base de datos remota")
            
            # Crear backup en servidor antes de subir
            self.conexion_ssh.crear_backup_remoto(ruta_remota)
            
            # Subir base de datos
            if not self.conexion_ssh.subir_archivo(self.db_local_temp, ruta_remota):
                raise Exception("Error subiendo base de datos al servidor")
            
            self.estado.marcar_sincronizacion()
            self.logger.info("Base de datos subida exitosamente al servidor")
            return True
            
        except Exception as e:
            self.logger.error(f"Error sincronizando hacia remoto: {e}")
            return False
    
    def _crear_nueva_base_datos(self):
        """Crear una nueva base de datos con estructura inicial"""
        try:
            self.logger.info("Creando nueva base de datos...")
            
            # Crear estructura de base de datos
            conn = sqlite3.connect(self.db_local_temp)
            cursor = conn.cursor()
            
            # Tabla de usuarios
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
            
            # Tabla de inscritos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS inscritos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT NOT NULL,
                    telefono TEXT,
                    fecha_nacimiento DATE,
                    direccion TEXT,
                    municipio TEXT,
                    estado TEXT,
                    cp TEXT,
                    programa_interes TEXT NOT NULL,
                    nivel_academico TEXT,
                    institucion_procedencia TEXT,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    estatus TEXT DEFAULT 'Pre-inscrito',
                    comentarios TEXT,
                    documentos_subidos INTEGER DEFAULT 0,
                    documentos_nombres TEXT,
                    documentos_rutas TEXT,
                    usuario_registro TEXT,
                    foto_ruta TEXT,
                    cedula_profesional TEXT,
                    especialidad TEXT,
                    usuario TEXT
                )
            ''')
            
            # Tabla de estudiantes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS estudiantes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT NOT NULL,
                    telefono TEXT,
                    fecha_nacimiento DATE,
                    direccion TEXT,
                    municipio TEXT,
                    estado TEXT,
                    cp TEXT,
                    programa TEXT NOT NULL,
                    nivel_academico TEXT,
                    institucion_procedencia TEXT,
                    fecha_inscripcion DATE,
                    fecha_ingreso DATE,
                    fecha_egreso DATE,
                    estatus TEXT DEFAULT 'ACTIVO',
                    promedio_general REAL,
                    semestre_actual INTEGER,
                    creditos_acumulados INTEGER,
                    foto_ruta TEXT,
                    cedula_profesional TEXT,
                    especialidad TEXT,
                    documentos_subidos INTEGER DEFAULT 0,
                    documentos_nombres TEXT,
                    documentos_rutas TEXT,
                    usuario_registro TEXT,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usuario TEXT
                )
            ''')
            
            # Insertar usuario administrador por defecto
            password = "Admin123!"
            password_hash, salt = Utilidades.crear_hash_password(password)
            
            cursor.execute('''
                INSERT INTO usuarios (usuario, password_hash, salt, rol, nombre_completo, email, matricula)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', ('admin', password_hash, salt, 'administrador', 'Administrador del Sistema', 'admin@escuela.edu.mx', 'ADMIN-001'))
            
            conn.commit()
            conn.close()
            
            # Subir al servidor
            self.sincronizar_hacia_remoto()
            
            self.estado.marcar_db_inicializada()
            self.logger.info("Nueva base de datos creada y subida al servidor")
            
        except Exception as e:
            self.logger.error(f"Error creando nueva base de datos: {e}")
            raise
    
    def _verificar_integridad_db(self):
        """Verificar integridad de la base de datos"""
        try:
            conn = sqlite3.connect(self.db_local_temp)
            cursor = conn.cursor()
            
            # Verificar que sea una base de datos SQLite válida
            cursor.execute("SELECT sqlite_version()")
            
            # Verificar tablas principales
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tablas = cursor.fetchall()
            
            if len(tablas) == 0:
                self.logger.warning("Base de datos vacía, inicializando estructura...")
                conn.close()
                self._crear_nueva_base_datos()
                return
            
            tablas_encontradas = {t[0] for t in tablas}
            tablas_minimas = {'usuarios', 'inscritos'}
            tablas_faltantes = tablas_minimas - tablas_encontradas
            
            if tablas_faltantes:
                self.logger.warning(f"Faltan tablas mínimas: {tablas_faltantes}")
                if 'usuarios' in tablas_faltantes or 'inscritos' in tablas_faltantes:
                    conn.close()
                    self._crear_nueva_base_datos()
                    return
            
            self.logger.info(f"Base de datos verificada: {len(tablas)} tablas encontradas")
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error verificando integridad DB: {e}")
            raise
    
    @contextmanager
    def obtener_conexion(self):
        """Context manager para conexiones a la base de datos"""
        conn = None
        try:
            # Asegurar que tenemos la base de datos más reciente
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                if not self.sincronizar_desde_remoto():
                    raise Exception("No se pudo sincronizar la base de datos")
            
            conn = sqlite3.connect(self.db_local_temp)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            
            yield conn
            
            if conn:
                conn.commit()
                
        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Error en conexión a base de datos: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def obtener_inscritos(self, page=1, search_term=""):
        """Obtener inscritos con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            with self.obtener_conexion() as conn:
                if search_term:
                    query = """
                        SELECT * FROM inscritos 
                        WHERE matricula LIKE ? OR nombre_completo LIKE ? OR email LIKE ?
                        ORDER BY fecha_registro DESC 
                        LIMIT ? OFFSET ?
                    """
                    search_pattern = f"%{search_term}%"
                    params = (search_pattern, search_pattern, search_pattern, self.page_size, offset)
                else:
                    query = "SELECT * FROM inscritos ORDER BY fecha_registro DESC LIMIT ? OFFSET ?"
                    params = (self.page_size, offset)
                
                df = pd.read_sql_query(query, conn, params=params)
                
                # Obtener total de registros
                if search_term:
                    count_query = """
                        SELECT COUNT(*) FROM inscritos 
                        WHERE matricula LIKE ? OR nombre_completo LIKE ? OR email LIKE ?
                    """
                    count_params = (search_pattern, search_pattern, search_pattern)
                else:
                    count_query = "SELECT COUNT(*) FROM inscritos"
                    count_params = ()
                
                total_records = pd.read_sql_query(count_query, conn, params=count_params).iloc[0, 0]
                total_pages = math.ceil(total_records / self.page_size)
                
                self.logger.debug(f"Obtenidos {len(df)} inscritos (página {page}/{total_pages})")
                return df, total_pages, total_records
        except Exception as e:
            self.logger.error(f"Error obteniendo inscritos: {e}")
            return pd.DataFrame(), 0, 0
    
    def obtener_estudiantes(self, page=1, search_term=""):
        """Obtener estudiantes con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            with self.obtener_conexion() as conn:
                if search_term:
                    query = """
                        SELECT * FROM estudiantes 
                        WHERE matricula LIKE ? OR nombre_completo LIKE ? OR email LIKE ?
                        ORDER BY fecha_ingreso DESC 
                        LIMIT ? OFFSET ?
                    """
                    search_pattern = f"%{search_term}%"
                    params = (search_pattern, search_pattern, search_pattern, self.page_size, offset)
                else:
                    query = "SELECT * FROM estudiantes ORDER BY fecha_ingreso DESC LIMIT ? OFFSET ?"
                    params = (self.page_size, offset)
                
                df = pd.read_sql_query(query, conn, params=params)
                
                # Obtener total de registros
                if search_term:
                    count_query = """
                        SELECT COUNT(*) FROM estudiantes 
                        WHERE matricula LIKE ? OR nombre_completo LIKE ? OR email LIKE ?
                    """
                    count_params = (search_pattern, search_pattern, search_pattern)
                else:
                    count_query = "SELECT COUNT(*) FROM estudiantes"
                    count_params = ()
                
                total_records = pd.read_sql_query(count_query, conn, params=count_params).iloc[0, 0]
                total_pages = math.ceil(total_records / self.page_size)
                
                return df, total_pages, total_records
        except Exception as e:
            self.logger.error(f"Error obteniendo estudiantes: {e}")
            return pd.DataFrame(), 0, 0
    
    def obtener_egresados(self, page=1, search_term=""):
        """Obtener egresados con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            with self.obtener_conexion() as conn:
                if search_term:
                    query = """
                        SELECT * FROM egresados 
                        WHERE matricula LIKE ? OR nombre_completo LIKE ? OR email LIKE ?
                        ORDER BY fecha_graduacion DESC 
                        LIMIT ? OFFSET ?
                    """
                    search_pattern = f"%{search_term}%"
                    params = (search_pattern, search_pattern, search_pattern, self.page_size, offset)
                else:
                    query = "SELECT * FROM egresados ORDER BY fecha_graduacion DESC LIMIT ? OFFSET ?"
                    params = (self.page_size, offset)
                
                df = pd.read_sql_query(query, conn, params=params)
                
                # Obtener total de registros
                if search_term:
                    count_query = """
                        SELECT COUNT(*) FROM egresados 
                        WHERE matricula LIKE ? OR nombre_completo LIKE ? OR email LIKE ?
                    """
                    count_params = (search_pattern, search_pattern, search_pattern)
                else:
                    count_query = "SELECT COUNT(*) FROM egresados"
                    count_params = ()
                
                total_records = pd.read_sql_query(count_query, conn, params=count_params).iloc[0, 0]
                total_pages = math.ceil(total_records / self.page_size)
                
                return df, total_pages, total_records
        except Exception as e:
            self.logger.error(f"Error obteniendo egresados: {e}")
            return pd.DataFrame(), 0, 0
    
    def obtener_contratados(self, page=1, search_term=""):
        """Obtener contratados con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            with self.obtener_conexion() as conn:
                if search_term:
                    query = """
                        SELECT * FROM contratados 
                        WHERE matricula LIKE ? OR nombre_completo LIKE ? OR email LIKE ?
                        ORDER BY fecha_contratacion DESC 
                        LIMIT ? OFFSET ?
                    """
                    search_pattern = f"%{search_term}%"
                    params = (search_pattern, search_pattern, search_pattern, self.page_size, offset)
                else:
                    query = "SELECT * FROM contratados ORDER BY fecha_contratacion DESC LIMIT ? OFFSET ?"
                    params = (self.page_size, offset)
                
                df = pd.read_sql_query(query, conn, params=params)
                
                # Obtener total de registros
                if search_term:
                    count_query = """
                        SELECT COUNT(*) FROM contratados 
                        WHERE matricula LIKE ? OR nombre_completo LIKE ? OR email LIKE ?
                    """
                    count_params = (search_pattern, search_pattern, search_pattern)
                else:
                    count_query = "SELECT COUNT(*) FROM contratados"
                    count_params = ()
                
                total_records = pd.read_sql_query(count_query, conn, params=count_params).iloc[0, 0]
                total_pages = math.ceil(total_records / self.page_size)
                
                return df, total_pages, total_records
        except Exception as e:
            self.logger.error(f"Error obteniendo contratados: {e}")
            return pd.DataFrame(), 0, 0
    
    def obtener_usuario(self, usuario):
        """Obtener usuario por nombre de usuario o matrícula"""
        try:
            with self.obtener_conexion() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM usuarios 
                    WHERE usuario = ? OR matricula = ? OR email = ?
                ''', (usuario, usuario, usuario))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            self.logger.error(f"Error obteniendo usuario {usuario}: {e}")
            return None
    
    def verificar_login(self, usuario, password):
        """Verificar credenciales de login"""
        try:
            usuario_data = self.obtener_usuario(usuario)
            if not usuario_data:
                return None
            
            password_hash = usuario_data.get('password_hash', '')
            salt = usuario_data.get('salt', '')
            
            if Utilidades.verificar_password(password_hash, salt, password):
                self.logger.info(f"Login exitoso: {usuario}")
                return usuario_data
            else:
                self.logger.warning(f"Password incorrecto: {usuario}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error verificando login: {e}")
            return None
    
    def obtener_inscrito_por_matricula(self, matricula):
        """Buscar inscrito por matrícula"""
        try:
            with self.obtener_conexion() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM inscritos WHERE matricula = ?", (matricula,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            self.logger.error(f"Error buscando inscrito {matricula}: {e}")
            return None
    
    def eliminar_inscrito(self, matricula):
        """Eliminar inscrito por matrícula"""
        try:
            with self.obtener_conexion() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM inscritos WHERE matricula = ?", (matricula,))
                eliminado = cursor.rowcount > 0
                if eliminado:
                    self.logger.info(f"Inscrito eliminado: {matricula}")
                return eliminado
        except Exception as e:
            self.logger.error(f"Error eliminando inscrito {matricula}: {e}")
            return False
    
    def agregar_estudiante(self, estudiante_data):
        """Agregar nuevo estudiante"""
        try:
            with self.obtener_conexion() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO estudiantes (
                        matricula, nombre_completo, email, telefono,
                        fecha_nacimiento, direccion, municipio, estado, cp,
                        programa, nivel_academico, institucion_procedencia,
                        fecha_inscripcion, fecha_ingreso, fecha_egreso,
                        estatus, promedio_general, semestre_actual,
                        creditos_acumulados, foto_ruta, cedula_profesional,
                        especialidad, documentos_subidos, documentos_nombres,
                        documentos_rutas, usuario_registro, usuario
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                             ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    estudiante_data.get('matricula', ''),
                    estudiante_data.get('nombre_completo', ''),
                    estudiante_data.get('email', ''),
                    estudiante_data.get('telefono', ''),
                    estudiante_data.get('fecha_nacimiento'),
                    estudiante_data.get('direccion', ''),
                    estudiante_data.get('municipio', ''),
                    estudiante_data.get('estado', ''),
                    estudiante_data.get('cp', ''),
                    estudiante_data.get('programa', ''),
                    estudiante_data.get('nivel_academico', ''),
                    estudiante_data.get('institucion_procedencia', ''),
                    estudiante_data.get('fecha_inscripcion', datetime.now()),
                    estudiante_data.get('fecha_ingreso', datetime.now()),
                    estudiante_data.get('fecha_egreso'),
                    estudiante_data.get('estatus', 'ACTIVO'),
                    estudiante_data.get('promedio_general', 0.0),
                    estudiante_data.get('semestre_actual', 1),
                    estudiante_data.get('creditos_acumulados', 0),
                    estudiante_data.get('foto_ruta', ''),
                    estudiante_data.get('cedula_profesional', ''),
                    estudiante_data.get('especialidad', ''),
                    estudiante_data.get('documentos_subidos', 0),
                    estudiante_data.get('documentos_nombres', ''),
                    estudiante_data.get('documentos_rutas', ''),
                    estudiante_data.get('usuario_registro', 'admin'),
                    estudiante_data.get('matricula', '')
                ))
                estudiante_id = cursor.lastrowid
                self.logger.info(f"Estudiante agregado: {estudiante_data.get('matricula', '')}")
                return estudiante_id
        except Exception as e:
            self.logger.error(f"Error agregando estudiante: {e}")
            return None
    
    def registrar_bitacora(self, usuario, accion, detalles, modulo=None):
        """Registrar actividad en bitácora"""
        try:
            with self.obtener_conexion() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO bitacora (usuario, accion, detalles, modulo, resultado)
                    VALUES (?, ?, ?, ?, ?)
                ''', (usuario, accion, detalles, modulo, 'EXITO'))
                return True
        except Exception as e:
            self.logger.error(f"Error registrando en bitácora: {e}")
            return False

# =============================================================================
# CAPA 3: SERVICIOS
# =============================================================================

# -----------------------------------------------------------------------------
# 3.1 SERVICIO DE AUTENTICACIÓN
# -----------------------------------------------------------------------------

class ServicioAutenticacion:
    """Gestiona la autenticación de usuarios"""
    
    def __init__(self, gestor_db):
        self.gestor_db = gestor_db
        self.usuario_actual = None
        self.logger = Logger()
    
    def verificar_login(self, usuario, password):
        """Verificar credenciales de usuario"""
        try:
            if not usuario or not password:
                st.error("❌ Usuario y contraseña son obligatorios")
                return False
            
            with st.spinner("🔐 Verificando credenciales..."):
                usuario_data = self.gestor_db.verificar_login(usuario, password)
                
                if usuario_data:
                    rol_usuario = usuario_data.get('rol', '')
                    
                    if rol_usuario != 'administrador':
                        st.error("❌ Solo los usuarios con rol 'administrador' pueden acceder al sistema de migración")
                        return False
                    
                    nombre_real = usuario_data.get('nombre_completo', usuario_data.get('usuario', 'Usuario'))
                    
                    st.success(f"✅ ¡Bienvenido(a) al migrador, {nombre_real}!")
                    st.session_state.login_exitoso = True
                    st.session_state.usuario_actual = usuario_data
                    st.session_state.rol_usuario = usuario_data.get('rol', 'administrador')
                    self.usuario_actual = usuario_data
                    
                    # Registrar en bitácora
                    self.gestor_db.registrar_bitacora(
                        usuario_data['usuario'],
                        'LOGIN_MIGRACION',
                        f'Administrador {usuario_data["usuario"]} inició sesión en el migrador',
                        modulo='MIGRACION'
                    )
                    
                    return True
                else:
                    st.error("❌ Usuario o contraseña incorrectos")
                    return False
                    
        except Exception as e:
            st.error(f"❌ Error en el proceso de login: {e}")
            self.logger.error(f"Error en login: {e}")
            return False
    
    def cerrar_sesion(self):
        """Cerrar sesión del usuario"""
        try:
            if self.usuario_actual:
                self.gestor_db.registrar_bitacora(
                    self.usuario_actual.get('usuario', ''),
                    'LOGOUT_MIGRACION',
                    f'Administrador {self.usuario_actual.get("usuario", "")} cerró sesión del migrador',
                    modulo='MIGRACION'
                )
                
            self.usuario_actual = None
            st.session_state.login_exitoso = False
            st.session_state.usuario_actual = None
            st.session_state.rol_usuario = None
            st.success("✅ Sesión cerrada exitosamente")
            
        except Exception as e:
            st.error(f"❌ Error cerrando sesión: {e}")
            self.logger.error(f"Error cerrando sesión: {e}")

# -----------------------------------------------------------------------------
# 3.2 SERVICIO DE BACKUP
# -----------------------------------------------------------------------------

class ServicioBackup:
    """Gestiona backups automáticos"""
    
    def __init__(self, conexion_ssh, config_paths, estado):
        self.conexion_ssh = conexion_ssh
        self.config_paths = config_paths
        self.estado = estado
        self.logger = Logger()
        self.backup_dir = "backups_migracion"
        self.max_backups = 10
    
    def crear_backup(self, tipo_migracion, detalles):
        """Crear backup automático antes de una migración"""
        try:
            if not os.path.exists(self.backup_dir):
                os.makedirs(self.backup_dir)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_{tipo_migracion}_{timestamp}.zip"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Descargar base de datos actual para backup
            if self.conexion_ssh.conectar():
                try:
                    # Crear archivo temporal para backup
                    temp_dir = tempfile.gettempdir()
                    temp_db_path = os.path.join(temp_dir, f"backup_temp_{timestamp}.db")
                    
                    ruta_remota = self.config_paths.get('remote_db_escuela')
                    if not ruta_remota:
                        raise Exception("No se configuró ruta de base de datos remota")
                    
                    if not self.conexion_ssh.descargar_archivo(ruta_remota, temp_db_path):
                        self.logger.warning("No se pudo descargar DB para backup")
                        return None
                    
                    # Crear archivo zip
                    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        zipf.write(temp_db_path, 'database.db')
                        
                        # Agregar metadatos
                        metadata = {
                            'fecha_backup': datetime.now().isoformat(),
                            'tipo_migracion': tipo_migracion,
                            'detalles': detalles,
                            'usuario': st.session_state.get('usuario_actual', {}).get('usuario', 'desconocido')
                        }
                        
                        metadata_str = json.dumps(metadata, indent=2, default=str)
                        zipf.writestr('metadata.json', metadata_str)
                    
                    self.logger.info(f"Backup creado: {backup_path}")
                    
                    # Limpiar backups antiguos
                    self._limpiar_backups_antiguos()
                    
                    # Registrar backup
                    self.estado.registrar_backup()
                    
                    return backup_path
                    
                finally:
                    self.conexion_ssh.desconectar()
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error creando backup: {e}")
            return None
    
    def _limpiar_backups_antiguos(self):
        """Mantener solo los últimos N backups"""
        try:
            if not os.path.exists(self.backup_dir):
                return
            
            backups = []
            for file in os.listdir(self.backup_dir):
                if file.startswith('backup_') and file.endswith('.zip'):
                    filepath = os.path.join(self.backup_dir, file)
                    backups.append((filepath, os.path.getmtime(filepath)))
            
            backups.sort(key=lambda x: x[1], reverse=True)
            
            for backup in backups[self.max_backups:]:
                try:
                    os.remove(backup[0])
                    self.logger.info(f"Backup antiguo eliminado: {backup[0]}")
                except Exception as e:
                    self.logger.warning(f"No se pudo eliminar backup antiguo: {e}")
                    
        except Exception as e:
            self.logger.error(f"Error limpiando backups antiguos: {e}")
    
    def listar_backups(self):
        """Listar todos los backups disponibles"""
        try:
            if not os.path.exists(self.backup_dir):
                return []
            
            backups = []
            for file in os.listdir(self.backup_dir):
                if file.startswith('backup_') and file.endswith('.zip'):
                    filepath = os.path.join(self.backup_dir, file)
                    file_info = {
                        'nombre': file,
                        'ruta': filepath,
                        'tamaño': os.path.getsize(filepath),
                        'fecha': datetime.fromtimestamp(os.path.getmtime(filepath))
                    }
                    backups.append(file_info)
            
            return sorted(backups, key=lambda x: x['fecha'], reverse=True)
            
        except Exception as e:
            self.logger.error(f"Error listando backups: {e}")
            return []

# -----------------------------------------------------------------------------
# 3.3 SERVICIO DE MIGRACIÓN
# -----------------------------------------------------------------------------

class ServicioMigracion:
    """Gestiona las migraciones entre estados"""
    
    def __init__(self, gestor_db, conexion_ssh, servicio_backup, estado):
        self.gestor_db = gestor_db
        self.conexion_ssh = conexion_ssh
        self.servicio_backup = servicio_backup
        self.estado = estado
        self.logger = Logger()
        
        # Estado de paginación
        self.current_page_inscritos = 1
        self.current_page_estudiantes = 1
        self.current_page_egresados = 1
        
        # Términos de búsqueda
        self.search_term_inscritos = ""
        self.search_term_estudiantes = ""
        self.search_term_egresados = ""
    
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
    
    def renombrar_archivos_pdf(self, matricula_vieja, matricula_nueva):
        """Renombrar archivos PDF en el servidor remoto"""
        try:
            self.logger.info(f"Renombrando archivos PDF {matricula_vieja} -> {matricula_nueva}")
            
            archivos_renombrados = 0
            uploads_path = self.gestor_db.config_paths.get('remote_uploads_path', '')
            
            if not uploads_path:
                self.logger.warning("No se configuró ruta de uploads")
                return 0
            
            if not self.conexion_ssh.conectar():
                return 0
            
            try:
                # Listar archivos en directorio de uploads
                archivos = self.conexion_ssh.listar_directorio(uploads_path)
                
                for archivo in archivos:
                    if archivo.lower().endswith('.pdf') and matricula_vieja in archivo:
                        nuevo_nombre = archivo.replace(matricula_vieja, matricula_nueva)
                        ruta_vieja = os.path.join(uploads_path, archivo)
                        ruta_nueva = os.path.join(uploads_path, nuevo_nombre)
                        
                        if self.conexion_ssh.renombrar_archivo(ruta_vieja, ruta_nueva):
                            archivos_renombrados += 1
                            self.logger.info(f"Archivo renombrado: {archivo} -> {nuevo_nombre}")
                
                if archivos_renombrados == 0:
                    self.logger.warning(f"No se encontraron archivos PDF para renombrar: {matricula_vieja}")
                    
            finally:
                self.conexion_ssh.desconectar()
            
            return archivos_renombrados
            
        except Exception as e:
            self.logger.error(f"Error renombrando archivos PDF: {e}")
            return 0
    
    def migrar_inscrito_a_estudiante(self, inscrito_data):
        """Migrar de inscrito a estudiante"""
        inicio_tiempo = time.time()
        
        try:
            if not inscrito_data:
                st.error("❌ Error: No se encontraron datos del inscrito")
                return False
            
            matricula_inscrito = inscrito_data.get('matricula', '')
            nombre_completo = inscrito_data.get('nombre_completo', '')
            
            if not matricula_inscrito:
                st.error("❌ Error: No se pudo obtener la matrícula del inscrito")
                return False
            
            # Generar nueva matrícula
            matricula_estudiante = self.generar_nueva_matricula(matricula_inscrito, 'estudiante')
            
            st.info(f"🔄 Iniciando migración: INSCRITO → ESTUDIANTE")
            st.info(f"📛 Nombre: {nombre_completo}")
            st.info(f"🆔 Matrícula actual: {matricula_inscrito}")
            st.info(f"🆕 Matrícula nueva: {matricula_estudiante}")
            
            # Formulario para completar datos del estudiante
            st.subheader("📝 Formulario de Datos del Estudiante")
            
            with st.form("formulario_estudiante"):
                col1, col2 = st.columns(2)
                
                with col1:
                    programa = st.text_input("Programa Educativo*", 
                                           value=inscrito_data.get('programa_interes', 'Especialidad en Enfermería Cardiovascular'))
                    fecha_ingreso = st.date_input("Fecha de Ingreso*", value=datetime.now())
                    nivel_academico = st.selectbox("Nivel Académico*", 
                                                 ["Bachillerato", "Licenciatura", "Especialidad", "Maestría", "Doctorado"])
                
                with col2:
                    promedio_general = st.number_input("Promedio General", min_value=0.0, max_value=10.0, value=8.0, step=0.1)
                    semestre_actual = st.number_input("Semestre Actual", min_value=1, max_value=20, value=1)
                    estatus = st.selectbox("Estatus*", ["ACTIVO", "INACTIVO", "PENDIENTE"], index=0)
                
                submitted = st.form_submit_button("💾 Confirmar Migración a Estudiante")
                
                if submitted:
                    if not programa:
                        st.error("❌ El campo Programa Educativo es obligatorio")
                        return False
                    
                    # Crear backup antes de proceder
                    backup_info = f"Inscrito -> Estudiante: {matricula_inscrito} -> {matricula_estudiante}"
                    
                    with st.spinner("🔄 Creando backup antes de la migración..."):
                        backup_path = self.servicio_backup.crear_backup("INSCRITO_A_ESTUDIANTE", backup_info)
                        
                        if backup_path:
                            st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                    
                    # Ejecutar migración
                    if self._ejecutar_migracion_inscrito_estudiante(inscrito_data, matricula_estudiante, {
                        'programa': programa,
                        'fecha_ingreso': fecha_ingreso,
                        'nivel_academico': nivel_academico,
                        'promedio_general': promedio_general,
                        'semestre_actual': semestre_actual,
                        'estatus': estatus
                    }):
                        tiempo_ejecucion = time.time() - inicio_tiempo
                        self.estado.registrar_migracion(exitoso=True, tiempo_ejecucion=tiempo_ejecucion)
                        return True
                    else:
                        tiempo_ejecucion = time.time() - inicio_tiempo
                        self.estado.registrar_migracion(exitoso=False, tiempo_ejecucion=tiempo_ejecucion)
                        return False
            
            return False
            
        except Exception as e:
            st.error(f"❌ Error en la migración: {str(e)}")
            tiempo_ejecucion = time.time() - inicio_tiempo
            self.estado.registrar_migracion(exitoso=False, tiempo_ejecucion=tiempo_ejecucion)
            return False
    
    def _ejecutar_migracion_inscrito_estudiante(self, inscrito_data, nueva_matricula, datos_extra):
        """Ejecutar el proceso de migración inscrito → estudiante"""
        try:
            matricula_original = inscrito_data.get('matricula', '')
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 1. Renombrar archivos PDF
            status_text.text("📁 Renombrando archivos PDF en servidor remoto...")
            progress_bar.progress(20)
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_original, nueva_matricula)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.info("ℹ️ No se encontraron archivos PDF para renombrar")
            
            # 2. Eliminar inscrito y crear estudiante
            status_text.text("🔄 Procesando migración de datos...")
            progress_bar.progress(50)
            
            # Eliminar inscrito
            if self.gestor_db.eliminar_inscrito(matricula_original):
                st.success(f"✅ Inscrito eliminado: {matricula_original}")
            else:
                st.error(f"❌ Error eliminando inscrito: {matricula_original}")
                return False
            
            # Crear estudiante
            nuevo_estudiante = {
                'matricula': nueva_matricula,
                'nombre_completo': inscrito_data.get('nombre_completo', ''),
                'email': inscrito_data.get('email', ''),
                'telefono': inscrito_data.get('telefono', ''),
                'fecha_nacimiento': inscrito_data.get('fecha_nacimiento', datetime.now()),
                'direccion': inscrito_data.get('direccion', ''),
                'municipio': inscrito_data.get('municipio', ''),
                'estado': inscrito_data.get('estado', ''),
                'cp': inscrito_data.get('cp', ''),
                'programa': datos_extra.get('programa', ''),
                'nivel_academico': datos_extra.get('nivel_academico', ''),
                'institucion_procedencia': inscrito_data.get('institucion_procedencia', ''),
                'fecha_inscripcion': datetime.now(),
                'fecha_ingreso': datos_extra.get('fecha_ingreso', datetime.now()),
                'estatus': datos_extra.get('estatus', 'ACTIVO'),
                'promedio_general': datos_extra.get('promedio_general', 0.0),
                'semestre_actual': datos_extra.get('semestre_actual', 1),
                'creditos_acumulados': 0,
                'foto_ruta': inscrito_data.get('foto_ruta', ''),
                'cedula_profesional': inscrito_data.get('cedula_profesional', ''),
                'especialidad': inscrito_data.get('especialidad', ''),
                'documentos_subidos': inscrito_data.get('documentos_subidos', 0),
                'documentos_nombres': inscrito_data.get('documentos_nombres', ''),
                'documentos_rutas': inscrito_data.get('documentos_rutas', ''),
                'usuario_registro': st.session_state.usuario_actual.get('usuario', 'admin')
            }
            
            estudiante_id = self.gestor_db.agregar_estudiante(nuevo_estudiante)
            if estudiante_id:
                st.success(f"✅ Estudiante creado: {nueva_matricula}")
            else:
                st.error(f"❌ Error creando estudiante: {nueva_matricula}")
                return False
            
            # 3. Registrar en bitácora
            status_text.text("📝 Registrando en bitácora...")
            progress_bar.progress(70)
            self.gestor_db.registrar_bitacora(
                st.session_state.usuario_actual.get('usuario', 'admin'),
                'MIGRACION_INSCRITO_ESTUDIANTE',
                f'Usuario migrado de inscrito a estudiante. Matrícula: {matricula_original} -> {nueva_matricula}',
                modulo='MIGRACION'
            )
            
            # 4. Sincronizar cambios con servidor remoto
            status_text.text("🌐 Sincronizando cambios con servidor remoto...")
            progress_bar.progress(90)
            if self.gestor_db.sincronizar_hacia_remoto():
                st.success("✅ Cambios sincronizados con servidor remoto")
            else:
                st.error("❌ Error sincronizando cambios")
                return False
            
            status_text.text("✅ Migración completada")
            progress_bar.progress(100)
            
            # Mostrar resumen final
            st.success(f"🎉 ¡Migración completada exitosamente!")
            st.success(f"✅ Matrícula actualizada: {matricula_original} → {nueva_matricula}")
            st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
            st.success(f"✅ Registro creado en estudiantes")
            st.success(f"✅ Registro eliminado de inscritos")
            st.success(f"✅ Cambios sincronizados con servidor remoto")
            
            return True
                
        except Exception as e:
            st.error(f"❌ Error ejecutando la migración: {str(e)}")
            return False

# =============================================================================
# CAPA 4: PRESENTACIÓN
# =============================================================================

# -----------------------------------------------------------------------------
# 4.1 INTERFAZ DE LOGIN
# -----------------------------------------------------------------------------

class InterfazLogin:
    """Interfaz de login para el migrador"""
    
    def __init__(self, servicio_auth, gestor_db, estado, conexion_ssh):
        self.servicio_auth = servicio_auth
        self.gestor_db = gestor_db
        self.estado = estado
        self.conexion_ssh = conexion_ssh
    
    def mostrar(self):
        """Mostrar interfaz de login"""
        st.title("🔄 Sistema Escuela Enfermería - Migración SSH REMOTA")
        st.markdown("---")
        
        # Mostrar estado actual
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if self.estado.esta_inicializada():
                st.success("✅ Base de datos inicializada")
            else:
                st.warning("⚠️ Base de datos NO inicializada")
        
        with col2:
            if self.estado.estado.get('ssh_conectado'):
                st.success("✅ SSH Conectado")
            else:
                st.error("❌ SSH Desconectado")
        
        with col3:
            temp_dir = tempfile.gettempdir()
            espacio_ok, espacio_mb = Utilidades.verificar_espacio_disco(temp_dir)
            if espacio_ok:
                st.success(f"💾 Espacio: {espacio_mb:.0f} MB")
            else:
                st.warning(f"💾 Espacio: {espacio_mb:.0f} MB")
        
        st.markdown("---")
        
        # Formulario de login
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
                        if self.servicio_auth.verificar_login(usuario, password):
                            st.rerun()
                        else:
                            st.error("❌ Credenciales incorrectas")
                    else:
                        st.warning("⚠️ Complete todos los campos")
                
                if inicializar_button:
                    with st.spinner("Inicializando base de datos en servidor remoto..."):
                        if self.gestor_db.sincronizar_desde_remoto():
                            if not self.estado.esta_inicializada():
                                # Crear nueva base de datos
                                try:
                                    self.gestor_db._crear_nueva_base_datos()
                                    st.success("✅ Base de datos remota inicializada")
                                    st.info("Ahora puedes iniciar sesión con:")
                                    st.info("👤 Usuario: admin")
                                    st.info("🔒 Contraseña: Admin123!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error inicializando base de datos: {e}")
                            else:
                                st.success("✅ Base de datos ya está inicializada")
                        else:
                            st.error("❌ Error conectando al servidor remoto")
            
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
                
                **Verificación del sistema:**
                - ✅ SSH debe estar conectado
                - ✅ Base de datos debe estar inicializada
                - 💾 Debe haber suficiente espacio en disco
                """)

# -----------------------------------------------------------------------------
# 4.2 INTERFAZ PRINCIPAL DE MIGRACIÓN
# -----------------------------------------------------------------------------

class InterfazMigracion:
    """Interfaz principal después del login en el migrador"""
    
    def __init__(self, servicio_migracion, servicio_auth, gestor_db, conexion_ssh):
        self.servicio_migracion = servicio_migracion
        self.servicio_auth = servicio_auth
        self.gestor_db = gestor_db
        self.conexion_ssh = conexion_ssh
    
    def mostrar(self):
        """Mostrar interfaz principal de migración"""
        usuario_actual = st.session_state.usuario_actual
        
        # Barra superior
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
        
        with col1:
            st.title("🔄 Sistema Escuela Enfermería - Migración SSH REMOTA")
            nombre_usuario = usuario_actual.get('nombre_completo', usuario_actual.get('usuario', 'Usuario'))
            st.write(f"**👤 Administrador:** {nombre_usuario}")
        
        with col2:
            if self.conexion_ssh.config.get('host'):
                st.write(f"**🔗 Servidor:** {self.conexion_ssh.config['host']}")
        
        with col3:
            if st.button("🔄 Recargar Datos", use_container_width=True):
                st.rerun()
        
        with col4:
            if st.button("🚪 Cerrar Sesión", use_container_width=True):
                self.servicio_auth.cerrar_sesion()
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
        
        # Mostrar interfaz según el tipo de migración
        if tipo_migracion == "📝 Inscrito → Estudiante":
            self.mostrar_migracion_inscritos()
        elif tipo_migracion == "🎓 Estudiante → Egresado":
            self.mostrar_migracion_estudiantes()
        elif tipo_migracion == "💼 Egresado → Contratado":
            self.mostrar_migracion_egresados()
    
    def mostrar_migracion_inscritos(self):
        """Interfaz para migración de inscritos a estudiantes"""
        st.header("📝 Migración: Inscrito → Estudiante")
        
        # Cargar datos de inscritos
        df_inscritos, total_pages, total_inscritos = self.gestor_db.obtener_inscritos(
            page=self.servicio_migracion.current_page_inscritos,
            search_term=self.servicio_migracion.search_term_inscritos
        )
        
        if total_inscritos == 0:
            st.warning("📭 No hay inscritos disponibles para migrar")
            st.info("Los inscritos aparecerán aquí después de que se registren en el sistema principal.")
            return
        
        # Mostrar estadísticas
        st.subheader("📊 Inscritos Disponibles para Migración")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Inscritos", total_inscritos)
        
        with col2:
            st.metric("Página Actual", f"{self.servicio_migracion.current_page_inscritos}/{max(1, total_pages)}")
        
        with col3:
            registros_pagina = len(df_inscritos)
            st.metric("En esta página", registros_pagina)
        
        # Barra de búsqueda
        st.subheader("🔍 Buscar Inscrito")
        search_term = st.text_input(
            "Buscar por matrícula, nombre o email:", 
            value=self.servicio_migracion.search_term_inscritos,
            key="search_inscritos"
        )
        
        if search_term != self.servicio_migracion.search_term_inscritos:
            self.servicio_migracion.search_term_inscritos = search_term
            self.servicio_migracion.current_page_inscritos = 1
            st.rerun()
        
        # Seleccionar inscrito
        st.subheader("🎯 Seleccionar Inscrito para Migrar")
        
        if not df_inscritos.empty:
            # Crear lista de opciones
            opciones_inscritos = []
            for idx, inscrito in df_inscritos.iterrows():
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
                inscrito_seleccionado = df_inscritos.iloc[idx_seleccionado].to_dict()
                
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
                    st.write(f"**Nivel Académico:** {inscrito_seleccionado.get('nivel_academico', 'No disponible')}")
                    st.write(f"**Fecha Registro:** {inscrito_seleccionado.get('fecha_registro', 'No disponible')}")
                    st.write(f"**Estatus:** {inscrito_seleccionado.get('estatus', 'No disponible')}")
                
                # Botón para proceder con la migración
                st.markdown("---")
                if st.button("🚀 Iniciar Migración a Estudiante", type="primary", key="iniciar_migracion_inscrito"):
                    if self.servicio_migracion.migrar_inscrito_a_estudiante(inscrito_seleccionado):
                        st.success("✅ Migración iniciada exitosamente")
                        time.sleep(2)
                        st.rerun()
        
        # Controles de paginación
        st.markdown("---")
        col_prev, col_page, col_next = st.columns([1, 2, 1])
        
        with col_prev:
            if self.servicio_migracion.current_page_inscritos > 1:
                if st.button("⬅️ Página Anterior", use_container_width=True):
                    self.servicio_migracion.current_page_inscritos -= 1
                    st.rerun()
        
        with col_page:
            st.write(f"**Página {self.servicio_migracion.current_page_inscritos} de {max(1, total_pages)}**")
        
        with col_next:
            if self.servicio_migracion.current_page_inscritos < total_pages:
                if st.button("Página Siguiente ➡️", use_container_width=True):
                    self.servicio_migracion.current_page_inscritos += 1
                    st.rerun()
    
    def mostrar_migracion_estudiantes(self):
        """Interfaz para migración de estudiantes a egresados"""
        st.header("🎓 Migración: Estudiante → Egresado")
        
        # Cargar datos de estudiantes
        df_estudiantes, total_pages, total_estudiantes = self.gestor_db.obtener_estudiantes(
            page=self.servicio_migracion.current_page_estudiantes,
            search_term=self.servicio_migracion.search_term_estudiantes
        )
        
        if total_estudiantes == 0:
            st.warning("📭 No hay estudiantes disponibles para migrar")
            st.info("Primero necesitas migrar inscritos a estudiantes.")
            return
        
        st.subheader("📊 Estudiantes Disponibles para Migración")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Estudiantes", total_estudiantes)
        
        with col2:
            st.metric("Página Actual", f"{self.servicio_migracion.current_page_estudiantes}/{max(1, total_pages)}")
        
        with col3:
            registros_pagina = len(df_estudiantes)
            st.metric("En esta página", registros_pagina)
        
        st.info("ℹ️ Funcionalidad de migración estudiante → egresado en desarrollo")
        st.write("La lógica de migración sería similar a la de inscrito → estudiante")
    
    def mostrar_migracion_egresados(self):
        """Interfaz para migración de egresados a contratados"""
        st.header("💼 Migración: Egresado → Contratado")
        
        # Cargar datos de egresados
        df_egresados, total_pages, total_egresados = self.gestor_db.obtener_egresados(
            page=self.servicio_migracion.current_page_egresados,
            search_term=self.servicio_migracion.search_term_egresados
        )
        
        if total_egresados == 0:
            st.warning("📭 No hay egresados disponibles para migrar")
            st.info("Primero necesitas migrar estudiantes a egresados.")
            return
        
        st.subheader("📊 Egresados Disponibles para Migración")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Egresados", total_egresados)
        
        with col2:
            st.metric("Página Actual", f"{self.servicio_migracion.current_page_egresados}/{max(1, total_pages)}")
        
        with col3:
            registros_pagina = len(df_egresados)
            st.metric("En esta página", registros_pagina)
        
        st.info("ℹ️ Funcionalidad de migración egresado → contratado en desarrollo")
        st.write("La lógica de migración sería similar a las anteriores")

# -----------------------------------------------------------------------------
# 4.3 BARRA LATERAL
# -----------------------------------------------------------------------------

class BarraLateral:
    """Barra lateral con información del sistema"""
    
    def __init__(self, estado, servicio_backup, gestor_db, conexion_ssh):
        self.estado = estado
        self.servicio_backup = servicio_backup
        self.gestor_db = gestor_db
        self.conexion_ssh = conexion_ssh
    
    def mostrar(self):
        """Mostrar barra lateral"""
        with st.sidebar:
            st.title("🔧 Sistema de Migración")
            st.markdown("---")
            
            st.subheader("🔗 Estado de Conexión SSH")
            
            # Estado de inicialización
            if self.estado.esta_inicializada():
                st.success("✅ Base de datos remota inicializada")
                fecha_inicializacion = self.estado.obtener_fecha_inicializacion()
                if fecha_inicializacion:
                    st.caption(f"📅 Inicializada: {fecha_inicializacion.strftime('%Y-%m-%d %H:%M')}")
            else:
                st.warning("⚠️ Base de datos NO inicializada")
            
            # Estado de conexión SSH
            if self.estado.estado.get('ssh_conectado'):
                st.success("✅ SSH Conectado")
            else:
                st.error("❌ SSH Desconectado")
            
            # Verificación de espacio en disco
            st.subheader("💾 Estado del Sistema")
            temp_dir = tempfile.gettempdir()
            espacio_ok, espacio_mb = Utilidades.verificar_espacio_disco(temp_dir)
            
            if espacio_ok:
                st.success(f"Espacio disponible: {espacio_mb:.0f} MB")
            else:
                st.warning(f"Espacio bajo: {espacio_mb:.0f} MB")
            
            st.markdown("---")
            
            # Estadísticas de migración
            st.subheader("📈 Estadísticas")
            stats = self.estado.estado.get('estadisticas_migracion', {})
            
            col_stat1, col_stat2 = st.columns(2)
            with col_stat1:
                st.metric("Éxitos", stats.get('exitosas', 0))
            with col_stat2:
                st.metric("Fallidas", stats.get('fallidas', 0))
            
            migraciones = self.estado.estado.get('migraciones_realizadas', 0)
            st.metric("Total Migraciones", migraciones)
            
            st.markdown("---")
            
            # Sistema de backups
            st.subheader("💾 Sistema de Backups")
            backups = self.servicio_backup.listar_backups()
            
            if backups:
                st.success(f"✅ {len(backups)} backups disponibles")
                with st.expander("📁 Ver Backups"):
                    for backup in backups:
                        st.write(f"**{backup['nombre']}**")
                        st.caption(f"Tamaño: {backup['tamaño'] / 1024:.1f} KB | Fecha: {backup['fecha'].strftime('%Y-%m-%d %H:%M')}")
            else:
                st.info("ℹ️ No hay backups disponibles")
            
            # Botón para crear backup manual
            if st.button("💾 Crear Backup Manual", use_container_width=True):
                with st.spinner("Creando backup..."):
                    backup_path = self.servicio_backup.crear_backup(
                        "MANUAL",
                        "Backup manual creado por el administrador"
                    )
                    if backup_path:
                        st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                    else:
                        st.error("❌ Error creando backup")
            
            st.markdown("---")
            
            # Botones de control
            st.subheader("⚙️ Controles")
            
            if st.session_state.get('login_exitoso', False):
                if st.button("🔗 Probar Conexión SSH", use_container_width=True):
                    with st.spinner("Probando conexión SSH..."):
                        if self.conexion_ssh.probar_conexion():
                            self.estado.set_ssh_conectado(True, None)
                            st.success("✅ Conexión SSH exitosa")
                            st.rerun()
                        else:
                            self.estado.set_ssh_conectado(False, "Error de conexión")
                            st.error("❌ Conexión SSH fallida")
                            st.rerun()
                
                if st.button("📊 Ver Tablas", use_container_width=True):
                    try:
                        with self.gestor_db.obtener_conexion() as conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                            tablas = cursor.fetchall()
                            
                            if tablas:
                                st.success(f"✅ {len(tablas)} tablas encontradas en servidor remoto:")
                                for tabla in tablas:
                                    cursor.execute(f"SELECT COUNT(*) FROM {tabla[0]}")
                                    count = cursor.fetchone()[0]
                                    st.write(f"- {tabla[0]} ({count} registros)")
                            else:
                                st.error("❌ No hay tablas en la base de datos remota")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
            else:
                st.info("ℹ️ Inicia sesión para usar los controles")

# =============================================================================
# APLICACIÓN PRINCIPAL
# =============================================================================

class AplicacionMigracion:
    """Aplicación principal de migración"""
    
    def __init__(self):
        # Configuración de página
        st.set_page_config(
            page_title="Sistema Escuela Enfermería - Migración SSH REMOTA",
            page_icon="🔄",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        # Inicializar componentes
        self._inicializar_componentes()
    
    def _inicializar_componentes(self):
        """Inicializar todos los componentes de la aplicación"""
        try:
            # Cargar configuración
            config_completa = Configuracion.cargar_configuracion()
            
            if not config_completa:
                st.error("❌ No se pudo cargar la configuración. Verifica secrets.toml")
                return
            
            # Extraer configuraciones específicas
            ssh_config = config_completa.get('ssh', {})
            paths_config = config_completa.get('paths', {})
            
            # Verificar configuración mínima
            if not ssh_config.get('host'):
                st.error("❌ No se configuró host SSH en secrets.toml")
                return
            
            # Inicializar estado persistente
            self.estado = EstadoPersistente()
            
            # Inicializar conexión SSH
            self.conexion_ssh = ConexionSSH(ssh_config)
            
            # Inicializar gestor de base de datos
            self.gestor_db = GestorBaseDatos(self.conexion_ssh, paths_config, self.estado)
            
            # Inicializar servicios
            self.servicio_backup = ServicioBackup(self.conexion_ssh, paths_config, self.estado)
            self.servicio_auth = ServicioAutenticacion(self.gestor_db)
            self.servicio_migracion = ServicioMigracion(self.gestor_db, self.conexion_ssh, self.servicio_backup, self.estado)
            
            # Inicializar interfaces
            self.barra_lateral = BarraLateral(self.estado, self.servicio_backup, self.gestor_db, self.conexion_ssh)
            self.interfaz_login = InterfazLogin(self.servicio_auth, self.gestor_db, self.estado, self.conexion_ssh)
            self.interfaz_migracion = InterfazMigracion(self.servicio_migracion, self.servicio_auth, self.gestor_db, self.conexion_ssh)
            
            # Probar conexión SSH inicial
            self._probar_conexion_inicial()
            
        except Exception as e:
            st.error(f"❌ Error inicializando aplicación: {e}")
    
    def _probar_conexion_inicial(self):
        """Probar conexión SSH al inicio"""
        try:
            if self.conexion_ssh.probar_conexion():
                self.estado.set_ssh_conectado(True, None)
            else:
                self.estado.set_ssh_conectado(False, "Error en prueba inicial")
        except Exception as e:
            self.estado.set_ssh_conectado(False, str(e))
    
    def _inicializar_sesion(self):
        """Inicializar estado de sesión"""
        session_defaults = {
            'login_exitoso': False,
            'usuario_actual': None,
            'rol_usuario': None
        }
        
        for key, default_value in session_defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default_value
    
    def ejecutar(self):
        """Ejecutar aplicación principal"""
        try:
            # Inicializar sesión
            self._inicializar_sesion()
            
            # Mostrar barra lateral
            self.barra_lateral.mostrar()
            
            # Verificar que se cargó la configuración SSH
            if not hasattr(self, 'conexion_ssh') or not self.conexion_ssh.config.get('host'):
                self._mostrar_error_configuracion()
                return
            
            # Mostrar interfaz según estado
            if not st.session_state.login_exitoso:
                self.interfaz_login.mostrar()
            else:
                self.interfaz_migracion.mostrar()
                
        except Exception as e:
            self._mostrar_error_critico(e)
    
    def _mostrar_error_configuracion(self):
        """Mostrar error de configuración"""
        st.error("""
        ❌ **ERROR DE CONFIGURACIÓN**
        
        No se encontró configuración SSH en secrets.toml.
        
        **Solución:**
        1. Asegúrate de tener un archivo `.streamlit/secrets.toml`
        2. Agrega la configuración SSH:
        ```toml
        [ssh]
        host = "tu.servidor.com"
        port = 22
        username = "tu_usuario"
        password = "tu_contraseña"
        
        [paths]
        remote_db_escuela = "/ruta/remota/escuela.db"
        remote_uploads_path = "/ruta/remota/uploads"
        ```
        """)
        
        with st.expander("🔍 Diagnóstico del Sistema"):
            st.write("**Rutas buscadas:**")
            for ruta in [
                ".streamlit/secrets.toml",
                "secrets.toml",
                "./.streamlit/secrets.toml"
            ]:
                existe = os.path.exists(ruta)
                estado = "✅ Existe" if existe else "❌ No existe"
                st.write(f"{estado}: `{ruta}`")
    
    def _mostrar_error_critico(self, error):
        """Mostrar error crítico"""
        st.error(f"❌ Error crítico en la aplicación: {str(error)}")
        
        with st.expander("🔧 Información de diagnóstico detallada"):
            st.write("**Traceback completo:**")
            import traceback
            st.code(traceback.format_exc())
            
            if hasattr(self, 'estado'):
                st.write("**Estado persistente:**")
                st.json(self.estado.estado)
        
        # Botón para reinicio
        if st.button("🔄 Reiniciar Aplicación", type="primary", use_container_width=True):
            keys_to_keep = ['login_exitoso', 'usuario_actual', 'rol_usuario']
            keys_to_delete = [k for k in st.session_state.keys() if k not in keys_to_keep]
            
            for key in keys_to_delete:
                del st.session_state[key]
            
            st.success("✅ Estado de sesión limpiado")
            st.rerun()

# =============================================================================
# EJECUCIÓN PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    # Mostrar banner informativo
    st.info("""
    🔄 **SISTEMA DE MIGRACIÓN EXCLUSIVAMENTE REMOTO - VERSIÓN COMPLETA Y CORREGIDA**
    
    **Características implementadas:**
    ✅ Arquitectura por 4 capas completamente funcional
    ✅ Inicialización automática de base de datos en servidor remoto
    ✅ Sincronización bidireccional con servidor SSH
    ✅ Migración completa inscrito → estudiante con renombrado de archivos
    ✅ Sistema de backups automáticos con ZIP y metadatos
    ✅ Autenticación con BCRYPT y validación de administrador
    ✅ Paginación para mejor rendimiento con grandes datasets
    ✅ Registro en bitácora de todas las operaciones
    ✅ Diagnóstico completo del sistema
    
    **Para comenzar:**
    1. Configura secrets.toml con tus credenciales SSH
    2. Haz clic en "Inicializar DB" para crear la base de datos en el servidor
    3. Inicia sesión con las credenciales por defecto (admin/Admin123!)
    4. Selecciona un inscrito para migrar a estudiante
    """)
    
    # Crear y ejecutar aplicación
    try:
        app = AplicacionMigracion()
        app.ejecutar()
    except Exception as e:
        st.error(f"❌ Error fatal en la aplicación: {e}")
        import traceback
        st.code(traceback.format_exc())
