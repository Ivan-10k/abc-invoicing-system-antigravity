# FEAT-001: Facturación Electrónica SUNAT UBL 2.1 y Migración de Almacén Legacy

- **Estado:** Aprobado (Spec-First Baseline)
- **Organización:** ABC Software Corp (Mayorista y Minorista de Abarrotes)
- **Marco Normativo:**
  - **RS N° 097-2012/SUNAT:** Sistema de Emisión Electrónica (SEE) del Contribuyente (Estándar OASIS `UBL-Invoice-2.1.xsd`, `UBL-CreditNote-2.1.xsd`, `UBL-DebitNote-2.1.xsd`).
  - **RS N° 234-2006/SUNAT:** Libro de Inventarios y Balances - Formato 13.1 (Registro de Inventario Permanente Valorizado - Kardex).
  - **Anexo N° 8 SUNAT:** Catálogos Oficiales (Catálogo 01, 02, 05, 06, 07, 08, 09, 10).
- **Inspiración de Flujo OSE/PSE:** API transaccional estilo Nubefact (`generar_comprobante`, `consultar_comprobante`, CDR asíncrono/síncrono).

---

## 1. Catálogo de Casos de Uso Descubiertos

| ID | Caso de Uso | Actor Primario | Normativa / Estándar | Flujo OSE / Nubefact Equivalente |
|:---|:---|:---|:---|:---|
| **CU-01** | **Emitir Factura / Boleta de Venta Electrónica UBL 2.1** | Cajero POS / Preventa Móvil | RS 097-2012, Cat. 01 (`01`, `03`), Cat. 02, Cat. 05, Cat. 07 | `operacion: "generar_comprobante"` (tipo 1 y 2) |
| **CU-02** | **Emitir Nota de Débito / Crédito Electrónica con Catálogo 08** | Supervisor de Facturación | RS 097-2012, Cat. 01 (`07`, `08`), **Cat. 08** (`01`, `02`, `03`, `10`, `11`) | `operacion: "generar_comprobante"` (tipo 3 y 4) |
| **CU-03** | **Validar RUC con Algoritmo Módulo 11** | Sistema / Cajero POS | Padrón RUC SUNAT (11 dígitos, prefijos `10`, `15`, `17`, `20`) | Validación previa a emisión (`cliente_numero_de_documento`) |
| **CU-04** | **Migrar Ficha de Almacén Legacy a Comprobante y Kardex** | Auditor de Almacén | RS 234-2006 (Formato 13.1), Trazabilidad bidireccional | Ingesta histórica + vinculación `migrated_invoice_id` |
| **CU-05** | **Consultar Estado CDR / OSE (Constancia de Recepción)** | Sistema / Facturador | RS 097-2012 (Códigos CDR `0`, `2000-2999`, `4000+`) | `operacion: "consultar_comprobante"` |

---

## 2. Especificaciones BDD (Gherkin) y Criterios de Aceptación

### CU-01: Emitir Factura / Boleta Electrónica UBL 2.1 con IGV, ISC e ICBPER

