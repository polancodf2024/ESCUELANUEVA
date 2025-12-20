"""
escuela20.py - Sistema de Gestión Escuela de Enfermería
VERSIÓN CONEXIÓN DIRECTA A SERVIDOR REMOTO VIA SSH
Base de datos SQLite remota - VERSIÓN COMPLETA Y CORREGIDA
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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de página
st.set_page_config(
    page_title="Sistema Escuela Enfermería - Modo Supervisión",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# CONFIGURACIÓN SSH Y SISTEMA DE CONEXIÓN REMOTA
# =============================================================================

class GestorConexionRemota:
    """Gestor de conexión SSH al servidor remoto para acceso a base de datos SQLite"""
    
    def __init__(self):
        self.ssh = None
        self.sftp = None
        self.config = self._cargar_configuracion_ssh()
        self.db_path_remoto = "/home/POLANCO6/ESCUELA/datos/escuela.db"
        self.temp_db_path = None
        self.conexion_local = None
    
    def _cargar_configuracion_ssh(self):
        """Cargar configuración SSH desde secrets.toml"""
        try:
            return {
                'remote_host': st.secrets["remote_host"],
                'remote_port': int(st.secrets.get("remote_port")),
                'remote_user': st.secrets["remote_user"],
                'remote_password': st.secrets["remote_password"]
            }
        except Exception as e:
            logger.error(f"Error cargando configuración SSH: {e}")
            st.error("❌ Error en configuración SSH. Verifique secrets.toml")
            return {}
    
    def conectar_ssh(self):
        """Establecer conexión SSH con el servidor remoto"""
        try:
            if not self.config:
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
            st.error("❌ Error de autenticación SSH. Verifique usuario/contraseña")
            logger.error("Error de autenticación SSH")
            return False
        except paramiko.SSHException as e:
            st.error(f"❌ Error SSH: {e}")
            logger.error(f"Error SSH: {e}")
            return False
        except Exception as e:
            st.error(f"❌ Error de conexión SSH: {e}")
            logger.error(f"Error de conexión SSH: {e}")
            return False
    
    def desconectar_ssh(self):
        """Cerrar conexión SSH"""
        try:
            if self.sftp:
                self.sftp.close()
            if self.ssh:
                self.ssh.close()
            logger.info("🔌 Conexión SSH cerrada")
        except:
            pass
    
    def descargar_db_remota(self):
        """Descargar la base de datos SQLite del servidor remoto a local temporal"""
        try:
            if not self.conectar_ssh():
                return None
            
            # Crear archivo temporal local
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.temp_db_path = os.path.join(temp_dir, f"escuela_temp_{timestamp}.db")
            
            # Descargar archivo desde remoto
            self.sftp.get(self.db_path_remoto, self.temp_db_path)
            
            logger.info(f"✅ Base de datos descargada a: {self.temp_db_path}")
            return self.temp_db_path
            
        except Exception as e:
            logger.error(f"❌ Error descargando base de datos: {e}")
            st.error(f"❌ Error descargando base de datos: {e}")
            return None
        finally:
            self.desconectar_ssh()
    
    def subir_db_local(self, ruta_local):
        """Subir base de datos local al servidor remoto (sobreescribir)"""
        try:
            if not self.conectar_ssh():
                return False
            
            # Crear backup de la base de datos remota antes de sobreescribir
            try:
                backup_path = f"{self.db_path_remoto}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                self.sftp.rename(self.db_path_remoto, backup_path)
                logger.info(f"✅ Backup creado: {backup_path}")
            except:
                pass  # Si no se puede crear backup, continuar igual
            
            # Subir nuevo archivo
            self.sftp.put(ruta_local, self.db_path_remoto)
            
            logger.info(f"✅ Base de datos subida a servidor: {self.db_path_remoto}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error subiendo base de datos: {e}")
            st.error(f"❌ Error subiendo base de datos: {e}")
            return False
        finally:
            self.desconectar_ssh()
    
    def ejecutar_comando_remoto(self, comando):
        """Ejecutar comando en el servidor remoto"""
        try:
            if not self.conectar_ssh():
                return None
            
            stdin, stdout, stderr = self.ssh.exec_command(comando)
            salida = stdout.read().decode()
            error = stderr.read().decode()
            
            self.desconectar_ssh()
            
            if error:
                logger.warning(f"⚠️ Error ejecutando comando remoto: {error}")
            
            return salida
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando comando remoto: {e}")
            return None
    
    def verificar_conexion(self):
        """Verificar que la conexión SSH funcione"""
        try:
            if self.conectar_ssh():
                self.desconectar_ssh()
                return True, "✅ Conexión SSH establecida correctamente"
            else:
                return False, "❌ No se pudo establecer conexión SSH"
        except Exception as e:
            return False, f"❌ Error: {e}"

# Instancia global del gestor de conexión remota
gestor_remoto = GestorConexionRemota()

# =============================================================================
# SISTEMA DE BASE DE DATOS SQLITE REMOTA - COMPLETO
# =============================================================================

class SistemaBaseDatosRemota:
    """Sistema de base de datos SQLite con sincronización remota via SSH"""
    
    def __init__(self):
        self.gestor = gestor_remoto
        self.db_local_temp = None
        self.conexion_actual = None
        self.ultima_sincronizacion = None
        
    def sincronizar_desde_remoto(self):
        """Sincronizar base de datos desde el servidor remoto"""
        with st.spinner("🌐 Sincronizando con servidor remoto..."):
            try:
                # 1. Descargar base de datos remota
                self.db_local_temp = self.gestor.descargar_db_remota()
                
                if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                    st.error("❌ No se pudo descargar la base de datos remota")
                    return False
                
                # 2. Verificar que el archivo es una base de datos SQLite válida
                try:
                    conn = sqlite3.connect(self.db_local_temp)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tablas = cursor.fetchall()
                    conn.close()
                    
                    if len(tablas) == 0:
                        logger.warning("⚠️ Base de datos vacía o corrupta")
                        # Inicializar estructura si está vacía
                        self._inicializar_estructura_db()
                except Exception as e:
                    logger.error(f"❌ Base de datos corrupta: {e}")
                    st.error("La base de datos remota está corrupta. Se creará una nueva.")
                    self._crear_nueva_db()
                
                self.ultima_sincronizacion = datetime.now()
                logger.info(f"✅ Sincronización exitosa: {len(tablas) if 'tablas' in locals() else 'N/A'} tablas")
                return True
                
            except Exception as e:
                logger.error(f"❌ Error en sincronización: {e}")
                st.error(f"❌ Error sincronizando con servidor remoto: {e}")
                return False
    
    def sincronizar_hacia_remoto(self):
        """Sincronizar base de datos local hacia el servidor remoto"""
        with st.spinner("🔄 Subiendo cambios al servidor..."):
            try:
                if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                    st.error("❌ No hay base de datos local para subir")
                    return False
                
                # Subir al servidor remoto
                exito = self.gestor.subir_db_local(self.db_local_temp)
                
                if exito:
                    self.ultima_sincronizacion = datetime.now()
                    logger.info("✅ Cambios subidos exitosamente al servidor")
                    return True
                else:
                    return False
                    
            except Exception as e:
                logger.error(f"❌ Error subiendo cambios: {e}")
                st.error(f"❌ Error subiendo cambios al servidor: {e}")
                return False
    
    def _crear_nueva_db(self):
        """Crear una nueva base de datos si no existe"""
        try:
            # Usar un archivo temporal nuevo
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.db_local_temp = os.path.join(temp_dir, f"escuela_nueva_{timestamp}.db")
            
            # Crear estructura inicial
            self._inicializar_estructura_db()
            
            logger.info(f"✅ Nueva base de datos creada: {self.db_local_temp}")
            return True
        except Exception as e:
            logger.error(f"❌ Error creando nueva base de datos: {e}")
            return False
    
    def _inicializar_estructura_db(self):
        """Inicializar estructura de la base de datos"""
        try:
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
                except:
                    pass
            
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
            
            conn.commit()
            conn.close()
            logger.info("✅ Estructura de base de datos inicializada")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura: {e}")
            raise
    
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
                # Sincronizar cambios con servidor remoto automáticamente
                self.sincronizar_hacia_remoto()
                
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
                return pd.read_sql_query(query, conn)
        except Exception as e:
            logger.error(f"Error obteniendo inscritos: {e}")
            return pd.DataFrame()
    
    def obtener_estudiantes(self):
        """Obtener todos los estudiantes"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM estudiantes ORDER BY fecha_ingreso DESC"
                return pd.read_sql_query(query, conn)
        except Exception as e:
            logger.error(f"Error obteniendo estudiantes: {e}")
            return pd.DataFrame()
    
    def obtener_egresados(self):
        """Obtener todos los egresados"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM egresados ORDER BY fecha_graduacion DESC"
                return pd.read_sql_query(query, conn)
        except Exception as e:
            logger.error(f"Error obteniendo egresados: {e}")
            return pd.DataFrame()
    
    def obtener_contratados(self):
        """Obtener todos los contratados"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM contratados ORDER BY fecha_contratacion DESC"
                return pd.read_sql_query(query, conn)
        except Exception as e:
            logger.error(f"Error obteniendo contratados: {e}")
            return pd.DataFrame()
    
    def obtener_usuarios(self):
        """Obtener todos los usuarios"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM usuarios ORDER BY fecha_creacion DESC"
                return pd.read_sql_query(query, conn)
        except Exception as e:
            logger.error(f"Error obteniendo usuarios: {e}")
            return pd.DataFrame()
    
    def obtener_programas(self):
        """Obtener todos los programas"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM programas ORDER BY nombre"
                return pd.read_sql_query(query, conn)
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
        logger.info("✅ Base de datos remota inicializada correctamente")
    else:
        logger.warning("⚠️ No se pudo sincronizar inicialmente")
