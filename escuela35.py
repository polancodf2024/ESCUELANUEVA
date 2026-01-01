"""
escuela30_remoto.py - Sistema Escuela Enfermería 100% REMOTO
Versión modificada para trabajar EXCLUSIVAMENTE con servidor remoto
Mismo modelo que aspirantes35.py - Sin archivos locales temporales
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
        
        file_handler = logging.FileHandler('escuela_detallado.log', encoding='utf-8')
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
    
    def log_operation(self, operation, status, details):
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'operation': operation,
            'status': status,
            'details': details
        }
        
        log_file = 'system_operations.json'
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    logs = json.load(f)
            else:
                logs = []
            
            logs.append(log_entry)
            
            with open(log_file, 'w') as f:
                json.dump(logs, f, indent=2, default=str)
        except Exception as e:
            self.error(f"Error guardando log de operación: {e}")

logger = EnhancedLogger()

# =============================================================================
# 1.2 CONFIGURACIÓN DE PÁGINA
# =============================================================================

st.set_page_config(
    page_title="Sistema Escuela Enfermería - 100% REMOTO",
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
                "descripcion": "Formación integral en enfermería con enfoque en cardiología.",
                "requisitos": ["Bachillerato terminado", "Promedio mínimo 8.0"],
                "categoria": "licenciatura"
            }
        ],
        "ESPECIALIDAD": [
            {
                "nombre": "Especialidad en Enfermería Cardiovascular",
                "duracion": "2 años",
                "modalidad": "Presencial",
                "descripcion": "Formación especializada en el cuidado de pacientes con patologías cardiovasculares.",
                "requisitos": ["Licenciatura en Enfermería", "Cédula profesional", "2 años de experiencia"],
                "categoria": "posgrado"
            }
        ],
        "MAESTRIA": [
            {
                "nombre": "Maestría en Ciencias Cardiológicas",
                "duracion": "2 años",
                "modalidad": "Presencial",
                "descripcion": "Formación de investigadores en el área de ciencias cardiológicas.",
                "requisitos": ["Licenciatura en áreas afines", "Promedio mínimo 8.5"],
                "categoria": "posgrado"
            }
        ],
        "DIPLOMADO": [
            {
                "nombre": "Diplomado de Cardiología Básica",
                "duracion": "6 meses",
                "modalidad": "Híbrida",
                "descripcion": "Actualización en fundamentos de cardiología para profesionales de la salud.",
                "requisitos": ["Título profesional en área de la salud"],
                "categoria": "educacion_continua"
            }
        ],
        "CURSO": [
            {
                "nombre": "Curso de RCP Avanzado",
                "duracion": "40 horas",
                "modalidad": "Presencial",
                "descripcion": "Certificación en Reanimación Cardiopulmonar Avanzada.",
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
        "Acta nacimiento (≤ 3 meses)",
        "CURP (≤ 1 mes)",
        "Cartilla Nacional de Salud",
        "INE del tutor",
        "Comprobante domicilio (≤ 3 meses)",
        "Certificado médico institucional (≤ 1 mes)",
        "12 fotografías infantiles B/N"
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
# 1.4 FUNCIÓN PARA LEER SECRETS.TOML - VERSIÓN 100% REMOTO
# =============================================================================

def cargar_configuracion_secrets():
    """Cargar configuración desde secrets.toml - VERSIÓN 100% REMOTO"""
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
# 1.7 ARCHIVO DE ESTADO PERSISTENTE - MODIFICADO PARA 100% REMOTO
# =============================================================================

class EstadoPersistente:
    """Maneja el estado persistente para el sistema 100% REMOTO"""
    
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
        """Estado por defecto - 100% REMOTO"""
        return {
            'db_inicializada': False,
            'fecha_inicializacion': None,
            'ultima_sincronizacion': None,
            'modo_operacion': '100%_remoto',
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
            'salones_reservados': [],
            'minutas_generadas': 0,
            'cartas_compromiso': 0,
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
    
    def marcar_sincronizacion(self):
        """Marcar última sincronización"""
        self.estado['ultima_sincronizacion'] = datetime.now().isoformat()
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
    
    def registrar_salon_reservado(self, salon, fecha, hora):
        """Registrar reserva de salón"""
        reserva = {
            'salon': salon,
            'fecha': fecha,
            'hora': hora,
            'timestamp': datetime.now().isoformat()
        }
        
        if 'salones_reservados' not in self.estado:
            self.estado['salones_reservados'] = []
        
        self.estado['salones_reservados'].append(reserva)
        self.guardar_estado()
    
    def registrar_minuta(self):
        """Registrar minuta generada"""
        self.estado['minutas_generadas'] = self.estado.get('minutas_generadas', 0) + 1
        self.guardar_estado()
    
    def registrar_carta_compromiso(self):
        """Registrar carta compromiso generada"""
        self.estado['cartas_compromiso'] = self.estado.get('cartas_compromiso', 0) + 1
        self.guardar_estado()
    
    def registrar_recordatorio(self):
        """Registrar envío de recordatorio"""
        self.estado['recordatorios_enviados'] = self.estado.get('recordatorios_enviados', 0) + 1
        self.guardar_estado()
    
    def registrar_duplicado_eliminado(self):
        """Registrar duplicado eliminado"""
        self.estado['duplicados_eliminados'] = self.estado.get('duplicados_eliminados', 0) + 1
        self.guardar_estado()
    
    def registrar_registro_incompleto_eliminado(self, cantidad=1):
        """Registrar registros incompletos eliminados"""
        self.estado['registros_incompletos_eliminados'] = self.estado.get('registros_incompletos_eliminados', 0) + cantidad
        self.guardar_estado()
    
    def set_total_inscritos(self, total):
        """Establecer total de inscritos"""
        self.estado['total_inscritos'] = total
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

# =============================================================================
# 2. CAPA DE DATOS (MODELO) - 100% REMOTO
# =============================================================================

# =============================================================================
# 2.1 GESTOR DE CONEXIÓN REMOTA VIA SSH - 100% REMOTO
# =============================================================================

class GestorConexionRemota:
    """Gestor de conexión SSH al servidor remoto - 100% REMOTO"""
    
    def __init__(self):
        self.ssh = None
        self.sftp = None
        self.conn_remota = None  # Conexión directa a DB remota
        
        logger.info("📋 Cargando configuración desde secrets.toml...")
        self.config_completa = cargar_configuracion_secrets()
        
        if not self.config_completa:
            logger.error("❌ No se pudo cargar configuración de secrets.toml")
            return
            
        self.config = self._cargar_configuracion_completa()
        
        self.config_sistema = self.config_completa.get('system', {})
        self.auto_connect = self.config_sistema.get('auto_connect', True)
        self.retry_attempts = self.config_sistema.get('retry_attempts', 3)
        self.retry_delay_base = self.config_sistema.get('retry_delay', 5)
        
        self.timeouts = {
            'ssh_connect': self.config_sistema.get('ssh_connect_timeout', 30),
            'ssh_command': self.config_sistema.get('ssh_command_timeout', 60),
            'sftp_transfer': self.config_sistema.get('sftp_transfer_timeout', 300),
            'db_operation': self.config_sistema.get('db_operation_timeout', 30)
        }
        
        if not self.config.get('host'):
            logger.warning("⚠️ No hay configuración SSH en secrets.toml")
            return
        
        self.db_path_remoto = self.config.get('remote_db_escuela')
        self.uploads_path_remoto = self.config.get('remote_uploads_path')
        
        logger.info(f"🔗 Configuración SSH cargada para {self.config.get('host', 'No configurado')}")
        
        if self.auto_connect and self.config.get('host'):
            self.probar_conexion_inicial()
    
    def _cargar_configuracion_completa(self):
        """Cargar toda la configuración necesaria - VERSIÓN 100% REMOTO"""
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
            
            # IMPORTANTE: SOLO RUTAS REMOTAS, SIN LOCALES
            paths_config = self.config_completa.get('paths', {})
            config.update({
                'remote_db_escuela': paths_config.get('remote_db_escuela', ''),
                'remote_uploads_path': paths_config.get('remote_uploads_path', ''),
                # NO hay rutas locales en versión 100% remota
            })
            
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
            
            logger.info("✅ Configuración 100% REMOTO cargada")
            
        except Exception as e:
            logger.error(f"❌ Error cargando configuración: {e}", exc_info=True)
        
        return config
    
    def _intento_conexion_con_backoff(self, attempt):
        """Calcular tiempo de espera con backoff exponencial"""
        wait_time = min(self.retry_delay_base * (2 ** attempt), 60)
        jitter = wait_time * 0.1 * np.random.random()
        return wait_time + jitter
    
    def probar_conexion_inicial(self):
        """Probar la conexión SSH al inicio"""
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
            
            # Probar acceso a base de datos remota
            stdin, stdout, stderr = ssh_test.exec_command(
                f"test -f '{self.db_path_remoto}' && echo 'EXISTS' || echo 'NOT_FOUND'",
                timeout=self.timeouts['ssh_command']
            )
            output = stdout.read().decode().strip()
            
            ssh_test.close()
            
            if output == 'EXISTS':
                logger.info(f"✅ Conexión SSH exitosa y DB encontrada: {self.config['host']}")
            else:
                logger.warning(f"✅ Conexión SSH exitosa pero DB no encontrada: {self.config['host']}")
            
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
        """Establecer conexión SSH con el servidor remoto"""
        try:
            if not self.config.get('host'):
                logger.error("No hay configuración SSH disponible")
                return False
                
            logger.info(f"🔗 Conectando SSH a {self.config['host']}:{self.config.get('port', 22)}...")
            
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            port = self.config.get('port', 22)
            timeout = self.timeouts['ssh_connect']
            
            temp_dir = tempfile.gettempdir()
            espacio_ok, espacio_mb = UtilidadesSistema.verificar_espacio_disco(temp_dir)
            if not espacio_ok:
                logger.warning(f"⚠️ Espacio en disco bajo: {espacio_mb:.1f} MB disponible en {temp_dir}")
            
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
        except paramiko.SSHException as ssh_exc:
            error_msg = f"Error SSH: {str(ssh_exc)}"
            logger.error(f"❌ {error_msg}")
            estado_sistema.set_ssh_conectado(False, error_msg)
            return False
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
        """Ejecutar comando en servidor remoto - NUEVO para 100% remoto"""
        try:
            if not self.ssh:
                if not self.conectar_ssh():
                    return None, None
            
            if timeout is None:
                timeout = self.timeouts['ssh_command']
            
            stdin, stdout, stderr = self.ssh.exec_command(comando, timeout=timeout)
            
            salida = stdout.read().decode('utf-8', errors='ignore').strip()
            error = stderr.read().decode('utf-8', errors='ignore').strip()
            
            return salida, error
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando comando remoto: {e}")
            return None, str(e)
    
    def ejecutar_sql_remoto(self, consulta_sql, parametros=None):
        """Ejecutar SQL directamente en servidor remoto - 100% REMOTO"""
        try:
            # Crear script SQL temporal en servidor
            temp_script = f"/tmp/sql_{int(time.time())}_{random.randint(1000, 9999)}.sql"
            resultado_temp = f"/tmp/result_{int(time.time())}_{random.randint(1000, 9999)}.json"
            
            # Crear script SQL
            script_content = f"""#!/bin/bash
