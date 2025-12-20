"""
migracion10.py - Sistema de migración con BCRYPT y SSH
Versión actualizada para usar bcrypt con conexión SSH y secrets.toml
Sistema completo de migración con base de datos SQLite remota
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
    page_title="Sistema Escuela Enfermería - Modo Migración SSH",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
                # Estado por defecto
                return {
                    'db_inicializada': False,
                    'fecha_inicializacion': None,
                    'ultima_sincronizacion': None,
                    'modo_operacion': 'local',
                    'migraciones_realizadas': 0,
                    'ultima_migracion': None
                }
        except Exception as e:
            logger.warning(f"⚠️ Error cargando estado: {e}")
            return self._estado_por_defecto()
    
    def _estado_por_defecto(self):
        """Estado por defecto"""
        return {
            'db_inicializada': False,
            'fecha_inicializacion': None,
            'ultima_sincronizacion': None,
            'modo_operacion': 'local',
            'migraciones_realizadas': 0,
            'ultima_migracion': None
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
    
    def set_modo_operacion(self, modo):
        """Establecer modo de operación"""
        self.estado['modo_operacion'] = modo
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
# GESTOR DE CONEXIÓN REMOTA VIA SSH - MEJORADO
# =============================================================================

class GestorConexionRemotaMigracion:
    """Gestor de conexión SSH al servidor remoto para migración"""
    
    def __init__(self):
        self.ssh = None
        self.sftp = None
        self.config = self._cargar_configuracion_ssh()
        
        # Determinar modo de operación
        if self.config and all(key in self.config for key in ['remote_host', 'remote_user', 'remote_password']):
            self.modo_remoto = True
            self.db_path_remoto = "/home/POLANCO6/ESCUELA/datos/escuela.db"
            self.uploads_path_remoto = "/home/POLANCO6/ESCUELA/uploads"
            estado_migracion.set_modo_operacion('remoto')
            logger.info("🔗 Modo remoto SSH activado para migración")
        else:
            self.modo_remoto = False
            # Usar base de datos local si no hay SSH
            self.db_local_path = "/mount/src/escuelanueva/datos/escuela.db"
            self.uploads_path_local = "/mount/src/escuelanueva/uploads"
            estado_migracion.set_modo_operacion('local')
            logger.info("💻 Modo local activado (sin SSH) para migración")
        
        self.temp_db_path = None
        self.conexion_local = None
    
    def _cargar_configuracion_ssh(self):
        """Cargar configuración SSH desde secrets.toml"""
        try:
            # Verificar si st.secrets está disponible
            if not hasattr(st, 'secrets'):
                logger.warning("st.secrets no está disponible para migración")
                return {}
            
            # Intentar cargar configuración
            config = {
                'remote_host': st.secrets.get("remote_host", ""),
                'remote_port': int(st.secrets.get("remote_port", 22)),  # Valor por defecto
                'remote_user': st.secrets.get("remote_user", ""),
                'remote_password': st.secrets.get("remote_password", "")
            }
            
            # Verificar que no estén vacíos
            for key, value in config.items():
                if not value:
                    logger.warning(f"Configuración SSH para migración: {key} está vacío")
                    return {}
            
            logger.info(f"✅ Configuración SSH cargada para {config['remote_host']}")
            return config
            
        except KeyError as e:
            # Error específico de clave faltante
            missing_key = str(e).replace("'", "")
            logger.warning(f"⚠️ Clave faltante en secrets.toml para migración: {missing_key}")
            return {}
            
        except Exception as e:
            # Error general
            logger.warning(f"⚠️ Error cargando configuración SSH para migración: {e}")
            return {}
    
    def conectar_ssh(self):
        """Establecer conexión SSH con el servidor remoto"""
        try:
            if not self.config or not self.modo_remoto:
                logger.warning("Modo remoto no disponible para migración")
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
        """Descargar base de datos SQLite del servidor remoto"""
        try:
            # Si estamos en modo local, usar base de datos local
            if not self.modo_remoto:
                logger.info("📁 Usando base de datos local para migración (modo sin SSH)")
                return self._usar_db_local()
            
            # Modo remoto: conectar SSH
            if not self.conectar_ssh():
                logger.warning("⚠️ Falló conexión SSH para migración, usando modo local")
                return self._usar_db_local()
            
            # Crear archivo temporal local
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.temp_db_path = os.path.join(temp_dir, f"migracion_temp_{timestamp}.db")
            
            # Intentar descargar archivo remoto
            try:
                logger.info(f"📥 Descargando base de datos para migración desde: {self.db_path_remoto}")
                self.sftp.get(self.db_path_remoto, self.temp_db_path)
                
                # Verificar que el archivo se descargó correctamente
                if os.path.exists(self.temp_db_path) and os.path.getsize(self.temp_db_path) > 0:
                    file_size = os.path.getsize(self.temp_db_path)
                    logger.info(f"✅ Base de datos para migración descargada: {self.temp_db_path} ({file_size} bytes)")
                    return self.temp_db_path
                else:
                    logger.warning("⚠️ Archivo descargado vacío o corrupto para migración")
                    return self._crear_nueva_db_local()
                    
            except FileNotFoundError:
                logger.warning(f"⚠️ Base de datos remota no encontrada para migración: {self.db_path_remoto}")
                return self._crear_nueva_db_local()
                
            except Exception as e:
                logger.error(f"❌ Error descargando archivo para migración: {e}")
                return self._crear_nueva_db_local()
                
        except Exception as e:
            logger.error(f"❌ Error en descargar_db_remota para migración: {e}")
            return self._crear_nueva_db_local()
        finally:
            if self.modo_remoto:
                self.desconectar_ssh()
    
    def _usar_db_local(self):
        """Usar base de datos local si existe, o crear una nueva"""
        try:
            # Si ya tenemos una base de datos temporal, usarla
            if self.temp_db_path and os.path.exists(self.temp_db_path):
                logger.info(f"📁 Usando base de datos temporal existente para migración: {self.temp_db_path}")
                return self.temp_db_path
            
            # Verificar si existe base de datos local en ruta estándar
            if os.path.exists(self.db_local_path):
                logger.info(f"📁 Usando base de datos local existente para migración: {self.db_local_path}")
                return self.db_local_path
            else:
                # Crear directorio si no existe
                os.makedirs(os.path.dirname(self.db_local_path), exist_ok=True)
                logger.info(f"📁 Creando nueva base de datos local para migración: {self.db_local_path}")
                return self._crear_nueva_db_local()
        except Exception as e:
            logger.error(f"❌ Error usando base de datos local para migración: {e}")
            return self._crear_nueva_db_local()
    
    def _crear_nueva_db_local(self):
        """Crear una nueva base de datos SQLite local para migración"""
        try:
            # Crear archivo temporal para la nueva base de datos
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.temp_db_path = os.path.join(temp_dir, f"migracion_nueva_{timestamp}.db")
            
            logger.info(f"📝 Creando nueva base de datos para migración en: {self.temp_db_path}")
            
            # Inicializar la base de datos inmediatamente
            self._inicializar_db_migracion(self.temp_db_path)
            
            return self.temp_db_path
            
        except Exception as e:
            logger.error(f"❌ Error creando nueva base de datos para migración: {e}")
            
            # Último intento: usar un archivo en directorio actual
            try:
                self.temp_db_path = "datos/escuela_migracion.db"
                os.makedirs("datos", exist_ok=True)
                self._inicializar_db_migracion(self.temp_db_path)
                return self.temp_db_path
            except Exception as e2:
                logger.critical(f"❌ No se pudo crear base de datos para migración: {e2}")
                return None
    
    def _inicializar_db_migracion(self, db_path):
        """Inicializar estructura de base de datos para migración"""
        try:
            logger.info(f"📝 Inicializando estructura para migración en: {db_path}")
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
                logger.info("✅ Usuario administrador por defecto creado con BCRYPT para migración")
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Estructura de base de datos para migración inicializada en {db_path}")
            
            # Marcar como inicializada en el estado persistente
            estado_migracion.marcar_db_inicializada()
            
        except Exception as e:
            logger.error(f"❌ Error inicializando base de datos para migración en {db_path}: {e}")
            raise
    
    def subir_db_local(self, ruta_local):
        """Subir base de datos local al servidor remoto (sobreescribir)"""
        try:
            if not self.modo_remoto:
                logger.info("📤 Modo local: no se sube a servidor remoto desde migración")
                return True
            
            if not self.conectar_ssh():
                return False
            
            # Crear backup de la base de datos remota antes de sobreescribir
            try:
                backup_path = f"{self.db_path_remoto}.backup_migracion_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                self.sftp.rename(self.db_path_remoto, backup_path)
                logger.info(f"✅ Backup creado desde migración: {backup_path}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo crear backup desde migración: {e}")
                # Continuar aunque no se pueda hacer backup
            
            # Subir nuevo archivo
            self.sftp.put(ruta_local, self.db_path_remoto)
            
            logger.info(f"✅ Base de datos de migración subida a servidor: {self.db_path_remoto}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error subiendo base de datos desde migración: {e}")
            return False
        finally:
            if self.modo_remoto:
                self.desconectar_ssh()
    
    def renombrar_archivos_pdf(self, matricula_vieja, matricula_nueva):
        """Renombrar archivos PDF en el servidor remoto"""
        try:
            if not self.modo_remoto:
                logger.info(f"📝 Modo local: Simulando renombrado {matricula_vieja} -> {matricula_nueva}")
                return 1  # Simular 1 archivo renombrado
            
            if not self.conectar_ssh():
                return 0
            
            archivos_renombrados = 0
            
            try:
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
                            logger.info(f"✅ Renombrado en servidor: {archivo} -> {nuevo_nombre}")
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
    
    def obtener_nombres_archivos_pdf(self, matricula):
        """Obtener los nombres de los archivos PDF renombrados para una matrícula"""
        try:
            if not self.modo_remoto:
                # Modo simulación
                return f"{matricula}_documentos.pdf, {matricula}_curp.pdf"
            
            if not self.conectar_ssh():
                return f"{matricula}_documentos.pdf"
            
            nombres_archivos = []
            
            try:
                archivos = self.sftp.listdir(self.uploads_path_remoto)
                
                # Buscar archivos que contengan la matrícula
                for archivo in archivos:
                    if (archivo.lower().endswith('.pdf') and 
                        (archivo.startswith(matricula + '_') or f"_{matricula}_" in archivo or matricula in archivo)):
                        nombres_archivos.append(archivo)
                
                logger.info(f"Encontrados {len(nombres_archivos)} archivos PDF para {matricula}")
                
            except FileNotFoundError:
                logger.warning(f"📁 Directorio de uploads no encontrado: {self.uploads_path_remoto}")
            
            self.desconectar_ssh()
            
            if nombres_archivos:
                resultado = ", ".join(nombres_archivos)
                return resultado
            else:
                return f"Documentos de {matricula}"
                
        except Exception as e:
            logger.error(f"Error obteniendo nombres de archivos PDF: {e}")
            return f"Documentos de {matricula}"

# Instancia global del gestor de conexión remota para migración
gestor_remoto_migracion = GestorConexionRemotaMigracion()

# =============================================================================
# SISTEMA DE BASE DE DATOS SQLITE PARA MIGRACIÓN - CON BCRYPT
# =============================================================================

class SistemaBaseDatosMigracion:
    """Sistema de base de datos SQLite para migración con sincronización remota via SSH"""
    
    def __init__(self):
        self.gestor = gestor_remoto_migracion
        self.db_local_temp = None
        self.conexion_actual = None
        self.ultima_sincronizacion = None
        
    def sincronizar_desde_remoto(self):
        """Sincronizar base de datos desde el servidor remoto o crear local"""
        try:
            # 1. Descargar base de datos remota o crear local
            self.db_local_temp = self.gestor.descargar_db_remota()
            
            if not self.db_local_temp:
                st.error("❌ No se pudo obtener base de datos para migración")
                return False
            
            # 2. Verificar que el archivo existe
            if not os.path.exists(self.db_local_temp):
                logger.error(f"❌ Archivo de base de datos para migración no existe: {self.db_local_temp}")
                return False
            
            # 3. Verificar que sea una base de datos SQLite válida con tablas
            try:
                conn = sqlite3.connect(self.db_local_temp)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tablas = cursor.fetchall()
                conn.close()
                
                logger.info(f"✅ Base de datos para migración verificada: {len(tablas)} tablas")
                
                if len(tablas) == 0:
                    logger.warning("⚠️ Base de datos vacía para migración, inicializando estructura...")
                    # Inicializar estructura
                    self._inicializar_estructura_db()
            except Exception as e:
                logger.error(f"❌ Base de datos corrupta para migración: {e}")
                st.warning("⚠️ La base de datos para migración está vacía o corrupta. Se inicializará estructura.")
                self._inicializar_estructura_db()
            
            self.ultima_sincronizacion = datetime.now()
            logger.info(f"✅ Sincronización para migración exitosa: {self.db_local_temp}")
            
            # Actualizar estado de sincronización
            estado_migracion.marcar_sincronizacion()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en sincronización para migración: {e}")
            st.error(f"❌ Error sincronizando para migración: {e}")
            return False
    
    def _inicializar_estructura_db(self):
        """Inicializar estructura de la base de datos para migración"""
        try:
            if not self.db_local_temp:
                logger.error("❌ No hay ruta de base de datos para inicializar migración")
                return
            
            conn = sqlite3.connect(self.db_local_temp)
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
                logger.info("✅ Usuario administrador por defecto creado con BCRYPT para migración")
            
            conn.commit()
            conn.close()
            logger.info("✅ Estructura de base de datos para migración inicializada")
            
            # Marcar como inicializada en el estado persistente
            estado_migracion.marcar_db_inicializada()
            
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura para migración: {e}")
            raise
    
    def sincronizar_hacia_remoto(self):
        """Sincronizar base de datos local hacia el servidor remoto"""
        try:
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                st.error("❌ No hay base de datos local para subir desde migración")
                return False
            
            # Subir al servidor remoto (si estamos en modo remoto)
            if self.gestor.modo_remoto:
                exito = self.gestor.subir_db_local(self.db_local_temp)
                
                if exito:
                    self.ultima_sincronizacion = datetime.now()
                    logger.info("✅ Cambios de migración subidos exitosamente al servidor")
                    
                    # Actualizar estado
                    estado_migracion.marcar_sincronizacion()
                    
                    return True
                else:
                    return False
            else:
                # En modo local, solo actualizamos la marca de tiempo
                self.ultima_sincronizacion = datetime.now()
                logger.info("💻 Modo local: cambios de migración guardados localmente")
                
                # Actualizar estado
                estado_migracion.marcar_sincronizacion()
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Error subiendo cambios desde migración: {e}")
            st.error(f"❌ Error subiendo cambios desde migración: {e}")
            return False
    
    @contextmanager
    def get_connection(self):
        """Context manager para conexiones a la base de datos de migración"""
        conn = None
        try:
            # Asegurar que tenemos la base de datos más reciente
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                # Si ya está inicializada, solo sincronizar
                if estado_migracion.esta_inicializada():
                    self.sincronizar_desde_remoto()
                else:
                    # Si no está inicializada, inicializar
                    if not self.sincronizar_desde_remoto():
                        raise Exception("No se pudo inicializar la base de datos para migración")
            
            conn = sqlite3.connect(self.db_local_temp)
            conn.row_factory = sqlite3.Row  # Para acceso por nombre de columna
            self.conexion_actual = conn
            yield conn
            
            if conn:
                conn.commit()
                
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"❌ Error en conexión a base de datos de migración: {e}")
            st.error(f"❌ Error en base de datos de migración: {e}")
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
            logger.error(f"Error al crear hash BCRYPT para migración: {e}")
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
            logger.error(f"Error verificando password para migración: {e}")
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
            logger.error(f"Error obteniendo usuario {usuario} para migración: {e}")
            return None
    
    def verificar_login(self, usuario, password):
        """Verificar credenciales de login para migración"""
        try:
            usuario_data = self.obtener_usuario(usuario)
            if not usuario_data:
                logger.warning(f"Usuario no encontrado para migración: {usuario}")
                return None
            
            password_hash = usuario_data.get('password_hash', '')
            salt = usuario_data.get('salt', '')
            
            if self.verify_password(password_hash, salt, password):
                logger.info(f"Login exitoso para migración: {usuario}")
                return usuario_data
            else:
                logger.warning(f"Password incorrecto para migración: {usuario}")
                return None
                
        except Exception as e:
            logger.error(f"Error verificando login para migración: {e}")
            return None
    
    def obtener_inscritos(self):
        """Obtener todos los inscritos"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM inscritos ORDER BY fecha_registro DESC"
                df = pd.read_sql_query(query, conn)
                logger.info(f"Obtenidos {len(df)} inscritos para migración")
                return df
        except Exception as e:
            logger.error(f"Error obteniendo inscritos para migración: {e}")
            return pd.DataFrame()
    
    def obtener_estudiantes(self):
        """Obtener todos los estudiantes"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM estudiantes ORDER BY fecha_ingreso DESC"
                df = pd.read_sql_query(query, conn)
                logger.info(f"Obtenidos {len(df)} estudiantes para migración")
                return df
        except Exception as e:
            logger.error(f"Error obteniendo estudiantes para migración: {e}")
            return pd.DataFrame()
    
    def obtener_egresados(self):
        """Obtener todos los egresados"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM egresados ORDER BY fecha_graduacion DESC"
                df = pd.read_sql_query(query, conn)
                logger.info(f"Obtenidos {len(df)} egresados para migración")
                return df
        except Exception as e:
            logger.error(f"Error obteniendo egresados para migración: {e}")
            return pd.DataFrame()
    
    def obtener_contratados(self):
        """Obtener todos los contratados"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM contratados ORDER BY fecha_contratacion DESC"
                df = pd.read_sql_query(query, conn)
                logger.info(f"Obtenidos {len(df)} contratados para migración")
                return df
        except Exception as e:
            logger.error(f"Error obteniendo contratados para migración: {e}")
            return pd.DataFrame()
    
    def obtener_usuarios(self):
        """Obtener todos los usuarios"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM usuarios ORDER BY fecha_creacion DESC"
                df = pd.read_sql_query(query, conn)
                logger.info(f"Obtenidos {len(df)} usuarios para migración")
                return df
        except Exception as e:
            logger.error(f"Error obteniendo usuarios para migración: {e}")
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
            logger.error(f"Error buscando inscrito {matricula} para migración: {e}")
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
            logger.error(f"Error buscando estudiante {matricula} para migración: {e}")
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
            logger.error(f"Error buscando egresado {matricula} para migración: {e}")
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
            logger.error(f"Error buscando contratado {matricula} para migración: {e}")
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
            logger.error(f"Error al actualizar usuario para migración: {e}")
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
            logger.error(f"Error eliminando inscrito {matricula} para migración: {e}")
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
            logger.error(f"Error eliminando estudiante {matricula} para migración: {e}")
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
            logger.error(f"Error eliminando egresado {matricula} para migración: {e}")
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
            logger.error(f"Error agregando estudiante para migración: {e}")
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
            logger.error(f"Error agregando egresado para migración: {e}")
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
            logger.error(f"Error agregando contratado para migración: {e}")
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
            logger.error(f"Error registrando en bitácora para migración: {e}")
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
        """Verificar credenciales de usuario para migración"""
        try:
            if not usuario or not password:
                st.error("❌ Usuario y contraseña son obligatorios para migración")
                return False
            
            with st.spinner("🔐 Verificando credenciales para migración..."):
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
                    st.error("❌ Usuario o contraseña incorrectos para migración")
                    return False
                    
        except Exception as e:
            st.error(f"❌ Error en el proceso de login para migración: {e}")
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
            st.success("✅ Sesión cerrada exitosamente del migrador")
            
        except Exception as e:
            st.error(f"❌ Error cerrando sesión del migrador: {e}")

