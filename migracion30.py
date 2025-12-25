"""
migracion20.py - Sistema de migración con BCRYPT y SSH
Versión completa mejorada con todas las recomendaciones
Sistema completo de migración con base de datos SQLite remota
NO SOPORTA MODO LOCAL - SIEMPRE CONECTA AL SERVIDOR REMOTO
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
        file_handler = logging.FileHandler('migracion_detallado.log', encoding='utf-8')
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
    
    def log_migration(self, operation, status, details):
        """Log específico para operaciones de migración"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'operation': operation,
            'status': status,
            'details': details
        }
        
        # Guardar en archivo JSON para análisis posterior
        log_file = 'migration_operations.json'
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
            self.error(f"Error guardando log de migración: {e}")

# Instancia global del logger mejorado
logger = EnhancedLogger()

# =============================================================================
# CONFIGURACIÓN DE PÁGINA
# =============================================================================

st.set_page_config(
    page_title="Sistema Escuela Enfermería - Migración SSH REMOTA",
    page_icon="🔄",
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
    """Sistema de backup automático antes de migraciones"""
    
    def __init__(self, gestor_ssh):
        self.gestor_ssh = gestor_ssh
        self.backup_dir = "backups_migracion"
        self.max_backups = 10  # Mantener solo los últimos 10 backups
        
    def crear_backup_pre_migracion(self, tipo_migracion, detalles):
        """Crear backup automático antes de una migración"""
        try:
            # Crear directorio de backups si no existe
            if not os.path.exists(self.backup_dir):
                os.makedirs(self.backup_dir)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_{tipo_migracion}_{timestamp}.zip"
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
                                'tipo_migracion': tipo_migracion,
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
    """Sistema de notificaciones para migraciones exitosas/fallidas"""
    
    def __init__(self, config_smtp):
        self.config_smtp = config_smtp
        self.notificaciones_habilitadas = bool(config_smtp.get('email_user'))
    
    def enviar_notificacion_migracion(self, tipo_migracion, estado, detalles, destinatarios=None):
        """Enviar notificación de migración por email"""
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
            subject = f"[Migración] {tipo_migracion} - {estado}"
            
            # Crear contenido HTML
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2>📊 Notificación de Migración</h2>
                <div style="background-color: {'#d4edda' if estado == 'EXITOSA' else '#f8d7da'}; 
                          padding: 15px; border-radius: 5px; margin: 10px 0;">
                    <h3>Estado: <strong>{estado}</strong></h3>
                    <p><strong>Tipo:</strong> {tipo_migracion}</p>
                    <p><strong>Fecha:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Usuario:</strong> {st.session_state.get('usuario_actual', {}).get('usuario', 'Desconocido')}</p>
                </div>
                
                <h3>📋 Detalles:</h3>
                <div style="background-color: #f8f9fa; padding: 10px; border-left: 4px solid #007bff;">
                    <pre style="white-space: pre-wrap;">{detalles}</pre>
                </div>
                
                <hr>
                <p style="color: #6c757d; font-size: 0.9em;">
                    Sistema de Migración - Escuela de Enfermería<br>
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
            
            logger.info(f"✅ Notificación enviada: {tipo_migracion} - {estado}")
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
# ARCHIVO DE ESTADO PERSISTENTE PARA MIGRACIÓN - MEJORADO
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
                    estado = json.load(f)
                    
                    # Migrar estado antiguo si es necesario
                    if 'estadisticas_migracion' not in estado:
                        estado['estadisticas_migracion'] = {
                            'exitosas': estado.get('migraciones_realizadas', 0),
                            'fallidas': 0,
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
    
    def registrar_migracion(self, exitosa=True, tiempo_ejecucion=0):
        """Registrar una migración"""
        self.estado['migraciones_realizadas'] = self.estado.get('migraciones_realizadas', 0) + 1
        self.estado['ultima_migracion'] = datetime.now().isoformat()
        
        # Estadísticas detalladas
        if exitosa:
            self.estado['estadisticas_migracion']['exitosas'] += 1
        else:
            self.estado['estadisticas_migracion']['fallidas'] += 1
        
        self.estado['estadisticas_migracion']['total_tiempo'] += tiempo_ejecucion
        
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
estado_migracion = EstadoPersistenteMigracion()

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

class GestorConexionRemotaMigracion:
    """Gestor de conexión SSH al servidor remoto para migración - EXCLUSIVAMENTE REMOTO"""
    
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
        
        # Configuración de migración con timeouts específicos
        self.config_migracion = self.config_completa.get('migration', {})
        self.auto_connect = self.config_migracion.get('auto_connect', True)
        self.sync_on_start = self.config_migracion.get('sync_on_start', True)
        self.retry_attempts = self.config_migracion.get('retry_attempts', 3)
        self.retry_delay_base = self.config_migracion.get('retry_delay', 5)
        self.fallback_to_local = self.config_migracion.get('fallback_to_local', False)
        
        # Timeouts específicos para diferentes operaciones
        self.timeouts = {
            'ssh_connect': self.config_migracion.get('ssh_connect_timeout', 30),
            'ssh_command': self.config_migracion.get('ssh_command_timeout', 60),
            'sftp_transfer': self.config_migracion.get('sftp_transfer_timeout', 300),
            'db_download': self.config_migracion.get('db_download_timeout', 180)
        }
        
        # Configuración de base de datos
        self.config_database = self.config_completa.get('database', {})
        self.sync_interval = self.config_database.get('sync_interval', 60)
        self.backup_before_migration = self.config_database.get('backup_before_migration', True)
        
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
        pattern = os.path.join(temp_dir, "migracion_*.db")
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
            estado_migracion.set_ssh_conectado(True, None)
            return True
            
        except socket.timeout:
            error_msg = f"Timeout conectando a {self.config['host']}"
            logger.error(f"❌ {error_msg}")
            estado_migracion.set_ssh_conectado(False, error_msg)
            return False
        except paramiko.AuthenticationException:
            error_msg = "Error de autenticación SSH - Credenciales incorrectas"
            logger.error(f"❌ {error_msg}")
            estado_migracion.set_ssh_conectado(False, error_msg)
            return False
        except Exception as e:
            error_msg = f"Error de conexión SSH: {str(e)}"
            logger.error(f"❌ {error_msg}")
            estado_migracion.set_ssh_conectado(False, error_msg)
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
            
            estado_migracion.set_ssh_conectado(True, None)
            return True
            
        except socket.timeout:
            error_msg = f"Timeout conectando a {self.config['host']}"
            logger.error(f"❌ {error_msg}")
            estado_migracion.set_ssh_conectado(False, error_msg)
            return False
        except paramiko.AuthenticationException:
            error_msg = "Error de autenticación SSH - Credenciales incorrectas"
            logger.error(f"❌ {error_msg}")
            estado_migracion.set_ssh_conectado(False, error_msg)
            return False
        except paramiko.SSHException as ssh_exc:
            error_msg = f"Error SSH: {str(ssh_exc)}"
            logger.error(f"❌ {error_msg}")
            estado_migracion.set_ssh_conectado(False, error_msg)
            return False
        except Exception as e:
            error_msg = f"Error de conexión: {str(e)}"
            logger.error(f"❌ {error_msg}")
            estado_migracion.set_ssh_conectado(False, error_msg)
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
                temp_db_path = os.path.join(temp_dir, f"migracion_temp_{timestamp}.db")
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
        """Verificar integridad de la base de datos SQLite con tablas actualizadas"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Verificar que sea una base de datos SQLite válida
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()[0]
            logger.debug(f"SQLite version: {version}")
            
            # Verificar tablas principales (actualizadas)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tablas = cursor.fetchall()
            
            tablas_esperadas = {
                'usuarios', 'inscritos', 'estudiantes', 'egresados', 
                'contratados', 'bitacora', 'documentos', 'configuracion'
            }
            tablas_encontradas = {t[0] for t in tablas}
            
            # Verificar tablas esenciales
            tablas_esenciales = {'usuarios', 'inscritos', 'estudiantes', 'egresados', 'contratados'}
            tablas_faltantes = tablas_esenciales - tablas_encontradas
            
            if tablas_faltantes:
                logger.warning(f"Faltan tablas esenciales: {tablas_faltantes}")
                return False
            
            # Verificar columnas básicas en cada tabla
            tablas_a_verificar = {
                'usuarios': ['usuario', 'password_hash', 'rol'],
                'inscritos': ['matricula', 'nombre_completo', 'email'],
                'estudiantes': ['matricula', 'nombre_completo', 'email', 'programa'],
                'egresados': ['matricula', 'nombre_completo', 'programa'],
                'contratados': ['matricula', 'nombre_completo', 'empresa']
            }
            
            for tabla, columnas in tablas_a_verificar.items():
                if tabla in tablas_encontradas:
                    try:
                        cursor.execute(f"PRAGMA table_info({tabla})")
                        columnas_tabla = [col[1] for col in cursor.fetchall()]
                        
                        for columna in columnas:
                            if columna not in columnas_tabla:
                                logger.warning(f"Tabla {tabla} falta columna: {columna}")
                                return False
                    except Exception as e:
                        logger.warning(f"Error verificando tabla {tabla}: {e}")
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
            temp_db_path = os.path.join(temp_dir, f"migracion_nueva_{timestamp}.db")
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
        """Inicializar estructura de base de datos - ACTUALIZADO según escuela30.py"""
        try:
            logger.info(f"📝 Inicializando estructura en: {db_path}")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Tabla de usuarios - CON BCRYPT (MANTENIDO)
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
            
            # Tabla de inscritos - ACTUALIZADA según escuela30.py
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
            
            # Tabla de estudiantes - ACTUALIZADA según escuela30.py
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
            
            # Tabla de egresados - ACTUALIZADA según escuela30.py
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS egresados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT,
                    telefono TEXT,
                    fecha_nacimiento DATE,
                    direccion TEXT,
                    municipio TEXT,
                    estado TEXT,
                    cp TEXT,
                    programa TEXT,
                    nivel_academico TEXT,
                    institucion_procedencia TEXT,
                    fecha_graduacion DATE,
                    promedio_final REAL,
                    titulo_obtenido TEXT,
                    cedula_profesional TEXT,
                    especialidad TEXT,
                    empleo_actual TEXT,
                    empresa_actual TEXT,
                    puesto_actual TEXT,
                    fecha_contratacion DATE,
                    salario_actual REAL,
                    estatus_laboral TEXT,
                    documentos_subidos INTEGER DEFAULT 0,
                    documentos_nombres TEXT,
                    documentos_rutas TEXT,
                    foto_ruta TEXT,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usuario TEXT
                )
            ''')
            
            # Tabla de contratados - ACTUALIZADA según escuela30.py
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS contratados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT,
                    telefono TEXT,
                    fecha_nacimiento DATE,
                    direccion TEXT,
                    municipio TEXT,
                    estado TEXT,
                    cp TEXT,
                    empresa TEXT NOT NULL,
                    puesto TEXT NOT NULL,
                    departamento TEXT,
                    fecha_contratacion DATE NOT NULL,
                    fecha_inicio DATE,
                    fecha_fin DATE,
                    tipo_contrato TEXT,
                    salario REAL,
                    prestaciones TEXT,
                    estatus TEXT DEFAULT 'ACTIVO',
                    motivo_baja TEXT,
                    documentos_subidos INTEGER DEFAULT 0,
                    documentos_nombres TEXT,
                    documentos_rutas TEXT,
                    foto_ruta TEXT,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usuario TEXT
                )
            ''')
            
            # Tabla de bitácora - ACTUALIZADA según escuela30.py
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bitacora (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usuario TEXT NOT NULL,
                    accion TEXT NOT NULL,
                    modulo TEXT,
                    detalles TEXT,
                    ip TEXT,
                    user_agent TEXT,
                    resultado TEXT
                )
            ''')
            
            # Tabla de documentos - NUEVA según escuela30.py
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS documentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo_documento TEXT NOT NULL,
                    nombre_archivo TEXT NOT NULL,
                    ruta_archivo TEXT NOT NULL,
                    tamaño INTEGER,
                    matricula TEXT NOT NULL,
                    usuario_subida TEXT,
                    fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    estatus TEXT DEFAULT 'ACTIVO',
                    observaciones TEXT,
                    categoria TEXT
                )
            ''')
            
            # Tabla de configuracion - NUEVA según escuela30.py
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS configuracion (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clave TEXT UNIQUE NOT NULL,
                    valor TEXT,
                    tipo TEXT,
                    descripcion TEXT,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Índices para rendimiento - ACTUALIZADOS
            indices = [
                ('idx_usuarios_usuario', 'usuarios(usuario)'),
                ('idx_usuarios_matricula', 'usuarios(matricula)'),
                ('idx_inscritos_matricula', 'inscritos(matricula)'),
                ('idx_estudiantes_matricula', 'estudiantes(matricula)'),
                ('idx_egresados_matricula', 'egresados(matricula)'),
                ('idx_contratados_matricula', 'contratados(matricula)'),
                ('idx_documentos_matricula', 'documentos(matricula)'),
                ('idx_inscritos_estatus', 'inscritos(estatus)'),
                ('idx_estudiantes_estatus', 'estudiantes(estatus)'),
                ('idx_bitacora_usuario', 'bitacora(usuario)'),
                ('idx_bitacora_timestamp', 'bitacora(timestamp)')
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
            logger.info(f"✅ Estructura de base de datos actualizada inicializada en {db_path}")
            
            # Marcar como inicializada en el estado persistente
            estado_migracion.marcar_db_inicializada()
            
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
            if self.backup_before_migration:
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
                    estado_migracion.registrar_backup()
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

# Instancia global del gestor de conexión remota para migración
gestor_remoto_migracion = GestorConexionRemotaMigracion()

# =============================================================================
# SISTEMA DE BASE DE DATOS SQLITE PARA MIGRACIÓN - MEJORADO CON PAGINACIÓN
# =============================================================================

class SistemaBaseDatosMigracion:
    """Sistema de base de datos SQLite para migración EXCLUSIVAMENTE REMOTO"""
    
    def __init__(self):
        self.gestor = gestor_remoto_migracion
        self.db_local_temp = None
        self.conexion_actual = None
        self.ultima_sincronizacion = None
        
        # Configuración de migración
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
                estado_migracion.marcar_sincronizacion()
                
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
                    estado_migracion.marcar_sincronizacion()
                    
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
    # MÉTODOS DE CONSULTA PARA MIGRACIÓN CON PAGINACIÓN
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
            logger.error(f"Error al actualizar usuario: {e}", exc_info=True)
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
    
    def agregar_estudiante(self, estudiante_data):
        """Agregar nuevo estudiante con campos actualizados"""
        try:
            with self.get_connection() as conn:
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
                        documentos_rutas, usuario_registro, fecha_registro,
                        fecha_actualizacion, usuario
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                             ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    estudiante_data.get('usuario_registro', st.session_state.usuario_actual.get('usuario', '')),
                    datetime.now(),
                    datetime.now(),
                    estudiante_data.get('matricula', '')
                ))
                estudiante_id = cursor.lastrowid
                logger.info(f"Estudiante agregado: {estudiante_data.get('matricula', '')}")
                return estudiante_id
        except Exception as e:
            logger.error(f"Error agregando estudiante: {e}", exc_info=True)
            return None
    
    def agregar_egresado(self, egresado_data):
        """Agregar nuevo egresado con campos actualizados"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO egresados (
                        matricula, nombre_completo, email, telefono,
                        fecha_nacimiento, direccion, municipio, estado, cp,
                        programa, nivel_academico, institucion_procedencia,
                        fecha_graduacion, promedio_final, titulo_obtenido,
                        cedula_profesional, especialidad, empleo_actual,
                        empresa_actual, puesto_actual, fecha_contratacion,
                        salario_actual, estatus_laboral, documentos_subidos,
                        documentos_nombres, documentos_rutas, foto_ruta,
                        fecha_registro, fecha_actualizacion, usuario
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                             ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    egresado_data.get('matricula', ''),
                    egresado_data.get('nombre_completo', ''),
                    egresado_data.get('email', ''),
                    egresado_data.get('telefono', ''),
                    egresado_data.get('fecha_nacimiento'),
                    egresado_data.get('direccion', ''),
                    egresado_data.get('municipio', ''),
                    egresado_data.get('estado', ''),
                    egresado_data.get('cp', ''),
                    egresado_data.get('programa', ''),
                    egresado_data.get('nivel_academico', ''),
                    egresado_data.get('institucion_procedencia', ''),
                    egresado_data.get('fecha_graduacion', datetime.now()),
                    egresado_data.get('promedio_final', 0.0),
                    egresado_data.get('titulo_obtenido', ''),
                    egresado_data.get('cedula_profesional', ''),
                    egresado_data.get('especialidad', ''),
                    egresado_data.get('empleo_actual', ''),
                    egresado_data.get('empresa_actual', ''),
                    egresado_data.get('puesto_actual', ''),
                    egresado_data.get('fecha_contratacion'),
                    egresado_data.get('salario_actual', 0.0),
                    egresado_data.get('estatus_laboral', ''),
                    egresado_data.get('documentos_subidos', 0),
                    egresado_data.get('documentos_nombres', ''),
                    egresado_data.get('documentos_rutas', ''),
                    egresado_data.get('foto_ruta', ''),
                    datetime.now(),
                    datetime.now(),
                    egresado_data.get('matricula', '')
                ))
                egresado_id = cursor.lastrowid
                logger.info(f"Egresado agregado: {egresado_data.get('matricula', '')}")
                return egresado_id
        except Exception as e:
            logger.error(f"Error agregando egresado: {e}", exc_info=True)
            return None
    
    def agregar_contratado(self, contratado_data):
        """Agregar nuevo contratado con campos actualizados"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO contratados (
                        matricula, nombre_completo, email, telefono,
                        fecha_nacimiento, direccion, municipio, estado, cp,
                        empresa, puesto, departamento, fecha_contratacion,
                        fecha_inicio, fecha_fin, tipo_contrato, salario,
                        prestaciones, estatus, motivo_baja, documentos_subidos,
                        documentos_nombres, documentos_rutas, foto_ruta,
                        fecha_registro, fecha_actualizacion, usuario
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                             ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    contratado_data.get('matricula', ''),
                    contratado_data.get('nombre_completo', ''),
                    contratado_data.get('email', ''),
                    contratado_data.get('telefono', ''),
                    contratado_data.get('fecha_nacimiento'),
                    contratado_data.get('direccion', ''),
                    contratado_data.get('municipio', ''),
                    contratado_data.get('estado', ''),
                    contratado_data.get('cp', ''),
                    contratado_data.get('empresa', ''),
                    contratado_data.get('puesto', ''),
                    contratado_data.get('departamento', ''),
                    contratado_data.get('fecha_contratacion', datetime.now()),
                    contratado_data.get('fecha_inicio', datetime.now()),
                    contratado_data.get('fecha_fin'),
                    contratado_data.get('tipo_contrato', ''),
                    contratado_data.get('salario', 0.0),
                    contratado_data.get('prestaciones', ''),
                    contratado_data.get('estatus', 'ACTIVO'),
                    contratado_data.get('motivo_baja', ''),
                    contratado_data.get('documentos_subidos', 0),
                    contratado_data.get('documentos_nombres', ''),
                    contratado_data.get('documentos_rutas', ''),
                    contratado_data.get('foto_ruta', ''),
                    datetime.now(),
                    datetime.now(),
                    contratado_data.get('matricula', '')
                ))
                contratado_id = cursor.lastrowid
                logger.info(f"Contratado agregado: {contratado_data.get('matricula', '')}")
                return contratado_id
        except Exception as e:
            logger.error(f"Error agregando contratado: {e}", exc_info=True)
            return None
    
    def registrar_bitacora(self, usuario, accion, detalles, ip='localhost', modulo=None):
        """Registrar actividad en bitácora con campos actualizados"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO bitacora (usuario, accion, detalles, ip, modulo, resultado)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (usuario, accion, detalles, ip, modulo, 'EXITO'))
                return True
        except Exception as e:
            logger.error(f"Error registrando en bitácora: {e}", exc_info=True)
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
        """Verificar credenciales de usuario"""
        try:
            if not usuario or not password:
                st.error("❌ Usuario y contraseña son obligatorios")
                return False
            
            with st.spinner("🔐 Verificando credenciales..."):
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
                        f'Administrador {usuario_data["usuario"]} inició sesión en el migrador',
                        modulo='MIGRACION'
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
        """Cerrar sesión del usuario en el migrador"""
        try:
            if self.sesion_activa and self.usuario_actual:
                db_migracion.registrar_bitacora(
                    self.usuario_actual.get('usuario', ''),
                    'LOGOUT_MIGRACION',
                    f'Administrador {self.usuario_actual.get("usuario", "")} cerró sesión del migrador',
                    modulo='MIGRACION'
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

# Instancia global del sistema de autenticación para migración
auth_migracion = SistemaAutenticacionMigracion()

# =============================================================================
# SISTEMA DE MIGRACIÓN DE ROLES - MEJORADO CON NOTIFICACIONES Y BACKUPS
# =============================================================================

class SistemaMigracionCompleto:
    def __init__(self):
        self.gestor = gestor_remoto_migracion
        self.db = db_migracion
        self.backup_system = SistemaBackupAutomatico(self.gestor)
        self.notificaciones = SistemaNotificaciones(
            gestor_remoto_migracion.config.get('smtp', {})
        )
        self.validador = ValidadorDatos()
        
        # Estado de paginación
        self.current_page_inscritos = 1
        self.current_page_estudiantes = 1
        self.current_page_egresados = 1
        
        # Términos de búsqueda
        self.search_term_inscritos = ""
        self.search_term_estudiantes = ""
        self.search_term_egresados = ""
        
        self.cargar_datos_paginados()
        
    def cargar_datos_paginados(self):
        """Cargar datos desde la base de datos de migración con paginación"""
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
                    page=1, search_term=""
                )
                
                self.df_usuarios, self.total_pages_usuarios, self.total_usuarios = self.db.obtener_usuarios(
                    page=1, search_term=""
                )
                
                logger.info(f"""
                📊 Datos cargados:
                - Inscritos: {self.total_inscritos} registros (página {self.current_page_inscritos}/{self.total_pages_inscritos})
                - Estudiantes: {self.total_estudiantes} registros (página {self.current_page_estudiantes}/{self.total_pages_estudiantes})
                - Egresados: {self.total_egresados} registros (página {self.current_page_egresados}/{self.total_pages_egresados})
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
    
    def migrar_inscrito_a_estudiante(self, inscrito_data):
        """Migrar de inscrito a estudiante con formulario actualizado"""
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
            
            # Formulario para completar datos del estudiante ACTUALIZADO
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
                    fecha_egreso = st.date_input("Fecha de Egreso Prevista", value=datetime.now() + timedelta(days=365))
                    nivel_academico = st.selectbox("Nivel Académico*", 
                                                 ["Bachillerato", "Licenciatura", "Especialidad", "Maestría", "Doctorado"])
                    institucion_procedencia = st.text_input("Institución de Procedencia", 
                                                          value=inscrito_data.get('institucion_procedencia', ''))
                    direccion = st.text_input("Dirección", value=inscrito_data.get('direccion', ''))
                    municipio = st.text_input("Municipio", value=inscrito_data.get('municipio', ''))
                
                with col2:
                    estado = st.text_input("Estado", value=inscrito_data.get('estado', ''))
                    cp = st.text_input("Código Postal", value=inscrito_data.get('cp', ''))
                    promedio_general = st.number_input("Promedio General", min_value=0.0, max_value=10.0, value=8.0, step=0.1)
                    semestre_actual = st.number_input("Semestre Actual", min_value=1, max_value=20, value=1)
                    creditos_acumulados = st.number_input("Créditos Acumulados", min_value=0, value=0)
                    cedula_profesional = st.text_input("Cédula Profesional", value=inscrito_data.get('cedula_profesional', ''))
                    especialidad = st.text_input("Especialidad", value=inscrito_data.get('especialidad', ''))
                    documentos_subidos = st.number_input("Documentos Subidos", min_value=0, value=inscrito_data.get('documentos_subidos', 0))
                    estatus = st.selectbox("Estatus*", ["ACTIVO", "INACTIVO", "PENDIENTE"], index=0)
                
                submitted = st.form_submit_button("💾 Confirmar Migración a Estudiante")
                
                if submitted:
                    # Validaciones mejoradas
                    if not programa:
                        st.error("❌ El campo Programa Educativo es obligatorio")
                        return False
                    
                    # Validar email si está presente
                    email = inscrito_data.get('email', '')
                    if email and not ValidadorDatos.validar_email(email):
                        st.error("❌ Formato de email inválido")
                        return False
                    
                    # Validar teléfono si está presente
                    telefono = inscrito_data.get('telefono', '')
                    if telefono and not ValidadorDatos.validar_telefono(telefono):
                        st.error("❌ Formato de teléfono inválido (mínimo 10 dígitos)")
                        return False
                    
                    # Guardar datos en session_state
                    st.session_state.datos_formulario_inscrito = {
                        'programa': programa,
                        'fecha_nacimiento': fecha_nacimiento,
                        'genero': genero,
                        'fecha_ingreso': fecha_ingreso,
                        'fecha_egreso': fecha_egreso,
                        'nivel_academico': nivel_academico,
                        'institucion_procedencia': institucion_procedencia,
                        'direccion': direccion,
                        'municipio': municipio,
                        'estado': estado,
                        'cp': cp,
                        'promedio_general': promedio_general,
                        'semestre_actual': semestre_actual,
                        'creditos_acumulados': creditos_acumulados,
                        'cedula_profesional': cedula_profesional,
                        'especialidad': especialidad,
                        'documentos_subidos': documentos_subidos,
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
                    st.info(f"**Nivel Académico:** {datos_form['nivel_academico']}")
                    
                    # Crear backup antes de proceder
                    backup_info = f"Inscrito -> Estudiante: {datos_form['matricula_inscrito']} -> {datos_form['matricula_estudiante']}"
                    
                    with st.spinner("🔄 Creando backup antes de la migración..."):
                        backup_path = self.backup_system.crear_backup_pre_migracion(
                            "INSCRITO_A_ESTUDIANTE", 
                            backup_info
                        )
                        
                        if backup_path:
                            st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                    
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
        """Migrar de estudiante a egresado con formulario actualizado"""
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
            
            # Formulario para completar datos del egresado ACTUALIZADO
            st.subheader("📝 Formulario de Datos del Egresado")
            
            with st.form("formulario_egresado"):
                st.write("Complete la información requerida para el egresado:")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    programa = st.text_input("Programa Original*", 
                                           value=estudiante_data.get('programa', 'Especialidad en Enfermería Cardiovascular'))
                    fecha_graduacion = st.date_input("Fecha de Graduación*", value=datetime.now())
                    nivel_academico = st.selectbox("Nivel Académico*", 
                                                 ["Bachillerato", "Licenciatura", "Especialidad", "Maestría", "Doctorado"],
                                                 index=0)
                    promedio_final = st.number_input("Promedio Final*", min_value=0.0, max_value=10.0, value=8.5, step=0.1)
                    titulo_obtenido = st.text_input("Título Obtenido*", value="Especialista en Enfermería Cardiovascular")
                    cedula_profesional = st.text_input("Cédula Profesional", value=estudiante_data.get('cedula_profesional', ''))
                    especialidad = st.text_input("Especialidad", value=estudiante_data.get('especialidad', ''))
                
                with col2:
                    empleo_actual = st.text_input("Empleo Actual", value="Enfermera Especialista")
                    empresa_actual = st.text_input("Empresa Actual", value="Hospital General")
                    puesto_actual = st.text_input("Puesto Actual", value="Jefe de Enfermería")
                    fecha_contratacion = st.date_input("Fecha de Contratación", value=datetime.now())
                    salario_actual = st.number_input("Salario Actual", min_value=0.0, value=25000.0)
                    estatus_laboral = st.selectbox("Estatus Laboral*",
                                                 ["Empleado", "Desempleado", "Independiente", "Estudiando", "Otro"],
                                                 index=0)
                    telefono = st.text_input("Teléfono", value=estudiante_data.get('telefono', ''))
                    email = st.text_input("Email*", value=estudiante_data.get('email', ''))
                    documentos_subidos = st.number_input("Documentos Subidos", min_value=0, 
                                                       value=estudiante_data.get('documentos_subidos', 0))
                
                submitted = st.form_submit_button("💾 Confirmar Migración a Egresado")
                
                if submitted:
                    if not programa or not nivel_academico or not titulo_obtenido or not email:
                        st.error("❌ Los campos marcados con * son obligatorios")
                        return False
                    
                    # Validar email
                    if not ValidadorDatos.validar_email(email):
                        st.error("❌ Formato de email inválido")
                        return False
                    
                    # Validar teléfono si está presente
                    if telefono and not ValidadorDatos.validar_telefono(telefono):
                        st.error("❌ Formato de teléfono inválido (mínimo 10 dígitos)")
                        return False
                    
                    # Guardar datos en session_state
                    st.session_state.datos_formulario_estudiante = {
                        'programa': programa,
                        'fecha_graduacion': fecha_graduacion,
                        'nivel_academico': nivel_academico,
                        'promedio_final': promedio_final,
                        'titulo_obtenido': titulo_obtenido,
                        'cedula_profesional': cedula_profesional,
                        'especialidad': especialidad,
                        'empleo_actual': empleo_actual,
                        'empresa_actual': empresa_actual,
                        'puesto_actual': puesto_actual,
                        'fecha_contratacion': fecha_contratacion,
                        'salario_actual': salario_actual,
                        'estatus_laboral': estatus_laboral,
                        'telefono': telefono,
                        'email': email,
                        'documentos_subidos': documentos_subidos,
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
                    st.info(f"**Programa Original:** {datos_form['programa']}")
                    st.info(f"**Nivel Académico:** {datos_form['nivel_academico']}")
                    st.info(f"**Título Obtenido:** {datos_form['titulo_obtenido']}")
                    
                    # Crear backup antes de proceder
                    backup_info = f"Estudiante -> Egresado: {datos_form['matricula_estudiante']} -> {datos_form['matricula_egresado']}"
                    
                    with st.spinner("🔄 Creando backup antes de la migración..."):
                        backup_path = self.backup_system.crear_backup_pre_migracion(
                            "ESTUDIANTE_A_EGRESADO", 
                            backup_info
                        )
                        
                        if backup_path:
                            st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                    
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
        """Migrar de egresado a contratado con formulario actualizado"""
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
            
            # Formulario para completar datos del contratado ACTUALIZADO
            st.subheader("📝 Formulario de Datos del Contratado")
            
            with st.form("formulario_contratado"):
                st.write("Complete la información requerida para el contratado:")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    empresa = st.text_input("Empresa*", value="Hospital General de la Ciudad")
                    puesto = st.text_input("Puesto*", value="Enfermera Especialista en Cardiología")
                    departamento = st.text_input("Departamento*", value="Terapia Intensiva Cardiovascular")
                    fecha_contratacion = st.date_input("Fecha de Contratación*", value=datetime.now())
                    fecha_inicio = st.date_input("Fecha Inicio*", value=datetime.now())
                    fecha_fin = st.date_input("Fecha Fin", value=datetime.now() + timedelta(days=365))
                    tipo_contrato = st.selectbox("Tipo de Contrato*", 
                                               ["Tiempo completo", "Medio tiempo", "Por honorarios", "Temporal"],
                                               index=0)
                    salario = st.number_input("Salario*", min_value=0.0, value=25000.0)
                
                with col2:
                    prestaciones = st.text_input("Prestaciones", value="Seguro médico, Vacaciones, Aguinaldo")
                    estatus = st.selectbox("Estatus*", ["ACTIVO", "INACTIVO", "LICENCIA", "BAJA"], index=0)
                    motivo_baja = st.text_input("Motivo de Baja (si aplica)")
                    documentos_subidos = st.number_input("Documentos Subidos", min_value=0, value=egresado_data.get('documentos_subidos', 0))
                    direccion = st.text_input("Dirección", value=egresado_data.get('direccion', ''))
                    municipio = st.text_input("Municipio", value=egresado_data.get('municipio', ''))
                    estado = st.text_input("Estado", value=egresado_data.get('estado', ''))
                    cp = st.text_input("Código Postal", value=egresado_data.get('cp', ''))
                
                submitted = st.form_submit_button("💾 Confirmar Migración a Contratado")
                
                if submitted:
                    if not empresa or not puesto or not departamento or not fecha_contratacion or not tipo_contrato:
                        st.error("❌ Los campos marcados con * son obligatorios")
                        return False
                    
                    # Validar email si está presente
                    email = egresado_data.get('email', '')
                    if email and not ValidadorDatos.validar_email(email):
                        st.error("❌ Formato de email inválido")
                        return False
                    
                    # Validar teléfono si está presente
                    telefono = egresado_data.get('telefono', '')
                    if telefono and not ValidadorDatos.validar_telefono(telefono):
                        st.error("❌ Formato de teléfono inválido (mínimo 10 dígitos)")
                        return False
                    
                    # Guardar datos en session_state
                    st.session_state.datos_formulario_egresado = {
                        'empresa': empresa,
                        'puesto': puesto,
                        'departamento': departamento,
                        'fecha_contratacion': fecha_contratacion,
                        'fecha_inicio': fecha_inicio,
                        'fecha_fin': fecha_fin,
                        'tipo_contrato': tipo_contrato,
                        'salario': salario,
                        'prestaciones': prestaciones,
                        'estatus': estatus,
                        'motivo_baja': motivo_baja,
                        'documentos_subidos': documentos_subidos,
                        'direccion': direccion,
                        'municipio': municipio,
                        'estado': estado,
                        'cp': cp,
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
                    st.info(f"**Empresa:** {datos_form['empresa']}")
                    st.info(f"**Puesto:** {datos_form['puesto']}")
                    st.info(f"**Departamento:** {datos_form['departamento']}")
                    
                    # Crear backup antes de proceder
                    backup_info = f"Egresado -> Contratado: {datos_form['matricula_egresado']} -> {datos_form['matricula_contratado']}"
                    
                    with st.spinner("🔄 Creando backup antes de la migración..."):
                        backup_path = self.backup_system.crear_backup_pre_migracion(
                            "EGRESADO_A_CONTRATADO", 
                            backup_info
                        )
                        
                        if backup_path:
                            st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                    
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
        inicio_tiempo = time.time()
        
        try:
            matricula_inscrito = datos_form['matricula_inscrito']
            matricula_estudiante = datos_form['matricula_estudiante']
            inscrito_data = datos_form['inscrito_data']
            
            if not inscrito_data:
                st.error("❌ Error: Datos del inscrito no disponibles")
                return False
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 1. Buscar usuario en base de datos
            status_text.text("🔍 Buscando usuario en base de datos...")
            progress_bar.progress(10)
            usuario_id = self.buscar_usuario_por_matricula(matricula_inscrito)
            
            if usuario_id:
                # Actualizar usuario en SQLite
                status_text.text("👤 Actualizando usuario en base de datos...")
                progress_bar.progress(20)
                if self.actualizar_rol_usuario(usuario_id, 'estudiante', matricula_estudiante):
                    st.success("✅ Usuario actualizado exitosamente")
                else:
                    st.warning("⚠️ No se pudo actualizar usuario, continuando con migración")
            else:
                st.warning("⚠️ Usuario no encontrado, continuando con migración de datos")
            
            # 2. Renombrar archivos PDF
            status_text.text("📁 Renombrando archivos PDF en servidor remoto...")
            progress_bar.progress(40)
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_inscrito, matricula_estudiante)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.info("ℹ️ No se encontraron archivos PDF para renombrar")
            
            # 3. Eliminar inscrito y crear estudiante
            status_text.text("🔄 Procesando migración de datos...")
            progress_bar.progress(60)
            
            # Eliminar inscrito
            if self.db.eliminar_inscrito(matricula_inscrito):
                st.success(f"✅ Inscrito eliminado: {matricula_inscrito}")
            else:
                st.error(f"❌ Error eliminando inscrito: {matricula_inscrito}")
                return False
            
            # Crear estudiante con datos actualizados
            nuevo_estudiante = {
                'matricula': matricula_estudiante,
                'nombre_completo': inscrito_data.get('nombre_completo', ''),
                'email': inscrito_data.get('email', ''),
                'telefono': inscrito_data.get('telefono', ''),
                'fecha_nacimiento': datos_form.get('fecha_nacimiento', datetime.now()),
                'direccion': datos_form.get('direccion', inscrito_data.get('direccion', '')),
                'municipio': datos_form.get('municipio', inscrito_data.get('municipio', '')),
                'estado': datos_form.get('estado', inscrito_data.get('estado', '')),
                'cp': datos_form.get('cp', inscrito_data.get('cp', '')),
                'programa': datos_form.get('programa', ''),
                'nivel_academico': datos_form.get('nivel_academico', ''),
                'institucion_procedencia': datos_form.get('institucion_procedencia', ''),
                'fecha_inscripcion': datetime.now(),
                'fecha_ingreso': datos_form.get('fecha_ingreso', datetime.now()),
                'fecha_egreso': datos_form.get('fecha_egreso'),
                'estatus': datos_form.get('estatus', 'ACTIVO'),
                'promedio_general': datos_form.get('promedio_general', 0.0),
                'semestre_actual': datos_form.get('semestre_actual', 1),
                'creditos_acumulados': datos_form.get('creditos_acumulados', 0),
                'foto_ruta': inscrito_data.get('foto_ruta', ''),
                'cedula_profesional': datos_form.get('cedula_profesional', ''),
                'especialidad': datos_form.get('especialidad', ''),
                'documentos_subidos': datos_form.get('documentos_subidos', 0),
                'documentos_nombres': inscrito_data.get('documentos_nombres', ''),
                'documentos_rutas': inscrito_data.get('documentos_rutas', ''),
                'usuario_registro': st.session_state.usuario_actual.get('usuario', ''),
                'usuario': matricula_estudiante
            }
            
            estudiante_id = self.db.agregar_estudiante(nuevo_estudiante)
            if estudiante_id:
                st.success(f"✅ Estudiante creado: {matricula_estudiante}")
            else:
                st.error(f"❌ Error creando estudiante: {matricula_estudiante}")
                return False
            
            # Registrar en bitácora
            status_text.text("📝 Registrando en bitácora...")
            progress_bar.progress(80)
            self.db.registrar_bitacora(
                st.session_state.usuario_actual.get('usuario', 'admin'),
                'MIGRACION_INSCRITO_ESTUDIANTE',
                f'Usuario migrado de inscrito a estudiante. Matrícula: {matricula_inscrito} -> {matricula_estudiante}',
                modulo='MIGRACION'
            )
            
            # Sincronizar cambios con servidor remoto
            status_text.text("🌐 Sincronizando cambios con servidor remoto...")
            progress_bar.progress(90)
            if self.db.sincronizar_hacia_remoto():
                st.success("✅ Cambios sincronizados con servidor remoto")
            else:
                st.error("❌ Error sincronizando cambios")
                return False
            
            status_text.text("✅ Migración completada")
            progress_bar.progress(100)
            
            tiempo_ejecucion = time.time() - inicio_tiempo
            
            # Registrar migración exitosa
            estado_migracion.registrar_migracion(exitoso=True, tiempo_ejecucion=tiempo_ejecucion)
            
            # Enviar notificación
            detalles_notificacion = f"""
            Migración exitosa: Inscrito → Estudiante
            Matrícula: {matricula_inscrito} → {matricula_estudiante}
            Nombre: {inscrito_data.get('nombre_completo', '')}
            Programa: {datos_form.get('programa', '')}
            Tiempo ejecución: {tiempo_ejecucion:.1f} segundos
            Archivos renombrados: {archivos_renombrados}
            Usuario: {st.session_state.usuario_actual.get('usuario', 'admin')}
            """
            
            self.notificaciones.enviar_notificacion_migracion(
                tipo_migracion="INSCRITO → ESTUDIANTE",
                estado="EXITOSA",
                detalles=detalles_notificacion
            )
            
            st.success(f"🎉 ¡Migración completada exitosamente en {tiempo_ejecucion:.1f} segundos!")
            st.balloons()
            
            # Mostrar resumen final
            st.subheader("📊 Resumen Final de la Migración")
            st.success(f"✅ Matrícula actualizada: {matricula_inscrito} → {matricula_estudiante}")
            st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
            st.success(f"✅ Registro creado en estudiantes")
            st.success(f"✅ Registro eliminado de inscritos")
            st.success(f"✅ Cambios sincronizados con servidor remoto")
            st.success(f"✅ Notificación enviada")
            
            # Limpiar estado de sesión
            if 'inscrito_seleccionado' in st.session_state:
                del st.session_state.inscrito_seleccionado
            if 'mostrar_confirmacion_inscrito' in st.session_state:
                del st.session_state.mostrar_confirmacion_inscrito
            if 'datos_formulario_inscrito' in st.session_state:
                del st.session_state.datos_formulario_inscrito
            
            # Registrar en log de migración
            logger.log_migration(
                operation="INSCRITO_A_ESTUDIANTE",
                status="EXITOSA",
                details={
                    'matricula_original': matricula_inscrito,
                    'matricula_nueva': matricula_estudiante,
                    'tiempo_ejecucion': tiempo_ejecucion,
                    'archivos_renombrados': archivos_renombrados
                }
            )
            
            # Recargar datos
            time.sleep(2)
            st.rerun()
            return True
                
        except Exception as e:
            tiempo_ejecucion = time.time() - inicio_tiempo
            logger.error(f"❌ Error ejecutando la migración: {str(e)}", exc_info=True)
            
            # Registrar migración fallida
            estado_migracion.registrar_migracion(exitoso=False, tiempo_ejecucion=tiempo_ejecucion)
            
            # Enviar notificación de error
            self.notificaciones.enviar_notificacion_migracion(
                tipo_migracion="INSCRITO → ESTUDIANTE",
                estado="FALLIDA",
                detalles=f"Error: {str(e)}\nTiempo transcurrido: {tiempo_ejecucion:.1f}s"
            )
            
            # Registrar en log de migración
            logger.log_migration(
                operation="INSCRITO_A_ESTUDIANTE",
                status="FALLIDA",
                details={
                    'error': str(e),
                    'tiempo_ejecucion': tiempo_ejecucion
                }
            )
            
            return False

    def ejecutar_migracion_estudiante_egresado(self, datos_form):
        """Ejecutar el proceso de migración estudiante → egresado"""
        inicio_tiempo = time.time()
        
        try:
            matricula_estudiante = datos_form['matricula_estudiante']
            matricula_egresado = datos_form['matricula_egresado']
            estudiante_data = datos_form['estudiante_data']
            
            if not estudiante_data:
                st.error("❌ Error: Datos del estudiante no disponibles")
                return False
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 1. Buscar usuario en base de datos
            status_text.text("🔍 Buscando usuario en base de datos...")
            progress_bar.progress(10)
            usuario_id = self.buscar_usuario_por_matricula(matricula_estudiante)
            
            if usuario_id:
                # Actualizar usuario en SQLite
                status_text.text("👤 Actualizando usuario en base de datos...")
                progress_bar.progress(20)
                if self.actualizar_rol_usuario(usuario_id, 'egresado', matricula_egresado):
                    st.success("✅ Usuario actualizado exitosamente")
                else:
                    st.warning("⚠️ No se pudo actualizar usuario, continuando con migración")
            else:
                st.warning("⚠️ Usuario no encontrado, continuando con migración de datos")
            
            # 2. Renombrar archivos PDF
            status_text.text("📁 Renombrando archivos PDF en servidor remoto...")
            progress_bar.progress(40)
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_estudiante, matricula_egresado)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.info("ℹ️ No se encontraron archivos PDF para renombrar")
            
            # 3. Eliminar estudiante y crear egresado
            status_text.text("🔄 Procesando migración de datos...")
            progress_bar.progress(60)
            
            # Eliminar estudiante
            if self.db.eliminar_estudiante(matricula_estudiante):
                st.success(f"✅ Estudiante eliminado: {matricula_estudiante}")
            else:
                st.error(f"❌ Error eliminando estudiante: {matricula_estudiante}")
                return False
            
            # Crear egresado con datos actualizados
            nuevo_egresado = {
                'matricula': matricula_egresado,
                'nombre_completo': estudiante_data.get('nombre_completo', ''),
                'email': datos_form.get('email', estudiante_data.get('email', '')),
                'telefono': datos_form.get('telefono', estudiante_data.get('telefono', '')),
                'fecha_nacimiento': estudiante_data.get('fecha_nacimiento', datetime.now()),
                'direccion': estudiante_data.get('direccion', ''),
                'municipio': estudiante_data.get('municipio', ''),
                'estado': estudiante_data.get('estado', ''),
                'cp': estudiante_data.get('cp', ''),
                'programa': datos_form.get('programa', estudiante_data.get('programa', '')),
                'nivel_academico': datos_form.get('nivel_academico', ''),
                'institucion_procedencia': estudiante_data.get('institucion_procedencia', ''),
                'fecha_graduacion': datos_form.get('fecha_graduacion', datetime.now()),
                'promedio_final': datos_form.get('promedio_final', 0.0),
                'titulo_obtenido': datos_form.get('titulo_obtenido', ''),
                'cedula_profesional': datos_form.get('cedula_profesional', ''),
                'especialidad': datos_form.get('especialidad', ''),
                'empleo_actual': datos_form.get('empleo_actual', ''),
                'empresa_actual': datos_form.get('empresa_actual', ''),
                'puesto_actual': datos_form.get('puesto_actual', ''),
                'fecha_contratacion': datos_form.get('fecha_contratacion'),
                'salario_actual': datos_form.get('salario_actual', 0.0),
                'estatus_laboral': datos_form.get('estatus_laboral', ''),
                'documentos_subidos': datos_form.get('documentos_subidos', 0),
                'documentos_nombres': estudiante_data.get('documentos_nombres', ''),
                'documentos_rutas': estudiante_data.get('documentos_rutas', ''),
                'foto_ruta': estudiante_data.get('foto_ruta', ''),
                'usuario': matricula_egresado
            }
            
            egresado_id = self.db.agregar_egresado(nuevo_egresado)
            if egresado_id:
                st.success(f"✅ Egresado creado: {matricula_egresado}")
            else:
                st.error(f"❌ Error creando egresado: {matricula_egresado}")
                return False
            
            # Registrar en bitácora
            status_text.text("📝 Registrando en bitácora...")
            progress_bar.progress(80)
            self.db.registrar_bitacora(
                st.session_state.usuario_actual.get('usuario', 'admin'),
                'MIGRACION_ESTUDIANTE_EGRESADO',
                f'Usuario migrado de estudiante a egresado. Matrícula: {matricula_estudiante} -> {matricula_egresado}',
                modulo='MIGRACION'
            )
            
            # Sincronizar cambios con servidor remoto
            status_text.text("🌐 Sincronizando cambios con servidor remoto...")
            progress_bar.progress(90)
            if self.db.sincronizar_hacia_remoto():
                st.success("✅ Cambios sincronizados con servidor remoto")
            else:
                st.error("❌ Error sincronizando cambios")
                return False
            
            status_text.text("✅ Migración completada")
            progress_bar.progress(100)
            
            tiempo_ejecucion = time.time() - inicio_tiempo
            
            # Registrar migración exitosa
            estado_migracion.registrar_migracion(exitoso=True, tiempo_ejecucion=tiempo_ejecucion)
            
            # Enviar notificación
            detalles_notificacion = f"""
            Migración exitosa: Estudiante → Egresado
            Matrícula: {matricula_estudiante} → {matricula_egresado}
            Nombre: {estudiante_data.get('nombre_completo', '')}
            Programa: {datos_form.get('programa', '')}
            Título: {datos_form.get('titulo_obtenido', '')}
            Tiempo ejecución: {tiempo_ejecucion:.1f} segundos
            Archivos renombrados: {archivos_renombrados}
            Usuario: {st.session_state.usuario_actual.get('usuario', 'admin')}
            """
            
            self.notificaciones.enviar_notificacion_migracion(
                tipo_migracion="ESTUDIANTE → EGRESADO",
                estado="EXITOSA",
                detalles=detalles_notificacion
            )
            
            st.success(f"🎉 ¡Migración completada exitosamente en {tiempo_ejecucion:.1f} segundos!")
            st.balloons()
            
            # Mostrar resumen final
            st.subheader("📊 Resumen Final de la Migración")
            st.success(f"✅ Matrícula actualizada: {matricula_estudiante} → {matricula_egresado}")
            st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
            st.success(f"✅ Registro creado en egresados")
            st.success(f"✅ Registro eliminado de estudiantes")
            st.success(f"✅ Cambios sincronizados con servidor remoto")
            st.success(f"✅ Notificación enviada")
            
            # Limpiar estado de sesión
            if 'estudiante_seleccionado' in st.session_state:
                del st.session_state.estudiante_seleccionado
            if 'mostrar_confirmacion_estudiante' in st.session_state:
                del st.session_state.mostrar_confirmacion_estudiante
            if 'datos_formulario_estudiante' in st.session_state:
                del st.session_state.datos_formulario_estudiante
            
            # Registrar en log de migración
            logger.log_migration(
                operation="ESTUDIANTE_A_EGRESADO",
                status="EXITOSA",
                details={
                    'matricula_original': matricula_estudiante,
                    'matricula_nueva': matricula_egresado,
                    'tiempo_ejecucion': tiempo_ejecucion,
                    'archivos_renombrados': archivos_renombrados
                }
            )
            
            # Recargar datos
            time.sleep(2)
            st.rerun()
            return True
                
        except Exception as e:
            tiempo_ejecucion = time.time() - inicio_tiempo
            logger.error(f"❌ Error ejecutando la migración: {str(e)}", exc_info=True)
            
            # Registrar migración fallida
            estado_migracion.registrar_migracion(exitoso=False, tiempo_ejecucion=tiempo_ejecucion)
            
            # Enviar notificación de error
            self.notificaciones.enviar_notificacion_migracion(
                tipo_migracion="ESTUDIANTE → EGRESADO",
                estado="FALLIDA",
                detalles=f"Error: {str(e)}\nTiempo transcurrido: {tiempo_ejecucion:.1f}s"
            )
            
            # Registrar en log de migración
            logger.log_migration(
                operation="ESTUDIANTE_A_EGRESADO",
                status="FALLIDA",
                details={
                    'error': str(e),
                    'tiempo_ejecucion': tiempo_ejecucion
                }
            )
            
            return False

    def ejecutar_migracion_egresado_contratado(self, datos_form):
        """Ejecutar el proceso de migración egresado → contratado"""
        inicio_tiempo = time.time()
        
        try:
            matricula_egresado = datos_form['matricula_egresado']
            matricula_contratado = datos_form['matricula_contratado']
            egresado_data = datos_form['egresado_data']
            
            if not egresado_data:
                st.error("❌ Error: Datos del egresado no disponibles")
                return False
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 1. Buscar usuario en base de datos
            status_text.text("🔍 Buscando usuario en base de datos...")
            progress_bar.progress(10)
            usuario_id = self.buscar_usuario_por_matricula(matricula_egresado)
            
            if usuario_id:
                # Actualizar usuario en SQLite
                status_text.text("👤 Actualizando usuario en base de datos...")
                progress_bar.progress(20)
                if self.actualizar_rol_usuario(usuario_id, 'contratado', matricula_contratado):
                    st.success("✅ Usuario actualizado exitosamente")
                else:
                    st.warning("⚠️ No se pudo actualizar usuario, continuando con migración")
            else:
                st.warning("⚠️ Usuario no encontrado, continuando con migración de datos")
            
            # 2. Renombrar archivos PDF
            status_text.text("📁 Renombrando archivos PDF en servidor remoto...")
            progress_bar.progress(40)
            archivos_renombrados = self.renombrar_archivos_pdf(matricula_egresado, matricula_contratado)
            if archivos_renombrados > 0:
                st.success(f"✅ {archivos_renombrados} archivos PDF renombrados")
            else:
                st.info("ℹ️ No se encontraron archivos PDF para renombrar")
            
            # 3. Eliminar egresado y crear contratado
            status_text.text("🔄 Procesando migración de datos...")
            progress_bar.progress(60)
            
            # Eliminar egresado
            if self.db.eliminar_egresado(matricula_egresado):
                st.success(f"✅ Egresado eliminado: {matricula_egresado}")
            else:
                st.error(f"❌ Error eliminando egresado: {matricula_egresado}")
                return False
            
            # Crear contratado con datos actualizados
            nuevo_contratado = {
                'matricula': matricula_contratado,
                'nombre_completo': egresado_data.get('nombre_completo', ''),
                'email': egresado_data.get('email', ''),
                'telefono': egresado_data.get('telefono', ''),
                'fecha_nacimiento': egresado_data.get('fecha_nacimiento', datetime.now()),
                'direccion': datos_form.get('direccion', egresado_data.get('direccion', '')),
                'municipio': datos_form.get('municipio', egresado_data.get('municipio', '')),
                'estado': datos_form.get('estado', egresado_data.get('estado', '')),
                'cp': datos_form.get('cp', egresado_data.get('cp', '')),
                'empresa': datos_form.get('empresa', ''),
                'puesto': datos_form.get('puesto', ''),
                'departamento': datos_form.get('departamento', ''),
                'fecha_contratacion': datos_form.get('fecha_contratacion', datetime.now()),
                'fecha_inicio': datos_form.get('fecha_inicio', datetime.now()),
                'fecha_fin': datos_form.get('fecha_fin'),
                'tipo_contrato': datos_form.get('tipo_contrato', ''),
                'salario': datos_form.get('salario', 0.0),
                'prestaciones': datos_form.get('prestaciones', ''),
                'estatus': datos_form.get('estatus', 'ACTIVO'),
                'motivo_baja': datos_form.get('motivo_baja', ''),
                'documentos_subidos': datos_form.get('documentos_subidos', 0),
                'documentos_nombres': egresado_data.get('documentos_nombres', ''),
                'documentos_rutas': egresado_data.get('documentos_rutas', ''),
                'foto_ruta': egresado_data.get('foto_ruta', ''),
                'usuario': matricula_contratado
            }
            
            contratado_id = self.db.agregar_contratado(nuevo_contratado)
            if contratado_id:
                st.success(f"✅ Contratado creado: {matricula_contratado}")
            else:
                st.error(f"❌ Error creando contratado: {matricula_contratado}")
                return False
            
            # Registrar en bitácora
            status_text.text("📝 Registrando en bitácora...")
            progress_bar.progress(80)
            self.db.registrar_bitacora(
                st.session_state.usuario_actual.get('usuario', 'admin'),
                'MIGRACION_EGRESADO_CONTRATADO',
                f'Usuario migrado de egresado a contratado. Matrícula: {matricula_egresado} -> {matricula_contratado}',
                modulo='MIGRACION'
            )
            
            # Sincronizar cambios con servidor remoto
            status_text.text("🌐 Sincronizando cambios con servidor remoto...")
            progress_bar.progress(90)
            if self.db.sincronizar_hacia_remoto():
                st.success("✅ Cambios sincronizados con servidor remoto")
            else:
                st.error("❌ Error sincronizando cambios")
                return False
            
            status_text.text("✅ Migración completada")
            progress_bar.progress(100)
            
            tiempo_ejecucion = time.time() - inicio_tiempo
            
            # Registrar migración exitosa
            estado_migracion.registrar_migracion(exitoso=True, tiempo_ejecucion=tiempo_ejecucion)
            
            # Enviar notificación
            detalles_notificacion = f"""
            Migración exitosa: Egresado → Contratado
            Matrícula: {matricula_egresado} → {matricula_contratado}
            Nombre: {egresado_data.get('nombre_completo', '')}
            Empresa: {datos_form.get('empresa', '')}
            Puesto: {datos_form.get('puesto', '')}
            Tiempo ejecución: {tiempo_ejecucion:.1f} segundos
            Archivos renombrados: {archivos_renombrados}
            Usuario: {st.session_state.usuario_actual.get('usuario', 'admin')}
            """
            
            self.notificaciones.enviar_notificacion_migracion(
                tipo_migracion="EGRESADO → CONTRATADO",
                estado="EXITOSA",
                detalles=detalles_notificacion
            )
            
            st.success(f"🎉 ¡Migración completada exitosamente en {tiempo_ejecucion:.1f} segundos!")
            st.balloons()
            
            # Mostrar resumen final
            st.subheader("📊 Resumen Final de la Migración")
            st.success(f"✅ Matrícula actualizada: {matricula_egresado} → {matricula_contratado}")
            st.success(f"✅ Archivos renombrados: {archivos_renombrados}")
            st.success(f"✅ Registro creado en contratados")
            st.success(f"✅ Registro eliminado de egresados")
            st.success(f"✅ Cambios sincronizados con servidor remoto")
            st.success(f"✅ Notificación enviada")
            
            # Limpiar estado de sesión
            if 'egresado_seleccionado' in st.session_state:
                del st.session_state.egresado_seleccionado
            if 'mostrar_confirmacion_egresado' in st.session_state:
                del st.session_state.mostrar_confirmacion_egresado
            if 'datos_formulario_egresado' in st.session_state:
                del st.session_state.datos_formulario_egresado
            
            # Registrar en log de migración
            logger.log_migration(
                operation="EGRESADO_A_CONTRATADO",
                status="EXITOSA",
                details={
                    'matricula_original': matricula_egresado,
                    'matricula_nueva': matricula_contratado,
                    'tiempo_ejecucion': tiempo_ejecucion,
                    'archivos_renombrados': archivos_renombrados
                }
            )
            
            # Recargar datos
            time.sleep(2)
            st.rerun()
            return True
                
        except Exception as e:
            tiempo_ejecucion = time.time() - inicio_tiempo
            logger.error(f"❌ Error ejecutando la migración: {str(e)}", exc_info=True)
            
            # Registrar migración fallida
            estado_migracion.registrar_migracion(exitoso=False, tiempo_ejecucion=tiempo_ejecucion)
            
            # Enviar notificación de error
            self.notificaciones.enviar_notificacion_migracion(
                tipo_migracion="EGRESADO → CONTRATADO",
                estado="FALLIDA",
                detalles=f"Error: {str(e)}\nTiempo transcurrido: {tiempo_ejecucion:.1f}s"
            )
            
            # Registrar en log de migración
            logger.log_migration(
                operation="EGRESADO_A_CONTRATADO",
                status="FALLIDA",
                details={
                    'error': str(e),
                    'tiempo_ejecucion': tiempo_ejecucion
                }
            )
            
            return False

# Instancia del sistema de migración completo
migrador = SistemaMigracionCompleto()

# =============================================================================
# INTERFAZ PRINCIPAL DEL MIGRADOR - MEJORADA CON PAGINACIÓN
# =============================================================================

def mostrar_login_migracion():
    """Interfaz de login para el migrador - SIEMPRE MOSTRAR FORMULARIO"""
    st.title("🔄 Sistema Escuela Enfermería - Migración SSH REMOTA")
    st.markdown("---")
    
    # Mostrar estado actual
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if estado_migracion.esta_inicializada():
            st.success("✅ Base de datos inicializada")
        else:
            st.warning("⚠️ Base de datos NO inicializada")
    
    with col2:
        if estado_migracion.estado.get('ssh_conectado'):
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
    
    # SIEMPRE mostrar formulario de login, independientemente del estado
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
                    with st.spinner("Verificando credenciales..."):
                        if auth_migracion.verificar_login(usuario, password):
                            st.rerun()
                        else:
                            st.error("❌ Credenciales incorrectas")
                else:
                    st.warning("⚠️ Complete todos los campos")
            
            if inicializar_button:
                with st.spinner("Inicializando base de datos en servidor remoto..."):
                    if db_migracion.sincronizar_desde_remoto():
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

def mostrar_interfaz_migracion():
    """Interfaz principal después del login en el migrador"""
    # Barra superior con información del usuario
    usuario_actual = st.session_state.usuario_actual
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
    
    with col1:
        st.title("🔄 Sistema Escuela Enfermería - Migración SSH REMOTA")
        nombre_usuario = usuario_actual.get('nombre_completo', usuario_actual.get('usuario', 'Usuario'))
        st.write(f"**👤 Administrador:** {nombre_usuario}")
    
    with col2:
        if gestor_remoto_migracion.config.get('host'):
            st.write(f"**🔗 Servidor:** {gestor_remoto_migracion.config['host']}")
    
    with col3:
        if st.button("🔄 Recargar Datos", use_container_width=True):
            migrador.cargar_datos_paginados()
            st.rerun()
    
    with col4:
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
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
    """Interfaz para migración de inscritos a estudiantes con paginación"""
    st.header("📝 Migración: Inscrito → Estudiante")
    
    # Si no hay datos, mostrar mensaje informativo
    if migrador.total_inscritos == 0:
        st.warning("📭 No hay inscritos disponibles para migrar")
        st.info("Los inscritos aparecerán aquí después de que se registren en el sistema principal.")
        
        # Opción para sincronizar
        if st.button("🔄 Sincronizar con servidor remoto"):
            with st.spinner("Sincronizando..."):
                if db_migracion.sincronizar_desde_remoto():
                    migrador.cargar_datos_paginados()
                    st.rerun()
                else:
                    st.error("❌ Error sincronizando")
        
        return
    
    # Mostrar estadísticas
    st.subheader("📊 Inscritos Disponibles para Migración")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Inscritos", migrador.total_inscritos)
    
    with col2:
        st.metric("Página Actual", f"{migrador.current_page_inscritos}/{max(1, migrador.total_pages_inscritos)}")
    
    with col3:
        registros_pagina = len(migrador.df_inscritos)
        st.metric("En esta página", registros_pagina)
    
    # Barra de búsqueda
    st.subheader("🔍 Buscar Inscrito")
    search_term = st.text_input(
        "Buscar por matrícula, nombre o email:", 
        value=migrador.search_term_inscritos,
        key="search_inscritos"
    )
    
    if search_term != migrador.search_term_inscritos:
        migrador.search_term_inscritos = search_term
        migrador.current_page_inscritos = 1
        migrador.cargar_datos_paginados()
        st.rerun()
    
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
                st.write(f"**Fecha Nacimiento:** {inscrito_seleccionado.get('fecha_nacimiento', 'No disponible')}")
                st.write(f"**Dirección:** {inscrito_seleccionado.get('direccion', 'No disponible')}")
            
            with col2:
                st.write("**🎓 Información Académica:**")
                st.write(f"**Programa de Interés:** {inscrito_seleccionado.get('programa_interes', 'No disponible')}")
                st.write(f"**Nivel Académico:** {inscrito_seleccionado.get('nivel_academico', 'No disponible')}")
                st.write(f"**Institución Procedencia:** {inscrito_seleccionado.get('institucion_procedencia', 'No disponible')}")
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
        st.warning("No hay inscritos disponibles para mostrar con los criterios de búsqueda")
    
    # Controles de paginación
    st.markdown("---")
    col_prev, col_page, col_next = st.columns([1, 2, 1])
    
    with col_prev:
        if migrador.current_page_inscritos > 1:
            if st.button("⬅️ Página Anterior", use_container_width=True):
                migrador.current_page_inscritos -= 1
                migrador.cargar_datos_paginados()
                st.rerun()
    
    with col_page:
        st.write(f"**Página {migrador.current_page_inscritos} de {max(1, migrador.total_pages_inscritos)}**")
    
    with col_next:
        if migrador.current_page_inscritos < migrador.total_pages_inscritos:
            if st.button("Página Siguiente ➡️", use_container_width=True):
                migrador.current_page_inscritos += 1
                migrador.cargar_datos_paginados()
                st.rerun()

def mostrar_migracion_estudiantes():
    """Interfaz para migración de estudiantes a egresados con paginación"""
    st.header("🎓 Migración: Estudiante → Egresado")
    
    if migrador.total_estudiantes == 0:
        st.warning("📭 No hay estudiantes disponibles para migrar")
        st.info("Primero necesitas migrar inscritos a estudiantes.")
        return
    
    # Mostrar estadísticas
    st.subheader("📊 Estudiantes Disponibles para Migración")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Estudiantes", migrador.total_estudiantes)
    
    with col2:
        st.metric("Página Actual", f"{migrador.current_page_estudiantes}/{max(1, migrador.total_pages_estudiantes)}")
    
    with col3:
        registros_pagina = len(migrador.df_estudiantes)
        st.metric("En esta página", registros_pagina)
    
    # Barra de búsqueda
    st.subheader("🔍 Buscar Estudiante")
    search_term = st.text_input(
        "Buscar por matrícula, nombre o email:", 
        value=migrador.search_term_estudiantes,
        key="search_estudiantes"
    )
    
    if search_term != migrador.search_term_estudiantes:
        migrador.search_term_estudiantes = search_term
        migrador.current_page_estudiantes = 1
        migrador.cargar_datos_paginados()
        st.rerun()
    
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
                st.write(f"**Fecha Nacimiento:** {estudiante_seleccionado.get('fecha_nacimiento', 'No disponible')}")
                st.write(f"**Dirección:** {estudiante_seleccionado.get('direccion', 'No disponible')}")
            
            with col2:
                st.write("**🎓 Información Académica:**")
                st.write(f"**Programa:** {estudiante_seleccionado.get('programa', 'No disponible')}")
                st.write(f"**Nivel Académico:** {estudiante_seleccionado.get('nivel_academico', 'No disponible')}")
                st.write(f"**Institución Procedencia:** {estudiante_seleccionado.get('institucion_procedencia', 'No disponible')}")
                st.write(f"**Promedio General:** {estudiante_seleccionado.get('promedio_general', 'No disponible')}")
                st.write(f"**Semestre Actual:** {estudiante_seleccionado.get('semestre_actual', 'No disponible')}")
                st.write(f"**Créditos Acumulados:** {estudiante_seleccionado.get('creditos_acumulados', 'No disponible')}")
            
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
        st.warning("No hay estudiantes disponibles para mostrar con los criterios de búsqueda")
    
    # Controles de paginación
    st.markdown("---")
    col_prev, col_page, col_next = st.columns([1, 2, 1])
    
    with col_prev:
        if migrador.current_page_estudiantes > 1:
            if st.button("⬅️ Página Anterior", use_container_width=True):
                migrador.current_page_estudiantes -= 1
                migrador.cargar_datos_paginados()
                st.rerun()
    
    with col_page:
        st.write(f"**Página {migrador.current_page_estudiantes} de {max(1, migrador.total_pages_estudiantes)}**")
    
    with col_next:
        if migrador.current_page_estudiantes < migrador.total_pages_estudiantes:
            if st.button("Página Siguiente ➡️", use_container_width=True):
                migrador.current_page_estudiantes += 1
                migrador.cargar_datos_paginados()
                st.rerun()

def mostrar_migracion_egresados():
    """Interfaz para migración de egresados a contratados con paginación"""
    st.header("💼 Migración: Egresado → Contratado")
    
    if migrador.total_egresados == 0:
        st.warning("📭 No hay egresados disponibles para migrar")
        st.info("Primero necesitas migrar estudiantes a egresados.")
        return
    
    # Mostrar estadísticas
    st.subheader("📊 Egresados Disponibles para Migración")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Egresados", migrador.total_egresados)
    
    with col2:
        st.metric("Página Actual", f"{migrador.current_page_egresados}/{max(1, migrador.total_pages_egresados)}")
    
    with col3:
        registros_pagina = len(migrador.df_egresados)
        st.metric("En esta página", registros_pagina)
    
    # Barra de búsqueda
    st.subheader("🔍 Buscar Egresado")
    search_term = st.text_input(
        "Buscar por matrícula, nombre o email:", 
        value=migrador.search_term_egresados,
        key="search_egresados"
    )
    
    if search_term != migrador.search_term_egresados:
        migrador.search_term_egresados = search_term
        migrador.current_page_egresados = 1
        migrador.cargar_datos_paginados()
        st.rerun()
    
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
                st.write(f"**Fecha Nacimiento:** {egresado_seleccionado.get('fecha_nacimiento', 'No disponible')}")
                st.write(f"**Dirección:** {egresado_seleccionado.get('direccion', 'No disponible')}")
            
            with col2:
                st.write("**🎓 Información Académica/Laboral:**")
                st.write(f"**Programa Original:** {egresado_seleccionado.get('programa', 'No disponible')}")
                st.write(f"**Nivel Académico:** {egresado_seleccionado.get('nivel_academico', 'No disponible')}")
                st.write(f"**Fecha Graduación:** {egresado_seleccionado.get('fecha_graduacion', 'No disponible')}")
                st.write(f"**Promedio Final:** {egresado_seleccionado.get('promedio_final', 'No disponible')}")
                st.write(f"**Empleo Actual:** {egresado_seleccionado.get('empleo_actual', 'No disponible')}")
                st.write(f"**Empresa Actual:** {egresado_seleccionado.get('empresa_actual', 'No disponible')}")
            
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
        st.warning("No hay egresados disponibles para mostrar con los criterios de búsqueda")
    
    # Controles de paginación
    st.markdown("---")
    col_prev, col_page, col_next = st.columns([1, 2, 1])
    
    with col_prev:
        if migrador.current_page_egresados > 1:
            if st.button("⬅️ Página Anterior", use_container_width=True):
                migrador.current_page_egresados -= 1
                migrador.cargar_datos_paginados()
                st.rerun()
    
    with col_page:
        st.write(f"**Página {migrador.current_page_egresados} de {max(1, migrador.total_pages_egresados)}**")
    
    with col_next:
        if migrador.current_page_egresados < migrador.total_pages_egresados:
            if st.button("Página Siguiente ➡️", use_container_width=True):
                migrador.current_page_egresados += 1
                migrador.cargar_datos_paginados()
                st.rerun()

# =============================================================================
# FUNCIÓN PRINCIPAL - MEJORADA CON MANEJO ROBUSTO DE ERRORES
# =============================================================================

def main():
    """Función principal de la aplicación de migración"""
    
    # Sidebar con estado del sistema
    with st.sidebar:
        st.title("🔧 Sistema de Migración")
        st.markdown("---")
        
        st.subheader("🔗 Estado de Conexión SSH")
        
        # Estado de inicialización
        if estado_migracion.esta_inicializada():
            st.success("✅ Base de datos remota inicializada")
            fecha_inicializacion = estado_migracion.obtener_fecha_inicializacion()
            if fecha_inicializacion:
                st.caption(f"📅 Inicializada: {fecha_inicializacion.strftime('%Y-%m-%d %H:%M')}")
        else:
            st.warning("⚠️ Base de datos NO inicializada")
        
        # Estado de conexión SSH
        if estado_migracion.estado.get('ssh_conectado'):
            st.success("✅ SSH Conectado")
            if gestor_remoto_migracion.config.get('host'):
                st.caption(f"🌐 Servidor: {gestor_remoto_migracion.config['host']}")
        else:
            st.error("❌ SSH Desconectado")
            error_ssh = estado_migracion.estado.get('ssh_error')
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
            if gestor_remoto_migracion.config.get('host'):
                st.write(f"**Host:** {gestor_remoto_migracion.config['host']}")
                st.write(f"**Puerto:** {gestor_remoto_migracion.config.get('port', 22)}")
                st.write(f"**Usuario:** {gestor_remoto_migracion.config['username']}")
                st.write(f"**Directorio:** {gestor_remoto_migracion.config.get('remote_dir', '')}")
                st.write(f"**DB Remota:** {gestor_remoto_migracion.config.get('remote_db_escuela', '')}")
        
        st.markdown("---")
        
        # Estadísticas de migración
        st.subheader("📈 Estadísticas")
        stats = estado_migracion.estado.get('estadisticas_migracion', {})
        
        col_stat1, col_stat2 = st.columns(2)
        with col_stat1:
            st.metric("Éxitos", stats.get('exitosas', 0))
        with col_stat2:
            st.metric("Fallidas", stats.get('fallidas', 0))
        
        migraciones = estado_migracion.estado.get('migraciones_realizadas', 0)
        st.metric("Total Migraciones", migraciones)
        
        # Última sincronización
        ultima_sync = estado_migracion.estado.get('ultima_sincronizacion')
        if ultima_sync:
            try:
                fecha_sync = datetime.fromisoformat(ultima_sync)
                st.caption(f"🔄 Última sincronización: {fecha_sync.strftime('%H:%M:%S')}")
            except:
                pass
        
        st.markdown("---")
        
        # Sistema de backups
        st.subheader("💾 Sistema de Backups")
        backups = migrador.backup_system.listar_backups()
        
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
                backup_path = migrador.backup_system.crear_backup_pre_migracion(
                    "MANUAL",
                    "Backup manual creado por el administrador"
                )
                if backup_path:
                    st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                else:
                    st.error("❌ Error creando backup")
        
        st.markdown("---")
        
        # Botones de control - SOLO SI ESTÁ LOGUEADO
        st.subheader("⚙️ Controles")
        
        if st.session_state.get('login_exitoso', False):
            if st.button("🔄 Sincronizar Ahora", use_container_width=True):
                with st.spinner("Sincronizando con servidor remoto..."):
                    if db_migracion.sincronizar_desde_remoto():
                        migrador.cargar_datos_paginados()
                        st.success("✅ Sincronización exitosa")
                        st.rerun()
                    else:
                        st.error("❌ Error sincronizando")
            
            if st.button("🔗 Probar Conexión SSH", use_container_width=True):
                with st.spinner("Probando conexión SSH..."):
                    if gestor_remoto_migracion.verificar_conexion_ssh():
                        st.success("✅ Conexión SSH exitosa")
                        st.rerun()
                    else:
                        st.error("❌ Conexión SSH fallida")
            
            if st.button("📊 Ver Tablas", use_container_width=True):
                try:
                    with db_migracion.get_connection() as conn:
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
    
    try:
        # Inicializar estado de sesión con valores por defecto
        session_defaults = {
            'login_exitoso': False,
            'usuario_actual': None,
            'rol_usuario': None,
            'mostrar_confirmacion_inscrito': False,
            'datos_formulario_inscrito': {},
            'inscrito_seleccionado': None,
            'estudiante_seleccionado': None,
            'egresado_seleccionado': None,
            'mostrar_confirmacion_estudiante': False,
            'datos_formulario_estudiante': {},
            'mostrar_confirmacion_egresado': False,
            'datos_formulario_egresado': {}
        }
        
        for key, default_value in session_defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default_value
        
        # Verificar configuración SSH
        if not gestor_remoto_migracion.config.get('host'):
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
            mostrar_login_migracion()
        else:
            mostrar_interfaz_migracion()
            
    except Exception as e:
        logger.error(f"Error crítico en main(): {e}", exc_info=True)
        
        st.error(f"❌ Error crítico en la aplicación: {str(e)}")
        
        # Información de diagnóstico
        with st.expander("🔧 Información de diagnóstico detallada"):
            st.write("**Estado persistente:**")
            st.json(estado_migracion.estado)
            
            st.write("**Configuración SSH cargada:**")
            if gestor_remoto_migracion.config:
                config_show = gestor_remoto_migracion.config.copy()
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
            for log_file in ['migracion_detallado.log', 'migration_operations.json']:
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
                    if os.path.exists('migracion_detallado.log'):
                        with open('migracion_detallado.log', 'r') as f:
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
        🔄 **SISTEMA DE MIGRACIÓN EXCLUSIVAMENTE REMOTO - VERSIÓN MEJORADA**
        
        **Mejoras implementadas:**
        ✅ Timeouts específicos para operaciones de red
        ✅ Paginación en tablas para mejor rendimiento  
        ✅ Logs detallados para diagnóstico
        ✅ Backups automáticos antes de migraciones
        ✅ Reintentos inteligentes con backoff exponencial
        ✅ Verificación de espacio en disco
        ✅ Sistema de notificaciones para migraciones
        
        **Base de datos actualizada según escuela30.py:**
        ✅ Tablas con campos completos
        ✅ Información personal y académica detallada
        ✅ Tablas de documentos y configuración añadidas
        ✅ Índices optimizados para mejor rendimiento
        
        **Para comenzar:**
        1. Configura secrets.toml con tus credenciales SSH
        2. Haz clic en "Inicializar DB" para crear la base de datos en el servidor
        3. Inicia sesión con las credenciales por defecto
        """)
        
        main()
    except Exception as e:
        st.error(f"❌ Error crítico en la aplicación de migración: {e}")
        logger.critical(f"Error crítico en migración: {e}", exc_info=True)
        
        # Información de diagnóstico final
        with st.expander("🚨 Información de diagnóstico crítico"):
            st.write("**Traceback completo:**")
            import traceback
            st.code(traceback.format_exc())
            
            st.write("**Variables de entorno:**")
            env_vars = {k: v for k, v in os.environ.items() if 'STREAMLIT' in k or 'PYTHON' in k}
            st.json(env_vars)