cd "$(dirname "{self.db_path_remoto}")"
sqlite3 "{os.path.basename(self.db_path_remoto)}" << 'EOF'
.headers on
.mode json
{consulta_sql}
EOF
"""
            
            # Subir script al servidor
            with self.sftp.open(temp_script, 'w') as f:
                f.write(script_content)
            
            # Hacer ejecutable
            self.ssh.exec_command(f"chmod +x {temp_script}")
            
            # Ejecutar script
            stdin, stdout, stderr = self.ssh.exec_command(
                temp_script,
                timeout=self.timeouts['db_operation']
            )
            
            resultado = stdout.read().decode('utf-8', errors='ignore')
            error = stderr.read().decode('utf-8', errors='ignore')
            
            # Limpiar archivo temporal
            self.ssh.exec_command(f"rm -f {temp_script}")
            
            if error and "Error:" in error:
                logger.error(f"❌ Error SQL remoto: {error}")
                return None, error
            
            # Parsear resultado JSON
            try:
                if resultado.strip():
                    resultado_json = json.loads(resultado)
                    return resultado_json, None
                else:
                    return [], None
            except json.JSONDecodeError:
                logger.warning(f"⚠️ Resultado no JSON: {resultado[:100]}")
                return resultado, None
                
        except Exception as e:
            logger.error(f"❌ Error ejecutando SQL remoto: {e}", exc_info=True)
            return None, str(e)
    
    def ejecutar_sql_modificacion(self, consulta_sql):
        """Ejecutar SQL de modificación (INSERT, UPDATE, DELETE) - 100% REMOTO"""
        try:
            # Para modificaciones, usar método más simple
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
                logger.info(f"✅ Base de datos encontrada en servidor: {self.db_path_remoto}")
                return True
            else:
                logger.warning(f"⚠️ Base de datos NO encontrada en servidor: {self.db_path_remoto}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error verificando existencia DB: {e}")
            return False
    
    def crear_db_remota(self):
        """Crear base de datos en servidor remoto si no existe"""
        try:
            logger.info(f"📝 Creando base de datos remota: {self.db_path_remoto}")
            
            # Crear directorio si no existe
            remote_dir = os.path.dirname(self.db_path_remoto)
            comando_mkdir = f"mkdir -p '{remote_dir}'"
            salida_mkdir, error_mkdir = self.ejecutar_comando_remoto(comando_mkdir)
            
            if error_mkdir:
                logger.warning(f"⚠️ Error creando directorio: {error_mkdir}")
            
            # Crear archivo de base de datos vacío
            comando_touch = f"touch '{self.db_path_remoto}'"
            salida_touch, error_touch = self.ejecutar_comando_remoto(comando_touch)
            
            if error_touch:
                logger.error(f"❌ Error creando archivo DB: {error_touch}")
                return False
            
            logger.info(f"✅ Archivo de base de datos creado: {self.db_path_remoto}")
            
            # Inicializar estructura
            return self._inicializar_estructura_db_remota()
            
        except Exception as e:
            logger.error(f"❌ Error creando DB remota: {e}", exc_info=True)
            return False
    
    def _inicializar_estructura_db_remota(self):
        """Inicializar estructura de base de datos en servidor remoto"""
        try:
            logger.info("📝 Inicializando estructura COMPLETA en servidor remoto...")
            
            # Crear script de inicialización
            init_script = f"""
