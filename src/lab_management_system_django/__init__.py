"""仓身份包——auth/errors 等跨 app 模块挂这里（saas 同款布局）。

有 __init__.py 使 mypy 文件实参解析出唯一模块名（lab_management_system_django.auth），
避免与命名空间包路径双身份冲突；src/ 本身保持无 __init__.py（config.* 平铺导入面）。
"""
