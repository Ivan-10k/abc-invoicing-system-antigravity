"""Puerto de Salida (`IXmlUblSignerPort`) para construcción, validación XSD y firma digital
de comprobantes electrónicos bajo estándar OASIS `UBL-Invoice-2.1.xsd` y `UBL-DebitNote-2.1.xsd`.
"""

from __future__ import annotations

from src.models.ports.i_ose_sunat_gateway import IXmlUblSignerPort, SignedUblArtifact

__all__ = ["IXmlUblSignerPort", "SignedUblArtifact"]
