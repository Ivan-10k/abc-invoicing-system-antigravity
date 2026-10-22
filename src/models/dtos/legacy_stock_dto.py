"""DTO y contrato Pydantic para migración de fichas informales de almacén legacy (RS N° 234-2006/SUNAT)."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

SERIES_CORRELATIVE_REGEX = re.compile(r"^([FBE][A-Z0-9]{3})[-_\s]+0*(\d{1,8})$", re.IGNORECASE)


class LegacyInventoryRecordDTO(BaseModel):
    """Ficha de almacén legacy (`fecha`, `ingreso`, `salida`, `producto`, `nro_documento`)
    con metadatos de normalización y trazabilidad hacia el comprobante electrónico UBL 2.1.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    legacy_record_id: UUID = Field(
        default_factory=uuid4,
        description="Identificador único asignado durante la migración.",
    )
    fecha: date = Field(..., description="Fecha original registrada en la ficha de almacén legacy.")
    ingreso: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Cantidad ingresada al almacén.",
    )
    salida: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Cantidad retirada del almacén.",
    )
    producto: str = Field(
        ...,
        min_length=2,
        max_length=250,
        description="Descripción o nombre del producto en el sistema legacy.",
    )
    nro_documento: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Número de documento informal original (ej. 'F001-000890').",
    )
    migrated_invoice_id: Optional[str] = Field(
        default=None,
        description="ID del comprobante electrónico UBL 2.1 generado o acoplado (trazabilidad bidireccional).",
    )
    normalized_series: Optional[str] = Field(
        default=None,
        description="Serie normalizada según estándar SUNAT (4 caracteres).",
    )
    normalized_correlative: Optional[int] = Field(
        default=None,
        ge=1,
        description="Correlativo entero extraído del documento legacy.",
    )
    sunat_table12_operation_type: Literal["01", "02", "05", "16", "99"] = Field(
        default="01",
        description="Tabla 12 SUNAT (RS 234-2006): 01=Venta, 02=Compra, 05=Devolución, 16=Saldo Inicial, 99=Otros.",
    )
    audit_sha256: Optional[str] = Field(
        default=None,
        description="Hash SHA-256 inmutable de los 5 campos originales de la ficha legacy.",
    )

    @model_validator(mode="after")
    def validate_kardex_movement_and_compute_traceability(self) -> "LegacyInventoryRecordDTO":
        """Valida que no existan movimientos ambiguos, extrae serie/correlativo y calcula el hash SHA-256."""
        if (self.ingreso > Decimal("0.00") and self.salida > Decimal("0.00")) or (
            self.ingreso == Decimal("0.00") and self.salida == Decimal("0.00")
        ):
            raise ValueError(
                "LEGACY_KARDEX_AMBIGUOUS_MOVEMENT: La ficha debe registrar exclusivamente ingreso > 0 o salida > 0."
            )

        # Inferir tipo de operación Tabla 12 SUNAT si no fue forzado
        if self.ingreso > Decimal("0.00") and self.sunat_table12_operation_type == "01":
            self.sunat_table12_operation_type = "02"  # 02 = Compra / Ingreso

        # Normalizar serie y correlativo si cumple patrón de comprobante
        match = SERIES_CORRELATIVE_REGEX.match(self.nro_documento)
        if match:
            self.normalized_series = match.group(1).upper()
            self.normalized_correlative = int(match.group(2))

        # Generar huella SHA-256 de auditoría
        canonical_payload = (
            f"{self.fecha.isoformat()}|{self.ingreso:.2f}|{self.salida:.2f}|"
            f"{self.producto.strip()}|{self.nro_documento.strip()}"
        )
        self.audit_sha256 = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        return self
