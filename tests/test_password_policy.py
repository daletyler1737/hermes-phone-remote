# -*- coding: utf-8 -*-
"""密码策略自检：python tests/test_password_policy.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "dashboard"))
from plugin_api import MIN_PASSWORD_LEN, password_problem


def demo():
    assert MIN_PASSWORD_LEN >= 12, MIN_PASSWORD_LEN
    assert password_problem("Abcdefgh1!23") is None            # 12 位、四类齐 -> 过
    assert password_problem("Abcdefgh1!2") == "密码至少 12 位"
    assert "小写" in password_problem("ABCDEFGH1!23")
    assert "大写" in password_problem("abcdefgh1!23")
    assert "数字" in password_problem("Abcdefghij!k")
    assert "符号" in password_problem("Abcdefgh1234")
    assert "小写字母、符号" in password_problem("ABCDEFGH1234")      # 多处缺失一起报
    print("password policy ok: %d 位 + 大小写数字符号" % MIN_PASSWORD_LEN)


if __name__ == "__main__":
    demo()
