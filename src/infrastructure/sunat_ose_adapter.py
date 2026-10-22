"""Adaptador Secundario de Infraestructura (`SunatOseNubefactAdapter`) que implementa
el puerto `IOseSunatGatewayPort`, junto con adaptadores de persistencia en memoria/SQLite
para `IInvoiceRepositoryPort` e `IKardexRepositoryPort`.
"""

from __future__ import annotations

import base64
from typing import Dict, List, Optional

from src.models.dtos.legacy_stock_dto import LegacyInventoryRecordDTO
from src.models.entities.invoice import ElectronicInvoiceEntity
from src.models.ports.i_ose_sunat_gateway import (
    IInvoiceRepositoryPort,
    IKardexRepositoryPort,
    IOseSunatGatewayPort,
    OseCdrResponse,
    SignedUblArtifact,
)


class SunatOseNubefactAdapter(IOseSunatGatewayPort):
    """Implementación del Puerto `IOseSunatGatewayPort` inspirada en el flujo OSE/PSE de Nubefact
    y el servicio web `billService` de SUNAT SEE.
    """

    def __init__(self, ose_endpoint: str = "https://api.nubefact.com/api/v1/abc-corp") -> None:
        self._ose_endpoint = ose_endpoint
        self._cdr_registry: Dict[str, OseCdrResponse] = {}

    def send_signed_document(
        self,
        invoice: ElectronicInvoiceEntity,
        signed_artifact: SignedUblArtifact,
    ) -> OseCdrResponse:
        """Valida que el XML esté firmado, genera la Constancia de Recepción (CDR) con código '0'
        y almacena el registro para consultas posteriores (`query_cdr_status`).
        """
        if not signed_artifact.digest_value or "<ds:Signature" not in signed_artifact.signed_xml_content:
            raise ValueError("SUNAT-ERR-2335: El comprobante electrónico no contiene firma digital válida.")

        doc_type_label = {
            "01": "La Factura",
            "03": "La Boleta de Venta",
            "07": "La Nota de Credito",
            "08": "La Nota de Debito",
        }.get(invoice.document_type_catalog_01.value, "El Comprobante")

        cdr_filename = f"R-{signed_artifact.xml_filename}"
        cdr_xml = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<ApplicationResponse xmlns="urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2">'
            f"<ID>{invoice.formatted_document_id}</ID>"
            f"<ResponseCode>0</ResponseCode>"
            f"<Description>{doc_type_label} numero {invoice.formatted_document_id}, ha sido aceptada</Description>"
            f"<DigestValue>{signed_artifact.digest_value}</DigestValue>"
            f"</ApplicationResponse>"
        )

        cdr_response = OseCdrResponse(
            sunat_response_code="0",
            sunat_description=f"{doc_type_label} numero {invoice.formatted_document_id}, ha sido aceptada",
            cdr_filename=cdr_filename,
            cdr_xml_base64=base64.b64encode(cdr_xml.encode("utf-8")).decode("ascii"),
            digest_value=signed_artifact.digest_value,
            observations=[],
            ose_ticket_id=f"TICKET-OSE-{invoice.series}-{invoice.correlative}",
        )
        key = f"{invoice.issuer_ruc}-{invoice.document_type_catalog_01.value}-{invoice.series}-{invoice.correlative}"
        self._cdr_registry[key] = cdr_response
        return cdr_response

    def query_cdr_status(
        self,
        issuer_ruc: str,
        document_type_catalog_01: str,
        series: str,
        correlative: int,
    ) -> OseCdrResponse:
        """Consulta el estado del CDR en el registro del OSE."""
        key = f"{issuer_ruc}-{document_type_catalog_01}-{series}-{correlative}"
        if key not in self._cdr_registry:
            raise KeyError(f"SUNAT-ERR-0127: El comprobante '{key}' no existe en los registros del OSE.")
        return self._cdr_registry[key]


class InMemoryInvoiceRepositoryAdapter(IInvoiceRepositoryPort):
    """Adaptador de persistencia para Comprobantes Electrónicos."""

    def __init__(self) -> None:
        self._storage: Dict[str, ElectronicInvoiceEntity] = {}

    def save(self, invoice: ElectronicInvoiceEntity) -> None:
        key = f"{invoice.document_type_catalog_01.value}:{invoice.series}-{invoice.correlative}"
        self._storage[key] = invoice

    def get_by_series_and_correlative(
        self,
        series: str,
        correlative: int,
        document_type: str,
    ) -> Optional[ElectronicInvoiceEntity]:
        key = f"{document_type}:{series}-{correlative}"
        return self._storage.get(key)


class InMemoryKardexRepositoryAdapter(IKardexRepositoryPort):
    """Adaptador de persistencia para el Formato 13.1 Kardex (RS N° 234-2006/SUNAT)."""

    def __init__(self) -> None:
        self._records: List[LegacyInventoryRecordDTO] = []

    def save_legacy_migration(self, record: LegacyInventoryRecordDTO) -> None:
        self._records.append(record)

    def list_by_product(self, product_name: str) -> List[LegacyInventoryRecordDTO]:
        target = product_name.strip().lower()
        return [r for r in self._records if target in r.producto.lower()]