-- Crear tabla de usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    rol TEXT DEFAULT 'administrador',
    nombre_completo TEXT,
    email TEXT,
    matricula TEXT UNIQUE,
    activo INTEGER DEFAULT 1,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    categoria_academica TEXT,
    tipo_programa TEXT,
    acepto_privacidad INTEGER DEFAULT 0,
    acepto_convocatoria INTEGER DEFAULT 0
);

-- Crear tabla de inscritos
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
);

-- Crear tabla de estudiantes
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
    usuario TEXT,
    tipo_programa TEXT CHECK(tipo_programa IN ('Pregrado', 'Posgrado', 'Licenciatura', 'Educación Continua')),
    matricula_unam TEXT,
    promedio_general REAL DEFAULT 0.0,
    materias_cursadas INTEGER DEFAULT 0,
    materias_aprobadas INTEGER DEFAULT 0
);

-- Insertar usuario administrador por defecto
INSERT OR IGNORE INTO usuarios (usuario, password, rol, nombre_completo, email, matricula, activo)
VALUES ('admin', 'Admin123!', 'administrador', 'Administrador del Sistema', 'admin@escuela.edu.mx', 'ADMIN-001', 1);
"""
            
            # Ejecutar script de inicialización
            exito, resultado = self.ejecutar_sql_modificacion(init_script)
            
            if exito:
                logger.info("✅ Estructura de base de datos inicializada en servidor remoto")
                estado_sistema.marcar_db_inicializada()
                return True
            else:
                logger.error(f"❌ Error inicializando estructura: {resultado}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura DB remota: {e}", exc_info=True)
            return False
    
    def subir_archivo_remoto(self, archivo_local, ruta_remota):
        """Subir archivo directamente al servidor remoto - 100% REMOTO"""
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
    
    def crear_backup_remoto(self):
        """Crear backup de la base de datos en servidor remoto"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{self.db_path_remoto}.backup_{timestamp}"
            
            comando = f"cp '{self.db_path_remoto}' '{backup_path}'"
            salida, error = self.ejecutar_comando_remoto(comando)
            
            if error:
                logger.error(f"❌ Error creando backup remoto: {error}")
                return False
            
            logger.info(f"✅ Backup remoto creado: {backup_path}")
            estado_sistema.registrar_backup()
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en backup remoto: {e}")
            return False
    
    def verificar_conexion_ssh(self):
        """Verificar estado de conexión SSH"""
        return self.probar_conexion_inicial()

# =============================================================================
# 2.2 SISTEMA DE BASE DE DATOS SQLITE - 100% REMOTO
# =============================================================================

class SistemaBaseDatos:
    """Sistema de base de datos SQLite 100% REMOTO"""
    
    def __init__(self):
        self.gestor = gestor_remoto
        self.page_size = 50
        self.validador = ValidadorDatos()
        
        # No hay archivos locales en versión 100% remota
        self.db_local_temp = None
        self.ultima_sincronizacion = None
    
    def inicializar_db_remota(self):
        """Inicializar base de datos en servidor remoto"""
        try:
            with st.spinner("🔄 Inicializando base de datos remota..."):
                # Verificar si ya existe
                if self.gestor.verificar_existencia_db():
                    logger.info("✅ Base de datos ya existe en servidor")
                    estado_sistema.marcar_db_inicializada()
                    return True
                
                # Crear nueva base de datos
                if self.gestor.crear_db_remota():
                    st.success("✅ Base de datos remota creada e inicializada")
                    return True
                else:
                    st.error("❌ Error creando base de datos remota")
                    return False
        except Exception as e:
            logger.error(f"❌ Error inicializando DB remota: {e}")
            st.error(f"❌ Error: {str(e)}")
            return False
    
    def ejecutar_consulta_remota(self, consulta_sql, parametros=None):
        """Ejecutar consulta SQL en servidor remoto"""
        try:
            if parametros:
                # Convertir consulta con parámetros
                consulta = consulta_sql
                for i, param in enumerate(parametros):
                    if isinstance(param, str):
                        param = param.replace("'", "''")
                    consulta = consulta.replace(f"?", f"'{param}'", 1)
            else:
                consulta = consulta_sql
            
            resultado, error = self.gestor.ejecutar_sql_remoto(consulta)
            
            if error:
                logger.error(f"❌ Error en consulta remota: {error}")
                return None
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando consulta remota: {e}")
            return None
    
    def ejecutar_modificacion_remota(self, consulta_sql, parametros=None):
        """Ejecutar modificación SQL en servidor remoto"""
        try:
            if parametros:
                # Convertir consulta con parámetros
                consulta = consulta_sql
                for i, param in enumerate(parametros):
                    if isinstance(param, str):
                        param = param.replace("'", "''").replace('"', '\\"')
                    consulta = consulta.replace(f"?", f"'{param}'", 1)
            else:
                consulta = consulta_sql
            
            exito, resultado = self.gestor.ejecutar_sql_modificacion(consulta)
            
            if not exito:
                logger.error(f"❌ Error en modificación remota: {resultado}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando modificación remota: {e}")
            return False
    
    # =============================================================================
    # MÉTODOS DE CONSULTA CON PAGINACIÓN - 100% REMOTO
    # =============================================================================
    
    def obtener_usuario(self, usuario):
        """Obtener usuario por nombre de usuario o matrícula"""
        try:
            consulta = f"""
            SELECT * FROM usuarios 
            WHERE usuario = '{usuario}' OR matricula = '{usuario}' OR email = '{usuario}'
            LIMIT 1
            """
            
            resultado = self.ejecutar_consulta_remota(consulta)
            
            if resultado and len(resultado) > 0:
                return resultado[0]
            return None
        except Exception as e:
            logger.error(f"Error obteniendo usuario {usuario}: {e}", exc_info=True)
            return None
    
    def verificar_login(self, usuario, password):
        """Verificar credenciales de login"""
        try:
            usuario_data = self.obtener_usuario(usuario)
            if not usuario_data:
                logger.warning(f"Usuario no encontrado: {usuario}")
                return None
            
            stored_password = usuario_data.get('password', '')
            
            # Verificar contraseña (simple para demo)
            if stored_password == password:
                logger.info(f"Login exitoso: {usuario}")
                return usuario_data
            else:
                logger.warning(f"Password incorrecto: {usuario}")
                return None
                
        except Exception as e:
            logger.error(f"Error verificando login: {e}", exc_info=True)
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
            
            folio = self.generar_folio_unico()
            
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
                '{inscrito_data.get('fecha_registro', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}',
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
                '{estudiante_data.get('fecha_inscripcion', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}',
                '{estudiante_data.get('estatus', 'ACTIVO')}',
                '{estudiante_data.get('documentos_subidos', '')}',
                '{estudiante_data.get('fecha_registro', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}',
                '{estudiante_data.get('programa_interes', '')}',
                '{estudiante_data.get('folio', '')}',
                '{estudiante_data.get('como_se_entero', '')}',
                '{estudiante_data.get('fecha_ingreso', datetime.now().strftime('%Y-%m-%d'))}',
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
                '{egresado_data.get('fecha_graduacion', datetime.now().strftime('%Y-%m-%d'))}',
                '{egresado_data.get('nivel_academico', '')}',
                '{egresado_data.get('email', '')}',
                '{egresado_data.get('telefono', '')}',
                '{egresado_data.get('estado_laboral', '')}',
                '{egresado_data.get('fecha_actualizacion', datetime.now().strftime('%Y-%m-%d'))}',
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
                '{contratado_data.get('fecha_contratacion', datetime.now().strftime('%Y-%m-%d'))}',
                '{contratado_data.get('puesto', '')}',
                '{contratado_data.get('departamento', '')}',
                '{contratado_data.get('estatus', '')}',
                '{contratado_data.get('salario', '')}',
                '{contratado_data.get('tipo_contrato', '')}',
                '{contratado_data.get('fecha_inicio', datetime.now().strftime('%Y-%m-%d'))}',
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
    
    def generar_folio_unico(self):
        """Generar folio único para publicación anónima"""
        fecha = datetime.now().strftime('%y%m%d')
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"FOL{fecha}{random_str}"
    
    def crear_backup_remoto(self):
        """Crear backup en servidor remoto"""
        return self.gestor.crear_backup_remoto()