except Exception as e:
    logger.error(f"❌ Error inicializando base de datos remota: {e}")

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
            return {
                'smtp_server': st.secrets.get("smtp_server", "smtp.gmail.com"),
                'smtp_port': st.secrets.get("smtp_port", 587),
                'email_user': st.secrets.get("email_user", ""),
                'email_password': st.secrets.get("email_password", ""),
                'notification_email': st.secrets.get("notification_email", "")
            }
        except Exception as e:
            st.error(f"Error al cargar configuración de email: {e}")
            return {}
    
    def verificar_configuracion_email(self):
        """Verificar que la configuración de email esté completa"""
        try:
            config = self.obtener_configuracion_email()
            email_user = config.get('email_user', '')
            email_password = config.get('email_password', '')
            notification_email = config.get('notification_email', '')
            
            if not email_user:
                st.error("❌ No se encontró 'email_user' en los secrets")
                return False
                
            if not email_password:
                st.error("❌ No se encontró 'email_password' en los secrets")
                return False
                
            if not notification_email:
                st.error("❌ No se encontró 'notification_email' en los secrets")
                return False
                
            st.success("✅ Configuración de email encontrada en secrets")
            st.info(f"📧 Remitente: {email_user}")
            st.info(f"📧 Email de notificación: {notification_email}")
            return True
            
        except Exception as e:
            st.error(f"❌ Error verificando configuración: {e}")
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
            msg['Cc'] = config['notification_email']  # AGREGAR COPIA AL EMAIL DE NOTIFICACIÓN
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
                                • Copia enviada a: {config['notification_email']}
                            </p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(cuerpo_html, 'html'))
            
            # Enviar email con timeout - INCLUYENDO EL EMAIL DE NOTIFICACIÓN EN LOS DESTINATARIOS
            destinatarios = [email_destino, config['notification_email']]
            
            server.sendmail(config['email_user'], destinatarios, msg.as_string())
            server.quit()
            
            st.success(f"✅ Email de confirmación enviado exitosamente a: {email_destino}")
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
# INTERFACES POR ROL - COMPLETAS
# =============================================================================

