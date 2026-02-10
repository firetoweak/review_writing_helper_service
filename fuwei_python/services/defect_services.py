import json
from collections import defaultdict
from datetime import datetime
from typing import List, Optional, Dict, Any

from flask import current_app, g, jsonify, request, session, flash, url_for
from pyexpat.errors import messages
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError, DataError, DatabaseError
from sqlalchemy import and_, or_, case, func, extract, text,exists, select

from conf.config import app_config
from conf.db import db
from constants.message_types import MESSAGE_TEMPLATES, MessageTypes
from models.defect.model import (
    Defect, DefectStatus, DefectStage, StageStatus, DefectLocaleInvitation,
    InvitationStatus, DefectSolutionDivision, DefectStageCollaborator,
    CollaboratorRole, DefectStageData, DataType, EvaluationMethod,
    DefectStageCombineRecord, DefectReminder, ReminderType, ReminderStatus,
    DefectFlowHistory, ActionType, DefectRejection, RejectionType,
    DefectStageType, DefectCounter, DefectSeverity, data_type_map, STATUS_MAPPING, DefectReproducibility
)
from models.defect_level.model import DefectLevel
from models.defect_message.model import DefectMessage
from models.product_line.model import Version, ProductLine, Product
from models.tech_group.model import Project, Platform, TechGroup
from models.users.models import User
from services.defect_email_service import DefectEmailService
from services.defect_message_service import DefectMessageService, MessageCreator
from services.inner_service import InnerSrvice, ErrorCode
from services.product_line_services import ProductLineService
from services.project_member_services import ProjectMemberService
from services.role_services import UserRoleService
from services.tech_group_service import ProjectService, TechGroupService
from flask_paginate import get_page_args, Pagination
from common.global_template_functions import get_all_checked_version_project


# 在模块顶部定义全局常量
OPEN_STATUS_VALUES = ['DefectStatus.OPEN', 'OPEN', 'open']  # 未关闭
CLOSED_STATUS_VALUES = ['DefectStatus.CLOSED', 'CLOSED', 'closed']  # 已关闭
ALL_STATUS_VALUES = OPEN_STATUS_VALUES + CLOSED_STATUS_VALUES  # 全部 （不统计 草稿、终止跟踪 的缺陷单）


class DefectService:
    """缺陷服务类，处理缺陷相关业务逻辑"""

    @staticmethod
    def defect_list(page, per_page, filters=None, user_id=0, admin_user_id=0):

        query = Defect.query.join(Defect.current_stage).join(DefectStage.assignee)
        processed_num = 0
        pending_num = 0
        pending_query = None
        processed_query = None

        # 确保 filters 存在
        if filters is None:
            filters = {}

        # 获取 deal_status，默认为 pending
        filters['deal_status'] = request.values.get('deal_status', 'pending')

        # 首先构建基础查询
        base_query = Defect.query.join(Defect.current_stage).join(DefectStage.assignee)

        if session['role_select'] == "流程使用者":
            # 构建 pending_query - 当前待处理的缺陷
            pending_query = base_query.filter(
                or_(
                    and_(Defect.status == 'DefectStatus.DRAFT', Defect.creator_id == user_id),
                    and_(
                        Defect.status != 'DefectStatus.DRAFT',
                        Defect.status != 'DefectStatus.CLOSED',
                        Defect.status != 'DefectStatus.TERMINATE_TRACKING'
                    )
                )
            ).outerjoin(DefectStage.invitations).outerjoin(
                DefectStage.solution_divisions
            ).filter(
                or_(
                    DefectLocaleInvitation.invitee_id == session['user_id'],
                    DefectSolutionDivision.assignee_id == session['user_id'],
                    DefectStage.assigned_to == session['user_id']
                )
            )

            user_current_stage_defects = Defect.query.join(Defect.current_stage).filter(and_(DefectStage.assigned_to == session['user_id'],Defect.status.in_(['DefectStatus.OPEN','DefectStatus.DRAFT']))).all()
            user_current_stage_defects_ids = [defect.id for defect in user_current_stage_defects]
            # 构建 processed_query - 曾经处理过的缺陷
            user_defect_stages = DefectStage.query.outerjoin(DefectStage.invitations).outerjoin(
                DefectStage.solution_divisions
            ).filter(and_(
                or_(
                    DefectLocaleInvitation.invitee_id == session['user_id'],
                    DefectSolutionDivision.assignee_id == session['user_id'],
                    DefectStage.assigned_to == session['user_id'],
                ))
            ).all()

            defect_ids = [defect_stage.defect_id for defect_stage in user_defect_stages if defect_stage.defect_id not in user_current_stage_defects_ids]
            processed_query = base_query.filter(
                or_(Defect.id.in_(defect_ids), Defect.creator_id == user_id)
            )

        current_app.logger.info(f"session['role_select']:  {session['role_select']}")

        # 权限过滤
        if session['role_select'] in ["全板块查阅人", "项目查阅人", "全板块管理员"]:
            all_projects_versions = ProjectMemberService.get_related_entities_by_user_id(user_id)
            conditions = []
            if all_projects_versions['project_ids']:
                conditions.append(Defect.project_id.in_(all_projects_versions['project_ids']))
            if all_projects_versions['version_ids']:
                conditions.append(Defect.version_id.in_(all_projects_versions['version_ids']))

            if conditions:
                query = query.filter(or_(*conditions))
                if pending_query is not None:
                    pending_query = pending_query.filter(or_(*conditions))
                if processed_query is not None:
                    processed_query = processed_query.filter(or_(*conditions))
            else:
                query = query.filter(False)
                if pending_query is not None:
                    pending_query = pending_query.filter(False)
                if processed_query is not None:
                    processed_query = processed_query.filter(False)

        # 应用筛选条件的函数
        def apply_filters(q):
            if q is None:
                return None
            temp_query = q
            if filters.get('search'):
                temp_query = temp_query.filter(
                    or_(
                        Defect.title.ilike(f"%{filters['search']}%"),
                        Defect.defect_number.ilike(f"%{filters['search']}%")
                    )
                )
            if filters.get('version_projects')!="" and filters.get('version_projects')!="all":
                level3_ids = filters['version_projects'].split(',')
                project_ids = []
                version_ids = []
                for level3_id in level3_ids:
                    if 'p3-' in level3_id:
                        project_ids.append(level3_id.replace("p3-", ""))
                    if 'v3-' in level3_id:
                        version_ids.append(level3_id.replace("v3-", ""))
                conditions = []
                if project_ids:
                    conditions.append(Defect.project_id.in_(project_ids))
                if version_ids:
                    conditions.append(Defect.version_id.in_(version_ids))
                if conditions:
                    temp_query= temp_query.filter(or_(*conditions))
            elif filters.get('version_projects')=="":
                temp_query = temp_query.filter(Defect.version_id==-1)
            if filters.get('severity'):
                temp_query = temp_query.filter(Defect.severity.in_(filters['severity'].split(',')))
            if filters.get('reproducible'):
                temp_query = temp_query.filter(Defect.defect_reproducibility.in_(filters['reproducible'].split(',')))
            if filters.get('completed_by'):
                my_stage_ids = DefectStage.query.filter(
                    DefectStage.completed_by == filters['completed_by']
                ).with_entities(DefectStage.defect_id).distinct().all()
                my_distinct_defect_ids = [defect_id for (defect_id,) in my_stage_ids]
                temp_query = temp_query.filter(
                    and_(
                        DefectStage.assigned_to != filters['completed_by'],
                        Defect.id.in_(my_distinct_defect_ids)
                    )
                )
            if filters.get('stage_types_name'):
                temp_query = temp_query.join(DefectStage.stage_type_ref).filter(
                    DefectStageType.stage_name.in_(filters['stage_types_name'].split(','))
                )
            defect_type = filters.get('defect_type')
            if defect_type in ["simplified", "simplified2"]:
                temp_query = temp_query.filter(Defect.defect_type == defect_type)
            else:
                # 排除这两个特定值，保留其他所有值（包括NULL）
                temp_query = temp_query.filter(or_(Defect.defect_type == None, Defect.defect_type == ""))
            return temp_query
        # 应用筛选条件到所有查询
        query = apply_filters(query)
        pending_query = apply_filters(pending_query)
        processed_query = apply_filters(processed_query)

        # 根据角色和状态选择查询并计算数量
        if session['role_select'] == "流程使用者":
            # 计算数量
            if pending_query is not None:
                pending_num = pending_query.distinct().count()
            if processed_query is not None:
                processed_num = processed_query.distinct().count()

            # 根据筛选条件设置查询
            if filters['deal_status'] == 'pending':
                query = pending_query if pending_query is not None else base_query.filter(False)
            elif filters['deal_status'] == 'processed':
                query = processed_query if processed_query is not None else base_query.filter(False)
            else:
                # 默认情况
                query = pending_query if pending_query is not None else base_query.filter(False)

        else:
            # 对于其他角色
            try:
                # 待处理：未关闭的缺陷
                pending_count_query = query.filter(
                    and_(
                        Defect.status != 'DefectStatus.CLOSED',
                        Defect.status != 'DefectStatus.TERMINATE_TRACKING'
                    )
                ) if query is not None else None
                pending_num = pending_count_query.distinct().count() if pending_count_query is not None else 0

                # 已处理：已关闭的缺陷
                processed_count_query = query.filter(
                    or_(
                        Defect.status == 'DefectStatus.CLOSED',
                        Defect.status == 'DefectStatus.TERMINATE_TRACKING'
                    )
                ) if query is not None else None
                processed_num = processed_count_query.distinct().count() if processed_count_query is not None else 0
            except Exception as e:
                current_app.logger.error(f"计算数量时出错: {e}")
                pending_num = 0
                processed_num = 0

        # 应用排序
        if filters.get('sort'):
            sort_param = filters['sort'].split(',')
            if len(sort_param) > 1:
                if sort_param[0] == "version_projects":
                    if sort_param[1] == 'desc':
                        query = query.order_by(Defect.version_id.desc())
                    else:
                        query = query.order_by(Defect.version_id.asc())
                elif sort_param[0] == "stage_types_name":
                    query = query.join(DefectStage.stage_type_ref)
                    if sort_param[1] == 'desc':
                        query = query.order_by(DefectStageType.stage_order.desc())
                    else:
                        query = query.order_by(DefectStageType.stage_order.asc())
                elif sort_param[0] == "severity":
                    if sort_param[1] == 'desc':
                        query = query.order_by(Defect.severity.desc())
                    else:
                        query = query.order_by(Defect.severity.asc())
                elif sort_param[0] == "reproducible":
                    if sort_param[1] == 'desc':
                        query = query.order_by(Defect.defect_reproducibility.desc())
                    else:
                        query = query.order_by(Defect.defect_reproducibility.asc())
                elif sort_param[0] == "days":
                    if sort_param[1] == 'desc':
                        query = query.order_by(Defect.created_time.desc())
                    else:
                        query = query.order_by(Defect.created_time.asc())

        # 最终查询 - 确保去重
        final_query = query.distinct()

        # 生成SQL语句用于调试
        version_projects = DefectService.get_distinct_version_project_ids(final_query)
        sql = final_query.statement.compile(compile_kwargs={"literal_binds": True})
        current_app.logger.info(f"最终SQL查询: {sql}")

        # 记录计数用于调试
        current_app.logger.info(f"pending_num: {pending_num}, 查询总数: {final_query.count()}")

        total = final_query.count()

        # 分页查询
        defects = final_query.order_by(Defect.updated_time.desc()).paginate(
            page=page, per_page=per_page, error_out=False)

        pagination = Pagination(
            page=page,
            per_page=per_page,
            total=total,
            css_framework='bootstrap5',  # 支持 bootstrap4/bootstrap5/foundation 等
            alignment='right',  # 分页居中
            prev_label='<',  # 自定义上一页文本
            next_label='>',  # 自定义下一页文本
        )

        # 记录实际返回的缺陷数量用于调试
        current_app.logger.info(f"实际返回缺陷数量: {len(defects.items)}")

        # 为每个缺陷添加stage_name字段
        version_ids = []
        project_ids = []
        for defect in defects.items:
            if defect.current_stage.stage_type_ref:
                defect.stage_name = defect.current_stage.stage_type_ref.stage_name
            else:
                defect.stage_name = None

            defect.status_name = STATUS_MAPPING.get(defect.status, '未知')

            if defect.version_id is not None:
                version_ids.append(defect.version_id)
            else:
                project_ids.append(defect.project_id)

        project_line = {}
        tech_group = {}
        if version_ids:
            project_line, _ = ProductLineService.get_versions_by_ids(version_ids)
        if project_ids:
            tech_group, _ = TechGroupService.get_projects_by_ids(project_ids)

        for defect in defects.items:
            if defect.version_id is not None:
                defect.product_or_version = project_line.get(defect.version_id)
            else:
                defect.product_or_version = tech_group.get(defect.project_id)

            current_date = datetime.now()
            # 计算天数差（向上取整）
            defect.days_passed = (current_date - defect.created_time).days + 1

            if defect.severity == DefectSeverity.MINOR_DEFECTS.value:
                defect.severity_class = "status-normal"
            elif defect.severity == DefectSeverity.MAJOR_DEFECTS.value:
                defect.severity_class = "status-serious"
            elif defect.severity == DefectSeverity.SUGGESTION_DEFECTS.value:
                defect.severity_class = "status-minor"
            else:
                defect.severity_class = "status-urgent"

        # 获取所有可用的阶段名称，用于筛选下拉框
        if filters.get('defect_type') != "simplified":
            stage_types = DefectStageType.query.order_by(DefectStageType.stage_order.asc()).all()
            stage_types_name = [stage_type.stage_name for stage_type in stage_types]
        else:
            stage_types_name = ['缺陷描述','开发人员定位问题','开发人员解决措施','测试人员回归测试']
        return defects, stage_types_name, pagination, version_projects, processed_num, pending_num

    @staticmethod
    def get_distinct_version_project_ids(query):
        my_version_ids = query.filter(Defect.version_id is not None).with_entities(Defect.version_id).distinct().all()
        my_project_ids = query.filter(Defect.project_id is not None).with_entities(Defect.project_id).distinct().all()
        my_distinct_version_ids = [version_id for (version_id,) in my_version_ids]
        my_distinct_project_ids = [project_id for (project_id,) in my_project_ids]
        product_line_distinct = {}
        tech_group_distinct = {}
        if len(my_distinct_version_ids) > 0:
           product_line_distinct,_ = ProductLineService.get_versions_by_ids(my_distinct_version_ids)
        if len(my_distinct_project_ids) > 0:
           tech_group_distinct,_ = TechGroupService.get_projects_by_ids(my_distinct_project_ids)
        return {"version":product_line_distinct,"project":tech_group_distinct}

    @staticmethod
    def generate_defect_number():
        date_str = datetime.now().strftime("%Y%m%d")

        # 使用数据库事务原子性更新计数器
        counter = DefectCounter.query.filter_by(date=date_str).with_for_update().first()

        if not counter:
            counter = DefectCounter(date=date_str, count=1)
            db.session.add(counter)
        else:
            counter.count += 1

        db.session.commit()

        return f"{date_str}{counter.count:04d}"  # 格式举例： 202508191024

    @staticmethod
    def validate_user_exists(user_id: int) -> bool:
        """验证用户ID是否存在"""
        return User.query.get(user_id) is not None

    @staticmethod
    def validate_defect_exists(defect_id: int) -> bool:
        """验证缺陷ID是否存在"""
        return Defect.query.get(defect_id) is not None

    @staticmethod
    def get_defect_stage_types_dict():
        try:
            stage_types = DefectStageType.query.order_by(DefectStageType.stage_order.asc()).all()
            result = {}
            for stage_type in stage_types:
                result[stage_type.stage_key] = stage_type.stage_name
            return result
        except Exception as e:
            print(f"Error fetching defect stage types: {str(e)}")
            return {}

    @staticmethod
    def create_defect(
            title: str,
            description: str,
            severity: str,
            defect_reproducibility: str,
            creator_id: int,
            version_id: int = None,
            project_id: int = None,
            status: str = '',
            defect_type: str = ''
    ) -> Optional[Defect]:
        """创建新的缺陷问题单（同时创建初始阶段），支持草稿或正常缺陷单，并记录流程历史记录"""
        try:
            # 验证creator_id是否存在
            if not DefectService.validate_user_exists(creator_id):
                current_app.logger.warning(f"创建者ID {creator_id} 不存在")
                raise ValueError(f"创建者ID {creator_id} 不存在")

            # 创建缺陷对象
            defect = Defect(
                title=title,
                defect_number=DefectService.generate_defect_number(),  # 缺陷单号 自动生成
                description=description,
                severity=severity,
                defect_reproducibility=defect_reproducibility,
                creator_id=creator_id,
                version_id=version_id,
                project_id=project_id,
                status=status,
                created_time=datetime.now(),
                updated_time=datetime.now(),
                defect_type=defect_type
            )
            db.session.add(defect)
            db.session.flush()  # 获取defect ID但不提交事务
            if not defect:
                db.session.rollback()
                return None
            current_app.logger.debug(f'defect.id: {defect.id}')

            # 创建初始阶段 - 问题描述阶段（未记录日志，也不保存阶段数据）
            initial_stage = DefectStageService.create_initial_stage(defect.id, creator_id)
            if not initial_stage:
                current_app.logger.error("创建初始阶段失败")
                db.session.rollback()
                return None

            defect.current_stage_id = initial_stage.id
            if defect.defect_type == 'simplified' or defect.defect_type == 'simplified2':
                notes = "创建缺陷问题单"
            else:
                # 记录流程历史
                if status == 'DefectStatus.DRAFT':
                    notes = "创建缺陷问题单(草稿，不进入缺陷描述审核阶段)"
                else:
                    notes = "创建缺陷问题单(将进入缺陷描述审核阶段)"
            flow_history = DefectFlowHistoryService.record_flow(
                defect_id=defect.id,
                to_stage_id=initial_stage.id,
                action_type=ActionType.CREATE,
                action_by=creator_id,
                notes=notes
            )

            if not flow_history:
                current_app.logger.error("记录流程历史失败")
                db.session.rollback()
                return None
            return defect

        except (IntegrityError, DataError, DatabaseError) as e:
            db.session.rollback()
            current_app.logger.error(f"数据库错误: {str(e)}")

            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            elif "data" in str(e).lower():
                raise ValueError(f"数据错误: 输入数据可能不符合要求")
            else:
                raise RuntimeError(f"数据库操作失败: {str(e)}")

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"创建缺陷时发生意外错误: {str(e)}")
            raise RuntimeError(f"创建缺陷时发生意外错误: {str(e)}")

    @staticmethod
    def update_defect(defect_id: int, **kwargs) -> Optional[Defect]:
        """更新缺陷信息"""
        try:
            # 验证defect_id是否存在
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")

            defect = Defect.query.get(defect_id)
            if not defect:
                return None

            # 如果有creator_id在kwargs中，验证其有效性
            if 'creator_id' in kwargs and not DefectService.validate_user_exists(kwargs['creator_id']):
                raise ValueError(f"创建者ID {kwargs['creator_id']} 不存在")

            for key, value in kwargs.items():
                if hasattr(defect, key):
                    setattr(defect, key, value)

            defect.updated_time = datetime.now()
            return defect

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except DataError as e:
            db.session.rollback()
            raise ValueError(f"数据错误: {str(e)}")
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"更新缺陷时发生错误: {str(e)}")

    @staticmethod
    def get_defect_by_id(defect_id: int) -> Optional[Defect]:
        """根据ID获取缺陷详情"""
        try:
            if not DefectService.validate_defect_exists(defect_id):
                return None

            # 获取缺陷详情
            defect = Defect.query.options(
                joinedload(Defect.creator),
                joinedload(Defect.version),
                joinedload(Defect.project),
                joinedload(Defect.current_stage)
            ).get(defect_id)

            # 为缺陷对象添加项目版本名称
            if defect:
                project_version_name = DefectService.get_project_version_name(defect)
                defect.type = "技术族" if getattr(defect, 'project_id', None) else "产品线"
                defect.project_version_name = project_version_name

            return defect
        except Exception as e:
            raise RuntimeError(f"获取缺陷信息时发生错误: {str(e)}")

    @staticmethod
    def mark_as_duplicate(defect_id: int, source_defect_id: int, user_id: int) -> Optional[Defect]:
        """标记缺陷为重复问题"""
        try:
            # 验证defect_id和source_defect_id是否存在
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectService.validate_defect_exists(source_defect_id):
                raise ValueError(f"源缺陷ID {source_defect_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            defect = Defect.query.get(defect_id)
            if not defect:
                return None

            defect.is_duplicate = True
            defect.duplicate_source_id = source_defect_id
            defect.status = 'DefectStatus.REJECTED'
            defect.updated_time = datetime.now()

            # 记录流程历史
            flow_history = DefectFlowHistoryService.record_flow(
                defect_id=defect.id,
                to_stage_id=defect.current_stage_id,
                action_type=ActionType.REJECT,
                action_by=user_id,
                notes=f"标记为重复问题，源问题ID: {source_defect_id}"
            )

            if not flow_history:
                db.session.rollback()
                return None

            return defect

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"标记缺陷为重复问题时发生错误: {str(e)}")

    @staticmethod
    def submit_defect(defect_id: int, user_id: int) -> Optional[Defect]:
        """将Draft状态的缺陷提交进入流程"""
        try:
            # 验证defect_id和user_id是否存在
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            defect = Defect.query.get(defect_id)
            if not defect or defect.status != 'DefectStatus.DRAFT':
                return None

            # 获取当前阶段（问题描述阶段）
            current_stage = DefectStage.query.get(defect.current_stage_id)
            if not current_stage:
                raise ValueError(f"缺陷 {defect_id} 的当前阶段不存在")

            # 创建问题描述阶段数据
            defect_description_data,is_change = DefectStageDataService.submit_stage_data(
                defect_stage_id=current_stage.id,
                data_type=DataType.DEFECT_DESCRIPTION,
                content={
                    "title": defect.title,
                    "description": defect.description,
                    "severity": defect.severity,
                    "defect_reproducibility": defect.defect_reproducibility
                },
                submitted_by=user_id,
                is_draft=False
            )

            if not defect_description_data:
                db.session.rollback()
                return None

            # 创建测试经理审核阶段
            # 假设测试经理的用户ID为1，实际应用中应该从项目配置或用户角色中获取
            test_manager_id = 1

            review_stage = DefectStageService.create_next_stage(  # 创建测试经理审核缺陷描述阶段
                defect_id=defect_id,
                stage_type_key="test_manager_review_desc",  # 假设存在这个阶段类型
                assigned_to=test_manager_id,
                previous_stage_id=current_stage.id,
                user_id=user_id
            )

            if not review_stage:
                db.session.rollback()
                return None

            # 更新缺陷状态
            defect.status = 'DefectStatus.OPEN'
            defect.updated_time = datetime.now()

            # 记录流程历史
            flow_history = DefectFlowHistoryService.record_flow(
                defect_id=defect.id,
                from_stage_id=current_stage.id,
                to_stage_id=review_stage.id,
                action_type=ActionType.SUBMIT,
                action_by=user_id,
                notes="提交缺陷进入测试经理审核阶段"
            )

            if not flow_history:
                db.session.rollback()
                return None

            return defect

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"提交草稿状态的缺陷进入流程时发生错误: {str(e)}")


    @staticmethod
    def get_project_version_name(defect:Defect) -> str:
        """
        获取 缺陷单 所属的 产品线/技术族 名称
        """
        project_version_name = '无'

        if defect.project_id:
            result, status_code = TechGroupService.get_hierarchy_by_project_id(defect.project_id)
            if result and result.get('data'):
                project_version_name = result.get('data').get('full_path', project_version_name)

        if defect.version_id:
            result, status_code = ProductLineService.get_hierarchy_by_version_id(defect.version_id)
            if result and result.get('data'):
                project_version_name = result.get('data').get('full_path', project_version_name)

        return project_version_name

    @staticmethod
    def get_duplicate_defects_infos(defect) -> List[Dict[str, Any]]:
        """通过关系获取所有复制生成的问题单"""
        if not defect:
            return []

        duplicate_defects = getattr(defect, 'duplicates', [])
        duplicate_defects_infos = []
        for item in duplicate_defects:
            project_version_name = DefectService.get_project_version_name(item)
            item_info = {
                "id": getattr(item, 'id', None),
                "defect_number": getattr(item, 'defect_number', None),
                "project_version_name": project_version_name,
                "type": "技术族" if getattr(item, 'project_id', None) else "产品线"
            }
            duplicate_defects_infos.append(item_info)
        return duplicate_defects_infos


