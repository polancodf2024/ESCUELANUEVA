import streamlit as st
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, date, timedelta
import hashlib
import base64
import random
import string
from PIL import Image
import paramiko
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import warnings
import sqlite3
import tempfile
import bcrypt
import socket
import re
import time
import logging
import atexit
import glob
import psutil
import math
warnings.filterwarnings('ignore')

# =============================================================================
# CONFIGURACIÓN DE PÁGINA PARA WEBSITE PÚBLICO
# =============================================================================

st.set_page_config(
    page_title="Sistema Escuela Enfermería - Pre-Inscripción",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# CONFIGURACIÓN DE LOGGING
# =============================================================================

class SistemaLogger:
    """Sistema de logging para diagnóstico"""
    
    def __init__(self):
        # Configurar logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('aspirantes.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('aspirantes_sistema')
    
    def info(self, message):
        self.logger.info(message)
    
    def error(self, message):
        self.logger.error(message)
    
    def warning(self, message):
        self.logger.warning(message)
    
    def debug(self, message):
        self.logger.debug(message)

logger = SistemaLogger()

# =============================================================================
# VALIDACIONES DE DATOS
# =============================================================================

class ValidadorDatos:
    """Validaciones de datos mejoradas"""
    
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
        digitos = ''.join(filter(str.isdigit, telefono))
        return len(digitos) >= 10
    
    @staticmethod
    def validar_matricula(matricula):
        """Validar formato de matrícula"""
        if not matricula:
            return False
        return len(matricula) >= 3 and any(char.isdigit() for char in matricula)
    
    @staticmethod
    def validar_nombre_completo(nombre):
        """Validar nombre completo"""
        if not nombre:
            return False
        # Debe tener al menos 2 palabras (nombre y apellido)
        palabras = nombre.strip().split()
        return len(palabras) >= 2

# =============================================================================
# GESTOR DE CONEXIÓN REMOTA VIA SSH - SIMPLIFICADO Y FUNCIONAL
# =============================================================================

class GestorConexionSSH:
    """Gestor simplificado de conexión SSH"""
    
    def __init__(self):
        self.ssh = None
        self.sftp = None
        self.config = self._cargar_configuracion()
        logger.info("✅ Configuración SSH cargada")
    
    def _cargar_configuracion(self):
        """Cargar configuración desde secrets.toml"""
        config = {
            'host': st.secrets["remote_host"],
            'port': int(st.secrets["remote_port"]),
            'username': st.secrets["remote_user"],
            'password': st.secrets["remote_password"],
            'remote_dir': st.secrets["remote_dir"],
            'remote_db_inscritos': st.secrets["remote_db_inscritos"],
            'remote_uploads_inscritos': st.secrets["remote_uploads_inscritos"]
        }
        return config
    
    def conectar(self):
        """Conectar al servidor SSH"""
        try:
            logger.info(f"🔗 Conectando a {self.config['host']}:{self.config['port']}")
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.ssh.connect(
                hostname=self.config['host'],
                port=self.config['port'],
                username=self.config['username'],
                password=self.config['password'],
                timeout=30
            )
            
            self.sftp = self.ssh.open_sftp()
            logger.info("✅ Conexión SSH establecida")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error de conexión SSH: {e}")
            return False
    
    def desconectar(self):
        """Desconectar del servidor SSH"""
        try:
            if self.sftp:
                self.sftp.close()
            if self.ssh:
                self.ssh.close()
            logger.debug("🔌 Conexión SSH cerrada")
        except:
            pass
    
    def ejecutar_comando(self, comando):
        """Ejecutar comando remoto"""
        try:
            stdin, stdout, stderr = self.ssh.exec_command(comando)
            salida = stdout.read().decode()
            error = stderr.read().decode()
            return salida, error
        except Exception as e:
            logger.error(f"Error ejecutando comando: {e}")
            return "", str(e)
    
    def descargar_archivo(self, ruta_remota, ruta_local):
        """Descargar archivo del servidor"""
        try:
            self.sftp.get(ruta_remota, ruta_local)
            logger.info(f"📥 Descargado: {ruta_remota} -> {ruta_local}")
            return True
        except Exception as e:
            logger.error(f"Error descargando archivo: {e}")
            return False
    
    def subir_archivo(self, ruta_local, ruta_remota):
        """Subir archivo al servidor"""
        try:
            self.sftp.put(ruta_local, ruta_remota)
            logger.info(f"📤 Subido: {ruta_local} -> {ruta_remota}")
            return True
        except Exception as e:
            logger.error(f"Error subiendo archivo: {e}")
            return False
    
    def crear_directorio(self, ruta_remota):
        """Crear directorio remoto"""
        try:
            self.sftp.mkdir(ruta_remota)
            logger.info(f"📁 Directorio creado: {ruta_remota}")
            return True
        except:
            # Directorio ya existe o error
            return False
    
    def archivo_existe(self, ruta_remota):
        """Verificar si archivo existe"""
        try:
            self.sftp.stat(ruta_remota)
            return True
        except:
            return False
    
    def listar_archivos(self, ruta_directorio):
        """Listar archivos en directorio"""
        try:
            return self.sftp.listdir(ruta_directorio)
        except:
            return []

# =============================================================================
# MANEJO DE BASE DE DATOS SQLITE REMOTA
# =============================================================================

class BaseDatosRemota:
    """Manejo de base de datos SQLite en servidor remoto"""
    
    def __init__(self):
        self.gestor_ssh = GestorConexionSSH()
        self.config = self.gestor_ssh.config
        self.ruta_db_remota = self.config['remote_db_inscritos']
        self.ruta_uploads_remota = self.config['remote_uploads_inscritos']
        self.db_local_temp = None
        
        # Inicializar estructura si no existe
        self._inicializar_db()
    
    def _inicializar_db(self):
        """Inicializar base de datos si no existe"""
        try:
            if not self.gestor_ssh.conectar():
                logger.error("❌ No se pudo conectar para inicializar DB")
                return False
            
            # Verificar si la DB existe en remoto
            if not self.gestor_ssh.archivo_existe(self.ruta_db_remota):
                logger.info("📝 Creando nueva base de datos remota...")
                
                # Crear directorios necesarios
                directorio_db = os.path.dirname(self.ruta_db_remota)
                self.gestor_ssh.crear_directorio(directorio_db)
                self.gestor_ssh.crear_directorio(self.ruta_uploads_remota)
                
                # Crear DB local temporal
                temp_db = self._crear_db_local()
                
                # Subir al servidor
                if temp_db:
                    self.gestor_ssh.subir_archivo(temp_db, self.ruta_db_remota)
                    logger.info("✅ Base de datos creada en servidor remoto")
                    
                    # Limpiar archivo temporal
                    if os.path.exists(temp_db):
                        os.remove(temp_db)
            else:
                logger.info("✅ Base de datos remota ya existe")
            
            self.gestor_ssh.desconectar()
            return True
            
        except Exception as e:
            logger.error(f"❌ Error inicializando DB: {e}")
            self.gestor_ssh.desconectar()
            return False
    
    def _crear_db_local(self):
        """Crear base de datos local con estructura inicial"""
        try:
            # Crear archivo temporal
            temp_dir = tempfile.gettempdir()
            temp_db_path = os.path.join(temp_dir, f"aspirantes_inicial_{int(time.time())}.db")
            
            # Conectar y crear tablas
            conn = sqlite3.connect(temp_db_path)
            cursor = conn.cursor()
            
            # Tabla de inscritos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS inscritos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT NOT NULL,
                    telefono TEXT,
                    programa_interes TEXT NOT NULL,
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
            
            # Tabla de usuarios (para login de inscritos)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    rol TEXT NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT,
                    matricula TEXT UNIQUE,
                    activo INTEGER DEFAULT 1,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Crear índices
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_inscritos_matricula ON inscritos(matricula)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_usuarios_usuario ON usuarios(usuario)')
            
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
            if not self.gestor_ssh.conectar():
                return None
            
            # Crear archivo temporal local
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_db_path = os.path.join(temp_dir, f"aspirantes_temp_{timestamp}.db")
            
            # Descargar base de datos remota
            if self.gestor_ssh.archivo_existe(self.ruta_db_remota):
                self.gestor_ssh.descargar_archivo(self.ruta_db_remota, temp_db_path)
                
                # Verificar que se descargó correctamente
                if os.path.exists(temp_db_path) and os.path.getsize(temp_db_path) > 0:
                    self.db_local_temp = temp_db_path
                    logger.info(f"✅ Base de datos descargada: {temp_db_path}")
                    self.gestor_ssh.desconectar()
                    return temp_db_path
                else:
                    logger.error("❌ Base de datos descargada vacía o corrupta")
                    # Crear nueva
                    return self._crear_db_local()
            else:
                logger.warning("⚠️ Base de datos remota no encontrada, creando nueva")
                self.gestor_ssh.desconectar()
                return self._crear_db_local()
                
        except Exception as e:
            logger.error(f"❌ Error obteniendo DB local: {e}")
            self.gestor_ssh.desconectar()
            return None
    
    def sincronizar_con_remoto(self):
        """Subir base de datos local al servidor remoto"""
        try:
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                logger.error("❌ No hay base de datos local para sincronizar")
                return False
            
            if not self.gestor_ssh.conectar():
                return False
            
            # Crear backup de la versión anterior
            if self.gestor_ssh.archivo_existe(self.ruta_db_remota):
                backup_path = f"{self.ruta_db_remota}.backup_{int(time.time())}"
                self.gestor_ssh.ejecutar_comando(f"cp {self.ruta_db_remota} {backup_path}")
                logger.info(f"✅ Backup creado: {backup_path}")
            
            # Subir nueva versión
            if self.gestor_ssh.subir_archivo(self.db_local_temp, self.ruta_db_remota):
                logger.info("✅ Base de datos sincronizada con servidor remoto")
                self.gestor_ssh.desconectar()
                return True
            else:
                logger.error("❌ Error subiendo base de datos")
                self.gestor_ssh.desconectar()
                return False
                
        except Exception as e:
            logger.error(f"❌ Error sincronizando: {e}")
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
                self.sincronizar_con_remoto()
                
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
            if not self.gestor_ssh.conectar():
                return False
            
            # Guardar archivo temporalmente localmente
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, nombre_archivo)
            
            with open(temp_path, 'wb') as f:
                f.write(archivo_bytes)
            
            # Ruta completa en servidor
            ruta_remota = os.path.join(self.ruta_uploads_remota, nombre_archivo)
            
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
            self.gestor_ssh.desconectar()
            return False

