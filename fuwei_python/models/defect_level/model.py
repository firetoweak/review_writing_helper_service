from sqlalchemy.orm import relationship

from conf.db import db
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from datetime import datetime

# 全局配置 - 缺陷级别字段显示名称映射
DEFECT_LEVEL_FIELD_DISPLAY_NAMES = {
    'critical_defects': '致命缺陷',
    'major_defects': '严重缺陷',
    'minor_defects': '一般缺陷',
    'suggestion_defects': '提示缺陷'
}


class DefectLevel(db.Model):
    __tablename__ = 'defect_level'

    id = Column(Integer, primary_key=True)
    critical_defects = db.Column(db.Float, default=10.0)  # 致命缺陷 10分
    major_defects = db.Column(db.Float, default=3.0)  # 严重缺陷 3分
    minor_defects = db.Column(db.Float, default=1.0)  # 一般缺陷 1分
    suggestion_defects = db.Column(db.Float, default=0.1)  # 提示缺陷 0.1分
    # 添加user_id外键字段
    user_id = Column(Integer, ForeignKey('user.user_id', ondelete='CASCADE'), nullable=False)

    # 建立关系（可选，便于双向查询）
    user = relationship('User', backref=db.backref('defect_levels', lazy='dynamic', cascade='all, delete-orphan'))

    def to_dict(self):
        return {
            'id': self.id,
            'critical_defects': {
                'value': self.critical_defects,
                'display_name': DEFECT_LEVEL_FIELD_DISPLAY_NAMES['critical_defects']
            },
            'major_defects': {
                'value': self.major_defects,
                'display_name': DEFECT_LEVEL_FIELD_DISPLAY_NAMES['major_defects']
            },
            'minor_defects': {
                'value': self.minor_defects,
                'display_name': DEFECT_LEVEL_FIELD_DISPLAY_NAMES['minor_defects']
            },
            'suggestion_defects': {
                'value': self.suggestion_defects,
                'display_name': DEFECT_LEVEL_FIELD_DISPLAY_NAMES['suggestion_defects']
            },
            'user_id': self.user_id
        }


class ModificationLog(db.Model):
    __tablename__ = 'modification_log'

    id = Column(Integer, primary_key=True)
    defect_level_id = Column(Integer, ForeignKey('defect_level.id', ondelete='CASCADE'), nullable=False)
    modifier = Column(String(50), nullable=False)
    field_name = Column(String(50), nullable=False)
    old_value = Column(db.Float, nullable=False)
    new_value = Column(db.Float, nullable=False)
    modified_time = Column(DateTime, default=datetime.now)

    defect_level = db.relationship('DefectLevel', backref=db.backref('logs', lazy=True))

    def to_dict(self):
        # 获取字段的中文显示名称
        display_name = DEFECT_LEVEL_FIELD_DISPLAY_NAMES.get(self.field_name, self.field_name)

        return {
            'id': self.id,
            'defect_level_id': self.defect_level_id,
            'modifier': self.modifier,
            'field_name': self.field_name,
            'field_display_name': display_name,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'modified_time': self.modified_time.isoformat(),
            # 添加用户信息（如果有关系的话）
            'user_id': self.defect_level.user_id if self.defect_level else None
        }
