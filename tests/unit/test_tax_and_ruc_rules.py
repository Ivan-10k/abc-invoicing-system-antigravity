"""Suite de Pruebas Unitarias y de Integración SDD (`pytest`) para:
1. Algoritmo Módulo 11 de validación de RUC (SUNAT).
2. Cálculo exacto de impuestos: IGV (18% sobre Base + ISC), ISC (Catálogo 05 = '2000') e ICBPER (Catálogo 05 = '7152').
3. Validación estricta del Catálogo 08 SUNAT para Notas de Débito ('08').
4. Migración de Fichas de Almacén Legacy (RS N° 234-2006) con trazabilidad (`migrated_invoice_id` y `audit_sha256`).
5. Generación XML UBL 2.1 (`UBL-Invoice-2.1.xsd` / `UBL-DebitNote-2.1.xsd`) y flujo OSE con `InvoiceController`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.controllers.invoice_controller import InvoiceController
from src.infrastructure.sunat_ose_adapter import (
    InMemoryInvoiceRepositoryAdapter,
    InMemoryKardexRepositoryAdapter,
    SunatOseNubefactAdapter,
)
from src.infrastructure.ubl_xml_builder import Ubl21XmlBuilderAndSignerAdapter
from src.models.dtos.invoice_dtos import (
    Catalog01DocumentType,
    Catalog02CurrencyCode,
    Catalog07IgvAffectationCode,
    Catalog08DebitNoteTypeCode,
    InvoiceDTO,
    InvoiceLineDTO,
    LegacyInventoryRecordDTO,
    validate_peruvian_ruc_modulo11,
)


@pytest.fixture
def mvc_controller() -> InvoiceController:
    """Ensambla el Controlador MVC inyectando los Adaptadores a través de los Puertos."""
    return InvoiceController(
        xml_signer_port=Ubl21XmlBuilderAndSignerAdapter(),
        ose_gateway_port=SunatOseNubefactAdapter(),
        invoice_repo_port=InMemoryInvoiceRepositoryAdapter(),
        kardex_repo_port=InMemoryKardexRepositoryAdapter(),
    )


class TestRucModulo11Validation:
    """CU-03: Pruebas del algoritmo Módulo 11 de SUNAT."""

    @pytest.mark.parametrize(
        "valid_ruc,expected_type",
        [
            ("20601234565", "PERSONA_JURIDICA"),
            ("20512345671", "PERSONA_JURIDICA"),
            ("10456789019", "PERSONA_NATURAL_CON_NEGOCIO"),
        ],
    )
    def test_valid_rucs_pass_modulo11(
        self,
        mvc_controller: InvoiceController,
        valid_ruc: str,
        expected_type: str,
    ) -> None:
        result = mvc_controller.validate_ruc_modulo11(valid_ruc)
        assert result["is_valid"] is True
        assert result["taxpayer_type"] == expected_type
        assert validate_peruvian_ruc_modulo11(valid_ruc) == valid_ruc

    @pytest.mark.parametrize(
        "invalid_ruc,expected_digit",
        [
            ("20601234568", 5),  # Dígito verificador incorrecto (8 en lugar de 5)
            ("30601234565", None),  # Prefijo '30' no permitido por SUNAT
            ("206012345", None),  # Longitud < 11 dígitos
        ],
    )
    def test_invalid_rucs_are_rejected_by_modulo11(
        self,
        mvc_controller: InvoiceController,
        invalid_ruc: str,
        expected_digit: int | None,
    ) -> None:
        result = mvc_controller.validate_ruc_modulo11(invalid_ruc)
        assert result["is_valid"] is False
        assert result["expected_check_digit"] == expected_digit


class TestTaxCalculationIgvIscIcbper:
    """CU-01: Pruebas de cálculo exacto de IGV (18%), ISC e ICBPER y generación XML UBL 2.1."""

    def test_invoice_with_igv_isc_and_icbper_matches_sunat_rules(
        self,
        mvc_controller: InvoiceController,
    ) -> None:
        request = InvoiceDTO(
            document_type_catalog_01=Catalog01DocumentType.FACTURA,
            series="F001",
            correlative=1045,
            issue_date=date(2026, 10, 22),
            currency_code_catalog_02=Catalog02CurrencyCode.PEN,
            issuer_ruc="20601234565",
            issuer_legal_name="ABC SOFTWARE CORP S.A.C.",
            customer_doc_type_catalog_06="6",
            customer_doc_number="20512345671",
            customer_legal_name="BODEGA CENTRAL MAYORISTA S.A.C.",
            lines=[
                # 1. Arroz gravado con IGV 18%: 10 * 120.00 = 1200.00 | IGV = 216.00
                InvoiceLineDTO(
                    line_number=1,
                    product_sku="AB-ARR-50",
                    description="Saco Arroz Extra 50kg",
                    unit_code="BG",
                    quantity=Decimal("10"),
                    unit_value=Decimal("120.00"),
                    catalog_07_igv_type=Catalog07IgvAffectationCode.GRAVADO_OPERACION_ONEROSA,
                ),
                # 2. Licor con ISC 20% + IGV 18% sobre (Base + ISC):
                # Base = 2 * 250.00 = 500.00 | ISC = 100.00 | IGV = (500 + 100) * 0.18 = 108.00
                InvoiceLineDTO(
                    line_number=2,
                    product_sku="BE-LIC-12",
                    description="Caja Licor Ron Cartavio x12",
                    unit_code="BX",
                    quantity=Decimal("2"),
                    unit_value=Decimal("250.00"),
                    catalog_07_igv_type=Catalog07IgvAffectationCode.GRAVADO_OPERACION_ONEROSA,
                    isc_rate=Decimal("0.20"),
                ),
                # 3. Bolsa plástica con ICBPER (S/ 0.50 c/u):
                # Base = 4 * 0.10 = 0.40 | IGV = 0.07 | ICBPER = 4 * 0.50 = 2.00
                InvoiceLineDTO(
                    line_number=3,
                    product_sku="EMP-BOL-G",
                    description="Bolsa Plástica Biodegradable Grande",
                    unit_code="NIU",
                    quantity=Decimal("4"),
                    unit_value=Decimal("0.10"),
                    catalog_07_igv_type=Catalog07IgvAffectationCode.GRAVADO_OPERACION_ONEROSA,
                    icbper_quantity=4,
                    icbper_unit_tax=Decimal("0.50"),
                ),
            ],
        )

        result = mvc_controller.emit_invoice_or_boleta(request)
        tax_summary = result["tax_summary"]

        assert result["status"] == "ACEPTADO"
        assert result["sunat_response_code"] == "0"
        assert result["xml_digest_value"] is not None
        assert tax_summary["total_gravadas"] == 1700.40
        assert tax_summary["total_isc"] == 100.00
        assert tax_summary["total_igv"] == 324.07
        assert tax_summary["total_icbper"] == 2.00
        assert tax_summary["payable_amount"] == 2126.47


class TestCatalog08DebitNoteRules:
    """CU-02: Pruebas del Catálogo 08 SUNAT en Notas de Débito ('08')."""

    @pytest.mark.parametrize(
        "cat08_code",
        [
            Catalog08DebitNoteTypeCode.INTERESES_POR_MORA,
            Catalog08DebitNoteTypeCode.AUMENTO_EN_EL_VALOR,
            Catalog08DebitNoteTypeCode.PENALIDADES_OTROS_CONCEPTOS,
            Catalog08DebitNoteTypeCode.AJUSTES_OPERACIONES_EXPORTACION,
            Catalog08DebitNoteTypeCode.AJUSTES_AFECTOS_IVAP,
        ],
    )
    def test_debit_note_accepts_all_valid_catalog_08_codes(
        self,
        mvc_controller: InvoiceController,
        cat08_code: Catalog08DebitNoteTypeCode,
    ) -> None:
        debit_note = InvoiceDTO(
            document_type_catalog_01=Catalog01DocumentType.NOTA_DEBITO,
            series="FD01",
            correlative=15,
            issue_date=date(2026, 10, 22),
            issuer_ruc="20601234565",
            issuer_legal_name="ABC SOFTWARE CORP S.A.C.",
            customer_doc_type_catalog_06="6",
            customer_doc_number="20512345671",
            customer_legal_name="BODEGA CENTRAL MAYORISTA S.A.C.",
            catalog_08_debit_note_type=cat08_code,
            referenced_document_series_number="F001-1045",
            discrepancy_reason="Ajuste comercial sustentado según Catálogo 08 SUNAT",
            lines=[
                InvoiceLineDTO(
                    line_number=1,
                    product_sku="AB-ARR-50",
                    description="Ajuste de valor en Saco Arroz Extra 50kg",
                    quantity=Decimal("10"),
                    unit_value=Decimal("10.00"),
                )
            ],
        )
        res = mvc_controller.emit_credit_or_debit_note(debit_note)
        assert res["status"] == "ACEPTADO"
        assert res["catalog_08_debit_note_type"] == cat08_code.value
        assert res["tax_summary"]["payable_amount"] == 118.00

    def test_debit_note_without_catalog_08_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="SUNAT_CATALOG_08_REQUIRED"):
            InvoiceDTO(
                document_type_catalog_01=Catalog01DocumentType.NOTA_DEBITO,
                series="FD01",
                correlative=16,
                issue_date=date(2026, 10, 22),
                issuer_ruc="20601234565",
                issuer_legal_name="ABC SOFTWARE CORP S.A.C.",
                customer_doc_type_catalog_06="6",
                customer_doc_number="20512345671",
                customer_legal_name="BODEGA CENTRAL MAYORISTA S.A.C.",
                catalog_08_debit_note_type=None,
                referenced_document_series_number="F001-1045",
                discrepancy_reason="Sustento sin código Catálogo 08",
                lines=[
                    InvoiceLineDTO(
                        line_number=1,
                        product_sku="AB-ARR-50",
                        description="Ajuste sin Catálogo 08",
                        quantity=Decimal("1"),
                        unit_value=Decimal("50.00"),
                    )
                ],
            )


class TestLegacyKardexMigrationTraceability:
    """CU-04: Pruebas de migración de fichas informales de almacén legacy (RS N° 234-2006)."""

    def test_legacy_sale_record_migrates_and_couples_to_ubl_invoice(
        self,
        mvc_controller: InvoiceController,
    ) -> None:
        legacy_record = LegacyInventoryRecordDTO(
            fecha=date(2026, 10, 15),
            ingreso=Decimal("0.00"),
            salida=Decimal("25.00"),
            producto="Azúcar Rubia Saco 50k",
            nro_documento="F001-000890",
        )
        migration_result = mvc_controller.migrate_legacy_kardex_record(
            legacy_dto=legacy_record,
            issuer_ruc="20601234565",
            issuer_legal_name="ABC SOFTWARE CORP S.A.C.",
            customer_ruc="20512345671",
            customer_legal_name="BODEGA CENTRAL MAYORISTA S.A.C.",
            default_unit_value=Decimal("100.00"),
        )

        assert migration_result["original_nro_documento"] == "F001-000890"
        assert migration_result["normalized_series"] == "F001"
        assert migration_result["normalized_correlative"] == 890
        assert migration_result["migrated_invoice_id"] is not None
        assert len(str(migration_result["audit_sha256"])) == 64
        assert migration_result["coupled_ubl_invoice"]["document_id"] == "F001-890"

    def test_legacy_ambiguous_movement_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="LEGACY_KARDEX_AMBIGUOUS_MOVEMENT"):
            LegacyInventoryRecordDTO(
                fecha=date(2026, 10, 15),
                ingreso=Decimal("10.00"),
                salida=Decimal("5.00"),
                producto="Aceite Vegetal Caja x12",
                nro_documento="F001-000891",
            )