def mostrar_interfaz_inscrito():
    """Interfaz para usuarios con rol 'inscrito'"""
    st.title("🎓 Portal del Inscrito")
    
    # Obtener datos del usuario actual
    usuario_actual = st.session_state.usuario_actual
    matricula = usuario_actual.get('matricula', usuario_actual.get('usuario', ''))
    
    if not matricula:
        st.error("❌ No se pudo identificar tu matrícula")
        return
    
    # Buscar datos del inscrito
    inscrito = db_remota.buscar_inscrito_por_matricula(matricula)
    
    if not inscrito:
        st.error("❌ No se encontraron tus datos como inscrito")
        return
    
    # Mostrar información personal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("👤 Información Personal")
        
        campos_inscritos = ['matricula', 'nombre_completo', 'email', 'telefono',
                           'programa_interes', 'fecha_registro', 'estatus',
                           'fecha_nacimiento', 'como_se_entero']
        
        for campo in campos_inscritos:
            if campo in inscrito and inscrito[campo]:
                nombre_campo = campo.replace('_', ' ').title()
                st.write(f"**{nombre_campo}:** {inscrito[campo]}")
    
    with col2:
        st.subheader("📊 Estado")
        st.success("✅ Inscrito")
        if 'estatus' in inscrito:
            st.write(f"**Estatus:** {inscrito['estatus']}")
        
        # Mostrar documentos subidos
        if inscrito.get('documentos_subidos', 0) > 0:
            st.info(f"📄 Documentos subidos: {inscrito['documentos_subidos']}")
    
    # SECCIÓN DE EDICIÓN
    st.markdown("---")
    st.subheader("✏️ Actualizar Información Personal")
    
    with st.form("editar_datos_inscrito"):
        col1, col2 = st.columns(2)
        
        with col1:
            nuevo_nombre = st.text_input("Nombre completo", value=inscrito.get('nombre_completo', ''))
            nuevo_email = st.text_input("Correo electrónico", value=inscrito.get('email', ''))
            nuevo_telefono = st.text_input("Teléfono", value=inscrito.get('telefono', ''))
        
        with col2:
            nuevo_programa = st.text_input("Programa de interés", value=inscrito.get('programa_interes', ''))
            # Manejar fecha de nacimiento
            fecha_nac_original = inscrito.get('fecha_nacimiento')
            if fecha_nac_original:
                try:
                    fecha_nac_date = datetime.strptime(fecha_nac_original, '%Y-%m-%d').date()
                except:
                    fecha_nac_date = datetime.now().date()
            else:
                fecha_nac_date = datetime.now().date()
            
            nueva_fecha_nacimiento = st.date_input("Fecha de nacimiento", value=fecha_nac_date)
            nuevo_como_se_entero = st.selectbox("¿Cómo se enteró?", 
                                              ["Internet", "Recomendación", "Medios", "Evento", "Redes Sociales", "Otro"],
                                              index=0)
            # Establecer índice correcto
            opciones = ["Internet", "Recomendación", "Medios", "Evento", "Redes Sociales", "Otro"]
            if inscrito.get('como_se_entero') in opciones:
                nuevo_como_se_entero = st.selectbox("¿Cómo se enteró?", opciones,
                                                  index=opciones.index(inscrito.get('como_se_entero')))
            else:
                nuevo_como_se_entero = st.selectbox("¿Cómo se enteró?", opciones)
        
        if st.form_submit_button("💾 Guardar Cambios"):
            cambios = {}
            
            if nuevo_nombre != inscrito.get('nombre_completo'):
                cambios['nombre_completo'] = nuevo_nombre
            if nuevo_email != inscrito.get('email'):
                cambios['email'] = nuevo_email
            if nuevo_telefono != inscrito.get('telefono'):
                cambios['telefono'] = nuevo_telefono
            if nuevo_programa != inscrito.get('programa_interes'):
                cambios['programa_interes'] = nuevo_programa
            if str(nueva_fecha_nacimiento) != inscrito.get('fecha_nacimiento'):
                cambios['fecha_nacimiento'] = str(nueva_fecha_nacimiento)
            if nuevo_como_se_entero != inscrito.get('como_se_entero'):
                cambios['como_se_entero'] = nuevo_como_se_entero
            
            if cambios:
                if db_remota.actualizar_inscrito(matricula, cambios):
                    st.success("✅ Cambios guardados exitosamente")
                    st.rerun()
                else:
                    st.error("❌ Error al guardar los cambios")
            else:
                st.info("ℹ️ No se realizaron cambios")
    
    # Gestión de documentos
    st.markdown("---")
    st.subheader("📁 Gestión de Documentos")
    
    documentos_requeridos = [
        "CURP",
        "Acta de Nacimiento", 
        "Comprobante de Estudios",
        "Fotografías Tamaño Infantil",
        "Comprobante de Domicilio"
    ]
    
    st.write("**Documentos requeridos:**")
    for i, doc in enumerate(documentos_requeridos, 1):
        st.write(f"{i}. {doc}")
    
    # Subir documentos
    st.subheader("📤 Subir Documentos")
    
    tipo_documento = st.selectbox("Selecciona el tipo de documento:", documentos_requeridos)
    archivo = st.file_uploader("Selecciona el archivo:", type=['pdf', 'jpg', 'jpeg', 'png'])
    
    if archivo is not None and tipo_documento:
        if st.button("📤 Subir Documento"):
            # Aquí iría la lógica para subir documentos al servidor remoto
            st.info("📤 Función de subida de documentos en desarrollo")
            # Nota: Se necesitaría implementar la subida via SFTP similar a escuela10.py