# Instancia global del sistema de autenticación para migración
auth_migracion = SistemaAutenticacionMigracion()

# =============================================================================
# SISTEMA DE MIGRACIÓN DE ROLES - ACTUALIZADO CON SSH Y SECRETS
# =============================================================================

class SistemaMigracionCompleto:
    def __init__(self):
        self.gestor = gestor_remoto_migracion
        self.db = db_migracion
        self.cargar_datos()
        
    def cargar_datos(self):
        """Cargar datos desde la base de datos de migración"""
        try:
            with st.spinner("📊 Cargando datos para migración..."):
                self.df_inscritos = self.db.obtener_inscritos()
                self.df_estudiantes = self.db.obtener_estudiantes()
                self.df_egresados = self.db.obtener_egresados()
                self.df_contratados = self.db.obtener_contratados()
                self.df_usuarios = self.db.obtener_usuarios()
                
                logger.info(f"Datos cargados: {len(self.df_inscritos)} inscritos, {len(self.df_estudiantes)} estudiantes")
        except Exception as e:
            logger.error(f"Error cargando datos para migración: {e}")
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
    
    def obtener_nombres_archivos_pdf(self, matricula):
        """Obtener los nombres de archivos PDF renombrados"""
        return self.gestor.obtener_nombres_archivos_pdf(matricula)
    
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
            
            # 1. Buscar usuario en base de datos
            st.subheader("🔍 Buscando usuario en base de datos...")
            usuario_id = self.buscar_usuario_por_matricula(matricula_inscrito)
            
            if usuario_id:
                # Actualizar usuario en SQLite
                st.subheader("👤 Actualizando usuario en base de datos...")
                if self.actualizar_rol_usuario(usuario_id, 'estudiante', matricula_estudiante):
                    st.success("✅ Usuario actualizado exitosamente")
                else:
                    st.warning("⚠️ No se pudo actualizar usuario, continuando con migración")
            else:
                st.warning("⚠️ Usuario no encontrado, continuando con migración de datos")
            
            # 2. Renombrar archivos PDF
            st.subheader("📁 Renombrando archivos PDF...")
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_inscrito, matricula_estudiante)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.info("📝 Modo simulación: Archivos PDF renombrados en simulación")
            
            # 3. Eliminar inscrito y crear estudiante
            st.subheader("🔄 Procesando migración de datos...")
            
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
            self.db.registrar_bitacora(
                st.session_state.usuario_actual.get('usuario', 'admin'),
                'MIGRACION_INSCRITO_ESTUDIANTE',
                f'Usuario migrado de inscrito a estudiante. Matrícula: {matricula_inscrito} -> {matricula_estudiante}'
            )
            
            # Registrar migración exitosa
            estado_migracion.registrar_migracion()
            
            # Sincronizar cambios con servidor remoto
            if self.db.sincronizar_hacia_remoto():
                st.success("✅ Cambios sincronizados con servidor remoto")
            else:
                st.warning("⚠️ Cambios guardados localmente (modo sin sincronización)")
            
            st.success(f"🎉 ¡Migración completada exitosamente!")
            st.balloons()
            
            # Mostrar resumen final
            st.subheader("📊 Resumen Final de la Migración")
            st.success(f"✅ Matrícula actualizada: {matricula_inscrito} → {matricula_estudiante}")
            st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
            st.success(f"✅ Registro creado en estudiantes")
            st.success(f"✅ Registro eliminado de inscritos")
            
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
            
            # 1. Buscar usuario en base de datos
            st.subheader("🔍 Buscando usuario en base de datos...")
            usuario_id = self.buscar_usuario_por_matricula(matricula_estudiante)
            
            if usuario_id:
                # Actualizar usuario en SQLite
                st.subheader("👤 Actualizando usuario en base de datos...")
                if self.actualizar_rol_usuario(usuario_id, 'egresado', matricula_egresado):
                    st.success("✅ Usuario actualizado exitosamente")
                else:
                    st.warning("⚠️ No se pudo actualizar usuario, continuando con migración")
            else:
                st.warning("⚠️ Usuario no encontrado, continuando con migración de datos")
            
            # 2. Renombrar archivos PDF
            st.subheader("📁 Renombrando archivos PDF...")
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_estudiante, matricula_egresado)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.info("📝 Modo simulación: Archivos PDF renombrados en simulación")
            
            # 3. Eliminar estudiante y crear egresado
            st.subheader("🔄 Procesando migración de datos...")
            
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
            self.db.registrar_bitacora(
                st.session_state.usuario_actual.get('usuario', 'admin'),
                'MIGRACION_ESTUDIANTE_EGRESADO',
                f'Usuario migrado de estudiante a egresado. Matrícula: {matricula_estudiante} -> {matricula_egresado}'
            )
            
            # Registrar migración exitosa
            estado_migracion.registrar_migracion()
            
            # Sincronizar cambios con servidor remoto
            if self.db.sincronizar_hacia_remoto():
                st.success("✅ Cambios sincronizados con servidor remoto")
            else:
                st.warning("⚠️ Cambios guardados localmente (modo sin sincronización)")
            
            st.success(f"🎉 ¡Migración completada exitosamente!")
            st.balloons()
            
            # Mostrar resumen final
            st.subheader("📊 Resumen Final de la Migración")
            st.success(f"✅ Matrícula actualizada: {matricula_estudiante} → {matricula_egresado}")
            st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
            st.success(f"✅ Registro creado en egresados")
            st.success(f"✅ Registro eliminado de estudiantes")
            
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
            
            # 1. Buscar usuario en base de datos
            st.subheader("🔍 Buscando usuario en base de datos...")
            usuario_id = self.buscar_usuario_por_matricula(matricula_egresado)
            
            if usuario_id:
                # Actualizar usuario en SQLite
                st.subheader("👤 Actualizando usuario en base de datos...")
                if self.actualizar_rol_usuario(usuario_id, 'contratado', matricula_contratado):
                    st.success("✅ Usuario actualizado exitosamente")
                else:
                    st.warning("⚠️ No se pudo actualizar usuario, continuando con migración")
            else:
                st.warning("⚠️ Usuario no encontrado, continuando con migración de datos")
            
            # 2. Renombrar archivos PDF
            st.subheader("📁 Renombrando archivos PDF...")
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_egresado, matricula_contratado)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.info("📝 Modo simulación: Archivos PDF renombrados en simulación")
            
            # 3. Eliminar egresado y crear contratado
            st.subheader("🔄 Procesando migración de datos...")
            
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
            self.db.registrar_bitacora(
                st.session_state.usuario_actual.get('usuario', 'admin'),
                'MIGRACION_EGRESADO_CONTRATADO',
                f'Usuario migrado de egresado a contratado. Matrícula: {matricula_egresado} -> {matricula_contratado}'
            )
            
            # Registrar migración exitosa
            estado_migracion.registrar_migracion()
            
            # Sincronizar cambios con servidor remoto
            if self.db.sincronizar_hacia_remoto():
                st.success("✅ Cambios sincronizados con servidor remoto")
            else:
                st.warning("⚠️ Cambios guardados localmente (modo sin sincronización)")
            
            st.success(f"🎉 ¡Migración completada exitosamente!")
            st.balloons()
            
            # Mostrar resumen final
            st.subheader("📊 Resumen Final de la Migración")
            st.success(f"✅ Matrícula actualizada: {matricula_egresado} → {matricula_contratado}")
            st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
            st.success(f"✅ Registro creado en contratados")
            st.success(f"✅ Registro eliminado de egresados")
            
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
# INTERFAZ PRINCIPAL DEL MIGRADOR
# =============================================================================

