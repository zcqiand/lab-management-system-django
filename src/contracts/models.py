"""合同域模型——DB-First（family schema 归 drizzle SSOT，全 managed=False 消费）。

lab contracts 表列全 text（id/时间戳/tenant_id 都是 text，V015 家族迁移链拥有）：
id 与时间戳由 app 侧生成（uuid4 + ISO NOW，nextjs oracle newId()/NOW() 同款），
不产 django 迁移，列形以 nextjs 仓 src/db/schema.ts contracts 为准。
"""

from __future__ import annotations

from django.db import models


class Contract(models.Model):
    id = models.TextField(primary_key=True)
    contract_code = models.TextField(db_column="contract_code")
    client_unit = models.TextField(db_column="client_unit")
    project_name = models.TextField(db_column="project_name")
    # 以下可空列（drizzle schema 本就 nullable）：null=True 让 Model.__init__ 缺省落
    # None（非 ""）——空串会撞 contracts_specialty_fk 等 FK/唯一面；nextjs oracle
    # 缺键落 NULL 同款语义。DJ001 豁免=列在 PG 真身可空，非掩错。
    project_location = models.TextField(db_column="project_location", null=True)  # noqa: DJ001
    construction_unit = models.TextField(db_column="construction_unit")
    inspection_specialty_code = models.TextField(  # noqa: DJ001
        db_column="inspection_specialty_code", null=True
    )
    building_unit = models.TextField(db_column="building_unit", null=True)  # noqa: DJ001
    supervisor_unit = models.TextField(db_column="supervisor_unit", null=True)  # noqa: DJ001
    inspection_person = models.TextField(db_column="inspection_person", null=True)  # noqa: DJ001
    inspection_phone = models.TextField(db_column="inspection_phone", null=True)  # noqa: DJ001
    witness_unit = models.TextField(db_column="witness_unit")
    witness = models.TextField()
    witness_phone = models.TextField(db_column="witness_phone", null=True)  # noqa: DJ001
    contact_person = models.TextField(db_column="contact_person", null=True)  # noqa: DJ001
    contact_phone = models.TextField(db_column="contact_phone", null=True)  # noqa: DJ001
    entrusted_date = models.TextField(db_column="entrusted_date", null=True)  # noqa: DJ001
    status = models.TextField()  # active | archived
    created_at = models.TextField(db_column="created_at")
    updated_at = models.TextField(db_column="updated_at")
    tenant_id = models.TextField(db_column="tenant_id")

    class Meta:
        managed = False
        db_table = "contracts"

    def __str__(self) -> str:
        return f"{self.contract_code}({self.project_name})"
