from conf.db import db
from sqlalchemy import Column, Integer, String, Enum, and_, DateTime, Text, Date, Boolean, ForeignKey, \
    UniqueConstraint, CheckConstraint, Index, JSON
from datetime import datetime
import enum  # Python 的标准 enum 模块


def get_enum_key_by_value(enum_cls, target_value):
    """针对枚举类（如 enum.Enum），可直接利用 __members__ 属性   根据值获取key"""
    for name, member in enum_cls.__members__.items():
        if member.value == target_value:
            return name
    return None


class DefectSeverity(enum.Enum):
    """缺陷级别"""
    CRITICAL_DEFECTS = '致命'
    MAJOR_DEFECTS = '严重'
    MINOR_DEFECTS = '一般'
    SUGGESTION_DEFECTS = '提示'


class DefectReproducibility(enum.Enum):
    ALWAYS_REPRODUCIBLE = '必然重现'
    CONDITIONALLY_REPRODUCIBLE = '有条件重现'
    RARELY_REPRODUCIBLE = '小概率重现'


class DefectStatus(enum.Enum):
    """缺陷整体状态枚举"""
    DRAFT = 'draft'
    OPEN = 'open'
    RESOLVED = 'resolved'  # 开发人员已经解决所有问题，填写了解决措施。
    CLOSED = 'closed'
    REJECTED = 'rejected'  # 问题提出人确认时不通过。
    TERMINATE_TRACKING = 'terminate_tracking'  # 终止跟踪
    SUSPEND_TRACKING = 'suspend_tracking'  # 挂起

# 定义状态映射字典
STATUS_MAPPING = {
    'DefectStatus.DRAFT': '草稿',
    'DefectStatus.OPEN': '开启',
    'DefectStatus.RESOLVED': '已解决',
    'DefectStatus.CLOSED': '已关闭',
    'DefectStatus.REJECTED': '确认未解决',
    'DefectStatus.TERMINATE_TRACKING': '终止跟踪',
    'DefectStatus.SUSPEND_TRACKING': '挂起'
}

class StageStatus(enum.Enum):
    """阶段状态枚举"""
    DRAFT = '草稿'
    IN_PROGRESS = '进行中'
    PENDING_UPDATE = '待更新'
    COMPLETED = '完成'  # 走到下一个阶段时，本阶段的状态设置为 completed
    REJECTED = '拒绝'  # 下一个阶段驳回时，本阶段设置为 rejected
    CANCELLED = '取消'
    EVALUATING = 'AI评估中'
    NotPASS = '未通过'
    TERMINATE_TRACKING = '终止跟踪'
    SUSPEND_TRACKING = '挂起'


class InvitationStatus(enum.Enum):
    """邀请状态枚举"""
    PENDING = 'pending'  # 待处理
    TRANSFERRED = 'transferred'  # 已转处理
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'  # 驳回原因分析或解决措施
    INVITATION_REJECTED = 'invitation_rejected'  # 驳回定位分析的邀请
    CANCELLED = 'cancelled'  # 弃用
    COMPLETED = 'completed'  # 完成


class DataType(enum.Enum):
    """数据类型枚举，这4类需要进行 AI评估"""
    DEFECT_DESCRIPTION = 'defect_description'
    CAUSE_ANALYSIS = 'cause_analysis'
    SOLUTION = 'developer_solution'
    TEST_RESULT = 'tester_regression'

"""用于显示到界面中"""
data_type_map = {
    DataType.DEFECT_DESCRIPTION: '产品缺陷描述',
    DataType.CAUSE_ANALYSIS: '原因分析',
    DataType.SOLUTION: '解决措施',
    DataType.TEST_RESULT: '回归测试'
}

class EvaluationMethod(enum.Enum):
    """评分方式枚举"""
    AUTO = 'auto'
    MANUAL = 'manual'


class ReminderType(enum.Enum):
    """跟催类型枚举"""
    ANALYSIS = '定位分析'  # 针对原因分析的跟催
    SOLUTION = '解决措施'  # 针对解决措施的跟催


class ReminderStatus(enum.Enum):
    """跟催状态枚举"""
    SENT = 'sent'
    VIEWED = 'viewed'
    ACTED = 'acted'


