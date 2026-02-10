# project_document/model.py
from sqlalchemy.orm import relationship

from conf.db import db
from sqlalchemy import Column, Integer, String, Float, and_, DateTime, Text, Date, Boolean, ForeignKey, \
    UniqueConstraint, JSON
from datetime import datetime


class ProjectDocument(db.Model):
    """项目文档表模型"""
    __tablename__ = 'project_documents'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='文档ID，自增主键')
    user_id = db.Column(db.BigInteger, db.ForeignKey('user.user_id'), nullable=False, comment='所属用户ID')
    title = db.Column(db.String(255), nullable=False, comment='文档标题（立项报告标题）')
    idea = db.Column(db.Text, comment='项目构想')
    status = db.Column(db.Enum('draft', 'writing', 'reviewing', 'completed', 'archived'),
                       default='draft', comment='文档状态')
    doc_guide = db.Column(db.Text, comment='全文写作要点指导')
    industry = db.Column(db.String(100), comment='行业名称')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    deleted_at = db.Column(db.DateTime, nullable=True, comment='软删除时间')
    total_review_score = db.Column(db.Float,nullable=True, comment='总评分数，0-10分')
    total_review_content = db.Column(db.Text, comment='总评内容')
    # 关系
    document_nodes = db.relationship('DocumentNode', backref='project_document', lazy='dynamic')
    tasks = db.relationship('Task', backref='project_document', lazy='dynamic')
    document_attachments = db.relationship('DocumentAttachment', backref='project_document', lazy='dynamic')
    improvement_drafts = db.relationship('ImprovementDraft', backref='project_document', lazy='dynamic')


class DocumentNode(db.Model):
    """文档节点表模型"""
    __tablename__ = 'document_nodes'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='节点ID，自增主键')
    document_id = db.Column(db.BigInteger, db.ForeignKey('project_documents.id'), nullable=False, comment='所属文档ID')
    node_id = db.Column(db.String(50), nullable=False, comment='节点标识符，如1, 1.1, 1.2等')
    level = db.Column(db.Integer, nullable=False, comment='节点层级：1=一级章节，2=二级小节')
    title = db.Column(db.String(255), nullable=False, comment='节点标题')
    key_point = db.Column(db.Text, comment='写作要点')
    content = db.Column(db.Text, comment='节点正文内容')
    parent_id = db.Column(db.BigInteger, db.ForeignKey('document_nodes.id'), nullable=True, comment='父节点ID')
    order_num = db.Column(db.Integer, default=0, comment='同一层级下的排序序号')
    review_score = db.Column(db.Float, comment='实际得分，0-10分')
    ideal_score = db.Column(db.Float, comment='应得分数，0-10分')
    business_level = db.Column(db.String(20),  comment='商业价值评级')
    business_describe = db.Column(db.String(255), default="", comment='等级标题内容')
    suggestion = db.Column(db.Text, comment='AI改进建议')
    evaluate = db.Column(db.Text, comment='AI原因分析')
    status = db.Column(db.Enum('pending', 'writing', 'reviewed', 'completed'),
                       default='pending', comment='节点状态')

    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 关系
    parent = db.relationship('DocumentNode', remote_side=[id], backref='children')
    tasks = db.relationship('Task', backref='document_node', lazy='dynamic')
    improvement_drafts = db.relationship('ImprovementDraft', backref='document_node', lazy='dynamic')

    # 唯一约束
    __table_args__ = (
        db.UniqueConstraint('document_id', 'node_id', name='uk_document_node'),
    )
    @property
    def review_detail(self):
        """
        虚拟字段：自动拼接AI改进建议和原因分析
        处理空值情况，避免拼接出 None 或空字符串
        """
        # 初始化空字符串，处理字段为 None 的情况
        suggestion_str = self.suggestion or ""
        evaluate_str = self.evaluate or ""
        return f'{evaluate_str} \n {suggestion_str}'