# =============================================================================
# SISTEMA DE CORREOS
# =============================================================================

class SistemaCorreos:
    """Sistema de envío de correos"""
    
    def __init__(self):
        try:
            self.smtp_server = st.secrets["smtp_server"]
            self.smtp_port = int(st.secrets["smtp_port"])
            self.email_user = st.secrets["email_user"]
            self.email_password = st.secrets["email_password"]
            self.correos_habilitados = True
            logger.info("✅ Sistema de correos configurado")
        except:
            self.correos_habilitados = False
            logger.warning("⚠️ Sistema de correos no configurado")
    
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
# SISTEMA PRINCIPAL DE INSCRITOS
# =============================================================================

class SistemaInscritos:
    """Sistema principal de gestión de inscritos"""
    
    def __init__(self):
        self.base_datos = BaseDatosRemota()
        self.sistema_correos = SistemaCorreos()
        self.validador = ValidadorDatos()
        logger.info("🚀 Sistema de inscritos inicializado")
    
    def generar_matricula(self):
        """Generar matrícula única"""
        while True:
            fecha = datetime.now().strftime('%y%m%d')
            random_num = ''.join(random.choices(string.digits, k=4))
            matricula = f"INS{fecha}{random_num}"
            
            # Verificar que no exista
            if not self.base_datos.obtener_inscrito_por_matricula(matricula):
                return matricula
    
    def generar_folio(self):
        """Generar folio único"""
        fecha = datetime.now().strftime('%y%m%d')
        random_num = ''.join(random.choices(string.digits, k=4))
        return f"FOL{fecha}{random_num}"
    
    def guardar_documentos(self, archivos, matricula, nombre_completo):
        """Guardar documentos en servidor remoto"""
        nombres_guardados = []
        
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
    
    def obtener_estadisticas(self):
        """Obtener estadísticas del sistema"""
        try:
            total_inscritos = self.base_datos.obtener_total_inscritos()
            
            # Obtener distribución por programa
            inscritos = self.base_datos.obtener_inscritos()
            programas = {}
            for inscrito in inscritos:
                programa = inscrito['programa_interes']
                programas[programa] = programas.get(programa, 0) + 1
            
            return {
                'total_inscritos': total_inscritos,
                'distribucion_programas': programas
            }
        except Exception as e:
            logger.error(f"❌ Error obteniendo estadísticas: {e}")
            return {'total_inscritos': 0, 'distribucion_programas': {}}

