#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SISTEMA DE GESTIÓN DE ASPIRANTES - ESCUELA DE ENFERMERÍA
Versión: 3.0 - CON SSH MEJORADO (igual que escuela20.py) + OPCIONES ACADÉMICAS
Autor: Departamento de Tecnología
Descripción: Sistema completo para gestión de inscritos con base de datos remota SSH
Mejoras: Timeouts, reintentos, manejo robusto de errores, logging detallado + Website público
"""

# =============================================================================
# IMPORTS Y CONFIGURACIÓN
# =============================================================================

import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import json
import tempfile
import os
import sys
import traceback
from datetime import datetime, date
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
from PIL import Image

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
        file_handler = logging.FileHandler('aspirantes_detallado.log', encoding='utf-8')
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
        log_file = 'aspirantes_operations.json'
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
# CONFIGURACIÓN DE PÁGINA STREAMLIT
# =============================================================================

st.set_page_config(
    page_title="Sistema Escuela Enfermería - Modo Inscripción",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# DATOS ESTÁTICOS DE LA INSTITUCIÓN (SOLO INFORMACIÓN PÚBLICA)
# =============================================================================

def obtener_programas_academicos():
    """Obtener lista de programas académicos disponibles - SOLO INFORMACIÓN PÚBLICA"""
    return [
        {
            "nombre": "Especialidad en Enfermería Cardiovascular",
            "duracion": "2 años",
            "modalidad": "Presencial",
            "descripcion": "Formación especializada en el cuidado de pacientes con patologías cardiovasculares.",
            "requisitos": ["Licenciatura en Enfermería", "Cédula profesional", "2 años de experiencia"]
        },
        {
            "nombre": "Licenciatura en Enfermería",
            "duracion": "4 años",
            "modalidad": "Presencial",
            "descripcion": "Formación integral en enfermería con enfoque en cardiología.",
            "requisitos": ["Bachillerato terminado", "Promedio mínimo 8.0"]
        },
        {
            "nombre": "Diplomado de Cardiología Básica",
            "duracion": "6 meses",
            "modalidad": "Híbrida",
            "descripcion": "Actualización en fundamentos de cardiología para profesionales de la salud.",
            "requisitos": ["Título profesional en área de la salud"]
        },
        {
            "nombre": "Maestría en Ciencias Cardiológicas",
            "duracion": "2 años",
            "modalidad": "Presencial",
            "descripcion": "Formación de investigadores en el área de ciencias cardiológicas.",
            "requisitos": ["Licenciatura en áreas afines", "Promedio mínimo 8.5"]
        }
    ]

def obtener_testimonios():
    """Obtener testimonios de estudiantes y egresados - SOLO INFORMACIÓN PÚBLICA"""
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
# SECCIONES DEL WEBSITE PÚBLICO (De aspirantes10.py)
# =============================================================================

def aplicar_estilos_publicos():
    """Aplicar estilos CSS para el website público"""
    st.markdown("""
    <style>
    .main-header {
        font-size: 3.5rem;
        color: #2E86AB;
        text-align: center;
        margin-bottom: 2rem;
        font-weight: bold;
    }
    .sub-header {
        font-size: 2rem;
        color: #A23B72;
        text-align: center;
        margin-bottom: 1.5rem;
        font-weight: 600;
    }
    .programa-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 5px solid #2E86AB;
        margin-bottom: 1rem;
    }
    .testimonio {
        background-color: #e8f4f8;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 4px solid #A23B72;
    }
    .btn-primary {
        background-color: #2E86AB;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        cursor: pointer;
    }
    </style>
    """, unsafe_allow_html=True)

def mostrar_header():
    """Mostrar header del website"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="main-header">🏥 Escuela de Enfermería</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-header">Formando Líderes en Salud Cardiovascular</div>', unsafe_allow_html=True)
    
    st.markdown("---")

def mostrar_hero():
    """Sección hero principal"""
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("## 🎓 Excelencia Académica en Cardiología")
        st.markdown("""
        ### **Forma parte de la institución líder en educación cardiovascular**
        
        - 👨‍⚕️ **Claustro docente** de alto nivel
        - 🏥 **Vinculación hospitalaria** con las mejores instituciones
        - 🔬 **Investigación** de vanguardia
        - 💼 **Bolsa de trabajo** exclusiva para egresados
        - 🌐 **Red de egresados** a nivel nacional
        
        *40 años formando profesionales de excelencia en el cuidado cardiovascular*
        """)
        
        if st.button("📝 ¡Inscríbete Ahora!", key="hero_inscripcion", use_container_width=True):
            st.session_state.mostrar_formulario = True
            st.rerun()
    
    with col2:
        st.info("**🏛️ Instalaciones de Vanguardia**")
        st.write("""
        - Laboratorios especializados
        - Simuladores de alta fidelidad
        - Biblioteca especializada
        - Aulas tecnológicas
        """)

def mostrar_programas_academicos():
    """Mostrar oferta académica"""
    st.markdown('<div class="sub-header">📚 Nuestra Oferta Académica</div>', unsafe_allow_html=True)
    
    programas = obtener_programas_academicos()
    
    for i, programa in enumerate(programas):
        with st.container():
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f'<div class="programa-card">', unsafe_allow_html=True)
                st.markdown(f"### **{programa['nombre']}**")
                st.markdown(f"**Duración:** {programa['duracion']} | **Modalidad:** {programa['modalidad']}")
                st.markdown(f"{programa['descripcion']}")
                
                with st.expander("📋 Ver requisitos"):
                    for requisito in programa['requisitos']:
                        st.write(f"• {requisito}")
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col2:
                st.write("")  # Espacio
                if st.button(f"🎯 Solicitar Informes", key=f"info_{i}", use_container_width=True):
                    st.session_state.programa_seleccionado = programa['nombre']
                    st.session_state.mostrar_formulario = True
                    st.rerun()

def mostrar_testimonios():
    """Mostrar testimonios de estudiantes y egresados"""
    st.markdown("---")
    st.markdown('<div class="sub-header">🌟 Testimonios de Nuestra Comunidad</div>', unsafe_allow_html=True)
    
    testimonios = obtener_testimonios()
    cols = st.columns(3)
    
    for i, testimonio in enumerate(testimonios):
        with cols[i]:
            st.markdown(f'<div class="testimonio">', unsafe_allow_html=True)
            st.markdown(f"### {testimonio['foto']}")
            st.markdown(f"**{testimonio['nombre']}**")
            st.markdown(f"*{testimonio['programa']}*")
            st.markdown(f"\"{testimonio['testimonio']}\"")
            st.markdown('</div>', unsafe_allow_html=True)

