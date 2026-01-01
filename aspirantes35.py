#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SISTEMA DE GESTIÓN DE ASPIRANTES - VERSIÓN 3.8 (TRABAJO REMOTO COMPLETO)
Sistema completo que trabaja directamente en el servidor remoto
VERSIÓN CORREGIDA: Solucionados problemas con st.rerun() y contador de documentos
VERSIÓN 3.9.2: CONTADOR DE DOCUMENTOS CORREGIDO - SOLUCIÓN COMPLETA
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
    'version': '3.9.2',  # Versión actualizada - CONTADOR DE DOCUMENTOS CORREGIDO
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
    """Cargar configuración desde secrets.toml"""
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
    """Gestor de conexión SSH al servidor remoto con gestión completa de archivos"""
    
    def __init__(self):
        self.ssh = None
        self.sftp = None
        self.temp_files = []
        
        self.auto_connect = True
        self.retry_attempts = TIME_CONFIG['retry_attempts']
        self.retry_delay_base = TIME_CONFIG['retry_delay_base']
        self.timeouts = {
            'ssh_connect': TIME_CONFIG['ssh_connect_timeout'],
            'ssh_command': TIME_CONFIG['ssh_command_timeout'],
            'sftp_transfer': TIME_CONFIG['sftp_transfer_timeout'],
            'db_download': TIME_CONFIG['db_download_timeout']
        }
        
        atexit.register(self._limpiar_archivos_temporales)
        
        logger.info("📋 Cargando configuración desde secrets.toml...")
        self.config_completa = cargar_configuracion_secrets()
        
        if not self.config_completa:
            logger.error("❌ No se pudo cargar configuración de secrets.toml")
            self.config = {}
            return
            
        self.config = self._cargar_configuracion_completa()
        
        if 'system' in self.config_completa:
            sys_config = self.config_completa['system']
            self.auto_connect = sys_config.get('auto_connect', True)
            self.retry_attempts = sys_config.get('retry_attempts', 3)
            self.retry_delay_base = sys_config.get('retry_delay', 5)
        
        if not self.config.get('host'):
            logger.warning("⚠️ No hay configuración SSH en secrets.toml")
            return
        
        self.db_path_remoto = self.config.get('remote_db_aspirantes')
        self.uploads_path_remoto = self.config.get('remote_uploads_path')
        self.uploads_inscritos_remoto = self.config.get('remote_uploads_inscritos')
        
        logger.info(f"🔗 Configuración SSH cargada para {self.config.get('host', 'No configurado')}")
        logger.info(f"📁 Ruta remota uploads: {self.uploads_path_remoto}")
        logger.info(f"📁 Ruta remota inscritos: {self.uploads_inscritos_remoto}")
        
        if self.auto_connect and self.config.get('host'):
            self.probar_conexion_inicial()
    
    def _cargar_configuracion_completa(self):
        config = {}
        
        try:
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
            
            paths_config = self.config_completa.get('paths', {})
            config.update({
                'remote_db_aspirantes': paths_config.get('remote_db_aspirantes', ''),
                'remote_uploads_path': paths_config.get('remote_uploads_path', ''),
                'remote_uploads_inscritos': paths_config.get('remote_uploads_inscritos', ''),
                'remote_uploads_estudiantes': paths_config.get('remote_uploads_estudiantes', ''),
                'remote_uploads_egresados': paths_config.get('remote_uploads_egresados', ''),
                'remote_uploads_contratados': paths_config.get('remote_uploads_contratados', ''),
                'db_local_path': paths_config.get('db_aspirantes', ''),
                'uploads_path_local': paths_config.get('uploads_path', '')
            })
            
            smtp_config = {
                'smtp_server': self.config_completa.get('smtp_server', ''),
                'smtp_port': int(self.config_completa.get('smtp_port', 587)),
                'email_user': self.config_completa.get('email_user', ''),
                'email_password': self.config_completa.get('email_password', ''),
                'notification_email': self.config_completa.get('notification_email', ''),
                'debug_mode': bool(self.config_completa.get('debug_mode', False))
            }
            config['smtp'] = smtp_config
            
            logger.info("✅ Configuración completa cargada")
            
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
            stdin, stdout, stderr = ssh_test.exec_command(f'ls -la "{self.uploads_path_remoto}"', timeout=self.timeouts['ssh_command'])
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()
            
            ssh_test.close()
            
            if error and "No such file" in error:
                logger.warning(f"⚠️ Directorio remoto no encontrado: {self.uploads_path_remoto}")
            else:
                logger.info(f"✅ Directorio remoto accesible: {self.uploads_path_remoto}")
            
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
        """Crear estructura completa de directorios en el servidor remoto"""
        try:
            if not self.conectar_ssh():
                return False
            
            # Directorios a crear
            directorios = [
                self.uploads_path_remoto,
                self.uploads_inscritos_remoto,
                os.path.join(self.uploads_path_remoto, 'estudiantes'),
                os.path.join(self.uploads_path_remoto, 'egresados'),
                os.path.join(self.uploads_path_remoto, 'contratados')
            ]
            
            for directorio in directorios:
                if directorio:
                    self._crear_directorio_remoto_recursivo(directorio)
            
            logger.info("✅ Estructura de directorios remota creada/verificada")
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
            
            # Construir ruta remota
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            
            params_inscrito = (
                datos_inscrito.get('matricula', ''),
                folio_unico,
                datos_inscrito.get('nombre_completo', ''),
                datos_inscrito.get('email', ''),
                datos_inscrito.get('email_gmail', ''),
                datos_inscrito.get('telefono', ''),
                datos_inscrito.get('tipo_programa', ''),
                datos_inscrito.get('categoria_academica', ''),
                datos_inscrito.get('programa_interes', ''),
                datos_inscrito.get('estado_civil', ''),
                datos_inscrito.get('edad', None),
                datos_inscrito.get('domicilio', ''),
                datos_inscrito.get('licenciatura_origen', ''),
                datos_inscrito.get('documentos_subidos', 0),
                datos_inscrito.get('documentos_guardados', ''),
                datos_inscrito.get('documentos_faltantes', ''),
                fecha_limite,
                'Pre-inscrito',
                datos_inscrito.get('estudio_socioeconomico', ''),
                1 if datos_inscrito.get('acepto_privacidad') else 0,
                1 if datos_inscrito.get('acepto_convocatoria') else 0,
                datetime.now().isoformat() if datos_inscrito.get('acepto_privacidad') else None,
                datetime.now().isoformat() if datos_inscrito.get('acepto_convocatoria') else None,
                1,
                datos_inscrito.get('matricula_unam', ''),
                0,
                datos_inscrito.get('observaciones', '')
            )
            
            inscrito_id = self.ejecutar_query(query_inscrito, params_inscrito)
            
            if datos_inscrito.get('estudio_socioeconomico_detallado'):
                self.guardar_estudio_socioeconomico(inscrito_id, datos_inscrito['estudio_socioeconomico_detallado'])
            
            # Subir archivos al servidor remoto y guardar en BD
            if datos_inscrito.get('archivos_subidos'):
                for archivo_info in datos_inscrito['archivos_subidos']:
                    self.guardar_documento_subido(
                        inscrito_id, 
                        archivo_info['nombre_documento'],
                        archivo_info['nombre_archivo'],
                        archivo_info['ruta_archivo'],  # Esta ya es la ruta remota
                        archivo_info['tamano_bytes'],
                        archivo_info['tipo_archivo']
                    )
            
            if inscrito_id:
                query_usuario = '''
                    INSERT INTO usuarios (
                        usuario, password, rol, nombre_completo, email, matricula, activo,
                        categoria_academica, tipo_programa, acepto_privacidad, acepto_convocatoria
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                '''
                
                # Contraseña por defecto para inscritos: su matrícula
                password_hash = hashlib.sha256(datos_inscrito.get('matricula', '').encode()).hexdigest()
                params_usuario = (
                    datos_inscrito.get('matricula', ''),
                    password_hash,
                    'inscrito',
                    datos_inscrito.get('nombre_completo', ''),
                    datos_inscrito.get('email', ''),
                    datos_inscrito.get('matricula', ''),
                    1,
                    datos_inscrito.get('categoria_academica', ''),
                    datos_inscrito.get('tipo_programa', ''),
                    1 if datos_inscrito.get('acepto_privacidad') else 0,
                    1 if datos_inscrito.get('acepto_convocatoria') else 0
                )
                
                self.ejecutar_query(query_usuario, params_usuario)
                logger.info(f"✅ Inscrito agregado: {datos_inscrito.get('matricula')} - Folio: {folio_unico}")
                
                return inscrito_id, folio_unico
            
            return None, None
            
        except Exception as e:
            logger.error(f"❌ Error agregando inscrito completo: {e}")
            raise
    
    def guardar_documento_subido(self, inscrito_id, nombre_documento, nombre_archivo, ruta_archivo, tamano_bytes, tipo_archivo):
        try:
            query = '''
                INSERT INTO documentos_subidos (
                    inscrito_id, nombre_documento, nombre_archivo, ruta_archivo,
                    tamano_bytes, tipo_archivo
                ) VALUES (?, ?, ?, ?, ?, ?)
            '''
            
            self.ejecutar_query(query, (
                inscrito_id,
                nombre_documento,
                nombre_archivo,
                ruta_archivo,
                tamano_bytes,
                tipo_archivo
            ))
            
            logger.info(f"✅ Documento subido registrado: {nombre_archivo} para inscrito {inscrito_id}")
            
        except Exception as e:
            logger.error(f"❌ Error guardando documento subido: {e}")
    
    def generar_folio_unico(self):
        fecha = datetime.now().strftime('%y%m%d')
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"FOL{fecha}{random_str}"
    
    def guardar_estudio_socioeconomico(self, inscrito_id, datos_estudio):
        try:
            query = '''
                INSERT INTO estudios_socioeconomicos (
                    inscrito_id, ingreso_familiar, personas_dependientes,
                    vivienda_propia, transporte_propio, seguro_medico,
                    discapacidad, beca_solicitada, trabajo_estudiantil, detalles
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            
            self.ejecutar_query(query, (
                inscrito_id,
                datos_estudio.get('ingreso_familiar'),
                datos_estudio.get('personas_dependientes'),
                1 if datos_estudio.get('vivienda_propia') else 0,
                1 if datos_estudio.get('transporte_propio') else 0,
                datos_estudio.get('seguro_medico'),
                1 if datos_estudio.get('discapacidad') else 0,
                1 if datos_estudio.get('beca_solicitada') else 0,
                1 if datos_estudio.get('trabajo_estudiantil') else 0,
                datos_estudio.get('detalles', '')
            ))
            
            logger.info(f"✅ Estudio socioeconómico guardado para inscrito {inscrito_id}")
            
        except Exception as e:
            logger.error(f"❌ Error guardando estudio socioeconómico: {e}")
    
    def obtener_documentos_faltantes(self, inscrito_id):
        try:
            query_tipo = "SELECT tipo_programa FROM inscritos WHERE id = ?"
            tipo_result = self.ejecutar_query(query_tipo, (inscrito_id,))
            
            if not tipo_result:
                return []
            
            tipo_programa = tipo_result[0]['tipo_programa']
            
            query_docs = '''
                SELECT nombre_documento FROM documentos_programa 
                WHERE tipo_programa = ? AND obligatorio = 1
                ORDER BY orden
            '''
            documentos_obligatorios = self.ejecutar_query(query_docs, (tipo_programa,))
            
            query_subidos = "SELECT documentos_guardados FROM inscritos WHERE id = ?"
            subidos_result = self.ejecutar_query(query_subidos, (inscrito_id,))
            
            documentos_subidos = []
            if subidos_result and subidos_result[0]['documentos_guardados']:
                documentos_subidos = subidos_result[0]['documentos_guardados'].split(', ')
            
            obligatorios_nombres = [doc['nombre_documento'] for doc in documentos_obligatorios]
            faltantes = [doc for doc in obligatorios_nombres if doc not in documentos_subidos]
            
            if faltantes:
                query_update = "UPDATE inscritos SET documentos_faltantes = ? WHERE id = ?"
                self.ejecutar_query(query_update, (', '.join(faltantes), inscrito_id))
            
            return faltantes
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo documentos faltantes: {e}")
            return []
    
    def enviar_recordatorio(self, inscrito_id):
        try:
            query = '''
                SELECT nombre_completo, email, email_gmail, fecha_limite_registro 
                FROM inscritos WHERE id = ? AND recordatorio_enviado = 0
            '''
            resultado = self.ejecutar_query(query, (inscrito_id,))
            
            if not resultado:
                return False
            
            inscrito = resultado[0]
            fecha_limite = datetime.strptime(inscrito['fecha_limite_registro'], '%Y-%m-%d').date()
            hoy = date.today()
            dias_restantes = (fecha_limite - hoy).days
            
            if dias_restantes > 0 and dias_restantes <= 7:
                query_update = '''
                    UPDATE inscritos 
                    SET recordatorio_enviado = 1, ultimo_recordatorio = ?
                    WHERE id = ?
                '''
                self.ejecutar_query(query_update, (datetime.now().isoformat(), inscrito_id))
                
                estado_sistema.registrar_recordatorio()
                logger.info(f"✅ Recordatorio registrado para inscrito {inscrito_id} ({dias_restantes} días restantes)")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error enviando recordatorio: {e}")
            return False
    
    def limpiar_registros_incompletos(self, dias_inactividad=7):
        try:
            fecha_limite = (datetime.now() - timedelta(days=dias_inactividad)).date()
            
            query = '''
                DELETE FROM inscritos 
                WHERE completado = 0 
                AND DATE(fecha_registro) < ?
                AND documentos_subidos < 5
            '''
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (fecha_limite.isoformat(),))
                eliminados = cursor.rowcount
            
            estado_sistema.registrar_registro_incompleto_eliminado(eliminados)
            logger.info(f"🗑️ Eliminados {eliminados} registros incompletos")
            return eliminados
            
        except Exception as e:
            logger.error(f"❌ Error limpiando registros incompletos: {e}")
            return 0
    
    def obtener_inscritos(self):
        try:
            query = "SELECT * FROM inscritos ORDER BY fecha_registro DESC"
            resultados = self.ejecutar_query(query)
            return resultados if resultados else []
        except Exception as e:
            logger.error(f"❌ Error obteniendo inscritos: {e}")
            return []
    
    def obtener_inscrito_por_matricula(self, matricula):
        try:
            query = "SELECT * FROM inscritos WHERE matricula = ?"
            resultados = self.ejecutar_query(query, (matricula,))
            return resultados[0] if resultados else None
        except Exception as e:
            logger.error(f"❌ Error obteniendo inscrito: {e}")
            return None
    
    def obtener_total_inscritos(self):
        try:
            query = "SELECT COUNT(*) as total FROM inscritos"
            resultados = self.ejecutar_query(query)
            total = resultados[0]['total'] if resultados else 0
            
            estado_sistema.set_total_inscritos(total)
            
            return total
        except Exception as e:
            logger.error(f"❌ Error obteniendo total: {e}")
            return 0

db_completa = SistemaBaseDatosCompleto()

# ============================================================================
# CAPA 8: SISTEMA DE BACKUPS, CORREOS Y GESTIÓN REMOTA
# ============================================================================

class SistemaBackupAutomatico:
    """Sistema de backup automático remoto"""
    
    def __init__(self, gestor_ssh):
        self.gestor_ssh = gestor_ssh
        self.backup_dir = APP_CONFIG['backup_dir']
        self.max_backups = APP_CONFIG['max_backups']
        
    def crear_backup(self, tipo_operacion, detalles):
        try:
            if not os.path.exists(self.backup_dir):
                os.makedirs(self.backup_dir)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_{tipo_operacion}_{timestamp}.zip"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            if self.gestor_ssh.conectar_ssh():
                try:
                    temp_db = self.gestor_ssh.descargar_db_remota()
                    if temp_db:
                        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            zipf.write(temp_db, 'database.db')
                            
                            metadata = {
                                'fecha_backup': datetime.now().isoformat(),
                                'tipo_operacion': tipo_operacion,
                                'detalles': detalles,
                                'usuario': 'sistema'
                            }
                            
                            metadata_str = json.dumps(metadata, indent=2, default=str)
                            zipf.writestr('metadata.json', metadata_str)
                        
                        logger.info(f"✅ Backup creado: {backup_path}")
                        self._limpiar_backups_antiguos()
                        
                        return backup_path
                finally:
                    self.gestor_ssh.desconectar_ssh()
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error creando backup: {e}")
            return None
    
    def _limpiar_backups_antiguos(self):
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
                    logger.info(f"🗑️ Backup antiguo eliminado: {backup[0]}")
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo eliminar backup antiguo: {e}")
                    
        except Exception as e:
            logger.error(f"Error limpiando backups antiguos: {e}")
    
    def listar_backups(self):
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
            logger.error(f"Error listando backups: {e}")
            return []

class SistemaCorreosCompleto:
    """Sistema de envío de correos completo"""
    
    def __init__(self):
        try:
            smtp_config = gestor_remoto.config.get('smtp', {})
            
            self.smtp_server = smtp_config.get("smtp_server", "")
            self.smtp_port = int(smtp_config.get("smtp_port", 587))
            self.email_user = smtp_config.get("email_user", "")
            self.email_password = smtp_config.get("email_password", "")
            self.correos_habilitados = bool(self.smtp_server and self.email_user)
            
            if self.correos_habilitados:
                logger.info("✅ Sistema de correos configurado")
            else:
                logger.warning("⚠️ Sistema de correos no configurado completamente")
        except Exception as e:
            logger.warning(f"⚠️ Configuración de correo no disponible: {e}")
            self.correos_habilitados = False
    
    def enviar_correo_confirmacion_completo(self, destinatario, nombre_estudiante, matricula, folio, programa, tipo_programa):
        if not self.correos_habilitados:
            return False, "Sistema de correos no configurado"
        
        try:
            mensaje = MIMEMultipart()
            mensaje['From'] = self.email_user
            mensaje['To'] = destinatario
            mensaje['Subject'] = f"Confirmación de Pre-Inscripción - Folio: {folio}"
            
            cuerpo = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                    <div style="text-align: center; background-color: #2E86AB; color: white; padding: 20px; border-radius: 10px 10px 0 0;">
                        <h1>🏥 Escuela de Enfermería</h1>
                        <h2>Confirmación de Pre-Inscripción</h2>
                        <h3>Convocatoria Febrero 2026</h3>
                    </div>
                    
                    <div style="padding: 20px;">
                        <p>Estimado/a <strong>{nombre_estudiante}</strong>,</p>
                        
                        <p>Hemos recibido exitosamente tu solicitud de pre-inscripción. <strong>IMPORTANTE:</strong> Los resultados se publicarán únicamente con el folio asignado para garantizar la confidencialidad.</p>
                        
                        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0; border-left: 4px solid #2E86AB;">
                            <h3 style="color: #2E86AB; margin-top: 0;">📋 Datos de tu Registro</h3>
                            <p><strong>Folio Único (ANÓNIMO):</strong> <span style="background-color: #ffeaa7; padding: 2px 5px; border-radius: 3px; font-weight: bold;">{folio}</span></p>
                            <p><strong>Matrícula:</strong> {matricula}</p>
                            <p><strong>Programa:</strong> {programa} ({tipo_programa})</p>
                            <p><strong>Fecha de registro:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
                            <p><strong>Estatus:</strong> Pre-inscrito</p>
                        </div>
                        
                        <div style="background-color: #e8f4f8; padding: 15px; border-radius: 5px; margin: 15px 0; border-left: 4px solid #A23B72;">
                            <h4 style="color: #A23B72; margin-top: 0;">⚠️ INFORMACIÓN CRÍTICA</h4>
                            <p><strong>¡GUARDA TU FOLIO!</strong> Los resultados finales se publicarán <strong>SÓLO CON EL FOLIO {folio}</strong> para garantizar la privacidad.</p>
                            <p>No se mostrarán nombres completos en la publicación de resultados.</p>
                        </div>
                        
                        <h3 style="color: #2E86AB;">📬 Próximos Pasos</h3>
                        <ol>
                            <li><strong>Revisión de documentos</strong> (2-3 días hábiles)</li>
                            <li><strong>Correo de confirmación</strong> con fecha de examen</li>
                            <li><strong>Examen de admisión</strong> (presencial/online)</li>
                            <li><strong>Entrevista personal</strong> (si aplica)</li>
                            <li><strong>Publicación de resultados</strong> (solo con folio)</li>
                        </ol>
                        
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
                        <p>Folio generado automáticamente: {folio} | Sistema de Pre-Inscripción v4.0</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            mensaje.attach(MIMEText(cuerpo, 'html'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(mensaje)
            
            logger.info(f"✅ Correo de confirmación enviado a {destinatario} - Folio: {folio}")
            return True, "Correo enviado exitosamente"
            
        except socket.timeout:
            logger.error(f"❌ Timeout enviando correo a {destinatario}")
            return False, "Timeout al enviar correo"
        except Exception as e:
            logger.error(f"❌ Error enviando correo: {e}")
            return False, f"Error: {str(e)}"

# ============================================================================
# CAPA 9: SISTEMA DE AUTENTICACIÓN CORREGIDO
# ============================================================================

class SistemaAutenticacion:
    """Sistema de autenticación para usuarios administrativos - CORREGIDO"""
    
    def __init__(self):
        self.usuario_actual = None
        self.rol_actual = None
        
        if 'autenticado' not in st.session_state:
            st.session_state.autenticado = False
            st.session_state.usuario = None
            st.session_state.rol = None
    
    def mostrar_login(self):
        """Mostrar formulario de login"""
        with st.container():
            st.markdown("""
            <div style="background-color: #f0f2f6; padding: 30px; border-radius: 10px; 
                        max-width: 400px; margin: 50px auto; border: 1px solid #ddd;">
                <h2 style="text-align: center; color: #2E86AB;">🔐 Acceso Administrativo</h2>
                <p style="text-align: center; color: #666;">Ingresa tus credenciales para acceder al sistema</p>
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col2:
                with st.form("form_login", clear_on_submit=True):
                    usuario = st.text_input("Usuario", placeholder="admin", key="login_usuario")
                    password = st.text_input("Contraseña", type="password", 
                                           placeholder="Admin123!", key="login_password")
                    enviar = st.form_submit_button("Iniciar Sesión", type="primary", use_container_width=True)
                    
                    if enviar:
                        if self.validar_credenciales(usuario, password):
                            st.session_state.autenticado = True
                            st.session_state.usuario = usuario
                            st.session_state.rol = self.rol_actual
                            st.success(f"✅ Bienvenido, {usuario}!")
                            time.sleep(1)
                            st.session_state['needs_refresh'] = True  # SOLUCIÓN 1: En lugar de st.rerun()
                        else:
                            st.error("❌ Usuario o contraseña incorrectos")
                            
                            # Información de debug temporal (eliminar después)
                            with st.expander("🔍 Información de depuración (temporal)"):
                                st.info("Credenciales por defecto:")
                                st.code("Usuario: admin\nContraseña: Admin123!")
                                
                                # Verificar si hay usuarios en la base de datos
                                try:
                                    query = "SELECT usuario, LENGTH(password) as pass_len FROM usuarios"
                                    usuarios = db_completa.ejecutar_query(query)
                                    if usuarios:
                                        st.write("Usuarios en base de datos:", usuarios)
                                    else:
                                        st.warning("No hay usuarios en la base de datos")
                                except Exception as e:
                                    st.error(f"Error consultando usuarios: {e}")
    
    def validar_credenciales(self, usuario, password):
        """Validar credenciales usando el método corregido de la base de datos"""
        try:
            usuario_data = db_completa.verificar_usuario(usuario, password)
            
            if usuario_data:
                self.usuario_actual = usuario_data
                self.rol_actual = usuario_data['rol']
                logger.info(f"✅ Autenticación exitosa para: {usuario}")
                return True
            
            logger.warning(f"❌ Autenticación fallida para: {usuario}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error validando credenciales: {e}")
            return False
    
    def verificar_autenticacion(self, rol_requerido=None):
        """Verificar si el usuario está autenticado y tiene el rol requerido"""
        if not st.session_state.autenticado:
            return False
        
        if rol_requerido and st.session_state.rol != rol_requerido:
            st.error(f"❌ No tienes permisos para acceder a esta sección. Rol requerido: {rol_requerido}")
            return False
        
        return True
    
    def cerrar_sesion(self):
        """Cerrar sesión del usuario"""
        st.session_state.autenticado = False
        st.session_state.usuario = None
        st.session_state.rol = None
        st.success("✅ Sesión cerrada exitosamente")
        time.sleep(1)
        st.session_state['needs_refresh'] = True  # SOLUCIÓN 1: En lugar de st.rerun()
    
    def mostrar_cerrar_sesion(self):
        """Mostrar botón para cerrar sesión"""
        if st.session_state.autenticado:
            col1, col2, col3 = st.columns([3, 1, 3])
            with col2:
                if st.button("🚪 Cerrar Sesión", use_container_width=True):
                    self.cerrar_sesion()

# ============================================================================
# CAPA 10: COMPONENTES UI REUTILIZABLES
# ============================================================================

class ComponentesUI:
    """Componentes UI reutilizables"""
    
    @staticmethod
    def mostrar_header(titulo, subtitulo=""):
        st.markdown(f"""
        <style>
        .main-header {{
            font-size: 2.5rem;
            color: #2E86AB;
            text-align: center;
            margin-bottom: 1rem;
            font-weight: bold;
        }}
        .sub-header {{
            font-size: 1.5rem;
            color: #A23B72;
            margin-bottom: 2rem;
            font-weight: 600;
            text-align: center;
        }}
        .step-header {{
            background-color: #2E86AB;
            color: white;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        }}
        .info-box {{
            background-color: #e8f4f8;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
            border-left: 4px solid #A23B72;
        }}
        </style>
        """, unsafe_allow_html=True)
        
        st.markdown(f'<div class="main-header">{titulo}</div>', unsafe_allow_html=True)
        if subtitulo:
            st.markdown(f'<div class="sub-header">{subtitulo}</div>', unsafe_allow_html=True)
        st.markdown("---")
    
    @staticmethod
    def crear_sidebar(sistema_auth):
        """Crear sidebar con autenticación - SIN PESTAÑAS, solo selectbox"""
        with st.sidebar:
            st.title("🏥 Sistema de Pre-Inscripción")
            st.markdown(f"**Versión {APP_CONFIG['version']}**")
            st.markdown("---")
            
            # Mostrar información de usuario si está autenticado
            if sistema_auth and st.session_state.autenticado:
                st.markdown(f"**👤 Usuario:** {st.session_state.usuario}")
                st.markdown(f"**🎭 Rol:** {st.session_state.rol}")
                st.markdown("---")
            
            st.subheader("🔍 Estado del Sistema")
            
            if estado_sistema.estado.get('ssh_conectado'):
                st.success("✅ SSH Conectado")
            else:
                st.error("❌ SSH Descon.")
            
            st.subheader("📊 Estadísticas")
            col_stat1, col_stat2 = st.columns(2)
            with col_stat1:
                total_inscritos = estado_sistema.estado.get('total_inscritos', 0)
                st.metric("Inscritos", total_inscritos)
            
            with col_stat2:
                recordatorios = estado_sistema.estado.get('recordatorios_enviados', 0)
                st.metric("Recordatorios", recordatorios)
            
            st.markdown("---")
            st.subheader("📱 Navegación")
            
            # Definir opciones de menú según autenticación
            if sistema_auth and st.session_state.autenticado:
                # Para usuarios autenticados (administradores)
                opciones_menu = [
                    "🏠 Inicio y Resumen",
                    "📝 Nueva Pre-Inscripción",
                    "📋 Consultar Inscritos",
                    "⚙️ Configuración",
                    "📊 Reportes y Backups"
                ]
            else:
                # Para usuarios no autenticados
                opciones_menu = [
                    "🏠 Inicio y Resumen",
                    "📝 Nueva Pre-Inscripción",
                    "🔐 Acceso Administrativo"
                ]
            
            # Usar selectbox simple para la navegación (sin pestañas)
            menu_seleccionado = st.selectbox(
                "Selecciona una opción:",
                opciones_menu,
                key="menu_principal_select"
            )
            
            st.markdown("---")
            
            # Información del sistema
            ultima_sinc = estado_sistema.estado.get('ultima_sincronizacion', 'Nunca')
            if ultima_sinc != 'Nunca':
                try:
                    fecha_sinc = datetime.fromisoformat(ultima_sinc.replace('Z', '+00:00'))
                    ultima_sinc = fecha_sinc.strftime('%Y-%m-d %H:%M')
                except:
                    pass
            
            st.caption(f"🔄 Última sincronización: {ultima_sinc}")
            st.caption(f"💾 Backups: {estado_sistema.estado.get('backups_realizados', 0)}")
            st.caption(f"📁 Archivos remotos: {estado_sistema.estado.get('archivos_subidos_remoto', 0)}")
            
            # Botón de cerrar sesión si está autenticado
            if sistema_auth and st.session_state.autenticado:
                if st.button("🚪 Cerrar Sesión", use_container_width=True, type="secondary"):
                    sistema_auth.cerrar_sesion()
            
            return menu_seleccionado
    
    @staticmethod
    def crear_paso_formulario(numero, titulo, contenido_func, expandido=True):
        with st.expander(f"PASO {numero}: {titulo}", expanded=expandido):
            return contenido_func()
    
    @staticmethod
    def mostrar_mensaje_exito(titulo, detalles):
        st.success(f"✅ **{titulo}**")
        st.markdown(f"""
        <div style="background-color: #d4edda; padding: 15px; border-radius: 5px; margin: 10px 0;">
        {detalles}
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def mostrar_mensaje_error(titulo, detalles):
        st.error(f"❌ **{titulo}**")
        st.markdown(f"""
        <div style="background-color: #f8d7da; padding: 15px; border-radius: 5px; margin: 10px 0;">
        {detalles}
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def crear_boton_accion(texto, tipo="primary", container=True):
        return st.button(texto, type=tipo, use_container_width=container)

# ============================================================================
# CAPA 11: SERVICIOS DE DATOS Y LÓGICA
# ============================================================================

class ServicioProgramas:
    """Servicio para gestión de programas académicos"""
    
    @staticmethod
    def obtener_programas_completos():
        """Obtener todos los programas organizados por categoría"""
        return [
            # POSGRADO
            {
                "categoria": "Posgrado",
                "categoria_id": "posgrado",
                "tipo_programa": "MAESTRIA",
                "nombre": "Maestría en Enfermería",
                "duracion": "2 años",
                "modalidad": "Presencial",
                "descripcion": "Formación avanzada en enfermería con especialización en investigación clínica. Desarrolla habilidades en gestión, liderazgo y metodología de investigación aplicada al ámbito de la salud.",
                "requisitos": ["Licenciatura en Enfermería", "Cédula profesional", "2 años de experiencia clínica", "Promedio mínimo de 8.0", "Examen de admisión", "Entrevista personal"]
            },
            {
                "categoria": "Posgrado",
                "categoria_id": "posgrado", 
                "tipo_programa": "ESPECIALIDAD",
                "nombre": "Especialidad en Enfermería Cardiovascular",
                "duracion": "2 años",
                "modalidad": "Presencial",
                "descripcion": "Formación especializada en el cuidado integral de pacientes con patologías cardiovasculares. Enfoque en técnicas avanzadas de monitorización, intervención y rehabilitación cardíaca.",
                "requisitos": ["Licenciatura en Enfermería", "Cédula profesional", "2 años de experiencia en área clínica", "Examen de conocimientos", "Entrevista con comité académico"]
            },
            {
                "categoria": "Posgrado",
                "categoria_id": "posgrado",
                "tipo_programa": "ESPECIALIDAD",
                "nombre": "Especialidad en Cuidados Intensivos",
                "duracion": "2 años",
                "modalidad": "Presencial",
                "descripcion": "Formación en cuidados críticos y atención especializada a pacientes en estado grave. Manejo de ventilación mecánica, monitorización hemodinámica y farmacología avanzada.",
                "requisitos": ["Licenciatura en Enfermería", "Cédula profesional", "1 año de experiencia en urgencias o terapia intensiva", "Examen de aptitudes", "Entrevista técnica"]
            },
            
            # PREGRADO
            {
                "categoria": "Pregrado",
                "categoria_id": "pregrado",
                "tipo_programa": "LICENCIATURA",
                "nombre": "Licenciatura en Enfermería",
                "duracion": "4 años",
                "modalidad": "Presencial",
                "descripcion": "Formación integral en enfermería con enfoque en cardiología. Desarrolla competencias en cuidado holístico, gestión de servicios de salud y prevención de enfermedades cardiovasculares.",
                "requisitos": ["Bachillerato terminado", "Promedio mínimo 8.0", "Examen de admisión", "Aptitud para el servicio", "Examen médico"]
            },
            {
                "categoria": "Pregrado",
                "categoria_id": "pregrado",
                "tipo_programa": "LICENCIATURA", 
                "nombre": "Licenciatura en Enfermería - RSC Cardiovascular",
                "duracion": "4 años",
                "modalidad": "Presencial",
                "descripcion": "Formación especializada en Rehabilitación y Salud Cardiovascular. Enfoque en prevención secundaria, programas de ejercicio terapéutico y manejo integral del paciente cardíaco.",
                "requisitos": ["Bachillerato terminado", "Promedio mínimo 8.0", "Aptitud física certificada", "Examen de conocimientos básicos", "Entrevista motivacional"]
            },
            {
                "categoria": "Pregrado",
                "categoria_id": "pregrado",
                "tipo_programa": "LICENCIATURA",
                "nombre": "Licenciatura en Enfermería - Cardiología Hepática",
                "duracion": "4 años",
                "modalidad": "Presencial",
                "descripcion": "Formación en cuidados de pacientes con patologías hepato-cardíacas. Integración de conocimientos en fisiopatología, farmacología especializada y manejo de complicaciones.",
                "requisitos": ["Bachillerato terminado", "Promedio mínimo 8.0", "Examen de admisión", "Interés demostrado en área clínica"]
            },
            {
                "categoria": "Pregrado",
                "categoria_id": "pregrado",
                "tipo_programa": "LICENCIATURA",
                "nombre": "Licenciatura en Enfermería Pediátrica",
                "duracion": "4 años",
                "modalidad": "Presencial",
                "descripcion": "Formación especializada en cuidados de enfermería para población infantil y adolescente. Énfasis en crecimiento y desarrollo, pediatría social y cuidados paliativos pediátricos.",
                "requisitos": ["Bachillerato terminado", "Promedio mínimo 8.0", "Vocación de servicio certificada", "Aptitud para trabajo con niños", "Entrevista psicológica"]
            },
            
            # EDUCACIÓN CONTINUA
            {
                "categoria": "Educación Continua",
                "categoria_id": "educacion_continua",
                "tipo_programa": "DIPLOMADO",
                "nombre": "Diplomado en Cardiología Básica",
                "duracion": "6 meses",
                "modalidad": "Híbrida",
                "descripcion": "Actualización en fundamentos de cardiología para profesionales de la salud. Interpretación de ECG, reconocimiento de arritmias y manejo inicial de síndromes coronarios agudos.",
                "requisitos": ["Título profesional en área de la salud", "Experiencia mínima 1 año", "Disponibilidad para sesiones prácticas"]
            },
            {
                "categoria": "Educación Continua",
                "categoria_id": "educacion_continua",
                "tipo_programa": "DIPLOMADO",
                "nombre": "Diplomado en Enfermería Oncológica",
                "duracion": "6 meses",
                "modalidad": "Híbrida",
                "descripcion": "Formación en cuidados de enfermería especializados para pacientes oncológicos. Manejo de quimioterapia, cuidados paliativos y soporte emocional al paciente y familia.",
                "requisitos": ["Licenciatura en Enfermería o área afín", "Experiencia en área clínica", "Disponibilidad para rotaciones hospitalarias"]
            },
            {
                "categoria": "Educación Continua",
                "categoria_id": "educacion_continua",
                "tipo_programa": "CURSO",
                "nombre": "Curso de RCP Avanzado",
                "duracion": "40 horas",
                "modalidad": "Presencial",
                "descripcion": "Certificación en Reanimación Cardiopulmonar Avanzada según estándares internacionales. Manejo de vía aérea, desfibrilación y algoritmos de emergencia cardiovascular.",
                "requisitos": ["Título en área de la salud", "Certificación BLS vigente", "Aptitud física"]
            },
            {
                "categoria": "Educación Continua",
                "categoria_id": "educacion_continua",
                "tipo_programa": "CURSO",
                "nombre": "Curso de Electrocardiografía Básica",
                "duracion": "30 horas",
                "modalidad": "Presencial",
                "descripcion": "Interpretación básica de electrocardiogramas para personal de salud. Reconocimiento de ritmos cardíacos, isquemia e infarto, y monitorización continua.",
                "requisitos": ["Estudiantes o profesionales de salud", "Conocimientos básicos de anatomía y fisiología"]
            },
            {
                "categoria": "Educación Continua",
                "categoria_id": "educacion_continua",
                "tipo_programa": "CURSO",
                "nombre": "Taller de Cuidados Paliativos",
                "duracion": "20 horas",
                "modalidad": "Presencial",
                "descripcion": "Atención integral a pacientes en fase terminal y sus familias. Manejo del dolor, comunicación efectiva y soporte emocional en situaciones de final de vida.",
                "requisitos": ["Personal de salud", "Interés en área humanística", "Disponibilidad emocional"]
            }
        ]
    
    @staticmethod
    def obtener_documentos_por_tipo(tipo_programa):
        """DEVUELVE EXACTAMENTE LOS DOCUMENTOS REQUERIDOS SIN INCONSISTENCIAS"""
        if tipo_programa == "LICENCIATURA":
            return [
                "Certificado preparatoria (promedio ≥ 8.0)",
                "Acta nacimiento (≤ 3 meses)",
                "CURP (≤ 1 mes)",
                "Cartilla Nacional de Salud",
                "INE del tutor",
                "Comprobante domicilio (≤ 3 meses)",
                "Certificado médico institucional (≤ 1 mes)",
                "12 fotografías infantiles B/N",
                "Comprobante domicilio (adicional)",
                "Carta de exposición de motivos"
            ]
        elif tipo_programa == "ESPECIALIDAD":
            return [
                "Certificado preparatoria (promedio ≥ 8.0)",
                "Acta nacimiento (≤ 3 meses)",
                "CURP (≤ 1 mes)",
                "Cartilla Nacional de Salud",
                "INE del tutor",
                "Comprobante domicilio (≤ 3 meses)",
                "Certificado médico institucional (≤ 1 mes)",
                "12 fotografías infantiles B/N",
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
        elif tipo_programa == "MAESTRIA":
            return [
                "Certificado preparatoria (promedio ≥ 8.0)",
                "Acta nacimiento (≤ 3 meses)",
                "CURP (≤ 1 mes)",
                "Cartilla Nacional de Salud",
                "INE del tutor",
                "Comprobante domicilio (≤ 3 meses)",
                "Certificado médico institucional (≤ 1 mes)",
                "12 fotografías infantiles B/N",
                "Título profesional",
                "Certificado de licenciatura",
                "Cédula profesional",
                "INE (vigente)",
                "Constancia de experiencia laboral (3+ años)",
                "Carta de intención",
                "Propuesta de investigación",
                "2 cartas de recomendación"
            ]
        elif tipo_programa == "DIPLOMADO":
            return [
                "Certificado preparatoria (promedio ≥ 8.0)",
                "Acta nacimiento (≤ 3 meses)",
                "CURP (≤ 1 mes)",
                "Cartilla Nacional de Salud",
                "INE del tutor",
                "Comprobante domicilio (≤ 3 meses)",
                "Certificado médico institucional (≤ 1 mes)",
                "12 fotografías infantiles B/N",
                "Título profesional",
                "Cédula profesional",
                "INE (vigente)",
                "Currículum vitae",
                "Carta de exposición de motivos"
            ]
        else:  # CURSO
            return [
                "Certificado preparatoria (promedio ≥ 8.0)",
                "Acta nacimiento (≤ 3 meses)",
                "CURP (≤ 1 mes)",
                "Cartilla Nacional de Salud",
                "INE del tutor",
                "Comprobante domicilio (≤ 3 meses)",
                "Certificado médico institucional (≤ 1 mes)",
                "12 fotografías infantiles B/N",
                "Identificación oficial",
                "Comprobante de estudios",
                "Currículum vitae"
            ]

class ServicioGeneradores:
    """Servicio para generar códigos únicos"""
    
    @staticmethod
    def generar_matricula():
        try:
            while True:
                fecha = datetime.now().strftime('%y%m%d')
                random_num = ''.join(random.choices(string.digits, k=4))
                matricula = f"INS{fecha}{random_num}"
                
                if db_completa:
                    if not db_completa.obtener_inscrito_por_matricula(matricula):
                        return matricula
                else:
                    return matricula
        except:
            return f"INS{datetime.now().strftime('%y%m%d%H%M%S')}"
    
    @staticmethod
    def generar_folio_unico():
        fecha = datetime.now().strftime('%y%m%d')
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"FOL{fecha}{random_str}"

class ServicioValidacionCompleto(ValidadorDatos):
    """Servicio de validación extendido"""
    
    # MÍNIMOS CONSISTENTES CON LOS DOCUMENTOS REALMENTE REQUERIDOS
    minimos_consistente = {
        "LICENCIATURA": 10,      # 10 documentos se muestran para LICENCIATURA
        "ESPECIALIDAD": 17,      # 17 documentos se muestran para ESPECIALIDAD
        "MAESTRIA": 16,          # 16 documentos se muestran para MAESTRIA
        "DIPLOMADO": 13,         # 13 documentos se muestran para DIPLOMADO
        "CURSO": 11              # 11 documentos se muestran para CURSO
    }
    
    @staticmethod
    def validar_campos_obligatorios(campos):
        errores = []
        for campo, nombre in campos:
            if not campo:
                errores.append(f"❌ {nombre} es obligatorio")
        return errores
    
    @staticmethod
    def validar_documentos_minimos(documentos_subidos, tipo_programa):
        """Validación CONSISTENTE: Si muestra X documentos, pide X documentos"""
        minimo_requerido = ServicioValidacionCompleto.minimos_consistente.get(tipo_programa, 11)
        
        if not isinstance(documentos_subidos, list):
            return False, f"❌ Error en el formato de documentos"
        
        # Contar documentos únicos (evitar duplicados)
        documentos_unicos = set()
        for doc_info in documentos_subidos:
            if 'archivo' in doc_info and doc_info['archivo'] is not None:
                archivo = doc_info['archivo']
                documentos_unicos.add(f"{archivo.name}_{archivo.size}")
        
        documentos_count = len(documentos_unicos)
        
        if documentos_count < minimo_requerido:
            return False, f"❌ Se requieren TODOS los {minimo_requerido} documentos para {tipo_programa}. Subiste {documentos_count}."
        
        return True, ""

# ============================================================================
# CAPA 12: SISTEMA DE INSCRITOS COMPLETO TRABAJANDO EN REMOTO - VERSIÓN CORREGIDA
# ============================================================================

class SistemaInscritosCompleto:
    """Sistema principal de gestión de inscritos COMPLETO que trabaja en remoto - VERSIÓN CORREGIDA"""
    
    def __init__(self):
        self.base_datos = db_completa
        self.sistema_correos = SistemaCorreosCompleto()
        self.validador = ServicioValidacionCompleto()
        self.generadores = ServicioGeneradores()
        self.servicio_programas = ServicioProgramas()
        self.backup_system = SistemaBackupAutomatico(gestor_remoto)
        self.gestor_archivos = SistemaGestionArchivosRemotos()
        
        # Inicializar estados específicos PARA CONTADOR DE DOCUMENTOS
        if 'formulario_estado' not in st.session_state:
            st.session_state.formulario_estado = {
                'programa_seleccionado': None,
                'programa_info': None,
                'matricula_generada': None,
                'documentos_subidos': [],
                'contador_documentos': 0
            }
        
        if 'documentos_subidos_info' not in st.session_state:
            st.session_state.documentos_subidos_info = []
        
        logger.info("🚀 Sistema de inscritos COMPLETO (remoto) inicializado - CONTADOR DE DOCUMENTOS CORREGIDO")
    
    def mostrar_formulario_completo_interactivo(self):
        """Formulario interactivo CORREGIDO - Con contador de documentos funcional"""
        ComponentesUI.mostrar_header("📝 Formulario Completo de Pre-Inscripción", 
                                    "Escuela de Enfermería - Convocatoria Febrero 2026")
        
        if 'formulario_enviado' not in st.session_state:
            st.session_state.formulario_enviado = False
        
        if not st.session_state.formulario_enviado:
            # Sección 1: Selección de programa
            self._mostrar_seleccion_programa()
            
            # Si hay programa seleccionado, mostrar el formulario
            if st.session_state.formulario_estado['programa_info']:
                programa_info = st.session_state.formulario_estado['programa_info']
                
                with st.form("formulario_completo_interactivo", clear_on_submit=False):  # IMPORTANTE: clear_on_submit=False
                    # Pasar la información del programa al resto del formulario
                    seleccion_programa = {
                        "categoria": programa_info['categoria'],
                        "categoria_id": programa_info['categoria_id'],
                        "tipo_programa": programa_info['tipo_programa'],
                        "programa": programa_info['nombre'],
                        "duracion": programa_info['duracion'],
                        "modalidad": programa_info['modalidad'],
                        "descripcion": programa_info['descripcion']
                    }
                    
                    # PASO 2: Datos personales
                    datos_personales = self._mostrar_paso_datos_personales(seleccion_programa["tipo_programa"])
                    
                    st.markdown("---")
                    
                    # PASO 3: Documentación (SUBIDA DIRECTA AL SERVIDOR REMOTO) - CORREGIDO
                    documentos = self._mostrar_paso_documentacion_completa_corregida(
                        seleccion_programa["tipo_programa"], 
                        datos_personales.get("matricula_generada", "")
                    )
                    
                    st.markdown("---")
                    
                    # PASO 4: Estudio socioeconómico
                    estudio_socioeconomico = self._mostrar_paso_estudio_socioeconomico()
                    
                    st.markdown("---")
                    
                    # PASO 5: Aceptaciones
                    aceptaciones = self._mostrar_paso_aceptaciones()
                    
                    st.markdown("---")
                    
                    # PASO 6: Examen psicométrico
                    examen_psicometrico = self._mostrar_paso_examen_psicometrico()
                    
                    st.markdown("---")
                    
                    enviado = st.form_submit_button(
                        "🚀 **ENVIAR SOLICITUD COMPLETA DE PRE-INSCRIPCIÓN**", 
                        use_container_width=True, type="primary"
                    )
                    
                    if enviado:
                        self._procesar_envio_corregido(
                            seleccion_programa,
                            datos_personales,
                            documentos,
                            estudio_socioeconomico,
                            aceptaciones,
                            examen_psicometrico
                        )
            else:
                st.warning("⚠️ **Debes seleccionar un programa antes de continuar con el formulario.**")
        
        else:
            self._mostrar_resultado_exitoso()
    
    def _mostrar_seleccion_programa(self):
        """Mostrar selección de programa"""
        st.markdown("### 🎓 Selecciona el programa de tu interés")
        
        # Obtener todos los programas
        programas = self.servicio_programas.obtener_programas_completos()
        
        # Crear opciones formateadas para mostrar
        opciones_programas = []
        programas_dict = {}
        
        for programa in programas:
            # Formato: "Categoría - Nombre del Programa (Tipo - Duración)"
            opcion_formateada = f"{programa['categoria']} - {programa['nombre']} ({programa['tipo_programa']} - {programa['duracion']})"
            opciones_programas.append(opcion_formateada)
            programas_dict[opcion_formateada] = programa
        
        # Usar clave única para el selectbox
        programa_seleccionado = st.selectbox(
            "**Programa de Interés ***",
            opciones_programas,
            help="Selecciona el programa que deseas cursar",
            key="programa_seleccionado_key",
            index=None,
            placeholder="Selecciona un programa..."
        )
        
        st.markdown("---")
        
        # Actualizar estado inmediatamente cuando se selecciona
        if programa_seleccionado and programa_seleccionado != st.session_state.get('ultimo_programa_seleccionado', ''):
            if programa_seleccionado in programas_dict:
                st.session_state.formulario_estado['programa_info'] = programas_dict[programa_seleccionado]
                st.session_state.formulario_estado['programa_seleccionado'] = programa_seleccionado
                st.session_state.ultimo_programa_seleccionado = programa_seleccionado
                st.success(f"✅ Programa seleccionado: {programa_seleccionado}")
        
        # Botón para confirmar selección
        if programa_seleccionado and st.button("✅ Confirmar Selección de Programa", key="confirmar_programa_btn"):
            if programa_seleccionado in programas_dict:
                st.session_state.formulario_estado['programa_info'] = programas_dict[programa_seleccionado]
                st.session_state.formulario_estado['programa_seleccionado'] = programa_seleccionado
                st.session_state.ultimo_programa_seleccionado = programa_seleccionado
                st.success(f"✅ Programa seleccionado: {programa_seleccionado}")
        
        # Mostrar información del programa seleccionado (si hay)
        if st.session_state.formulario_estado['programa_info']:
            programa_info = st.session_state.formulario_estado['programa_info']
            self._mostrar_info_programa(programa_info)
    
    def _mostrar_info_programa(self, programa_info):
        """Mostrar información del programa seleccionado"""
        # Obtener documentos requeridos para este programa
        documentos_requeridos = self.servicio_programas.obtener_documentos_por_tipo(programa_info['tipo_programa'])
        minimo_requerido = ServicioValidacionCompleto.minimos_consistente.get(programa_info['tipo_programa'], len(documentos_requeridos))
        
        # Mostrar detalles del programa seleccionado
        with st.container():
            # Encabezado con icono y colores
            st.markdown(f"""
            <div style="background-color: #e8f4f8; padding: 15px; border-radius: 5px; 
                        border-left: 4px solid #2E86AB; margin-bottom: 15px;">
                <h3 style="color: #2E86AB; margin: 0;">
                📋 <strong>INFORMACIÓN DEL PROGRAMA SELECCIONADO</strong>
                </h3>
            </div>
            """, unsafe_allow_html=True)
            
            # Usar columnas para mejor organización
            col_info1, col_info2 = st.columns(2)
            
            with col_info1:
                st.markdown(f"**🏷️ Categoría:** `{programa_info['categoria']}`")
                st.markdown(f"**📚 Tipo de Programa:** `{programa_info['tipo_programa']}`")
                st.markdown(f"**⏱️ Duración:** `{programa_info['duracion']}`")
            
            with col_info2:
                st.markdown(f"**🎓 Modalidad:** `{programa_info['modalidad']}`")
                st.markdown(f"**📄 Documentos requeridos:** `{minimo_requerido}`")
            
            # Descripción en un recuadro destacado
            with st.expander("📝 **DESCRIPCIÓN DETALLADA**", expanded=True):
                st.write(programa_info['descripcion'])
            
            # Requisitos en una lista numerada
            with st.expander("✅ **REQUISITOS DE INGRESO**", expanded=True):
                for i, req in enumerate(programa_info['requisitos'], 1):
                    st.markdown(f"{i}. {req}")
            
            # Mostrar documentos específicos para este tipo de programa
            with st.expander(f"📄 **DOCUMENTOS REQUERIDOS ({len(documentos_requeridos)} documentos - TODOS OBLIGATORIOS)**", expanded=False):
                st.info(f"**¡IMPORTANTE!** Debes subir **TODOS los {minimo_requerido} documentos** para completar tu pre-inscripción.")
                
                # Dividir documentos en columnas para mejor visualización
                col_doc1, col_doc2 = st.columns(2)
                
                docs_col1 = documentos_requeridos[:len(documentos_requeridos)//2]
                docs_col2 = documentos_requeridos[len(documentos_requeridos)//2:]
                
                with col_doc1:
                    for i, doc in enumerate(docs_col1, 1):
                        st.markdown(f"**{i}. {doc}**")
                
                with col_doc2:
                    start_idx = len(docs_col1) + 1
                    for i, doc in enumerate(docs_col2, start_idx):
                        st.markdown(f"**{i}. {doc}**")
            
            st.markdown("---")
    
    def _mostrar_paso_datos_personales(self, tipo_programa):
        # Generar matrícula automáticamente
        if not st.session_state.formulario_estado['matricula_generada']:
            st.session_state.formulario_estado['matricula_generada'] = self.generadores.generar_matricula()
        
        matricula_generada = st.session_state.formulario_estado['matricula_generada']
        
        col_datos1, col_datos2 = st.columns(2)
        
        with col_datos1:
            nombre_completo = st.text_input("**Nombre Completo ***", placeholder="Ej: María González López", key="nombre_input")
            email = st.text_input("**Correo Electrónico Personal ***", placeholder="ejemplo@email.com", key="email_input")
            email_gmail = st.text_input("**Correo Gmail ***", placeholder="ejemplo@gmail.com", 
                                       help="Debe ser una cuenta @gmail.com - Se usará para comunicación oficial", key="email_gmail_input")
        
        with col_datos2:
            telefono = st.text_input("**Teléfono ***", placeholder="5512345678", key="telefono_input")
            
            if tipo_programa in ["LICENCIATURA", "MAESTRIA"]:
                estado_civil = st.selectbox("**Estado Civil**", ["", "Soltero/a", "Casado/a", "Divorciado/a", "Viudo/a", "Unión libre"], key="estado_civil_input")
                edad = st.number_input("**Edad**", min_value=17, max_value=60, value=18, key="edad_input")
                domicilio = st.text_area("**Domicilio Completo**", placeholder="Calle, número, colonia, ciudad, estado, código postal", key="domicilio_input")
            
            elif tipo_programa == "ESPECIALIDAD":
                licenciatura_origen = st.text_input("**Licenciatura de Origen ***", 
                                                   placeholder="Ej: Licenciatura en Enfermería", key="licenciatura_input")
                domicilio = st.text_area("**Domicilio Completo**", placeholder="Calle, número, colonia, ciudad, estado, código postal", key="domicilio_input2")
            else:
                domicilio = st.text_area("**Domicilio**", placeholder="Calle, número, colonia, ciudad, estado, código postal", key="domicilio_input3")
        
        matricula_unam = st.text_input("Matrícula UNAM (si ya tienes)", placeholder="Dejar vacío si no aplica", key="matricula_unam_input")
        
        # Mostrar matrícula generada
        st.info(f"**🎫 Tu matrícula asignada:** `{matricula_generada}`")
        
        return {
            "matricula_generada": matricula_generada,
            "nombre": nombre_completo,
            "email": email,
            "email_gmail": email_gmail,
            "telefono": telefono,
            "estado_civil": estado_civil if tipo_programa in ["LICENCIATURA", "MAESTRIA"] else "",
            "edad": edad if tipo_programa in ["LICENCIATURA", "MAESTRIA"] else None,
            "domicilio": domicilio,
            "licenciatura_origen": licenciatura_origen if tipo_programa == "ESPECIALIDAD" else "",
            "matricula_unam": matricula_unam
        }
    
    def _mostrar_paso_documentacion_completa_corregida(self, tipo_programa, matricula):
        """VERSIÓN CORREGIDA - Contador de documentos funcional"""
        st.markdown("### 📄 **SUBA SUS DOCUMENTOS (DIRECTO AL SERVIDOR REMOTO)**")
        
        documentos_requeridos = self.servicio_programas.obtener_documentos_por_tipo(tipo_programa)
        minimo_requerido = ServicioValidacionCompleto.minimos_consistente.get(tipo_programa, len(documentos_requeridos))
        
        st.info(f"""
        **Matrícula:** `{matricula}` 
        **📋 Documentos requeridos:** **{minimo_requerido} documentos** (TODOS obligatorios)
        **🌐 Los documentos se subirán DIRECTAMENTE al servidor remoto**
        """)
        
        # Inicializar lista de archivos subidos si no existe
        if 'archivos_subidos_info' not in st.session_state:
            st.session_state.archivos_subidos_info = []
        
        # Dividir documentos en grupos para mejor organización
        documentos_grupo1 = documentos_requeridos[:len(documentos_requeridos)//2]
        documentos_grupo2 = documentos_requeridos[len(documentos_requeridos)//2:]
        
        col_doc1, col_doc2 = st.columns(2)
        
        archivos_subidos_info = []
        
        with col_doc1:
            for i, doc in enumerate(documentos_grupo1, 1):
                # Usar una clave única basada en matrícula y documento
                unique_key = f"doc_{matricula}_{doc.replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_')}_{i}"
                
                archivo = st.file_uploader(
                    f"**{i}. {doc}**",
                    type=['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'],
                    key=unique_key,
                    help=f"Documento {i} de {minimo_requerido}: {doc}"
                )
                
                if archivo is not None:
                    # Verificar duplicados por nombre y tamaño
                    file_already_added = any(
                        a['archivo'].name == archivo.name and 
                        a['archivo'].size == archivo.size
                        for a in archivos_subidos_info
                    )
                    
                    if not file_already_added:
                        st.success(f"✅ **{archivo.name}** ({archivo.size:,} bytes)")
                        
                        archivos_subidos_info.append({
                            'nombre_documento': doc,
                            'archivo': archivo,
                            'indice': i
                        })
                    else:
                        st.warning(f"⚠️ Este archivo ya fue seleccionado")
        
        with col_doc2:
            for i, doc in enumerate(documentos_grupo2, len(documentos_grupo1) + 1):
                # Usar una clave única basada en matrícula y documento
                unique_key = f"doc_{matricula}_{doc.replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_')}_{i}"
                
                archivo = st.file_uploader(
                    f"**{i}. {doc}**",
                    type=['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'],
                    key=unique_key,
                    help=f"Documento {i} de {minimo_requerido}: {doc}"
                )
                
                if archivo is not None:
                    # Verificar duplicados por nombre y tamaño
                    file_already_added = any(
                        a['archivo'].name == archivo.name and 
                        a['archivo'].size == archivo.size
                        for a in archivos_subidos_info
                    )
                    
                    if not file_already_added:
                        st.success(f"✅ **{archivo.name}** ({archivo.size:,} bytes)")
                        
                        archivos_subidos_info.append({
                            'nombre_documento': doc,
                            'archivo': archivo,
                            'indice': i
                        })
                    else:
                        st.warning(f"⚠️ Este archivo ya fue seleccionado")
        
        # ACTUALIZAR EL ESTADO GLOBAL - CORRECCIÓN CLAVE
        st.session_state.archivos_subidos_info = archivos_subidos_info
        
        # Mostrar resumen claro
        documentos_count = len(archivos_subidos_info)
        
        # Actualizar contador en estado del formulario
        st.session_state.formulario_estado['contador_documentos'] = documentos_count
        
        # Mostrar diagnóstico detallado
        with st.expander("🔍 **RESUMEN DE DOCUMENTOS**", expanded=True):
            st.write(f"**Documentos requeridos:** {minimo_requerido}")
            st.write(f"**Documentos subidos:** {documentos_count}")
            
            if documentos_count > 0:
                st.write("**Detalles de archivos subidos:**")
                for i, info in enumerate(archivos_subidos_info, 1):
                    st.write(f"{i}. **{info['nombre_documento']}:** {info['archivo'].name} ({info['archivo'].size:,} bytes)")
        
        # Mostrar estado actual con contador
        st.markdown(f"### 📊 **CONTADOR DE DOCUMENTOS:** `{documentos_count}/{minimo_requerido}`")
        
        if documentos_count > 0:
            if documentos_count == minimo_requerido:
                st.success(f"✅ **¡PERFECTO!** Has subido {documentos_count} de {minimo_requerido} documentos requeridos")
            elif documentos_count > minimo_requerido:
                st.success(f"✅ **¡EXCELENTE!** Has subido {documentos_count} documentos (más de los {minimo_requerido} requeridos)")
            else:
                st.warning(f"⚠️ **FALTAN DOCUMENTOS:** Has subido {documentos_count} de {minimo_requerido} documentos requeridos")
        else:
            st.error(f"❌ **No has subido ningún documento.** Necesitas {minimo_requerido} documentos.")
        
        # Mostrar gráfica de progreso
        progreso = documentos_count / minimo_requerido if minimo_requerido > 0 else 0
        st.progress(progreso, text=f"Progreso: {documentos_count}/{minimo_requerido} documentos")
        
        return {
            "documentos_requeridos": documentos_requeridos,
            "archivos_subidos_info": archivos_subidos_info,  # RETORNAR LA LISTA ACTUAL
            "total_subidos": documentos_count,
            "minimo_requerido": minimo_requerido
        }
    
    def _mostrar_paso_estudio_socioeconomico(self):
        with st.expander("📊 Estudio Socioeconómico (Opcional)", expanded=False):
            col_soc1, col_soc2 = st.columns(2)
            
            with col_soc1:
                ingreso_familiar = st.number_input("Ingreso Familiar Mensual (MXN)", min_value=0, value=0, step=1000, key="ingreso_input")
                personas_dependientes = st.number_input("Personas Dependientes", min_value=0, max_value=20, value=1, key="dependientes_input")
                vivienda_propia = st.checkbox("Vivienda Propia", key="vivienda_input")
                transporte_propio = st.checkbox("Transporte Propio", key="transporte_input")
            
            with col_soc2:
                seguro_medico = st.selectbox("Seguro Médico", ["", "IMSS", "ISSSTE", "Privado", "Ninguno"], key="seguro_input")
                discapacidad = st.checkbox("Discapacidad o Condición Especial", key="discapacidad_input")
                beca_solicitada = st.checkbox("Solicita Beca", key="beca_input")
                trabajo_estudiantil = st.checkbox("Trabajo Estudiantil", key="trabajo_input")
            
            detalles_socioeconomicos = st.text_area("Observaciones Adicionales", key="detalles_input")
        
        return {
            'ingreso_familiar': ingreso_familiar,
            'personas_dependientes': personas_dependientes,
            'vivienda_propia': vivienda_propia,
            'transporte_propio': transporte_propio,
            'seguro_medico': seguro_medico,
            'discapacidad': discapacidad,
            'beca_solicitada': beca_solicitada,
            'trabajo_estudiantil': trabajo_estudiantil,
            'detalles': detalles_socioeconomicos
        }
    
    def _mostrar_paso_aceptaciones(self):
        st.markdown("**📄 Aceptaciones obligatorias:**")
        
        col_acep1, col_acep2 = st.columns(2)
        
        with col_acep1:
            with st.expander("📜 Leer Aviso de Privacidad", expanded=False):
                st.markdown("""
                **AVISO DE PRIVACIDAD INTEGRAL**
                
                En cumplimiento a lo dispuesto por la Ley Federal de Protección de Datos Personales en Posesión de los Particulares, la Escuela de Enfermería hace de su conocimiento que los datos personales que nos proporcione serán tratados de manera confidencial y utilizados exclusivamente para:
                
                1. Proceso de admisión y selección
                2. Comunicación institucional
                3. Gestión académica
                4. Estadísticas institucionales
                
                Sus datos no serán compartidos con terceros sin su consentimiento expreso.
                """)
            
            aviso_privacidad = st.checkbox(
                "**He leído y acepto el Aviso de Privacidad ***",
                help="El aviso de privacidad describe cómo se manejarán tus datos personales.",
                key="aviso_checkbox"
            )
        
        with col_acep2:
            with st.expander("📜 Leer Convocatoria UNAM 2026", expanded=False):
                st.markdown("""
                **CONVOCATORIA UNAM FEBRERO 2026**
                
                La Universidad Nacional Autónoma de México convoca a los interesados en cursar estudios en la Escuela de Enfermería a participar en el proceso de admisión para el ciclo escolar Febrero-Julio 2026.
                
                **Requisitos:**
                - Bachillerato terminado o equivalente
                - Promedio mínimo de 8.0
                - Aprobar examen de admisión
                - Presentar documentación completa
                
                **Fechas importantes:**
                - Registro: hasta 15 de enero 2026
                - Examen: 25 de enero 2026
                - Resultados: 5 de febrero 2026
                """)
            
            convocatoria_unam = st.checkbox(
                "**He leído y acepto los términos de la Convocatoria UNAM Febrero 2026 ***",
                help="Convocatoria oficial para el proceso de admisión Febrero 2026",
                key="convocatoria_checkbox"
            )
        
        return {
            "aviso_privacidad": aviso_privacidad,
            "convocatoria_unam": convocatoria_unam
        }
    
    def _mostrar_paso_examen_psicometrico(self):
        with st.expander("🧠 Examen Psicométrico (Opcional)", expanded=False):
            realizar_examen = st.checkbox("Realizar Examen Psicométrico en Línea", 
                                         help="Examen rápido para evaluación de aptitudes",
                                         key="examen_checkbox")
            
            resultado_psicometrico = None
            if realizar_examen:
                col_apt1, col_apt2 = st.columns(2)
                
                with col_apt1:
                    aptitud_1 = st.slider("Capacidad de trabajo bajo presión", 1, 10, 5, key="aptitud1_slider")
                    aptitud_2 = st.slider("Habilidades de comunicación", 1, 10, 5, key="aptitud2_slider")
                
                with col_apt2:
                    aptitud_3 = st.slider("Empatía con pacientes", 1, 10, 5, key="aptitud3_slider")
                    aptitud_4 = st.slider("Capacidad de aprendizaje rápido", 1, 10, 5, key="aptitud4_slider")
                
                aptitud_general = (aptitud_1 + aptitud_2 + aptitud_3 + aptitud_4) / 4
                
                resultado_psicometrico = {
                    'resultado': f"Aptitud General: {aptitud_general:.1f}/10",
                    'aptitudes': f"Presión: {aptitud_1}/10, Comunicación: {aptitud_2}/10, Empatía: {aptitud_3}/10, Aprendizaje: {aptitud_4}/10",
                    'recomendaciones': "Adecuado para programas de salud" if aptitud_general >= 6 else "Se recomienda evaluación adicional"
                }
                
                st.info(f"**Resultado preliminar:** {aptitud_general:.1f}/10")
        
        return resultado_psicometrico
    
    def _procesar_envio_corregido(self, programa, datos, documentos, estudio, aceptaciones, examen):
        """VERSIÓN CORREGIDA - Manejo correcto de contador de documentos"""
        errores = []
        
        # Mostrar diagnóstico de documentos antes de validar
        with st.expander("🔍 **VALIDACIÓN DE DOCUMENTOS**", expanded=True):
            st.write(f"**Tipo de programa:** {programa['tipo_programa']}")
            st.write(f"**Documentos requeridos:** {documentos.get('minimo_requerido', '?')}")
            
            # Usar la lista de archivos del estado de sesión - CORRECCIÓN CLAVE
            archivos_subidos_info = st.session_state.archivos_subidos_info
            st.write(f"**Documentos en session_state 'archivos_subidos_info':** {len(archivos_subidos_info)}")
            
            # Mostrar detalles de archivos
            if archivos_subidos_info:
                st.write("**Detalles de archivos:**")
                for i, archivo_info in enumerate(archivos_subidos_info, 1):
                    if 'archivo' in archivo_info and archivo_info['archivo'] is not None:
                        st.write(f"{i}. {archivo_info['nombre_documento']}: {archivo_info['archivo'].name} ({archivo_info['archivo'].size:,} bytes)")
                    else:
                        st.write(f"{i}. {archivo_info['nombre_documento']}: ARCHIVO NO VÁLIDO")
        
        campos_obligatorios = [
            (datos["nombre"], "Nombre completo"),
            (datos["email"], "Correo electrónico personal"),
            (datos["email_gmail"], "Correo Gmail"),
            (datos["telefono"], "Teléfono"),
            (programa["programa"], "Programa de interés"),
            (aceptaciones["aviso_privacidad"], "Aviso de privacidad"),
            (aceptaciones["convocatoria_unam"], "Convocatoria UNAM")
        ]
        
        errores.extend(self.validador.validar_campos_obligatorios(campos_obligatorios))
        
        if datos["email"] and not self.validador.validar_email(datos["email"]):
            errores.append("❌ Formato de correo electrónico personal inválido")
        
        if datos["email_gmail"] and not self.validador.validar_email_gmail(datos["email_gmail"]):
            errores.append("❌ El correo Gmail debe ser de dominio @gmail.com")
        
        if datos["telefono"] and not self.validador.validar_telefono(datos["telefono"]):
            errores.append("❌ Teléfono debe tener al menos 10 dígitos")
        
        # Validar documentos - CORRECCIÓN: Usar archivos_subidos_info del session_state
        documentos_requeridos = documentos.get("minimo_requerido", 11)
        
        # CONTAR DOCUMENTOS VÁLIDOS (ARCHIVOS REALES)
        documentos_validos = []
        for doc_info in archivos_subidos_info:
            if 'archivo' in doc_info and doc_info['archivo'] is not None:
                # Verificar que el archivo sea un objeto válido de Streamlit
                if hasattr(doc_info['archivo'], 'name') and hasattr(doc_info['archivo'], 'size'):
                    if doc_info['archivo'].size > 0:
                        documentos_validos.append(doc_info)
        
        documentos_count = len(documentos_validos)
        
        # Mostrar diagnóstico de validación
        with st.expander("🔍 **DIAGNÓSTICO DE VALIDACIÓN**", expanded=True):
            st.write(f"**Documentos en session_state:** {len(archivos_subidos_info)}")
            st.write(f"**Documentos válidos (con archivo):** {documentos_count}")
            st.write(f"**Documentos requeridos:** {documentos_requeridos}")
            
            if documentos_count < documentos_requeridos:
                st.error(f"❌ FALTAN DOCUMENTOS: {documentos_count} de {documentos_requeridos}")
        
        if documentos_count < documentos_requeridos:
            errores.append(f"❌ Se requieren TODOS los {documentos_requeridos} documentos para {programa['tipo_programa']}. Subiste {documentos_count} documentos válidos.")
        
        if programa["tipo_programa"] == "ESPECIALIDAD" and not datos.get("licenciatura_origen"):
            errores.append("❌ Licenciatura de origen es obligatoria para especialidades")
        
        if errores:
            for error in errores:
                st.error(error)
            return
        
        with st.spinner("🔄 Procesando tu solicitud completa..."):
            try:
                # Crear backup antes de la operación
                backup_info = f"Agregar inscrito: {datos['nombre']}"
                backup_path = self.backup_system.crear_backup("AGREGAR_INSCRITO_COMPLETO", backup_info)
                
                if backup_path:
                    logger.info(f"✅ Backup creado antes de operación: {os.path.basename(backup_path)}")
                
                # Subir archivos directamente al servidor remoto
                archivos_subidos = []
                documentos_subidos_nombres = []
                
                # Usar SOLO documentos válidos
                for archivo_info in documentos_validos:
                    archivo_subido = self.gestor_archivos.subir_documento_remoto(
                        archivo_info['archivo'],
                        archivo_info['nombre_documento'],
                        datos['matricula_generada']
                    )
                    if archivo_subido:
                        archivos_subidos.append(archivo_subido)
                        documentos_subidos_nombres.append(archivo_info['nombre_documento'])
                
                datos_completos = {
                    'matricula': datos['matricula_generada'],
                    'nombre_completo': datos['nombre'],
                    'email': datos['email'],
                    'email_gmail': datos['email_gmail'],
                    'telefono': datos['telefono'],
                    'tipo_programa': programa['tipo_programa'],
                    'categoria_academica': programa['categoria'],
                    'programa_interes': programa['programa'],
                    'estado_civil': datos.get('estado_civil', ''),
                    'edad': datos.get('edad'),
                    'domicilio': datos.get('domicilio', ''),
                    'licenciatura_origen': datos.get('licenciatura_origen', ''),
                    'matricula_unam': datos.get('matricula_unam', ''),
                    'acepto_privacidad': aceptaciones['aviso_privacidad'],
                    'acepto_convocatoria': aceptaciones['convocatoria_unam'],
                    'estudio_socioeconomico': 'Completado' if any(estudio.values()) else 'No realizado',
                    'estudio_socioeconomico_detallado': estudio,
                    'resultado_psicometrico': examen,
                    'archivos_subidos': archivos_subidos
                }
                
                datos_completos['documentos_subidos'] = len(archivos_subidos)
                datos_completos['documentos_guardados'] = ', '.join(documentos_subidos_nombres) if documentos_subidos_nombres else ''
                
                inscrito_id, folio_unico = self.base_datos.agregar_inscrito_completo(datos_completos)
                
                if inscrito_id:
                    if self.base_datos.sincronizar_hacia_remoto():
                        st.session_state.formulario_enviado = True
                        st.session_state.datos_exitosos = {
                            'folio': folio_unico,
                            'matricula': datos_completos['matricula'],
                            'nombre': datos['nombre'],
                            'email': datos['email'],
                            'email_gmail': datos['email_gmail'],
                            'programa': programa['programa'],
                            'tipo_programa': programa['tipo_programa'],
                            'categoria': programa['categoria'],
                            'duracion': programa.get('duracion', ''),
                            'modalidad': programa.get('modalidad', ''),
                            'documentos': len(archivos_subidos),
                            'documentos_requeridos': documentos_requeridos,
                            'estudio_socioeconomico': 'Sí' if any(estudio.values()) else 'No',
                            'examen_psicometrico': 'Sí' if examen else 'No',
                            'archivos_subidos': len(archivos_subidos),
                            'carpeta_documentos': f"{gestor_remoto.uploads_inscritos_remoto}/{datos['matricula_generada']}/"
                        }
                        
                        correo_enviado = False
                        mensaje_correo = "Sistema de correos no configurado"
                        
                        if self.sistema_correos.correos_habilitados:
                            correo_enviado, mensaje_correo = self.sistema_correos.enviar_correo_confirmacion_completo(
                                datos['email_gmail'],
                                datos['nombre'],
                                datos_completos['matricula'],
                                folio_unico,
                                programa['programa'],
                                programa['tipo_programa']
                            )
                        
                        st.session_state.datos_exitosos['correo_enviado'] = correo_enviado
                        st.session_state.datos_exitosos['mensaje_correo'] = mensaje_correo
                        
                        # Limpiar estado de archivos
                        st.session_state.archivos_subidos_info = []
                        
                        # Limpiar estado del formulario
                        st.session_state.formulario_estado = {
                            'programa_seleccionado': None,
                            'programa_info': None,
                            'matricula_generada': None,
                            'documentos_subidos': [],
                            'contador_documentos': 0
                        }
                        
                        st.rerun()
                    else:
                        st.error("❌ Error al sincronizar con el servidor remoto")
                else:
                    st.error("❌ Error al guardar en la base de datos")
                
            except ValueError as e:
                st.error(f"❌ Error de validación: {str(e)}")
            except Exception as e:
                st.error(f"❌ Error en el registro: {str(e)}")
                logger.error(f"Error registrando inscripción completa: {e}", exc_info=True)
    
    def _mostrar_resultado_exitoso(self):
        datos = st.session_state.datos_exitosos
        
        st.success("🎉 **¡PRE-INSCRIPCIÓN COMPLETADA EXITOSAMENTE!**")
        st.balloons()
        
        col_res1, col_res2 = st.columns(2)
        
        with col_res1:
            st.info(f"**📋 Folio Único (ANÓNIMO):**\n\n**{datos['folio']}**")
            st.info(f"**🎓 Matrícula:**\n\n{datos['matricula']}")
            st.info(f"**👤 Nombre:**\n\n{datos['nombre']}")
            st.info(f"**📧 Correo Gmail:**\n\n{datos['email_gmail']}")
        
        with col_res2:
            st.info(f"**🎯 Programa:**\n\n{datos['programa']}")
            st.info(f"**📄 Categoría:**\n\n{datos['categoria']}")
            st.info(f"**📎 Documentos subidos:**\n\n{datos['documentos']} de {datos.get('documentos_requeridos', '?')}")
            st.info(f"**🏫 Modalidad:**\n\n{datos.get('modalidad', 'No especificada')}")
        
        # Información sobre la carpeta de documentos en el servidor remoto
        if 'carpeta_documentos' in datos:
            st.info(f"**📁 Carpeta de documentos en servidor remoto:**\n\n`{datos['carpeta_documentos']}`")
        
        st.markdown(f"""
        <div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #ffc107; margin: 15px 0;">
        <h4 style="color: #856404; margin-top: 0;">⚠️ **INFORMACIÓN CRÍTICA - LEA CON ATENCIÓN**</h4>
        
        **TU FOLIO ÚNICO ES: `{datos['folio']}`**
        
        1. **🔒 Confidencialidad:** Los resultados se publicarán **ÚNICAMENTE CON ESTE FOLIO**
        2. **📋 Anonimato:** No se mostrarán nombres completos en la publicación de resultados
        3. **💾 Guarda este folio:** Es tu identificador único para consultar resultados
        4. **📧 Verificación:** Recibirás un correo de confirmación en {datos['email_gmail']}
        5. **📄 Documentos subidos:** Has subido {datos['documentos']} de {datos.get('documentos_requeridos', '?')} documento(s) **DIRECTAMENTE AL SERVIDOR REMOTO**
        6. **🌐 Acceso remoto:** Tus documentos están almacenados en el servidor seguro
        
        **Fecha límite para completar documentos:** {(datetime.now() + timedelta(days=14)).strftime('%d/%m/%Y')}
        </div>
        """, unsafe_allow_html=True)
        
        if datos.get('correo_enviado'):
            st.success("📧 **Se ha enviado un correo de confirmación detallado a tu dirección de Gmail.**")
        else:
            st.warning(f"⚠️ **No se pudo enviar el correo de confirmación:** {datos.get('mensaje_correo', 'Razón desconocida')}")
        
        if st.button("📝 Realizar otra pre-inscripción", type="primary", use_container_width=True):
            # Limpiar el estado del formulario
            st.session_state.formulario_enviado = False
            st.session_state.datos_exitosos = None
            st.session_state.formulario_estado = {
                'programa_seleccionado': None,
                'programa_info': None,
                'matricula_generada': None,
                'documentos_subidos': [],
                'contador_documentos': 0
            }
            st.session_state.archivos_subidos_info = []
            st.rerun()

# ============================================================================
# CAPA 13: PÁGINAS/VISTAS PRINCIPALES
# ============================================================================

class PaginaInscripcion:
    """Página para nueva pre-inscripción"""

    def __init__(self):
        self.sistema_inscritos = SistemaInscritosCompleto()

    def mostrar(self):
        """Mostrar formulario de pre-inscripción"""
        self.sistema_inscritos.mostrar_formulario_completo_interactivo()


class PaginaPrincipal:
    """Página principal del sistema"""
    
    @staticmethod
    def mostrar():
        ComponentesUI.mostrar_header(
            "🏥 Sistema Completo de Pre-Inscripción",
            f"Versión {APP_CONFIG['version']} - Convocatoria Febrero 2026"
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            #### ✅ **PROCESO DE PRE-INSCRIPCIÓN**
            
            1. **Documentos por tipo de programa**
            2. **Documentación específica** 
            3. **Convocatoria Feb 2026**
            4. **Formulario ampliado**
            5. **Estudio socioeconómico**
            6. **Correo Gmail obligatorio**
            7. **Notificación por correo**
            8. **Folio único anónimo**
            9. **Aviso de privacidad**
            10. **Recordatorio días restantes**
            11. **Eliminar duplicidad**
            12. **Desechar preinscripciones incompletas**
            13. **Convocatoria UNAM con aceptación**
            14. **Examen psicométrico en línea**
            15. **Trípticos informativos**
            """)
        
        with col2:
            # CORREGIR ESTA SECCIÓN:
            ssh_conectado = "✅ Sí" if estado_sistema.estado.get('ssh_conectado', False) else "❌ No"
            archivos_remotos = estado_sistema.estado.get('archivos_subidos_remoto', 0)
            backups = estado_sistema.estado.get('backups_realizados', 0)
            
            st.markdown(f"""
            #### 🌐 **TRABAJO REMOTO COMPLETO**
            
            16. **Base de datos en servidor remoto**
            17. **Archivos subidos directamente al servidor**
            18. **Sincronización automática**
            19. **Backup automático remoto**
            20. **Conexión SSH permanente**
            21. **Gestión centralizada**
            22. **Acceso desde cualquier lugar**
            23. **Seguridad mejorada**
            24. **Rendimiento optimizado**
            
            ---
            
            **🔗 Conexión SSH:** {ssh_conectado}
            **📁 Archivos remotos:** {archivos_remotos}
            **💾 Backups:** {backups}
            """)
        
        st.markdown("---")


class PaginaConsulta:
    """Página de consulta de inscritos - CON MANEJO DE ERRORES MEJORADO"""
    
    @staticmethod
    def mostrar():
        ComponentesUI.mostrar_header("📋 Consulta de Inscritos")
        
        try:
            with st.spinner("🔄 Sincronizando con servidor remoto..."):
                if db_completa.sincronizar_desde_remoto():
                    st.success("✅ Base de datos sincronizada desde servidor remoto")
                else:
                    st.warning("⚠️ No se pudo sincronizar completamente")
            
            inscritos = db_completa.obtener_inscritos()
            total_inscritos = len(inscritos)
            
            st.metric("Total de Inscritos", total_inscritos)
            
            if total_inscritos > 0:
                datos_tabla = []
                for inscrito in inscritos:
                    datos_tabla.append({
                        'Folio Único': inscrito['folio_unico'],
                        'Matrícula': inscrito['matricula'],
                        'Nombre': inscrito['nombre_completo'],
                        'Programa': inscrito['programa_interes'],
                        'Tipo': inscrito['tipo_programa'],
                        'Categoría': inscrito['categoria_academica'],
                        'Fecha Registro': inscrito['fecha_registro'][:10] if isinstance(inscrito['fecha_registro'], str) else inscrito['fecha_registro'].strftime('%Y-%m-%d'),
                        'Documentos': inscrito['documentos_subidos'],
                        'Completado': '✅' if inscrito['completado'] else '⚠️'
                    })
                
                df = pd.DataFrame(datos_tabla)
                
                st.subheader("🔍 Búsqueda de Inscritos")
                search_term = st.text_input("Buscar por folio, matrícula o nombre:")
                
                if search_term:
                    df = df[df.apply(lambda row: row.astype(str).str.contains(search_term, case=False).any(), axis=1)]
                
                if not df.empty:
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    
                    st.subheader("📊 Exportar Datos")
                    col_exp1, col_exp2 = st.columns(2)
                    
                    with col_exp1:
                        # Intentar exportar a Excel si openpyxl está disponible
                        try:
                            import openpyxl
                            # Crear Excel en memoria
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                df.to_excel(writer, sheet_name='Inscritos', index=False)
                            output.seek(0)
                            
                            st.download_button(
                                label="📥 Descargar Excel",
                                data=output,
                                file_name=f"inscritos_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        except ImportError:
                            st.warning("⚠️ Para exportar a Excel, instala: `pip install openpyxl`")
                        except Exception as e:
                            st.error(f"❌ Error al crear Excel: {e}")
                    
                    with col_exp2:
                        # Crear CSV en memoria (siempre funciona)
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 Descargar CSV",
                            data=csv,
                            file_name=f"inscritos_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )
                else:
                    st.info("ℹ️ No hay inscritos registrados o no hay coincidencias con la búsqueda")
            else:
                st.info("ℹ️ No hay inscritos registrados")
            
        except Exception as e:
            st.error(f"❌ Error cargando inscritos: {e}")
            
            # Información de diagnóstico más detallada
            with st.expander("🔍 Información de diagnóstico"):
                st.write(f"**Tipo de error:** {type(e).__name__}")
                st.write(f"**Mensaje:** {str(e)}")
                
                # Instrucciones para solucionar
                if "openpyxl" in str(e).lower():
                    st.markdown("""
                    **Solución:** Instala openpyxl con:
                    ```bash
                    pip install openpyxl
                    ```
                    """)

class PaginaConfiguracion:
    """Página de configuración del sistema"""
    
    @staticmethod
    def mostrar():
        ComponentesUI.mostrar_header("⚙️ Configuración del Sistema")
        
        with st.expander("🔗 Estado de Conexión Remota", expanded=True):
            col_conf1, col_conf2 = st.columns(2)
            
            with col_conf1:
                if estado_sistema.esta_inicializada():
                    st.success("✅ Base de Datos Inicializada")
                    fecha = estado_sistema.obtener_fecha_inicializacion()
                    if fecha:
                        st.caption(f"Fecha: {fecha.strftime('%Y-%m-%d %H:%M')}")
                else:
                    st.error("❌ Base de Datos No Inicializada")
            
            with col_conf2:
                if estado_sistema.estado.get('ssh_conectado'):
                    st.success("✅ SSH Conectado")
                    if gestor_remoto.config.get('host'):
                        st.caption(f"Servidor: {gestor_remoto.config['host']}")
                else:
                    st.error("❌ SSH Desconectado")
            
            if st.button("🔗 Probar Conexión SSH", use_container_width=True):
                with st.spinner("Probando conexión..."):
                    if gestor_remoto.verificar_conexion_ssh():
                        st.success("✅ Conexión SSH exitosa")
                        st.rerun()
                    else:
                        st.error("❌ Conexión SSH fallida")
        
        with st.expander("🌐 Gestión de Archivos Remotos", expanded=True):
            st.info("Los archivos se suben directamente al servidor remoto:")
            st.caption(f"📁 Ruta base: {gestor_remoto.uploads_path_remoto}")
            st.caption(f"📁 Ruta inscritos: {gestor_remoto.uploads_inscritos_remoto}")
            
            if st.button("🔄 Crear/Verificar Directorios Remotos", use_container_width=True):
                with st.spinner("Creando/verificando estructura de directorios..."):
                    if gestor_remoto.crear_estructura_directorios_remota():
                        st.success("✅ Estructura de directorios remota verificada/creada")
                        st.rerun()
                    else:
                        st.error("❌ Error creando estructura de directorios remota")
        
        with st.expander("🔄 Mantenimiento del Sistema", expanded=True):
            col_mant1, col_mant2 = st.columns(2)
            
            with col_mant1:
                if st.button("🧹 Limpiar Registros Incompletos", use_container_width=True):
                    with st.spinner("Limpiando registros incompletos..."):
                        eliminados = db_completa.limpiar_registros_incompletos()
                        if eliminados > 0:
                            st.success(f"✅ Eliminados {eliminados} registros incompletos")
                            st.rerun()
                        else:
                            st.info("ℹ️ No se encontraron registros incompletos para eliminar")
            
            with col_mant2:
                if st.button("📧 Enviar Recordatorios Automáticos", use_container_width=True):
                    with st.spinner("Enviando recordatorios..."):
                        try:
                            # Enviar recordatorios a todos los inscritos
                            inscritos = db_completa.obtener_inscritos()
                            enviados = 0
                            for inscrito in inscritos:
                                if db_completa.enviar_recordatorio(inscrito['id']):
                                    enviados += 1
                            
                            if enviados > 0:
                                st.success(f"✅ {enviados} recordatorios enviados")
                            else:
                                st.info("ℹ️ No hay recordatorios pendientes por enviar")
                        except Exception as e:
                            st.error(f"❌ Error enviando recordatorios: {e}")

class PaginaReportes:
    """Página de reportes y backups"""
    
    @staticmethod
    def mostrar():
        ComponentesUI.mostrar_header("📊 Reportes y Sistema de Backups")
        
        st.subheader("📈 Estadísticas del Sistema")
        
        col_rep1, col_rep2, col_rep3, col_rep4 = st.columns(4)
        
        with col_rep1:
            total_inscritos = estado_sistema.estado.get('total_inscritos', 0)
            st.metric("Total Inscritos", total_inscritos)
        
        with col_rep2:
            recordatorios = estado_sistema.estado.get('recordatorios_enviados', 0)
            st.metric("Recordatorios", recordatorios)
        
        with col_rep3:
            duplicados = estado_sistema.estado.get('duplicados_eliminados', 0)
            st.metric("Duplicados Eliminados", duplicados)
        
        with col_rep4:
            archivos_remotos = estado_sistema.estado.get('archivos_subidos_remoto', 0)
            st.metric("Archivos Remotos", archivos_remotos)
        
        backup_system = SistemaBackupAutomatico(gestor_remoto)
        backups = backup_system.listar_backups()
        
        st.markdown("---")
        st.subheader("💾 Sistema de Backups")
        
        if backups:
            st.success(f"✅ {len(backups)} backups disponibles")
            
            backup_data = []
            for backup in backups:
                backup_data.append({
                    'Nombre': backup['nombre'],
                    'Tamaño': f"{backup['tamaño']:,} bytes",
                    'Fecha': backup['fecha'].strftime('%Y-%m-%d %H:%M'),
                })
            
            df_backups = pd.DataFrame(backup_data)
            st.dataframe(df_backups, use_container_width=True, hide_index=True)
            
            # Botón para crear nuevo backup
            col_back1, col_back2 = st.columns(2)
            
            with col_back1:
                if st.button("💾 Crear Nuevo Backup", use_container_width=True, type="primary"):
                    with st.spinner("Creando backup..."):
                        backup_path = backup_system.crear_backup(
                            "REPORTE_MENSUAL",
                            "Backup mensual del sistema remoto"
                        )
                        if backup_path:
                            st.success(f"✅ Backup creado exitosamente: {os.path.basename(backup_path)}")
                            st.rerun()
            
            with col_back2:
                # Botón para descargar backup seleccionado
                if backups:
                    backup_seleccionado = st.selectbox("Seleccionar backup para descargar:", 
                                                      [b['nombre'] for b in backups])
                    
                    if backup_seleccionado:
                        backup_info = next((b for b in backups if b['nombre'] == backup_seleccionado), None)
                        if backup_info:
                            with open(backup_info['ruta'], 'rb') as f:
                                backup_bytes = f.read()
                            
                            st.download_button(
                                label="📥 Descargar Backup Seleccionado",
                                data=backup_bytes,
                                file_name=backup_info['nombre'],
                                mime="application/zip"
                            )
        else:
            st.info("ℹ️ No hay backups disponibles. Crea el primer backup.")
            
            if st.button("💾 Crear Primer Backup", use_container_width=True, type="primary"):
                with st.spinner("Creando primer backup..."):
                    backup_path = backup_system.crear_backup(
                        "PRIMER_BACKUP",
                        "Primer backup del sistema remoto"
                    )
                    if backup_path:
                        st.success(f"✅ Backup creado exitosamente: {os.path.basename(backup_path)}")
                        st.rerun()

# ============================================================================
# CAPA 14: CONTROLADOR PRINCIPAL
# ============================================================================

class ControladorPrincipal:
    """Controlador principal de la aplicación"""
    
    def __init__(self):
        self.sistema_auth = SistemaAutenticacion()
        
        # Inicializar páginas
        self.paginas = {
            "inicio": PaginaPrincipal(),
            "inscripcion": PaginaInscripcion(),
            "consulta": PaginaConsulta(),
            "configuracion": PaginaConfiguracion(),
            "reportes": PaginaReportes(),
            "login": self.sistema_auth
        }
        
        # Mapeo de menú simplificado
        self.mapeo_menu_autenticado = {
            "🏠 Inicio y Resumen": "inicio",
            "📝 Nueva Pre-Inscripción": "inscripcion",
            "📋 Consultar Inscritos": "consulta",
            "⚙️ Configuración": "configuracion",
            "📊 Reportes y Backups": "reportes"
        }
        
        self.mapeo_menu_no_autenticado = {
            "🏠 Inicio y Resumen": "inicio",
            "📝 Nueva Pre-Inscripción": "inscripcion",
            "🔐 Acceso Administrativo": "login"
        }
        
        if 'pagina_actual' not in st.session_state:
            st.session_state.pagina_actual = "inicio"
    
    def configurar_aplicacion(self):
        st.set_page_config(
            page_title=APP_CONFIG['page_title'],
            page_icon=APP_CONFIG['page_icon'],
            layout=APP_CONFIG['layout'],
            initial_sidebar_state=APP_CONFIG['sidebar_state']
        )
    
    def ejecutar(self):
        self.configurar_aplicacion()
        
        # Determinar qué mapeo de menú usar
        if self.sistema_auth and st.session_state.autenticado:
            mapeo_menu = self.mapeo_menu_autenticado
        else:
            mapeo_menu = self.mapeo_menu_no_autenticado
        
        # Obtener selección del sidebar
        seleccion_menu = ComponentesUI.crear_sidebar(self.sistema_auth)
        
        # Obtener página seleccionada
        pagina_seleccionada = mapeo_menu.get(seleccion_menu, "inicio")
        
        # Verificar autenticación para páginas administrativas
        if pagina_seleccionada in ["consulta", "configuracion", "reportes"]:
            if not self.sistema_auth.verificar_autenticacion(rol_requerido="admin"):
                # Redirigir a login si no está autenticado
                pagina_seleccionada = "login"
        
        # Actualizar página actual si cambió
        if pagina_seleccionada != st.session_state.pagina_actual:
            st.session_state.pagina_actual = pagina_seleccionada
        
        try:
            # Mostrar página seleccionada
            pagina = self.paginas[st.session_state.pagina_actual]
            
            if st.session_state.pagina_actual == "login":
                pagina.mostrar_login()
            else:
                pagina.mostrar()
                
        except KeyError:
            st.error("Página no encontrada")
            self.paginas["inicio"].mostrar()

# ============================================================================
# CAPA 15: PUNTO DE ENTRADA PRINCIPAL
# ============================================================================

def main():
    """Función principal de la aplicación"""
    
    try:
        controlador = ControladorPrincipal()
        
        # Mostrar encabezado
        st.markdown(f"""
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 10px; margin-bottom: 20px; 
                    border-left: 5px solid #2E86AB;">
            <h3 style="margin: 0; color: #2E86AB;">🏥 Sistema de Pre-Inscripción (REMOTO)</h3>
            <p style="margin: 5px 0; color: #666;">Escuela de Enfermería - Versión {APP_CONFIG['version']}</p>
            <p style="margin: 0; font-size: 0.9em; color: #888;">
                🌐 Trabajo 100% en Servidor Remoto | 📁 Archivos Directos al SSH | 🔄 Sincronización Automática
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Ejecutar controlador principal
        controlador.ejecutar()
        
    except Exception as e:
        st.error(f"❌ Error crítico en la aplicación: {e}")
        logger.critical(f"Error crítico en sistema: {e}", exc_info=True)
        
        with st.expander("🚨 Información de diagnóstico"):
            st.write("**Traceback completo:**")
            st.code(traceback.format_exc())

# ============================================================================
# EJECUCIÓN
# ============================================================================

if __name__ == "__main__":
    main()