class DefectStageService:
    """缺陷阶段服务类，处理阶段相关业务逻辑"""

    @staticmethod
    def validate_stage_exists(stage_id: int) -> bool:
        """验证阶段ID是否存在"""
        return DefectStage.query.get(stage_id) is not None

    @staticmethod
    def create_initial_stage(defect_id: int, creator_id: int) -> Optional[DefectStage]:
        """创建初始阶段（缺陷描述阶段 和 草稿创建阶段）"""
        try:
            # 验证defect_id和creator_id是否存在
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectService.validate_user_exists(creator_id):
                raise ValueError(f"创建者ID {creator_id} 不存在")

            # 获取缺陷描述阶段的类型
            description_stage_type = DefectStageType.query.filter_by(
                stage_key="defect_description").first()

            if not description_stage_type:  # 异常处理，如果数据库中不小心删除了DefectStageType，使用此方式规避
                # 如果不存在，创建一个默认的问题描述阶段类型
                description_stage_type = DefectStageType(
                    stage_key="defect_description",
                    stage_name="问题描述",
                    description="缺陷问题描述阶段",
                    stage_order=1
                )
                db.session.add(description_stage_type)
                db.session.flush()
            defect = DefectService.get_defect_by_id(defect_id)
            stage_type = 'defect_description'
            stage_status = 'StageStatus.IN_PROGRESS'
            if defect.status == 'DefectStatus.DRAFT' and defect.defect_type!='simplified':
                stage_type = 'draft_creation'
                stage_status = 'StageStatus.DRAFT'
            stage = DefectStage(
                defect_id=defect_id,
                stage_type=stage_type,  # 'defect_description' 或者 'draft_creation'
                assigned_to=creator_id,
                status=stage_status,
                notes='创建缺陷单时同步创建',
                created_time=datetime.now(),
                updated_time=datetime.now()
            )

            db.session.add(stage)
            db.session.flush()

            return stage

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"创建初始阶段时发生错误: {str(e)}")

    @staticmethod
    def create_next_stage(defect_id: int, stage_type_key: str, assigned_to: int,
                          previous_stage_id: int, user_id: int,ai_sug_score_id=None) -> Optional[DefectStage]:
        """创建下一阶段"""
        try:
            # 验证所有ID的有效性
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectService.validate_user_exists(assigned_to):
                raise ValueError(f"分配用户ID {assigned_to} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")
            if not DefectStageService.validate_stage_exists(previous_stage_id):
                raise ValueError(f"前一阶段ID {previous_stage_id} 不存在")

            defect = Defect.query.get(defect_id)
            if not defect:
                return None

            # 获取阶段类型
            stage_type = DefectStageType.query.filter_by(stage_key=stage_type_key).first()
            if not stage_type:
                raise ValueError(f"阶段类型 {stage_type_key} 不存在")
            notes = ''
            if defect.defect_type=='simplified2':
                notes = '创建缺陷单时同步创建'
            # 创建新阶段
            stage = DefectStage(
                defect_id=defect_id,
                stage_type=stage_type.stage_key,
                assigned_to=assigned_to,
                previous_stage_id=previous_stage_id,
                status=StageStatus.IN_PROGRESS,
                notes=notes,
                created_time=datetime.now(),
                updated_time=datetime.now()
            )

            db.session.add(stage)
            db.session.flush()

            # 更新缺陷的当前阶段
            defect.current_stage_id = stage.id
            defect.updated_time = datetime.now()

            # 完成前一阶段
            previous_stage = DefectStage.query.get(previous_stage_id)
            if previous_stage:
                if defect.defect_type != 'simplified' and defect.defect_type != 'simplified2':
                    previous_stage.status = StageStatus.COMPLETED
                    previous_stage.completed_time = datetime.now()
                previous_stage.completed_by = user_id

            if defect.defect_type!='simplified' and defect.defect_type!='simplified2':
                # 记录流程历史
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=defect_id,
                    from_stage_id=previous_stage_id,
                    to_stage_id=stage.id,
                    action_type=ActionType.UPDATE if ai_sug_score_id is None else ActionType.VAL_SUBMIT,
                    action_by=user_id,
                    notes=f"执行操作，使缺陷单进入 {stage_type.stage_name} 阶段" if ai_sug_score_id is None else f"执行AI评估完成，使缺陷单进入{stage_type.stage_name} 阶段",
                    ai_sug_score_id=ai_sug_score_id,
                )

                if not flow_history:
                    db.session.rollback()
                    return None

            return stage

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"创建下一阶段时发生错误: {str(e)}")

    @staticmethod
    def update_stage(stage_id: int, assigned_to: int = None, completed_by: int = None,
                     updated_time: datetime = None, completed_time: datetime = None,
                     status: StageStatus = None, notes: str = None) -> Optional[DefectStage]:
        """更新阶段信息

        Args:
            stage_id: 要更新的阶段ID
            assigned_to: 新的负责人ID
            completed_by: 新的完成人ID
            updated_time: 更新时间
            completed_time: 完成时间
            status: 阶段状态
            notes: 阶段备注信息

        Returns:
            更新后的阶段对象，如果更新失败则返回None

        Raises:
            ValueError: 参数验证失败
            RuntimeError: 更新过程中发生错误
        """
        try:
            # 验证阶段是否存在
            stage = DefectStage.query.get(stage_id)
            if not stage:
                raise ValueError(f"阶段ID {stage_id} 不存在")

            # 验证用户ID有效性（如果提供了的话）
            if assigned_to is not None and not DefectService.validate_user_exists(assigned_to):
                raise ValueError(f"分配用户ID {assigned_to} 不存在")

            if completed_by is not None and not DefectService.validate_user_exists(completed_by):
                raise ValueError(f"完成用户ID {completed_by} 不存在")

            # 更新字段
            if assigned_to is not None:
                stage.assigned_to = assigned_to

            if completed_by is not None:
                stage.completed_by = completed_by

            if updated_time is not None:
                stage.updated_time = updated_time
            else:
                stage.updated_time = datetime.now()  # 如果没有提供更新时间，则使用当前时间

            if completed_time is not None:
                stage.completed_time = completed_time

            if status is not None:
                stage.status = status

                # 如果状态变为完成且没有设置完成时间，则自动设置
                if status == StageStatus.COMPLETED and stage.completed_time is None:
                    stage.completed_time = datetime.now()

            if notes is not None:
                stage.notes = notes

            # 提交到数据库
            db.session.commit()

            # 记录更新日志（可选，根据实际需求添加）
            # DefectFlowHistoryService.record_flow(
            #     defect_id=stage.defect_id,
            #     from_stage_id=stage_id,
            #     to_stage_id=stage_id,
            #     action_type=ActionType.UPDATE,
            #     action_by=completed_by or assigned_to,  # 使用完成人或负责人
            #     notes=f"更新阶段信息: {notes}" if notes else "更新阶段信息"
            # )

            return stage

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"更新阶段时发生错误: {str(e)}")

    @staticmethod
    def get_stage_user(defect_id, stage_type):
        """根据缺陷ID和阶段类型获取对应的用户，供简化版DTS使用"""
        stage = DefectStageService.get_stage_by_defect_and_type(defect_id, stage_type)
        current_app.logger.debug(f'get_stage_by_defect_and_type stage {stage}')
        if stage and stage.notes:
            return User.get_user_by_id(stage.assigned_to)
        return None

    @staticmethod
    def get_stage_by_id(stage_id: int) -> Optional[DefectStage]:
        """根据ID获取阶段详情"""
        try:
            if not DefectStageService.validate_stage_exists(stage_id):
                return None

            return DefectStage.query.options(
                joinedload(DefectStage.defect),
                joinedload(DefectStage.stage_type_ref),
                joinedload(DefectStage.assignee),
                joinedload(DefectStage.completer)
            ).get(stage_id)
        except Exception as e:
            raise RuntimeError(f"获取阶段信息时发生错误: {str(e)}")

    @staticmethod
    def get_stage_by_defect_and_type(defect_id: int, stage_type: str) -> Optional[DefectStage]:
        """根据缺陷ID和阶段类型获取首个匹配的阶段记录

        Args:
            defect_id: 缺陷ID
            stage_type: 阶段类型键值

        Returns:
            Optional[DefectStage]: 匹配的阶段记录，如不存在则返回None

        Raises:
            RuntimeError: 查询过程中发生错误时抛出
        """
        try:
            return DefectStage.query.options(
                joinedload(DefectStage.defect),
                joinedload(DefectStage.stage_type_ref),
                joinedload(DefectStage.assignee),
                joinedload(DefectStage.completer),
                joinedload(DefectStage.previous_stage)
            ).filter_by(
                defect_id=defect_id,
                stage_type=stage_type
            ).first()
        except Exception as e:
            raise RuntimeError(f"get_stage_by_defect_and_type Error: {str(e)}")

    @staticmethod
    def get_stage_ids_by_type(defect_id: int, stage_type: str) -> List[int]:
        """
        根据缺陷ID和阶段类型查询对应的阶段ID列表（按ID降序排列）

        参数:
            defect_id (int): 缺陷的唯一标识符
            stage_type (str): 要查询的阶段类型（如："cause_analysis"、 "developer_solution"）

        返回:
            List[int]: 符合条件的阶段ID列表（按ID降序），如果没有找到则返回空列表
        """
        # 查询指定缺陷ID和阶段类型的所有阶段记录，并按id降序排列
        stages = DefectStage.query.filter(
            DefectStage.defect_id == defect_id,
            DefectStage.stage_type == stage_type
        ).order_by(DefectStage.id.desc()).all()  # 添加降序排序

        return [stage.id for stage in stages]  # 直接推导式返回，空列表会自动处理

    @staticmethod
    def get_stages_by_defect(defect_id: int) -> List[DefectStage]:
        """获取缺陷的所有阶段"""
        try:
            if not DefectService.validate_defect_exists(defect_id):
                return []

            return DefectStage.query.filter_by(defect_id=defect_id).order_by(
                DefectStage.created_time).all()
        except Exception as e:
            raise RuntimeError(f"获取缺陷阶段列表时发生错误: {str(e)}")

    @staticmethod
    def reject_stage(stage_id: int, reason: str, previous_stage_id: int,
                     user_id: int, rejection_type: RejectionType) -> bool:
        """驳回阶段"""
        try:
            # 验证所有ID的有效性
            if not DefectStageService.validate_stage_exists(stage_id):
                raise ValueError(f"阶段ID {stage_id} 不存在")
            if not DefectStageService.validate_stage_exists(previous_stage_id):
                raise ValueError(f"前一阶段ID {previous_stage_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            stage = DefectStage.query.get(stage_id)
            if not stage:
                return False

            # 更新阶段状态
            stage.status = StageStatus.REJECTED
            stage.updated_time = datetime.now()
            stage.rejection_count += 1

            # 更新缺陷的当前阶段
            defect = Defect.query.get(stage.defect_id)
            if defect:
                defect.current_stage_id = previous_stage_id
                defect.updated_time = datetime.now()

            # 记录驳回
            rejection = DefectRejectionService.record_rejection(
                defect_id=stage.defect_id,
                defect_stage_id=stage_id,
                rejection_type=rejection_type,
                rejected_by=user_id,
                reason=reason,
                previous_stage_id=previous_stage_id
            )

            if not rejection:
                db.session.rollback()
                return False

            # 记录流程历史
            flow_history = DefectFlowHistoryService.record_flow(
                defect_id=stage.defect_id,
                from_stage_id=stage_id,
                to_stage_id=previous_stage_id,
                action_type=ActionType.REJECT,
                action_by=user_id,
                notes=f"阶段驳回: {reason}"
            )

            if not flow_history:
                db.session.rollback()
                return False

            return True

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"驳回阶段时发生错误: {str(e)}")

    @staticmethod
    def abandon_stage(stage_id: int, reason: str, user_id: int) -> bool:
        """弃用阶段（记录弃用原因）"""
        try:
            # 验证所有ID的有效性
            if not DefectStageService.validate_stage_exists(stage_id):
                raise ValueError(f"阶段ID {stage_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            stage = DefectStage.query.get(stage_id)
            if not stage:
                return False

            # 记录弃用原因到notes字段
            stage.notes = f"弃用原因({datetime.now().strftime('%Y-%m-%d %H:%M')} by {user_id}): {reason}"
            stage.updated_time = datetime.now()

            # 记录流程历史
            flow_history = DefectFlowHistoryService.record_flow(
                defect_id=stage.defect_id,
                to_stage_id=stage_id,
                action_type=ActionType.UPDATE,
                action_by=user_id,
                notes=f"阶段弃用: {reason}"
            )

            if not flow_history:
                db.session.rollback()
                return False

            return True

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"弃用阶段时发生错误: {str(e)}")


class DefectLocaleInvitationService:
    """开发者定位问题邀请服务类"""

    @staticmethod
    def validate_invitation_exists(invitation_id: int) -> bool:
        """验证邀请ID是否存在"""
        return DefectLocaleInvitation.query.get(invitation_id) is not None

    @staticmethod
    def create_invitation(defect_stage_id: int, inviter_id: int, invitee_id: int,
                          reason: str, action_type: ActionType) -> Optional[DefectLocaleInvitation]:
        """创建定位问题邀请"""
        try:
            current_app.logger.info('邀请开发人员参与问题定位 create_invitation ...')
            # 验证所有ID的有效性
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            if not DefectService.validate_user_exists(inviter_id):
                raise ValueError(f"邀请人ID {inviter_id} 不存在")
            if not DefectService.validate_user_exists(invitee_id):
                raise ValueError(f"被邀请人ID {invitee_id} 不存在")

            invitation = DefectLocaleInvitation(
                defect_stage_id=defect_stage_id,
                inviter_id=inviter_id,
                invitee_id=invitee_id,
                invitation_reason=reason,
                status=InvitationStatus.PENDING,
                created_time=datetime.now(),
                updated_time=datetime.now()
            )

            db.session.add(invitation)
            db.session.flush()
            invitee = User.get_user_by_id(invitee_id)
            # 记录流程历史
            stage = DefectStage.query.get(defect_stage_id)
            if stage:
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=stage.defect_id,
                    to_stage_id=defect_stage_id,
                    action_type=action_type,
                    action_by=inviter_id,
                    notes=f"邀请开发人员 {invitee.real_name}/{invitee.email} 参与问题定位: {reason}"
                )

                if not flow_history:
                    db.session.rollback()
                    return None

            return invitation

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"创建定位邀请时发生错误: {str(e)}")

    @staticmethod
    def get_cause_analysis_invitations(defect_id):
        """
        根据缺陷ID获取原因分析阶段的邀请记录
        1、从 defect_stages 表中根据 defect的 id 获取 stage_type 为"cause_analysis"的 stage 的id。
        2、从 defect_locale_invitations 表中根据 stage 的 id 获取邀请记录（仅获取 待处理、已完成、驳回 的即可，弃用的不需要），按 created_time 升序排列。

        Args:
            defect_id (int): 缺陷ID

        Returns:
            list: 邀请记录列表，按创建时间升序排列
        """
        # 1. 从defect_stages表中获取stage_type为"cause_analysis"的阶段ID
        stage_ids = DefectStageService.get_stage_ids_by_type(defect_id, stage_type="cause_analysis")
        current_app.logger.info(f'get_cause_analysis_invitations stage_ids: {stage_ids}')
        if not stage_ids:
            return []
        if len(stage_ids) > 1:
            current_app.logger.warning('获取原因分析阶段的邀请记录，cause_analysis 阶段 stage_ids 的个数大于1')

        # 2. 从defect_locale_invitations表中获取邀请记录
        # 只获取待处理和已完成的邀请，按创建时间降序排列
        invitations = DefectLocaleInvitation.query.filter(
            DefectLocaleInvitation.defect_stage_id.in_(stage_ids),
            DefectLocaleInvitation.status.in_([
                InvitationStatus.PENDING,
                InvitationStatus.COMPLETED,
                InvitationStatus.REJECTED,
                InvitationStatus.CANCELLED,
            ])
        ).order_by(DefectLocaleInvitation.created_time.asc()).all()

        return invitations

    @staticmethod
    def get_invitations_by_ids(invitation_ids, status_filter=None, include_relationships=False):
        """
        根据邀请ID列表获取邀请记录

        Args:
            invitation_ids (list): 邀请ID列表
            status_filter (list, optional): 状态过滤列表，如不指定则返回所有状态
            include_relationships (bool, optional): 是否预加载关联关系

        Returns:
            list: 邀请记录列表，按创建时间升序排列
        """
        if not invitation_ids:
            return []

        try:
            # 构建基础查询
            query = DefectLocaleInvitation.query.filter(
                DefectLocaleInvitation.id.in_(invitation_ids)
            )

            # 添加状态过滤
            if status_filter:
                query = query.filter(DefectLocaleInvitation.status.in_(status_filter))

            # 预加载关联关系
            if include_relationships:
                query = query.options(
                    db.joinedload(DefectLocaleInvitation.defect_stage),
                    db.joinedload(DefectLocaleInvitation.inviter),
                    db.joinedload(DefectLocaleInvitation.invitee)
                )

            # 按创建时间升序排列
            invitations = query.order_by(DefectLocaleInvitation.created_time.asc()).all()

            current_app.logger.info(f'get_invitations_by_ids 成功获取 {len(invitations)} 条邀请记录')
            return invitations

        except Exception as e:
            current_app.logger.error(f'获取邀请记录失败，invitation_ids: {invitation_ids}, 错误: {str(e)}')
            return []

    @staticmethod
    def update_invitation_status(invitation_id: int, new_status: InvitationStatus, reason: str = '') -> Optional[
        DefectLocaleInvitation]:
        """
        更新邀请状态

        Args:
            invitation_id: 邀请ID
            new_status: 新的状态值（InvitationStatus枚举）
            reason: 原因

        Returns:
            DefectLocaleInvitation: 更新后的邀请对象，失败时返回None
        """
        try:
            # 验证所有ID的有效性
            if not DefectLocaleInvitationService.validate_invitation_exists(invitation_id):
                raise ValueError(f"邀请ID {invitation_id} 不存在")

            invitation = DefectLocaleInvitation.query.get(invitation_id)
            if not invitation:
                return None

            # 更新状态
            old_status = invitation.status
            invitation.status = new_status
            invitation.updated_time = datetime.now()

            # 如果是完成状态，记录完成时间
            if new_status == InvitationStatus.COMPLETED:
                invitation.completed_time = datetime.now()

            # 如果是完成状态，记录完成时间
            if new_status == InvitationStatus.REJECTED:
                invitation.rejection_time = datetime.now()
                invitation.rejection_reason = reason

            # 记录流程历史（如果需要）
            if str(old_status) != str(new_status):
                stage = DefectStage.query.get(invitation.defect_stage_id)
                if stage:
                    action_note = f"定位分析邀请状态更新: {old_status} -> {new_status}"

                    flow_history = DefectFlowHistoryService.record_flow(
                        defect_id=stage.defect_id,
                        to_stage_id=invitation.defect_stage_id,
                        action_type=ActionType.UPDATE,
                        action_by=g.user_id,
                        notes=action_note
                    )

                    if not flow_history:
                        db.session.rollback()
                        return None

            return invitation

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"更新邀请状态时发生错误: {str(e)}")

    @staticmethod
    def respond_to_invitation(invitation_id: int, user_id: int, accepted: bool,
                              reason: str = None) -> Optional[DefectLocaleInvitation]:
        """响应邀请"""
        try:
            # 验证所有ID的有效性
            if not DefectLocaleInvitationService.validate_invitation_exists(invitation_id):
                raise ValueError(f"邀请ID {invitation_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            invitation = DefectLocaleInvitation.query.get(invitation_id)
            if not invitation or invitation.invitee_id != user_id:
                return None

            if accepted:
                invitation.status = InvitationStatus.ACCEPTED

                # 添加协作者
                collaborator = DefectStageCollaboratorService.add_collaborator(
                    defect_stage_id=invitation.defect_stage_id,
                    user_id=user_id,
                    role=CollaboratorRole.COLLABORATOR,
                    locale_invitation_id=invitation_id
                )

                if not collaborator:
                    db.session.rollback()
                    return None

                action_note = "接受问题定位邀请"
            else:
                invitation.status = InvitationStatus.REJECTED
                invitation.rejection_reason = reason
                invitation.rejection_time = datetime.now()
                action_note = f"拒绝问题定位邀请: {reason}"

            invitation.updated_time = datetime.now()

            # 记录流程历史
            stage = DefectStage.query.get(invitation.defect_stage_id)
            if stage:
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=stage.defect_id,
                    to_stage_id=invitation.defect_stage_id,
                    action_type=ActionType.UPDATE,
                    action_by=user_id,
                    notes=action_note
                )

                if not flow_history:
                    db.session.rollback()
                    return None

            return invitation

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"响应邀请时发生错误: {str(e)}")

    @staticmethod
    def send_reminder(invitation_id: int, reminder_by: int, message: str) -> bool:
        """发送邀请跟催"""
        try:
            # 验证所有ID的有效性
            if not DefectLocaleInvitationService.validate_invitation_exists(invitation_id):
                raise ValueError(f"邀请ID {invitation_id} 不存在")
            if not DefectService.validate_user_exists(reminder_by):
                raise ValueError(f"提醒人ID {reminder_by} 不存在")

            invitation = DefectLocaleInvitation.query.get(invitation_id)
            if not invitation:
                return False

            # 更新邀请的跟催信息
            invitation.reminder_count += 1
            invitation.last_reminder_time = datetime.now()
            invitation.updated_time = datetime.now()

            # 创建跟催记录
            stage = DefectStage.query.get(invitation.defect_stage_id)
            if stage:
                reminder = DefectReminderService.create_reminder(
                    defect_id=stage.defect_id,
                    defect_stage_id=invitation.defect_stage_id,
                    reminder_type=ReminderType.ANALYSIS,
                    target_id=invitation_id,
                    reminder_by=reminder_by,
                    reminder_message=message
                )

                if not reminder:
                    db.session.rollback()
                    return False

                MessageCreator.create_urge_message(
                    defect_id=stage.defect_id,
                    target_user_id=invitation.invitee_id,
                    operator_id=reminder_by,
                    urge_type='reason_analysis',
                    reason=message
                )
                email_content = DefectEmailService.get_urge_email_content(
                    defect=stage.defect,
                    urge_type='reason_analysis',
                    urge_reason=message,
                    urger_id=reminder_by  # 用户ID
                )
                email_subject = DefectEmailService.get_email_subject_by_message_type(
                    defect=stage.defect,
                    message_type=MessageTypes.URGE_REASON_ANALYSIS
                )
                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=invitation.invitee_id,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title=email_subject
                                                                    )


            return True

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"发送邀请跟催时发生错误: {str(e)}")


class DefectSolutionDivisionService:
    """解决措施分工服务类"""

    @staticmethod
    def validate_division_exists(division_id: int) -> bool:
        """验证分工ID是否存在"""
        return DefectSolutionDivision.query.get(division_id) is not None

    @staticmethod
    def create_division(defect_stage_id: int, module: str, due_date: datetime, assign_by_id: int,
                        assignee_id: int, action_plan: str) -> Optional[DefectSolutionDivision]:
        """创建解决措施分工"""
        try:
            # 验证所有ID的有效性
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            if not DefectService.validate_user_exists(assign_by_id):
                current_app.logger.error(f"分配人ID {assign_by_id} 不存在")
                raise ValueError(f"分配人ID {assignee_id} 不存在")
            if not DefectService.validate_user_exists(assignee_id):
                current_app.logger.error(f"被分配人ID {assignee_id} 不存在")
                raise ValueError(f"被分配人ID {assignee_id} 不存在")

            division = DefectSolutionDivision(
                defect_stage_id=defect_stage_id,
                module=module,
                due_date=due_date,
                assign_by_id=assign_by_id,
                assignee_id=assignee_id,
                action_plan=action_plan,
                created_time=datetime.now(),
                updated_time=datetime.now()
            )

            db.session.add(division)
            db.session.flush()
            assignee = User.get_user_by_id(assignee_id)
            # 记录流程历史
            stage = DefectStage.query.get(defect_stage_id)
            if stage:
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=stage.defect_id,
                    to_stage_id=defect_stage_id,
                    action_type=ActionType.ASSIGN_DIVISION,
                    action_by=assign_by_id,  # 这里应该是分配者ID，可能需要调整
                    notes=f"分配解决措施任务给 {assignee.real_name}/{assignee.email}: {action_plan}"
                )

                if not flow_history:
                    db.session.rollback()
                    return None

            return division

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"创建分工时发生错误: {str(e)}")

    @staticmethod
    def get_solution_divisions_by_defect_id(defect_id):
        """
        根据缺陷ID获取解决措施阶段的邀请记录
        1、从 defect_stages 表中根据 defect的 id 获取 stage_type 为"developer_solution"的 stage 的id。
        2、从 defect_solution_divisions 表中根据 stage 的 id 获取分工记录（仅获取 待处理、已完成、驳回 的即可，弃用的不需要），按 created_time 升序排列。

        参数:
            defect_id: 缺陷ID

        返回:
            解决措施阶段的邀请记录列表，按创建时间升序排列
        """
        # 1. 获取stage_type为"developer_solution"的阶段ID
        current_app.logger.info(f'get_solution_divisions_by_defect_id defect_id: {defect_id}')
        stage_ids = DefectStageService.get_stage_ids_by_type(defect_id, stage_type="developer_solution")
        current_app.logger.info(f'get_solution_divisions_by_defect_id stage_ids: {stage_ids}')
        if not stage_ids:
            return []
        if len(stage_ids) > 1:
            current_app.logger.warning('获取解决措施阶段的邀请记录，developer_solution 阶段 stage_ids 的个数大于1')

        # 2. 获取邀请记录（仅获取待处理和已完成的）
        divisions = DefectSolutionDivision.query.filter(
            DefectSolutionDivision.defect_stage_id.in_(stage_ids),
            DefectSolutionDivision.status.in_([
                InvitationStatus.PENDING,
                InvitationStatus.COMPLETED,
                InvitationStatus.REJECTED,
            ])
        ).order_by(DefectSolutionDivision.created_time.asc()).all()

        return divisions

    @staticmethod
    def get_solution_divisions_by_division_ids(division_ids):
        """
        根据分工记录ID列表获取分工记录

        参数:
            division_ids: 分工记录ID列表

        返回:
            分工记录列表，按创建时间升序排列
        """
        if not division_ids:
            return []

        current_app.logger.info(f'get_solution_divisions_by_division_ids division_ids: {division_ids}')

        # 直接根据分工记录ID列表查询，并过滤指定状态
        divisions = DefectSolutionDivision.query.filter(
            DefectSolutionDivision.id.in_(division_ids),
            DefectSolutionDivision.status.in_([
                InvitationStatus.PENDING,
                InvitationStatus.COMPLETED,
                InvitationStatus.REJECTED,
            ])
        ).order_by(DefectSolutionDivision.created_time.asc()).all()

        current_app.logger.info(f'get_solution_divisions_by_division_ids found {len(divisions)} divisions')

        return divisions

    @staticmethod
    def update_division_status(division_id: int, new_status: InvitationStatus, reason: str = '') -> Optional[
        DefectSolutionDivision]:
        """
        更新分工状态

        Args:
            division_id: 分工ID
            new_status: 新的状态值（InvitationStatus枚举）
            reason: 原因

        Returns:
            DefectSolutionDivision: 更新后的分工对象，失败时返回None
        """
        try:
            # 验证所有ID的有效性
            if not DefectSolutionDivisionService.validate_division_exists(division_id):
                raise ValueError(f"分工ID {division_id} 不存在")

            division = DefectSolutionDivision.query.get(division_id)
            if not division:
                return None

            # 更新状态
            old_status = division.status
            division.status = new_status
            division.updated_time = datetime.now()

            # 如果是完成状态，记录完成时间
            if new_status == InvitationStatus.COMPLETED:
                division.completed_time = datetime.now()

            # 如果是驳回状态，记录驳回时间和原因
            if new_status == InvitationStatus.REJECTED:
                division.rejection_time = datetime.now()
                division.rejection_reason = reason

            # 记录流程历史（如果需要）
            if old_status != new_status:
                stage = DefectStage.query.get(division.defect_stage_id)
                if stage:
                    action_note = f"解决措施分工状态更新: {old_status} -> {new_status}"

                    flow_history = DefectFlowHistoryService.record_flow(
                        defect_id=stage.defect_id,
                        to_stage_id=division.defect_stage_id,
                        action_type=ActionType.UPDATE,
                        action_by=g.user_id,
                        notes=action_note
                    )

                    if not flow_history:
                        db.session.rollback()
                        return None

            return division

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"更新分工状态时发生错误: {str(e)}")

    @staticmethod
    def send_division_reminder(division_id: int, reminder_by: int, message: str) -> bool:
        """发送分工跟催"""
        try:
            # 验证所有ID的有效性
            if not DefectSolutionDivisionService.validate_division_exists(division_id):
                raise ValueError(f"分工ID {division_id} 不存在")
            if not DefectService.validate_user_exists(reminder_by):
                raise ValueError(f"提醒人ID {reminder_by} 不存在")

            division = DefectSolutionDivision.query.get(division_id)
            if not division:
                return False

            # 更新分工的跟催信息
            division.reminder_count += 1
            division.last_reminder_time = datetime.now()
            division.updated_time = datetime.now()

            # 创建跟催记录
            stage = DefectStage.query.get(division.defect_stage_id)
            if stage:
                reminder = DefectReminderService.create_reminder(
                    defect_id=stage.defect_id,
                    defect_stage_id=division.defect_stage_id,
                    reminder_type=ReminderType.SOLUTION,
                    target_id=division_id,
                    reminder_by=reminder_by,
                    reminder_message=message
                )

                current_app.logger.debug(f'发送跟催成功！')

                if not reminder:
                    db.session.rollback()
                    return False

                # 记录消息通知
                MessageCreator.create_urge_message(
                    defect_id=stage.defect_id,
                    target_user_id=division.assignee_id,
                    operator_id=reminder_by,
                    urge_type='solution_measures',
                    reason=message
                )

                email_content = DefectEmailService.get_urge_email_content(
                    defect=stage.defect,
                    urge_type='solution_measures',
                    urge_reason=message,
                    urger_id=reminder_by  # 用户ID
                )
                email_subject = DefectEmailService.get_email_subject_by_message_type(
                    defect=stage.defect,
                    message_type=MessageTypes.URGE_SOLUTION_MEASURES
                )
                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=division.assignee_id,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title=email_subject
                                                                    )

            return True

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"发送分工跟催时发生错误: {str(e)}")