def mostrar_contacto():
    """Mostrar información de contacto"""
    st.markdown("---")
    st.markdown('<div class="sub-header">📞 Información de Contacto</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 🏛️ Dirección")
        st.markdown("""
        Av. Insurgentes Sur 1234  
        Col. Nápoles  
        Ciudad de México, CDMX  
        C.P. 03810
        """)
    
    with col2:
        st.markdown("### 📱 Contacto")
        st.markdown("""
        **Teléfono:** (55) 1234-5678  
        **WhatsApp:** (55) 8765-4321  
        **Email:** admisiones@escuelaenfermeria.edu.mx
        """)
    
    with col3:
        st.markdown("### 🕒 Horarios")
        st.markdown("""
        **Atención a aspirantes:**  
        Lunes a Viernes: 9:00 - 18:00  
        Sábados: 9:00 - 13:00  
        **Proceso de admisión:**  
        Abierto todo el año
        """)

def mostrar_footer():
    """Mostrar footer del website"""
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("### 🏥 Instituto")
        st.markdown("""
        - Nuestra historia
        - Misión y visión
        - Directiva
        - Instalaciones
        """)
    
    with col2:
        st.markdown("### 📚 Programas")
        st.markdown("""
        - Licenciaturas
        - Especialidades
        - Maestrías
        - Diplomados
        """)
    
    with col3:
        st.markdown("### 📞 Contacto")
        st.markdown("""
        - Tel: 55-1234-5678
        - Email: admisiones@cardio.edu.mx
        - Dirección: Av. Instituto 123
        - Horario: 9:00 - 18:00 hrs
        """)
    
    with col4:
        st.markdown("### 🔗 Síguenos")
        st.markdown("""
        - Facebook
        - Twitter
        - Instagram
        - LinkedIn
        """)
    
    st.markdown("---")
    st.markdown("<center>© 2024 Instituto Nacional de Cardiología. Todos los derechos reservados.</center>", unsafe_allow_html=True)

# =============================================================================
# ARCHIVO DE ESTADO PERSISTENTE - MEJORADO
# =============================================================================

class EstadoPersistente:
    """Maneja el estado persistente para el sistema de aspirantes"""
    
    def __init__(self, archivo_estado="estado_aspirantes.json"):
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
                # Estado por defecto
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
                    'total_inscritos': 0
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
            'total_inscritos': 0
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
    
    def set_total_inscritos(self, total):
        """Establecer total de inscritos"""
        self.estado['total_inscritos'] = total
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
    def validar_nombre_completo(nombre):
        """Validar nombre completo"""
        if not nombre:
            return False
        # Debe tener al menos dos palabras
        palabras = nombre.strip().split()
        return len(palabras) >= 2
    
    @staticmethod
    def validar_fecha_nacimiento(fecha_str):
        """Validar fecha de nacimiento"""
        try:
            if not fecha_str:
                return True  # No es obligatorio
            
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            hoy = date.today()
            
            # Verificar que sea una fecha válida (no en el futuro y mayor de 15 años)
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
        # Formato: INS + fecha + 4 dígitos
        return matricula.startswith('INS') and len(matricula) >= 10
    
    @staticmethod
    def validar_folio(folio):
        """Validar formato de folio"""
        if not folio:
            return False
        # Formato: FOL + fecha + 4 dígitos
        return folio.startswith('FOL') and len(folio) >= 10

# =============================================================================
# FUNCIÓN PARA LEER SECRETS.TOML - VERSIÓN MEJORADA
# =============================================================================

def cargar_configuracion_secrets():
    """Cargar configuración desde secrets.toml - VERSIÓN MEJORADA"""
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
# GESTOR DE CONEXIÓN REMOTA VIA SSH - MEJORADO CON TIMEOUTS Y REINTENTOS
# =============================================================================

class GestorConexionRemota:
    """Gestor de conexión SSH al servidor remoto - MEJORADO"""
    
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
        self.db_path_remoto = self.config.get('remote_db_aspirantes')
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
                'remote_db_aspirantes': paths_config.get('remote_db_aspirantes', ''),
                'remote_uploads_path': paths_config.get('remote_uploads_path', ''),
                'db_local_path': paths_config.get('db_aspirantes', ''),
                'uploads_path_local': paths_config.get('uploads_path', '')
            })
            
            # 3. Configuración SMTP (opcional)
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
        pattern = os.path.join(temp_dir, "aspirantes_*.db")
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
                temp_db_path = os.path.join(temp_dir, f"aspirantes_temp_{timestamp}.db")
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
            
            tablas_esperadas = {'usuarios', 'inscritos'}
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
            temp_db_path = os.path.join(temp_dir, f"aspirantes_nueva_{timestamp}.db")
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
            
            # Tabla de usuarios
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
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                    programa_interes TEXT NOT NULL,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    estatus TEXT DEFAULT 'Pre-inscrito',
                    folio TEXT UNIQUE,
                    fecha_nacimiento DATE,
                    como_se_entero TEXT,
                    documentos_subidos INTEGER DEFAULT 0,
                    documentos_guardados TEXT,
                    observaciones TEXT
                )
            ''')
            
            # Insertar usuario administrador por defecto
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO usuarios (usuario, password, rol, nombre_completo, email, matricula, activo) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ('admin', 'admin123', 'admin', 'Administrador', 'admin@enfermeria.edu', 'ADMIN-001', 1)
                )
            except Exception as e:
                logger.warning(f"⚠️ Error insertando admin: {e}")
            
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
# SISTEMA DE BACKUP AUTOMÁTICO
# =============================================================================

class SistemaBackupAutomatico:
    """Sistema de backup automático"""
    
    def __init__(self, gestor_ssh):
        self.gestor_ssh = gestor_ssh
        self.backup_dir = "backups_aspirantes"
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
                                'usuario': 'sistema'  # En aspirantes no hay login
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
    
    def enviar_notificacion(self, tipo_operacion, estado, detalles):
        """Enviar notificación por email"""
        try:
            if not self.notificaciones_habilitadas:
                logger.warning("⚠️ Notificaciones por email no configuradas")
                return False
            
            destinatarios = [self.config_smtp.get('notification_email')]
            
            if not destinatarios or not all(destinatarios):
                logger.warning("⚠️ No hay destinatarios para notificación")
                return False
            
            # Preparar mensaje
            subject = f"[Aspirantes] {tipo_operacion} - {estado}"
            
            # Crear contenido HTML
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2>📊 Notificación del Sistema de Aspirantes</h2>
                <div style="background-color: {'#d4edda' if estado == 'EXITOSA' else '#f8d7da'}; 
                          padding: 15px; border-radius: 5px; margin: 10px 0;">
                    <h3>Estado: <strong>{estado}</strong></h3>
                    <p><strong>Operación:</strong> {tipo_operacion}</p>
                    <p><strong>Fecha:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                
                <h3>📋 Detalles:</h3>
                <div style="background-color: #f8f9fa; padding: 10px; border-left: 4px solid #007bff;">
                    <pre style="white-space: pre-wrap;">{detalles}</pre>
                </div>
                
                <hr>
                <p style="color: #6c757d; font-size: 0.9em;">
                    Sistema de Aspirantes - Escuela de Enfermería<br>
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

# =============================================================================
# SISTEMA DE BASE DE DATOS SQLITE - MEJORADO
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
        
        # Instancias adicionales
        self.backup_system = SistemaBackupAutomatico(self.gestor)
        self.notificaciones = SistemaNotificaciones(
            gestor_remoto.config.get('smtp', {})
        )
        self.validador = ValidadorDatos()
    
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
    
    def ejecutar_query(self, query, params=()):
        """Ejecutar query en la base de datos"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                
                if query.strip().upper().startswith('SELECT'):
                    resultados = cursor.fetchall()
                    # Convertir a lista de diccionarios
                    resultados = [dict(row) for row in resultados]
                    return resultados
                else:
                    ultimo_id = cursor.lastrowid
                    return ultimo_id
                    
        except Exception as e:
            logger.error(f"❌ Error ejecutando query: {e} - Query: {query}")
            return None
    
    def agregar_inscrito(self, datos_inscrito):
        """Agregar nuevo inscrito a la base de datos"""
        try:
            # Validar datos
            if not self.validador.validar_email(datos_inscrito.get('email')):
                raise ValueError("Email inválido")
            
            if not self.validador.validar_nombre_completo(datos_inscrito.get('nombre_completo')):
                raise ValueError("Nombre completo inválido")
            
            # Verificar si ya existe el email
            query_check = "SELECT COUNT(*) as count FROM inscritos WHERE email = ?"
            resultado = self.ejecutar_query(query_check, (datos_inscrito['email'],))
            
            if resultado and resultado[0]['count'] > 0:
                raise ValueError("Ya existe un inscrito con este email")
            
            # Insertar inscrito
            query_inscrito = '''
                INSERT INTO inscritos (
                    matricula, nombre_completo, email, telefono, programa_interes,
                    fecha_registro, estatus, folio, fecha_nacimiento, como_se_entero,
                    documentos_subidos, documentos_guardados
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            
            params_inscrito = (
                datos_inscrito.get('matricula', ''),
                datos_inscrito.get('nombre_completo', ''),
                datos_inscrito.get('email', ''),
                datos_inscrito.get('telefono', ''),
                datos_inscrito.get('programa_interes', ''),
                datos_inscrito.get('fecha_registro', datetime.now()),
                datos_inscrito.get('estatus', 'Pre-inscrito'),
                datos_inscrito.get('folio', ''),
                datos_inscrito.get('fecha_nacimiento'),
                datos_inscrito.get('como_se_entero', ''),
                datos_inscrito.get('documentos_subidos', 0),
                datos_inscrito.get('documentos_guardados', '')
            )
            
            inscrito_id = self.ejecutar_query(query_inscrito, params_inscrito)
            
            # También crear usuario para el inscrito
            if inscrito_id:
                query_usuario = '''
                    INSERT INTO usuarios (
                        usuario, password, rol, nombre_completo, email, matricula, activo
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                '''
                
                params_usuario = (
                    datos_inscrito.get('matricula', ''),
                    '123',  # Password por defecto
                    'inscrito',
                    datos_inscrito.get('nombre_completo', ''),
                    datos_inscrito.get('email', ''),
                    datos_inscrito.get('matricula', ''),
                    1
                )
                
                self.ejecutar_query(query_usuario, params_usuario)
                logger.info(f"✅ Inscrito agregado: {datos_inscrito.get('matricula')}")
                
                # Enviar notificación
                self.notificaciones.enviar_notificacion(
                    tipo_operacion="AGREGAR_INSCRITO",
                    estado="EXITOSA",
                    detalles=f"Inscrito agregado exitosamente:\nMatrícula: {datos_inscrito.get('matricula')}\nNombre: {datos_inscrito.get('nombre_completo')}"
                )
                
                return inscrito_id
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error agregando inscrito: {e}")
            raise
    
    def obtener_inscritos(self):
        """Obtener todos los inscritos"""
        try:
            query = "SELECT * FROM inscritos ORDER BY fecha_registro DESC"
            resultados = self.ejecutar_query(query)
            return resultados if resultados else []
        except Exception as e:
            logger.error(f"❌ Error obteniendo inscritos: {e}")
            return []
    
    def obtener_inscrito_por_matricula(self, matricula):
        """Obtener inscrito por matrícula"""
        try:
            query = "SELECT * FROM inscritos WHERE matricula = ?"
            resultados = self.ejecutar_query(query, (matricula,))
            return resultados[0] if resultados else None
        except Exception as e:
            logger.error(f"❌ Error obteniendo inscrito: {e}")
            return None
    
    def obtener_total_inscritos(self):
        """Obtener total de inscritos"""
        try:
            query = "SELECT COUNT(*) as total FROM inscritos"
            resultados = self.ejecutar_query(query)
            total = resultados[0]['total'] if resultados else 0
            
            # Actualizar estado persistente
            estado_sistema.set_total_inscritos(total)
            
            return total
        except Exception as e:
            logger.error(f"❌ Error obteniendo total: {e}")
            return 0
    
    def guardar_documento(self, archivo_bytes, nombre_archivo):
        """Guardar documento en el servidor remoto"""
        try:
            if not self.gestor.conectar_ssh():
                return False
            
            # Crear directorio de uploads si no existe
            if self.gestor.uploads_path_remoto:
                self.gestor._crear_directorio_remoto_recursivo(self.gestor.uploads_path_remoto)
            
            # Guardar archivo temporalmente localmente
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, nombre_archivo)
            
            with open(temp_path, 'wb') as f:
                f.write(archivo_bytes)
            
            # Ruta completa en servidor
            ruta_remota = os.path.join(self.gestor.uploads_path_remoto, nombre_archivo) if self.gestor.uploads_path_remoto else nombre_archivo
            
            # Subir al servidor con timeout
            start_time = time.time()
            self.gestor.sftp.put(temp_path, ruta_remota)
            upload_time = time.time() - start_time
            
            logger.info(f"✅ Documento subido: {nombre_archivo} ({upload_time:.1f}s)")
            
            # Limpiar archivo temporal
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            self.gestor.desconectar_ssh()
            return True
            
        except socket.timeout:
            logger.error("❌ Timeout subiendo documento")
            return False
        except Exception as e:
            logger.error(f"❌ Error guardando documento: {e}")
            if self.gestor.ssh:
                self.gestor.desconectar_ssh()
            return False