class Task(db.Model):
    """任务表模型"""
    __tablename__ = 'tasks'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='任务ID，自增主键')
    task_uuid = db.Column(db.String(50), unique=True, nullable=False, comment='任务唯一标识符')
    document_id = db.Column(db.BigInteger, db.ForeignKey('project_documents.id'), nullable=False, comment='所属文档ID')
    node_id = db.Column(db.BigInteger, db.ForeignKey('document_nodes.id'), nullable=True, comment='关联的文档节点ID')
    task_type = db.Column(db.Enum('industry', 'outline', 'heuristic_writing', 'section_review', 'help',
                                  'merge', 'full_review', 'full_polish', 'text_restruct', 'knowledge_index'),
                          nullable=False, comment='任务类型')
    status = db.Column(db.Enum('created', 'processing', 'completed', 'failed', 'cancelled'),
                       default='created', comment='任务状态')
    request_data = db.Column(db.JSON, comment='任务请求数据')
    response_data = db.Column(db.JSON, comment='任务响应数据')
    error_message = db.Column(db.Text, comment='错误信息')
    progress = db.Column(db.Integer, default=0, comment='任务进度百分比，0-100')
    started_at = db.Column(db.DateTime, nullable=True, comment='任务开始时间')
    completed_at = db.Column(db.DateTime, nullable=True, comment='任务完成时间')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 关系
    conversation_messages = db.relationship('ConversationMessage', backref='task', lazy='dynamic')


class ConversationMessage(db.Model):
    """对话消息表模型"""
    __tablename__ = 'conversation_messages'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='消息ID，自增主键')
    task_id = db.Column(db.BigInteger, db.ForeignKey('tasks.id'), nullable=False, comment='所属任务ID')
    session_id = db.Column(db.String(50), nullable=False, comment='会话ID')
    message_id = db.Column(db.String(50), nullable=False, comment='消息唯一标识符，如m_ai_1, m_u_1')
    role = db.Column(db.Enum('user', 'assistant', 'system'), nullable=False, comment='消息角色')
    message_type = db.Column(db.Enum('question', 'answer', 'text', 'suggestion'), comment='消息类型')
    content = db.Column(db.Text, nullable=False, comment='消息内容')
    document_attachments_id = db.Column(db.BigInteger, default=0, comment='附件id，没附件的时候为0')
    message_metadata = db.Column(db.JSON, comment='消息元数据')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')

    # 唯一约束
    __table_args__ = (
        db.UniqueConstraint('task_id', 'session_id', 'message_id', name='uk_task_session_message'),
    )


class KnowledgeBaseDocument(db.Model):
    """知识库文档表模型"""
    __tablename__ = 'knowledge_base_documents'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='文档ID，自增主键')
    user_id = db.Column(db.BigInteger, db.ForeignKey('user.user_id'), nullable=False, comment='所属用户ID')
    project_id = db.Column(db.String(100), nullable=True, comment='项目ID')
    collection_id = db.Column(db.String(100), comment='文档集合ID')
    filename = db.Column(db.String(255), nullable=False, comment='原始文件名')
    file_url = db.Column(db.String(500), nullable=False, comment='文件存储路径')
    mime_type = db.Column(db.String(100), comment='文件MIME类型')
    file_size = db.Column(db.BigInteger, comment='文件大小（字节）')
    status = db.Column(db.Enum('uploading', 'indexing', 'indexed', 'failed', 'deleting', 'deleted'),
                       default='uploading', comment='文档状态')
    error_reason = db.Column(db.Text, comment='失败原因')
    chunk_count = db.Column(db.Integer, default=0, comment='文档分片数量')
    indexed_at = db.Column(db.DateTime, nullable=True, comment='索引完成时间')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    deleted_at = db.Column(db.DateTime, nullable=True, comment='删除时间')