# =============================================================================
# 3. CAPA DE SERVICIOS (LÓGICA DE NEGOCIO)
# =============================================================================

# =============================================================================
# 3.1 SISTEMA DE BACKUP AUTOMÁTICO - MODIFICADO PARA 100% REMOTO
# =============================================================================

class SistemaBackupAutomatico:
    """Sistema de backup automático - 100% REMOTO"""
    
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
# 3.2 SISTEMA DE NOTIFICACIONES
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
# 3.3 SISTEMA DE AUTENTICACIÓN
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
                usuario_data = db.verificar_login(usuario, password)
                
                if usuario_data:
                    nombre_real = usuario_data.get('nombre_completo', usuario_data.get('usuario', 'Usuario'))
                    
                    st.success(f"✅ ¡Bienvenido(a), {nombre_real}!")
                    st.session_state.login_exitoso = True
                    st.session_state.usuario_actual = usuario_data
                    st.session_state.rol_usuario = usuario_data.get('rol', 'usuario')
                    self.sesion_activa = True
                    self.usuario_actual = usuario_data
                    
                    db.registrar_bitacora(
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
# 3.4 SISTEMA PRINCIPAL - MODIFICADO PARA 100% REMOTO
# =============================================================================

class SistemaPrincipal:
    def __init__(self):
        self.gestor = gestor_remoto
        self.db = db
        self.backup_system = SistemaBackupAutomatico(self.gestor)
        self.notificaciones = SistemaNotificaciones(
            gestor_remoto.config.get('smtp', {})
        )
        self.validador = ValidadorDatos()
        
        self.current_page_inscritos = 1
        self.current_page_estudiantes = 1
        self.current_page_egresados = 1
        self.current_page_contratados = 1
        
        self.search_term_inscritos = ""
        self.search_term_estudiantes = ""
        self.search_term_egresados = ""
        self.search_term_contratados = ""
        
        # No hay carga inicial de datos - se cargan bajo demanda
        
    def cargar_datos_paginados(self):
        """Cargar datos desde la base de datos REMOTA con paginación"""
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
                    page=1, search_term=""
                )
                
                logger.info(f"""
                📊 Datos cargados REMOTAMENTE:
                - Inscritos: {self.total_inscritos} registros (página {self.current_page_inscritos}/{self.total_pages_inscritos})
                - Estudiantes: {self.total_estudiantes} registros (página {self.current_page_estudiantes}/{self.total_pages_estudiantes})
                - Egresados: {self.total_egresados} registros (página {self.current_page_egresados}/{self.total_pages_egresados})
                - Contratados: {self.total_contratados} registros (página {self.current_page_contratados}/{self.total_pages_contratados})
                """)
                
        except Exception as e:
            logger.error(f"Error cargando datos remotos: {e}", exc_info=True)
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

# =============================================================================
# 4. CAPA DE INTERFAZ (STREAMLIT UI)
# =============================================================================

# Instancias globales de los servicios
logger = EnhancedLogger()
estado_sistema = EstadoPersistente()
gestor_remoto = GestorConexionRemota()
db = SistemaBaseDatos()
auth = SistemaAutenticacion()
sistema_principal = None

# =============================================================================
# 4.1 FUNCIONES DE INTERFAZ
# =============================================================================

def mostrar_login():
    """Interfaz de login - SIEMPRE MOSTRAR FORMULARIO"""
    st.title("🏥 Sistema Escuela Enfermería - 100% REMOTO")
    st.markdown("---")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if estado_sistema.esta_inicializada():
            st.success("✅ Base de datos inicializada")
        else:
            st.warning("⚠️ Base de datos NO inicializada")
    
    with col2:
        if estado_sistema.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
        else:
            st.error("❌ SSH Desconectado")
    
    with col3:
        temp_dir = tempfile.gettempdir()
        espacio_ok, espacio_mb = UtilidadesSistema.verificar_espacio_disco(temp_dir)
        if espacio_ok:
            st.success(f"💾 Espacio: {espacio_mb:.0f} MB")
        else:
            st.warning(f"💾 Espacio: {espacio_mb:.0f} MB")
    
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            st.subheader("Iniciar Sesión")
            
            usuario = st.text_input("👤 Usuario", placeholder="admin", key="login_usuario")
            password = st.text_input("🔒 Contraseña", type="password", placeholder="Admin123!", key="login_password")
            
            col_a, col_b = st.columns(2)
            with col_a:
                login_button = st.form_submit_button("🚀 Iniciar Sesión", use_container_width=True)
            with col_b:
                inicializar_button = st.form_submit_button("🔄 Inicializar DB Remota", use_container_width=True, type="secondary")

            if login_button:
                if usuario and password:
                    with st.spinner("Verificando credenciales..."):
                        if auth.verificar_login(usuario, password):
                            st.rerun()
                        else:
                            st.error("❌ Credenciales incorrectas")
                else:
                    st.warning("⚠️ Complete todos los campos")
            
            if inicializar_button:
                with st.spinner("Inicializando base de datos en servidor remoto..."):
                    if db.inicializar_db_remota():
                        st.success("✅ Base de datos remota inicializada")
                        st.info("Ahora puedes iniciar sesión con:")
                        st.info("👤 Usuario: admin")
                        st.info("🔒 Contraseña: Admin123!")
                        st.rerun()
                    else:
                        st.error("❌ Error inicializando base de datos remota")
            
            with st.expander("ℹ️ Información de acceso"):
                st.info("""
                **Primer uso (100% REMOTO):**
                1. Haz clic en **"Inicializar DB Remota"** para crear la base de datos en el servidor
                2. Usa las credenciales por defecto que se crearán automáticamente
                3. Inicia sesión con esas credenciales
                
                **Credenciales por defecto (después de inicializar):**
                - 👤 Usuario: **admin**
                - 🔒 Contraseña: **Admin123!**
                
                **Verificación del sistema 100% REMOTO:**
                - ✅ SSH debe estar conectado
                - ✅ Base de datos debe estar inicializada en servidor remoto
                - 💾 Debe haber suficiente espacio en disco temporal
                - 🌐 Todos los datos se manejan directamente en servidor remoto
                """)

