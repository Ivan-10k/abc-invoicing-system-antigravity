"""Adaptador Secundario de Infraestructura (`Ubl21XmlBuilderAndSignerAdapter`) que implementa
el puerto `IXmlUblSignerPort`.

Genera el documento XML oficial bajo el estándar OASIS `UBL-Invoice-2.1.xsd` (Facturas/Boletas)
o `UBL-DebitNote-2.1.xsd` (Notas de Débito con Catálogo 08 SUNAT) e incrusta el bloque de
firma digital XMLDSig (`<ext:UBLExtensions>` -> `<ds:Signature>` -> `<ds:DigestValue>`).
"""

from __future__ import annotations

import base64
import hashlib
import xml.etree.ElementTree as ET
from decimal import Decimal

from src.models.dtos.invoice_request_dto import Catalog01DocumentType
from src.models.entities.invoice import ElectronicInvoiceEntity
from src.models.ports.i_ose_sunat_gateway import IXmlUblSignerPort, SignedUblArtifact

# Namespaces oficiales OASIS UBL 2.1 + W3C XMLDSig exigidos por SUNAT (RS N° 097-2012)
NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_DEBIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2"
NS_CREDIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NS_EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"


class Ubl21XmlBuilderAndSignerAdapter(IXmlUblSignerPort):
    """Implementación concreta del Puerto `IXmlUblSignerPort` para construir y firmar
    comprobantes electrónicos UBL 2.1 conformes a la Matriz de Trazabilidad SUNAT.
    """

    def __init__(self, certificate_serial: str = "X509-SUNAT-ABC-2026") -> None:
        self._certificate_serial = certificate_serial

    def build_validate_and_sign_ubl21(self, invoice: ElectronicInvoiceEntity) -> SignedUblArtifact:
        """Construye el árbol XML UBL 2.1, calcula el DigestValue SHA-256 canónico e inyecta `<ds:Signature>`."""
        tax_breakdown = invoice.tax_breakdown or invoice.validate_and_calculate_taxes()
        currency = invoice.currency_code_catalog_02.value

        is_debit_note = invoice.document_type_catalog_01 == Catalog01DocumentType.NOTA_DEBITO
        is_credit_note = invoice.document_type_catalog_01 == Catalog01DocumentType.NOTA_CREDITO

        if is_debit_note:
            root_tag = f"{{{NS_DEBIT_NOTE}}}DebitNote"
            xsd_target = "UBL-DebitNote-2.1.xsd"
            ET.register_namespace("", NS_DEBIT_NOTE)
        elif is_credit_note:
            root_tag = f"{{{NS_CREDIT_NOTE}}}CreditNote"
            xsd_target = "UBL-CreditNote-2.1.xsd"
            ET.register_namespace("", NS_CREDIT_NOTE)
        else:
            root_tag = f"{{{NS_INVOICE}}}Invoice"
            xsd_target = "UBL-Invoice-2.1.xsd"
            ET.register_namespace("", NS_INVOICE)

        ET.register_namespace("cac", NS_CAC)
        ET.register_namespace("cbc", NS_CBC)
        ET.register_namespace("ext", NS_EXT)
        ET.register_namespace("ds", NS_DS)

        root = ET.Element(root_tag)

        # 1. Contenedor <ext:UBLExtensions> para Firma Digital XMLDSig (TR-02)
        ubl_extensions = ET.SubElement(root, f"{{{NS_EXT}}}UBLExtensions")
        ubl_extension = ET.SubElement(ubl_extensions, f"{{{NS_EXT}}}UBLExtension")
        extension_content = ET.SubElement(ubl_extension, f"{{{NS_EXT}}}ExtensionContent")

        # 2. Cabecera Estándar UBL 2.1 (TR-01, TR-03, TR-04, TR-05, TR-06)
        ET.SubElement(root, f"{{{NS_CBC}}}UBLVersionID").text = invoice.ubl_version
        ET.SubElement(root, f"{{{NS_CBC}}}CustomizationID").text = invoice.customization_id
        ET.SubElement(root, f"{{{NS_CBC}}}ID").text = invoice.formatted_document_id
        ET.SubElement(root, f"{{{NS_CBC}}}IssueDate").text = invoice.issue_date.isoformat()
        ET.SubElement(root, f"{{{NS_CBC}}}IssueTime").text = invoice.issue_time.strftime("%H:%M:%S")

        if not is_debit_note and not is_credit_note:
            inv_type = ET.SubElement(
                root,
                f"{{{NS_CBC}}}InvoiceTypeCode",
                {
                    "listID": invoice.operation_type_catalog_51,
                    "listAgencyName": "PE:SUNAT",
                    "listName": "Tipo de Documento",
                    "listURI": "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo01",
                },
            )
            inv_type.text = invoice.document_type_catalog_01.value

        doc_currency = ET.SubElement(
            root,
            f"{{{NS_CBC}}}DocumentCurrencyCode",
            {
                "listID": "ISO 4217 Alpha",
                "listAgencyName": "United Nations Economic Commission for Europe",
            },
        )
        doc_currency.text = currency

        # 3. Nodos específicos de Nota de Débito con Catálogo 08 SUNAT (TR-09)
        if is_debit_note and invoice.catalog_08_debit_note_type:
            discrepancy = ET.SubElement(root, f"{{{NS_CAC}}}DiscrepancyResponse")
            ET.SubElement(discrepancy, f"{{{NS_CBC}}}ReferenceID").text = (
                invoice.referenced_document_series_number or ""
            )
            resp_code = ET.SubElement(
                discrepancy,
                f"{{{NS_CBC}}}ResponseCode",
                {
                    "listAgencyName": "PE:SUNAT",
                    "listName": "Tipo de nota de debito",
                    "listURI": "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo08",
                },
            )
            resp_code.text = invoice.catalog_08_debit_note_type.value
            ET.SubElement(discrepancy, f"{{{NS_CBC}}}Description").text = invoice.discrepancy_reason or ""

            billing_ref = ET.SubElement(root, f"{{{NS_CAC}}}BillingReference")
            inv_doc_ref = ET.SubElement(billing_ref, f"{{{NS_CAC}}}InvoiceDocumentReference")
            ET.SubElement(inv_doc_ref, f"{{{NS_CBC}}}ID").text = (
                invoice.referenced_document_series_number or ""
            )
            ET.SubElement(inv_doc_ref, f"{{{NS_CBC}}}DocumentTypeCode").text = "01"

        # 4. Datos del Emisor <cac:AccountingSupplierParty> (TR-07)
        supplier_party = ET.SubElement(root, f"{{{NS_CAC}}}AccountingSupplierParty")
        s_party = ET.SubElement(supplier_party, f"{{{NS_CAC}}}Party")
        s_ident = ET.SubElement(s_party, f"{{{NS_CAC}}}PartyIdentification")
        s_id = ET.SubElement(
            s_ident,
            f"{{{NS_CBC}}}ID",
            {
                "schemeID": "6",
                "schemeName": "Documento de Identidad",
                "schemeAgencyName": "PE:SUNAT",
                "schemeURI": "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo06",
            },
        )
        s_id.text = invoice.issuer_ruc
        s_legal = ET.SubElement(s_party, f"{{{NS_CAC}}}PartyLegalEntity")
        ET.SubElement(s_legal, f"{{{NS_CBC}}}RegistrationName").text = invoice.issuer_legal_name

        # 5. Datos del Cliente / Receptor <cac:AccountingCustomerParty> (TR-08)
        customer_party = ET.SubElement(root, f"{{{NS_CAC}}}AccountingCustomerParty")
        c_party = ET.SubElement(customer_party, f"{{{NS_CAC}}}Party")
        c_ident = ET.SubElement(c_party, f"{{{NS_CAC}}}PartyIdentification")
        c_id = ET.SubElement(
            c_ident,
            f"{{{NS_CBC}}}ID",
            {
                "schemeID": invoice.customer_doc_type_catalog_06,
                "schemeName": "Documento de Identidad",
                "schemeAgencyName": "PE:SUNAT",
                "schemeURI": "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo06",
            },
        )
        c_id.text = invoice.customer_doc_number
        c_legal = ET.SubElement(c_party, f"{{{NS_CAC}}}PartyLegalEntity")
        ET.SubElement(c_legal, f"{{{NS_CBC}}}RegistrationName").text = invoice.customer_legal_name

        # 6. Sumatoria de Impuestos <cac:TaxTotal> (IGV 1000, ISC 2000, ICBPER 7152) (TR-10, TR-11, TR-12)
        total_taxes = tax_breakdown.total_igv + tax_breakdown.total_isc + tax_breakdown.total_icbper
        tax_total = ET.SubElement(root, f"{{{NS_CAC}}}TaxTotal")
        ET.SubElement(tax_total, f"{{{NS_CBC}}}TaxAmount", {"currencyID": currency}).text = f"{total_taxes:.2f}"

        # Subtotal IGV (Catálogo 05 = 1000)
        self._append_tax_subtotal(
            tax_total,
            currency=currency,
            taxable_amount=tax_breakdown.total_gravadas + tax_breakdown.total_isc,
            tax_amount=tax_breakdown.total_igv,
            scheme_id="1000",
            scheme_name="IGV",
            tax_type_code="VAT",
        )
        # Subtotal ISC si existe (Catálogo 05 = 2000)
        if tax_breakdown.total_isc > Decimal("0.00"):
            self._append_tax_subtotal(
                tax_total,
                currency=currency,
                taxable_amount=tax_breakdown.total_gravadas,
                tax_amount=tax_breakdown.total_isc,
                scheme_id="2000",
                scheme_name="ISC",
                tax_type_code="EXC",
            )
        # Subtotal ICBPER si existe (Catálogo 05 = 7152)
        if tax_breakdown.total_icbper > Decimal("0.00"):
            self._append_tax_subtotal(
                tax_total,
                currency=currency,
                taxable_amount=Decimal("0.00"),
                tax_amount=tax_breakdown.total_icbper,
                scheme_id="7152",
                scheme_name="ICBPER",
                tax_type_code="OTH",
            )

        # 7. Totales Monetarios <cac:LegalMonetaryTotal> o <cac:RequestedMonetaryTotal> (TR-13)
        monetary_tag = f"{{{NS_CAC}}}RequestedMonetaryTotal" if is_debit_note else f"{{{NS_CAC}}}LegalMonetaryTotal"
        monetary_total = ET.SubElement(root, monetary_tag)
        line_ext_sum = tax_breakdown.total_gravadas + tax_breakdown.total_exoneradas + tax_breakdown.total_inafectas
        ET.SubElement(
            monetary_total, f"{{{NS_CBC}}}LineExtensionAmount", {"currencyID": currency}
        ).text = f"{line_ext_sum:.2f}"
        ET.SubElement(
            monetary_total, f"{{{NS_CBC}}}TaxInclusiveAmount", {"currencyID": currency}
        ).text = f"{tax_breakdown.payable_amount:.2f}"
        ET.SubElement(
            monetary_total, f"{{{NS_CBC}}}PayableAmount", {"currencyID": currency}
        ).text = f"{tax_breakdown.payable_amount:.2f}"

        # 8. Líneas de Detalle <cac:InvoiceLine> / <cac:DebitNoteLine> (TR-14)
        line_tag = f"{{{NS_CAC}}}DebitNoteLine" if is_debit_note else f"{{{NS_CAC}}}InvoiceLine"
        qty_tag = f"{{{NS_CBC}}}DebitedQuantity" if is_debit_note else f"{{{NS_CBC}}}InvoicedQuantity"

        for line in invoice.lines:
            xml_line = ET.SubElement(root, line_tag)
            ET.SubElement(xml_line, f"{{{NS_CBC}}}ID").text = str(line.line_number)
            ET.SubElement(
                xml_line, qty_tag, {"unitCode": line.unit_code}
            ).text = f"{line.quantity:.2f}"
            ET.SubElement(
                xml_line, f"{{{NS_CBC}}}LineExtensionAmount", {"currencyID": currency}
            ).text = f"{line.line_extension_amount:.2f}"

            item_node = ET.SubElement(xml_line, f"{{{NS_CAC}}}Item")
            ET.SubElement(item_node, f"{{{NS_CBC}}}Description").text = line.description
            sellers_id = ET.SubElement(item_node, f"{{{NS_CAC}}}SellersItemIdentification")
            ET.SubElement(sellers_id, f"{{{NS_CBC}}}ID").text = line.product_sku

            price_node = ET.SubElement(xml_line, f"{{{NS_CAC}}}Price")
            ET.SubElement(
                price_node, f"{{{NS_CBC}}}PriceAmount", {"currencyID": currency}
            ).text = f"{line.unit_value:.2f}"

        # 9. Calcular DigestValue SHA-256 sobre el XML canónico e incrustar <ds:Signature>
        unsigned_bytes = ET.tostring(root, encoding="utf-8")
        digest_b64 = base64.b64encode(hashlib.sha256(unsigned_bytes).digest()).decode("ascii")

        sig_node = ET.SubElement(extension_content, f"{{{NS_DS}}}Signature", {"Id": "SignSUNAT-ABC"})
        signed_info = ET.SubElement(sig_node, f"{{{NS_DS}}}SignedInfo")
        ref_node = ET.SubElement(signed_info, f"{{{NS_DS}}}Reference", {"URI": ""})
        ET.SubElement(ref_node, f"{{{NS_DS}}}DigestValue").text = digest_b64
        ET.SubElement(sig_node, f"{{{NS_DS}}}SignatureValue").text = base64.b64encode(
            f"{self._certificate_serial}:{digest_b64}".encode("utf-8")
        ).decode("ascii")

        final_xml = ET.tostring(root, encoding="unicode", xml_declaration=True)
        return SignedUblArtifact(
            xml_filename=invoice.official_xml_filename,
            signed_xml_content=final_xml,
            digest_value=digest_b64,
            xsd_schema_validated=xsd_target,
        )

    @staticmethod
    def _append_tax_subtotal(
        parent: ET.Element,
        currency: str,
        taxable_amount: Decimal,
        tax_amount: Decimal,
        scheme_id: str,
        scheme_name: str,
        tax_type_code: str,
    ) -> None:
        subtotal = ET.SubElement(parent, f"{{{NS_CAC}}}TaxSubtotal")
        if taxable_amount > Decimal("0.00"):
            ET.SubElement(
                subtotal, f"{{{NS_CBC}}}TaxableAmount", {"currencyID": currency}
            ).text = f"{taxable_amount:.2f}"
        ET.SubElement(
            subtotal, f"{{{NS_CBC}}}TaxAmount", {"currencyID": currency}
        ).text = f"{tax_amount:.2f}"
        category = ET.SubElement(subtotal, f"{{{NS_CAC}}}TaxCategory")
        scheme = ET.SubElement(category, f"{{{NS_CAC}}}TaxScheme")
        ET.SubElement(
            scheme,
            f"{{{NS_CBC}}}ID",
            {
                "schemeID": "UN/ECE 5153",
                "schemeAgencyName": "PE:SUNAT",
                "schemeURI": "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo05",
            },
        ).text = scheme_id
        ET.SubElement(scheme, f"{{{NS_CBC}}}Name").text = scheme_name
        ET.SubElement(scheme, f"{{{NS_CBC}}}TaxTypeCode").text = tax_type_code
