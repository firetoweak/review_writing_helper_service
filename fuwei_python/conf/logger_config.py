import os
import logging
import inspect
from logging.handlers import RotatingFileHandler
from flask import Flask
from typing import Dict
# ===================== 日志配置常量 =====================
MODULE_LOG_MAP: Dict[str, str] = {
    "model": "model.log",
    "admin_view":"admin_view.log"
}
COMMON_LOG_FORMAT = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s.%(funcName)s - %(message)s - %(filename)s:%(lineno)d",
    datefmt="%Y-%m-%d %H:%M:%S"
)
MODULE_LOG_FORMAT= logging.Formatter(
    "%(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
# ===================== 日志初始化函数 =====================
def setup_module_logger(app: Flask):
    # 1. 全局根日志器重置
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()

    # 2. 创建日志目录
    log_dir = os.path.join('./', "logs")
    os.makedirs(log_dir, exist_ok=True)
    print(f"[日志配置] 日志目录：{log_dir}")

    app.logger.handlers.clear()
    app.logger.propagate = False
    app.logger.setLevel(logging.DEBUG)  # 确保app.logger接收所有级别

    # ===================== 通用日志处理器（终端+文件） =====================
    # 控制台处理器（输出所有通用日志）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(COMMON_LOG_FORMAT)
    console_handler.setLevel(logging.DEBUG)

    # ===================== 模块日志处理器（专属文件） =====================
    module_handlers = {}
    for module_name, log_file in MODULE_LOG_MAP.items():
        module_handler = RotatingFileHandler(
            os.path.join(log_dir, log_file),
            maxBytes=500 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8"
        )
        module_handler.setFormatter(MODULE_LOG_FORMAT)
        module_handler.setLevel(logging.INFO)

        # 模块过滤器：只处理对应biz_module的日志
        def module_filter(record, target_module=module_name):
            return getattr(record, "biz_module", "") == target_module

        module_handler.addFilter(module_filter)
        module_handlers[module_name] = module_handler

    # ===================== 绑定所有处理器到app.logger =====================
    # 通用处理器（终端+文件）
    app.logger.addHandler(console_handler)
    # 模块处理器
    for handler in module_handlers.values():
        app.logger.addHandler(handler)

    def log_with_module(level, message, biz_module):
        if biz_module not in MODULE_LOG_MAP:
            raise ValueError(f"无效模块：{biz_module}，可选：{list(MODULE_LOG_MAP.keys())}")

        # 获取真实调用者的栈帧信息
        try:
            stack = inspect.stack()
            caller_frame = stack[2] if len(stack) >= 3 else stack[0]
            fn = os.path.basename(caller_frame.filename)
            lno = caller_frame.lineno
            funcName = caller_frame.function
            record = app.logger.makeRecord(
                name=app.logger.name,
                level=level,
                fn=fn,
                lno=lno,
                msg=message,
                args=(),
                exc_info=None,
                extra={"biz_module": biz_module},
                func=funcName
            )
            app.logger.handle(record)
        except Exception as e:
            print(f"{e}")
        finally:
            del stack  # 释放栈引用
    app.logger.info_module = lambda msg, module: log_with_module(logging.INFO, msg, module)
    app.logger.error_module = lambda msg, module: log_with_module(logging.ERROR, msg, module)
    app.logger.warning_module = lambda msg, module: log_with_module(logging.WARNING, msg, module)
logging.getLogger('werkzeug').setLevel(logging.WARNING)