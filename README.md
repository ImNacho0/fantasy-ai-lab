# 🧪 Fantasy AI Lab

**Fantasy AI Lab** es un sistema autónomo de simulación, aprendizaje continuo y modelado de estrategias para aplicaciones de Fantasy Football. Funciona como un laboratorio de experimentación diseñado para integrarse de forma desacoplada con plataformas existentes como `fantasy-manager`.

Este proyecto está estructurado desde el primer día para funcionar con **infraestructura de coste 0 €**, utilizando GitHub Actions como motor gratuito de simulación a gran escala, y Render Free para consultas interactivas de la API y visualización de paneles.

---

## 🚀 Características Clave de la Fase 1

- **Motor de Simulación Determinista y Persistente**: Simulación real de múltiples ligas, managers, jornadas de liga, puntuación de jugadores, mercado de transferencias, pujas y liquidación de ofertas.
- **Reproducibilidad Absoluta**: El uso de un sistema de semillas jerárquicas garantiza que la misma semilla genere idénticos resultados, incluso con IDs autoincrementales cambiantes.
- **Snapshots de Jornada**: Congela el estado completo de una liga en JSON y restáuralo, bifurca la simulación (`fork`) o reprodúcela (`replay`) para auditar decisiones o simular contrafactuales.
- **Resiliencia y Checkpoints**: Los trabajos de simulación (`SimulationJob`) registran checkpoints al final de cada liga. Si el corredor se interrumpe, se puede reanudar sin duplicados ni pérdida de progreso.
- **Inyección de Escenarios Extremos**: Permite programar eventos catastróficos o de alta volatilidad (ej. `STAR_PLAYER_INJURED`, `MARKET_CRASH`) y evaluar la respuesta de los agentes.
- **Almacenamiento de Conocimiento**: Registra sistemáticamente cada situación contextual, decisión, resultado y métrica de recompensa, sentando las bases operativas para el aprendizaje por refuerzo y búsqueda de patrones de similitud.
- **FastAPI API & Dashboard Web**: Interfaz REST completa para integraciones desacopladas de recomendación y un panel de control interactivo para monitorizar estadísticas en tiempo real.

---

## 🧠 Características Clave de la Fase 2

- **Estrategias Desacopladas y Configurables**: Las políticas de decisión se han separado de los agentes (`BaseStrategy`), y se rigen por pesos y tolerancias validables y serializables mediante **Pydantic**.
- **9 Perfiles de Agentes Inteligentes**:
  - `Conservative`: Reduce riesgos de plantilla, evita comprar lesionados y prioriza liquidez.
  - `Aggressive`: Arriesga capital pujando fuertemente por estrellas y tolera lesiones.
  - `Trader`: Compra jugadores infravalorados y vende durante breakouts para maximizar plusvalías.
  - `PointsMaximizer`: Prioriza el rendimiento inmediato basándose en puntos esperados xP.
  - `LongTerm`: Apuesta por jugadores consistentes con xP alto a largo plazo.
  - `Opportunistic`: Rastrea y compra gangas y rebajas extremas del mercado.
  - `BudgetManager`: Controla estrictamente el flujo de caja, restringiendo fichajes caros.
  - `Balanced`: Combina equilibradamente todos los pesos tácticos y presupuestarios.
  - `RandomBaseline`: Actúa de forma pseudoaleatoria determinista para servir de línea de comparación.
- **Contextos y Decisiones Enriquecidos**: Cada decisión guarda las estimaciones previas (`expected_outcome` como puntos, crecimiento y riesgo), el nivel de confianza (entre 0.0 y 1.0), todas las opciones viables (`availableActions`) y alternativas descartadas (`alternativeActions`).
- **Sistema Multicriterio de Recompensas (Rewards)**: Evalúa cada decisión bajo 4 perfiles independientes y persistidos de manera separada de los resultados físicos (`Outcome`): `points-focused`, `wealth-focused`, `balanced`, y `risk-adjusted`.

---

## 🛠️ Stack Tecnológico

- **Python 3.12**
- **FastAPI** (API Web de consulta y recomendación)
- **SQLAlchemy** (ORM con soporte dinámico para PostgreSQL y SQLite)
- **Alembic** (Control de versiones de base de datos)
- **pytest** (Suite exhaustiva de pruebas unitarias y de integración)
- **Docker & Docker Compose** (Despliegue local unificado)

---

