"""
escuela20.py - Sistema Escuela Enfermería con BCRYPT y SSH
Versión completa mejorada con todas las recomendaciones
Sistema completo EXCLUSIVAMENTE REMOTO con base de datos SQLite remota
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
import socket
import re
import glob
import atexit
import math
import psutil
from typing import Optional, Dict, Any, List, Tuple
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
# CONFIGURACIÓN DE LOGGING MEJORADA
# =============================================================================

class EnhancedLogger:
    """Logger mejorado con diferentes niveles y formato detallado"""
    
    def __init__(self):
        # Configurar logging a archivo y consola
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        
        # Formato detallado
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler para consola
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        # Handler para archivo
        file_handler = logging.FileHandler('escuela_detallado.log', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        # Agregar handlers
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def debug(self, message, extra=None):
        """Log nivel debug"""
        self.logger.debug(message, extra=extra)
    
    def info(self, message, extra=None):
        """Log nivel info"""
        self.logger.info(message, extra=extra)
    
    def warning(self, message, extra=None):
        """Log nivel warning"""
        self.logger.warning(message, extra=extra)
    
    def error(self, message, exc_info=False, extra=None):
        """Log nivel error"""
        self.logger.error(message, exc_info=exc_info, extra=extra)
    
    def critical(self, message, exc_info=False, extra=None):
        """Log nivel critical"""
        self.logger.critical(message, exc_info=exc_info, extra=extra)
    
    def log_operation(self, operation, status, details):
        """Log específico para operaciones del sistema"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'operation': operation,
            'status': status,
            'details': details
        }
        
        # Guardar en archivo JSON para análisis posterior
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

# Instancia global del logger mejorado
logger = EnhancedLogger()

# =============================================================================
# CONFIGURACIÓN DE PÁGINA
# =============================================================================