class DefectStageCollaboratorService:
    """阶段协作者服务类：开发人员定位 及 开发人员编写解决措施 涉及的人员记录到服务——一个人员记录一次"""

    @staticmethod
    def add_collaborator(defect_stage_id: int, user_id: int,
                         role: CollaboratorRole = CollaboratorRole.COLLABORATOR,
                         locale_invitation_id: int = None,
                         solution_division_id: int = None) -> Optional[DefectStageCollaborator]:
        """添加阶段协作者"""
        try:
            # 验证所有ID的有效性
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")
            if locale_invitation_id and not DefectLocaleInvitationService.validate_invitation_exists(
                    locale_invitation_id):
                raise ValueError(f"邀请ID {locale_invitation_id} 不存在")
            if solution_division_id and not DefectSolutionDivisionService.validate_division_exists(
                    solution_division_id):
                raise ValueError(f"分工ID {solution_division_id} 不存在")

            # 检查是否已存在
            existing = DefectStageCollaborator.query.filter_by(
                defect_stage_id=defect_stage_id, user_id=user_id).first()

            if existing:
                return existing

            collaborator = DefectStageCollaborator(
                defect_stage_id=defect_stage_id,
                user_id=user_id,
                role=role,
                locale_invitation_id=locale_invitation_id,
                solution_division_id=solution_division_id,
                joined_time=datetime.now()
            )

            db.session.add(collaborator)
            db.session.flush()
            return collaborator

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"添加协作者时发生错误: {str(e)}")

    @staticmethod
    def remove_collaborator(defect_stage_id: int, user_id: int) -> bool:
        """移除阶段协作者"""
        try:
            # 验证所有ID的有效性
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            collaborator = DefectStageCollaborator.query.filter_by(
                defect_stage_id=defect_stage_id, user_id=user_id).first()

            if not collaborator:
                return False

            collaborator.left_time = datetime.now()
            return True

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"移除协作者时发生错误: {str(e)}")

    @staticmethod
    def get_collaborators(defect_stage_id: int) -> List[DefectStageCollaborator]:
        """获取阶段的所有协作者"""
        try:
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                return []

            return DefectStageCollaborator.query.filter_by(
                defect_stage_id=defect_stage_id, left_time=None).all()
        except Exception as e:
            raise RuntimeError(f"获取协作者列表时发生错误: {str(e)}")


class DefectStageDataService:
    """阶段数据服务类"""

    @staticmethod
    def get_defect_description_data(defect_id: int) -> List[Dict]:
        """
        根据缺陷ID获取问题描述阶段的阶段数据，包含关联的阶段状态信息

        参数:
            defect_id: 缺陷ID

        返回:
            包含问题描述数据和阶段状态的字典列表
        """
        try:
            # 获取问题描述阶段ID、新增 draft_creation （草稿创建阶段）
            stage_ids = DefectStageService.get_stage_ids_by_type(
                defect_id, "defect_description")
            if not stage_ids:
                stage_ids = DefectStageService.get_stage_ids_by_type(
                    defect_id, "draft_creation")
                if not stage_ids:
                    return []
            current_app.logger.info(
                f'【get_defect_description_data】 defect_description 或 draft_creation阶段对应的 stage_ids：{stage_ids}')
            # 使用关联查询获取阶段数据和对应的阶段状态
            query = db.session.query(
                DefectStageData,
                DefectStage.status
            ).join(
                DefectStage,
                DefectStageData.defect_stage_id == DefectStage.id
            ).filter(
                DefectStageData.defect_stage_id.in_([stage_ids[0]]),
                DefectStageData.data_type == DataType.DEFECT_DESCRIPTION,
                DefectStageData.is_current == True
            )

            results = query.all()

            # 构建返回结果
            result_list = []
            for stage_data, stage_status in results:
                data_dict = stage_data.to_dict()
                data_dict['stage_status'] = stage_status if stage_status else None
                result_list.append(data_dict)

            return result_list

        except Exception as e:
            current_app.logger.error(
                f"获取问题描述阶段数据时发生错误: {str(e)}")
            raise RuntimeError(
                f"获取问题描述阶段数据时发生错误: {str(e)}")

    @staticmethod
    def get_locale_invitation_data(defect_id: int, is_simplified=False) -> List[Dict]:
        """
        根据缺陷ID获取已完成、已取消定位邀请、已驳回的阶段数据，包含邀请人、被邀请人信息和邀请状态
        获取以下状态的数据：
        InvitationStatus.COMPLETED,
        InvitationStatus.CANCELLED,
        InvitationStatus.REJECTED,
        InvitationStatus.PENDING,  暂存的数据

        参数:
            defect_id: 缺陷ID

        返回:
            包含邀请信息的阶段数据字典列表（新增status字段）
        """
        try:
            # 获取原因分析阶段ID
            stage_ids = DefectStageService.get_stage_ids_by_type(
                defect_id, "cause_analysis")
            current_app.logger.info(
                f'【get_locale_invitation_data】 cause_analysis 阶段对应的 stage_ids：{stage_ids}')
            if not stage_ids:
                return []

            # 使用关联查询获取阶段数据和对应的邀请信息（增加status字段）
            query = db.session.query(
                DefectStageData,
                DefectLocaleInvitation.inviter_id,
                DefectLocaleInvitation.invitee_id,
                DefectLocaleInvitation.status  # 新增查询字段
            ).join(
                DefectLocaleInvitation,
                DefectStageData.locale_invitation_id == DefectLocaleInvitation.id
            ).filter(
                DefectStageData.defect_stage_id.in_(stage_ids),
                DefectStageData.data_type == DataType.CAUSE_ANALYSIS,
                DefectStageData.is_current == True,
                DefectLocaleInvitation.status.in_([
                    InvitationStatus.COMPLETED,
                    InvitationStatus.CANCELLED,
                    InvitationStatus.REJECTED,
                    InvitationStatus.PENDING
                ])
            )

            results = query.all()

            # 构建返回结果（增加status字段）
            result_list = []
            for stage_data, inviter_id, invitee_id, status in results:  # 解包新增字段
                data_dict = stage_data.to_dict()
                data_dict['inviter_id'] = inviter_id
                data_dict['invitee_id'] = invitee_id
                data_dict['status'] = status  # 新增status字段
                result_list.append(data_dict)
            return result_list

        except Exception as e:
            current_app.logger.error(
                f"获取已完成或已取消定位邀请的阶段数据时发生错误: {str(e)}")
            raise RuntimeError(
                f"获取已完成或已取消定位邀请的阶段数据时发生错误: {str(e)}")

    @staticmethod
    def filter_completed_invitations(invitation_data: List[Dict]) -> List[Dict]:
        """
        从邀请数据列表中筛选出状态为 COMPLETED 的项

        该函数接收 get_locale_invitation_data 方法返回的数据列表，
        并筛选出其中状态为 InvitationStatus.COMPLETED 的数据项。

        参数:
            invitation_data: get_locale_invitation_data 返回的邀请数据列表，
                             每个字典应包含 'status' 字段

        返回:
            仅包含状态为 COMPLETED 的邀请数据列表，保持原始数据结构不变

        示例:
            # 获取原始邀请数据
            raw_data = DefectService.get_locale_invitation_data(defect_id=123)

            # 筛选已完成状态的邀请
            completed_data = filter_completed_invitations(raw_data)
        """
        # 使用列表推导式筛选状态为 COMPLETED 的项
        # 使用 get() 方法安全地获取状态值，避免因缺少键而抛出 KeyError
        return [
            item for item in invitation_data
            if item.get('status') == 'InvitationStatus.COMPLETED'
        ]

    @staticmethod
    def get_solution_division_data(defect_id: int) -> List[Dict]:
        """
        根据缺陷ID获取已完成、已取消及驳回的解决方案分工的阶段数据，包含分配人、被分配人信息和分工状态
        获取以下状态的数据：
        InvitationStatus.COMPLETED,
        InvitationStatus.CANCELLED, （这种状态的数据 对应解决措施 不存在）
        InvitationStatus.REJECTED
        InvitationStatus.PENDING 暂存

        参数:
            defect_id: 缺陷ID

        返回:
            包含分工信息的阶段数据字典列表（新增status字段）
        """
        try:
            # 获取解决方案阶段ID
            stage_ids = DefectStageService.get_stage_ids_by_type(
                defect_id, "developer_solution")
            current_app.logger.info(
                f'【get_solution_division_data】 developer_solution 阶段对应的 stage_ids：{stage_ids}')
            if not stage_ids:
                return []

            # 修改查询：增加DefectSolutionDivision.status字段
            query = db.session.query(
                DefectStageData,
                DefectSolutionDivision.assign_by_id,
                DefectSolutionDivision.assignee_id,  # 修改人
                DefectSolutionDivision.status,  # 状态
                DefectSolutionDivision.module,  # 模块
                DefectSolutionDivision.version,  # 版本
                DefectSolutionDivision.due_date,  # 完成时间
                DefectSolutionDivision.action_plan,  # 计划执行措施
            ).join(
                DefectSolutionDivision,
                DefectStageData.solution_division_id == DefectSolutionDivision.id
            ).filter(
                DefectStageData.defect_stage_id.in_(stage_ids),
                DefectStageData.data_type == DataType.SOLUTION,
                DefectStageData.is_current == True,
                DefectSolutionDivision.status.in_([
                    InvitationStatus.COMPLETED,
                    InvitationStatus.CANCELLED,
                    InvitationStatus.REJECTED,
                    InvitationStatus.PENDING
                ])
            )
            results = query.all()

            # 构建返回结果（增加status字段和新增字段）
            result_list = []
            for (stage_data, assign_by_id, assignee_id, status,
                 module, version, due_date, action_plan) in results:  # 解包所有字段
                data_dict = stage_data.to_dict()
                data_dict['assign_by_id'] = assign_by_id
                data_dict['assignee_id'] = assignee_id
                data_dict['status'] = status
                data_dict['module'] = module  # 新增模块字段
                data_dict['version'] = version  # 新增版本字段
                data_dict['due_date'] = due_date  # 新增完成时间字段
                data_dict['action_plan'] = action_plan  # 新增计划执行措施字段
                result_list.append(data_dict)

            return result_list

        except Exception as e:
            current_app.logger.error(
                f"获取已完成或已取消解决方案分工的阶段数据时发生错误: {str(e)}")
            raise RuntimeError(
                f"获取已完成或已取消解决方案分工的阶段数据时发生错误: {str(e)}")

    @staticmethod
    def filter_completed_divisions(division_data: List[Dict]) -> List[Dict]:
        """
        从解决方案分工数据中筛选出状态为 COMPLETED 的项

        参数:
            division_data: 解决方案分工数据列表，每个元素应包含 status 字段

        返回:
            只包含状态为 COMPLETED 的分工数据列表
        """
        # 筛选出状态为 COMPLETED 的项
        return [
            item for item in division_data
            if item.get('status') == 'InvitationStatus.COMPLETED'
        ]

    @staticmethod
    def get_test_result_data(defect_id: int) -> List[Dict]:
        """
        根据缺陷ID获取测试回归阶段的阶段数据，包含关联的阶段状态信息

        参数:
            defect_id: 缺陷ID

        返回:
            包含测试回归数据和阶段状态的字典列表
        """
        try:
            # 获取测试回归阶段ID
            stage_ids = DefectStageService.get_stage_ids_by_type(
                defect_id, DataType.TEST_RESULT.value)  # 'tester_regression'
            current_app.logger.info(
                f'【get_test_result_data】 tester_regression 阶段对应的 stage_ids：{stage_ids}')
            if not stage_ids:
                return []

            # 使用关联查询获取阶段数据和对应的阶段状态
            query = db.session.query(
                DefectStageData,
                DefectStage.status
            ).join(
                DefectStage,
                DefectStageData.defect_stage_id == DefectStage.id
            ).filter(
                DefectStageData.defect_stage_id.in_(stage_ids),
                DefectStageData.data_type == DataType.TEST_RESULT,
                DefectStageData.is_current == True,
            ).order_by(DefectStageData.id.desc())
            results = query.all()

            # 构建返回结果
            result_list = []
            for stage_data, stage_status in results:
                data_dict = stage_data.to_dict()
                data_dict['stage_status'] = stage_status if stage_status else None
                result_list.append(data_dict)

            return result_list

        except Exception as e:
            current_app.logger.error(
                f"获取测试回归阶段数据时发生错误: {str(e)}")
            raise RuntimeError(
                f"获取测试回归阶段数据时发生错误: {str(e)}")

    @staticmethod
    def get_stage_data_by_type(defect_id: int, stage_data_type: DataType) -> List[Dict]:
        """
        根据缺陷ID和数据类型获取对应的阶段数据，包含关联的阶段状态信息——供简化版2使用，获取 原因分析和解决措施阶段的数据

        参数:
            defect_id: 缺陷ID
            stage_data_type: DataType数据类型枚举值

        返回:
            包含阶段数据和阶段状态的字典列表
        """
        try:
            # 获取指定数据类型对应的阶段ID
            stage_ids = DefectStageService.get_stage_ids_by_type(
                defect_id, stage_data_type.value)
            current_app.logger.info(
                f'【get_stage_data_by_type】 {stage_data_type.value} 阶段对应的 stage_ids：{stage_ids}')
            if not stage_ids:
                return []

            # 使用关联查询获取阶段数据和对应的阶段状态
            query = db.session.query(
                DefectStageData,
                DefectStage.status
            ).join(
                DefectStage,
                DefectStageData.defect_stage_id == DefectStage.id
            ).filter(
                DefectStageData.defect_stage_id.in_(stage_ids),
                DefectStageData.data_type == stage_data_type,
                DefectStageData.is_current == True
            )

            results = query.all()

            # 构建返回结果
            result_list = []
            for stage_data, stage_status in results:
                data_dict = stage_data.to_dict()
                data_dict['stage_status'] = stage_status if stage_status else None
                result_list.append(data_dict)

            return result_list

        except Exception as e:
            current_app.logger.error(
                f"获取{stage_data_type.value}阶段数据时发生错误: {str(e)}")
            raise RuntimeError(
                f"获取{stage_data_type.value}阶段数据时发生错误: {str(e)}")

    @staticmethod
    def get_all_stage_data_by_criteria(
            defect_stage_id: int,
            data_type: DataType = None,
            is_current: bool = None,
            submitted_by: int = None  # 新增筛选字段
    ) -> List[DefectStageData]:
        """
        根据条件获取所有匹配的阶段数据记录

        Args:
            defect_stage_id: 缺陷阶段ID
            data_type: 数据类型枚举，可选
            is_current: 是否当前最新数据，可选
            submitted_by: 提交人ID，可选  # 新增参数说明

        Returns:
            List[DefectStageData]: 符合条件的阶段数据对象列表

        Raises:
            RuntimeError: 查询过程中发生错误
        """
        try:
            # 构建基础查询条件
            query = DefectStageData.query.filter(
                DefectStageData.defect_stage_id == defect_stage_id
            )

            # 添加可选条件
            if data_type is not None:
                query = query.filter(DefectStageData.data_type == data_type)

            if is_current is not None:
                query = query.filter(DefectStageData.is_current == is_current)

            if submitted_by is not None:  # 新增筛选条件
                query = query.filter(DefectStageData.submitter_id == submitted_by)

            # 使用options加载相关关联数据
            query = query.options(
                db.joinedload(DefectStageData.defect_stage),  # 加载关联的阶段信息
                db.joinedload(DefectStageData.invitation),  # 加载关联的邀请信息
                db.joinedload(DefectStageData.division),  # 加载关联的分工信息
                db.joinedload(DefectStageData.submitter)  # 加载提交人信息
            )

            # 返回所有查询结果
            return query.all()
        except Exception as e:
            raise RuntimeError(f"根据条件获取阶段数据列表时发生错误: {str(e)}")

    @staticmethod
    def get_stage_data_by_id(stage_data_id: int) -> Optional[DefectStageData]:
        """根据ID获取阶段详情"""
        try:
            # 使用options加载相关关联数据
            return DefectStageData.query.options(
                db.joinedload(DefectStageData.defect_stage),  # 加载关联的阶段信息
                db.joinedload(DefectStageData.invitation),  # 加载关联的邀请信息
                db.joinedload(DefectStageData.division),  # 加载关联的分工信息
                db.joinedload(DefectStageData.submitter)  # 加载提交人信息
            ).get(stage_data_id)
        except Exception as e:
            raise RuntimeError(f"获取阶段数据信息时发生错误: {str(e)}")

    @staticmethod
    def create_defect_description_data(defect_stage_id: int, title: str,
                                       description: str, severity: str, defect_reproducibility: str,
                                       submitted_by: int) -> Optional[DefectStageData]:
        """创建问题描述阶段数据"""
        try:
            # 验证所有ID的有效性
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            if not DefectService.validate_user_exists(submitted_by):
                raise ValueError(f"提交人ID {submitted_by} 不存在")

            # 创建问题描述数据
            stage_data = DefectStageData(
                defect_stage_id=defect_stage_id,
                data_type=DataType.DEFECT_DESCRIPTION,
                content={
                    "title": title,
                    "description": description,
                    "severity": severity,
                    "defect_reproducibility": defect_reproducibility
                },
                submitted_by=submitted_by,
                is_current=True,
                created_time=datetime.now(),
                updated_time=datetime.now()
            )

            db.session.add(stage_data)
            db.session.flush()

            return stage_data

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"创建问题描述数据时发生错误: {str(e)}")

    @staticmethod
    def submit_stage_data(defect_stage_id: int, data_type: DataType, content: dict,
                          submitted_by: int, is_draft: bool = False,
                          locale_invitation_id: int = None, solution_division_id: int = None, ai_suggestion:str = None, ai_score:int = None) -> tuple[Optional[
        DefectStageData],str]:
        """提交阶段数据"""
        try:
            # 验证所有ID的有效性
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            if not DefectService.validate_user_exists(submitted_by):
                raise ValueError(f"提交人ID {submitted_by} 不存在")
            if locale_invitation_id and not DefectLocaleInvitationService.validate_invitation_exists(
                    locale_invitation_id):
                raise ValueError(f"邀请ID {locale_invitation_id} 不存在")
            if solution_division_id and not DefectSolutionDivisionService.validate_division_exists(
                    solution_division_id):
                raise ValueError(f"分工ID {solution_division_id} 不存在")

            current_app.logger.debug(
                f'将之前数据标记为非最新（如果有）... defect_stage_id: {defect_stage_id}, DataType(data_type): {DataType(data_type)}, data_type: {data_type}  data_type.value: {data_type.value}')
            # 将之前数据标记为非最新（如果有）
            # 构建基础查询条件
            query_filters = {
                'defect_stage_id': defect_stage_id,
                'data_type': data_type,
                'is_current': True,
                # 'submitted_by': submitted_by # 对于复制的缺陷单或者指定人员重新测试，缺陷描述的提交人与重新提交人不同，不需要该条件以确保数据的 is_current 只有一个
            }
            current_stage = DefectStage.query.get(defect_stage_id)
            # 如果数据类型不是缺陷描述或回归测试，则添加 submitted_by 条件
            if current_stage.defect.defect_type!='simplified2':
                if data_type != DataType.DEFECT_DESCRIPTION or data_type != DataType.TEST_RESULT: #确保数据的 is_current 只有一个
                    query_filters['submitted_by'] = submitted_by

            # 动态添加过滤条件
            if locale_invitation_id:
                query_filters['locale_invitation_id'] = locale_invitation_id  # 新增条件
            if solution_division_id:
                query_filters['solution_division_id'] = solution_division_id  # 新增条件


            is_change = ""
            stage_data = DefectStageData.query.filter_by(**query_filters).first()
            if stage_data is not None:
                if data_type == DataType.DEFECT_DESCRIPTION:
                    if stage_data.content['description'] != content['description']:
                        is_change = "1"
                elif data_type == DataType.CAUSE_ANALYSIS:
                    if stage_data.content['analyses'] != content['analyses']:
                        is_change = "1"
                elif data_type == DataType.SOLUTION:
                    if stage_data.content['solutions'] != content['solutions']:
                        is_change = "1"
                elif data_type == DataType.TEST_RESULT:
                    if stage_data.content['description'] != content['description']:
                        is_change = "1"

            # 执行更新操作
            DefectStageData.query.filter_by(**query_filters).update(
                {"is_current": False})  # 确保对应 data_type（数据类型） 的只有一个是当前使用的，其他为历史数据
            # 创建新数据
            stage_data = DefectStageData(
                defect_stage_id=defect_stage_id,
                data_type=data_type,
                locale_invitation_id=locale_invitation_id,
                solution_division_id=solution_division_id,
                content=content,
                is_draft=is_draft,
                submitted_by=submitted_by,
                is_current=True,
                created_time=datetime.now(),
                updated_time=datetime.now(),
                ai_suggestion=ai_suggestion,
                ai_score=ai_score
            )

            db.session.add(stage_data)
            db.session.flush()

            # 记录流程历史
            action_type = ActionType.UPDATE
            if data_type == DataType.SOLUTION:
                action_type = ActionType.SUBMIT_SOLUTION

            show_data_type = data_type_map.get(data_type, '')
            current_app.logger.debug(f'data_type 提交的数据类型 {data_type}')

            stage = DefectStage.query.get(defect_stage_id)
            addition_note = ''
            if is_draft:
                addition_note = '(暂存)'

            if stage:
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=stage.defect_id,
                    to_stage_id=defect_stage_id,
                    action_type=action_type,
                    action_by=submitted_by,
                    notes=f"提交 {show_data_type} 数据 {addition_note}"
                )

                if not flow_history:
                    db.session.rollback()
                    return None,is_change

            return stage_data,is_change

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"提交阶段数据时发生错误: {str(e)}")

    @staticmethod
    def evaluate_stage_data(stage_data_id: int, ai_suggestion: str, ai_score: int,
                            evaluation_method: EvaluationMethod = EvaluationMethod.AUTO) -> Optional[DefectStageData]:
        """评估阶段数据（AI或手动评估）"""
        try:
            stage_data = DefectStageData.query.get(stage_data_id)
            if not stage_data:
                return None

            stage_data.ai_suggestion = ai_suggestion
            stage_data.ai_score = ai_score
            stage_data.evaluation_method = evaluation_method
            stage_data.ai_evaluation_time = datetime.now()
            stage_data.updated_time = datetime.now()

            return stage_data

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"评估阶段数据时发生错误: {str(e)}")

    @staticmethod
    def combine_stage_data(defect_id:int,defect_stage_id: int,
                           source_data_ids: List[int],ai_suggestion:str,ai_score:int) -> Optional[DefectStageData]:
        """合并多个阶段数据"""
        try:
            # 验证所有ID的有效性
            print(f"combine_stage_data:{defect_stage_id}")
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            combine_record =DefectStageCombineRecord.query.filter(DefectStageCombineRecord.defect_stage_id==defect_stage_id).first()
            if  combine_record:
                combine_record.ai_suggestion = ai_suggestion
                combine_record.ai_score = ai_score
                combine_record.source_data_ids = source_data_ids
                combine_record.combine_time = datetime.now()
            else:
                # 创建合并记录
                combine_record = DefectStageCombineRecord(
                    defect_id=defect_id,
                    defect_stage_id=defect_stage_id,
                    source_data_ids=source_data_ids,
                    ai_suggestion = ai_suggestion,
                    ai_score = ai_score,
                    combine_time=datetime.now()
                )
                db.session.add(combine_record)
                db.session.flush()
            return combine_record
        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"合并阶段数据时发生错误: {str(e)}")


class DefectReminderService:
    """跟催服务类"""

    @staticmethod
    def create_reminder(defect_id: int, defect_stage_id: int, reminder_type: ReminderType,
                        target_id: int, reminder_by: int, reminder_message: str) -> Optional[DefectReminder]:
        """
        创建跟催记录

        target_id：跟催目标ID（邀请ID或分工ID）

        """
        try:
            # 验证所有ID的有效性
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            if not DefectService.validate_user_exists(reminder_by):
                raise ValueError(f"提醒人ID {reminder_by} 不存在")
            remind_to_user = None
            if reminder_type == ReminderType.ANALYSIS:
                locale_invitation = DefectLocaleInvitation.query.filter_by(id=target_id).first()
                if not locale_invitation:
                    raise ValueError(f"定位分析邀请记录 {target_id} 不存在")
                else:
                    remind_to_user = User.get_user_by_id(locale_invitation.invitee_id)
                    if not remind_to_user:
                        raise ValueError(f"定位分析被邀请的用户 {locale_invitation.invitee_id} 不存在")
            elif reminder_type == ReminderType.SOLUTION:
                solution_division = DefectSolutionDivision.query.filter_by(id=target_id).first()
                if not solution_division:
                    raise ValueError(f"解决措施分工记录 {target_id} 不存在")
                else:
                    remind_to_user = User.get_user_by_id(solution_division.assignee_id)
                    if not remind_to_user:
                        raise ValueError(f"定位分析被邀请的用户 {solution_division.assignee_id} 不存在")

            reminder = DefectReminder(
                defect_id=defect_id,
                defect_stage_id=defect_stage_id,
                reminder_type=reminder_type,
                target_id=target_id,
                reminder_by=reminder_by,
                reminder_message=reminder_message,
                reminder_time=datetime.now(),
                reminder_status=ReminderStatus.SENT,
                created_time=datetime.now(),
                updated_time=datetime.now()
            )

            db.session.add(reminder)
            db.session.flush()

            # 记录流程历史
            flow_history = DefectFlowHistoryService.record_flow(
                defect_id=defect_id,
                to_stage_id=defect_stage_id,
                action_type=ActionType.REMIND,
                action_by=reminder_by,
                notes=f"给 {remind_to_user.real_name}/{remind_to_user.email} 发送 {reminder_type.value} 跟催: {reminder_message}"
            )

            if not flow_history:
                db.session.rollback()
                return None

            return reminder

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"创建跟催记录时发生错误: {str(e)}")

    @staticmethod
    def update_reminder_status(reminder_id: int, status: ReminderStatus,
                               action_notes: str = None) -> Optional[DefectReminder]:
        """更新跟催状态"""
        try:
            reminder = DefectReminder.query.get(reminder_id)
            if not reminder:
                return None

            reminder.reminder_status = status
            if status == ReminderStatus.VIEWED:
                reminder.updated_time = datetime.now()
            elif status == ReminderStatus.ACTED:
                reminder.action_time = datetime.now()
                reminder.action_notes = action_notes
                reminder.updated_time = datetime.now()

            return reminder

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"更新跟催状态时发生错误: {str(e)}")