class ImprovementDraft(db.Model):
    """改进草稿本表模型"""
    __tablename__ = 'improvement_drafts'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='草稿ID，自增主键')
    document_id = db.Column(db.BigInteger, db.ForeignKey('project_documents.id'), nullable=False, comment='所属文档ID')
    node_id = db.Column(db.BigInteger, db.ForeignKey('document_nodes.id'), nullable=False, comment='关联的文档节点ID')
    session_id = db.Column(db.String(50), nullable=True, comment='会话ID')
    source_type = db.Column(db.Enum('help_session', 'review_suggestion', 'manual'),nullable=False, comment='来源类型')
    content = db.Column(db.Text, nullable=False, comment='草稿内容')
    help_text = db.Column(db.String(500), comment='对应的"我能帮你"文本')
    is_selected = db.Column(db.Boolean, default=False, comment='是否被用户勾选')
    is_deleted = db.Column(db.Boolean, default=False, comment='是否被删除')
    is_merged = db.Column(db.Boolean, default=False, comment='是否已合入正文')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class DocumentAttachment(db.Model):
    """文档附件表模型"""
    __tablename__ = 'document_attachments'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='附件ID，自增主键')
    document_id = db.Column(db.BigInteger, db.ForeignKey('project_documents.id'), nullable=True, comment='所属文档ID')
    filename = db.Column(db.String(255), nullable=False, comment='文件名')
    file_url = db.Column(db.String(500), nullable=False, comment='文件存储路径')
    mime_type = db.Column(db.String(100), comment='文件MIME类型')
    file_size = db.Column(db.BigInteger, comment='文件大小（字节）')
    is_in_knowledge_base = db.Column(db.Boolean, default=False, comment='是否已存入知识库')
    knowledge_doc_id = db.Column(db.BigInteger, db.ForeignKey('knowledge_base_documents.id'), nullable=True,comment='关联的知识库文档ID')
    content = db.Column(db.Text,nullable=False,default=0,comment='文档内容')
    img_urls = db.Column(db.JSON, nullable=True,comment='对应内容的img标签')
    is_admin = db.Column(db.Integer,nullable=False,default=0,comment='是否管理后台新增')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    # 关系
    knowledge_base_document = db.relationship('KnowledgeBaseDocument', backref='document_attachments')
    @staticmethod
    def add_one(data):
        record = DocumentAttachment(
            document_id = data['document_id'],
            filename=data['filename'],
            file_url=data['file_url'],
            is_admin = data['is_admin'],
            mime_type = data['mime_type'],
            file_size = data['file_size'],
            is_in_knowledge_base = data['is_in_knowledge_base'],
            knowledge_doc_id = data['knowledge_doc_id']
        )
        db.session.add(record)
        db.session.commit()
    @staticmethod
    def delete_admin_file(file_name):
        DocumentAttachment.query.filter(and_(DocumentAttachment.is_admin==1,DocumentAttachment.filename==file_name)).delete()
        db.session.commit()
    @staticmethod
    def get_admin_files():
        return DocumentAttachment.query.filter(DocumentAttachment.is_admin==1).all()
    @staticmethod
    def get_admin_file_by_name(filename):
        return DocumentAttachment.query.filter(DocumentAttachment.filename==filename,DocumentAttachment.is_admin==1).first()

class Prompt(db.Model):
    """提示词表模型"""
    __tablename__ = 'prompts'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='提示词ID，自增主键')
    name = db.Column(db.String(100), unique=True, nullable=False, comment='提示词名称，唯一标识')
    category = db.Column(db.Enum('industry', 'outline', 'heuristic', 'review', 'help', 'merge',
                                 'full_review', 'full_polish', 'restruct', 'float'),
                         nullable=False, comment='提示词类别')
    sub_category = db.Column(db.String(50), nullable=True, comment='子类别')
    content = db.Column(db.Text, nullable=False, comment='提示词内容')
    version = db.Column(db.String(20), default='1.0', comment='提示词版本')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用')
    description = db.Column(db.Text, comment='提示词描述')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class IndustryList(db.Model):
    """行业特点列表"""
    __tablename__ = 'industry_list'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='行业ID')
    name = db.Column(db.String(100), nullable=False, unique=True, comment='行业名称')
    description = db.Column(db.Text, comment='行业描述')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    @staticmethod
    def add_one(data):
        record = IndustryList(name=data['name'],description=data['description'])
        db.session.add(record)
        db.session.commit()


class OutlineRules(db.Model):
    """大纲规则"""
    __tablename__ = 'outline_rules'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='规则ID，自增主键')
    title_num = db.Column(db.String(64), nullable=False, comment='标题前面的数字标签')
    sort = db.Column(db.Integer, nullable=False, default=0, comment='排序')
    content = db.Column(db.Text, comment='规则内容')
    heuristic_writing_prompt = db.Column(db.Text, nullable=True, comment='启发式写作启动的prompt')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    @staticmethod
    def add_one(data):
        record = OutlineRules(title_num=data['title_num'],sort=data['sort'],content=data['content'])
        db.session.add(record)
        db.session.commit()

class ReviewRules(db.Model):
    """评审规则"""
    __tablename__ = 'review_rules'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment='规则ID，自增主键')
    title_num = db.Column(db.String(64), nullable=False, comment='标题前面的数字标签')
    prompt = db.Column(db.Text, nullable=True, comment='评审对应的prompt')
    sort = db.Column(db.Integer, nullable=False, default=0, comment='排序')
    content = db.Column(db.Text, comment='规则内容')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    @staticmethod
    def add_one(data):
        record = ReviewRules(title_num=data['title_num'],sort=data['sort'],content=data['content'])
        db.session.add(record)
        db.session.commit()