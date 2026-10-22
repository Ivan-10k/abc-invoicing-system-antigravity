# Matriz de Trazabilidad Normativa: SUNAT (RS N° 097-2012 / RS N° 234-2006) vs. OASIS `UBL-Invoice-2.1.xsd`

- **Organización:** ABC Software Corp (Mayorista y Minorista de Abarrotes)
- **Propósito:** Garantizar trazabilidad 1:1 entre la normativa tributaria peruana, los campos del sistema legacy/dominio (`LegacyInventoryRecordDTO` e `InvoiceRequestDTO`), los nodos XPath exactos de los esquemas OASIS `UBL-Invoice-2.1.xsd` / `UBL-DebitNote-2.1.xsd` y las reglas de validación XSD y de negocio OSE/SUNAT.

---

## 1. Espacios de Nombres XML Oficiales (Namespaces OASIS UBL 2.1 + SUNAT)

| Prefijo | Namespace URI | Uso en el Comprobante Electrónico |
|:---|:---|:---|
| `(default)` | `urn:oasis:names:specification:ubl:schema:xsd:Invoice-2` | Nodo raíz `<Invoice>` (Facturas `01` y Boletas `03`) |
| `(default ND)` | `urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2` | Nodo raíz `<DebitNote>` (Notas de Débito `08` - Catálogo 08) |
| `cac` | `urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2` | Componentes agregados (`AccountingSupplierParty`, `TaxTotal`, `InvoiceLine`, etc.) |
| `cbc` | `urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2` | Elementos básicos de datos (`ID`, `IssueDate`, `TaxAmount`, `PayableAmount`, etc.) |
| `ext` | `urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2` | Contenedor `<ext:UBLExtensions>` para incrustar la firma digital XMLDSig |
| `ds` | `http://www.w3.org/2000/09/xmldsig#` | Firma criptográfica W3C XML Signature (`<ds:Signature>`, `<ds:DigestValue>`) |

---

## 2. Matriz Exhaustiva de Trazabilidad Normativa (Legacy + Facturación UBL 2.1)