class DefectFlowHistoryService:
    """流程历史服务类"""

    @staticmethod
    def record_flow(defect_id: int, to_stage_id: int, action_type: ActionType,
                    action_by: int, from_stage_id: int = None, reminder_id: int = None,
                    notes: str = None,ai_sug_score_id:str=None) -> Optional[DefectFlowHistory]:
        """记录流程历史"""
        try:
            # 验证所有ID的有效性
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectStageService.validate_stage_exists(to_stage_id):
                raise ValueError(f"目标阶段ID {to_stage_id} 不存在")
            if from_stage_id and not DefectStageService.validate_stage_exists(from_stage_id):
                raise ValueError(f"来源阶段ID {from_stage_id} 不存在")
            if not DefectService.validate_user_exists(action_by):
                raise ValueError(f"操作人ID {action_by} 不存在")
            if reminder_id and not DefectReminder.query.get(reminder_id):
                raise ValueError(f"提醒ID {reminder_id} 不存在")

            history = DefectFlowHistory(
                defect_id=defect_id,
                from_stage_id=from_stage_id,
                to_stage_id=to_stage_id,
                action_type=action_type,
                reminder_id=reminder_id,
                action_by=action_by,
                action_time=datetime.now(),
                notes=notes,
                ai_sug_score_id = ai_sug_score_id
            )

            db.session.add(history)
            db.session.flush()
            return history

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"记录流程历史时发生错误: {str(e)}")

    @staticmethod
    def get_flow_history(defect_id: int) -> List[Dict]:
        """获取缺陷的流程历史，包含操作人的 email 和 real_name"""
        try:
            if not DefectService.validate_defect_exists(defect_id):
                return []

            # 使用 joinedload 加载关联的 action_user 关系，并选择特定字段
            history_records = DefectFlowHistory.query.options(
                joinedload(DefectFlowHistory.action_user).load_only(User.email, User.real_name)
            ).filter_by(defect_id=defect_id).order_by(
                DefectFlowHistory.id.asc()
            ).all()

            # 将记录转换为字典并添加用户信息
            result = []
            for record in history_records:
                if record.notes.startswith('定位分析邀请状态更新') or record.notes.startswith('解决措施分工状态更新'):
                    continue
                # 手动构建字典，避免使用 to_dict() 方法
                record_dict = {
                    'id': record.id,
                    'defect_id': record.defect_id,
                    'from_stage_id': record.from_stage_id,
                    'to_stage_id': record.to_stage_id,
                    'action_type': getattr(record.action_type, 'value', record.action_type),  # 安全获取值
                    'reminder_id': record.reminder_id,
                    'action_by': record.action_by,
                    'action_time': record.action_time.isoformat() if record.action_time else None,
                    'notes': record.notes,
                    'ai_sug_score_id': record.ai_sug_score_id,
                }
                # 添加操作人的 email 、 real_name、部门
                if record.action_user:
                    record_dict['action_by_email'] = record.action_user.email
                    record_dict['action_by_real_name'] = record.action_user.real_name
                    record_dict['action_by_dept'] = record.action_user.dept # 部门
                    record_dict['position'] = record.action_user.position  # 职位
                else:
                    record_dict['action_by_email'] = None
                    record_dict['action_by_real_name'] = None
                    record_dict['action_by_dept'] = None
                    record_dict['position'] = None

                result.append(record_dict)

            return result
        except Exception as e:
            raise RuntimeError(f"获取流程历史时发生错误: {str(e)}")


class DefectRejectionService:
    """驳回服务类"""

    @staticmethod
    def record_rejection(defect_id: int, defect_stage_id: int, rejection_type: RejectionType,
                         rejected_by: int, reason: str, previous_stage_id: int = None,
                         invitation_id: int = None, stage_data_id: int = None) -> Optional[DefectRejection]:
        """记录驳回"""
        try:
            # 验证所有ID的有效性
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            if not DefectService.validate_user_exists(rejected_by):
                raise ValueError(f"驳回人ID {rejected_by} 不存在")
            if previous_stage_id and not DefectStageService.validate_stage_exists(previous_stage_id):
                raise ValueError(f"前一阶段ID {previous_stage_id} 不存在")
            if invitation_id and not DefectLocaleInvitationService.validate_invitation_exists(invitation_id):
                raise ValueError(f"邀请ID {invitation_id} 不存在")
            if stage_data_id and not DefectStageData.query.get(stage_data_id):
                raise ValueError(f"阶段数据ID {stage_data_id} 不存在")

            rejection = DefectRejection(
                defect_id=defect_id,
                defect_stage_id=defect_stage_id,
                rejection_type=rejection_type,
                invitation_id=invitation_id,
                stage_data_id=stage_data_id,
                rejected_by=rejected_by,
                reason=reason,
                previous_stage_id=previous_stage_id,
                created_time=datetime.now()
            )

            db.session.add(rejection)
            db.session.flush()
            return rejection

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"记录驳回时发生错误: {str(e)}")

    @staticmethod
    def get_rejections(defect_id: int) -> List[DefectRejection]:
        """获取缺陷的所有驳回记录"""
        try:
            if not DefectService.validate_defect_exists(defect_id):
                return []

            return DefectRejection.query.filter_by(defect_id=defect_id).order_by(
                DefectRejection.created_time.desc()).all()
        except Exception as e:
            raise RuntimeError(f"获取驳回记录时发生错误: {str(e)}")


