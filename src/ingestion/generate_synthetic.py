"""
Generador de  datos sintéticos para el sistema de detección de fraude en seguros.
Genera tablas: asegurados, pólizas, vehículos, proveedores, siniestros, documentos.
"""
import os
import random
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

OUTPUT_DIR = os.path.join("data", "synthetic")


def _set_seed(seed: Optional[int] = None) -> int:
    """Inicializa random/numpy. Si seed es None, usa una semilla aleatoria nueva."""
    if seed is None:
        seed = secrets.randbelow(2**31 - 1) + 1
    random.seed(seed)
    np.random.seed(seed)
    return seed

CIUDADES = [
    "Quito", "Guayaquil", "Cuenca", "Ambato", "Loja", "Manta",
    "Riobamba", "Ibarra", "Machala", "Santo Domingo", "Portoviejo", "Esmeraldas"
]
MARCAS_MODELOS = {
    "Chevrolet": ["Aveo", "Sail", "Spark", "Cruze", "Tracker", "Equinox", "D-Max"],
    "Kia": ["Rio", "Sportage", "Picanto", "Cerato", "Seltos", "Sorento"],
    "Hyundai": ["Accent", "Tucson", "Creta", "Santa Fe", "Grand i10", "Elantra"],
    "Toyota": ["Corolla", "Hilux", "Fortuner", "Yaris", "RAV4", "Prado"],
    "Nissan": ["Sentra", "Frontier", "Kicks", "Versa", "X-Trail", "March"],
    "Mazda": ["3", "CX-5", "CX-30", "2", "CX-3", "BT-50"],
    "Ford": ["Escape", "Explorer", "Ranger", "EcoSport", "Bronco"],
    "Renault": ["Duster", "Kwid", "Logan", "Stepway", "Koleos"],
    "Volkswagen": ["Gol", "T-Cross", "Tiguan", "Amarok", "Polo"],
    "Suzuki": ["Swift", "Vitara", "S-Cross", "Jimny", "Baleno"],
}
RAMOS = ["Vehículos", "Salud", "Vida", "Generales", "Hogar"]
COBERTURAS_POR_RAMO = {
    "Vehículos": [
        "Choque", "Robo", "Pérdida Total", "Pérdida Total por Robo (PTxRB)",
        "Responsabilidad Civil", "Daño Parcial", "Volcadura",
    ],
    "Salud": ["Atención Médica", "Hospitalización", "Cirugía", "Emergencia"],
    "Vida": ["Fallecimiento", "Incapacidad", "Enfermedad Grave"],
    "Generales": ["Incendio", "Daño", "Robo", "Responsabilidad Civil"],
    "Hogar": ["Incendio", "Robo", "Daño por Agua", "Desastres Naturales"],
}
ESTADOS_SINIESTRO = [
    "Reserva", "Pago Total", "Pago Parcial", "Anticipo",
    "Negativa", "Cierre Sin Consecuencia", "Liquidado"
]
SUCURSALES = ["Norte", "Sur", "Centro", "Costa", "Sierra", "Oriente"]
TIPOS_PROVEEDOR = ["Taller", "Clínica", "Hospital", "Perito", "Grúa", "Abogado", "Intermediario"]
TIPOS_DOCUMENTO = ["Denuncia", "Factura", "Informe Pericial", "Fotografías", "Parte Policial", "Certificado Médico", "Acta de Defunción"]
CANALES_VENTA = ["Agente", "Broker", "Digital", "Bancaseguros", "Directo"]
SEGMENTOS = ["Individual", "Corporativo", "PYME", "Preferente"]

NARRATIVAS_NORMALES = [
    "El vehículo fue impactado por otro automóvil en la intersección de la Av. Principal con calle secundaria.",
    "Se reporta robo del vehículo estacionado frente al domicilio del asegurado durante la noche.",
    "Colisión lateral en la autopista debido a cambio de carril imprudente del otro conductor.",
    "Daños en la parte trasera del vehículo por choque en cadena en hora pico.",
    "El asegurado reporta que un vehículo no identificado impactó su auto estacionado.",
    "Accidente en vía mojada, el vehículo perdió tracción y colisionó contra la baranda.",
    "Impacto frontal contra poste de alumbrado al intentar esquivar un peatón.",
    "Robo del vehículo en estacionamiento del centro comercial, no hay cámaras disponibles.",
    "El asegurado fue víctima de asalto, le sustrajeron el vehículo con amenaza.",
    "Volcadura en carretera rural por exceso de velocidad según informe de tránsito.",
    "Incendio del vehículo de origen eléctrico según informe del perito.",
    "Daño por granizo severo que afectó capó, techo y panel lateral.",
    "Choque por alcance en semáforo, el conductor de atrás no frenó a tiempo.",
    "El paciente acudió a emergencia por dolor abdominal agudo, requirió cirugía.",
    "Hospitalización por fractura de fémur tras caída en el trabajo.",
    "Consulta médica por cuadro respiratorio, derivado a especialista.",
    "Incendio en cocina del domicilio, daños en muebles y estructura.",
    "Robo de electrodomésticos en domicilio durante vacaciones del asegurado.",
    "Inundación por tubería rota que afectó pisos y paredes del primer nivel.",
    "Daños en techo por caída de árbol durante tormenta eléctrica.",
]

