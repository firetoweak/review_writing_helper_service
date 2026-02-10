from sqlalchemy.orm import relationship

from conf.db import db
from sqlalchemy import Column, Integer, String, Float, and_, DateTime, Text, Date, Boolean, ForeignKey, UniqueConstraint
from datetime import datetime


class Role(db.Model):
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    # 新增创建人 ID 字段，设置缺省值为 0
    create_user_id = Column(Integer, default=0, nullable=False)
    # 新增创建时间字段，设置缺省值为当前时间
    create_time = Column(DateTime, default=datetime.now(), nullable=False)
    # 关系定义
    users = db.relationship('User', secondary='user_roles', back_populates='roles', overlaps="user_roles")
    user_roles = db.relationship('UserRole', back_populates='role', cascade='all, delete-orphan', overlaps="role")


class UserRole(db.Model):
    __tablename__ = 'user_roles'

    id = Column(db.Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.user_id', ondelete='CASCADE'))
    role_id = Column(Integer, ForeignKey('roles.id', ondelete='CASCADE'))
    created_time = Column(DateTime, default=datetime.now())
    # 关联版本ID
    version_id = Column(Integer, db.ForeignKey('versions.id'), comment='关联版本ID') # 版本管理员、版本查阅人需要配置此字段
    # 关联项目ID
    project_id = Column(Integer, db.ForeignKey('projects.id'), comment='关联项目ID') # 项目管理员、项目查阅人需要配置此字段
    notes = Column(Text)
    # 关系定义
    user = relationship('User', back_populates='user_roles', overlaps="users")
    role = relationship('Role', back_populates='user_roles' , overlaps="users")
    version = relationship('Version', back_populates='user_roles', overlaps="versions")
    project = relationship('Project', back_populates='user_roles' , overlaps="projects")

    @staticmethod
    def get_user_roles(user_id, role_id):
        return UserRole.query.filter(and_(UserRole.user_id == user_id, UserRole.role_id == role_id)).first()