class DefectWorkflowService:
    """缺陷工作流服务类，处理完整的缺陷流程"""
    @staticmethod
    def get_current_stage_name(defect:Defect) -> str:
        """
        获取缺陷单当前阶段的名称
        """
        current_stage = DefectStageService.get_stage_by_id(defect.current_stage_id)
        stage_types_dict = DefectService.get_defect_stage_types_dict()
        current_stage_name = stage_types_dict.get(current_stage.stage_type)
        return current_stage_name
    @staticmethod
    def get_project_manager_id(defect:Defect) -> int:
        """根据缺陷单获取对应的项目管理员ID"""
        # 根据实际情况实现，查询项目-用户关联表
        ret_user_id = None
        user_ids = ProjectMemberService.get_user_ids_by_role(defect.project_id, defect.version_id, 'project_admin')
        if user_ids:
            ret_user_id = user_ids[0]
        return ret_user_id  # 项目管理员的用户ID

    @staticmethod
    def get_test_manager_id(defect:Defect) -> int:
        """根据缺陷单获取测试经理ID（根据实际情况实现）"""
        # 根据实际情况实现，查询项目-用户关联表
        ret_user_id = None
        user_ids = ProjectMemberService.get_user_ids_by_role(defect.project_id, defect.version_id, 'test_manager')
        if user_ids:
            ret_user_id = user_ids[0]
        return ret_user_id  # 测试经理的用户ID

    @staticmethod
    def get_dev_manager_id(defect:Defect):
        """根据缺陷单获取开发主管ID（根据实际情况实现）"""
        # 根据实际情况实现，查询项目-用户关联表
        ret_user_id = None
        user_ids = ProjectMemberService.get_user_ids_by_role(defect.project_id, defect.version_id, 'dev_manager')
        if user_ids:
            ret_user_id = user_ids[0]
        return ret_user_id  # 测试经理的用户ID


    @staticmethod
    def get_test_manager_id_with_validation(defect, is_raise_exception=True):
        """
        获取缺陷对应的测试经理ID，并验证配置是否存在

        Args:
            defect: 缺陷对象，需要包含project_id和version_id属性
            is_raise_exception: 是否在未配置测试经理时抛出异常，默认为True

        Returns:
            str or None: 测试经理ID，如果未配置且is_raise_exception=False则返回None

        Raises:
            ValueError: 当未配置测试经理且is_raise_exception=True时抛出异常
        """
        test_manager_id = DefectWorkflowService.get_test_manager_id(defect)
        current_app.logger.debug(f'project_id:.............. {defect.project_id}     version_id:.............. {defect.version_id} ')
        current_app.logger.debug(f'test_manager_id:.............. {test_manager_id}')
        if test_manager_id:
            return test_manager_id

        # 如果未配置测试经理
        project_version_name = DefectService.get_project_version_name(defect)

        message = f" {project_version_name} 未配置测试经理。"
        current_app.logger.error(message)

        if is_raise_exception:
            raise ValueError(message)
        else:
            return None

    @staticmethod
    def get_dev_manager_id_with_validation(defect, is_raise_exception=True):
        """
        获取缺陷对应的开发主管ID，并验证配置是否存在

        Args:
            defect: 缺陷对象，需要包含project_id和version_id属性
            is_raise_exception: 是否在未配置开发主管时抛出异常，默认为True

        Returns:
            str or None: 开发主管ID，如果未配置且is_raise_exception=False则返回None

        Raises:
            ValueError: 当未配置开发主管且is_raise_exception=True时抛出异常
        """
        dev_manager_id = DefectWorkflowService.get_dev_manager_id(defect)

        if dev_manager_id:
            return dev_manager_id

        # 如果未配置开发主管
        project_version_name = DefectService.get_project_version_name(defect)

        message = f" {project_version_name} 未配置开发主管。"
        current_app.logger.error(message)

        if is_raise_exception:
            raise ValueError(message)
        else:
            return None

    @staticmethod
    def submit_defect_description(title: str, description: str, severity: str, defect_reproducibility: str,
                                  creator_id: int, version_id: int = None, project_id: int = None,
                                  defect_id: int = None, is_draft_flag: bool = True) -> tuple[Optional[Defect],str]:
        """提交缺陷描述（支持从草稿提交或直接创建问题单时的提交），保存到 DefectStageData 表中
           将根据 is_draft_flag 确认是否需要立即创建 “测试经理审核描述”阶段，更新当前defect的 current_stage_id
           不执行 commit，在Route中执行
        """
        try:
            if is_draft_flag:
                current_app.logger.info('提交缺陷描述（草稿），不走给测试经理审核...')
            else:
                current_app.logger.info('提交缺陷描述，将走给测试经理审核...')

            # 验证creator_id是否存在
            if not DefectService.validate_user_exists(creator_id):
                raise ValueError(f"创建者ID {creator_id} 不存在")

            current_app.logger.debug(f'检查是否传入了defect.id: {defect_id}')
            defect = None
            current_stage = None
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")

            defect = Defect.query.get(defect_id)
            if not defect:
                current_app.logger.error(f'根据id获取缺陷失败: {defect_id}')
                return None, ""

            defect_change = ""
            if defect.version_id != version_id or defect.project_id != project_id or defect.defect_reproducibility != defect_reproducibility or defect.severity != severity:
                defect_change = "1"

            # 更新缺陷信息
            defect.title = title
            defect.description = description
            defect.severity = severity
            defect.defect_reproducibility = defect_reproducibility
            defect.version_id = version_id
            defect.project_id = project_id
            defect.updated_time = datetime.now()

            # 关键修改：在更新defect后立即flush
            db.session.flush()

            if defect.defect_type == 'simplified' or defect.defect_type == 'simplified2':
                current_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'defect_description')
            else:
                # 获取当前阶段（问题描述阶段）
                current_stage = DefectStage.query.get(defect.current_stage_id)

            if not current_stage:
                raise ValueError(f"缺陷 {defect_id} 的当前阶段不存在")

            # 创建问题描述阶段数据
            current_app.logger.debug(f'执行 submit_stage_data for defect_description : {defect_id}')
            defect_description_data, is_change = DefectStageDataService.submit_stage_data(
                defect_stage_id=current_stage.id,
                data_type=DataType.DEFECT_DESCRIPTION,
                content={
                    "title": title,
                    "description": description,
                    "severity": severity,
                    "defect_reproducibility": defect_reproducibility
                },
                submitted_by=creator_id,
                is_draft=is_draft_flag
            )

            if defect_change != "" or is_change != "":
                is_change = "1"

            if not is_draft_flag:
                current_stage.status = "StageStatus.EVALUATING"
                # 关键修改：在更新stage后也flush
                db.session.flush()

            if not defect_description_data:
                current_app.logger.error('创建问题描述阶段数据 失败')
                db.session.rollback()
                return None, ""

            current_app.logger.debug(
                '创建问题描述阶段数据成功, defect_description_data_id: {0} '.format(defect_description_data.id))

            # 无论是否是草稿，都需要修改更新时间
            defect.updated_time = datetime.now()
            return defect, is_change

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"提交缺陷描述时发生错误: {str(e)}")

    @staticmethod
    def assign_tester(defect_id, tester_id, current_user_id, reason):
        """
        指定测试人员 重新对缺陷描述进行重写

        参数:
        defect_id: 缺陷ID
        tester_id: 测试人员用户ID
        current_user_id: 当前操作用户ID
        reason: 分配原因
        """
        # 获取缺陷和当前阶段
        defect = Defect.query.get(defect_id)
        if not defect:
            raise ValueError("缺陷单不存在")

        # 检查测试人员是否存在
        tester = User.query.get(tester_id)
        if not tester:
            raise ValueError("测试人员不存在")

        # 获取当前阶段
        current_stage = defect.current_stage
        if not current_stage:
            raise ValueError("缺陷没有当前阶段")

        # 检查当前阶段是否允许分配测试人员
        # 这里假设只有在特定阶段（如开发解决后）才能分配测试人员
        # 根据实际业务逻辑调整
        if current_stage.stage_type not in ['test_manager_review_desc']:
            raise ValueError("当前阶段不允许分配测试人员")

        # 检查测试人员是否已经是当前阶段的负责人
        # if current_stage.assigned_to == tester_id:
        #     raise ValueError("该测试人员已经是当前阶段的负责人")

        # 更新当前阶段的负责人
        # 与驳回类似：需将缺陷的当前阶段设置为前一阶段(将前一阶段的状态设置为 PENDING_UPDATE
        previous_stage = DefectStage.query.get(current_stage.previous_stage_id)
        if not previous_stage:
            # 如果没有前一阶段，则不能驳回，只能关闭或作其他处理
            raise ValueError("无法指定，没有前一阶段——缺陷描述阶段可退回")

        defect.current_stage_id = previous_stage.id
        previous_stage.status = StageStatus.PENDING_UPDATE
        previous_assignee = previous_stage.assigned_to # 从之前的阶段获取被分配人
        previous_stage.assigned_to = tester_id # 设置为本次 指定测试人员
        defect.updated_time = datetime.now()
        previous_stage.updated_time = datetime.now()
        current_stage.updated_time = datetime.now()
        extra_params = {'reason': reason} if reason else None
        MessageCreator.create_assign_message(
            defect_id=defect.id,
            assignee_id=tester_id,
            assigner_id=current_user_id,
            assign_type='retest',
            extra_params=extra_params
        )
        email_content = DefectEmailService.get_assign_email_content(
            defect=defect,
            assign_type='retest',
            assigner_id=current_user_id,
            reason=reason
        )
        email_subject = DefectEmailService.get_email_subject_by_message_type(
            defect=defect,
            message_type=MessageTypes.ASSIGN_RETEST
        )
        send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=tester_id,
                                                            admin_user_id=g.admin_user_id,
                                                            current_user_id=g.user_id,
                                                            content=email_content,
                                                            title=email_subject
                                                            )

        # 记录流程历史
        flow_history = DefectFlowHistory(
            defect_id=defect_id,
            from_stage_id=current_stage.id,
            to_stage_id=current_stage.id,  # 阶段未变，只是负责人变更
            action_type=ActionType.TRANSFER,
            action_by=current_user_id,
            action_time=datetime.now(),
            notes=f"分配测试人员: {reason}. 原负责人: {User.get_user_by_id(previous_assignee).real_name}/{User.get_user_by_id(previous_assignee).email}, "
                  f"新负责人: {User.get_user_by_id(tester_id).real_name}/{User.get_user_by_id(tester_id).email}"
        )
        db.session.add(flow_history)

        # 更新缺陷的更新时间
        defect.updated_time = datetime.now()

        # 提交更改
        db.session.commit()

        # 可选: 发送通知给测试人员
        # notification_service.send_assignment_notification(tester_id, defect_id, current_user_id, reason)

        return True

    @staticmethod
    def terminate_defect(defect_id: int, user_id: int, reason: str = None):
        """
        终止跟踪缺陷
        :param defect_id: 缺陷ID
        :param user_id: 用户ID
        :param reason: 终止原因
        :return: None
        :raises: 各种可能的异常
        """

        # 1. 获取缺陷对象
        defect = Defect.query.get(defect_id)
        if not defect:
            raise ValueError("缺陷单不存在")

        # 2. 检查用户权限
        # 只有创建者或测试经理可以终止
        test_manager_id = DefectWorkflowService.get_test_manager_id(defect)
        test_manager = User.get_user_by_id(test_manager_id)
        if defect.creator_id != user_id and test_manager_id != user_id:
            # 这里可以添加更复杂的权限检查逻辑
            raise PermissionError(f"没有权限终止该缺陷，只有测试经理（{test_manager.real_name}/{test_manager.email}）和提单人（{defect.creator.real_name}/{defect.creator.email}）才有权限终止该缺陷。")

        # 3. 检查缺陷当前状态是否允许终止
        if defect.status == 'DefectStatus.TERMINATE_TRACKING':
            raise ValueError("缺陷已经终止跟踪")

        # 4. 开始数据库事务
        try:
            # 5. 更新缺陷状态
            defect.status = 'DefectStatus.TERMINATE_TRACKING'
            defect.updated_time = datetime.now()

            # 6. 如果有当前阶段，更新阶段状态为取消
            if defect.current_stage_id:
                current_stage = DefectStage.query.get(defect.current_stage_id)
                if current_stage:
                    current_stage.status = StageStatus.COMPLETED  # 测试经理审核缺陷描述阶段，如果确认终止，对应测试经理来说他在这一阶段的工作已经完成
                    current_stage.completed_time = datetime.now()
                    current_stage.completed_by = user_id

            # 7. 记录流程历史
            flow_history = DefectFlowHistory(
                defect_id=defect_id,
                from_stage_id=defect.current_stage_id,
                to_stage_id=defect.current_stage_id,  # 终止后阶段不变
                action_type=ActionType.TERMINATE,
                action_by=user_id,
                action_time=datetime.now(),
                notes=f"终止跟踪缺陷，原因：{reason}"
            )
            db.session.add(flow_history)

            # 8. 记录驳回信息，终止操作可以视为一种特殊驳回，记录到驳回表
            rejection = DefectRejection(
                defect_id=defect_id,
                defect_stage_id=defect.current_stage_id,
                rejection_type=RejectionType.STAGE,
                rejected_by=user_id,
                reason=reason,
                previous_stage_id=defect.current_stage_id,  # 终止后不退回上一阶段
                created_time=datetime.now()
            )
            db.session.add(rejection)

            # 提交事务
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def get_distinct_user_ids(defect_id):
        """ 获取以下各阶段责任人的 user_id，得到去重后的user_id 列表
         :param defect_id: 缺陷ID
        """
        description_user = DefectStageService.get_stage_user(defect_id, 'defect_description')
        cause_analysis_user = DefectStageService.get_stage_user(defect_id, 'cause_analysis')
        developer_solution_user = DefectStageService.get_stage_user(defect_id, 'developer_solution')
        tester_regression_user = DefectStageService.get_stage_user(defect_id, 'tester_regression')
        # 收集所有有效的user_id
        user_ids = []
        for user in [
            description_user,
            cause_analysis_user,
            developer_solution_user,
            tester_regression_user
        ]:
            if user is not None and hasattr(user, 'user_id'):
                user_id = getattr(user, 'user_id', None)
                if user_id is not None:
                    user_ids.append(user_id)
        # 去重并返回
        return list(set(user_ids))

    @staticmethod
    def resolve_defect(defect_id: int, user_id: int, reason: str = None, closure_type: str = 'resolved'):
        """
        处理缺陷状态变更（支持解决、挂起、终止、重新打开四种操作）
        :param defect_id: 缺陷ID
        :param user_id: 用户ID
        :param reason: 操作原因
        :param closure_type: 操作类型 ('resolved', 'suspended', 'terminated', 'reopen')
        :return: None
        :raises: 各种可能的异常
        """

        # 验证操作类型
        valid_types = ['resolved', 'suspended', 'terminated', 'reopen']
        if closure_type not in valid_types:
            raise ValueError(f"无效的操作类型: {closure_type}，有效类型: {valid_types}")

        # 1. 获取缺陷对象
        defect = Defect.query.get(defect_id)
        if not defect:
            raise ValueError("缺陷单不存在")

        # 2. 检查用户权限
        # 只有创建者可以执行关闭/重新打开操作
        description_user = DefectStageService.get_stage_user(defect_id, 'defect_description')
        # 收集所有有效的user_id
        user_ids = DefectWorkflowService.get_distinct_user_ids(defect_id)

        if description_user.user_id != user_id:
            raise PermissionError(
                f"没有权限操作该缺陷，缺陷描述责任人（{description_user.real_name}/{description_user.email}）才有权限。")

        # 3. 检查缺陷当前状态是否允许操作
        if closure_type == 'reopen':
            # 重新打开：只有在挂起状态下才能重新打开
            if defect.status not in ['DefectStatus.SUSPEND_TRACKING']:
                raise ValueError(f"缺陷当前状态为{defect.status}，无法重新打开，只有已挂起的缺陷可以重新打开")
        else:
            # 关闭操作：检查状态是否允许关闭
            if defect.status == 'DefectStatus.TERMINATE_TRACKING':
                raise ValueError("缺陷已经终止跟踪，无法执行关闭操作")
            elif defect.status == 'DefectStatus.CLOSED':
                raise ValueError("缺陷已经关闭，无法再次关闭")
            elif defect.status == 'DefectStatus.SUSPEND_TRACKING' and closure_type == 'suspended':
                raise ValueError("缺陷已经挂起，无法再次挂起")

        # 4. 根据操作类型确定最终状态和操作备注
        status_map = {
            'resolved': 'DefectStatus.CLOSED',
            'suspended': 'DefectStatus.SUSPEND_TRACKING',
            'terminated': 'DefectStatus.TERMINATE_TRACKING',
            'reopen': 'DefectStatus.OPEN'  # 新增重新打开状态
        }

        action_notes_map = {
            'resolved': f"问题已解决，正常关闭，原因：{reason}",
            'suspended': f"问题暂时挂起，原因：{reason}",
            'terminated': f"问题终止跟踪，原因：{reason}",
            'reopen': f"问题重新打开，原因：{reason}"  # 新增重新打开备注
        }

        final_status = status_map[closure_type]
        action_notes = action_notes_map[closure_type]

        # 5. 确定动作类型
        if closure_type == 'reopen':
            action_type = ActionType.REOPEN  # 需要确保ActionType枚举包含REOPEN
        else:
            action_type = ActionType.CLOSE

        # 6. 开始数据库事务
        try:
            # 7. 更新缺陷状态
            defect.status = final_status
            defect.updated_time = datetime.now()
            defect_description_stage = DefectStageService.get_stage_by_defect_and_type(defect_id,
                                                                                       'defect_description')
            tester_regression_stage = DefectStageService.get_stage_by_defect_and_type(defect_id,
                                                                                      'tester_regression')
            requester_confirm_stage = DefectStageService.get_stage_by_defect_and_type(defect_id,
                                                                                      'requester_confirm')
            to_stage_id = defect.current_stage_id
            email_title=''
            if closure_type == 'reopen':
                # 重新打开
                requester_confirm_stage.completed_time = None
                requester_confirm_stage.status = StageStatus.IN_PROGRESS
                email_title = '缺陷已重新开启'
                if not defect_description_stage:
                    raise ValueError("缺陷描述阶段不存在")
            elif closure_type == 'resolved':
                # 解决关闭
                requester_confirm_stage.completed_time = datetime.now()
                requester_confirm_stage.status = StageStatus.COMPLETED
                email_title = '缺陷已经解决'
                if not tester_regression_stage:
                    raise ValueError("测试回归阶段不存在")
            else:
                # 挂起和终止跟踪保持当前阶段不变
                if closure_type == 'suspended':
                    requester_confirm_stage.completed_time = datetime.now()
                    requester_confirm_stage.status = StageStatus.SUSPEND_TRACKING
                    email_title = '缺陷已经挂起'
                else:
                    requester_confirm_stage.status = StageStatus.TERMINATE_TRACKING
                    email_title = '缺陷已终止跟踪'


            for user_id in user_ids:
                send_to_user_id = user_id
                # 发送邮件
                email_content = DefectEmailService.get_general_defect_email_content(defect, message=email_title, action_type="")
                # 简化版
                DESCRIPTION_CHANGED = f"【{email_title}，请知悉】{defect.defect_number} - {defect.title}"
                email_subject = DESCRIPTION_CHANGED

                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=send_to_user_id,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title=email_subject)
                # 发送消息
                extra_params = {'reason': reason} if reason else None
                DefectMessage.create_message(
                    send_to_user_id=send_to_user_id,
                    send_from_user_id=g.user_id,
                    defect_id=defect_id,
                    message_type=MessageTypes.DEFECT_STATUS_CHANGED,
                    content=email_subject,
                    extra_params=extra_params
                )

            # 8. 记录流程历史
            flow_history = DefectFlowHistory(
                defect_id=defect_id,
                from_stage_id=defect.current_stage_id,
                to_stage_id=to_stage_id,
                action_type=action_type,
                action_by=user_id,
                action_time=datetime.now(),
                notes=action_notes
            )
            db.session.add(flow_history)

            # 提交事务
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def get_defect_project_admin_user_ids(defect_id: int) -> list:
        """
        根据缺陷ID获取对应的项目管理员用户ID列表

        通过缺陷对象关联的版本或项目信息，确定对应的实体类型和ID，
        然后查询该实体下的项目管理员用户ID列表。

        Args:
            defect_id (int): 缺陷ID，用于查询对应的缺陷记录

        Returns:
            list: 项目管理员用户ID列表，如果未找到相关管理员则返回空列表

        Raises:
            ValueError: 当缺陷单不存在或缺陷同时设置了version_id和project_id时抛出

        Example:
            >>> user_ids = get_defect_project_admin_user_ids(123)
            >>> print(user_ids)
            [1, 2, 3]
        """
        project_admin_user_ids = []
        # 获取当前缺陷
        defect = Defect.query.get(defect_id)
        if not defect:
            raise ValueError("缺陷单不存在")

        entity_type = ''
        entity_id = None

        if defect.version_id and defect.project_id:
            raise ValueError(f"缺陷单 {defect.defect_number} 同时设置了version_id 和 project_id，不符合实际情况")

        if defect.version_id:
            entity_type = 'product_line'
            entity_id = defect.version_id

        if defect.project_id:
            entity_type = 'tech_group'
            entity_id = defect.project_id

        project_admin_user_ids = ProjectMemberService.get_project_admin_user_ids(entity_type, entity_id)
        return project_admin_user_ids


    @staticmethod
    def transfer_to_other(defect_id, current_user_id, transfer_to_user_id, reason, stage_type=''):
        """
        将缺陷转交给其他用户处理

        Args:
            defect_id: 缺陷ID
            current_user_id: 当前操作用户ID
            transfer_to_user_id: 转交给的用户ID
            stage_type: 当前阶段的类型
            reason: 转交原因

        Raises:
            ValueError: 如果被转交用户之前已拒绝过该缺陷的处理
        """
        # 获取当前缺陷和阶段信息
        defect = Defect.query.get(defect_id)
        if not defect:
            raise ValueError("缺陷单不存在")

        current_stage = defect.current_stage
        if not current_stage:
            raise ValueError("缺陷没有当前阶段")

        # 检查目标用户是否存在
        target_user = User.query.get(transfer_to_user_id)
        if not target_user:
            raise ValueError("目标用户不存在")

        # 检查被转交用户是否之前拒绝过该缺陷的处理
        # 1. 检查原因分析阶段的邀请记录
        if stage_type == 'cause_analysis':
            cause_analysis_invitations = DefectLocaleInvitationService.get_cause_analysis_invitations(defect_id)
            # 修改最后一条记录
            if not cause_analysis_invitations:
                raise ValueError("没有定位邀请记录")
            else:
                cause_analysis_invitations[-1].inviter_id = current_user_id
                cause_analysis_invitations[-1].invitee_id = transfer_to_user_id
                cause_analysis_invitations[-1].status = 'InvitationStatus.PENDING'
                cause_analysis_invitations[-1].updated_time = datetime.now()

        # 2. 检查解决措施阶段的分工记录
        if stage_type == 'developer_solution':
            solution_divisions = DefectSolutionDivisionService.get_solution_divisions_by_defect_id(defect_id)
            # 修改最后一条记录
            if not solution_divisions:
                raise ValueError("没有分工记录")
            else:
                solution_divisions[-1].assign_by_id = current_user_id
                solution_divisions[-1].assignee_id = transfer_to_user_id
                solution_divisions[-1].status = 'InvitationStatus.PENDING'
                solution_divisions[-1].updated_time = datetime.now()

        # 检查当前用户是否有权限转交（通常是当前负责人或有特定权限的用户）
        project_admin_user_ids = DefectWorkflowService.get_defect_project_admin_user_ids(defect_id)
        success, user_info = UserRoleService.get_user_roles_info(g.user_id)  # 设置  g.is_company_admin  is_global_admin
        if current_stage.assigned_to != current_user_id and not g.is_company_admin and not g.is_global_admin and current_user_id not in project_admin_user_ids:
            raise PermissionError("没有操作权限。当前处理人、公司管理员、全板块管理员及项目管理员才可以设置缺陷当前处理人。")

        # 更新阶段负责人
        original_assignee = User.get_user_by_id(current_stage.assigned_to)
        current_stage.assigned_to = transfer_to_user_id
        current_stage.updated_time = datetime.now()
        extra_params = {'reason': reason} if reason else None
        DefectMessageService.save_message(
            send_to_user_id=transfer_to_user_id,
            send_from_user_id=current_user_id,
            defect_id=defect_id,
            message_type=MessageTypes.TRANSFER_TO_OTHER,  # 转处理
            extra_params=extra_params
        )

        email_content = DefectEmailService.get_email_content_by_message_type(
            defect=defect,
            message_type=MessageTypes.TRANSFER_TO_OTHER,
            extra_params=extra_params,
            from_user_id=current_user_id
        )
        email_subject = DefectEmailService.get_email_subject_by_message_type(
            defect=defect,
            message_type=MessageTypes.TRANSFER_TO_OTHER
        )
        send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=transfer_to_user_id,
                                                            admin_user_id=g.admin_user_id,
                                                            current_user_id=g.user_id,
                                                            content=email_content,
                                                            title=email_subject
                                                            )

        # 记录流程历史
        flow_history = DefectFlowHistory(
            defect_id=defect_id,
            from_stage_id=current_stage.id,
            to_stage_id=current_stage.id,  # 转交不改变阶段，所以前后阶段相同
            action_type=ActionType.TRANSFER,
            action_by=current_user_id,
            action_time=datetime.now(),
            notes=f"从用户 {original_assignee.real_name}/{original_assignee.email} 转交给用户 {target_user.real_name}/{target_user.email}，原因：{reason}"
        )

        db.session.add(flow_history)
        db.session.commit()

        # 这里可以添加通知逻辑，通知新负责人
        # notification_service.notify_transfer(defect, target_user, current_user, reason)

    @staticmethod
    def invite_developer(defect_id: int, invitee_id: int, review_notes: str, inviter_id: int, defect_type='') -> Optional[
        DefectLocaleInvitation]:
        """
        邀请开发人员参与问题定位(支持test_manager_review_desc阶段及cause_analysis阶段)

        Args:
            defect_id: 缺陷ID
            invitee_id: 被邀请的开发人员ID
            review_notes: 邀请说明/备注
            inviter_id: 邀请人ID
            defect_type: simplified（精简版，在创建缺陷单时就会邀请开发定位）

        Returns:
            创建的邀请对象，如果失败则返回None
        """
        try:
            current_app.logger.info('邀请开发人员参与问题定位...')
            # 验证所有ID的有效性
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectService.validate_user_exists(invitee_id):
                raise ValueError(f"被邀请人ID {invitee_id} 不存在")
            if not DefectService.validate_user_exists(inviter_id):
                raise ValueError(f"邀请人ID {inviter_id} 不存在")

            defect = Defect.query.get(defect_id)
            # 获取当前缺陷和阶段信息
            current_app.logger.info('defect.status in invite_developer: {0}'.format(defect.status))
            if not defect:
                raise ValueError(f"缺陷单不存在， 缺陷ID： {defect_id} ")

            # 获取当前阶段
            current_stage = DefectStage.query.get(defect.current_stage_id)
            if not current_stage:
                raise ValueError(f"缺陷单缺少当前阶段数据")
            action_type = ActionType.INVITE_TO_ANALYZE  # 执行类型（用于记录流程历史）
            defect_stage_id_for_invitation = -1
            # 确保当前阶段是 test_manager_review_desc
            extra_params = {'reason': review_notes} if review_notes else None

            if current_stage.stage_type == "test_manager_review_desc":
                action_type = ActionType.INVITE_TO_ANALYZE
                current_app.logger.info("测试经理审核描述阶段邀请开发人员")
                cause_analysis_stage = DefectStageService.create_next_stage(  # 创建 开发人员定位问题 阶段
                    defect_id=defect.id,
                    stage_type_key="cause_analysis",
                    assigned_to=invitee_id,
                    previous_stage_id=current_stage.id,
                    user_id=g.user_id
                )

                if not cause_analysis_stage:
                    db.session.rollback()
                    return None
                # 确保新创建的阶段有ID
                db.session.flush()
                defect_stage_id_for_invitation = cause_analysis_stage.id

                # 更新缺陷状态
                defect.current_stage_id = cause_analysis_stage.id
                defect.status = DefectStatus.OPEN
                defect.updated_time = datetime.now()
                DefectMessageService.save_message(
                    send_to_user_id=invitee_id,
                    send_from_user_id=inviter_id,
                    defect_id=defect_id,
                    message_type=MessageTypes.REASON_ANALYSIS,  # 主处理人 【原因分析】
                    extra_params=extra_params
                )
                current_app.logger.debug('Send Email..........')

                email_content = DefectEmailService.get_invite_email_content(
                    defect=defect,
                    invite_type='reason_analysis',
                    inviter_id=g.user_id,
                    reason=review_notes
                )
                email_subject = DefectEmailService.get_email_subject_by_message_type(
                    defect=defect,
                    message_type=MessageTypes.REASON_ANALYSIS
                )
                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=invitee_id,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title=email_subject
                                                                    )
                if send_result_dict.get('code') != ErrorCode.SUCCESS:
                    current_app.logger.error(f'邀请开发人员定位问题，邮件发送失败 {send_result_dict.get("message")}')
                else:
                    current_app.logger.debug('邀请开发人员定位问题，邮件发送成功')


            elif current_stage.stage_type == "cause_analysis" or defect_type == "simplified" or defect_type == "simplified2":
                if defect_type == "simplified" or defect_type == "simplified2":
                    current_app.logger.info("简化版DTS，在创建缺陷单时邀请开发定位")
                else:
                    current_app.logger.info("原因分析阶段主处理人邀请开发人员共同定位")
                action_type = ActionType.INVITE_CO_ANALYZE
                invite_type = 'common_analysis'
                if defect_type == "simplified" or defect_type == "simplified2":
                    defect_stage_id_for_invitation = DefectStageService.get_stage_by_defect_and_type(defect_id, 'cause_analysis').id
                    invite_type = 'reason_analysis'
                else:
                    defect_stage_id_for_invitation = current_stage.id

                DefectMessageService.save_message(
                    send_to_user_id=invitee_id,
                    send_from_user_id=inviter_id,
                    defect_id=defect_id,
                    message_type=MessageTypes.INVITE_REASON_ANALYSIS,  # 【邀请共同分析】
                    extra_params=extra_params
                )
                try:
                    email_content = DefectEmailService.get_invite_email_content(
                        defect=defect,
                        invite_type=invite_type,
                        inviter_id=g.user_id,
                        reason=review_notes
                    )
                    email_subject = DefectEmailService.get_email_subject_by_message_type(
                        defect=defect,
                        message_type=MessageTypes.INVITE_REASON_ANALYSIS
                    )
                    send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=invitee_id,
                                                                        admin_user_id=g.admin_user_id,
                                                                        current_user_id=g.user_id,
                                                                        content=email_content,
                                                                        title=email_subject
                                                                        )
                except Exception as e:
                    current_app.logger.error('邀请开发人员进行原因分析的邮件发送失败。Error: {0}'.format(e))

            if defect_stage_id_for_invitation == -1:
                current_app.logger.error('获取 defect_stage_id_for_invitation 失败')
                return None
            # 创建邀请
            current_app.logger.info(
                'current_stage.stage_type at invite_developer: {0}'.format(current_stage.stage_type))

            reject_stages = DefectStage.query.filter(DefectStage.stage_type == "cause_analysis",
                                                     DefectStage.defect_id == defect.id,
                                                     DefectStage.status == "StageStatus.REJECTED").all()
            reject_stage_ids = [rs.id for rs in reject_stages]
            print(f"reject_stage_ids{reject_stage_ids}")
            DefectStageData.query.filter(DefectStageData.defect_stage_id.in_(reject_stage_ids)).delete()
            DefectLocaleInvitation.query.filter(DefectLocaleInvitation.defect_stage_id.in_(reject_stage_ids)).delete()
            invitation = DefectLocaleInvitationService.create_invitation(
                defect_stage_id=defect_stage_id_for_invitation,
                inviter_id=inviter_id,
                invitee_id=invitee_id,
                reason=review_notes,
                action_type=action_type
            )

            if not invitation:
                return None
            db.session.commit()
            return invitation

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
                print(str(e))
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"邀请开发人员时发生错误: {str(e)}")

    @staticmethod
    def test_manager_review_description(defect_id: int, user_id: int, approved: bool,
                                        review_notes: str = None) -> Optional[Defect]:
        """测试经理审核缺陷描述"""
        try:
            # 验证所有ID的有效性
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            defect = Defect.query.get(defect_id)
            if not defect or defect.status != 'DefectStatus.OPEN':
                return None

            # 获取当前阶段（测试经理审核描述阶段）
            current_stage = DefectStage.query.get(defect.current_stage_id)  # 测试经理审核缺陷描述
            if not current_stage or current_stage.stage_type != "test_manager_review_desc":
                return None

            if approved:
                # 创建测试人员确认描述阶段
                tester_confirm_stage = DefectStageService.create_next_stage(
                    defect_id=defect_id,
                    stage_type_key="tester_confirm_desc",
                    assigned_to=defect.creator_id,  # 分配给缺陷创建者（测试人员）
                    previous_stage_id=current_stage.id,
                    user_id=user_id
                )

                if not tester_confirm_stage:
                    db.session.rollback()
                    return None

                # 记录流程历史
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=defect.id,
                    from_stage_id=current_stage.id,
                    to_stage_id=tester_confirm_stage.id,
                    action_type=ActionType.APPROVE,
                    action_by=user_id,
                    notes=f"测试经理审核通过缺陷描述: {review_notes}"
                )
            else:
                # 驳回回问题描述阶段
                description_stage = DefectStage.query.filter_by(
                    defect_id=defect_id,
                    stage_type="defect_description"
                ).first()

                if not description_stage:
                    db.session.rollback()
                    return None

                # 更新缺陷的当前阶段
                defect.current_stage_id = description_stage.id
                defect.updated_time = datetime.now()

                # 记录驳回
                rejection = DefectRejectionService.record_rejection(
                    defect_id=defect_id,
                    defect_stage_id=current_stage.id,
                    rejection_type=RejectionType.STAGE,
                    rejected_by=user_id,
                    reason=review_notes or "测试经理驳回缺陷描述",
                    previous_stage_id=description_stage.id
                )

                if not rejection:
                    db.session.rollback()
                    return None

                # 记录流程历史
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=defect.id,
                    from_stage_id=current_stage.id,
                    to_stage_id=description_stage.id,
                    action_type=ActionType.REJECT,
                    action_by=user_id,
                    notes=f"测试经理驳回缺陷描述: {review_notes}"
                )

            if not flow_history:
                db.session.rollback()
                return None

            return defect

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"测试经理审核缺陷描述时发生错误: {str(e)}")

    @staticmethod
    def tester_confirm_description(defect_id: int, user_id: int, confirmed: bool,
                                   notes: str = None) -> Optional[Defect]:
        """测试人员确认缺陷描述"""
        try:
            # 验证所有ID的有效性
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            defect = Defect.query.get(defect_id)
            if not defect or defect.status != 'DefectStatus.OPEN':
                return None

            # 获取当前阶段（测试人员确认描述阶段）
            current_stage = DefectStage.query.get(defect.current_stage_id)
            if not current_stage or current_stage.stage_type != "tester_confirm_desc":
                return None

            if confirmed:
                # 创建开发人员定位问题阶段
                cause_analysis_stage = DefectStageService.create_next_stage(
                    defect_id=defect_id,
                    stage_type_key="cause_analysis",
                    assigned_to=None,  # 需要后续邀请或分配开发人员
                    previous_stage_id=current_stage.id,
                    user_id=user_id
                )

                if not cause_analysis_stage:
                    db.session.rollback()
                    return None

                # 记录流程历史
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=defect.id,
                    from_stage_id=current_stage.id,
                    to_stage_id=cause_analysis_stage.id,
                    action_type=ActionType.APPROVE,
                    action_by=user_id,
                    notes=f"测试人员确认缺陷描述: {notes}"
                )
            else:
                # 驳回回问题描述阶段
                description_stage = DefectStage.query.filter_by(
                    defect_id=defect_id,
                    stage_type="defect_description"
                ).first()

                if not description_stage:
                    db.session.rollback()
                    return None

                # 更新缺陷的当前阶段
                defect.current_stage_id = description_stage.id
                defect.updated_time = datetime.now()

                # 记录驳回
                rejection = DefectRejectionService.record_rejection(
                    defect_id=defect_id,
                    defect_stage_id=current_stage.id,
                    rejection_type=RejectionType.STAGE,
                    rejected_by=user_id,
                    reason=notes or "测试人员驳回缺陷描述",
                    previous_stage_id=description_stage.id
                )

                if not rejection:
                    db.session.rollback()
                    return None

                # 记录流程历史
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=defect.id,
                    from_stage_id=current_stage.id,
                    to_stage_id=description_stage.id,
                    action_type=ActionType.REJECT,
                    action_by=user_id,
                    notes=f"测试人员驳回缺陷描述: {notes}"
                )

            if not flow_history:
                db.session.rollback()
                return None

            return defect

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"测试人员确认缺陷描述时发生错误: {str(e)}")

    # @staticmethod
    # def invite_for_analysis(defect_stage_id: int, inviter_id: int, invitee_id: int,
    #                         reason: str) -> Optional[DefectLocaleInvitation]:
    #     """邀请开发人员参与问题分析"""
    #     try:
    #         # 验证所有ID的有效性
    #         if not DefectStageService.validate_stage_exists(defect_stage_id):
    #             raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
    #         if not DefectService.validate_user_exists(inviter_id):
    #             raise ValueError(f"邀请人ID {inviter_id} 不存在")
    #         if not DefectService.validate_user_exists(invitee_id):
    #             raise ValueError(f"被邀请人ID {invitee_id} 不存在")
    #
    #         # 获取阶段信息
    #         stage = DefectStage.query.get(defect_stage_id)
    #         if not stage or stage.stage_type != "cause_analysis":
    #             return None
    #
    #         return DefectLocaleInvitationService.create_invitation(
    #             defect_stage_id=defect_stage_id,
    #             inviter_id=inviter_id,
    #             invitee_id=invitee_id,
    #             reason=reason
    #         )
    #     except Exception as e:
    #         raise RuntimeError(f"邀请分析时发生错误: {str(e)}")

    @staticmethod
    def submit_analysis(defect_stage_id: int, analysis_content: dict,
                        submitted_by: int, is_draft: bool = False,
                        locale_invitation_id: int = None) -> tuple[Optional[DefectStageData],str]:
        """提交原因分析"""
        try:
            # 验证所有ID的有效性
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            if not DefectService.validate_user_exists(submitted_by):
                raise ValueError(f"提交人ID {submitted_by} 不存在")
            if locale_invitation_id and not DefectLocaleInvitationService.validate_invitation_exists(
                    locale_invitation_id):
                raise ValueError(f"邀请ID {locale_invitation_id} 不存在")

            # 获取阶段信息
            stage = DefectStage.query.get(defect_stage_id)
            if not stage or stage.stage_type != "cause_analysis":
                return None
            # 需要进行原因分析的 AI 评估——待修改

            return DefectStageDataService.submit_stage_data(
                defect_stage_id=defect_stage_id,
                data_type=DataType.CAUSE_ANALYSIS,
                content=analysis_content,
                submitted_by=submitted_by,
                is_draft=is_draft,
                locale_invitation_id=locale_invitation_id
            )
        except Exception as e:
            raise RuntimeError(f"提交分析时发生错误: {str(e)}")

    @staticmethod
    def dev_lead_review_analysis(defect_id: int, user_id: int, approved: bool,
                                 review_notes: str = None) -> Optional[Defect]:
        """开发主管审核原因分析"""
        try:
            # 验证所有ID的有效性
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            defect = Defect.query.get(defect_id)
            if not defect or defect.status != 'DefectStatus.OPEN':
                return None

            # 获取当前阶段（开发主管审核原因分析阶段）
            current_stage = DefectStage.query.get(defect.current_stage_id)
            if not current_stage or current_stage.stage_type != "dev_lead_review_analysis":
                return None

            if approved:
                # 创建开发人员解决措施阶段
                developer_solution_stage = DefectStageService.create_next_stage(
                    defect_id=defect_id,
                    stage_type_key="developer_solution",
                    assigned_to=current_stage.assigned_to,  # 分配给分析阶段的负责人
                    previous_stage_id=current_stage.id,
                    user_id=user_id
                )

                if not developer_solution_stage:
                    db.session.rollback()
                    return None

                # 记录流程历史
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=defect.id,
                    from_stage_id=current_stage.id,
                    to_stage_id=developer_solution_stage.id,
                    action_type=ActionType.APPROVE,
                    action_by=user_id,
                    notes=f"开发主管审核通过原因分析: {review_notes}"
                )
            else:
                # 驳回回原因分析阶段
                analysis_stage = DefectStage.query.filter_by(
                    defect_id=defect_id,
                    stage_type="cause_analysis"
                ).first()

                if not analysis_stage:
                    db.session.rollback()
                    return None

                # 更新缺陷的当前阶段
                defect.current_stage_id = analysis_stage.id
                defect.updated_time = datetime.now()

                # 记录驳回
                rejection = DefectRejectionService.record_rejection(
                    defect_id=defect_id,
                    defect_stage_id=current_stage.id,
                    rejection_type=RejectionType.STAGE,
                    rejected_by=user_id,
                    reason=review_notes or "开发主管驳回原因分析",
                    previous_stage_id=analysis_stage.id
                )

                if not rejection:
                    db.session.rollback()
                    return None

                # 记录流程历史
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=defect.id,
                    from_stage_id=current_stage.id,
                    to_stage_id=analysis_stage.id,
                    action_type=ActionType.REJECT,
                    action_by=user_id,
                    notes=f"开发主管驳回原因分析: {review_notes}"
                )

            if not flow_history:
                db.session.rollback()
                return None

            return defect

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"开发主管审核原因分析时发生错误: {str(e)}")

    @staticmethod
    def assign_for_solution(defect_stage_id: int, module: str, version: str,
                            due_date: datetime, assignee_id: int, action_plan: str) -> Optional[DefectSolutionDivision]:
        """分配开发人员进行解决"""
        try:
            # 验证所有ID的有效性
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            if not DefectService.validate_user_exists(assignee_id):
                raise ValueError(f"分配人ID {assignee_id} 不存在")

            # 获取阶段信息
            stage = DefectStage.query.get(defect_stage_id)
            if not stage or stage.stage_type != "developer_solution":
                return None

            return DefectSolutionDivisionService.create_division(
                defect_stage_id=defect_stage_id,
                module=module,
                version=version,
                due_date=due_date,
                assignee_id=assignee_id,
                action_plan=action_plan
            )
        except Exception as e:
            raise RuntimeError(f"分配解决方案时发生错误: {str(e)}")

    @staticmethod
    def submit_solution(defect_stage_id: int, solution_content: dict,
                        submitted_by: int, solution_division_id: int = None) -> tuple[Optional[DefectStageData],str]:
        """提交解决措施"""
        try:
            # 验证所有ID的有效性
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            if not DefectService.validate_user_exists(submitted_by):
                raise ValueError(f"提交人ID {submitted_by} 不存在")
            if solution_division_id and not DefectSolutionDivisionService.validate_division_exists(
                    solution_division_id):
                raise ValueError(f"分工ID {solution_division_id} 不存在")

            # 获取阶段信息
            stage = DefectStage.query.get(defect_stage_id)
            if not stage or stage.stage_type != "developer_solution":
                return None

            return DefectStageDataService.submit_stage_data(
                defect_stage_id=defect_stage_id,
                data_type=DataType.SOLUTION,
                content=solution_content,
                submitted_by=submitted_by,
                is_draft=False,
                solution_division_id=solution_division_id
            )
        except Exception as e:
            raise RuntimeError(f"提交解决方案时发生错误: {str(e)}")

    @staticmethod
    def dev_lead_review_solution(defect_id: int, user_id: int, tester_id: int, approved: bool,
                                 review_notes: str = None) -> Optional[Defect]:
        """开发主管审核解决措施"""
        try:
            # 验证所有ID的有效性
            if not DefectService.validate_defect_exists(defect_id):
                current_app.logger.info(f"缺陷ID {defect_id} 不存在")
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                current_app.logger.info(f"用户ID {user_id} 不存在")
                raise ValueError(f"用户ID {user_id} 不存在")

            defect = Defect.query.get(defect_id)
            current_app.logger.info(f"dev_lead_review_solution defect.status {defect.status}")
            if not defect:
                raise ValueError(f"缺陷单不存在， 缺陷ID： {defect_id} ")

            # 获取当前阶段（开发主管审核解决措施阶段）
            current_stage = DefectStage.query.get(defect.current_stage_id)
            if not current_stage or (current_stage.stage_type != "dev_lead_review_solution" and defect.defect_type != 'simplified' and defect.defect_type != 'simplified2'):
                return None
            current_app.logger.info('dev_lead_review_solution是否审核通过：{0}'.format(approved))
            if approved:
                if not DefectService.validate_user_exists(tester_id):
                    current_app.logger.info(f"回归测试用户ID {tester_id} 不存在")
                    raise ValueError(f"回归测试用户ID {tester_id} 不存在")
                if defect.defect_type == 'simplified' or defect.defect_type == 'simplified2':
                    tester_regression_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'tester_regression')
                    # 更新阶段信息
                    tester_regression_stage = DefectStageService.update_stage(stage_id=tester_regression_stage.id,
                                                                              assigned_to = tester_id,  # 分配给指定的（测试人员）
                                                                              notes="简化版指定回归测试人员",
                                                                              status=StageStatus.IN_PROGRESS
                                                                              )
                else:
                    # 创建测试人员回归测试阶段
                    tester_regression_stage = DefectStageService.create_next_stage(
                        defect_id=defect_id,
                        stage_type_key="tester_regression",
                        assigned_to=tester_id,  # 分配给指定的（测试人员）
                        previous_stage_id=current_stage.id,
                        user_id=user_id
                    )

                    if not tester_regression_stage:
                        db.session.rollback()
                        return None

                extra_params = {'reason': review_notes} if review_notes else None
                DefectMessageService.save_message(
                    send_to_user_id=tester_id,
                    send_from_user_id=g.user_id,
                    defect_id=defect_id,
                    message_type=MessageTypes.REGRESSION_TEST,  # 回归测试
                    extra_params=extra_params
                )

                email_content = DefectEmailService.get_email_content_by_message_type(
                    defect=defect,
                    message_type=MessageTypes.REGRESSION_TEST,
                    extra_params=extra_params,
                    from_user_id=g.user_id
                )
                email_subject = DefectEmailService.get_email_subject_by_message_type(
                    defect=defect,
                    message_type=MessageTypes.REGRESSION_TEST
                )
                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=tester_id,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title= email_subject
                                                                    )
                pre_note = "开发主管审核通过解决措施"
                if defect.defect_type == 'simplified' or defect.defect_type == 'simplified2':
                    pre_note = "指定回归测试人员"
                # 记录流程历史
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=defect.id,
                    from_stage_id=current_stage.id,
                    to_stage_id=tester_regression_stage.id,
                    action_type=ActionType.APPROVE,
                    action_by=user_id,
                    notes=f"{pre_note}: {review_notes}"
                )
                if not flow_history:
                    db.session.rollback()
                    return None
            else:
                # 调用相应的服务方法处理驳回逻辑
                defect = DefectWorkflowService.reject_defect(defect_id, g.user_id, review_notes)
            return defect
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"开发主管审核解决措施时发生错误: {str(e)}")

    @staticmethod
    def submit_regression_test(defect_stage_id: int, test_result: dict,
                               submitted_by: int) -> tuple[Optional[DefectStageData],str]:
        """提交回归测试结果"""
        try:
            # 验证所有ID的有效性
            if not DefectStageService.validate_stage_exists(defect_stage_id):
                raise ValueError(f"缺陷阶段ID {defect_stage_id} 不存在")
            if not DefectService.validate_user_exists(submitted_by):
                raise ValueError(f"提交人ID {submitted_by} 不存在")

            # 获取阶段信息
            stage = DefectStage.query.get(defect_stage_id)
            if not stage or stage.stage_type != "tester_regression":
                return None

            return DefectStageDataService.submit_stage_data(
                defect_stage_id=defect_stage_id,
                data_type=DataType.TEST_RESULT,
                content=test_result,
                submitted_by=submitted_by,
                is_draft=False
            )
        except Exception as e:
            raise RuntimeError(f"提交回归测试结果时发生错误: {str(e)}")

    @staticmethod
    def test_manager_review_regression(defect_id: int, user_id: int, approved: bool,
                                       review_notes: str = None) -> Optional[Defect]:
        """测试经理审核回归测试"""
        try:
            # 验证所有ID的有效性
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            defect = Defect.query.get(defect_id)
            if not defect or defect.status != 'DefectStatus.OPEN':
                return None

            # 获取当前阶段（测试经理审核回归测试阶段）
            current_stage = DefectStage.query.get(defect.current_stage_id)
            if not current_stage or current_stage.stage_type != "test_manager_review_regression":
                return None

            if approved:
                # 创建提出人确认阶段
                requester_confirm_stage = DefectStageService.create_next_stage(
                    defect_id=defect_id,
                    stage_type_key="requester_confirm",
                    assigned_to=defect.creator_id,  # 分配给缺陷创建者
                    previous_stage_id=current_stage.id,
                    user_id=user_id
                )

                if not requester_confirm_stage:
                    db.session.rollback()
                    return None

                # 记录流程历史
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=defect.id,
                    from_stage_id=current_stage.id,
                    to_stage_id=requester_confirm_stage.id,
                    action_type=ActionType.APPROVE,
                    action_by=user_id,
                    notes=f"测试经理审核通过回归测试: {review_notes}"
                )
                if not flow_history:
                    db.session.rollback()
                    return None
            else:
                # 调用相应的服务方法处理驳回逻辑
                defect = DefectWorkflowService.reject_defect(defect_id, g.user_id, review_notes)
            return defect
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"测试经理审核回归测试时发生错误: {str(e)}")

    @staticmethod
    def requester_confirm(defect_id: int, user_id: int, confirmed: bool,
                          notes: str = None) -> Optional[Defect]:
        """提出人确认缺陷解决(支持 驳回 和 确认解决)"""
        try:
            # 验证所有ID的有效性
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            defect = Defect.query.get(defect_id)
            if not defect:
                current_app.logger.error(f'缺陷单不存在 defect_id: {defect_id}')
                return None
            if defect.defect_type == 'simplified' or defect.defect_type == 'simplified2':
                current_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'tester_regression')
            else:# 获取当前阶段（提出人确认阶段）
                current_stage = DefectStage.query.get(defect.current_stage_id)
                if not current_stage or current_stage.stage_type != "requester_confirm":
                    return None
            if defect.defect_type == 'simplified' or defect.defect_type == 'simplified2':
                defect_status_message = '已解决'
                if confirmed:
                    # 更新缺陷状态为已关闭
                    defect.status = 'DefectStatus.CLOSED'
                    defect.updated_time = datetime.now()
                    # 完成当前阶段
                    current_stage.status = StageStatus.COMPLETED
                    current_stage.completed_time = datetime.now()
                    current_stage.completed_by = user_id
                    message_type=MessageTypes.DEFECT_CLOSE_CONFIRM
                    email_content = DefectEmailService.get_close_confirm_email_content(defect, g.user_id)
                    # message = f"操作人：{session['real_name']} 确认缺陷已解决，请查看"
                    # email_content = DefectEmailService.get_general_defect_email_content2(defect.id, message, "关闭确认")
                    #email_content = DefectEmailService.get_close_confirm_email_content(defect, g.user_id, is_closed=False)

                else:
                    defect_status_message = '未解决'
                    # 更新缺陷状态为已打开
                    defect.status = 'DefectStatus.OPEN'
                    defect.updated_time = datetime.now()
                    # 完成当前阶段
                    current_stage.status = StageStatus.NotPASS
                    current_stage.completed_time = datetime.now()
                    current_stage.completed_by = user_id
                    message_type = MessageTypes.REJECT_REGRESSION_TEST
                    email_content = DefectEmailService.get_close_confirm_email_content(defect, g.user_id, is_closed=False)
                    # message = f"操作人：{session['real_name']} 确认缺陷未解决，请查看"
                    # email_content = DefectEmailService.get_general_defect_email_content2(defect.id, message, "关闭确认")
                    #email_content = DefectEmailService.get_close_confirm_email_content(defect, g.user_id, is_closed=False)

                # 无论是否解决都需要发送消息和邮件、记录日志
                extra_params = {'reason': notes} if notes else None
                DefectMessageService.save_message(
                    send_to_user_id=defect.creator_id,  # 发给问题提出人
                    send_from_user_id=g.user_id,
                    defect_id=defect_id,
                    message_type=message_type,  # 确认是否关闭
                    extra_params=extra_params
                )
                previous_stage = current_stage.previous_stage
                DefectMessageService.save_message(
                    send_to_user_id=previous_stage.assigned_to,  # 发给上一流程人
                    send_from_user_id=g.user_id,
                    defect_id=defect_id,
                    message_type=message_type,  # 确认是否关闭
                    extra_params=extra_params
                )


                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=defect.creator_id,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title=f'【缺陷电子流 {defect.defect_number}】回归测试确认缺陷{defect_status_message}'
                                                                    )

                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=previous_stage.assigned_to,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title=f'【缺陷电子流 {defect.defect_number}】回归测试确认缺陷{defect_status_message}'
                                                                    )
                if send_result_dict.get('code') != ErrorCode.SUCCESS:
                    current_app.logger.error(f'问题确认{defect_status_message}，邮件发送失败： {send_result_dict.get("message")}')
                else:
                    current_app.logger.info(f'问题确认{defect_status_message}，邮件发送成功。')
                pre_notes = f'回归测试确认缺陷{defect_status_message}'
                if defect.defect_type == 'simplified2':
                    pre_notes = f'提单人确认缺陷{defect_status_message}'
                # 记录流程历史
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=defect.id,
                    from_stage_id=current_stage.id,
                    to_stage_id=current_stage.id,  # 没有下一阶段，停留在当前阶段
                    action_type=ActionType.APPROVE,
                    action_by=user_id,
                    notes=f"{pre_notes}: {notes}"
                )

            else:
                if confirmed:
                    defect_status_message = '已解决'
                    # 更新缺陷状态为已关闭
                    defect.status = 'DefectStatus.CLOSED'
                    defect.updated_time = datetime.now()

                    # 完成当前阶段
                    current_stage.status = StageStatus.COMPLETED
                    current_stage.completed_time = datetime.now()
                    current_stage.completed_by = user_id

                    extra_params = {'reason': notes} if notes else None
                    DefectMessageService.save_message(
                        send_to_user_id=defect.creator_id, # 发给问题提出人
                        send_from_user_id=g.user_id,
                        defect_id=defect_id,
                        message_type=MessageTypes.DEFECT_CLOSE_CONFIRM ,  # 确认关闭
                        extra_params=extra_params
                    )
                    previous_stage = current_stage.previous_stage
                    DefectMessageService.save_message(
                        send_to_user_id=previous_stage.assigned_to,  # 发给上一流程人
                        send_from_user_id=g.user_id,
                        defect_id=defect_id,
                        message_type=MessageTypes.DEFECT_CLOSE_CONFIRM,  # 确认关闭
                        extra_params=extra_params
                    )

                    email_content = DefectEmailService.get_close_confirm_email_content(defect, g.user_id)
                    send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=defect.creator_id,
                                                                        admin_user_id=g.admin_user_id,
                                                                        current_user_id=g.user_id,
                                                                        content=email_content,
                                                                        title=f'【缺陷电子流 {defect.defect_number}】提出人确认缺陷{defect_status_message}'
                                                                        )

                    send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=previous_stage.assigned_to,
                                                                        admin_user_id=g.admin_user_id,
                                                                        current_user_id=g.user_id,
                                                                        content=email_content,
                                                                        title=f'【缺陷电子流 {defect.defect_number}】提出人确认缺陷{defect_status_message}'
                                                                        )
                    if send_result_dict.get('code') != ErrorCode.SUCCESS:
                        current_app.logger.error(f'问题确认{defect_status_message}，邮件发送失败： {send_result_dict.get("message")}')
                    else:
                        current_app.logger.info(f'问题确认{defect_status_message}，邮件发送成功。')

                    pre_notes = f'提出人确认缺陷{defect_status_message}'
                    # 记录流程历史
                    flow_history = DefectFlowHistoryService.record_flow(
                        defect_id=defect.id,
                        from_stage_id=current_stage.id,
                        to_stage_id=current_stage.id,  # 没有下一阶段，停留在当前阶段
                        action_type=ActionType.APPROVE,
                        action_by=user_id,
                        notes=f"{pre_notes}: {notes}"
                    )
                else:
                    # 调用相应的服务方法处理驳回逻辑
                    defect = DefectWorkflowService.reject_defect(defect_id, g.user_id, notes)

            return defect

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"提出人确认缺陷解决时发生错误: {str(e)}")

    @staticmethod
    def reject_defect(defect_id: int, user_id: int, reason: str) -> Optional[Defect]:
        """驳回缺陷 （通用方法）
        1.验证缺陷和用户是否存在
        2.获取当前缺陷和当前阶段信息
        3.获取前一阶段用于退回
        4.更新当前阶段状态为“已驳回”
        5. 将缺陷的当前阶段设置为前一阶段(将前一阶段的状态设置为 PENDING_UPDATE，驳回次数 +1)
        6、如果是原因分析与解决方案的驳回需要特殊处理：修改 邀请（defect_locale_invitations） 或 分工（defect_solution_divisions）表对应记录的status为 InvitationStatus.REJECTED（如果之前已经弃用则不用被驳回）
        7. 记录驳回原因到DefectRejection 表
        8.记录流程历史到DefectFlowHistory 表
        9. 提交事务或回滚错误
        """
        try:
            # 验证缺陷ID和用户ID是否存在
            if not DefectService.validate_defect_exists(defect_id):
                raise ValueError(f"缺陷ID {defect_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            # 获取缺陷对象
            defect = Defect.query.get(defect_id)
            if not defect:
                return None

            # 获取当前阶段
            current_stage = DefectStage.query.get(defect.current_stage_id)
            if not current_stage:
                raise ValueError(f"缺陷 {defect_id} 的当前阶段不存在")

            # 获取前一阶段（用于驳回后退回）
            previous_stage = DefectStage.query.get(current_stage.previous_stage_id)
            if not previous_stage:
                # 如果没有前一阶段，则不能驳回，只能关闭或作其他处理
                raise ValueError("无法驳回，没有前一阶段可退回")

            if previous_stage.stage_type == 'cause_analysis':  # 对于原因分析的驳回，需要确认有几人的原因分析
                selected_invitation_ids = request.form.get('selected_invitation_ids')
                current_app.logger.debug(f'selected_invitation_ids: {selected_invitation_ids}')
                cause_analysis_invitations = []
                if selected_invitation_ids:
                    invitation_ids = [int(id_str.strip()) for id_str in selected_invitation_ids.split(',')]
                    cause_analysis_invitations = DefectLocaleInvitationService.get_invitations_by_ids(invitation_ids)
                else:
                    cause_analysis_invitations = DefectLocaleInvitationService.get_cause_analysis_invitations(defect_id)
                current_app.logger.info(
                    f'原因分析 在开发主管审核阶段被驳回，共有 {len(cause_analysis_invitations)} 人的原因分析')

                for invitation in cause_analysis_invitations:
                    if invitation.status == 'InvitationStatus.CANCELLED':  # 被弃用的原因分析无需处理驳回
                        continue

                    MessageCreator.create_reject_message(defect_id=defect_id,
                                                         reviewer_id=g.user_id,
                                                         submitter_id=invitation.invitee_id,
                                                         reject_type='reason_analysis',
                                                         reason=reason)

                    email_content = DefectEmailService.get_reject_email_content(
                        defect=defect,
                        reject_type='reason_analysis',
                        reject_reason=reason,
                        reviewer_id=g.user_id
                    )
                    email_subject = DefectEmailService.get_email_subject_by_message_type(
                        defect=defect,
                        message_type=MessageTypes.REJECT_REASON_ANALYSIS
                    )
                    send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=invitation.invitee_id,
                                                                        admin_user_id=g.admin_user_id,
                                                                        current_user_id=g.user_id,
                                                                        content=email_content,
                                                                        title=email_subject
                                                                        )

                    DefectLocaleInvitationService.update_invitation_status(invitation.id, InvitationStatus.REJECTED,
                                                                           reason)

            if previous_stage.stage_type == 'developer_solution':  # 对于解决措施的驳回，需要确认有几人的分工(全量的驳回)
                selected_division_ids = request.form.get('selected_division_ids')
                current_app.logger.debug(f'selected_division_ids: {selected_division_ids}')
                solution_divisions = []
                if selected_division_ids:
                    division_ids = [int(id_str.strip()) for id_str in selected_division_ids.split(',')]
                    solution_divisions = DefectSolutionDivisionService.get_solution_divisions_by_division_ids(division_ids)
                else:
                    solution_divisions = DefectSolutionDivisionService.get_solution_divisions_by_defect_id(defect_id)
                current_app.logger.info(
                    f'原因分析 在解决措施阶段被驳回，共有 {len(solution_divisions)} 人的分工信息')
                for division in solution_divisions:
                    MessageCreator.create_reject_message(defect_id=defect_id,
                                                         reviewer_id=g.user_id,
                                                         submitter_id=division.assignee_id,
                                                         reject_type='solution_measures',
                                                         reason=reason)

                    email_content = DefectEmailService.get_reject_email_content(
                        defect=defect,
                        reject_type='solution_measures',
                        reject_reason=reason,
                        reviewer_id=g.user_id
                    )
                    email_subject = DefectEmailService.get_email_subject_by_message_type(
                        defect=defect,
                        message_type=MessageTypes.REJECT_SOLUTION_MEASURES
                    )
                    send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=division.assignee_id,
                                                                        admin_user_id=g.admin_user_id,
                                                                        current_user_id=g.user_id,
                                                                        content=email_content,
                                                                        title=email_subject
                                                                        )

                    DefectSolutionDivisionService.update_division_status(division.id, InvitationStatus.REJECTED, reason)

            if previous_stage.stage_type == "defect_description": # 发送消息和邮件
                MessageCreator.create_reject_message(defect_id=defect_id,
                                                     reviewer_id=g.user_id,
                                                     submitter_id=previous_stage.assigned_to,
                                                     reject_type='defect_description',
                                                     reason=reason)
                email_content = DefectEmailService.get_reject_email_content(
                    defect=defect,
                    reject_type='defect_description',
                    reject_reason=reason,
                    reviewer_id=g.user_id
                )
                email_subject = DefectEmailService.get_email_subject_by_message_type(
                    defect=defect,
                    message_type=MessageTypes.REJECT_DEFECT_DESCRIPTION
                )
                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=previous_stage.assigned_to,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title=email_subject
                                                                    )

            # 上一步是 测试经理审核描述 然后邀请开发人员定位问题，当前阶段为 开发人员定位问题
            if previous_stage.stage_type == "test_manager_review_desc" and current_stage.stage_type=="cause_analysis":  # 发送消息和邮件
                cause_analysis_invitations = DefectLocaleInvitationService.get_cause_analysis_invitations(defect_id)
                for invitation in cause_analysis_invitations:
                    if invitation.status == 'InvitationStatus.CANCELLED':  # 被弃用的原因分析无需处理驳回
                        continue
                    DefectLocaleInvitationService.update_invitation_status(invitation.id, InvitationStatus.REJECTED,
                                                                           reason)
                DefectMessageService.save_message(
                    send_to_user_id=previous_stage.assigned_to,
                    send_from_user_id=g.user_id,
                    defect_id=defect_id,
                    message_type=MessageTypes.REJECT_INVITATION,  # 驳回原因分析邀请
                    extra_params = {'reason': reason} if reason else None
                )

                email_content = DefectEmailService.get_email_content_by_message_type(
                    defect=defect,
                    message_type=MessageTypes.REJECT_INVITATION,
                    extra_params = {'reason': reason} if reason else None,
                    from_user_id=g.user_id
                )
                email_subject = DefectEmailService.get_email_subject_by_message_type(
                    defect=defect,
                    message_type=MessageTypes.REJECT_INVITATION
                )
                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=previous_stage.assigned_to,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title=email_subject
                                                                    )

            if previous_stage.stage_type == "dev_lead_review_solution":  #
                MessageCreator.create_reject_message(defect_id=defect_id,
                                                     reviewer_id=g.user_id,
                                                     submitter_id=previous_stage.assigned_to,
                                                     reject_type='solution_measures',
                                                     reason=reason)

                email_content = DefectEmailService.get_reject_email_content(
                    defect=defect,
                    reject_type='solution_measures',
                    reject_reason=reason,
                    reviewer_id=g.user_id
                )
                email_subject = DefectEmailService.get_email_subject_by_message_type(
                    defect=defect,
                    message_type=MessageTypes.REJECT_SOLUTION_MEASURES
                )
                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=previous_stage.assigned_to,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title=email_subject
                                                                    )

            if previous_stage.stage_type == "tester_regression":
                MessageCreator.create_reject_message(defect_id=defect_id,
                                                     reviewer_id=g.user_id,
                                                     submitter_id=previous_stage.assigned_to,
                                                     reject_type='regression_test',
                                                     reason=reason)
                email_content = DefectEmailService.get_reject_email_content(
                    defect=defect,
                    reject_type='regression_test',
                    reject_reason=reason,
                    reviewer_id=g.user_id
                )
                email_subject = DefectEmailService.get_email_subject_by_message_type(
                    defect=defect,
                    message_type=MessageTypes.REJECT_REGRESSION_TEST
                )
                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=previous_stage.assigned_to,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title=email_subject
                                                                    )

            if previous_stage.stage_type == "test_manager_review_regression":
                MessageCreator.create_reject_message(defect_id=defect_id,
                                                     reviewer_id=g.user_id,
                                                     submitter_id=previous_stage.assigned_to,
                                                     reject_type='test_manager_review_regression',
                                                     reason=reason)
                email_content = DefectEmailService.get_reject_email_content(
                    defect=defect,
                    reject_type='test_manager_review_regression',
                    reject_reason=reason,
                    reviewer_id=g.user_id
                )
                email_subject = DefectEmailService.get_email_subject_by_message_type(
                    defect=defect,
                    message_type=MessageTypes.TEST_MANAGER_REVIEW_REGRESSION
                )
                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=previous_stage.assigned_to,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title=email_subject
                                                                    )


            # 更新当前阶段状态为已驳回
            current_stage.status = StageStatus.REJECTED
            current_stage.updated_time = datetime.now()

            # 更新缺陷的当前阶段为前一阶段(将前一阶段的状态设置为 PENDING_UPDATE，驳回次数 +1)
            defect.current_stage_id = previous_stage.id
            previous_stage.status = StageStatus.PENDING_UPDATE
            previous_stage.rejection_count += 1
            defect.updated_time = datetime.now()

            # 记录驳回
            rejection = DefectRejectionService.record_rejection(
                defect_id=defect_id,
                defect_stage_id=current_stage.id,
                rejection_type=RejectionType.STAGE,
                rejected_by=user_id,
                reason=reason,
                previous_stage_id=previous_stage.id
            )

            if not rejection:
                db.session.rollback()
                return None
            # 获取阶段类型
            stage_type = DefectStageType.query.filter_by(stage_key=current_stage.stage_type).first()
            stage_name_show = ''
            if stage_type:
                stage_name_show = stage_type.stage_name

            # 发送 驳回消息

            # 记录流程历史
            previous_stage_history = DefectFlowHistory.query.filter(DefectFlowHistory.from_stage_id==previous_stage.id).first()
            if previous_stage_history:
                if previous_stage_history.ai_sug_score_id:
                    reason = reason+f'&nbsp;<a href="/user/aiVal/list?record_id={previous_stage_history.ai_sug_score_id}" target="_blank" style="color:#01aaed;">查看原评估记录</a>'
            flow_history = DefectFlowHistoryService.record_flow(
                defect_id=defect_id,
                from_stage_id=current_stage.id,
                to_stage_id=previous_stage.id,
                action_type=ActionType.REJECT,
                action_by=user_id,
                notes=f"{stage_name_show} 驳回缺陷流程: {reason}"
            )

            if not flow_history:
                db.session.rollback()
                return None

            # 提交事务
            db.session.commit()
            return defect

        except IntegrityError as e:
            db.session.rollback()
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"驳回缺陷时发生错误: {str(e)}")

    @staticmethod
    def reject_invitation(invitation_id: int, user_id: int, reason: str) -> Optional[DefectLocaleInvitation]:
        """
          驳回 定位分析 邀请
            :param invitation_id: 邀请ID
            :param user_id: 用户ID（被邀请人ID）
            :param reason: 驳回原因
            :return: 更新后的邀请对象或None

          1、验证邀请ID有效性：使用现有的 DefectLocaleInvitationService.validate_invitation_exists 方法验证邀请是否存在
          2、验证用户一致性：确保当前用户就是被邀请人，防止越权操作
          3、更新邀请状态：
                将状态设置为 INVITATION_REJECTED
                记录驳回原因和时间
                更新最后修改时间
          4、记录流程历史：使用现有的流程历史服务记录驳回操作
          5、异常处理：
                处理数据库完整性错误
                处理其他未知错误
                在发生错误时回滚事务
        """
        try:
            # 1. 验证邀请ID是否存在
            if not DefectLocaleInvitationService.validate_invitation_exists(invitation_id):
                current_app.logger.warning(f"邀请ID {invitation_id} 不存在")
                return None

            # 获取邀请记录
            invitation = DefectLocaleInvitation.query.get(invitation_id)
            if not invitation:
                return None

            # 2. 验证用户ID是否与被邀请人ID一致
            if invitation.invitee_id != user_id:
                current_app.logger.warning(
                    f"用户ID {user_id} 与邀请记录中的被邀请人ID {invitation.invitee_id} 不一致")
                return None

            target_user = User.query.get(user_id)
            if not target_user:
                raise ValueError("目标用户不存在")

            # 3. 更新邀请状态和相关信息
            invitation.status = InvitationStatus.INVITATION_REJECTED
            invitation.rejection_reason = reason
            invitation.rejection_time = datetime.now()
            invitation.updated_time = datetime.now()

            # 记录流程历史
            stage = DefectStage.query.get(invitation.defect_stage_id)
            if stage:
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=stage.defect_id,
                    to_stage_id=invitation.defect_stage_id,
                    action_type=ActionType.REJECT,
                    action_by=user_id,
                    notes=f"驳回了定位分析邀请: {reason}"
                )
                extra_params = {'reason': reason} if reason else None
                DefectMessageService.save_message(
                    send_to_user_id=invitation.inviter_id,
                    send_from_user_id=user_id,
                    defect_id=stage.defect_id,
                    message_type=MessageTypes.REJECT_INVITATION,
                    extra_params=extra_params
                )

                email_content = DefectEmailService.get_reject_invitation_email_content(
                    defect=stage.defect,
                    reject_reason=reason,
                    rejecter_id=g.user_id
                )
                email_subject = DefectEmailService.get_email_subject_by_message_type(
                    defect=stage.defect,
                    message_type=MessageTypes.REJECT_INVITATION
                )
                send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=invitation.inviter_id,
                                                                    admin_user_id=g.admin_user_id,
                                                                    current_user_id=g.user_id,
                                                                    content=email_content,
                                                                    title= email_subject
                                                                    )



                if not flow_history:
                    db.session.rollback()
                    return None
            db.session.commit()
            return invitation

        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"数据库完整性错误: {str(e)}")
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"驳回邀请时发生错误: {str(e)}")
            raise RuntimeError(f"驳回邀请时发生错误: {str(e)}")

    @staticmethod
    def reject_single_analysis(invitation_id: int, user_id: int, reason: str, action_type: str = '') -> Optional[
        DefectLocaleInvitation]:
        """
        驳回或弃用单个原因分析
            :param invitation_id: 邀请ID
            :param user_id: 用户ID（当前操作用户ID）
            :param reason: 驳回/弃用原因
            :param action_type: 操作类型（'reject'表示驳回，其他值表示弃用）
            :return: 更新后的邀请对象或None

        1、验证邀请ID有效性：使用现有的 DefectLocaleInvitationService.validate_invitation_exists 方法验证邀请是否存在
        2、验证数据完整性：
              - 确保关联的缺陷阶段存在
              - 确保对应的缺陷单存在
              - 确保原因分析邀请记录存在
        3、权限验证：确保当前操作用户是原因分析的主处理人（invitee_id）
        4、更新邀请状态：
              - 根据 action_type 将状态设置为 REJECTED（驳回）或 CANCELLED（弃用）
              - 记录驳回/弃用原因和时间
              - 更新最后修改时间
        5、记录流程历史：使用流程历史服务记录驳回/弃用操作，包含操作用户信息和原因
        6、异常处理：
              - 处理数据库完整性错误
              - 处理其他未知错误
              - 在发生错误时回滚事务
        """
        try:
            # 1. 验证邀请ID是否存在
            if not DefectLocaleInvitationService.validate_invitation_exists(invitation_id):
                current_app.logger.error(f"邀请ID {invitation_id} 不存在")
                return None

            # 获取邀请记录
            invitation = DefectLocaleInvitation.query.get(invitation_id)
            if not invitation:
                current_app.logger.warning(
                    f"邀请记录不存在。邀请记录的ID： {invitation.id} ")
                return None

            # 获取关联的缺陷ID用于重定向
            stage = DefectStage.query.get(invitation.defect_stage_id)
            defect = Defect.query.get(stage.defect_id)
            if not defect:
                current_app.logger.error(
                    f"对应的缺陷单已经不存在。 invitation.id ： {invitation.id} ")
                return None

            cause_analysis_invitations = DefectLocaleInvitationService.get_cause_analysis_invitations(defect.id)
            if not cause_analysis_invitations:
                current_app.logger.error(
                    f"原因分析邀请记录已经不存在。 invitation.id ： {invitation.id} ")
                return None
            # 2. 验证用户ID是否与被邀请人ID一致
            if cause_analysis_invitations[0].invitee_id != user_id:
                current_app.logger.warning(
                    f"用户ID {user_id} 与原因分析的主处理人ID（{cause_analysis_invitations[0].invitee_id} ）不一致，没有操作权限。")
                return None

            # 增加逻辑处理：
            target_user = User.query.get(user_id)
            if not target_user:
                raise ValueError("目标用户不存在")

            # 3. 更新邀请状态和相关信息
            if action_type == 'reject':
                invitation.status = InvitationStatus.REJECTED
                action_type = ActionType.REJECT
                notes_head = '驳回'
            else:
                invitation.status = InvitationStatus.CANCELLED
                action_type = ActionType.CANCEL
                notes_head = '弃用'
            invitation.rejection_reason = reason
            invitation.rejection_time = datetime.now()
            invitation.updated_time = datetime.now()

            # 记录流程历史
            stage = DefectStage.query.get(invitation.defect_stage_id)
            if stage:
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=stage.defect_id,
                    to_stage_id=invitation.defect_stage_id,
                    action_type=action_type,
                    action_by=user_id,
                    notes=f"{notes_head}了 {target_user.real_name}/{target_user.email} 的定位分析: {reason}"
                )

                if not flow_history:
                    db.session.rollback()
                    return None
            db.session.commit()
            return invitation

        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"数据库完整性错误: {str(e)}")
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"驳回原因分析时发生错误: {str(e)}")
            raise RuntimeError(f"驳回原因分析时发生错误: {str(e)}")

    @staticmethod
    def reject_single_solution(division_id: int, user_id: int, reason: str, action_type: str = '') -> Optional[
        DefectSolutionDivision]:
        """
        驳回或弃用单个原因分析
            :param division_id: 分工ID
            :param user_id: 用户ID（当前操作用户ID）
            :param reason: 驳回
            :param action_type: 操作类型（'reject'表示驳回，无弃用类型）
            :return: 更新后的邀请对象或None

        1、验证邀请ID有效性：使用现有的 DefectLocaleInvitationService.validate_invitation_exists 方法验证邀请是否存在
        2、验证数据完整性：
              - 确保关联的缺陷阶段存在
              - 确保对应的缺陷单存在
              - 确保原因分析邀请记录存在
        3、权限验证：确保当前操作用户是原因分析的主处理人（invitee_id）
        4、更新邀请状态：
              - 根据 action_type 将状态设置为 REJECTED（驳回）或 CANCELLED（弃用-暂不支持）
              - 记录驳回/弃用原因和时间
              - 更新最后修改时间
        5、记录流程历史：使用流程历史服务记录驳回/弃用操作，包含操作用户信息和原因
        6、异常处理：
              - 处理数据库完整性错误
              - 处理其他未知错误
              - 在发生错误时回滚事务
        """
        try:
            # 1. 验证邀请ID是否存在
            if not DefectLocaleInvitationService.validate_invitation_exists(division_id):
                current_app.logger.error(f"分工ID {division_id} 不存在")
                return None

            # 获取分工记录
            division = DefectSolutionDivision.query.get(division_id)
            if not division:
                current_app.logger.warning(
                    f"分工记录不存在。分工记录的ID： {division.id} ")
                return None

            # 获取关联的缺陷ID用于重定向
            stage = DefectStage.query.get(division.defect_stage_id)
            defect = Defect.query.get(stage.defect_id)
            if not defect:
                current_app.logger.error(
                    f"对应的缺陷单已经不存在。 division.id ： {division.id} ")
                return None

            solution_divisions = DefectSolutionDivisionService.get_solution_divisions_by_defect_id(defect.id)
            if not solution_divisions:
                current_app.logger.error(
                    f"解决措施分工记录已经不存在。 division.id ： {division.id} ")
                return None
            # 2. 验证用户ID是否为 开发主管 - 待修改
            dev_lead_id = DefectWorkflowService.get_dev_manager_id_with_validation(defect)
            if user_id != dev_lead_id:
                current_app.logger.error(
                    f"用户ID {user_id} 不属于开发主管，没有驳回操作权限。")
                return None

            # 增加逻辑处理：
            target_user = User.query.get(user_id)
            if not target_user:
                raise ValueError("目标用户不存在")

            # 3. 更新分工状态和相关信息
            if action_type == 'reject':
                division.status = InvitationStatus.REJECTED
                action_type = ActionType.REJECT
                notes_head = '驳回'
            else:
                current_app.logger.error(f"单个解决措施驳回时未设置操作类型 ： {division.id} ")
                return None
            # division.rejection_reason = reason  没有这两个字段，记录到流程历史中
            # division.rejection_time = datetime.now()
            division.updated_time = datetime.now()

            # 记录流程历史
            stage = DefectStage.query.get(division.defect_stage_id)
            if stage:
                flow_history = DefectFlowHistoryService.record_flow(
                    defect_id=stage.defect_id,
                    to_stage_id=division.defect_stage_id,
                    action_type=action_type,
                    action_by=user_id,
                    notes=f"{notes_head}了 {target_user.real_name}/{target_user.email} 的解决措施: {reason}"
                )

                if not flow_history:
                    db.session.rollback()
                    return None
            db.session.commit()
            return division

        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"数据库完整性错误: {str(e)}")
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"驳回原因分析时发生错误: {str(e)}")
            raise RuntimeError(f"驳回原因分析时发生错误: {str(e)}")

    @staticmethod
    def copy_defect(source_defect_id: int, user_id: int, project_id: int = None,
                    version_id: int = None, test_manager_id: int = None) -> Optional[Defect]:
        """
        基于已有的问题单复制（继承再创建）一张新的问题单
        1.验证输入参数(源缺陷ID和用户ID是否存在)
        2.获取源缺陷信息
        3.创建新的缺陷对象,并复制源缺陷的部分信息
        4. 创建初始阶段(问题描述阶段)
        5.复制源缺陷的问题描述数据(如果有)
        6.记录流程历史
        7.如果指定了测试经理,则创建测试经理审核阶段
        8. 异常处理

        参数:
            source_defect_id: 源缺陷ID，要复制的原始缺陷单ID
            user_id: 执行复制操作的用户ID
            project_id: 可选，新缺陷单所属项目ID， 二选一
            version_id: 可选，新缺陷单所属版本ID， 二选一  project_id 和 version_id都不粗在，则报错
            test_manager_id: 可选，指定测试经理ID，如提供会创建测试经理审核阶段

        返回:
            Optional[Defect]: 成功时返回新创建的Defect对象，失败时返回None

        异常:
            ValueError: 当源缺陷或用户不存在时抛出
            RuntimeError: 当复制过程中发生未知错误时抛出
            IntegrityError: 当数据库完整性错误时抛出
        """
        try:
            # 验证源缺陷ID和用户ID是否存在
            if not DefectService.validate_defect_exists(source_defect_id):
                raise ValueError(f"源缺陷ID {source_defect_id} 不存在")
            if not DefectService.validate_user_exists(user_id):
                raise ValueError(f"用户ID {user_id} 不存在")

            # 所有外键验证
            if project_id and not ProjectService.validate_project_exists(project_id):
                raise ValueError(f"项目ID {project_id} 不存在")
            if version_id and not ProductLineService.validate_version_exists(version_id):
                raise ValueError(f"版本ID {version_id} 不存在")
            if not project_id and not version_id:
                raise ValueError(f"必须指定待复制的目标 版本ID {version_id} 或目标 项目ID {project_id} ")
            # if test_manager_id and not DefectService.validate_user_exists(test_manager_id):
            #     raise ValueError(f"测试经理ID {test_manager_id} 不存在")

            # 获取源缺陷信息
            source_defect = Defect.query.get(source_defect_id)
            if not source_defect:
                return None

            # 验证源缺陷的外键引用
            if source_defect.project_id and not ProjectService.validate_project_exists(source_defect.project_id):
                raise ValueError(f"源缺陷引用的项目ID {source_defect.project_id} 不存在")
            if source_defect.version_id and not ProductLineService.validate_version_exists(source_defect.version_id):
                raise ValueError(f"源缺陷引用的版本ID {source_defect.version_id} 不存在")

            # 创建新的缺陷（复制源缺陷的信息）
            new_defect = Defect(
                title=f"【复制】{source_defect.title}",
                defect_number=DefectService.generate_defect_number(),  # 缺陷单号 自动生成
                description=source_defect.description,
                duplicate_source_id=source_defect_id,
                severity=source_defect.severity,
                defect_reproducibility=source_defect.defect_reproducibility,
                creator_id=user_id,
                version_id=version_id,
                project_id=project_id,
                status=DefectStatus.OPEN,
                created_time=datetime.now(),
                updated_time=datetime.now()
            )

            db.session.add(new_defect)
            db.session.flush()

            # 创建初始阶段 - 问题描述阶段
            initial_stage = DefectStageService.create_initial_stage(new_defect.id, user_id)
            if not initial_stage:
                db.session.rollback()
                return None

            new_defect.current_stage_id = initial_stage.id

            # 创建问题描述阶段数据（复制源缺陷的描述数据）
            source_description_stage = DefectStage.query.filter_by(
                defect_id=source_defect_id,
                stage_type="defect_description"
            ).first()

            # 如果先保存为草稿或者先AI评估，则描述数据是在 draft_creation Stage 下保存的
            if not source_description_stage:
                source_description_stage = DefectStage.query.filter_by(
                    defect_id=source_defect_id,
                    stage_type="draft_creation"
                ).first()

            if source_description_stage:
                source_description_data = DefectStageData.query.filter_by(
                    defect_stage_id=source_description_stage.id,
                    data_type=DataType.DEFECT_DESCRIPTION,
                    is_current=True
                ).first()

                if source_description_data:
                    DefectStageDataService.submit_stage_data(
                        defect_stage_id=initial_stage.id,
                        data_type=DataType.DEFECT_DESCRIPTION,
                        content=source_description_data.content,
                        submitted_by=user_id,
                        is_draft=False,
                        ai_suggestion=source_description_data.ai_suggestion,
                        ai_score=source_description_data.ai_score

                    )

            # 记录流程历史
            flow_history = DefectFlowHistoryService.record_flow(
                defect_id=new_defect.id,
                to_stage_id=initial_stage.id,
                action_type=ActionType.CREATE,
                action_by=user_id,
                notes=f'从缺陷单 <a class="defect-link" href="/defect/{source_defect_id}">{source_defect.defect_number}</a> 复制创建新缺陷单'
            )

            if not flow_history:
                db.session.rollback()
                return None
            test_manager_id = DefectWorkflowService.get_test_manager_id_with_validation(new_defect)
            # 如果指定了测试经理，创建测试经理审核阶段
            if test_manager_id:
                # 验证阶段类型存在
                stage_type = DefectStageType.query.get("test_manager_review_desc")
                if not stage_type:
                    raise ValueError(f"阶段类型键 'test_manager_review_desc' 不存在")

                test_manager_review_stage = DefectStageService.create_next_stage(
                    defect_id=new_defect.id,
                    stage_type_key="test_manager_review_desc",
                    assigned_to=test_manager_id,
                    previous_stage_id=initial_stage.id,
                    user_id=user_id
                )

                if test_manager_review_stage:
                    new_defect.current_stage_id = test_manager_review_stage.id
                    new_defect.updated_time = datetime.now()

            return new_defect

        except IntegrityError as e:
            db.session.rollback()
            # 提供更详细的错误信息
            current_app.logger.error(f"数据库完整性错误: {str(e)}")
            if "foreign key constraint" in str(e).lower():
                raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
            raise
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"复制缺陷单时发生错误: {str(e)}")
            raise RuntimeError(f"复制缺陷单时发生错误: {str(e)}")

    # 添加项目验证方法（需要根据实际情况实现）
    @staticmethod
    def validate_project_exists(project_id: int) -> bool:
        """验证项目ID是否存在"""
        # 这里需要根据您的项目模型实现验证逻辑
        # 假设有一个Project模型
        return Project.query.get(project_id) is not None

    # 添加版本验证方法（需要根据实际情况实现）
    @staticmethod
    def validate_version_exists(version_id: int) -> bool:
        """验证版本ID是否存在"""
        # 这里需要根据您的版本模型实现验证逻辑
        # 假设有一个Version模型
        return Version.query.get(version_id) is not None