def mostrar_interfaz_estudiante():
    """Interfaz para usuarios con rol 'estudiante'"""
    st.title("🎓 Portal del Estudiante")
    
    usuario_actual = st.session_state.usuario_actual
    matricula = usuario_actual.get('matricula', usuario_actual.get('usuario', ''))
    
    if not matricula:
        st.error("❌ No se pudo identificar tu matrícula")
        return
    
    estudiante = db_remota.buscar_estudiante_por_matricula(matricula)
    
    if not estudiante:
        st.error("❌ No se encontraron tus datos como estudiante")
        return
    
    # Mostrar información académica
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("👤 Información Académica")
        
        campos_estudiantes = ['matricula', 'nombre_completo', 'programa', 'email', 
                             'telefono', 'fecha_nacimiento', 'genero', 'estatus', 'fecha_ingreso']
        
        for campo in campos_estudiantes:
            if campo in estudiante and estudiante[campo]:
                nombre_campo = campo.replace('_', ' ').title()
                st.write(f"**{nombre_campo}:** {estudiante[campo]}")
    
    with col2:
        st.subheader("📊 Estado Académico")
        st.success("✅ Estudiante Activo")
        if 'estatus' in estudiante:
            st.write(f"**Estatus:** {estudiante['estatus']}")
    
    # Edición de datos
    st.markdown("---")
    st.subheader("✏️ Actualizar Información Académica")
    
    with st.form("editar_datos_estudiante"):
        col1, col2 = st.columns(2)
        
        with col1:
            nuevo_nombre = st.text_input("Nombre completo", value=estudiante.get('nombre_completo', ''))
            nuevo_email = st.text_input("Correo electrónico", value=estudiante.get('email', ''))
            nuevo_telefono = st.text_input("Teléfono", value=estudiante.get('telefono', ''))
        
        with col2:
            nuevo_programa = st.text_input("Programa", value=estudiante.get('programa', ''))
            nuevo_genero = st.selectbox("Género", ["Masculino", "Femenino", "Otro", "Prefiero no decir"],
                                      index=0)
            # Establecer índice correcto
            opciones_genero = ["Masculino", "Femenino", "Otro", "Prefiero no decir"]
            if estudiante.get('genero') in opciones_genero:
                nuevo_genero = st.selectbox("Género", opciones_genero,
                                          index=opciones_genero.index(estudiante.get('genero')))
            
            nuevo_estatus = st.selectbox("Estatus", ["Activo", "Inactivo", "Graduado"],
                                       index=0)
            # Establecer índice correcto
            opciones_estatus = ["Activo", "Inactivo", "Graduado"]
            if estudiante.get('estatus') in opciones_estatus:
                nuevo_estatus = st.selectbox("Estatus", opciones_estatus,
                                           index=opciones_estatus.index(estudiante.get('estatus')))
        
        if st.form_submit_button("💾 Guardar Cambios"):
            cambios = {}
            
            if nuevo_nombre != estudiante.get('nombre_completo'):
                cambios['nombre_completo'] = nuevo_nombre
            if nuevo_email != estudiante.get('email'):
                cambios['email'] = nuevo_email
            if nuevo_telefono != estudiante.get('telefono'):
                cambios['telefono'] = nuevo_telefono
            if nuevo_programa != estudiante.get('programa'):
                cambios['programa'] = nuevo_programa
            if nuevo_genero != estudiante.get('genero'):
                cambios['genero'] = nuevo_genero
            if nuevo_estatus != estudiante.get('estatus'):
                cambios['estatus'] = nuevo_estatus
            
            if cambios:
                if db_remota.actualizar_estudiante(matricula, cambios):
                    st.success("✅ Cambios guardados exitosamente")
                    st.rerun()
                else:
                    st.error("❌ Error al guardar los cambios")
            else:
                st.info("ℹ️ No se realizaron cambios")

