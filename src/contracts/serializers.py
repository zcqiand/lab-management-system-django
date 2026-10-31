"""serializer 从生成 DTO 变换（design-codegen.md 方案 B：contract DTO 区为形状真源）。

列全 text，无需类型映射——只做 snake_case 列名 -> 契约 camelCase 字段名。
可空列 None 照 DRF 原样出 null（nextjs returning() 行同款，禁止静默丢字段——
 camelCase 属性名不带 source 会 AttributeError -> SkipField 悄悄缺字段，saas 同坑）。
"""

from __future__ import annotations

from rest_framework import serializers

from contracts.models import Contract


class ContractSerializer(serializers.Serializer[Contract]):
    """契约 Contract DTO（21 字段，含服务端 stamp 的 tenantId）。"""

    id = serializers.CharField(read_only=True)
    contractCode = serializers.CharField(source="contract_code", read_only=True)  # noqa: N815
    clientUnit = serializers.CharField(source="client_unit", read_only=True)  # noqa: N815
    projectName = serializers.CharField(source="project_name", read_only=True)  # noqa: N815
    projectLocation = serializers.CharField(  # noqa: N815
        source="project_location", read_only=True
    )
    constructionUnit = serializers.CharField(  # noqa: N815
        source="construction_unit", read_only=True
    )
    inspectionSpecialtyCode = serializers.CharField(  # noqa: N815
        source="inspection_specialty_code", read_only=True
    )
    buildingUnit = serializers.CharField(source="building_unit", read_only=True)  # noqa: N815
    supervisorUnit = serializers.CharField(source="supervisor_unit", read_only=True)  # noqa: N815
    inspectionPerson = serializers.CharField(  # noqa: N815
        source="inspection_person", read_only=True
    )
    inspectionPhone = serializers.CharField(source="inspection_phone", read_only=True)  # noqa: N815
    witnessUnit = serializers.CharField(source="witness_unit", read_only=True)  # noqa: N815
    witness = serializers.CharField(read_only=True)
    witnessPhone = serializers.CharField(source="witness_phone", read_only=True)  # noqa: N815
    contactPerson = serializers.CharField(source="contact_person", read_only=True)  # noqa: N815
    contactPhone = serializers.CharField(source="contact_phone", read_only=True)  # noqa: N815
    entrustedDate = serializers.CharField(source="entrusted_date", read_only=True)  # noqa: N815
    status = serializers.CharField(read_only=True)
    createdAt = serializers.CharField(source="created_at", read_only=True)  # noqa: N815
    updatedAt = serializers.CharField(source="updated_at", read_only=True)  # noqa: N815
    tenantId = serializers.CharField(source="tenant_id", read_only=True)  # noqa: N815
