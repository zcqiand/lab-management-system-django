"""authn app 配置：认证域（M00.F01/F02 + M01.F04/F05）。

app 名刻意用 authn 而非 auth——避开 django.contrib.auth 的 app label（INSTALLED_APPS
"auth" 会撞 label），views/urls 对外仍挂 /api/auth/**（契约面不变）。
"""

from django.apps import AppConfig


class AuthnConfig(AppConfig):
    name = "authn"
    verbose_name = "Authn (lab family auth domain)"