# Instancia de base de datos
db = SistemaBaseDatos()

# =============================================================================
# SISTEMA DE CORREOS (Mejorado con HTML de aspirantes10.py)
# =============================================================================

class SistemaCorreos:
    """Sistema de envío de correos"""
    
    def __init__(self):
        try:
            # Obtener configuración desde el gestor remoto
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
    
    def enviar_correo_confirmacion(self, destinatario, nombre_estudiante, matricula, folio, programa):
        """Enviar correo de confirmación de pre-inscripción"""
        if not self.correos_habilitados:
            return False, "Sistema de correos no configurado"
        
        try:
            # Crear mensaje
            mensaje = MIMEMultipart()
            mensaje['From'] = self.email_user
            mensaje['To'] = destinatario
            mensaje['Subject'] = f"Confirmación de Pre-Inscripción - {matricula}"
            
            # Cuerpo del correo (HTML mejorado de aspirantes10.py)
            cuerpo = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                    <div style="text-align: center; background-color: #2E86AB; color: white; padding: 20px; border-radius: 10px 10px 0 0;">
                        <h1>🏥 Escuela de Enfermería</h1>
                        <h2>Confirmación de Pre-Inscripción</h2>
                    </div>
                    
                    <div style="padding: 20px;">
                        <p>Estimado/a <strong>{nombre_estudiante}</strong>,</p>
                        
                        <p>Hemos recibido exitosamente tu solicitud de pre-inscripción. A continuación encontrarás los detalles de tu registro:</p>
                        
                        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <h3 style="color: #2E86AB; margin-top: 0;">📋 Datos de tu Registro</h3>
                            <p><strong>Matrícula:</strong> {matricula}</p>
                            <p><strong>Folio:</strong> {folio}</p>
                            <p><strong>Programa:</strong> {programa}</p>
                            <p><strong>Fecha de registro:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
                            <p><strong>Estatus:</strong> Pre-inscrito</p>
                        </div>
                        
                        <h3 style="color: #2E86AB;">📬 Próximos Pasos</h3>
                        <ol>
                            <li><strong>Revisión de documentos</strong> (2-3 días hábiles)</li>
                            <li><strong>Correo de confirmación</strong> con fecha de examen</li>
                            <li><strong>Examen de admisión</strong> (presencial/online)</li>
                            <li><strong>Entrevista personal</strong> (si aplica)</li>
                            <li><strong>Resultados finales</strong> (5-7 días después del examen)</li>
                        </ol>
                        
                        <div style="background-color: #e8f4f8; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <h4 style="color: #A23B72; margin-top: 0;">ℹ️ Información Importante</h4>
                            <p>Guarda esta información, ya que tu matrícula y folio serán necesarios para cualquier consulta sobre tu proceso de admisión.</p>
                        </div>
                        
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
                    </div>
                </div>
            </body>
            </html>
            """
            
            mensaje.attach(MIMEText(cuerpo, 'html'))
            
            # Enviar correo
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(mensaje)
            
            logger.info(f"✅ Correo enviado a {destinatario}")
            return True, "Correo enviado exitosamente"
            
        except socket.timeout:
            logger.error(f"❌ Timeout enviando correo a {destinatario}")
            return False, "Timeout al enviar correo"
        except Exception as e:
            logger.error(f"❌ Error enviando correo: {e}")
            return False, f"Error: {str(e)}"

# =============================================================================
# SISTEMA PRINCIPAL DE INSCRITOS - MEJORADO
# =============================================================================

class SistemaInscritos:
    """Sistema principal de gestión de inscritos mejorado"""
    
    def __init__(self):
        # Inicializar componentes con manejo de errores
        try:
            self.base_datos = db
            self.sistema_correos = SistemaCorreos()
            self.validador = ValidadorDatos()
            self.backup_system = SistemaBackupAutomatico(gestor_remoto)
            logger.info("🚀 Sistema de inscritos inicializado con SSH mejorado")
        except Exception as e:
            logger.error(f"❌ Error inicializando sistema: {e}")
            # Configuración mínima para permitir que la aplicación funcione
            self.base_datos = db
            self.sistema_correos = SistemaCorreos()
            self.validador = ValidadorDatos()
    
    def generar_matricula(self):
        """Generar matrícula única"""
        try:
            while True:
                fecha = datetime.now().strftime('%y%m%d')
                random_num = ''.join(random.choices(string.digits, k=4))
                matricula = f"INS{fecha}{random_num}"
                
                # Verificar que no exista si tenemos base de datos
                if self.base_datos:
                    if not self.base_datos.obtener_inscrito_por_matricula(matricula):
                        return matricula
                else:
                    # Si no hay base de datos, generar una única
                    return matricula
        except:
            # Generación de fallback
            return f"INS{datetime.now().strftime('%y%m%d%H%M%S')}"
    
    def generar_folio(self):
        """Generar folio único"""
        fecha = datetime.now().strftime('%y%m%d')
        random_num = ''.join(random.choices(string.digits, k=4))
        return f"FOL{fecha}{random_num}"
    
    def guardar_documentos(self, archivos, matricula, nombre_completo):
        """Guardar documentos en servidor remoto"""
        nombres_guardados = []
        
        if not self.base_datos:
            logger.warning("⚠️ No hay base de datos para guardar documentos")
            return nombres_guardados
        
        tipos_documentos = {
            'acta_nacimiento': 'ACTA_NACIMIENTO',
            'curp': 'CURP',
            'certificado': 'CERTIFICADO',
            'foto': 'FOTOGRAFIA'
        }
        
        for key, archivo in archivos.items():
            if archivo is not None:
                tipo = tipos_documentos.get(key, 'DOCUMENTO')
                timestamp = datetime.now().strftime('%y%m%d%H%M%S')
                
                # Limpiar nombre
                nombre_limpio = ''.join(c for c in nombre_completo if c.isalnum() or c in (' ', '-', '_')).rstrip()
                nombre_limpio = nombre_limpio.replace(' ', '_')[:20]
                
                # Obtener extensión
                if hasattr(archivo, 'name'):
                    extension = archivo.name.split('.')[-1] if '.' in archivo.name else 'pdf'
                else:
                    extension = 'pdf'
                
                # Nombre del archivo
                nombre_archivo = f"{matricula}_{nombre_limpio}_{timestamp}_{tipo}.{extension}"
                
                # Obtener bytes del archivo
                if hasattr(archivo, 'getvalue'):
                    archivo_bytes = archivo.getvalue()
                elif hasattr(archivo, 'read'):
                    archivo_bytes = archivo.read()
                else:
                    archivo_bytes = archivo
                
                # Guardar en servidor
                if self.base_datos.guardar_documento(archivo_bytes, nombre_archivo):
                    nombres_guardados.append(nombre_archivo)
        
        return nombres_guardados
    
    def registrar_inscripcion(self, datos_formulario, archivos):
        """Registrar nueva inscripción con backup automático"""
        try:
            # Validar datos
            errores = self.validar_datos(datos_formulario, archivos)
            if errores:
                raise ValueError("\n".join(errores))
            
            # Verificar que tenemos base de datos
            if not self.base_datos:
                raise Exception("Sistema de base de datos no disponible")
            
            # Crear backup antes de la operación
            backup_info = f"Agregar inscrito: {datos_formulario['nombre_completo']}"
            
            backup_path = self.backup_system.crear_backup(
                "AGREGAR_INSCRITO", 
                backup_info
            )
            
            if backup_path:
                logger.info(f"✅ Backup creado antes de operación: {os.path.basename(backup_path)}")
            
            # Generar identificadores
            matricula = self.generar_matricula()
            folio = self.generar_folio()
            
            logger.info(f"📝 Registrando inscripción para: {datos_formulario['nombre_completo']}")
            
            # Guardar documentos
            nombres_documentos = self.guardar_documentos(archivos, matricula, datos_formulario['nombre_completo'])
            
            # Preparar datos para base de datos
            datos_inscrito = {
                'matricula': matricula,
                'nombre_completo': datos_formulario['nombre_completo'],
                'email': datos_formulario['email'],
                'telefono': datos_formulario['telefono'],
                'programa_interes': datos_formulario['programa_interes'],
                'fecha_registro': datetime.now(),
                'estatus': 'Pre-inscrito',
                'folio': folio,
                'fecha_nacimiento': datos_formulario.get('fecha_nacimiento'),
                'como_se_entero': datos_formulario['como_se_entero'],
                'documentos_subidos': len(nombres_documentos),
                'documentos_guardados': ', '.join(nombres_documentos) if nombres_documentos else ''
            }
            
            # Guardar en base de datos
            inscrito_id = self.base_datos.agregar_inscrito(datos_inscrito)
            
            if inscrito_id:
                # Sincronizar con servidor remoto
                if self.base_datos.sincronizar_hacia_remoto():
                    # Enviar correo de confirmación
                    correo_enviado = False
                    mensaje_correo = "Sistema de correos no configurado"
                    
                    if self.sistema_correos.correos_habilitados:
                        correo_enviado, mensaje_correo = self.sistema_correos.enviar_correo_confirmacion(
                            datos_formulario['email'],
                            datos_formulario['nombre_completo'],
                            matricula,
                            folio,
                            datos_formulario['programa_interes']
                        )
                    
                    return {
                        'success': True,
                        'matricula': matricula,
                        'folio': folio,
                        'nombre': datos_formulario['nombre_completo'],
                        'email': datos_formulario['email'],
                        'programa': datos_formulario['programa_interes'],
                        'documentos': len(nombres_documentos),
                        'correo_enviado': correo_enviado,
                        'mensaje_correo': mensaje_correo,
                        'inscrito_id': inscrito_id
                    }
                else:
                    raise Exception("Error al sincronizar con servidor remoto")
            else:
                raise Exception("Error al guardar en base de datos")
            
        except ValueError as e:
            logger.error(f"❌ Error de validación: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"❌ Error registrando inscripción: {e}")
            return {'success': False, 'error': f"Error interno: {str(e)}"}
    
    def validar_datos(self, datos, archivos):
        """Validar datos del formulario"""
        errores = []
        
        # Campos obligatorios
        campos_obligatorios = [
            ('nombre_completo', 'Nombre completo'),
            ('email', 'Correo electrónico'),
            ('telefono', 'Teléfono'),
            ('programa_interes', 'Programa de interés'),
            ('como_se_entero', 'Cómo se enteró')
        ]
        
        for campo, nombre in campos_obligatorios:
            if not datos.get(campo):
                errores.append(f"❌ {nombre} es obligatorio")
        
        # Validar email
        if datos.get('email') and not self.validador.validar_email(datos['email']):
            errores.append("❌ Formato de email inválido")
        
        # Validar teléfono
        if datos.get('telefono') and not self.validador.validar_telefono(datos['telefono']):
            errores.append("❌ Teléfono debe tener al menos 10 dígitos")
        
        # Validar documentos obligatorios
        documentos_obligatorios = ['acta_nacimiento', 'curp', 'certificado']
        for doc in documentos_obligatorios:
            if not archivos.get(doc):
                errores.append(f"❌ Documento {doc.replace('_', ' ').title()} es obligatorio")
        
        return errores

# Instancia global del sistema
sistema = SistemaInscritos()

# =============================================================================
# FUNCIONES PRINCIPALES DEL WEBSITE PÚBLICO
# =============================================================================

def mostrar_formulario_inscripcion():
    """Mostrar formulario de pre-inscripción para inscritos"""
    st.markdown("---")
    st.markdown('<div class="sub-header">📝 Formulario de Pre-Inscripción</div>', unsafe_allow_html=True)
    
    if 'formulario_enviado' not in st.session_state:
        st.session_state.formulario_enviado = False
    
    if not st.session_state.formulario_enviado:
        with st.form("formulario_inscripcion", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                nombre_completo = st.text_input("👤 Nombre Completo *", placeholder="Ej: María González López")
                email = st.text_input("📧 Correo Electrónico *", placeholder="ejemplo@email.com")
                programa_interes = st.selectbox(
                    "🎯 Programa de Interés *",
                    [p['nombre'] for p in obtener_programas_academicos()]
                )
            
            with col2:
                telefono = st.text_input("📞 Teléfono *", placeholder="5512345678")
                
                # FECHA DE NACIMIENTO CON RANGO DESDE 1980
                fecha_actual = date.today()
                fecha_minima = date(1980, 1, 1)
                fecha_maxima = fecha_actual
                
                fecha_nacimiento = st.date_input(
                    "🎂 Fecha de Nacimiento",
                    min_value=fecha_minima,
                    max_value=fecha_maxima,
                    value=None,
                    format="YYYY-MM-DD"
                )
                
                # OPCIONES PARA "¿CÓMO SE ENTERÓ?"
                opciones_como_se_entero = ["Redes Sociales", "Google/Buscador", "Recomendación", "Evento", "Otro"]
                como_se_entero = st.selectbox(
                    "🔍 ¿Cómo se enteró de nosotros? *",
                    opciones_como_se_entero
                )
            
            # Documentos requeridos
            st.markdown("### 📎 Documentos Requeridos")
            st.info("Por favor, suba los siguientes documentos en formato PDF:")
            
            col_doc1, col_doc2 = st.columns(2)
            
            with col_doc1:
                acta_nacimiento = st.file_uploader("📄 Acta de Nacimiento", type=['pdf'], key="acta")
                curp = st.file_uploader("🆔 CURP", type=['pdf'], key="curp")
            
            with col_doc2:
                certificado = st.file_uploader("🎓 Último Grado de Estudios", type=['pdf'], key="certificado")
                foto = st.file_uploader("📷 Fotografía", type=['pdf', 'jpg', 'png'], key="foto")
            
            # Términos y condiciones
            acepta_terminos = st.checkbox("✅ Acepto los términos y condiciones del proceso de admisión *")
            
            enviado = st.form_submit_button("🚀 Enviar Solicitud de Admisión", use_container_width=True)
            
            if enviado:
                # Validar campos obligatorios
                if not all([nombre_completo, email, telefono, programa_interes, acepta_terminos]):
                    st.error("❌ Por favor completa todos los campos obligatorios (*)")
                    return
                
                # Validar que se seleccionó una opción en "¿Cómo se enteró?"
                if not como_se_entero:
                    st.error("❌ Por favor selecciona cómo te enteraste de nosotros")
                    return
                
                # Validar documentos requeridos
                documentos_requeridos = [acta_nacimiento, curp, certificado]
                nombres_docs = ["Acta de Nacimiento", "CURP", "Certificado de Estudios"]
                docs_faltantes = [nombres_docs[i] for i, doc in enumerate(documentos_requeridos) if doc is None]
                
                if docs_faltantes:
                    st.error(f"❌ Faltan los siguientes documentos: {', '.join(docs_faltantes)}")
                    return
                
                # Registrar inscripción usando el sistema mejorado
                datos_formulario = {
                    'nombre_completo': nombre_completo,
                    'email': email,
                    'telefono': telefono,
                    'programa_interes': programa_interes,
                    'fecha_nacimiento': fecha_nacimiento.strftime('%Y-%m-%d') if fecha_nacimiento else None,
                    'como_se_entero': como_se_entero
                }
                
                archivos = {
                    'acta_nacimiento': acta_nacimiento,
                    'curp': curp,
                    'certificado': certificado,
                    'foto': foto
                }
                
                with st.spinner("Procesando tu solicitud..."):
                    resultado = sistema.registrar_inscripcion(datos_formulario, archivos)
                    
                    if resultado['success']:
                        st.session_state.formulario_enviado = True
                        st.session_state.datos_exitosos = {
                            'folio': resultado['folio'],
                            'matricula': resultado['matricula'],
                            'email': resultado['email'],
                            'telefono': telefono,
                            'programa': programa_interes,
                            'documentos': resultado['documentos'],
                            'nombre': resultado['nombre'],
                            'correo_enviado': resultado['correo_enviado'],
                            'mensaje_correo': resultado['mensaje_correo']
                        }
                        st.rerun()
                    else:
                        st.error(f"❌ Error: {resultado['error']}")
    
    else:
        # Mostrar resultados exitosos
        datos = st.session_state.datos_exitosos
        
        st.success("🎉 ¡Solicitud enviada exitosamente!")
        
        col_res1, col_res2 = st.columns(2)
        with col_res1:
            st.info(f"**📋 Folio de solicitud:** {datos['folio']}")
            st.info(f"**🎓 Matrícula de inscrito:** {datos['matricula']}")
            st.info(f"**📧 Email de contacto:** {datos['email']}")
        
        with col_res2:
            st.info(f"**📞 Teléfono registrado:** {datos['telefono']}")
            st.info(f"**🎯 Programa de interés:** {datos['programa']}")
            st.info(f"**📎 Documentos subidos:** {datos['documentos']}/4")
        
        st.markdown("---")
        st.markdown("### 📬 Próximos Pasos")
        st.markdown("""
        1. **Revisión de documentos** (2-3 días hábiles)
        2. **Correo de confirmación** con fecha de examen  
        3. **Examen de admisión** (presencial/online)
        4. **Entrevista personal** (si aplica)
        5. **Resultados finales** (5-7 días después del examen)
        
        *Te contactaremos al correo proporcionado para informarte los siguientes pasos.*
        """)
        
        if datos['correo_enviado']:
            st.info("📧 **Se ha enviado un correo de confirmación a tu dirección de email con todos los detalles de tu registro.**")
        else:
            st.warning(f"⚠️ **No se pudo enviar el correo de confirmación:** {datos.get('mensaje_correo', 'Razón desconocida')}")
        
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            if st.button("📝 Realizar otra pre-inscripción", use_container_width=True):
                st.session_state.formulario_enviado = False
                st.session_state.mostrar_formulario = False
                st.rerun()

def mostrar_pagina_principal_website():
    """Página principal del website público"""
    
    # Aplicar estilos
    aplicar_estilos_publicos()
    
    # Inicializar variables de sesión
    if 'mostrar_formulario' not in st.session_state:
        st.session_state.mostrar_formulario = False
    
    # Mostrar header
    mostrar_header()
    
    # Navegación
    if not st.session_state.mostrar_formulario:
        # Página principal
        mostrar_hero()
        mostrar_programas_academicos()
        mostrar_testimonios()
        mostrar_contacto()
    else:
        # Formulario de inscripción
        mostrar_formulario_inscripcion()
        mostrar_contacto()
    
    # Mostrar footer
    mostrar_footer()

# =============================================================================
# INTERFAZ DE USUARIO PARA SISTEMA DE ADMINISTRACIÓN
# =============================================================================

def mostrar_encabezado_administracion():
    """Mostrar encabezado de la aplicación de administración"""
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("""
        <div style="background-color: #2c3e50; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; text-align: center;">
            <h1>🏥 Sistema de Gestión de Aspirantes - SSH REMOTO</h1>
            <h3>Escuela de Enfermería - Versión Mejorada</h3>
        </div>
        """, unsafe_allow_html=True)

def mostrar_panel_estadisticas():
    """Mostrar panel de estadísticas"""
    try:
        # Sincronizar antes de obtener datos
        with st.spinner("🔄 Sincronizando con servidor remoto..."):
            if db.sincronizar_desde_remoto():
                st.success("✅ Base de datos sincronizada")
            else:
                st.warning("⚠️ No se pudo sincronizar completamente")
        
        total_inscritos = db.obtener_total_inscritos()
        
        st.markdown("### 📊 Estadísticas del Sistema")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; text-align: center;">
                <h3>Total Inscritos</h3>
                <h2>{total_inscritos}</h2>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            # Obtener inscritos del mes actual
            mes_actual = datetime.now().month
            try:
                with db.get_connection() as conn:
                    query = "SELECT COUNT(*) as total FROM inscritos WHERE strftime('%m', fecha_registro) = ?"
                    df = pd.read_sql_query(query, conn, params=(f"{mes_actual:02d}",))
                    inscritos_mes = df.iloc[0, 0] if not df.empty else 0
            except:
                inscritos_mes = 0
            
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 20px; border-radius: 10px; text-align: center;">
                <h3>Este Mes</h3>
                <h2>{inscritos_mes}</h2>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; padding: 20px; border-radius: 10px; text-align: center;">
                <h3>Pre-inscritos</h3>
                <h2>{total_inscritos}</h2>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            backups = sistema.backup_system.listar_backups()
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); color: white; padding: 20px; border-radius: 10px; text-align: center;">
                <h3>Backups</h3>
                <h2>{len(backups)}</h2>
            </div>
            """, unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"❌ Error cargando estadísticas: {e}")
        logger.error(f"Error en panel de estadísticas: {e}", exc_info=True)