# =============================================================================
# INTERFAZ DE USUARIO - FORMULARIO DE INSCRIPCIÓN
# =============================================================================

def mostrar_formulario_inscripcion():
    """Mostrar formulario de inscripción"""
    
    # Inicializar sistema si no existe
    if 'sistema_inscritos' not in st.session_state:
        st.session_state.sistema_inscritos = SistemaInscritos()
    
    sistema = st.session_state.sistema_inscritos
    
    st.title("📝 Formulario de Pre-Inscripción")
    
    # Mostrar estado del sistema en sidebar
    with st.sidebar:
        st.header("🔧 Estado del Sistema")
        
        # Estadísticas
        stats = sistema.obtener_estadisticas()
        st.metric("Total Inscritos", stats['total_inscritos'])
        
        # Distribución por programa
        if stats['distribucion_programas']:
            st.write("**Distribución por programa:**")
            for programa, cantidad in stats['distribucion_programas'].items():
                st.caption(f"{programa}: {cantidad}")
        
        st.divider()
        
        # Verificación de conexión
        if st.button("🔄 Verificar Conexión"):
            with st.spinner("Verificando..."):
                if sistema.base_datos.gestor_ssh.conectar():
                    st.success("✅ Conectado al servidor SSH")
                    sistema.base_datos.gestor_ssh.desconectar()
                else:
                    st.error("❌ Error de conexión SSH")
        
        # Verificación de correos
        if st.button("📧 Verificar Correos"):
            with st.spinner("Verificando..."):
                if sistema.sistema_correos.correos_habilitados:
                    st.success("✅ Sistema de correos configurado")
                else:
                    st.warning("⚠️ Sistema de correos no configurado")
    
    # Formulario principal
    with st.form("formulario_inscripcion", clear_on_submit=True):
        st.subheader("👤 Información Personal")
        
        col1, col2 = st.columns(2)
        
        with col1:
            nombre_completo = st.text_input(
                "Nombre Completo *",
                placeholder="Juan Pérez López",
                help="Ingresa tu nombre completo"
            )
            
            email = st.text_input(
                "Correo Electrónico *",
                placeholder="ejemplo@email.com",
                help="Usaremos este correo para contactarte"
            )
            
            telefono = st.text_input(
                "Teléfono *",
                placeholder="5512345678",
                help="Ingresa tu número de teléfono"
            )
        
        with col2:
            # Fecha de nacimiento
            fecha_nacimiento = st.date_input(
                "Fecha de Nacimiento",
                min_value=date(1960, 1, 1),
                max_value=date.today(),
                value=date(1990, 1, 1)
            )
            
            # Cómo se enteró
            como_se_entero = st.selectbox(
                "¿Cómo se enteró de nosotros? *",
                [
                    "Redes Sociales",
                    "Google / Buscador",
                    "Recomendación",
                    "Publicidad",
                    "Evento",
                    "Otro"
                ]
            )
        
        # Programa de interés
        st.subheader("🎓 Programa de Interés")
        
        programas_opciones = [
            "Especialidad en Enfermería Cardiovascular",
            "Licenciatura en Enfermería",
            "Diplomado de Cardiología Básica",
            "Maestría en Ciencias Cardiológicas"
        ]
        
        programa_interes = st.selectbox(
            "Selecciona el programa *",
            programas_opciones
        )
        
        # Documentos requeridos
        st.subheader("📎 Documentos Requeridos")
        st.info("Por favor, sube los siguientes documentos en formato PDF:")
        
        col_doc1, col_doc2 = st.columns(2)
        
        with col_doc1:
            acta_nacimiento = st.file_uploader(
                "Acta de Nacimiento *",
                type=['pdf'],
                key="acta"
            )
            
            curp = st.file_uploader(
                "CURP *",
                type=['pdf'],
                key="curp"
            )
        
        with col_doc2:
            certificado = st.file_uploader(
                "Último Grado de Estudios *",
                type=['pdf'],
                key="certificado"
            )
            
            foto = st.file_uploader(
                "Fotografía (Opcional)",
                type=['pdf', 'jpg', 'jpeg', 'png'],
                key="foto"
            )
        
        # Términos y condiciones
        st.divider()
        acepta_terminos = st.checkbox(
            "✅ Acepto los términos y condiciones del proceso de admisión *"
        )
        
        # Botón de envío
        col_submit1, col_submit2, col_submit3 = st.columns([1, 2, 1])
        with col_submit2:
            submitted = st.form_submit_button(
                "🚀 Enviar Solicitud",
                use_container_width=True,
                type="primary"
            )
        
        if submitted:
            # Validar campos obligatorios
            if not all([nombre_completo, email, telefono, programa_interes, acepta_terminos, como_se_entero]):
                st.error("❌ Por favor completa todos los campos obligatorios (*)")
                return
            
            # Validar documentos obligatorios
            if not all([acta_nacimiento, curp, certificado]):
                st.error("❌ Los documentos marcados con * son obligatorios")
                return
            
            # Preparar datos
            datos_formulario = {
                'nombre_completo': nombre_completo,
                'email': email,
                'telefono': telefono,
                'programa_interes': programa_interes,
                'fecha_nacimiento': fecha_nacimiento,
                'como_se_entero': como_se_entero
            }
            
            archivos = {
                'acta_nacimiento': acta_nacimiento,
                'curp': curp,
                'certificado': certificado,
                'foto': foto
            }
            
            # Mostrar progreso
            with st.spinner("Procesando tu solicitud..."):
                resultado = sistema.registrar_inscripcion(datos_formulario, archivos)
                
                if resultado['success']:
                    # Mostrar éxito
                    st.success("🎉 ¡Solicitud enviada exitosamente!")
                    
                    # Mostrar información
                    col_info1, col_info2 = st.columns(2)
                    
                    with col_info1:
                        st.info(f"**📋 Folio:** {resultado['folio']}")
                        st.info(f"**🎓 Matrícula:** {resultado['matricula']}")
                        st.info(f"**👤 Nombre:** {resultado['nombre']}")
                    
                    with col_info2:
                        st.info(f"**📧 Email:** {resultado['email']}")
                        st.info(f"**🎯 Programa:** {resultado['programa']}")
                        st.info(f"**📎 Documentos:** {resultado['documentos']}")
                    
                    # Estado del correo
                    if resultado['correo_enviado']:
                        st.success("✅ Correo de confirmación enviado")
                    else:
                        st.warning(f"⚠️ {resultado['mensaje_correo']}")
                    
                    # Botón para nueva inscripción
                    if st.button("📝 Realizar otra inscripción"):
                        st.rerun()
                        
                else:
                    st.error(f"❌ Error: {resultado.get('error', 'Error desconocido')}")