## 📂 Arquitectura del Repositorio

La arquitectura sigue una separación limpia y modular conforme a los requisitos:

```text
fantasy-ai-lab/
│
├── .github/
│   └── workflows/
│       └── simulate.yml        # Ejecutor de simulaciones en GitHub Actions
│
├── src/
│   ├── fantasy_ai_lab/
│   │   ├── api/
│   │   │   └── main.py          # Servidor FastAPI y Endpoints REST
│   │   │
│   │   ├── simulator/
│   │   │   ├── engine.py        # Orquestación de Ligas (SimulationEngine)
│   │   │   ├── matchday.py      # Flujo de Jornada (MatchdayEngine)
│   │   │   ├── market.py        # Mercado de Fichajes y Pujas (MarketEngine)
│   │   │   ├── scoring.py       # Cálculo estocástico de puntos (ScoringEngine)
│   │   │   ├── events.py        # Motor de Lesiones y Sanciones (EventEngine)
│   │   │   └── snapshots.py     # Serialización y bifurcación (SnapshotService)
│   │   │
│   │   ├── data/
│   │   │   └── provider.py      # Generador de datos reproducibles (MockDataProvider)
│   │   │
│   │   ├── agents/
│   │   │   └── base.py          # Interfaz BaseAgent
│   │   │
│   │   ├── strategy/
│   │   │   └── base.py          # Clase abstracta BaseStrategy y perfiles configurables de la Fase 2
│   │   │
│   │   ├── database/
│   │   │   ├── connection.py    # Conexión ORM y soporte de motores
│   │   │   └── models.py        # Modelos declarativos SQLAlchemy
│   │   │
│   │   ├── config.py            # Configuraciones y variables de entorno
│   │   └── simulate.py          # CLI de ejecución del simulador
│
├── tests/                       # Suite de tests con pytest (test_core, test_phase2, etc.)
├── migrations/                  # Versiones de esquema de base de datos Alembic
├── docs/                        # Documentación detallada por módulo
├── requirements.txt             # Dependencias del proyecto
├── Dockerfile                   # Empaquetado para despliegue
├── docker-compose.yml           # Orquestador local Docker
└── .env.example                 # Variables de entorno de referencia
```

---

## 💻 Guía de Inicio Rápido (Local)

### 1. Clonar el repositorio y configurar variables de entorno
```bash
git checkout feature/phase-2-agents-strategies
python setup_env.py
```
El archivo `.env` se creará automáticamente con SQLite local por defecto:
`DATABASE_URL=sqlite:///fantasy_ai.db`

### 2. Instalar dependencias y ejecutar migraciones
```bash
pip install -r requirements.txt
alembic upgrade head
```

### 3. Ejecutar una simulación de prueba con múltiples agentes autónomos desde CLI
```bash
PYTHONPATH=src python -m fantasy_ai_lab.simulate --leagues 3 --matchdays 5 --seed 42
```

### 4. Levantar la API de FastAPI y el Dashboard Web
```bash
uvicorn src.fantasy_ai_lab.api.main:app --reload --port 8000
```
- **Documentación Swagger**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Dashboard Web**: [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)

---

## 🐳 Ejecución con Docker Compose (PostgreSQL)

Para levantar la base de datos PostgreSQL y la API en contenedores aislados:

```bash
docker-compose up --build
```
La API estará accesible en el puerto `8000` y conectada al contenedor PostgreSQL.

---

## 🧪 Ejecución de Tests

La suite completa de tests de integración, reproducción determinista, snapshots y APIs se ejecuta mediante:

```bash
PYTHONPATH=. pytest
```

---

## 📖 Documentación Detallada

Para comprender a fondo cada aspecto del laboratorio, consulta los documentos de diseño en la carpeta `docs/`:
- [Arquitectura Conceptual](docs/architecture.md)
- [Simulación y Determinismo](docs/simulation.md)
- [Modelos y Persistencia SQL](docs/database.md)
- [Endpoints de la API](docs/api.md)
- [Snapshots, Forks y Replays](docs/snapshots.md)
- [Integración con GitHub Actions](docs/github-actions.md)
- [Agentes Autónomos (Fase 2)](docs/agents.md)
- [Estrategias Configurables (Fase 2)](docs/strategies.md)
- [Estructura de Decisiones (Fase 2)](docs/decisions.md)
- [Sistema de Recompensas (Fase 2)](docs/rewards.md)