class ActionType(enum.Enum):
    """操作类型枚举"""
    CREATE = 'create'
    SUBMIT = 'submit'
    UPDATE = 'update'
    APPROVE = 'approve'
    INVITE_TO_ANALYZE = 'invite_to_analyze'  # 邀请分析
    INVITE_CO_ANALYZE = 'invite_co_analyze'  # 邀请共同分析
    REJECT = 'reject'
    CANCEL = 'cancel'  # 弃用单个原因分析
    TRANSFER = 'transfer'
    TERMINATE = 'terminate'  # 终止跟踪
    ASSIGN_DIVISION = 'assign_division'  # 解决措施分工
    SUBMIT_SOLUTION = 'submit_solution'
    REMIND = 'remind'
    VAL_SELF = 'val_self' #自评
    VAL_SUBMIT = 'val_submit' #提交评估
    CLOSE = 'close' #解决后关闭
    SUSPEND = 'suspend' #暂不解决，挂起
    REOPEN   = 'reopen' #挂起后的重新开启


class RejectionType(enum.Enum):
    """驳回类型枚举"""
    STAGE = 'stage'  # 针对阶段的驳回
    INVITATION = 'invitation'  # 邀请的驳回
    ANALYSIS = 'analysis'  # 已分析的驳回
    SOLUTION = 'solution'  # 已填写解决措施的驳回


class CollaboratorRole(enum.Enum):
    """协作者角色枚举"""
    PRIMARY = 'primary'  # 主处理人
    COLLABORATOR = 'collaborator'  # 协作人


class BaseModel(db.Model):
    __abstract__ = True
    __table_args__ = {'mysql_engine': 'InnoDB'}  # MySQL的MyISAM引擎不支持外键，而InnoDB支持


class DefectStageType(BaseModel):
    """缺陷阶段类型模型"""
    __tablename__ = 'defect_stage_types'

    # 阶段唯一标识键
    stage_key = Column(String(50), primary_key=True, comment='阶段唯一标识键')
    # 阶段名称
    stage_name = Column(String(100), nullable=False, comment='阶段名称')
    # 阶段描述
    description = Column(Text, comment='阶段描述')
    # 阶段顺序，用于确定流程中的位置
    stage_order = Column(Integer, default=0, nullable=False, comment='阶段顺序，用于确定流程中的位置')

    def to_dict(self):
        """转换为字典格式"""
        return {
            'stage_key': self.stage_key,
            'stage_name': self.stage_name,
            'description': self.description,
            'stage_order': self.stage_order
        }


class DefectCounter(BaseModel):
    """问题个数计数器表"""
    __tablename__ = 'defect_counters'
    date = db.Column(db.String(8), primary_key=True)  # 存储日期（如20250819）
    count = db.Column(db.Integer, default=0)  # 当日计数器


class Defect(BaseModel):
    """缺陷主表模型"""
    __tablename__ = 'defects'

    # 缺陷ID，主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='缺陷ID，主键')
    # 缺陷单号
    defect_number = Column(String(64), autoincrement=False, comment='缺陷单号，唯一，例如 202508191024')
    # 缺陷标题
    title = Column(String(255), nullable=False, comment='缺陷标题')
    # 缺陷详细描述
    description = Column(Text, comment='缺陷详细描述')
    # 缺陷严重程度
    severity = Column(String(50), Enum(DefectSeverity), nullable=False, default='一般',
                      comment='缺陷严重程度')
    # 缺陷重现概率
    defect_reproducibility = Column(String(50), Enum(DefectReproducibility), nullable=False,
                                    default='小概率复现',
                                    comment='缺陷重现概率')
    # 缺陷创建者ID
    creator_id = Column(Integer, db.ForeignKey('user.user_id'), nullable=False,
                        comment='缺陷创建者ID')
    # 关联版本ID
    version_id = Column(Integer, db.ForeignKey('versions.id'), comment='关联版本ID')
    # 关联项目ID
    project_id = Column(Integer, db.ForeignKey('projects.id'), comment='关联项目ID')
    # 是否为重复缺陷
    is_duplicate = Column(Boolean, default=False, comment='是否为重复缺陷')
    # 重复的源缺陷ID
    duplicate_source_id = Column(Integer, db.ForeignKey('defects.id'), comment='重复的源缺陷ID')
    # 当前所处阶段ID，defect_stages 表的ID
    current_stage_id = Column(Integer, db.ForeignKey('defect_stages.id'), comment='当前所处阶段ID')
    # 缺陷整体状态
    status = Column(String(50), Enum(DefectStatus), default=DefectStatus.DRAFT, comment='缺陷整体状态')
    # 创建时间
    created_time = Column(DateTime, default=datetime.now, comment='创建时间')
    # 最后更新时间
    updated_time = Column(DateTime, default=datetime.now, onupdate=datetime.now,
                          comment='最后更新时间')

    defect_type = Column(String(50), comment='simplified-简化版')

    # 关系定义 - 暂时注释掉，后续通过迁移添加
    creator = db.relationship('User', foreign_keys=[creator_id], backref='created_defects')
    version = db.relationship('Version', backref='defects')
    project = db.relationship('Project', backref='defects')
    duplicate_source = db.relationship('Defect', remote_side=[id], backref='duplicates')
    current_stage = db.relationship('DefectStage', foreign_keys=[current_stage_id],
                                    backref=db.backref('current_defects', uselist=False))

    # 添加索引
    __table_args__ = (
        Index('ix_defects_creator_id', 'creator_id'),
        Index('ix_defects_version_id', 'version_id'),
        Index('ix_defects_project_id', 'project_id'),
        Index('ix_defects_current_stage_id', 'current_stage_id'),
        Index('ix_defects_status', 'status'),
    )

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'severity': self.severity,
            'defect_reproducibility': self.defect_reproducibility,
            'creator_id': self.creator_id,
            'version_id': self.version_id,
            'project_id': self.project_id,
            'is_duplicate': self.is_duplicate,
            'duplicate_source_id': self.duplicate_source_id,
            'current_stage_id': self.current_stage_id,
            'status': self.status.value if self.status else None,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'updated_time': self.updated_time.isoformat() if self.updated_time else None,
            'defect_type': self.defect_type
        }