def mostrar_interfaz_principal():
    """Interfaz principal después del login"""
    global sistema_principal
    
    usuario_actual = st.session_state.usuario_actual
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

    with col1:
        st.title("🏥 Sistema Escuela Enfermería - 100% REMOTO")
        nombre_usuario = usuario_actual.get('nombre_completo', usuario_actual.get('usuario', 'Usuario'))
        st.write(f"**👤 Usuario:** {nombre_usuario} | **🎭 Rol:** {usuario_actual.get('rol', 'usuario')}")

    with col2:
        if gestor_remoto.config.get('host'):
            st.write(f"**🔗 Servidor:** {gestor_remoto.config['host']}")

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
    st.header("📊 Dashboard - 100% REMOTO")
    
    if sistema_principal is None:
        st.error("❌ Sistema principal no inicializado")
        return
    
    # Cargar datos si no están cargados
    if sistema_principal.total_inscritos == 0:
        sistema_principal.cargar_datos_paginados()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("👥 Inscritos", sistema_principal.total_inscritos)
    
    with col2:
        st.metric("🎓 Estudiantes", sistema_principal.total_estudiantes)
    
    with col3:
        st.metric("🏆 Egresados", sistema_principal.total_egresados)
    
    with col4:
        st.metric("💼 Contratados", sistema_principal.total_contratados)
    
    st.markdown("---")
    
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📈 Distribución por Categoría")
        
        datos_categorias = {
            'Inscritos': sistema_principal.total_inscritos,
            'Estudiantes': sistema_principal.total_estudiantes,
            'Egresados': sistema_principal.total_egresados,
            'Contratados': sistema_principal.total_contratados
        }
        
        if sum(datos_categorias.values()) > 0:
            import plotly.express as px
            df_categorias = pd.DataFrame({
                'Categoría': list(datos_categorias.keys()),
                'Cantidad': list(datos_categorias.values())
            })
            
            fig = px.pie(df_categorias, values='Cantidad', names='Categoría',
                        title='Distribución de Personas por Categoría')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("ℹ️ No hay datos para mostrar gráficos")
    
    with col_right:
        st.subheader("🔗 Estado del Sistema 100% REMOTO")
        
        if estado_sistema.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
            if gestor_remoto.config.get('host'):
                st.info(f"Servidor: {gestor_remoto.config['host']}")
        else:
            st.error("❌ SSH Desconectado")
        
        ultima_sync = estado_sistema.estado.get('ultima_sincronizacion')
        if ultima_sync:
            try:
                fecha_sync = datetime.fromisoformat(ultima_sync)
                st.info(f"🔄 Última operación: {fecha_sync.strftime('%Y-%m-%d %H:%M')}")
            except:
                pass
        
        if estado_sistema.esta_inicializada():
            st.success("✅ Base de datos en servidor remoto")
        else:
            st.error("❌ Base de datos NO inicializada en servidor")
        
        backups = sistema_principal.backup_system.listar_backups()
        if backups:
            st.success(f"💾 {len(backups)} backups registrados")
        else:
            st.info("💾 No hay backups registrados")
    
    st.markdown("---")
    st.subheader("🚀 Acciones Rápidas 100% REMOTO")
    
    col_act1, col_act2, col_act3 = st.columns(3)
    
    with col_act1:
        if st.button("📊 Cargar Datos", use_container_width=True):
            with st.spinner("Cargando datos desde servidor remoto..."):
                sistema_principal.cargar_datos_paginados()
                st.success("✅ Datos cargados desde servidor remoto")
                st.rerun()
    
    with col_act2:
        if st.button("💾 Crear Backup Remoto", use_container_width=True):
            with st.spinner("Creando backup en servidor remoto..."):
                backup_path = sistema_principal.backup_system.crear_backup(
                    "MANUAL_DASHBOARD",
                    "Backup manual creado desde dashboard"
                )
                if backup_path:
                    st.success(f"✅ Backup creado en servidor remoto")
                else:
                    st.error("❌ Error creando backup remoto")
    
    with col_act3:
        if st.button("🔗 Probar Conexión", use_container_width=True):
            with st.spinner("Probando conexión SSH..."):
                if gestor_remoto.verificar_conexion_ssh():
                    st.success("✅ Conexión SSH exitosa")
                    st.rerun()
                else:
                    st.error("❌ Conexión SSH fallida")
    
    st.markdown("---")
    st.subheader("📋 Información del Sistema")
    
    with st.expander("🔍 Ver detalles técnicos"):
        col_tech1, col_tech2 = st.columns(2)
        
        with col_tech1:
            st.write("**Configuración SSH:**")
            if gestor_remoto.config.get('host'):
                st.write(f"- Host: {gestor_remoto.config['host']}")
                st.write(f"- Puerto: {gestor_remoto.config.get('port', 22)}")
                st.write(f"- Usuario: {gestor_remoto.config['username']}")
            
            st.write("**Rutas remotas:**")
            st.write(f"- DB: {gestor_remoto.config.get('remote_db_escuela', 'No configurada')}")
            st.write(f"- Uploads: {gestor_remoto.config.get('remote_uploads_path', 'No configurada')}")
        
        with col_tech2:
            st.write("**Estadísticas del sistema:**")
            stats = estado_sistema.estado.get('estadisticas_sistema', {})
            st.write(f"- Sesiones exitosas: {stats.get('sesiones', 0)}")
            st.write(f"- Backups realizados: {estado_sistema.estado.get('backups_realizados', 0)}")
            st.write(f"- Total sesiones: {estado_sistema.estado.get('sesiones_iniciadas', 0)}")