| ID | Requisito Normativo SUNAT / Catálogo | Campo del Negocio / DTO Legacy o Facturación | XPath / Etiqueta Exacta en `UBL-Invoice-2.1.xsd` (`UBL-DebitNote-2.1.xsd`) | Regla de Validación XSD / Regla de Negocio SUNAT (Códigos Error CDR) |
|:---|:---|:---|:---|:---|
| **TR-01** | **RS 097-2012** (Estándar UBL 2.1 y Customización 2.0) | `InvoiceRequestDTO.ubl_version` (`"2.1"`)<br/>`InvoiceRequestDTO.customization_id` (`"2.0"`) | `/Invoice/cbc:UBLVersionID`<br/>`/Invoice/cbc:CustomizationID` | **Regla SUNAT 2074 / 2075:** `cbc:UBLVersionID` debe ser literalmente `"2.1"` y `cbc:CustomizationID` debe ser `"2.0"`. |
| **TR-02** | **RS 097-2012** (Firma Digital X.509 / XMLDSig Enveloped) | Certificado `.PFX` Emisor + `CdrEmitResponse.xml_digest_value` | `/Invoice/ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/ds:Signature`<br/>`.../ds:SignedInfo/ds:Reference/ds:DigestValue` | **Regla SUNAT 2335 / 2022:** El documento electrónico debe estar firmado con certificado digital vigente vinculado al RUC emisor; la transformación debe ser `enveloped-signature` + `C14N`. |
| **TR-03** | **RS 234-2006 (Formato 13.1)** & **RS 097-2012** (Numeración Serie-Correlativo) | **Legacy:** `nro_documento` (ej. `"F001-000890"`)<br/>**Dominio:** `series` (`"F001"`), `correlative` (`890`) | `/Invoice/cbc:ID` | **Regla SUNAT 1001 / XSD:** Formato alfanumérico `^[FB][A-Z0-9]{3}-[0-9]{1,8}$`. En migración legacy se normaliza eliminando ceros a la izquierda en el correlativo y conservando el original con hash `audit_sha256`. |
| **TR-04** | **RS 234-2006 (Formato 13.1)** & **RS 097-2012** (Fecha y Hora de Emisión) | **Legacy:** `fecha` (`YYYY-MM-DD`)<br/>**Dominio:** `issue_date`, `issue_time` | `/Invoice/cbc:IssueDate`<br/>`/Invoice/cbc:IssueTime` | **Tipo XSD `xsd:date` / `xsd:time`:** Formato ISO-8601 `YYYY-MM-DD` y `HH:MM:SS`. **Regla SUNAT 2329:** La fecha de emisión no puede ser mayor a la fecha de recepción ni anterior al plazo máximo de envío (3 días calendario para facturas). |
| **TR-05** | **Catálogo 01 SUNAT** (Código de Tipo de Documento) + **Catálogo 51** (Tipo de Operación) | `document_type_catalog_01` (`"01"`, `"03"`, `"07"`, `"08"`)<br/>`operation_type_catalog_51` (`"0101"`) | `/Invoice/cbc:InvoiceTypeCode`<br/>`@listID="0101"`<br/>`@listAgencyName="PE:SUNAT"`<br/>`@listName="Tipo de Documento"`<br/>`@listURI="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo01"` | **Regla SUNAT 1003 / 2015:** `01`=Factura (serie inicia con `F`), `03`=Boleta (serie inicia con `B`), `07`=Nota de Crédito, `08`=Nota de Débito. El atributo `@listID` debe contener el código del Catálogo 51 (`0101` Venta Interna). |
| **TR-06** | **Catálogo 02 SUNAT** (Moneda ISO 4217) | `currency_code_catalog_02` (`"PEN"`, `"USD"`, `"EUR"`) | `/Invoice/cbc:DocumentCurrencyCode`<br/>`@listID="ISO 4217 Alpha"`<br/>`@listAgencyName="United Nations Economic Commission for Europe"` | **Regla SUNAT 2070:** Código ISO de 3 letras; todos los elementos monetarios (`cbc:LineExtensionAmount`, `cbc:TaxAmount`, `cbc:PayableAmount`) deben llevar `@currencyID` idéntico a `cbc:DocumentCurrencyCode`. |
| **TR-07** | **Padrón RUC SUNAT (Módulo 11)** & **Catálogo 06** (Emisor) | `issuer_ruc` (11 dígitos), `issuer_legal_name`, `issuer_ubigeo` | `/Invoice/cac:AccountingSupplierParty/cac:Party/cac:PartyIdentification/cbc:ID[@schemeID="6"]`<br/>`.../cac:PartyLegalEntity/cbc:RegistrationName`<br/>`.../cac:RegistrationAddress/cbc:AddressTypeCode` | **Algoritmo Módulo 11 + Regla SUNAT 1034 / 2017:** Longitud exacta 11 dígitos, prefijos `10`, `15`, `17`, `20`, validación con pesos `[5, 4, 3, 2, 7, 6, 5, 4, 3, 2]`. `@schemeID="6"` (Catálogo 06 = RUC) y `@schemeURI="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo06"`. |
| **TR-08** | **Padrón RUC SUNAT (Módulo 11)** & **Catálogo 06** (Cliente / Receptor) | `customer_doc_type_catalog_06` (`"6"`, `"1"`, etc.)<br/>`customer_doc_number`, `customer_legal_name` | `/Invoice/cac:AccountingCustomerParty/cac:Party/cac:PartyIdentification/cbc:ID[@schemeID="6"]`<br/>`.../cac:PartyLegalEntity/cbc:RegistrationName` | **Regla SUNAT 2017 / 2800:** Si `InvoiceTypeCode == "01"` (Factura), `@schemeID` del cliente debe ser obligatoriamente `"6"` (RUC) y pasar la validación **Módulo 11**. Si es Boleta (`"03"`), permite `"1"` (DNI) o `"6"` (RUC). |
| **TR-09** | **Catálogo 08 SUNAT** (Códigos de Tipo de Nota de Débito) | `catalog_08_debit_note_type` (`"01"`, `"02"`, `"03"`, `"10"`, `"11"`)<br/>`discrepancy_reason`<br/>`referenced_document_series_number` | `/DebitNote/cac:DiscrepancyResponse/cbc:ReferenceID`<br/>`/DebitNote/cac:DiscrepancyResponse/cbc:ResponseCode[@listName="Tipo de nota de debito"][@listURI="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo08"]`<br/>`/DebitNote/cac:DiscrepancyResponse/cbc:Description`<br/>`/DebitNote/cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID` | **Regla SUNAT 2119 / 2120:** Obligatorio en Nota de Débito (`08`). Solo admite códigos del **Catálogo 08**: `01` (Intereses por mora), `02` (Aumento en el valor), `03` (Penalidades/otros conceptos), `10` (Ajustes de exportación), `11` (Ajustes afectos al IVAP). Debe referenciar la Factura/Boleta origen en `<cac:BillingReference>`. |
| **TR-10** | **Catálogo 05 (`1000` IGV)** & **Catálogo 07** (Afectación del IGV por ítem y global) | `total_gravadas`, `total_igv`, `InvoiceLineDTO.catalog_07_igv_type` (`"10"`..`"40"`), `igv_rate` (`0.18`), `igv_amount` | **Global:** `/Invoice/cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cac:TaxScheme/cbc:ID` (`1000` / `IGV` / `VAT`)<br/>**Por Línea:** `/Invoice/cac:InvoiceLine/cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:TaxExemptionReasonCode[@listURI="...:catalogo07"]` | **Regla SUNAT 2048 / 2600:** Para operaciones gravadas (`Catálogo 07` códigos `10` al `16`), el tributo en Catálogo 05 es `1000` (`IGV`, código internacional `VAT`). La base imponible del IGV es `(LineExtensionAmount + Monto_ISC)`. |
| **TR-11** | **Catálogo 05 (`2000` ISC)** & **Catálogo 08/Sistema ISC (Catálogo 08 ISC = Tipo de Sistema)** | `total_isc`, `InvoiceLineDTO.isc_rate`, `InvoiceLineDTO.isc_amount` | `/Invoice/cac:TaxTotal/cac:TaxSubtotal[cac:TaxCategory/cac:TaxScheme/cbc:ID="2000"]`<br/>`.../cbc:Name` (`ISC`)<br/>`.../cbc:TaxTypeCode` (`EXC`) | **Regla SUNAT 2051:** Aplica a bienes selectivos (ej. licores, bebidas en abarrotes mayoristas). Se calcula sobre el valor de venta (`LineExtensionAmount * isc_rate`) y **forma parte de la base imponible del IGV**. |
| **TR-12** | **Ley N° 30884 & Catálogo 05 (`7152` ICBPER)** (Impuesto a las Bolsas de Plástico) | `total_icbper`, `InvoiceLineDTO.icbper_quantity`, `icbper_unit_tax` (`0.50`), `icbper_amount` | `/Invoice/cac:InvoiceLine/cac:TaxTotal/cac:TaxSubtotal[cac:TaxCategory/cac:TaxScheme/cbc:ID="7152"]`<br/>`.../cbc:BaseUnitMeasure[@unitCode="NIU"]`<br/>`.../cac:TaxCategory/cbc:PerUnitAmount[@currencyID="PEN"]` | **Regla SUNAT 3206:** El tributo `7152` (`ICBPER`, código internacional `OTH`) no grava por porcentaje sino por cantidad de bolsas (`BaseUnitMeasure` $\times$ `PerUnitAmount` S/ 0.50). No forma parte de la base imponible del IGV. |
| **TR-13** | **RS 097-2012** (Totales Monetarios Legales del Comprobante) | `total_gravadas`, `total_exoneradas`, `total_inafectas`, `payable_amount` | `/Invoice/cac:LegalMonetaryTotal/cbc:LineExtensionAmount`<br/>`/Invoice/cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount`<br/>`/Invoice/cac:LegalMonetaryTotal/cbc:PayableAmount` | **Regla SUNAT 2062 / 2063:** `LineExtensionAmount` = suma de valores de venta sin impuestos. `TaxInclusiveAmount` y `PayableAmount` = `LineExtensionAmount + total_isc + total_igv + total_icbper`. Tolerancia máxima de redondeo SUNAT: $\pm 1.00$ (nuestro motor usa redondeo exacto a 2 decimales `ROUND_HALF_UP`). |
| **TR-14** | **RS 234-2006 (Formato 13.1 - Kardex)** & **RS 097-2012** (Detalle de Ítems y Trazabilidad Legacy) | **Legacy:** `producto`, `ingreso`, `salida`, `migrated_invoice_id`<br/>**Dominio (`InvoiceLineItemDTO`):** `line_number`, `product_sku`, `description`, `unit_code`, `quantity`, `unit_value`, `catalog_07_igv_type`, `igv_rate`, `igv_amount`, `isc_rate`, `isc_amount`, `icbper_quantity`, `icbper_unit_tax`, `icbper_amount`, `line_extension_amount`, `line_total_with_taxes` | `/Invoice/cac:InvoiceLine/cbc:ID`<br/>`.../cbc:InvoicedQuantity[@unitCode]`<br/>`.../cbc:LineExtensionAmount`<br/>`.../cac:TaxTotal/cbc:TaxAmount`<br/>`.../cac:Item/cbc:Description`<br/>`.../cac:Item/cac:SellersItemIdentification/cbc:ID`<br/>`.../cac:Price/cbc:PriceAmount` | **Regla SUNAT 2024 / RS 234-2006:** Cada movimiento de salida en la ficha de almacén legacy (`salida > 0`) genera o vincula un `<cac:InvoiceLine>` donde `InvoicedQuantity` coincide exactamente con `salida`, conservando el vínculo bidireccional `migrated_invoice_id` y el hash `audit_sha256` en el Kardex Formato 13.1. |

