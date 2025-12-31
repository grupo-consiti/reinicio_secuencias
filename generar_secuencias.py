#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script: Generador de Secuencias de Documentos Fiscales
Proposito: Crear las 7 secuencias de documentos para cada caja registradora por año
Compatible: Odoo 13, 17, 18

INSTALACION:
    pip install psycopg2-binary python-dotenv

USO:
    # Diagnostico de conexiones disponibles
    python generar_secuencias.py --diagnose

    # Listar bases disponibles (auto-detecta conexion)
    python generar_secuencias.py --list

    # Ejecutar con auto-deteccion de conexion
    python generar_secuencias.py --year 2026 --auto

    # Todas las bases de datos
    python generar_secuencias.py --year 2026

    # Base de datos especifica
    python generar_secuencias.py --year 2026 --database AMBIENTE2

    # Excluyendo bases
    python generar_secuencias.py --year 2026 --exclude test,demo

    # Especificar host y puerto manualmente
    python generar_secuencias.py --year 2026 --host localhost --port 5434
    python generar_secuencias.py --year 2026 --host databaseodoo --port 5432

    # Modo prueba (dry-run) - analiza sin ejecutar
    python generar_secuencias.py --year 2026 --dry-run
    python generar_secuencias.py --year 2026 --database AMBIENTE2 --dry-run

    # Ver ayuda
    python generar_secuencias.py --help
