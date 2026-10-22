# Diagramas de Arquitectura: Monolito Limpio MVC hacia Arquitectura Hexagonal y Microservicios

- **Cliente:** ABC Software Corp (Comercializadora Mayorista y Minorista de Abarrotes)
- **Estándares Tributarios:** RS N° 097-2012/SUNAT (`UBL-Invoice-2.1.xsd`, Catálogos 01, 02, 05, 07, 08) y RS N° 234-2006/SUNAT (Kardex Formato 13.1).
- **Estrategia Evolutiva:** *Clean MVC Hexagonal-Ready* (Fase 1) $\rightarrow$ *Ports & Adapters / Microservicios* (Fase 2).

---

## 1. Diagrama 1: Estado Inicial — Monolito Limpio MVC con Puertos Desacoplados (Hexagonal-Ready)

En el **Estado Inicial**, la aplicación se despliega como un **Monolito Limpio MVC** empaquetado nativamente para **Windows (`.MSI`)** y **Android (`.APK`)**.
La clave arquitectónica es el **Principio de Inversión de Dependencias (DIP)**:
- La capa `views/` (Vista) invoca a `controllers/` (Controlador).
- Los `controllers/` orquestan la lógica apoyándose en `models/entities/` y `models/dtos/`.
- **Regla de Oro:** Ni `controllers/` ni `models/` importan clases concretas de `infrastructure/`. Toda salida hacia Base de Datos, Generador/Firmador XML UBL 2.1, Conector OSE/Nubefact o Importador Legacy ocurre exclusivamente a través de **Puertos (`models/ports/i_*_port.py`)**.

```mermaid
graph TD
    subgraph Client_Packages["Distribución Nativa Multiplataforma"]
        WIN_MSI["💻 Windows Desktop (.MSI)<br/>Cajas POS Mayorista / Almacén Central"]
        AND_APK["📱 Android Mobile (.APK)<br/>Preventa en Ruta / Auditoría Kardex"]
    end

    subgraph Clean_MVC_Monolith["Monolito Limpio MVC (Hexagonal-Ready)"]
        
        subgraph View_Layer["CAPA VISTA (src/views/multiplatform_ui/)"]
            UI_SHELL["AppShell (Flet / BeeWare Runtime)"]
            V_POS["PosBillingView<br/>(Emisión Factura/Boleta/Nota Débito Cat.08)"]
            V_KARDEX["KardexAuditView<br/>(Migración Fichas Legacy RS 234-2006)"]
        end

        subgraph Controller_Layer["CAPA CONTROLADOR (src/controllers/)"]
            C_BILL["BillingController<br/>(Orquestador Emisión UBL 2.1)"]
            C_MIG["KardexMigrationController<br/>(Orquestador Ingesta y Trazabilidad)"]
            C_TAX["TaxValidationController<br/>(Validador RUC Mód. 11 y Catálogos)"]
        end

        subgraph Model_Layer["CAPA MODELO / DOMINIO PURO (src/models/)"]
            subgraph Entities_DTOs["Entidades y Contratos (entities/ & dtos/)"]
                E_INV["Invoice & TaxCatalog<br/>(IGV 18%, ISC, ICBPER, Cat. 01/05/07/08)"]
                E_KAR["KardexEntry & Product<br/>(Formato 13.1 SUNAT)"]
                DTO_ALL["InvoiceRequestDTO / LegacyInventoryRecordDTO<br/>(Validación Pydantic + SHA-256)"]
            end

            subgraph Output_Ports["PUERTOS DE SALIDA - Interfaces ABC (src/models/ports/)"]
                P_INV_REPO[["<<interface>><br/>IInvoiceRepository"]]
                P_KAR_REPO[["<<interface>><br/>IKardexRepository"]]
                P_XML_SIGN[["<<interface>><br/>IXmlSignerPort<br/>(UBL 2.1 + XAdES-BES)"]]
                P_OSE_GW[["<<interface>><br/>IOseGatewayPort<br/>(Envío/Consulta CDR)"]]
            end
        end

        subgraph Infra_Layer["CAPA INFRAESTRUCTURA / ADAPTADORES SECUNDARIOS (src/infrastructure/)"]
            A_SQLITE["SqliteRepository<br/>(Persistencia Transaccional Local)"]
            A_CSV["LegacyCsvImporter<br/>(Lector Fichas Informales)"]
            A_UBL["Ubl21XmlBuilder + XadesBesSigner<br/>(lxml + XSD Validator + XMLDSig)"]
            A_OSE["OseRestSoapAdapter<br/>(Conector Nubefact / SUNAT SEE)"]
        end
    end

    subgraph External_Systems["Sistemas Externos y Normativos"]
        LEGACY_DB[("📄 Fichas Almacén Legacy<br/>(fecha, ingreso, salida, producto, nro_doc)")]
        OSE_SUNAT["☁️ OSE / SUNAT SEE<br/>(Nubefact API / WebService CDR)"]
        CERT_X509["🔐 Certificado Digital X.509<br/>(.PFX / .P12 Emisor)"]
    end

    %% Relaciones Vista -> Controlador
    WIN_MSI --> UI_SHELL
    AND_APK --> UI_SHELL
    UI_SHELL --> V_POS
    UI_SHELL --> V_KARDEX
    V_POS --> C_BILL
    V_POS --> C_TAX
    V_KARDEX --> C_MIG

    %% Relaciones Controlador -> Modelo y Puertos
    C_BILL --> E_INV
    C_BILL --> DTO_ALL
    C_BILL --> P_INV_REPO
    C_BILL --> P_XML_SIGN
    C_BILL --> P_OSE_GW

    C_MIG --> E_KAR
    C_MIG --> DTO_ALL
    C_MIG --> P_KAR_REPO
    C_MIG --> P_INV_REPO

    C_TAX --> E_INV

    %% Inversión de Dependencias: Infraestructura implementa Puertos del Modelo
    A_SQLITE -. "implementa" .-> P_INV_REPO
    A_SQLITE -. "implementa" .-> P_KAR_REPO
    A_CSV --> C_MIG
    A_UBL -. "implementa" .-> P_XML_SIGN
    A_OSE -. "implementa" .-> P_OSE_GW

    %% Salidas a Sistemas Externos
    A_CSV --> LEGACY_DB
    A_UBL --> CERT_X509
    A_OSE --> OSE_SUNAT
```

