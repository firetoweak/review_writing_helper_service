from mammoth.documents import comment
from sqlalchemy.orm import relationship
from conf.db import db
from sqlalchemy import Column, Integer, Boolean, String, Float, DateTime, ForeignKey, JSON
from datetime import datetime


class TemplateType(db.Model):
    """模板类型表，存储不同类型的模板定义"""
    __tablename__ = 'template_type'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='模板类型ID，主键自增长')
    name = Column(String(50), nullable=False, comment='模板类型名称（如"缺陷描述"、"回归测试"）')
    description = Column(db.Text, comment='模板类型详细描述')
    created_time = Column(DateTime, default=datetime.now(), comment='记录创建时间')
    updated_time = Column(DateTime, default=datetime.now(), onupdate=datetime.now(), comment='记录最后更新时间')

    # 关系，templates表示当前模型通过外键关联到Template模型的多个实例，
    # backref='type'会在Template模型中自动创建名为type的属性，用于从子对象反向访问父对象（如template.type）
    templates = relationship('Template', backref='type', lazy=True)

    def __repr__(self):
        return f'<TemplateType {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'updated_time': self.updated_time.isoformat() if self.updated_time else None
        }


class Template(db.Model):
    """模板表，存储各个用户定制的模板信息"""
    __tablename__ = 'template'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='模板ID，主键自增长')
    user_id = Column(Integer, db.ForeignKey('user.user_id'), nullable=False,
                        comment='关联的用户ID，外键关联user表')
    type_id = Column(Integer, db.ForeignKey('template_type.id'), nullable=False,
                        comment='模板类型ID，外键关联template_type表')
    name = Column(String(100), nullable=False, comment='模板名称')
    is_active = Column(Boolean, default=True, comment='模板启用状态：1-启用，0-禁用')
    created_by = Column(Integer, nullable=False, comment='创建者用户ID，关联用户表')
    updated_by = Column(Integer, comment='最后更新者用户ID，关联用户表')
    created_time = Column(DateTime, default=datetime.now(), comment='记录创建时间')
    updated_time = Column(DateTime, default=datetime.now(), onupdate=datetime.now(), comment='记录最后更新时间')

    # 关系
    items = relationship('TemplateItem', backref='template', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Template {self.name}>'

    def to_dict(self, include_items=True):
        result = {
            'id': self.id,
            'user_id': self.user_id,
            'type_id': self.type_id,
            'name': self.name,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'updated_by': self.updated_by,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'updated_time': self.updated_time.isoformat() if self.updated_time else None
        }

        # 可选包含模板项
        if include_items and self.items:
            result['items'] = [item.to_dict() for item in self.items]

        return result


class TemplateItem(db.Model):
    """模板项表，存储模板中的各个项目信息"""
    __tablename__ = 'template_item'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='模板项ID，主键自增长')
    template_id = Column(Integer, db.ForeignKey('template.id'), nullable=False,
                            comment='所属模板ID，外键关联template表')
    content = Column(db.JSON, comment='标题：描述')
    sort_order = Column(Integer, default=0, comment='排序顺序，数值越小越靠前')
    is_removable = Column(Boolean, default=False, comment='是否可移除：1-可移除，0-不可移除')
    is_required = Column(Boolean, default=False, comment='是否必填：1-必填，0-可选')
    created_time = Column(DateTime, default=datetime.now(), comment='记录创建时间')
    updated_time = Column(DateTime, default=datetime.now(), onupdate=datetime.now(), comment='记录最后更新时间')

    def __repr__(self):
        return f'<TemplateItem {self.id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'template_id': self.template_id,
            'content': self.content,
            'sort_order': self.sort_order,
            'is_removable': self.is_removable,
            'is_required': self.is_required,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'updated_time': self.updated_time.isoformat() if self.updated_time else None
        }