"""

import argparse
import sys
import os
from datetime import datetime

# =============================================================================
# IMPORTS
# =============================================================================

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2-binary no esta instalado")
    print("   Ejecuta: pip install psycopg2-binary")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()  # Cargar variables de .env si existe
except ImportError:
    pass  # python-dotenv es opcional

# =============================================================================
# CONFIGURACION POR DEFECTO
# =============================================================================

# PostgreSQL - Lee de variables de entorno o usa valores por defecto
# Detectar si estamos dentro de Docker o fuera
def detectar_entorno():
    """Detecta si estamos dentro de un contenedor Docker"""
    # Verificar si existe /.dockerenv (indicador de Docker)
    if os.path.exists('/.dockerenv'):
        return True
    # Verificar si estamos en Linux con cgroup de Docker
    try:
        with open('/proc/1/cgroup', 'r') as f:
            return 'docker' in f.read()
    except:
        pass
    return False

ES_DOCKER = detectar_entorno()

# Puertos comunes de PostgreSQL para escanear
PUERTOS_POSTGRESQL = [5432, 5433, 5434, 5435]

# Valores por defecto segun entorno
if ES_DOCKER:
    DEFAULT_PG_HOST = os.getenv('ODOO_PG_HOST', 'databaseodoo')
    DEFAULT_PG_PORT = int(os.getenv('ODOO_PG_PORT', 5432))
else:
    DEFAULT_PG_HOST = os.getenv('ODOO_PG_HOST', 'localhost')
    DEFAULT_PG_PORT = int(os.getenv('ODOO_PG_PORT', 5434))

DEFAULT_PG_USER = os.getenv('ODOO_PG_USER', 'odoo')
DEFAULT_PG_PASSWORD = os.getenv('ODOO_PG_PASSWORD', 'odoo')

BASES_SISTEMA = ['postgres', 'template0', 'template1']

# =============================================================================
# CONFIGURACION DE SECUENCIAS
# =============================================================================

# Configuracion usando CODIGO del documento (name en felsv_parameter_acc_tipo_documento)
# El script buscara el ID real en cada base de datos
SECUENCIAS_CONFIG = [
    {'nombre_base': 'fcf', 'tipo_documento_code': '01', 'tipo_nombre': '01 - Factura'},
    {'nombre_base': 'ccf', 'tipo_documento_code': '03', 'tipo_nombre': '03 - CCF'},
    {'nombre_base': 'nr', 'tipo_documento_code': '04', 'tipo_nombre': '04 - Nota Remision'},
    {'nombre_base': 'nc', 'tipo_documento_code': '05', 'tipo_nombre': '05 - Nota Credito'},
    {'nombre_base': 'nota_debito', 'tipo_documento_code': '06', 'tipo_nombre': '06 - Nota Debito'},
    {'nombre_base': 'retencion', 'tipo_documento_code': '07', 'tipo_nombre': '07 - Retencion'},
    {'nombre_base': 'exportacion', 'tipo_documento_code': '11', 'tipo_nombre': '11 - Exportacion'},
    {'nombre_base': 'sujeto', 'tipo_documento_code': '14', 'tipo_nombre': '14 - Sujeto Excluido'},
    {'nombre_base': 'donacion', 'tipo_documento_code': '15', 'tipo_nombre': '15 - Donacion'},
]


# =============================================================================
# CLASE PRINCIPAL
# =============================================================================

class GeneradorSecuencias:
    def __init__(self, year=None, database=None, exclude=None, host=None, port=None, dry_run=False):
        self.year = year
        self.database = database
        self.exclude = exclude.split(',') if exclude else []
        self.resultados = {}
        self.fecha_inicio = f'{year}-01-01' if year else None
        self.fecha_fin = f'{year}-12-31' if year else None
        self.dry_run = dry_run

        # Configuracion de conexion (prioridad: parametro > env > default)
        self.pg_host = host or DEFAULT_PG_HOST
        self.pg_port = port or DEFAULT_PG_PORT
        self.pg_user = DEFAULT_PG_USER
        self.pg_password = DEFAULT_PG_PASSWORD

    def test_conexion(self):
        """Prueba la conexion a PostgreSQL"""
        try:
            conn = psycopg2.connect(
                host=self.pg_host,
                port=self.pg_port,
                user=self.pg_user,
                password=self.pg_password,
                database='postgres',
                connect_timeout=5
            )
            conn.close()
            return True, None
        except Exception as e:
            return False, str(e)

    def diagnostico_conexion(self):
        """Muestra diagnostico de conexion escaneando puertos"""
        print("")
        print("=" * 70)
        print("        DIAGNOSTICO DE CONEXION A POSTGRESQL")
        print("=" * 70)
        print("")
        print(f"Entorno: {'Docker' if ES_DOCKER else 'Windows/Local'}")
        print(f"Usuario: {self.pg_user}")
        print("")
        print("Escaneando puertos...")
        print("-" * 70)

        conexiones_ok = []

        # Si estamos en Docker, probar databaseodoo primero
        if ES_DOCKER:
            try:
                conn = psycopg2.connect(
                    host='databaseodoo', port=5432,
                    user=self.pg_user, password=self.pg_password,
                    database='postgres', connect_timeout=2
                )
                cur = conn.cursor()
                cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres')")
                bases = [r[0] for r in cur.fetchall()]
                cur.close()
                conn.close()
                print(f"  [OK] databaseodoo:5432 - {len(bases)} bases")
                conexiones_ok.append(('databaseodoo', 5432, bases))
            except:
                print(f"  [X]  databaseodoo:5432")

        # Escanear puertos localhost
        for puerto in PUERTOS_POSTGRESQL:
            try:
                conn = psycopg2.connect(
                    host='localhost', port=puerto,
                    user=self.pg_user, password=self.pg_password,
                    database='postgres', connect_timeout=1
                )
                cur = conn.cursor()
                cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres')")
                bases = [r[0] for r in cur.fetchall()]
                cur.close()
                conn.close()
                print(f"  [OK] localhost:{puerto} - {len(bases)} bases: {', '.join(bases[:3])}{'...' if len(bases)>3 else ''}")
                conexiones_ok.append(('localhost', puerto, bases))
            except:
                pass  # Puerto no disponible

        print("-" * 70)

        if conexiones_ok:
            print(f"\n{len(conexiones_ok)} conexion(es) encontrada(s):\n")
            for host, puerto, bases in conexiones_ok:
                print(f"  python generar_secuencias.py --year 2026 --host {host} --port {puerto}")
        else:
            print("\nNo se encontraron conexiones. Verifica Docker.")

        print("=" * 70)

    def conectar_postgres(self, database='postgres'):
        """Conecta a PostgreSQL"""
        return psycopg2.connect(
            host=self.pg_host,
            port=self.pg_port,
            user=self.pg_user,
            password=self.pg_password,
            database=database
        )

    def obtener_bases_datos(self):
        """Obtiene lista de bases de datos a procesar"""
        conn = self.conectar_postgres('postgres')
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname")
        todas_bases = [row[0] for row in cur.fetchall()]

        cur.close()
        conn.close()

        # Filtrar bases del sistema
        bases = [db for db in todas_bases if db not in BASES_SISTEMA]

        # Si se especifico una base especifica
        if self.database:
            if self.database in bases:
                return [self.database]
            else:
                print(f"ERROR: La base '{self.database}' no existe")
                print(f"Bases disponibles: {', '.join(bases)}")
                return []

        # Aplicar exclusiones
        if self.exclude:
            bases = [db for db in bases if db not in self.exclude]

        return bases

    def listar_bases(self):
        """Lista las bases de datos disponibles"""
        print("")
        print("=" * 60)
        print("        BASES DE DATOS DISPONIBLES")
        print(f"        Conexion: {self.pg_host}:{self.pg_port}")
        print("=" * 60)
        print("")

        # Probar conexion
        ok, error = self.test_conexion()
        if not ok:
            print(f"ERROR: No se pudo conectar a PostgreSQL")
            print(f"       {error}")
            print("")
            print("Verifica:")
            print(f"  - Host: {self.pg_host}")
            print(f"  - Puerto: {self.pg_port}")
            print(f"  - Usuario: {self.pg_user}")
            print("  - Que Docker este corriendo")
            return

        try:
            bases = self.obtener_bases_datos()
            print(f"Total: {len(bases)} bases de datos")
            print("-" * 60)
            for i, db in enumerate(bases, 1):
                print(f"  {i}. {db}")
            print("-" * 60)
            print("")
            print("Uso:")
            print(f"  python generar_secuencias.py --year 2026 -d {bases[0] if bases else 'NOMBRE_BASE'}")
            print("")
        except Exception as e:
            print(f"ERROR: {e}")

    def verificar_tabla_existe(self, conn, tabla):
        """Verifica si una tabla existe en la base de datos"""
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (tabla,))
        existe = cur.fetchone()[0]
        cur.close()
        return existe

    def obtener_nit_compania(self, conn):
        """Obtiene el NIT de la compania"""
        cur = conn.cursor()
        cur.execute("SELECT nit FROM res_company WHERE nit IS NOT NULL LIMIT 1")
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None

    def obtener_tipo_documento_id(self, conn, codigo):
        """Busca el ID del tipo de documento por su codigo (ej: '01', '15')"""
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM felsv_parameter_acc_tipo_documento WHERE name = %s LIMIT 1",
            (codigo,)
        )
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None

    def obtener_todos_tipos_documento(self, conn):
        """Obtiene un diccionario de codigo -> id para todos los tipos de documento"""
        cur = conn.cursor()
        cur.execute("SELECT name, id FROM felsv_parameter_acc_tipo_documento")
        rows = cur.fetchall()
        cur.close()
        return {row[0]: row[1] for row in rows}

    def obtener_cajas_registradoras(self, conn):
        """Obtiene las cajas registradoras con su tienda asociada"""
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                cr.id as cash_register_id,
                cr.name as caja_nombre,
                cr.store_id,
                s.name as tienda_nombre
            FROM cash_register cr
            JOIN store s ON cr.store_id = s.id
            ORDER BY cr.id
        """)
        cajas = cur.fetchall()
        cur.close()
        return cajas

    def verificar_secuencia_existe(self, conn, nombre_secuencia):
        """Verifica si ya existe una secuencia con ese nombre"""
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM document_sequence WHERE sequence_name = %s",
            (nombre_secuencia,)
        )
        row = cur.fetchone()
        cur.close()
        return row is not None

    def validar_secuencia_existente(self, conn, nombre_secuencia, datos_esperados):
        """
        Valida que una secuencia existente tenga la configuracion correcta.
        Retorna: (es_valida, detalles)
        """
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                id,
                nit,
                validity_start,
                validity_end,
                sequence_name,
                tipo_documento_id,
                store_id,
                cash_register_id
            FROM document_sequence
            WHERE sequence_name = %s
        """, (nombre_secuencia,))
        row = cur.fetchone()
        cur.close()

        if not row:
            return False, "No encontrada"

        errores = []

        # Validar NIT
        if row['nit'] != datos_esperados['nit']:
            errores.append(f"NIT: {row['nit']} (esperado: {datos_esperados['nit']})")

        # Validar fechas (convertir a string para comparar)
        fecha_inicio_db = str(row['validity_start']) if row['validity_start'] else None
        fecha_fin_db = str(row['validity_end']) if row['validity_end'] else None

        if fecha_inicio_db != datos_esperados['validity_start']:
            errores.append(f"Inicio: {fecha_inicio_db} (esperado: {datos_esperados['validity_start']})")

        if fecha_fin_db != datos_esperados['validity_end']:
            errores.append(f"Fin: {fecha_fin_db} (esperado: {datos_esperados['validity_end']})")

        # Validar tipo documento
        if row['tipo_documento_id'] != datos_esperados['tipo_documento_id']:
            errores.append(f"Tipo Doc: {row['tipo_documento_id']} (esperado: {datos_esperados['tipo_documento_id']})")

        # Validar store_id
        if row['store_id'] != datos_esperados['store_id']:
            errores.append(f"Store: {row['store_id']} (esperado: {datos_esperados['store_id']})")

        # Validar cash_register_id
        if row['cash_register_id'] != datos_esperados['cash_register_id']:
            errores.append(f"Caja: {row['cash_register_id']} (esperado: {datos_esperados['cash_register_id']})")

        if errores:
            return False, "; ".join(errores)

        return True, "Configuracion correcta"

    def crear_secuencia(self, conn, datos):
        """Crea una secuencia de documento"""
        cur = conn.cursor()

        try:
            # 1. Insertar en la tabla document_sequence
            cur.execute("""
                INSERT INTO document_sequence (
                    nit,
                    validity_start,
                    validity_end,
                    sequence_name,
                    initial_number,
                    maximum_number,
                    tipo_documento_id,
                    store_id,
                    cash_register_id,
                    create_uid,
                    create_date,
                    write_uid,
                    write_date
                ) VALUES (
                    %(nit)s,
                    %(validity_start)s,
                    %(validity_end)s,
                    %(sequence_name)s,
                    %(initial_number)s,
                    %(maximum_number)s,
                    %(tipo_documento_id)s,
                    %(store_id)s,
                    %(cash_register_id)s,
                    1,
                    NOW(),
                    1,
                    NOW()
                )
            """, datos)

            # 2. Crear la secuencia en PostgreSQL
            cur.execute(
                f"CREATE SEQUENCE IF NOT EXISTS {datos['sequence_name']} START WITH 1"
            )

            conn.commit()
            cur.close()
            return {'exito': True, 'error': None}

        except Exception as e:
            conn.rollback()
            cur.close()
            return {'exito': False, 'error': str(e)}

    def generar_nombre_secuencia(self, nombre_base, indice_caja, total_cajas):
        """Genera el nombre de la secuencia segun el formato"""
        if total_cajas > 1:
            # Multi-sucursal: s01_fcf_2026
            prefijo = f"s{str(indice_caja).zfill(2)}_"
            return f"{prefijo}{nombre_base}_{self.year}"
        else:
            # Una sola caja: fcf_2026
            return f"{nombre_base}_{self.year}"

    def procesar_base(self, db_name):
        """Procesa una base de datos individual"""
        resultado = {
            'nit': None,
            'cajas': [],
            'total_secuencias': 0,
            'secuencias_creadas': 0,
            'secuencias_existentes': 0,
            'secuencias_validadas_ok': 0,
            'secuencias_con_error_config': 0,
            'secuencias_omitidas': 0,
            'secuencias_con_error_creacion': 0,
            'observaciones_omitidas': [],
            'observaciones_error_creacion': [],
            'errores': [],
            'estado': 'PENDIENTE',
            'multi_sucursal': False
        }

        try:
            conn = self.conectar_postgres(db_name)

            # Verificar que existe la tabla document_sequence
            if not self.verificar_tabla_existe(conn, 'document_sequence'):
                resultado['estado'] = 'OMITIDA'
                resultado['errores'].append('Tabla document_sequence no existe')
                conn.close()
                return resultado

            # Verificar que existe la tabla cash_register
            if not self.verificar_tabla_existe(conn, 'cash_register'):
                resultado['estado'] = 'OMITIDA'
                resultado['errores'].append('Tabla cash_register no existe')
                conn.close()
                return resultado

            # Obtener NIT de la compania
            nit = self.obtener_nit_compania(conn)
            if not nit:
                resultado['estado'] = 'ERROR'
                resultado['errores'].append('No se encontro NIT de compania')
                conn.close()
                return resultado

            resultado['nit'] = nit

            # Obtener cajas registradoras
            cajas = self.obtener_cajas_registradoras(conn)
            if not cajas:
                resultado['estado'] = 'ERROR'
                resultado['errores'].append('No se encontraron cajas registradoras')
                conn.close()
                return resultado

            total_cajas = len(cajas)
            resultado['multi_sucursal'] = total_cajas > 1

            # Obtener mapeo de codigos a IDs de tipos de documento
            tipos_documento_map = self.obtener_todos_tipos_documento(conn)
            if not tipos_documento_map:
                resultado['estado'] = 'ERROR'
                resultado['errores'].append('No se encontraron tipos de documento en felsv_parameter_acc_tipo_documento')
                conn.close()
                return resultado

            # Procesar cada caja
            for indice, caja in enumerate(cajas, 1):
                caja_resultado = {
                    'nombre': caja['caja_nombre'],
                    'tienda': caja['tienda_nombre'],
                    'secuencias': []
                }

                # Crear las secuencias para esta caja
                for sec_config in SECUENCIAS_CONFIG:
                    # Buscar el ID del tipo de documento por codigo
                    tipo_doc_code = sec_config['tipo_documento_code']
                    tipo_doc_id = tipos_documento_map.get(tipo_doc_code)

                    # Si no existe el tipo de documento, saltar
                    if tipo_doc_id is None:
                        nombre_seq_omitido = f"{sec_config['nombre_base']}_{self.year}"
                        detalle_omision = f"Tipo documento '{tipo_doc_code}' no existe en BD"
                        sec_resultado = {
                            'nombre': nombre_seq_omitido,
                            'tipo': sec_config['tipo_nombre'],
                            'estado': 'OMITIDO',
                            'detalle': detalle_omision
                        }
                        caja_resultado['secuencias'].append(sec_resultado)
                        resultado['secuencias_omitidas'] += 1
                        resultado['observaciones_omitidas'].append(
                            f"{nombre_seq_omitido}: {detalle_omision}"
                        )
                        continue

                    nombre_seq = self.generar_nombre_secuencia(
                        sec_config['nombre_base'],
                        indice,
                        total_cajas
                    )

                    sec_resultado = {
                        'nombre': nombre_seq,
                        'tipo': sec_config['tipo_nombre'],
                        'estado': 'PENDIENTE',
                        'detalle': ''
                    }

                    # Datos esperados para validacion (usando el ID encontrado)
                    datos_esperados = {
                        'nit': nit,
                        'validity_start': self.fecha_inicio,
                        'validity_end': self.fecha_fin,
                        'tipo_documento_id': tipo_doc_id,
                        'store_id': caja['store_id'],
                        'cash_register_id': caja['cash_register_id'],
                    }

                    # Verificar si ya existe
                    if self.verificar_secuencia_existe(conn, nombre_seq):
                        # Validar que la configuracion sea correcta
                        es_valida, detalle = self.validar_secuencia_existente(
                            conn, nombre_seq, datos_esperados
                        )
                        if es_valida:
                            sec_resultado['estado'] = 'VALIDADA OK'
                            sec_resultado['detalle'] = detalle
                            resultado['secuencias_validadas_ok'] += 1
                        else:
                            sec_resultado['estado'] = 'ERROR CONFIG'
                            sec_resultado['detalle'] = detalle
                            resultado['secuencias_con_error_config'] += 1
                            resultado['errores'].append(f"{nombre_seq}: {detalle}")
                        resultado['secuencias_existentes'] += 1
                    else:
                        # Modo dry-run: solo marcar como pendiente
                        if self.dry_run:
                            sec_resultado['estado'] = 'PENDIENTE'
                            sec_resultado['detalle'] = 'Se creara'
                            resultado['secuencias_creadas'] += 1  # Contamos como "a crear"
                        else:
                            # Crear la secuencia
                            datos = {
                                'nit': nit,
                                'validity_start': self.fecha_inicio,
                                'validity_end': self.fecha_fin,
                                'sequence_name': nombre_seq,
                                'initial_number': 1,
                                'maximum_number': 999999999,
                                'tipo_documento_id': tipo_doc_id,
                                'store_id': caja['store_id'],
                                'cash_register_id': caja['cash_register_id'],
                            }

                            res = self.crear_secuencia(conn, datos)

                            if res['exito']:
                                sec_resultado['estado'] = 'OK'
                                resultado['secuencias_creadas'] += 1
                            else:
                                sec_resultado['estado'] = 'ERROR'
                                sec_resultado['detalle'] = res['error']
                                resultado['secuencias_con_error_creacion'] += 1
                                resultado['observaciones_error_creacion'].append(
                                    f"{nombre_seq}: {res['error']}"
                                )
                                resultado['errores'].append(f"{nombre_seq}: {res['error']}")

                    resultado['total_secuencias'] += 1
                    caja_resultado['secuencias'].append(sec_resultado)

                resultado['cajas'].append(caja_resultado)

            conn.close()
            resultado['estado'] = 'COMPLETADO' if not resultado['errores'] else 'COMPLETADO CON ERRORES'

        except Exception as e:
            resultado['estado'] = 'ERROR'
            resultado['errores'].append(str(e))

        return resultado

    def generar_log(self):
        """Genera el log detallado de resultados"""
        linea = "=" * 80
        linea_simple = "-" * 80

        log = []
        log.append(linea)
        if self.dry_run:
            log.append("                    INFORME DE ANALISIS (DRY-RUN)")
            log.append("                    *** NO SE REALIZARON CAMBIOS ***")
        else:
            log.append("                    REPORTE DE CREACION DE SECUENCIAS")
        log.append(f"                    Año: {self.year} | Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log.append(linea)
        log.append("")

        total_bases = 0
        total_exitosas = 0
        total_omitidas = 0
        total_errores = 0
        total_secuencias = 0

        for db_name, resultado in self.resultados.items():
            total_bases += 1

            log.append(linea_simple)
            log.append(f"BASE: {db_name}")
            log.append(linea_simple)

            if resultado['estado'] == 'OMITIDA':
                log.append(f"  ESTADO: OMITIDA")
                log.append(f"  Razon: {', '.join(resultado['errores'])}")
                total_omitidas += 1
                log.append("")
                continue

            if resultado['estado'] == 'ERROR' and not resultado['cajas']:
                log.append(f"  ESTADO: ERROR")
                log.append(f"  Errores: {', '.join(resultado['errores'])}")
                total_errores += 1
                log.append("")
                continue

            total_exitosas += 1
            log.append(f"  NIT Compania: {resultado['nit']}")
            log.append(f"  Cajas Registradoras: {len(resultado['cajas'])}")
            log.append(f"  Multi-sucursal: {'SI' if resultado.get('multi_sucursal') else 'NO'}")
            log.append("")

            for caja in resultado['cajas']:
                log.append(f"  CAJA: {caja['nombre']} (Tienda: {caja['tienda']})")
                log.append("  +-----------------------------+----------------------+--------------+")
                log.append("  | Secuencia                   | Tipo Documento       | Estado       |")
                log.append("  +-----------------------------+----------------------+--------------+")

                for sec in caja['secuencias']:
                    nombre = sec['nombre'][:27].ljust(27)
                    tipo = sec['tipo'][:20].ljust(20)
                    estado = sec['estado'][:12].ljust(12)
                    log.append(f"  | {nombre} | {tipo} | {estado} |")

                log.append("  +-----------------------------+----------------------+--------------+")

                creadas = sum(1 for s in caja['secuencias'] if s['estado'] == 'OK')
                validadas = sum(1 for s in caja['secuencias'] if s['estado'] == 'VALIDADA OK')
                error_config = sum(1 for s in caja['secuencias'] if s['estado'] == 'ERROR CONFIG')
                omitidas = sum(1 for s in caja['secuencias'] if s['estado'] == 'OMITIDO')
                error_creacion = sum(1 for s in caja['secuencias'] if s['estado'] == 'ERROR')
                log.append(f"  Creadas: {creadas} | Validadas: {validadas} | Omitidas: {omitidas} | Errores: {error_config + error_creacion}")

                # Mostrar detalles de problemas
                for sec in caja['secuencias']:
                    if sec['estado'] == 'ERROR CONFIG' and sec.get('detalle'):
                        log.append(f"    [!] {sec['nombre']}: Config incorrecta - {sec['detalle']}")
                    elif sec['estado'] == 'OMITIDO' and sec.get('detalle'):
                        log.append(f"    [-] {sec['nombre']}: {sec['detalle']}")
                    elif sec['estado'] == 'ERROR' and sec.get('detalle'):
                        log.append(f"    [X] {sec['nombre']}: Error creacion - {sec['detalle']}")
                log.append("")

            total_secuencias += resultado['secuencias_creadas']
            sec_omitidas = resultado.get('secuencias_omitidas', 0)
            sec_error_creacion = resultado.get('secuencias_con_error_creacion', 0)
            if self.dry_run:
                log.append(f"  TOTAL BASE: {resultado['secuencias_creadas']} a crear | {resultado['secuencias_validadas_ok']} ya existen OK | {sec_omitidas} omitidas | {resultado['secuencias_con_error_config']} con error config")
            else:
                log.append(f"  TOTAL BASE: {resultado['secuencias_creadas']} creadas | {resultado['secuencias_validadas_ok']} validadas | {sec_omitidas} omitidas | {resultado['secuencias_con_error_config'] + sec_error_creacion} errores")
            log.append(f"  ESTADO: {resultado['estado']}")

            if resultado['errores']:
                log.append(f"  ERRORES:")
                for err in resultado['errores']:
                    log.append(f"    - {err}")

            log.append("")

        # Calcular totales globales
        total_validadas_ok = sum(r.get('secuencias_validadas_ok', 0) for r in self.resultados.values())
        total_error_config = sum(r.get('secuencias_con_error_config', 0) for r in self.resultados.values())
        total_sec_omitidas = sum(r.get('secuencias_omitidas', 0) for r in self.resultados.values())
        total_error_creacion = sum(r.get('secuencias_con_error_creacion', 0) for r in self.resultados.values())

        # Recopilar todas las observaciones
        todas_obs_omitidas = []
        todas_obs_error = []
        for db_name, resultado in self.resultados.items():
            for obs in resultado.get('observaciones_omitidas', []):
                todas_obs_omitidas.append(f"[{db_name}] {obs}")
            for obs in resultado.get('observaciones_error_creacion', []):
                todas_obs_error.append(f"[{db_name}] {obs}")

        # Resumen final
        log.append(linea)
        log.append("                              RESUMEN FINAL")
        log.append(linea)
        log.append(f"  Bases procesadas:       {total_bases}")
        log.append(f"  Bases exitosas:         {total_exitosas}")
        log.append(f"  Bases omitidas:         {total_omitidas}")
        log.append(f"  Bases con error:        {total_errores}")
        log.append("")
        if self.dry_run:
            log.append(f"  Secuencias A CREAR:     {total_secuencias}")
            log.append(f"  Secuencias existentes:  {total_validadas_ok} (ya existen, config correcta)")
            log.append(f"  Secuencias omitidas:    {total_sec_omitidas} (tipo documento no existe)")
            log.append(f"  Secuencias con error:   {total_error_config} (config incorrecta)")
        else:
            log.append(f"  Secuencias creadas:     {total_secuencias}")
            log.append(f"  Secuencias validadas:   {total_validadas_ok} (ya existian, config correcta)")
            log.append(f"  Secuencias omitidas:    {total_sec_omitidas} (tipo documento no existe)")
            log.append(f"  Secuencias con error:   {total_error_config + total_error_creacion} (config incorrecta o fallo creacion)")
        log.append("")

        # Mostrar observaciones de omitidas (sin duplicados)
        if todas_obs_omitidas:
            log.append("  SECUENCIAS OMITIDAS (tipo documento no encontrado):")
            # Eliminar duplicados manteniendo orden
            obs_unicas = []
            vistos = set()
            for obs in todas_obs_omitidas:
                # Extraer solo el tipo de documento para agrupar
                if obs not in vistos:
                    vistos.add(obs)
                    obs_unicas.append(obs)
            for obs in obs_unicas[:10]:  # Limitar a 10 para no saturar
                log.append(f"    [-] {obs}")
            if len(obs_unicas) > 10:
                log.append(f"    ... y {len(obs_unicas) - 10} mas")
            log.append("")

        # Mostrar observaciones de errores de creacion
        if todas_obs_error:
            log.append("  SECUENCIAS CON ERROR DE CREACION:")
            for obs in todas_obs_error[:10]:
                log.append(f"    [X] {obs}")
            if len(todas_obs_error) > 10:
                log.append(f"    ... y {len(todas_obs_error) - 10} mas")
            log.append("")

        log.append("  Detalle por base:")

        for db_name, resultado in self.resultados.items():
            if resultado['estado'] not in ['OMITIDA', 'ERROR']:
                cajas_count = len(resultado['cajas'])
                sec_creadas = resultado['secuencias_creadas']
                sec_validadas = resultado.get('secuencias_validadas_ok', 0)
                sec_omit = resultado.get('secuencias_omitidas', 0)
                sec_error = resultado.get('secuencias_con_error_config', 0) + resultado.get('secuencias_con_error_creacion', 0)
                detalles = []
                if sec_creadas > 0:
                    detalles.append(f"{sec_creadas} creadas")
                if sec_validadas > 0:
                    detalles.append(f"{sec_validadas} OK")
                if sec_omit > 0:
                    detalles.append(f"{sec_omit} omit")
                if sec_error > 0:
                    detalles.append(f"{sec_error} err")
                detalle_str = ", ".join(detalles) if detalles else "sin cambios"
                log.append(f"  +-- {db_name}: {detalle_str} ({cajas_count} cajas)")
            else:
                log.append(f"  +-- {db_name}: {resultado['estado']}")

        log.append(linea)

        return "\n".join(log)

    def ejecutar(self):
        """Ejecuta el proceso principal"""
        print("")
        print("=" * 80)
        if self.dry_run:
            print("          ANALISIS DE SECUENCIAS (DRY-RUN)")
            print("          *** MODO SIMULACION - NO SE CREARA NADA ***")
        else:
            print("          GENERADOR DE SECUENCIAS DE DOCUMENTOS FISCALES")
        print(f"          Año: {self.year}")
        print(f"          Conexion: {self.pg_host}:{self.pg_port}")
        print("=" * 80)
        print("")

        # Validar conexion primero
        print("Validando conexion a PostgreSQL...")
        ok, error = self.test_conexion()
        if not ok:
            print(f"ERROR: No se pudo conectar a PostgreSQL")
            print(f"       {error}")
            print("")
            print("Verifica:")
            print(f"  - Host: {self.pg_host}")
            print(f"  - Puerto: {self.pg_port}")
            print(f"  - Usuario: {self.pg_user}")
            print("  - Que Docker este corriendo")
            print("")
            print("Puedes especificar host y puerto:")
            print("  python generar_secuencias.py --year 2026 --host localhost --port 5434")
            return

        print(f"Conexion OK: {self.pg_host}:{self.pg_port}")
        print("")

        # Obtener lista de bases
        print("Obteniendo lista de bases de datos...")
        bases = self.obtener_bases_datos()

        if not bases:
            print("No se encontraron bases de datos para procesar")
            print("")
            print("Usa --list para ver las bases disponibles:")
            print("  python generar_secuencias.py --list")
            return

        print(f"Bases a procesar: {', '.join(bases)}")
        print("")

        # Procesar cada base
        for i, db_name in enumerate(bases, 1):
            print(f"[{i}/{len(bases)}] Procesando: {db_name}...")
            self.resultados[db_name] = self.procesar_base(db_name)
            print(f"         -> {self.resultados[db_name]['estado']}")

        # Generar y mostrar log
        log = self.generar_log()
        print("")
        print(log)

        # Guardar log en archivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Crear carpeta logs si no existe
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        log_filename = os.path.join(log_dir, f"secuencias_{self.year}_{timestamp}.log")

        try:
            with open(log_filename, 'w', encoding='utf-8') as f:
                f.write(log)
            print(f"\nLog guardado en: {log_filename}")
        except Exception as e:
            print(f"\nNo se pudo guardar el log: {e}")


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

def main():
    print("""