def mostrar_inscritos():
    """Interfaz para gestión de inscritos - 100% REMOTO"""
    global sistema_principal
    st.header("📝 Gestión de Inscritos - 100% REMOTO")
    
    if sistema_principal is None:
        sistema_principal = SistemaPrincipal()
    
    # Cargar datos si no están cargados
    if sistema_principal.df_inscritos.empty:
        sistema_principal.cargar_datos_paginados()
    
    tab1, tab2 = st.tabs(["📋 Lista de Inscritos", "➕ Agregar Inscrito"])
    
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
                key="search_inscritos_tabla"
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
            
            col_prev, col_page, col_next = st.columns([1, 2, 1])
            
            with col_prev:
                if sistema_principal.current_page_inscritos > 1:
                    if st.button("⬅️ Página Anterior", use_container_width=True):
                        sistema_principal.current_page_inscritos -= 1
                        sistema_principal.cargar_datos_paginados()
                        st.rerun()
            
            with col_page:
                st.write(f"**Página {sistema_principal.current_page_inscritos} de {max(1, sistema_principal.total_pages_inscritos)}**")
            
            with col_next:
                if sistema_principal.current_page_inscritos < sistema_principal.total_pages_inscritos:
                    if st.button("Página Siguiente ➡️", use_container_width=True):
                        sistema_principal.current_page_inscritos += 1
                        sistema_principal.cargar_datos_paginados()
                        st.rerun()
    
    with tab2:
        st.subheader("➕ Agregar Nuevo Inscrito")
        
        with st.form("form_agregar_inscrito"):
            col_i1, col_i2 = st.columns(2)
            
            with col_i1:
                nombre_completo = st.text_input("Nombre Completo*", placeholder="Juan Pérez López")
                email = st.text_input("Email*", placeholder="juan@ejemplo.com")
                telefono = st.text_input("Teléfono", placeholder="5512345678")
                programa_interes = st.selectbox("Programa de Interés*", ["", "Licenciatura en Enfermería", "Especialidad en Enfermería Cardiovascular", "Maestría en Ciencias Cardiológicas", "Diplomado de Cardiología Básica", "Curso de RCP Avanzado"])
            
            with col_i2:
                fecha_nacimiento = st.date_input("Fecha de Nacimiento", value=datetime(2000, 1, 1))
                como_se_entero = st.selectbox("¿Cómo se enteró?", ["", "Internet", "Redes Sociales", "Amigo/Familiar", "Publicidad", "Otro"])
                documentos_subidos = st.number_input("Documentos Subidos", min_value=0, max_value=20, value=0)
                estatus = st.selectbox("Estatus", ["Pre-inscrito", "En revisión", "Aceptado", "Rechazado"])
            
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
                        'como_se_entero': como_se_entero,
                        'documentos_subidos': documentos_subidos,
                        'estatus': estatus,
                        'fecha_registro': datetime.now()
                    }
                    
                    if db.agregar_inscrito(inscrito_data):
                        st.success("✅ Inscrito agregado exitosamente al servidor remoto")
                        
                        # Crear backup automático
                        sistema_principal.backup_system.crear_backup(
                            "AGREGAR_INSCRITO",
                            f"Nuevo inscrito: {nombre_completo} - {email}"
                        )
                        
                        # Recargar datos
                        sistema_principal.cargar_datos_paginados()
                        st.rerun()
                    else:
                        st.error("❌ Error agregando inscrito")

def mostrar_estudiantes():
    """Interfaz para gestión de estudiantes - 100% REMOTO"""
    global sistema_principal
    st.header("🎓 Gestión de Estudiantes - 100% REMOTO")
    
    if sistema_principal is None:
        sistema_principal = SistemaPrincipal()
    
    # Cargar datos si no están cargados
    if sistema_principal.df_estudiantes.empty:
        sistema_principal.cargar_datos_paginados()
    
    if sistema_principal.total_estudiantes == 0:
        st.warning("🎓 No hay estudiantes registrados")
    else:
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        
        with col_stat1:
            st.metric("Total Estudiantes", sistema_principal.total_estudiantes)
        
        with col_stat2:
            st.metric("Página Actual", f"{sistema_principal.current_page_estudiantes}/{max(1, sistema_principal.total_pages_estudiantes)}")
        
        with col_stat3:
            registros_pagina = len(sistema_principal.df_estudiantes)
            st.metric("En esta página", registros_pagina)
        
        st.subheader("🔍 Buscar Estudiante")
        search_term = st.text_input(
            "Buscar por matrícula, nombre o email:", 
            value=sistema_principal.search_term_estudiantes,
            key="search_estudiantes"
        )
        
        if st.button("🔎 Buscar Estudiantes", key="btn_buscar_estudiantes"):
            sistema_principal.search_term_estudiantes = search_term
            sistema_principal.current_page_estudiantes = 1
            sistema_principal.cargar_datos_paginados()
            st.rerun()
        
        if not sistema_principal.df_estudiantes.empty:
            st.dataframe(
                sistema_principal.df_estudiantes,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("ℹ️ No hay estudiantes que coincidan con la búsqueda")
        
        col_prev, col_page, col_next = st.columns([1, 2, 1])
        
        with col_prev:
            if sistema_principal.current_page_estudiantes > 1:
                if st.button("⬅️ Página Anterior", key="prev_estudiantes", use_container_width=True):
                    sistema_principal.current_page_estudiantes -= 1
                    sistema_principal.cargar_datos_paginados()
                    st.rerun()
        
        with col_page:
            st.write(f"**Página {sistema_principal.current_page_estudiantes} de {max(1, sistema_principal.total_pages_estudiantes)}**")
        
        with col_next:
            if sistema_principal.current_page_estudiantes < sistema_principal.total_pages_estudiantes:
                if st.button("Página Siguiente ➡️", key="next_estudiantes", use_container_width=True):
                    sistema_principal.current_page_estudiantes += 1
                    sistema_principal.cargar_datos_paginados()
                    st.rerun()

def mostrar_egresados():
    """Interfaz para gestión de egresados - 100% REMOTO"""
    global sistema_principal
    st.header("🏆 Gestión de Egresados - 100% REMOTO")
    
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
    """Interfaz para gestión de contratados - 100% REMOTO"""
    global sistema_principal
    st.header("💼 Gestión de Contratados - 100% REMOTO")
    
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
    """Interfaz para gestión de usuarios - 100% REMOTO"""
    global sistema_principal
    st.header("👥 Gestión de Usuarios - 100% REMOTO")
    
    if sistema_principal is None:
        sistema_principal = SistemaPrincipal()
    
    try:
        df_usuarios, total_pages, total_usuarios = db.obtener_usuarios(page=1)

        if total_usuarios == 0:
            st.warning("📭 No hay usuarios registrados")
        else:
            st.subheader("📋 Lista de Usuarios")
            st.dataframe(
                df_usuarios[['usuario', 'nombre_completo', 'rol', 'email', 'matricula', 'activo']],
                use_container_width=True,
                hide_index=True
            )
        
        st.subheader("➕ Agregar Nuevo Usuario")

        with st.form("form_agregar_usuario"):
            col_u1, col_u2 = st.columns(2)

            with col_u1:
                usuario = st.text_input("Usuario*", placeholder="nuevo_usuario")
                password = st.text_input("Contraseña*", type="password", placeholder="********")
                rol = st.selectbox("Rol*", ["administrador", "usuario", "inscrito", "estudiante"])
                nombre_completo = st.text_input("Nombre Completo*", placeholder="Nombre Apellido")

            with col_u2:
                email = st.text_input("Email*", placeholder="usuario@ejemplo.com")
                matricula = st.text_input("Matrícula", placeholder="USR-001")
                categoria_academica = st.selectbox("Categoría Académica", ["", "pregrado", "posgrado", "licenciatura", "educacion_continua"])
                tipo_programa = st.selectbox("Tipo de Programa", ["", "LICENCIATURA", "ESPECIALIDAD", "MAESTRIA", "DIPLOMADO", "CURSO"])

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
                        'activo': True,
                        'categoria_academica': categoria_academica if categoria_academica else None,
                        'tipo_programa': tipo_programa if tipo_programa else None
                    }
                    
                    if db.agregar_usuario(usuario_data):
                        st.success(f"✅ Usuario {usuario} creado exitosamente en servidor remoto")
                        
                        # Crear backup automático
                        sistema_principal.backup_system.crear_backup(
                            "AGREGAR_USUARIO",
                            f"Nuevo usuario: {usuario} - {rol}"
                        )
                        
                        st.rerun()
                    else:
                        st.error("❌ Error creando usuario")

        with st.expander("🔐 Información de Seguridad 100% REMOTO"):
            st.info("""
            **Características de seguridad implementadas:**
            ✅ **Operaciones 100% remotas** - Sin archivos locales
            ✅ **Conexión SSH segura** con timeout configurable
            ✅ **Backups automáticos** en servidor remoto
            ✅ **Registro de bitácora** de todas las operaciones
            ✅ **Contraseñas almacenadas** en servidor remoto
            ✅ **Validaciones de datos** antes de operaciones
            """)

    except Exception as e:
        st.error(f"❌ Error obteniendo usuarios: {e}")