class DefectStage(BaseModel):
    """缺陷阶段表模型"""
    __tablename__ = 'defect_stages'

    # 阶段记录ID，主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='阶段记录ID，主键')
    # 关联的缺陷ID
    defect_id = Column(Integer, db.ForeignKey('defects.id', ondelete='CASCADE'),
                       nullable=False, comment='关联的缺陷ID')
    # 阶段类型，引用defect_stage_types
    stage_type = Column(String(50), db.ForeignKey('defect_stage_types.stage_key'),
                        nullable=False, comment='阶段类型')
    # 阶段负责人ID
    assigned_to = Column(Integer, db.ForeignKey('user.user_id'), comment='阶段负责人ID')
    # 阶段完成人ID
    completed_by = Column(Integer, db.ForeignKey('user.user_id'), comment='阶段完成人ID')
    # 阶段备注信息
    notes = Column(Text, comment='阶段备注信息（记录 原因分析的弃用，将被弃用的内容记录到这里）')
    # 阶段创建时间
    created_time = Column(DateTime, default=datetime.now, comment='阶段创建时间')
    # 阶段最后更新时间
    updated_time = Column(DateTime, default=datetime.now, onupdate=datetime.now,
                          comment='阶段最后更新时间')
    # 阶段完成时间
    completed_time = Column(DateTime, comment='阶段完成时间')
    # 阶段状态
    status = Column(String(50), Enum(StageStatus), default=StageStatus.IN_PROGRESS, comment='阶段状态')
    # 上一阶段ID，用于驳回时快速定位
    previous_stage_id = Column(Integer, db.ForeignKey('defect_stages.id'),
                               comment='上一阶段ID')
    # 阶段被驳回次数
    rejection_count = Column(Integer, default=0, comment='阶段被驳回次数')

    # 关系定义 - 暂时注释掉，后续通过迁移添加
    defect = db.relationship('Defect', backref=db.backref('stages', cascade='all, delete-orphan'),
                             foreign_keys=[defect_id])  # 明确指定外键
    stage_type_ref = db.relationship('DefectStageType', backref='stages', foreign_keys=[stage_type])  # 明确指定外键
    assignee = db.relationship('User', foreign_keys=[assigned_to], backref='assigned_stages')  # 被分配人员
    completer = db.relationship('User', foreign_keys=[completed_by], backref='completed_stages')  # 完成人
    previous_stage = db.relationship('DefectStage', remote_side=[id], foreign_keys=[previous_stage_id],  # 明确指定外键
                                     backref=db.backref('next_stages', uselist=True))

    # 添加索引
    __table_args__ = (
        Index('ix_defect_stages_defect_id', 'defect_id'),
        Index('ix_defect_stages_stage_type', 'stage_type'),
        Index('ix_defect_stages_assigned_to', 'assigned_to'),
        Index('ix_defect_stages_status', 'status'),
    )

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'defect_id': self.defect_id,
            'stage_type': self.stage_type,
            'assigned_to': self.assigned_to,
            'completed_by': self.completed_by,
            'notes': self.notes,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'updated_time': self.updated_time.isoformat() if self.updated_time else None,
            'completed_time': self.completed_time.isoformat() if self.completed_time else None,
            'status': self.status.value if self.status else None,
            'previous_stage_id': self.previous_stage_id,
            'rejection_count': self.rejection_count
        }


