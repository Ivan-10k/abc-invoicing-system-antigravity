# ADR-0001: Arquitectura Monolítica Limpia MVC con Transición Planificada a Arquitectura Hexagonal y Microservicios

- **Estado:** Aceptado
- **Fecha:** 2026-10-22
- **Decisores:** Equipo de Arquitectura Senior & ABC Software Corp
- **Requisitos Vinculados:** FEAT-001 (CU-01 a CU-05), RS N° 097-2012/SUNAT, RS N° 234-2006/SUNAT

---

## 1. Contexto y Problemática

**ABC Software Corp** opera tanto en venta mayorista como minorista de abarrotes. Actualmente adolece de dos problemas críticos:
1. Un sistema legacy de almacén que registra movimientos en fichas informales (`fecha`, `ingreso`, `salida`, `producto`, `nro_documento`) sin estructura contable ni vínculo a comprobantes electrónicos.
2. La urgencia regulatoria de emitir Facturas (`01`), Boletas (`03`), Notas de Crédito (`07`) y Notas de Débito (`08` con **Catálogo 08**) bajo el estándar OASIS `UBL-Invoice-2.1.xsd`, validando RUCs con **Módulo 11** y desglosando **IGV, ISC e ICBPER**.

El equipo de ingeniería requiere un arranque rápido, mantenible y comprensible (**patrón MVC**) que pueda empaquetarse localmente en instaladores **Windows (`.MSI`)** y **Android (`.APK`)**, pero que **evite el acoplamiento clásico de los monolitos MVC** para permitir que, en una segunda etapa, el motor de firma UBL 2.1 y el conector OSE/SUNAT se desprendan como **Microservicios bajo Arquitectura Hexagonal (Ports & Adapters)**.

---

## 2. Decisión Arquitectónica

Adoptamos el patrón **Clean MVC Hexagonal-Ready** (Monolito Limpio MVC con Puertos Desacoplados) estructurado bajo las siguientes reglas estrictas de dependencia:

1. **El Modelo (`src/models/`) es el Núcleo del Hexágono:**
   - Contiene `entities/` (reglas tributarias puras), `dtos/` (contratos Pydantic inmutables) y `ports/` (interfaces abstractas `ABC` / `Protocol`).
   - **Prohibición estricta:** Ningún archivo dentro de `src/models/` puede importar librerías de base de datos (`sqlite3`, `sqlalchemy`), clientes HTTP (`httpx`, `requests`), procesadores XML externos ni componentes gráficos de `src/views/`.

2. **Los Controladores (`src/controllers/`) actúan como Casos de Uso / Servicios de Aplicación:**
   - Reciben DTOs validados desde la Vista (`src/views/`) o desde tests automatizados.
   - Orquestan el flujo invocando entidades del Modelo y comunicándose con el exterior **únicamente a través de los Puertos definidos en `src/models/ports/`**:
     - `IInvoiceRepository` (persistencia de comprobantes y estado CDR).
     - `IKardexRepository` (persistencia del Formato 13.1 RS 234-2006 y trazabilidad `migrated_invoice_id`).
     - `IXmlSignerPort` (construcción del árbol XML `UBL-Invoice-2.1.xsd`, validación XSD y firma digital XMLDSig / XAdES-BES).
     - `IOseGatewayPort` (envío síncrono/asíncrono a OSE estilo Nubefact o SUNAT SEE y descarga de CDR).

3. **La Infraestructura (`src/infrastructure/`) contiene los Adaptadores Secundarios (Driven Adapters):**
   - Implementa explícitamente las interfaces de `src/models/ports/`.
   - La inyección de dependencias se realiza en el punto de ensamblaje (`app_shell.py` o *Composition Root*), permitiendo sustituir un `SqliteRepository` o `LocalXmlSignerAdapter` por un `GrpcXmlSignerAdapter` o `RabbitMqOseAdapter` sin tocar ni el Modelo ni los Controladores.

---

## 3. Estrategia de Evolución Gradual (Strangler Fig / Hexagonal Extraction)

| Etapa | Topología | Mecanismo de Desacoplamiento |
|:---|:---|:---|
| **Fase 1 (Actual)** | Monolito Limpio MVC en `.MSI` y `.APK` | Inyección en memoria de adaptadores locales (`SqliteRepository`, `Ubl21XmlBuilder`, `OseRestSoapAdapter`). |
| **Fase 2 (Crecimiento Mayorista)** | Hexagonal Distribuido (Cliente Ligero + Core Central) | Las Vistas `.MSI`/`.APK` consumen un `HttpControllerAdapter` (Driving Adapter) que expone los mismos Controladores vía FastAPI/gRPC. |
| **Fase 3 (Alta Escala / Multi-Sede)** | Microservicios Especializados | `IXmlSignerPort` y `IOseGatewayPort` delegan por red a los microservicios independientes `ms-ubl-xsd-signer` y `ms-ose-sunat-connector`. |

---

## 4. Consecuencias

### Positivas
- **Cero reescritura de reglas SUNAT:** El cálculo de IGV/ISC/ICBPER, la validación de RUC Módulo 11, las reglas del Catálogo 08 y la trazabilidad SHA-256 de fichas legacy se escriben una sola vez en `src/models/` y sobreviven intactos el paso a microservicios.
- **Testabilidad Unitaria y BDD al 100%:** Los controladores y entidades se prueban en milisegundos inyectando *Fakes/Mocks* de los puertos (`FakeOseGateway`, `InMemoryKardexRepo`) sin requerir certificados digitales reales ni conexión a SUNAT.

### Negativas / Trade-offs
- **Mayor disciplina inicial:** Exige definir interfaces (`ports/`) y DTOs explícitos antes de programar la infraestructura, lo cual se mitiga mediante nuestra metodología **Spec-First (SDD)**.
