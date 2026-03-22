#!/usr/bin/env python
"""Django 命令列管理工具"""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            '無法匯入 Django，請確認已安裝且虛擬環境已啟用。'
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
