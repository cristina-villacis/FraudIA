-- ============================================
-- FraudIA Claims - Schema MySQL
-- Ejecutar en MySQL Workbench o cliente MySQL
-- ============================================

CREATE DATABASE IF NOT EXISTS fraudia_claims
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE fraudia_claims;

-- Tabla: Asegurados
CREATE TABLE IF NOT EXISTS asegurados (
    id_asegurado VARCHAR(20) PRIMARY KEY,
    segmento VARCHAR(50),
    antiguedad_anos INT,
    ciudad VARCHAR(100),
    numero_polizas INT DEFAULT 0,
    reclamos_ultimos_12m INT DEFAULT 0,
    mora_actual INT DEFAULT 0,
    score_cliente FLOAT
) ENGINE=InnoDB;

-- Tabla: Vehiculos
CREATE TABLE IF NOT EXISTS vehiculos (
    id_vehiculo VARCHAR(20) PRIMARY KEY,
    id_asegurado VARCHAR(20),
    placa VARCHAR(20),
    chasis VARCHAR(30),
    motor VARCHAR(20),
    marca VARCHAR(50),
    modelo VARCHAR(50),
    ano INT,
    color VARCHAR(30),
    tipo VARCHAR(30),
    INDEX ix_vehiculos_placa (placa),
    INDEX ix_vehiculos_chasis (chasis),
    FOREIGN KEY (id_asegurado) REFERENCES asegurados(id_asegurado)
) ENGINE=InnoDB;

-- Tabla: Polizas
CREATE TABLE IF NOT EXISTS polizas (
    id_poliza VARCHAR(20) PRIMARY KEY,
    id_asegurado VARCHAR(20),
    ramo VARCHAR(50),
    fecha_inicio DATE,
    fecha_fin DATE,
    prima FLOAT DEFAULT 0,
    suma_asegurada FLOAT DEFAULT 0,
    deducible FLOAT DEFAULT 0,
    canal_venta VARCHAR(50),
    ciudad VARCHAR(100),
    estado_poliza VARCHAR(30),
    INDEX ix_polizas_ramo (ramo),
    INDEX ix_polizas_estado (estado_poliza),
    FOREIGN KEY (id_asegurado) REFERENCES asegurados(id_asegurado)
) ENGINE=InnoDB;

-- Tabla: Proveedores
CREATE TABLE IF NOT EXISTS proveedores (
    id_proveedor VARCHAR(20) PRIMARY KEY,
    nombre_proveedor VARCHAR(200),
    tipo VARCHAR(50),
    ciudad VARCHAR(100),
    reclamos_asociados INT DEFAULT 0,
    monto_promedio_reclamado FLOAT DEFAULT 0,
    casos_observados INT DEFAULT 0,
    porcentaje_casos_observados FLOAT DEFAULT 0,
    en_lista_restrictiva INT DEFAULT 0,
    antiguedad_anos INT,
    INDEX ix_proveedores_tipo (tipo),
    INDEX ix_proveedores_lista (en_lista_restrictiva)
) ENGINE=InnoDB;

-- Tabla: Siniestros (principal)
CREATE TABLE IF NOT EXISTS siniestros (
    id_siniestro VARCHAR(20) PRIMARY KEY,
    id_poliza VARCHAR(20),
    id_asegurado VARCHAR(20),
    id_vehiculo VARCHAR(20) NULL,
    id_conductor VARCHAR(20) NULL,
    ramo VARCHAR(50),
    cobertura VARCHAR(100),
    fecha_ocurrencia DATE,
    fecha_reporte DATE,
    monto_reclamado FLOAT DEFAULT 0,
    monto_estimado FLOAT DEFAULT 0,
    monto_pagado FLOAT DEFAULT 0,
    estado VARCHAR(50),
    sucursal VARCHAR(50),
    descripcion TEXT,
    documentos_completos VARCHAR(5) DEFAULT 'No',
    id_proveedor VARCHAR(20) NULL,
    beneficiario VARCHAR(200),
    dias_desde_inicio_poliza INT DEFAULT 0,
    dias_desde_fin_poliza INT DEFAULT 0,
    dias_entre_ocurrencia_reporte INT DEFAULT 0,
    historial_siniestros_asegurado INT DEFAULT 0,
    etiqueta_fraude_simulada INT DEFAULT 0,
    -- Campos de scoring (se llenan al ejecutar pipeline)
    score_reglas FLOAT NULL,
    score_hibrido FLOAT NULL,
    ml_fraud_probability FLOAT NULL,
    anomaly_score FLOAT NULL,
    semaforo_final VARCHAR(10) NULL,
    num_alertas INT NULL,
    alertas_reglas TEXT NULL,
    INDEX ix_siniestros_ramo (ramo),
    INDEX ix_siniestros_cobertura (cobertura),
    INDEX ix_siniestros_semaforo (semaforo_final),
    INDEX ix_siniestros_score (score_hibrido),
    INDEX ix_siniestros_fecha (fecha_ocurrencia),
    FOREIGN KEY (id_poliza) REFERENCES polizas(id_poliza),
    FOREIGN KEY (id_asegurado) REFERENCES asegurados(id_asegurado),
    FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo),
    FOREIGN KEY (id_proveedor) REFERENCES proveedores(id_proveedor)
) ENGINE=InnoDB;

-- Tabla: Documentos
CREATE TABLE IF NOT EXISTS documentos (
    id_documento VARCHAR(20) PRIMARY KEY,
    id_siniestro VARCHAR(20),
    tipo_documento VARCHAR(100),
    entregado VARCHAR(5) DEFAULT 'No',
    legible VARCHAR(5) DEFAULT 'No',
    fecha_emision DATE NULL,
    inconsistencia_detectada TEXT NULL,
    observacion TEXT NULL,
    FOREIGN KEY (id_siniestro) REFERENCES siniestros(id_siniestro)
) ENGINE=InnoDB;

-- Tabla: Historial de ejecuciones de analisis
CREATE TABLE IF NOT EXISTS analisis_runs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fecha_ejecucion DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_siniestros INT,
    rojos INT,
    amarillos INT,
    verdes INT,
    score_promedio FLOAT,
    auc_roc FLOAT NULL,
    anomalias_detectadas INT NULL,
    duracion_segundos FLOAT NULL,
    estado VARCHAR(20) DEFAULT 'completado'
) ENGINE=InnoDB;