class DefectLocaleInvitation(BaseModel):
    """开发者定位问题邀请表模型"""
    __tablename__ = 'defect_locale_invitations'

    # 邀请ID，主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='邀请ID，主键')
    # 关联的缺陷阶段ID
    defect_stage_id = Column(Integer, db.ForeignKey('defect_stages.id', ondelete='CASCADE'),
                             nullable=False, comment='关联的缺陷阶段ID')
    # 邀请人ID
    inviter_id = Column(Integer, db.ForeignKey('user.user_id'), nullable=False,
                        comment='邀请人ID')
    # 被邀请人ID（系统用户）
    invitee_id = Column(Integer, db.ForeignKey('user.user_id'), comment='被邀请人ID')
    # 邀请原因
    invitation_reason = Column(Text, nullable=False, comment='邀请原因')
    # 邀请状态
    status = Column(String(50), Enum(InvitationStatus), default=InvitationStatus.PENDING,
                    comment='邀请状态')
    # 跟催次数
    reminder_count = Column(Integer, default=0, comment='跟催次数')
    # 最后跟催时间
    last_reminder_time = Column(DateTime, comment='最后跟催时间')
    # 驳回原因
    rejection_reason = Column(Text, comment='驳回原因')
    # 驳回时间
    rejection_time = Column(DateTime, comment='驳回时间')
    # 创建时间
    created_time = Column(DateTime, default=datetime.now, comment='创建时间')
    # 最后更新时间
    updated_time = Column(DateTime, default=datetime.now, onupdate=datetime.now,
                          comment='最后更新时间')

    # 关系定义
    defect_stage = db.relationship('DefectStage', backref=db.backref('invitations',
                                                                     cascade='all, delete-orphan'))
    inviter = db.relationship('User', foreign_keys=[inviter_id], backref='sent_invitations')
    invitee = db.relationship('User', foreign_keys=[invitee_id], backref='received_invitations')

    # 添加索引
    __table_args__ = (
        Index('ix_invitations_defect_stage_id', 'defect_stage_id'),
        Index('ix_invitations_invitee_id', 'invitee_id'),
        Index('ix_invitations_status', 'status'),
    )

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'defect_stage_id': self.defect_stage_id,
            'inviter_id': self.inviter_id,
            'invitee_id': self.invitee_id,
            'invitation_reason': self.invitation_reason,
            'status': self.status.value if self.status else None,
            'reminder_count': self.reminder_count,
            'last_reminder_time': self.last_reminder_time.isoformat() if self.last_reminder_time else None,
            'rejection_reason': self.rejection_reason,
            'rejection_time': self.rejection_time.isoformat() if self.rejection_time else None,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'updated_time': self.updated_time.isoformat() if self.updated_time else None
        }


class DefectSolutionDivision(BaseModel):
    """开发主管审核原因分析后分工表模型——对应于 开发主管审核原因分析 阶段"""
    __tablename__ = 'defect_solution_divisions'

    # 分工记录ID，主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='分工记录ID，主键')
    # 关联的缺陷阶段ID
    defect_stage_id = Column(Integer, db.ForeignKey('defect_stages.id', ondelete='CASCADE'),
                             nullable=False, comment='关联的缺陷阶段ID')
    # 负责模块
    module = Column(String(255), nullable=False, comment='负责模块')
    # 版本信息
    version = Column(String(100), nullable=True, comment='版本信息，非必填')
    # 截止日期
    due_date = Column(Date, nullable=False, comment='截止日期')
    # 分配人ID
    assign_by_id = Column(Integer, db.ForeignKey('user.user_id'), nullable=False,
                          comment='分配人ID-开发主管')
    # 被分配人ID
    assignee_id = Column(Integer, db.ForeignKey('user.user_id'), nullable=False,
                         comment='被分配人ID')
    # 行动计划
    action_plan = Column(Text, nullable=False, comment='行动计划')
    # 创建时间
    created_time = Column(DateTime, default=datetime.now, comment='创建时间')
    # 最后更新时间
    updated_time = Column(DateTime, default=datetime.now, onupdate=datetime.now,
                          comment='最后更新时间')
    # 邀请状态
    status = Column(String(50), Enum(InvitationStatus), default=InvitationStatus.PENDING,
                    comment='邀请状态')
    # 跟催次数
    reminder_count = Column(Integer, default=0, comment='跟催次数')
    # 最后跟催时间
    last_reminder_time = Column(DateTime, comment='最后跟催时间')

    # 关系定义
    defect_stage = db.relationship('DefectStage',
                                   backref=db.backref('solution_divisions', cascade='all, delete-orphan'))

    # 分配人关系
    assigner = db.relationship('User', foreign_keys=[assign_by_id], backref='assigned_solution_divisions')
    assignee = db.relationship('User', foreign_keys=[assignee_id], backref='received_solution_divisions')

    # 添加索引
    __table_args__ = (
        Index('ix_divisions_defect_stage_id', 'defect_stage_id'),
        Index('ix_divisions_assignee_id', 'assignee_id'),
    )

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'defect_stage_id': self.defect_stage_id,
            'module': self.module,
            'version': self.version,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'assign_by_id': self.assign_by_id,
            'assignee_id': self.assignee_id,
            'action_plan': self.action_plan,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'updated_time': self.updated_time.isoformat() if self.updated_time else None,
            'status': self.status.value if self.status else None,
            'reminder_count': self.reminder_count,
            'last_reminder_time': self.last_reminder_time.isoformat() if self.last_reminder_time else None
        }


