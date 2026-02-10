from conf.db import db
from sqlalchemy import Column, Integer, String, Float, and_, DateTime, Text, Date, Boolean, ForeignKey, UniqueConstraint
from datetime import datetime

class TechGroup(db.Model):
    """技术族模型"""
    __tablename__ = 'tech_groups'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey('user.user_id'), nullable=True)
    created_time = Column(DateTime, default=datetime.now)
    updated_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系定义
    platforms = db.relationship('Platform', backref='tech_group', cascade='all, delete-orphan', lazy='dynamic')
    # 添加与User模型的关系
    user = db.relationship('User', backref='tech_groups')

    def __repr__(self):
        return f'<TechGroup {self.name}>'

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'user_id': self.user_id,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'updated_time': self.updated_time.isoformat() if self.updated_time else None,
            'platform_count': self.platforms.count()
        }


class Platform(db.Model):
    """平台模型"""
    __tablename__ = 'platforms'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tech_group_id = Column(Integer, ForeignKey('tech_groups.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default='ACTIVE')
    created_time = Column(DateTime, default=datetime.now())

    # 关系定义
    projects = db.relationship('Project', backref='platform', cascade='all, delete-orphan', lazy='dynamic')

    # 同一技术族下平台名称唯一
    __table_args__ = (
        UniqueConstraint('tech_group_id', 'name', name='unique_tech_group_platform'),
    )

    def __repr__(self):
        return f'<Platform {self.name} ({self.type})>'

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'tech_group_id': self.tech_group_id,
            'name': self.name,
            'type': self.type,
            'description': self.description,
            'status': self.status,
            'created_time': self.created_time.isoformat(),
            'project_count': self.projects.count()
        }
class Project(db.Model):
    """项目模型"""
    __tablename__ = 'projects'

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(Integer, ForeignKey('platforms.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    repo_url = Column(String(255), nullable=True)
    current_version = Column(String(20), nullable=True)
    status = Column(String(20), default='PLANNING')
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    created_time = Column(DateTime, default=datetime.now())
    # 关系定义
    user_roles = db.relationship('UserRole', back_populates='project', cascade='all, delete-orphan')


    # 同一平台下项目名称唯一
    __table_args__ = (
        UniqueConstraint('platform_id', 'name', name='unique_platform_project'),
    )

    def __repr__(self):
        return f'<Project {self.code} - {self.name}>'

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'platform_id': self.platform_id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'repo_url': self.repo_url,
            'current_version': self.current_version,
            'status': self.status,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'created_time': self.created_time.isoformat()
        }