def mostrar_interfaz_egresado():
    """Interfaz para usuarios con rol 'egresado'"""
    st.title("🎓 Portal del Egresado")
    
    usuario_actual = st.session_state.usuario_actual
    matricula = usuario_actual.get('matricula', usuario_actual.get('usuario', ''))
    
    if not matricula:
        st.error("❌ No se pudo identificar tu matrícula")
        return
    
    egresado = db_remota.buscar_egresado_por_matricula(matricula)
    
    if not egresado:
        st.error("❌ No se encontraron tus datos como egresado")
        return
    
    # Mostrar información profesional
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("👤 Información Profesional")
        
        campos_egresados = ['matricula', 'nombre_completo', 'programa_original',
                           'fecha_graduacion', 'nivel_academico', 'email', 'telefono',
                           'estado_laboral']
        
        for campo in campos_egresados:
            if campo in egresado and egresado[campo]:
                nombre_campo = campo.replace('_', ' ').title()
                st.write(f"**{nombre_campo}:** {egresado[campo]}")
    
    with col2:
        st.subheader("📊 Estado Profesional")
        st.success("✅ Egresado")
        if 'estado_laboral' in egresado:
            st.write(f"**Estado Laboral:** {egresado['estado_laboral']}")
    
    # Información de actualización
    if 'fecha_actualizacion' in egresado:
        st.info(f"📅 Última actualización: {egresado['fecha_actualizacion']}")

def mostrar_interfaz_contratado():
    """Interfaz para usuarios con rol 'contratado'"""
    st.title("💼 Portal del Personal Contratado")
    
    usuario_actual = st.session_state.usuario_actual
    matricula = usuario_actual.get('matricula', usuario_actual.get('usuario', ''))
    
    if not matricula:
        st.error("❌ No se pudo identificar tu matrícula")
        return
    
    contratado = db_remota.buscar_contratado_por_matricula(matricula)
    
    if not contratado:
        st.error("❌ No se encontraron tus datos como contratado")
        return
    
    # Mostrar información laboral
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("👤 Información Laboral")
        
        campos_contratados = ['matricula', 'fecha_contratacion', 'puesto', 'departamento',
                             'estatus', 'salario', 'tipo_contrato', 'fecha_inicio']
        
        for campo in campos_contratados:
            if campo in contratado and contratado[campo]:
                nombre_campo = campo.replace('_', ' ').title()
                st.write(f"**{nombre_campo}:** {contratado[campo]}")
    
    with col2:
        st.subheader("📊 Estado Laboral")
        st.success("✅ Contratado Activo")
        if 'estatus' in contratado:
            st.write(f"**Estatus:** {contratado['estatus']}")

# =============================================================================
# INTERFAZ DE ADMINISTRADOR - COMPLETA
# =============================================================================

def mostrar_interfaz_administrador():
    """Interfaz para usuarios con rol 'administrador'"""
    st.title("⚙️ Panel de Administración")
    
    # Verificar permisos
    if not st.session_state.login_exitoso or st.session_state.usuario_actual.get('rol') != 'administrador':
        st.error("❌ No tienes permisos de administrador")
        return
    
    # Menú de administración
    opcion = st.sidebar.selectbox(
        "Menú de Administración",
        [
            "📊 Dashboard General",
            "👥 Gestión de Usuarios", 
            "📝 Gestión de Inscritos",
            "🎓 Gestión de Estudiantes",
            "🎓 Gestión de Egresados",
            "💼 Gestión de Contratados",
            "📧 Configuración de Email",
            "🔧 Herramientas del Sistema"
        ]
    )
    
    if opcion == "📊 Dashboard General":
        mostrar_dashboard_administrador()
    elif opcion == "👥 Gestión de Usuarios":
        mostrar_gestion_usuarios()
    elif opcion == "📝 Gestión de Inscritos":
        mostrar_gestion_inscritos()
    elif opcion == "🎓 Gestión de Estudiantes":
        mostrar_gestion_estudiantes()
    elif opcion == "🎓 Gestión de Egresados":
        mostrar_gestion_egresados()
    elif opcion == "💼 Gestión de Contratados":
        mostrar_gestion_contratados()
    elif opcion == "📧 Configuración de Email":
        mostrar_configuracion_email()
    elif opcion == "🔧 Herramientas del Sistema":
        mostrar_herramientas_sistema()