class DefectStageCollaborator(BaseModel):
    """阶段协作人员表模型， 开发人员定位 及 开发人员编写解决措施 涉及的人员记录到此表——一个人员记录一次"""
    __tablename__ = 'defect_stage_collaborators'

    # 协作记录ID，主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='协作记录ID，主键')
    # 关联的缺陷阶段ID
    defect_stage_id = Column(Integer, db.ForeignKey('defect_stages.id', ondelete='CASCADE'),
                             nullable=False, comment='关联的缺陷阶段ID')
    # 协作者用户ID
    user_id = Column(Integer, db.ForeignKey('user.user_id'), nullable=False,
                     comment='协作者用户ID')
    # 协作者角色
    role = Column(String(50), Enum(CollaboratorRole), default=CollaboratorRole.COLLABORATOR,  # 主处理人、协作人
                  comment='协作者角色')
    # 加入时间
    joined_time = Column(DateTime, default=datetime.now, comment='加入时间')
    # 离开时间
    left_time = Column(DateTime, comment='离开时间')
    # 关联的定位“原因分析”邀请ID
    locale_invitation_id = Column(Integer, db.ForeignKey('defect_locale_invitations.id'),
                                  comment='关联的“原因分析”邀请ID')
    # 关联的“解决措施”分工ID
    solution_division_id = Column(Integer, db.ForeignKey('defect_solution_divisions.id'),
                                  comment='关联的“解决措施”分工ID')

    # 关系定义
    defect_stage = db.relationship('DefectStage', backref=db.backref('collaborators',
                                                                     cascade='all, delete-orphan'))
    user = db.relationship('User', backref='collaborations')
    locale_invitation = db.relationship('DefectLocaleInvitation', backref='collaborator_records')
    solution_division = db.relationship('DefectSolutionDivision', backref='collaborator_records')
    # 修正唯一约束，移除不存在的status字段
    __table_args__ = (
        db.UniqueConstraint('defect_stage_id', 'user_id', name='unique_collaborator'),
        Index('ix_collaborators_defect_stage_id', 'defect_stage_id'),
        Index('ix_collaborators_user_id', 'user_id'),
        Index('ix_collaborators_locale_invitation', 'locale_invitation_id'),
        Index('ix_collaborators_solution_division', 'solution_division_id'),
    )

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'defect_stage_id': self.defect_stage_id,
            'user_id': self.user_id,
            'role': self.role.value if self.role else None,
            'joined_time': self.joined_time.isoformat() if self.joined_time else None,
            'left_time': self.left_time.isoformat() if self.left_time else None,
            'locale_invitation_id': self.locale_invitation_id,
            'solution_division_id': self.solution_division_id
        }


