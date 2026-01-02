#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SISTEMA DE GESTIÓN DE ASPIRANTES - VERSIÓN 3.8 (TRABAJO REMOTO COMPLETO)
Sistema completo que trabaja directamente en el servidor remoto
VERSIÓN CORREGIDA: Compatibilidad completa con secrets.toml
VERSIÓN 4.0.0: CONFIGURACIÓN UNIFICADA CON SECRETS.TOML
"""

# ============================================================================
# CAPA 1: IMPORTS Y CONFIGURACIÓN COMPLETA
# ============================================================================

import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import json
import tempfile
import os
import sys
import traceback
from datetime import datetime, date, timedelta
import time
import random
import string
import hashlib
import zipfile
import io
import base64
from pathlib import Path
import logging
import paramiko
from paramiko import SSHClient, AutoAddPolicy
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import warnings
import psutil
import socket
import re
import glob
import atexit
import math
from contextlib import contextmanager
from typing import Optional, Dict, Any, List, Tuple
import shutil

warnings.filterwarnings('ignore')

# Intentar importar tomllib/tomli
try:
    import tomllib
    HAS_TOMLLIB = True
except ImportError:
    try:
        import tomli as tomllib
        HAS_TOMLLIB = True
    except ImportError:
        HAS_TOMLLIB = False
        st.warning("⚠️ Instalar tomli: pip install tomli")
        # Continuar sin tomllib

# ============================================================================
# CAPA 2: CONSTANTES, CONFIGURACIÓN Y DATOS ESTÁTICOS
# ============================================================================

# Configuración de la aplicación
APP_CONFIG = {
    'app_name': 'Sistema Escuela Enfermería',
    'version': '4.0.0',  # Versión actualizada - CONFIGURACIÓN UNIFICADA
    'page_title': 'Sistema Escuela Enfermería - Pre-Inscripción',
    'page_icon': '🏥',
    'layout': 'wide',
    'sidebar_state': 'expanded',
    'backup_dir': 'backups_aspirantes',
    'uploads_dir': 'uploads',
    'max_backups': 10,
    'estado_file': 'estado_aspirantes.json',
    'session_timeout': 60  # minutos
}

# Constantes de tiempo
TIME_CONFIG = {
    'recordatorio_dias': 14,
    'limpieza_inactividad_dias': 7,
    'ssh_connect_timeout': 30,
    'ssh_command_timeout': 60,
    'sftp_transfer_timeout': 300,
    'db_download_timeout': 180,
    'retry_attempts': 3,
    'retry_delay_base': 5
}

# Categorías académicas CORREGIDAS (solo 3 categorías sin redundancia)
CATEGORIAS_ACADEMICAS = [
    {"id": "pregrado", "nombre": "Pregrado", "descripcion": "Programas técnicos y profesional asociado (incluye licenciaturas)"},
    {"id": "posgrado", "nombre": "Posgrado", "descripcion": "Especialidades, maestrías y doctorados"},
    {"id": "educacion_continua", "nombre": "Educación Continua", "descripcion": "Diplomados, cursos y talleres"}
]

# Tipos de programa
TIPOS_PROGRAMA = ["LICENCIATURA", "ESPECIALIDAD", "MAESTRIA", "DIPLOMADO", "CURSO"]

# Documentos base para todos los programas
DOCUMENTOS_BASE = [
    "Certificado preparatoria (promedio ≥ 8.0)",
    "Acta nacimiento (≤ 3 meses)",
    "CURP (≤ 1 mes)",
    "Cartilla Nacional de Salud",
    "INE del tutor",
    "Comprobante domicilio (≤ 3 meses)",
    "Certificado médico institucional (≤ 1 mes)",
    "12 fotografías infantiles B/N"
]

# Testimonios
TESTIMONIOS = [
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
    }
]

# ============================================================================
# CAPA 3: LOGGING Y MANEJO DE ESTADO
# ============================================================================

class EnhancedLogger:
    """Logger mejorado con diferentes niveles y formato detallado"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        file_handler = logging.FileHandler('aspirantes_detallado.log', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
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

class EstadoPersistente:
    """Maneja el estado persistente para el sistema de aspirantes"""
    
    def __init__(self, archivo_estado="estado_aspirantes.json"):
        self.archivo_estado = archivo_estado
        self.estado = self._cargar_estado()
    
    def _cargar_estado(self):
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
        return {
            'db_inicializada': False,
            'fecha_inicializacion': None,
            'ultima_sincronizacion': None,
            'modo_operacion': 'remoto',
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
            'registros_incompletos_eliminados': 0,
            'archivos_subidos_remoto': 0
        }
    
    def guardar_estado(self):
        try:
            with open(self.archivo_estado, 'w') as f:
                json.dump(self.estado, f, indent=2, default=str)
            logger.debug(f"Estado guardado en {self.archivo_estado}")
        except Exception as e:
            logger.error(f"❌ Error guardando estado: {e}")
    
    def marcar_db_inicializada(self):
        self.estado['db_inicializada'] = True
        self.estado['fecha_inicializacion'] = datetime.now().isoformat()
        self.guardar_estado()
    
    def registrar_recordatorio(self):
        self.estado['recordatorios_enviados'] = self.estado.get('recordatorios_enviados', 0) + 1
        self.guardar_estado()
    
    def registrar_duplicado_eliminado(self):
        self.estado['duplicados_eliminados'] = self.estado.get('duplicados_eliminados', 0) + 1
        self.guardar_estado()
    
    def registrar_registro_incompleto_eliminado(self, cantidad=1):
        self.estado['registros_incompletos_eliminados'] = self.estado.get('registros_incompletos_eliminados', 0) + cantidad
        self.guardar_estado()
    
    def set_total_inscritos(self, total):
        self.estado['total_inscritos'] = total
        self.guardar_estado()
    
    def set_ssh_conectado(self, conectado, error=None):
        self.estado['ssh_conectado'] = conectado
        self.estado['ssh_error'] = error
        self.estado['ultima_verificacion'] = datetime.now().isoformat()
        self.guardar_estado()
    
    def marcar_sincronizacion(self):
        self.estado['ultima_sincronizacion'] = datetime.now().isoformat()
        self.guardar_estado()
    
    def registrar_sesion(self, exitosa=True, tiempo_ejecucion=0):
        self.estado['sesiones_iniciadas'] = self.estado.get('sesiones_iniciadas', 0) + 1
        self.estado['ultima_sesion'] = datetime.now().isoformat()
        
        if exitosa:
            self.estado['estadisticas_sistema']['sesiones'] += 1
        
        self.estado['estadisticas_sistema']['total_tiempo'] += tiempo_ejecucion
        self.guardar_estado()
    
    def registrar_backup(self):
        self.estado['backups_realizados'] = self.estado.get('backups_realizados', 0) + 1
        self.guardar_estado()
    
    def registrar_archivo_subido_remoto(self, cantidad=1):
        self.estado['archivos_subidos_remoto'] = self.estado.get('archivos_subidos_remoto', 0) + cantidad
        self.guardar_estado()
    
    def esta_inicializada(self):
        return self.estado.get('db_inicializada', False)
    
    def obtener_fecha_inicializacion(self):
        fecha_str = self.estado.get('fecha_inicializacion')
        if fecha_str:
            try:
                return datetime.fromisoformat(fecha_str)
            except:
                return None
        return None