NARRATIVAS_SOSPECHOSAS = [
    "El vehículo fue sustraído durante la madrugada, el asegurado no recuerda detalles exactos del lugar.",
    "El vehículo fue robado, no hay testigos ni cámaras, la denuncia se hizo varios días después.",
    "Choque frontal sin testigos en zona solitaria durante la noche, el otro vehículo huyó.",
    "Pérdida total del vehículo por incendio de origen desconocido sin causa aparente.",
    "El vehículo fue robado con las llaves puestas, el asegurado no puede explicar las circunstancias.",
    "Accidente en madrugada sin testigos, múltiples vehículos involucrados, relatos contradictorios.",
    "El asegurado reporta daño severo pero las fotos no coinciden con la descripción del impacto.",
    "Robo del vehículo reportado días después, sin denuncia policial inmediata.",
    "El vehículo fue sustraído durante la madrugada, el asegurado no recuerda detalles exactos del lugar.",
    "Pérdida total por volcadura en vía recta sin obstáculos visibles según fotos del lugar.",
]


def generate_plate():
    letters = "".join(random.choices(string.ascii_uppercase, k=3))
    numbers = "".join(random.choices(string.digits, k=4))
    return f"{letters}-{numbers}"


def generate_chassis():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=17))


def generate_motor():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=12))


def generate_asegurados(n=500):
    records = []
    for i in range(n):
        ciudad = random.choice(CIUDADES)
        antiguedad = random.randint(1, 20)
        n_polizas = random.randint(1, 5)
        reclamos_12m = np.random.poisson(0.8)
        mora = random.choice([0, 0, 0, 0, 1, 2, 3])
        score = round(random.uniform(300, 900), 1)
        records.append({
            "id_asegurado": f"ASG-{i+1:05d}",
            "segmento": random.choice(SEGMENTOS),
            "antiguedad_anos": antiguedad,
            "ciudad": ciudad,
            "numero_polizas": n_polizas,
            "reclamos_ultimos_12m": reclamos_12m,
            "mora_actual": mora,
            "score_cliente": score,
            "en_lista_restrictiva": 1 if random.random() < 0.03 else 0,
        })
    return pd.DataFrame(records)


def generate_vehiculos(asegurados_df, n=600):
    records = []
    for i in range(n):
        marca = random.choice(list(MARCAS_MODELOS.keys()))
        modelo = random.choice(MARCAS_MODELOS[marca])
        ano = random.randint(2010, 2025)
        asegurado = random.choice(asegurados_df["id_asegurado"].tolist())
        records.append({
            "id_vehiculo": f"VEH-{i+1:05d}",
            "id_asegurado": asegurado,
            "placa": generate_plate(),
            "chasis": generate_chassis(),
            "motor": generate_motor(),
            "marca": marca,
            "modelo": modelo,
            "ano": ano,
            "color": random.choice(["Blanco", "Negro", "Gris", "Rojo", "Azul", "Plateado"]),
            "tipo": random.choice(["Sedán", "SUV", "Camioneta", "Hatchback", "Pick-up"]),
        })
    return pd.DataFrame(records)


def generate_polizas(asegurados_df, n=700):
    records = []
    base_date = datetime(2023, 1, 1)
    for i in range(n):
        asegurado = random.choice(asegurados_df["id_asegurado"].tolist())
        ramo = random.choice(RAMOS)
        fecha_inicio = base_date + timedelta(days=random.randint(0, 730))
        fecha_fin = fecha_inicio + timedelta(days=365)
        suma_asegurada = round(random.uniform(5000, 150000), 2)
        prima = round(suma_asegurada * random.uniform(0.02, 0.08), 2)
        deducible = round(suma_asegurada * random.uniform(0.005, 0.05), 2)
        records.append({
            "id_poliza": f"POL-{i+1:05d}",
            "id_asegurado": asegurado,
            "ramo": ramo,
            "fecha_inicio": fecha_inicio.strftime("%Y-%m-%d"),
            "fecha_fin": fecha_fin.strftime("%Y-%m-%d"),
            "prima": prima,
            "suma_asegurada": suma_asegurada,
            "deducible": deducible,
            "canal_venta": random.choice(CANALES_VENTA),
            "ciudad": random.choice(CIUDADES),
            "estado_poliza": random.choice(["Activa", "Activa", "Activa", "Cancelada", "Vencida"]),
        })
    return pd.DataFrame(records)


