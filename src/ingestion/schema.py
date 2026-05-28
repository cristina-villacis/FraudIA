"""
Esquema canónico del reto (solo definiciones de campos — sin dataset embebido).
Cualquier Excel de prueba se mapea a estos nombres para el análisis.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# (nombre_campo, descripción)
SINIESTROS_FIELDS: List[Tuple[str, str]] = [
    ("id_siniestro", "Identificador único del siniestro."),
    ("id_poliza", "Identificador de la póliza."),
    ("id_asegurado", "Identificador anónimo del asegurado."),
    ("ramo", "Vehículos, salud, vida, generales, hogar u otro."),
    ("cobertura", "Choque, robo, atención médica, incendio, daño u otro."),
    ("fecha_ocurrencia", "Fecha del evento."),
    ("fecha_reporte", "Fecha de notificación."),
    ("monto_reclamado", "Valor solicitado por el asegurado o proveedor."),
    ("monto_estimado", "Valor estimado por la aseguradora."),
    ("monto_pagado", "Valor pagado, si aplica."),
    ("estado", "Reserva, Pago Total, Pago Parcial, Anticipo, Negativa, Cierre Sin Consecuencia, Liquidado."),
    ("sucursal", "Sucursal del siniestro."),
    ("descripcion", "Texto libre del reclamo."),
    ("documentos_completos", "Indicador Sí/No."),
    ("beneficiario", "Taller, clínica, perito u otro."),
    ("dias_desde_inicio_poliza", "Días entre inicio de póliza y siniestro."),
    ("dias_desde_fin_poliza", "Días entre fin de póliza y siniestro."),
    ("dias_entre_ocurrencia_reporte", "Diferencia entre ocurrencia y reporte."),
    ("historial_siniestros_asegurado", "Número de siniestros previos del asegurado."),
    ("etiqueta_fraude_simulada", "0/1, solo para entrenamiento o evaluación si aplica."),
]

POLIZAS_FIELDS: List[Tuple[str, str]] = [
    ("id_poliza", "Identificador de la póliza."),
    ("id_asegurado", "Identificador del asegurado."),
    ("ramo", "Ramo de la póliza."),
    ("fecha_inicio", "Inicio de vigencia."),
    ("fecha_fin", "Fin de vigencia."),
    ("prima", "Prima."),
    ("suma_asegurada", "Suma asegurada."),
    ("deducible", "Deducible."),
    ("canal_venta", "Canal de venta."),
    ("ciudad", "Ciudad."),
    ("estado_poliza", "Estado de la póliza."),
]

ASEGURADOS_FIELDS: List[Tuple[str, str]] = [
    ("id_asegurado", "Identificador del asegurado."),
    ("segmento", "Segmento del cliente."),
    ("antiguedad_anos", "Antigüedad en años."),
    ("ciudad", "Ciudad."),
    ("numero_polizas", "Número de pólizas."),
    ("reclamos_ultimos_12m", "Reclamos últimos 12 meses."),
    ("mora_actual", "Mora actual."),
    ("score_cliente", "Score cliente simulado."),
]

PROVEEDORES_FIELDS: List[Tuple[str, str]] = [
    ("id_proveedor", "Identificador del proveedor/beneficiario."),
    ("tipo", "Tipo de proveedor."),
    ("ciudad", "Ciudad."),
    ("reclamos_asociados", "Reclamos asociados."),
    ("monto_promedio_reclamado", "Monto promedio reclamado."),
    ("porcentaje_casos_observados", "Porcentaje de casos observados."),
    ("antiguedad_anos", "Antigüedad."),
]

DOCUMENTOS_FIELDS: List[Tuple[str, str]] = [
    ("id_documento", "Identificador del documento."),
    ("id_siniestro", "Siniestro asociado."),
    ("tipo_documento", "Tipo de documento."),
    ("entregado", "Indicador de entrega."),
    ("legible", "Indicador de legibilidad."),
    ("fecha_emision", "Fecha de emisión."),
    ("inconsistencia_detectada", "Inconsistencias detectadas."),
    ("observacion", "Observaciones."),
]

# Campos extra del Excel de demo/prueba (opcionales para reglas avanzadas)
SINIESTROS_OPTIONAL = [
    "placa_vehiculo",
    "id_proveedor",
    "prov_en_lista_restrictiva",
    "similitud_narrativa_max",
    "numero_parte_policial",
    "suma_asegurada",
]

CANONICAL_TABLES = ("siniestros", "polizas", "asegurados", "proveedores", "documentos")

FIELD_DESCRIPTIONS: Dict[str, Dict[str, str]] = {
    "siniestros": dict(SINIESTROS_FIELDS),
    "polizas": dict(POLIZAS_FIELDS),
    "asegurados": dict(ASEGURADOS_FIELDS),
    "proveedores": dict(PROVEEDORES_FIELDS),
    "documentos": dict(DOCUMENTOS_FIELDS),
}

EXPECTED_COLUMNS: Dict[str, List[str]] = {
    "siniestros": [f[0] for f in SINIESTROS_FIELDS] + SINIESTROS_OPTIONAL,
    "polizas": [f[0] for f in POLIZAS_FIELDS],
    "asegurados": [f[0] for f in ASEGURADOS_FIELDS] + ["nombres_asegurado"],
    "proveedores": [f[0] for f in PROVEEDORES_FIELDS] + ["nombre_proveedor", "en_lista_restrictiva"],
    "documentos": [f[0] for f in DOCUMENTOS_FIELDS] + ["nombre_archivo_pdf"],
}

REQUIRED_COLUMNS: Dict[str, List[str]] = {
    "siniestros": ["id_siniestro", "id_poliza", "id_asegurado", "ramo", "fecha_ocurrencia", "monto_reclamado"],
    "polizas": ["id_poliza", "id_asegurado"],
    "asegurados": ["id_asegurado"],
    "proveedores": ["id_proveedor"],
    "documentos": ["id_documento", "id_siniestro"],
}

# Hojas Excel → tabla interna
SHEET_ALIASES: Dict[str, str] = {
    "siniestros": "siniestros",
    "1_siniestros": "siniestros",
    "polizas": "polizas",
    "2_polizas": "polizas",
    "asegurados": "asegurados",
    "3_asegurados": "asegurados",
    "proveedores": "proveedores",
    "4_proveedores": "proveedores",
    "documentos": "documentos",
    "5_documentos": "documentos",
    "readme": "readme",
}

# Plantilla descargable (nombres de hoja legibles)
TEMPLATE_SHEETS: Dict[str, List[str]] = {
    "Siniestros": [f[0] for f in SINIESTROS_FIELDS],
    "Polizas": [f[0] for f in POLIZAS_FIELDS],
    "Asegurados": [f[0] for f in ASEGURADOS_FIELDS],
    "Proveedores": [f[0] for f in PROVEEDORES_FIELDS],
    "Documentos": [f[0] for f in DOCUMENTOS_FIELDS],
}

SKIP_SHEETS = frozenset({"readme", "guia", "indice_documentos"})