# =============================================================================
# PÁGINA PRINCIPAL DEL SITIO WEB
# =============================================================================

def mostrar_pagina_principal():
    """Mostrar página principal del sitio web"""
    
    # Header
    st.markdown("""
    <style>
    .main-header {
        font-size: 3rem;
        color: #2E86AB;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #A23B72;
        text-align: center;
        margin-bottom: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<h1 class="main-header">🏥 Escuela de Enfermería</h1>', unsafe_allow_html=True)
    st.markdown('<h2 class="sub-header">Formando Líderes en Salud Cardiovascular</h2>', unsafe_allow_html=True)
    
    # Sección hero
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ## 🎓 Excelencia en Educación Cardiovascular
        
        **Programas académicos de vanguardia:**
        - 👨‍⚕️ **Claustro docente** especializado
        - 🏥 **Vinculación hospitalaria** con instituciones líderes
        - 🔬 **Investigación** aplicada a la práctica clínica
        - 💼 **Bolsa de trabajo** exclusiva para egresados
        
        *40 años formando profesionales de excelencia*
        """)
        
        if st.button("📝 ¡Inscríbete Ahora!", type="primary", use_container_width=True):
            st.session_state.pagina_actual = "formulario"
            st.rerun()
    
    with col2:
        st.info("**🏛️ Instalaciones:**")
        st.write("""
        - Laboratorios especializados
        - Simuladores de alta fidelidad
        - Biblioteca especializada
        - Aulas tecnológicas
        """)
    
    # Programas académicos
    st.divider()
    st.header("📚 Programas Académicos")
    
    programas = [
        {
            "nombre": "Especialidad en Enfermería Cardiovascular",
            "duracion": "2 años",
            "modalidad": "Presencial",
            "descripcion": "Formación especializada en cuidados cardiovasculares."
        },
        {
            "nombre": "Licenciatura en Enfermería",
            "duracion": "4 años",
            "modalidad": "Presencial",
            "descripcion": "Formación integral con enfoque cardiológico."
        },
        {
            "nombre": "Diplomado de Cardiología Básica",
            "duracion": "6 meses",
            "modalidad": "Híbrida",
            "descripcion": "Actualización para profesionales de la salud."
        }
    ]
    
    cols = st.columns(3)
    for i, programa in enumerate(programas):
        with cols[i]:
            with st.container():
                st.markdown(f"### {programa['nombre']}")
                st.markdown(f"**Duración:** {programa['duracion']}")
                st.markdown(f"**Modalidad:** {programa['modalidad']}")
                st.markdown(programa['descripcion'])
                
                if st.button(f"ℹ️ Más información", key=f"info_{i}"):
                    st.session_state.programa_seleccionado = programa['nombre']
                    st.session_state.pagina_actual = "formulario"
                    st.rerun()
    
    # Testimonios
    st.divider()
    st.header("🌟 Testimonios")
    
    testimonios = [
        {
            "nombre": "Dra. Ana Martínez",
            "programa": "Especialidad en Enfermería Cardiovascular",
            "testimonio": "La especialidad me dio herramientas para trabajar en la unidad de cardiología."
        },
        {
            "nombre": "Lic. Carlos Rodríguez",
            "programa": "Licenciatura en Enfermería",
            "testimonio": "La formación con enfoque cardiológico me diferencié en el mercado laboral."
        }
    ]
    
    cols_test = st.columns(2)
    for i, testimonio in enumerate(testimonios):
        with cols_test[i]:
            with st.container():
                st.markdown(f"**{testimonio['nombre']}**")
                st.markdown(f"*{testimonio['programa']}*")
                st.markdown(f"\"{testimonio['testimonio']}\"")
    
    # Contacto
    st.divider()
    st.header("📞 Contacto")
    
    col_cont1, col_cont2, col_cont3 = st.columns(3)
    
    with col_cont1:
        st.markdown("**🏛️ Dirección:**")
        st.write("Av. Insurgentes Sur 1234")
        st.write("Ciudad de México")
    
    with col_cont2:
        st.markdown("**📱 Contacto:**")
        st.write("Tel: (55) 1234-5678")
        st.write("Email: admisiones@escuelaenfermeria.edu.mx")
    
    with col_cont3:
        st.markdown("**🕒 Horarios:**")
        st.write("Lunes a Viernes: 9:00 - 18:00")
        st.write("Sábados: 9:00 - 13:00")
    
    # Footer
    st.divider()
    st.markdown("<center>© 2024 Escuela de Enfermería. Todos los derechos reservados.</center>", unsafe_allow_html=True)

