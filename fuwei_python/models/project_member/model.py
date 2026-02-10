from conf.db import db
from sqlalchemy import Column, Integer, String, Float, and_, DateTime, Text, Date, Boolean, ForeignKey, \
    UniqueConstraint, CheckConstraint, Enum
from datetime import datetime
import enum

# 删除 RoleType 枚举定义，保留角色字典
role_dict = {
    'company_admin': '公司管理员',
    'global_admin': '全板块管理员',
    'global_viewer': '全板块查阅人',
    'project_admin': '项目管理员',
    'project_viewer': '项目查阅人',
    'dev_manager': '开发主管',
    'test_manager': '测试经理',
    'developer': '开发人员',
    'tester': '测试人员',
    'process_user': '流程使用者'
}


class ProjectMember(db.Model):
    __tablename__ = 'project_members'

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, db.ForeignKey('projects.id', ondelete='CASCADE'))
    version_id = Column(Integer, db.ForeignKey('versions.id', ondelete='CASCADE'))
    user_id = Column(Integer, db.ForeignKey('user.user_id', ondelete='CASCADE'), nullable=False)
    role_type = Column(String(50), nullable=False)
    created_time = Column(db.DateTime, default=datetime.now())

    # 唯一性约束（复合键）
    __table_args__ = (
        UniqueConstraint('project_id', 'version_id', 'user_id', 'role_type', name='uq_project_version_user'),
        CheckConstraint('project_id IS NOT NULL OR version_id IS NOT NULL', name='chk_at_least_one_entity')
    )

    # 关系定义（假设存在对应的 Project、Version、User 模型）
    project = db.relationship('Project', backref=db.backref('members', passive_deletes=True))
    version = db.relationship('Version', backref=db.backref('members', passive_deletes=True))
    user = db.relationship('User', backref=db.backref('project_roles', passive_deletes=True))

    def to_dict(self, include_relations=False):
        """将模型实例转换为字典

        Args:
            include_relations (bool): 是否包含关联对象信息

        Returns:
            dict: 包含模型字段值的字典
        """
        data = {
            'id': self.id,
            'project_id': self.project_id,
            'version_id': self.version_id,
            'user_id': self.user_id,
            'role_type': self.role_type if self.role_type else None,
            'created_time': self.created_time.isoformat() if self.created_time else None
        }

        if include_relations:
            # 添加关联对象信息（如果存在）
            if self.project:
                data['project'] = self.project.to_dict() if hasattr(self.project, 'to_dict') else {
                    'id': self.project.id}
            if self.version:
                data['version'] = self.version.to_dict() if hasattr(self.version, 'to_dict') else {
                    'id': self.version.id}
            if self.user:
                data['user'] = self.user.to_dict() if hasattr(self.user, 'to_dict') else {'user_id': self.user.user_id}

        return data