def mostrar_login_migracion():
    """Interfaz de login para el migrador"""
    st.title("🔄 Sistema Escuela Enfermería - Modo Migración SSH")
    st.markdown("---")
    
    # Información del estado
    if not estado_migracion.esta_inicializada():
        st.warning("""
        ⚠️ **Primer uso del sistema de migración**
        
        Para comenzar, necesitas inicializar la base de datos:
        
        1. Haz clic en **"Inicializar Base de Datos"** en el sidebar
        2. Se crearán todas las tablas necesarias para migración
        3. Se creará automáticamente el usuario administrador
        4. Podrás iniciar sesión con las credenciales por defecto
        """)
        
        st.info("""
        **Credenciales por defecto (se crearán automáticamente):**
        - 👤 Usuario: **admin**
        - 🔒 Contraseña: **Admin123!**
        """)
        
        return
    
    # Si ya está inicializada, mostrar formulario de login
    st.success("✅ Base de datos de migración lista. Puedes iniciar sesión.")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form_migracion"):
            st.subheader("Iniciar Sesión en Migrador")
            
            usuario = st.text_input("👤 Usuario", placeholder="admin", key="login_usuario_migracion")
            password = st.text_input("🔒 Contraseña", type="password", placeholder="Admin123!", key="login_password_migracion")
            
            login_button = st.form_submit_button("🚀 Ingresar al Migrador", use_container_width=True)

            if login_button:
                if usuario and password:
                    with st.spinner("Verificando credenciales..."):
                        if auth_migracion.verificar_login(usuario, password):
                            st.rerun()
                        else:
                            st.error("❌ Credenciales incorrectas")
                else:
                    st.warning("⚠️ Complete todos los campos")
            
            # Información de acceso
            with st.expander("ℹ️ Información de acceso para migración"):
                st.info("**Credenciales por defecto:**")
                st.info("👤 Usuario: admin")
                st.info("🔒 Contraseña: Admin123!")

