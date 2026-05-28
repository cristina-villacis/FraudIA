# Modelo de Datos (Ajustado)

## 1) Tabla base obligatoria: `siniestros`

Esta es la tabla mínima que el usuario puede cargar de forma directa.

| Campo | Descripción |
|---|---|
| id_siniestro | Identificador único del siniestro |
| id_poliza | Identificador de la póliza |
| id_asegurado | Identificador anónimo del asegurado |
| ramo | Línea de negocio (Vehículos, Salud, Vida, Generales, Hogar) |
| cobertura | Tipo de cobertura (Choque, Robo, Incendio, etc.) |
| fecha_ocurrencia | Fecha del evento |
| fecha_reporte | Fecha de notificación |
| monto_reclamado | Valor solicitado por asegurado/proveedor |
| monto_estimado | Valor estimado por la aseguradora |
| monto_pagado | Valor pagado, si aplica |
| estado | Estado del siniestro |
| sucursal | Sucursal del siniestro |
| descripcion | Texto libre del reclamo |
| documentos_completos | Indicador Sí/No |
| beneficiario | Taller, clínica, perito u otro |
| dias_desde_inicio_poliza | Días entre inicio de póliza y siniestro |
| dias_desde_fin_poliza | Días entre fin de póliza y siniestro |
| dias_entre_ocurrencia_reporte | Diferencia de días entre ocurrencia y reporte |
| historial_siniestros_asegurado | Número de reclamos previos del asegurado |
| etiqueta_fraude_simulada | 0/1 para entrenamiento/evaluación (si aplica) |

## 2) Tablas complementarias sugeridas (trazabilidad)

### `polizas`
`id_poliza, id_asegurado, ramo, fecha_inicio, fecha_fin, prima, suma_asegurada, deducible, canal_venta, ciudad, estado_poliza`

### `asegurados`
`id_asegurado, segmento, antiguedad_anos, ciudad, numero_polizas, reclamos_ultimos_12m, mora_actual, score_cliente`

### `proveedores`
`id_proveedor, tipo, ciudad, reclamos_asociados, monto_promedio_reclamado, casos_observados, porcentaje_casos_observados, antiguedad_anos`

### `documentos`
`id_documento, id_siniestro, tipo_documento, entregado, legible, fecha_emision, inconsistencia_detectada, observacion`

## 3) Señales de fraude priorizadas para reglas, ML y chatbot

- Reclamo cercano al borde de vigencia
- Demora de denuncia por robo
- Alta frecuencia de reclamos (asegurado, vehículo, conductor)
- Frecuencia atípica de reclamos solo RC
- Proveedor/beneficiario recurrente o en lista restrictiva
- Documentos incompletos o inconsistentes
- Dinámica sospechosa del accidente
- Evento sin tercero identificado
- Reporte tardío
- Narrativas similares (NLP)
- Monto cercano/superior a suma asegurada

## 4) Relaciones principales

`asegurados 1─N polizas`  
`polizas 1─N siniestros`  
`siniestros N─1 proveedores`  
`siniestros 1─N documentos`
