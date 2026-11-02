"""schema parity：entities 生成区 24 表模型 ↔ 库 information_schema 逐列对账（DB-First 防线）。

生成器 scripts/scaffold-models.py 真源=库（家族细则 §6.2 DB-First）；本测试反方向锁
一致——列集 / 可空 / 类型映射 / 默认值语义漂移即红。家族 bookkeeping 表
（drizzle/rails）不参与。T1（REQ-2026-035）随生成区落地建立，后续每域切片的红灯地基。
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.models import (
    BigIntegerField,
    BooleanField,
    DateField,
    DateTimeField,
    IntegerField,
    JSONField,
    Model,
    TextField,
)
from django.db.models.fields import NOT_PROVIDED

from entities import models as entities


@pytest.fixture(autouse=True)
def _unblock_db(django_db_blocker):  # type: ignore[no-untyped-def]
    """只读 information_schema 对账，不开事务不写库——过 pytest-django 阻断器即可。"""
    with django_db_blocker.unblock():
        yield


BOOKKEEPING_TABLES = {
    "__drizzle_migrations",  # drizzle tracking
    "schema_migrations",  # rails bookkeeping（lab_dev 由本族 rails 栈共用）
    "ar_internal_metadata",  # rails bookkeeping 同上
}

# PG udt_name → 期望的 django 字段类（与生成器 scaffold-models.py 同一张映射；
# 未知类型生成器 throw 不静默，这里同样 fail-loud）
UDT_TO_FIELD: dict[str, type] = {
    "text": TextField,
    "varchar": TextField,
    "int4": IntegerField,
    "int8": BigIntegerField,
    "bool": BooleanField,
    "jsonb": JSONField,
    "date": DateField,
    "timestamp": DateTimeField,
    "timestamptz": DateTimeField,
}


def _business_tables() -> set[str]:
    with connection.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        return {row[0] for row in cur.fetchall()} - BOOKKEEPING_TABLES


def _model_by_table() -> dict[str, type]:
    out: dict[str, type] = {}
    for name in dir(entities):
        obj = getattr(entities, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, Model)
            and obj is not Model
            and not obj._meta.abstract
            and obj._meta.db_table
        ):
            out[obj._meta.db_table] = obj
    return out


def _columns(table: str) -> list[tuple[str, str, bool, str | None, bool]]:
    """(column_name, udt_name, nullable, column_default, is_pk)。"""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT c.column_name, c.udt_name, c.is_nullable = 'YES', c.column_default,
                   EXISTS (
                     SELECT 1 FROM information_schema.table_constraints tc
                     JOIN information_schema.key_column_usage k
                       ON tc.constraint_name = k.constraint_name
                      AND tc.table_schema = k.table_schema
                      AND tc.table_name = k.table_name
                     WHERE tc.constraint_type = 'PRIMARY KEY'
                       AND tc.table_schema = c.table_schema
                       AND tc.table_name = c.table_name
                       AND k.column_name = c.column_name
                   )
            FROM information_schema.columns c
            WHERE c.table_schema = 'public' AND c.table_name = %s
            ORDER BY c.ordinal_position
            """,
            [table],
        )
        return [(r[0], r[1], bool(r[2]), r[3], bool(r[4])) for r in cur.fetchall()]


def test_model_set_matches_database_tables() -> None:
    """生成区模型集合与库业务表集合双向相等（多出/缺模型都红）。"""
    tables = _business_tables()
    mapped = _model_by_table()
    assert mapped.keys() == tables, (
        f"生成区与库漂移：仅库有={sorted(tables - mapped.keys())}，"
        f"仅生成区有={sorted(mapped.keys() - tables)}"
    )


def test_columns_type_nullability_default_parity() -> None:
    """逐表逐列：db_column / 类型映射 / 可空 / 默认值语义四对账。"""
    from django.db.models import Field

    for table, model in sorted(_model_by_table().items()):
        fields: dict[str, Field] = {}
        for f in model._meta.concrete_fields:
            col = getattr(f, "db_column", None) or f.name
            fields[col] = f
        cols = _columns(table)
        assert {c[0] for c in cols} == set(fields), (
            f"{table}: 列集漂移 db={sorted(c[0] for c in cols)} model={sorted(fields)}"
        )
        for col, udt, nullable, default, is_pk in cols:
            f = fields[col]
            expected_cls = UDT_TO_FIELD.get(udt)
            assert expected_cls is not None, f"{table}.{col}: 未知 udt {udt}（生成器应已 throw）"
            assert isinstance(f, expected_cls), (
                f"{table}.{col}: udt={udt} 期望 {expected_cls.__name__}，实为 {type(f).__name__}"
            )
            assert f.null == nullable, f"{table}.{col}: nullable 漂移 db={nullable} model={f.null}"
            assert f.primary_key == is_pk, f"{table}.{col}: pk 漂移 db={is_pk}"
            # has_default() 只看 python default；db_default（PG 侧默认，家族口径）要单独查
            has_default = (
                f.default is not NOT_PROVIDED or f.db_default is not NOT_PROVIDED or f.primary_key
            )
            assert has_default == (default is not None or is_pk), (
                f"{table}.{col}: 默认值漂移 db={default!r} model_default={f.default!r} "
                f"db_default={f.db_default!r}"
            )


def test_spot_family_semantics() -> None:
    """家族语义锚点抽查：contracts 全 text + 可空落 NULL；jsonb 默认 callable 形。"""
    contract = _model_by_table()["contracts"]
    assert contract._meta.get_field("project_location").null is True
    assert contract._meta.get_field("witness_unit").null is False
    assert contract._meta.get_field("id").primary_key is True
    receipts = _model_by_table()["sample_receipts"]
    assert isinstance(receipts._meta.get_field("ext"), JSONField)
    assert isinstance(receipts._meta.get_field("flow_history"), JSONField)
    assert receipts._meta.get_field("issued_at").null is True
    specialties = _model_by_table()["inspection_specialties"]
    assert specialties._meta.get_field("code").primary_key is True
