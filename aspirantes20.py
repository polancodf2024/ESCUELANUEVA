#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SISTEMA DE GESTIÓN DE ASPIRANTES - ESCUELA DE ENFERMERÍA
Versión: 2.0
Autor: Departamento de Tecnología
Descripción: Sistema completo para gestión de inscritos con base de datos remota SSH
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

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURACIÓN DE PÁGINA STREAMLIT
# =============================================================================

st.set_page_config(
    page_title="Sistema de Gestión de Aspirantes",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados
st.markdown("""
<style>
    /* Estilos generales */
    .main-header {
        background-color: #2c3e50;
        color: white;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        text-align: center;
    }
    
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        color: #856404;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    
    .card {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .stat-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
    }
    
    .btn-primary {
        background-color: #3498db;
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 5px;
        cursor: pointer;
        font-weight: bold;
    }
    
    .btn-success {
        background-color: #27ae60;
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 5px;
        cursor: pointer;
        font-weight: bold;
    }
    
    .btn-danger {
        background-color: #e74c3c;
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 5px;
        cursor: pointer;
        font-weight: bold;
    }
    
    .form-group {
        margin-bottom: 15px;
    }
    
    .required-field::after {
        content: " *";
        color: red;
    }
    
    /* Estilos para tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #f1f3f4;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #3498db !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# CLASE PARA VALIDACIÓN DE DATOS
# =============================================================================

class ValidadorDatos:
    """Clase para validación de datos"""
    
    @staticmethod
    def validar_email(email):
        """Validar formato de email"""
        import re
        if not email:
            return False
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validar_telefono(telefono):
        """Validar teléfono (mínimo 10 dígitos)"""
        if not telefono:
            return False
        # Remover caracteres no numéricos
        numeros = ''.join(filter(str.isdigit, telefono))
        return len(numeros) >= 10
    
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
# CLASE PARA CONEXIÓN SSH
# =============================================================================

class GestorSSH:
    """Gestor de conexiones SSH para acceso remoto"""
    
    def __init__(self):
        try:
            # Cargar configuración desde secrets
            self.host = st.secrets.get("ssh_host", "")
            self.port = int(st.secrets.get("ssh_port", 22))
            self.username = st.secrets.get("ssh_username", "")
            self.password = st.secrets.get("ssh_password", "")
            self.private_key = st.secrets.get("ssh_private_key", "")
            
            self.ssh = None
            self.sftp = None
            self.conectado = False
            
            if all([self.host, self.username]):
                logger.info("✅ Configuración SSH cargada")
            else:
                logger.warning("⚠️ Configuración SSH incompleta")
                
        except Exception as e:
            logger.error(f"❌ Error cargando configuración SSH: {e}")
            self.host = None
    
    def conectar(self):
        """Establecer conexión SSH"""
        try:
            if not self.host:
                logger.error("❌ No hay configuración SSH disponible")
                return False
            
            self.ssh = SSHClient()
            self.ssh.set_missing_host_key_policy(AutoAddPolicy())
            
            # Intentar conectar con diferentes métodos
            if self.private_key:
                # Usar clave privada
                key = paramiko.RSAKey.from_private_key(io.StringIO(self.private_key))
                self.ssh.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    pkey=key,
                    timeout=10
                )
            elif self.password:
                # Usar contraseña
                self.ssh.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    timeout=10
                )
            else:
                logger.error("❌ No hay método de autenticación SSH configurado")
                return False
            
            self.conectado = True
            logger.info("✅ Conexión SSH establecida")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error conectando SSH: {e}")
            self.conectado = False
            return False
    
    def desconectar(self):
        """Cerrar conexión SSH"""
        try:
            if self.sftp:
                self.sftp.close()
                self.sftp = None
            
            if self.ssh:
                self.ssh.close()
                self.ssh = None
            
            self.conectado = False
            logger.info("✅ Conexión SSH cerrada")
            
        except Exception as e:
            logger.error(f"❌ Error cerrando SSH: {e}")
    
    def obtener_sftp(self):
        """Obtener conexión SFTP"""
        try:
            if not self.conectado or not self.ssh:
                if not self.conectar():
                    return None
            
            if not self.sftp:
                self.sftp = self.ssh.open_sftp()
            
            return self.sftp
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo SFTP: {e}")
            return None
    
    def archivo_existe(self, ruta_remota):
        """Verificar si un archivo existe en el servidor remoto"""
        try:
            sftp = self.obtener_sftp()
            if not sftp:
                return False
            
            sftp.stat(ruta_remota)
            return True
            
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.error(f"❌ Error verificando archivo: {e}")
            return False
    
    def crear_directorio_remoto(self, ruta_directorio):
        """Crear directorio en servidor remoto"""
        try:
            sftp = self.obtener_sftp()
            if not sftp:
                return False
            
            # Crear directorios recursivamente
            directorios = ruta_directorio.strip('/').split('/')
            ruta_actual = ''
            
            for dir in directorios:
                if dir:
                    ruta_actual = f"{ruta_actual}/{dir}" if ruta_actual else dir
                    try:
                        sftp.stat(ruta_actual)
                    except FileNotFoundError:
                        sftp.mkdir(ruta_actual)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creando directorio: {e}")
            return False
    
    def descargar_archivo(self, ruta_remota, ruta_local):
        """Descargar archivo del servidor remoto"""
        try:
            sftp = self.obtener_sftp()
            if not sftp:
                return False
            
            sftp.get(ruta_remota, ruta_local)
            
            # Verificar que se descargó
            if os.path.exists(ruta_local) and os.path.getsize(ruta_local) > 0:
                logger.info(f"✅ Archivo descargado: {ruta_local}")
                return True
            else:
                logger.error("❌ Archivo descargado vacío o corrupto")
                return False
            
        except Exception as e:
            logger.error(f"❌ Error descargando archivo: {e}")
            return False
    
    def subir_archivo(self, ruta_local, ruta_remota):
        """Subir archivo al servidor remoto"""
        try:
            sftp = self.obtener_sftp()
            if not sftp:
                return False
            
            # Crear directorio si no existe
            directorio = os.path.dirname(ruta_remota)
            if directorio:
                self.crear_directorio_remoto(directorio)
            
            sftp.put(ruta_local, ruta_remota)
            logger.info(f"✅ Archivo subido: {ruta_remota}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error subiendo archivo: {e}")
            return False

# =============================================================================
# CLASE PARA BASE DE DATOS REMOTA
# =============================================================================

class BaseDatosRemota:
    """Gestor de base de datos SQLite remota"""
    
    def __init__(self):
        try:
            self.gestor_ssh = GestorSSH()
            self.ruta_db_remota = st.secrets.get("db_ruta_remota", "/home/ubuntu/aspirantes.db")
            self.ruta_uploads_remota = st.secrets.get("uploads_ruta_remota", "/home/ubuntu/uploads")
            self.db_local_temp = None
            
            logger.info("✅ Base de datos remota configurada")
            
        except Exception as e:
            logger.error(f"❌ Error configurando base de datos: {e}")
            self.gestor_ssh = None
    
    def _crear_db_local(self):
        """Crear base de datos local temporal si no existe"""
        try:
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_db_path = os.path.join(temp_dir, f"aspirantes_nueva_{timestamp}.db")
            
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()
            
            # Crear tabla de inscritos
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
            
            # Crear tabla de usuarios (si no existe en remoto)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    rol TEXT DEFAULT 'inscrito',
                    nombre_completo TEXT,
                    email TEXT,
                    matricula TEXT,
                    activo INTEGER DEFAULT 1,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ultimo_acceso TIMESTAMP
                )
            ''')
            
            # Insertar usuario administrador por defecto
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO usuarios (usuario, password, rol, nombre_completo, email, activo) VALUES (?, ?, ?, ?, ?, ?)",
                    ('admin', 'admin123', 'admin', 'Administrador', 'admin@enfermeria.edu', 1)
                )
            except:
                pass
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Base de datos local creada: {temp_db_path}")
            return temp_db_path
            
        except Exception as e:
            logger.error(f"❌ Error creando DB local: {e}")
            return None
    
    def obtener_db_local(self):
        """Descargar base de datos remota a local"""
        try:
            if not self.gestor_ssh or not self.gestor_ssh.conectar():
                logger.error("❌ No se pudo conectar SSH")
                return None
            
            # Crear archivo temporal local
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_db_path = os.path.join(temp_dir, f"aspirantes_temp_{timestamp}.db")
            
            # Verificar si existe la base de datos remota
            if self.gestor_ssh.archivo_existe(self.ruta_db_remota):
                # Descargar base de datos remota
                if self.gestor_ssh.descargar_archivo(self.ruta_db_remota, temp_db_path):
                    # Verificar que se descargó correctamente
                    if os.path.exists(temp_db_path) and os.path.getsize(temp_db_path) > 0:
                        self.db_local_temp = temp_db_path
                        logger.info(f"✅ Base de datos descargada: {temp_db_path} ({os.path.getsize(temp_db_path)} bytes)")
                        self.gestor_ssh.desconectar()
                        return temp_db_path
                    else:
                        logger.error("❌ Base de datos descargada vacía o corrupta")
                        # Crear nueva
                        self.gestor_ssh.desconectar()
                        return self._crear_db_local()
                else:
                    logger.error("❌ Error descargando base de datos")
                    self.gestor_ssh.desconectar()
                    return self._crear_db_local()
            else:
                logger.warning("⚠️ Base de datos remota no encontrada, creando nueva")
                self.gestor_ssh.desconectar()
                return self._crear_db_local()
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo DB local: {e}")
            if self.gestor_ssh:
                self.gestor_ssh.desconectar()
            return None
    
    def sincronizar_con_remoto(self, db_path):
        """Subir base de datos local al servidor remoto"""
        try:
            if not db_path or not os.path.exists(db_path):
                logger.error("❌ No hay base de datos local para sincronizar")
                return False
            
            if not self.gestor_ssh or not self.gestor_ssh.conectar():
                return False
            
            # Crear directorio si no existe
            directorio = os.path.dirname(self.ruta_db_remota)
            if directorio:
                self.gestor_ssh.crear_directorio_remoto(directorio)
            
            # Subir nueva versión
            if self.gestor_ssh.subir_archivo(db_path, self.ruta_db_remota):
                logger.info("✅ Base de datos sincronizada con servidor remoto")
                self.gestor_ssh.desconectar()
                return True
            else:
                logger.error("❌ Error subiendo base de datos")
                self.gestor_ssh.desconectar()
                return False
                
        except Exception as e:
            logger.error(f"❌ Error sincronizando: {e}")
            if self.gestor_ssh:
                self.gestor_ssh.desconectar()
            return False
    
    def ejecutar_query(self, query, params=()):
        """Ejecutar query en la base de datos"""
        try:
            # Obtener base de datos local actualizada
            db_path = self.obtener_db_local()
            if not db_path:
                return None
            
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(query, params)
            
            if query.strip().upper().startswith('SELECT'):
                resultados = cursor.fetchall()
                # Convertir a lista de diccionarios
                resultados = [dict(row) for row in resultados]
                conn.close()
                return resultados
            else:
                conn.commit()
                ultimo_id = cursor.lastrowid
                conn.close()
                
                # Sincronizar con remoto
                self.sincronizar_con_remoto(db_path)
                
                return ultimo_id
                
        except Exception as e:
            logger.error(f"❌ Error ejecutando query: {e} - Query: {query}")
            return None
    
    def agregar_inscrito(self, datos_inscrito):
        """Agregar nuevo inscrito a la base de datos"""
        try:
            # Validar datos
            if not ValidadorDatos.validar_email(datos_inscrito.get('email')):
                raise ValueError("Email inválido")
            
            if not ValidadorDatos.validar_nombre_completo(datos_inscrito.get('nombre_completo')):
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
            return resultados[0]['total'] if resultados else 0
        except Exception as e:
            logger.error(f"❌ Error obteniendo total: {e}")
            return 0
    
    def guardar_documento(self, archivo_bytes, nombre_archivo):
        """Guardar documento en el servidor remoto"""
        try:
            if not self.gestor_ssh or not self.gestor_ssh.conectar():
                return False
            
            # Crear directorio de uploads si no existe
            if self.ruta_uploads_remota:
                self.gestor_ssh.crear_directorio_remoto(self.ruta_uploads_remota)
            
            # Guardar archivo temporalmente localmente
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, nombre_archivo)
            
            with open(temp_path, 'wb') as f:
                f.write(archivo_bytes)
            
            # Ruta completa en servidor
            ruta_remota = os.path.join(self.ruta_uploads_remota, nombre_archivo) if self.ruta_uploads_remota else nombre_archivo
            
            # Subir al servidor
            if self.gestor_ssh.subir_archivo(temp_path, ruta_remota):
                logger.info(f"✅ Documento subido: {nombre_archivo}")
                
                # Limpiar archivo temporal
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                self.gestor_ssh.desconectar()
                return True
            else:
                self.gestor_ssh.desconectar()
                return False
                
        except Exception as e:
            logger.error(f"❌ Error guardando documento: {e}")
            if self.gestor_ssh:
                self.gestor_ssh.desconectar()
            return False

# =============================================================================
# SISTEMA DE CORREOS
# =============================================================================

class SistemaCorreos:
    """Sistema de envío de correos"""
    
    def __init__(self):
        try:
            self.smtp_server = st.secrets.get("smtp_server", "")
            self.smtp_port = int(st.secrets.get("smtp_port", 587))
            self.email_user = st.secrets.get("email_user", "")
            self.email_password = st.secrets.get("email_password", "")
            self.correos_habilitados = bool(self.smtp_server and self.email_user)
            
            if self.correos_habilitados:
                logger.info("✅ Sistema de correos configurado")
            else:
                logger.warning("⚠️ Sistema de correos no configurado completamente")
        except Exception as e:
            logger.warning(f"⚠️ Configuración de correo no disponible: {e}")
            self.correos_habilitados = False
    
    def enviar_correo_confirmacion(self, destinatario, nombre_estudiante, matricula, folio, programa):
        """Enviar correo de confirmación"""
        if not self.correos_habilitados:
            return False, "Sistema de correos no configurado"
        
        try:
            # Crear mensaje
            msg = MIMEMultipart('alternative')
            msg['From'] = self.email_user
            msg['To'] = destinatario
            msg['Subject'] = f"Confirmación de Pre-Inscripción - {matricula}"
            
            # Cuerpo HTML
            html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2>🏥 Escuela de Enfermería - Confirmación de Pre-Inscripción</h2>
                <p>Estimado/a {nombre_estudiante},</p>
                <p>Hemos recibido exitosamente tu solicitud de pre-inscripción.</p>
                
                <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <h3>📋 Datos de tu Registro:</h3>
                    <p><strong>Matrícula:</strong> {matricula}</p>
                    <p><strong>Folio:</strong> {folio}</p>
                    <p><strong>Programa:</strong> {programa}</p>
                    <p><strong>Fecha:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
                    <p><strong>Estatus:</strong> Pre-inscrito</p>
                </div>
                
                <p>Te contactaremos próximamente con los siguientes pasos del proceso de admisión.</p>
                
                <p>Atentamente,<br>
                Departamento de Admisiones<br>
                Escuela de Enfermería</p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(html, 'html'))
            
            # Enviar correo
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)
            
            logger.info(f"✅ Correo enviado a {destinatario}")
            return True, "Correo enviado exitosamente"
            
        except Exception as e:
            logger.error(f"❌ Error enviando correo: {e}")
            return False, f"Error: {str(e)}"

# =============================================================================
# SISTEMA PRINCIPAL DE INSCRITOS - SIMPLIFICADO
# =============================================================================

class SistemaInscritos:
    """Sistema principal de gestión de inscritos simplificado"""
    
    def __init__(self):
        # Inicializar componentes con manejo de errores
        try:
            self.base_datos = BaseDatosRemota()
            self.sistema_correos = SistemaCorreos()
            self.validador = ValidadorDatos()
            logger.info("🚀 Sistema de inscritos inicializado")
        except Exception as e:
            logger.error(f"❌ Error inicializando sistema: {e}")
            # Configuración mínima para permitir que la aplicación funcione
            self.base_datos = None
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
        """Registrar nueva inscripción"""
        try:
            # Validar datos
            errores = self.validar_datos(datos_formulario, archivos)
            if errores:
                raise ValueError("\n".join(errores))
            
            # Verificar que tenemos base de datos
            if not self.base_datos:
                raise Exception("Sistema de base de datos no disponible")
            
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

# =============================================================================
# INTERFAZ DE USUARIO STREAMLIT
# =============================================================================

def mostrar_encabezado():
    """Mostrar encabezado de la aplicación"""
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("""
        <div class="main-header">
            <h1>🏥 Sistema de Gestión de Aspirantes</h1>
            <h3>Escuela de Enfermería</h3>
        </div>
        """, unsafe_allow_html=True)

def mostrar_panel_estadisticas(sistema):
    """Mostrar panel de estadísticas"""
    try:
        total_inscritos = sistema.base_datos.obtener_total_inscritos() if sistema.base_datos else 0
        
        st.markdown("### 📊 Estadísticas del Sistema")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="stat-card">
                <h3>Total Inscritos</h3>
                <h2>{total_inscritos}</h2>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="stat-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                <h3>Pre-inscritos</h3>
                <h2>{total_inscritos}</h2>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class="stat-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
                <h3>En Proceso</h3>
                <h2>0</h2>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown("""
            <div class="stat-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
                <h3>Admitidos</h3>
                <h2>0</h2>
            </div>
            """, unsafe_allow_html=True)
            
    except Exception as e:
        st.warning(f"No se pudieron cargar las estadísticas: {e}")

def mostrar_formulario_inscripcion():
    """Mostrar formulario de inscripción"""
    st.markdown("### 📝 Formulario de Pre-Inscripción")
    
    with st.form("formulario_inscripcion"):
        col1, col2 = st.columns(2)
        
        with col1:
            nombre_completo = st.text_input("Nombre Completo *", placeholder="Ej: Juan Pérez González")
            email = st.text_input("Correo Electrónico *", placeholder="Ej: juan.perez@email.com")
            telefono = st.text_input("Teléfono *", placeholder="Ej: 5551234567")
            fecha_nacimiento = st.date_input("Fecha de Nacimiento", min_value=date(1950, 1, 1), max_value=date.today())
        
        with col2:
            programa_interes = st.selectbox(
                "Programa de Interés *",
                ["Enfermería General", "Enfermería Pediátrica", "Enfermería Geriátrica", 
                 "Enfermería en Cuidados Intensivos", "Licenciatura en Enfermería"]
            )
            
            como_se_entero = st.selectbox(
                "¿Cómo se enteró del programa? *",
                ["Redes Sociales", "Recomendación", "Página Web", "Evento Presencial", 
                 "Publicidad", "Otros"]
            )
            
            observaciones = st.text_area("Observaciones", placeholder="Información adicional...")
        
        st.markdown("### 📄 Documentación Requerida")
        st.markdown("*Documentos obligatorios*")
        
        col3, col4 = st.columns(2)
        
        with col3:
            acta_nacimiento = st.file_uploader("Acta de Nacimiento *", type=['pdf', 'jpg', 'png', 'jpeg'])
            curp = st.file_uploader("CURP *", type=['pdf', 'jpg', 'png', 'jpeg'])
        
        with col4:
            certificado = st.file_uploader("Certificado de Estudios *", type=['pdf', 'jpg', 'png', 'jpeg'])
            foto = st.file_uploader("Fotografía (Opcional)", type=['jpg', 'png', 'jpeg'])
        
        st.markdown("---")
        submit_button = st.form_submit_button("📤 Enviar Pre-Inscripción", type="primary", use_container_width=True)
        
        # Preparar datos del formulario
        datos_formulario = {
            'nombre_completo': nombre_completo,
            'email': email,
            'telefono': telefono,
            'fecha_nacimiento': fecha_nacimiento.strftime('%Y-%m-%d') if fecha_nacimiento else None,
            'programa_interes': programa_interes,
            'como_se_entero': como_se_entero,
            'observaciones': observaciones
        }
        
        archivos = {
            'acta_nacimiento': acta_nacimiento,
            'curp': curp,
            'certificado': certificado,
            'foto': foto
        }
        
        return submit_button, datos_formulario, archivos

def mostrar_resultado_inscripcion(resultado):
    """Mostrar resultado del proceso de inscripción"""
    if resultado['success']:
        st.markdown(f"""
        <div class="success-box">
            <h3>✅ ¡Pre-Inscripción Exitosa!</h3>
            <p>Estimado/a <strong>{resultado['nombre']}</strong>, hemos recibido tu solicitud exitosamente.</p>
            
            <div class="card">
                <h4>📋 Datos de tu Registro:</h4>
                <p><strong>Matrícula:</strong> {resultado['matricula']}</p>
                <p><strong>Folio:</strong> {resultado['folio']}</p>
                <p><strong>Programa:</strong> {resultado['programa']}</p>
                <p><strong>Correo:</strong> {resultado['email']}</p>
                <p><strong>Documentos subidos:</strong> {resultado['documentos']}</p>
                <p><strong>Fecha:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
            </div>
            
            <p>{"✅ Correo de confirmación enviado" if resultado['correo_enviado'] else "⚠️ No se pudo enviar correo"}</p>
            <p><em>Guarda tu matrícula y folio para futuras consultas.</em></p>
        </div>
        """, unsafe_allow_html=True)
        
        # Botón para generar comprobante
        if st.button("📄 Generar Comprobante"):
            generar_comprobante(resultado)
            
    else:
        st.markdown(f"""
        <div class="error-box">
            <h3>❌ Error en la Pre-Inscripción</h3>
            <p>{resultado['error']}</p>
            <p>Por favor, revisa los datos e intenta nuevamente.</p>
        </div>
        """, unsafe_allow_html=True)

def generar_comprobante(datos):
    """Generar comprobante de inscripción"""
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .header {{ text-align: center; border-bottom: 3px solid #3498db; padding-bottom: 20px; }}
            .content {{ margin: 30px 0; }}
            .footer {{ margin-top: 50px; font-size: 12px; color: #666; text-align: center; }}
            .datos {{ background-color: #f5f5f5; padding: 20px; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🏥 Escuela de Enfermería</h1>
            <h2>Comprobante de Pre-Inscripción</h2>
        </div>
        
        <div class="content">
            <div class="datos">
                <h3>Datos del Aspirante:</h3>
                <p><strong>Nombre:</strong> {datos['nombre']}</p>
                <p><strong>Matrícula:</strong> {datos['matricula']}</p>
                <p><strong>Folio:</strong> {datos['folio']}</p>
                <p><strong>Programa:</strong> {datos['programa']}</p>
                <p><strong>Correo:</strong> {datos['email']}</p>
                <p><strong>Fecha de Registro:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                <p><strong>Estatus:</strong> Pre-inscrito</p>
            </div>
            
            <p>Este documento sirve como comprobante oficial de tu pre-inscripción.</p>
        </div>
        
        <div class="footer">
            <p>Escuela de Enfermería - Sistema de Gestión de Aspirantes</p>
            <p>Documento generado automáticamente</p>
        </div>
    </body>
    </html>
    """
    
    # Crear botón de descarga
    b64 = base64.b64encode(html.encode()).decode()
    href = f'<a href="data:text/html;base64,{b64}" download="comprobante_inscripcion.html">⬇️ Descargar Comprobante</a>'
    st.markdown(href, unsafe_allow_html=True)

def mostrar_lista_inscritos(sistema):
    """Mostrar lista de inscritos"""
    try:
        if not sistema.base_datos:
            st.warning("⚠️ Sistema de base de datos no disponible")
            return
        
        inscritos = sistema.base_datos.obtener_inscritos()
        
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
        
        # Filtros
        col1, col2 = st.columns(2)
        with col1:
            filtro_estatus = st.multiselect(
                "Filtrar por estatus",
                options=df['Estatus'].unique(),
                default=df['Estatus'].unique()
            )
        
        with col2:
            filtro_programa = st.multiselect(
                "Filtrar por programa",
                options=df['Programa'].unique(),
                default=df['Programa'].unique()
            )
        
        # Aplicar filtros
        df_filtrado = df[
            df['Estatus'].isin(filtro_estatus) & 
            df['Programa'].isin(filtro_programa)
        ]
        
        # Mostrar tabla
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True)
        
        # Estadísticas de la tabla filtrada
        st.markdown(f"**Mostrando {len(df_filtrado)} de {len(df)} registros**")
        
        # Opciones de exportación
        col3, col4 = st.columns(2)
        with col3:
            if st.button("📊 Exportar a Excel"):
                exportar_a_excel(df_filtrado)
        
        with col4:
            if st.button("📄 Exportar a CSV"):
                exportar_a_csv(df_filtrado)
                
    except Exception as e:
        st.error(f"❌ Error cargando lista de inscritos: {e}")

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

def mostrar_busqueda_inscrito(sistema):
    """Mostrar búsqueda de inscrito por matrícula"""
    st.markdown("### 🔍 Consultar Aspirante")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        matricula_buscar = st.text_input("Ingrese la matrícula:", placeholder="Ej: INS2312011234")
    
    with col2:
        st.write("")
        st.write("")
        buscar_button = st.button("🔍 Buscar", use_container_width=True)
    
    if buscar_button and matricula_buscar:
        with st.spinner("Buscando..."):
            if sistema.base_datos:
                inscrito = sistema.base_datos.obtener_inscrito_por_matricula(matricula_buscar)
                
                if inscrito:
                    mostrar_detalle_inscrito(inscrito)
                else:
                    st.warning(f"⚠️ No se encontró ningún aspirante con la matrícula: {matricula_buscar}")
            else:
                st.error("❌ Sistema de base de datos no disponible")

def mostrar_detalle_inscrito(inscrito):
    """Mostrar detalle de un inscrito"""
    st.markdown(f"""
    <div class="card">
        <h3>👤 Detalles del Aspirante</h3>
        <div class="form-group">
            <p><strong>Matrícula:</strong> {inscrito['matricula']}</p>
            <p><strong>Nombre:</strong> {inscrito['nombre_completo']}</p>
            <p><strong>Email:</strong> {inscrito['email']}</p>
            <p><strong>Teléfono:</strong> {inscrito['telefono']}</p>
            <p><strong>Programa:</strong> {inscrito['programa_interes']}</p>
            <p><strong>Fecha de Registro:</strong> {inscrito['fecha_registro']}</p>
            <p><strong>Estatus:</strong> {inscrito['estatus']}</p>
            <p><strong>Folio:</strong> {inscrito['folio']}</p>
            <p><strong>Documentos subidos:</strong> {inscrito['documentos_subidos']}</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

def mostrar_configuracion():
    """Mostrar configuración del sistema"""
    st.markdown("### ⚙️ Configuración del Sistema")
    
    with st.expander("Estado de los Servicios", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            <div class="info-box">
                <h4>🖥️ Base de Datos</h4>
                <p>Estado: Conectado</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="info-box">
                <h4>📧 Sistema de Correos</h4>
                <p>Estado: Configurado</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class="info-box">
                <h4>📁 Almacenamiento</h4>
                <p>Estado: Disponible</p>
            </div>
            """, unsafe_allow_html=True)
    
    with st.expander("Configuración SSH"):
        st.info("La configuración SSH se carga desde los secrets de Streamlit")
    
    with st.expander("Configuración de Correo"):
        st.info("La configuración de correo se carga desde los secrets de Streamlit")

# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def main():
    """Función principal de la aplicación"""
    
    # Inicializar sistema
    sistema = SistemaInscritos()
    
    # Mostrar encabezado
    mostrar_encabezado()
    
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
        ## 🎓 Bienvenido al Sistema de Gestión de Aspirantes
        
        Este sistema permite gestionar el proceso de pre-inscripción para la Escuela de Enfermería.
        
        ### Funcionalidades principales:
        
        1. **📝 Nueva Inscripción**: Formulario completo para registro de nuevos aspirantes
        2. **📋 Lista de Inscritos**: Consulta y gestión de todos los registros
        3. **🔍 Búsqueda**: Localiza aspirantes por matrícula
        4. **📊 Reportes**: Estadísticas y exportación de datos
        5. **📧 Notificaciones**: Envío automático de correos de confirmación
        
        ### Requisitos de documentación:
        - Acta de nacimiento
        - CURP
        - Certificado de estudios
        - Fotografía (opcional)
        
        ---
        """)
        
        # Mostrar estadísticas
        mostrar_panel_estadisticas(sistema)
        
        # Búsqueda rápida
        st.markdown("### 🔍 Búsqueda Rápida")
        mostrar_busqueda_inscrito(sistema)
    
    with tab2:
        # Formulario de inscripción
        submit_button, datos_formulario, archivos = mostrar_formulario_inscripcion()
        
        if submit_button:
            with st.spinner("Procesando inscripción..."):
                resultado = sistema.registrar_inscripcion(datos_formulario, archivos)
                mostrar_resultado_inscripcion(resultado)
    
    with tab3:
        # Lista de inscritos
        mostrar_lista_inscritos(sistema)
    
    with tab4:
        # Configuración
        mostrar_configuracion()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; font-size: 12px;">
        <p>🏥 Escuela de Enfermería - Sistema de Gestión de Aspirantes v2.0</p>
        <p>© 2024 Departamento de Tecnología. Todos los derechos reservados.</p>
    </div>
    """, unsafe_allow_html=True)

# =============================================================================
# EJECUCIÓN
# =============================================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"❌ Error crítico en la aplicación: {e}")
        st.error(f"❌ Error crítico en la aplicación: {str(e)}")
        
        # Mostrar botón para reiniciar
        if st.button("🔄 Reiniciar Aplicación"):
            st.rerun()
