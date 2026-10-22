"""Entidades de Dominio Puro para Facturación Electrónica SUNAT UBL 2.1 y Migración Legacy (RS N° 097-2012 y RS N° 234-2006).

Regla Arquitectónica (ADR-0001):
Este módulo pertenece al núcleo del Modelo (`src/models/entities/`) y NO tiene dependencias hacia
librerías de infraestructura (bases de datos, clientes HTTP, lxml, ni frameworks de UI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from src.models.dtos.invoice_request_dto import (
    Catalog01DocumentType,
    Catalog02CurrencyCode,
    Catalog05TaxSchemeCode,
    Catalog07IgvAffectationCode,
    Catalog08DebitNoteTypeCode,
    InvoiceLineDTO,
    InvoiceRequestDTO,
    validate_peruvian_ruc_modulo11,
)
from src.models.dtos.legacy_stock_dto import LegacyInventoryRecordDTO

TWO_DECIMALS = Decimal("0.01")


@dataclass(frozen=True)
class TaxBreakdown:
    """Value Object inmutable con el desglose exacto de impuestos según Catálogo 05 SUNAT."""

    currency_code: Catalog02CurrencyCode
    total_gravadas: Decimal
    total_exoneradas: Decimal
    total_inafectas: Decimal
    total_isc: Decimal       # Catálogo 05 = '2000' (EXC)
    total_igv: Decimal       # Catálogo 05 = '1000' (VAT) calculado sobre (Base Gravada + ISC)
    total_icbper: Decimal    # Catálogo 05 = '7152' (OTH) S/ 0.50 por bolsa plástica
    payable_amount: Decimal  # <cbc:PayableAmount>


@dataclass
class ElectronicInvoiceEntity:
    """Agregado Raíz de Dominio que representa un Comprobante Electrónico SUNAT (UBL 2.1):
    - Factura ('01')
    - Boleta de Venta ('03')
    - Nota de Crédito ('07')
    - Nota de Débito ('08' con Catálogo 08 obligatorio)

    Mantiene trazabilidad bidireccional con fichas de almacén legacy (`source_legacy_record_id`).
    """

    invoice_id: UUID = field(default_factory=uuid4)
    ubl_version: str = "2.1"
    customization_id: str = "2.0"
    operation_type_catalog_51: str = "0101"
    document_type_catalog_01: Catalog01DocumentType = Catalog01DocumentType.FACTURA
    series: str = "F001"
    correlative: int = 1
    issue_date: date = field(default_factory=date.today)
    issue_time: time = field(default_factory=lambda: time(12, 0, 0))
    currency_code_catalog_02: Catalog02CurrencyCode = Catalog02CurrencyCode.PEN

    # Emisor y Cliente
    issuer_ruc: str = ""
    issuer_legal_name: str = ""
    issuer_ubigeo: str = "150101"
    customer_doc_type_catalog_06: str = "6"
    customer_doc_number: str = ""
    customer_legal_name: str = ""

    # Nota de Débito (Catálogo 08) / Nota de Crédito
    catalog_08_debit_note_type: Optional[Catalog08DebitNoteTypeCode] = None
    referenced_document_series_number: Optional[str] = None
    discrepancy_reason: Optional[str] = None

    # Trazabilidad hacia Ficha de Almacén Legacy (RS N° 234-2006)
    source_legacy_record_id: Optional[str] = None
    legacy_audit_sha256: Optional[str] = None

    # Líneas y Estado Tributario
    lines: List[InvoiceLineDTO] = field(default_factory=list)
    tax_breakdown: Optional[TaxBreakdown] = None
    status: str = "BORRADOR"
    xml_digest_value: Optional[str] = None
    sunat_cdr_code: Optional[str] = None
    sunat_cdr_description: Optional[str] = None
    sunat_observations: List[str] = field(default_factory=list)

    @property
    def formatted_document_id(self) -> str:
        """Retorna el identificador oficial SUNAT `<Serie>-<Correlativo>` (ej. `F001-1045`)."""
        return f"{self.series}-{self.correlative}"

    @property
    def official_xml_filename(self) -> str:
        """Nombre estándar de archivo XML exigido por RS N° 097-2012: `<RUC>-<Cat01>-<Serie>-<Correlativo>.xml`."""
        return f"{self.issuer_ruc}-{self.document_type_catalog_01.value}-{self.series}-{self.correlative}.xml"

    @staticmethod
    def validate_ruc(ruc: str) -> str:
        """Delega la validación algorítmica Módulo 11 de SUNAT."""
        return validate_peruvian_ruc_modulo11(ruc)

    def validate_and_calculate_taxes(self) -> TaxBreakdown:
        """Ejecuta las invariantes de dominio tributario (Módulo 11, Catálogo 08, IGV/ISC/ICBPER)
        y construye el Value Object `TaxBreakdown`.
        """
        # 1. Validar RUC del emisor siempre con Módulo 11
        validate_peruvian_ruc_modulo11(self.issuer_ruc)

        # 2. Validar RUC del cliente si es Factura ('01') o tipo doc '6'
        if self.document_type_catalog_01 == Catalog01DocumentType.FACTURA and self.customer_doc_type_catalog_06 != "6":
            raise ValueError("SUNAT-ERR-2800: Las Facturas ('01') requieren cliente con RUC (Catálogo 06 = '6').")
        if self.customer_doc_type_catalog_06 == "6":
            validate_peruvian_ruc_modulo11(self.customer_doc_number)

        # 3. Validar Catálogo 08 si es Nota de Débito ('08')
        if self.document_type_catalog_01 == Catalog01DocumentType.NOTA_DEBITO:
            if self.catalog_08_debit_note_type is None:
                raise ValueError(
                    "SUNAT-ERR-2119: La Nota de Débito ('08') requiere obligatoriamente un código del Catálogo 08 SUNAT."
                )
            if not self.referenced_document_series_number or not self.discrepancy_reason:
                raise ValueError(
                    "SUNAT-ERR-2120: La Nota de Débito ('08') requiere serie-correlativo de referencia y sustento."
                )

        if not self.lines:
            raise ValueError("SUNAT-ERR-2024: El comprobante electrónico debe tener al menos una línea de detalle.")

        # 4. Consolidar bases imponibles e impuestos (ISC, IGV sobre Base+ISC, ICBPER)
        total_gravadas = sum(
            (line.line_extension_amount for line in self.lines if line.catalog_07_igv_type.value.startswith("1")),
            Decimal("0.00"),
        ).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)

        total_exoneradas = sum(
            (line.line_extension_amount for line in self.lines if line.catalog_07_igv_type.value.startswith("2")),
            Decimal("0.00"),
        ).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)

        total_inafectas = sum(
            (line.line_extension_amount for line in self.lines if line.catalog_07_igv_type.value.startswith("3")),
            Decimal("0.00"),
        ).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)

        total_isc = sum((line.isc_amount for line in self.lines), Decimal("0.00")).quantize(
            TWO_DECIMALS, rounding=ROUND_HALF_UP
        )
        total_igv = sum((line.igv_amount for line in self.lines), Decimal("0.00")).quantize(
            TWO_DECIMALS, rounding=ROUND_HALF_UP
        )
        total_icbper = sum((line.icbper_amount for line in self.lines), Decimal("0.00")).quantize(
            TWO_DECIMALS, rounding=ROUND_HALF_UP
        )

        payable_amount = (
            total_gravadas + total_exoneradas + total_inafectas + total_isc + total_igv + total_icbper
        ).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)

        self.tax_breakdown = TaxBreakdown(
            currency_code=self.currency_code_catalog_02,
            total_gravadas=total_gravadas,
            total_exoneradas=total_exoneradas,
            total_inafectas=total_inafectas,
            total_isc=total_isc,
            total_igv=total_igv,
            total_icbper=total_icbper,
            payable_amount=payable_amount,
        )
        return self.tax_breakdown

    @classmethod
    def from_request_dto(cls, dto: InvoiceRequestDTO) -> "ElectronicInvoiceEntity":
        """Fábrica de Dominio que construye una entidad validada a partir de `InvoiceRequestDTO`."""
        entity = cls(
            ubl_version=dto.ubl_version,
            customization_id=dto.customization_id,
            operation_type_catalog_51=dto.operation_type_catalog_51,
            document_type_catalog_01=dto.document_type_catalog_01,
            series=dto.series,
            correlative=dto.correlative,
            issue_date=dto.issue_date,
            issue_time=dto.issue_time,
            currency_code_catalog_02=dto.currency_code_catalog_02,
            issuer_ruc=dto.issuer_ruc,
            issuer_legal_name=dto.issuer_legal_name,
            issuer_ubigeo=dto.issuer_ubigeo,
            customer_doc_type_catalog_06=dto.customer_doc_type_catalog_06,
            customer_doc_number=dto.customer_doc_number,
            customer_legal_name=dto.customer_legal_name,
            catalog_08_debit_note_type=dto.catalog_08_debit_note_type,
            referenced_document_series_number=dto.referenced_document_series_number,
            discrepancy_reason=dto.discrepancy_reason,
            source_legacy_record_id=dto.source_legacy_record_id,
            lines=list(dto.lines),
        )
        entity.validate_and_calculate_taxes()
        return entity

    @classmethod
    def from_legacy_kardex_record(
        cls,
        legacy_dto: LegacyInventoryRecordDTO,
        issuer_ruc: str,
        issuer_legal_name: str,
        customer_ruc: str,
        customer_legal_name: str,
        unit_value: Decimal,
        product_sku: str = "LEGACY-SKU-001",
    ) -> "ElectronicInvoiceEntity":
        """Crea y acopla un Comprobante Electrónico UBL 2.1 a partir de una ficha informal de salida
        del sistema legacy (`fecha`, `ingreso`, `salida`, `producto`, `nro_documento`), manteniendo
        trazabilidad inmutable (`migrated_invoice_id` y `audit_sha256`).
        """
        if legacy_dto.salida <= Decimal("0.00"):
            raise ValueError(
                f"LEGACY_MIGRATION_NOT_A_SALE: La ficha '{legacy_dto.nro_documento}' no corresponde a una salida de venta."
            )

        series = legacy_dto.normalized_series or "F001"
        correlative = legacy_dto.normalized_correlative or 1
        doc_type = (
            Catalog01DocumentType.BOLETA if series.upper().startswith("B") else Catalog01DocumentType.FACTURA
        )

        line = InvoiceLineDTO(
            line_number=1,
            product_sku=product_sku,
            description=legacy_dto.producto,
            unit_code="NIU",
            quantity=legacy_dto.salida,
            unit_value=unit_value,
            catalog_07_igv_type=Catalog07IgvAffectationCode.GRAVADO_OPERACION_ONEROSA,
            igv_rate=Decimal("0.18"),
        )

        entity = cls(
            document_type_catalog_01=doc_type,
            series=series,
            correlative=correlative,
            issue_date=legacy_dto.fecha,
            issuer_ruc=issuer_ruc,
            issuer_legal_name=issuer_legal_name,
            customer_doc_type_catalog_06="6",
            customer_doc_number=customer_ruc,
            customer_legal_name=customer_legal_name,
            source_legacy_record_id=str(legacy_dto.legacy_record_id),
            legacy_audit_sha256=legacy_dto.audit_sha256,
            lines=[line],
        )
        entity.validate_and_calculate_taxes()
        # Vincular bidireccionalmente la ficha legacy con el ID del comprobante electrónico
        legacy_dto.migrated_invoice_id = str(entity.invoice_id)
        return entity

    def apply_cdr_response(
        self,
        cdr_code: str,
        cdr_description: str,
        digest_value: str,
        observations: Optional[List[str]] = None,
    ) -> None:
        """Actualiza el estado tributario de la entidad según el CDR recibido desde SUNAT / OSE."""
        self.sunat_cdr_code = cdr_code
        self.sunat_cdr_description = cdr_description
        self.xml_digest_value = digest_value
        self.sunat_observations = observations or []

        if cdr_code == "0":
            self.status = "ACEPTADO_CON_OBSERVACIONES" if self.sunat_observations else "ACEPTADO"
        else:
            self.status = "RECHAZADO"

    def to_summary_dict(self) -> Dict[str, object]:
        """Serializa el resumen ejecutivo del comprobante y su trazabilidad."""
        tb = self.tax_breakdown or self.validate_and_calculate_taxes()
        return {
            "invoice_id": str(self.invoice_id),
            "document_type_catalog_01": self.document_type_catalog_01.value,
            "document_id": self.formatted_document_id,
            "official_xml_filename": self.official_xml_filename,
            "status": self.status,
            "sunat_response_code": self.sunat_cdr_code,
            "sunat_description": self.sunat_cdr_description,
            "sunat_observations": self.sunat_observations,
            "xml_digest_value": self.xml_digest_value,
            "source_legacy_record_id": self.source_legacy_record_id,
            "legacy_audit_sha256": self.legacy_audit_sha256,
            "catalog_08_debit_note_type": (
                self.catalog_08_debit_note_type.value if self.catalog_08_debit_note_type else None
            ),
            "tax_summary": {
                "currency_code": tb.currency_code.value,
                "total_gravadas": float(tb.total_gravadas),
                "total_exoneradas": float(tb.total_exoneradas),
                "total_inafectas": float(tb.total_inafectas),
                "total_isc": float(tb.total_isc),
                "total_igv": float(tb.total_igv),
                "total_icbper": float(tb.total_icbper),
                "payable_amount": float(tb.payable_amount),
            },
        }