================================================================================
          GENERADOR DE SECUENCIAS DE DOCUMENTOS FISCALES
          Grupo Consiti - 2025
================================================================================
    """)

    parser = argparse.ArgumentParser(
        description='Generador de Secuencias de Documentos Fiscales',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EJECUCION DENTRO DE DOCKER (recomendado):
  # Copiar al contenedor y ejecutar
  docker cp generar_secuencias.py odoo-13-odoo-1:/tmp/
  docker exec -it odoo-13-odoo-1 python /tmp/generar_secuencias.py --year 2026

EJECUCION DESDE WINDOWS:
  # Escanear puertos disponibles
  python generar_secuencias.py --diagnose

  # Ejecutar especificando puerto
  python generar_secuencias.py --year 2026 --port 5434  # Odoo 13
  python generar_secuencias.py --year 2026 --port 5432  # Odoo 17
  python generar_secuencias.py --year 2026 --port 5437  # Odoo 18

  # Base de datos especifica
  python generar_secuencias.py --year 2026 --port 5434 -d AMBIENTE2

Puertos tipicos:
  - 5432: Odoo 17 / PostgreSQL estandar
  - 5434: Odoo 13
  - 5437: Odoo 18
  - databaseodoo:5432 (dentro de Docker)
        """
    )

    parser.add_argument(
        '--year',
        type=int,
        help='Año para las secuencias (ej: 2026)'
    )

    parser.add_argument(
        '-d', '--database',
        type=str,
        default=None,
        help='Base de datos especifica (opcional)'
    )

    parser.add_argument(
        '-e', '--exclude',
        type=str,
        default=None,
        help='Bases a excluir separadas por coma (opcional)'
    )

    parser.add_argument(
        '--host',
        type=str,
        default=None,
        help=f'Host de PostgreSQL (default: {DEFAULT_PG_HOST})'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=None,
        help=f'Puerto de PostgreSQL (default: {DEFAULT_PG_PORT})'
    )

    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='Listar bases de datos disponibles'
    )

    parser.add_argument(
        '--diagnose',
        action='store_true',
        help='Escanear puertos y mostrar conexiones disponibles'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Modo simulacion: analiza sin crear secuencias'
    )

    args = parser.parse_args()

    # Modo diagnostico - escanea puertos
    if args.diagnose:
        generador = GeneradorSecuencias(host=args.host, port=args.port)
        generador.diagnostico_conexion()
        return

    # Modo listar bases
    if args.list:
        generador = GeneradorSecuencias(host=args.host, port=args.port)
        generador.listar_bases()
        return

    # Validar año
    if not args.year:
        print("ERROR: Debes especificar --year o usar --list/--diagnose")
        print("")
        print("Ejemplos:")
        print("  python generar_secuencias.py --diagnose              # Ver puertos disponibles")
        print("  python generar_secuencias.py --list                  # Listar bases")
        print("  python generar_secuencias.py --year 2026             # Ejecutar")
        print("  python generar_secuencias.py --year 2026 --port 5434 # Puerto especifico")
        sys.exit(1)

    if args.year < 2020 or args.year > 2100:
        print("ERROR: El año debe estar entre 2020 y 2100")
        sys.exit(1)

    generador = GeneradorSecuencias(
        year=args.year,
        database=args.database,
        exclude=args.exclude,
        host=args.host,
        port=args.port,
        dry_run=args.dry_run
    )

    try:
        generador.ejecutar()
    except KeyboardInterrupt:
        print("\n\nProceso interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\nError fatal: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
