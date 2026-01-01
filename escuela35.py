"""
escuela35.py - Sistema Escuela Enfermería 100% REMOTO
Versión unificada para trabajar con UNA SOLA base de datos
Configuración optimizada para secrets.toml unificado
VERSIÓN COMPLETA CON TODAS LAS FUNCIONALIDADES
"""

# =============================================================================
# 1. CONFIGURACIÓN Y UTILIDADES
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
import socket
import re
import glob
import atexit
import math
import psutil
from typing import Optional, Dict, Any, List, Tuple
import calendar
import random
import string
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

# =============================================================================
# 1.1 LOGGING MEJORADO
# =============================================================================

class EnhancedLogger:
    """Logger optimizado que evita crear múltiples handlers"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EnhancedLogger, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.logger = logging.getLogger('escuela_app')
            # Solo configurar si no tiene handlers
            if not self.logger.handlers:
                self.logger.setLevel(logging.INFO)
                
                # Handler de consola
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.INFO)
                
                formatter = logging.Formatter(
                    '%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%H:%M:%S'
                )
                console_handler.setFormatter(formatter)
                
                self.logger.addHandler(console_handler)
                
            self._initialized = True
            self.logger.propagate = False
    
    def debug(self, message, extra=None):
        self.logger.debug(message, extra=extra)
    
    def info(self, message, extra=None):
        self.logger.info(message, extra=extra)
    
    def warning(self, message, extra=None):
        self.logger.warning(message, extra=extra)
    
    def error(self, message, exc_info=False, extra=None):
        self.logger.error(message, exc_info=exc_info, extra=extra)
    
    def critical(self, message, exc_info=False, extra=None):
        self.logger.critical(message, exc_info=exc_info, extra=extra)

logger = EnhancedLogger()

# =============================================================================
# 1.2 CONFIGURACIÓN DE PÁGINA
# =============================================================================

st.set_page_config(
    page_title="Sistema Escuela Enfermería - Base de Datos Única",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# 1.3 DATOS ESTÁTICOS DE LA INSTITUCIÓN
# =============================================================================

def obtener_programas_academicos():
    """Obtener lista de programas académicos disponibles por categoría"""
    return {
        "LICENCIATURA": [
            {
                "nombre": "Licenciatura en Enfermería",
                "duracion": "4 años",
                "modalidad": "Presencial",
                "descripcion": "Formación integral en enfermería con enfoque especializado.",
                "requisitos": ["Bachillerato terminado", "Promedio mínimo 8.0"],
                "categoria": "licenciatura"
            }
        ],
        "ESPECIALIDAD": [
            {
                "nombre": "Especialidad en Enfermería Clínica",
                "duracion": "2 años",
                "modalidad": "Presencial",
                "descripcion": "Formación especializada en el cuidado de pacientes.",
                "requisitos": ["Licenciatura en Enfermería", "Cédula profesional", "2 años de experiencia"],
                "categoria": "posgrado"
            }
        ],
        "MAESTRIA": [
            {
                "nombre": "Maestría en Ciencias de la Salud",
                "duracion": "2 años",
                "modalidad": "Presencial",
                "descripcion": "Formación de investigadores en el área de ciencias de la salud.",
                "requisitos": ["Licenciatura en áreas afines", "Promedio mínimo 8.5"],
                "categoria": "posgrado"
            }
        ],
        "DIPLOMADO": [
            {
                "nombre": "Diplomado en Salud Pública",
                "duracion": "6 meses",
                "modalidad": "Híbrida",
                "descripcion": "Actualización en fundamentos de salud pública para profesionales.",
                "requisitos": ["Título profesional en área de la salud"],
                "categoria": "educacion_continua"
            }
        ],
        "CURSO": [
            {
                "nombre": "Curso de RCP Básico",
                "duracion": "40 horas",
                "modalidad": "Presencial",
                "descripcion": "Certificación en Reanimación Cardiopulmonar Básica.",
                "requisitos": ["Título en área de la salud"],
                "categoria": "educacion_continua"
            }
        ]
    }

def obtener_categorias_academicas():
    """Obtener categorías académicas para los 4 grupos"""
    return [
        {"id": "pregrado", "nombre": "Pregrado", "descripcion": "Programas de nivel técnico y profesional asociado"},
        {"id": "posgrado", "nombre": "Posgrado", "descripcion": "Especialidades, maestrías y doctorados"},
        {"id": "licenciatura", "nombre": "Licenciatura", "descripcion": "Programas de licenciatura"},
        {"id": "educacion_continua", "nombre": "Educación Continua", "descripcion": "Diplomados, cursos y talleres"}
    ]

def obtener_documentos_requeridos(tipo_programa):
    """Obtener documentos requeridos según tipo de programa"""
    documentos_base = [
        "Certificado preparatoria (promedio ≥ 8.0)",
        "Acta nacimiento",
        "CURP",
        "Cartilla Nacional de Salud",
        "INE del tutor",
        "Comprobante domicilio",
        "Certificado médico institucional",
        "12 fotografías tamaño infantil"
    ]
    
    if tipo_programa == "LICENCIATURA":
        documentos_especificos = [
            "Comprobante domicilio (adicional)",
            "Carta de exposición de motivos",
            "Certificado de bachillerato"
        ]
        return documentos_base + documentos_especificos
    
    elif tipo_programa == "ESPECIALIDAD":
        documentos_especificos = [
            "Título profesional",
            "Certificado de licenciatura",
            "Cédula profesional",
            "INE (vigente)",
            "Comprobante de Servicio Social",
            "Autorización de titulación",
            "Constancia de experiencia laboral (2+ años)",
            "Constancia de cómputo",
            "Constancia de comprensión de textos"
        ]
        return documentos_base + documentos_especificos
    
    else:
        return documentos_base

# =============================================================================
# 1.4 FUNCIÓN PARA LEER SECRETS.TOML
# =============================================================================

def cargar_configuracion_completa():
    """Cargar configuración completa desde secrets.toml"""
    try:
        if not HAS_TOMLLIB:
            logger.error("❌ ERROR: No se puede cargar secrets.toml sin tomllib/tomli")
            return {}
        
        posibles_rutas = [
            ".streamlit/secrets.toml",
            "secrets.toml",
            "./.streamlit/secrets.toml",
            "../.streamlit/secrets.toml",
            "/mount/src/escuelanueva/.streamlit/secrets.toml",
            "config/secrets.toml",
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
        
        with open(ruta_encontrada, 'rb') as f:
            config = tomllib.load(f)
            logger.info(f"✅ Configuración completa cargada desde: {ruta_encontrada}")
            return config
        
    except Exception as e:
        logger.error(f"❌ Error cargando secrets.toml: {e}", exc_info=True)
        return {}

# =============================================================================
# 1.5 VALIDACIONES MEJORADAS
# =============================================================================

class ValidadorDatos:
    """Clase para validaciones de datos mejoradas"""
    
    @staticmethod
    def validar_email(email):
        """Validar formato de email"""
        if not email:
            return False
        
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validar_email_gmail(email):
        """Validar que sea email Gmail"""
        if not email:
            return False
        
        pattern = r'^[a-zA-Z0-9._%+-]+@gmail\.com$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validar_telefono(telefono):
        """Validar formato de teléfono (mínimo 10 dígitos)"""
        if not telefono:
            return True
        
        digitos = ''.join(filter(str.isdigit, telefono))
        return len(digitos) >= 10
    
    @staticmethod
    def validar_nombre_completo(nombre):
        """Validar nombre completo"""
        if not nombre:
            return False
        palabras = nombre.strip().split()
        return len(palabras) >= 2
    
    @staticmethod
    def validar_fecha_nacimiento(fecha_str):
        """Validar fecha de nacimiento"""
        try:
            if not fecha_str:
                return True
            
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            hoy = datetime.now().date()
            
            if fecha > hoy:
                return False
            
            edad = hoy.year - fecha.year - ((hoy.month, hoy.day) < (fecha.month, fecha.day))
            return edad >= 15
        except:
            return False
    
    @staticmethod
    def validar_matricula(matricula):
        """Validar formato de matrícula"""
        if not matricula:
            return False
        return matricula.startswith('INS') and len(matricula) >= 10
    
    @staticmethod
    def validar_folio(folio):
        """Validar formato de folio"""
        if not folio:
            return False
        return folio.startswith('FOL') and len(folio) >= 10
    
    @staticmethod
    def validar_calificacion(calificacion):
        """Validar que la calificación esté entre 0 y 100"""
        try:
            calif = float(calificacion)
            return 0 <= calif <= 100
        except:
            return False

# =============================================================================
# 1.6 UTILIDADES DE DISCO Y RED
# =============================================================================

class UtilidadesSistema:
    """Utilidades para verificación de disco y red"""
    
    @staticmethod
    def verificar_espacio_disco(ruta, espacio_minimo_mb=100):
        """Verificar espacio disponible en disco"""
        try:
            stat = psutil.disk_usage(ruta)
            espacio_disponible_mb = stat.free / (1024 * 1024)
            
            logger.debug(f"Espacio disponible en {ruta}: {espacio_disponible_mb:.2f} MB")
            
            if espacio_disponible_mb < espacio_minimo_mb:
                logger.warning(f"⚠️ Espacio en disco bajo: {espacio_disponible_mb:.2f} MB")
                return False, espacio_disponible_mb
            
            return True, espacio_disponible_mb
            
        except Exception as e:
            logger.error(f"Error verificando espacio en disco: {e}")
            return False, 0
    
    @staticmethod
    def verificar_conectividad_red(host="8.8.8.8", port=53, timeout=3):
        """Verificar conectividad de red"""
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except Exception as e:
            logger.warning(f"Sin conectividad de red: {e}")
            return False

# =============================================================================
# 1.7 ARCHIVO DE ESTADO PERSISTENTE
# =============================================================================

class EstadoPersistente:
    """Maneja el estado persistente para el sistema"""
    
    def __init__(self, archivo_estado="estado_sistema.json"):
        self.archivo_estado = archivo_estado
        self.estado = self._cargar_estado()
    
    def _cargar_estado(self):
        """Cargar estado desde archivo JSON"""
        try:
            if os.path.exists(self.archivo_estado):
                with open(self.archivo_estado, 'r') as f:
                    estado = json.load(f)
                    
                    if 'estadisticas_sistema' not in estado:
                        estado['estadisticas_sistema'] = {
                            'sesiones': estado.get('sesiones_iniciadas', 0),
                            'registros': 0,
                            'total_tiempo': 0
                        }
                    
                    return estado
            else:
                return self._estado_por_defecto()
        except Exception as e:
            logger.warning(f"⚠️ Error cargando estado: {e}")
            return self._estado_por_defecto()
    
    def _estado_por_defecto(self):
        """Estado por defecto"""
        return {
            'db_inicializada': False,
            'fecha_inicializacion': None,
            'ultima_sincronizacion': None,
            'sesiones_iniciadas': 0,
            'ultima_sesion': None,
            'ssh_conectado': False,
            'ssh_error': None,
            'ultima_verificacion': None,
            'estadisticas_sistema': {
                'sesiones': 0,
                'registros': 0,
                'total_tiempo': 0
            },
            'backups_realizados': 0,
            'total_inscritos': 0,
            'recordatorios_enviados': 0,
            'duplicados_eliminados': 0,
            'registros_incompletos_eliminados': 0
        }
    
    def guardar_estado(self):
        """Guardar estado a archivo JSON"""
        try:
            with open(self.archivo_estado, 'w') as f:
                json.dump(self.estado, f, indent=2, default=str)
            logger.debug(f"Estado guardado en {self.archivo_estado}")
        except Exception as e:
            logger.error(f"❌ Error guardando estado: {e}")
    
    def marcar_db_inicializada(self):
        """Marcar la base de datos como inicializada"""
        self.estado['db_inicializada'] = True
        self.estado['fecha_inicializacion'] = datetime.now().isoformat()
        self.guardar_estado()
    
    def registrar_sesion(self, exitosa=True, tiempo_ejecucion=0):
        """Registrar una sesión"""
        self.estado['sesiones_iniciadas'] = self.estado.get('sesiones_iniciadas', 0) + 1
        self.estado['ultima_sesion'] = datetime.now().isoformat()
        
        if exitosa:
            self.estado['estadisticas_sistema']['sesiones'] += 1
        
        self.estado['estadisticas_sistema']['total_tiempo'] += tiempo_ejecucion
        self.guardar_estado()
    
    def registrar_backup(self):
        """Registrar que se realizó un backup"""
        self.estado['backups_realizados'] = self.estado.get('backups_realizados', 0) + 1
        self.guardar_estado()
    
    def registrar_duplicado_eliminado(self):
        """Registrar duplicado eliminado"""
        self.estado['duplicados_eliminados'] = self.estado.get('duplicados_eliminados', 0) + 1
        self.guardar_estado()
    
    def registrar_registro_incompleto_eliminado(self, cantidad=1):
        """Registrar registros incompletos eliminados"""
        self.estado['registros_incompletos_eliminados'] = self.estado.get('registros_incompletos_eliminados', 0) + cantidad
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

# =============================================================================
# 2. GESTOR DE CONEXIÓN REMOTA VIA SSH
# =============================================================================

class GestorConexionRemota:
    """Gestor de conexión SSH al servidor remoto - Base de datos única"""
    
    def __init__(self):
        self.ssh = None
        self.sftp = None
        self.config = None
        
        logger.info("📋 Cargando configuración desde secrets.toml...")
        self.config_completa = cargar_configuracion_completa()
        
        if not self.config_completa:
            logger.error("❌ No se pudo cargar configuración de secrets.toml")
            return
            
        self.config = self._cargar_configuracion()
        
        if not self.config.get('ssh_host'):
            logger.warning("⚠️ No hay configuración SSH en secrets.toml")
            return
        
        # Base de datos única
        self.db_path_remoto = self.config.get('db_principal')
        
        if not self.db_path_remoto:
            logger.critical("❌ ERROR CRÍTICO: No hay base de datos configurada")
            return
        
        logger.info(f"🔗 Configuración SSH cargada para servidor remoto")
        logger.info(f"📁 Usando base de datos única: {self.db_path_remoto}")
        
        # Probar conexión inicial
        self.probar_conexion_inicial()
    
    def _cargar_configuracion(self):
        """Cargar configuración desde secrets.toml"""
        config = {}
        
        try:
            # Configuración SSH
            ssh_config = self.config_completa.get('ssh', {})
            config.update({
                'ssh_host': ssh_config.get('host', self.config_completa.get('remote_host', '')),
                'ssh_port': int(ssh_config.get('port', self.config_completa.get('remote_port', 22))),
                'ssh_username': ssh_config.get('username', self.config_completa.get('remote_user', '')),
                'ssh_password': ssh_config.get('password', self.config_completa.get('remote_password', '')),
                'ssh_enabled': bool(ssh_config.get('enabled', True)),
                'ssh_timeout': int(ssh_config.get('timeout', 30))
            })
            
            # Configuración de rutas
            paths_config = self.config_completa.get('paths', {})
            config.update({
                'db_principal': paths_config.get('db_principal', ''),
                'base_path': paths_config.get('base_path', ''),
                'uploads_path': paths_config.get('uploads_path', ''),
                'backup_path': paths_config.get('backup_path', ''),
                'logs_path': paths_config.get('logs_path', '')
            })
            
            # Configuración SMTP
            config.update({
                'smtp_server': self.config_completa.get('smtp_server', ''),
                'smtp_port': self.config_completa.get('smtp_port', 587),
                'email_user': self.config_completa.get('email_user', ''),
                'email_password': self.config_completa.get('email_password', ''),
                'notification_email': self.config_completa.get('notification_email', '')
            })
            
            # Configuración del sistema
            system_config = self.config_completa.get('system', {})
            config.update({
                'auto_connect': system_config.get('auto_connect', True),
                'retry_attempts': system_config.get('retry_attempts', 3),
                'retry_delay': system_config.get('retry_delay', 5),
                'max_login_attempts': system_config.get('max_login_attempts', 5)
            })
            
            logger.info("✅ Configuración cargada correctamente")
            
        except Exception as e:
            logger.error(f"❌ Error cargando configuración: {e}", exc_info=True)
        
        return config
    
    def probar_conexion_inicial(self):
        """Probar la conexión SSH al inicio"""
        try:
            if not self.config.get('ssh_host'):
                return False
                
            logger.info(f"🔍 Probando conexión SSH...")
            
            ssh_test = paramiko.SSHClient()
            ssh_test.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh_test.connect(
                hostname=self.config['ssh_host'],
                port=self.config['ssh_port'],
                username=self.config['ssh_username'],
                password=self.config['ssh_password'],
                timeout=self.config['ssh_timeout'],
                banner_timeout=self.config['ssh_timeout'],
                allow_agent=False,
                look_for_keys=False
            )
            
            # Verificar que la base de datos existe
            stdin, stdout, stderr = ssh_test.exec_command(
                f"test -f '{self.db_path_remoto}' && echo 'EXISTS' || echo 'NOT_FOUND'",
                timeout=self.config['ssh_timeout']
            )
            output = stdout.read().decode().strip()
            
            ssh_test.close()
            
            if output == 'EXISTS':
                logger.info(f"✅ Conexión SSH exitosa y DB encontrada")
                estado_sistema.set_ssh_conectado(True, None)
                return True
            else:
                logger.warning(f"⚠️ Conexión SSH exitosa pero DB no encontrada")
                estado_sistema.set_ssh_conectado(False, "Base de datos no encontrada en servidor")
                return False
            
        except Exception as e:
            error_msg = f"Error de conexión SSH: {str(e)}"
            logger.error(f"❌ {error_msg}")
            estado_sistema.set_ssh_conectado(False, error_msg)
            return False
    
    def conectar_ssh(self):
        """Establecer conexión SSH con el servidor remoto"""
        try:
            if not self.config.get('ssh_host'):
                logger.error("No hay configuración SSH disponible")
                return False
                
            logger.info(f"🔗 Conectando SSH...")
            
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.ssh.connect(
                hostname=self.config['ssh_host'],
                port=self.config['ssh_port'],
                username=self.config['ssh_username'],
                password=self.config['ssh_password'],
                timeout=self.config['ssh_timeout'],
                banner_timeout=self.config['ssh_timeout'],
                allow_agent=False,
                look_for_keys=False
            )
            
            self.sftp = self.ssh.open_sftp()
            
            logger.info(f"✅ Conexión SSH establecida")
            estado_sistema.set_ssh_conectado(True, None)
            return True
            
        except Exception as e:
            error_msg = f"Error de conexión: {str(e)}"
            logger.error(f"❌ {error_msg}")
            estado_sistema.set_ssh_conectado(False, error_msg)
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
    
    def ejecutar_comando_remoto(self, comando, timeout=None):
        """Ejecutar comando en servidor remoto"""
        try:
            if not self.ssh:
                if not self.conectar_ssh():
                    return None, None
            
            if timeout is None:
                timeout = self.config['ssh_timeout']
            
            stdin, stdout, stderr = self.ssh.exec_command(comando, timeout=timeout)
            
            salida = stdout.read().decode('utf-8', errors='ignore').strip()
            error = stderr.read().decode('utf-8', errors='ignore').strip()
            
            return salida, error
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando comando remoto: {e}")
            return None, str(e)
    
    def ejecutar_sql_remoto(self, consulta_sql):
        """Ejecutar SQL directamente en servidor remoto"""
        try:
            comando = f"cd \"$(dirname \\\"{self.db_path_remoto}\\\")\" && sqlite3 -json \"{os.path.basename(self.db_path_remoto)}\" \"{consulta_sql.replace('\"', '\\\"')}\""
            
            salida, error = self.ejecutar_comando_remoto(comando)
            
            if error and "Error:" in error:
                logger.error(f"❌ Error SQL remoto: {error}")
                return None, error
            
            # Parsear resultado JSON
            try:
                if salida and salida.strip():
                    resultado_json = json.loads(salida)
                    return resultado_json, None
                else:
                    return [], None
            except json.JSONDecodeError:
                return salida, None
                
        except Exception as e:
            logger.error(f"❌ Error ejecutando SQL remoto: {e}", exc_info=True)
            return None, str(e)
    
    def ejecutar_sql_modificacion(self, consulta_sql):
        """Ejecutar SQL de modificación (INSERT, UPDATE, DELETE)"""
        try:
            comando = f"cd \"$(dirname \\\"{self.db_path_remoto}\\\")\" && sqlite3 \"{os.path.basename(self.db_path_remoto)}\" \"{consulta_sql.replace('\"', '\\\"')}\""
            
            salida, error = self.ejecutar_comando_remoto(comando)
            
            if error:
                logger.error(f"❌ Error en modificación SQL: {error}")
                return False, error
            
            return True, salida
            
        except Exception as e:
            logger.error(f"❌ Error en modificación SQL remota: {e}")
            return False, str(e)
    
    def verificar_existencia_db(self):
        """Verificar si la base de datos existe en servidor remoto"""
        try:
            comando = f"test -f '{self.db_path_remoto}' && echo 'EXISTS' || echo 'NOT_FOUND'"
            salida, error = self.ejecutar_comando_remoto(comando)
            
            if salida == 'EXISTS':
                logger.info(f"✅ Base de datos encontrada en servidor")
                return True
            else:
                logger.warning(f"⚠️ Base de datos NO encontrada en servidor")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error verificando existencia DB: {e}")
            return False
    
    def crear_backup_remoto(self):
        """Crear backup de la base de datos en servidor remoto"""
        try:
            backup_dir = self.config.get('backup_path', '/tmp')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{backup_dir}/escuela_backup_{timestamp}.db"
            
            comando = f"cp '{self.db_path_remoto}' '{backup_path}' && echo 'BACKUP_CREADO:{backup_path}' || echo 'ERROR_BACKUP'"
            salida, error = self.ejecutar_comando_remoto(comando)
            
            if 'BACKUP_CREADO' in salida:
                logger.info(f"✅ Backup remoto creado")
                estado_sistema.registrar_backup()
                return True
            else:
                logger.error(f"❌ Error creando backup remoto: {error}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Error en backup remoto: {e}")
            return False
    
    def subir_archivo_remoto(self, archivo_local, ruta_remota):
        """Subir archivo directamente al servidor remoto"""
        try:
            if not self.sftp:
                if not self.conectar_ssh():
                    return False
            
            # Crear directorio remoto si no existe
            remote_dir = os.path.dirname(ruta_remota)
            try:
                self.sftp.stat(remote_dir)
            except:
                self._crear_directorio_remoto_recursivo(remote_dir)
            
            # Subir archivo
            self.sftp.put(archivo_local, ruta_remota)
            
            logger.info(f"✅ Archivo subido a servidor: {ruta_remota}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error subiendo archivo a servidor: {e}")
            return False
    
    def _crear_directorio_remoto_recursivo(self, remote_path):
        """Crear directorio remoto recursivamente"""
        try:
            self.sftp.stat(remote_path)
            logger.info(f"📁 Directorio remoto ya existe: {remote_path}")
        except:
            try:
                self.sftp.mkdir(remote_path)
                logger.info(f"✅ Directorio remoto creado: {remote_path}")
            except:
                parent_dir = os.path.dirname(remote_path)
                if parent_dir and parent_dir != '/':
                    self._crear_directorio_remoto_recursivo(parent_dir)
                self.sftp.mkdir(remote_path)
                logger.info(f"✅ Directorio remoto creado recursivamente: {remote_path}")
    
    def verificar_conexion_ssh(self):
        """Verificar estado de conexión SSH"""
        return self.probar_conexion_inicial()

# =============================================================================
# 3. SISTEMA DE BASE DE DATOS SQLITE - BASE DE DATOS ÚNICA
# =============================================================================

class SistemaBaseDatos:
    """Sistema de base de datos SQLite con base de datos única"""
    
    def __init__(self):
        self.gestor = gestor_remoto
        self.page_size = 20
        
    def inicializar_db_remota(self):
        """Inicializar base de datos en servidor remoto"""
        try:
            with st.spinner("🔄 Inicializando base de datos remota..."):
                # Verificar si ya existe
                if self.gestor.verificar_existencia_db():
                    logger.info("✅ Base de datos ya existe en servidor")
                    
                    # Verificar si tiene la tabla usuarios
                    consulta = "SELECT name FROM sqlite_master WHERE type='table' AND name='usuarios'"
                    resultado, error = self.gestor.ejecutar_sql_remoto(consulta)
                    
                    if resultado and len(resultado) > 0:
                        logger.info("✅ Tabla 'usuarios' encontrada")
                        estado_sistema.marcar_db_inicializada()
                        return True
                    else:
                        logger.warning("⚠️ Tabla 'usuarios' no encontrada")
                        return False
                else:
                    st.error("❌ Base de datos no encontrada en servidor")
                    return False
        except Exception as e:
            logger.error(f"❌ Error inicializando DB remota: {e}")
            st.error(f"❌ Error: {str(e)}")
            return False
    
    def ejecutar_consulta_remota(self, consulta_sql):
        """Ejecutar consulta SQL en servidor remoto"""
        try:
            resultado, error = self.gestor.ejecutar_sql_remoto(consulta_sql)
            
            if error:
                logger.error(f"❌ Error en consulta remota: {error}")
                return None
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando consulta remota: {e}")
            return None
    
    def ejecutar_modificacion_remota(self, consulta_sql):
        """Ejecutar modificación SQL en servidor remoto"""
        try:
            exito, resultado = self.gestor.ejecutar_sql_modificacion(consulta_sql)
            
            if not exito:
                logger.error(f"❌ Error en modificación remota: {resultado}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando modificación remota: {e}")
            return False
    
    # =============================================================================
    # MÉTODOS DE CONSULTA CON PAGINACIÓN
    # =============================================================================
    
    def obtener_usuario(self, usuario):
        """Obtener usuario por nombre de usuario o matrícula"""
        try:
            logger.info(f"🔍 Buscando usuario en base de datos única: {usuario}")
            
            consulta = f"""
            SELECT * FROM usuarios 
            WHERE (usuario = '{usuario}' OR email = '{usuario}' OR matricula = '{usuario}')
            AND activo = 1
            LIMIT 1
            """
            
            resultado = self.ejecutar_consulta_remota(consulta)
            
            if resultado and len(resultado) > 0:
                logger.info(f"✅ Usuario encontrado: {usuario}")
                return resultado[0]
            else:
                logger.warning(f"Usuario no encontrado: {usuario}")
                return None
        except Exception as e:
            logger.error(f"Error obteniendo usuario {usuario}: {e}", exc_info=True)
            return None
    
    def verificar_login(self, usuario, password):
        """Verificar credenciales de login contra base de datos remota"""
        try:
            logger.info(f"🔐 Intentando login para usuario: {usuario}")
            
            # Primero obtener el usuario desde la base de datos remota
            usuario_data = self.obtener_usuario(usuario)
            
            if not usuario_data:
                logger.warning(f"Usuario no encontrado en base de datos remota: {usuario}")
                return None
            
            stored_password = usuario_data.get('password', '')
            
            # COMPARACIÓN DIRECTA (texto plano)
            if stored_password == password:
                logger.info(f"✅ Login exitoso para usuario: {usuario}")
                return usuario_data
            else:
                logger.warning(f"❌ Contraseña incorrecta para usuario: {usuario}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error verificando login: {e}", exc_info=True)
            return None
    
    def obtener_inscritos(self, page=1, search_term=""):
        """Obtener inscritos con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            if search_term:
                consulta = f"""
                SELECT * FROM inscritos 
                WHERE matricula LIKE '%{search_term}%' 
                   OR nombre_completo LIKE '%{search_term}%' 
                   OR email LIKE '%{search_term}%' 
                   OR folio_unico LIKE '%{search_term}%'
                ORDER BY fecha_registro DESC 
                LIMIT {self.page_size} OFFSET {offset}
                """
            else:
                consulta = f"""
                SELECT * FROM inscritos 
                ORDER BY fecha_registro DESC 
                LIMIT {self.page_size} OFFSET {offset}
                """
            
            resultado = self.ejecutar_consulta_remota(consulta)
            
            if resultado is None:
                return pd.DataFrame(), 0, 0
            
            df = pd.DataFrame(resultado)
            
            # Obtener total de registros
            if search_term:
                count_consulta = f"""
                SELECT COUNT(*) as total FROM inscritos 
                WHERE matricula LIKE '%{search_term}%' 
                   OR nombre_completo LIKE '%{search_term}%' 
                   OR email LIKE '%{search_term}%' 
                   OR folio_unico LIKE '%{search_term}%'
                """
            else:
                count_consulta = "SELECT COUNT(*) as total FROM inscritos"
            
            count_result = self.ejecutar_consulta_remota(count_consulta)
            
            if count_result and len(count_result) > 0:
                total_records = count_result[0].get('total', 0)
            else:
                total_records = 0
            
            total_pages = math.ceil(total_records / self.page_size) if total_records > 0 else 0
            
            logger.debug(f"Obtenidos {len(df)} inscritos (página {page}/{total_pages})")
            return df, total_pages, total_records
        except Exception as e:
            logger.error(f"Error obteniendo inscritos: {e}", exc_info=True)
            return pd.DataFrame(), 0, 0
    
    def obtener_estudiantes(self, page=1, search_term=""):
        """Obtener estudiantes con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            if search_term:
                consulta = f"""
                SELECT * FROM estudiantes 
                WHERE matricula LIKE '%{search_term}%' 
                   OR nombre_completo LIKE '%{search_term}%' 
                   OR email LIKE '%{search_term}%'
                ORDER BY fecha_ingreso DESC 
                LIMIT {self.page_size} OFFSET {offset}
                """
            else:
                consulta = f"""
                SELECT * FROM estudiantes 
                ORDER BY fecha_ingreso DESC 
                LIMIT {self.page_size} OFFSET {offset}
                """
            
            resultado = self.ejecutar_consulta_remota(consulta)
            
            if resultado is None:
                return pd.DataFrame(), 0, 0
            
            df = pd.DataFrame(resultado)
            
            # Obtener total de registros
            if search_term:
                count_consulta = f"""
                SELECT COUNT(*) as total FROM estudiantes 
                WHERE matricula LIKE '%{search_term}%' 
                   OR nombre_completo LIKE '%{search_term}%' 
                   OR email LIKE '%{search_term}%'
                """
            else:
                count_consulta = "SELECT COUNT(*) as total FROM estudiantes"
            
            count_result = self.ejecutar_consulta_remota(count_consulta)
            
            if count_result and len(count_result) > 0:
                total_records = count_result[0].get('total', 0)
            else:
                total_records = 0
            
            total_pages = math.ceil(total_records / self.page_size) if total_records > 0 else 0
            
            logger.debug(f"Obtenidos {len(df)} estudiantes (página {page}/{total_pages})")
            return df, total_pages, total_records
        except Exception as e:
            logger.error(f"Error obteniendo estudiantes: {e}", exc_info=True)
            return pd.DataFrame(), 0, 0
    
    def obtener_egresados(self, page=1, search_term=""):
        """Obtener egresados con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            if search_term:
                consulta = f"""
                SELECT * FROM egresados 
                WHERE matricula LIKE '%{search_term}%' 
                   OR nombre_completo LIKE '%{search_term}%' 
                   OR email LIKE '%{search_term}%'
                ORDER BY fecha_graduacion DESC 
                LIMIT {self.page_size} OFFSET {offset}
                """
            else:
                consulta = f"""
                SELECT * FROM egresados 
                ORDER BY fecha_graduacion DESC 
                LIMIT {self.page_size} OFFSET {offset}
                """
            
            resultado = self.ejecutar_consulta_remota(consulta)
            
            if resultado is None:
                return pd.DataFrame(), 0, 0
            
            df = pd.DataFrame(resultado)
            
            # Obtener total de registros
            if search_term:
                count_consulta = f"""
                SELECT COUNT(*) as total FROM egresados 
                WHERE matricula LIKE '%{search_term}%' 
                   OR nombre_completo LIKE '%{search_term}%' 
                   OR email LIKE '%{search_term}%'
                """
            else:
                count_consulta = "SELECT COUNT(*) as total FROM egresados"
            
            count_result = self.ejecutar_consulta_remota(count_consulta)
            
            if count_result and len(count_result) > 0:
                total_records = count_result[0].get('total', 0)
            else:
                total_records = 0
            
            total_pages = math.ceil(total_records / self.page_size) if total_records > 0 else 0
            
            logger.debug(f"Obtenidos {len(df)} egresados (página {page}/{total_pages})")
            return df, total_pages, total_records
        except Exception as e:
            logger.error(f"Error obteniendo egresados: {e}", exc_info=True)
            return pd.DataFrame(), 0, 0
    
    def obtener_contratados(self, page=1, search_term=""):
        """Obtener contratados con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            if search_term:
                consulta = f"""
                SELECT * FROM contratados 
                WHERE matricula LIKE '%{search_term}%' 
                   OR nombre_completo LIKE '%{search_term}%' 
                   OR email LIKE '%{search_term}%'
                ORDER BY fecha_contratacion DESC 
                LIMIT {self.page_size} OFFSET {offset}
                """
            else:
                consulta = f"""
                SELECT * FROM contratados 
                ORDER BY fecha_contratacion DESC 
                LIMIT {self.page_size} OFFSET {offset}
                """
            
            resultado = self.ejecutar_consulta_remota(consulta)
            
            if resultado is None:
                return pd.DataFrame(), 0, 0
            
            df = pd.DataFrame(resultado)
            
            # Obtener total de registros
            if search_term:
                count_consulta = f"""
                SELECT COUNT(*) as total FROM contratados 
                WHERE matricula LIKE '%{search_term}%' 
                   OR nombre_completo LIKE '%{search_term}%' 
                   OR email LIKE '%{search_term}%'
                """
            else:
                count_consulta = "SELECT COUNT(*) as total FROM contratados"
            
            count_result = self.ejecutar_consulta_remota(count_consulta)
            
            if count_result and len(count_result) > 0:
                total_records = count_result[0].get('total', 0)
            else:
                total_records = 0
            
            total_pages = math.ceil(total_records / self.page_size) if total_records > 0 else 0
            
            logger.debug(f"Obtenidos {len(df)} contratados (página {page}/{total_pages})")
            return df, total_pages, total_records
        except Exception as e:
            logger.error(f"Error obteniendo contratados: {e}", exc_info=True)
            return pd.DataFrame(), 0, 0
    
    def obtener_usuarios(self, page=1, search_term=""):
        """Obtener usuarios con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            if search_term:
                consulta = f"""
                SELECT * FROM usuarios 
                WHERE usuario LIKE '%{search_term}%' 
                   OR nombre_completo LIKE '%{search_term}%' 
                   OR email LIKE '%{search_term}%' 
                   OR matricula LIKE '%{search_term}%'
                ORDER BY fecha_creacion DESC 
                LIMIT {self.page_size} OFFSET {offset}
                """
            else:
                consulta = f"""
                SELECT * FROM usuarios 
                ORDER BY fecha_creacion DESC 
                LIMIT {self.page_size} OFFSET {offset}
                """
            
            resultado = self.ejecutar_consulta_remota(consulta)
            
            if resultado is None:
                return pd.DataFrame(), 0, 0
            
            df = pd.DataFrame(resultado)
            
            # Obtener total de registros
            if search_term:
                count_consulta = f"""
                SELECT COUNT(*) as total FROM usuarios 
                WHERE usuario LIKE '%{search_term}%' 
                   OR nombre_completo LIKE '%{search_term}%' 
                   OR email LIKE '%{search_term}%' 
                   OR matricula LIKE '%{search_term}%'
                """
            else:
                count_consulta = "SELECT COUNT(*) as total FROM usuarios"
            
            count_result = self.ejecutar_consulta_remota(count_consulta)
            
            if count_result and len(count_result) > 0:
                total_records = count_result[0].get('total', 0)
            else:
                total_records = 0
            
            total_pages = math.ceil(total_records / self.page_size) if total_records > 0 else 0
            
            logger.debug(f"Obtenidos {len(df)} usuarios (página {page}/{total_pages})")
            return df, total_pages, total_records
        except Exception as e:
            logger.error(f"Error obteniendo usuarios: {e}", exc_info=True)
            return pd.DataFrame(), 0, 0
    
    def obtener_inscrito_por_matricula(self, matricula):
        """Buscar inscrito por matrícula"""
        try:
            consulta = f"SELECT * FROM inscritos WHERE matricula = '{matricula}' LIMIT 1"
            resultado = self.ejecutar_consulta_remota(consulta)
            
            if resultado and len(resultado) > 0:
                return resultado[0]
            return None
        except Exception as e:
            logger.error(f"Error buscando inscrito {matricula}: {e}", exc_info=True)
            return None
    
    def agregar_inscrito(self, inscrito_data):
        """Agregar nuevo inscrito"""
        try:
            if not inscrito_data.get('matricula'):
                fecha = datetime.now().strftime('%y%m%d')
                random_num = ''.join(random.choices(string.digits, k=4))
                inscrito_data['matricula'] = f"INS{fecha}{random_num}"
            
            folio = f"FOL{datetime.now().strftime('%y%m%d')}{random.randint(1000, 9999)}"
            
            consulta = f"""
            INSERT INTO inscritos (
                matricula, nombre_completo, email, telefono, programa_interes,
                fecha_registro, estatus, folio_unico, fecha_nacimiento, como_se_entero,
                documentos_subidos, documentos_guardados
            ) VALUES (
                '{inscrito_data.get('matricula', '')}',
                '{inscrito_data.get('nombre_completo', '')}',
                '{inscrito_data.get('email', '')}',
                '{inscrito_data.get('telefono', '')}',
                '{inscrito_data.get('programa_interes', '')}',
                '{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}',
                '{inscrito_data.get('estatus', 'Pre-inscrito')}',
                '{folio}',
                '{inscrito_data.get('fecha_nacimiento', '')}',
                '{inscrito_data.get('como_se_entero', '')}',
                {inscrito_data.get('documentos_subidos', 0)},
                '{inscrito_data.get('documentos_guardados', '')}'
            )
            """
            
            exito = self.ejecutar_modificacion_remota(consulta)
            
            if exito:
                logger.info(f"Inscrito agregado: {inscrito_data.get('matricula', '')}")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error agregando inscrito: {e}", exc_info=True)
            return False
    
    def agregar_estudiante(self, estudiante_data):
        """Agregar nuevo estudiante"""
        try:
            consulta = f"""
            INSERT INTO estudiantes (
                matricula, nombre_completo, programa, email, telefono,
                fecha_nacimiento, genero, fecha_inscripcion, estatus,
                documentos_subidos, fecha_registro, programa_interes,
                folio, como_se_entero, fecha_ingreso, usuario
            ) VALUES (
                '{estudiante_data.get('matricula', '')}',
                '{estudiante_data.get('nombre_completo', '')}',
                '{estudiante_data.get('programa', '')}',
                '{estudiante_data.get('email', '')}',
                '{estudiante_data.get('telefono', '')}',
                '{estudiante_data.get('fecha_nacimiento', '')}',
                '{estudiante_data.get('genero', '')}',
                '{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}',
                '{estudiante_data.get('estatus', 'ACTIVO')}',
                '{estudiante_data.get('documentos_subidos', '')}',
                '{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}',
                '{estudiante_data.get('programa_interes', '')}',
                '{estudiante_data.get('folio', '')}',
                '{estudiante_data.get('como_se_entero', '')}',
                '{datetime.now().strftime('%Y-%m-%d')}',
                '{estudiante_data.get('matricula', '')}'
            )
            """
            
            exito = self.ejecutar_modificacion_remota(consulta)
            
            if exito:
                logger.info(f"Estudiante agregado: {estudiante_data.get('matricula', '')}")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error agregando estudiante: {e}", exc_info=True)
            return False
    
    def agregar_egresado(self, egresado_data):
        """Agregar nuevo egresado"""
        try:
            consulta = f"""
            INSERT INTO egresados (
                matricula, nombre_completo, programa_original, fecha_graduacion,
                nivel_academico, email, telefono, estado_laboral,
                fecha_actualizacion, documentos_subidos
            ) VALUES (
                '{egresado_data.get('matricula', '')}',
                '{egresado_data.get('nombre_completo', '')}',
                '{egresado_data.get('programa_original', '')}',
                '{datetime.now().strftime('%Y-%m-%d')}',
                '{egresado_data.get('nivel_academico', '')}',
                '{egresado_data.get('email', '')}',
                '{egresado_data.get('telefono', '')}',
                '{egresado_data.get('estado_laboral', '')}',
                '{datetime.now().strftime('%Y-%m-%d')}',
                '{egresado_data.get('documentos_subidos', '')}'
            )
            """
            
            exito = self.ejecutar_modificacion_remota(consulta)
            
            if exito:
                logger.info(f"Egresado agregado: {egresado_data.get('matricula', '')}")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error agregando egresado: {e}", exc_info=True)
            return False
    
    def agregar_contratado(self, contratado_data):
        """Agregar nuevo contratado"""
        try:
            consulta = f"""
            INSERT INTO contratados (
                matricula, fecha_contratacion, puesto, departamento,
                estatus, salario, tipo_contrato, fecha_inicio,
                fecha_fin, documentos_subidos
            ) VALUES (
                '{contratado_data.get('matricula', '')}',
                '{datetime.now().strftime('%Y-%m-%d')}',
                '{contratado_data.get('puesto', '')}',
                '{contratado_data.get('departamento', '')}',
                '{contratado_data.get('estatus', '')}',
                '{contratado_data.get('salario', '')}',
                '{contratado_data.get('tipo_contrato', '')}',
                '{datetime.now().strftime('%Y-%m-%d')}',
                '{contratado_data.get('fecha_fin', datetime.now().strftime('%Y-%m-%d'))}',
                '{contratado_data.get('documentos_subidos', '')}'
            )
            """
            
            exito = self.ejecutar_modificacion_remota(consulta)
            
            if exito:
                logger.info(f"Contratado agregado: {contratado_data.get('matricula', '')}")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error agregando contratado: {e}", exc_info=True)
            return False
    
    def agregar_usuario(self, usuario_data):
        """Agregar nuevo usuario"""
        try:
            consulta = f"""
            INSERT INTO usuarios (
                usuario, password, rol, nombre_completo, email,
                matricula, activo, categoria_academica, tipo_programa
            ) VALUES (
                '{usuario_data.get('usuario', '')}',
                '{usuario_data.get('password', '')}',
                '{usuario_data.get('rol', 'administrador')}',
                '{usuario_data.get('nombre_completo', '')}',
                '{usuario_data.get('email', '')}',
                '{usuario_data.get('matricula', '')}',
                {1 if usuario_data.get('activo', True) else 0},
                '{usuario_data.get('categoria_academica', '')}',
                '{usuario_data.get('tipo_programa', '')}'
            )
            """
            
            exito = self.ejecutar_modificacion_remota(consulta)
            
            if exito:
                logger.info(f"Usuario agregado: {usuario_data.get('usuario', '')}")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error agregando usuario: {e}", exc_info=True)
            return False
    
    def eliminar_inscrito(self, matricula):
        """Eliminar inscrito por matrícula"""
        try:
            consulta = f"DELETE FROM inscritos WHERE matricula = '{matricula}'"
            exito = self.ejecutar_modificacion_remota(consulta)
            
            if exito:
                logger.info(f"Inscrito eliminado: {matricula}")
                estado_sistema.registrar_registro_incompleto_eliminado()
                return True
            return False
        except Exception as e:
            logger.error(f"Error eliminando inscrito {matricula}: {e}", exc_info=True)
            return False
    
    def eliminar_estudiante(self, matricula):
        """Eliminar estudiante por matrícula"""
        try:
            consulta = f"DELETE FROM estudiantes WHERE matricula = '{matricula}'"
            exito = self.ejecutar_modificacion_remota(consulta)
            
            if exito:
                logger.info(f"Estudiante eliminado: {matricula}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error eliminando estudiante {matricula}: {e}", exc_info=True)
            return False
    
    def eliminar_egresado(self, matricula):
        """Eliminar egresado por matrícula"""
        try:
            consulta = f"DELETE FROM egresados WHERE matricula = '{matricula}'"
            exito = self.ejecutar_modificacion_remota(consulta)
            
            if exito:
                logger.info(f"Egresado eliminado: {matricula}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error eliminando egresado {matricula}: {e}", exc_info=True)
            return False
    
    def eliminar_contratado(self, matricula):
        """Eliminar contratado por matrícula"""
        try:
            consulta = f"DELETE FROM contratados WHERE matricula = '{matricula}'"
            exito = self.ejecutar_modificacion_remota(consulta)
            
            if exito:
                logger.info(f"Contratado eliminado: {matricula}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error eliminando contratado {matricula}: {e}", exc_info=True)
            return False
    
    def actualizar_inscrito(self, matricula, datos_actualizados):
        """Actualizar datos de un inscrito"""
        try:
            campos = []
            for campo, valor in datos_actualizados.items():
                if campo != 'matricula' and valor is not None:
                    if isinstance(valor, str):
                        valor = valor.replace("'", "''")
                    campos.append(f"{campo} = '{valor}'")
            
            if campos:
                campos.append("fecha_actualizacion = CURRENT_TIMESTAMP")
                consulta = f"UPDATE inscritos SET {', '.join(campos)} WHERE matricula = '{matricula}'"
                exito = self.ejecutar_modificacion_remota(consulta)
                
                if exito:
                    logger.info(f"Inscrito actualizado: {matricula}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error actualizando inscrito {matricula}: {e}", exc_info=True)
            return False
    
    def registrar_bitacora(self, usuario, accion, detalles, ip='localhost'):
        """Registrar actividad en bitácora"""
        try:
            consulta = f"""
            INSERT INTO bitacora (usuario, accion, detalles, ip)
            VALUES ('{usuario}', '{accion}', '{detalles.replace("'", "''")}', '{ip}')
            """
            
            exito = self.ejecutar_modificacion_remota(consulta)
            return exito
        except Exception as e:
            logger.error(f"Error registrando en bitácora: {e}", exc_info=True)
            return False
    
    def crear_backup_remoto(self):
        """Crear backup en servidor remoto"""
        return self.gestor.crear_backup_remoto()