---

## 2. Diagrama 2: Estado Futuro — Evolución a Arquitectura Hexagonal y Microservicios

Gracias a que el **Modelo (`src/models/`)** no tiene dependencias hacia frameworks de UI ni librerías de infraestructura, en el **Estado Futuro** cuando ABC Software Corp escale a múltiples sucursales y alto volumen mayorista:
1. El paquete `models/` + casos de uso de `controllers/` se consolidan directamente como el **Hexágono de Dominio y Aplicación**.
2. Las Vistas (`.MSI` / `.APK`), un nuevo API Gateway REST/gRPC y los consumidores de colas pasan a ser **Adaptadores Primarios (Driving Adapters)**.
3. Los adaptadores pesados o críticos en regulación (**Motor Generador/Validador XSD UBL 2.1 + Firma XAdES-BES**, **Conector OSE/SUNAT con reintentos asíncronos**, y **Servicio de Inventario Kardex RS 234-2006**) se desprenden como **Microservicios Independientes** sin modificar una sola línea de las reglas tributarias del Dominio.

```mermaid
graph TD
    subgraph Driving_Adapters["ADAPTADORES PRIMARIOS (Driving / Entrada)"]
        UI_WIN["💻 Cliente Windows (.MSI)<br/>POS Mayorista / Almacén"]
        UI_AND["📱 App Android (.APK)<br/>Fuerza de Ventas Móvil"]
        B2B_API["🌐 Portal Web B2B / ERP Externo"]
        CLI_MIG["⚙️ CLI Batch Migrador Legacy"]
    end

    subgraph API_Gateway_Layer["API Gateway & BFF (Backend For Frontend)"]
        APIGW["🚪 Kong / Envoy API Gateway<br/>(Auth JWT, Rate Limiting, Routing)"]
    end

    subgraph Core_Hexagon["HEXÁGONO CENTRAL (Núcleo de Dominio y Aplicación)"]
        subgraph Inbound_Ports["Puertos de Entrada (Use Case Interfaces)"]
            IN_ISSUE[["<<Inbound Port>><br/>IssueElectronicInvoiceUseCase"]]
            IN_DEBIT[["<<Inbound Port>><br/>IssueDebitNoteCat08UseCase"]]
            IN_MIGRATE[["<<Inbound Port>><br/>MigrateLegacyKardexUseCase"]]
            IN_RUC[["<<Inbound Port>><br/>ValidateRucModulo11UseCase"]]
        end

        subgraph Domain_Core["Núcleo de Dominio Puro (Zero External Dependencies)"]
            DOM_TAX["Motor Tributario SUNAT<br/>(IGV, ISC, ICBPER, Cat. 01, 02, 05, 07, 08)"]
            DOM_MOD11["Validador RUC Módulo 11"]
            DOM_KARDEX["Agregado Kardex Formato 13.1<br/>(Trazabilidad SHA-256 + migrated_invoice_id)"]
        end

        subgraph Outbound_Ports["Puertos de Salida (Driven Ports)"]
            OUT_REPO[["<<Outbound Port>><br/>IInvoice & IKardexRepository"]]
            OUT_SIGN[["<<Outbound Port>><br/>IXmlSignerPort"]]
            OUT_OSE[["<<Outbound Port>><br/>IOseGatewayPort"]]
            OUT_EVT[["<<Outbound Port>><br/>IDomainEventPublisher"]]
        end
    end

    subgraph Driven_Adapters_Microservices["ADAPTADORES SECUNDARIOS Y MICROSERVICIOS DESACOPLADOS"]
        
        subgraph MS_Persistence["Clúster de Persistencia"]
            AD_PG["PostgreSQL / SQLite Sync Adapter"]
            DB_MAIN[("🗄️ PostgreSQL HA<br/>Comprobantes & Kardex 13.1")]
        end

        subgraph MS_UBL_Validator["Microservicio 1: UBL 2.1 XSD & Firma Digital (gRPC)"]
            AD_GRPC_UBL["gRPC XmlSigner Adapter"]
            SVC_XSD["Validador Estricto OASIS<br/>UBL-Invoice-2.1.xsd / DebitNote-2.1.xsd"]
            SVC_XADES["Firmador Criptográfico XAdES-BES<br/>(HSM / Vault PKCS#12)"]
        end

        subgraph MS_OSE_Connector["Microservicio 2: Conector OSE / SUNAT Resiliente"]
            AD_BROKER["RabbitMQ / Kafka Event Adapter"]
            SVC_OSE_WORKER["Worker OSE / PSE (Nubefact / SUNAT SOAP)<br/>Circuit Breaker + Retry Queue"]
            SVC_CDR_STORE[("📦 Almacén Inmutable XML & CDR<br/>(S3 / MinIO - 5 años RS 097-2012)")]
        end
    end

    subgraph External_SUNAT["Entidades Reguladoras"]
        EXT_OSE["☁️ OSE Nubefact / SUNAT SEE"]
    end

    %% Flujo de Entrada
    UI_WIN --> APIGW
    UI_AND --> APIGW
    B2B_API --> APIGW
    CLI_MIG --> APIGW

    APIGW --> IN_ISSUE
    APIGW --> IN_DEBIT
    APIGW --> IN_MIGRATE
    APIGW --> IN_RUC

    %% Conexión Interna del Hexágono
    IN_ISSUE --> DOM_TAX
    IN_DEBIT --> DOM_TAX
    IN_MIGRATE --> DOM_KARDEX
    IN_RUC --> DOM_MOD11

    DOM_TAX --> OUT_REPO
    DOM_TAX --> OUT_SIGN
    DOM_TAX --> OUT_OSE
    DOM_KARDEX --> OUT_REPO
    DOM_KARDEX --> OUT_EVT

    %% Salida hacia Adaptadores y Microservicios
    OUT_REPO -. "implementado por" .-> AD_PG
    AD_PG --> DB_MAIN

    OUT_SIGN -. "implementado por" .-> AD_GRPC_UBL
    AD_GRPC_UBL --> SVC_XSD
    SVC_XSD --> SVC_XADES

    OUT_OSE -. "implementado por" .-> AD_BROKER
    OUT_EVT -. "implementado por" .-> AD_BROKER
    AD_BROKER --> SVC_OSE_WORKER
    SVC_OSE_WORKER --> SVC_CDR_STORE
    SVC_OSE_WORKER --> EXT_OSE
```

