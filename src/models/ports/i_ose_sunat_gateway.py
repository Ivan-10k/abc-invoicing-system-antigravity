"""Puertos de Salida (Driven Ports / Interfaces Abstractas) del Modelo hacia la Infraestructura.

Regla Arquitectónica (ADR-0001):
En el Monolito Limpio MVC, los Controladores (`src/controllers/`) dependen EXCLUSIVAMENTE de estas
interfaces abstractas (`ABC`). En la transición a Arquitectura Hexagonal y Microservicios, estas
mismas interfaces se implementan mediante adaptadores gRPC, RabbitMQ/Kafka o REST hacia Nubefact/SUNAT
sin tocar una sola línea del Modelo ni de los Controladores.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from src.models.dtos.legacy_stock_dto import LegacyInventoryRecordDTO
from src.models.entities.invoice import ElectronicInvoiceEntity


@dataclass(frozen=True)
class SignedUblArtifact:
    """Artefacto inmutable producido por el puerto generador y firmador UBL 2.1."""

    xml_filename: str
    signed_xml_content: str
    digest_value: str  # <ds:DigestValue> SHA-256 del documento firmado
    xsd_schema_validated: str = "UBL-Invoice-2.1.xsd"


@dataclass(frozen=True)
class OseCdrResponse:
    """Respuesta estandarizada de Constancia de Recepción (CDR) devuelta por SUNAT o un OSE (ej. Nubefact)."""

    sunat_response_code: str          # "0" = Aceptado, "2000-2999" = Rechazo, "4000+" = Observación
    sunat_description: str            # Ejemplo: "La Factura numero F001-1045, ha sido aceptada"
    cdr_filename: str                 # Ejemplo: "R-20601234568-01-F001-1045.xml"
    cdr_xml_base64: str               # Contenido del CDR firmado por SUNAT/OSE
    digest_value: str                 # Hash del comprobante aceptado
    observations: List[str] = field(default_factory=list)
    ose_ticket_id: Optional[str] = None


class IXmlUblSignerPort(ABC):
    """Puerto de Salida para construcción de XML bajo estándar OASIS `UBL-Invoice-2.1.xsd` / `UBL-DebitNote-2.1.xsd`,
    validación contra esquema XSD oficial y firma digital criptográfica X.509 (`XMLDSig` / `XAdES-BES`).
    """

    @abstractmethod
    def build_validate_and_sign_ubl21(self, invoice: ElectronicInvoiceEntity) -> SignedUblArtifact:
        """Construye el XML UBL 2.1, valida su estructura XSD e incrusta la firma en `<ext:UBLExtensions>`."""


class IOseSunatGatewayPort(ABC):
    """Puerto de Salida (Driven Port) para transmisión de comprobantes electrónicos firmados hacia
    SUNAT SEE o un Operador de Servicios Electrónicos (OSE estilo Nubefact).
    """

    @abstractmethod
    def send_signed_document(
        self,
        invoice: ElectronicInvoiceEntity,
        signed_artifact: SignedUblArtifact,
    ) -> OseCdrResponse:
        """Envía el comprobante UBL 2.1 firmado y retorna la Constancia de Recepción (CDR)."""

    @abstractmethod
    def query_cdr_status(
        self,
        issuer_ruc: str,
        document_type_catalog_01: str,
        series: str,
        correlative: int,
    ) -> OseCdrResponse:
        """Consulta el estado del CDR en SUNAT/OSE para flujos asíncronos o contingencia."""


class IInvoiceRepositoryPort(ABC):
    """Puerto de Salida para persistencia transaccional de Comprobantes Electrónicos e histórico CDR."""

    @abstractmethod
    def save(self, invoice: ElectronicInvoiceEntity) -> None:
        """Persiste o actualiza el comprobante electrónico y su estado tributario."""

    @abstractmethod
    def get_by_series_and_correlative(
        self,
        series: str,
        correlative: int,
        document_type: str,
    ) -> Optional[ElectronicInvoiceEntity]:
        """Recupera un comprobante por su numeración oficial SUNAT."""


class IKardexRepositoryPort(ABC):
    """Puerto de Salida para persistencia del Registro de Inventario Permanente Valorizado
    (Formato 13.1 - RS N° 234-2006/SUNAT) y fichas migradas del almacén legacy.
    """

    @abstractmethod
    def save_legacy_migration(self, record: LegacyInventoryRecordDTO) -> None:
        """Guarda la ficha de almacén legacy junto con su `migrated_invoice_id` y `audit_sha256`."""

    @abstractmethod
    def list_by_product(self, product_name: str) -> List[LegacyInventoryRecordDTO]:
        """Lista los movimientos históricos Kardex de un producto para auditoría SUNAT."""
