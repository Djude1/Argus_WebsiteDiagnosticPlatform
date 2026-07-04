"""密碼強度自訂 validator，補足 Django 內建只查長度的不足。"""

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ComplexityValidator:
    """密碼複雜度：必須同時包含英文字母與數字（可另加符號）。

    Django 內建的 MinimumLengthValidator 只查長度，CommonPasswordValidator 只擋
    廣為人知的弱密碼，缺一個「必須混合字元類型」的規則。此 validator 補上這塊。

    參數可透過 settings.AUTH_PASSWORD_VALIDATORS 的 `OPTIONS` 覆寫。
    """

    def __init__(self, require_letter: bool = True, require_digit: bool = True) -> None:
        self.require_letter = require_letter
        self.require_digit = require_digit

    def validate(self, password: str, user=None) -> None:
        errors = []
        if self.require_letter and not re.search(r"[a-zA-Z]", password):
            errors.append(_("密碼需至少包含一個英文字母。"))
        if self.require_digit and not re.search(r"\d", password):
            errors.append(_("密碼需至少包含一個數字。"))
        if errors:
            raise ValidationError(errors, code="password_complexity")

    def get_help_text(self) -> str:
        parts = []
        if self.require_letter:
            parts.append("英文字母")
        if self.require_digit:
            parts.append("數字")
        return _("密碼需同時包含 %s。") % "、".join(parts)
