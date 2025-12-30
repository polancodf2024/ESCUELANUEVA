#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SISTEMA DE GESTIÓN DE ASPIRANTES - VERSIÓN SEGURA 4.1
Sistema completo con seguridad por roles, autenticación y separación de vistas
"""

# ============================================================================
# CAPA 1: IMPORTS Y CONFIGURACIÓN COMPLETA
# ============================================================================

import streamlit as st
import streamlit_authenticator as stauth
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
import yaml
from yaml.loader import SafeLoader
import bcrypt

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
        st.error("❌ ERROR CRÍTICO: Instalar tomli: pip install tomli")
        st.stop()

# ============================================================================
# CAPA 2: CONSTANTES, CONFIGURACIÓN Y DATOS ESTÁTICOS
# ============================================================================

# Configuración de la aplicación
APP_CONFIG = {
    'app_name': 'Sistema Seguro Escuela Enfermería',
    'version': '4.1',
    'page_title': 'Sistema Escuela Enfermería - Seguro',
    'page_icon': '🏥',
    'layout': 'wide',
    'sidebar_state': 'collapsed',  # Controlado por autenticación
    'backup_dir': 'backups_aspirantes_secure',
    'max_backups': 10,
    'estado_file': 'estado_aspirantes_secure.json',
    'session_timeout_minutes': 60,
    'max_login_attempts': 3
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

# Categorías académicas
CATEGORIAS_ACADEMICAS = [
    {"id": "pregrado", "nombre": "Pregrado", "descripcion": "Programas técnicos y profesional asociado"},
    {"id": "posgrado", "nombre": "Posgrado", "descripcion": "Especialidades, maestrías y doctorados"},
    {"id": "licenciatura", "nombre": "Licenciatura", "descripcion": "Programas de licenciatura"},
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
# CAPA 3: LOGGING Y MANEJO DE ESTADO SEGURO
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

class EstadoPersistenteSeguro:
    """Maneja el estado persistente para el sistema de aspirantes con seguridad"""
    
    def __init__(self, archivo_estado="estado_aspirantes_secure.json"):
        self.archivo_estado = archivo_estado
        self.estado = self._cargar_estado()
        self._limpiar_sesiones_expiradas()
    
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
                    
                    if 'sesiones_activas' not in estado:
                        estado['sesiones_activas'] = {}
                    
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
            'sesiones_activas': {},
            'ultima_sesion': None,
            'ssh_conectado': False,
            'ssh_error': None,
            'ultima_verificacion': None,
            'estadisticas_sistema': {
                'sesiones': 0,
                'registros': 0,
                'total_tiempo': 0,
                'intentos_fallidos': 0
            },
            'backups_realizados': 0,
            'total_inscritos': 0,
            'recordatorios_enviados': 0,
            'duplicados_eliminados': 0,
            'registros_incompletos_eliminados': 0,
            'usuarios_bloqueados': {}
        }
    
    def guardar_estado(self):
        try:
            with open(self.archivo_estado, 'w') as f:
                json.dump(self.estado, f, indent=2, default=str)
            logger.debug(f"Estado guardado en {self.archivo_estado}")
        except Exception as e:
            logger.error(f"❌ Error guardando estado: {e}")
    
    def _limpiar_sesiones_expiradas(self):
        """Eliminar sesiones expiradas"""
        try:
            sesiones_activas = self.estado.get('sesiones_activas', {})
            ahora = datetime.now().timestamp()
            
            sesiones_limpias = {}
            for session_id, session_data in sesiones_activas.items():
                expiracion = session_data.get('expiracion', 0)
                if expiracion > ahora:
                    sesiones_limpias[session_id] = session_data
            
            self.estado['sesiones_activas'] = sesiones_limpias
            self.guardar_estado()
            
        except Exception as e:
            logger.warning(f"Error limpiando sesiones expiradas: {e}")
    
    def registrar_sesion(self, username, user_ip, exitosa=True, tiempo_ejecucion=0):
        """Registrar sesión con información de seguridad"""
        self.estado['sesiones_iniciadas'] = self.estado.get('sesiones_iniciadas', 0) + 1
        self.estado['ultima_sesion'] = datetime.now().isoformat()
        
        if exitosa:
            self.estado['estadisticas_sistema']['sesiones'] += 1
            
            # Registrar sesión activa
            session_id = hashlib.sha256(f"{username}{time.time()}".encode()).hexdigest()[:16]
            expiracion = datetime.now().timestamp() + (APP_CONFIG['session_timeout_minutes'] * 60)
            
            self.estado['sesiones_activas'][session_id] = {
                'username': username,
                'inicio': datetime.now().isoformat(),
                'expiracion': expiracion,
                'ip': user_ip
            }
            
            # Mantener máximo 100 sesiones activas
            if len(self.estado['sesiones_activas']) > 100:
                # Eliminar las más antiguas
                sesiones_ordenadas = sorted(
                    self.estado['sesiones_activas'].items(),
                    key=lambda x: x[1].get('inicio', '')
                )
                for i in range(len(sesiones_ordenadas) - 100):
                    del self.estado['sesiones_activas'][sesiones_ordenadas[i][0]]
        else:
            self.estado['estadisticas_sistema']['intentos_fallidos'] += 1
        
        self.estado['estadisticas_sistema']['total_tiempo'] += tiempo_ejecucion
        self.guardar_estado()
        
        return session_id if exitosa else None
    
    def verificar_usuario_bloqueado(self, username, user_ip):
        """Verificar si usuario está bloqueado por intentos fallidos"""
        bloqueados = self.estado.get('usuarios_bloqueados', {})
        
        # Verificar por usuario
        if username in bloqueados:
            bloqueo_data = bloqueados[username]
            if bloqueo_data.get('hasta', 0) > time.time():
                minutos_restantes = int((bloqueo_data['hasta'] - time.time()) / 60)
                return True, f"Usuario bloqueado. Intente nuevamente en {minutos_restantes} minutos"
        
        # Verificar por IP
        for user_data in bloqueados.values():
            if user_data.get('ip') == user_ip and user_data.get('hasta', 0) > time.time():
                minutos_restantes = int((user_data['hasta'] - time.time()) / 60)
                return True, f"IP bloqueada. Intente nuevamente en {minutos_restantes} minutos"
        
        return False, ""
    
    def registrar_intento_fallido(self, username, user_ip):
        """Registrar intento fallido y bloquear si es necesario"""
        if 'intentos_recientes' not in self.estado:
            self.estado['intentos_recientes'] = {}
        
        key = f"{username}_{user_ip}"
        
        if key not in self.estado['intentos_recientes']:
            self.estado['intentos_recientes'][key] = {
                'intentos': 1,
                'primer_intento': time.time(),
                'ultimo_intento': time.time()
            }
        else:
            self.estado['intentos_recientes'][key]['intentos'] += 1
            self.estado['intentos_recientes'][key]['ultimo_intento'] = time.time()
        
        # Bloquear si hay más de 3 intentos en 5 minutos
        intentos_data = self.estado['intentos_recientes'][key]
        if intentos_data['intentos'] >= APP_CONFIG['max_login_attempts']:
            tiempo_transcurrido = time.time() - intentos_data['primer_intento']
            if tiempo_transcurrido <= 300:  # 5 minutos
                # Bloquear por 15 minutos
                bloqueo_hasta = time.time() + (15 * 60)
                
                if 'usuarios_bloqueados' not in self.estado:
                    self.estado['usuarios_bloqueados'] = {}
                
                self.estado['usuarios_bloqueados'][username] = {
                    'hasta': bloqueo_hasta,
                    'razon': 'demasiados_intentos',
                    'ip': user_ip,
                    'timestamp': datetime.now().isoformat()
                }
                
                logger.warning(f"Usuario {username} bloqueado desde IP {user_ip}")
        
        self.guardar_estado()
    
    def limpiar_intentos_fallidos(self):
        """Limpiar intentos fallidos antiguos"""
        try:
            if 'intentos_recientes' not in self.estado:
                return
            
            ahora = time.time()
            intentos_limpiados = {}
            
            for key, data in self.estado['intentos_recientes'].items():
                if ahora - data['ultimo_intento'] <= 300:  # Mantener solo últimos 5 minutos
                    intentos_limpiados[key] = data
            
            self.estado['intentos_recientes'] = intentos_limpiados
            
            # Limpiar bloqueos expirados
            if 'usuarios_bloqueados' in self.estado:
                bloqueos_limpiados = {}
                for username, bloqueo_data in self.estado['usuarios_bloqueados'].items():
                    if bloqueo_data.get('hasta', 0) > ahora:
                        bloqueos_limpiados[username] = bloqueo_data
                
                self.estado['usuarios_bloqueados'] = bloqueos_limpiados
            
            self.guardar_estado()
            
        except Exception as e:
            logger.warning(f"Error limpiando intentos fallidos: {e}")
    
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
    
    def registrar_backup(self):
        self.estado['backups_realizados'] = self.estado.get('backups_realizados', 0) + 1
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

estado_sistema = EstadoPersistenteSeguro()

# ============================================================================
# CAPA 4: SISTEMA DE SEGURIDAD Y AUTENTICACIÓN
# ============================================================================

class SecurityManager:
    """Gestor de seguridad completo para el sistema"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.auth_config = self._load_auth_config()
        self.authenticator = None
        
    def _load_auth_config(self) -> Dict:
        """Cargar configuración de autenticación"""
        cookie_key = st.secrets.get("COOKIE_KEY", "default-cookie-key-change-in-production")
        
        # Verificar que la clave tenga al menos 32 caracteres
        if len(cookie_key) < 32:
            logger.warning("⚠️ Cookie key demasiado corta. Recomendado: mínimo 32 caracteres")
            # Generar una clave temporal más segura
            cookie_key = hashlib.sha256(cookie_key.encode()).hexdigest()[:32]
        
        return {
            'credentials': {
                'usernames': {}  # Se poblará desde DB
            },
            'cookie': {
                'expiry_days': 1,
                'key': cookie_key,
                'name': 'enfermeria_auth_secure'
            },
            'preauthorized': {
                'emails': st.secrets.get("PREAUTHORIZED_EMAILS", [])
            }
        }
    
    def initialize_admin_user(self):
        """Inicializar usuario admin encriptado"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Verificar si admin ya existe
            cursor.execute("SELECT usuario, password FROM usuarios WHERE usuario = 'admin'")
            admin_data = cursor.fetchone()
            
            if admin_data:
                usuario, password_hash = admin_data
                # Si el password está en texto plano, actualizarlo
                if password_hash == 'admin123' or password_hash == 'Admin123!':
                    # Encriptar con bcrypt
                    hashed_password = bcrypt.hashpw('Admin123!'.encode(), bcrypt.gensalt()).decode()
                    cursor.execute(
                        "UPDATE usuarios SET password = ?, fecha_actualizacion = ? WHERE usuario = 'admin'",
                        (hashed_password, datetime.now().isoformat())
                    )
                    conn.commit()
                    logger.info("✅ Password de admin actualizado y encriptado")
            else:
                # Crear admin con password encriptado
                hashed_password = bcrypt.hashpw('Admin123!'.encode(), bcrypt.gensalt()).decode()
                cursor.execute(
                    """INSERT INTO usuarios 
                       (usuario, password, rol, nombre_completo, email, activo, fecha_creacion) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    ('admin', hashed_password, 'admin', 'Administrador Sistema', 
                     'admin@enfermeria.edu', 1, datetime.now().isoformat())
                )
                conn.commit()
                logger.info("✅ Usuario admin creado con password encriptado")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ Error inicializando admin: {e}")
    
    def load_users_from_db(self):
        """Cargar usuarios desde base de datos"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT usuario, password, rol, nombre_completo, email 
                FROM usuarios 
                WHERE activo = 1
            """)
            usuarios = cursor.fetchall()
            
            # Convertir a formato para streamlit-authenticator
            for usuario in usuarios:
                # Solo agregar si el password parece estar hasheado
                password_hash = usuario['password']
                if password_hash and len(password_hash) > 20:  # Hash mínimo
                    self.auth_config['credentials']['usernames'][usuario['usuario']] = {
                        'name': usuario['nombre_completo'] or usuario['usuario'],
                        'email': usuario['email'] or f"{usuario['usuario']}@enfermeria.edu",
                        'password': password_hash,
                        'rol': usuario['rol'] or 'inscrito'
                    }
                else:
                    logger.warning(f"⚠️ Password inseguro para usuario {usuario['usuario']}")
            
            conn.close()
            logger.info(f"✅ Cargados {len(usuarios)} usuarios desde DB")
            return len(usuarios) > 0
            
        except Exception as e:
            logger.error(f"❌ Error cargando usuarios: {e}")
            return False
    
    def create_authenticator(self):
        """Crear instancia del autenticador"""
        if not self.auth_config['credentials']['usernames']:
            self.load_users_from_db()
        
        self.authenticator = stauth.Authenticate(
            self.auth_config['credentials'],
            self.auth_config['cookie']['name'],
            self.auth_config['cookie']['key'],
            self.auth_config['cookie']['expiry_days'],
            self.auth_config['preauthorized']
        )
        return self.authenticator
    
    def register_new_user(self, username: str, password: str, name: str, email: str, role: str = 'inscrito'):
        """Registrar nuevo usuario (para inscripción pública)"""
        try:
            # Validaciones
            if len(password) < 8:
                raise ValueError("La contraseña debe tener al menos 8 caracteres")
            
            if not re.match(r'^[a-zA-Z0-9_]+$', username):
                raise ValueError("El nombre de usuario solo puede contener letras, números y guiones bajos")
            
            # Verificar si usuario ya existe
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT usuario FROM usuarios WHERE usuario = ?", (username,))
            if cursor.fetchone():
                conn.close()
                raise ValueError("El nombre de usuario ya existe")
            
            # Verificar si email ya existe
            cursor.execute("SELECT email FROM usuarios WHERE email = ?", (email,))
            if cursor.fetchone():
                conn.close()
                raise ValueError("El email ya está registrado")
            
            # Encriptar password con bcrypt
            hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            
            # Generar matrícula única
            matricula = self._generar_matricula()
            
            # Guardar en base de datos
            cursor.execute(
                """INSERT INTO usuarios 
                   (usuario, password, rol, nombre_completo, email, matricula, activo, fecha_creacion) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (username, hashed_password, role, name, email, matricula, 1, datetime.now().isoformat())
            )
            
            conn.commit()
            conn.close()
            
            # Actualizar configuración en memoria
            self.auth_config['credentials']['usernames'][username] = {
                'name': name,
                'email': email,
                'password': hashed_password,
                'rol': role
            }
            
            # Recrear autenticador
            self.create_authenticator()
            
            logger.info(f"✅ Nuevo usuario registrado: {username} ({role})")
            return True, matricula
            
        except ValueError as ve:
            raise ve
        except Exception as e:
            logger.error(f"❌ Error registrando usuario: {e}")
            raise ValueError(f"Error al registrar usuario: {str(e)}")
    
    def _generar_matricula(self):
        """Generar matrícula única"""
        fecha = datetime.now().strftime('%y%m%d')
        random_num = ''.join(random.choices(string.digits, k=4))
        return f"USR{fecha}{random_num}"
    
    def verify_password_strength(self, password):
        """Verificar fortaleza de contraseña"""
        if len(password) < 8:
            return False, "La contraseña debe tener al menos 8 caracteres"
        
        if not re.search(r'[A-Z]', password):
            return False, "Debe contener al menos una mayúscula"
        
        if not re.search(r'[a-z]', password):
            return False, "Debe contener al menos una minúscula"
        
        if not re.search(r'[0-9]', password):
            return False, "Debe contener al menos un número"
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Debe contener al menos un carácter especial"
        
        return True, "Contraseña segura"

# ============================================================================
# CAPA 5: UTILIDADES Y SERVICIOS BASE SEGUROS
# ============================================================================

class UtilidadesSistemaSeguro:
    """Utilidades para verificación de disco y red con seguridad"""
    
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
    
    @staticmethod
    def obtener_ip_usuario():
        """Obtener IP del usuario (simplificado para Streamlit)"""
        try:
            # En Streamlit Cloud, esto obtiene la IP real
            query_params = st.experimental_get_query_params()
            client_ip = query_params.get('client_ip', ['unknown'])[0]
            
            # Si no está disponible, usar placeholder
            if client_ip == 'unknown':
                # Intentar obtener de headers (no siempre disponible)
                try:
                    import requests
                    response = requests.get('https://api.ipify.org?format=json', timeout=2)
                    if response.status_code == 200:
                        client_ip = response.json()['ip']
                    else:
                        client_ip = '127.0.0.1'
                except:
                    client_ip = '127.0.0.1'
            
            return client_ip
        except Exception as e:
            logger.warning(f"No se pudo obtener IP: {e}")
            return '127.0.0.1'

class ValidadorDatosSeguro:
    """Clase para validaciones de datos mejoradas con seguridad"""
    
    @staticmethod
    def validar_email(email):
        if not email:
            return False
        
        # Patrón básico de email
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        # Verificar que no tenga caracteres peligrosos
        if re.search(r'[<>\"\'();]', email):
            return False
        
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validar_email_gmail(email):
        if not email:
            return False
        
        # Validar que sea Gmail y tenga formato seguro
        pattern = r'^[a-zA-Z0-9._%+-]+@gmail\.com$'
        
        # Verificar longitud máxima
        if len(email) > 100:
            return False
        
        # Verificar caracteres peligrosos
        if re.search(r'[<>\"\'();]', email):
            return False
        
        return bool(re.match(pattern, email))
    
    @staticmethod
    def sanitizar_input(texto, max_length=500):
        """Sanitizar entrada de texto para prevenir XSS"""
        if not texto:
            return ""
        
        # Truncar si es muy largo
        if len(texto) > max_length:
            texto = texto[:max_length]
        
        # Eliminar caracteres peligrosos
        texto = re.sub(r'[<>\"\'();]', '', texto)
        
        # Escapar caracteres HTML
        texto = (texto.replace('&', '&amp;')
                      .replace('<', '&lt;')
                      .replace('>', '&gt;')
                      .replace('"', '&quot;')
                      .replace("'", '&#x27;'))
        
        return texto
    
    @staticmethod
    def validar_telefono(telefono):
        if not telefono:
            return True
        
        # Eliminar espacios y caracteres no numéricos
        digitos = ''.join(filter(str.isdigit, telefono))
        
        # Verificar longitud (México: 10 dígitos)
        if len(digitos) != 10:
            return False
        
        # Verificar que sea un número válido (no todos ceros, etc.)
        if digitos == '0' * 10:
            return False
        
        return True
    
    @staticmethod
    def validar_nombre_completo(nombre):
        if not nombre:
            return False
        
        # Sanitizar nombre
        nombre = ValidadorDatosSeguro.sanitizar_input(nombre, 100)
        
        # Verificar longitud mínima
        if len(nombre.strip()) < 5:
            return False
        
        # Verificar que tenga al menos 2 palabras
        palabras = nombre.strip().split()
        if len(palabras) < 2:
            return False
        
        # Verificar que cada palabra tenga al menos 2 caracteres
        for palabra in palabras:
            if len(palabra) < 2:
                return False
        
        return True
    
    @staticmethod
    def validar_fecha_nacimiento(fecha_str):
        try:
            if not fecha_str:
                return True
            
            # Verificar formato
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            hoy = date.today()
            
            # Verificar que no sea futura
            if fecha > hoy:
                return False
            
            # Calcular edad
            edad = hoy.year - fecha.year - ((hoy.month, hoy.day) < (fecha.month, fecha.day))
            
            # Rango de edad razonable para estudiantes (15-70 años)
            return 15 <= edad <= 70
            
        except:
            return False
    
    @staticmethod
    def validar_matricula(matricula):
        if not matricula:
            return False
        
        # Sanitizar
        matricula = ValidadorDatosSeguro.sanitizar_input(matricula, 20)
        
        # Verificar formato básico
        return matricula.startswith('INS') and len(matricula) >= 10
    
    @staticmethod
    def validar_folio(folio):
        if not folio:
            return False
        
        # Sanitizar
        folio = ValidadorDatosSeguro.sanitizar_input(folio, 20)
        
        # Verificar formato básico
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
# CAPA 6: GESTIÓN DE CONEXIÓN SSH SEGURA
# ============================================================================

class GestorConexionRemotaSeguro:
    """Gestor de conexión SSH al servidor remoto con seguridad mejorada"""
    
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
        
        logger.info(f"🔗 Configuración SSH cargada para {self.config.get('host', 'No configurado')}")
        
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
                'db_local_path': paths_config.get('db_aspirantes', ''),
                'uploads_path_local': paths_config.get('uploads_path', '')
            })
            
            smtp_config = {
                'smtp_server': self.config_completa.get('smtp_server', ''),
                'smtp_port': self.config_completa.get('smtp_port', 587),
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
        
        # Limpiar archivos temporales antiguos (> 1 hora)
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
            
            if not UtilidadesSistemaSeguro.verificar_conectividad_red():
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
            espacio_ok, espacio_mb = UtilidadesSistemaSeguro.verificar_espacio_disco(temp_dir)
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
                
                espacio_ok, espacio_mb = UtilidadesSistemaSeguro.verificar_espacio_disco(temp_dir, espacio_minimo_mb=200)
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
            
            # Verificar que existan tablas esenciales
            tablas_esenciales = ['usuarios', 'inscritos', 'documentos_programa']
            tablas_encontradas = [t[0] for t in tablas]
            
            for tabla in tablas_esenciales:
                if tabla not in tablas_encontradas:
                    logger.warning(f"⚠️ Falta tabla esencial: {tabla}")
                    return False
            
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
            self._inicializar_db_estructura_completa_segura(temp_db_path)
            
            if self.conectar_ssh():
                try:
                    if not self.db_path_remoto:
                        raise Exception("No se configuró la ruta de la base de datos remota")
                    
                    remote_dir = os.path.dirname(self.db_path_remoto)
                    try:
                        self.sftp.stat(remote_dir)
                    except:
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
    
    def _crear_directorio_remoto_recursivo(self, remote_path):
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
    
    def _inicializar_db_estructura_completa_segura(self, db_path):
        try:
            logger.info(f"📝 Inicializando estructura COMPLETA SEGURA en: {db_path}")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Tabla de usuarios con campos de seguridad
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
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ultimo_acceso TIMESTAMP,
                    categoria_academica TEXT,
                    tipo_programa TEXT,
                    acepto_privacidad INTEGER DEFAULT 0,
                    acepto_convocatoria INTEGER DEFAULT 0,
                    intentos_fallidos INTEGER DEFAULT 0,
                    bloqueado_hasta TIMESTAMP,
                    CHECK (rol IN ('admin', 'secretaria', 'inscrito', 'publico'))
                )
            ''')
            
            # Tabla de inscritos
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
            
            # Tabla de documentos
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
            
            # Tabla de estudios socioeconómicos
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
            
            # Tabla de logs de seguridad
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS logs_seguridad (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usuario TEXT,
                    accion TEXT,
                    recurso TEXT,
                    ip TEXT,
                    exito INTEGER,
                    detalles TEXT
                )
            ''')
            
            # Insertar documentos
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
            
            # Crear usuario admin con password encriptado
            admin_password = bcrypt.hashpw('Admin123!'.encode(), bcrypt.gensalt()).decode()
            cursor.execute('''
                INSERT OR IGNORE INTO usuarios 
                (usuario, password, rol, nombre_completo, email, matricula, activo)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', ('admin', admin_password, 'admin', 'Administrador Sistema', 
                  'admin@enfermeria.edu', 'ADMIN-001', 1))
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Estructura de base de datos COMPLETA SEGURA inicializada en {db_path}")
            
            estado_sistema.marcar_db_inicializada()
            
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura segura: {e}", exc_info=True)
            raise
    
    def subir_db_remota(self, ruta_local):
        try:
            logger.info(f"📤 Subiendo base de datos al servidor remoto...")
            
            if not self.conectar_ssh():
                return False
            
            if not self.db_path_remoto:
                logger.error("No se configuró la ruta de la base de datos remota")
                return False
            
            # Crear backup en servidor
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = f"{self.db_path_remoto}.backup_{timestamp}"
                self.sftp.rename(self.db_path_remoto, backup_path)
                logger.info(f"✅ Backup creado en servidor: {backup_path}")
                estado_sistema.registrar_backup()
            except Exception as e:
                logger.warning(f"⚠️ No se pudo crear backup en servidor: {e}")
            
            # Subir nueva base de datos
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

# Inicializar gestor remoto seguro
gestor_remoto = GestorConexionRemotaSeguro()

# ============================================================================
# CAPA 7: SISTEMA DE BASE DE DATOS SEGURO
# ============================================================================

class SistemaBaseDatosSeguro:
    """Sistema de base de datos SQLite SEGURO con todos los cambios"""
    
    def __init__(self):
        self.gestor = gestor_remoto
        self.db_local_temp = None
        self.conexion_actual = None
        self.ultima_sincronizacion = None
        self.validador = ValidadorDatosSeguro()
        self.security_manager = None
    
    def set_security_manager(self, security_manager):
        """Establecer el gestor de seguridad"""
        self.security_manager = security_manager
    
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
                
                # Verificar integridad
                try:
                    conn = sqlite3.connect(self.db_local_temp)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tablas = cursor.fetchall()
                    conn.close()
                    
                    logger.info(f"✅ Base de datos verificada: {len(tablas)} tablas")
                    
                    if len(tablas) == 0:
                        logger.warning("⚠️ Base de datos vacía, inicializando estructura completa segura...")
                        self._inicializar_estructura_db_segura()
                except Exception as e:
                    logger.error(f"❌ Base de datos corrupta: {e}")
                    raise Exception(f"Base de datos corrupta: {e}")
                
                self.ultima_sincronizacion = datetime.now()
                tiempo_total = time.time() - inicio_tiempo
                
                logger.info(f"✅ Sincronización exitosa en {tiempo_total:.1f}s: {self.db_local_temp}")
                estado_sistema.marcar_sincronizacion()
                
                # Inicializar gestor de seguridad con la base de datos
                if self.security_manager is None:
                    self.security_manager = SecurityManager(self.db_local_temp)
                    self.security_manager.initialize_admin_user()
                    self.security_manager.load_users_from_db()
                
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
    
    def _inicializar_estructura_db_segura(self):
        try:
            if not self.db_local_temp:
                logger.error("❌ No hay ruta de base de datos para inicializar")
                return
            
            self.gestor._inicializar_db_estructura_completa_segura(self.db_local_temp)
            
        except Exception as e:
            logger.error(f"❌ Error inicializando estructura segura: {e}", exc_info=True)
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
    def get_connection(self, user_role='publico'):
        conn = None
        try:
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                if not self.sincronizar_desde_remoto():
                    raise Exception("No se pudo sincronizar la base de datos")
            
            conn = sqlite3.connect(self.db_local_temp)
            conn.row_factory = sqlite3.Row
            
            # Configurar timeout y journal mode
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA journal_mode = WAL")
            
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
    
    def ejecutar_query_segura(self, query, params=(), user_role='publico', username=None):
        """Ejecutar query con validaciones de seguridad por rol"""
        try:
            # Validar query según rol
            if user_role in ['publico', 'inscrito']:
                # Usuarios públicos solo pueden hacer SELECT de sus propios datos
                query_upper = query.strip().upper()
                if query_upper.startswith(('INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE')):
                    raise PermissionError(f"Rol '{user_role}' no tiene permisos para esta operación")
            
            # Sanitizar parámetros
            params_sanitizados = []
            for param in params:
                if isinstance(param, str):
                    param = ValidadorDatosSeguro.sanitizar_input(param)
                params_sanitizados.append(param)
            
            with self.get_connection(user_role) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params_sanitizados)
                
                if query.strip().upper().startswith('SELECT'):
                    resultados = cursor.fetchall()
                    # Filtrar resultados según rol
                    if user_role in ['publico', 'inscrito'] and username:
                        resultados = self._filtrar_resultados_por_usuario(resultados, username, query)
                    
                    resultados = [dict(row) for row in resultados]
                    return resultados
                else:
                    ultimo_id = cursor.lastrowid
                    return ultimo_id
                    
        except PermissionError as pe:
            logger.warning(f"⛔ Intento de acceso no autorizado: {pe}")
            raise
        except Exception as e:
            logger.error(f"❌ Error ejecutando query segura: {e} - Query: {query[:100]}...")
            return None
    
    def _filtrar_resultados_por_usuario(self, resultados, username, query):
        """Filtrar resultados para que usuarios solo vean sus datos"""
        if not resultados:
            return resultados
        
        resultados_filtrados = []
        
        # Determinar qué tabla se está consultando
        if 'FROM inscritos' in query.upper():
            # Para inscritos, filtrar por email o matrícula
            for row in resultados:
                row_dict = dict(row)
                if (row_dict.get('email') == username or 
                    row_dict.get('email_gmail') == username or
                    row_dict.get('matricula') == username):
                    resultados_filtrados.append(row)
        elif 'FROM usuarios' in query.upper():
            # Para usuarios, solo permitir ver su propio registro
            for row in resultados:
                row_dict = dict(row)
                if row_dict.get('usuario') == username or row_dict.get('email') == username:
                    resultados_filtrados.append(row)
        else:
            # Para otras tablas, no permitir acceso
            return []
        
        return resultados_filtrados
    
    def agregar_inscrito_completo_seguro(self, datos_inscrito, username):
        """Agregar inscrito con validaciones de seguridad"""
        try:
            # Validar datos
            if datos_inscrito.get('email_gmail'):
                if not self.validador.validar_email_gmail(datos_inscrito['email_gmail']):
                    raise ValueError("❌ El correo debe ser de dominio @gmail.com")
            
            # Verificar duplicados
            query_check = '''
                SELECT COUNT(*) as count FROM inscritos 
                WHERE email = ? OR email_gmail = ?
            '''
            resultado = self.ejecutar_query_segura(query_check, (
                datos_inscrito['email'],
                datos_inscrito.get('email_gmail', '')
            ), user_role='publico', username=username)
            
            if resultado and resultado[0]['count'] > 0:
                estado_sistema.registrar_duplicado_eliminado()
                raise ValueError("❌ Ya existe un registro con este correo electrónico")
            
            # Generar identificadores únicos
            folio_unico = self.generar_folio_unico()
            fecha_limite = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
            
            # Insertar inscrito
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
                    completado, observaciones, usuario_actualizacion
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            
            params_inscrito = (
                datos_inscrito.get('matricula', ''),
                folio_unico,
                self.validador.sanitizar_input(datos_inscrito.get('nombre_completo', '')),
                datos_inscrito.get('email', ''),
                datos_inscrito.get('email_gmail', ''),
                datos_inscrito.get('telefono', ''),
                datos_inscrito.get('tipo_programa', ''),
                datos_inscrito.get('categoria_academica', ''),
                self.validador.sanitizar_input(datos_inscrito.get('programa_interes', '')),
                datos_inscrito.get('estado_civil', ''),
                datos_inscrito.get('edad', None),
                self.validador.sanitizar_input(datos_inscrito.get('domicilio', '')),
                self.validador.sanitizar_input(datos_inscrito.get('licenciatura_origen', '')),
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
                self.validador.sanitizar_input(datos_inscrito.get('observaciones', '')),
                username
            )
            
            inscrito_id = self.ejecutar_query_segura(query_inscrito, params_inscrito, 
                                                    user_role='publico', username=username)
            
            # Insertar estudio socioeconómico si existe
            if datos_inscrito.get('estudio_socioeconomico_detallado'):
                self.guardar_estudio_socioeconomico(inscrito_id, datos_inscrito['estudio_socioeconomico_detallado'], username)
            
            logger.info(f"✅ Inscrito agregado por {username}: {datos_inscrito.get('matricula')} - Folio: {folio_unico}")
            
            return inscrito_id, folio_unico
            
        except Exception as e:
            logger.error(f"❌ Error agregando inscrito seguro: {e}")
            raise
    
    def generar_folio_unico(self):
        fecha = datetime.now().strftime('%y%m%d')
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"FOL{fecha}{random_str}"
    
    def guardar_estudio_socioeconomico(self, inscrito_id, datos_estudio, username):
        try:
            query = '''
                INSERT INTO estudios_socioeconomicos (
                    inscrito_id, ingreso_familiar, personas_dependientes,
                    vivienda_propia, transporte_propio, seguro_medico,
                    discapacidad, beca_solicitada, trabajo_estudiantil, detalles
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            
            self.ejecutar_query_segura(query, (
                inscrito_id,
                datos_estudio.get('ingreso_familiar'),
                datos_estudio.get('personas_dependientes'),
                1 if datos_estudio.get('vivienda_propia') else 0,
                1 if datos_estudio.get('transporte_propio') else 0,
                self.validador.sanitizar_input(datos_estudio.get('seguro_medico', '')),
                1 if datos_estudio.get('discapacidad') else 0,
                1 if datos_estudio.get('beca_solicitada') else 0,
                1 if datos_estudio.get('trabajo_estudiantil') else 0,
                self.validador.sanitizar_input(datos_estudio.get('detalles', ''))
            ), user_role='publico', username=username)
            
            logger.info(f"✅ Estudio socioeconómico guardado por {username} para inscrito {inscrito_id}")
            
        except Exception as e:
            logger.error(f"❌ Error guardando estudio socioeconómico: {e}")
    
    def obtener_documentos_faltantes(self, inscrito_id, username):
        try:
            # Verificar que el usuario tenga acceso a este inscrito
            query_verificacion = "SELECT email, email_gmail, matricula FROM inscritos WHERE id = ?"
            resultado = self.ejecutar_query_segura(query_verificacion, (inscrito_id,), 
                                                  user_role='publico', username=username)
            
            if not resultado:
                raise PermissionError("No tienes permisos para acceder a estos datos")
            
            # Continuar con la consulta original
            query_tipo = "SELECT tipo_programa FROM inscritos WHERE id = ?"
            tipo_result = self.ejecutar_query_segura(query_tipo, (inscrito_id,), 
                                                    user_role='publico', username=username)
            
            if not tipo_result:
                return []
            
            tipo_programa = tipo_result[0]['tipo_programa']
            
            query_docs = '''
                SELECT nombre_documento FROM documentos_programa 
                WHERE tipo_programa = ? AND obligatorio = 1
                ORDER BY orden
            '''
            documentos_obligatorios = self.ejecutar_query_segura(query_docs, (tipo_programa,), 
                                                                user_role='publico', username=username)
            
            query_subidos = "SELECT documentos_guardados FROM inscritos WHERE id = ?"
            subidos_result = self.ejecutar_query_segura(query_subidos, (inscrito_id,), 
                                                       user_role='publico', username=username)
            
            documentos_subidos = []
            if subidos_result and subidos_result[0]['documentos_guardados']:
                documentos_subidos = subidos_result[0]['documentos_guardados'].split(', ')
            
            obligatorios_nombres = [doc['nombre_documento'] for doc in documentos_obligatorios]
            faltantes = [doc for doc in obligatorios_nombres if doc not in documentos_subidos]
            
            if faltantes:
                query_update = "UPDATE inscritos SET documentos_faltantes = ? WHERE id = ?"
                self.ejecutar_query_segura(query_update, (', '.join(faltantes), inscrito_id), 
                                          user_role='publico', username=username)
            
            return faltantes
            
        except PermissionError as pe:
            logger.warning(f"⛔ Intento de acceso no autorizado a documentos: {pe}")
            return []
        except Exception as e:
            logger.error(f"❌ Error obteniendo documentos faltantes: {e}")
            return []
    
    def enviar_recordatorio(self, inscrito_id, username):
        try:
            # Verificar permisos
            query_verificacion = "SELECT id FROM inscritos WHERE id = ?"
            resultado = self.ejecutar_query_segura(query_verificacion, (inscrito_id,), 
                                                  user_role='secretaria', username=username)
            
            if not resultado:
                raise PermissionError("No tienes permisos para enviar recordatorios")
            
            # Continuar con la lógica original
            query = '''
                SELECT nombre_completo, email, email_gmail, fecha_limite_registro 
                FROM inscritos WHERE id = ? AND recordatorio_enviado = 0
            '''
            resultado = self.ejecutar_query_segura(query, (inscrito_id,), 
                                                  user_role='secretaria', username=username)
            
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
                self.ejecutar_query_segura(query_update, (datetime.now().isoformat(), inscrito_id), 
                                          user_role='secretaria', username=username)
                
                estado_sistema.registrar_recordatorio()
                logger.info(f"✅ Recordatorio enviado por {username} para inscrito {inscrito_id} ({dias_restantes} días restantes)")
                return True
            
            return False
            
        except PermissionError as pe:
            logger.warning(f"⛔ Intento no autorizado de enviar recordatorio: {pe}")
            return False
        except Exception as e:
            logger.error(f"❌ Error enviando recordatorio: {e}")
            return False
    
    def limpiar_registros_incompletos(self, dias_inactividad=7, username='admin'):
        try:
            # Solo admin puede limpiar registros
            if not username or username != 'admin':
                raise PermissionError("Solo administradores pueden limpiar registros")
            
            fecha_limite = (datetime.now() - timedelta(days=dias_inactividad)).date()
            
            query = '''
                DELETE FROM inscritos 
                WHERE completado = 0 
                AND DATE(fecha_registro) < ?
                AND documentos_subidos < 5
            '''
            
            with self.get_connection('admin') as conn:
                cursor = conn.cursor()
                cursor.execute(query, (fecha_limite.isoformat(),))
                eliminados = cursor.rowcount
            
            estado_sistema.registrar_registro_incompleto_eliminado(eliminados)
            logger.info(f"🗑️ Eliminados {eliminados} registros incompletos por {username}")
            return eliminados
            
        except PermissionError as pe:
            logger.warning(f"⛔ Intento no autorizado de limpiar registros: {pe}")
            return 0
        except Exception as e:
            logger.error(f"❌ Error limpiando registros incompletos: {e}")
            return 0
    
    def obtener_inscritos(self, username, user_role):
        try:
            if user_role in ['admin', 'secretaria']:
                # Admin y secretaria ven todos
                query = "SELECT * FROM inscritos ORDER BY fecha_registro DESC"
                resultados = self.ejecutar_query_segura(query, user_role=user_role, username=username)
            else:
                # Usuarios normales solo ven sus datos
                query = """
                    SELECT * FROM inscritos 
                    WHERE email = ? OR email_gmail = ? OR matricula = ?
                    ORDER BY fecha_registro DESC
                """
                resultados = self.ejecutar_query_segura(query, (username, username, username), 
                                                       user_role=user_role, username=username)
            
            return resultados if resultados else []
        except Exception as e:
            logger.error(f"❌ Error obteniendo inscritos: {e}")
            return []
    
    def obtener_inscrito_por_matricula(self, matricula, username, user_role):
        try:
            query = "SELECT * FROM inscritos WHERE matricula = ?"
            resultados = self.ejecutar_query_segura(query, (matricula,), 
                                                   user_role=user_role, username=username)
            
            if resultados:
                # Verificar permisos
                inscrito = resultados[0]
                if user_role in ['admin', 'secretaria']:
                    return inscrito
                elif (inscrito.get('email') == username or 
                      inscrito.get('email_gmail') == username or
                      inscrito.get('matricula') == username):
                    return inscrito
                else:
                    raise PermissionError("No tienes permisos para ver este registro")
            
            return None
            
        except PermissionError as pe:
            raise pe
        except Exception as e:
            logger.error(f"❌ Error obteniendo inscrito: {e}")
            return None
    
    def obtener_total_inscritos(self, username, user_role):
        try:
            if user_role in ['admin', 'secretaria']:
                query = "SELECT COUNT(*) as total FROM inscritos"
                resultados = self.ejecutar_query_segura(query, user_role=user_role, username=username)
            else:
                query = """
                    SELECT COUNT(*) as total FROM inscritos 
                    WHERE email = ? OR email_gmail = ? OR matricula = ?
                """
                resultados = self.ejecutar_query_segura(query, (username, username, username), 
                                                       user_role=user_role, username=username)
            
            total = resultados[0]['total'] if resultados else 0
            
            # Solo admin actualiza el estado global
            if user_role == 'admin':
                estado_sistema.set_total_inscritos(total)
            
            return total
        except Exception as e:
            logger.error(f"❌ Error obteniendo total: {e}")
            return 0

# Inicializar base de datos segura
db_segura = SistemaBaseDatosSeguro()

# ============================================================================
# CAPA 8: COMPONENTES UI SEGUROS
# ============================================================================

class ComponentesUISeguro:
    """Componentes UI reutilizables con seguridad"""
    
    @staticmethod
    def mostrar_header(titulo, subtitulo="", nivel=1):
        if nivel == 1:
            st.markdown(f"""
            <style>
            .main-header-seguro {{
                font-size: 2.5rem;
                color: #2E86AB;
                text-align: center;
                margin-bottom: 1rem;
                font-weight: bold;
                padding: 10px;
                background-color: #f8f9fa;
                border-radius: 10px;
                border-left: 5px solid #A23B72;
            }}
            .sub-header-seguro {{
                font-size: 1.5rem;
                color: #A23B72;
                margin-bottom: 2rem;
                font-weight: 600;
                text-align: center;
            }}
            </style>
            """, unsafe_allow_html=True)
            
            st.markdown(f'<div class="main-header-seguro">{titulo}</div>', unsafe_allow_html=True)
            if subtitulo:
                st.markdown(f'<div class="sub-header-seguro">{subtitulo}</div>', unsafe_allow_html=True)
        else:
            st.title(titulo)
            if subtitulo:
                st.subheader(subtitulo)
        
        st.markdown("---")
    
    @staticmethod
    def crear_sidebar_seguro(usuario_nombre, usuario_rol, seguridad_manager):
        with st.sidebar:
            # Información del usuario
            st.title(f"🏥 {usuario_nombre}")
            st.caption(f"Rol: {usuario_rol}")
            
            # Estado del sistema
            st.markdown("---")
            st.subheader("🔍 Estado del Sistema")
            
            col_est1, col_est2 = st.columns(2)
            with col_est1:
                if estado_sistema.esta_inicializada():
                    st.success("✅ BD")
                else:
                    st.error("❌ BD")
            
            with col_est2:
                if estado_sistema.estado.get('ssh_conectado'):
                    st.success("✅ SSH")
                else:
                    st.error("❌ SSH")
            
            # Estadísticas según rol
            st.markdown("---")
            if usuario_rol in ['admin', 'secretaria']:
                st.subheader("📊 Estadísticas")
                
                col_stat1, col_stat2 = st.columns(2)
                with col_stat1:
                    total_inscritos = estado_sistema.estado.get('total_inscritos', 0)
                    st.metric("Inscritos", total_inscritos)
                
                with col_stat2:
                    recordatorios = estado_sistema.estado.get('recordatorios_enviados', 0)
                    st.metric("Recordatorios", recordatorios)
            
            # Navegación según rol
            st.markdown("---")
            st.subheader("📱 Navegación")
            
            return ComponentesUISeguro._obtener_opciones_menu(usuario_rol)
    
    @staticmethod
    def _obtener_opciones_menu(rol):
        """Obtener opciones de menú según rol"""
        if rol == 'admin':
            return [
                "🏠 Inicio y Resumen",
                "📝 Nueva Pre-Inscripción",
                "📋 Consultar Inscritos",
                "👥 Gestión de Usuarios",
                "⚙️ Configuración",
                "📊 Reportes y Backups"
            ]
        elif rol == 'secretaria':
            return [
                "🏠 Inicio",
                "📝 Nueva Pre-Inscripción",
                "📋 Consultar Inscritos",
                "📊 Reportes Básicos"
            ]
        elif rol == 'inscrito':
            return [
                "👤 Mi Perfil",
                "📄 Mis Documentos",
                "📋 Mi Progreso"
            ]
        else:  # publico
            return [
                "📝 Inscripción Pública"
            ]
    
    @staticmethod
    def crear_paso_formulario_seguro(numero, titulo, contenido_func, expandido=True):
        with st.expander(f"🔒 PASO {numero}: {titulo}", expanded=expandido):
            return contenido_func()
    
    @staticmethod
    def mostrar_mensaje_exito(titulo, detalles):
        st.success(f"✅ **{titulo}**")
        st.markdown(f"""
        <div style="background-color: #d4edda; padding: 15px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #28a745;">
        {detalles}
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def mostrar_mensaje_error(titulo, detalles):
        st.error(f"❌ **{titulo}**")
        st.markdown(f"""
        <div style="background-color: #f8d7da; padding: 15px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #dc3545;">
        {detalles}
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def mostrar_mensaje_advertencia(titulo, detalles):
        st.warning(f"⚠️ **{titulo}**")
        st.markdown(f"""
        <div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #ffc107;">
        {detalles}
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def crear_boton_accion_seguro(texto, tipo="primary", container=True, disabled=False):
        return st.button(texto, type=tipo, use_container_width=container, disabled=disabled)
    
    @staticmethod
    def mostrar_panel_seguridad(usuario_rol, ultimo_acceso=None):
        """Mostrar panel de información de seguridad"""
        if usuario_rol in ['admin', 'secretaria']:
            with st.expander("🔐 Información de Seguridad", expanded=False):
                col_sec1, col_sec2 = st.columns(2)
                
                with col_sec1:
                    st.metric("Sesiones Activas", len(estado_sistema.estado.get('sesiones_activas', {})))
                    if ultimo_acceso:
                        st.caption(f"Último acceso: {ultimo_acceso}")
                
                with col_sec2:
                    st.metric("Intentos Fallidos", estado_sistema.estado.get('estadisticas_sistema', {}).get('intentos_fallidos', 0))
                    st.caption(f"Usuarios bloqueados: {len(estado_sistema.estado.get('usuarios_bloqueados', {}))}")

# ============================================================================
# CAPA 9: SISTEMA DE INSCRITOS SEGURO
# ============================================================================

class SistemaInscritosSeguro:
    """Sistema principal de gestión de inscritos SEGURO"""
    
    def __init__(self, seguridad_manager):
        self.base_datos = db_segura
        self.seguridad = seguridad_manager
        self.base_datos.set_security_manager(seguridad_manager)
        self.validador = ValidadorDatosSeguro()
        
        logger.info("🔐 Sistema de inscritos SEGURO inicializado")
    
    def mostrar_formulario_publico(self):
        """Mostrar formulario para usuarios públicos (sin login)"""
        ComponentesUISeguro.mostrar_header(
            "📝 Formulario de Pre-Inscripción Pública", 
            "Escuela de Enfermería - Convocatoria Febrero 2026", nivel=1
        )
        
        st.info("""
        **Instrucciones para inscripción pública:**
        1. Completa todos los campos obligatorios (*)
        2. Asegúrate de usar un correo Gmail válido
        3. Guarda tu folio único para consultar resultados
        4. Los resultados se publican de forma anónima
        """)
        
        if 'formulario_publico_enviado' not in st.session_state:
            st.session_state.formulario_publico_enviado = False
        
        if not st.session_state.formulario_publico_enviado:
            with st.form("formulario_publico", clear_on_submit=True):
                # Generar identificador temporal para usuario público
                if 'usuario_publico_id' not in st.session_state:
                    st.session_state.usuario_publico_id = f"publico_{int(time.time())}_{random.randint(1000, 9999)}"
                
                # PASO 1: Selección de programa
                seleccion_programa = self._mostrar_paso_seleccion_programa_publico()
                
                st.markdown("---")
                
                # PASO 2: Datos personales
                datos_personales = self._mostrar_paso_datos_personales_publico(seleccion_programa["tipo_programa"])
                
                st.markdown("---")
                
                # PASO 3: Documentación
                documentos = self._mostrar_paso_documentacion_publico(seleccion_programa["tipo_programa"])
                
                st.markdown("---")
                
                # PASO 4: Aceptaciones
                aceptaciones = self._mostrar_paso_aceptaciones_publico()
                
                st.markdown("---")
                
                # Botón de envío
                col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
                with col_btn2:
                    enviado = st.form_submit_button(
                        "🚀 **ENVIAR SOLICITUD DE PRE-INSCRIPCIÓN**", 
                        use_container_width=True, type="primary"
                    )
                
                if enviado:
                    self._procesar_envio_publico(
                        seleccion_programa,
                        datos_personales,
                        documentos,
                        aceptaciones
                    )
        
        else:
            self._mostrar_resultado_exitoso_publico()
    
    def _mostrar_paso_seleccion_programa_publico(self):
        col_cat1, col_cat2 = st.columns(2)
        
        with col_cat1:
            categoria_academica = st.selectbox(
                "**Categoría Académica ***",
                [c["nombre"] for c in CATEGORIAS_ACADEMICAS],
                format_func=lambda x: x.replace("_", " ").title(),
                help="Selecciona la categoría académica correspondiente"
            )
        
        with col_cat2:
            tipo_programa = st.selectbox(
                "**Tipo de Programa ***",
                TIPOS_PROGRAMA,
                help="Selecciona el tipo de programa que deseas cursar"
            )
        
        # Programas disponibles (simplificado para público)
        programas_disponibles = {
            "LICENCIATURA": ["Licenciatura en Enfermería"],
            "ESPECIALIDAD": ["Especialidad en Enfermería Cardiovascular"],
            "MAESTRIA": ["Maestría en Ciencias Cardiológicas"],
            "DIPLOMADO": ["Diplomado de Cardiología Básica"],
            "CURSO": ["Curso de RCP Avanzado"]
        }
        
        programa_interes = st.selectbox(
            "**Programa de Interés ***", 
            programas_disponibles.get(tipo_programa, ["Selecciona tipo primero"])
        )
        
        return {
            "categoria": categoria_academica,
            "tipo_programa": tipo_programa,
            "programa": programa_interes
        }
    
    def _mostrar_paso_datos_personales_publico(self, tipo_programa):
        col_datos1, col_datos2 = st.columns(2)
        
        with col_datos1:
            nombre_completo = st.text_input("**Nombre Completo ***", 
                                          placeholder="Ej: María González López",
                                          max_chars=100)
            
            email = st.text_input("**Correo Electrónico Personal ***", 
                                placeholder="ejemplo@email.com",
                                max_chars=100)
            
            email_gmail = st.text_input("**Correo Gmail ***", 
                                      placeholder="ejemplo@gmail.com", 
                                      help="Debe ser una cuenta @gmail.com - Se usará para comunicación oficial",
                                      max_chars=100)
        
        with col_datos2:
            telefono = st.text_input("**Teléfono ***", 
                                   placeholder="5512345678",
                                   max_chars=15)
            
            if tipo_programa == "ESPECIALIDAD":
                licenciatura_origen = st.text_input("**Licenciatura de Origen ***", 
                                                  placeholder="Ej: Licenciatura en Enfermería",
                                                  max_chars=100)
            else:
                licenciatura_origen = ""
            
            domicilio = st.text_area("**Domicilio Completo**", 
                                   placeholder="Calle, número, colonia, ciudad, estado, código postal",
                                   max_chars=200)
        
        matricula_unam = st.text_input("Matrícula UNAM (si aplica)", 
                                     placeholder="Dejar vacío si no aplica",
                                     max_chars=20)
        
        return {
            "nombre": nombre_completo,
            "email": email,
            "email_gmail": email_gmail,
            "telefono": telefono,
            "licenciatura_origen": licenciatura_origen,
            "domicilio": domicilio,
            "matricula_unam": matricula_unam
        }
    
    def _mostrar_paso_documentacion_publico(self, tipo_programa):
        st.markdown("**📋 Documentos obligatorios:**")
        
        # Documentos según tipo de programa (simplificado)
        documentos_base = [
            "Certificado preparatoria (promedio ≥ 8.0)",
            "Acta nacimiento (≤ 3 meses)",
            "CURP (≤ 1 mes)",
            "Cartilla Nacional de Salud"
        ]
        
        if tipo_programa == "ESPECIALIDAD":
            documentos_extra = [
                "Título profesional",
                "Cédula profesional",
                "Constancia de experiencia laboral (2+ años)"
            ]
            documentos_requeridos = documentos_base + documentos_extra
        else:
            documentos_requeridos = documentos_base
        
        with st.expander("Ver lista completa de documentos", expanded=False):
            for i, doc in enumerate(documentos_requeridos, 1):
                st.write(f"{i}. {doc}")
        
        st.markdown("**Documentos disponibles (marcar los que ya tienes):**")
        
        col_doc1, col_doc2 = st.columns(2)
        documentos_subidos = []
        
        with col_doc1:
            for doc in documentos_requeridos[:len(documentos_requeridos)//2]:
                if st.checkbox(doc):
                    documentos_subidos.append(doc)
        
        with col_doc2:
            for doc in documentos_requeridos[len(documentos_requeridos)//2:]:
                if st.checkbox(doc):
                    documentos_subidos.append(doc)
        
        return {
            "documentos_requeridos": documentos_requeridos,
            "documentos_subidos": documentos_subidos,
            "total_subidos": len(documentos_subidos)
        }
    
    def _mostrar_paso_aceptaciones_publico(self):
        st.markdown("**📄 Aceptaciones obligatorias:**")
        
        col_acep1, col_acep2 = st.columns(2)
        
        with col_acep1:
            aviso_privacidad = st.checkbox(
                "**He leído y acepto el Aviso de Privacidad ***",
                help="El aviso de privacidad describe cómo se manejarán tus datos personales."
            )
        
        with col_acep2:
            convocatoria_unam = st.checkbox(
                "**He leído y acepto los términos de la Convocatoria UNAM Febrero 2026 ***",
                help="Convocatoria oficial para el proceso de admisión Febrero 2026"
            )
        
        return {
            "aviso_privacidad": aviso_privacidad,
            "convocatoria_unam": convocatoria_unam
        }
    
    def _procesar_envio_publico(self, programa, datos, documentos, aceptaciones):
        errores = []
        
        # Validaciones
        campos_obligatorios = [
            (datos["nombre"], "Nombre completo"),
            (datos["email"], "Correo electrónico personal"),
            (datos["email_gmail"], "Correo Gmail"),
            (datos["telefono"], "Teléfono"),
            (programa["programa"], "Programa de interés"),
            (aceptaciones["aviso_privacidad"], "Aviso de privacidad"),
            (aceptaciones["convocatoria_unam"], "Convocatoria UNAM")
        ]
        
        for campo, nombre in campos_obligatorios:
            if not campo:
                errores.append(f"❌ {nombre} es obligatorio")
        
        if datos["email"] and not self.validador.validar_email(datos["email"]):
            errores.append("❌ Formato de correo electrónico personal inválido")
        
        if datos["email_gmail"] and not self.validador.validar_email_gmail(datos["email_gmail"]):
            errores.append("❌ El correo Gmail debe ser de dominio @gmail.com")
        
        if datos["telefono"] and not self.validador.validar_telefono(datos["telefono"]):
            errores.append("❌ Teléfono debe tener 10 dígitos")
        
        if programa["tipo_programa"] == "ESPECIALIDAD" and not datos.get("licenciatura_origen"):
            errores.append("❌ Licenciatura de origen es obligatoria para especialidades")
        
        # Validar documentos mínimos
        minimos = {
            "LICENCIATURA": 4,
            "ESPECIALIDAD": 6,
            "MAESTRIA": 4,
            "DIPLOMADO": 3,
            "CURSO": 2
        }
        
        minimo_requerido = minimos.get(programa["tipo_programa"], 3)
        if len(documentos["documentos_subidos"]) < minimo_requerido:
            errores.append(f"❌ Se requieren al menos {minimo_requerido} documentos para {programa['tipo_programa']}")
        
        if errores:
            for error in errores:
                st.error(error)
            return
        
        # Procesar inscripción
        with st.spinner("🔄 Procesando tu solicitud..."):
            try:
                # Generar matrícula única
                matricula = self._generar_matricula_unica()
                
                datos_completos = {
                    'matricula': matricula,
                    'nombre_completo': datos['nombre'],
                    'email': datos['email'],
                    'email_gmail': datos['email_gmail'],
                    'telefono': datos['telefono'],
                    'tipo_programa': programa['tipo_programa'],
                    'categoria_academica': programa['categoria'],
                    'programa_interes': programa['programa'],
                    'licenciatura_origen': datos.get('licenciatura_origen', ''),
                    'matricula_unam': datos.get('matricula_unam', ''),
                    'domicilio': datos.get('domicilio', ''),
                    'acepto_privacidad': aceptaciones['aviso_privacidad'],
                    'acepto_convocatoria': aceptaciones['convocatoria_unam'],
                    'documentos_subidos': documentos['total_subidos'],
                    'documentos_guardados': ', '.join(documentos['documentos_subidos']) if documentos['documentos_subidos'] else ''
                }
                
                # Usar el ID temporal del usuario público
                username = st.session_state.usuario_publico_id
                
                # Agregar a base de datos
                inscrito_id, folio_unico = self.base_datos.agregar_inscrito_completo_seguro(
                    datos_completos, 
                    username
                )
                
                if inscrito_id:
                    # Sincronizar con servidor remoto
                    if self.base_datos.sincronizar_hacia_remoto():
                        st.session_state.formulario_publico_enviado = True
                        st.session_state.datos_exitosos_publico = {
                            'folio': folio_unico,
                            'matricula': matricula,
                            'nombre': datos['nombre'],
                            'email_gmail': datos['email_gmail'],
                            'programa': programa['programa'],
                            'tipo_programa': programa['tipo_programa'],
                            'documentos': documentos['total_subidos']
                        }
                        
                        st.rerun()
                    else:
                        st.error("❌ Error al sincronizar con el servidor")
                else:
                    st.error("❌ Error al guardar en la base de datos")
                
            except ValueError as ve:
                st.error(f"❌ Error de validación: {str(ve)}")
            except Exception as e:
                st.error(f"❌ Error en el registro: {str(e)}")
                logger.error(f"Error registrando inscripción pública: {e}", exc_info=True)
    
    def _generar_matricula_unica(self):
        """Generar matrícula única"""
        fecha = datetime.now().strftime('%y%m%d')
        random_num = ''.join(random.choices(string.digits, k=4))
        return f"INS{fecha}{random_num}"
    
    def _mostrar_resultado_exitoso_publico(self):
        datos = st.session_state.datos_exitosos_publico
        
        ComponentesUISeguro.mostrar_header("🎉 ¡PRE-INSCRIPCIÓN COMPLETADA!", nivel=2)
        st.balloons()
        
        col_res1, col_res2 = st.columns(2)
        
        with col_res1:
            st.info(f"**📋 Folio Único (ANÓNIMO):**\n\n**{datos['folio']}**")
            st.info(f"**🎓 Matrícula:**\n\n{datos['matricula']}")
        
        with col_res2:
            st.info(f"**👤 Nombre:**\n\n{datos['nombre']}")
            st.info(f"**📧 Correo Gmail:**\n\n{datos['email_gmail']}")
            st.info(f"**🎯 Programa:**\n\n{datos['programa']}")
        
        # Información crítica
        st.markdown(f"""
        <div style="background-color: #fff3cd; padding: 20px; border-radius: 10px; margin: 20px 0; border-left: 5px solid #ffc107;">
        <h4 style="color: #856404; margin-top: 0;">⚠️ **INFORMACIÓN CRÍTICA - LEA CON ATENCIÓN**</h4>
        
        **TU FOLIO ÚNICO ES: `{datos['folio']}`**
        
        1. **🔒 Confidencialidad:** Los resultados se publicarán **ÚNICAMENTE CON ESTE FOLIO**
        2. **📋 Anonimato:** No se mostrarán nombres completos en la publicación de resultados
        3. **💾 Guarda este folio:** Es tu identificador único para consultar resultados
        4. **📧 Verificación:** Recibirás un correo de confirmación en {datos['email_gmail']}
        
        **Fecha límite para completar documentos:** {(datetime.now() + timedelta(days=14)).strftime('%d/%m/%Y')}
        </div>
        """, unsafe_allow_html=True)
        
        # Opciones
        col_op1, col_op2 = st.columns(2)
        with col_op1:
            if ComponentesUISeguro.crear_boton_accion_seguro("📝 Realizar otra inscripción"):
                st.session_state.formulario_publico_enviado = False
                st.rerun()
        
        with col_op2:
            if ComponentesUISeguro.crear_boton_accion_seguro("🚪 Salir del sistema"):
                for key in list(st.session_state.keys()):
                    if key != 'usuario_publico_id':  # Mantener ID para posible re-uso
                        del st.session_state[key]
                st.rerun()

# ============================================================================
# CAPA 10: CONTROLADOR PRINCIPAL SEGURO
# ============================================================================

class ControladorPrincipalSeguro:
    """Controlador principal de la aplicación con seguridad"""
    
    def __init__(self):
        self.db_path = None
        self.security_manager = None
        self.sistema_inscripciones = None
        
        # Estado inicial
        if 'authentication_status' not in st.session_state:
            st.session_state.authentication_status = None
        if 'role' not in st.session_state:
            st.session_state.role = None
        if 'username' not in st.session_state:
            st.session_state.username = None
        if 'name' not in st.session_state:
            st.session_state.name = None
        
        logger.info("🔐 Controlador principal seguro inicializado")
    
    def configurar_aplicacion(self):
        """Configuración inicial de la aplicación"""
        st.set_page_config(
            page_title=APP_CONFIG['page_title'],
            page_icon=APP_CONFIG['page_icon'],
            layout=APP_CONFIG['layout'],
            initial_sidebar_state=APP_CONFIG['sidebar_state']
        )
    
    def inicializar_sistema(self):
        """Inicializar sistema de base de datos y seguridad"""
        try:
            # Sincronizar base de datos
            with st.spinner("🔄 Sincronizando con servidor remoto..."):
                if db_segura.sincronizar_desde_remoto():
                    self.db_path = db_segura.db_local_temp
                    
                    # Inicializar gestor de seguridad
                    self.security_manager = SecurityManager(self.db_path)
                    db_segura.set_security_manager(self.security_manager)
                    
                    # Inicializar sistema de inscripciones
                    self.sistema_inscripciones = SistemaInscritosSeguro(self.security_manager)
                    
                    return True
                else:
                    st.error("❌ No se pudo sincronizar con el servidor remoto")
                    return False
                    
        except Exception as e:
            st.error(f"❌ Error inicializando sistema: {e}")
            logger.error(f"Error inicializando sistema: {e}", exc_info=True)
            return False
    
    def mostrar_pagina_login(self):
        """Mostrar página de login/registro"""
        # Ocultar sidebar
        st.markdown("""
        <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            .stDeployButton {visibility: hidden;}
        </style>
        """, unsafe_allow_html=True)
        
        # Banner superior
        st.markdown("""
        <div style="background: linear-gradient(135deg, #2E86AB 0%, #A23B72 100%); 
                    color: white; padding: 25px; border-radius: 10px; margin-bottom: 30px;">
            <h1 style="margin: 0; text-align: center;">🏥 Escuela de Enfermería</h1>
            <h3 style="margin: 10px 0; text-align: center;">Sistema de Pre-Inscripción Seguro</h3>
            <p style="text-align: center; margin: 0;">Versión {APP_CONFIG['version']} - Convocatoria Febrero 2026</p>
        </div>
        """.format(APP_CONFIG=APP_CONFIG), unsafe_allow_html=True)
        
        # Tabs para diferentes tipos de acceso
        tab1, tab2 = st.tabs(["🔐 Acceso Administrativo", "📝 Inscripción Pública"])
        
        with tab1:
            self._mostrar_login_administrativo()
        
        with tab2:
            self._mostrar_inscripcion_publica()
    
    def _mostrar_login_administrativo(self):
        """Mostrar formulario de login administrativo"""
        st.markdown("### 🔐 Acceso para Personal Autorizado")
        
        # Verificar bloqueos
        user_ip = UtilidadesSistemaSeguro.obtener_ip_usuario()
        bloqueado, mensaje_bloqueo = estado_sistema.verificar_usuario_bloqueado('', user_ip)
        
        if bloqueado:
            st.error(f"⛔ {mensaje_bloqueo}")
            return
        
        # Crear autenticador
        if self.security_manager:
            authenticator = self.security_manager.create_authenticator()
            
            if authenticator:
                # Widget de login
                name, auth_status, username = authenticator.login(
                    'Inicio de Sesión', 
                    location='main'
                )
                
                if auth_status:
                    # Obtener rol del usuario
                    user_data = self.security_manager.auth_config['credentials']['usernames'].get(username, {})
                    user_role = user_data.get('rol', 'inscrito')
                    
                    # Registrar sesión exitosa
                    estado_sistema.limpiar_intentos_fallidos()
                    estado_sistema.registrar_sesion(username, user_ip, True, 0)
                    
                    # Actualizar estado de sesión
                    st.session_state.update({
                        'name': name,
                        'authentication_status': auth_status,
                        'username': username,
                        'role': user_role,
                        'last_activity': time.time()
                    })
                    
                    st.rerun()
                    
                elif auth_status == False:
                    # Registrar intento fallido
                    estado_sistema.registrar_intento_fallido(username or 'unknown', user_ip)
                    estado_sistema.registrar_sesion(username or 'unknown', user_ip, False, 0)
                    
                    st.error("❌ Usuario o contraseña incorrectos")
                    
                    # Mostrar advertencia si hay muchos intentos
                    if estado_sistema.estado.get('estadisticas_sistema', {}).get('intentos_fallidos', 0) >= 2:
                        st.warning("⚠️ Demasiados intentos fallidos. Su IP podría ser bloqueada.")
        
        else:
            st.warning("⚠️ Sistema de autenticación no disponible")
    
    def _mostrar_inscripcion_publica(self):
        """Mostrar opción de inscripción pública"""
        st.markdown("### 📝 Inscripción para Aspirantes")
        
        st.info("""
        **Proceso de inscripción pública:**
        - No requiere cuenta previa
        - Solo podrás ver TU información
        - Los resultados se publican de forma anónima
        - Necesitas un correo Gmail para comunicación oficial
        """)
        
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            if st.button("📝 Comenzar Inscripción Pública", type="primary", use_container_width=True):
                # Configurar sesión como público
                user_ip = UtilidadesSistemaSeguro.obtener_ip_usuario()
                
                st.session_state.update({
                    'authentication_status': 'publico',
                    'role': 'publico',
                    'username': f'publico_{int(time.time())}',
                    'name': 'Usuario Público',
                    'last_activity': time.time()
                })
                
                # Registrar sesión pública
                estado_sistema.registrar_sesion('publico', user_ip, True, 0)
                
                st.rerun()
    
    def verificar_sesion_activa(self):
        """Verificar si la sesión sigue activa"""
        if 'last_activity' in st.session_state:
            tiempo_transcurrido = time.time() - st.session_state.last_activity
            if tiempo_transcurrido > APP_CONFIG['session_timeout_minutes'] * 60:
                # Sesión expirada
                self.cerrar_sesion("Sesión expirada por inactividad")
                return False
            
            # Actualizar tiempo de actividad
            st.session_state.last_activity = time.time()
        
        return True
    
    def cerrar_sesion(self, motivo="Sesión cerrada por el usuario"):
        """Cerrar sesión actual"""
        logger.info(f"🔒 Cerrando sesión: {motivo}")
        
        # Limpiar estado de sesión
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        
        # Limpiar estado de autenticación
        st.session_state.authentication_status = None
        st.session_state.role = None
        st.session_state.username = None
        st.session_state.name = None
    
    def mostrar_pagina_publica(self):
        """Mostrar página para usuarios públicos"""
        # Ocultar sidebar completamente
        st.markdown("""
        <style>
            section[data-testid="stSidebar"] {display: none;}
            .stDeployButton {visibility: hidden;}
        </style>
        """, unsafe_allow_html=True)
        
        # Mostrar sistema de inscripciones públicas
        if self.sistema_inscripciones:
            self.sistema_inscripciones.mostrar_formulario_publico()
        else:
            st.error("❌ Sistema de inscripciones no disponible")
    
    def mostrar_pagina_autenticada(self):
        """Mostrar página para usuarios autenticados"""
        # Verificar sesión activa
        if not self.verificar_sesion_activa():
            return
        
        # Obtener información del usuario
        username = st.session_state.get('username')
        user_role = st.session_state.get('role')
        user_name = st.session_state.get('name')
        
        # Sidebar con información del usuario
        with st.sidebar:
            # Encabezado del usuario
            st.title(f"👤 {user_name}")
            st.caption(f"Rol: {user_role}")
            
            # Estado del sistema
            st.markdown("---")
            st.subheader("🔍 Estado del Sistema")
            
            col1, col2 = st.columns(2)
            with col1:
                if estado_sistema.esta_inicializada():
                    st.success("✅ BD")
                else:
                    st.error("❌ BD")
            
            with col2:
                if estado_sistema.estado.get('ssh_conectado'):
                    st.success("✅ SSH")
                else:
                    st.error("❌ SSH")
            
            # Navegación según rol
            st.markdown("---")
            st.subheader("📱 Navegación")
            
            opciones_menu = self._obtener_opciones_menu_por_rol(user_role)
            seleccion_menu = st.selectbox("Selecciona una opción:", opciones_menu)
            
            # Botón de logout
            st.markdown("---")
            if st.button("🚪 Cerrar Sesión", type="secondary", use_container_width=True):
                self.cerrar_sesion()
                st.rerun()
            
            # Información adicional para admin
            if user_role == 'admin':
                st.markdown("---")
                st.caption(f"💾 Backups: {estado_sistema.estado.get('backups_realizados', 0)}")
                st.caption(f"🔄 Última sinc: {estado_sistema.estado.get('ultima_sincronizacion', 'Nunca')}")
        
        # Mostrar contenido según selección
        self._mostrar_contenido_por_seleccion(seleccion_menu, user_role, username)
    
    def _obtener_opciones_menu_por_rol(self, rol):
        """Obtener opciones de menú según rol"""
        if rol == 'admin':
            return [
                "🏠 Inicio y Resumen",
                "📝 Nueva Pre-Inscripción",
                "📋 Consultar Inscritos",
                "👥 Gestión de Usuarios",
                "⚙️ Configuración",
                "📊 Reportes y Backups"
            ]
        elif rol == 'secretaria':
            return [
                "🏠 Inicio",
                "📝 Nueva Pre-Inscripción",
                "📋 Consultar Inscritos",
                "📊 Reportes Básicos"
            ]
        elif rol == 'inscrito':
            return [
                "👤 Mi Perfil",
                "📄 Mis Documentos",
                "📋 Mi Progreso"
            ]
        else:
            return ["🏠 Inicio"]
    
    def _mostrar_contenido_por_seleccion(self, seleccion, user_role, username):
        """Mostrar contenido según la selección del menú"""
        
        if seleccion == "🏠 Inicio" or seleccion == "🏠 Inicio y Resumen":
            self._mostrar_pagina_inicio(user_role, username)
        
        elif seleccion == "📝 Nueva Pre-Inscripción":
            if user_role in ['admin', 'secretaria']:
                self._mostrar_pagina_inscripcion_admin()
            else:
                st.error("⛔ No tienes permisos para esta acción")
        
        elif seleccion == "📋 Consultar Inscritos":
            if user_role in ['admin', 'secretaria']:
                self._mostrar_pagina_consulta_admin(username, user_role)
            elif user_role == 'inscrito':
                self._mostrar_pagina_mi_perfil(username)
            else:
                st.error("⛔ No tienes permisos para esta acción")
        
        elif seleccion == "👤 Mi Perfil" and user_role == 'inscrito':
            self._mostrar_pagina_mi_perfil(username)
        
        elif seleccion == "👥 Gestión de Usuarios" and user_role == 'admin':
            self._mostrar_pagina_gestion_usuarios()
        
        elif seleccion == "⚙️ Configuración" and user_role == 'admin':
            self._mostrar_pagina_configuracion()
        
        elif seleccion == "📊 Reportes y Backups" and user_role == 'admin':
            self._mostrar_pagina_reportes()
        
        elif seleccion == "📊 Reportes Básicos" and user_role == 'secretaria':
            self._mostrar_pagina_reportes_basicos(username)
        
        elif seleccion == "📄 Mis Documentos" and user_role == 'inscrito':
            self._mostrar_pagina_mis_documentos(username)
        
        elif seleccion == "📋 Mi Progreso" and user_role == 'inscrito':
            self._mostrar_pagina_mi_progreso(username)
        
        else:
            st.error("⛔ Opción no disponible para tu rol")
    
    def _mostrar_pagina_inicio(self, user_role, username):
        """Mostrar página de inicio según rol"""
        ComponentesUISeguro.mostrar_header(
            f"🏥 Bienvenido al Sistema de Pre-Inscripción",
            f"Rol: {user_role} | Usuario: {username}", nivel=1
        )
        
        if user_role == 'admin':
            st.markdown("""
            ### 👋 ¡Bienvenido Administrador!
            
            **Funciones disponibles:**
            - 📝 **Nueva Pre-Inscripción**: Registrar nuevos aspirantes
            - 📋 **Consultar Inscritos**: Ver y gestionar todos los registros
            - 👥 **Gestión de Usuarios**: Administrar usuarios del sistema
            - ⚙️ **Configuración**: Configurar sistema y conexiones
            - 📊 **Reportes y Backups**: Generar reportes y backups
            """)
            
            # Estadísticas rápidas
            col1, col2, col3 = st.columns(3)
            with col1:
                total = db_segura.obtener_total_inscritos(username, user_role)
                st.metric("Total Inscritos", total)
            with col2:
                st.metric("Sesiones Activas", len(estado_sistema.estado.get('sesiones_activas', {})))
            with col3:
                st.metric("Backups", estado_sistema.estado.get('backups_realizados', 0))
        
        elif user_role == 'secretaria':
            st.markdown("""
            ### 👋 ¡Bienvenida Secretaria!
            
            **Funciones disponibles:**
            - 📝 **Nueva Pre-Inscripción**: Registrar nuevos aspirantes
            - 📋 **Consultar Inscritos**: Ver y gestionar registros
            - 📊 **Reportes Básicos**: Ver estadísticas básicas
            """)
        
        elif user_role == 'inscrito':
            st.markdown("""
            ### 👋 ¡Bienvenido Aspirante!
            
            **Funciones disponibles:**
            - 👤 **Mi Perfil**: Ver tu información personal
            - 📄 **Mis Documentos**: Ver y completar tu documentación
            - 📋 **Mi Progreso**: Seguir tu proceso de admisión
            """)
            
            # Mostrar información básica del aspirante
            try:
                inscritos = db_segura.obtener_inscritos(username, user_role)
                if inscritos:
                    inscrito = inscritos[0]
                    col_info1, col_info2 = st.columns(2)
                    with col_info1:
                        st.info(f"**Folio:** {inscrito['folio_unico']}")
                        st.info(f"**Matrícula:** {inscrito['matricula']}")
                        st.info(f"**Programa:** {inscrito['programa_interes']}")
                    with col_info2:
                        st.info(f"**Estatus:** {inscrito['estatus']}")
                        st.info(f"**Documentos:** {inscrito['documentos_subidos']}/10")
                        st.info(f"**Fecha límite:** {inscrito['fecha_limite_registro']}")
                else:
                    st.info("ℹ️ No tienes una inscripción registrada.")
            except Exception as e:
                st.error(f"❌ Error cargando información: {e}")
    
    def _mostrar_pagina_inscripcion_admin(self):
        """Mostrar página de inscripción para administradores"""
        st.warning("🚧 Página de inscripción administrativa en desarrollo")
        st.info("Para inscripciones públicas, cierra sesión y selecciona 'Inscripción Pública'")
    
    def _mostrar_pagina_consulta_admin(self, username, user_role):
        """Mostrar página de consulta para administradores"""
        ComponentesUISeguro.mostrar_header("📋 Consulta de Inscritos", nivel=2)
        
        try:
            # Sincronizar datos
            with st.spinner("🔄 Actualizando datos..."):
                db_segura.sincronizar_desde_remoto()
            
            # Obtener inscritos
            inscritos = db_segura.obtener_inscritos(username, user_role)
            total_inscritos = len(inscritos)
            
            st.metric("Total de Inscritos", total_inscritos)
            
            if total_inscritos > 0:
                # Preparar datos para tabla
                datos_tabla = []
                for inscrito in inscritos:
                    datos_tabla.append({
                        'ID': inscrito['id'],
                        'Folio': inscrito['folio_unico'],
                        'Matrícula': inscrito['matricula'],
                        'Nombre': inscrito['nombre_completo'],
                        'Programa': inscrito['programa_interes'],
                        'Tipo': inscrito['tipo_programa'],
                        'Estatus': inscrito['estatus'],
                        'Documentos': inscrito['documentos_subidos'],
                        'Fecha Registro': inscrito['fecha_registro'][:10] if isinstance(inscrito['fecha_registro'], str) else inscrito['fecha_registro'].strftime('%Y-%m-%d'),
                        'Completado': '✅' if inscrito['completado'] else '⚠️'
                    })
                
                df = pd.DataFrame(datos_tabla)
                
                # Búsqueda
                st.subheader("🔍 Búsqueda de Inscritos")
                col_bus1, col_bus2 = st.columns(2)
                with col_bus1:
                    search_term = st.text_input("Buscar por folio, matrícula o nombre:")
                with col_bus2:
                    filtro_estatus = st.selectbox("Filtrar por estatus:", 
                                                ["Todos", "Pre-inscrito", "En revisión", "Aceptado", "Rechazado"])
                
                # Aplicar filtros
                if search_term:
                    df = df[df.apply(lambda row: row.astype(str).str.contains(search_term, case=False).any(), axis=1)]
                
                if filtro_estatus != "Todos":
                    df = df[df['Estatus'] == filtro_estatus]
                
                # Mostrar tabla
                if not df.empty:
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    
                    # Acciones
                    st.subheader("📊 Acciones")
                    col_acc1, col_acc2, col_acc3 = st.columns(3)
                    
                    with col_acc1:
                        if st.button("📄 Exportar a Excel", use_container_width=True):
                            st.success("✅ Datos exportados (simulación)")
                    
                    with col_acc2:
                        if st.button("📊 Generar Reporte", use_container_width=True):
                            st.success("✅ Reporte generado (simulación)")
                    
                    with col_acc3:
                        if st.button("🔄 Sincronizar", use_container_width=True):
                            st.rerun()
                else:
                    st.info("ℹ️ No hay inscritos que coincidan con los filtros")
            else:
                st.info("ℹ️ No hay inscritos registrados")
            
        except Exception as e:
            st.error(f"❌ Error cargando inscritos: {e}")
    
    def _mostrar_pagina_mi_perfil(self, username):
        """Mostrar página de perfil para inscritos"""
        ComponentesUISeguro.mostrar_header("👤 Mi Perfil", nivel=2)
        
        try:
            inscritos = db_segura.obtener_inscritos(username, 'inscrito')
            
            if inscritos:
                inscrito = inscritos[0]
                
                # Información en columnas
                col1, col2 = st.columns(2)
                
                with col1:
                    st.info(f"**📋 Folio Único:**\n\n**{inscrito['folio_unico']}**")
                    st.info(f"**🎓 Matrícula:**\n\n{inscrito['matricula']}")
                    st.info(f"**👤 Nombre:**\n\n{inscrito['nombre_completo']}")
                    st.info(f"**📧 Correo Personal:**\n\n{inscrito['email']}")
                    st.info(f"**📧 Correo Gmail:**\n\n{inscrito['email_gmail']}")
                
                with col2:
                    st.info(f"**📞 Teléfono:**\n\n{inscrito['telefono']}")
                    st.info(f"**🎯 Programa:**\n\n{inscrito['programa_interes']}")
                    st.info(f"**📄 Tipo:**\n\n{inscrito['tipo_programa']}")
                    st.info(f"**📊 Estatus:**\n\n{inscrito['estatus']}")
                    st.info(f"**📅 Fecha Límite:**\n\n{inscrito['fecha_limite_registro']}")
                
                # Documentos
                st.subheader("📄 Mis Documentos")
                if inscrito['documentos_guardados']:
                    docs = inscrito['documentos_guardados'].split(', ')
                    for doc in docs:
                        st.checkbox(doc, value=True, disabled=True)
                    
                    st.info(f"**Progreso:** {inscrito['documentos_subidos']} documentos subidos")
                    
                    # Mostrar documentos faltantes
                    faltantes = db_segura.obtener_documentos_faltantes(inscrito['id'], username)
                    if faltantes:
                        st.warning("**📋 Documentos faltantes:**")
                        for doc in faltantes:
                            st.write(f"- {doc}")
                else:
                    st.warning("⚠️ No has subido documentos aún")
                
                # Información importante
                st.markdown(f"""
                <div style="background-color: #e8f4f8; padding: 15px; border-radius: 5px; margin-top: 20px;">
                <h4>📌 Información Importante</h4>
                <p><strong>Folio único:</strong> {inscrito['folio_unico']}</p>
                <p>Los resultados se publicarán <strong>sólo con este folio</strong> para garantizar tu privacidad.</p>
                </div>
                """, unsafe_allow_html=True)
                
            else:
                st.info("ℹ️ No tienes una inscripción registrada.")
                
        except Exception as e:
            st.error(f"❌ Error cargando perfil: {e}")
    
    def _mostrar_pagina_gestion_usuarios(self):
        """Mostrar página de gestión de usuarios (solo admin)"""
        ComponentesUISeguro.mostrar_header("👥 Gestión de Usuarios", nivel=2)
        
        st.warning("🚧 Página en desarrollo")
        st.info("Funcionalidad completa de gestión de usuarios próximamente")
    
    def _mostrar_pagina_configuracion(self):
        """Mostrar página de configuración (solo admin)"""
        ComponentesUISeguro.mostrar_header("⚙️ Configuración del Sistema", nivel=2)
        
        st.warning("🚧 Página en desarrollo")
        st.info("Configuración completa del sistema próximamente")
    
    def _mostrar_pagina_reportes(self):
        """Mostrar página de reportes (solo admin)"""
        ComponentesUISeguro.mostrar_header("📊 Reportes y Backups", nivel=2)
        
        st.warning("🚧 Página en desarrollo")
        st.info("Reportes y sistema de backups próximamente")
    
    def _mostrar_pagina_reportes_basicos(self, username):
        """Mostrar página de reportes básicos (secretaria)"""
        ComponentesUISeguro.mostrar_header("📊 Reportes Básicos", nivel=2)
        
        try:
            inscritos = db_segura.obtener_inscritos(username, 'secretaria')
            total = len(inscritos)
            
            if total > 0:
                # Estadísticas básicas
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    preinscritos = sum(1 for i in inscritos if i['estatus'] == 'Pre-inscrito')
                    st.metric("Pre-inscritos", preinscritos)
                
                with col2:
                    completados = sum(1 for i in inscritos if i['completado'])
                    st.metric("Completados", completados)
                
                with col3:
                    con_documentos = sum(1 for i in inscritos if i['documentos_subidos'] >= 5)
                    st.metric("Con documentos", con_documentos)
                
                with col4:
                    especialidad = sum(1 for i in inscritos if i['tipo_programa'] == 'ESPECIALIDAD')
                    st.metric("Especialidad", especialidad)
                
                # Gráfico simple de programas
                st.subheader("📈 Distribución por Programa")
                programas = {}
                for inscrito in inscritos:
                    programa = inscrito['programa_interes']
                    programas[programa] = programas.get(programa, 0) + 1
                
                df_programas = pd.DataFrame({
                    'Programa': list(programas.keys()),
                    'Cantidad': list(programas.values())
                })
                
                if not df_programas.empty:
                    st.bar_chart(df_programas.set_index('Programa'))
                else:
                    st.info("ℹ️ No hay datos para mostrar")
                
            else:
                st.info("ℹ️ No hay inscritos para generar reportes")
                
        except Exception as e:
            st.error(f"❌ Error generando reportes: {e}")
    
    def _mostrar_pagina_mis_documentos(self, username):
        """Mostrar página de documentos para inscritos"""
        ComponentesUISeguro.mostrar_header("📄 Mis Documentos", nivel=2)
        
        st.info("ℹ️ Funcionalidad de gestión de documentos próximamente")
        st.info("Actualmente puedes ver tus documentos en 'Mi Perfil'")
    
    def _mostrar_pagina_mi_progreso(self, username):
        """Mostrar página de progreso para inscritos"""
        ComponentesUISeguro.mostrar_header("📋 Mi Progreso", nivel=2)
        
        st.info("ℹ️ Funcionalidad de seguimiento de progreso próximamente")
    
    def ejecutar(self):
        """Ejecutar aplicación principal"""
        self.configurar_aplicacion()
        
        # Inicializar sistema
        if not hasattr(self, 'security_manager') or self.security_manager is None:
            if not self.inicializar_sistema():
                st.error("❌ No se pudo inicializar el sistema. Por favor, recarga la página.")
                return
        
        # Determinar qué mostrar según estado de autenticación
        auth_status = st.session_state.get('authentication_status')
        
        if not auth_status:
            # Mostrar página de login
            self.mostrar_pagina_login()
        
        elif auth_status == 'publico':
            # Mostrar página pública
            self.mostrar_pagina_publica()
        
        elif auth_status == True:
            # Mostrar página autenticada
            self.mostrar_pagina_autenticada()
        
        else:
            # Estado inválido, mostrar login
            st.error("❌ Estado de sesión inválido")
            self.cerrar_sesion("Estado de sesión inválido")
            self.mostrar_pagina_login()

# ============================================================================
# CAPA 11: PUNTO DE ENTRADA PRINCIPAL SEGURO
# ============================================================================

def main_segura():
    """Función principal segura de la aplicación"""
    
    try:
        # Inicializar estado del sistema
        estado_sistema.limpiar_intentos_fallidos()
        
        # Mostrar banner informativo
        st.markdown(f"""
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 10px; margin-bottom: 20px; 
                    border-left: 5px solid #2E86AB;">
            <h3 style="margin: 0; color: #2E86AB;">🏥 Sistema de Pre-Inscripción Seguro</h3>
            <p style="margin: 5px 0; color: #666;">Escuela de Enfermería - Versión {APP_CONFIG['version']}</p>
            <p style="margin: 0; font-size: 0.9em; color: #888;">
                🔒 Sistema protegido con autenticación por roles | 📅 Convocatoria Febrero 2026
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Inicializar y ejecutar controlador
        controlador = ControladorPrincipalSeguro()
        controlador.ejecutar()
        
        # Footer de seguridad
        st.markdown("---")
        st.caption(f"🔒 Sistema seguro v{APP_CONFIG['version']} | 📊 {estado_sistema.estado.get('sesiones_iniciadas', 0)} sesiones | ⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
    except Exception as e:
        st.error(f"❌ Error crítico en la aplicación: {e}")
        logger.critical(f"Error crítico en sistema seguro: {e}", exc_info=True)
        
        with st.expander("🚨 Información de diagnóstico para soporte"):
            st.write("**Traceback completo:**")
            st.code(traceback.format_exc())
            
            st.write("**Información del sistema:**")
            st.write(f"- Python: {sys.version}")
            st.write(f"- Streamlit: {st.__version__}")
            st.write(f"- Sistema operativo: {os.name}")
            st.write(f"- Directorio actual: {os.getcwd()}")

# ============================================================================
# EJECUCIÓN PRINCIPAL
# ============================================================================

if __name__ == "__main__":
    main_segura()
