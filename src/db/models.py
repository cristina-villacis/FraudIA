"""
Modelos ORM - Tablas de la base de datos.
Compatible con MySQL en la nube y SQLite local.
"""
from datetime import date, datetime

from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, Text,
    ForeignKey, Index, func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Asegurado(Base):
    __tablename__ = "asegurados"

    id_asegurado = Column(String(20), primary_key=True)
    segmento = Column(String(50))
    antiguedad_anos = Column(Integer)
    ciudad = Column(String(100))
    numero_polizas = Column(Integer, default=0)
    reclamos_ultimos_12m = Column(Integer, default=0)
    mora_actual = Column(Integer, default=0)
    score_cliente = Column(Float)

    polizas = relationship("Poliza", back_populates="asegurado")
    vehiculos = relationship("Vehiculo", back_populates="asegurado")
    siniestros = relationship("Siniestro", back_populates="asegurado", foreign_keys="Siniestro.id_asegurado")


class Vehiculo(Base):
    __tablename__ = "vehiculos"

    id_vehiculo = Column(String(20), primary_key=True)
    id_asegurado = Column(String(20), ForeignKey("asegurados.id_asegurado"))
    placa = Column(String(20))
    chasis = Column(String(30))
    motor = Column(String(20))
    marca = Column(String(50))
    modelo = Column(String(50))
    ano = Column(Integer)
    color = Column(String(30))
    tipo = Column(String(30))

    asegurado = relationship("Asegurado", back_populates="vehiculos")
    siniestros = relationship("Siniestro", back_populates="vehiculo")

    __table_args__ = (
        Index("ix_vehiculos_placa", "placa"),
        Index("ix_vehiculos_chasis", "chasis"),
    )


class Poliza(Base):
    __tablename__ = "polizas"

    id_poliza = Column(String(20), primary_key=True)
    id_asegurado = Column(String(20), ForeignKey("asegurados.id_asegurado"))
    ramo = Column(String(50))
    fecha_inicio = Column(Date)
    fecha_fin = Column(Date)
    prima = Column(Float, default=0)
    suma_asegurada = Column(Float, default=0)
    deducible = Column(Float, default=0)
    canal_venta = Column(String(50))
    ciudad = Column(String(100))
    estado_poliza = Column(String(30))

    asegurado = relationship("Asegurado", back_populates="polizas")
    siniestros = relationship("Siniestro", back_populates="poliza")

    __table_args__ = (
        Index("ix_polizas_ramo", "ramo"),
        Index("ix_polizas_estado", "estado_poliza"),
    )


class Proveedor(Base):
    __tablename__ = "proveedores"

    id_proveedor = Column(String(20), primary_key=True)
    nombre_proveedor = Column(String(200))
    tipo = Column(String(50))
    ciudad = Column(String(100))
    reclamos_asociados = Column(Integer, default=0)
    monto_promedio_reclamado = Column(Float, default=0)
    casos_observados = Column(Integer, default=0)
    porcentaje_casos_observados = Column(Float, default=0)
    en_lista_restrictiva = Column(Integer, default=0)
    antiguedad_anos = Column(Integer)

    siniestros = relationship("Siniestro", back_populates="proveedor")

    __table_args__ = (
        Index("ix_proveedores_tipo", "tipo"),
        Index("ix_proveedores_lista", "en_lista_restrictiva"),
    )


class Siniestro(Base):
    __tablename__ = "siniestros"

    id_siniestro = Column(String(20), primary_key=True)
    id_poliza = Column(String(20), ForeignKey("polizas.id_poliza"))
    id_asegurado = Column(String(20), ForeignKey("asegurados.id_asegurado"))
    id_vehiculo = Column(String(20), ForeignKey("vehiculos.id_vehiculo"), nullable=True)
    id_conductor = Column(String(20), nullable=True)
    ramo = Column(String(50))
    cobertura = Column(String(100))
    fecha_ocurrencia = Column(Date)
    fecha_reporte = Column(Date)
    monto_reclamado = Column(Float, default=0)
    monto_estimado = Column(Float, default=0)
    monto_pagado = Column(Float, default=0)
    estado = Column(String(50))
    sucursal = Column(String(50))
    descripcion = Column(Text)
    documentos_completos = Column(String(5), default="No")
    id_proveedor = Column(String(20), ForeignKey("proveedores.id_proveedor"), nullable=True)
    beneficiario = Column(String(200))
    dias_desde_inicio_poliza = Column(Integer, default=0)
    dias_desde_fin_poliza = Column(Integer, default=0)
    dias_entre_ocurrencia_reporte = Column(Integer, default=0)
    historial_siniestros_asegurado = Column(Integer, default=0)
    etiqueta_fraude_simulada = Column(Integer, default=0)

    # Campos de scoring (se llenan al ejecutar pipeline)
    score_reglas = Column(Float, nullable=True)
    score_hibrido = Column(Float, nullable=True)
    ml_fraud_probability = Column(Float, nullable=True)
    anomaly_score = Column(Float, nullable=True)
    semaforo_final = Column(String(10), nullable=True)
    num_alertas = Column(Integer, nullable=True)
    alertas_reglas = Column(Text, nullable=True)

    poliza = relationship("Poliza", back_populates="siniestros")
    asegurado = relationship("Asegurado", back_populates="siniestros", foreign_keys=[id_asegurado])
    vehiculo = relationship("Vehiculo", back_populates="siniestros")
    proveedor = relationship("Proveedor", back_populates="siniestros")
    documentos = relationship("Documento", back_populates="siniestro", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_siniestros_ramo", "ramo"),
        Index("ix_siniestros_cobertura", "cobertura"),
        Index("ix_siniestros_semaforo", "semaforo_final"),
        Index("ix_siniestros_score", "score_hibrido"),
        Index("ix_siniestros_fecha", "fecha_ocurrencia"),
    )


class Documento(Base):
    __tablename__ = "documentos"

    id_documento = Column(String(20), primary_key=True)
    id_siniestro = Column(String(20), ForeignKey("siniestros.id_siniestro"))
    tipo_documento = Column(String(100))
    entregado = Column(String(5), default="No")
    legible = Column(String(5), default="No")
    fecha_emision = Column(Date, nullable=True)
    inconsistencia_detectada = Column(Text, nullable=True)
    observacion = Column(Text, nullable=True)

    siniestro = relationship("Siniestro", back_populates="documentos")


class AnalisisRun(Base):
    """Registro de cada ejecución del pipeline de análisis."""
    __tablename__ = "analisis_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha_ejecucion = Column(DateTime, default=func.now())
    total_siniestros = Column(Integer)
    rojos = Column(Integer)
    amarillos = Column(Integer)
    verdes = Column(Integer)
    score_promedio = Column(Float)
    auc_roc = Column(Float, nullable=True)
    anomalias_detectadas = Column(Integer, nullable=True)
    duracion_segundos = Column(Float, nullable=True)
    estado = Column(String(20), default="completado")