class DefectStaticsService:
    @staticmethod
    def get_defect_level_config(user_id):
        """
        根据用户ID获取DI配置规则

        Args:
            user_id: 当前登录用户的ID

        Returns:
            dict: DI配置规则字典
        """
        # 获取当前用户
        current_user = User.query.get(user_id)
        if not current_user:
            return {
                'critical_defects': 10.0,
                'major_defects': 3.0,
                'minor_defects': 1.0,
                'suggestion_defects': 0.1
            }

        # 获取admin_user_id
        admin_user_id = current_user.admin_user_id if current_user.admin_user_id else user_id

        # 查询DI配置
        defect_level = DefectLevel.query.filter_by(user_id=admin_user_id).first()

        if defect_level:
            return {
                'critical_defects': defect_level.critical_defects,
                'major_defects': defect_level.major_defects,
                'minor_defects': defect_level.minor_defects,
                'suggestion_defects': defect_level.suggestion_defects
            }
        else:
            # 返回默认值
            return {
                'critical_defects': 10.0,
                'major_defects': 3.0,
                'minor_defects': 1.0,
                'suggestion_defects': 0.1
            }

    @staticmethod
    def get_user_accessible_projects_versions_filter(admin_user_id):
        """
        获取用户有权限访问的所有项目和版本的过滤条件

        参数:
            admin_user_id: 管理员用户ID

        返回:
            SQLAlchemy or_条件: 用于过滤用户有权限访问的项目和版本
        """
        # 获取用户相关的产品线下的所有版本  产品线 (Product Line)-产品 (Product)-版本 (Version)
        product_line_versions_query = Version.query.join(Product).join(ProductLine).filter(
            ProductLine.user_id == admin_user_id
        )

        # 打印产品线版本查询信息
        product_line_versions_count = product_line_versions_query.count()
        product_line_versions_list = product_line_versions_query.all()
        current_app.logger.debug(f"用户相关的产品线版本数量: {product_line_versions_count}")
        current_app.logger.debug(f"用户相关的产品线版本ID: {[v.id for v in product_line_versions_list]}")

        product_line_versions = product_line_versions_query.subquery()

        # 获取用户相关的技术族下的所有项目 技术族(Tech Group)-平台(Platform)-项目(Project)
        tech_group_projects_query = Project.query.join(Platform).join(TechGroup).filter(
            TechGroup.user_id == admin_user_id
        )

        # 打印技术族项目查询信息
        tech_group_projects_count = tech_group_projects_query.count()
        tech_group_projects_list = tech_group_projects_query.all()
        current_app.logger.debug(f"用户相关的技术族项目数量: {tech_group_projects_count}")
        current_app.logger.debug(f"用户相关的技术族项目ID: {[p.id for p in tech_group_projects_list]}")

        tech_group_projects = tech_group_projects_query.subquery()

        # 构建过滤条件：版本在用户相关的产品线中或项目在用户相关的技术族中
        filter_condition = or_(
            Defect.version_id.in_(db.session.query(product_line_versions.c.id)),
            Defect.project_id.in_(db.session.query(tech_group_projects.c.id))
        )

        return filter_condition

    @staticmethod
    def deal_version_projects(version_projects: str) -> tuple[list[str], list[str]]:
        """
        解析从导航树中获取的已选节点ID字符串，分离出版本ID和项目ID

        Args:
            version_projects: 从导航树中获取的已选节点ID字符串，多个ID用逗号分隔。
                             格式示例: "p3-123,v3-456,p3-789,v3-012"
                             - 以'p3-'开头的为项目ID
                             - 以'v3-'开头的为版本ID

        Returns:
            tuple[list[str], list[str]]: 包含两个列表的元组
                - 第一个列表: 版本ID列表 (去除'v3-'前缀)
                - 第二个列表: 项目ID列表 (去除'p3-'前缀)

        Example:
            >>> deal_version_projects("p3-123,v3-456,p3-789")
            (['456'], ['123', '789'])
        """
        level3_ids = version_projects.split(',')
        project_ids = []
        version_ids = []
        for level3_id in level3_ids:
            if 'p3-' in level3_id:
                project_ids.append(level3_id.replace("p3-", ""))
            if 'v3-' in level3_id:
                version_ids.append(level3_id.replace("v3-", ""))
        return version_ids, project_ids

    @staticmethod
    def deal_version_projects_from_list(checked_child_ids: list[str]) -> tuple[list[str], list[str]]:
        """
        解析从导航树中获取的已选节点ID列表，分离出版本ID和项目ID

        Args:
            checked_child_ids: 从导航树中获取的已选节点ID列表
                              - 以'p3-'开头的为项目ID
                              - 以'v3-'开头的为版本ID

        Returns:
            tuple[list[str], list[str]]: 包含两个列表的元组
                - 第一个列表: 版本ID列表 (去除'v3-'前缀)
                - 第二个列表: 项目ID列表 (去除'p3-'前缀)

        Example:
            >>> deal_version_projects_from_list(['v3-41', 'v3-38', 'p3-11', 'p3-12'])
            (['41', '38'], ['11', '12'])
        """
        project_ids = []
        version_ids = []

        for child_id in checked_child_ids:
            if child_id.startswith('p3-'):
                project_ids.append(child_id.replace("p3-", ""))
            elif child_id.startswith('v3-'):
                version_ids.append(child_id.replace("v3-", ""))

        return version_ids, project_ids

    @staticmethod
    def get_di_statistics():
        """
        统计每月缺陷单的DI值

        功能描述:
        此接口用于计算指定时间范围内缺陷的DI（缺陷指数）值统计。
        DI值是根据缺陷的严重程度和对应的权重配置计算得出的综合指标。
        支持按项目、版本和状态进行筛选，并按月份分组统计。

        处理流程:
        1. 接收并验证请求参数
        2. 解析日期范围并设置时间边界
        3. 获取当前用户的DI配置权重
        4. 构建基础查询并应用各种过滤条件
        5. 计算DI值并按月份分组统计
        6. 生成完整的月份列表并填充缺失的月份
        7. 格式化结果并返回

        请求参数:
        - start_date: 开始日期 (YYYY-MM-DD)，必填
        - end_date: 结束日期 (YYYY-MM-DD)，必填
        - project_id: 项目ID (可选)，用于筛选特定项目的缺陷
        - version_id: 版本ID (可选)，用于筛选特定版本的缺陷
        - version_projects: 项目ID 版本ID （多个，逗号分隔，可选）
        - defect_status: 状态筛选 ('all', 'open', 'closed')，可选，默认为'all'
        - defect_type: 缺陷类型 ('normal', 'simplified', 'simplified2')

        Returns:
            JSON: 包含DI配置和按月统计的DI值
        """
        try:
            # 步骤1: 获取并记录请求参数
            checkedChildIds = get_all_checked_version_project()
            version_ids, project_ids = DefectStaticsService.deal_version_projects_from_list(checkedChildIds)
            start_date_str = request.args.get('start_date')
            end_date_str = request.args.get('end_date')
            project_id = request.args.get('project_id', type=int)
            version_id = request.args.get('version_id', type=int)
            version_projects = request.args.get('version_projects', type=str)
            status_filter = request.args.get('defect_status', 'all')  # all, open, closed
            # 缺陷类型: normal(正常), simplified(简化), simplified2(简化2)
            defect_type = request.args.get('defect_type', 'normal')

            current_app.logger.debug(f"Received parameters: start_date={start_date_str}, end_date={end_date_str}, "
                                     f"version_projects={version_projects}, version_id={version_id}, status={status_filter}, "
                                     f"defect_type={defect_type}")

            # 步骤2: 验证必要参数
            if not start_date_str or not end_date_str:
                return jsonify({
                    'error': '开始日期和结束日期是必填参数',
                    'code': 400
                }), 400

            if version_projects:
                version_ids, project_ids = DefectStaticsService.deal_version_projects(version_projects)

            # 步骤3: 解析日期并设置时间边界
            try:
                # 将字符串日期转换为datetime对象
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                # 将结束日期设置为当天的最后时刻(23:59:59)，确保包含结束日期当天的所有数据
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                return jsonify({
                    'error': '日期格式不正确，应为YYYY-MM-DD',
                    'code': 400
                }), 400

            # 验证日期范围合理性
            if start_date > end_date:
                return jsonify({
                    'error': '开始日期不能晚于结束日期',
                    'code': 400
                }), 400

            # 步骤4: 获取当前用户ID和DI配置
            current_user_id = g.user_id  # 假设从会话或JWT中获取
            di_config = DefectStaticsService.get_defect_level_config(current_user_id)

            # 步骤5: 构建基础查询
            base_query = Defect.query

            # 步骤6: 添加日期范围过滤
            base_query = base_query.filter(Defect.created_time >= start_date, Defect.created_time <= end_date)

            # 步骤7: 应用状态过滤
            if status_filter == 'open':
                # 过滤出所有打开状态的缺陷（包括不同格式的状态值）
                base_query = base_query.filter(Defect.status.in_(OPEN_STATUS_VALUES))
                current_app.logger.debug("应用打开状态过滤")
            elif status_filter == 'closed':
                # 过滤出所有关闭状态的缺陷（包括不同格式的状态值）
                base_query = base_query.filter(Defect.status.in_(CLOSED_STATUS_VALUES))
                current_app.logger.debug("应用关闭状态过滤")
            else:
                base_query = base_query.filter(Defect.status.in_(ALL_STATUS_VALUES))
                current_app.logger.debug("应用全部状态过滤")

            # 步骤8: 获取当前用户的管理员ID（用于权限控制）
            current_user = User.query.get(current_user_id)
            admin_user_id = current_user.admin_user_id if current_user and current_user.admin_user_id else current_user_id
            current_app.logger.debug(f"当前用户ID: {current_user_id}, 管理员ID: {admin_user_id}")

            # 添加缺陷类型过滤条件
            if defect_type == 'simplified':
                base_query = base_query.filter(Defect.defect_type == 'simplified')
            elif defect_type == 'simplified2':
                base_query = base_query.filter(Defect.defect_type == 'simplified2')
            else:
                # 当缺陷类型为'normal'时，排除简化类型缺陷（包括'simplified'和'simplified2'）
                base_query = base_query.filter(
                    Defect.defect_type.notin_(['simplified', 'simplified2']) | (Defect.defect_type == None))

            # 步骤9: 处理项目/版本过滤
            if project_id:
                # 如果指定了项目ID，只查询该项目的缺陷
                base_query = base_query.filter(Defect.project_id == project_id)
                current_app.logger.debug(f"应用项目ID过滤: {project_id}")
            elif version_id:
                # 如果指定了版本ID，只查询该版本的缺陷
                base_query = base_query.filter(Defect.version_id == version_id)
                current_app.logger.debug(f"应用版本ID过滤: {version_id}")
            else:
                base_query = base_query.filter(
                    or_(
                        Defect.version_id.in_(version_ids),
                        Defect.project_id.in_(project_ids)
                    )
                )

            # 步骤10: 记录最终过滤后的查询计数（用于调试）
            count_final = base_query.count()
            current_app.logger.debug(f"最终过滤后的缺陷数量: {count_final}")

            # 步骤11: 定义DI值计算规则
            # 根据缺陷的严重程度应用不同的权重值
            di_case = case(
                (Defect.severity == '致命', di_config['critical_defects']),
                (Defect.severity == '严重', di_config['major_defects']),
                (Defect.severity == '一般', di_config['minor_defects']),
                (Defect.severity == '提示', di_config['suggestion_defects']),
                else_=0.0  # 其他严重程度不计入DI值
            )

            # 步骤12: 按年月分组并计算DI值总和
            result = base_query.with_entities(
                func.date_format(Defect.created_time, '%Y-%m').label('month'),  # 按月格式化创建时间
                func.sum(di_case).label('di_value')  # 计算每月的DI值总和
            ).group_by('month').order_by('month').all()  # 按月份分组并排序

            # 步骤13: 将查询结果转换为字典，便于查找
            stats_dict = {}
            for row in result:
                month_str = row.month
                di_value = round(float(row.di_value), 1) if row.di_value else 0.0
                stats_dict[month_str] = {
                    'month': month_str,
                    'di_value': di_value
                }

            # 步骤14: 生成完整的月份列表
            data = []

            # 获取开始和结束的年份和月份
            current_year = start_date.year
            current_month = start_date.month
            end_year = end_date.year
            end_month = end_date.month

            # 循环生成从开始月份到结束月份的所有月份
            while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
                month_str = f"{current_year}-{current_month:02d}"

                if month_str in stats_dict:
                    data.append(stats_dict[month_str])
                else:
                    data.append({
                        'month': month_str,
                        'di_value': 0.0
                    })

                # 移动到下一个月
                if current_month == 12:
                    current_month = 1
                    current_year += 1
                else:
                    current_month += 1

            current_app.logger.debug(f"最终结果: {data}")

            # 步骤15: 返回结果
            return jsonify({
                'di_config': di_config,  # 返回DI配置权重
                'data': data,  # 返回按月统计的DI值
                'code': 0
            })

        except Exception as e:
            # 异常处理：记录错误日志并返回错误信息
            current_app.logger.error(f"获取DI统计信息时发生错误: {str(e)}", exc_info=True)
            return jsonify({
                'error': f'服务器内部错误: {str(e)}',
                'code': 500
            }), 500

    @staticmethod
    def get_defect_monthly_nums():
        """
        按月统计缺陷数量接口

        统计指定条件下每月创建的缺陷数量，支持多种过滤条件。
        参数:
        start_date: 开始日期 (YYYY-MM-DD) - 必需
        end_date: 结束日期 (YYYY-MM-DD) - 必需
        project_id: 项目ID (可选)
        version_id: 版本ID (可选)
        severity (str): 严重程度筛选，可选值：'致命'/'严重'/'一般'/'提示'/'all'(全部)
        defect_status (str): 状态筛选，可选值：'open'(未关闭)/'closed'(已关闭)/'all'(全部)
        defect_type: 缺陷类型 ('normal', 'simplified', 'simplified2')
        """
        try:
            # 获取查询参数
            checkedChildIds = get_all_checked_version_project()
            version_ids, project_ids = DefectStaticsService.deal_version_projects_from_list(checkedChildIds)
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            project_id = request.args.get('project_id', type=int)
            version_id = request.args.get('version_id', type=int)
            version_projects = request.args.get('version_projects', type=str)
            severity = request.args.get('severity', 'all')  # 致命、严重、一般、提示、所有
            status_filter = request.args.get('defect_status', 'all')  # 未关闭、已关闭、所有
            # 缺陷类型: normal(正常), simplified(简化), simplified2(简化2)
            defect_type = request.args.get('defect_type', 'normal')

            # 验证必填参数
            if not start_date or not end_date:
                return jsonify({
                    'success': False,
                    'message': '开始日期和结束日期是必填参数',
                    'code': 400
                }), 400

            # 解析日期
            start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
            end_datetime = datetime.strptime(end_date, '%Y-%m-%d')

            # 包含结束日期的全天
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)

            # 获取当前用户ID（根据实际情况调整获取方式）
            current_user_id = g.user_id

            # 构建基础查询
            query = Defect.query

            if version_projects:
                version_ids, project_ids = DefectStaticsService.deal_version_projects(version_projects)

            # 应用日期范围过滤
            query = query.filter(Defect.created_time >= start_datetime)
            query = query.filter(Defect.created_time <= end_datetime)

            # 应用严重程度过滤
            if severity != 'all':
                query = query.filter(Defect.severity == severity)

            # 应用状态过滤
            if status_filter == 'open':
                query = query.filter(Defect.status.in_(OPEN_STATUS_VALUES))
            elif status_filter == 'closed':
                query = query.filter(Defect.status.in_(CLOSED_STATUS_VALUES))
            else:
                query = query.filter(Defect.status.in_(ALL_STATUS_VALUES))

            # 添加缺陷类型过滤条件
            if defect_type == 'simplified':
                query = query.filter(Defect.defect_type == 'simplified')
            elif defect_type == 'simplified2':
                query = query.filter(Defect.defect_type == 'simplified2')
            else:
                # 当缺陷类型为'normal'时，排除简化类型缺陷
                query = query.filter(
                    Defect.defect_type.notin_(['simplified', 'simplified2']) | (Defect.defect_type == None))

            # 应用项目和版本过滤
            if project_id or version_id:
                if project_id:
                    query = query.filter(Defect.project_id == project_id)
                if version_id:
                    query = query.filter(Defect.version_id == version_id)
            else:
                query = query.filter(
                    or_(
                        Defect.version_id.in_(version_ids),
                        Defect.project_id.in_(project_ids)
                    )
                )

            # 按月分组统计
            monthly_stats = query.with_entities(
                extract('year', Defect.created_time).label('year'),
                extract('month', Defect.created_time).label('month'),
                func.count(Defect.id).label('count')
            ).group_by(
                extract('year', Defect.created_time),
                extract('month', Defect.created_time)
            ).order_by(
                extract('year', Defect.created_time),
                extract('month', Defect.created_time)
            ).all()

            # 记录SQL查询（用于调试）
            sql = query.statement.compile(compile_kwargs={"literal_binds": True})
            current_app.logger.info(f"统计最终SQL查询: {sql}")

            # 将查询结果转换为字典，便于查找
            stats_dict = {}
            total_count = 0
            for stat in monthly_stats:
                year = int(stat.year)
                month = int(stat.month)
                key = f"{year}-{month:02d}"
                stats_dict[key] = {
                    'year': year,
                    'month': month,
                    'count': stat.count
                }
                total_count += stat.count

            # 生成完整的月份列表
            result = []
            current_date = start_datetime.replace(day=1, hour=0, minute=0, second=0)
            end_date_first = end_datetime.replace(day=1, hour=0, minute=0, second=0)

            while current_date <= end_date_first:
                year = current_date.year
                month = current_date.month
                key = f"{year}-{month:02d}"

                if key in stats_dict:
                    result.append(stats_dict[key])
                else:
                    result.append({
                        'year': year,
                        'month': month,
                        'count': 0
                    })

                # 移动到下一个月
                if month == 12:
                    current_date = current_date.replace(year=year + 1, month=1)
                else:
                    current_date = current_date.replace(month=month + 1)

            return jsonify({
                'success': True,
                'data': result,
                'total': total_count,
                'code': 0
            })

        except ValueError as e:
            return jsonify({
                'success': False,
                'message': f'日期格式错误，请使用YYYY-MM-DD格式: {str(e)}'
            }), 400
        except Exception as e:
            current_app.logger.error(f"统计失败: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f'统计失败: {str(e)}'
            }), 500

    @staticmethod
    def get_ai_score_statistics():
        """
        获取AI评分统计信息
        查询参数:
            start_date: 开始日期 (格式: YYYY-MM-DD)
            end_date: 结束日期 (格式: YYYY-MM-DD)
            project_id: 项目ID（可选）
            version_id: 版本ID（可选）
            defect_status: 缺陷状态 ('all', 'open', 'closed')
            defect_type: 缺陷类型 ('normal', 'simplified', 'simplified2')
        """
        try:
            # 获取查询参数
            checkedChildIds = get_all_checked_version_project()
            version_ids, project_ids = DefectStaticsService.deal_version_projects_from_list(checkedChildIds)
            current_app.logger.debug(f'checkedChildIds: {checkedChildIds}')
            start_date_str = request.args.get('start_date')
            end_date_str = request.args.get('end_date')
            project_id = request.args.get('project_id', type=int)
            version_id = request.args.get('version_id', type=int)
            version_projects = request.args.get('version_projects', type=str)
            defect_status = request.args.get('defect_status', 'all')
            data_type = request.args.get('data_type', 'all') #
            # 缺陷类型: normal(正常), simplified(简化), simplified2(简化2)
            defect_type = request.args.get('defect_type', 'normal')
            current_app.logger.debug(f'defect_type in sta {defect_type}')
            if version_projects:
                version_ids, project_ids = DefectStaticsService.deal_version_projects(version_projects)
            # 获取当前用户ID
            current_user_id = g.user_id  # 需要根据您的认证系统实现

            # 构建基础查询
            query = db.session.query(
                DefectStageData.ai_score,
                func.count(DefectStageData.id).label('count')
            ).filter(
                DefectStageData.is_current == True,  # 只统计最新的有效数据
                DefectStageData.ai_score.isnot(None)
            ).join(
                DefectStage, DefectStage.id == DefectStageData.defect_stage_id
            ).join(
                Defect, Defect.id == DefectStage.defect_id
            ).group_by(DefectStageData.ai_score)

            # 添加缺陷类型过滤条件
            if defect_type == 'simplified':
                query = query.filter(Defect.defect_type == 'simplified')
            elif defect_type == 'simplified2':
                query = query.filter(Defect.defect_type == 'simplified2')
            else:
                # 当缺陷类型为'normal'时，排除简化类型缺陷（包括'simplified'和'simplified2'）
                query = query.filter(Defect.defect_type.notin_(['simplified', 'simplified2'])|(Defect.defect_type == None))

            # 应用日期过滤
            if start_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                query = query.filter(DefectStageData.created_time >= start_date)

            if end_date_str:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                # 包含结束日期的全天
                end_date = end_date.replace(hour=23, minute=59, second=59)
                query = query.filter(DefectStageData.created_time <= end_date)

            # 应用项目/版本过滤
            if project_id:
                query = query.filter(Defect.project_id == project_id)

            elif version_id:
                query = query.filter(Defect.version_id == version_id)

            else:
                query = query.filter(
                    or_(
                        Defect.version_id.in_(version_ids),
                        Defect.project_id.in_(project_ids)
                    )
                )
            # 应用数据类型过滤
            """ DataType.DEFECT_DESCRIPTION
                DataType.CAUSE_ANALYSIS
                DataType.SOLUTION
                DataType.TEST_RESULT"""
            if data_type != 'all':
                if data_type == 'description':
                    query = query.filter(DefectStageData.data_type=='DataType.DEFECT_DESCRIPTION')
                elif data_type == 'analysis':
                    query = query.filter(DefectStageData.data_type=='DataType.CAUSE_ANALYSIS')
                elif data_type == 'solution':
                    query = query.filter(DefectStageData.data_type=='DataType.SOLUTION')
                else:  # 'TEST_RESULT'
                    query = query.filter(DefectStageData.data_type=='DataType.TEST_RESULT')

            # 应用缺陷状态过滤
            if defect_status != 'all':
                if defect_status == 'open':
                    query = query.filter(Defect.status.in_(OPEN_STATUS_VALUES))
                elif defect_status == 'closed':
                    query = query.filter(Defect.status.in_(CLOSED_STATUS_VALUES))
                else:
                    query = query.filter(Defect.status.in_(ALL_STATUS_VALUES))

            # 执行查询
            results = query.all()

            # 处理结果
            score_counts = defaultdict(int)
            for score, count in results:
                # 将分数转换为整数（如果数据库中是浮点数）
                score_int = int(score) if score is not None else None
                score_counts[score_int] += count

            # 转换为前端需要的格式
            data = [{'score': score, 'count': count} for score, count in sorted(score_counts.items())]

            return jsonify({
                'success': True,
                'data': data,
                'total': sum(score_counts.values()),
                'code': 0
            })

        except Exception as e:
            current_app.logger.error(f"获取AI评分统计失败: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'获取统计信息失败: {str(e)}'
            }), 500

    @staticmethod
    def get_stage_duration():
        """
        统计问题单在不同阶段停留的平均时间（天数）

        功能说明：
        - 计算缺陷在各个处理阶段的平均停留时间（以天为单位）
        - 支持按创建日期范围、项目ID、版本ID和缺陷状态进行筛选
        - 返回按阶段顺序排序的结果列表
        - 排除 stage_type 为 "draft_creation" 的数据

        查询参数：
        - start_date: 开始日期（格式：YYYY-MM-DD），可选
        - end_date: 结束日期（格式：YYYY-MM-DD），可选
        - project_id: 项目ID，整数类型，可选
        - version_id: 版本ID，整数类型，可选
        - defect_status: 缺陷状态筛选，可选值：'all'(全部), 'open'(开启), 'closed'(关闭)，默认为'all'
        - defect_type: 缺陷类型 ('normal', 'simplified', 'simplified2')

        返回格式:
        [
            {
                'stage_type': '阶段类型标识',      # 阶段的唯一标识符
                'stage_name': '阶段名称',          # 阶段的可读名称
                'stage_order': 阶段顺序,           # 阶段的排序序号
                'avg_duration': 平均停留天数       # 平均停留天数（保留两位小数）
            },
            ...
        ]

        权限要求：
        - 用户需要登录
        - 如果未指定项目和版本，则只返回用户有权限访问的项目和版本的数据

        异常处理：
        - 参数错误返回400状态码
        - 服务器错误返回500状态码
        """
        try:
            checkedChildIds = get_all_checked_version_project()
            version_ids, project_ids = DefectStaticsService.deal_version_projects_from_list(checkedChildIds)
            # 从请求参数中获取筛选条件
            # 开始日期，格式：YYYY-MM-DD
            start_date = request.args.get('start_date')
            # 结束日期，格式：YYYY-MM-DD
            end_date = request.args.get('end_date')
            # 项目ID，转换为整数类型
            project_id = request.args.get('project_id', type=int)
            # 版本ID，转换为整数类型
            version_id = request.args.get('version_id', type=int)
            version_projects = request.args.get('version_projects', type=str)
            # 状态过滤: all(全部), open(开启), closed(关闭)
            status_filter = request.args.get('defect_status', 'all')
            # 缺陷类型: normal(正常), simplified(简化), simplified2(简化2)
            defect_type = request.args.get('defect_type', 'normal')

            # 从全局上下文获取当前用户ID
            current_user_id = g.user_id

            if version_projects:
                version_ids, project_ids = DefectStaticsService.deal_version_projects(version_projects)

            # 构建基础SQL查询：
            # 选择阶段类型、名称、顺序和平均停留时间
            # 使用case表达式计算每个阶段的停留时间：
            # - 如果阶段已完成，使用completed_time计算实际停留时间
            # - 如果阶段未完成，使用当前时间计算至今的停留时间
            # 时间单位转换为天数（86400秒=1天）
            query = db.session.query(
                DefectStage.stage_type,
                DefectStageType.stage_name,
                DefectStageType.stage_order,
                func.avg(
                    case(
                        (DefectStage.completed_time.isnot(None),
                         func.timestampdiff(text('SECOND'), DefectStage.created_time,
                                            DefectStage.completed_time) / 86400.0),
                        else_=func.timestampdiff(text('SECOND'), DefectStage.created_time, func.now()) / 86400.0
                    )
                ).label('avg_duration')
            ).join(  # 连接阶段类型表获取阶段名称和顺序
                DefectStageType, DefectStage.stage_type == DefectStageType.stage_key
            ).join(  # 连接缺陷表用于后续的过滤条件
                Defect, DefectStage.defect_id == Defect.id
            ).filter(  # 排除 stage_type 为 "draft_creation" 的数据
                DefectStage.stage_type != 'draft_creation'
            ).group_by(  # 按阶段类型分组计算平均值
                DefectStage.stage_type, DefectStageType.stage_name, DefectStageType.stage_order
            ).order_by(  # 按阶段顺序升序排列结果
                DefectStageType.stage_order.asc()
            )

            # 添加缺陷类型过滤条件
            if defect_type == 'simplified':
                query = query.filter(Defect.defect_type == 'simplified')
            elif defect_type == 'simplified2':
                query = query.filter(Defect.defect_type == 'simplified2')
            else:
                # 当缺陷类型为'normal'时，排除简化类型缺陷（包括'simplified'和'simplified2'）
                query = query.filter(
                    Defect.defect_type.notin_(['simplified', 'simplified2']) | (Defect.defect_type == None))

            # 应用日期范围过滤条件
            if start_date:
                # 将字符串转换为datetime对象，时间设为00:00:00
                start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Defect.created_time >= start_datetime)

            if end_date:
                # 将字符串转换为datetime对象，时间设为23:59:59以包含整天的数据
                end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
                query = query.filter(Defect.created_time <= end_datetime)

            # 应用缺陷状态过滤条件
            if status_filter != 'all':
                if status_filter == 'open':
                    # 筛选处于开启状态的缺陷
                    query = query.filter(Defect.status.in_(OPEN_STATUS_VALUES))
                elif status_filter == 'closed':
                    # 筛选处于关闭状态的缺陷
                    query = query.filter(Defect.status.in_(CLOSED_STATUS_VALUES))
                else:
                    query = query.filter(Defect.status.in_(ALL_STATUS_VALUES))

            # 应用项目和版本过滤条件
            if project_id or version_id:
                # 如果明确指定了项目或版本ID，直接使用这些ID过滤
                if project_id:
                    query = query.filter(Defect.project_id == project_id)
                if version_id:
                    query = query.filter(Defect.version_id == version_id)
            else:
                query = query.filter(
                    or_(
                        Defect.version_id.in_(version_ids),
                        Defect.project_id.in_(project_ids)
                    )
                )

            # 执行查询并获取所有结果
            results = query.all()

            # 格式化查询结果为字典列表
            statistics = [
                {
                    'stage_type': stage_type,
                    'stage_name': stage_name,
                    'stage_order': stage_order,
                    'avg_duration': round(float(avg_duration), 2) if avg_duration else 0.0  # 保留两位小数
                }
                for stage_type, stage_name, stage_order, avg_duration in results
            ]

            # 返回JSON格式的成功响应
            return jsonify({
                'success': True,
                'data': statistics,
                'code': 0
            })

        except ValueError as e:
            # 参数格式错误（如日期格式不正确）
            current_app.logger.warning(f"参数错误: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'参数错误: {str(e)}'
            }), 400  # HTTP 400 Bad Request
        except Exception as e:
            # 其他未预期错误
            current_app.logger.error(f"统计阶段停留时间失败: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'统计失败: {str(e)}'
            }), 500  # HTTP 500 Internal Server Error

    @staticmethod
    def defect_stage_statistics():
        """
        缺陷阶段统计接口

        统计指定时间范围内、指定项目或版本中、指定状态各缺陷阶段的缺陷单数量，
        当不指定项目或版本时，使用当前用户的权限过滤条件
        结果按阶段顺序(stage_order)升序排列

        Query Parameters:
            start_date (str): 开始日期，格式为YYYY-MM-DD，必填
            end_date (str): 结束日期，格式为YYYY-MM-DD，必填
            project_id (int, optional): 项目ID，与version_id二选一
            version_id (int, optional): 版本ID，与project_id二选一
            defect_status: 缺陷状态筛选，可选值：'all'(全部), 'open'(开启), 'closed'(关闭)，默认为'all'
            defect_type: 缺陷类型 ('normal', 'simplified', 'simplified2')

        Returns:
            JSON: 各缺陷阶段的缺陷单数量统计，包含阶段名称、数量和顺序信息
            [
                {
                    "stage_name": "阶段名称",
                    "defect_count": 数量,
                    "stage_order": 阶段顺序
                },
                ...
            ]
        Errors:
            400: 参数错误（缺少必要参数、日期格式错误、同时提供了project_id和version_id）
            500: 服务器内部错误
        """
        # 获取查询参数
        checkedChildIds = get_all_checked_version_project()
        version_ids, project_ids = DefectStaticsService.deal_version_projects_from_list(checkedChildIds)
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        project_id = request.args.get('project_id', type=int)
        version_id = request.args.get('version_id', type=int)
        version_projects = request.args.get('version_projects', type=str)
        # 状态过滤: all(全部), open(开启), closed(关闭)
        status_filter = request.args.get('defect_status', 'all')
        # 缺陷类型: normal(正常), simplified(简化), simplified2(简化2)
        defect_type = request.args.get('defect_type', 'normal')

        # 验证必要参数
        if not start_date_str or not end_date_str:
            return jsonify({
                'error': '开始日期和结束日期是必须参数',
                'message': '请提供start_date和end_date参数，格式为YYYY-MM-DD'
            }), 400

        if project_id and version_id:
            return jsonify({
                'error': '参数冲突',
                'message': 'project_id和version_id只能选择一个，不能同时提供'
            }), 400

        try:
            # 转换日期格式
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            # 将结束日期设置为当天的最后时刻，确保包含结束日期当天的所有数据
            end_date = end_date.replace(hour=23, minute=59, second=59)
        except ValueError:
            return jsonify({
                'error': '日期格式不正确',
                'message': '日期格式应为YYYY-MM-DD，例如：2023-10-01'
            }), 400

        try:
            # 构建基础查询
            query = db.session.query(
                DefectStageType.stage_name,
                DefectStageType.stage_order,
                func.count(Defect.id).label('defect_count')
            ).join(DefectStage, DefectStage.stage_type == DefectStageType.stage_key
                   ).join(Defect, Defect.current_stage_id == DefectStage.id
                          ).filter(
                Defect.created_time >= start_date,
                Defect.created_time <= end_date,
                # 排除阶段名称为"草稿创建"的数据
                DefectStageType.stage_name != "草稿创建"
                # DefectStage.status == 'StageStatus.IN_PROGRESS'  # 进行中（未完成）
            )

            # 添加缺陷类型过滤条件
            if defect_type == 'simplified':
                query = query.filter(Defect.defect_type == 'simplified')
            elif defect_type == 'simplified2':
                query = query.filter(Defect.defect_type == 'simplified2')
            else:
                # 当缺陷类型为'normal'时，排除简化类型缺陷（包括'simplified'和'simplified2'）
                query = query.filter(Defect.defect_type.notin_(['simplified', 'simplified2'])|(Defect.defect_type == None))

            # 添加项目或版本过滤条件
            if project_id:
                query = query.filter(Defect.project_id == project_id)
            elif version_id:
                query = query.filter(Defect.version_id == version_id)
            else:
                query = query.filter(
                    or_(
                        Defect.version_id.in_(version_ids),
                        Defect.project_id.in_(project_ids)
                    )
                )

            # 应用缺陷状态过滤条件
            query = query.filter(Defect.status.in_(OPEN_STATUS_VALUES))
            # 按阶段名称和顺序分组，并按阶段顺序升序排列
            query = query.group_by(
                DefectStageType.stage_name,
                DefectStageType.stage_order
            ).order_by(DefectStageType.stage_order.asc())

            # 执行查询
            results = query.all()

            # 构建返回结果
            statistics = [
                {
                    "stage_name": result.stage_name,
                    "defect_count": result.defect_count,
                    "stage_order": result.stage_order
                }
                for result in results
            ]

            return jsonify({
                'statistics': statistics,
                'code': 0})

        except Exception as e:
            # 记录错误日志
            current_app.logger.error(f"缺陷阶段统计查询失败: {str(e)}")
            return jsonify({
                'error': '服务器内部错误',
                'message': '统计查询过程中发生错误，请稍后重试'
            }), 500