estado_sistema = EstadoPersistente()

# ============================================================================
# CAPA 4: UTILIDADES Y SERVICIOS BASE
# ============================================================================

class UtilidadesSistema:
    """Utilidades para verificación de disco y red"""
    
    @staticmethod
    def verificar_espacio_disco(ruta, espacio_minimo_mb=100):
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
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except Exception as e:
            logger.warning(f"Sin conectividad de red: {e}")
            return False

class ValidadorDatos:
    """Clase para validaciones de datos mejoradas"""
    
    @staticmethod
    def validar_email(email):
        if not email:
            return False
        
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validar_email_gmail(email):
        if not email:
            return False
        
        pattern = r'^[a-zA-Z0-9._%+-]+@gmail\.com$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validar_telefono(telefono):
        if not telefono:
            return True
        
        digitos = ''.join(filter(str.isdigit, telefono))
        return len(digitos) >= 10
    
    @staticmethod
    def validar_nombre_completo(nombre):
        if not nombre:
            return False
        palabras = nombre.strip().split()
        return len(palabras) >= 2
    
    @staticmethod
    def validar_fecha_nacimiento(fecha_str):
        try:
            if not fecha_str:
                return True
            
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            hoy = date.today()
            
            if fecha > hoy:
                return False
            
            edad = hoy.year - fecha.year - ((hoy.month, hoy.day) < (fecha.month, fecha.day))
            return edad >= 15
        except:
            return False
    
    @staticmethod
    def validar_matricula(matricula):
        if not matricula:
            return False
        return matricula.startswith('INS') and len(matricula) >= 10
    
    @staticmethod
    def validar_folio(folio):
        if not folio:
            return False
        return folio.startswith('FOL') and len(folio) >= 10

def cargar_configuracion_secrets():
    """Cargar configuración desde secrets.toml - VERSIÓN UNIFICADA"""
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
            logger.info(f"✅ Configuración cargada desde: {ruta_encontrada}")
            return config
        
    except Exception as e:
        logger.error(f"❌ Error cargando secrets.toml: {e}", exc_info=True)
        return {}

# ============================================================================
# CAPA 5: GESTIÓN DE CONEXIÓN SSH COMPLETA CON SUBIDA DE ARCHIVOS
# ============================================================================

