# Limitaciones del Sistema

## Limitaciones de Datos

1. **Datos sintéticos**: El prototipo usa datos generados artificialmente. Los patrones de fraude real pueden ser más complejos y sutiles.

2. **Etiqueta simulada**: La variable `etiqueta_fraude_simulada` fue generada con reglas conocidas, lo que puede crear sesgo circular en el modelo supervisado.

3. **Volumen limitado**: 1,500 siniestros es un volumen reducido para un modelo de producción. Se recomienda mínimo 10,000+ registros reales.

4. **Sin datos temporales reales**: Las fechas son sintéticas y no reflejan estacionalidad real del negocio.

## Limitaciones del Modelo

1. **Random Forest**: Modelo interpretable pero no el más potente. Para producción considerar Gradient Boosting (XGBoost/LightGBM) o redes neuronales.

2. **Desbalanceo**: Aunque se usa class_weight="balanced", un desbalanceo extremo (fraude <1%) requiere técnicas adicionales (SMOTE, undersampling).

3. **Feature drift**: Los patrones de fraude evolucionan. El modelo requiere reentrenamiento periódico.

4. **Sin datos externos**: No se integran fuentes externas (listas negras, bases judiciales, redes sociales).

## Limitaciones de NLP

1. **TF-IDF básico**: La similitud textual usa TF-IDF. Modelos de embeddings contextuales (BERT, Sentence-BERT) darían mejores resultados.

2. **Sin análisis semántico profundo**: No se detectan contradicciones lógicas en narrativas.

3. **Idioma**: Optimizado para español, pero las stopwords y el preprocesamiento son básicos.

## Limitaciones de Producción

1. **Escalabilidad**: Flask no es adecuado para alta concurrencia. Considerar FastAPI + Celery + Redis.

2. **Persistencia**: Los datos se mantienen en memoria durante la sesión. Para producción usar base de datos (PostgreSQL).

3. **Seguridad**: Sin autenticación ni autorización implementada.

4. **Sin monitoreo MLOps**: No hay tracking de experimentos, versionado de modelos ni monitoreo de drift.

## Arquitectura Futura Sugerida

```
[Load Balancer]
      │
[FastAPI / Gunicorn]  ←  [Celery Workers]
      │                        │
[PostgreSQL]            [Redis Queue]
      │                        │
[MLflow / Model Registry]  [Monitoring (Grafana)]
      │
[Power BI Gateway / API REST]
```

### Mejoras propuestas:
- Base de datos relacional (PostgreSQL) para persistencia
- Cache con Redis para consultas frecuentes
- Celery para procesamiento asíncrono de pipelines
- MLflow para gestión de experimentos
- API REST documentada (OpenAPI/Swagger)
- Autenticación (JWT/OAuth2)
- Dashboard en tiempo real con WebSockets
- Integración con Power BI Gateway para actualización automática
- Modelos de NLP avanzados (transformers multilingües)
- Grafos de relaciones (Neo4j) para detectar redes de fraude
