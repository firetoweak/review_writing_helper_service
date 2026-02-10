# filters.py - 定义所有自定义过滤器

from flask import current_app

def status_class_filter(severity):
    """根据缺陷级别返回对应的CSS类"""
    if severity == '致命':
        return 'status-urgent'
    elif severity == '严重':
        return 'status-serious'
    elif severity == '一般':
        return 'status-normal'
    elif severity == '提示':
        return 'status-minor'
    else:
        return 'status-default'

def register_filters(app):
    """注册所有过滤器到Flask应用"""
    app.jinja_env.filters['status_class'] = status_class_filter
    # 可以继续注册其他过滤器

