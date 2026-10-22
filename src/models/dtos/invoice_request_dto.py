"""DTOs y Contratos Pydantic para Emisión de Comprobantes Electrónicos OASIS UBL 2.1 (RS N° 097-2012/SUNAT)."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TWO_DECIMALS = Decimal("0.01")
MODULO_11_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
VALID_RUC_PREFIXES = ("10", "15", "17", "20")


def validate_peruvian_ruc_modulo11(ruc: str) -> str:
    """Valida algorítmicamente un RUC peruano de 11 dígitos aplicando el Módulo 11 de SUNAT."""
    cleaned = ruc.strip()
    if len(cleaned) != 11 or not cleaned.isdigit():
        raise ValueError(f"RUC inválido '{ruc}': Debe contener exactamente 11 dígitos numéricos.")
    if not cleaned.startswith(VALID_RUC_PREFIXES):
        raise ValueError(
            f"RUC inválido '{ruc}': El prefijo '{cleaned[:2]}' no pertenece al padrón SUNAT {VALID_RUC_PREFIXES}."
        )
    weighted_sum = sum(int(cleaned[i]) * MODULO_11_WEIGHTS[i] for i in range(10))
    remainder = 11 - (weighted_sum % 11)
    check_digit = 0 if remainder == 10 else (1 if remainder == 11 else remainder)
    if int(cleaned[10]) != check_digit:
        raise ValueError(
            f"RUC inválido '{ruc}': Dígito verificador '{cleaned[10]}' no coincide con Módulo 11 (esperado '{check_digit}')."
        )
    return cleaned


class Catalog01DocumentType(str, Enum):
    """Catálogo 01 SUNAT: Código de Tipo de Documento."""

    FACTURA = "01"
    BOLETA = "03"
    NOTA_CREDITO = "07"
    NOTA_DEBITO = "08"


class Catalog02CurrencyCode(str, Enum):
    """Catálogo 02 SUNAT (ISO 4217): Código de Tipo de Moneda."""

    PEN = "PEN"
    USD = "USD"
    EUR = "EUR"


class Catalog05TaxSchemeCode(str, Enum):
    """Catálogo 05 SUNAT: Códigos de Tipos de Tributos."""

    IGV = "1000"
    IVAP = "1016"
    ISC = "2000"
    ICBPER = "7152"
    EXPORTACION = "9995"
    GRATUITO = "9996"
    EXONERADO = "9997"
    INAFECTO = "9998"
    OTROS = "9999"


class Catalog07IgvAffectationCode(str, Enum):
    """Catálogo 07 SUNAT: Códigos de Tipo de Afectación del IGV."""

    GRAVADO_OPERACION_ONEROSA = "10"
    GRAVADO_RETIRO_POR_PREMIO = "11"
    GRAVADO_RETIRO_POR_DONACION = "12"
    GRAVADO_RETIRO = "13"
    GRAVADO_RETIRO_POR_PUBLICIDAD = "14"
    GRAVADO_BONIFICACIONES = "15"
    GRAVADO_RETIRO_ENTREGA_TRABAJADORES = "16"
    GRAVADO_IVAP = "17"
    EXONERADO_OPERACION_ONEROSA = "20"
    EXONERADO_TRANSFERENCIA_GRATUITA = "21"
    INAFECTO_OPERACION_ONEROSA = "30"
    INAFECTO_RETIRO_BONIFICACION = "31"
    INAFECTO_RETIRO = "32"
    INAFECTO_RETIRO_MUESTRAS_MEDICAS = "33"
    INAFECTO_RETIRO_CONVENIO_COLECTIVO = "34"
    INAFECTO_RETIRO_POR_PREMIO = "35"
    INAFECTO_RETIRO_POR_PUBLICIDAD = "36"
    EXPORTACION = "40"


class Catalog08DebitNoteTypeCode(str, Enum):
    """Catálogo 08 SUNAT: Códigos de Tipo de Nota de Débito."""

    INTERESES_POR_MORA = "01"
    AUMENTO_EN_EL_VALOR = "02"
    PENALIDADES_OTROS_CONCEPTOS = "03"
    AJUSTES_OPERACIONES_EXPORTACION = "10"
    AJUSTES_AFECTOS_IVAP = "11"


class InvoiceLineDTO(BaseModel):
    """Estructura estricta del ítem de la factura (`InvoiceLineItemDTO`) basada en `UBL-Invoice-2.1.xsd` para SUNAT.
    Contiene exactamente los 16 campos normativos definidos en `specs/contracts/domain-dtos-schema.json`.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, title="InvoiceLineItemDTO")

    line_number: int = Field(
        ...,
        ge=1,
        description="Número secuencial de la línea (XPath: cac:InvoiceLine/cbc:ID)",
    )
    product_sku: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="Código interno del producto SKU (XPath: cac:InvoiceLine/cac:Item/cac:SellersItemIdentification/cbc:ID)",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Descripción detallada del ítem (XPath: cac:InvoiceLine/cac:Item/cbc:Description)",
    )
    unit_code: str = Field(
        default="NIU",
        description="Unidad de medida según Catálogo 03 SUNAT, ej. NIU, KGM (XPath: cac:InvoiceLine/cbc:InvoicedQuantity/@unitCode)",
    )
    quantity: Decimal = Field(
        ...,
        gt=Decimal("0"),
        description="Cantidad facturada (XPath: cac:InvoiceLine/cbc:InvoicedQuantity)",
    )
    unit_value: Decimal = Field(
        ...,
        ge=Decimal("0.00"),
        description="Valor unitario sin impuestos (XPath: cac:InvoiceLine/cac:Price/cbc:PriceAmount)",
    )
    catalog_07_igv_type: Catalog07IgvAffectationCode = Field(
        default=Catalog07IgvAffectationCode.GRAVADO_OPERACION_ONEROSA,
        description="Código del Catálogo 07 de SUNAT, ej. '10' (Gravado), '20' (Exonerado), '30' (Inafecto)",
    )
    igv_rate: Decimal = Field(
        default=Decimal("0.18"),
        ge=Decimal("0.00"),
        description="Tasa del IGV, ej. 0.18",
    )
    igv_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Monto total del IGV de la línea (XPath: cac:InvoiceLine/cac:TaxTotal/cac:TaxAmount)",
    )
    isc_rate: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Tasa del ISC si aplica",
    )
    isc_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Monto total del ISC",
    )
    icbper_quantity: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        description="Cantidad de bolsas plásticas si aplica",
    )
    icbper_unit_tax: Decimal = Field(
        default=Decimal("0.50"),
        ge=Decimal("0.00"),
        description="Impuesto unitario por bolsa plástica",
    )
    icbper_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Monto total del ICBPER",
    )
    line_extension_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Valor de venta de la línea (Cantidad * Valor unitario)",
    )
    line_total_with_taxes: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Precio de venta total de la línea con impuestos incluidos",
    )

    @property
    def catalog_05_tax_code(self) -> Catalog05TaxSchemeCode:
        """Retorna el código de tributo del Catálogo 05 SUNAT derivado del Catálogo 07."""
        if self.catalog_07_igv_type == Catalog07IgvAffectationCode.GRAVADO_IVAP:
            return Catalog05TaxSchemeCode.IVAP
        if self.catalog_07_igv_type.value.startswith("1"):
            return Catalog05TaxSchemeCode.IGV
        if self.catalog_07_igv_type.value.startswith("2"):
            return Catalog05TaxSchemeCode.EXONERADO
        if self.catalog_07_igv_type.value.startswith("3"):
            return Catalog05TaxSchemeCode.INAFECTO
        return Catalog05TaxSchemeCode.EXPORTACION

    @property
    def unit_price_with_taxes(self) -> Decimal:
        """Retorna el precio unitario referencial con impuestos incluidos (Catálogo 16 código '01')."""
        unit_with_tax = self.unit_value * (Decimal("1.00") + self.isc_rate) * (Decimal("1.00") + self.igv_rate)
        return unit_with_tax.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)

    @model_validator(mode="after")
    def compute_line_taxes_and_totals(self) -> "InvoiceLineDTO":
        """Calcula con precisión decimal bancaria (ROUND_HALF_UP) el valor de venta, ISC, IGV e ICBPER."""
        self.line_extension_amount = (self.quantity * self.unit_value).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)
        self.isc_amount = (self.line_extension_amount * self.isc_rate).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)

        if self.catalog_07_igv_type.value.startswith("1"):
            taxable_base_igv = self.line_extension_amount + self.isc_amount
            self.igv_amount = (taxable_base_igv * self.igv_rate).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)
        else:
            self.igv_rate = Decimal("0.00")
            self.igv_amount = Decimal("0.00")

        self.icbper_amount = (Decimal(self.icbper_quantity) * self.icbper_unit_tax).quantize(
            TWO_DECIMALS, rounding=ROUND_HALF_UP
        )

        self.line_total_with_taxes = (
            self.line_extension_amount + self.isc_amount + self.igv_amount + self.icbper_amount
        ).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)
        return self