def mostrar_configuracion():
    """Interfaz para configuración del sistema - 100% REMOTO"""
    global sistema_principal
    st.header("⚙️ Configuración del Sistema - 100% REMOTO")

    if sistema_principal is None:
        st.error("❌ Sistema principal no inicializado")
        return

    st.subheader("🔧 Información del Sistema 100% REMOTO")

    col_info1, col_info2 = st.columns(2)

    with col_info1:
        st.write("**📊 Estado del Sistema:**")
        if estado_sistema.esta_inicializada():
            st.success("✅ Base de datos inicializada en servidor remoto")
            fecha_inicializacion = estado_sistema.obtener_fecha_inicializacion()
            if fecha_inicializacion:
                st.write(f"📅 Fecha inicialización: {fecha_inicializacion.strftime('%Y-%m-%d %H:%M')}")
        else:
            st.warning("⚠️ Base de datos NO inicializada en servidor")

        if estado_sistema.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
            if gestor_remoto.config.get('host'):
                st.write(f"🌐 Servidor: {gestor_remoto.config['host']}")
                st.write(f"🔌 Puerto: {gestor_remoto.config.get('port', 22)}")
        else:
            st.error("❌ SSH Desconectado")
            error_ssh = estado_sistema.estado.get('ssh_error')
            if error_ssh:
                st.error(f"⚠️ Error: {error_ssh}")

    with col_info2:
        st.write("**💾 Recursos y Estadísticas:**")

        temp_dir = tempfile.gettempdir()
        espacio_ok, espacio_mb = UtilidadesSistema.verificar_espacio_disco(temp_dir)

        if espacio_ok:
            st.success(f"✅ Espacio temporal disponible: {espacio_mb:.0f} MB")
        else:
            st.warning(f"⚠️ Espacio temporal bajo: {espacio_mb:.0f} MB")

        backups = sistema_principal.backup_system.listar_backups()
        if backups:
            st.success(f"✅ {len(backups)} backups registrados")
        else:
            st.info("ℹ️ No hay backups registrados")

        stats = estado_sistema.estado.get('estadisticas_sistema', {})
        st.write(f"📈 Sesiones exitosas: {stats.get('sesiones', 0)}")
        st.write(f"🔄 Backups realizados: {estado_sistema.estado.get('backups_realizados', 0)}")
        st.write(f"👥 Total sesiones: {estado_sistema.estado.get('sesiones_iniciadas', 0)}")
    
    st.markdown("---")
    st.subheader("🔗 Configuración SSH")
    
    with st.expander("📋 Ver configuración actual"):
        if gestor_remoto.config.get('host'):
            config_show = gestor_remoto.config.copy()
            # Ocultar información sensible
            if 'password' in config_show:
                config_show['password'] = '********'
            if 'smtp' in config_show and 'email_password' in config_show['smtp']:
                config_show['smtp']['email_password'] = '********'
            
            st.json(config_show)
        else:
            st.error("❌ No hay configuración SSH cargada")
    
    st.markdown("---")
    st.subheader("🛠️ Herramientas del Sistema")
    
    col_tool1, col_tool2, col_tool3 = st.columns(3)
    
    with col_tool1:
        if st.button("💾 Crear Backup Ahora", use_container_width=True):
            with st.spinner("Creando backup en servidor remoto..."):
                if sistema_principal:
                    backup_path = sistema_principal.backup_system.crear_backup(
                        "MANUAL_CONFIG",
                        "Backup manual creado desde configuración"
                    )
                    if backup_path:
                        st.success("✅ Backup creado en servidor remoto")
                    else:
                        st.error("❌ Error creando backup")
    
    with col_tool2:
        if st.button("🔍 Verificar Conexión", use_container_width=True):
            with st.spinner("Verificando conexión SSH..."):
                if gestor_remoto.verificar_conexion_ssh():
                    st.success("✅ Conexión SSH verificada")
                    st.rerun()
                else:
                    st.error("❌ Error en conexión SSH")
    
    with col_tool3:
        if st.button("📊 Ver Tablas DB", use_container_width=True):
            try:
                consulta = "SELECT name FROM sqlite_master WHERE type='table'"
                resultado = db.ejecutar_consulta_remota(consulta)
                
                if resultado:
                    st.success(f"✅ {len(resultado)} tablas en base de datos remota:")
                    for tabla in resultado:
                        nombre_tabla = tabla.get('name', '')
                        count_consulta = f"SELECT COUNT(*) as total FROM {nombre_tabla}"
                        count_result = db.ejecutar_consulta_remota(count_consulta)
                        count = count_result[0].get('total', 0) if count_result else 0
                        st.write(f"- **{nombre_tabla}**: {count} registros")
                else:
                    st.error("❌ No hay tablas en la base de datos remota")
            except Exception as e:
                st.error(f"❌ Error: {e}")

# =============================================================================
# 5. EJECUCIÓN PRINCIPAL - 100% REMOTO
# =============================================================================