---

## 3. Comparativa de Transición Arquitectónica (Fase 1 vs. Fase 2)

| Dimensión | Fase 1: Monolito Limpio MVC (Actual) | Fase 2: Hexagonal + Microservicios (Futuro) | Impacto en `src/models/` (Dominio) |
|:---|:---|:---|:---|
| **Comunicación UI $\rightarrow$ Lógica** | Llamada en memoria `View` $\rightarrow$ `Controller` | Llamada HTTP/REST o gRPC vía API Gateway $\rightarrow$ `Inbound Port` | **0% cambios** en entidades y DTOs |
| **Generación y Firma UBL 2.1** | Adaptador local `Ubl21XmlBuilder` + `XadesBesSigner` | Microservicio gRPC dedicado con validación `UBL-Invoice-2.1.xsd` y HSM | **0% cambios** (se inyecta `GrpcXmlSignerAdapter` en `IXmlSignerPort`) |
| **Envío a OSE / SUNAT** | Adaptador HTTP/SOAP `OseRestSoapAdapter` | Microservicio Worker asíncrono con colas, Circuit Breaker y archivo S3 de CDRs | **0% cambios** (se inyecta `AsyncOseGatewayAdapter` en `IOseGatewayPort`) |
| **Persistencia Kardex (RS 234-2006)** | `SqliteRepository` embebido (offline-first en `.MSI`/`.APK`) | `PostgresRepository` centralizado + sincronización de bordes | **0% cambios** (ambos implementan `IKardexRepository`) |