def mostrar_interfaz_migracion():
    """Interfaz principal después del login en el migrador"""
    # Barra superior con información del usuario
    usuario_actual = st.session_state.usuario_actual
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
    
    with col1:
        st.title("🔄 Sistema Escuela Enfermería - Modo Migración SSH")
        nombre_usuario = usuario_actual.get('nombre_completo', usuario_actual.get('usuario', 'Usuario'))
        st.write(f"**👤 Administrador:** {nombre_usuario}")
    
    with col2:
        modo = estado_migracion.estado.get('modo_operacion', 'local')
        if modo == 'remoto':
            st.write("**🔗 Modo:** Remoto SSH")
        else:
            st.write("**💻 Modo:** Local")
    
    with col3:
        if st.button("🔄 Recargar Datos"):
            migrador.cargar_datos()
            st.rerun()
    
    with col4:
        if st.button("🚪 Cerrar Sesión"):
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
        
        # Opción para crear datos de demostración
        if st.button("📊 Crear inscrito de demostración"):
            try:
                # Crear un inscrito de ejemplo
                import random
                nombres = ["Ana García", "Carlos López", "María Rodríguez", "Juan Pérez"]
                programas = ["Especialidad en Enfermería Cardiovascular", "Licenciatura en Enfermería"]
                
                inscrito_ejemplo = {
                    'matricula': f'MAT-INS{random.randint(10000, 99999)}',
                    'nombre_completo': random.choice(nombres),
                    'email': f'ejemplo{random.randint(1, 100)}@email.com',
                    'telefono': f'55{random.randint(10000000, 99999999)}',
                    'programa_interes': random.choice(programas),
                    'fecha_registro': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'estatus': 'Pre-inscrito',
                    'folio': f'FOL-{datetime.now().strftime("%Y%m%d")}-{random.randint(100, 999)}'
                }
                
                st.session_state.inscrito_seleccionado = inscrito_ejemplo
                st.success("✅ Datos de demostración creados. Ahora puedes proceder con la migración.")
                st.rerun()
            except Exception as e:
                st.error(f"Error creando datos: {e}")
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
# FUNCIÓN PRINCIPAL
# =============================================================================