class DefectStageData(BaseModel):
    """阶段特定数据表模型， 4个特殊阶段，需要进行AI评估"""
    __tablename__ = 'defect_stage_data'

    # 阶段数据ID，主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='阶段数据ID，主键')
    # 关联的缺陷阶段ID
    defect_stage_id = Column(Integer, db.ForeignKey('defect_stages.id', ondelete='CASCADE'),
                             nullable=False, comment='关联的缺陷阶段ID')
    # 数据类型
    data_type = Column(String(50), Enum(DataType), nullable=False,
                       comment='数据类型，对应问题描述、原因分析、解决措施及验证4个特殊阶段')
    # 关联的 定位问题邀请ID（如果是原因分析）
    locale_invitation_id = Column(Integer, db.ForeignKey('defect_locale_invitations.id'),
                                  comment='关联的邀请ID')
    # 关联的分工ID（如果是解决措施）
    solution_division_id = Column(Integer, db.ForeignKey('defect_solution_divisions.id'),
                                  comment='关联的分工ID')
    # 数据内容（JSON格式）
    content = Column(JSON, nullable=False, comment='数据内容')
    # 是否为草稿
    is_draft = Column(Boolean, default=False, comment='是否草稿——仅本人可见')
    # 提交人ID
    submitted_by = Column(Integer, db.ForeignKey('user.user_id'), nullable=False,
                          comment='提交人ID')
    # 是否为合并后的数据
    is_combined = Column(Boolean, default=False, comment='是否为合并后的数据')
    # 是否为当前最新数据
    is_current = Column(Boolean, default=True, comment='是否为当前最新数据')
    # AI评分方式：自动或手动
    evaluation_method = Column(String(50), Enum(EvaluationMethod), default=EvaluationMethod.AUTO,
                               comment='评分方式')
    # AI评估建议
    ai_suggestion = Column(Text, comment='AI评估建议')
    # AI评估分数
    ai_score = Column(Integer, comment='AI评估分数')
    # AI评估时间
    ai_evaluation_time = Column(DateTime, comment='AI评估时间')
    # 创建时间
    created_time = Column(DateTime, default=datetime.now, comment='创建时间')
    # 最后更新时间
    updated_time = Column(DateTime, default=datetime.now, onupdate=datetime.now,
                          comment='最后更新时间')

    # 关系定义
    defect_stage = db.relationship('DefectStage', backref=db.backref('stage_data',
                                                                     cascade='all, delete-orphan'))
    invitation = db.relationship('DefectLocaleInvitation', backref='stage_data')
    division = db.relationship('DefectSolutionDivision', backref='stage_data')
    submitter = db.relationship('User', backref='submitted_data')

    # 唯一约束
    __table_args__ = (
        # db.UniqueConstraint('defect_stage_id', 'data_type', 'is_current',
        #                     name='uk_stage_data_type'),
        Index('ix_stage_data_defect_stage_id', 'defect_stage_id'),
        Index('ix_stage_data_data_type', 'data_type'),
        Index('ix_stage_data_submitted_by', 'submitted_by'),
    )

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'defect_stage_id': self.defect_stage_id,
            'data_type': self.data_type if self.data_type else None,
            'locale_invitation_id': self.locale_invitation_id,
            'solution_division_id': self.solution_division_id,
            'content': self.content,
            'is_draft': self.is_draft,
            'submitted_by': self.submitted_by,
            'is_combined': self.is_combined,
            'is_current': self.is_current,
            'evaluation_method': self.evaluation_method if self.evaluation_method else None,
            'ai_suggestion': self.ai_suggestion,
            'ai_score': self.ai_score,
            'ai_evaluation_time': self.ai_evaluation_time.isoformat() if self.ai_evaluation_time else None,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'updated_time': self.updated_time.isoformat() if self.updated_time else None
        }


class DefectStageCombineRecord(BaseModel):
    """合并记录表模型， 对于多人共同分析及共同解决的问题需要合并后再进行AI评估"""
    __tablename__ = 'defect_stage_combine_records'

    # 合并记录ID，主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='合并记录ID，主键')
    # 关联的缺陷ID
    defect_id = Column(Integer, db.ForeignKey('defects.id', ondelete='CASCADE'),
                       nullable=False, comment='关联的缺陷ID')
    # 关联的缺陷阶段ID
    defect_stage_id = Column(Integer, db.ForeignKey('defect_stages.id', ondelete='CASCADE'),
                             nullable=False, comment='关联的缺陷阶段ID')
    # 源数据ID集合
    source_data_ids = Column(JSON, nullable=False, comment='源数据ID集合')
    # AI评分方式：自动或手动
    evaluation_method = Column(String(50), Enum(EvaluationMethod), default=EvaluationMethod.AUTO,
                               comment='评分方式')
    # AI评估建议
    ai_suggestion = Column(Text, comment='AI评估建议')
    # AI评估分数
    ai_score = Column(Integer, comment='AI评估分数')
    # 合并时间
    combine_time = Column(DateTime, default=datetime.now, comment='合并时间')

    # 关系定义
    defect = db.relationship('Defect', backref=db.backref('combine_records',
                                                          cascade='all, delete-orphan'))
    defect_stage = db.relationship('DefectStage', backref=db.backref('combine_records',
                                                                     cascade='all, delete-orphan'))

    # 添加索引
    __table_args__ = (
        Index('ix_combine_records_defect_id', 'defect_id'),
        Index('ix_combine_records_defect_stage_id', 'defect_stage_id'),
    )

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'defect_id': self.defect_id,
            'defect_stage_id': self.defect_stage_id,
            'source_data_ids': self.source_data_ids,
            'evaluation_method': self.evaluation_method.value if self.evaluation_method else None,
            'ai_suggestion': self.ai_suggestion,
            'ai_score': self.ai_score,
            'combine_time': self.combine_time.isoformat() if self.combine_time else None
        }