def mostrar_dashboard_administrador():
    """Dashboard general para administradores"""
    st.subheader("📊 Dashboard General")
    
    # Sincronizar datos primero
    with st.spinner("🔄 Sincronizando datos..."):
        datos = cargar_datos_completos()
    
    # Métricas generales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_inscritos = len(datos['inscritos']) if not datos['inscritos'].empty else 0
        st.metric("Total Inscritos", total_inscritos)
    
    with col2:
        total_estudiantes = len(datos['estudiantes']) if not datos['estudiantes'].empty else 0
        st.metric("Total Estudiantes", total_estudiantes)
    
    with col3:
        total_egresados = len(datos['egresados']) if not datos['egresados'].empty else 0
        st.metric("Total Egresados", total_egresados)
    
    with col4:
        total_contratados = len(datos['contratados']) if not datos['contratados'].empty else 0
        st.metric("Total Contratados", total_contratados)
    
    # Estado del sistema
    st.subheader("🔧 Estado del Sistema")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Verificar conexión SSH
        conexion_ok, mensaje = gestor_remoto.verificar_conexion()
        if conexion_ok:
            st.success("✅ Conexión SSH: Activa")
        else:
            st.error(f"❌ Conexión SSH: {mensaje}")
        
        # Verificar email
        estado_email, mensaje_email = sistema_email.test_conexion_smtp()
        if estado_email:
            st.success(f"📧 Email: {mensaje_email}")
        else:
            st.warning(f"📧 Email: {mensaje_email}")
    
    with col2:
        # Última sincronización
        if db_remota.ultima_sincronizacion:
            st.info(f"🔄 Última sincronización: {db_remota.ultima_sincronizacion.strftime('%H:%M:%S')}")
        else:
            st.warning("🔄 Última sincronización: Nunca")
        
        # Botón para sincronizar manualmente
        if st.button("🔄 Sincronizar Ahora", use_container_width=True):
            if db_remota.sincronizar_desde_remoto():
                st.success("✅ Sincronización exitosa")
                st.rerun()
    
    # Tablas de datos recientes
    st.subheader("📋 Datos Recientes")
    
    tab1, tab2, tab3 = st.tabs(["Inscritos", "Estudiantes", "Usuarios"])
    
    with tab1:
        if not datos['inscritos'].empty:
            st.dataframe(datos['inscritos'].head(10), use_container_width=True)
        else:
            st.info("No hay inscritos")
    
    with tab2:
        if not datos['estudiantes'].empty:
            st.dataframe(datos['estudiantes'].head(10), use_container_width=True)
        else:
            st.info("No hay estudiantes")
    
    with tab3:
        if not datos['usuarios'].empty:
            st.dataframe(datos['usuarios'].head(10), use_container_width=True)
        else:
            st.info("No hay usuarios")

def mostrar_gestion_usuarios():
    """Gestión de usuarios para administradores"""
    st.subheader("👥 Gestión de Usuarios")
    
    datos = cargar_datos_completos()
    df_usuarios = datos['usuarios']
    
    if df_usuarios.empty:
        st.info("📭 No hay usuarios registrados")
        return
    
    # Mostrar tabla de usuarios
    st.dataframe(df_usuarios[['usuario', 'nombre_completo', 'rol', 'matricula', 'email', 'activo']], 
                 use_container_width=True)
    
    # Opciones de gestión
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Agregar Usuario")
        with st.form("agregar_usuario"):
            nuevo_usuario = st.text_input("Usuario")
            nueva_contraseña = st.text_input("Contraseña", type="password")
            nuevo_rol = st.selectbox("Rol", ["inscrito", "estudiante", "egresado", "contratado", "administrador"])
            nuevo_email = st.text_input("Email")
            nuevo_nombre = st.text_input("Nombre completo")
            nueva_matricula = st.text_input("Matrícula")
            
            if st.form_submit_button("➕ Agregar Usuario"):
                if not nuevo_usuario or not nueva_contraseña or not nuevo_rol:
                    st.warning("⚠️ Usuario, contraseña y rol son obligatorios")
                else:
                    # Crear hash de contraseña
                    password_hash, salt = db_remota.hash_password(nueva_contraseña)
                    
                    # Insertar en base de datos
                    try:
                        usuario_id = db_remota.agregar_usuario({
                            'usuario': nuevo_usuario,
                            'password_hash': password_hash,
                            'salt': salt,
                            'rol': nuevo_rol,
                            'nombre_completo': nuevo_nombre,
                            'email': nuevo_email,
                            'matricula': nueva_matricula,
                            'activo': 1
                        })
                        
                        if usuario_id:
                            st.success(f"✅ Usuario {nuevo_usuario} agregado exitosamente")
                            st.rerun()
                        else:
                            st.error("❌ Error al agregar usuario")
                    except Exception as e:
                        st.error(f"❌ Error agregando usuario: {e}")

