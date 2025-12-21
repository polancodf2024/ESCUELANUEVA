import streamlit as st
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, date, timedelta
import hashlib
import base64
import random
import string
from PIL import Image
import paramiko
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import warnings
import sqlite3
import tempfile
import bcrypt
import socket
import re
import time
import logging
import atexit
import glob
import psutil
import math
warnings.filterwarnings('ignore')

# =============================================================================
# CONFIGURACIÓN DE PÁGINA PARA WEBSITE PÚBLICO
# =============================================================================

st.set_page_config(
    page_title="Sistema Escuela Enfermería - Pre-Inscripción",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# CONFIGURACIÓN DE LOGGING
# =============================================================================

class SistemaLogger:
    """Sistema de logging para diagnóstico"""
    
    def __init__(self):
        # Configurar logging
        self.logger = logging.getLogger('aspirantes_sistema')
        self.logger.setLevel(logging.INFO)
        
        # Formato del log
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler para consola
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        # Handler para archivo
        file_handler = logging.FileHandler('aspirantes.log', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        # Agregar handlers
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def info(self, message):
        self.logger.info(message)
    
    def error(self, message):
        self.logger.error(message)
    
    def warning(self, message):
        self.logger.warning(message)
    
    def debug(self, message):
        self.logger.debug(message)

logger = SistemaLogger()

# =============================================================================
# VALIDACIONES DE DATOS
# =============================================================================

class ValidadorDatos:
    """Validaciones de datos mejoradas"""
    
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
            return True  # Opcional
        digitos = ''.join(filter(str.isdigit, telefono))
        return len(digitos) >= 10
    
    @staticmethod
    def validar_matricula(matricula):
        """Validar formato de matrícula"""
        if not matricula:
            return False
        return len(matricula) >= 3 and any(char.isdigit() for char in matricula)
    
    @staticmethod
    def validar_nombre_completo(nombre):
        """Validar nombre completo"""
        if not nombre:
            return False
        # Debe tener al menos 2 palabras (nombre y apellido)
        palabras = nombre.strip().split()
        return len(palabras) >= 2

# =============================================================================
# GESTOR DE CONEXIÓN REMOTA VIA SSH - MEJORADO
# =============================================================================

class GestorConexionRemota:
    """Gestor de conexión SSH al servidor remoto"""
    
    def __init__(self):
        self.ssh = None
        self.sftp = None
        self.temp_files = []
        self.config = self._cargar_configuracion()
        
        # Registrar limpieza al cerrar
        atexit.register(self._limpiar_archivos_temporales)
        
        # Timeouts
        self.timeouts = {
            'ssh_connect': 30,
            'ssh_command': 60,
            'sftp_transfer': 300
        }
        
        # Configurar rutas
        self.BASE_DIR_REMOTO = self.config.get('remote_dir', '')
        self.db_path_remoto = self.config.get('remote_db_inscritos', '')
        self.uploads_path_remoto = self.config.get('remote_uploads_inscritos', '')
        
        logger.info(f"🔗 Configuración SSH cargada: {self.config.get('host', 'No configurado')}")
    
    def _cargar_configuracion(self):
        """Cargar configuración desde secrets.toml"""
        try:
            config = {}
            
            # Intentar cargar desde secrets.toml
            try:
                # Configuración SSH
                config['host'] = st.secrets.get("remote_host", "")
                config['port'] = int(st.secrets.get("remote_port", 22))
                config['username'] = st.secrets.get("remote_user", "")
                config['password'] = st.secrets.get("remote_password", "")
                config['timeout'] = int(st.secrets.get("ssh_timeout", 30))
                config['remote_dir'] = st.secrets.get("remote_dir", "")
                
                # Rutas
                config['remote_db_inscritos'] = st.secrets.get("remote_db_inscritos", "")
                config['remote_uploads_inscritos'] = st.secrets.get("remote_uploads_inscritos", "")
                
                logger.info("✅ Configuración cargada desde secrets.toml")
                
            except Exception as e:
                logger.warning(f"⚠️ Error cargando secrets.toml: {e}")
                
                # Configuración por defecto para desarrollo
                config = {
                    'host': '',
                    'port': 22,
                    'username': '',
                    'password': '',
                    'timeout': 30,
                    'remote_dir': '',
                    'remote_db_inscritos': '',
                    'remote_uploads_inscritos': ''
                }
            
            return config
            
        except Exception as e:
            logger.error(f"❌ Error en configuración: {e}")
            return {}
    
    def _limpiar_archivos_temporales(self):
        """Limpiar archivos temporales creados"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.debug(f"🗑️ Archivo temporal eliminado: {temp_file}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar {temp_file}: {e}")
    
    def verificar_conectividad(self):
        """Verificar conectividad de red"""
        try:
            socket.setdefaulttimeout(3)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
            return True
        except:
            logger.warning("Sin conectividad de red")
            return False
    
    def conectar_ssh(self):
        """Establecer conexión SSH con el servidor remoto"""
        try:
            if not self.config.get('host'):
                logger.error("No hay configuración SSH disponible")
                return False
                
            if not self.verificar_conectividad():
                logger.error("No hay conectividad de red")
                return False
                
            logger.info(f"🔗 Conectando SSH a {self.config['host']}:{self.config['port']}...")
            
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.ssh.connect(
                hostname=self.config['host'],
                port=self.config['port'],
                username=self.config['username'],
                password=self.config['password'],
                timeout=self.timeouts['ssh_connect'],
                banner_timeout=self.timeouts['ssh_connect'],
                allow_agent=False,
                look_for_keys=False
            )
            
            self.sftp = self.ssh.open_sftp()
            self.sftp.get_channel().settimeout(self.timeouts['sftp_transfer'])
            
            logger.info(f"✅ Conexión SSH establecida a {self.config['host']}")
            return True
            
        except socket.timeout:
            logger.error(f"❌ Timeout conectando a {self.config['host']}")
            return False
        except paramiko.AuthenticationException:
            logger.error("❌ Error de autenticación SSH - Credenciales incorrectas")
            return False
        except Exception as e:
            logger.error(f"❌ Error de conexión: {str(e)}")
            return False
    
    def desconectar_ssh(self):
        """Cerrar conexión SSH"""
        try:
            if self.sftp:
                self.sftp.close()
            if self.ssh:
                self.ssh.close()
            logger.debug("🔌 Conexión SSH cerrada")
        except Exception as e:
            logger.warning(f"⚠️ Error cerrando conexión SSH: {e}")
    
    def descargar_db_remota(self):
        """Descargar base de datos SQLite del servidor remoto"""
        try:
            logger.info("📥 Descargando base de datos remota...")
            
            if not self.conectar_ssh():
                return None
            
            # Crear archivo temporal local
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_db_path = os.path.join(temp_dir, f"aspirantes_temp_{timestamp}.db")
            self.temp_files.append(temp_db_path)
            
            # Verificar que el archivo remoto existe
            try:
                self.sftp.stat(self.db_path_remoto)
                
                # Descargar archivo
                start_time = time.time()
                self.sftp.get(self.db_path_remoto, temp_db_path)
                download_time = time.time() - start_time
                
                # Verificar que se descargó correctamente
                if os.path.exists(temp_db_path) and os.path.getsize(temp_db_path) > 0:
                    file_size = os.path.getsize(temp_db_path)
                    logger.info(f"✅ Base de datos descargada: {temp_db_path} ({file_size} bytes en {download_time:.1f}s)")
                    
                    # Verificar integridad
                    if self._verificar_integridad_db(temp_db_path):
                        return temp_db_path
                    else:
                        logger.error("❌ Base de datos corrupta")
                        os.remove(temp_db_path)
                        return self._crear_nueva_db_remota()
                else:
                    logger.warning("⚠️ Archivo descargado vacío")
                    return self._crear_nueva_db_remota()
                    
            except FileNotFoundError:
                logger.warning("⚠️ Base de datos remota no encontrada, creando nueva")
                return self._crear_nueva_db_remota()
                
        except Exception as e:
            logger.error(f"❌ Error descargando base de datos: {e}")
            return None
        finally:
            if self.ssh:
                self.desconectar_ssh()
    
    def _verificar_integridad_db(self, db_path):
        """Verificar integridad de la base de datos SQLite"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Verificar que sea una base de datos SQLite válida
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()[0]
            logger.debug(f"SQLite version: {version}")
            
            # Verificar tablas principales
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tablas = cursor.fetchall()
            
            conn.close()
            return len(tablas) > 0
            
        except Exception as e:
            logger.error(f"Error verificando integridad DB: {e}")
            return False
    
    def _crear_nueva_db_remota(self):
        """Crear una nueva base de datos SQLite"""
        try:
            logger.info("📝 Creando nueva base de datos...")
            
            # Crear archivo temporal para la nueva base de datos
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_db_path = os.path.join(temp_dir, f"aspirantes_nueva_{timestamp}.db")
            self.temp_files.append(temp_db_path)
            
            # Inicializar la base de datos
            self._inicializar_db_estructura(temp_db_path)
            
            # Subir al servidor remoto
            if self.conectar_ssh():
                try:
                    # Crear directorio si no existe
                    remote_dir = os.path.dirname(self.db_path_remoto)
                    self._crear_directorio_remoto_recursivo(remote_dir)
                    
                    # Subir archivo
                    self.sftp.put(temp_db_path, self.db_path_remoto)
                    logger.info(f"✅ Nueva base de datos creada en servidor: {self.db_path_remoto}")
                finally:
                    self.desconectar_ssh()
            
            return temp_db_path
            
        except Exception as e:
            logger.error(f"❌ Error creando nueva base de datos: {e}")
            return None
    
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
            
            # Tabla de inscritos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS inscritos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT NOT NULL,
                    telefono TEXT,
                    programa_interes TEXT NOT NULL,
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
            
            # Tabla de usuarios (para los inscritos como usuarios del sistema)
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
            
            # Índices para rendimiento
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_inscritos_matricula ON inscritos(matricula)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_usuarios_usuario ON usuarios(usuario)')
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Estructura de base de datos inicializada en {db_path}")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura: {e}")
            raise
    
    def subir_db_remota(self, ruta_local):
        """Subir base de datos local al servidor remoto"""
        try:
            logger.info(f"📤 Subiendo base de datos al servidor remoto...")
            
            if not self.conectar_ssh():
                return False
            
            if not os.path.exists(ruta_local):
                logger.error(f"❌ Archivo local no existe: {ruta_local}")
                return False
            
            # Crear backup de la base de datos remota antes de sobreescribir
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = f"{self.db_path_remoto}.backup_{timestamp}"
                self.sftp.rename(self.db_path_remoto, backup_path)
                logger.info(f"✅ Backup creado en servidor: {backup_path}")
            except:
                logger.warning("⚠️ No se pudo crear backup en servidor")
                pass
            
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
    
    def guardar_documento_remoto(self, contenido_bytes, nombre_archivo):
        """Guardar documento en el servidor remoto"""
        try:
            if not self.conectar_ssh():
                return False
            
            # Crear directorio de uploads si no existe
            self._crear_directorio_remoto_recursivo(self.uploads_path_remoto)
            
            # Ruta completa del archivo
            ruta_completa = os.path.join(self.uploads_path_remoto, nombre_archivo)
            
            # Guardar archivo
            with self.sftp.file(ruta_completa, 'wb') as archivo_remoto:
                archivo_remoto.write(contenido_bytes)
            
            logger.info(f"✅ Documento guardado en servidor: {ruta_completa}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando documento remoto: {e}")
            return False
        finally:
            if self.ssh:
                self.desconectar_ssh()

# =============================================================================
# SISTEMA DE BASE DE DATOS SQLITE
# =============================================================================

class SistemaBaseDatos:
    """Sistema de base de datos SQLite remoto"""
    
    def __init__(self):
        self.gestor = GestorConexionRemota()
        self.db_local_temp = None
        self.ultima_sincronizacion = None
        self.validador = ValidadorDatos()
        
    def sincronizar_desde_remoto(self):
        """Sincronizar base de datos desde el servidor remoto"""
        try:
            logger.info("🔄 Sincronizando desde servidor remoto...")
            
            # Descargar base de datos remota
            self.db_local_temp = self.gestor.descargar_db_remota()
            
            if not self.db_local_temp:
                raise Exception("No se pudo obtener base de datos remota")
            
            # Verificar que el archivo existe
            if not os.path.exists(self.db_local_temp):
                raise Exception(f"Archivo de base de datos no existe: {self.db_local_temp}")
            
            self.ultima_sincronizacion = datetime.now()
            logger.info(f"✅ Sincronización exitosa: {self.db_local_temp}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error sincronizando: {e}")
            return False
    
    def sincronizar_hacia_remoto(self):
        """Sincronizar base de datos local hacia el servidor remoto"""
        try:
            logger.info("📤 Sincronizando hacia servidor remoto...")
            
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                raise Exception("No hay base de datos local para subir")
            
            # Subir al servidor remoto
            exito = self.gestor.subir_db_remota(self.db_local_temp)
            
            if exito:
                self.ultima_sincronizacion = datetime.now()
                logger.info("✅ Cambios subidos exitosamente al servidor")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"❌ Error sincronizando: {e}")
            return False
    
    def get_connection(self):
        """Obtener conexión a la base de datos"""
        try:
            # Asegurar que tenemos la base de datos más reciente
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                if not self.sincronizar_desde_remoto():
                    raise Exception("No se pudo sincronizar la base de datos")
            
            conn = sqlite3.connect(self.db_local_temp)
            conn.row_factory = sqlite3.Row
            return conn
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo conexión: {e}")
            raise
    
    def hash_password_bcrypt(self, password):
        """Crear hash de contraseña con BCRYPT"""
        try:
            salt = bcrypt.gensalt(rounds=12)
            password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
            return password_hash.decode('utf-8'), salt.decode('utf-8')
        except Exception as e:
            logger.error(f"Error al crear hash BCRYPT: {e}")
            # Fallback
            salt = os.urandom(32).hex()
            hash_obj = hashlib.sha256((password + salt).encode())
            return hash_obj.hexdigest(), salt
    
    def verificar_inscrito_existente(self, email, matricula):
        """Verificar si ya existe un inscrito con el mismo email o matrícula"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT COUNT(*) FROM inscritos 
                WHERE email = ? OR matricula = ?
            ''', (email, matricula))
            
            count = cursor.fetchone()[0]
            conn.close()
            
            return count > 0
            
        except Exception as e:
            logger.error(f"Error verificando inscrito existente: {e}")
            return False
    
    def agregar_inscrito(self, inscrito_data):
        """Agregar nuevo inscrito a la base de datos"""
        try:
            # Validar datos
            if not self.validador.validar_email(inscrito_data.get('email', '')):
                raise ValueError("Email inválido")
            
            if not self.validador.validar_nombre_completo(inscrito_data.get('nombre_completo', '')):
                raise ValueError("Nombre completo inválido")
            
            if not self.validador.validar_matricula(inscrito_data.get('matricula', '')):
                raise ValueError("Matrícula inválida")
            
            # Verificar si ya existe
            if self.verificar_inscrito_existente(
                inscrito_data.get('email', ''), 
                inscrito_data.get('matricula', '')
            ):
                raise ValueError("Ya existe un inscrito con este email o matrícula")
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Insertar inscrito
            cursor.execute('''
                INSERT INTO inscritos (
                    matricula, nombre_completo, email, telefono, programa_interes,
                    fecha_registro, estatus, folio, fecha_nacimiento, como_se_entero,
                    documentos_subidos, documentos_guardados
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                inscrito_data.get('matricula', ''),
                inscrito_data.get('nombre_completo', ''),
                inscrito_data.get('email', ''),
                inscrito_data.get('telefono', ''),
                inscrito_data.get('programa_interes', ''),
                inscrito_data.get('fecha_registro', datetime.now()),
                inscrito_data.get('estatus', 'Pre-inscrito'),
                inscrito_data.get('folio', ''),
                inscrito_data.get('fecha_nacimiento'),
                inscrito_data.get('como_se_entero', ''),
                inscrito_data.get('documentos_subidos', 0),
                inscrito_data.get('documentos_guardados', '')
            ))
            
            # También crear usuario para el inscrito
            password_hash, salt = self.hash_password_bcrypt("123")  # Password por defecto
            
            cursor.execute('''
                INSERT INTO usuarios (
                    usuario, password_hash, salt, rol, nombre_completo, 
                    email, matricula, activo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                inscrito_data.get('matricula', ''),
                password_hash,
                salt,
                'inscrito',
                inscrito_data.get('nombre_completo', ''),
                inscrito_data.get('email', ''),
                inscrito_data.get('matricula', ''),
                1
            ))
            
            inscrito_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            logger.info(f"Inscrito agregado: {inscrito_data.get('matricula', '')}")
            
            # Sincronizar con servidor remoto
            if self.sincronizar_hacia_remoto():
                return inscrito_id
            else:
                logger.warning("Inscrito agregado localmente pero error sincronizando con remoto")
                return inscrito_id
            
        except Exception as e:
            logger.error(f"Error agregando inscrito: {e}")
            raise
    
    def obtener_inscritos(self):
        """Obtener todos los inscritos"""
        try:
            conn = self.get_connection()
            df = pd.read_sql_query("SELECT * FROM inscritos ORDER BY fecha_registro DESC", conn)
            conn.close()
            return df
        except Exception as e:
            logger.error(f"Error obteniendo inscritos: {e}")
            return pd.DataFrame()
    
    def obtener_inscrito_por_matricula(self, matricula):
        """Buscar inscrito por matrícula"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM inscritos WHERE matricula = ?", (matricula,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error buscando inscrito: {e}")
            return None

# =============================================================================
# SISTEMA DE ENVÍO DE CORREOS ELECTRÓNICOS - MEJORADO
# =============================================================================

class SistemaCorreos:
    """Sistema de envío de correos electrónicos con manejo de errores"""
    
    def __init__(self):
        try:
            # Usar las claves correctas de secrets.toml
            self.smtp_server = st.secrets.get("smtp_server", "")
            self.smtp_port = int(st.secrets.get("smtp_port", 587))
            self.smtp_username = st.secrets.get("email_user", "")
            self.smtp_password = st.secrets.get("email_password", "")
            self.email_from = st.secrets.get("email_user", "")
            self.correos_habilitados = bool(self.smtp_server and self.smtp_username)
            
            if self.correos_habilitados:
                logger.info("✅ Sistema de correos habilitado")
            else:
                logger.warning("⚠️ Sistema de correos no configurado completamente")
                
        except Exception as e:
            logger.warning(f"⚠️ Configuración de correo no disponible: {e}")
            self.correos_habilitados = False
    
    def probar_conexion_smtp(self):
        """Probar conexión al servidor SMTP"""
        try:
            if not self.correos_habilitados:
                return False, "Sistema de correos no configurado"
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                return True, "Conexión SMTP exitosa"
                
        except Exception as e:
            return False, f"Error SMTP: {str(e)}"
    
    def enviar_correo_confirmacion(self, destinatario, nombre_estudiante, matricula, folio, programa):
        """Enviar correo de confirmación de pre-inscripción"""
        if not self.correos_habilitados:
            logger.warning("⚠️ Sistema de correos no configurado")
            return False, "Sistema de correos no configurado"
            
        try:
            # Probar conexión primero
            conexion_ok, mensaje = self.probar_conexion_smtp()
            if not conexion_ok:
                return False, mensaje
            
            # Crear mensaje
            mensaje = MIMEMultipart('alternative')
            mensaje['From'] = self.email_from
            mensaje['To'] = destinatario
            mensaje['Subject'] = f"Confirmación de Pre-Inscripción - {matricula}"
            
            # Cuerpo del correo en HTML
            cuerpo_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                    <div style="text-align: center; background-color: #2E86AB; color: white; padding: 20px; border-radius: 10px 10px 0 0;">
                        <h1>🏥 Escuela de Enfermería</h1>
                        <h2>Confirmación de Pre-Inscripción</h2>
                    </div>
                    
                    <div style="padding: 20px;">
                        <p>Estimado/a <strong>{nombre_estudiante}</strong>,</p>
                        
                        <p>Hemos recibido exitosamente tu solicitud de pre-inscripción. A continuación encontrarás los detalles de tu registro:</p>
                        
                        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <h3 style="color: #2E86AB; margin-top: 0;">📋 Datos de tu Registro</h3>
                            <p><strong>Matrícula:</strong> {matricula}</p>
                            <p><strong>Folio:</strong> {folio}</p>
                            <p><strong>Programa:</strong> {programa}</p>
                            <p><strong>Fecha de registro:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
                            <p><strong>Estatus:</strong> Pre-inscrito</p>
                        </div>
                        
                        <h3 style="color: #2E86AB;">📬 Próximos Pasos</h3>
                        <ol>
                            <li><strong>Revisión de documentos</strong> (2-3 días hábiles)</li>
                            <li><strong>Correo de confirmación</strong> con fecha de examen</li>
                            <li><strong>Examen de admisión</strong> (presencial/online)</li>
                            <li><strong>Entrevista personal</strong> (si aplica)</li>
                            <li><strong>Resultados finales</strong> (5-7 días después del examen)</li>
                        </ol>
                        
                        <div style="background-color: #e8f4f8; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <h4 style="color: #A23B72; margin-top: 0;">ℹ️ Información Importante</h4>
                            <p>Guarda esta información, ya que tu matrícula y folio serán necesarios para cualquier consulta sobre tu proceso de admisión.</p>
                        </div>
                        
                        <p>Si tienes alguna pregunta, no dudes en contactarnos:</p>
                        <ul>
                            <li>📧 Email: admisiones@escuelaenfermeria.edu.mx</li>
                            <li>📞 Teléfono: (55) 1234-5678</li>
                            <li>🕒 Horario: Lunes a Viernes de 9:00 a 18:00 hrs</li>
                        </ul>
                        
                        <p>¡Te deseamos mucho éxito en tu proceso de admisión!</p>
                        
                        <p>Atentamente,<br>
                        <strong>Departamento de Admisiones</strong><br>
                        Escuela de Enfermería<br>
                        Formando Líderes en Salud Cardiovascular</p>
                    </div>
                    
                    <div style="text-align: center; background-color: #f1f1f1; padding: 15px; border-radius: 0 0 10px 10px; font-size: 12px; color: #666;">
                        <p>Este es un correo automático, por favor no respondas a este mensaje.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Versión de texto plano
            cuerpo_texto = f"""
            Confirmación de Pre-Inscripción - Escuela de Enfermería
            
            Estimado/a {nombre_estudiante},
            
            Hemos recibido exitosamente tu solicitud de pre-inscripción.
            
            Datos de tu registro:
            - Matrícula: {matricula}
            - Folio: {folio}
            - Programa: {programa}
            - Fecha de registro: {datetime.now().strftime('%d/%m/%Y %H:%M')}
            - Estatus: Pre-inscrito
            
            Próximos pasos:
            1. Revisión de documentos (2-3 días hábiles)
            2. Correo de confirmación con fecha de examen
            3. Examen de admisión (presencial/online)
            4. Entrevista personal (si aplica)
            5. Resultados finales (5-7 días después del examen)
            
            ¡Te deseamos mucho éxito en tu proceso de admisión!
            
            Atentamente,
            Departamento de Admisiones
            Escuela de Enfermería
            """
            
            # Adjuntar ambas versiones
            parte_texto = MIMEText(cuerpo_texto, 'plain')
            parte_html = MIMEText(cuerpo_html, 'html')
            
            mensaje.attach(parte_texto)
            mensaje.attach(parte_html)
            
            # Enviar correo
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(mensaje)
            
            logger.info(f"✅ Correo enviado exitosamente a: {destinatario}")
            return True, "Correo enviado exitosamente"
            
        except smtplib.SMTPException as e:
            logger.error(f"❌ Error SMTP al enviar correo: {e}")
            return False, f"Error SMTP: {str(e)}"
        except Exception as e:
            logger.error(f"❌ Error al enviar correo: {e}")
            return False, f"Error inesperado: {str(e)}"

# =============================================================================
# SISTEMA DE GESTIÓN DE INSCRITOS - MEJORADO
# =============================================================================

class SistemaInscritos:
    """Sistema de gestión de inscritos con base de datos SQLite remota"""
    
    def __init__(self):
        # Instancias de los sistemas
        self.gestor_remoto = GestorConexionRemota()
        self.base_datos = SistemaBaseDatos()
        self.sistema_correos = SistemaCorreos()
        self.validador = ValidadorDatos()
        
        # Cargar datos iniciales
        self.inicializar_sistema()
    
    def inicializar_sistema(self):
        """Inicializar el sistema sincronizando con la base de datos remota"""
        try:
            logger.info("🚀 Inicializando sistema de inscritos...")
            
            # Verificar conectividad
            if not self.gestor_remoto.verificar_conectividad():
                logger.warning("⚠️ Sin conectividad de red")
            
            # Sincronizar base de datos
            if not self.base_datos.sincronizar_desde_remoto():
                logger.warning("⚠️ No se pudo sincronizar base de datos inicial")
            
            # Verificar sistema de correos
            if self.sistema_correos.correos_habilitados:
                conexion_ok, mensaje = self.sistema_correos.probar_conexion_smtp()
                if conexion_ok:
                    logger.info("✅ Sistema de correos operativo")
                else:
                    logger.warning(f"⚠️ Sistema de correos no operativo: {mensaje}")
            
            logger.info("✅ Sistema de inscritos inicializado")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando sistema: {e}")
    
    def generar_matricula_inscrito(self):
        """Generar matrícula única para inscrito"""
        try:
            while True:
                # Generar matrícula con formato: INS-YYYYMMDD-XXXXX
                fecha = datetime.now().strftime('%Y%m%d')
                random_num = ''.join(random.choices(string.digits, k=5))
                matricula = f"INS-{fecha}-{random_num}"
                
                # Verificar que no exista
                if not self.base_datos.obtener_inscrito_por_matricula(matricula):
                    return matricula
                    
        except Exception as e:
            logger.error(f"Error generando matrícula: {e}")
            # Generación de fallback
            return f"INS-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    def generar_folio(self):
        """Generar folio único"""
        try:
            while True:
                folio = f"FOL-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
                return folio  # Asumimos que es suficientemente único
        except:
            return f"FOL-{int(time.time())}"
    
    def guardar_documento(self, archivo, matricula, nombre_completo, tipo_documento):
        """Guardar documento en el servidor remoto"""
        try:
            if archivo is None:
                return None
            
            # Generar nombre de archivo seguro
            timestamp = datetime.now().strftime('%y%m%d%H%M%S')
            nombre_limpio = ''.join(c for c in nombre_completo if c.isalnum() or c in (' ', '-', '_')).rstrip()
            nombre_limpio = nombre_limpio.replace(' ', '_')[:30]
            tipo_limpio = tipo_documento.replace(' ', '_').upper()
            
            # Obtener extensión del archivo
            if hasattr(archivo, 'name'):
                extension = archivo.name.split('.')[-1] if '.' in archivo.name else 'pdf'
            else:
                extension = 'pdf'
            
            # Nombre final del archivo
            nombre_archivo = f"{matricula}_{nombre_limpio}_{timestamp}_{tipo_limpio}.{extension}"
            
            # Obtener contenido del archivo
            if hasattr(archivo, 'getvalue'):
                contenido = archivo.getvalue()
            elif hasattr(archivo, 'read'):
                contenido = archivo.read()
            else:
                contenido = archivo
            
            # Guardar en servidor remoto
            if self.gestor_remoto.guardar_documento_remoto(contenido, nombre_archivo):
                logger.info(f"✅ Documento guardado: {nombre_archivo}")
                return nombre_archivo
            else:
                logger.error(f"❌ Error guardando documento: {nombre_archivo}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error en guardar_documento: {e}")
            return None
    
    def registrar_inscrito(self, datos_formulario, archivos):
        """Registrar nuevo inscrito en el sistema"""
        try:
            # Validar datos del formulario
            errores = self.validar_datos_inscripcion(datos_formulario, archivos)
            if errores:
                raise ValueError("\n".join(errores))
            
            # Generar identificadores únicos
            matricula = self.generar_matricula_inscrito()
            folio = self.generar_folio()
            
            logger.info(f"📝 Registrando inscrito: {datos_formulario['nombre_completo']} - {matricula}")
            
            # Guardar documentos
            nombres_documentos = []
            documentos_guardados = 0
            
            # Mapeo de archivos a tipos de documento
            documentos_info = [
                (archivos.get('acta_nacimiento'), "ACTA_NACIMIENTO"),
                (archivos.get('curp'), "CURP"),
                (archivos.get('certificado'), "CERTIFICADO_ESTUDIOS"),
                (archivos.get('foto'), "FOTOGRAFIA")
            ]
            
            for archivo, tipo in documentos_info:
                if archivo is not None:
                    nombre_doc = self.guardar_documento(
                        archivo, matricula, 
                        datos_formulario['nombre_completo'], tipo
                    )
                    if nombre_doc:
                        nombres_documentos.append(nombre_doc)
                        documentos_guardados += 1
            
            # Preparar datos para la base de datos
            inscrito_data = {
                'matricula': matricula,
                'nombre_completo': datos_formulario['nombre_completo'],
                'email': datos_formulario['email'],
                'telefono': datos_formulario.get('telefono', ''),
                'programa_interes': datos_formulario['programa_interes'],
                'fecha_registro': datetime.now(),
                'estatus': 'Pre-inscrito',
                'folio': folio,
                'fecha_nacimiento': datos_formulario.get('fecha_nacimiento'),
                'como_se_entero': datos_formulario.get('como_se_entero', ''),
                'documentos_subidos': documentos_guardados,
                'documentos_guardados': ', '.join(nombres_documentos) if nombres_documentos else ''
            }
            
            # Guardar en base de datos
            inscrito_id = self.base_datos.agregar_inscrito(inscrito_data)
            
            if inscrito_id:
                # Enviar correo de confirmación
                correo_enviado, mensaje_correo = self.sistema_correos.enviar_correo_confirmacion(
                    destinatario=datos_formulario['email'],
                    nombre_estudiante=datos_formulario['nombre_completo'],
                    matricula=matricula,
                    folio=folio,
                    programa=datos_formulario['programa_interes']
                )
                
                if correo_enviado:
                    logger.info(f"📧 Correo enviado a: {datos_formulario['email']}")
                else:
                    logger.warning(f"⚠️ No se pudo enviar correo: {mensaje_correo}")
                
                # Retornar resultados
                return {
                    'success': True,
                    'matricula': matricula,
                    'folio': folio,
                    'email': datos_formulario['email'],
                    'nombre': datos_formulario['nombre_completo'],
                    'programa': datos_formulario['programa_interes'],
                    'documentos_subidos': documentos_guardados,
                    'correo_enviado': correo_enviado,
                    'mensaje_correo': mensaje_correo
                }
            else:
                raise Exception("Error al guardar en base de datos")
            
        except ValueError as e:
            logger.error(f"❌ Error de validación: {e}")
            return {
                'success': False,
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"❌ Error registrando inscrito: {e}")
            return {
                'success': False,
                'error': f"Error interno del sistema: {str(e)}"
            }
    
    def validar_datos_inscripcion(self, datos, archivos):
        """Validar datos del formulario de inscripción"""
        errores = []
        
        # Validar campos obligatorios
        campos_obligatorios = [
            ('nombre_completo', 'Nombre completo'),
            ('email', 'Correo electrónico'),
            ('telefono', 'Teléfono'),
            ('programa_interes', 'Programa de interés'),
            ('como_se_entero', 'Cómo se enteró')
        ]
        
        for campo, nombre in campos_obligatorios:
            if not datos.get(campo):
                errores.append(f"❌ {nombre} es obligatorio")
        
        # Validar formato de email
        if datos.get('email') and not self.validador.validar_email(datos['email']):
            errores.append("❌ Formato de email inválido")
        
        # Validar teléfono
        if datos.get('telefono') and not self.validador.validar_telefono(datos['telefono']):
            errores.append("❌ Teléfono debe tener al menos 10 dígitos")
        
        # Validar nombre completo
        if datos.get('nombre_completo') and not self.validador.validar_nombre_completo(datos['nombre_completo']):
            errores.append("❌ Nombre completo debe incluir al menos nombre y apellido")
        
        # Validar documentos obligatorios
        documentos_obligatorios = [
            ('acta_nacimiento', 'Acta de nacimiento'),
            ('curp', 'CURP'),
            ('certificado', 'Certificado de estudios')
        ]
        
        for campo, nombre in documentos_obligatorios:
            if not archivos.get(campo):
                errores.append(f"❌ {nombre} es obligatorio")
        
        return errores

# =============================================================================
# CONFIGURACIÓN Y ESTILOS DEL WEBSITE PÚBLICO
# =============================================================================

def aplicar_estilos_publicos():
    """Aplicar estilos CSS para el website público"""
    st.markdown("""
    <style>
    /* Estilos generales */
    .main-header {
        font-size: 3.5rem;
        color: #2E86AB;
        text-align: center;
        margin-bottom: 2rem;
        font-weight: bold;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }
    
    .sub-header {
        font-size: 2rem;
        color: #A23B72;
        text-align: center;
        margin-bottom: 1.5rem;
        font-weight: 600;
    }
    
    /* Tarjetas de programas */
    .programa-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 15px;
        border-left: 5px solid #2E86AB;
        margin-bottom: 1rem;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .programa-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 15px rgba(0,0,0,0.2);
    }
    
    /* Testimonios */
    .testimonio {
        background-color: #e8f4f8;
        padding: 1.5rem;
        border-radius: 15px;
        margin: 1rem 0;
        border-left: 4px solid #A23B72;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Botones */
    .stButton > button {
        background-color: #2E86AB;
        color: white;
        border: none;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        font-weight: 600;
        transition: background-color 0.3s ease;
        width: 100%;
    }
    
    .stButton > button:hover {
        background-color: #1A5A7A;
        color: white;
    }
    
    /* Formularios */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > select {
        border-radius: 8px;
        border: 1px solid #ddd;
        padding: 0.5rem;
    }
    
    /* Alertas */
    .stAlert {
        border-radius: 10px;
    }
    
    /* Footer */
    .footer {
        text-align: center;
        padding: 2rem;
        background-color: #f8f9fa;
        border-top: 1px solid #ddd;
        margin-top: 3rem;
        border-radius: 10px;
    }
    
    /* Animaciones */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .fade-in {
        animation: fadeIn 0.5s ease-out;
    }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# DATOS ESTÁTICOS DE LA INSTITUCIÓN
# =============================================================================

def obtener_programas_academicos():
    """Obtener lista de programas académicos disponibles"""
    return [
        {
            "nombre": "Especialidad en Enfermería Cardiovascular",
            "duracion": "2 años",
            "modalidad": "Presencial",
            "descripcion": "Formación especializada en el cuidado de pacientes con patologías cardiovasculares.",
            "requisitos": ["Licenciatura en Enfermería", "Cédula profesional", "2 años de experiencia"]
        },
        {
            "nombre": "Licenciatura en Enfermería",
            "duracion": "4 años",
            "modalidad": "Presencial",
            "descripcion": "Formación integral en enfermería con enfoque en cardiología.",
            "requisitos": ["Bachillerato terminado", "Promedio mínimo 8.0"]
        },
        {
            "nombre": "Diplomado de Cardiología Básica",
            "duracion": "6 meses",
            "modalidad": "Híbrida",
            "descripcion": "Actualización en fundamentos de cardiología para profesionales de la salud.",
            "requisitos": ["Título profesional en área de la salud"]
        },
        {
            "nombre": "Maestría en Ciencias Cardiológicas",
            "duracion": "2 años",
            "modalidad": "Presencial",
            "descripcion": "Formación de investigadores en el área de ciencias cardiológicas.",
            "requisitos": ["Licenciatura en áreas afines", "Promedio mínimo 8.5"]
        }
    ]

def obtener_testimonios():
    """Obtener testimonios de estudiantes y egresados"""
    return [
        {
            "nombre": "Dra. Ana Martínez",
            "programa": "Especialidad en Enfermería Cardiovascular",
            "testimonio": "La especialidad me dio las herramientas para trabajar en la unidad de cardiología del hospital más importante del país.",
            "foto": "👩‍⚕️"
        },
        {
            "nombre": "Lic. Carlos Rodríguez",
            "programa": "Licenciatura en Enfermería",
            "testimonio": "La formación con enfoque cardiológico me diferenció en el mercado laboral. ¡Altamente recomendable!",
            "foto": "👨‍⚕️"
        },
        {
            "nombre": "Dr. Miguel Torres",
            "programa": "Diplomado de Cardiología Básica",
            "testimonio": "Perfecto para actualizarse sin dejar de trabajar. Los profesores son expertos en su área.",
            "foto": "🧑‍⚕️"
        }
    ]

# =============================================================================
# SECCIONES DEL WEBSITE PÚBLICO - MEJORADAS
# =============================================================================

def mostrar_header():
    """Mostrar header del website"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="main-header fade-in">🏥 Escuela de Enfermería</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-header fade-in">Formando Líderes en Salud Cardiovascular</div>', unsafe_allow_html=True)
        st.markdown("""
        <div style="text-align: center; color: #666; margin-top: 1rem;">
            <p>📅 Inscripciones abiertas | 📚 Excelencia académica | 🏥 Vinculación hospitalaria</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")

def mostrar_hero():
    """Sección hero principal mejorada"""
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("## 🎓 Excelencia Académica en Cardiología")
        st.markdown("""
        ### **Forma parte de la institución líder en educación cardiovascular**
        
        - 👨‍⚕️ **Claustro docente** de alto nivel con especialistas certificados
        - 🏥 **Vinculación hospitalaria** con las mejores instituciones del país
        - 🔬 **Investigación** de vanguardia en ciencias cardiovasculares
        - 💼 **Bolsa de trabajo** exclusiva para egresados
        - 🌐 **Red de egresados** a nivel nacional e internacional
        - 📊 **95%** de nuestros egresados están empleados en el sector salud
        
        *Más de 40 años formando profesionales de excelencia en el cuidado cardiovascular*
        """)
        
        # Botón de inscripción con verificación del sistema
        if 'sistema_inscritos' in st.session_state:
            sistema = st.session_state.sistema_inscritos
            if sistema.gestor_remoto.config.get('host'):
                if st.button("📝 ¡Inscríbete Ahora!", key="hero_inscripcion", use_container_width=True):
                    st.session_state.mostrar_formulario = True
                    st.rerun()
            else:
                st.warning("⚠️ Sistema en modo local - Configura SSH para funcionalidad completa")
                if st.button("📝 Continuar en modo local", key="hero_inscripcion_local", use_container_width=True):
                    st.session_state.mostrar_formulario = True
                    st.rerun()
    
    with col2:
        st.info("**🏛️ Instalaciones de Vanguardia**")
        st.write("""
        ### 🔬 Laboratorios Especializados
        - Simuladores de alta fidelidad
        - Equipamiento cardiológico actualizado
        - Salas de simulación clínica
        
        ### 📚 Recursos Académicos
        - Biblioteca especializada en cardiología
        - Acceso a bases de datos científicas
        - Aulas tecnológicas inteligentes
        
        ### 🏥 Práctica Clínica
        - Rotaciones en hospitales asociados
        - Tutorías personalizadas
        - Seguimiento académico continuo
        """)

def mostrar_programas_academicos():
    """Mostrar oferta académica mejorada"""
    st.markdown('<div class="sub-header fade-in">📚 Nuestra Oferta Académica</div>', unsafe_allow_html=True)
    
    programas = obtener_programas_academicos()
    
    for i, programa in enumerate(programas):
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                st.markdown(f'<div class="programa-card fade-in">', unsafe_allow_html=True)
                st.markdown(f"### **{programa['nombre']}**")
                
                # Badges
                col_badge1, col_badge2 = st.columns(2)
                with col_badge1:
                    st.markdown(f"**⏱️ Duración:** {programa['duracion']}")
                with col_badge2:
                    st.markdown(f"**🌐 Modalidad:** {programa['modalidad']}")
                
                st.markdown(f"{programa['descripcion']}")
                
                with st.expander("📋 Ver requisitos de admisión"):
                    for requisito in programa['requisitos']:
                        st.write(f"✅ {requisito}")
                    st.markdown("---")
                    st.info("**📅 Proceso de admisión continuo**")
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col2:
                st.write("")  # Espacio
                if st.button(f"📋 Más información", key=f"info_{i}", use_container_width=True):
                    st.session_state.programa_seleccionado = programa['nombre']
                    st.session_state.mostrar_formulario = True
                    st.rerun()
            
            with col3:
                st.write("")  # Espacio
                if st.button(f"🎯 Inscribirme", key=f"inscribir_{i}", type="primary", use_container_width=True):
                    st.session_state.programa_seleccionado = programa['nombre']
                    st.session_state.mostrar_formulario = True
                    st.rerun()

def mostrar_testimonios():
    """Mostrar testimonios de estudiantes y egresados"""
    st.markdown("---")
    st.markdown('<div class="sub-header fade-in">🌟 Testimonios de Nuestra Comunidad</div>', unsafe_allow_html=True)
    
    testimonios = obtener_testimonios()
    cols = st.columns(3)
    
    for i, testimonio in enumerate(testimonios):
        with cols[i]:
            st.markdown(f'<div class="testimonio fade-in">', unsafe_allow_html=True)
            
            # Avatar y nombre
            col_avatar, col_name = st.columns([1, 3])
            with col_avatar:
                st.markdown(f"## {testimonio['foto']}")
            with col_name:
                st.markdown(f"**{testimonio['nombre']}**")
                st.markdown(f"*{testimonio['programa']}*")
            
            # Testimonio
            st.markdown(f"\"{testimonio['testimonio']}\"")
            
            # Separador
            st.markdown("---")
            
            # Estado actual
            st.caption("🏥 Actualmente trabajando en hospital especializado")
            
            st.markdown('</div>', unsafe_allow_html=True)

def mostrar_formulario_inscripcion():
    """Mostrar formulario de pre-inscripción mejorado"""
    st.markdown("---")
    
    # Verificar si el sistema está inicializado
    if 'sistema_inscritos' not in st.session_state:
        st.error("❌ El sistema no está inicializado correctamente")
        st.info("Por favor, recarga la página o contacta al administrador.")
        return
    
    sistema = st.session_state.sistema_inscritos
    
    # Título con animación
    st.markdown('<div class="sub-header fade-in">📝 Formulario de Pre-Inscripción</div>', unsafe_allow_html=True)
    
    # Información del sistema
    with st.expander("🔧 Estado del Sistema", expanded=False):
        col_status1, col_status2, col_status3 = st.columns(3)
        
        with col_status1:
            if sistema.gestor_remoto.config.get('host'):
                st.success("✅ SSH Configurado")
            else:
                st.warning("⚠️ SSH No configurado")
        
        with col_status2:
            if sistema.sistema_correos.correos_habilitados:
                st.success("✅ Correos Habilitados")
            else:
                st.warning("⚠️ Correos No configurados")
        
        with col_status3:
            st.info("💾 Base de datos remota")
    
    if 'formulario_enviado' not in st.session_state:
        st.session_state.formulario_enviado = False
    
    if not st.session_state.formulario_enviado:
        with st.form("formulario_inscripcion", clear_on_submit=True):
            st.markdown("### 👤 Información Personal")
            
            col1, col2 = st.columns(2)
            
            with col1:
                nombre_completo = st.text_input(
                    "**Nombre Completo***",
                    placeholder="Ej: María González López",
                    help="Ingresa tu nombre completo tal como aparece en documentos oficiales"
                )
                
                email = st.text_input(
                    "**Correo Electrónico***",
                    placeholder="ejemplo@email.com",
                    help="Usaremos este correo para todas las comunicaciones"
                )
                
                programa_interes = st.selectbox(
                    "**Programa de Interés***",
                    [p['nombre'] for p in obtener_programas_academicos()],
                    help="Selecciona el programa al que deseas aplicar"
                )
                
                # Mostrar información del programa seleccionado
                if programa_interes:
                    programa_info = next((p for p in obtener_programas_academicos() if p['nombre'] == programa_interes), None)
                    if programa_info:
                        with st.expander("📋 Información del programa seleccionado"):
                            st.write(f"**Duración:** {programa_info['duracion']}")
                            st.write(f"**Modalidad:** {programa_info['modalidad']}")
                            st.write(f"**Descripción:** {programa_info['descripcion']}")
            
            with col2:
                telefono = st.text_input(
                    "**Teléfono***",
                    placeholder="5512345678",
                    help="Ingresa tu número de teléfono a 10 dígitos"
                )
                
                # FECHA DE NACIMIENTO CON RANGO DESDE 1980
                fecha_actual = date.today()
                fecha_minima = date(1980, 1, 1)
                fecha_maxima = fecha_actual
                
                fecha_nacimiento = st.date_input(
                    "**Fecha de Nacimiento**",
                    min_value=fecha_minima,
                    max_value=fecha_maxima,
                    value=None,
                    format="YYYY-MM-DD",
                    help="Debes tener al menos 18 años para aplicar"
                )
                
                # Validar edad mínima
                if fecha_nacimiento:
                    edad = (fecha_actual - fecha_nacimiento).days // 365
                    if edad < 18:
                        st.warning(f"⚠️ Debes tener al menos 18 años para aplicar. Edad actual: {edad} años")
                
                # OPCIONES PARA "¿CÓMO SE ENTERÓ?"
                opciones_como_se_entero = [
                    "Redes Sociales", 
                    "Google/Buscador", 
                    "Recomendación de amigo/familiar",
                    "Recomendación de egresado",
                    "Evento o feria educativa",
                    "Publicidad en línea",
                    "Publicidad tradicional",
                    "Visita a instalaciones",
                    "Otro"
                ]
                como_se_entero = st.selectbox(
                    "**¿Cómo se enteró de nosotros?***",
                    opciones_como_se_entero,
                    help="Esta información nos ayuda a mejorar nuestra comunicación"
                )
            
            # Documentos requeridos
            st.markdown("---")
            st.markdown("### 📎 Documentos Requeridos")
            
            st.info("""
            **Instrucciones para documentos:**
            1. Todos los documentos deben estar en formato **PDF** (excepto la fotografía)
            2. Tamaño máximo por archivo: **5 MB**
            3. Nombra los archivos de forma clara (ej: acta_nacimiento.pdf)
            4. Escanea documentos en buena calidad
            """)
            
            col_doc1, col_doc2 = st.columns(2)
            
            with col_doc1:
                st.markdown("**📄 Documentos Obligatorios**")
                
                acta_nacimiento = st.file_uploader(
                    "**Acta de Nacimiento***", 
                    type=['pdf'],
                    key="acta",
                    help="Documento oficial vigente"
                )
                
                curp = st.file_uploader(
                    "**CURP***", 
                    type=['pdf'],
                    key="curp",
                    help="Clave Única de Registro de Población"
                )
                
                certificado = st.file_uploader(
                    "**Último Grado de Estudios***", 
                    type=['pdf'],
                    key="certificado",
                    help="Certificado de bachillerato, licenciatura o título"
                )
            
            with col_doc2:
                st.markdown("**🖼️ Documento Opcional**")
                
                foto = st.file_uploader(
                    "**Fotografía** (Opcional)", 
                    type=['pdf', 'jpg', 'jpeg', 'png'],
                    key="foto",
                    help="Fotografía reciente tamaño credencial (Formato: JPG, PNG o PDF)"
                )
                
                if foto:
                    # Mostrar información del archivo
                    file_size = len(foto.getvalue()) / 1024  # KB
                    if file_size > 5120:  # 5 MB
                        st.warning(f"⚠️ El archivo es muy grande ({file_size:.1f} KB). Máximo recomendado: 5 MB")
                
                st.markdown("---")
                st.markdown("**📝 Documentos Adicionales**")
                
                st.info("""
                **Nota:** Puedes subir documentos adicionales como:
                - Cédula profesional
                - Cartas de recomendación
                - Constancias de experiencia
                - Otros documentos relevantes
                
                (Puedes combinar varios documentos en un solo PDF)
                """)
            
            # Términos y condiciones
            st.markdown("---")
            st.markdown("### ✅ Términos y Condiciones")
            
            col_terms1, col_terms2 = st.columns([1, 4])
            with col_terms1:
                acepta_terminos = st.checkbox("**Acepto***")
            with col_terms2:
                st.markdown("""
                Acepto los términos y condiciones del proceso de admisión, 
                autorizo el tratamiento de mis datos personales conforme al 
                **Aviso de Privacidad** y confirmo que la información proporcionada es verídica.
                """)
            
            # Botón de envío
            st.markdown("---")
            col_submit1, col_submit2, col_submit3 = st.columns([1, 2, 1])
            with col_submit2:
                enviado = st.form_submit_button(
                    "🚀 Enviar Solicitud de Admisión", 
                    use_container_width=True,
                    type="primary"
                )
            
            if enviado:
                # Mostrar progreso
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Validar campos obligatorios
                status_text.text("🔍 Validando información...")
                progress_bar.progress(10)
                
                if not all([nombre_completo, email, telefono, programa_interes, acepta_terminos, como_se_entero]):
                    status_text.text("❌ Validación fallida")
                    st.error("Por favor completa todos los campos obligatorios (*)")
                    return
                
                # Validar que se seleccionó una opción en "¿Cómo se enteró?"
                if not como_se_entero:
                    st.error("❌ Por favor selecciona cómo te enteraste de nosotros")
                    return
                
                # Validar documentos requeridos
                status_text.text("📄 Verificando documentos...")
                progress_bar.progress(30)
                
                documentos_requeridos = [acta_nacimiento, curp, certificado]
                nombres_docs = ["Acta de Nacimiento", "CURP", "Certificado de Estudios"]
                docs_faltantes = [nombres_docs[i] for i, doc in enumerate(documentos_requeridos) if doc is None]
                
                if docs_faltantes:
                    st.error(f"❌ Faltan los siguientes documentos obligatorios: {', '.join(docs_faltantes)}")
                    return
                
                # Preparar datos del formulario
                status_text.text("📦 Preparando datos...")
                progress_bar.progress(50)
                
                datos_formulario = {
                    'nombre_completo': nombre_completo,
                    'email': email,
                    'telefono': telefono,
                    'programa_interes': programa_interes,
                    'fecha_nacimiento': fecha_nacimiento,
                    'como_se_entero': como_se_entero
                }
                
                archivos = {
                    'acta_nacimiento': acta_nacimiento,
                    'curp': curp,
                    'certificado': certificado,
                    'foto': foto
                }
                
                # Registrar inscrito
                status_text.text("💾 Guardando información...")
                progress_bar.progress(70)
                
                resultado = sistema.registrar_inscrito(datos_formulario, archivos)
                
                if resultado['success']:
                    status_text.text("✅ Proceso completado")
                    progress_bar.progress(100)
                    
                    st.session_state.formulario_enviado = True
                    st.session_state.datos_exitosos = {
                        'folio': resultado['folio'],
                        'matricula': resultado['matricula'],
                        'email': resultado['email'],
                        'nombre': resultado['nombre'],
                        'programa': resultado['programa'],
                        'documentos': resultado['documentos_subidos'],
                        'correo_enviado': resultado['correo_enviado'],
                        'mensaje_correo': resultado.get('mensaje_correo', '')
                    }
                    
                    # Limpiar el formulario visualmente
                    st.rerun()
                else:
                    status_text.text("❌ Error en el proceso")
                    st.error(f"Error al registrar: {resultado.get('error', 'Error desconocido')}")
    
    else:
        # Mostrar resultados exitosos
        datos = st.session_state.datos_exitosos
        
        st.success("🎉 ¡Solicitud enviada exitosamente!")
        
        # Animación de celebración
        st.balloons()
        
        # Panel de resultados
        st.markdown("### 📋 Resumen de tu Solicitud")
        
        col_res1, col_res2 = st.columns(2)
        
        with col_res1:
            st.info(f"**📋 Folio de solicitud:**\n## {datos['folio']}")
            st.info(f"**🎓 Matrícula asignada:**\n## {datos['matricula']}")
            st.info(f"**📧 Email de contacto:**\n{datos['email']}")
        
        with col_res2:
            st.info(f"**👤 Nombre registrado:**\n{datos['nombre']}")
            st.info(f"**🎯 Programa seleccionado:**\n{datos['programa']}")
            st.info(f"**📎 Documentos subidos:**\n{datos['documentos']} de 4")
        
        # Estado del correo
        st.markdown("---")
        st.markdown("### 📬 Estado de la Confirmación")
        
        if datos['correo_enviado']:
            st.success("✅ Se ha enviado un correo de confirmación a tu dirección de email.")
            st.info("**Revisa tu bandeja de entrada (y carpeta de spam/spam).**")
        else:
            st.warning(f"⚠️ No se pudo enviar el correo de confirmación: {datos['mensaje_correo']}")
            st.info("""
            **Guarda esta información:** Necesitarás tu matrícula y folio para cualquier consulta.
            
            **Contacto alternativo:**
            - 📧 Email: admisiones@escuelaenfermeria.edu.mx
            - 📞 Teléfono: (55) 1234-5678
            """)
        
        # Próximos pasos
        st.markdown("---")
        st.markdown("### 📅 Próximos Pasos en tu Proceso de Admisión")
        
        pasos = [
            {
                "paso": 1,
                "titulo": "Revisión de documentos",
                "descripcion": "Nuestro equipo revisará tus documentos (2-3 días hábiles)",
                "icono": "🔍"
            },
            {
                "paso": 2,
                "titulo": "Correo de confirmación",
                "descripcion": "Recibirás un correo con la fecha y hora de tu examen de admisión",
                "icono": "📧"
            },
            {
                "paso": 3,
                "titulo": "Examen de admisión",
                "descripcion": "Presentarás el examen (modalidad presencial u online)",
                "icono": "📝"
            },
            {
                "paso": 4,
                "titulo": "Entrevista personal",
                "descripcion": "Si tu examen es satisfactorio, serás citado a entrevista",
                "icono": "💬"
            },
            {
                "paso": 5,
                "titulo": "Resultados finales",
                "descripcion": "Publicación de resultados (5-7 días después del examen)",
                "icono": "🏆"
            }
        ]
        
        for paso in pasos:
            with st.container():
                col_paso1, col_paso2 = st.columns([1, 4])
                with col_paso1:
                    st.markdown(f"### {paso['icono']}")
                with col_paso2:
                    st.markdown(f"**Paso {paso['paso']}: {paso['titulo']}**")
                    st.caption(paso['descripcion'])
                st.markdown("---")
        
        # Acciones finales
        st.markdown("### 🔄 Otras Acciones")
        
        col_acc1, col_acc2, col_acc3 = st.columns(3)
        
        with col_acc2:
            if st.button("📝 Realizar otra pre-inscripción", use_container_width=True):
                st.session_state.formulario_enviado = False
                st.session_state.mostrar_formulario = False
                st.session_state.datos_exitosos = None
                st.rerun()
        
        with col_acc3:
            if st.button("🏠 Volver al inicio", use_container_width=True):
                st.session_state.formulario_enviado = False
                st.session_state.mostrar_formulario = False
                st.session_state.datos_exitosos = None
                st.rerun()

def mostrar_contacto():
    """Mostrar información de contacto mejorada"""
    st.markdown("---")
    st.markdown('<div class="sub-header fade-in">📞 Información de Contacto</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 🏛️ Dirección y Ubicación")
        st.markdown("""
        **Campus Principal**  
        Av. Insurgentes Sur 1234  
        Col. Nápoles  
        Ciudad de México, CDMX  
        C.P. 03810
        
        **📍 Cómo llegar:**
        - Metro: Estación Mixcoac (Línea 12)
        - Metrobús: Estación Parque Lira
        - Estacionamiento disponible
        
        **🕒 Horario de oficina:**  
        Lunes a Viernes: 8:00 - 20:00  
        Sábados: 9:00 - 14:00
        """)
        
        # Mapa de ubicación (placeholder)
        st.info("🗺️ [Ver en Google Maps](https://maps.google.com)")
    
    with col2:
        st.markdown("### 📱 Contacto Directo")
        st.markdown("""
        **Admisiones y Informes:**
        - 📞 Teléfono: **(55) 1234-5678**
        - 📱 WhatsApp: **(55) 8765-4321**
        - 📧 Email: **admisiones@escuelaenfermeria.edu.mx**
        
        **Atención a alumnos:**
        - 📧 Email: alumnos@escuelaenfermeria.edu.mx
        - 📞 Teléfono: (55) 1234-5679
        
        **Información académica:**
        - 📧 Email: academico@escuelaenfermeria.edu.mx
        - 📞 Teléfono: (55) 1234-5680
        
        **📞 Línea de emergencias:** (55) 1234-9999
        """)
        
        # Botón de contacto rápido
        if st.button("📧 Enviar mensaje rápido", use_container_width=True):
            st.info("Redirigiendo al formulario de contacto...")
    
    with col3:
        st.markdown("### 🕒 Horarios y Atención")
        st.markdown("""
        **Atención a aspirantes:**  
        📅 **Lunes a Viernes:** 9:00 - 18:00  
        📅 **Sábados:** 9:00 - 13:00  
        
        **Proceso de admisión:**  
        ✅ **Abierto todo el año**
        
        **Visitas guiadas:**  
        🗓️ **Miércoles y Viernes:** 10:00 y 16:00  
        📞 **Reserva previa requerida**
        
        **Períodos de inscripción:**
        - 🎓 **Invierno:** Enero - Marzo
        - 🎓 **Verano:** Mayo - Julio
        - 🎓 **Otoño:** Septiembre - Noviembre
        """)
        
        # Calendario de próximos eventos
        with st.expander("📅 Próximos eventos"):
            eventos = [
                {"fecha": "15 Ene", "evento": "Feria de carreras de salud"},
                {"fecha": "30 Ene", "evento": "Examen de admisión"},
                {"fecha": "10 Feb", "evento": "Inicio de clases invierno"},
                {"fecha": "15 Mar", "evento": "Día de puertas abiertas"}
            ]
            for evento in eventos:
                st.write(f"**{evento['fecha']}:** {evento['evento']}")

def mostrar_footer():
    """Mostrar footer del website"""
    st.markdown("---")
    
    # Sección principal del footer
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("### 🏥 Institución")
        st.markdown("""
        - Nuestra historia
        - Misión y visión
        - Directiva y autoridades
        - Instalaciones
        - Reconocimientos y acreditaciones
        - Transparencia
        """)
    
    with col2:
        st.markdown("### 📚 Oferta Académica")
        st.markdown("""
        - Licenciaturas
        - Especialidades
        - Maestrías
        - Doctorados
        - Diplomados
        - Cursos y talleres
        - Educación continua
        """)
    
    with col3:
        st.markdown("### 📞 Contacto y Ayuda")
        st.markdown("""
        - Preguntas frecuentes (FAQ)
        - Solicitud de informes
        - Visitas guiadas
        - Bolsa de trabajo
        - Biblioteca digital
        - Plataforma virtual
        - Portal del estudiante
        """)
    
    with col4:
        st.markdown("### 🔗 Conéctate con Nosotros")
        st.markdown("""
        - 📘 Facebook
        - 🐦 Twitter / X
        - 📸 Instagram
        - 💼 LinkedIn
        - ▶️ YouTube
        - 📧 Newsletter
        - 📱 App móvil
        """)
    
    # Línea separadora
    st.markdown("---")
    
    # Información legal y de copyright
    col_legal1, col_legal2, col_legal3 = st.columns([2, 1, 2])
    
    with col_legal1:
        st.markdown("""
        **Aviso de privacidad** | **Términos y condiciones** | **Mapa del sitio**
        """)
    
    with col_legal2:
        st.markdown("<center>🏥</center>", unsafe_allow_html=True)
    
    with col_legal3:
        st.markdown("""
        **Accesibilidad** | **Sostenibilidad** | **Ética y cumplimiento**
        """)
    
    # Copyright
    st.markdown("<center>© 2024 Escuela de Enfermería Especializada en Cardiología. Todos los derechos reservados.</center>", unsafe_allow_html=True)
    
    # Información adicional
    st.markdown("<center><small>Este sitio está protegido por reCAPTCHA y se aplican la Política de Privacidad y los Términos de Servicio de Google.</small></center>", unsafe_allow_html=True)

# =============================================================================
# APLICACIÓN PRINCIPAL - MEJORADA
# =============================================================================

def main():
    """Función principal del website público"""
    
    # Aplicar estilos
    aplicar_estilos_publicos()
    
    # Inicializar sistema de inscritos (una sola vez)
    if 'sistema_inscritos' not in st.session_state:
        with st.spinner("🚀 Inicializando sistema..."):
            st.session_state.sistema_inscritos = SistemaInscritos()
    
    # Inicializar variables de sesión
    if 'mostrar_formulario' not in st.session_state:
        st.session_state.mostrar_formulario = False
    
    # Mostrar header
    mostrar_header()
    
    # Barra lateral con información del sistema
    with st.sidebar:
        st.markdown("### 🔧 Estado del Sistema")
        
        sistema = st.session_state.sistema_inscritos
        
        # Información de conexión SSH
        if sistema.gestor_remoto.config.get('host'):
            st.success("✅ Sistema Remoto Configurado")
            st.caption(f"🌐 Servidor: {sistema.gestor_remoto.config['host']}")
        else:
            st.warning("⚠️ Modo Local")
            st.caption("Configura SSH para sincronización remota")
        
        # Información de correos
        if sistema.sistema_correos.correos_habilitados:
            st.success("✅ Correos Configurados")
        else:
            st.warning("⚠️ Correos No Configurados")
        
        # Botón de diagnóstico
        if st.button("🩺 Diagnóstico del Sistema", use_container_width=True):
            with st.expander("📊 Resultados del Diagnóstico"):
                # Prueba de conexión SSH
                if sistema.gestor_remoto.config.get('host'):
                    st.write("**SSH:**")
                    if sistema.gestor_remoto.verificar_conectividad():
                        st.success("✅ Conectividad de red OK")
                    else:
                        st.error("❌ Sin conectividad de red")
                
                # Prueba de correos
                st.write("**Correos:**")
                if sistema.sistema_correos.correos_habilitados:
                    conexion_ok, mensaje = sistema.sistema_correos.probar_conexion_smtp()
                    if conexion_ok:
                        st.success(f"✅ {mensaje}")
                    else:
                        st.error(f"❌ {mensaje}")
                else:
                    st.warning("⚠️ No configurado")
                
                # Estado de base de datos
                st.write("**Base de Datos:**")
                try:
                    df = sistema.base_datos.obtener_inscritos()
                    st.success(f"✅ Conectada ({len(df)} inscritos)")
                except:
                    st.error("❌ Error de conexión")
        
        st.markdown("---")
        st.markdown("### 📊 Estadísticas")
        
        try:
            df_inscritos = sistema.base_datos.obtener_inscritos()
            total_inscritos = len(df_inscritos)
            st.metric("Total Inscritos", total_inscritos)
            
            if total_inscritos > 0:
                # Inscritos por programa
                programas = df_inscritos['programa_interes'].value_counts().head(3)
                st.caption("**Top 3 Programas:**")
                for programa, count in programas.items():
                    st.caption(f"{programa[:20]}...: {count}")
        except:
            st.caption("Estadísticas no disponibles")
        
        st.markdown("---")
        st.markdown("### 🆘 Ayuda y Soporte")
        
        st.info("""
        **¿Necesitas ayuda?**
        
        📞 **Teléfono:** (55) 1234-5678  
        📧 **Email:** soporte@escuelaenfermeria.edu.mx  
        🕒 **Horario:** 9:00 - 18:00 hrs
        
        **Problemas comunes:**
        - Error al subir documentos
        - No recibí correo de confirmación
        - Error en el formulario
        """)
        
        if st.button("📞 Contactar Soporte", use_container_width=True):
            st.session_state.mostrar_formulario = True
    
    # Navegación principal
    if not st.session_state.mostrar_formulario:
        # Página principal
        mostrar_hero()
        mostrar_programas_academicos()
        mostrar_testimonios()
        mostrar_contacto()
    else:
        # Formulario de inscripción
        mostrar_formulario_inscripcion()
        mostrar_contacto()
    
    # Mostrar footer
    mostrar_footer()
    
    # Script para analytics (opcional)
    st.markdown("""
    <script>
    // Script para seguimiento básico
    document.addEventListener('DOMContentLoaded', function() {
        console.log('Página cargada - Sistema de Preinscripción');
        
        // Track form interactions
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            form.addEventListener('submit', function() {
                console.log('Formulario enviado');
            });
        });
    });
    </script>
    """, unsafe_allow_html=True)

# =============================================================================
# MANEJO DE ERRORES GLOBAL
# =============================================================================

def manejo_errores_global(func):
    """Decorador para manejo global de errores"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"❌ Error crítico en la aplicación: {e}")
            
            # Mostrar página de error amigable
            st.error("""
            ## 🚨 Error del Sistema
            
            Lo sentimos, ha ocurrido un error inesperado en el sistema.
            
            **Por favor intenta:**
            1. 📍 Recargar la página
            2. 🕒 Esperar unos minutos y volver a intentar
            3. 📞 Contactar a soporte si el problema persiste
            
            **Información técnica:**
            ```python
            Error: {}
            ```
            
            **Estado del sistema:**
            - ✅ Aplicación cargada
            - ⚠️ Error en ejecución
            - 🔧 Contacta a soporte técnico
            """.format(str(e)))
            
            # Botón para recargar
            if st.button("🔄 Recargar Aplicación", type="primary"):
                st.rerun()
            
            return None
    return wrapper

# =============================================================================
# EJECUCIÓN DE LA APLICACIÓN CON MANEJO DE ERRORES
# =============================================================================

@manejo_errores_global
def ejecutar_aplicacion():
    """Ejecutar la aplicación con manejo de errores"""
    main()

if __name__ == "__main__":
    # Banner informativo
    st.info("""
    🏥 **SISTEMA DE PRE-INSCRIPCIÓN - ESCUELA DE ENFERMERÍA ESPECIALIZADA**
    
    **Características implementadas:**
    ✅ Sistema de base de datos SQLite remota via SSH
    ✅ Envío de correos electrónicos con confirmación automática
    ✅ Validación de datos en tiempo real
    ✅ Subida segura de documentos al servidor remoto
    ✅ Generación automática de matrículas y folios únicos
    ✅ Sistema de logging para diagnóstico
    ✅ Interfaz responsive y amigable
    
    **Para comenzar:**
    1. Completa el formulario de pre-inscripción
    2. Sube tus documentos requeridos
    3. Recibe tu matrícula y folio únicos
    4. Obtén confirmación por correo electrónico
    """)
    
    # Ejecutar aplicación principal
    ejecutar_aplicacion()