# =============================================================================
# 4. SISTEMA DE BACKUP AUTOMÁTICO
# =============================================================================

class SistemaBackupAutomatico:
    """Sistema de backup automático"""
    
    def __init__(self, gestor_ssh):
        self.gestor_ssh = gestor_ssh
        self.backup_dir = "backups_sistema"
        self.max_backups = 10
        
    def crear_backup(self, tipo_operacion, detalles):
        """Crear backup automático en servidor remoto"""
        try:
            logger.info(f"💾 Creando backup remoto: {tipo_operacion}")
            
            # Crear backup directamente en servidor remoto
            if self.gestor_ssh.crear_backup_remoto():
                logger.info(f"✅ Backup remoto creado para operación: {tipo_operacion}")
                
                # Registrar localmente la operación
                if not os.path.exists(self.backup_dir):
                    os.makedirs(self.backup_dir)
                
                metadata = {
                    'fecha_backup': datetime.now().isoformat(),
                    'tipo_operacion': tipo_operacion,
                    'detalles': detalles,
                    'usuario': st.session_state.get('usuario_actual', {}).get('usuario', 'desconocido'),
                    'ubicacion': 'servidor_remoto'
                }
                
                metadata_file = os.path.join(self.backup_dir, f"backup_metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2, default=str)
                
                self._limpiar_metadatos_antiguos()
                
                return "backup_creado_en_servidor"
            else:
                logger.error("❌ Error creando backup remoto")
                return None
            
        except Exception as e:
            logger.error(f"❌ Error creando backup: {e}")
            return None
    
    def _limpiar_metadatos_antiguos(self):
        """Mantener solo los últimos N metadatos de backups"""
        try:
            if not os.path.exists(self.backup_dir):
                return
            
            metadata_files = []
            for file in os.listdir(self.backup_dir):
                if file.startswith('backup_metadata_') and file.endswith('.json'):
                    filepath = os.path.join(self.backup_dir, file)
                    metadata_files.append((filepath, os.path.getmtime(filepath)))
            
            metadata_files.sort(key=lambda x: x[1], reverse=True)
            
            for metadata_file in metadata_files[self.max_backups:]:
                try:
                    os.remove(metadata_file[0])
                    logger.debug(f"🗑️ Metadato antiguo eliminado: {metadata_file[0]}")
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo eliminar metadato antiguo: {e}")
                    
        except Exception as e:
            logger.error(f"Error limpiando metadatos antiguos: {e}")
    
    def listar_backups(self):
        """Listar backups disponibles (solo metadatos locales)"""
        try:
            if not os.path.exists(self.backup_dir):
                return []
            
            backups = []
            for file in os.listdir(self.backup_dir):
                if file.startswith('backup_metadata_') and file.endswith('.json'):
                    filepath = os.path.join(self.backup_dir, file)
                    try:
                        with open(filepath, 'r') as f:
                            metadata = json.load(f)
                        
                        file_info = {
                            'nombre': file,
                            'ruta': filepath,
                            'fecha': datetime.fromisoformat(metadata['fecha_backup']),
                            'tipo_operacion': metadata['tipo_operacion'],
                            'ubicacion': metadata['ubicacion']
                        }
                        backups.append(file_info)
                    except Exception as e:
                        logger.warning(f"⚠️ Error leyendo metadato {file}: {e}")
            
            return sorted(backups, key=lambda x: x['fecha'], reverse=True)
            
        except Exception as e:
            logger.error(f"Error listando backups: {e}")
            return []

# =============================================================================
# 5. SISTEMA DE NOTIFICACIONES
# =============================================================================

class SistemaNotificaciones:
    """Sistema de notificaciones"""
    
    def __init__(self, config_smtp):
        self.config_smtp = config_smtp
        self.notificaciones_habilitadas = bool(config_smtp.get('email_user'))
    
    def enviar_notificacion(self, tipo_operacion, estado, detalles, destinatarios=None):
        """Enviar notificación por email"""
        try:
            if not self.notificaciones_habilitadas:
                logger.warning("⚠️ Notificaciones por email no configuradas")
                return False
            
            if not destinatarios:
                destinatarios = [self.config_smtp.get('notification_email')]
            
            if not destinatarios or not all(destinatarios):
                logger.warning("⚠️ No hay destinatarios para notificación")
                return False
            
            subject = f"[Sistema Escuela] {tipo_operacion} - {estado}"
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2>📊 Notificación del Sistema</h2>
                <div style="background-color: {'#d4edda' if estado == 'EXITOSA' else '#f8d7da'}; 
                          padding: 15px; border-radius: 5px; margin: 10px 0;">
                    <h3>Estado: <strong>{estado}</strong></h3>
                    <p><strong>Operación:</strong> {tipo_operacion}</p>
                    <p><strong>Fecha:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Usuario:</strong> {st.session_state.get('usuario_actual', {}).get('usuario', 'Desconocido')}</p>
                </div>
                
                <h3>📋 Detalles:</h3>
                <div style="background-color: #f8f9fa; padding: 10px; border-left: 4px solid #007bff;">
                    <pre style="white-space: pre-wrap;">{detalles}</pre>
                </div>
                
                <hr>
                <p style="color: #6c757d; font-size: 0.9em;">
                    Sistema Escuela de Enfermería<br>
                    Este es un mensaje automático, por favor no responder.
                </p>
            </body>
            </html>
            """
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.config_smtp['email_user']
            msg['To'] = ', '.join(destinatarios)
            
            msg.attach(MIMEText(html_content, 'html'))
            
            with smtplib.SMTP(self.config_smtp['smtp_server'], self.config_smtp['smtp_port']) as server:
                server.starttls()
                server.login(self.config_smtp['email_user'], self.config_smtp['email_password'])
                server.send_message(msg)
            
            logger.info(f"✅ Notificación enviada: {tipo_operacion} - {estado}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error enviando notificación: {e}")
            return False
    
    def mostrar_notificacion_streamlit(self, estado, mensaje, tipo="info"):
        """Mostrar notificación en Streamlit"""
        if tipo == "success":
            st.success(f"✅ {mensaje}")
        elif tipo == "error":
            st.error(f"❌ {mensaje}")
        elif tipo == "warning":
            st.warning(f"⚠️ {mensaje}")
        else:
            st.info(f"ℹ️ {mensaje}")

# =============================================================================
# 6. SISTEMA DE AUTENTICACIÓN
# =============================================================================

class SistemaAutenticacion:
    def __init__(self):
        self.sesion_activa = False
        self.usuario_actual = None
        
    def verificar_login(self, usuario, password):
        """Verificar credenciales de usuario contra base de datos remota"""
        try:
            if not usuario or not password:
                st.error("❌ Usuario y contraseña son obligatorios")
                return False
            
            with st.spinner("🔐 Verificando credenciales en servidor remoto..."):
                # Primero verificar si la base de datos existe
                if not gestor_remoto.verificar_existencia_db():
                    st.error("❌ ERROR: Base de datos no encontrada en servidor remoto")
                    st.info("""
                    **Solución:**
                    1. Verifica que la base de datos escuela.db existe en el servidor
                    2. Confirma la ruta en secrets.toml: `db_principal`
                    """)
                    return False
                
                # Verificar credenciales usando la base de datos remota
                usuario_data = db.verificar_login(usuario, password)
                
                if usuario_data:
                    nombre_real = usuario_data.get('nombre_completo', usuario_data.get('usuario', 'Usuario'))
                    
                    st.success(f"✅ ¡Bienvenido(a), {nombre_real}!")
                    st.session_state.login_exitoso = True
                    st.session_state.usuario_actual = usuario_data
                    st.session_state.rol_usuario = usuario_data.get('rol', 'usuario')
                    self.sesion_activa = True
                    self.usuario_actual = usuario_data
                    
                    # Registrar en bitácora
                    db.registrar_bitacora(
                        usuario_data['usuario'],
                        'LOGIN',
                        f'Usuario {usuario_data["usuario"]} inició sesión desde sistema 100% remoto'
                    )
                    
                    estado_sistema.registrar_sesion(exitosa=True)
                    return True
                else:
                    st.error("❌ Usuario o contraseña incorrectos")
                    return False
                    
        except Exception as e:
            st.error(f"❌ Error en el proceso de login: {e}")
            logger.error(f"Error en login: {e}", exc_info=True)
            return False
    
    def cerrar_sesion(self):
        """Cerrar sesión del usuario"""
        try:
            if self.sesion_activa and self.usuario_actual:
                db.registrar_bitacora(
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
            logger.error(f"Error cerrando sesión: {e}", exc_info=True)

# =============================================================================
# 7. SISTEMA PRINCIPAL
# =============================================================================

class SistemaPrincipal:
    def __init__(self):
        self.gestor = gestor_remoto
        self.db = db
        self.backup_system = SistemaBackupAutomatico(self.gestor)
        self.notificaciones = SistemaNotificaciones(
            gestor_remoto.config
        )
        self.validador = ValidadorDatos()
        
        self.current_page_inscritos = 1
        self.current_page_estudiantes = 1
        self.current_page_egresados = 1
        self.current_page_contratados = 1
        self.current_page_usuarios = 1
        
        self.search_term_inscritos = ""
        self.search_term_estudiantes = ""
        self.search_term_egresados = ""
        self.search_term_contratados = ""
        self.search_term_usuarios = ""
        
        self.df_inscritos = pd.DataFrame()
        self.df_estudiantes = pd.DataFrame()
        self.df_egresados = pd.DataFrame()
        self.df_contratados = pd.DataFrame()
        self.df_usuarios = pd.DataFrame()
        
        self.total_pages_inscritos = 0
        self.total_pages_estudiantes = 0
        self.total_pages_egresados = 0
        self.total_pages_contratados = 0
        self.total_pages_usuarios = 0
        
        self.total_inscritos = 0
        self.total_estudiantes = 0
        self.total_egresados = 0
        self.total_contratados = 0
        self.total_usuarios = 0
        
    def cargar_datos_paginados(self):
        """Cargar datos desde la base de datos remota con paginación"""
        try:
            with st.spinner("📊 Cargando datos desde servidor remoto..."):
                self.df_inscritos, self.total_pages_inscritos, self.total_inscritos = self.db.obtener_inscritos(
                    page=self.current_page_inscritos,
                    search_term=self.search_term_inscritos
                )
                
                self.df_estudiantes, self.total_pages_estudiantes, self.total_estudiantes = self.db.obtener_estudiantes(
                    page=self.current_page_estudiantes,
                    search_term=self.search_term_estudiantes
                )
                
                self.df_egresados, self.total_pages_egresados, self.total_egresados = self.db.obtener_egresados(
                    page=self.current_page_egresados,
                    search_term=self.search_term_egresados
                )
                
                self.df_contratados, self.total_pages_contratados, self.total_contratados = self.db.obtener_contratados(
                    page=self.current_page_contratados,
                    search_term=self.search_term_contratados
                )
                
                self.df_usuarios, self.total_pages_usuarios, self.total_usuarios = self.db.obtener_usuarios(
                    page=self.current_page_usuarios,
                    search_term=self.search_term_usuarios
                )
                
                logger.info(f"""
                📊 Datos cargados desde base de datos única:
                - Inscritos: {self.total_inscritos} registros (página {self.current_page_inscritos}/{self.total_pages_inscritos})
                - Estudiantes: {self.total_estudiantes} registros (página {self.current_page_estudiantes}/{self.total_pages_estudiantes})
                - Egresados: {self.total_egresados} registros (página {self.current_page_egresados}/{self.total_pages_egresados})
                - Contratados: {self.total_contratados} registros (página {self.current_page_contratados}/{self.total_pages_contratados})
                - Usuarios: {self.total_usuarios} registros (página {self.current_page_usuarios}/{self.total_pages_usuarios})
                """)
                
        except Exception as e:
            logger.error(f"Error cargando datos remotos: {e}", exc_info=True)
            st.error(f"❌ Error cargando datos: {e}")

# =============================================================================
# 8. INTERFAZ STREAMLIT
# =============================================================================

# Instancias globales de los servicios
estado_sistema = EstadoPersistente()
gestor_remoto = GestorConexionRemota()
db = SistemaBaseDatos()
auth = SistemaAutenticacion()
sistema_principal = None

def mostrar_login():
    """Interfaz de login"""
    st.title("🏥 Sistema Escuela Enfermería - Base de Datos Única")
    st.markdown("---")
    
    # Mostrar estado de conexión
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if gestor_remoto.verificar_existencia_db():
            st.success("✅ Base de datos encontrada")
        else:
            st.error("❌ Base de datos NO encontrada")
    
    with col2:
        if estado_sistema.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
        else:
            st.error("❌ SSH Desconectado")
    
    with col3:
        st.info(f"📁 DB: escuela.db")
    
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            st.subheader("Iniciar Sesión")
            
            usuario = st.text_input("👤 Usuario", placeholder="usuario", key="login_usuario")
            password = st.text_input("🔒 Contraseña", type="password", placeholder="contraseña", key="login_password")
            
            login_button = st.form_submit_button("🚀 Iniciar Sesión", use_container_width=True)

            if login_button:
                if usuario and password:
                    with st.spinner("Verificando credenciales..."):
                        if auth.verificar_login(usuario, password):
                            st.success("✅ Login exitoso")
                            st.rerun()
                        else:
                            st.error("❌ Credenciales incorrectas")
                else:
                    st.warning("⚠️ Complete todos los campos")
            
            with st.expander("ℹ️ Información de acceso"):
                st.info("""
                **Configuración del sistema:**
                
                1. ✅ **Base de datos única:** escuela.db
                2. ✅ **Conexión SSH:** Al servidor remoto
                3. ✅ **Usuario admin:** Debe existir en la tabla usuarios
                
                **Base de datos:** Todos los datos se almacenan en el servidor remoto.
                """)

def mostrar_interfaz_principal():
    """Interfaz principal después del login"""
    global sistema_principal
    
    usuario_actual = st.session_state.usuario_actual
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

    with col1:
        st.title("🏥 Sistema Escuela Enfermería - Base de Datos Única")
        nombre_usuario = usuario_actual.get('nombre_completo', usuario_actual.get('usuario', 'Usuario'))
        st.write(f"**👤 Usuario:** {nombre_usuario} | **🎭 Rol:** {usuario_actual.get('rol', 'usuario')}")

    with col2:
        if gestor_remoto.config.get('ssh_host'):
            st.write(f"**🔗 Conectado al servidor**")

    with col3:
        if st.button("🔄 Recargar Datos", use_container_width=True):
            if sistema_principal:
                sistema_principal.cargar_datos_paginados()
            st.rerun()

    with col4:
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            auth.cerrar_sesion()
            st.rerun()

    st.markdown("---")

    if sistema_principal is None:
        sistema_principal = SistemaPrincipal()

    menu_opciones = [
        "📊 Dashboard",
        "📝 Inscritos",
        "🎓 Estudiantes",
        "🏆 Egresados",
        "💼 Contratados",
        "👥 Usuarios",
        "⚙️ Configuración"
    ]

    opcion_seleccionada = st.sidebar.selectbox("Menú Principal", menu_opciones)

    if opcion_seleccionada == "📊 Dashboard":
        mostrar_dashboard()
    elif opcion_seleccionada == "📝 Inscritos":
        mostrar_inscritos()
    elif opcion_seleccionada == "🎓 Estudiantes":
        mostrar_estudiantes()
    elif opcion_seleccionada == "🏆 Egresados":
        mostrar_egresados()
    elif opcion_seleccionada == "💼 Contratados":
        mostrar_contratados()
    elif opcion_seleccionada == "👥 Usuarios":
        mostrar_usuarios()
    elif opcion_seleccionada == "⚙️ Configuración":
        mostrar_configuracion()

def mostrar_dashboard():
    """Dashboard principal"""
    global sistema_principal
    st.header("📊 Dashboard - Base de Datos Única")
    
    if sistema_principal is None:
        st.error("❌ Sistema principal no inicializado")
        return
    
    # Cargar datos si no están cargados
    if sistema_principal.total_inscritos == 0:
        sistema_principal.cargar_datos_paginados()
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("👥 Inscritos", sistema_principal.total_inscritos)
    
    with col2:
        st.metric("🎓 Estudiantes", sistema_principal.total_estudiantes)
    
    with col3:
        st.metric("🏆 Egresados", sistema_principal.total_egresados)
    
    with col4:
        st.metric("💼 Contratados", sistema_principal.total_contratados)
    
    with col5:
        st.metric("👤 Usuarios", sistema_principal.total_usuarios)
    
    st.markdown("---")
    
    # Información del sistema
    col_info1, col_info2 = st.columns(2)
    
    with col_info1:
        st.subheader("🔗 Estado del Sistema")
        
        if estado_sistema.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
        else:
            st.error("❌ SSH Desconectado")
        
        if gestor_remoto.verificar_existencia_db():
            st.success("✅ Base de datos en servidor remoto")
        else:
            st.error("❌ Base de datos NO encontrada en servidor")
        
        stats = estado_sistema.estado.get('estadisticas_sistema', {})
        st.write(f"📈 Sesiones exitosas: {stats.get('sesiones', 0)}")
        st.write(f"🔄 Backups realizados: {estado_sistema.estado.get('backups_realizados', 0)}")
        st.write(f"🗑️ Registros eliminados: {estado_sistema.estado.get('registros_incompletos_eliminados', 0)}")
    
    with col_info2:
        st.subheader("📋 Tablas Disponibles")
        try:
            consulta = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            resultado = db.ejecutar_consulta_remota(consulta)
            
            if resultado:
                st.write(f"✅ {len(resultado)} tablas en base de datos:")
                for tabla in resultado:
                    nombre_tabla = tabla.get('name', '')
                    count_consulta = f"SELECT COUNT(*) as total FROM {nombre_tabla}"
                    count_result = db.ejecutar_consulta_remota(count_consulta)
                    count = count_result[0].get('total', 0) if count_result else 0
                    st.write(f"- **{nombre_tabla}**: {count} registros")
            else:
                st.info("ℹ️ No se pudieron obtener las tablas")
        except:
            st.info("ℹ️ No se pudieron obtener las tablas")
    
    st.markdown("---")
    st.subheader("🚀 Acciones Rápidas")
    
    col_act1, col_act2, col_act3 = st.columns(3)
    
    with col_act1:
        if st.button("📊 Cargar Datos", use_container_width=True):
            with st.spinner("Cargando datos desde servidor..."):
                sistema_principal.cargar_datos_paginados()
                st.success("✅ Datos cargados")
                st.rerun()
    
    with col_act2:
        if st.button("💾 Crear Backup", use_container_width=True):
            with st.spinner("Creando backup..."):
                if sistema_principal:
                    backup_path = sistema_principal.backup_system.crear_backup(
                        "MANUAL_DASHBOARD",
                        "Backup manual creado desde dashboard"
                    )
                    if backup_path:
                        st.success(f"✅ Backup creado en servidor remoto")
                    else:
                        st.error("❌ Error creando backup")
    
    with col_act3:
        if st.button("🔗 Probar Conexión", use_container_width=True):
            with st.spinner("Probando conexión..."):
                if gestor_remoto.verificar_conexion_ssh():
                    st.success("✅ Conexión SSH exitosa")
                    st.rerun()
                else:
                    st.error("❌ Conexión SSH fallida")

def mostrar_inscritos():
    """Interfaz para gestión de inscritos"""
    global sistema_principal
    st.header("📝 Gestión de Inscritos")
    
    if sistema_principal is None:
        sistema_principal = SistemaPrincipal()
    
    # Cargar datos si no están cargados
    if sistema_principal.df_inscritos.empty:
        sistema_principal.cargar_datos_paginados()
    
    tab1, tab2, tab3 = st.tabs(["📋 Lista de Inscritos", "➕ Agregar Inscrito", "⚡ Acciones Rápidas"])
    
    with tab1:
        if sistema_principal.total_inscritos == 0:
            st.warning("📭 No hay inscritos registrados")
        else:
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            
            with col_stat1:
                st.metric("Total Inscritos", sistema_principal.total_inscritos)
            
            with col_stat2:
                st.metric("Página Actual", f"{sistema_principal.current_page_inscritos}/{max(1, sistema_principal.total_pages_inscritos)}")
            
            with col_stat3:
                registros_pagina = len(sistema_principal.df_inscritos)
                st.metric("En esta página", registros_pagina)
            
            st.subheader("🔍 Buscar Inscrito")
            search_term = st.text_input(
                "Buscar por matrícula, nombre o email:", 
                value=sistema_principal.search_term_inscritos,
                key="search_inscritos"
            )
            
            if st.button("🔎 Buscar", key="btn_buscar_inscritos"):
                sistema_principal.search_term_inscritos = search_term
                sistema_principal.current_page_inscritos = 1
                sistema_principal.cargar_datos_paginados()
                st.rerun()
            
            if not sistema_principal.df_inscritos.empty:
                st.dataframe(
                    sistema_principal.df_inscritos,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("ℹ️ No hay inscritos que coincidan con la búsqueda")
            
            # Navegación de páginas
            if sistema_principal.total_pages_inscritos > 1:
                col_prev, col_page, col_next = st.columns([1, 2, 1])
                
                with col_prev:
                    if sistema_principal.current_page_inscritos > 1:
                        if st.button("⬅️ Anterior", key="prev_inscritos"):
                            sistema_principal.current_page_inscritos -= 1
                            sistema_principal.cargar_datos_paginados()
                            st.rerun()
                
                with col_page:
                    st.write(f"**Página {sistema_principal.current_page_inscritos} de {sistema_principal.total_pages_inscritos}**")
                
                with col_next:
                    if sistema_principal.current_page_inscritos < sistema_principal.total_pages_inscritos:
                        if st.button("Siguiente ➡️", key="next_inscritos"):
                            sistema_principal.current_page_inscritos += 1
                            sistema_principal.cargar_datos_paginados()
                            st.rerun()
    
    with tab2:
        st.subheader("➕ Agregar Nuevo Inscrito")
        
        with st.form("form_agregar_inscrito"):
            col_i1, col_i2 = st.columns(2)
            
            with col_i1:
                nombre_completo = st.text_input("Nombre Completo*", placeholder="Nombre Apellidos")
                email = st.text_input("Email*", placeholder="correo@ejemplo.com")
                telefono = st.text_input("Teléfono", placeholder="Número telefónico")
            
            with col_i2:
                programa_interes = st.selectbox("Programa de Interés*", ["", "Licenciatura en Enfermería", "Especialidad en Enfermería Clínica", "Maestría en Ciencias de la Salud", "Diplomado en Salud Pública", "Curso de RCP Básico"])
                fecha_nacimiento = st.date_input("Fecha de Nacimiento", value=datetime(2000, 1, 1))
                documentos_subidos = st.number_input("Documentos Subidos", min_value=0, max_value=20, value=0)
            
            submit_inscrito = st.form_submit_button("📝 Registrar Inscrito")
            
            if submit_inscrito:
                if not nombre_completo or not email or not programa_interes:
                    st.error("❌ Los campos marcados con * son obligatorios")
                elif not ValidadorDatos.validar_email(email):
                    st.error("❌ Formato de email inválido")
                elif not ValidadorDatos.validar_nombre_completo(nombre_completo):
                    st.error("❌ Nombre completo debe tener al menos 2 palabras")
                else:
                    inscrito_data = {
                        'nombre_completo': nombre_completo,
                        'email': email,
                        'telefono': telefono,
                        'programa_interes': programa_interes,
                        'fecha_nacimiento': fecha_nacimiento.strftime('%Y-%m-%d') if fecha_nacimiento else None,
                        'documentos_subidos': documentos_subidos,
                        'estatus': 'Pre-inscrito'
                    }
                    
                    if db.agregar_inscrito(inscrito_data):
                        st.success("✅ Inscrito agregado exitosamente")
                        
                        # Crear backup automático
                        sistema_principal.backup_system.crear_backup(
                            "AGREGAR_INSCRITO",
                            f"Nuevo inscrito: {nombre_completo} - {email}"
                        )
                        
                        # Enviar notificación
                        sistema_principal.notificaciones.mostrar_notificacion_streamlit(
                            "success",
                            f"Inscrito {nombre_completo} agregado exitosamente"
                        )
                        
                        sistema_principal.cargar_datos_paginados()
                        st.rerun()
                    else:
                        st.error("❌ Error agregando inscrito")
    
    with tab3:
        st.subheader("⚡ Acciones Rápidas")
        
        col_acc1, col_acc2 = st.columns(2)
        
        with col_acc1:
            if st.button("🗑️ Eliminar Duplicados", use_container_width=True):
                with st.spinner("Buscando duplicados..."):
                    st.info("🔍 Función de eliminación de duplicados en desarrollo")
        
        with col_acc2:
            if st.button("📧 Enviar Recordatorios", use_container_width=True):
                with st.spinner("Enviando recordatorios..."):
                    st.info("📧 Función de recordatorios en desarrollo")

def mostrar_estudiantes():
    """Interfaz para gestión de estudiantes"""
    global sistema_principal
    st.header("🎓 Gestión de Estudiantes")
    
    if sistema_principal is None:
        sistema_principal = SistemaPrincipal()
    
    # Cargar datos si no están cargados
    if sistema_principal.df_estudiantes.empty:
        sistema_principal.cargar_datos_paginados()
    
    if sistema_principal.total_estudiantes == 0:
        st.warning("🎓 No hay estudiantes registrados")
    else:
        st.dataframe(
            sistema_principal.df_estudiantes,
            use_container_width=True,
            hide_index=True
        )
        
        st.info(f"📊 Total de estudiantes: {sistema_principal.total_estudiantes}")

def mostrar_egresados():
    """Interfaz para gestión de egresados"""
    global sistema_principal
    st.header("🏆 Gestión de Egresados")
    
    if sistema_principal is None:
        sistema_principal = SistemaPrincipal()
    
    # Cargar datos si no están cargados
    if sistema_principal.df_egresados.empty:
        sistema_principal.cargar_datos_paginados()
    
    if sistema_principal.total_egresados == 0:
        st.warning("🏆 No hay egresados registrados")
    else:
        st.dataframe(
            sistema_principal.df_egresados,
            use_container_width=True,
            hide_index=True
        )
        
        st.info(f"📊 Total de egresados: {sistema_principal.total_egresados}")

def mostrar_contratados():
    """Interfaz para gestión de contratados"""
    global sistema_principal
    st.header("💼 Gestión de Contratados")
    
    if sistema_principal is None:
        sistema_principal = SistemaPrincipal()
    
    # Cargar datos si no están cargados
    if sistema_principal.df_contratados.empty:
        sistema_principal.cargar_datos_paginados()
    
    if sistema_principal.total_contratados == 0:
        st.warning("💼 No hay contratados registrados")
    else:
        st.dataframe(
            sistema_principal.df_contratados,
            use_container_width=True,
            hide_index=True
        )
        
        st.info(f"📊 Total de contratados: {sistema_principal.total_contratados}")

def mostrar_usuarios():
    """Interfaz para gestión de usuarios"""
    global sistema_principal
    st.header("👥 Gestión de Usuarios")
    
    if sistema_principal is None:
        sistema_principal = SistemaPrincipal()
    
    # Cargar datos si no están cargados
    if sistema_principal.df_usuarios.empty:
        sistema_principal.cargar_datos_paginados()
    
    if sistema_principal.total_usuarios == 0:
        st.warning("📭 No hay usuarios registrados")
    else:
        st.dataframe(
            sistema_principal.df_usuarios,
            use_container_width=True,
            hide_index=True
        )
        
        st.info(f"📊 Total de usuarios: {sistema_principal.total_usuarios}")
    
    st.subheader("➕ Agregar Nuevo Usuario")
    
    with st.form("form_agregar_usuario"):
        col_u1, col_u2 = st.columns(2)
        
        with col_u1:
            usuario = st.text_input("Usuario*", placeholder="nuevo_usuario")
            password = st.text_input("Contraseña*", type="password", placeholder="********")
            rol = st.selectbox("Rol*", ["administrador", "usuario", "estudiante"])
        
        with col_u2:
            nombre_completo = st.text_input("Nombre Completo*", placeholder="Nombre Apellido")
            email = st.text_input("Email*", placeholder="usuario@ejemplo.com")
            matricula = st.text_input("Matrícula", placeholder="USR-001")
        
        submit_usuario = st.form_submit_button("👤 Crear Usuario")
        
        if submit_usuario:
            if not usuario or not password or not rol or not nombre_completo or not email:
                st.error("❌ Los campos marcados con * son obligatorios")
            elif not ValidadorDatos.validar_email(email):
                st.error("❌ Formato de email inválido")
            else:
                usuario_data = {
                    'usuario': usuario,
                    'password': password,
                    'rol': rol,
                    'nombre_completo': nombre_completo,
                    'email': email,
                    'matricula': matricula if matricula else None,
                    'activo': True
                }
                
                if db.agregar_usuario(usuario_data):
                    st.success(f"✅ Usuario {usuario} creado exitosamente")
                    
                    # Crear backup automático
                    sistema_principal.backup_system.crear_backup(
                        "AGREGAR_USUARIO",
                        f"Nuevo usuario: {usuario} - {rol}"
                    )
                    
                    sistema_principal.cargar_datos_paginados()
                    st.rerun()
                else:
                    st.error("❌ Error creando usuario")

def mostrar_configuracion():
    """Interfaz para configuración del sistema"""
    global sistema_principal
    st.header("⚙️ Configuración del Sistema")

    if sistema_principal is None:
        st.error("❌ Sistema principal no inicializado")
        return

    st.subheader("🔧 Información del Sistema")

    col_info1, col_info2 = st.columns(2)

    with col_info1:
        st.write("📊 Estado del Sistema:")
        if gestor_remoto.verificar_existencia_db():
            st.success("✅ Base de datos encontrada en servidor remoto")
        else:
            st.error("❌ Base de datos NO encontrada en servidor")

        if estado_sistema.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
        else:
            st.error("❌ SSH Desconectado")
            error_ssh = estado_sistema.estado.get('ssh_error')
            if error_ssh:
                st.error(f"⚠️ Error: {error_ssh}")

    with col_info2:
        st.write("💾 Base de Datos Única:")
        db_path = gestor_remoto.db_path_remoto
        st.write(f"📁 Ruta: {db_path}")
        
        try:
            consulta = "SELECT COUNT(*) as total_tablas FROM sqlite_master WHERE type='table'"
            resultado = db.ejecutar_consulta_remota(consulta)
            if resultado and len(resultado) > 0:
                total_tablas = resultado[0].get('total_tablas', 0)
                st.write(f"📊 Tablas: {total_tablas}")
        except:
            pass
    
    st.markdown("---")
    st.subheader("🛠️ Herramientas del Sistema")
    
    col_tool1, col_tool2, col_tool3 = st.columns(3)
    
    with col_tool1:
        if st.button("💾 Crear Backup", use_container_width=True):
            with st.spinner("Creando backup..."):
                if gestor_remoto.crear_backup_remoto():
                    st.success("✅ Backup creado en servidor remoto")
                else:
                    st.error("❌ Error creando backup")
    
    with col_tool2:
        if st.button("🔍 Verificar Conexión", use_container_width=True):
            with st.spinner("Verificando conexión..."):
                if gestor_remoto.verificar_conexion_ssh():
                    st.success("✅ Conexión SSH verificada")
                    st.rerun()
                else:
                    st.error("❌ Error en conexión SSH")
    
    with col_tool3:
        if st.button("📊 Ver Tablas DB", use_container_width=True):
            try:
                consulta = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                resultado = db.ejecutar_consulta_remota(consulta)
                
                if resultado:
                    st.success(f"✅ {len(resultado)} tablas en base de datos:")
                    for tabla in resultado:
                        nombre_tabla = tabla.get('name', '')
                        count_consulta = f"SELECT COUNT(*) as total FROM {nombre_tabla}"
                        count_result = db.ejecutar_consulta_remota(count_consulta)
                        count = count_result[0].get('total', 0) if count_result else 0
                        st.write(f"- **{nombre_tabla}**: {count} registros")
                else:
                    st.error("❌ No hay tablas en la base de datos")
            except Exception as e:
                st.error(f"❌ Error: {e}")
    
    st.markdown("---")
    st.subheader("📁 Sistema de Backups")
    
    backups = SistemaBackupAutomatico(gestor_remoto).listar_backups()
    if backups:
        st.write(f"📊 {len(backups)} backups registrados:")
        for backup in backups[:5]:  # Mostrar solo los últimos 5
            fecha_str = backup['fecha'].strftime('%Y-%m-%d %H:%M')
            st.write(f"📅 {fecha_str} - {backup['tipo_operacion']}")
    else:
        st.info("ℹ️ No hay backups registrados")

# =============================================================================
# 9. EJECUCIÓN PRINCIPAL
# =============================================================================

def main():
    """Función principal de la aplicación"""
    
    with st.sidebar:
        st.title("🔧 Sistema Escuela - DB Única")
        st.markdown("---")

        st.subheader("🔗 Estado de Conexión")

        if gestor_remoto.verificar_existencia_db():
            st.success("✅ Base de datos remota")
        else:
            st.error("❌ Base de datos NO encontrada")

        if estado_sistema.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
        else:
            st.error("❌ SSH Desconectado")

        st.markdown("---")

        st.subheader("📈 Estadísticas")
        stats = estado_sistema.estado.get('estadisticas_sistema', {})

        col_stat1, col_stat2 = st.columns(2)
        with col_stat1:
            st.metric("Sesiones", stats.get('sesiones', 0))
        with col_stat2:
            st.metric("Backups", estado_sistema.estado.get('backups_realizados', 0))

        st.markdown("---")

        st.subheader("💾 Sistema de Backups")

        if st.button("💾 Crear Backup", use_container_width=True):
            global sistema_principal
            if sistema_principal:
                with st.spinner("Creando backup..."):
                    backup_path = sistema_principal.backup_system.crear_backup(
                        "MANUAL_SIDEBAR",
                        "Backup manual creado desde sidebar"
                    )
                    if backup_path:
                        st.success(f"✅ Backup creado")
                    else:
                        st.error("❌ Error creando backup")

        st.markdown("---")

        st.caption("🏥 Sistema Escuela Enfermería v3.0")
        st.caption("📁 Base de datos única: escuela.db")
        st.caption("🔗 Conexión SSH directa al servidor")

    try:
        session_defaults = {
            'login_exitoso': False,
            'usuario_actual': None,
            'rol_usuario': None
        }

        for key, default_value in session_defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default_value

        if not gestor_remoto.config.get('ssh_host'):
            st.error("""
            ❌ **ERROR DE CONFIGURACIÓN**

            No se encontró configuración SSH en secrets.toml.

            **Verifica que secrets.toml contiene la configuración necesaria:**
            ```toml
            [ssh]
            host = "tu_servidor"
            port = 22
            username = "tu_usuario"
            password = "tu_contraseña"

            [paths]
            db_principal = "/ruta/a/escuela.db"
            ```
            """)
            return

        if not st.session_state.login_exitoso:
            mostrar_login()
        else:
            mostrar_interfaz_principal()

    except Exception as e:
        logger.error(f"Error crítico en main(): {e}", exc_info=True)
        st.error(f"❌ Error crítico en la aplicación: {str(e)}")

# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    try:
        st.info("""
        🏥 **SISTEMA DE GESTIÓN ESCOLAR - BASE DE DATOS ÚNICA**

        **Características:**
        ✅ **Base de datos única:** escuela.db con todas las tablas
        ✅ **Conexión SSH directa** al servidor remoto
        ✅ **Gestión completa** de inscritos, estudiantes, egresados, contratados y usuarios
        ✅ **Sistema de notificaciones** por email
        ✅ **Backup automático** en servidor remoto
        ✅ **Bitácora de auditoría** de todas las operaciones
        ✅ **Interfaz Streamlit** optimizada
        
        **Base de datos:** Todas las operaciones se realizan directamente en el servidor remoto.
        """)

        main()
    except Exception as e:
        st.error(f"❌ Error crítico en la aplicación: {e}")
        logger.critical(f"Error crítico en sistema: {e}", exc_info=True)