def mostrar_gestion_inscritos():
    """Gestión de inscritos"""
    st.subheader("📝 Gestión de Inscritos")
    
    datos = cargar_datos_completos()
    df_inscritos = datos['inscritos']
    
    if df_inscritos.empty:
        st.info("📭 No hay inscritos registrados")
        return
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        filtro_estatus = st.selectbox("Filtrar por estatus", 
                                    ["Todos"] + list(df_inscritos['estatus'].unique()))
    with col2:
        filtro_programa = st.selectbox("Filtrar por programa",
                                     ["Todos"] + list(df_inscritos['programa_interes'].unique()))
    with col3:
        buscar = st.text_input("🔍 Buscar por nombre o matrícula")
    
    # Aplicar filtros
    df_filtrado = df_inscritos.copy()
    if filtro_estatus != "Todos":
        df_filtrado = df_filtrado[df_filtrado['estatus'] == filtro_estatus]
    if filtro_programa != "Todos":
        df_filtrado = df_filtrado[df_filtrado['programa_interes'] == filtro_programa]
    if buscar:
        mask = df_filtrado['nombre_completo'].str.contains(buscar, case=False) | \
               df_filtrado['matricula'].str.contains(buscar, case=False)
        df_filtrado = df_filtrado[mask]
    
    # Mostrar datos
    st.dataframe(df_filtrado, use_container_width=True)
    
    # Estadísticas
    st.info(f"📊 Mostrando {len(df_filtrado)} de {len(df_inscritos)} inscritos")

def mostrar_gestion_estudiantes():
    """Gestión de estudiantes"""
    st.subheader("🎓 Gestión de Estudiantes")
    
    datos = cargar_datos_completos()
    df_estudiantes = datos['estudiantes']
    
    if df_estudiantes.empty:
        st.info("📭 No hay estudiantes registrados")
        return
    
    st.dataframe(df_estudiantes, use_container_width=True)

def mostrar_gestion_egresados():
    """Gestión de egresados"""
    st.subheader("🎓 Gestión de Egresados")
    
    datos = cargar_datos_completos()
    df_egresados = datos['egresados']
    
    if df_egresados.empty:
        st.info("📭 No hay egresados registrados")
        return
    
    st.dataframe(df_egresados, use_container_width=True)

def mostrar_gestion_contratados():
    """Gestión de contratados"""
    st.subheader("💼 Gestión de Contratados")
    
    datos = cargar_datos_completos()
    df_contratados = datos['contratados']
    
    if df_contratados.empty:
        st.info("📭 No hay contratados registrados")
        return
    
    st.dataframe(df_contratados, use_container_width=True)

def mostrar_configuracion_email():
    """Configuración del sistema de email"""
    st.subheader("📧 Configuración del Sistema de Email")
    
    st.write("### 🔍 Verificación de Configuración Actual")
    
    config_ok = sistema_email.verificar_configuracion_email()
    
    if config_ok:
        st.success("✅ Configuración de email encontrada en secrets.toml")
        
        # Probar conexión SMTP
        st.write("### 🧪 Probar Conexión SMTP")
        if st.button("🔍 Probar Conexión"):
            with st.spinner("Probando conexión SMTP..."):
                exito, mensaje = sistema_email.test_conexion_smtp()
                if exito:
                    st.success(mensaje)
                else:
                    st.error(mensaje)
    else:
        st.error("❌ Configuración de email incompleta o incorrecta")