---

## 3. Especificación Estricta de Campos de Línea (`InvoiceLineDTO` / `InvoiceLineItemDTO`)

Sincronizado con [`specs/contracts/domain-dtos-schema.json`](file:///C:/Users/User/.gemini/antigravity/scratch/abc-erp-sunat/specs/contracts/domain-dtos-schema.json) (`http://json-schema.org/draft-07/schema#`):

| Campo en `InvoiceLineItemDTO` | Tipo JSON Schema | Requerido | XPath / Mapeo en `UBL-Invoice-2.1.xsd` |
|:---|:---|:---:|:---|
| `line_number` | `integer` | Sí | `cac:InvoiceLine/cbc:ID` |
| `product_sku` | `string` | Sí | `cac:InvoiceLine/cac:Item/cac:SellersItemIdentification/cbc:ID` |
| `description` | `string` | Sí | `cac:InvoiceLine/cac:Item/cbc:Description` |
| `unit_code` | `string` | Sí | `cac:InvoiceLine/cbc:InvoicedQuantity/@unitCode` (Catálogo 03 SUNAT: `NIU`, `KGM`, `BX`, `BG`) |
| `quantity` | `number` | Sí | `cac:InvoiceLine/cbc:InvoicedQuantity` |
| `unit_value` | `number` | Sí | `cac:InvoiceLine/cac:Price/cbc:PriceAmount` (Valor unitario sin impuestos) |
| `catalog_07_igv_type` | `string` | Sí | `cac:InvoiceLine/cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:TaxExemptionReasonCode` (`'10'`, `'20'`, `'30'`) |
| `igv_rate` | `number` | No | `cac:InvoiceLine/cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:Percent` (ej. `0.18`) |
| `igv_amount` | `number` | Sí | `cac:InvoiceLine/cac:TaxTotal/cac:TaxAmount` (Monto total del IGV de la línea) |
| `isc_rate` | `number` | No | Tasa del ISC si aplica (Catálogo 05 = `2000`) |
| `isc_amount` | `number` | No | Monto total del ISC de la línea |
| `icbper_quantity` | `number` | No | Cantidad de bolsas plásticas si aplica (Catálogo 05 = `7152`) |
| `icbper_unit_tax` | `number` | No | Impuesto unitario por bolsa plástica (S/ 0.50) |
| `icbper_amount` | `number` | No | Monto total del ICBPER de la línea |
| `line_extension_amount` | `number` | Sí | `cac:InvoiceLine/cbc:LineExtensionAmount` (`quantity * unit_value`) |
| `line_total_with_taxes` | `number` | Sí | Precio de venta total de la línea con impuestos incluidos (`line_extension_amount + isc_amount + igv_amount + icbper_amount`) |