def mostrar_configuracion_administracion():
    """Mostrar configuración del sistema mejorada"""
    st.markdown("### ⚙️ Configuración del Sistema")

    with st.expander("🔗 Estado de Conexión", expanded=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            if estado_sistema.esta_inicializada():
                st.success("✅ Base de Datos")
                fecha = estado_sistema.obtener_fecha_inicializacion()
                if fecha:
                    st.caption(f"Inicializada: {fecha.strftime('%Y-%m-%d')}")
            else:
                st.error("❌ Base de Datos")

        with col2:
            if estado_sistema.estado.get('ssh_conectado'):
                st.success("✅ SSH Conectado")
                if gestor_remoto.config.get('host'):
                    st.caption(f"{gestor_remoto.config['host']}")
            else:
                st.error("❌ SSH Desconectado")

        with col3:
            if sistema.sistema_correos.correos_habilitados:
                st.success("✅ Correos Activo")
            else:
                st.warning("⚠️ Correos Inactivo")

        # Botón para probar conexión
        if st.button("🔗 Probar Conexión SSH", use_container_width=True):
            with st.spinner("Probando conexión..."):
                if gestor_remoto.verificar_conexion_ssh():
                    st.success("✅ Conexión SSH exitosa")
                    st.rerun()
                else:
                    st.error("❌ Conexión SSH fallida")

    with st.expander("💾 Sistema de Backups"):
        backups = sistema.backup_system.listar_backups()

        if backups:
            st.success(f"✅ {len(backups)} backups disponibles")

            # Listar backups recientes
            st.markdown("**Backups recientes:**")
            for backup in backups[:5]:  # Mostrar solo los 5 más recientes
                st.write(f"- {backup['nombre']} ({backup['tamaño']:,} bytes) - {backup['fecha'].strftime('%Y-%m-%d %H:%M')}")

            # Botón para crear nuevo backup
            if st.button("💾 Crear Backup Manual", use_container_width=True):
                with st.spinner("Creando backup..."):
                    backup_path = sistema.backup_system.crear_backup(
                        "MANUAL_CONFIG",
                        "Backup manual desde configuración"
                    )
                    if backup_path:
                        st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                        st.rerun()
                    else:
                        st.error("❌ Error creando backup")
        else:
            st.info("ℹ️ No hay backups disponibles")

    with st.expander("📊 Estadísticas del Sistema"):
        # Estadísticas del estado persistente
        stats = estado_sistema.estado.get('estadisticas_sistema', {})

        col_stat1, col_stat2, col_stat3 = st.columns(3)

        with col_stat1:
            st.metric("Sesiones Exitosas", stats.get('sesiones', 0))

        with col_stat2:
            st.metric("Backups Realizados", estado_sistema.estado.get('backups_realizados', 0))

        with col_stat3:
            total_time = stats.get('total_tiempo', 0)
            horas = total_time / 3600
            st.metric("Tiempo Total", f"{horas:.1f}h")

        # Total de inscritos
        total_inscritos = estado_sistema.estado.get('total_inscritos', 0)
        st.metric("Total Inscritos", total_inscritos)

        # Última sincronización
        ultima_sync = estado_sistema.estado.get('ultima_sincronizacion')
        if ultima_sync:
            try:
                fecha_sync = datetime.fromisoformat(ultima_sync)
                st.info(f"🔄 Última sincronización: {fecha_sync.strftime('%Y-%m-%d %H:%M:%S')}")
            except:
                pass

def mostrar_lista_inscritos_administracion():
    """Mostrar lista de inscritos con paginación"""
    try:
        # Sincronizar primero
        with st.spinner("🔄 Sincronizando datos..."):
            if not db.sincronizar_desde_remoto():
                st.warning("⚠️ No se pudo sincronizar completamente con el servidor")
        
        inscritos = db.obtener_inscritos()
        
        st.markdown("### 📋 Lista de Aspirantes Inscritos")
        
        if not inscritos:
            st.info("📭 No hay aspirantes inscritos aún")
            return
        
        # Crear DataFrame para mostrar
        datos_tabla = []
        for inscrito in inscritos:
            datos_tabla.append({
                'Matrícula': inscrito['matricula'],
                'Nombre': inscrito['nombre_completo'],
                'Email': inscrito['email'],
                'Programa': inscrito['programa_interes'],
                'Fecha Registro': inscrito['fecha_registro'][:10] if isinstance(inscrito['fecha_registro'], str) else inscrito['fecha_registro'].strftime('%Y-%m-%d'),
                'Estatus': inscrito['estatus'],
                'Documentos': inscrito['documentos_subidos']
            })
        
        df = pd.DataFrame(datos_tabla)
        
        # Búsqueda
        st.subheader("🔍 Búsqueda Avanzada")
        search_term = st.text_input("Buscar por matrícula, nombre o email:", key="search_inscritos_admin")
        
        if search_term:
            df = df[df.apply(lambda row: row.astype(str).str.contains(search_term, case=False).any(), axis=1)]
        
        # Mostrar tabla
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Estadísticas
            st.markdown(f"**Mostrando {len(df)} de {len(datos_tabla)} registros**")
            
            # Opciones de exportación
            col_export1, col_export2, col_export3 = st.columns(3)
            
            with col_export1:
                if st.button("📊 Exportar a Excel", use_container_width=True):
                    exportar_a_excel(df)
            
            with col_export2:
                if st.button("📄 Exportar a CSV", use_container_width=True):
                    exportar_a_csv(df)
            
            with col_export3:
                if st.button("💾 Crear Backup", use_container_width=True):
                    with st.spinner("Creando backup..."):
                        backup_path = sistema.backup_system.crear_backup(
                            "EXPORT_INSCRITOS",
                            f"Exportación de {len(df)} inscritos"
                        )
                        if backup_path:
                            st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                        else:
                            st.error("❌ Error creando backup")
        else:
            st.info("ℹ️ No hay registros que coincidan con la búsqueda")
            
    except Exception as e:
        st.error(f"❌ Error cargando lista de inscritos: {e}")
        logger.error(f"Error en lista de inscritos: {e}", exc_info=True)

def exportar_a_excel(df):
    """Exportar DataFrame a Excel"""
    try:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Inscritos')
        
        excel_data = output.getvalue()
        b64 = base64.b64encode(excel_data).decode()
        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="inscritos_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx">⬇️ Descargar Excel</a>'
        st.markdown(href, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error exportando a Excel: {e}")

def exportar_a_csv(df):
    """Exportar DataFrame a CSV"""
    try:
        csv = df.to_csv(index=False).encode('utf-8')
        b64 = base64.b64encode(csv).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="inscritos_{datetime.now().strftime("%Y%m%d_%H%M")}.csv">⬇️ Descargar CSV</a>'
        st.markdown(href, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error exportando a CSV: {e}")

def mostrar_pagina_principal_administracion():
    """Página principal del sistema de administración"""
    mostrar_encabezado_administracion()

    # Verificar estado del sistema
    if not estado_sistema.esta_inicializada():
        st.warning("""
        ⚠️ **Sistema No Inicializado**

        Para usar el sistema, primero necesitas:
        1. **Configurar secrets.toml** con credenciales SSH
        2. **Inicializar la base de datos** en el servidor remoto

        **Pasos para inicializar:**
        """)

        col_init1, col_init2 = st.columns(2)

        with col_init1:
            if st.button("🔄 Inicializar Base de Datos", use_container_width=True):
                with st.spinner("Inicializando base de datos en servidor remoto..."):
                    if db.sincronizar_desde_remoto():
                        st.success("✅ Base de datos inicializada exitosamente")
                        st.rerun()
                    else:
                        st.error("❌ Error inicializando base de datos")

        with col_init2:
            if st.button("🔗 Probar Conexión SSH", use_container_width=True):
                with st.spinner("Probando conexión..."):
                    if gestor_remoto.verificar_conexion_ssh():
                        st.success("✅ Conexión SSH establecida")
                        st.rerun()
                    else:
                        st.error("❌ No se pudo establecer conexión SSH")

        # Mostrar información de diagnóstico
        with st.expander("🔍 Diagnóstico del Sistema"):
            st.write("**Configuración SSH cargada:**")
            if gestor_remoto.config.get('host'):
                config_show = gestor_remoto.config.copy()
                if 'password' in config_show:
                    config_show['password'] = '********'
                st.json(config_show)
            else:
                st.error("❌ No hay configuración SSH")

            st.write("**Archivos secrets.toml encontrados:**")
            posibles_rutas = [
                ".streamlit/secrets.toml",
                "secrets.toml",
                "./.streamlit/secrets.toml"
            ]
            for ruta in posibles_rutas:
                existe = os.path.exists(ruta)
                estado = "✅ Existe" if existe else "❌ No existe"
                st.write(f"{estado}: `{ruta}`")

        return

    # Crear pestañas
    tab1, tab2, tab3, tab4 = st.tabs([
        "🏠 Inicio",
        "📝 Nueva Inscripción",
        "📋 Lista de Inscritos",
        "⚙️ Configuración"
    ])

    with tab1:
        # Panel de bienvenida
        st.markdown("""
        ## 🎓 Bienvenido al Sistema de Gestión de Aspirantes - SSH REMOTO

        Este sistema permite gestionar el proceso de pre-inscripción para la Escuela de Enfermería con conexión remota segura via SSH.

        ### 🚀 Funcionalidades mejoradas:

        1. **🔗 Conexión SSH Robusta** - Timeouts, reintentos, manejo de errores
        2. **📝 Formulario Completo** - Validaciones mejoradas, documentos obligatorios
        3. **📋 Lista de Inscritos** - Búsqueda, filtrado, exportación
        4. **📊 Panel de Estadísticas** - Métricas en tiempo real
        5. **💾 Sistema de Backups** - Automático y manual
        6. **📧 Notificaciones** - Correos automáticos con confirmación
        7. **🔒 Seguridad** - Logs detallados, verificación de integridad

        ### 📄 Requisitos de documentación:
        - ✅ Acta de nacimiento (obligatorio)
        - ✅ CURP (obligatorio)
        - ✅ Certificado de estudios (obligatorio)
        - 📷 Fotografía (opcional)

        ---
        """)

        # Mostrar estadísticas
        mostrar_panel_estadisticas()

    with tab2:
        # Mostrar formulario del website público
        mostrar_formulario_inscripcion()

    with tab3:
        # Lista de inscritos
        mostrar_lista_inscritos_administracion()

    with tab4:
        # Configuración
        mostrar_configuracion_administracion()

    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; font-size: 12px;">
        <p>🏥 Escuela de Enfermería - Sistema de Gestión de Aspirantes v3.0</p>
        <p>🔗 Conectado remotamente via SSH - Timeouts y Reintentos Inteligentes</p>
        <p>© 2024 Departamento de Tecnología. Todos los derechos reservados.</p>
    </div>
    """, unsafe_allow_html=True)

# =============================================================================
# FUNCIÓN PRINCIPAL - INTEGRACIÓN COMPLETA
# =============================================================================

def main():
    """Función principal de la aplicación integrada"""
    
    # Sidebar con estado del sistema y navegación
    with st.sidebar:
        st.title("🏥 Sistema de Enfermería")
        st.markdown("---")
        
        st.subheader("🔗 Estado del Sistema")
        
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

        st.markdown("---")
        
        # Navegación principal
        st.subheader("📱 Navegación")
        
        # Modo de operación
        modo = st.radio(
            "Selecciona el modo:",
            ["🌐 Website Público", "🔧 Administración"],
            key="modo_navegacion"
        )
        
        st.markdown("---")
        
        # Estadísticas rápidas
        st.subheader("📈 Estadísticas")
        col_stat1, col_stat2 = st.columns(2)
        with col_stat1:
            total_inscritos = estado_sistema.estado.get('total_inscritos', 0)
            st.metric("Inscritos", total_inscritos)
        with col_stat2:
            backups = estado_sistema.estado.get('backups_realizados', 0)
            st.metric("Backups", backups)

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
                backup_path = sistema.backup_system.crear_backup(
                    "MANUAL_SIDEBAR",
                    "Backup manual creado desde sidebar"
                )
                if backup_path:
                    st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                else:
                    st.error("❌ Error creando backup")
        
        st.markdown("---")
        
        # Información de versión
        st.caption("🏥 Sistema Integrado v3.0")
        st.caption("🔗 SSH Mejorado + Website Público")

    # Mostrar la interfaz correspondiente al modo seleccionado
    if st.session_state.get('modo_navegacion') == "🌐 Website Público":
        mostrar_pagina_principal_website()
    else:
        mostrar_pagina_principal_administracion()

# =============================================================================
# EJECUCIÓN PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    try:
        # Mostrar banner informativo
        st.info("""
        🏥 **SISTEMA DE GESTIÓN DE ASPIRANTES - VERSIÓN MEJORADA CON SSH + WEBSITE PÚBLICO**

        **Mejoras implementadas:**
        ✅ Timeouts específicos para operaciones de red (conexión, comandos, transferencia)
        ✅ Reintentos inteligentes con backoff exponencial (3 intentos por defecto)
        ✅ Verificación de espacio en disco antes de operaciones
        ✅ Sistema de backup automático antes de operaciones críticas
        ✅ Logs detallados para diagnóstico de problemas
        ✅ Manejo robusto de errores con información específica
        ✅ Notificaciones por email para operaciones importantes
        ✅ Verificación de integridad de base de datos
        ✅ **NUEVO:** Website público con información institucional
        ✅ **NUEVO:** Opciones académicas mejoradas
        ✅ **NUEVO:** Testimonios de estudiantes y egresados

        **Para comenzar:**
        1. Configura secrets.toml con tus credenciales SSH
        2. Haz clic en "Inicializar Base de Datos" en la página principal
        3. Usa el formulario para registrar nuevos aspirantes

        **Características exclusivas de esta versión:**
        🔒 Todos los datos se guardan EXCLUSIVAMENTE en servidor remoto
        📊 Panel de estadísticas en tiempo real
        💾 Sistema automático de backups con retención de 10 backups
        📧 Envío automático de correos de confirmación a aspirantes
        🌐 Website público con información institucional
        🎓 Catálogo completo de programas académicos
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

            st.write("**Variables de entorno relevantas:**")
            env_vars = {k: v for k, v in os.environ.items() if 'STREAMLIT' in k or 'PYTHON' in k}
            st.json(env_vars)
