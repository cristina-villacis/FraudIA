# Reglas de Negocio para Detección de Fraude

## Señales de Posible Fraude (Scoring)

| # | Señal | Máx. Pts | Criterio |
|---|-------|----------|----------|
| 1 | Reclamo cercano al borde de vigencia | 8 | ≤10 días: 8pts, 11-30: 4pts |
| 2 | Demora denuncia por robo | 8 | >48h: 8pts, 24-48h: 4pts |
| 3 | Alta frecuencia reclamos Asegurado | 8 | ≥3: 8pts, 2: 4pts |
| 4 | Alta frecuencia reclamos Vehículo | 6 | ≥3: 6pts, 2: 3pts |
| 5 | Alta frecuencia conductor | 8 | ≥3: 8pts, 2: 4pts |
| 6 | Alta frecuencia solo RC | 6 | >2: 6pts, 1: 3pts |
| 7 | Proveedor recurrente | 10 | Lista Restrictiva: 10pts, >2 casos: 5pts |
| 8 | Documentos incompletos | 4 | Falta doc obligatorio: 4pts |
| 9 | Documentos inconsistentes | 10 | Alteración/inconsistencia: 10pts |
| 10 | Reporte tardío | 5 | >7 días: 5pts, 4-7: 3pts |
| 11 | Narrativas similares | 8 | >85%: 8pts, 70-84%: 4pts |
| 12 | Monto cercano a suma asegurada | 5 | >95% suma o +50% promedio: 4-5pts |

**Score máximo teórico**: 86 puntos (normalizado a escala 0-100)

## Reglas Críticas (RF-01 … RF-07)

| Código | Regla | Clasificación | Criterio en sistema |
|--------|-------|---------------|---------------------|
| RF-01 | Cobertura Pérdida Total por Robo (PTxRB) | Rojo | Cobertura PTxRB o combinación pérdida total + robo |
| RF-02 | Falsificación o adulteración documental evidente | Rojo | Inconsistencia documental, flag o texto en descripción |
| RF-03 | Asegurado, beneficiario o APS en lista restrictiva | Rojo | `aseg_`, `prov_`/`beneficiario` o conductor = asegurado en lista |
| RF-04 | Dinámica del accidente físicamente imposible | Rojo | Flag o narrativa con patrones de imposibilidad física |
| RF-05 | Siniestro extremo al borde de vigencia (< 48 h) | Amarillo | Menos de 48 h desde inicio o fin de póliza |
| RF-06 | Demora atípica en denuncia de robo (> 4 días) | Amarillo | Cobertura de robo y más de 4 días hasta el reporte |
| RF-07 | Narrativa idéntica (clonada) | Amarillo | Similitud textual ≥ 90 % con otro reclamo |

Las reglas **rojas** fuerzan semáforo **Rojo** (score mínimo 76). Las **amarillas** elevan al menos a **Amarillo** (score mínimo 41). Los códigos activos se guardan en `reglas_criticas`.

## Clasificación por Semáforo (Score de riesgo sugerido)

| Rango | Nivel | Semáforo | Acción sugerida |
|-------|-------|----------|-----------------|
| 0 - 40 | Bajo | 🟢 Verde | Continuar flujo normal. |
| 41 - 75 | Medio | 🟡 Amarillo | Escala a Unidad Antifraude para revisión documental. |
| 76 - 100 | Alto | 🔴 Rojo | Escala Unidad Antifraude para revisión especializada de campo. |

## Score Híbrido

El score final combina tres componentes:
- **Reglas de negocio** (40%): Señales basadas en experiencia del negocio
- **Modelo ML supervisado** (35%): Probabilidad de fraude por Random Forest
- **Detección de anomalías** (25%): Score de Isolation Forest

```
Score_Final = (Score_Reglas × 0.40) + (Prob_ML × 0.35) + (Score_Anomalía × 0.25)
```

## Limitaciones

- Las reglas son configurables y deben ajustarse según la experiencia real
- El modelo supervisado depende de la calidad de la etiqueta de fraude
- El sistema NO acusa de fraude; identifica casos para revisión humana
- Los umbrales de semáforo son ajustables según la tolerancia al riesgo