def mostrar_herramientas_sistema():
    """Herramientas del sistema"""
    st.subheader("🔧 Herramientas del Sistema")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**🔄 Sincronización**")
        if st.button("Sincronizar con Servidor Remoto", use_container_width=True):
            if db_remota.sincronizar_desde_remoto():
                st.success("✅ Sincronización exitosa")
            else:
                st.error("❌ Error en sincronización")
        
        st.write("**📊 Base de Datos**")
        if st.button("Verificar Integridad BD", use_container_width=True):
            try:
                with db_remota.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tablas = cursor.fetchall()
                    st.success(f"✅ Base de datos OK. Tablas: {len(tablas)}")
                    for tabla in tablas:
                        st.write(f"- {tabla[0]}")
            except Exception as e:
                st.error(f"❌ Error: {e}")
    
    with col2:
        st.write("**📤 Exportación**")
        if st.button("Exportar Inscritos a CSV", use_container_width=True):
            datos = cargar_datos_completos()
            if not datos['inscritos'].empty:
                csv = datos['inscritos'].to_csv(index=False)
                st.download_button(
                    label="⬇️ Descargar CSV",
                    data=csv,
                    file_name=f"inscritos_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
            else:
                st.warning("No hay datos para exportar")
        
        st.write("**🗑️ Limpieza**")
        if st.button("Limpiar Caché Local", use_container_width=True):
            try:
                if db_remota.temp_db_path and os.path.exists(db_remota.temp_db_path):
                    os.remove(db_remota.temp_db_path)
                    st.success("✅ Caché local limpiado")
                else:
                    st.info("No hay caché local para limpiar")
            except Exception as e:
                st.error(f"❌ Error: {e}")

# =============================================================================
# FUNCIONES DE CARGA DE DATOS - COMPLETAS
# =============================================================================

def cargar_datos_completos():
    """Cargar todos los datos desde la base de datos remota"""
    with st.spinner("📊 Cargando datos desde servidor remoto..."):
        try:
            datos = {
                'inscritos': db_remota.obtener_inscritos(),
                'estudiantes': db_remota.obtener_estudiantes(),
                'egresados': db_remota.obtener_egresados(),
                'contratados': db_remota.obtener_contratados(),
                'usuarios': db_remota.obtener_usuarios(),
                'programas': db_remota.obtener_programas()
            }
            
            total_registros = sum(len(df) for df in datos.values() if isinstance(df, pd.DataFrame))
            if total_registros > 0:
                logger.info(f"✅ {total_registros} registros cargados desde remoto")
            
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
# INTERFAZ DE LOGIN MEJORADA - COMPLETA
# =============================================================================

def mostrar_login():
    """Interfaz de login - CON ESTADO DE CONEXIÓN REMOTA"""
    st.title("🔐 Sistema Escuela Enfermería - Modo Supervisión Remota")
    st.markdown("---")

    # Estado de la conexión remota
    with st.expander("🌐 Estado de la Conexión Remota", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Probar conexión SSH
            if st.button("🔗 Probar Conexión SSH"):
                conexion_ok, mensaje = gestor_remoto.verificar_conexion()
                if conexion_ok:
                    st.success(mensaje)
                else:
                    st.error(mensaje)
        
        with col2:
            # Última sincronización
            if db_remota.ultima_sincronizacion:
                st.info(f"🔄 Última sinc: {db_remota.ultima_sincronizacion.strftime('%H:%M:%S')}")
            else:
                st.warning("🔄 Nunca sincronizado")
        
        with col3:
            # Sincronizar ahora
            if st.button("🔄 Sincronizar Ahora"):
                if db_remota.sincronizar_desde_remoto():
                    st.success("✅ Sincronización exitosa")
                else:
                    st.error("❌ Error en sincronización")
        
        # Cargar y mostrar estadísticas rápidas
        datos = cargar_datos_completos()
        
        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
        with col_stat1:
            ins = len(datos['inscritos'])
            st.metric("Inscritos", f"{'✅' if ins > 0 else '❌'} {ins}")
        with col_stat2:
            est = len(datos['estudiantes'])
            st.metric("Estudiantes", f"{'✅' if est > 0 else '❌'} {est}")
        with col_stat3:
            egr = len(datos['egresados'])
            st.metric("Egresados", f"{'✅' if egr > 0 else '❌'} {egr}")
        with col_stat4:
            con = len(datos['contratados'])
            st.metric("Contratados", f"{'✅' if con > 0 else '❌'} {con}")

    # Diagnóstico de email
    with st.expander("🔧 Diagnóstico del Sistema de Email", expanded=False):
        st.write("### 🔍 Verificación de Configuración")
        config_ok = sistema_email.verificar_configuracion_email()
        
        if config_ok:
            st.success("✅ Configuración de email encontrada")
            if st.button("🧪 Probar Conexión SMTP"):
                exito, mensaje = sistema_email.test_conexion_smtp()
                if exito:
                    st.success(mensaje)
                else:
                    st.error(mensaje)
        else:
            st.error("❌ Configuración de email incompleta")

    # Formulario de login
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            st.subheader("Iniciar Sesión")
            usuario = st.text_input("👤 Usuario", placeholder="admin")
            password = st.text_input("🔒 Contraseña", type="password", placeholder="Admin123!")
            login_button = st.form_submit_button("🚀 Ingresar al Sistema", use_container_width=True)

            if login_button:
                if usuario and password:
                    with st.spinner("Verificando credenciales..."):
                        if auth.verificar_login(usuario, password):
                            st.rerun()
                        else:
                            st.error("❌ Credenciales incorrectas")
                else:
                    st.warning("⚠️ Complete todos los campos")
            
            # Información de acceso por defecto
            st.info("**Credenciales por defecto:**")
            st.info("👤 Usuario: admin")
            st.info("🔒 Contraseña: Admin123!")

# =============================================================================
# FUNCIÓN PRINCIPAL - COMPLETA
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
    
    # Mostrar interfaz según estado de login
    if not st.session_state.login_exitoso:
        mostrar_login()
    else:
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
# EJECUCIÓN PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"❌ Error crítico en la aplicación: {e}")
        logger.error(f"Error crítico: {e}", exc_info=True)
        
        # Botón de recuperación
        if st.button("🔄 Reintentar Conexión"):
            try:
                db_remota.sincronizar_desde_remoto()
                st.rerun()
            except:
                st.error("No se pudo recuperar la conexión")