```gherkin
# language: es
Característica: Emisión de Factura y Boleta Electrónica bajo estándar OASIS UBL 2.1
  Como cajero de ABC Software Corp (mayorista y minorista de abarrotes)
  Quiero emitir facturas (Catálogo 01 = '01') y boletas (Catálogo 01 = '03') calculando IGV, ISC e ICBPER
  Para cumplir con la RS N° 097-2012/SUNAT y obtener el CDR de aceptación del OSE

  Antecedentes:
    Dado que el emisor "ABC SOFTWARE CORP S.A.C." tiene RUC válido "20601234568"
    Y el certificado digital X.509 para firma XMLDSig se encuentra vigente
    Y la tasa vigente de IGV es 18.00% y la tarifa ICBPER es S/ 0.50 por bolsa plástica

  Escenario: AC-01.1 - Emisión exitosa de Factura Mayorista con IGV (Cat. 07 = '10'), ISC e ICBPER
    Dado un cliente mayorista con RUC válido "20512345679" y razón social "BODEGA CENTRAL S.A.C."
    Y una solicitud de Factura serie "F001" correlativo 1045 en moneda "PEN" (Catálogo 02)
    Con las siguientes líneas de detalle de abarrotes:
      | sku       | descripcion                    | cantidad | valor_unitario | cat_07 | tasa_isc | aplica_icbper |
      | AB-ARR-50 | Saco Arroz Extra 50kg          | 10       | 120.00         | 10     | 0.00     | false         |
      | BE-LIC-12 | Caja Licor Ron Cartavio x12    | 2        | 250.00         | 10     | 0.20     | false         |
      | EMP-BOL-G | Bolsa Plástica Biodegradable L | 4        | 0.10           | 10     | 0.00     | true          |
    Cuando el controlador de facturación procesa la emisión del comprobante
    Entonces el cálculo tributario del comprobante debe ser exactamente:
      | concepto                      | monto_pen |
      | total_gravadas (Base IGV)     | 1700.40   |
      | total_isc (Catálogo 05=2000)  | 100.00    |
      | total_igv (Catálogo 05=1000)  | 324.07    |
      | total_icbper (Cat. 05=7152)   | 2.00      |
      | importe_total                 | 2126.47   |
    Y se genera el XML conforme a "UBL-Invoice-2.1.xsd" con UBLVersionID "2.1" y CustomizationID "2.0"
    Y el XML es firmado digitalmente y enviado al OSE retornando estado "ACEPTADO" con código CDR "0"
```

---

### CU-02: Emitir Nota de Débito / Crédito con Catálogo 08 SUNAT

```gherkin
# language: es
Característica: Emisión de Notas de Débito vinculadas mediante Catálogo 08 de SUNAT
  Como supervisor de facturación de ABC Software Corp
  Quiero emitir Notas de Débito Electrónicas aplicando el Catálogo 08 de SUNAT
  Para ajustar intereses por mora, aumentos en el valor o penalidades sobre facturas previamente aceptadas

  Escenario: AC-02.1 - Emisión de Nota de Débito por Aumento en el Valor (Catálogo 08 = '02')
    Dada una Factura origen "F001-1045" previamente aceptada en SUNAT con RUC cliente "20512345679"
    Cuando emito una Nota de Débito serie "FD01" correlativo 15 con Tipo de Documento "08" (Catálogo 01)
    Y selecciono el código de motivo "02" del Catálogo 08 ("Aumento en el valor")
    Y agrego el sustento "Ajuste de precio mayorista en Saco Arroz Extra 50kg según adenda comercial"
    Por un valor de venta adicional gravado de S/ 100.00 más S/ 18.00 de IGV
    Entonces el nodo XML "<cac:DiscrepancyResponse>" debe incluir "<cbc:ResponseCode listAgencyName='PE:SUNAT' listName='Tipo de nota de debito' listURI='urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo08'>02</cbc:ResponseCode>"
    Y el nodo "<cac:BillingReference>" debe referenciar al documento "F001-1045" con tipo "01"
    Y el comprobante resulta con importe total S/ 118.00 listo para envío al OSE

  Esquema del escenario: AC-02.2 - Validación estricta de códigos permitidos en el Catálogo 08 SUNAT
    Dado un documento electrónico de tipo "08" (Nota de Débito)
    Cuando se asigna el código de Catálogo 08 "<codigo_cat_08>" con descripción "<descripcion>"
    Entonces el resultado de validación de dominio debe ser "<resultado>"

    Ejemplos:
      | codigo_cat_08 | descripcion                                   | resultado |
      | 01            | Intereses por mora                            | VALIDO    |
      | 02            | Aumento en el valor                           | VALIDO    |
      | 03            | Penalidades / otros conceptos                 | VALIDO    |
      | 10            | Ajustes de operaciones de exportación         | VALIDO    |
      | 11            | Ajustes afectos al IVAP                       | VALIDO    |
      | 99            | Código inexistente fuera de Anexo 8 SUNAT     | RECHAZADO |
```

---