st.set_page_config(
    page_title="Sistema Escuela Enfermería - Administración SSH REMOTA",
    page_icon="🏥",
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
        
        # Leer el archivo
        with open(ruta_encontrada, 'rb') as f:
            config = tomllib.load(f)
            logger.info(f"✅ Configuración cargada desde: {ruta_encontrada}")
            return config
        
    except Exception as e:
        logger.error(f"❌ Error cargando secrets.toml: {e}", exc_info=True)
        return {}

# =============================================================================
# SISTEMA DE BACKUP AUTOMÁTICO
# =============================================================================

class SistemaBackupAutomatico:
    """Sistema de backup automático"""
    
    def __init__(self, gestor_ssh):
        self.gestor_ssh = gestor_ssh
        self.backup_dir = "backups_sistema"
        self.max_backups = 10  # Mantener solo los últimos 10 backups
        
    def crear_backup(self, tipo_operacion, detalles):
        """Crear backup automático"""
        try:
            # Crear directorio de backups si no existe
            if not os.path.exists(self.backup_dir):
                os.makedirs(self.backup_dir)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_{tipo_operacion}_{timestamp}.zip"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Descargar base de datos actual para backup
            if self.gestor_ssh.conectar_ssh():
                try:
                    # Crear archivo temporal para backup
                    temp_db = self.gestor_ssh.descargar_db_remota()
                    if temp_db:
                        # Crear archivo zip con metadatos
                        import zipfile
                        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            zipf.write(temp_db, 'database.db')
                            
                            # Agregar metadatos
                            metadata = {
                                'fecha_backup': datetime.now().isoformat(),
                                'tipo_operacion': tipo_operacion,
                                'detalles': detalles,
                                'usuario': st.session_state.get('usuario_actual', {}).get('usuario', 'desconocido')
                            }
                            
                            metadata_str = json.dumps(metadata, indent=2, default=str)
                            zipf.writestr('metadata.json', metadata_str)
                        
                        logger.info(f"✅ Backup creado: {backup_path}")
                        
                        # Limpiar backups antiguos
                        self._limpiar_backups_antiguos()
                        
                        return backup_path
                finally:
                    self.gestor_ssh.desconectar_ssh()
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error creando backup: {e}")
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
            
            # Ordenar por fecha (más reciente primero)
            backups.sort(key=lambda x: x[1], reverse=True)
            
            # Eliminar backups antiguos
            for backup in backups[self.max_backups:]:
                try:
                    os.remove(backup[0])
                    logger.info(f"🗑️ Backup antiguo eliminado: {backup[0]}")
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo eliminar backup antiguo: {e}")
                    
        except Exception as e:
            logger.error(f"Error limpiando backups antiguos: {e}")
    
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
            logger.error(f"Error listando backups: {e}")
            return []

# =============================================================================
# SISTEMA DE NOTIFICACIONES
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
            
            # Preparar mensaje
            subject = f"[Sistema Escuela] {tipo_operacion} - {estado}"
            
            # Crear contenido HTML
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
            
            # Configurar mensaje
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.config_smtp['email_user']
            msg['To'] = ', '.join(destinatarios)
            
            # Adjuntar partes HTML y texto plano
            msg.attach(MIMEText(html_content, 'html'))
            
            # Enviar email
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
# VALIDACIONES MEJORADAS
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
    def validar_telefono(telefono):
        """Validar formato de teléfono (mínimo 10 dígitos)"""
        if not telefono:
            return True  # Opcional
        
        # Extraer solo dígitos
        digitos = ''.join(filter(str.isdigit, telefono))
        return len(digitos) >= 10
    
    @staticmethod
    def validar_matricula(matricula):
        """Validar formato de matrícula"""
        if not matricula:
            return False
        
        # Debe contener al menos 3 caracteres y algún número
        return len(matricula) >= 3 and any(char.isdigit() for char in matricula)
    
    @staticmethod
    def validar_fecha(fecha_str):
        """Validar formato de fecha"""
        try:
            datetime.fromisoformat(fecha_str.replace('Z', '+00:00'))
            return True
        except:
            return False

# =============================================================================
# ARCHIVO DE ESTADO PERSISTENTE - MEJORADO
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
                    
                    # Migrar estado antiguo si es necesario
                    if 'estadisticas_sistema' not in estado:
                        estado['estadisticas_sistema'] = {
                            'sesiones': estado.get('sesiones_iniciadas', 0),
                            'registros': 0,
                            'total_tiempo': 0
                        }
                    
                    return estado
            else:
                # Estado por defecto - SOLO MODO REMOTO
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
                    'backups_realizados': 0
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
            'backups_realizados': 0
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
        
        # Estadísticas detalladas
        if exitosa:
            self.estado['estadisticas_sistema']['sesiones'] += 1
        
        self.estado['estadisticas_sistema']['total_tiempo'] += tiempo_ejecucion
        
        self.guardar_estado()
    
    def registrar_backup(self):
        """Registrar que se realizó un backup"""
        self.estado['backups_realizados'] = self.estado.get('backups_realizados', 0) + 1
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
estado_sistema = EstadoPersistente()

# =============================================================================
# UTILIDADES DE DISCO Y RED
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
# GESTOR DE CONEXIÓN REMOTA VIA SSH - MEJORADO CON TIMEOUTS Y REINTENTOS
# =============================================================================

class GestorConexionRemota:
    """Gestor de conexión SSH al servidor remoto - EXCLUSIVAMENTE REMOTO"""
    
    def __init__(self):
        self.ssh = None
        self.sftp = None
        self.temp_files = []  # Lista para rastrear archivos temporales
        
        # Registrar limpieza al cerrar
        atexit.register(self._limpiar_archivos_temporales)
        
        # Cargar configuración desde secrets.toml
        logger.info("📋 Cargando configuración desde secrets.toml...")
        self.config_completa = cargar_configuracion_secrets()
        
        if not self.config_completa:
            logger.error("❌ No se pudo cargar configuración de secrets.toml")
            return
            
        self.config = self._cargar_configuracion_completa()
        
        # Configuración de sistema con timeouts específicos
        self.config_sistema = self.config_completa.get('system', {})
        self.auto_connect = self.config_sistema.get('auto_connect', True)
        self.sync_on_start = self.config_sistema.get('sync_on_start', True)
        self.retry_attempts = self.config_sistema.get('retry_attempts', 3)
        self.retry_delay_base = self.config_sistema.get('retry_delay', 5)
        
        # Timeouts específicos para diferentes operaciones
        self.timeouts = {
            'ssh_connect': self.config_sistema.get('ssh_connect_timeout', 30),
            'ssh_command': self.config_sistema.get('ssh_command_timeout', 60),
            'sftp_transfer': self.config_sistema.get('sftp_transfer_timeout', 300),
            'db_download': self.config_sistema.get('db_download_timeout', 180)
        }
        
        # Configuración de base de datos
        self.config_database = self.config_completa.get('database', {})
        self.sync_interval = self.config_database.get('sync_interval', 60)
        self.backup_before_operations = self.config_database.get('backup_before_operations', True)
        
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
            logger.error(f"❌ Error cargando configuración: {e}", exc_info=True)
        
        return config
    
    def _limpiar_archivos_temporales(self):
        """Limpiar archivos temporales creados"""
        logger.debug("Limpiando archivos temporales...")
        
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.debug(f"🗑️ Archivo temporal eliminado: {temp_file}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar {temp_file}: {e}")
        
        # También limpiar archivos antiguos en temp
        temp_dir = tempfile.gettempdir()
        pattern = os.path.join(temp_dir, "escuela_*.db")
        for old_file in glob.glob(pattern):
            try:
                # Eliminar archivos con más de 1 hora
                if os.path.getmtime(old_file) < time.time() - 3600:
                    os.remove(old_file)
                    logger.debug(f"🗑️ Archivo temporal antiguo eliminado: {old_file}")
            except:
                pass
    
    def _intento_conexion_con_backoff(self, attempt):
        """Calcular tiempo de espera con backoff exponencial"""
        # Backoff exponencial con jitter aleatorio
        wait_time = min(self.retry_delay_base * (2 ** attempt), 60)  # Máximo 60 segundos
        jitter = wait_time * 0.1 * np.random.random()  # 10% de jitter
        return wait_time + jitter
    
    def probar_conexion_inicial(self):
        """Probar la conexión SSH al inicio"""
        try:
            if not self.config.get('host'):
                return False
                
            logger.info(f"🔍 Probando conexión SSH a {self.config['host']}...")
            
            # Verificar conectividad de red primero
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
            
            # Ejecutar comando simple para verificar con timeout
            stdin, stdout, stderr = ssh_test.exec_command('pwd', timeout=self.timeouts['ssh_command'])
            output = stdout.read().decode().strip()
            
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
        """Establecer conexión SSH con el servidor remoto con manejo detallado de errores"""
        try:
            if not self.config.get('host'):
                logger.error("No hay configuración SSH disponible")
                return False
                
            logger.info(f"🔗 Conectando SSH a {self.config['host']}:{self.config.get('port', 22)}...")
            
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            port = self.config.get('port', 22)
            timeout = self.timeouts['ssh_connect']
            
            # Verificar espacio en disco antes de conectar
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
            
            # Configurar timeout para operaciones SFTP
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
    
    def descargar_db_remota(self):
        """Descargar base de datos SQLite del servidor remoto - CON REINTENTOS INTELIGENTES"""
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
                
                # Crear archivo temporal local
                temp_dir = tempfile.gettempdir()
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                temp_db_path = os.path.join(temp_dir, f"escuela_temp_{timestamp}.db")
                self.temp_files.append(temp_db_path)
                
                # Verificar espacio en disco antes de descargar
                espacio_ok, espacio_mb = UtilidadesSistema.verificar_espacio_disco(temp_dir, espacio_minimo_mb=200)
                if not espacio_ok:
                    raise Exception(f"Espacio en disco insuficiente: {espacio_mb:.1f} MB disponibles (se requieren 200 MB)")
                
                # Intentar descargar archivo remoto con timeout
                logger.info(f"📥 Descargando base de datos desde: {self.db_path_remoto}")
                
                # Configurar timeout para la descarga
                start_time = time.time()
                self.sftp.get(self.db_path_remoto, temp_db_path)
                download_time = time.time() - start_time
                
                # Verificar que el archivo se descargó correctamente
                if os.path.exists(temp_db_path) and os.path.getsize(temp_db_path) > 0:
                    file_size = os.path.getsize(temp_db_path)
                    logger.info(f"✅ Base de datos descargada: {temp_db_path} ({file_size} bytes en {download_time:.1f}s)")
                    
                    # Verificar integridad del archivo
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
                    # Intentar crear una nueva
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
            
            tablas_esperadas = {'usuarios', 'inscritos', 'estudiantes', 'egresados', 'contratados', 'bitacora'}
            tablas_encontradas = {t[0] for t in tablas}
            
            if not tablas_esperadas.issubset(tablas_encontradas):
                logger.warning(f"Faltan tablas: {tablas_esperadas - tablas_encontradas}")
                return False
            
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error verificando integridad DB: {e}")
            return False
    
    def _crear_nueva_db_remota(self):
        """Crear una nueva base de datos SQLite y subirla al servidor remoto"""
        try:
            logger.info("📝 Creando nueva base de datos remota...")
            
            # Crear archivo temporal para la nueva base de datos
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_db_path = os.path.join(temp_dir, f"escuela_nueva_{timestamp}.db")
            self.temp_files.append(temp_db_path)
            
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
                    
                    # Subir archivo con timeout
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
            estado_sistema.marcar_db_inicializada()
            
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura: {e}", exc_info=True)
            raise
    
    def subir_db_remota(self, ruta_local):
        """Subir base de datos local al servidor remoto (sobreescribir) - CON BACKUP"""
        try:
            logger.info(f"📤 Subiendo base de datos al servidor remoto...")
            
            if not self.conectar_ssh():
                return False
            
            # Crear backup de la base de datos remota antes de sobreescribir
            if self.backup_before_operations:
                try:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_path = f"{self.db_path_remoto}.backup_{timestamp}"
                    
                    # Verificar espacio en servidor remoto
                    try:
                        stat = self.sftp.stat(self.db_path_remoto)
                        file_size_mb = stat.st_size / (1024 * 1024)
                        logger.info(f"📊 Tamaño archivo a respaldar: {file_size_mb:.1f} MB")
                    except:
                        pass
                    
                    self.sftp.rename(self.db_path_remoto, backup_path)
                    logger.info(f"✅ Backup creado en servidor: {backup_path}")
                    estado_sistema.registrar_backup()
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo crear backup en servidor: {e}")
                    # Continuar aunque no se pueda hacer backup
            
            # Subir nuevo archivo con timeout
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

# Instancia global del gestor de conexión remota
gestor_remoto = GestorConexionRemota()

# =============================================================================
# SISTEMA DE BASE DE DATOS SQLITE - MEJORADO CON PAGINACIÓN
# =============================================================================

class SistemaBaseDatos:
    """Sistema de base de datos SQLite EXCLUSIVAMENTE REMOTO"""
    
    def __init__(self):
        self.gestor = gestor_remoto
        self.db_local_temp = None
        self.conexion_actual = None
        self.ultima_sincronizacion = None
        
        # Configuración de sistema
        self.retry_attempts = self.gestor.retry_attempts
        self.retry_delay_base = self.gestor.retry_delay_base
        
        # Configuración de paginación
        self.page_size = 50  # Registros por página
    
    def _intento_conexion_con_backoff(self, attempt):
        """Calcular tiempo de espera con backoff exponencial"""
        return self.gestor._intento_conexion_con_backoff(attempt)
    
    def sincronizar_desde_remoto(self):
        """Sincronizar base de datos desde el servidor remoto - CON REINTENTOS INTELIGENTES"""
        inicio_tiempo = time.time()
        
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
                tiempo_total = time.time() - inicio_tiempo
                
                logger.info(f"✅ Sincronización exitosa en {tiempo_total:.1f}s: {self.db_local_temp}")
                
                # Actualizar estado de sincronización
                estado_sistema.marcar_sincronizacion()
                
                return True
                
            except Exception as e:
                logger.error(f"❌ Error en intento {attempt + 1}: {e}", exc_info=True)
                if attempt < self.retry_attempts - 1:
                    wait_time = self._intento_conexion_con_backoff(attempt)
                    logger.info(f"⏳ Esperando {wait_time:.1f} segundos antes de reintentar...")
                    time.sleep(wait_time)
                    continue
                else:
                    tiempo_total = time.time() - inicio_tiempo
                    logger.error(f"❌ Sincronización fallida después de {tiempo_total:.1f}s")
                    return False
    
    def _inicializar_estructura_db(self):
        """Inicializar estructura de la base de datos"""
        try:
            if not self.db_local_temp:
                logger.error("❌ No hay ruta de base de datos para inicializar")
                return
            
            self.gestor._inicializar_db_estructura(self.db_local_temp)
            
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura: {e}", exc_info=True)
            raise
    
    def sincronizar_hacia_remoto(self):
        """Sincronizar base de datos local hacia el servidor remoto - CON REINTENTOS"""
        inicio_tiempo = time.time()
        
        for attempt in range(self.retry_attempts):
            try:
                logger.info(f"📤 Intento {attempt + 1}/{self.retry_attempts} sincronizando hacia remoto...")
                
                if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                    raise Exception("No hay base de datos local para subir")
                
                # Subir al servidor remoto
                exito = self.gestor.subir_db_remota(self.db_local_temp)
                
                if exito:
                    self.ultima_sincronizacion = datetime.now()
                    tiempo_total = time.time() - inicio_tiempo
                    
                    logger.info(f"✅ Cambios subidos exitosamente al servidor en {tiempo_total:.1f}s")
                    
                    # Actualizar estado
                    estado_sistema.marcar_sincronizacion()
                    
                    return True
                else:
                    raise Exception("Error subiendo al servidor")
                    
            except Exception as e:
                logger.error(f"❌ Error en intento {attempt + 1}: {e}", exc_info=True)
                if attempt < self.retry_attempts - 1:
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
            
            # Configurar timeout para queries
            conn.execute("PRAGMA busy_timeout = 5000")  # 5 segundos
            
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
    # MÉTODOS DE CONSULTA CON PAGINACIÓN
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
            logger.error(f"Error obteniendo usuario {usuario}: {e}", exc_info=True)
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
            logger.error(f"Error verificando login: {e}", exc_info=True)
            return None
    
    def obtener_inscritos(self, page=1, search_term=""):
        """Obtener inscritos con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            with self.get_connection() as conn:
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
                
                logger.debug(f"Obtenidos {len(df)} inscritos (página {page}/{total_pages})")
                return df, total_pages, total_records
        except Exception as e:
            logger.error(f"Error obteniendo inscritos: {e}", exc_info=True)
            return pd.DataFrame(), 0, 0
    
    def obtener_estudiantes(self, page=1, search_term=""):
        """Obtener estudiantes con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            with self.get_connection() as conn:
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
                
                logger.debug(f"Obtenidos {len(df)} estudiantes (página {page}/{total_pages})")
                return df, total_pages, total_records
        except Exception as e:
            logger.error(f"Error obteniendo estudiantes: {e}", exc_info=True)
            return pd.DataFrame(), 0, 0
    
    def obtener_egresados(self, page=1, search_term=""):
        """Obtener egresados con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            with self.get_connection() as conn:
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
                
                logger.debug(f"Obtenidos {len(df)} egresados (página {page}/{total_pages})")
                return df, total_pages, total_records
        except Exception as e:
            logger.error(f"Error obteniendo egresados: {e}", exc_info=True)
            return pd.DataFrame(), 0, 0
    
    def obtener_contratados(self, page=1, search_term=""):
        """Obtener contratados con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            with self.get_connection() as conn:
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
                
                logger.debug(f"Obtenidos {len(df)} contratados (página {page}/{total_pages})")
                return df, total_pages, total_records
        except Exception as e:
            logger.error(f"Error obteniendo contratados: {e}", exc_info=True)
            return pd.DataFrame(), 0, 0
    
    def obtener_usuarios(self, page=1, search_term=""):
        """Obtener usuarios con paginación y búsqueda"""
        try:
            offset = (page - 1) * self.page_size
            
            with self.get_connection() as conn:
                if search_term:
                    query = """
                        SELECT * FROM usuarios 
                        WHERE usuario LIKE ? OR nombre_completo LIKE ? OR email LIKE ? OR matricula LIKE ?
                        ORDER BY fecha_creacion DESC 
                        LIMIT ? OFFSET ?
                    """
                    search_pattern = f"%{search_term}%"
                    params = (search_pattern, search_pattern, search_pattern, search_pattern, self.page_size, offset)
                else:
                    query = "SELECT * FROM usuarios ORDER BY fecha_creacion DESC LIMIT ? OFFSET ?"
                    params = (self.page_size, offset)
                
                df = pd.read_sql_query(query, conn, params=params)
                
                # Obtener total de registros
                if search_term:
                    count_query = """
                        SELECT COUNT(*) FROM usuarios 
                        WHERE usuario LIKE ? OR nombre_completo LIKE ? OR email LIKE ? OR matricula LIKE ?
                    """
                    count_params = (search_pattern, search_pattern, search_pattern, search_pattern)
                else:
                    count_query = "SELECT COUNT(*) FROM usuarios"
                    count_params = ()
                
                total_records = pd.read_sql_query(count_query, conn, params=count_params).iloc[0, 0]
                total_pages = math.ceil(total_records / self.page_size)
                
                logger.debug(f"Obtenidos {len(df)} usuarios (página {page}/{total_pages})")
                return df, total_pages, total_records
        except Exception as e:
            logger.error(f"Error obteniendo usuarios: {e}", exc_info=True)
            return pd.DataFrame(), 0, 0
    
    def obtener_inscrito_por_matricula(self, matricula):
        """Buscar inscrito por matrícula"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM inscritos WHERE matricula = ?", (matricula,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error buscando inscrito {matricula}: {e}", exc_info=True)
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
            logger.error(f"Error buscando estudiante {matricula}: {e}", exc_info=True)
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
            logger.error(f"Error buscando egresado {matricula}: {e}", exc_info=True)
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
            logger.error(f"Error buscando contratado {matricula}: {e}", exc_info=True)
            return None
    
    def actualizar_inscrito(self, matricula, datos_actualizados):
        """Actualizar datos de un inscrito"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                campos = []
                valores = []
                
                for campo, valor in datos_actualizados.items():
                    if campo != 'matricula' and valor is not None:
                        campos.append(f"{campo} = ?")
                        valores.append(valor)
                
                if campos:
                    valores.append(matricula)
                    query = f"UPDATE inscritos SET {', '.join(campos)}, fecha_actualizacion = CURRENT_TIMESTAMP WHERE matricula = ?"
                    cursor.execute(query, valores)
                    logger.info(f"Inscrito actualizado: {matricula}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error actualizando inscrito {matricula}: {e}", exc_info=True)
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
            logger.error(f"Error eliminando inscrito {matricula}: {e}", exc_info=True)
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
            logger.error(f"Error eliminando estudiante {matricula}: {e}", exc_info=True)
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
            logger.error(f"Error eliminando egresado {matricula}: {e}", exc_info=True)
            return False
    
    def agregar_inscrito(self, inscrito_data):
        """Agregar nuevo inscrito"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
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
                    inscrito_data.get('fecha_nacimiento', None),
                    inscrito_data.get('como_se_entero', ''),
                    inscrito_data.get('documentos_subidos', 0),
                    inscrito_data.get('documentos_guardados', '')
                ))
                inscrito_id = cursor.lastrowid
                logger.info(f"Inscrito agregado: {inscrito_data.get('matricula', '')}")
                return inscrito_id
        except Exception as e:
            logger.error(f"Error agregando inscrito: {e}", exc_info=True)
            return None
    
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
            logger.error(f"Error agregando estudiante: {e}", exc_info=True)
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
            logger.error(f"Error agregando egresado: {e}", exc_info=True)
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
            logger.error(f"Error agregando contratado: {e}", exc_info=True)
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
            logger.error(f"Error registrando en bitácora: {e}", exc_info=True)
            return False

# =============================================================================
# INSTANCIA DE BASE DE DATOS
# =============================================================================

db = SistemaBaseDatos()

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

# Instancia global del sistema de autenticación
auth = SistemaAutenticacion()

# =============================================================================
# SISTEMA PRINCIPAL - MEJORADO CON NOTIFICACIONES Y BACKUPS
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
        
        # Estado de paginación
        self.current_page_inscritos = 1
        self.current_page_estudiantes = 1
        self.current_page_egresados = 1
        self.current_page_contratados = 1
        
        # Términos de búsqueda
        self.search_term_inscritos = ""
        self.search_term_estudiantes = ""
        self.search_term_egresados = ""
        self.search_term_contratados = ""
        
        self.cargar_datos_paginados()
        
    def cargar_datos_paginados(self):
        """Cargar datos desde la base de datos con paginación"""
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
                📊 Datos cargados:
                - Inscritos: {self.total_inscritos} registros (página {self.current_page_inscritos}/{self.total_pages_inscritos})
                - Estudiantes: {self.total_estudiantes} registros (página {self.current_page_estudiantes}/{self.total_pages_estudiantes})
                - Egresados: {self.total_egresados} registros (página {self.current_page_egresados}/{self.total_pages_egresados})
                - Contratados: {self.total_contratados} registros (página {self.current_page_contratados}/{self.total_pages_contratados})
                """)
                
        except Exception as e:
            logger.error(f"Error cargando datos: {e}", exc_info=True)
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
# INTERFAZ PRINCIPAL - MEJORADA CON PAGINACIÓN
# =============================================================================

