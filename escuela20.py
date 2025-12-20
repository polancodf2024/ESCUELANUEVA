"""
escuela20.py - Sistema de Gestión Escuela de Enfermería
VERSIÓN CONEXIÓN DIRECTA A SERVIDOR REMOTO VIA SSH
Base de datos SQLite remota - VERSIÓN COMPLETA Y CORREGIDA
CON MODO LOCAL COMO FALLBACK Y CREACIÓN AUTOMÁTICA DE TABLAS
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

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuración de página
st.set_page_config(
    page_title="Sistema Escuela Enfermería - Modo Supervisión",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# CONFIGURACIÓN SSH Y SISTEMA DE CONEXIÓN REMOTA - MEJORADA CON FALLBACK
# =============================================================================

class GestorConexionRemota:
    """Gestor de conexión SSH al servidor remoto para acceso a base de datos SQLite
    CON MODO LOCAL COMO FALLBACK"""
    
    def __init__(self):
        self.ssh = None
        self.sftp = None
        self.config = self._cargar_configuracion_ssh()
        
        # Determinar modo de operación
        if self.config and all(key in self.config for key in ['remote_host', 'remote_user', 'remote_password']):
            self.modo_remoto = True
            self.db_path_remoto = "/home/POLANCO6/ESCUELA/datos/escuela.db"
            logger.info("🔗 Modo remoto SSH activado")
        else:
            self.modo_remoto = False
            # Usar base de datos local si no hay SSH
            self.db_local_path = "/mount/src/escuelanueva/datos/escuela.db"
            logger.info("💻 Modo local activado (sin SSH)")
        
        self.temp_db_path = None
        self.conexion_local = None
    
    def _cargar_configuracion_ssh(self):
        """Cargar configuración SSH desde secrets.toml - CON MEJOR MANEJO DE ERRORES"""
        try:
            # Verificar si st.secrets está disponible
            if not hasattr(st, 'secrets'):
                logger.warning("st.secrets no está disponible")
                return {}
            
            # Intentar cargar configuración
            config = {
                'remote_host': st.secrets["remote_host"],
                'remote_port': int(st.secrets.get("remote_port", 22)),  # Valor por defecto
                'remote_user': st.secrets["remote_user"],
                'remote_password': st.secrets["remote_password"]
            }
            
            # Verificar que no estén vacíos
            for key, value in config.items():
                if not value:
                    logger.warning(f"Configuración SSH: {key} está vacío")
                    return {}
            
            logger.info(f"✅ Configuración SSH cargada para {config['remote_host']}")
            return config
            
        except KeyError as e:
            # Error específico de clave faltante
            missing_key = str(e).replace("'", "")
            logger.warning(f"⚠️ Clave faltante en secrets.toml: {missing_key}")
            return {}
            
        except Exception as e:
            # Error general
            logger.warning(f"⚠️ Error cargando configuración SSH: {e}")
            return {}
    
    def conectar_ssh(self):
        """Establecer conexión SSH con el servidor remoto"""
        try:
            if not self.config or not self.modo_remoto:
                logger.warning("Modo remoto no disponible")
                return False
            
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(
                hostname=self.config['remote_host'],
                port=self.config['remote_port'],
                username=self.config['remote_user'],
                password=self.config['remote_password'],
                timeout=30,
                banner_timeout=30
            )
            self.sftp = self.ssh.open_sftp()
            logger.info(f"✅ Conexión SSH establecida a {self.config['remote_host']}")
            return True
            
        except paramiko.AuthenticationException:
            logger.error("❌ Error de autenticación SSH. Verifique usuario/contraseña")
            return False
        except paramiko.SSHException as e:
            logger.error(f"❌ Error SSH: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error de conexión SSH: {e}")
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
        """Descargar base de datos SQLite del servidor remoto - CON MANEJO MEJORADO"""
        try:
            # Si estamos en modo local, usar base de datos local
            if not self.modo_remoto:
                logger.info("📁 Usando base de datos local (modo sin SSH)")
                return self._usar_db_local()
            
            # Modo remoto: conectar SSH
            if not self.conectar_ssh():
                logger.warning("⚠️ Falló conexión SSH, usando modo local")
                return self._usar_db_local()
            
            # Crear archivo temporal local
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.temp_db_path = os.path.join(temp_dir, f"escuela_temp_{timestamp}.db")
            
            # Intentar descargar archivo remoto
            try:
                logger.info(f"📥 Descargando base de datos desde: {self.db_path_remoto}")
                self.sftp.get(self.db_path_remoto, self.temp_db_path)
                
                # Verificar que el archivo se descargó correctamente
                if os.path.exists(self.temp_db_path) and os.path.getsize(self.temp_db_path) > 0:
                    file_size = os.path.getsize(self.temp_db_path)
                    logger.info(f"✅ Base de datos descargada exitosamente: {self.temp_db_path} ({file_size} bytes)")
                    return self.temp_db_path
                else:
                    logger.warning("⚠️ Archivo descargado vacío o corrupto")
                    return self._crear_nueva_db_local()
                    
            except FileNotFoundError:
                logger.warning(f"⚠️ Base de datos remota no encontrada: {self.db_path_remoto}")
                return self._crear_nueva_db_local()
                
            except Exception as e:
                logger.error(f"❌ Error descargando archivo: {e}")
                return self._crear_nueva_db_local()
                
        except Exception as e:
            logger.error(f"❌ Error en descargar_db_remota: {e}")
            return self._crear_nueva_db_local()
        finally:
            if self.modo_remoto:
                self.desconectar_ssh()
    
    def _usar_db_local(self):
        """Usar base de datos local si existe, o crear una nueva"""
        try:
            # Si ya tenemos una base de datos temporal, usarla
            if self.temp_db_path and os.path.exists(self.temp_db_path):
                logger.info(f"📁 Usando base de datos temporal existente: {self.temp_db_path}")
                return self.temp_db_path
            
            # Verificar si existe base de datos local en ruta estándar
            if os.path.exists(self.db_local_path):
                logger.info(f"📁 Usando base de datos local existente: {self.db_local_path}")
                return self.db_local_path
            else:
                # Crear directorio si no existe
                os.makedirs(os.path.dirname(self.db_local_path), exist_ok=True)
                logger.info(f"📁 Creando nueva base de datos local: {self.db_local_path}")
                return self._crear_nueva_db_local()
        except Exception as e:
            logger.error(f"❌ Error usando base de datos local: {e}")
            return self._crear_nueva_db_local()
    
    def _crear_nueva_db_local(self):
        """Crear una nueva base de datos SQLite local"""
        try:
            # Crear archivo temporal para la nueva base de datos
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.temp_db_path = os.path.join(temp_dir, f"escuela_nueva_{timestamp}.db")
            
            logger.info(f"📝 Creando nueva base de datos en: {self.temp_db_path}")
            
            # Inicializar la base de datos inmediatamente
            self._inicializar_db(self.temp_db_path)
            
            return self.temp_db_path
            
        except Exception as e:
            logger.error(f"❌ Error creando nueva base de datos: {e}")
            
            # Último intento: usar un archivo en directorio actual
            try:
                self.temp_db_path = "datos/escuela_temp.db"
                os.makedirs("datos", exist_ok=True)
                self._inicializar_db(self.temp_db_path)
                return self.temp_db_path
            except Exception as e2:
                logger.critical(f"❌ No se pudo crear base de datos: {e2}")
                return None
    
    def _inicializar_db(self, db_path):
        """Inicializar estructura de base de datos en una ruta específica"""
        try:
            logger.info(f"📝 Inicializando estructura en: {db_path}")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Tabla de usuarios - COMPATIBLE CON ESCUELA10
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
            
            # Tabla de inscritos - COMPATIBLE CON ESCUELA10
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
            
            # Tabla de estudiantes - COMPATIBLE CON ESCUELA10
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
            
            # Tabla de egresados - COMPATIBLE CON ESCUELA10
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
            
            # Tabla de contratados - COMPATIBLE CON ESCUELA10
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
            
            # Tabla de bitácora - COMPATIBLE CON ESCUELA10
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
            
            # Tabla de documentos
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
            
            # Tabla para programas educativos
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
            
            # Índices para rendimiento
            indices = [
                ('idx_usuarios_usuario', 'usuarios(usuario)'),
                ('idx_usuarios_matricula', 'usuarios(matricula)'),
                ('idx_inscritos_matricula', 'inscritos(matricula)'),
                ('idx_estudiantes_matricula', 'estudiantes(matricula)'),
                ('idx_egresados_matricula', 'egresados(matricula)'),
                ('idx_contratados_matricula', 'contratados(matricula)'),
                ('idx_documentos_matricula', 'documentos(matricula)')
            ]
            
            for nombre_idx, definicion in indices:
                try:
                    cursor.execute(f'CREATE INDEX IF NOT EXISTS {nombre_idx} ON {definicion}')
                except Exception as e:
                    logger.warning(f"⚠️ Error creando índice {nombre_idx}: {e}")
            
            # Verificar si existe usuario admin
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE usuario = 'admin'")
            if cursor.fetchone()[0] == 0:
                # Insertar usuario administrador por defecto
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
                logger.info("✅ Usuario administrador por defecto creado")
            
            # Crear algunos programas de ejemplo
            cursor.execute("SELECT COUNT(*) FROM programas")
            if cursor.fetchone()[0] == 0:
                programas_ejemplo = [
                    ('ENF-001', 'Enfermería General', 'Programa de enfermería general', 36, 25000.00, 'Presencial'),
                    ('ENF-002', 'Enfermería Pediátrica', 'Especialidad en enfermería pediátrica', 24, 30000.00, 'Presencial'),
                    ('ENF-003', 'Enfermería Geriátrica', 'Especialidad en cuidado geriátrico', 24, 28000.00, 'Mixta'),
                ]
                
                for programa in programas_ejemplo:
                    cursor.execute('''
                        INSERT INTO programas (codigo, nombre, descripcion, duracion_meses, costo, modalidad)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', programa)
                
                logger.info("✅ Programas de ejemplo creados")
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Estructura de base de datos inicializada en {db_path}")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando base de datos en {db_path}: {e}")
            raise
    
    def subir_db_local(self, ruta_local):
        """Subir base de datos local al servidor remoto (sobreescribir)"""
        try:
            if not self.modo_remoto:
                logger.info("📤 Modo local: no se sube a servidor remoto")
                return True
            
            if not self.conectar_ssh():
                return False
            
            # Crear backup de la base de datos remota antes de sobreescribir
            try:
                backup_path = f"{self.db_path_remoto}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
            if self.modo_remoto:
                self.desconectar_ssh()
    
    def ejecutar_comando_remoto(self, comando):
        """Ejecutar comando en el servidor remoto"""
        try:
            if not self.modo_remoto or not self.conectar_ssh():
                return None
            
            stdin, stdout, stderr = self.ssh.exec_command(comando)
            salida = stdout.read().decode()
            error = stderr.read().decode()
            
            if error:
                logger.warning(f"⚠️ Error ejecutando comando remoto: {error}")
            
            return salida
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando comando remoto: {e}")
            return None
        finally:
            if self.modo_remoto:
                self.desconectar_ssh()
    
    def verificar_conexion(self):
        """Verificar que la conexión SSH funcione"""
        try:
            if not self.modo_remoto:
                return False, "❌ Modo local activado (sin SSH)"
            
            if self.conectar_ssh():
                self.desconectar_ssh()
                return True, f"✅ Conexión SSH establecida a {self.config['remote_host']}"
            else:
                return False, "❌ No se pudo establecer conexión SSH"
        except Exception as e:
            return False, f"❌ Error: {e}"

# Instancia global del gestor de conexión remota
gestor_remoto = GestorConexionRemota()

# =============================================================================
# SISTEMA DE BASE DE DATOS SQLITE REMOTA - COMPLETO CON FALLBACK
# =============================================================================

class SistemaBaseDatosRemota:
    """Sistema de base de datos SQLite con sincronización remota via SSH
    Y modo local como fallback"""
    
    def __init__(self):
        self.gestor = gestor_remoto
        self.db_local_temp = None
        self.conexion_actual = None
        self.ultima_sincronizacion = None
        self.estructura_inicializada = False
        
    def sincronizar_desde_remoto(self):
        """Sincronizar base de datos desde el servidor remoto o crear local"""
        try:
            # 1. Descargar base de datos remota o crear local
            self.db_local_temp = self.gestor.descargar_db_remota()
            
            if not self.db_local_temp:
                st.error("❌ No se pudo obtener base de datos")
                return False
            
            # 2. Verificar que el archivo existe
            if not os.path.exists(self.db_local_temp):
                logger.error(f"❌ Archivo de base de datos no existe: {self.db_local_temp}")
                return False
            
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
                st.warning("⚠️ La base de datos está vacía o corrupta. Se inicializará estructura.")
                self._inicializar_estructura_db()
            
            self.ultima_sincronizacion = datetime.now()
            logger.info(f"✅ Sincronización exitosa: {self.db_local_temp}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en sincronización: {e}")
            st.error(f"❌ Error sincronizando: {e}")
            return False
    
    def _inicializar_estructura_db(self):
        """Inicializar estructura de la base de datos"""
        try:
            if not self.db_local_temp:
                logger.error("❌ No hay ruta de base de datos para inicializar")
                return
            
            conn = sqlite3.connect(self.db_local_temp)
            cursor = conn.cursor()
            
            # Tabla de usuarios - COMPATIBLE CON ESCUELA10
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
            
            # Tabla de inscritos - COMPATIBLE CON ESCUELA10
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
            
            # Tabla de estudiantes - COMPATIBLE CON ESCUELA10
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
            
            # Tabla de egresados - COMPATIBLE CON ESCUELA10
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
            
            # Tabla de contratados - COMPATIBLE CON ESCUELA10
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
            
            # Tabla de bitácora - COMPATIBLE CON ESCUELA10
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
            
            # Tabla de documentos
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
            
            # Tabla para programas educativos
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
            
            # Índices para rendimiento
            indices = [
                ('idx_usuarios_usuario', 'usuarios(usuario)'),
                ('idx_usuarios_matricula', 'usuarios(matricula)'),
                ('idx_inscritos_matricula', 'inscritos(matricula)'),
                ('idx_estudiantes_matricula', 'estudiantes(matricula)'),
                ('idx_egresados_matricula', 'egresados(matricula)'),
                ('idx_contratados_matricula', 'contratados(matricula)'),
                ('idx_documentos_matricula', 'documentos(matricula)')
            ]
            
            for nombre_idx, definicion in indices:
                try:
                    cursor.execute(f'CREATE INDEX IF NOT EXISTS {nombre_idx} ON {definicion}')
                except Exception as e:
                    logger.warning(f"⚠️ Error creando índice {nombre_idx}: {e}")
            
            # Verificar si existe usuario admin
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE usuario = 'admin'")
            if cursor.fetchone()[0] == 0:
                # Insertar usuario administrador por defecto
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
                logger.info("✅ Usuario administrador por defecto creado")
            
            # Crear algunos programas de ejemplo
            cursor.execute("SELECT COUNT(*) FROM programas")
            if cursor.fetchone()[0] == 0:
                programas_ejemplo = [
                    ('ENF-001', 'Enfermería General', 'Programa de enfermería general', 36, 25000.00, 'Presencial'),
                    ('ENF-002', 'Enfermería Pediátrica', 'Especialidad en enfermería pediátrica', 24, 30000.00, 'Presencial'),
                    ('ENF-003', 'Enfermería Geriátrica', 'Especialidad en cuidado geriátrico', 24, 28000.00, 'Mixta'),
                ]
                
                for programa in programas_ejemplo:
                    cursor.execute('''
                        INSERT INTO programas (codigo, nombre, descripcion, duracion_meses, costo, modalidad)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', programa)
                
                logger.info("✅ Programas de ejemplo creados")
            
            conn.commit()
            conn.close()
            logger.info("✅ Estructura de base de datos inicializada")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura: {e}")
            # Intentar crear una base de datos completamente nueva
            self._crear_nueva_db()
    
    def _crear_nueva_db(self):
        """Crear una nueva base de datos si no existe"""
        try:
            # Obtener nueva ruta del gestor
            self.db_local_temp = self.gestor._crear_nueva_db_local()
            
            if self.db_local_temp:
                logger.info(f"✅ Nueva base de datos creada: {self.db_local_temp}")
                return True
            else:
                logger.error("❌ No se pudo crear nueva base de datos")
                return False
        except Exception as e:
            logger.error(f"❌ Error creando nueva base de datos: {e}")
            return False
    
    def sincronizar_hacia_remoto(self):
        """Sincronizar base de datos local hacia el servidor remoto"""
        try:
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                st.error("❌ No hay base de datos local para subir")
                return False
            
            # Subir al servidor remoto (si estamos en modo remoto)
            if self.gestor.modo_remoto:
                exito = self.gestor.subir_db_local(self.db_local_temp)
                
                if exito:
                    self.ultima_sincronizacion = datetime.now()
                    logger.info("✅ Cambios subidos exitosamente al servidor")
                    return True
                else:
                    return False
            else:
                # En modo local, solo actualizamos la marca de tiempo
                self.ultima_sincronizacion = datetime.now()
                logger.info("💻 Modo local: cambios guardados localmente")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error subiendo cambios: {e}")
            st.error(f"❌ Error subiendo cambios: {e}")
            return False
    
    @contextmanager
    def get_connection(self):
        """Context manager para conexiones a la base de datos"""
        conn = None
        try:
            # Asegurar que tenemos la base de datos más reciente
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                self.sincronizar_desde_remoto()
            
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
            st.error(f"❌ Error en base de datos: {e}")
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
        """Verificar contraseña"""
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
    # MÉTODOS DE CONSULTA - COMPLETOS
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
    
    def obtener_programas(self):
        """Obtener todos los programas"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM programas ORDER BY nombre"
                df = pd.read_sql_query(query, conn)
                logger.info(f"Obtenidos {len(df)} programas")
                return df
        except Exception as e:
            logger.error(f"Error obteniendo programas: {e}")
            return pd.DataFrame()
    
    def obtener_inscritos_recientes(self, limite=10):
        """Obtener inscritos más recientes"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM inscritos ORDER BY fecha_registro DESC LIMIT ?"
                return pd.read_sql_query(query, conn, params=(limite,))
        except Exception as e:
            logger.error(f"Error obteniendo inscritos recientes: {e}")
            return pd.DataFrame()
    
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
    # MÉTODOS DE INSERCIÓN/ACTUALIZACIÓN - COMPLETOS
    # =============================================================================
    
    def agregar_inscrito(self, inscrito_data):
        """Agregar nuevo inscrito"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Generar matrícula si no existe
                if not inscrito_data.get('matricula'):
                    matricula = f"INS-{datetime.now().strftime('%y%m%d%H%M%S')}"
                    inscrito_data['matricula'] = matricula
                
                cursor.execute('''
                    INSERT INTO inscritos (
                        matricula, nombre_completo, email, telefono,
                        programa_interes, fecha_registro, estatus, folio,
                        fecha_nacimiento, como_se_entero
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    inscrito_data['matricula'],
                    inscrito_data['nombre_completo'],
                    inscrito_data['email'],
                    inscrito_data.get('telefono', ''),
                    inscrito_data['programa_interes'],
                    datetime.now(),
                    'Pre-inscrito',
                    f"FOL-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                    inscrito_data.get('fecha_nacimiento'),
                    inscrito_data.get('como_se_entero', '')
                ))
                
                inscrito_id = cursor.lastrowid
                
                # Crear usuario automáticamente
                self._crear_usuario_desde_inscrito(inscrito_data)
                
                return inscrito_id, inscrito_data['matricula']
                
        except Exception as e:
            logger.error(f"Error agregando inscrito: {e}")
            return None, None
    
    def _crear_usuario_desde_inscrito(self, inscrito_data):
        """Crear usuario automáticamente para un inscrito"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                matricula = inscrito_data['matricula']
                nombre = inscrito_data['nombre_completo']
                email = inscrito_data['email']
                
                # Contraseña temporal (primeros 6 chars de matrícula + 123)
                password_temp = matricula[:6] + "123"
                password_hash, salt = self.hash_password(password_temp)
                
                cursor.execute('''
                    INSERT INTO usuarios (
                        usuario, password_hash, salt, rol, 
                        nombre_completo, email, matricula
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    matricula,  # Usuario = matrícula
                    password_hash,
                    salt,
                    'inscrito',
                    nombre,
                    email,
                    matricula
                ))
                
                logger.info(f"Usuario creado para inscrito: {matricula}")
                
        except Exception as e:
            logger.error(f"Error creando usuario desde inscrito: {e}")
    
    def agregar_estudiante(self, estudiante_data):
        """Agregar nuevo estudiante"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO estudiantes (
                        matricula, nombre_completo, programa, email, telefono,
                        fecha_nacimiento, genero, estatus, fecha_ingreso
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    estudiante_data.get('matricula', ''),
                    estudiante_data.get('nombre_completo', ''),
                    estudiante_data.get('programa', ''),
                    estudiante_data.get('email', ''),
                    estudiante_data.get('telefono', ''),
                    estudiante_data.get('fecha_nacimiento'),
                    estudiante_data.get('genero', ''),
                    estudiante_data.get('estatus', 'Activo'),
                    datetime.now()
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
                        matricula, nombre_completo, programa_original,
                        fecha_graduacion, nivel_academico, email, telefono,
                        estado_laboral
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    egresado_data.get('matricula', ''),
                    egresado_data.get('nombre_completo', ''),
                    egresado_data.get('programa_original', ''),
                    egresado_data.get('fecha_graduacion', datetime.now()),
                    egresado_data.get('nivel_academico', ''),
                    egresado_data.get('email', ''),
                    egresado_data.get('telefono', ''),
                    egresado_data.get('estado_laboral', '')
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
                        estatus, salario, tipo_contrato, fecha_inicio
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    contratado_data.get('matricula', ''),
                    datetime.now(),
                    contratado_data.get('puesto', ''),
                    contratado_data.get('departamento', ''),
                    contratado_data.get('estatus', 'Activo'),
                    contratado_data.get('salario', ''),
                    contratado_data.get('tipo_contrato', ''),
                    datetime.now()
                ))
                
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error agregando contratado: {e}")
            return None
    
    def agregar_usuario(self, usuario_data):
        """Agregar nuevo usuario"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO usuarios (
                        usuario, password_hash, salt, rol, nombre_completo,
                        email, matricula, activo
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    usuario_data.get('usuario', ''),
                    usuario_data.get('password_hash', ''),
                    usuario_data.get('salt', ''),
                    usuario_data.get('rol', ''),
                    usuario_data.get('nombre_completo', ''),
                    usuario_data.get('email', ''),
                    usuario_data.get('matricula', ''),
                    usuario_data.get('activo', 1)
                ))
                
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error agregando usuario: {e}")
            return None
    
    def actualizar_inscrito(self, matricula, datos):
        """Actualizar inscrito existente"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                campos = []
                valores = []
                
                for campo, valor in datos.items():
                    campos.append(f"{campo} = ?")
                    valores.append(valor)
                
                valores.append(matricula)
                
                query = f"UPDATE inscritos SET {', '.join(campos)} WHERE matricula = ?"
                cursor.execute(query, valores)
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error actualizando inscrito {matricula}: {e}")
            return False
    
    def actualizar_estudiante(self, matricula, datos):
        """Actualizar estudiante existente"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                campos = []
                valores = []
                
                for campo, valor in datos.items():
                    campos.append(f"{campo} = ?")
                    valores.append(valor)
                
                valores.append(matricula)
                
                query = f"UPDATE estudiantes SET {', '.join(campos)} WHERE matricula = ?"
                cursor.execute(query, valores)
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error actualizando estudiante {matricula}: {e}")
            return False
    
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
            logger.error(f"Error registrando bitácora: {e}")
            return False
    
    def obtener_estadisticas_generales(self):
        """Obtener estadísticas generales"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                estadisticas = {}
                
                # Contar inscritos
                cursor.execute("SELECT COUNT(*) FROM inscritos")
                estadisticas['inscritos'] = cursor.fetchone()[0]
                
                # Contar estudiantes
                cursor.execute("SELECT COUNT(*) FROM estudiantes")
                estadisticas['estudiantes'] = cursor.fetchone()[0]
                
                # Contar egresados
                cursor.execute("SELECT COUNT(*) FROM egresados")
                estadisticas['egresados'] = cursor.fetchone()[0]
                
                # Contar contratados
                cursor.execute("SELECT COUNT(*) FROM contratados")
                estadisticas['contratados'] = cursor.fetchone()[0]
                
                # Contar usuarios
                cursor.execute("SELECT COUNT(*) FROM usuarios")
                estadisticas['usuarios'] = cursor.fetchone()[0]
                
                return estadisticas
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {}

# =============================================================================
# INSTANCIA DE BASE DE DATOS REMOTA
# =============================================================================

# Crear instancia global
db_remota = SistemaBaseDatosRemota()

# Intentar sincronizar inicialmente
try:
    sincronizado = db_remota.sincronizar_desde_remoto()
    if sincronizado:
        logger.info("✅ Base de datos inicializada correctamente")
    else:
        logger.warning("⚠️ No se pudo sincronizar inicialmente")
except Exception as e:
    logger.error(f"❌ Error inicializando base de datos: {e}")

# =============================================================================
# SISTEMA DE AUTENTICACIÓN
# =============================================================================

class SistemaAutenticacion:
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
                # Usar base de datos remota
                usuario_data = db_remota.verificar_login(usuario, password)
                
                if usuario_data:
                    nombre_real = usuario_data.get('nombre_completo', usuario_data.get('usuario', 'Usuario'))
                    
                    st.success(f"✅ ¡Bienvenido(a), {nombre_real}!")
                    st.session_state.login_exitoso = True
                    st.session_state.usuario_actual = usuario_data
                    st.session_state.rol_usuario = usuario_data.get('rol', 'usuario')
                    self.sesion_activa = True
                    self.usuario_actual = usuario_data
                    
                    # Registrar en bitácora
                    db_remota.registrar_bitacora(
                        usuario_data['usuario'],
                        'LOGIN',
                        f'Usuario {usuario_data["usuario"]} inició sesión'
                    )
                    
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
                db_remota.registrar_bitacora(
                    self.usuario_actual.get('usuario', ''),
                    'LOGOUT',
                    f'Usuario {self.usuario_actual.get("usuario", "")} cerró sesión'
                )
                
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
# SISTEMA DE EMAIL - COMPLETO (COPIADO DE ESCUELA10.PY)
# =============================================================================

class SistemaEmail:
    def __init__(self):
        self.config = self.obtener_configuracion_email()
        
    def obtener_configuracion_email(self):
        """Obtiene la configuración de email desde secrets.toml"""
        try:
            if not hasattr(st, 'secrets'):
                logger.warning("st.secrets no disponible para email")
                return {}
                
            return {
                'smtp_server': st.secrets.get("smtp_server", "smtp.gmail.com"),
                'smtp_port': st.secrets.get("smtp_port", 587),
                'email_user': st.secrets.get("email_user", ""),
                'email_password': st.secrets.get("email_password", ""),
                'notification_email': st.secrets.get("notification_email", "")
            }
        except Exception as e:
            logger.error(f"Error al cargar configuración de email: {e}")
            return {}
    
    def verificar_configuracion_email(self):
        """Verificar que la configuración de email esté completa"""
        try:
            config = self.obtener_configuracion_email()
            email_user = config.get('email_user', '')
            email_password = config.get('email_password', '')
            notification_email = config.get('notification_email', '')
            
            if not email_user:
                logger.error("❌ No se encontró 'email_user' en los secrets")
                return False
                
            if not email_password:
                logger.error("❌ No se encontró 'email_password' en los secrets")
                return False
                
            if not notification_email:
                logger.warning("⚠️ No se encontró 'notification_email' en los secrets")
                # No es crítico, solo advertencia
                config['notification_email'] = email_user  # Usar email_user como fallback
                
            logger.info("✅ Configuración de email verificada")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error verificando configuración: {e}")
            return False
    
    def test_conexion_smtp(self):
        """Probar conexión SMTP para diagnóstico"""
        try:
            config = self.obtener_configuracion_email()
            email_user = config.get('email_user', '')
            email_password = config.get('email_password', '')
            
            if not email_user or not email_password:
                return False, "Credenciales no configuradas"
                
            server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
            server.starttls()
            server.login(email_user, email_password)
            server.quit()
            
            return True, "✅ Conexión SMTP exitosa"
            
        except Exception as e:
            return False, f"❌ Error SMTP: {e}"
    
    def obtener_email_usuario(self, usuario):
        """Obtener email del usuario desde la base de datos"""
        try:
            usuario_data = db_remota.obtener_usuario(usuario)
            if usuario_data and usuario_data.get('email'):
                return usuario_data['email']
            return None
        except Exception as e:
            logger.error(f"Error obteniendo email del usuario: {e}")
            return None

    def enviar_notificacion_email(self, datos_inscripcion, documentos_guardados, es_completado=False):
        """Envía notificación por email cuando se completa una inscripción"""
        try:
            config = self.obtener_configuracion_email()
            
            if not config.get('email_user') or not config.get('email_password'):
                st.warning("⚠️ Configuración de email no disponible")
                return False
            
            # Obtener email del usuario destino desde la base de datos
            usuario_destino = datos_inscripcion.get('usuario', '')
            email_destino = self.obtener_email_usuario(usuario_destino)
            
            if not email_destino:
                st.warning(f"⚠️ No se pudo obtener email para el usuario: {usuario_destino}")
                # Usar el email del formulario como respaldo
                email_destino = datos_inscripcion.get('email', '')
                if not email_destino:
                    st.error("❌ No se pudo determinar el email destino")
                    return False
            
            # Configurar servidor SMTP
            server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
            server.starttls()
            server.login(config['email_user'], config['email_password'])
            
            # Crear mensaje
            msg = MIMEMultipart()
            msg['From'] = config['email_user']
            msg['To'] = email_destino
            msg['Cc'] = config.get('notification_email', config['email_user'])  # AGREGAR COPIA
            msg['Subject'] = f"✅ Confirmación de Proceso - Instituto Nacional de Cardiología"
            
            # Determinar tipo de proceso
            if es_completado:
                tipo_proceso = "COMPLETADO"
                titulo = "✅ PROCESO COMPLETADO EXITOSAMENTE"
                mensaje_estado = "ha sido completado exitosamente"
            else:
                tipo_proceso = "PROGRESO GUARDADO"
                titulo = "💾 PROGRESO GUARDADO CORRECTAMENTE"
                mensaje_estado = "se ha guardado correctamente"
            
            # Cuerpo del email con formato HTML mejorado
            cuerpo_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                    <div style="text-align: center; background: linear-gradient(135deg, #003366 0%, #00509e 100%); color: white; padding: 20px; border-radius: 10px 10px 0 0;">
                        <h2 style="margin: 0; font-size: 24px;">Instituto Nacional de Cardiología </h2>
                        <h3 style="margin: 10px 0 0 0; font-size: 18px; font-weight: normal;">Escuela de Enfermería</h3>
                    </div>
                    
                    <div style="padding: 20px;">
                        <h3 style="color: #27ae60; margin-top: 0;">{titulo}</h3>
                        
                        <p>Estimado(a) <strong>{datos_inscripcion.get('nombre_completo', 'Usuario')}</strong>,</p>
                        
                        <p>Le informamos que su proceso {mensaje_estado} en nuestro sistema académico.</p>
                        
                        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <p style="font-weight: bold; margin-bottom: 10px;">📋 Detalles del proceso:</p>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;"><strong>Usuario:</strong></td>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;">{usuario_destino}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;"><strong>Matrícula:</strong></td>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;">{datos_inscripcion.get('matricula', 'N/A')}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;"><strong>Tipo de proceso:</strong></td>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;">{tipo_proceso}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;"><strong>Fecha y hora:</strong></td>
                                    <td style="padding: 5px; border-bottom: 1px solid #eee;">{datetime.now().strftime('%d/%m/%Y %H:%M')}</td>
                                </tr>
                            </table>
                        </div>
                        
                        <div style="background-color: #e8f5e8; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <p style="font-weight: bold; margin-bottom: 10px;">📄 Documentos procesados:</p>
                            <p>Total de documentos: <strong>{len(documentos_guardados)}</strong></p>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                {''.join([f'<li>{doc.get("nombre_original", "Documento")}</li>' for doc in documentos_guardados])}
                            </ul>
                        </div>
                        
                        <p>El estado actual de su solicitud es: <strong style="color: #27ae60;">{tipo_proceso}</strong></p>
                        
                        <p>Si usted no realizó esta acción o tiene alguna duda, por favor contacte al administrador del sistema inmediatamente.</p>
                        
                        <div style="margin-top: 20px; padding: 15px; background-color: #fff3cd; border-radius: 5px;">
                            <p style="margin: 0; font-size: 12px; color: #856404;">
                                <strong>⚠️ Información importante:</strong><br>
                                • Este es un mensaje automático, por favor no responda a este email.<br>
                                • Sistema Académico - Instituto Nacional de Cardiología<br>
                                • Copia enviada a: {config.get('notification_email', 'No especificado')}
                            </p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(cuerpo_html, 'html'))
            
            # Enviar email con timeout - INCLUYENDO EL EMAIL DE NOTIFICACIÓN EN LOS DESTINATARIOS
            destinatarios = [email_destino]
            if config.get('notification_email'):
                destinatarios.append(config['notification_email'])
            
            server.sendmail(config['email_user'], destinatarios, msg.as_string())
            server.quit()
            
            st.success(f"✅ Email de confirmación enviado exitosamente a: {email_destino}")
            if config.get('notification_email'):
                st.success(f"✅ Copia enviada a: {config['notification_email']}")
            return True
            
        except smtplib.SMTPAuthenticationError:
            st.error("❌ Error de autenticación SMTP. Verifica:")
            st.error("1. Tu email y contraseña de aplicación")
            st.error("2. Que hayas habilitado la verificación en 2 pasos")
            st.error("3. Que hayas creado una contraseña de aplicación")
            return False
            
        except smtplib.SMTPConnectError:
            st.error("❌ Error de conexión SMTP. Verifica:")
            st.error("1. Tu conexión a internet")
            st.error("2. Que el puerto 587 no esté bloqueado")
            return False
            
        except Exception as e:
            st.error(f"❌ Error inesperado al enviar email: {e}")
            return False

    def enviar_email_confirmacion(self, usuario_destino, nombre_usuario, tipo_documento, nombre_archivo, tipo_accion="subida"):
        """Enviar email de confirmación al usuario con copia a notification_email"""
        # Crear estructura de datos compatible
        datos_inscripcion = {
            'usuario': usuario_destino,
            'nombre_completo': nombre_usuario,
            'matricula': 'Sistema',
            'email': self.obtener_email_usuario(usuario_destino) or ''
        }
        
        documentos_guardados = [{
            'nombre_original': f"{tipo_documento} - {nombre_archivo}",
            'tipo': tipo_documento
        }]
        
        es_completado = (tipo_accion == "completado")
        
        return self.enviar_notificacion_email(datos_inscripcion, documentos_guardados, es_completado)

# Instancia del sistema de email
sistema_email = SistemaEmail()

# =============================================================================
# FUNCIÓN PRINCIPAL MEJORADA CON VERIFICACIÓN DE BASE DE DATOS
# =============================================================================

def main():
    """Función principal de la aplicación"""
    
    # Inicializar estado de sesión
    if 'login_exitoso' not in st.session_state:
        st.session_state.login_exitoso = False
    if 'usuario_actual' not in st.session_state:
        st.session_state.usuario_actual = None
    if 'rol_usuario' not in st.session_state:
        st.session_state.rol_usuario = None
    if 'db_inicializada' not in st.session_state:
        st.session_state.db_inicializada = False
    
    # Sidebar con estado del sistema
    with st.sidebar:
        st.subheader("🔧 Estado del Sistema")
        
        # Modo de operación
        if gestor_remoto.modo_remoto:
            st.success("🔗 Modo remoto SSH")
            if gestor_remoto.config.get('remote_host'):
                st.caption(f"Servidor: {gestor_remoto.config['remote_host']}")
        else:
            st.info("💻 Modo local activado")
            st.caption("(Sin configuración SSH)")
        
        # Estado de la base de datos
        if not st.session_state.db_inicializada:
            st.warning("⚠️ Base de datos no inicializada")
            if st.button("🔄 Inicializar Base de Datos", use_container_width=True):
                with st.spinner("Inicializando base de datos..."):
                    if db_remota.sincronizar_desde_remoto():
                        st.session_state.db_inicializada = True
                        st.success("✅ Base de datos inicializada")
                        st.rerun()
                    else:
                        st.error("❌ Error inicializando base de datos")
        else:
            st.success("✅ Base de datos OK")
            if db_remota.ultima_sincronizacion:
                st.caption(f"🔄 Última sinc: {db_remota.ultima_sincronizacion.strftime('%H:%M:%S')}")
        
        # Botón para verificar tablas
        if st.button("📊 Verificar Tablas", use_container_width=True):
            try:
                with db_remota.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tablas = cursor.fetchall()
                    
                    if tablas:
                        st.success(f"✅ {len(tablas)} tablas encontradas:")
                        for tabla in tablas:
                            st.write(f"- {tabla[0]}")
                    else:
                        st.error("❌ No hay tablas en la base de datos")
                        st.info("Intenta inicializar la base de datos primero")
            except Exception as e:
                st.error(f"❌ Error: {e}")
    
    # Mostrar interfaz según estado de login
    if not st.session_state.login_exitoso:
        mostrar_login()
    else:
        mostrar_interfaz_principal()

def mostrar_login():
    """Interfaz de login mejorada"""
    st.title("🔐 Sistema Escuela Enfermería - Modo Supervisión Remota")
    st.markdown("---")
    
    # Verificar si la base de datos está inicializada
    if not st.session_state.db_inicializada:
        st.warning("⚠️ La base de datos no está inicializada")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Inicializar Base de Datos", use_container_width=True):
                with st.spinner("Creando base de datos y tablas..."):
                    if db_remota.sincronizar_desde_remoto():
                        st.session_state.db_inicializada = True
                        st.success("✅ Base de datos inicializada correctamente")
                        st.rerun()
                    else:
                        st.error("❌ Error inicializando base de datos")
        
        with col2:
            if st.button("📊 Verificar Estado", use_container_width=True):
                try:
                    if db_remota.db_local_temp and os.path.exists(db_remota.db_local_temp):
                        file_size = os.path.getsize(db_remota.db_local_temp)
                        st.info(f"📁 Base de datos: {db_remota.db_local_temp}")
                        st.info(f"📏 Tamaño: {file_size} bytes")
                        
                        conn = sqlite3.connect(db_remota.db_local_temp)
                        cursor = conn.cursor()
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tablas = cursor.fetchall()
                        conn.close()
                        
                        if tablas:
                            st.success(f"✅ {len(tablas)} tablas encontradas")
                            for tabla in tablas:
                                st.write(f"- {tabla[0]}")
                        else:
                            st.error("❌ No hay tablas")
                    else:
                        st.error("❌ No hay base de datos creada")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
        
        st.markdown("---")
    
    # Formulario de login
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            st.subheader("Iniciar Sesión")
            
            # Verificar si podemos hacer login
            if not st.session_state.db_inicializada:
                st.warning("⚠️ Primero inicializa la base de datos")
                login_disabled = True
            else:
                login_disabled = False
            
            usuario = st.text_input("👤 Usuario", placeholder="admin", key="login_usuario", disabled=login_disabled)
            password = st.text_input("🔒 Contraseña", type="password", placeholder="Admin123!", key="login_password", disabled=login_disabled)
            
            login_button = st.form_submit_button("🚀 Ingresar al Sistema", use_container_width=True, disabled=login_disabled)

            if login_button and not login_disabled:
                if usuario and password:
                    with st.spinner("Verificando credenciales..."):
                        if auth.verificar_login(usuario, password):
                            st.rerun()
                        else:
                            st.error("❌ Credenciales incorrectas")
                else:
                    st.warning("⚠️ Complete todos los campos")
            
            # Información de acceso por defecto
            with st.expander("ℹ️ Información de acceso", expanded=not st.session_state.db_inicializada):
                st.info("**Credenciales por defecto (se crean automáticamente):**")
                st.info("👤 Usuario: admin")
                st.info("🔒 Contraseña: Admin123!")
                
                st.info("""
                **Notas importantes:**
                1. Si es la primera vez, haz clic en "Inicializar Base de Datos"
                2. Se crearán automáticamente todas las tablas necesarias
                3. Se creará el usuario administrador con las credenciales anteriores
                4. También se crearán programas de ejemplo
                """)

def mostrar_interfaz_principal():
    """Interfaz principal después del login"""
    # Barra superior con información del usuario
    usuario_actual = st.session_state.usuario_actual
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        st.title("🏥 Sistema Escuela Enfermería - Modo Supervisión Remota")
        nombre_usuario = usuario_actual.get('nombre_completo', usuario_actual.get('usuario', 'Usuario'))
        st.write(f"**👤 Usuario:** {nombre_usuario}")
    
    with col2:
        rol_usuario = usuario_actual.get('rol', 'usuario').title()
        st.write(f"**🎭 Rol:** {rol_usuario}")
        
        # Estado de sincronización
        if db_remota.ultima_sincronizacion:
            st.caption(f"🔄 {db_remota.ultima_sincronizacion.strftime('%H:%M:%S')}")
    
    with col3:
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            auth.cerrar_sesion()
            st.rerun()
    
    st.markdown("---")
    
    # Mostrar interfaz según rol
    rol_actual = usuario_actual.get('rol', '').lower()
    
    if rol_actual == 'administrador':
        mostrar_interfaz_administrador()
    elif rol_actual == 'inscrito':
        mostrar_interfaz_inscrito()
    elif rol_actual == 'estudiante':
        mostrar_interfaz_estudiante()
    elif rol_actual == 'egresado':
        mostrar_interfaz_egresado()
    elif rol_actual == 'contratado':
        mostrar_interfaz_contratado()
    else:
        st.error(f"❌ Rol no reconocido: {rol_actual}")
        st.info("Roles disponibles: administrador, inscrito, estudiante, egresado, contratado")

# =============================================================================
# INTERFACES POR ROL (versiones simplificadas para prueba)
# =============================================================================

def mostrar_interfaz_administrador():
    """Interfaz para administradores"""
    st.title("⚙️ Panel de Administración")
    
    # Dashboard rápido
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        try:
            inscritos = db_remota.obtener_inscritos()
            total_inscritos = len(inscritos) if not inscritos.empty else 0
            st.metric("Total Inscritos", total_inscritos)
        except:
            st.metric("Total Inscritos", 0)
    
    with col2:
        try:
            estudiantes = db_remota.obtener_estudiantes()
            total_estudiantes = len(estudiantes) if not estudiantes.empty else 0
            st.metric("Total Estudiantes", total_estudiantes)
        except:
            st.metric("Total Estudiantes", 0)
    
    with col3:
        try:
            usuarios = db_remota.obtener_usuarios()
            total_usuarios = len(usuarios) if not usuarios.empty else 0
            st.metric("Total Usuarios", total_usuarios)
        except:
            st.metric("Total Usuarios", 0)
    
    with col4:
        try:
            programas = db_remota.obtener_programas()
            total_programas = len(programas) if not programas.empty else 0
            st.metric("Total Programas", total_programas)
        except:
            st.metric("Total Programas", 0)
    
    # Opciones de administración
    st.subheader("📋 Acciones Rápidas")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("👥 Ver Usuarios", use_container_width=True):
            try:
                usuarios = db_remota.obtener_usuarios()
                if not usuarios.empty:
                    st.dataframe(usuarios[['usuario', 'nombre_completo', 'rol', 'email']], use_container_width=True)
                else:
                    st.info("No hay usuarios registrados")
            except Exception as e:
                st.error(f"Error: {e}")
    
    with col2:
        if st.button("📝 Ver Inscritos", use_container_width=True):
            try:
                inscritos = db_remota.obtener_inscritos()
                if not inscritos.empty:
                    st.dataframe(inscritos[['matricula', 'nombre_completo', 'email', 'programa_interes']], use_container_width=True)
                else:
                    st.info("No hay inscritos registrados")
            except Exception as e:
                st.error(f"Error: {e}")
    
    with col3:
        if st.button("🎓 Ver Programas", use_container_width=True):
            try:
                programas = db_remota.obtener_programas()
                if not programas.empty:
                    st.dataframe(programas[['codigo', 'nombre', 'modalidad', 'costo']], use_container_width=True)
                else:
                    st.info("No hay programas registrados")
            except Exception as e:
                st.error(f"Error: {e}")
    
    # Herramientas del sistema
    st.subheader("🔧 Herramientas del Sistema")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Sincronizar Ahora", use_container_width=True):
            with st.spinner("Sincronizando..."):
                if db_remota.sincronizar_desde_remoto():
                    st.success("✅ Sincronización exitosa")
                    st.rerun()
                else:
                    st.error("❌ Error en sincronización")
    
    with col2:
        if st.button("📊 Verificar Tablas", use_container_width=True):
            try:
                with db_remota.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tablas = cursor.fetchall()
                    
                    st.success(f"✅ Base de datos OK - {len(tablas)} tablas:")
                    for tabla in tablas:
                        # Contar registros en cada tabla
                        try:
                            cursor.execute(f"SELECT COUNT(*) FROM {tabla[0]}")
                            count = cursor.fetchone()[0]
                            st.write(f"- {tabla[0]}: {count} registros")
                        except:
                            st.write(f"- {tabla[0]}")
            except Exception as e:
                st.error(f"❌ Error: {e}")

def mostrar_interfaz_inscrito():
    """Interfaz simplificada para inscritos"""
    st.title("🎓 Portal del Inscrito")
    
    usuario_actual = st.session_state.usuario_actual
    matricula = usuario_actual.get('matricula', usuario_actual.get('usuario', ''))
    
    st.success(f"✅ Bienvenido, {usuario_actual.get('nombre_completo', 'Inscrito')}")
    st.info(f"📋 Tu matrícula: {matricula}")
    
    # Aquí puedes agregar más funcionalidades específicas para inscritos

def mostrar_interfaz_estudiante():
    """Interfaz simplificada para estudiantes"""
    st.title("🎓 Portal del Estudiante")
    
    usuario_actual = st.session_state.usuario_actual
    
    st.success(f"✅ Bienvenido, {usuario_actual.get('nombre_completo', 'Estudiante')}")
    st.info("Aquí puedes ver tu información académica y gestionar tus documentos.")

def mostrar_interfaz_egresado():
    """Interfaz simplificada para egresados"""
    st.title("🎓 Portal del Egresado")
    
    usuario_actual = st.session_state.usuario_actual
    
    st.success(f"✅ Bienvenido, {usuario_actual.get('nombre_completo', 'Egresado')}")
    st.info("Aquí puedes actualizar tu información profesional y ver oportunidades.")

def mostrar_interfaz_contratado():
    """Interfaz simplificada para contratados"""
    st.title("💼 Portal del Personal Contratado")
    
    usuario_actual = st.session_state.usuario_actual
    
    st.success(f"✅ Bienvenido, {usuario_actual.get('nombre_completo', 'Contratado')}")
    st.info("Aquí puedes ver tu información laboral y documentos relacionados.")

# =============================================================================
# EJECUCIÓN PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"❌ Error crítico en la aplicación: {e}")
        logger.error(f"Error crítico: {e}", exc_info=True)
        
        # Información de diagnóstico
        with st.expander("🔧 Información de diagnóstico"):
            st.write("**Versiones:**")
            try:
                st.write(f"- Python: {sys.version}")
                st.write(f"- Streamlit: {st.__version__}")
                st.write(f"- Pandas: {pd.__version__}")
                st.write(f"- SQLite: {sqlite3.sqlite_version}")
            except:
                pass
            
            st.write("**Variables de entorno:**")
            st.write(f"- Directorio actual: {os.getcwd()}")
            
            # Verificar si hay base de datos
            if db_remota.db_local_temp:
                st.write(f"- Ruta BD: {db_remota.db_local_temp}")
                if os.path.exists(db_remota.db_local_temp):
                    st.write(f"- BD existe: Sí ({os.path.getsize(db_remota.db_local_temp)} bytes)")
                else:
                    st.write("- BD existe: No")
        
        # Botones de recuperación
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Reintentar Conexión"):
                try:
                    if db_remota.sincronizar_desde_remoto():
                        st.success("✅ Conexión reestablecida")
                        st.rerun()
                    else:
                        st.error("No se pudo recuperar la conexión")
                except:
                    st.error("Error en recuperación")
        
        with col2:
            if st.button("🔄 Recargar Página"):
                st.rerun()