@staticmethod
def get_project_version(defect):
    project_version_id = ''
    project_version_name = '无'
    if defect.project_id:
        project_version_id = 'p3-' + str(defect.project_id)
        result, status_code = TechGroupService.get_hierarchy_by_project_id(defect.project_id)
        project_version_name = result.get('data').get('full_path')
    if defect.version_id:
        project_version_id = 'v3-' + str(defect.version_id)
        result, status_code = ProductLineService.get_hierarchy_by_version_id(defect.version_id)
        project_version_name = result.get('data').get('full_path')
    return project_version_name,project_version_id




@staticmethod
def ai_done_check(record_user_ids,current_step,login_user_id)->tuple[Optional[dict],int]:
    if current_step == -1:
        return {
            'error': '当前记录可评估阶段',
        }, 401
    current_app.logger.debug(f'login_user_id: {login_user_id},  record_user_ids:{record_user_ids}')
    # if login_user_id not in record_user_ids:
    #     return {
    #         'error': '当前用户没有权限',
    #     }, 402
    return None,200


def commit_changes():
    """提交数据库变更"""
    try:
        db.session.commit()
        return True
    except IntegrityError as e:
        db.session.rollback()
        if "foreign key constraint" in str(e).lower():
            raise ValueError("数据库完整性错误: 可能存在无效的外键引用")
        raise
    except DataError as e:
        db.session.rollback()
        raise ValueError(f"数据错误: {str(e)}")
    except DatabaseError as e:
        db.session.rollback()
        raise RuntimeError(f"数据库操作失败: {str(e)}")
    except Exception as e:
        db.session.rollback()
        raise RuntimeError(f"提交数据库变更时发生意外错误: {str(e)}")