class GestorConexionRemota:
    """Gestor de conexión SSH al servidor remoto con gestión completa de archivos - VERSIÓN UNIFICADA"""
    
    def __init__(self):
        self.ssh = None
        self.sftp = None
        self.temp_files = []
        
        self.auto_connect = True
        self.config_completa = cargar_configuracion_secrets()
        
        if not self.config_completa:
            logger.error("❌ No se pudo cargar configuración de secrets.toml")
            self.config = {}
            return
            
        self.config = self._cargar_configuracion_completa()
        
        # Configurar reintentos desde secrets.toml
        if 'system' in self.config_completa:
            sys_config = self.config_completa['system']
            self.retry_attempts = sys_config.get('retry_attempts', 3)
            self.retry_delay_base = sys_config.get('retry_delay', 5)
        else:
            self.retry_attempts = TIME_CONFIG['retry_attempts']
            self.retry_delay_base = TIME_CONFIG['retry_delay_base']
        
        self.timeouts = {
            'ssh_connect': TIME_CONFIG['ssh_connect_timeout'],
            'ssh_command': TIME_CONFIG['ssh_command_timeout'],
            'sftp_transfer': TIME_CONFIG['sftp_transfer_timeout'],
            'db_download': TIME_CONFIG['db_download_timeout']
        }
        
        atexit.register(self._limpiar_archivos_temporales)
        
        if not self.config.get('host'):
            logger.warning("⚠️ No hay configuración SSH en secrets.toml")
            return
        
        # Usar las rutas de secrets.toml UNIFICADAS
        self.db_path_remoto = self.config.get('db_principal')
        self.uploads_path_remoto = self.config.get('uploads_path')
        self.uploads_inscritos_remoto = self.config.get('uploads_inscritos')
        
        logger.info(f"🔗 Configuración SSH cargada para {self.config.get('host', 'No configurado')}")
        logger.info(f"📁 Ruta base uploads: {self.uploads_path_remoto}")
        logger.info(f"📁 Ruta inscritos: {self.uploads_inscritos_remoto}")
        logger.info(f"📁 Base de datos principal: {self.db_path_remoto}")
        
        if self.auto_connect and self.config.get('host'):
            self.probar_conexion_inicial()
    
    def _cargar_configuracion_completa(self):
        """Cargar configuración UNIFICADA desde secrets.toml"""
        config = {}
        
        try:
            # Configuración SSH
            ssh_config = {}
            
            # Buscar configuración SSH en diferentes secciones
            if 'ssh' in self.config_completa:
                ssh_config = self.config_completa['ssh']
            elif all(k in self.config_completa for k in ['remote_host', 'remote_user', 'remote_password']):
                # Usar configuración antigua si existe
                ssh_config = {
                    'host': self.config_completa.get('remote_host'),
                    'port': self.config_completa.get('remote_port', 22),
                    'username': self.config_completa.get('remote_user'),
                    'password': self.config_completa.get('remote_password'),
                    'timeout': 30,
                    'remote_dir': self.config_completa.get('paths', {}).get('base_path', ''),
                    'enabled': True
                }
            
            config.update({
                'host': ssh_config.get('host', ''),
                'port': int(ssh_config.get('port', 22)),
                'username': ssh_config.get('username', ''),
                'password': ssh_config.get('password', ''),
                'timeout': int(ssh_config.get('timeout', 30)),
                'remote_dir': ssh_config.get('remote_dir', ''),
                'enabled': bool(ssh_config.get('enabled', True))
            })
            
            # Configuración de rutas - BUSCAR EN DIFERENTES SECCIONES
            paths_config = self.config_completa.get('paths', {})
            
            config.update({
                'db_principal': paths_config.get('db_principal', ''),
                'uploads_path': paths_config.get('uploads_path', ''),
                'uploads_inscritos': paths_config.get('uploads_inscritos', ''),
                'uploads_estudiantes': paths_config.get('uploads_estudiantes', ''),
                'uploads_egresados': paths_config.get('uploads_egresados', ''),
                'uploads_contratados': paths_config.get('uploads_contratados', ''),
                'uploads_aspirantes': paths_config.get('uploads_aspirantes', ''),
                'uploads_documentos': paths_config.get('uploads_documentos', ''),
                'backup_path': paths_config.get('backup_path', ''),
                'export_path': paths_config.get('export_path', ''),
                'logs_path': paths_config.get('logs_path', ''),
                'base_path': paths_config.get('base_path', '')
            })
            
            # Configuración SMTP
            smtp_config = {
                'smtp_server': self.config_completa.get('smtp_server', ''),
                'smtp_port': int(self.config_completa.get('smtp_port', 587)),
                'email_user': self.config_completa.get('email_user', ''),
                'email_password': self.config_completa.get('email_password', ''),
                'notification_email': self.config_completa.get('notification_email', ''),
                'debug_mode': bool(self.config_completa.get('debug_mode', False))
            }
            config['smtp'] = smtp_config
            
            logger.info("✅ Configuración UNIFICADA cargada desde secrets.toml")
            
        except Exception as e:
            logger.error(f"❌ Error cargando configuración: {e}", exc_info=True)
        
        return config
    
    def _limpiar_archivos_temporales(self):
        logger.debug("Limpiando archivos temporales...")
        
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.debug(f"🗑️ Archivo temporal eliminado: {temp_file}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar {temp_file}: {e}")
        
        temp_dir = tempfile.gettempdir()
        pattern = os.path.join(temp_dir, "aspirantes_*.db")
        for old_file in glob.glob(pattern):
            try:
                if os.path.getmtime(old_file) < time.time() - 3600:
                    os.remove(old_file)
                    logger.debug(f"🗑️ Archivo temporal antiguo eliminado: {old_file}")
            except:
                pass
    
    def _intento_conexion_con_backoff(self, attempt):
        wait_time = min(self.retry_delay_base * (2 ** attempt), 60)
        jitter = wait_time * 0.1 * np.random.random()
        return wait_time + jitter
    
    def probar_conexion_inicial(self):
        try:
            if not self.config.get('host'):
                return False
                
            logger.info(f"🔍 Probando conexión SSH a {self.config['host']}...")
            
            if not UtilidadesSistema.verificar_conectividad_red():
                logger.warning("⚠️ No hay conectividad de red")
                return False
            
            ssh_test = paramiko.SSHClient()
            ssh_test.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            port = self.config.get('port', 22)
            timeout = self.timeouts['ssh_connect']
            
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
            
            # Verificar estructura de directorios remotos
            if self.uploads_path_remoto:
                stdin, stdout, stderr = ssh_test.exec_command(f'ls -la "{self.uploads_path_remoto}"', timeout=self.timeouts['ssh_command'])
                output = stdout.read().decode().strip()
                error = stderr.read().decode().strip()
                
                if error and "No such file" in error:
                    logger.warning(f"⚠️ Directorio remoto no encontrado: {self.uploads_path_remoto}")
                else:
                    logger.info(f"✅ Directorio remoto accesible: {self.uploads_path_remoto}")
            
            ssh_test.close()
            
            logger.info(f"✅ Conexión SSH exitosa a {self.config['host']}")
            estado_sistema.set_ssh_conectado(True, None)
            return True
            
        except socket.timeout:
            error_msg = f"Timeout conectando a {self.config['host']}"
            logger.error(f"❌ {error_msg}")
            estado_sistema.set_ssh_conectado(False, error_msg)
            return False
        except paramiko.AuthenticationException:
            error_msg = "Error de autenticación SSH - Credenciales incorrectas"
            logger.error(f"❌ {error_msg}")
            estado_sistema.set_ssh_conectado(False, error_msg)
            return False
        except Exception as e:
            error_msg = f"Error de conexión SSH: {str(e)}"
            logger.error(f"❌ {error_msg}")
            estado_sistema.set_ssh_conectado(False, error_msg)
            return False
    
    def conectar_ssh(self):
        try:
            if not self.config.get('host'):
                logger.error("No hay configuración SSH disponible")
                return False
                
            logger.info(f"🔗 Conectando SSH a {self.config['host']}:{self.config.get('port', 22)}...")
            
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            port = self.config.get('port', 22)
            timeout = self.timeouts['ssh_connect']
            
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
            self.sftp.get_channel().settimeout(self.timeouts['sftp_transfer'])
            
            logger.info(f"✅ Conexión SSH establecida a {self.config['host']}")
            estado_sistema.set_ssh_conectado(True, None)
            return True
            
        except socket.timeout:
            error_msg = f"Timeout conectando a {self.config['host']}"
            logger.error(f"❌ {error_msg}")
            estado_sistema.set_ssh_conectado(False, error_msg)
            return False
        except paramiko.AuthenticationException:
            error_msg = "Error de autenticación SSH - Credenciales incorrectas"
            logger.error(f"❌ {error_msg}")
            estado_sistema.set_ssh_conectado(False, error_msg)
            return False
        except Exception as e:
            error_msg = f"Error de conexión: {str(e)}"
            logger.error(f"❌ {error_msg}")
            estado_sistema.set_ssh_conectado(False, error_msg)
            return False
    
    def desconectar_ssh(self):
        try:
            if self.sftp:
                self.sftp.close()
            if self.ssh:
                self.ssh.close()
            logger.debug("🔌 Conexión SSH cerrada")
        except Exception as e:
            logger.warning(f"⚠️ Error cerrando conexión SSH: {e}")
    
    def _crear_directorio_remoto_recursivo(self, remote_path):
        """Crear directorio remoto recursivamente"""
        try:
            self.sftp.stat(remote_path)
            logger.info(f"📁 Directorio remoto ya existe: {remote_path}")
            return True
        except FileNotFoundError:
            try:
                parent_dir = os.path.dirname(remote_path)
                if parent_dir and parent_dir != '/':
                    self._crear_directorio_remoto_recursivo(parent_dir)
                self.sftp.mkdir(remote_path)
                logger.info(f"✅ Directorio remoto creado: {remote_path}")
                return True
            except Exception as e:
                logger.error(f"❌ Error creando directorio remoto {remote_path}: {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Error verificando directorio remoto {remote_path}: {e}")
            return False
    
    def crear_estructura_directorios_remota(self):
        """Crear estructura completa de directorios en el servidor remoto - VERSIÓN UNIFICADA"""
        try:
            if not self.conectar_ssh():
                return False
            
            # Directorios a crear según secrets.toml
            directorios = [
                self.uploads_path_remoto,
                self.uploads_inscritos_remoto,
                self.uploads_estudiantes_remoto,
                self.uploads_egresados_remoto,
                self.uploads_contratados_remoto,
                self.uploads_aspirantes_remoto,
                self.uploads_documentos_remoto,
                self.config.get('backup_path', ''),
                self.config.get('export_path', ''),
                self.config.get('logs_path', '')
            ]
            
            for directorio in directorios:
                if directorio:
                    self._crear_directorio_remoto_recursivo(directorio)
            
            # Crear directorio para la base de datos si no existe
            if self.db_path_remoto:
                db_dir = os.path.dirname(self.db_path_remoto)
                if db_dir:
                    self._crear_directorio_remoto_recursivo(db_dir)
            
            logger.info("✅ Estructura de directorios remota UNIFICADA creada/verificada")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creando estructura de directorios remota: {e}")
            return False
        finally:
            if self.ssh:
                self.desconectar_ssh()
    
    def subir_archivo_remoto(self, archivo_local, ruta_remota):
        """Subir un archivo directamente al servidor remoto"""
        try:
            if not self.conectar_ssh():
                return False
            
            # Crear directorio remoto si no existe
            remote_dir = os.path.dirname(ruta_remota)
            self._crear_directorio_remoto_recursivo(remote_dir)
            
            # Subir archivo
            self.sftp.put(archivo_local, ruta_remota)
            logger.info(f"✅ Archivo subido a remoto: {ruta_remota}")
            estado_sistema.registrar_archivo_subido_remoto()
            return True
            
        except Exception as e:
            logger.error(f"❌ Error subiendo archivo a remoto: {e}")
            return False
        finally:
            if self.ssh:
                self.desconectar_ssh()
    
    def subir_buffer_remoto(self, buffer_archivo, nombre_archivo, ruta_remota):
        """Subir un archivo desde buffer (Streamlit uploaded file) al servidor remoto"""
        try:
            if not self.conectar_ssh():
                return False
            
            # Crear directorio remoto si no existe
            remote_dir = os.path.dirname(ruta_remota)
            self._crear_directorio_remoto_recursivo(remote_dir)
            
            # Guardar temporalmente el archivo
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, nombre_archivo)
            
            with open(temp_path, 'wb') as f:
                f.write(buffer_archivo)
            
            # Subir archivo
            self.sftp.put(temp_path, ruta_remota)
            
            # Eliminar temporal
            os.remove(temp_path)
            
            logger.info(f"✅ Buffer subido a remoto: {ruta_remota}")
            estado_sistema.registrar_archivo_subido_remoto()
            return True
            
        except Exception as e:
            logger.error(f"❌ Error subiendo buffer a remoto: {e}")
            return False
        finally:
            if self.ssh:
                self.desconectar_ssh()
    
    def descargar_db_remota(self):
        inicio_tiempo = time.time()
        
        for attempt in range(self.retry_attempts):
            try:
                logger.info(f"📥 Intento {attempt + 1}/{self.retry_attempts} descargando DB remota...")
                
                if not self.conectar_ssh():
                    logger.error(f"❌ Falló conexión SSH en intento {attempt + 1}")
                    if attempt < self.retry_attempts - 1:
                        wait_time = self._intento_conexion_con_backoff(attempt)
                        logger.info(f"⏳ Esperando {wait_time:.1f} segundos antes de reintentar...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise Exception("No se pudo conectar SSH después de múltiples intentos")
                
                temp_dir = tempfile.gettempdir()
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                temp_db_path = os.path.join(temp_dir, f"aspirantes_temp_{timestamp}.db")
                self.temp_files.append(temp_db_path)
                
                espacio_ok, espacio_mb = UtilidadesSistema.verificar_espacio_disco(temp_dir, espacio_minimo_mb=200)
                if not espacio_ok:
                    raise Exception(f"Espacio en disco insuficiente: {espacio_mb:.1f} MB disponibles")
                
                if not self.db_path_remoto:
                    raise Exception("No se configuró la ruta de la base de datos remota")
                
                logger.info(f"📥 Descargando base de datos desde: {self.db_path_remoto}")
                
                start_time = time.time()
                self.sftp.get(self.db_path_remoto, temp_db_path)
                download_time = time.time() - start_time
                
                if os.path.exists(temp_db_path) and os.path.getsize(temp_db_path) > 0:
                    file_size = os.path.getsize(temp_db_path)
                    logger.info(f"✅ Base de datos descargada: {temp_db_path} ({file_size} bytes en {download_time:.1f}s)")
                    
                    if self._verificar_integridad_db(temp_db_path):
                        tiempo_total = time.time() - inicio_tiempo
                        logger.info(f"⏱️ Descarga completada en {tiempo_total:.1f} segundos")
                        return temp_db_path
                    else:
                        logger.error("❌ Base de datos corrupta después de descarga")
                        os.remove(temp_db_path)
                        raise Exception("Base de datos corrupta")
                else:
                    logger.warning("⚠️ Archivo descargado vacío o corrupto")
                    return self._crear_nueva_db_remota()
                    
            except socket.timeout:
                logger.error(f"❌ Timeout en intento {attempt + 1}")
                if attempt < self.retry_attempts - 1:
                    wait_time = self._intento_conexion_con_backoff(attempt)
                    logger.info(f"⏳ Esperando {wait_time:.1f} segundos antes de reintentar...")
                    time.sleep(wait_time)
                    continue
                else:
                    return self._crear_nueva_db_remota()
                    
            except Exception as e:
                logger.error(f"❌ Error en intento {attempt + 1}: {e}", exc_info=True)
                if attempt < self.retry_attempts - 1:
                    wait_time = self._intento_conexion_con_backoff(attempt)
                    logger.info(f"⏳ Esperando {wait_time:.1f} segundos antes de reintentar...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error("❌ Todos los intentos fallaron")
                    raise Exception(f"No se pudo descargar la base de datos después de {self.retry_attempts} intentos")
            finally:
                if self.ssh:
                    self.desconectar_ssh()
        
        return None
    
    def _verificar_integridad_db(self, db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()[0]
            logger.debug(f"SQLite version: {version}")
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tablas = cursor.fetchall()
            
            if len(tablas) == 0:
                logger.info("⚠️ Base de datos vacía, se inicializará estructura")
                return True
            
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error verificando integridad DB: {e}")
            return False
    
    def _crear_nueva_db_remota(self):
        try:
            logger.info("📝 Creando nueva base de datos remota...")
            
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_db_path = os.path.join(temp_dir, f"aspirantes_nueva_{timestamp}.db")
            self.temp_files.append(temp_db_path)
            
            logger.info(f"📝 Creando nueva base de datos en: {temp_db_path}")
            self._inicializar_db_estructura_completa(temp_db_path)
            
            if self.conectar_ssh():
                try:
                    if not self.db_path_remoto:
                        raise Exception("No se configuró la ruta de la base de datos remota")
                    
                    remote_dir = os.path.dirname(self.db_path_remoto)
                    self._crear_directorio_remoto_recursivo(remote_dir)
                    
                    start_time = time.time()
                    self.sftp.put(temp_db_path, self.db_path_remoto)
                    upload_time = time.time() - start_time
                    
                    logger.info(f"✅ Nueva base de datos subida a servidor: {self.db_path_remoto} ({upload_time:.1f}s)")
                finally:
                    self.desconectar_ssh()
            
            return temp_db_path
            
        except Exception as e:
            logger.error(f"❌ Error creando nueva base de datos remota: {e}", exc_info=True)
            raise
    
    def _inicializar_db_estructura_completa(self, db_path):
        try:
            logger.info(f"📝 Inicializando estructura COMPLETA en: {db_path}")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    rol TEXT DEFAULT 'inscrito',
                    nombre_completo TEXT,
                    email TEXT,
                    matricula TEXT UNIQUE,
                    activo INTEGER DEFAULT 1,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    categoria_academica TEXT,
                    tipo_programa TEXT,
                    acepto_privacidad INTEGER DEFAULT 0,
                    acepto_convocatoria INTEGER DEFAULT 0
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS inscritos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    folio_unico TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT NOT NULL,
                    email_gmail TEXT,
                    telefono TEXT,
                    tipo_programa TEXT NOT NULL,
                    categoria_academica TEXT,
                    programa_interes TEXT NOT NULL,
                    estado_civil TEXT,
                    edad INTEGER,
                    domicilio TEXT,
                    licenciatura_origen TEXT,
                    documentos_subidos INTEGER DEFAULT 0,
                    documentos_guardados TEXT,
                    documentos_faltantes TEXT,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_limite_registro DATE,
                    estatus TEXT DEFAULT 'Pre-inscrito',
                    estudio_socioeconomico TEXT,
                    acepto_privacidad INTEGER DEFAULT 0,
                    acepto_convocatoria INTEGER DEFAULT 0,
                    fecha_aceptacion_privacidad TIMESTAMP,
                    fecha_aceptacion_convocatoria TIMESTAMP,
                    duplicado_verificado INTEGER DEFAULT 0,
                    matricula_unam TEXT,
                    recordatorio_enviado INTEGER DEFAULT 0,
                    ultimo_recordatorio TIMESTAMP,
                    completado INTEGER DEFAULT 0,
                    observaciones TEXT,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usuario_actualizacion TEXT DEFAULT 'sistema'
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS documentos_programa (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo_programa TEXT NOT NULL,
                    nombre_documento TEXT NOT NULL,
                    obligatorio INTEGER DEFAULT 1,
                    descripcion TEXT,
                    orden INTEGER DEFAULT 0
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS estudios_socioeconomicos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inscrito_id INTEGER NOT NULL,
                    ingreso_familiar REAL,
                    personas_dependientes INTEGER,
                    vivienda_propia INTEGER,
                    transporte_propio INTEGER,
                    seguro_medico TEXT,
                    discapacidad INTEGER,
                    beca_solicitada INTEGER,
                    trabajo_estudiantil INTEGER,
                    detalles TEXT,
                    FOREIGN KEY (inscrito_id) REFERENCES inscritos (id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS documentos_subidos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inscrito_id INTEGER NOT NULL,
                    nombre_documento TEXT NOT NULL,
                    nombre_archivo TEXT NOT NULL,
                    ruta_archivo TEXT NOT NULL,
                    fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tamano_bytes INTEGER,
                    tipo_archivo TEXT,
                    verificado INTEGER DEFAULT 0,
                    observaciones TEXT,
                    FOREIGN KEY (inscrito_id) REFERENCES inscritos (id)
                )
            ''')
            
            documentos_licenciatura = [
                ("LICENCIATURA", "Certificado preparatoria (promedio ≥ 8.0)", 1, "Certificado de bachillerato original", 1),
                ("LICENCIATURA", "Acta nacimiento (≤ 3 meses)", 1, "Acta de nacimiento actualizada", 2),
                ("LICENCIATURA", "CURP (≤ 1 mes)", 1, "Clave Única de Registro de Población", 3),
                ("LICENCIATURA", "Cartilla Nacional de Salud", 1, "Cartilla de vacunación", 4),
                ("LICENCIATURA", "INE del tutor", 1, "Identificación oficial del tutor", 5),
                ("LICENCIATURA", "Comprobante domicilio (≤ 3 meses)", 1, "Comprobante de domicilio actual", 6),
                ("LICENCIATURA", "Certificado médico institucional (≤ 1 mes)", 1, "Certificado médico oficial", 7),
                ("LICENCIATURA", "12 fotografías infantiles B/N", 1, "12 fotografías tamaño infantil", 8),
                ("LICENCIATURA", "Comprobante domicilio (adicional)", 1, "Comprobante de domicilio específico", 9),
                ("LICENCIATURA", "Carta de exposición de motivos", 0, "Carta explicando motivos para estudiar", 10)
            ]
            
            documentos_especialidad = [
                ("ESPECIALIDAD", "Certificado preparatoria (promedio ≥ 8.0)", 1, "Certificado de bachillerato original", 1),
                ("ESPECIALIDAD", "Acta nacimiento (≤ 3 meses)", 1, "Acta de nacimiento actualizada", 2),
                ("ESPECIALIDAD", "CURP (≤ 1 mes)", 1, "Clave Única de Registro de Población", 3),
                ("ESPECIALIDAD", "Cartilla Nacional de Salud", 1, "Cartilla de vacunación", 4),
                ("ESPECIALIDAD", "INE del tutor", 1, "Identificación oficial del tutor", 5),
                ("ESPECIALIDAD", "Comprobante domicilio (≤ 3 meses)", 1, "Comprobante de domicilio actual", 6),
                ("ESPECIALIDAD", "Certificado médico institucional (≤ 1 mes)", 1, "Certificado médico oficial", 7),
                ("ESPECIALIDAD", "12 fotografías infantiles B/N", 1, "12 fotografías tamaño infantil", 8),
                ("ESPECIALIDAD", "Título profesional", 1, "Título de licenciatura", 9),
                ("ESPECIALIDAD", "Certificado de licenciatura", 1, "Certificado de estudios de licenciatura", 10),
                ("ESPECIALIDAD", "Cédula profesional", 1, "Cédula profesional vigente", 11),
                ("ESPECIALIDAD", "INE (vigente)", 1, "Identificación oficial vigente", 12),
                ("ESPECIALIDAD", "Comprobante de Servicio Social", 1, "Constancia de servicio social", 13),
                ("ESPECIALIDAD", "Autorización de titulación", 1, "Autorización de titulación de licenciatura", 14),
                ("ESPECIALIDAD", "Constancia de experiencia laboral (2+ años)", 1, "Constancia de experiencia mínima 2 años", 15),
                ("ESPECIALIDAD", "Constancia de cómputo", 1, "Constancia de conocimientos en computación", 16),
                ("ESPECIALIDAD", "Constancia de comprensión de textos", 1, "Constancia de comprensión lectora", 17)
            ]
            
            for doc in documentos_licenciatura + documentos_especialidad:
                cursor.execute('''
                    INSERT OR IGNORE INTO documentos_programa 
                    (tipo_programa, nombre_documento, obligatorio, descripcion, orden)
                    VALUES (?, ?, ?, ?, ?)
                ''', doc)
            
            try:
                # Insertar admin con password seguro (hash) - CORREGIDO
                password_hash = hashlib.sha256("Admin123!".encode()).hexdigest()
                cursor.execute(
                    "INSERT OR IGNORE INTO usuarios (usuario, password, rol, nombre_completo, email, matricula, activo) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ('admin', password_hash, 'admin', 'Administrador', 'admin@enfermeria.edu', 'ADMIN-001', 1)
                )
                logger.info("✅ Usuario admin creado con password hasheado: Admin123!")
            except Exception as e:
                logger.warning(f"⚠️ Error insertando admin: {e}")
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Estructura de base de datos COMPLETA inicializada en {db_path}")
            
            estado_sistema.marcar_db_inicializada()
            
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura completa: {e}", exc_info=True)
            raise
    
    def subir_db_remota(self, ruta_local):
        try:
            logger.info(f"📤 Subiendo base de datos al servidor remoto...")
            
            if not self.conectar_ssh():
                return False
            
            if not self.db_path_remoto:
                logger.error("No se configuró la ruta de la base de datos remota")
                return False
            
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = f"{self.db_path_remoto}.backup_{timestamp}"
                self.sftp.rename(self.db_path_remoto, backup_path)
                logger.info(f"✅ Backup creado en servidor: {backup_path}")
                estado_sistema.registrar_backup()
            except Exception as e:
                logger.warning(f"⚠️ No se pudo crear backup en servidor: {e}")
            
            start_time = time.time()
            self.sftp.put(ruta_local, self.db_path_remoto)
            upload_time = time.time() - start_time
            
            logger.info(f"✅ Base de datos subida a servidor: {self.db_path_remoto} ({upload_time:.1f}s)")
            
            return True
            
        except socket.timeout:
            logger.error("❌ Timeout subiendo base de datos")
            return False
        except Exception as e:
            logger.error(f"❌ Error subiendo base de datos: {e}", exc_info=True)
            return False
        finally:
            if self.ssh:
                self.desconectar_ssh()
    
    def verificar_conexion_ssh(self):
        return self.probar_conexion_inicial()

gestor_remoto = GestorConexionRemota()

# ============================================================================
# CAPA 6: SISTEMA DE GESTIÓN DE ARCHIVOS REMOTOS
# ============================================================================

class SistemaGestionArchivosRemotos:
    """Sistema para gestionar la subida y almacenamiento de documentos directamente en el servidor remoto"""
    
    def __init__(self):
        self.gestor = gestor_remoto
        self.crear_estructura_directorios()
    
    def crear_estructura_directorios(self):
        """Crear estructura de directorios en el servidor remoto"""
        try:
            if not self.gestor.crear_estructura_directorios_remota():
                logger.warning("⚠️ No se pudo crear/verificar estructura de directorios remota")
        except Exception as e:
            logger.error(f"❌ Error creando estructura de directorios: {e}")
    
    def subir_documento_remoto(self, archivo, nombre_documento, matricula):
        """Subir documento directamente al servidor remoto"""
        try:
            if archivo is None:
                return None
            
            # Generar nombre seguro para el archivo
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            nombre_original = archivo.name
            extension = nombre_original.split('.')[-1] if '.' in nombre_original else 'pdf'
            
            # Nombre seguro
            nombre_doc_simple = re.sub(r'[^\w\s-]', '', nombre_documento)
            nombre_doc_simple = re.sub(r'[-\s]+', '_', nombre_doc_simple)
            
            nombre_seguro = f"{nombre_doc_simple}_{timestamp}.{extension}"
            
            # Construir ruta remota usando la configuración UNIFICADA
            ruta_remota = os.path.join(
                self.gestor.uploads_inscritos_remoto,
                matricula,
                nombre_seguro
            )
            
            # Subir archivo directamente al servidor remoto
            if self.gestor.subir_buffer_remoto(archivo.getbuffer(), nombre_seguro, ruta_remota):
                tamano_bytes = len(archivo.getbuffer())
                
                logger.info(f"✅ Documento subido a remoto: {matricula}/{nombre_seguro} ({tamano_bytes} bytes)")
                
                return {
                    'nombre_documento': nombre_documento,
                    'nombre_archivo': nombre_seguro,
                    'ruta_archivo': ruta_remota,  # Ruta remota
                    'tamano_bytes': tamano_bytes,
                    'tipo_archivo': extension,
                    'matricula': matricula
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error subiendo documento remoto: {e}")
            return None
    
    def obtener_ruta_archivo_remoto(self, nombre_archivo, matricula):
        """Obtener ruta remota completa de un archivo"""
        return os.path.join(
            self.gestor.uploads_inscritos_remoto,
            matricula,
            nombre_archivo
        )
    
    def listar_documentos_remotos(self, matricula):
        """Listar documentos de un usuario en el servidor remoto"""
        try:
            if not self.gestor.conectar_ssh():
                return []
            
            ruta_carpeta = os.path.join(self.gestor.uploads_inscritos_remoto, matricula)
            
            try:
                archivos = self.gestor.sftp.listdir(ruta_carpeta)
                
                documentos = []
                for archivo in archivos:
                    ruta_completa = os.path.join(ruta_carpeta, archivo)
                    stat = self.gestor.sftp.stat(ruta_completa)
                    
                    documentos.append({
                        'nombre': archivo,
                        'ruta': ruta_completa,
                        'tamaño': stat.st_size,
                        'fecha': datetime.fromtimestamp(stat.st_mtime)
                    })
                
                return documentos
                
            except FileNotFoundError:
                logger.info(f"📁 Carpeta remota no encontrada: {ruta_carpeta}")
                return []
            finally:
                self.gestor.desconectar_ssh()
                
        except Exception as e:
            logger.error(f"❌ Error listando documentos remotos: {e}")
            return []
    
    def eliminar_documentos_usuario_remoto(self, matricula):
        """Eliminar todos los documentos de un usuario en el servidor remoto"""
        try:
            if not self.gestor.conectar_ssh():
                return False
            
            ruta_carpeta = os.path.join(self.gestor.uploads_inscritos_remoto, matricula)
            
            try:
                # Listar archivos
                archivos = self.gestor.sftp.listdir(ruta_carpeta)
                
                # Eliminar cada archivo
                for archivo in archivos:
                    ruta_archivo = os.path.join(ruta_carpeta, archivo)
                    self.gestor.sftp.remove(ruta_archivo)
                
                # Eliminar carpeta
                self.gestor.sftp.rmdir(ruta_carpeta)
                
                logger.info(f"✅ Carpeta remota eliminada: {matricula}")
                return True
                
            except FileNotFoundError:
                logger.info(f"📁 Carpeta remota no encontrada: {ruta_carpeta}")
                return False
            except Exception as e:
                logger.error(f"❌ Error eliminando documentos remotos: {e}")
                return False
            finally:
                self.gestor.desconectar_ssh()
                
        except Exception as e:
            logger.error(f"❌ Error conectando para eliminar documentos: {e}")
            return False

# ============================================================================
# CAPA 7: SISTEMA DE BASE DE DATOS COMPLETO (CON LOGIN CORREGIDO)
# ============================================================================

class SistemaBaseDatosCompleto:
    """Sistema de base de datos SQLite COMPLETO que trabaja directamente en el servidor remoto"""
    
    def __init__(self):
        self.gestor = gestor_remoto
        self.gestor_archivos = SistemaGestionArchivosRemotos()
        self.db_local_temp = None
        self.conexion_actual = None
        self.ultima_sincronizacion = None
        self.validador = ValidadorDatos()
    
    def _intento_conexion_con_backoff(self, attempt):
        return self.gestor._intento_conexion_con_backoff(attempt)
    
    def sincronizar_desde_remoto(self):
        inicio_tiempo = time.time()
        
        for attempt in range(self.gestor.retry_attempts):
            try:
                logger.info(f"🔄 Intento {attempt + 1}/{self.gestor.retry_attempts} sincronizando desde remoto...")
                
                self.db_local_temp = self.gestor.descargar_db_remota()
                
                if not self.db_local_temp:
                    raise Exception("No se pudo obtener base de datos remota")
                
                if not os.path.exists(self.db_local_temp):
                    raise Exception(f"Archivo de base de datos no existe: {self.db_local_temp}")
                
                try:
                    conn = sqlite3.connect(self.db_local_temp)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tablas = cursor.fetchall()
                    conn.close()
                    
                    logger.info(f"✅ Base de datos verificada: {len(tablas)} tablas")
                    
                    if len(tablas) == 0:
                        logger.warning("⚠️ Base de datos vacía, inicializando estructura completa...")
                        self._inicializar_estructura_db_completa()
                except Exception as e:
                    logger.error(f"❌ Base de datos corrupta: {e}")
                    raise Exception(f"Base de datos corrupta: {e}")
                
                self.ultima_sincronizacion = datetime.now()
                tiempo_total = time.time() - inicio_tiempo
                
                logger.info(f"✅ Sincronización exitosa en {tiempo_total:.1f}s: {self.db_local_temp}")
                estado_sistema.marcar_sincronizacion()
                
                return True
                
            except Exception as e:
                logger.error(f"❌ Error en intento {attempt + 1}: {e}", exc_info=True)
                if attempt < self.gestor.retry_attempts - 1:
                    wait_time = self._intento_conexion_con_backoff(attempt)
                    logger.info(f"⏳ Esperando {wait_time:.1f} segundos antes de reintentar...")
                    time.sleep(wait_time)
                    continue
                else:
                    tiempo_total = time.time() - inicio_tiempo
                    logger.error(f"❌ Sincronización fallida después de {tiempo_total:.1f}s")
                    return False
    
    def _inicializar_estructura_db_completa(self):
        try:
            if not self.db_local_temp:
                logger.error("❌ No hay ruta de base de datos para inicializar")
                return
            
            self.gestor._inicializar_db_estructura_completa(self.db_local_temp)
            
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura: {e}", exc_info=True)
            raise
    
    def sincronizar_hacia_remoto(self):
        inicio_tiempo = time.time()
        
        for attempt in range(self.gestor.retry_attempts):
            try:
                logger.info(f"📤 Intento {attempt + 1}/{self.gestor.retry_attempts} sincronizando hacia remoto...")
                
                if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                    raise Exception("No hay base de datos local para subir")
                
                exito = self.gestor.subir_db_remota(self.db_local_temp)
                
                if exito:
                    self.ultima_sincronizacion = datetime.now()
                    tiempo_total = time.time() - inicio_tiempo
                    
                    logger.info(f"✅ Cambios subidos exitosamente al servidor en {tiempo_total:.1f}s")
                    estado_sistema.marcar_sincronizacion()
                    
                    return True
                else:
                    raise Exception("Error subiendo al servidor")
                    
            except Exception as e:
                logger.error(f"❌ Error en intento {attempt + 1}: {e}", exc_info=True)
                if attempt < self.gestor.retry_attempts - 1:
                    wait_time = self._intento_conexion_con_backoff(attempt)
                    logger.info(f"⏳ Esperando {wait_time:.1f} segundos antes de reintentar...")
                    time.sleep(wait_time)
                    continue
                else:
                    tiempo_total = time.time() - inicio_tiempo
                    logger.error(f"❌ Sincronización fallida después de {tiempo_total:.1f}s")
                    return False
    
    @contextmanager
    def get_connection(self):
        conn = None
        try:
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
            logger.error(f"❌ Error en conexión a base de datos: {e}", exc_info=True)
            raise
        finally:
            if conn:
                conn.close()
                self.conexion_actual = None
    
    def ejecutar_query(self, query, params=()):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                
                if query.strip().upper().startswith('SELECT'):
                    resultados = cursor.fetchall()
                    resultados = [dict(row) for row in resultados]
                    return resultados
                else:
                    ultimo_id = cursor.lastrowid
                    return ultimo_id
                    
        except Exception as e:
            logger.error(f"❌ Error ejecutando query: {e} - Query: {query}")
            return None
    
    def verificar_usuario(self, usuario, password):
        """VERIFICACIÓN DE USUARIO CORREGIDA - Maneja passwords hasheadas y texto plano"""
        try:
            query = "SELECT * FROM usuarios WHERE usuario = ?"
            resultados = self.ejecutar_query(query, (usuario,))
            
            if not resultados:
                logger.warning(f"Usuario no encontrado: {usuario}")
                return None
            
            usuario_data = resultados[0]
            stored_password = usuario_data['password']
            
            # PRIMERO: Intentar con hash (la forma segura)
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            if stored_password == password_hash:
                logger.info(f"✅ Login exitoso (hash) para: {usuario}")
                return usuario_data
            
            # SEGUNDO: Si no funciona con hash, probar texto plano (para compatibilidad)
            if stored_password == password:
                logger.info(f"✅ Login exitoso (texto) para: {usuario}")
                # Si la contraseña estaba en texto, la actualizamos a hash
                self._actualizar_password_a_hash(usuario, password_hash)
                return usuario_data
            
            # Si llegamos aquí, la contraseña no coincide
            logger.warning(f"Contraseña incorrecta para usuario: {usuario}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error verificando usuario: {e}", exc_info=True)
            return None
    
    def _actualizar_password_a_hash(self, usuario, password_hash):
        """Actualizar contraseña en texto plano a hash para mayor seguridad"""
        try:
            query = "UPDATE usuarios SET password = ? WHERE usuario = ?"
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (password_hash, usuario))
                conn.commit()
            logger.info(f"✅ Contraseña actualizada a hash para usuario: {usuario}")
            return True
        except Exception as e:
            logger.error(f"❌ Error actualizando password a hash: {e}")
            return False
    
    def agregar_inscrito_completo(self, datos_inscrito):
        try:
            if datos_inscrito.get('email_gmail'):
                if not self.validador.validar_email_gmail(datos_inscrito['email_gmail']):
                    raise ValueError("❌ El correo debe ser de dominio @gmail.com")
            
            query_check = '''
                SELECT COUNT(*) as count FROM inscritos 
                WHERE email = ? OR email_gmail = ?
            '''
            resultado = self.ejecutar_query(query_check, (
                datos_inscrito['email'],
                datos_inscrito.get('email_gmail', '')
            ))
            
            if resultado and resultado[0]['count'] > 0:
                estado_sistema.registrar_duplicado_eliminado()
                raise ValueError("❌ Ya existe un registro con este correo electrónico")
            
            folio_unico = self.generar_folio_unico()
            fecha_limite = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
            
            query_inscrito = '''
                INSERT INTO inscritos (
                    matricula, folio_unico, nombre_completo, email, email_gmail, telefono,
                    tipo_programa, categoria_academica, programa_interes,
                    estado_civil, edad, domicilio, licenciatura_origen,
                    documentos_subidos, documentos_guardados, documentos_faltantes,
                    fecha_limite_registro,
                    estatus, estudio_socioeconomico,
                    acepto_privacidad, acepto_convocatoria,
                    fecha_aceptacion_privacidad, fecha_aceptacion_convocatoria,
                    duplicado_verificado, matricula_unam,
                    completado, observaciones
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
The document content is too long to display in full