### CU-03: Validar RUC mediante Algoritmo Módulo 11

```gherkin
# language: es
Característica: Validación algorítmica de RUC peruano con Módulo 11
  Como sistema de facturación y almacén
  Quiero validar cada número de RUC antes de emitir comprobantes o migrar fichas
  Para evitar rechazos OSE (errores 2017 / 2305 de SUNAT)

  Esquema del escenario: AC-03.1 - Verificación de longitud, prefijo y dígito verificador Módulo 11
    Dado el número de documento RUC "<ruc>"
    Cuando se ejecuta el validador de Módulo 11 con pesos [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    Entonces la validación retorna "<es_valido>" y el detalle "<mensaje>"

    Ejemplos:
      | ruc         | es_valido | mensaje                                         |
      | 20601234568 | true      | RUC Persona Jurídica válido (dígito 8 correcto) |
      | 10456789012 | false     | Dígito verificador inválido según Módulo 11     |
      | 30601234568 | false     | Prefijo '30' no permitido por SUNAT             |
      | 206012345   | false     | Longitud inválida (debe tener 11 dígitos)       |
```

---

### CU-04: Migrar Ficha de Almacén Legacy a Comprobante y Kardex (RS N° 234-2006)

```gherkin
# language: es
Característica: Migración de Fichas Informales de Almacén Legacy manteniendo trazabilidad
  Como auditor de almacén de ABC Software Corp
  Quiero migrar los registros históricos ({fecha, ingreso, salida, producto, nro_documento})
  Para cumplir con el Formato 13.1 de la RS N° 234-2006/SUNAT y vincularlos a comprobantes UBL 2.1

  Escenario: AC-04.1 - Migración de salida informal legacy y acoplamiento con comprobante electrónico
    Dada una ficha informal del sistema legacy con los datos:
      | fecha      | ingreso | salida | producto              | nro_documento |
      | 2026-10-15 | 0.00    | 25.00  | Azúcar Rubia Saco 50k | F001-000890   |
    Cuando el controlador de migración procesa la ficha legacy
    Entonces se normaliza el documento "F001-000890" separando serie "F001" y correlativo 890
    Y se clasifica como operación de "SALIDA_VENTA" (Tabla 12 SUNAT: Código "01" Venta)
    Y se genera o vincula el identificador inmutable "migrated_invoice_id" y un hash SHA-256 de auditoría
    Y la ficha migrada conserva el valor original de "nro_documento" para trazabilidad histórica 100% auditable

  Escenario: AC-04.2 - Rechazo de ficha legacy inconsistente (ingreso y salida simultáneos o negativos)
    Dada una ficha informal legacy con "ingreso" = 10.00 y "salida" = 5.00 en la misma línea
    Cuando el controlador de migración intenta importar el registro
    Entonces se marca en cuarentena con error "LEGACY_KARDEX_AMBIGUOUS_MOVEMENT" sin alterar el saldo Kardex
```

---

### CU-05: Consultar Estado CDR / OSE (Flujo Asíncrono y Síncrono tipo Nubefact)

```gherkin
# language: es
Característica: Consulta de Estado CDR y manejo de observaciones/rechazos SUNAT/OSE
  Como sistema de facturación de ABC Software Corp
  Quiero consultar el estado de un comprobante enviado a SUNAT o al OSE
  Para almacenar el archivo XML del CDR, su hash y actualizar el estado tributario del documento

  Escenario: AC-05.1 - Recepción de CDR Aceptado con Observaciones (Códigos 4000+)
    Dado que la Factura "F001-1045" fue enviada al OSE con ticket o identificador de operación
    Cuando consulto el estado del comprobante mediante el puerto "IOseGatewayPort"
    Y el OSE responde con "sunat_responsecode" = "0" y nota "4252 - El RUC del receptor no está afecto a detracciones"
    Entonces el comprobante pasa a estado "ACEPTADO_CON_OBSERVACIONES"
    Y se registra el hash del resumen ("DigestValue"), el enlace al XML firmado y la lista de observaciones SUNAT
```