def rollback_changes():
    """回滚数据库变更"""
    try:
        db.session.rollback()
        return True
    except Exception as e:
        raise RuntimeError(f"回滚数据库变更时发生错误: {str(e)}")


class DefectExportService:
    @staticmethod
    def get_defects_for_export(filters, user_id, admin_user_id):
        """获取导出用的缺陷数据（不分页）"""
        try:
            # 复用defect_list的查询逻辑，但不分页
            query = Defect.query.join(Defect.current_stage).join(DefectStage.assignee)

            # 确保 filters 存在
            if filters is None:
                filters = {}

            # 获取 deal_status，默认为 pending
            filters['deal_status'] = request.values.get('deal_status', 'pending')

            # 首先构建基础查询
            base_query = Defect.query.join(Defect.current_stage).join(DefectStage.assignee)
            current_app.logger.debug(f"role_select: {session['role_select']}")
            pending_query = None
            processed_query = None
            # 根据角色构建查询（与defect_list相同的逻辑）
            if session['role_select'] == "流程使用者":
                # 构建 pending_query - 当前待处理的缺陷
                pending_query = base_query.filter(
                    or_(
                        and_(Defect.status == 'DefectStatus.DRAFT', Defect.creator_id == user_id),
                        and_(
                            Defect.status != 'DefectStatus.DRAFT',
                            Defect.status != 'DefectStatus.CLOSED',
                            Defect.status != 'DefectStatus.TERMINATE_TRACKING'
                        )
                    )
                ).outerjoin(DefectStage.invitations).outerjoin(
                    DefectStage.solution_divisions
                ).filter(
                    or_(
                        DefectLocaleInvitation.invitee_id == session['user_id'],
                        DefectSolutionDivision.assignee_id == session['user_id'],
                        DefectStage.assigned_to == session['user_id']
                    )
                )

                user_current_stage_defects = Defect.query.join(Defect.current_stage).filter(
                    and_(DefectStage.assigned_to == session['user_id'],
                         Defect.status.in_(['DefectStatus.OPEN', 'DefectStatus.DRAFT']))).all()
                user_current_stage_defects_ids = [defect.id for defect in user_current_stage_defects]

                # 构建 processed_query - 曾经处理过的缺陷
                user_defect_stages = DefectStage.query.outerjoin(DefectStage.invitations).outerjoin(
                    DefectStage.solution_divisions
                ).filter(and_(
                    or_(
                        DefectLocaleInvitation.invitee_id == session['user_id'],
                        DefectSolutionDivision.assignee_id == session['user_id'],
                        DefectStage.assigned_to == session['user_id'],
                    ))
                ).all()

                defect_ids = [defect_stage.defect_id for defect_stage in user_defect_stages if
                              defect_stage.defect_id not in user_current_stage_defects_ids]
                processed_query = base_query.filter(
                    or_(Defect.id.in_(defect_ids), Defect.creator_id == user_id)
                )

            # 权限过滤
            if session['role_select'] in ["全板块查阅人", "项目查阅人", "全板块管理员"]:
                current_app.logger.debug('-------2025-------')
                all_projects_versions = ProjectMemberService.get_related_entities_by_user_id(user_id)
                conditions = []
                if all_projects_versions['project_ids']:
                    conditions.append(Defect.project_id.in_(all_projects_versions['project_ids']))
                if all_projects_versions['version_ids']:
                    conditions.append(Defect.version_id.in_(all_projects_versions['version_ids']))

                if conditions:
                    query = query.filter(or_(*conditions))
                    current_app.logger.debug('-------2025-1-------')
                    if pending_query is not None:
                        current_app.logger.debug('-------2025-2-------')
                        pending_query = pending_query.filter(or_(*conditions))
                    if processed_query is not None:
                        current_app.logger.debug('-------2025-3-------')
                        processed_query = processed_query.filter(or_(*conditions))
                else:
                    query = query.filter(False)
                    if pending_query is not None:
                        pending_query = pending_query.filter(False)
                    if processed_query is not None:
                        processed_query = processed_query.filter(False)

            # 应用筛选条件的函数（与defect_list相同）
            def apply_filters(q):
                if q is None:
                    return None
                temp_query = q
                if filters.get('search'):
                    temp_query = temp_query.filter(
                        or_(
                            Defect.title.ilike(f"%{filters['search']}%"),
                            Defect.defect_number.ilike(f"%{filters['search']}%")
                        )
                    )
                if filters.get('version_projects') != "" and filters.get('version_projects') != "all":
                    level3_ids = filters['version_projects'].split(',')
                    project_ids = []
                    version_ids = []
                    for level3_id in level3_ids:
                        if 'p3-' in level3_id:
                            project_ids.append(level3_id.replace("p3-", ""))
                        if 'v3-' in level3_id:
                            version_ids.append(level3_id.replace("v3-", ""))
                    conditions = []
                    if project_ids:
                        conditions.append(Defect.project_id.in_(project_ids))
                    if version_ids:
                        conditions.append(Defect.version_id.in_(version_ids))
                    if conditions:
                        temp_query = temp_query.filter(or_(*conditions))
                elif filters.get('version_projects') == "":
                    temp_query = temp_query.filter(Defect.version_id == -1)
                if filters.get('severity'):
                    temp_query = temp_query.filter(Defect.severity.in_(filters['severity'].split(',')))
                if filters.get('reproducible'):
                    temp_query = temp_query.filter(
                        Defect.defect_reproducibility.in_(filters['reproducible'].split(',')))
                if filters.get('completed_by'):
                    my_stage_ids = DefectStage.query.filter(
                        DefectStage.completed_by == filters['completed_by']
                    ).with_entities(DefectStage.defect_id).distinct().all()
                    my_distinct_defect_ids = [defect_id for (defect_id,) in my_stage_ids]
                    temp_query = temp_query.filter(
                        and_(
                            DefectStage.assigned_to != filters['completed_by'],
                            Defect.id.in_(my_distinct_defect_ids)
                        )
                    )
                if filters.get('stage_types_name'):
                    temp_query = temp_query.join(DefectStage.stage_type_ref).filter(
                        DefectStageType.stage_name.in_(filters['stage_types_name'].split(','))
                    )
                defect_type = filters.get('defect_type')
                if defect_type in ["simplified", "simplified2"]:
                    temp_query = temp_query.filter(Defect.defect_type == defect_type)
                else:
                    # 排除这两个特定值，保留其他所有值（包括NULL）
                    temp_query = temp_query.filter(or_(Defect.defect_type == None, Defect.defect_type == ""))
                return temp_query

            # 应用筛选条件到所有查询
            query = apply_filters(query)
            pending_query = apply_filters(pending_query)
            processed_query = apply_filters(processed_query)

            # 根据角色和状态选择查询
            if session['role_select'] == "流程使用者":
                # 根据筛选条件设置查询
                if filters['deal_status'] == 'pending':
                    query = pending_query if pending_query is not None else base_query.filter(False)
                elif filters['deal_status'] == 'processed':
                    query = processed_query if processed_query is not None else base_query.filter(False)
                else:
                    # 默认情况
                    query = pending_query if pending_query is not None else base_query.filter(False)

            # 应用排序
            if filters.get('sort'):
                sort_param = filters['sort'].split(',')
                if len(sort_param) > 1:
                    if sort_param[0] == "version_projects":
                        if sort_param[1] == 'desc':
                            query = query.order_by(Defect.version_id.desc())
                        else:
                            query = query.order_by(Defect.version_id.asc())
                    elif sort_param[0] == "stage_types_name":
                        query = query.join(DefectStage.stage_type_ref)
                        if sort_param[1] == 'desc':
                            query = query.order_by(DefectStageType.stage_order.desc())
                        else:
                            query = query.order_by(DefectStageType.stage_order.asc())
                    elif sort_param[0] == "severity":
                        if sort_param[1] == 'desc':
                            query = query.order_by(Defect.severity.desc())
                        else:
                            query = query.order_by(Defect.severity.asc())
                    elif sort_param[0] == "reproducible":
                        if sort_param[1] == 'desc':
                            query = query.order_by(Defect.defect_reproducibility.desc())
                        else:
                            query = query.order_by(Defect.defect_reproducibility.asc())
                    elif sort_param[0] == "days":
                        if sort_param[1] == 'desc':
                            query = query.order_by(Defect.created_time.desc())
                        else:
                            query = query.order_by(Defect.created_time.asc())

            # 最终查询 - 确保去重
            final_query = query.distinct()

            # 获取所有数据（不分页）
            defects = final_query.order_by(Defect.updated_time.desc()).all()

            # 为每个缺陷添加额外字段（与defect_list相同）
            version_ids = []
            project_ids = []
            for defect in defects:
                if defect.current_stage and defect.current_stage.stage_type_ref:
                    defect.stage_name = defect.current_stage.stage_type_ref.stage_name
                else:
                    defect.stage_name = None

                defect.status_name = STATUS_MAPPING.get(defect.status, '未知')

                # 获取严重程度显示名称
                defect.severity_display = defect.severity

                # 获取可重现性显示名称
                defect.reproducible_display = defect.defect_reproducibility

                if defect.version_id is not None:
                    version_ids.append(defect.version_id)
                else:
                    project_ids.append(defect.project_id)

            # 获取产品线/版本信息
            project_line = {}
            tech_group = {}
            if version_ids:
                project_line, _ = ProductLineService.get_versions_by_ids(version_ids)
            if project_ids:
                tech_group, _ = TechGroupService.get_projects_by_ids(project_ids)

            for defect in defects:
                if defect.version_id is not None:
                    defect.product_or_version = project_line.get(defect.version_id, '')
                else:
                    defect.product_or_version = tech_group.get(defect.project_id, '')

                current_date = datetime.now()
                # 计算天数差（向上取整）
                defect.days_passed = (current_date - defect.created_time).days + 1

                # 获取创建人姓名（假设有User模型）
                if defect.creator:
                    defect.creator_name = defect.creator.real_name  # 根据实际情况调整
                else:
                    defect.creator_name = ''

                # 获取当前处理人姓名
                if defect.current_stage and defect.current_stage.assignee:
                    defect.assigned_to_name = defect.current_stage.assignee.real_name  # 根据实际情况调整
                else:
                    defect.assigned_to_name = ''

            return defects

        except Exception as e:
            current_app.logger.error(f"获取导出数据时发生错误: {str(e)}")
            raise

    @staticmethod
    def prepare_excel_data(defects, base_url=None, defect_detail_endpoint=None):
        """准备Excel数据，包含缺陷ID和详情链接"""
        data = []

        for defect in defects:
            # 构建详情链接
            defect_detail_url = ''
            if defect.defect_type:
                defect_detail_url = f"{base_url}/defect/{defect.defect_type}/{defect.id}"
            else:
                defect_detail_url = f"{base_url}/defect/{defect.id}"
            # if base_url and defect_detail_endpoint and hasattr(defect, 'id'):
            #     try:
            #         # 使用url_for生成完整的URL
            #         defect_detail_url = url_for(defect_detail_endpoint, defect_id=defect.id, _external=True)
            #     except:
            #         # 如果url_for失败，手动构建URL
            #         defect_detail_url = f"{base_url}/defect/{defect.id}"

            row = {
                'defect_id': defect.id,  # 缺陷ID
                'defect_number': defect.defect_number or '',
                'title': defect.title or '',
                'product_or_version': getattr(defect, 'product_or_version', '') or '',
                'stage_name': getattr(defect, 'stage_name', '') or '',
                'severity_display': getattr(defect, 'severity_display', '') or '',
                'reproducible_display': getattr(defect, 'reproducible_display', '') or '',
                'days_passed': getattr(defect, 'days_passed', 0) or 0,
                'status_name': getattr(defect, 'status_name', '') or '',
                'creator_name': getattr(defect, 'creator_name', '') or '',
                'assigned_to_name': getattr(defect, 'assigned_to_name', '') or '',
                'created_time': defect.created_time.strftime('%Y-%m-%d %H:%M:%S') if defect.created_time else '',
                'updated_time': defect.updated_time.strftime('%Y-%m-%d %H:%M:%S') if defect.updated_time else '',
                'description': defect.description or '',
                'defect_detail_url': defect_detail_url  # 详情链接
            }
            data.append(row)

        return data