def main():
    """Función principal de la aplicación 100% REMOTO"""
    
    with st.sidebar:
        st.title("🔧 Sistema Escuela - 100% REMOTO")
        st.markdown("---")

        st.subheader("🔗 Estado de Conexión SSH")

        if estado_sistema.esta_inicializada():
            st.success("✅ Base de datos remota inicializada")
            fecha_inicializacion = estado_sistema.obtener_fecha_inicializacion()
            if fecha_inicializacion:
                st.caption(f"📅 Inicializada: {fecha_inicializacion.strftime('%Y-%m-%d %H:%M')}")
        else:
            st.warning("⚠️ Base de datos NO inicializada")

        if estado_sistema.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
            if gestor_remoto.config.get('host'):
                st.caption(f"🌐 Servidor: {gestor_remoto.config['host']}")
        else:
            st.error("❌ SSH Desconectado")
            error_ssh = estado_sistema.estado.get('ssh_error')
            if error_ssh:
                st.caption(f"⚠️ Error: {error_ssh}")

        st.subheader("💾 Estado del Sistema")
        temp_dir = tempfile.gettempdir()
        espacio_ok, espacio_mb = UtilidadesSistema.verificar_espacio_disco(temp_dir)

        if espacio_ok:
            st.success(f"Espacio temporal: {espacio_mb:.0f} MB")
        else:
            st.warning(f"Espacio temporal bajo: {espacio_mb:.0f} MB")

        with st.expander("📋 Información del Servidor"):
            if gestor_remoto.config.get('host'):
                st.write(f"**Host:** {gestor_remoto.config['host']}")
                st.write(f"**Puerto:** {gestor_remoto.config.get('port', 22)}")
                st.write(f"**Usuario:** {gestor_remoto.config['username']}")
                st.write(f"**Modo:** 100% REMOTO")

        st.markdown("---")

        st.subheader("📈 Estadísticas")
        stats = estado_sistema.estado.get('estadisticas_sistema', {})

        col_stat1, col_stat2 = st.columns(2)
        with col_stat1:
            st.metric("Sesiones", stats.get('sesiones', 0))
        with col_stat2:
            st.metric("Backups", estado_sistema.estado.get('backups_realizados', 0))

        sesiones = estado_sistema.estado.get('sesiones_iniciadas', 0)
        st.metric("Total Sesiones", sesiones)

        ultima_verificacion = estado_sistema.estado.get('ultima_verificacion')
        if ultima_verificacion:
            try:
                fecha_ver = datetime.fromisoformat(ultima_verificacion)
                st.caption(f"🔄 Última verificación: {fecha_ver.strftime('%H:%M:%S')}")
            except:
                pass

        st.markdown("---")

        st.subheader("💾 Sistema de Backups Remotos")

        if st.button("💾 Crear Backup Remoto", use_container_width=True):
            global sistema_principal
            if sistema_principal:
                with st.spinner("Creando backup en servidor remoto..."):
                    backup_path = sistema_principal.backup_system.crear_backup(
                        "MANUAL_SIDEBAR",
                        "Backup manual creado desde sidebar"
                    )
                    if backup_path:
                        st.success(f"✅ Backup creado en servidor remoto")
                    else:
                        st.error("❌ Error creando backup remoto")

        backups = SistemaBackupAutomatico(gestor_remoto).listar_backups()
        if backups and len(backups) > 0:
            with st.expander(f"📂 Ver últimos {min(len(backups), 5)} backups"):
                for backup in backups[:5]:
                    fecha_str = backup['fecha'].strftime('%Y-%m-%d %H:%M')
                    st.caption(f"📅 {fecha_str} - {backup['tipo_operacion']} ({backup['ubicacion']})")

        st.markdown("---")

        st.caption("🏥 Sistema Escuela Enfermería v3.0 - 100% REMOTO")
        st.caption("🔗 Conectado directamente a servidor via SSH")
        st.caption("📚 Todos los datos almacenados en servidor remoto")

    try:
        session_defaults = {
            'login_exitoso': False,
            'usuario_actual': None,
            'rol_usuario': None
        }

        for key, default_value in session_defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default_value

        if not gestor_remoto.config.get('host'):
            st.error("""
            ❌ **ERROR DE CONFIGURACIÓN 100% REMOTO**

            No se encontró configuración SSH en secrets.toml.

            **Solución para modo 100% REMOTO:**
            1. Asegúrate de tener un archivo `.streamlit/secrets.toml`
            2. Agrega la configuración SSH (SOLO RUTAS REMOTAS):
            ```toml
            [ssh]
            host = "tu.servidor.com"
            port = 22
            username = "tu_usuario"
            password = "tu_contraseña"
            enabled = true

            [paths]
            remote_db_escuela = "/ruta/remota/escuela.db"
            remote_uploads_path = "/ruta/remota/uploads"
            # NO incluir rutas locales

            [system]
            auto_connect = true
            retry_attempts = 3
            retry_delay = 5
            ```
            
            **IMPORTANTE:** Este sistema es 100% REMOTO. No descarga archivos locales.
            """)

            with st.expander("🔍 Diagnóstico del Sistema"):
                st.write("**Rutas buscadas para secrets.toml:**")
                for ruta in [
                    ".streamlit/secrets.toml",
                    "secrets.toml",
                    "./.streamlit/secrets.toml"
                ]:
                    existe = os.path.exists(ruta)
                    estado = "✅ Existe" if existe else "❌ No existe"
                    st.write(f"{estado}: `{ruta}`")
                
                st.write("**Modo de operación:** 100% REMOTO")
                st.write("**Archivos locales temporales:** NO se utilizan")

            return

        if not st.session_state.login_exitoso:
            mostrar_login()
        else:
            mostrar_interfaz_principal()

    except Exception as e:
        logger.error(f"Error crítico en main(): {e}", exc_info=True)

        st.error(f"❌ Error crítico en la aplicación 100% REMOTO: {str(e)}")

        with st.expander("🔧 Información de diagnóstico detallada"):
            st.write("**Estado persistente:**")
            st.json(estado_sistema.estado)

            st.write("**Configuración SSH cargada:**")
            if gestor_remoto.config:
                config_show = gestor_remoto.config.copy()
                if 'password' in config_show:
                    config_show['password'] = '********'
                if 'smtp' in config_show and 'email_password' in config_show['smtp']:
                    config_show['smtp']['email_password'] = '********'
                st.json(config_show)
            else:
                st.write("No hay configuración SSH cargada")
            
            st.write("**Modo de operación:** 100% REMOTO")
            st.write("**Archivos locales temporales:** NO se utilizan")

        col_reset1, col_reset2 = st.columns(2)
        with col_reset1:
            if st.button("🔄 Reiniciar Aplicación", type="primary", use_container_width=True):
                keys_to_keep = ['login_exitoso', 'usuario_actual', 'rol_usuario']
                keys_to_delete = [k for k in st.session_state.keys() if k not in keys_to_keep]

                for key in keys_to_delete:
                    del st.session_state[key]

                st.success("✅ Estado de sesión limpiado")
                st.rerun()

        with col_reset2:
            if st.button("📋 Ver Logs Recientes", use_container_width=True):
                try:
                    if os.path.exists('escuela_detallado.log'):
                        with open('escuela_detallado.log', 'r') as f:
                            lines = f.readlines()[-50:]
                            st.text_area("Últimas líneas del log:", ''.join(lines), height=300)
                    else:
                        st.warning("No se encontró archivo de log")
                except Exception as log_error:
                    st.error(f"Error leyendo logs: {log_error}")

# =============================================================================
# PUNTO DE ENTRADA - 100% REMOTO
# =============================================================================

if __name__ == "__main__":
    try:
        st.info("""
        🏥 **SISTEMA DE GESTIÓN ESCOLAR 100% REMOTO - VERSIÓN COMPLETA 3.0**

        **Características principales:**
        ✅ **100% Operaciones remotas** - Sin descarga de archivos locales
        ✅ **Base de datos directa en servidor** - Sin sincronización
        ✅ **Backups automáticos en servidor remoto**
        ✅ **Conexión SSH segura** con reintentos automáticos
        ✅ **Interfaz Streamlit completa** con todas las funcionalidades
        
        **Para comenzar en modo 100% REMOTO:**
        1. Configura secrets.toml con tus credenciales SSH (solo rutas remotas)
        2. Haz clic en "Inicializar DB Remota" para crear la base de datos en el servidor
        3. Inicia sesión con las credenciales por defecto
        4. Todos los datos se manejarán DIRECTAMENTE en el servidor remoto
        
        **IMPORTANTE:** Este sistema NO descarga archivos locales. Todo queda en el servidor.
        """)

        main()
    except Exception as e:
        st.error(f"❌ Error crítico en la aplicación 100% REMOTO: {e}")
        logger.critical(f"Error crítico en sistema 100% remoto: {e}", exc_info=True)

        with st.expander("🚨 Información de diagnóstico crítico"):
            import traceback
            st.code(traceback.format_exc())
