"""Controlador MVC Limpio (Hexagonal-Ready) para Emisión Electrónica SUNAT UBL 2.1,
Notas de Débito Catálogo 08, Validación RUC Módulo 11 y Migración de Almacén Legacy.

Regla Arquitectónica (ADR-0001):
`InvoiceController` NO importa ninguna clase concreta de `src/infrastructure/` (ni `sqlite3`, ni `lxml`,
ni `httpx`). Recibe todas sus dependencias mediante Inyección de Constructores a través de los
Puertos definidos en `src/models/ports/i_ose_sunat_gateway.py`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List

from src.models.dtos.invoice_request_dto import (
    Catalog01DocumentType,
    InvoiceRequestDTO,
     MODULO_11_WEIGHTS,
    VALID_RUC_PREFIXES,
    validate_peruvian_ruc_modulo11,
)
from src.models.dtos.legacy_stock_dto import LegacyInventoryRecordDTO
from src.models.entities.invoice import ElectronicInvoiceEntity
from src.models.ports.i_ose_sunat_gateway import (
    IInvoiceRepositoryPort,
    IKardexRepositoryPort,
    IOseSunatGatewayPort,
    IXmlUblSignerPort,
)


class InvoiceController:
    """Controlador de Aplicación MVC que orquesta los Casos de Uso (CU-01 a CU-05)
    usando exclusivamente entidades del Modelo y Puertos de Salida.
    """

    def __init__(
        self,
        xml_signer_port: IXmlUblSignerPort,
        ose_gateway_port: IOseSunatGatewayPort,
        invoice_repo_port: IInvoiceRepositoryPort,
        kardex_repo_port: IKardexRepositoryPort,
    ) -> None:
        self._xml_signer = xml_signer_port
        self._ose_gateway = ose_gateway_port
        self._invoice_repo = invoice_repo_port
        self._kardex_repo = kardex_repo_port

    def emit_invoice_or_boleta(self, request_dto: InvoiceRequestDTO) -> Dict[str, object]:
        """CU-01: Emite una Factura ('01') o Boleta de Venta ('03') UBL 2.1 con IGV, ISC e ICBPER."""
        if request_dto.document_type_catalog_01 not in (
            Catalog01DocumentType.FACTURA,
            Catalog01DocumentType.BOLETA,
        ):
            raise ValueError(
                "SUNAT-ERR-1003: El endpoint de Facturas/Boletas solo admite Catálogo 01 en ['01', '03']."
            )
        return self._orchestrate_ubl_emission(request_dto)

    def emit_credit_or_debit_note(self, request_dto: InvoiceRequestDTO) -> Dict[str, object]:
        """CU-02: Emite una Nota de Débito ('08' con Catálogo 08 obligatorio) o Nota de Crédito ('07')."""
        if request_dto.document_type_catalog_01 not in (
            Catalog01DocumentType.NOTA_CREDITO,
            Catalog01DocumentType.NOTA_DEBITO,
        ):
            raise ValueError(
                "SUNAT-ERR-2119: El flujo de Notas solo admite Catálogo 01 en ['07' (Crédito), '08' (Débito)]."
            )
        return self._orchestrate_ubl_emission(request_dto)

    def migrate_legacy_kardex_record(
        self,
        legacy_dto: LegacyInventoryRecordDTO,
        issuer_ruc: str,
        issuer_legal_name: str,
        customer_ruc: str,
        customer_legal_name: str,
        default_unit_value: Decimal = Decimal("100.00"),
    ) -> Dict[str, object]:
        """CU-04: Migra una ficha informal de almacén legacy (`fecha`, `ingreso`, `salida`, `producto`,
        `nro_documento`) hacia el Kardex Formato 13.1 (RS N° 234-2006) y, si es salida de venta,
        genera y acopla su comprobante electrónico UBL 2.1 preservando `migrated_invoice_id` y `audit_sha256`.
        """
        invoice_summary = None
        if legacy_dto.salida > Decimal("0.00"):
            invoice_entity = ElectronicInvoiceEntity.from_legacy_kardex_record(
                legacy_dto=legacy_dto,
                issuer_ruc=issuer_ruc,
                issuer_legal_name=issuer_legal_name,
                customer_ruc=customer_ruc,
                customer_legal_name=customer_legal_name,
                unit_value=default_unit_value,
            )
            signed_artifact = self._xml_signer.build_validate_and_sign_ubl21(invoice_entity)
            cdr_response = self._ose_gateway.send_signed_document(invoice_entity, signed_artifact)
            invoice_entity.apply_cdr_response(
                cdr_code=cdr_response.sunat_response_code,
                cdr_description=cdr_response.sunat_description,
                digest_value=cdr_response.digest_value,
                observations=cdr_response.observations,
            )
            self._invoice_repo.save(invoice_entity)
            invoice_summary = invoice_entity.to_summary_dict()

        # Persistir en Kardex Formato 13.1 con el vínculo `migrated_invoice_id` ya sellado
        self._kardex_repo.save_legacy_migration(legacy_dto)

        return {
            "legacy_record_id": str(legacy_dto.legacy_record_id),
            "original_nro_documento": legacy_dto.nro_documento,
            "normalized_series": legacy_dto.normalized_series,
            "normalized_correlative": legacy_dto.normalized_correlative,
            "sunat_table12_operation_type": legacy_dto.sunat_table12_operation_type,
            "migrated_invoice_id": legacy_dto.migrated_invoice_id,
            "audit_sha256": legacy_dto.audit_sha256,
            "coupled_ubl_invoice": invoice_summary,
        }

    @staticmethod
    def validate_ruc_modulo11(ruc: str) -> Dict[str, object]:
        """CU-03: Ejecuta la validación algorítmica Módulo 11 retornando diagnóstico detallado."""
        cleaned = ruc.strip()
        try:
            validate_peruvian_ruc_modulo11(cleaned)
            taxpayer_map: Dict[str, str] = {
                "10": "PERSONA_NATURAL_CON_NEGOCIO",
                "15": "SUJECIONES_ESPECIALES_NO_DOMICILIADOS",
                "17": "PERSONA_NATURAL_REGIMEN_TRANSITORIO",
                "20": "PERSONA_JURIDICA",
            }
            return {
                "ruc": cleaned,
                "is_valid": True,
                "taxpayer_type": taxpayer_map.get(cleaned[:2], "CONTRIBUYENTE_SUNAT"),
                "expected_check_digit": int(cleaned[10]),
                "provided_check_digit": int(cleaned[10]),
                "message": "RUC válido conforme al algoritmo Módulo 11 de SUNAT.",
            }
        except ValueError as exc:
            expected_digit = None
            if len(cleaned) == 11 and cleaned.isdigit() and cleaned.startswith(VALID_RUC_PREFIXES):
                weighted_sum = sum(int(cleaned[i]) * MODULO_11_WEIGHTS[i] for i in range(10))
                rem = 11 - (weighted_sum % 11)
                expected_digit = 0 if rem == 10 else (1 if rem == 11 else rem)
            return {
                "ruc": cleaned,
                "is_valid": False,
                "taxpayer_type": None,
                "expected_check_digit": expected_digit,
                "provided_check_digit": int(cleaned[10]) if len(cleaned) == 11 and cleaned.isdigit() else None,
                "message": str(exc),
            }

    def _orchestrate_ubl_emission(self, request_dto: InvoiceRequestDTO) -> Dict[str, object]:
        """Flujo transaccional común:
        1. Construye Entidad de Dominio y recalcula IGV, ISC, ICBPER + valida Catálogo 08 / Módulo 11.
        2. Invoca al Puerto `IXmlUblSignerPort` para generar XML UBL 2.1, validar XSD y firmar XAdES-BES.
        3. Invoca al Puerto `IOseSunatGatewayPort` para transmitir al OSE/SUNAT y recibir el CDR.
        4. Persiste en `IInvoiceRepositoryPort` y retorna el resumen auditable.
        """
        invoice_entity = ElectronicInvoiceEntity.from_request_dto(request_dto)
        signed_artifact = self._xml_signer.build_validate_and_sign_ubl21(invoice_entity)
        cdr_response = self._ose_gateway.send_signed_document(invoice_entity, signed_artifact)

        invoice_entity.apply_cdr_response(
            cdr_code=cdr_response.sunat_response_code,
            cdr_description=cdr_response.sunat_description,
            digest_value=cdr_response.digest_value,
            observations=cdr_response.observations,
        )
        self._invoice_repo.save(invoice_entity)
        return invoice_entity.to_summary_dict()