def main():
    """Función principal de la aplicación de migración"""
    
    # Sidebar con estado del sistema
    with st.sidebar:
        st.subheader("🔧 Estado del Sistema de Migración")
        
        # Estado de inicialización
        if estado_migracion.esta_inicializada():
            st.success("✅ Base de datos inicializada")
            fecha_inicializacion = estado_migracion.obtener_fecha_inicializacion()
            if fecha_inicializacion:
                st.caption(f"📅 Inicializada: {fecha_inicializacion.strftime('%Y-%m-%d %H:%M')}")
        else:
            st.warning("⚠️ Base de datos NO inicializada")
        
        # Modo de operación
        modo = estado_migracion.estado.get('modo_operacion', 'local')
        if modo == 'remoto':
            st.success("🔗 Modo remoto SSH")
            if gestor_remoto_migracion.config.get('remote_host'):
                st.caption(f"🌐 Servidor: {gestor_remoto_migracion.config['remote_host']}")
        else:
            st.info("💻 Modo local")
            st.caption("📍 Sin conexión SSH")
        
        # Estadísticas de migración
        st.subheader("📈 Estadísticas de Migración")
        migraciones = estado_migracion.estado.get('migraciones_realizadas', 0)
        st.metric("Migraciones realizadas", migraciones)
        
        # Botón para inicializar/reinicializar
        if not estado_migracion.esta_inicializada():
            if st.button("🔄 Inicializar Base de Datos", use_container_width=True, type="primary"):
                with st.spinner("Creando base de datos y tablas para migración..."):
                    if db_migracion.sincronizar_desde_remoto():
                        st.success("✅ Base de datos de migración inicializada")
                        st.rerun()
                    else:
                        st.error("❌ Error inicializando base de datos de migración")
        else:
            if st.button("🔄 Sincronizar Ahora", use_container_width=True):
                with st.spinner("Sincronizando base de datos de migración..."):
                    if db_migracion.sincronizar_desde_remoto():
                        st.success("✅ Sincronización exitosa")
                        st.rerun()
                    else:
                        st.error("❌ Error sincronizando")
            
            if st.button("📊 Verificar Tablas", use_container_width=True):
                try:
                    with db_migracion.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tablas = cursor.fetchall()
                        
                        if tablas:
                            st.success(f"✅ {len(tablas)} tablas encontradas:")
                            for tabla in tablas:
                                st.write(f"- {tabla[0]}")
                        else:
                            st.error("❌ No hay tablas")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
    
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
        main()
    except Exception as e:
        st.error(f"❌ Error crítico en la aplicación de migración: {e}")
        logger.error(f"Error crítico en migración: {e}", exc_info=True)
        
        # Información de diagnóstico
        with st.expander("🔧 Información de diagnóstico para migración"):
            st.write("**Estado persistente de migración:**")
            st.json(estado_migracion.estado)
            
            st.write("**Configuración SSH para migración:**")
            if gestor_remoto_migracion.config:
                st.json({k: '***' if 'password' in k else v for k, v in gestor_remoto_migracion.config.items()})
            else:
                st.write("No hay configuración SSH")
        
        # Botones de recuperación
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Reinicializar Sistema de Migración", use_container_width=True):
                try:
                    # Eliminar archivo de estado
                    if os.path.exists(estado_migracion.archivo_estado):
                        os.remove(estado_migracion.archivo_estado)
                    
                    # Crear nuevo estado
                    estado_migracion.estado = estado_migracion._estado_por_defecto()
                    estado_migracion.guardar_estado()
                    
                    st.success("✅ Sistema de migración reinicializado")
                    st.rerun()
                except Exception as e2:
                    st.error(f"❌ Error: {e2}")
        
        with col2:
            if st.button("🔄 Recargar Página", use_container_width=True):
                st.rerun()