InvoiceLineItemDTO = InvoiceLineDTO


class InvoiceRequestDTO(BaseModel):
    """Contrato principal de Emisión de Comprobante Electrónico UBL 2.1 (Factura, Boleta, Nota de Crédito/Débito)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ubl_version: Literal["2.1"] = Field(default="2.1", description="Versión del estándar OASIS UBL.")
    customization_id: Literal["2.0"] = Field(default="2.0", description="Versión de la estructura del documento SUNAT.")
    operation_type_catalog_51: str = Field(
        default="0101",
        description="Catálogo 51 SUNAT: Tipo de operación (0101 = Venta Interna).",
    )
    document_type_catalog_01: Catalog01DocumentType = Field(
        ...,
        description="Catálogo 01 SUNAT: 01=Factura, 03=Boleta, 07=Nota de Crédito, 08=Nota de Débito.",
    )
    series: str = Field(
        ...,
        pattern=r"^[FB][A-Z0-9]{3}$",
        description="Serie electrónica de 4 caracteres (ej. F001, B001, FD01, FC01).",
    )
    correlative: int = Field(..., ge=1, le=99999999, description="Correlativo numérico del comprobante.")
    issue_date: date = Field(..., description="Fecha de emisión (YYYY-MM-DD).")
    issue_time: time = Field(default=time(12, 0, 0), description="Hora de emisión (HH:MM:SS).")
    currency_code_catalog_02: Catalog02CurrencyCode = Field(
        default=Catalog02CurrencyCode.PEN,
        description="Catálogo 02 SUNAT: Moneda del comprobante (PEN, USD, EUR).",
    )

    # Datos del Emisor (ABC Software Corp)
    issuer_ruc: str = Field(..., description="RUC de 11 dígitos del emisor validado por Módulo 11.")
    issuer_legal_name: str = Field(..., min_length=3, max_length=150, description="Razón social del emisor.")
    issuer_ubigeo: str = Field(default="150101", pattern=r"^[0-9]{6}$", description="Código Ubigeo INEI (Catálogo 13).")

    # Datos del Receptor / Cliente
    customer_doc_type_catalog_06: Literal["1", "6", "4", "7", "0"] = Field(
        ...,
        description="Catálogo 06 SUNAT: 6=RUC, 1=DNI, 4=Carnet Extranjería, 7=Pasaporte, 0=Varios.",
    )
    customer_doc_number: str = Field(..., min_length=1, max_length=15, description="Número de documento del cliente.")
    customer_legal_name: str = Field(..., min_length=2, max_length=150, description="Razón social o nombre del cliente.")

    # Campos específicos para Nota de Débito (Catálogo 08) y Nota de Crédito
    catalog_08_debit_note_type: Optional[Catalog08DebitNoteTypeCode] = Field(
        default=None,
        description="Código del Catálogo 08 SUNAT (obligatorio cuando document_type_catalog_01 == '08').",
    )
    referenced_document_series_number: Optional[str] = Field(
        default=None,
        pattern=r"^[FB][A-Z0-9]{3}-[0-9]{1,8}$",
        description="Serie-Correlativo del comprobante que modifica la Nota de Débito/Crédito.",
    )
    discrepancy_reason: Optional[str] = Field(
        default=None,
        max_length=250,
        description="Sustento o motivo de emisión de la Nota de Débito/Crédito.",
    )

    # Vínculo opcional con ficha de almacén legacy
    source_legacy_record_id: Optional[str] = Field(
        default=None,
        description="ID de la ficha de almacén legacy origen si fue generado por migración.",
    )

    lines: List[InvoiceLineDTO] = Field(..., min_length=1, description="Detalle de ítems del comprobante.")

    # Totales Tributarios UBL 2.1 (<cac:TaxTotal> y <cac:LegalMonetaryTotal>)
    total_gravadas: Decimal = Field(default=Decimal("0.00"), description="Total valor de venta operaciones gravadas.")
    total_exoneradas: Decimal = Field(default=Decimal("0.00"), description="Total valor de venta operaciones exoneradas.")
    total_inafectas: Decimal = Field(default=Decimal("0.00"), description="Total valor de venta operaciones inafectas.")
    total_igv: Decimal = Field(default=Decimal("0.00"), description="Sumatoria total de IGV (Catálogo 05 = 1000).")
    total_isc: Decimal = Field(default=Decimal("0.00"), description="Sumatoria total de ISC (Catálogo 05 = 2000).")
    total_icbper: Decimal = Field(default=Decimal("0.00"), description="Sumatoria total de ICBPER (Catálogo 05 = 7152).")
    payable_amount: Decimal = Field(default=Decimal("0.00"), description="Importe total a pagar (<cbc:PayableAmount>).")

    @field_validator("issuer_ruc")
    @classmethod
    def check_issuer_ruc(cls, value: str) -> str:
        return validate_peruvian_ruc_modulo11(value)

    @model_validator(mode="after")
    def validate_sunat_business_rules_and_totals(self) -> "InvoiceRequestDTO":
        """Aplica reglas de negocio RS 097-2012 (Módulo 11 para cliente RUC, Catálogo 08 para Nota de Débito)
        y consolida los totales tributarios del comprobante.
        """
        if self.document_type_catalog_01 == Catalog01DocumentType.FACTURA and self.customer_doc_type_catalog_06 != "6":
            raise ValueError("SUNAT_RULE_01: Las Facturas Electrónicas ('01') requieren cliente con RUC (Catálogo 06 = '6').")

        if self.customer_doc_type_catalog_06 == "6":
            validate_peruvian_ruc_modulo11(self.customer_doc_number)

        if self.document_type_catalog_01 == Catalog01DocumentType.NOTA_DEBITO:
            if not self.catalog_08_debit_note_type:
                raise ValueError(
                    "SUNAT_CATALOG_08_REQUIRED: Una Nota de Débito ('08') exige un código válido del Catálogo 08 SUNAT."
                )
            if not self.referenced_document_series_number or not self.discrepancy_reason:
                raise ValueError(
                    "SUNAT_BILLING_REFERENCE_REQUIRED: Las Notas de Débito requieren documento de referencia y sustento."
                )

        self.total_gravadas = sum(
            (line.line_extension_amount for line in self.lines if line.catalog_07_igv_type.value.startswith("1")),
            Decimal("0.00"),
        ).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)

        self.total_exoneradas = sum(
            (line.line_extension_amount for line in self.lines if line.catalog_07_igv_type.value.startswith("2")),
            Decimal("0.00"),
        ).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)

        self.total_inafectas = sum(
            (line.line_extension_amount for line in self.lines if line.catalog_07_igv_type.value.startswith("3")),
            Decimal("0.00"),
        ).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)

        self.total_isc = sum((line.isc_amount for line in self.lines), Decimal("0.00")).quantize(
            TWO_DECIMALS, rounding=ROUND_HALF_UP
        )
        self.total_igv = sum((line.igv_amount for line in self.lines), Decimal("0.00")).quantize(
            TWO_DECIMALS, rounding=ROUND_HALF_UP
        )
        self.total_icbper = sum((line.icbper_amount for line in self.lines), Decimal("0.00")).quantize(
            TWO_DECIMALS, rounding=ROUND_HALF_UP
        )

        self.payable_amount = (
            self.total_gravadas
            + self.total_exoneradas
            + self.total_inafectas
            + self.total_isc
            + self.total_igv
            + self.total_icbper
        ).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)

        return self