def generate_proveedores(n=80):
    records = []
    for i in range(n):
        tipo = random.choice(TIPOS_PROVEEDOR)
        ciudad = random.choice(CIUDADES)
        reclamos = random.randint(1, 60)
        monto_promedio = round(random.uniform(500, 20000), 2)
        casos_observados = random.randint(0, 5)
        porcentaje_observado = round((casos_observados / max(reclamos, 1)) * 100, 2)
        en_lista_restrictiva = 1 if random.random() < 0.05 else 0
        records.append({
            "id_proveedor": f"PRV-{i+1:04d}",
            "nombre_proveedor": f"{tipo} {ciudad} #{i+1}",
            "tipo": tipo,
            "ciudad": ciudad,
            "reclamos_asociados": reclamos,
            "monto_promedio_reclamado": monto_promedio,
            "casos_observados": casos_observados,
            "porcentaje_casos_observados": porcentaje_observado,
            "en_lista_restrictiva": en_lista_restrictiva,
            "antiguedad_anos": random.randint(1, 15),
        })
    return pd.DataFrame(records)


def generate_siniestros(polizas_df, asegurados_df, proveedores_df, vehiculos_df, n=1500):
    records = []
    for i in range(n):
        poliza = polizas_df.sample(1).iloc[0]
        id_poliza = poliza["id_poliza"]
        id_asegurado = poliza["id_asegurado"]
        ramo = poliza["ramo"]
        is_suspicious = random.random() < 0.15

        cobertura = random.choice(COBERTURAS_POR_RAMO[ramo])
        if is_suspicious and ramo == "Vehículos" and random.random() < 0.25:
            cobertura = "Pérdida Total por Robo (PTxRB)"

        fecha_inicio_pol = datetime.strptime(poliza["fecha_inicio"], "%Y-%m-%d")
        fecha_fin_pol = datetime.strptime(poliza["fecha_fin"], "%Y-%m-%d")

        if is_suspicious and random.random() < 0.4:
            dias_offset = random.randint(1, 20)
            fecha_ocurrencia = fecha_inicio_pol + timedelta(days=dias_offset)
        elif is_suspicious and random.random() < 0.3:
            dias_offset = random.randint(1, 20)
            fecha_ocurrencia = fecha_fin_pol - timedelta(days=dias_offset)
        else:
            max_dias = (fecha_fin_pol - fecha_inicio_pol).days
            if max_dias > 0:
                fecha_ocurrencia = fecha_inicio_pol + timedelta(days=random.randint(30, max(31, max_dias - 30)))
            else:
                fecha_ocurrencia = fecha_inicio_pol + timedelta(days=30)

        if is_suspicious and random.random() < 0.5:
            dias_reporte = random.randint(5, 30)
        else:
            dias_reporte = random.randint(0, 5)
        fecha_reporte = fecha_ocurrencia + timedelta(days=dias_reporte)

        suma_asegurada = poliza["suma_asegurada"]
        if is_suspicious and random.random() < 0.3:
            monto_reclamado = round(suma_asegurada * random.uniform(0.85, 1.0), 2)
        else:
            monto_reclamado = round(suma_asegurada * random.uniform(0.05, 0.5), 2)

        monto_estimado = round(monto_reclamado * random.uniform(0.6, 1.1), 2)
        if random.random() < 0.7:
            monto_pagado = round(monto_estimado * random.uniform(0.8, 1.0), 2)
        else:
            monto_pagado = 0.0

        if is_suspicious:
            descripcion = random.choice(NARRATIVAS_SOSPECHOSAS)
        else:
            descripcion = random.choice(NARRATIVAS_NORMALES)

        docs_completos = "No" if (is_suspicious and random.random() < 0.4) else "Sí"

        proveedor = proveedores_df.sample(1).iloc[0]

        dias_desde_inicio = (fecha_ocurrencia - fecha_inicio_pol).days
        dias_desde_fin = (fecha_fin_pol - fecha_ocurrencia).days
        dias_ocurrencia_reporte = (fecha_reporte - fecha_ocurrencia).days

        asegurado_info = asegurados_df[asegurados_df["id_asegurado"] == id_asegurado]
        historial = int(asegurado_info["reclamos_ultimos_12m"].values[0]) if len(asegurado_info) > 0 else 0

        vehiculo_asignado = vehiculos_df[vehiculos_df["id_asegurado"] == id_asegurado]
        id_vehiculo = vehiculo_asignado.iloc[0]["id_vehiculo"] if len(vehiculo_asignado) > 0 else None

        id_conductor = id_asegurado if random.random() < 0.8 else random.choice(asegurados_df["id_asegurado"].tolist())

        etiqueta = 1 if is_suspicious else 0

        records.append({
            "id_siniestro": f"SIN-{i+1:06d}",
            "id_poliza": id_poliza,
            "id_asegurado": id_asegurado,
            "id_vehiculo": id_vehiculo,
            "id_conductor": id_conductor,
            "ramo": ramo,
            "cobertura": cobertura,
            "fecha_ocurrencia": fecha_ocurrencia.strftime("%Y-%m-%d"),
            "fecha_reporte": fecha_reporte.strftime("%Y-%m-%d"),
            "monto_reclamado": monto_reclamado,
            "monto_estimado": monto_estimado,
            "monto_pagado": monto_pagado,
            "estado": random.choice(ESTADOS_SINIESTRO),
            "sucursal": random.choice(SUCURSALES),
            "descripcion": descripcion,
            "documentos_completos": docs_completos,
            "id_proveedor": proveedor["id_proveedor"],
            "beneficiario": proveedor["nombre_proveedor"],
            "dias_desde_inicio_poliza": max(0, dias_desde_inicio),
            "dias_desde_fin_poliza": max(0, dias_desde_fin),
            "dias_entre_ocurrencia_reporte": max(0, dias_ocurrencia_reporte),
            "historial_siniestros_asegurado": historial,
            "etiqueta_fraude_simulada": etiqueta,
        })
    return pd.DataFrame(records)