def mostrar_login():
    """Interfaz de login - SIEMPRE MOSTRAR FORMULARIO"""
    st.title("🏥 Sistema Escuela Enfermería - Administración SSH REMOTA")
    st.markdown("---")
    
    # Mostrar estado actual
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
        # Verificar espacio en disco
        temp_dir = tempfile.gettempdir()
        espacio_ok, espacio_mb = UtilidadesSistema.verificar_espacio_disco(temp_dir)
        if espacio_ok:
            st.success(f"💾 Espacio: {espacio_mb:.0f} MB")
        else:
            st.warning(f"💾 Espacio: {espacio_mb:.0f} MB")
    
    st.markdown("---")
    
    # SIEMPRE mostrar formulario de login
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
                inicializar_button = st.form_submit_button("🔄 Inicializar DB", use_container_width=True, type="secondary")

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
                    if db.sincronizar_desde_remoto():
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
                
                **Verificación del sistema:**
                - ✅ SSH debe estar conectado
                - ✅ Base de datos debe estar inicializada
                - 💾 Debe haber suficiente espacio en disco
                """)

# Declarar la variable global aquí, antes de cualquier función que la use
sistema_principal = None

def mostrar_interfaz_principal():
    """Interfaz principal después del login"""
    # Declarar global primero
    global sistema_principal
    
    # Barra superior con información del usuario
    usuario_actual = st.session_state.usuario_actual
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

    with col1:
        st.title("🏥 Sistema Escuela Enfermería - Administración SSH REMOTA")
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

    # Crear instancia del sistema principal si no existe
    if sistema_principal is None:
        sistema_principal = SistemaPrincipal()

    # Menú de navegación
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

    # Mostrar contenido según opción seleccionada
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
    st.header("📊 Dashboard")
    
    if sistema_principal is None:
        st.error("❌ Sistema principal no inicializado")
        return
    
    # Métricas principales
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
    
    # Gráficos y estadísticas
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📈 Distribución por Categoría")
        
        # Crear gráfico de pastel
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
        st.subheader("🔗 Estado del Sistema")
        
        # Estado de conexión SSH
        if estado_sistema.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
            if gestor_remoto.config.get('host'):
                st.info(f"Servidor: {gestor_remoto.config['host']}")
        else:
            st.error("❌ SSH Desconectado")
        
        # Última sincronización
        ultima_sync = estado_sistema.estado.get('ultima_sincronizacion')
        if ultima_sync:
            try:
                fecha_sync = datetime.fromisoformat(ultima_sync)
                st.info(f"🔄 Última sincronización: {fecha_sync.strftime('%Y-%m-%d %H:%M')}")
            except:
                pass
        
        # Espacio en disco
        temp_dir = tempfile.gettempdir()
        espacio_ok, espacio_mb = UtilidadesSistema.verificar_espacio_disco(temp_dir)
        if espacio_ok:
            st.success(f"💾 Espacio disponible: {espacio_mb:.0f} MB")
        else:
            st.warning(f"💾 Espacio bajo: {espacio_mb:.0f} MB")
        
        # Backups disponibles
        backups = sistema_principal.backup_system.listar_backups()
        if backups:
            st.success(f"💾 {len(backups)} backups disponibles")
        else:
            st.info("💾 No hay backups")
    
    # Acciones rápidas
    st.markdown("---")
    st.subheader("🚀 Acciones Rápidas")
    
    col_act1, col_act2, col_act3, col_act4 = st.columns(4)
    
    with col_act1:
        if st.button("📥 Sincronizar Ahora", use_container_width=True):
            with st.spinner("Sincronizando..."):
                if db.sincronizar_desde_remoto():
                    sistema_principal.cargar_datos_paginados()
                    st.success("✅ Sincronización exitosa")
                    st.rerun()
                else:
                    st.error("❌ Error sincronizando")
    
    with col_act2:
        if st.button("💾 Crear Backup", use_container_width=True):
            with st.spinner("Creando backup..."):
                backup_path = sistema_principal.backup_system.crear_backup(
                    "MANUAL_DASHBOARD",
                    "Backup manual creado desde dashboard"
                )
                if backup_path:
                    st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                else:
                    st.error("❌ Error creando backup")
    
    with col_act3:
        if st.button("🔗 Probar Conexión", use_container_width=True):
            with st.spinner("Probando conexión SSH..."):
                if gestor_remoto.verificar_conexion_ssh():
                    st.success("✅ Conexión SSH exitosa")
                    st.rerun()
                else:
                    st.error("❌ Conexión SSH fallida")
    
    with col_act4:
        if st.button("📊 Ver Tablas", use_container_width=True):
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tablas = cursor.fetchall()
                    
                    if tablas:
                        st.success(f"✅ {len(tablas)} tablas en base de datos:")
                        for tabla in tablas:
                            cursor.execute(f"SELECT COUNT(*) FROM {tabla[0]}")
                            count = cursor.fetchone()[0]
                            st.write(f"- **{tabla[0]}**: {count} registros")
                    else:
                        st.error("❌ No hay tablas en la base de datos")
            except Exception as e:
                st.error(f"❌ Error: {e}")

def mostrar_inscritos():
    """Interfaz para gestión de inscritos con paginación"""
    global sistema_principal
    st.header("📝 Gestión de Inscritos")
    
    if sistema_principal is None:
        st.error("❌ Sistema principal no inicializado")
        return
    
    # Crear pestañas
    tab1, tab2 = st.tabs(["📋 Lista de Inscritos", "➕ Agregar Inscrito"])
    
    with tab1:
        if sistema_principal.total_inscritos == 0:
            st.warning("📭 No hay inscritos registrados")
        else:
            # Mostrar estadísticas
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            
            with col_stat1:
                st.metric("Total Inscritos", sistema_principal.total_inscritos)
            
            with col_stat2:
                st.metric("Página Actual", f"{sistema_principal.current_page_inscritos}/{max(1, sistema_principal.total_pages_inscritos)}")
            
            with col_stat3:
                registros_pagina = len(sistema_principal.df_inscritos)
                st.metric("En esta página", registros_pagina)
            
            # Barra de búsqueda
            st.subheader("🔍 Buscar Inscrito")
            search_term = st.text_input(
                "Buscar por matrícula, nombre o email:", 
                value=sistema_principal.search_term_inscritos,
                key="search_inscritos_tabla"
            )
            
            if search_term != sistema_principal.search_term_inscritos:
                sistema_principal.search_term_inscritos = search_term
                sistema_principal.current_page_inscritos = 1
                sistema_principal.cargar_datos_paginados()
                st.rerun()
            
            # Mostrar tabla de inscritos
            if not sistema_principal.df_inscritos.empty:
                st.dataframe(
                    sistema_principal.df_inscritos,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("ℹ️ No hay inscritos que coincidan con la búsqueda")
            
            # Controles de paginación
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
            col1, col2 = st.columns(2)
            
            with col1:
                matricula = st.text_input("Matrícula*", placeholder="MAT-INS-001")
                nombre_completo = st.text_input("Nombre Completo*", placeholder="Juan Pérez")
                email = st.text_input("Email*", placeholder="juan@ejemplo.com")
                telefono = st.text_input("Teléfono", placeholder="+52 123 456 7890")
                programa_interes = st.text_input("Programa de Interés*", placeholder="Especialidad en Enfermería Cardiovascular")
            
            with col2:
                fecha_nacimiento = st.date_input("Fecha de Nacimiento", value=datetime.now() - timedelta(days=365*25))
                como_se_entero = st.selectbox("¿Cómo se enteró del programa?", 
                                           ["Internet", "Redes Sociales", "Amigo/Familiar", "Publicidad", "Evento", "Otro"])
                folio = st.text_input("Folio", placeholder="FOL-2024001")
                documentos_subidos = st.number_input("Documentos Subidos", min_value=0, max_value=10, value=0)
                estatus = st.selectbox("Estatus", ["Pre-inscrito", "En revisión", "Aceptado", "Rechazado"])
            
            submitted = st.form_submit_button("💾 Guardar Inscrito")
            
            if submitted:
                # Validaciones
                if not matricula or not nombre_completo or not email or not programa_interes:
                    st.error("❌ Los campos marcados con * son obligatorios")
                elif not ValidadorDatos.validar_email(email):
                    st.error("❌ Formato de email inválido")
                elif not ValidadorDatos.validar_matricula(matricula):
                    st.error("❌ Formato de matrícula inválido")
                else:
                    # Crear backup antes de la operación
                    backup_info = f"Agregar inscrito: {matricula} - {nombre_completo}"
                    
                    with st.spinner("🔄 Creando backup..."):
                        backup_path = sistema_principal.backup_system.crear_backup(
                            "AGREGAR_INSCRITO", 
                            backup_info
                        )
                    
                    # Guardar inscrito
                    inscrito_data = {
                        'matricula': matricula,
                        'nombre_completo': nombre_completo,
                        'email': email,
                        'telefono': telefono,
                        'programa_interes': programa_interes,
                        'fecha_registro': datetime.now(),
                        'estatus': estatus,
                        'folio': folio,
                        'fecha_nacimiento': fecha_nacimiento,
                        'como_se_entero': como_se_entero,
                        'documentos_subidos': documentos_subidos,
                        'documentos_guardados': f"doc_{matricula}"
                    }
                    
                    with st.spinner("Guardando inscrito..."):
                        inscrito_id = db.agregar_inscrito(inscrito_data)
                        
                        if inscrito_id:
                            # Sincronizar con servidor remoto
                            if db.sincronizar_hacia_remoto():
                                # Registrar en bitácora
                                db.registrar_bitacora(
                                    st.session_state.usuario_actual.get('usuario', 'admin'),
                                    'AGREGAR_INSCRITO',
                                    f'Inscrito agregado: {matricula} - {nombre_completo}'
                                )
                                
                                # Enviar notificación
                                sistema_principal.notificaciones.enviar_notificacion(
                                    tipo_operacion="AGREGAR_INSCRITO",
                                    estado="EXITOSA",
                                    detalles=f"Inscrito agregado exitosamente:\nMatrícula: {matricula}\nNombre: {nombre_completo}\nEmail: {email}"
                                )
                                
                                st.success(f"✅ Inscrito agregado exitosamente: {matricula}")
                                st.balloons()
                                
                                # Recargar datos
                                sistema_principal.cargar_datos_paginados()
                                st.rerun()
                            else:
                                st.error("❌ Error sincronizando con servidor")
                        else:
                            st.error("❌ Error al agregar inscrito")

def mostrar_estudiantes():
    """Interfaz para gestión de estudiantes con paginación"""
    global sistema_principal
    st.header("🎓 Gestión de Estudiantes")
    
    if sistema_principal is None:
        st.error("❌ Sistema principal no inicializado")
        return
    
    # Crear pestañas
    tab1, tab2 = st.tabs(["📋 Lista de Estudiantes", "➕ Agregar Estudiante"])
    
    with tab1:
        if sistema_principal.total_estudiantes == 0:
            st.warning("📭 No hay estudiantes registrados")
        else:
            # Mostrar estadísticas
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            
            with col_stat1:
                st.metric("Total Estudiantes", sistema_principal.total_estudiantes)
            
            with col_stat2:
                st.metric("Página Actual", f"{sistema_principal.current_page_estudiantes}/{max(1, sistema_principal.total_pages_estudiantes)}")
            
            with col_stat3:
                registros_pagina = len(sistema_principal.df_estudiantes)
                st.metric("En esta página", registros_pagina)
            
            # Barra de búsqueda
            st.subheader("🔍 Buscar Estudiante")
            search_term = st.text_input(
                "Buscar por matrícula, nombre o email:", 
                value=sistema_principal.search_term_estudiantes,
                key="search_estudiantes_tabla"
            )
            
            if search_term != sistema_principal.search_term_estudiantes:
                sistema_principal.search_term_estudiantes = search_term
                sistema_principal.current_page_estudiantes = 1
                sistema_principal.cargar_datos_paginados()
                st.rerun()
            
            # Mostrar tabla de estudiantes
            if not sistema_principal.df_estudiantes.empty:
                st.dataframe(
                    sistema_principal.df_estudiantes,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("ℹ️ No hay estudiantes que coincidan con la búsqueda")
            
            # Controles de paginación
            col_prev, col_page, col_next = st.columns([1, 2, 1])
            
            with col_prev:
                if sistema_principal.current_page_estudiantes > 1:
                    if st.button("⬅️ Página Anterior", use_container_width=True):
                        sistema_principal.current_page_estudiantes -= 1
                        sistema_principal.cargar_datos_paginados()
                        st.rerun()
            
            with col_page:
                st.write(f"**Página {sistema_principal.current_page_estudiantes} de {max(1, sistema_principal.total_pages_estudiantes)}**")
            
            with col_next:
                if sistema_principal.current_page_estudiantes < sistema_principal.total_pages_estudiantes:
                    if st.button("Página Siguiente ➡️", use_container_width=True):
                        sistema_principal.current_page_estudiantes += 1
                        sistema_principal.cargar_datos_paginados()
                        st.rerun()
    
    with tab2:
        st.subheader("➕ Agregar Nuevo Estudiante")
        
        with st.form("form_agregar_estudiante"):
            col1, col2 = st.columns(2)
            
            with col1:
                matricula = st.text_input("Matrícula*", placeholder="MAT-EST-001")
                nombre_completo = st.text_input("Nombre Completo*", placeholder="Juan Pérez")
                email = st.text_input("Email*", placeholder="juan@ejemplo.com")
                telefono = st.text_input("Teléfono", placeholder="+52 123 456 7890")
                programa = st.text_input("Programa*", placeholder="Especialidad en Enfermería Cardiovascular")
                fecha_nacimiento = st.date_input("Fecha de Nacimiento", value=datetime.now() - timedelta(days=365*25))
            
            with col2:
                genero = st.selectbox("Género", ["Masculino", "Femenino", "Otro", "Prefiero no decir"])
                fecha_ingreso = st.date_input("Fecha de Ingreso*", value=datetime.now())
                estatus = st.selectbox("Estatus*", ["ACTIVO", "INACTIVO", "PENDIENTE"], index=0)
                documentos_subidos = st.text_input("Documentos Subidos", placeholder="CURP, INE, Título")
                programa_interes = st.text_input("Programa de Interés", placeholder="Especialidad en Enfermería Cardiovascular")
                folio = st.text_input("Folio", placeholder="FOL-2024001")
            
            submitted = st.form_submit_button("💾 Guardar Estudiante")
            
            if submitted:
                # Validaciones
                if not matricula or not nombre_completo or not email or not programa or not fecha_ingreso or not estatus:
                    st.error("❌ Los campos marcados con * son obligatorios")
                elif not ValidadorDatos.validar_email(email):
                    st.error("❌ Formato de email inválido")
                elif not ValidadorDatos.validar_matricula(matricula):
                    st.error("❌ Formato de matrícula inválido")
                else:
                    # Crear backup antes de la operación
                    backup_info = f"Agregar estudiante: {matricula} - {nombre_completo}"
                    
                    with st.spinner("🔄 Creando backup..."):
                        backup_path = sistema_principal.backup_system.crear_backup(
                            "AGREGAR_ESTUDIANTE", 
                            backup_info
                        )
                    
                    # Guardar estudiante
                    estudiante_data = {
                        'matricula': matricula,
                        'nombre_completo': nombre_completo,
                        'programa': programa,
                        'email': email,
                        'telefono': telefono,
                        'fecha_nacimiento': fecha_nacimiento,
                        'genero': genero,
                        'fecha_inscripcion': datetime.now(),
                        'estatus': estatus,
                        'documentos_subidos': documentos_subidos,
                        'fecha_registro': datetime.now(),
                        'programa_interes': programa_interes,
                        'folio': folio,
                        'como_se_entero': '',
                        'fecha_ingreso': fecha_ingreso,
                        'usuario': matricula
                    }
                    
                    with st.spinner("Guardando estudiante..."):
                        estudiante_id = db.agregar_estudiante(estudiante_data)
                        
                        if estudiante_id:
                            # Sincronizar con servidor remoto
                            if db.sincronizar_hacia_remoto():
                                # Registrar en bitácora
                                db.registrar_bitacora(
                                    st.session_state.usuario_actual.get('usuario', 'admin'),
                                    'AGREGAR_ESTUDIANTE',
                                    f'Estudiante agregado: {matricula} - {nombre_completo}'
                                )
                                
                                # Enviar notificación
                                sistema_principal.notificaciones.enviar_notificacion(
                                    tipo_operacion="AGREGAR_ESTUDIANTE",
                                    estado="EXITOSA",
                                    detalles=f"Estudiante agregado exitosamente:\nMatrícula: {matricula}\nNombre: {nombre_completo}\nPrograma: {programa}"
                                )
                                
                                st.success(f"✅ Estudiante agregado exitosamente: {matricula}")
                                st.balloons()
                                
                                # Recargar datos
                                sistema_principal.cargar_datos_paginados()
                                st.rerun()
                            else:
                                st.error("❌ Error sincronizando con servidor")
                        else:
                            st.error("❌ Error al agregar estudiante")

def mostrar_egresados():
    """Interfaz para gestión de egresados con paginación"""
    global sistema_principal
    st.header("🏆 Gestión de Egresados")
    
    if sistema_principal is None:
        st.error("❌ Sistema principal no inicializado")
        return
    
    # Crear pestañas
    tab1, tab2 = st.tabs(["📋 Lista de Egresados", "➕ Agregar Egresado"])
    
    with tab1:
        if sistema_principal.total_egresados == 0:
            st.warning("📭 No hay egresados registrados")
        else:
            # Mostrar estadísticas
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            
            with col_stat1:
                st.metric("Total Egresados", sistema_principal.total_egresados)
            
            with col_stat2:
                st.metric("Página Actual", f"{sistema_principal.current_page_egresados}/{max(1, sistema_principal.total_pages_egresados)}")
            
            with col_stat3:
                registros_pagina = len(sistema_principal.df_egresados)
                st.metric("En esta página", registros_pagina)
            
            # Barra de búsqueda
            st.subheader("🔍 Buscar Egresado")
            search_term = st.text_input(
                "Buscar por matrícula, nombre o email:", 
                value=sistema_principal.search_term_egresados,
                key="search_egresados_tabla"
            )
            
            if search_term != sistema_principal.search_term_egresados:
                sistema_principal.search_term_egresados = search_term
                sistema_principal.current_page_egresados = 1
                sistema_principal.cargar_datos_paginados()
                st.rerun()
            
            # Mostrar tabla de egresados
            if not sistema_principal.df_egresados.empty:
                st.dataframe(
                    sistema_principal.df_egresados,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("ℹ️ No hay egresados que coincidan con la búsqueda")
            
            # Controles de paginación
            col_prev, col_page, col_next = st.columns([1, 2, 1])
            
            with col_prev:
                if sistema_principal.current_page_egresados > 1:
                    if st.button("⬅️ Página Anterior", use_container_width=True):
                        sistema_principal.current_page_egresados -= 1
                        sistema_principal.cargar_datos_paginados()
                        st.rerun()
            
            with col_page:
                st.write(f"**Página {sistema_principal.current_page_egresados} de {max(1, sistema_principal.total_pages_egresados)}**")
            
            with col_next:
                if sistema_principal.current_page_egresados < sistema_principal.total_pages_egresados:
                    if st.button("Página Siguiente ➡️", use_container_width=True):
                        sistema_principal.current_page_egresados += 1
                        sistema_principal.cargar_datos_paginados()
                        st.rerun()
    
    with tab2:
        st.subheader("➕ Agregar Nuevo Egresado")
        
        with st.form("form_agregar_egresado"):
            col1, col2 = st.columns(2)
            
            with col1:
                matricula = st.text_input("Matrícula*", placeholder="MAT-EGR-001")
                nombre_completo = st.text_input("Nombre Completo*", placeholder="Juan Pérez")
                email = st.text_input("Email*", placeholder="juan@ejemplo.com")
                telefono = st.text_input("Teléfono", placeholder="+52 123 456 7890")
                programa_original = st.text_input("Programa Original*", placeholder="Especialidad en Enfermería Cardiovascular")
                fecha_graduacion = st.date_input("Fecha de Graduación*", value=datetime.now())
            
            with col2:
                nivel_academico = st.selectbox("Nivel Académico*", ["Especialidad", "Maestría", "Doctorado", "Diplomado"], index=0)
                estado_laboral = st.selectbox("Estado Laboral*", ["Contratada", "Buscando empleo", "Empleado independiente", "Estudiando", "Otro"], index=0)
                documentos_subidos = st.text_input("Documentos Subidos", placeholder="Cédula Profesional, Título")
                
            submitted = st.form_submit_button("💾 Guardar Egresado")
            
            if submitted:
                # Validaciones
                if not matricula or not nombre_completo or not email or not programa_original or not fecha_graduacion or not nivel_academico or not estado_laboral:
                    st.error("❌ Los campos marcados con * son obligatorios")
                elif not ValidadorDatos.validar_email(email):
                    st.error("❌ Formato de email inválido")
                elif not ValidadorDatos.validar_matricula(matricula):
                    st.error("❌ Formato de matrícula inválido")
                else:
                    # Crear backup antes de la operación
                    backup_info = f"Agregar egresado: {matricula} - {nombre_completo}"
                    
                    with st.spinner("🔄 Creando backup..."):
                        backup_path = sistema_principal.backup_system.crear_backup(
                            "AGREGAR_EGRESADO", 
                            backup_info
                        )
                    
                    # Guardar egresado
                    egresado_data = {
                        'matricula': matricula,
                        'nombre_completo': nombre_completo,
                        'programa_original': programa_original,
                        'fecha_graduacion': fecha_graduacion,
                        'nivel_academico': nivel_academico,
                        'email': email,
                        'telefono': telefono,
                        'estado_laboral': estado_laboral,
                        'fecha_actualizacion': datetime.now(),
                        'documentos_subidos': documentos_subidos
                    }
                    
                    with st.spinner("Guardando egresado..."):
                        egresado_id = db.agregar_egresado(egresado_data)
                        
                        if egresado_id:
                            # Sincronizar con servidor remoto
                            if db.sincronizar_hacia_remoto():
                                # Registrar en bitácora
                                db.registrar_bitacora(
                                    st.session_state.usuario_actual.get('usuario', 'admin'),
                                    'AGREGAR_EGRESADO',
                                    f'Egresado agregado: {matricula} - {nombre_completo}'
                                )
                                
                                # Enviar notificación
                                sistema_principal.notificaciones.enviar_notificacion(
                                    tipo_operacion="AGREGAR_EGRESADO",
                                    estado="EXITOSA",
                                    detalles=f"Egresado agregado exitosamente:\nMatrícula: {matricula}\nNombre: {nombre_completo}\nPrograma: {programa_original}"
                                )
                                
                                st.success(f"✅ Egresado agregado exitosamente: {matricula}")
                                st.balloons()
                                
                                # Recargar datos
                                sistema_principal.cargar_datos_paginados()
                                st.rerun()
                            else:
                                st.error("❌ Error sincronizando con servidor")
                        else:
                            st.error("❌ Error al agregar egresado")

def mostrar_contratados():
    """Interfaz para gestión de contratados con paginación"""
    global sistema_principal
    st.header("💼 Gestión de Contratados")
    
    if sistema_principal is None:
        st.error("❌ Sistema principal no inicializado")
        return
    
    # Crear pestañas
    tab1, tab2 = st.tabs(["📋 Lista de Contratados", "➕ Agregar Contratado"])
    
    with tab1:
        if sistema_principal.total_contratados == 0:
            st.warning("📭 No hay contratados registrados")
        else:
            # Mostrar estadísticas
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            
            with col_stat1:
                st.metric("Total Contratados", sistema_principal.total_contratados)
            
            with col_stat2:
                st.metric("Página Actual", f"{sistema_principal.current_page_contratados}/{max(1, sistema_principal.total_pages_contratados)}")
            
            with col_stat3:
                registros_pagina = len(sistema_principal.df_contratados)
                st.metric("En esta página", registros_pagina)
            
            # Barra de búsqueda
            st.subheader("🔍 Buscar Contratado")
            search_term = st.text_input(
                "Buscar por matrícula, nombre o email:", 
                value=sistema_principal.search_term_contratados,
                key="search_contratados_tabla"
            )
            
            if search_term != sistema_principal.search_term_contratados:
                sistema_principal.search_term_contratados = search_term
                sistema_principal.current_page_contratados = 1
                sistema_principal.cargar_datos_paginados()
                st.rerun()
            
            # Mostrar tabla de contratados
            if not sistema_principal.df_contratados.empty:
                st.dataframe(
                    sistema_principal.df_contratados,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("ℹ️ No hay contratados que coincidan con la búsqueda")
            
            # Controles de paginación
            col_prev, col_page, col_next = st.columns([1, 2, 1])
            
            with col_prev:
                if sistema_principal.current_page_contratados > 1:
                    if st.button("⬅️ Página Anterior", use_container_width=True):
                        sistema_principal.current_page_contratados -= 1
                        sistema_principal.cargar_datos_paginados()
                        st.rerun()
            
            with col_page:
                st.write(f"**Página {sistema_principal.current_page_contratados} de {max(1, sistema_principal.total_pages_contratados)}**")
            
            with col_next:
                if sistema_principal.current_page_contratados < sistema_principal.total_pages_contratados:
                    if st.button("Página Siguiente ➡️", use_container_width=True):
                        sistema_principal.current_page_contratados += 1
                        sistema_principal.cargar_datos_paginados()
                        st.rerun()
    
    with tab2:
        st.subheader("➕ Agregar Nuevo Contratado")
        
        with st.form("form_agregar_contratado"):
            col1, col2 = st.columns(2)
            
            with col1:
                matricula = st.text_input("Matrícula*", placeholder="MAT-CON-001")
                fecha_contratacion = st.date_input("Fecha de Contratación*", value=datetime.now())
                puesto = st.text_input("Puesto*", placeholder="Enfermera Especialista en Cardiología")
                departamento = st.text_input("Departamento*", placeholder="Terapia Intensiva Cardiovascular")
                estatus = st.selectbox("Estatus*", ["Activo", "Inactivo", "Licencia", "Baja"], index=0)
            
            with col2:
                salario = st.text_input("Salario*", placeholder="25000 MXN")
                tipo_contrato = st.selectbox("Tipo de Contrato*", ["Tiempo completo", "Medio tiempo", "Por honorarios", "Temporal"], index=0)
                fecha_inicio = st.date_input("Fecha Inicio*", value=datetime.now())
                fecha_fin = st.date_input("Fecha Fin*", value=datetime.now() + timedelta(days=365))
                documentos_subidos = st.text_input("Documentos Subidos", placeholder="Identificación Oficial, CURP")
                
            submitted = st.form_submit_button("💾 Guardar Contratado")
            
            if submitted:
                # Validaciones
                if not matricula or not puesto or not departamento or not estatus or not salario or not tipo_contrato:
                    st.error("❌ Los campos marcados con * son obligatorios")
                elif not ValidadorDatos.validar_matricula(matricula):
                    st.error("❌ Formato de matrícula inválido")
                else:
                    # Crear backup antes de la operación
                    backup_info = f"Agregar contratado: {matricula} - {puesto}"
                    
                    with st.spinner("🔄 Creando backup..."):
                        backup_path = sistema_principal.backup_system.crear_backup(
                            "AGREGAR_CONTRATADO", 
                            backup_info
                        )
                    
                    # Guardar contratado
                    contratado_data = {
                        'matricula': matricula,
                        'fecha_contratacion': fecha_contratacion,
                        'puesto': puesto,
                        'departamento': departamento,
                        'estatus': estatus,
                        'salario': salario,
                        'tipo_contrato': tipo_contrato,
                        'fecha_inicio': fecha_inicio,
                        'fecha_fin': fecha_fin,
                        'documentos_subidos': documentos_subidos
                    }
                    
                    with st.spinner("Guardando contratado..."):
                        contratado_id = db.agregar_contratado(contratado_data)
                        
                        if contratado_id:
                            # Sincronizar con servidor remoto
                            if db.sincronizar_hacia_remoto():
                                # Registrar en bitácora
                                db.registrar_bitacora(
                                    st.session_state.usuario_actual.get('usuario', 'admin'),
                                    'AGREGAR_CONTRATADO',
                                    f'Contratado agregado: {matricula} - {puesto}'
                                )
                                
                                # Enviar notificación
                                sistema_principal.notificaciones.enviar_notificacion(
                                    tipo_operacion="AGREGAR_CONTRATADO",
                                    estado="EXITOSA",
                                    detalles=f"Contratado agregado exitosamente:\nMatrícula: {matricula}\nPuesto: {puesto}\nDepartamento: {departamento}"
                                )
                                
                                st.success(f"✅ Contratado agregado exitosamente: {matricula}")
                                st.balloons()
                                
                                # Recargar datos
                                sistema_principal.cargar_datos_paginados()
                                st.rerun()
                            else:
                                st.error("❌ Error sincronizando con servidor")
                        else:
                            st.error("❌ Error al agregar contratado")

def mostrar_usuarios():
    """Interfaz para gestión de usuarios"""
    global sistema_principal
    st.header("👥 Gestión de Usuarios")
    
    if sistema_principal is None:
        st.error("❌ Sistema principal no inicializado")
        return
    
    try:
        # Obtener usuarios
        df_usuarios, total_pages, total_usuarios = db.obtener_usuarios(page=1)
        
        if total_usuarios == 0:
            st.warning("📭 No hay usuarios registrados")
            return
        
        # Mostrar tabla de usuarios
        st.subheader("📋 Lista de Usuarios")
        st.dataframe(
            df_usuarios[['usuario', 'nombre_completo', 'rol', 'email', 'matricula', 'activo']],
            use_container_width=True,
            hide_index=True
        )
        
        # Información de seguridad
        with st.expander("🔐 Información de Seguridad"):
            st.info("""
            **Características de seguridad implementadas:**
            
            ✅ **BCRYPT** para hash de contraseñas
            ✅ **Salt único** por usuario
            ✅ **Roles de usuario** (administrador, usuario)
            ✅ **Registro de bitácora** de todas las operaciones
            ✅ **Contraseñas nunca** se muestran en texto claro
            
            **Credenciales por defecto (admin):**
            - Usuario: `admin`
            - Contraseña: `Admin123!`
            - Rol: `administrador`
            """)
        
    except Exception as e:
        st.error(f"❌ Error obteniendo usuarios: {e}")

def mostrar_configuracion():
    """Interfaz para configuración del sistema"""
    global sistema_principal
    st.header("⚙️ Configuración del Sistema")
    
    if sistema_principal is None:
        st.error("❌ Sistema principal no inicializado")
        return
    
    # Información del sistema
    st.subheader("🔧 Información del Sistema")
    
    col_info1, col_info2 = st.columns(2)
    
    with col_info1:
        st.write("**📊 Estado del Sistema:**")
        if estado_sistema.esta_inicializada():
            st.success("✅ Base de datos inicializada")
            fecha_inicializacion = estado_sistema.obtener_fecha_inicializacion()
            if fecha_inicializacion:
                st.write(f"📅 Fecha inicialización: {fecha_inicializacion.strftime('%Y-%m-%d %H:%M')}")
        else:
            st.warning("⚠️ Base de datos NO inicializada")
        
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
        st.write("**💾 Recursos del Sistema:**")
        
        # Espacio en disco
        temp_dir = tempfile.gettempdir()
        espacio_ok, espacio_mb = UtilidadesSistema.verificar_espacio_disco(temp_dir)
        
        if espacio_ok:
            st.success(f"✅ Espacio disponible: {espacio_mb:.0f} MB")
        else:
            st.warning(f"⚠️ Espacio bajo: {espacio_mb:.0f} MB")
        
        # Backups disponibles
        backups = sistema_principal.backup_system.listar_backups()
        if backups:
            st.success(f"✅ {len(backups)} backups disponibles")
        else:
            st.info("ℹ️ No hay backups")
        
        # Estadísticas
        stats = estado_sistema.estado.get('estadisticas_sistema', {})
        st.write(f"📈 Sesiones exitosas: {stats.get('sesiones', 0)}")
        st.write(f"🔄 Backups realizados: {estado_sistema.estado.get('backups_realizados', 0)}")
    
    # Controles del sistema
    st.markdown("---")
    st.subheader("🎮 Controles del Sistema")
    
    col_control1, col_control2, col_control3 = st.columns(3)
    
    with col_control1:
        if st.button("🔄 Sincronizar Ahora", use_container_width=True):
            with st.spinner("Sincronizando con servidor remoto..."):
                if db.sincronizar_desde_remoto():
                    sistema_principal.cargar_datos_paginados()
                    st.success("✅ Sincronización exitosa")
                    st.rerun()
                else:
                    st.error("❌ Error sincronizando")
    
    with col_control2:
        if st.button("🔗 Probar Conexión SSH", use_container_width=True):
            with st.spinner("Probando conexión SSH..."):
                if gestor_remoto.verificar_conexion_ssh():
                    st.success("✅ Conexión SSH exitosa")
                    st.rerun()
                else:
                    st.error("❌ Conexión SSH fallida")
    
    with col_control3:
        if st.button("💾 Crear Backup Manual", use_container_width=True):
            with st.spinner("Creando backup..."):
                backup_path = sistema_principal.backup_system.crear_backup(
                    "MANUAL_CONFIG",
                    "Backup manual creado desde configuración"
                )
                if backup_path:
                    st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                else:
                    st.error("❌ Error creando backup")
    
    # Información de configuración
    st.markdown("---")
    st.subheader("📋 Información de Configuración")
    
    with st.expander("🔍 Ver Configuración SSH"):
        if gestor_remoto.config:
            config_show = gestor_remoto.config.copy()
            # Ocultar contraseñas para seguridad
            if 'password' in config_show:
                config_show['password'] = '********'
            if 'smtp' in config_show and 'email_password' in config_show['smtp']:
                config_show['smtp']['email_password'] = '********'
            
            st.json(config_show)
        else:
            st.error("❌ No hay configuración SSH cargada")
    
    # Logs del sistema
    with st.expander("📝 Ver Logs del Sistema"):
        if os.path.exists('escuela_detallado.log'):
            with open('escuela_detallado.log', 'r') as f:
                lines = f.readlines()[-50:]  # Últimas 50 líneas
                st.text_area("Últimas líneas del log:", ''.join(lines), height=300)
        else:
            st.warning("No se encontró archivo de log")
    
    # Estado persistente
    with st.expander("💾 Ver Estado Persistente"):
        st.json(estado_sistema.estado)

# =============================================================================
# FUNCIÓN PRINCIPAL - MEJORADA CON MANEJO ROBUSTO DE ERRORES
# =============================================================================

def main():
    """Función principal de la aplicación"""
    
    # Sidebar con estado del sistema
    with st.sidebar:
        st.title("🔧 Sistema Escuela")
        st.markdown("---")
        
        st.subheader("🔗 Estado de Conexión SSH")
        
        # Estado de inicialización
        if estado_sistema.esta_inicializada():
            st.success("✅ Base de datos remota inicializada")
            fecha_inicializacion = estado_sistema.obtener_fecha_inicializacion()
            if fecha_inicializacion:
                st.caption(f"📅 Inicializada: {fecha_inicializacion.strftime('%Y-%m-%d %H:%M')}")
        else:
            st.warning("⚠️ Base de datos NO inicializada")
        
        # Estado de conexión SSH
        if estado_sistema.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
            if gestor_remoto.config.get('host'):
                st.caption(f"🌐 Servidor: {gestor_remoto.config['host']}")
        else:
            st.error("❌ SSH Desconectado")
            error_ssh = estado_sistema.estado.get('ssh_error')
            if error_ssh:
                st.caption(f"⚠️ Error: {error_ssh}")
        
        # Verificación de espacio en disco
        st.subheader("💾 Estado del Sistema")
        temp_dir = tempfile.gettempdir()
        espacio_ok, espacio_mb = UtilidadesSistema.verificar_espacio_disco(temp_dir)
        
        if espacio_ok:
            st.success(f"Espacio disponible: {espacio_mb:.0f} MB")
        else:
            st.warning(f"Espacio bajo: {espacio_mb:.0f} MB")
        
        # Información del servidor
        with st.expander("📋 Información del Servidor"):
            if gestor_remoto.config.get('host'):
                st.write(f"**Host:** {gestor_remoto.config['host']}")
                st.write(f"**Puerto:** {gestor_remoto.config.get('port', 22)}")
                st.write(f"**Usuario:** {gestor_remoto.config['username']}")
                st.write(f"**Directorio:** {gestor_remoto.config.get('remote_dir', '')}")
                st.write(f"**DB Remota:** {gestor_remoto.config.get('remote_db_escuela', '')}")
        
        st.markdown("---")
        
        # Estadísticas del sistema
        st.subheader("📈 Estadísticas")
        stats = estado_sistema.estado.get('estadisticas_sistema', {})
        
        col_stat1, col_stat2 = st.columns(2)
        with col_stat1:
            st.metric("Sesiones", stats.get('sesiones', 0))
        with col_stat2:
            st.metric("Backups", estado_sistema.estado.get('backups_realizados', 0))
        
        sesiones = estado_sistema.estado.get('sesiones_iniciadas', 0)
        st.metric("Total Sesiones", sesiones)
        
        # Última sincronización
        ultima_sync = estado_sistema.estado.get('ultima_sincronizacion')
        if ultima_sync:
            try:
                fecha_sync = datetime.fromisoformat(ultima_sync)
                st.caption(f"🔄 Última sincronización: {fecha_sync.strftime('%H:%M:%S')}")
            except:
                pass
        
        st.markdown("---")
        
        # Sistema de backups
        st.subheader("💾 Sistema de Backups")
        
        # Botón para crear backup manual
        if st.button("💾 Crear Backup Manual", use_container_width=True):
            with st.spinner("Creando backup..."):
                backup_path = sistema_principal.backup_system.crear_backup(
                    "MANUAL",
                    "Backup manual creado desde sidebar"
                )
                if backup_path:
                    st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                else:
                    st.error("❌ Error creando backup")
        
        st.markdown("---")
        
        # Información de versión
        st.caption("🏥 Sistema Escuela Enfermería v2.0")
        st.caption("🔗 Conectado remotamente via SSH")
    
    try:
        # Inicializar estado de sesión con valores por defecto
        session_defaults = {
            'login_exitoso': False,
            'usuario_actual': None,
            'rol_usuario': None
        }
        
        for key, default_value in session_defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default_value
        
        # Verificar configuración SSH
        if not gestor_remoto.config.get('host'):
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
            
            # Mostrar diagnóstico
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
            
            return
        
        # Mostrar interfaz según estado
        if not st.session_state.login_exitoso:
            mostrar_login()
        else:
            mostrar_interfaz_principal()
            
    except Exception as e:
        logger.error(f"Error crítico en main(): {e}", exc_info=True)
        
        st.error(f"❌ Error crítico en la aplicación: {str(e)}")
        
        # Información de diagnóstico
        with st.expander("🔧 Información de diagnóstico detallada"):
            st.write("**Estado persistente:**")
            st.json(estado_sistema.estado)
            
            st.write("**Configuración SSH cargada:**")
            if gestor_remoto.config:
                config_show = gestor_remoto.config.copy()
                # Ocultar contraseñas para seguridad
                if 'password' in config_show:
                    config_show['password'] = '********'
                if 'smtp' in config_show and 'email_password' in config_show['smtp']:
                    config_show['smtp']['email_password'] = '********'
                st.json(config_show)
            else:
                st.write("No hay configuración SSH cargada")
            
            st.write("**Archivos de log:**")
            log_files = []
            for log_file in ['escuela_detallado.log', 'system_operations.json']:
                if os.path.exists(log_file):
                    size = os.path.getsize(log_file)
                    log_files.append(f"{log_file} ({size} bytes)")
                else:
                    log_files.append(f"{log_file} (no existe)")
            
            for log_info in log_files:
                st.write(f"- {log_info}")
        
        # Botón para reinicio seguro
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
                            lines = f.readlines()[-50:]  # Últimas 50 líneas
                            st.text_area("Últimas líneas del log:", ''.join(lines), height=300)
                    else:
                        st.warning("No se encontró archivo de log")
                except Exception as log_error:
                    st.error(f"Error leyendo logs: {log_error}")

# =============================================================================
# EJECUCIÓN PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    try:
        # Mostrar banner informativo
        st.info("""
        🏥 **SISTEMA DE GESTIÓN ESCOLAR EXCLUSIVAMENTE REMOTO - VERSIÓN MEJORADA**
        
        **Mejoras implementadas:**
        ✅ Timeouts específicos para operaciones de red
        ✅ Paginación en tablas para mejor rendimiento  
        ✅ Logs detallados para diagnóstico
        ✅ Backups automáticos antes de operaciones
        ✅ Reintentos inteligentes con backoff exponencial
        ✅ Verificación de espacio en disco
        ✅ Sistema de notificaciones
        
        **Para comenzar:**
        1. Configura secrets.toml con tus credenciales SSH
        2. Haz clic en "Inicializar DB" para crear la base de datos en el servidor
        3. Inicia sesión con las credenciales por defecto
        """)
        
        main()
    except Exception as e:
        st.error(f"❌ Error crítico en la aplicación: {e}")
        logger.critical(f"Error crítico en sistema: {e}", exc_info=True)
        
        # Información de diagnóstico final
        with st.expander("🚨 Información de diagnóstico crítico"):
            st.write("**Traceback completo:**")
            import traceback
            st.code(traceback.format_exc())
            
            st.write("**Variables de entorno:**")
            env_vars = {k: v for k, v in os.environ.items() if 'STREAMLIT' in k or 'PYTHON' in k}
            st.json(env_vars)