class DefectReminder(BaseModel):
    """跟催记录表模型"""
    __tablename__ = 'defect_reminders'

    # 跟催记录ID，主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='跟催记录ID，主键')
    # 关联的缺陷ID
    defect_id = Column(Integer, db.ForeignKey('defects.id', ondelete='CASCADE'),
                       nullable=False, comment='关联的缺陷ID')
    # 关联的缺陷阶段ID
    defect_stage_id = Column(Integer, db.ForeignKey('defect_stages.id', ondelete='CASCADE'),
                             nullable=False, comment='关联的缺陷阶段ID')
    # 跟催类型：原因分析跟催或解决措施跟催
    reminder_type = Column(String(50), Enum(ReminderType), nullable=False, comment='跟催类型')
    # 跟催目标ID（邀请ID或分工ID）
    target_id = Column(Integer, nullable=False, comment='跟催目标ID')
    # 跟催人ID
    reminder_by = Column(Integer, db.ForeignKey('user.user_id'), nullable=False,
                         comment='跟催人ID')
    # 跟催时间
    reminder_time = Column(DateTime, default=datetime.now, comment='跟催时间')
    # 跟催内容
    reminder_message = Column(Text, comment='跟催内容')
    # 跟催状态：已发送、已查看、已处理
    reminder_status = Column(String(50), Enum(ReminderStatus), default=ReminderStatus.SENT,
                             comment='跟催状态')
    # 处理时间
    action_time = Column(DateTime, comment='处理时间')
    # 处理备注
    action_notes = Column(Text, comment='处理备注')
    # 创建时间
    created_time = Column(DateTime, default=datetime.now, comment='创建时间')
    # 最后更新时间
    updated_time = Column(DateTime, default=datetime.now, onupdate=datetime.now,
                          comment='最后更新时间')

    # 关系定义
    defect = db.relationship('Defect', backref=db.backref('reminders', cascade='all, delete-orphan'))
    defect_stage = db.relationship('DefectStage', backref=db.backref('reminders',
                                                                     cascade='all, delete-orphan'))
    reminder_user = db.relationship('User', backref='sent_reminders')

    # 添加索引
    __table_args__ = (
        Index('ix_reminders_defect_id', 'defect_id'),
        Index('ix_reminders_defect_stage_id', 'defect_stage_id'),
        Index('ix_reminders_reminder_by', 'reminder_by'),
        Index('ix_reminders_reminder_type', 'reminder_type'),
    )

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'defect_id': self.defect_id,
            'defect_stage_id': self.defect_stage_id,
            'reminder_type': self.reminder_type.value if self.reminder_type else None,
            'target_id': self.target_id,
            'reminder_by': self.reminder_by,
            'reminder_time': self.reminder_time.isoformat() if self.reminder_time else None,
            'reminder_message': self.reminder_message,
            'reminder_status': self.reminder_status.value if self.reminder_status else None,
            'action_time': self.action_time.isoformat() if self.action_time else None,
            'action_notes': self.action_notes,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'updated_time': self.updated_time.isoformat() if self.updated_time else None
        }