# =============================================================================
# APLICACIÓN PRINCIPAL
# =============================================================================

def main():
    """Función principal de la aplicación"""
    
    # Inicializar estado de sesión
    if 'pagina_actual' not in st.session_state:
        st.session_state.pagina_actual = "principal"
    
    if 'sistema_inscritos' not in st.session_state:
        # Inicializar con spinner para que el usuario vea que está cargando
        with st.spinner("🚀 Inicializando sistema..."):
            st.session_state.sistema_inscritos = SistemaInscritos()
    
    # Navegación
    if st.session_state.pagina_actual == "principal":
        mostrar_pagina_principal()
    else:
        # Botón para volver al inicio
        if st.button("← Volver al inicio"):
            st.session_state.pagina_actual = "principal"
            st.rerun()
        
        mostrar_formulario_inscripcion()

# =============================================================================
# EJECUCIÓN
# =============================================================================

if __name__ == "__main__":
    # Información del sistema
    st.info("""
    🏥 **SISTEMA DE PRE-INSCRIPCIÓN - CONEXIÓN SSH REMOTA**
    
    **Características:**
    ✅ Conexión SSH a servidor remoto
    ✅ Base de datos SQLite centralizada
    ✅ Subida de documentos al servidor
    ✅ Envío de correos de confirmación
    ✅ Generación automática de matrículas
    
    **Estado:** Conectando al servidor SSH...
    """)
    
    try:
        main()
    except Exception as e:
        st.error(f"❌ Error en la aplicación: {str(e)}")
        logger.error(f"Error crítico: {e}")
        
        # Botón para reiniciar
        if st.button("🔄 Reiniciar aplicación"):
            # Limpiar estado
            keys = list(st.session_state.keys())
            for key in keys:
                del st.session_state[key]
            st.rerun()
