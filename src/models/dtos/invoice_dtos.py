"""Modelos y Contratos Pydantic (DTOs) para Migración de Almacén Legacy (RS N° 234-2006)
y Emisión de Comprobantes Electrónicos SUNAT UBL 2.1 (RS N° 097-2012).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from src.models.dtos.invoice_request_dto import (
    Catalog01DocumentType,
    Catalog02CurrencyCode,
    Catalog05TaxSchemeCode,
    Catalog07IgvAffectationCode,
    Catalog08DebitNoteTypeCode,
    InvoiceLineDTO,
    InvoiceLineItemDTO,
    InvoiceRequestDTO,
    MODULO_11_WEIGHTS,
    TWO_DECIMALS,
    VALID_RUC_PREFIXES,
    validate_peruvian_ruc_modulo11,
)
from src.models.dtos.legacy_stock_dto import LegacyInventoryRecordDTO


class InvoiceDTO(InvoiceRequestDTO):
    """Modelo Pydantic principal de Comprobante Electrónico UBL 2.1 (`InvoiceDTO`),
    compatible con Facturas ('01'), Boletas ('03'), Notas de Crédito ('07') y
    Notas de Débito ('08' con validación obligatoria del Catálogo 08 SUNAT).
    """

    invoice_status: Literal[
        "BORRADOR",
        "ACEPTADO",
        "ACEPTADO_CON_OBSERVACIONES",
        "RECHAZADO",
    ] = Field(
        default="BORRADOR",
        description="Estado tributario del comprobante frente a SUNAT / OSE.",
    )
    sunat_cdr_code: Optional[str] = Field(
        default=None,
        description="Código de respuesta CDR SUNAT ('0' = Aceptado).",
    )
    xml_digest_value: Optional[str] = Field(
        default=None,
        description="Hash SHA-256 (<ds:DigestValue>) de la firma digital XMLDSig.",
    )


__all__ = [
    "Catalog01DocumentType",
    "Catalog02CurrencyCode",
    "Catalog05TaxSchemeCode",
    "Catalog07IgvAffectationCode",
    "Catalog08DebitNoteTypeCode",
    "InvoiceDTO",
    "InvoiceLineDTO",
    "InvoiceLineItemDTO",
    "InvoiceRequestDTO",
    "LegacyInventoryRecordDTO",
    "MODULO_11_WEIGHTS",
    "TWO_DECIMALS",
    "VALID_RUC_PREFIXES",
    "validate_peruvian_ruc_modulo11",
]