def generate_documentos(siniestros_df):
    records = []
    doc_id = 1
    for _, sin in siniestros_df.iterrows():
        n_docs = random.randint(2, 5)
        tipos_seleccionados = random.sample(TIPOS_DOCUMENTO, min(n_docs, len(TIPOS_DOCUMENTO)))
        is_suspicious = sin["etiqueta_fraude_simulada"] == 1

        for tipo in tipos_seleccionados:
            entregado = "No" if (is_suspicious and random.random() < 0.3) else "Sí"
            legible = "No" if (is_suspicious and random.random() < 0.2) else "Sí"
            fecha_evento = datetime.strptime(sin["fecha_ocurrencia"], "%Y-%m-%d")

            if is_suspicious and random.random() < 0.15:
                fecha_emision = fecha_evento - timedelta(days=random.randint(1, 10))
                inconsistencia = "Fecha de emisión anterior al evento"
            else:
                fecha_emision = fecha_evento + timedelta(days=random.randint(0, 5))
                inconsistencia = ""

            if is_suspicious and random.random() < 0.2:
                inconsistencia = random.choice([
                    "Valores no coinciden con factura",
                    "Fecha de emisión anterior al evento",
                    "Documento ilegible o borroso",
                    "Firma no coincide con registros",
                    "Número de documento duplicado",
                ])

            records.append({
                "id_documento": f"DOC-{doc_id:06d}",
                "id_siniestro": sin["id_siniestro"],
                "tipo_documento": tipo,
                "entregado": entregado,
                "legible": legible,
                "fecha_emision": fecha_emision.strftime("%Y-%m-%d"),
                "inconsistencia_detectada": inconsistencia,
                "observacion": "" if not inconsistencia else f"Requiere revisión: {inconsistencia}",
            })
            doc_id += 1
    return pd.DataFrame(records)


def main(seed: Optional[int] = None) -> int:
    """Genera datasets sintéticos. Retorna la semilla usada."""
    used_seed = _set_seed(seed)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Generando datos sintéticos (semilla={used_seed})...")
    print("Generando asegurados...")
    asegurados = generate_asegurados(500)

    print("Generando vehículos...")
    vehiculos = generate_vehiculos(asegurados, 600)

    print("Generando pólizas...")
    polizas = generate_polizas(asegurados, 700)

    print("Generando proveedores...")
    proveedores = generate_proveedores(80)

    print("Generando siniestros...")
    siniestros = generate_siniestros(polizas, asegurados, proveedores, vehiculos, 1500)

    print("Generando documentos...")
    documentos = generate_documentos(siniestros)

    datasets = {
        "asegurados": asegurados,
        "vehiculos": vehiculos,
        "polizas": polizas,
        "proveedores": proveedores,
        "siniestros": siniestros,
        "documentos": documentos,
    }

    for name, df in datasets.items():
        csv_path = os.path.join(OUTPUT_DIR, f"{name}.csv")
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"  {name}: {len(df)} registros -> {csv_path}")

    excel_path = os.path.join(OUTPUT_DIR, "dataset_completo.xlsx")
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        for name, df in datasets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    print(f"\nDataset completo exportado a: {excel_path}")

    print("\n--- Resumen ---")
    for name, df in datasets.items():
        print(f"  {name}: {df.shape[0]} filas x {df.shape[1]} columnas")

    fraud_rate = siniestros["etiqueta_fraude_simulada"].mean() * 100
    print(f"\n  Tasa de fraude simulada: {fraud_rate:.1f}%")
    return used_seed


if __name__ == "__main__":
    main()