class DefectFlowHistory(BaseModel):
    """流程历史记录表模型"""
    __tablename__ = 'defect_flow_history'

    # 历史记录ID，主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='历史记录ID，主键')
    # 关联的缺陷ID
    defect_id = Column(Integer, db.ForeignKey('defects.id', ondelete='CASCADE'),
                       nullable=False, comment='关联的缺陷ID')
    # 源阶段ID
    from_stage_id = Column(Integer, db.ForeignKey('defect_stages.id'), comment='源阶段ID')
    # 目标阶段ID
    to_stage_id = Column(Integer, db.ForeignKey('defect_stages.id'), nullable=False,
                         comment='目标阶段ID')
    # 操作类型
    action_type = Column(String(50), Enum(ActionType), nullable=False, comment='操作类型')
    # 关联的跟催记录ID
    reminder_id = Column(Integer, db.ForeignKey('defect_reminders.id'), comment='关联的跟催记录ID')
    # 关联的AI建议评分ID
    ai_sug_score_id = Column(String(128), db.ForeignKey('ai_sug_score.id'), comment='关联的AI建议评分ID')
    # 操作人ID
    action_by = Column(Integer, db.ForeignKey('user.user_id'), nullable=False, comment='操作人ID')
    # 操作时间
    action_time = Column(DateTime, default=datetime.now, comment='操作时间')
    # 操作备注
    notes = Column(Text, comment='操作备注')

    # 关系定义
    defect = db.relationship('Defect', backref=db.backref('flow_history', cascade='all, delete-orphan'))
    from_stage = db.relationship('DefectStage', foreign_keys=[from_stage_id],
                                 backref='flow_history_from')
    to_stage = db.relationship('DefectStage', foreign_keys=[to_stage_id], backref='flow_history_to')
    reminder = db.relationship('DefectReminder', backref='flow_history')
    ai_sug_score = db.relationship('AiSugScore', backref='flow_history')
    action_user = db.relationship('User', backref='actions')

    # 添加索引
    __table_args__ = (
        Index('ix_flow_history_defect_id', 'defect_id'),
        Index('ix_flow_history_action_by', 'action_by'),
        Index('ix_flow_history_action_time', 'action_time'),
        Index('ix_flow_history_ai_sug_score_id', 'ai_sug_score_id'),
    )

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'defect_id': self.defect_id,
            'from_stage_id': self.from_stage_id,
            'to_stage_id': self.to_stage_id,
            'action_type': self.action_type.value if self.action_type else None,
            'reminder_id': self.reminder_id,
            'ai_sug_score_id': self.ai_sug_score_id,
            'action_by': self.action_by,
            'action_time': self.action_time.isoformat() if self.action_time else None,
            'notes': self.notes
        }


class DefectRejection(BaseModel):
    """统一的驳回记录表模型"""
    __tablename__ = 'defect_rejections'

    # 驳回记录ID，主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='驳回记录ID，主键')
    # 关联的缺陷ID
    defect_id = Column(Integer, db.ForeignKey('defects.id', ondelete='CASCADE'),
                       nullable=False, comment='关联的缺陷ID')
    # 关联的缺陷阶段ID
    defect_stage_id = Column(Integer, db.ForeignKey('defect_stages.id', ondelete='CASCADE'),
                             nullable=False, comment='关联的缺陷阶段ID')
    # 驳回类型：阶段驳回或邀请驳回
    rejection_type = Column(String(50), Enum(RejectionType), nullable=False, comment='驳回类型')
    # 如果是邀请驳回，记录邀请ID
    invitation_id = Column(Integer, db.ForeignKey('defect_locale_invitations.id'),
                           comment='关联的邀请ID')
    # 如果是原因分析驳回和解决措施驳回，记录阶段数据ID
    stage_data_id = Column(Integer, db.ForeignKey('defect_stage_data.id'),
                           comment='阶段数据ID')
    # 驳回人ID
    rejected_by = Column(Integer, db.ForeignKey('user.user_id'), nullable=False,
                         comment='驳回人ID')
    # 驳回原因
    reason = Column(Text, nullable=False, comment='驳回原因')
    # 驳回后返回的阶段ID
    previous_stage_id = Column(Integer, db.ForeignKey('defect_stages.id'),
                               comment='驳回后返回的阶段ID')
    # 驳回时间
    created_time = Column(DateTime, default=datetime.now, comment='驳回时间')

    # 关系定义
    defect = db.relationship('Defect', backref=db.backref('rejections', cascade='all, delete-orphan'))
    defect_stage = db.relationship('DefectStage', foreign_keys=[defect_stage_id],
                                   backref='rejections')
    invitation = db.relationship('DefectLocaleInvitation', backref='rejections')
    stage_data = db.relationship('DefectStageData', backref='rejections')
    rejecter = db.relationship('User', backref='rejections')
    previous_stage = db.relationship('DefectStage', foreign_keys=[previous_stage_id],
                                     backref='rejection_returns')

    # 添加索引
    __table_args__ = (
        Index('ix_rejections_defect_id', 'defect_id'),
        Index('ix_rejections_defect_stage_id', 'defect_stage_id'),
        Index('ix_rejections_rejected_by', 'rejected_by'),
    )

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'defect_id': self.defect_id,
            'defect_stage_id': self.defect_stage_id,
            'rejection_type': self.rejection_type.value if self.rejection_type else None,
            'invitation_id': self.invitation_id,
            'stage_data_id': self.stage_data_id,
            'rejected_by': self.rejected_by,
            'reason': self.reason,
            'previous_stage_id': self.previous_stage_id,
            'created_time': self.created_time.isoformat() if self.created_time else None
        }
