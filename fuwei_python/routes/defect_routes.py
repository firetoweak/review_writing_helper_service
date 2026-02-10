# routes/defect_routes.py
import re
from importlib.metadata import version
from io import BytesIO

import pandas as pd
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, g, current_app, session, \
    request, send_file

# from flask_login import login_required, current_user
from datetime import datetime

from oss2.exceptions import status
from sqlalchemy.exc import SQLAlchemyError
import json

from conf.config import app_config
from conf.db import db
from constants.message_types import MessageTypes
from models.ai_sug_score.model import AiSugScore
from models.defect_message.model import DefectMessage
from models.users.models import User
from services import defect_services
from services.defect_email_service import DefectEmailService
from services.defect_message_service import DefectMessageService, MessageCreator
from services.defect_services import DefectWorkflowService, DefectService, DefectStageService, DefectStageDataService, \
    DefectSolutionDivisionService, DefectFlowHistoryService, DefectLocaleInvitationService, DefectStaticsService, \
    DefectExportService
from models.defect.model import DefectStatus, StageStatus, DataType, Defect, DefectSeverity, \
    DefectReproducibility, DefectStage, DefectSolutionDivision, DefectStageType, \
    InvitationStatus, DefectLocaleInvitation, DefectStageCombineRecord, DefectFlowHistory, ActionType, STATUS_MAPPING
from common.Ai import Ai
from services.inner_service import InnerSrvice, ErrorCode
from services.product_line_services import ProductLineService
from services.project_member_services import ProjectMemberService
from services.role_services import RoleService, UserRoleService
from services.tech_group_service import TechGroupService

defect_bp = Blueprint('defect', __name__)


@defect_bp.route('/api/defect_severity_options')
def get_defect_severity_options():
    """获取缺陷级别选项"""
    options = [{'value': member.name, 'text': member.value}
               for member in DefectSeverity]
    return jsonify(options)


@defect_bp.route('/api/defect_reproducibility_options')
def get_defect_reproducibility_options():
    """获取缺陷重现性选项"""
    options = [{'value': member.name, 'text': member.value}
               for member in DefectReproducibility]
    return jsonify(options)


@defect_bp.route('/')
@UserRoleService.check_global_roles(
    allowed_roles=['all'],  # 所有角色均能访问
    template='defect/defect_levels.html',
    json_response=False
)
def defect_list():
    """缺陷列表页面"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        filters = {
                   'search': request.values.get('search', ''),
                   'assigned_to': request.args.get('assigned_to', ''),
                   'completed_by': request.args.get('completed_by', ''),
                   'deal_status': request.values.get('deal_status', ''),
                   'version_projects':request.values.get('version_projects', 'all'),
                   'stage_types_name': request.args.get('stage_types_name', ''),
                   'severity': request.args.get('severity', ''),
                   'reproducible': request.args.get('reproducible', ''),
                   'sort': request.args.get('sort', ''),
                   'defect_type':request.args.get('defect_type', ''),
        }
        defects,stage_types_name,pagination,version_projects,processed_num,pending_num = DefectService.defect_list(page,per_page,filters,g.user_id,g.admin_user_id)
        dropdown_states = {}
        for k in filters:
            if k in ['reproducible','severity','stage_types_name','version_projects'] and filters[k] !="":
                state = {
                    "all": False,
                    "items": {}
                }
                filter_list = filters[k].split(',')
                for filter_val in filter_list:
                    state["items"][filter_val] = True
                dropdown_states[k] = state
        if session['role_select'] =="流程使用者":
            add_button = 1
        else:
            add_button = 0
        return render_template('defect/list.html',
                               filters=filters,
                               processed_num = processed_num,
                               pending_num = pending_num,
                               defects=defects,
                               stage_types_name= json.dumps(stage_types_name,ensure_ascii=False),  # 传递所有阶段类型
                               DefectStatus=DefectStatus,
                               pagination=pagination,
                               version_projects = json.dumps(version_projects,ensure_ascii=False),
                               severity=json.dumps([DefectSeverity.CRITICAL_DEFECTS.value,DefectSeverity.MAJOR_DEFECTS.value,DefectSeverity.MINOR_DEFECTS.value,DefectSeverity.SUGGESTION_DEFECTS.value],ensure_ascii=False),
                               reproducible = json.dumps([DefectReproducibility.ALWAYS_REPRODUCIBLE.value,DefectReproducibility.CONDITIONALLY_REPRODUCIBLE.value,DefectReproducibility.RARELY_REPRODUCIBLE.value]),
                               chosen_dropdown_states = json.dumps(dropdown_states,ensure_ascii=False),
                               add_button = add_button
                               )
    except SQLAlchemyError as e:
        flash('获取缺陷列表时发生错误', 'error')
        return render_template('defect/list.html', defects=[])


# Excel导出接口
# 在export_defects函数中更新列映射和数据处理逻辑
@defect_bp.route('/export')
@UserRoleService.check_global_roles(
    allowed_roles=['all'],
    template='defect/list.html',
    json_response=False
)
def export_defects():
    """导出缺陷列表到Excel"""
    try:
        # 获取与列表页面相同的筛选条件
        filters = {
            'search': request.values.get('search', ''),
            'assigned_to': request.args.get('assigned_to', ''),
            'completed_by': request.args.get('completed_by', ''),
            'deal_status': request.values.get('deal_status', ''),
            'version_projects': request.values.get('version_projects', 'all'),
            'stage_types_name': request.args.get('stage_types_name', ''),
            'severity': request.args.get('severity', ''),
            'reproducible': request.args.get('reproducible', ''),
            'defect_type': request.args.get('defect_type', ''),
        }

        # 获取所有数据（不分页）
        defects = DefectExportService.get_defects_for_export(filters, g.user_id, g.admin_user_id)

        # 获取当前请求的主机信息和URL前缀，用于构建完整的详情链接
        base_url = request.host_url.rstrip('/')
        # 假设缺陷详情页的路由是 'defect.defect_detail'
        defect_detail_endpoint = 'defect.defect_detail'

        # 准备Excel数据，传入base_url和defect_detail_endpoint用于构建链接
        excel_data = DefectExportService.prepare_excel_data(defects, base_url, defect_detail_endpoint)

        # 创建DataFrame
        df = pd.DataFrame(excel_data)

        # 重命名列名为中文
        column_mapping = {
            'defect_id': '缺陷ID',
            'defect_number': '缺陷编号',
            'title': '缺陷标题',
            'product_or_version': '所属产品线/版本',
            'stage_name': '当前阶段',
            'severity_display': '严重程度',
            'reproducible_display': '可重现性',
            'days_passed': '创建天数',
            'status_name': '状态',
            'creator_name': '创建人',
            'assigned_to_name': '当前处理人',
            'created_time': '创建时间',
            'updated_time': '更新时间',
            'description': '缺陷描述',
            'defect_detail_url': '详情链接'  # 新增详情链接列
        }

        # 只保留实际存在的列
        existing_columns = {k: v for k, v in column_mapping.items() if k in df.columns}
        df = df.rename(columns=existing_columns)

        # 调整列顺序，将缺陷ID放在第一列
        desired_columns = [
            '缺陷ID', '缺陷编号', '缺陷标题', '所属产品线/版本', '当前阶段', '严重程度',
            '可重现性', '创建天数', '状态', '创建人', '当前处理人',
            '创建时间', '更新时间', '缺陷描述', '详情链接'
        ]

        # 只保留存在的列
        final_columns = [col for col in desired_columns if col in df.columns]
        df = df[final_columns]

        # 创建Excel写入器
        output = BytesIO()

        # 使用ExcelWriter，设置引擎为openpyxl
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='缺陷列表')

            # 获取工作表
            workbook = writer.book
            worksheet = writer.sheets['缺陷列表']

            # 为详情链接列添加超链接
            from openpyxl.utils import get_column_letter

            # 找到详情链接列的索引
            link_col_idx = None
            for idx, col in enumerate(final_columns, start=1):
                if col == '详情链接':
                    link_col_idx = idx
                    break

            if link_col_idx:
                # 为每一行的链接列设置超链接
                for row in range(2, len(df) + 2):  # 从第2行开始（跳过标题行）
                    cell = worksheet.cell(row=row, column=link_col_idx)
                    url = cell.value
                    if url and url.startswith(('http://', 'https://')):
                        cell.value = '点击查看详情'
                        cell.hyperlink = url
                        cell.style = 'Hyperlink'

            # 自动调整列宽（近似值）
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        # 如果是超链接单元格，使用显示文本长度
                        cell_value = '点击查看详情' if cell.hyperlink else cell.value
                        if len(str(cell_value)) > max_length:
                            max_length = len(str(cell_value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)  # 最大宽度限制为50
                worksheet.column_dimensions[column_letter].width = adjusted_width

        output.seek(0)

        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'缺陷列表_导出_{timestamp}.xlsx'

        # 返回Excel文件
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        current_app.logger.error(f"导出Excel时发生错误: {str(e)}")
        flash('导出Excel时发生错误', 'error')
        return redirect(url_for('defect.defect_list'))



@defect_bp.route('/exception_handling_defect_list')
@UserRoleService.check_global_roles(
    allowed_roles=['global_admin',],
    template='defect/defect_levels.html',
    json_response=False
)
def exception_handling_defect_list():
    """缺陷列表页面"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        filters = {
            'search': request.args.get('search', ''),
            'assigned_to': request.args.get('assigned_to', ''),
            'completed_by': request.args.get('completed_by', ''),
            'deal_status': request.values.get('deal_status', ''),
            'version_projects': request.values.get('version_projects', 'all'),
            'stage_types_name': request.args.get('stage_types_name', ''),
            'severity': request.args.get('severity', ''),
            'reproducible': request.args.get('reproducible', ''),
            'sort': request.args.get('sort', ''),
            'defect_type': request.args.get('defect_type', ''),
        }
        defects, stage_types_name, pagination, version_projects, processed_num, pending_num = DefectService.defect_list(
            page, per_page, filters, g.user_id, g.admin_user_id)
        dropdown_states = {}
        for k in filters:
            if k in ['reproducible', 'severity', 'stage_types_name', 'version_projects'] and filters[k] != "":
                state = {
                    "all": False,
                    "items": {}
                }
                filter_list = filters[k].split(',')
                for filter_val in filter_list:
                    state["items"][filter_val] = True
                dropdown_states[k] = state
        company_user_list = User.get_company_users_by_user_id(g.user_id)
        return render_template('defect/exception_handling_defect_list.html',
                               filters_version_projects=filters['version_projects'],
                               filters=filters,
                               is_global_admin=g.is_global_admin,
                               is_global_viewer=g.is_global_viewer,
                               processed_num=processed_num,
                               pending_num=pending_num,
                               defects=defects,
                               company_user_list=company_user_list,
                               stage_types_name=json.dumps(stage_types_name, ensure_ascii=False),  # 传递所有阶段类型
                               DefectStatus=DefectStatus,
                               pagination=pagination,
                               version_projects=json.dumps(version_projects, ensure_ascii=False),
                               severity=json.dumps(
                                   [DefectSeverity.CRITICAL_DEFECTS.value, DefectSeverity.MAJOR_DEFECTS.value,
                                    DefectSeverity.MINOR_DEFECTS.value, DefectSeverity.SUGGESTION_DEFECTS.value],
                                   ensure_ascii=False),
                               reproducible=json.dumps([DefectReproducibility.ALWAYS_REPRODUCIBLE.value,
                                                        DefectReproducibility.CONDITIONALLY_REPRODUCIBLE.value,
                                                        DefectReproducibility.RARELY_REPRODUCIBLE.value]),
                               chosen_dropdown_states=json.dumps(dropdown_states, ensure_ascii=False),
                               )
    except SQLAlchemyError as e:
        flash('获取缺陷列表时发生错误', 'error')
        return render_template('defect/exception_handling_defect_list.html', defects=[])


@defect_bp.route('/statistics', methods=['GET', 'POST'])
@UserRoleService.check_global_roles(
    allowed_roles=['global_admin', 'global_viewer', 'project_admin', 'project_viewer'],
    template='defect/defect_levels.html',
    json_response=False
)
def get_statistics():
    """创建缺陷页面，支持创建草稿和创建正式缺陷单（将进入审核缺陷描述阶段）"""
    # 获取当前用户ID
    user_id = g.user_id
    if not user_id:
        return jsonify({'error': '用户未认证'}), 401
    if request.method == 'GET':
        return render_template('defect/statistics.html', filters_version_projects = '')

def parse_project_version_id(project_version_id):
    """
    解析项目版本ID，返回version_id和project_id

    参数:
        project_version_id (str): 项目版本ID字符串

    返回值:
        tuple: 包含version_id和project_id的元组 (version_id, project_id)
    """
    version_id = None
    project_id = None

    if project_version_id:
        if project_version_id.startswith('v3'):
            version_id = int(project_version_id.replace('v3-', '').strip())
        elif project_version_id.startswith('p3'):
            project_id = int(project_version_id.replace('p3-', '').strip())

    return version_id, project_id

@defect_bp.route('/create', methods=['GET', 'POST'])
def create_defect():
    """创建缺陷页面，支持创建草稿和创建正式缺陷单（将进入审核缺陷描述阶段）"""
    # 获取当前用户ID
    user_id = g.user_id
    if not user_id:
        return jsonify({'error': '用户未认证'}), 401
    company_user_list = User.get_company_users_by_user_id(g.user_id)
    ai_done_act = request.form.get('ai_done_act', "")
    if request.method == 'GET':
        return render_template('defect/create.html', user_list=company_user_list)
    current_app.logger.info(f'create_defect ......')
    try:
        title = request.form.get('title')
        description = request.form.get('description')
        severity = request.form.get('severity')
        defect_reproducibility = request.form.get('defect_reproducibility')
        project_version_id = request.form.get('project_version_id')
        is_draft = request.form.get('is_draft')
        is_draft_flag = True
        if is_draft and is_draft.lower() == 'true':
            status = 'DefectStatus.DRAFT'
        else:
            status = 'DefectStatus.OPEN'  # 默认为 OPEN
            is_draft_flag = False

        if not is_draft_flag and not project_version_id:
            message = '请选择一个版本或项目'
            flash(message, 'error')
        version_id, project_id = parse_project_version_id(project_version_id)

        current_app.logger.debug(f'project_version_id: {project_version_id}')
        current_app.logger.debug(f'severity: {severity}')
        current_app.logger.debug(f'defect_reproducibility: {defect_reproducibility}')

        # 验证必要字段（草稿保存不需要验证所有必填字段）
        if not is_draft_flag and not all([title, description, severity, defect_reproducibility]):
            flash('非暂存，请填写所有必填字段', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

        # 创建新的缺陷问题单（同时创建初始阶段），支持草稿或正常缺陷单，并记录流程历史记录
        defect = DefectService.create_defect(
            title=title,
            description=description,
            severity=severity,
            defect_reproducibility=defect_reproducibility,
            creator_id=user_id,
            version_id=version_id,
            project_id=project_id,
            status=status
        )
        if not defect:
            if status == 'DefectStatus.DRAFT':
                message = '创建缺陷描述草稿失败'
                flash(message, 'error')
            else:
                message = '创建缺陷描述失败'
            flash(message, 'error')
            return redirect(url_for('defect.defect_list'))
        # 无论是否为草稿，均需要提交缺陷描述数据
        defect,is_change = DefectWorkflowService.submit_defect_description(defect.title, defect.description, defect.severity,
                                                                 defect.defect_reproducibility,
                                                                 user_id, defect.version_id, defect.project_id,
                                                                 defect.id, is_draft_flag)
        if not defect:
            message = '提交缺陷描述数据失败'
            flash(message, 'error')
            return redirect(url_for('defect.defect_list'))

        # 提交事务
        db.session.commit()
        if status == 'DefectStatus.DRAFT':
            message = '创建缺陷描述草稿成功（暂不进入测试经理审核描述阶段）'
            flash(message, 'success')
            return redirect(url_for('defect.defect_detail', defect_id=defect.id,ai_done_act=ai_done_act))
        else:
            message = '创建缺陷描述成功，等待AI评估...'
            flash(message, 'success')
            return redirect(url_for('defect.defect_detail', defect_id=defect.id,ai_done_act=ai_done_act,is_change=is_change))

    except Exception as e:
        db.session.rollback()
        flash(f'创建缺陷时发生错误: {str(e)}', 'error')
        return render_template('defect/create.html', user_list=company_user_list)


@defect_bp.route('/create_simplified', methods=['GET', 'POST'])
def create_simplified_defect():
    """简化版DTS 创建缺陷页面，支持创建草稿和创建正式缺陷单（将进入审核缺陷描述阶段）"""
    # 获取当前用户ID
    user_id = g.user_id
    if not user_id:
        if request.method == 'POST':
            return jsonify({'code': 1, 'message': '用户未认证'}), 401
        else:
            return jsonify({'code': 1, 'message': '用户未认证'}), 401

    company_user_list = User.get_company_users_by_user_id(g.user_id)

    # GET 请求 - 返回页面
    if request.method == 'GET':
        return render_template('defect/create_simplified.html', user_list=company_user_list,defect_type="simplified")

    # POST 请求 - 处理创建缺陷逻辑，返回JSON
    current_app.logger.info(f'create_defect ......')
    try:
        title = request.form.get('title')
        description = request.form.get('description')
        severity = request.form.get('severity')
        defect_reproducibility = request.form.get('defect_reproducibility')
        project_version_id = request.form.get('project_version_id')
        is_draft = request.form.get('is_draft')
        ai_done_act = request.form.get('ai_done_act', "")

        is_draft_flag = True
        if is_draft and is_draft.lower() == 'true':
            status = 'DefectStatus.DRAFT'
        else:
            status = 'DefectStatus.OPEN'  # 默认为 OPEN
            is_draft_flag = False

        if not is_draft_flag and not project_version_id:
            return jsonify({
                'code': 1,
                'message': '请选择一个版本或项目'
            }), 400

        version_id, project_id = parse_project_version_id(project_version_id)

        current_app.logger.debug(f'project_version_id: {project_version_id}')
        current_app.logger.debug(f'severity: {severity}')
        current_app.logger.debug(f'defect_reproducibility: {defect_reproducibility}')

        # 验证必要字段（草稿保存不需要验证所有必填字段）
        if not is_draft_flag and not all([title, description, severity, defect_reproducibility]):
            return jsonify({
                'code': 1,
                'message': '非暂存，请填写所有必填字段'
            }), 400

        # 创建新的缺陷问题单（同时创建初始阶段），支持草稿或正常缺陷单，并记录流程历史记录
        defect = DefectService.create_defect(
            title=title,
            description=description,
            severity=severity,
            defect_reproducibility=defect_reproducibility,
            creator_id=user_id,
            version_id=version_id,
            project_id=project_id,
            status=status,
            defect_type='simplified'
        )

        if not defect:
            message = '创建缺陷描述草稿失败' if status == 'DefectStatus.DRAFT' else '创建缺陷描述失败'
            return jsonify({
                'code': 1,
                'message': message
            }), 500

        # 创建各个阶段
        cause_analysis_stage = DefectStageService.create_next_stage(
            defect_id=defect.id,
            stage_type_key="cause_analysis",
            assigned_to=g.user_id,
            previous_stage_id=defect.current_stage_id,
            user_id=g.user_id
        )
        current_app.logger.debug(f'defect.current_stage_id: {defect.current_stage_id}')
        db.session.flush()
        current_app.logger.debug(f'cause_analysis_stage.id: {cause_analysis_stage.id}')

        developer_solution_stage = DefectStageService.create_next_stage(
            defect_id=defect.id,
            stage_type_key="developer_solution",
            assigned_to=g.user_id,
            previous_stage_id=cause_analysis_stage.id,
            user_id=g.user_id
        )
        db.session.flush()
        current_app.logger.debug(f'developer_solution_stage.id: {developer_solution_stage.id}')

        tester_regression_stage = DefectStageService.create_next_stage(
            defect_id=defect.id,
            stage_type_key="tester_regression",
            assigned_to=g.user_id,
            previous_stage_id=developer_solution_stage.id,
            user_id=g.user_id
        )

        # 设置缺陷当前阶段id
        defect_description_stage = DefectStageService.get_stage_by_defect_and_type(defect.id, 'defect_description')
        defect.current_stage_id = defect_description_stage.id

        # 无论是否为草稿，均需要提交缺陷描述数据
        defect, is_change = DefectWorkflowService.submit_defect_description(
            defect.title, defect.description, defect.severity,
            defect.defect_reproducibility,
            user_id, defect.version_id, defect.project_id,
            defect.id, is_draft_flag
        )

        # 提交事务
        db.session.commit()
        current_app.logger.debug(f'tester_regression_stage.id: {tester_regression_stage.id}')
        detail_url = 'defect.defect_detail_simplified'

        if status == 'DefectStatus.DRAFT':
            return jsonify({
                'code': 0,
                'message': '创建缺陷描述草稿成功',
                'data': {
                    'redirect_url': url_for(detail_url, defect_id=defect.id, ai_done_act=ai_done_act, stage_type="defect_description"),                    'defect_id': defect.id
                }
            })
        else:
            return jsonify({
                'code': 0,
                'message': '创建缺陷描述成功，等待AI评估...',
                'data': {
                    'redirect_url': url_for(detail_url, defect_id=defect.id, ai_done_act=ai_done_act,
                                            is_change=is_change,stage_type="defect_description"),
                    'defect_id': defect.id,
                    'is_change': is_change
                }
            })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'创建缺陷时发生错误: {str(e)}')
        return jsonify({
            'code': 1,
            'message': f'创建缺陷时发生错误: {str(e)}'
        }), 500

@defect_bp.route('/api/company_users', methods=['GET'])
def get_company_users():
    """获取公司用户列表"""
    user_list = User.get_company_users_by_user_id(g.user_id)
    return jsonify(user_list)


@defect_bp.route('/create_simplified2', methods=['GET', 'POST'])
def create_simplified2_defect():
    """简化版DTS 创建缺陷页面，支持创建草稿和创建正式缺陷单（将进入审核缺陷描述阶段）"""
    # 获取当前用户ID
    user_id = g.user_id
    if not user_id:
        if request.method == 'POST':
            return jsonify({'code': 1, 'message': '用户未认证'}), 401
        else:
            return jsonify({'code': 1, 'message': '用户未认证'}), 401

    company_user_list = User.get_company_users_by_user_id(g.user_id)

    # GET 请求 - 返回页面
    if request.method == 'GET':
        return render_template('defect/create_simplified2.html', user_list=company_user_list, defect_type="simplified2",
                               now_page="create_simplified2")

    # POST 请求 - 处理创建缺陷逻辑，返回JSON
    current_app.logger.info(f'create_defect ......')
    try:
        # 判断请求数据格式
        if request.is_json:
            # 从 JSON 中获取数据
            data = request.get_json()
            title = data.get('title')
            description = data.get('description', '').strip()
            severity = data.get('severity')
            defect_reproducibility = data.get('defect_reproducibility')
            project_version_id = data.get('project_version_id')
            is_draft = data.get('is_draft')
            ai_done_act = data.get('ai_done_act', "")

            # 获取阶段责任人设置
            stage_assignments_json = data.get('stage_assignments', '{}')
        else:
            # 从 form 中获取数据（兼容原有的表单提交）
            title = request.form.get('title')
            description = request.form.get('description', '').strip()
            severity = request.form.get('severity')
            defect_reproducibility = request.form.get('defect_reproducibility')
            project_version_id = request.form.get('project_version_id')
            is_draft = request.form.get('is_draft')
            ai_done_act = request.form.get('ai_done_act', "")

            # 获取阶段责任人设置
            stage_assignments_json = request.form.get('stage_assignments', '{}')

        stage_assignments = {}
        if stage_assignments_json:
            try:
                stage_assignments = json.loads(stage_assignments_json)
            except json.JSONDecodeError as e:
                current_app.logger.error(f'解析阶段责任人设置失败: {str(e)}')

        is_draft_flag = True
        if is_draft and is_draft.lower() == 'true':
            status = 'DefectStatus.DRAFT'
        else:
            status = 'DefectStatus.OPEN'  # 默认为 OPEN
            is_draft_flag = False

        if not is_draft_flag and not project_version_id:
            return jsonify({
                'code': 1,
                'message': '请选择一个版本或项目'
            }), 400

        version_id, project_id = parse_project_version_id(project_version_id)

        current_app.logger.debug(f'project_version_id: {project_version_id}')
        current_app.logger.debug(f'severity: {severity}')
        current_app.logger.debug(f'defect_reproducibility: {defect_reproducibility}')
        current_app.logger.debug(f'stage_assignments: {stage_assignments}')

        # 验证必要字段（草稿保存不需要验证所有必填字段）
        if not is_draft_flag and not all([title, description, severity, defect_reproducibility]):
            return jsonify({
                'code': 1,
                'message': '非暂存，请填写所有必填字段'
            }), 400

        # 创建新的缺陷问题单（同时创建初始阶段），支持草稿或正常缺陷单，并记录流程历史记录
        defect = DefectService.create_defect(
            title=title,
            description=description,
            severity=severity,
            defect_reproducibility=defect_reproducibility,
            creator_id=user_id,
            version_id=version_id,
            project_id=project_id,
            status=status,
            defect_type='simplified2'
        )

        if not defect:
            message = '创建缺陷描述草稿失败' if status == 'DefectStatus.DRAFT' else '创建缺陷描述失败'
            return jsonify({
                'code': 1,
                'message': message
            }), 500

        # 使用阶段责任人设置创建各个阶段
        # 缺陷描述阶段（使用传入的责任人或当前用户）
        defect_description_assignee = stage_assignments.get('defect_description', user_id)
        cause_analysis_assignee = stage_assignments.get('cause_analysis', user_id)
        developer_solution_assignee = stage_assignments.get('developer_solution', user_id)
        tester_regression_assignee = stage_assignments.get('tester_regression', user_id)

        # 获取缺陷描述阶段并更新责任人
        defect_description_stage = DefectStageService.get_stage_by_defect_and_type(defect.id, 'defect_description')
        if defect_description_stage:
            defect_description_stage.assigned_to = defect_description_assignee
        else:
            return jsonify({
                'code': 1,
                'message': f'创建缺陷时发生错误: 缺陷描述阶段不存在。'
            }), 500
        # 创建原因分析阶段
        cause_analysis_stage = DefectStageService.create_next_stage(
            defect_id=defect.id,
            stage_type_key="cause_analysis",
            assigned_to=cause_analysis_assignee,
            previous_stage_id=defect_description_stage.id,
            user_id=user_id
        )
        current_app.logger.debug(f'defect.current_stage_id: {defect.current_stage_id}')
        db.session.flush()
        current_app.logger.debug(f'cause_analysis_stage.id: {cause_analysis_stage.id}')

        # 创建解决措施阶段
        developer_solution_stage = DefectStageService.create_next_stage(
            defect_id=defect.id,
            stage_type_key="developer_solution",
            assigned_to=developer_solution_assignee,
            previous_stage_id=cause_analysis_stage.id,
            user_id=user_id
        )
        db.session.flush()
        current_app.logger.debug(f'developer_solution_stage.id: {developer_solution_stage.id}')

        # 创建回归测试阶段
        tester_regression_stage = DefectStageService.create_next_stage(
            defect_id=defect.id,
            stage_type_key="tester_regression",
            assigned_to=tester_regression_assignee,
            previous_stage_id=developer_solution_stage.id,
            user_id=user_id
        )
        db.session.flush()
        # 创建提出人确认阶段
        requester_confirm_stage = DefectStageService.create_next_stage(
            defect_id=defect.id,
            stage_type_key="requester_confirm",
            assigned_to=defect_description_assignee,
            previous_stage_id=tester_regression_stage.id,
            user_id=user_id
        )
        db.session.flush()
        # 设置缺陷当前阶段id
        defect.current_stage_id = defect_description_stage.id if defect_description_stage else defect.current_stage_id

        # 无论是否为草稿，均需要提交缺陷描述数据
        defect, _ = DefectWorkflowService.submit_defect_description(
            defect.title, defect.description, defect.severity,
            defect.defect_reproducibility,
            user_id, defect.version_id, defect.project_id,
            defect.id, is_draft_flag
        )
        is_change = "1"
        # 发送邮件
        '''
        email_content = DefectEmailService.get_general_defect_email_content(defect, "缺陷描述已提交", "原因分析")
        DESCRIPTION_CHANGED = f"【缺陷描述已提交，请处理原因分析】{defect.defect_number} - {defect.title}"
        email_subject = DESCRIPTION_CHANGED
        send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=cause_analysis_stage.assigned_to,
                                                            admin_user_id=g.admin_user_id,
                                                            current_user_id=g.user_id,
                                                            content=email_content,
                                                            title=email_subject)
        # 发送消息
        DefectMessageService.save_message(
            send_to_user_id=cause_analysis_stage.assigned_to,
            send_from_user_id=g.user_id,
            defect_id=defect.id,
            message_type=MessageTypes.DESCRIPTION_CHANGED,
        )
        '''
        # 提交事务
        db.session.commit()


        current_app.logger.debug(f'tester_regression_stage.id: {tester_regression_stage.id}')
        detail_url = 'defect.defect_detail_simplified2'
        if status == 'DefectStatus.DRAFT':
            return jsonify({
                'code': 0,
                'message': '创建缺陷描述草稿成功',
                'data': {
                    'redirect_url': url_for(detail_url, defect_id=defect.id, ai_done_act=ai_done_act,
                                            stage_type="simplified2"),
                    'defect_id': defect.id
                }
            })
        else:
            from_page = "create" if ai_done_act == "self" else ""
            return jsonify({
                'code': 0,
                'message': '创建缺陷描述成功，等待AI评估...',
                'data': {
                    'redirect_url': url_for(detail_url, defect_id=defect.id, ai_done_act=ai_done_act,
                                            is_change=is_change, stage_type="simplified2", from_page=from_page),
                    'defect_id': defect.id,
                    'is_change': is_change
                }
            })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'创建缺陷时发生错误: {str(e)}')
        return jsonify({
            'code': 1,
            'message': f'创建缺陷时发生错误: {str(e)}'
        }), 500

@defect_bp.route('/<int:defect_id>/<update_type>', methods=['GET'])
def defect_update(defect_id, update_type):
    """统一处理缺陷更新页面"""
    # 验证update_type的合法性
    valid_update_types = {
        'defect_description_update': 'defect/defect_description_update.html',
        'defect_cause_analysis_update': 'defect/defect_cause_analysis_update.html',
        'defect_developer_solution_update': 'defect/defect_developer_solution_update.html',
        'defect_tester_regression_update': 'defect/defect_tester_regression_update.html'
    }
    if update_type not in valid_update_types:
        flash('无效的更新类型', 'error')
        return redirect(url_for('defect.defect_list'))

    try:
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            flash('缺陷单不存在', 'error')
            return redirect(url_for('defect.defect_list'))

        stages = DefectStageService.get_stages_by_defect(defect_id)
        current_stage = DefectStageService.get_stage_by_id(defect.current_stage_id)
        stage_types_dict = DefectService.get_defect_stage_types_dict()
        current_stage_name = stage_types_dict.get(current_stage.stage_type)

        # 获取当前阶段数据
        stage_data = None
        if current_stage:
            stage_data_list = DefectStageDataService.get_all_stage_data_by_criteria(current_stage.id, None, True, None)
            stage_data = stage_data_list[0] if len(stage_data_list) > 0 else None
            if stage_data:
                current_app.logger.debug(f'stage_data.id: {stage_data.id}')

        # 检查当前用户是否是阶段负责人
        is_assignee = False
        if current_stage and g.user_id == current_stage.assigned_to:
            is_assignee = True

        # # 根据value获取key，用于前端选项自动选中
        # defect.severity = get_enum_key_by_value(DefectSeverity, defect.severity)
        # defect.defect_reproducibility = get_enum_key_by_value(DefectReproducibility, defect.defect_reproducibility)

        current_app.logger.debug(f'更新原因分析 显示的 严重程度 555: {defect.severity}')

        template_name = valid_update_types[update_type]
        return render_template(template_name,
                               defect=defect,
                               stages=stages,
                               current_stage=current_stage,
                               current_stage_name=current_stage_name,
                               stage_data=stage_data,
                               is_assignee=is_assignee,
                               DefectStatus=DefectStatus,
                               StageStatus=StageStatus,
                               DataType=DataType)

    except Exception as e:
        flash(f'进入更新页面发生错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))


@defect_bp.route('/<int:defect_id>/submit_defect_update_info', methods=['POST'])
def submit_defect_update_info(defect_id):
    """提交缺陷更新信息（用于缺陷描述被驳回后的 重新提交及暂存; 以及草稿状态的重新提交及暂存 ）"""
    current_app.logger.debug(f'提交缺陷更新信息: ...')
    # 获取当前用户ID
    user_id = g.user_id
    if not user_id:
        flash('用户未认证', 'error')
        return redirect(url_for('defect.defect_list'))

    detail_url = 'defect.defect_detail'
    try:
        # 检查缺陷是否存在
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            flash('缺陷单不存在', 'error')
            return redirect(url_for('defect.defect_list'))

        defect_type = defect.defect_type
        if defect_type == 'simplified':
            detail_url = 'defect.defect_detail_simplified'

        # 获取表单数据
        title = request.form.get('title')
        description = request.form.get('description')
        severity = request.form.get('severity')
        is_draft = request.form.get('is_draft')
        current_app.logger.info(f'submit_defect_update_info  is_draft: {is_draft}')
        defect_reproducibility = request.form.get('defect_reproducibility')
        project_version_id = request.form.get('project_version_id')
        # 检查是暂存还是更新缺陷（走流程）
        is_draft_flag = is_draft and is_draft.lower() == 'true'
        current_app.logger.info(f'is_draft_flag: {is_draft_flag}  description {description}')
        ai_done_act = request.form.get('ai_done_act','')
        if not is_draft_flag and not project_version_id:
            message = '请选择一个版本或项目'
            flash(message, 'error')
        version_id, project_id = parse_project_version_id(project_version_id)
        current_app.logger.debug(f'submit_defect_update_info  project_id: {project_id}')
        current_app.logger.debug(f'submit_defect_update_info  version_id: {version_id}')
        # 验证必要字段（草稿保存不需要验证所有必填字段）
        if not is_draft_flag and not all([title, description, severity, defect_reproducibility]):
            flash('请填写所有必填字段', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))

        # 设置默认值（如果是草稿且某些字段为空，则使用该缺陷单之前的值）
        if is_draft_flag:
            if not title:
                title = defect.title
            if not description:
                description = defect.description
            if not severity:
                severity = defect.severity.name if hasattr(defect.severity, 'name') else str(defect.severity)
            if not defect_reproducibility:
                defect_reproducibility = defect.defect_reproducibility.name if hasattr(defect.defect_reproducibility,
                                                                                       'name') else str(
                    defect.defect_reproducibility)

        # 更新缺陷信息
        updated_defect = DefectService.update_defect(
            defect_id=defect_id,
            title=title,
            description=description,
            severity=severity,
            defect_reproducibility=defect_reproducibility,
            version_id=version_id,
            project_id=project_id,
            updater_id=user_id,
            is_draft=is_draft_flag  # 添加is_draft参数到更新函数
        )

        if not updated_defect:
            flash('更新缺陷信息失败', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))

        # 如果不是草稿，则重新提交缺陷描述（进入测试经理审核流程）

        defect,is_change = DefectWorkflowService.submit_defect_description(
            defect_id=defect_id,
            title=title,
            description=description,
            severity=severity,
            defect_reproducibility=defect_reproducibility,
            creator_id=user_id,
            version_id=version_id,
            project_id=project_id,
            is_draft_flag=is_draft_flag
        )

        if not defect:
            flash('提交缺陷描述数据失败', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))

        db.session.commit()
        if is_draft_flag:
            flash('草稿保存成功', 'success')
        else:
            flash('缺陷信息已更新并重新提交审核，AI正在评估中，请稍后....', 'success')
        url = url_for(detail_url, defect_id=defect_id,ai_done_act=ai_done_act,is_change=is_change)
        return redirect(url)

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'提交缺陷更新信息时发生错误: {str(e)}')
        flash(f'提交缺陷更新信息时发生错误: {str(e)}', 'error')
        return redirect(url_for(detail_url, defect_id=defect_id))


@defect_bp.route('/<int:defect_id>/submit_defect_update_info-api', methods=['POST'])
def submit_defect_update_info_api(defect_id):
    """提交缺陷更新信息 API 版本（用于缺陷描述被驳回后的重新提交及暂存; 以及草稿状态的重新提交及暂存）- JSON API版本"""
    current_app.logger.debug(f'提交缺陷更新信息 API: defect_id={defect_id}')

    try:
        # 获取当前用户ID
        user_id = g.user_id
        if not user_id:
            return jsonify({
                'code': 1,
                'message': '用户未登录或会话已过期'
            }), 401

        # 获取请求数据（支持JSON和form格式）
        if request.is_json:
            data = request.get_json()
            title = data.get('title', '')
            description = data.get('description', '')
            severity = data.get('severity', '')
            is_draft = data.get('is_draft', 'false')
            defect_reproducibility = data.get('defect_reproducibility', '')
            project_version_id = data.get('project_version_id', '')
            ai_done_act = data.get('ai_done_act', '')
        else:
            title = request.form.get('title', '')
            description = request.form.get('description', '')
            severity = request.form.get('severity', '')
            is_draft = request.form.get('is_draft', 'false')
            defect_reproducibility = request.form.get('defect_reproducibility', '')
            project_version_id = request.form.get('project_version_id', '')
            ai_done_act = request.form.get('ai_done_act', '')

        current_app.logger.info(f'submit_defect_update_info_api is_draft: {is_draft}')
        current_app.logger.info(f'ai_done_act: {ai_done_act}')

        # 检查缺陷是否存在
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            return jsonify({
                'code': 1,
                'message': '指定的缺陷单不存在或已被删除'
            }), 404

        # 确定详情页面类型
        detail_url = f'/defect/simplified/{defect_id}'

        # 检查是暂存还是更新缺陷（走流程）
        is_draft_flag = is_draft and is_draft.lower() == 'true'
        current_app.logger.info(f'is_draft_flag: {is_draft_flag}')

        # 验证必要字段（草稿保存不需要验证所有必填字段）
        if not is_draft_flag and not project_version_id:
            return jsonify({
                'code': 1,
                'message': '请选择一个版本或项目'
            }), 400

        version_id, project_id = parse_project_version_id(project_version_id)
        current_app.logger.debug(f'submit_defect_update_info_api project_id: {project_id}')
        current_app.logger.debug(f'submit_defect_update_info_api version_id: {version_id}')

        # 验证必要字段（草稿保存不需要验证所有必填字段）
        if not is_draft_flag and not all([title, description, severity, defect_reproducibility]):
            return jsonify({
                'code': 1,
                'message': '请填写所有必填字段'
            }), 400

        # 设置默认值（如果是草稿且某些字段为空，则使用该缺陷单之前的值）
        if is_draft_flag:
            if not title:
                title = defect.title
            if not description:
                description = defect.description
            if not severity:
                severity = defect.severity.name if hasattr(defect.severity, 'name') else str(defect.severity)
            if not defect_reproducibility:
                defect_reproducibility = defect.defect_reproducibility.name if hasattr(defect.defect_reproducibility,
                                                                                       'name') else str(
                    defect.defect_reproducibility)
        # 获取原因分析第一责任人
        cause_analysis_user = DefectStageService.get_stage_user(defect_id, 'cause_analysis')
        defect_status = DefectStatus.OPEN
        if is_draft_flag and not cause_analysis_user:
            defect_status = DefectStatus.DRAFT
        # 更新缺陷信息
        updated_defect = DefectService.update_defect(
            defect_id=defect_id,
            title=title,
            description=description,
            severity=severity,
            defect_reproducibility=defect_reproducibility,
            version_id=version_id,
            project_id=project_id,
            updater_id=user_id,
            status=defect_status,
            is_draft=is_draft_flag
        )
        if not updated_defect:
            return jsonify({
                'code': 1,
                'message': '更新缺陷信息失败'
            }), 400

        # 如果不是草稿，则重新提交缺陷描述（进入测试经理审核流程）
        defect, is_change = DefectWorkflowService.submit_defect_description(
            defect_id=defect_id,
            title=title,
            description=description,
            severity=severity,
            defect_reproducibility=defect_reproducibility,
            creator_id=user_id,
            version_id=version_id,
            project_id=project_id,
            is_draft_flag=is_draft_flag
        )
        current_app.logger.debug('submit_defect_update_info-api submit_defect_description done')

        if not defect:
            return jsonify({
                'code': 1,
                'message': '提交缺陷描述数据失败'
            }), 400

        db.session.commit()

        # 构建成功响应
        if is_draft_flag:
            return jsonify({
                'code': 0,
                'message': '保存成功',
                'data': {
                    'defect_id': defect_id,
                    'status': 'draft_saved',
                    'redirect_url': url_for('defect.defect_detail_simplified', defect_id=defect.id, ai_done_act=ai_done_act,
                                            is_change=is_change,stage_type="defect_description"),
                    'ai_done_act': ai_done_act,
                    'is_change': is_change
                }
            })
        else:
            return jsonify({
                'code': 0,
                'message': '缺陷信息已更新并重新提交审核，AI正在评估中，请稍后...',
                'data': {
                    'defect_id': defect_id,
                    'status': 'submitted',
                    'redirect_url': url_for('defect.defect_detail_simplified', defect_id=defect.id, ai_done_act=ai_done_act,
                                            is_change=is_change,stage_type="defect_description"),
                    'ai_done_act': ai_done_act,
                    'is_change': is_change
                }
            })

    except ValueError as e:
        db.session.rollback()
        current_app.logger.error(f'数据验证错误: {str(e)}')
        return jsonify({
            'code': 1,
            'message': f'数据验证错误: {str(e)}'
        }), 400

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'api提交缺陷更新信息时发生错误: {str(e)}')
        return jsonify({
            'code': 1,
            'message': f'提交缺陷更新信息时发生错误: {str(e)}'
        }), 500

@defect_bp.route('/api/<int:defect_id>/duplicates')
def get_defect_duplicates(defect_id):
    """获取缺陷的重复缺陷信息 API"""
    defect = Defect.query.get_or_404(defect_id)
    duplicate_infos = DefectService.get_duplicate_defects_infos(defect)
    return jsonify({
        'success': True,
        'data': duplicate_infos
    })

@defect_bp.route('/<int:defect_id>')
def defect_detail(defect_id):
    """缺陷详情页面"""
    try:
        current_app.logger.debug(f'get detail for defect. ID:{defect_id}')
        defect = DefectService.get_defect_by_id(defect_id)
        current_user = User.get_user_by_id(g.user_id)
        if not defect:
            return render_template('defect/error.html',
                                   error_message=f'{current_user.company_name} 缺陷单不存在。',
                                   link_to_title='返回缺陷列表',
                                   redirect_url=url_for('defect.defect_list'))
        create_user = defect.creator
        current_app.logger.info(
            f'【current_user.user_id】: {current_user.user_id}, '
            f'【current_user.admin_user_id】: {current_user.admin_user_id}, '
            f'【defect.creator.admin_user_id】: {create_user.admin_user_id}')
        # 检查缺陷单是否为本公司的缺陷单，根据缺陷单的创建人判断

        # if create_user.admin_user_id == 0:
        #     return render_template('defect/error.html',
        #                            error_message='当前缺陷单为公司管理员创建，不符合实际业务场景。',
        #                            link_to_title='返回缺陷列表',
        #                            redirect_url=url_for('defect.defect_list'))
        if current_user.admin_user_id == 0:
            return render_template('defect/error.html',
                                   error_message='🎉 哇哦！发现一位尊贵的公司管理员！<br>'
                                                 '您可是要处理大事的大佬呢～<br>'
                                                 '这种小缺陷单就交给小伙伴们去处理吧！<br>'
                                                 '💼 您还是继续运筹帷幄，指点江山～',
                                   link_to_title='配置全板块管理员',
                                   redirect_url=url_for('global_settings.global_admin_list'))
        # if current_user.admin_user_id != create_user.admin_user_id:
        #     return render_template('defect/error.html',
        #                            error_message=f'{current_user.company_name} 缺陷单不存在。',
        #                            link_to_title='返回缺陷列表',
        #                            redirect_url=url_for('defect.defect_list'))
        project_version_name,project_version_id = defect_services.get_project_version(defect)
        stages = DefectStageService.get_stages_by_defect(defect_id)
        current_stage = DefectStageService.get_stage_by_id(defect.current_stage_id)
        current_stage_name = DefectWorkflowService.get_current_stage_name(defect)
        ai_done_act = request.args.get('ai_done_act','')
        current_app.logger.debug(f'current_stage.stage_type: {current_stage.stage_type}')
        current_app.logger.debug(f'current_stage.status: {current_stage.status}')

        # 获取各阶段数据
        stage_data = None  # 当前阶段数据
        if current_stage:
            current_app.logger.info(f'current_stage id: {current_stage.id}')
            stage_data_list = DefectStageDataService.get_all_stage_data_by_criteria(current_stage.id, None, True, None)
            stage_data = stage_data_list[0] if len(stage_data_list) > 0 else None
            if stage_data:
                current_app.logger.debug(f'stage_data.id: {stage_data.id}')
        source_defect = None
        if defect.duplicate_source_id:
            source_defect = DefectService.get_defect_by_id(defect.duplicate_source_id)
        # 检查当前用户是否是阶段负责人
        is_assignee = False
        if current_stage and g.user_id == current_stage.assigned_to:
            is_assignee = True
        current_user = User.get_user_by_id(g.user_id)
        is_test_manager = False
        test_manager_id = DefectWorkflowService.get_test_manager_id(defect)
        dev_manager_id = DefectWorkflowService.get_dev_manager_id(defect)
        if current_user.user_id == test_manager_id:
            is_test_manager = True
        is_dev_manager = False
        if current_user.user_id == dev_manager_id:
            is_dev_manager = True
        # 获取本缺陷单的所有 流程历史记录
        defect_flow_histories = DefectFlowHistoryService.get_flow_history(defect_id)
        current_app.logger.debug(f'len(defect_flow_histories): {len(defect_flow_histories)}')
        # 返回用户列表
        user_list = User.get_company_users_by_user_id(g.user_id)

        # 缺陷描述阶段（待 更新）
        description_data = DefectStageDataService.get_defect_description_data(defect_id)
        current_app.logger.debug(f'description_data length: {len(description_data)}')
        defect_description_list = []
        if description_data:
            content_dict = description_data[0].get('content')
            try:
                defect_description_list = json.loads(content_dict.get('description'))
                if defect_description_list:
                    current_app.logger.info( f"defect_description_list[0].get('title') : {defect_description_list[0].get('title')}")
                    current_app.logger.info(
                        f'current_stage status: {current_stage.status}  description_data status: {description_data[0].get("stage_status")}')
            except Exception as e:
                current_app.logger.error(f'2、description_data 数据格式不符合要求: {e}')


        if (current_stage.stage_type == 'defect_description' or current_stage.stage_type == 'draft_creation') and (
                current_stage.status == 'StageStatus.PENDING_UPDATE'
                or current_stage.status == 'StageStatus.DRAFT'
                or current_stage.status == 'StageStatus.IN_PROGRESS'
                or current_stage.status == 'StageStatus.EVALUATING'
        ):
            return render_template('defect/create.html',
                                   defect=defect,
                                   project_version_id=project_version_id,
                                   project_version_name=project_version_name,
                                   stages=stages,
                                   current_stage=current_stage,
                                   current_stage_name=current_stage_name,
                                   stage_data=stage_data,
                                   description_data=description_data,
                                   defect_description_list=defect_description_list,
                                   is_assignee=is_assignee,
                                   is_dev_manager=is_dev_manager,  # 是否为开发主管
                                   is_test_manager=is_test_manager,  # 是否为测试经理
                                   current_user=current_user,
                                   defect_flow_histories=defect_flow_histories,
                                   DefectStatus=DefectStatus,
                                   StageStatus=StageStatus,
                                   source_defect=source_defect,
                                   user_list=user_list,
                                   DataType=DataType)
        # 原因分析数据
        cause_analysis_data = DefectStageDataService.get_locale_invitation_data(defect_id)
        cause_analysis_ai = None
        if cause_analysis_data:
            defect_stage_id = cause_analysis_data[0]['defect_stage_id']
            cause_analysis_ai = DefectStageCombineRecord.query.filter(DefectStageCombineRecord.defect_stage_id==defect_stage_id).first()
        current_app.logger.debug(f'cause_analysis_data length: {len(cause_analysis_data)}')
        if cause_analysis_data:
            current_app.logger.debug(f"cause_analysis_data: {cause_analysis_data[0].get('content').get('analyses')}")
        analysis_data_list = []
        completed_analysis_data = DefectStageDataService.filter_completed_invitations(cause_analysis_data)
        current_app.logger.debug(f'len(completed_analysis_data): {len(completed_analysis_data)}')
        for data in completed_analysis_data:
            for item in data.get('content').get('analyses'):
                analysis_data_list.append(item)
        # 解决措施数据
        solution_ai = None
        solution_data = DefectStageDataService.get_solution_division_data(defect_id)
        if solution_data:
            defect_stage_id = solution_data[0]['defect_stage_id']
            solution_ai = DefectStageCombineRecord.query.filter(DefectStageCombineRecord.defect_stage_id==defect_stage_id).first()
        solution_data_list = []
        completed_solution_data = DefectStageDataService.filter_completed_divisions(solution_data)
        current_app.logger.debug(f'len(completed_solution_data): {len(completed_solution_data)}')
        for data in completed_solution_data:
            for item in data.get('content').get('solutions'):
                solution_data_list.append(item)
        current_app.logger.debug(f'solution_data_list: {solution_data_list}')
        current_app.logger.debug(f'solution_data: {solution_data}')
        test_result_data = DefectStageDataService.get_test_result_data(defect_id)
        print(f"test_result_data:{test_result_data}")
        test_result_data_list = []
        if test_result_data:
            content_dict = test_result_data[0].get('content')
            try:
                test_result_data_list = json.loads(content_dict.get('description'))
                if test_result_data_list:
                    current_app.logger.info( f"test_result_data_list[0].get('title') : {test_result_data_list[0].get('title')}")
                    current_app.logger.info(
                        f'current_stage status: {current_stage.status}  test_result_data status: {test_result_data[0].get("stage_status")}')
            except Exception as e:
                current_app.logger.error(f'test_result_data 数据格式不符合要求: {e}')


        # 获取当前阶段的分工信息（如果是developer_solution阶段）
        divisions = []
        if current_stage and current_stage.stage_type == "developer_solution":
            divisions = DefectSolutionDivision.query.filter_by(
                defect_stage_id=current_stage.id
            ).all()

        # 将 solution_data_list 与  divisions 关联起来


        cause_analysis_invitations = DefectLocaleInvitationService.get_cause_analysis_invitations(defect_id)  # 主处理人 在转处理后会发生变化，需要完善

        invitee_id_set = {invitation.invitee_id for invitation in cause_analysis_invitations}
        is_same_invitee = len(invitee_id_set) <= 1 # 多个邀请是否都针对同一人，这是一种特殊情况，前端已经排除了这种情况（批量邀请时不会多次选中同一用户）

        current_app.logger.info(f'len(invitations): {len(cause_analysis_invitations)}')

        solution_divisions = DefectSolutionDivisionService.get_solution_divisions_by_defect_id(defect_id)
        current_app.logger.info(f'len(solution_divisions): {len(solution_divisions)}')

        # 通过关系获取所有复制生成的问题单
        duplicate_defects_infos = DefectService.get_duplicate_defects_infos(defect)
        if f"self_res_{defect_id}" in session:
            self_ai_done = "1"
        else:
            self_ai_done = ""
        return render_template('defect/detail.html',
                               self_ai_done = self_ai_done,
                               defect=defect,
                               project_version_id=project_version_id,
                               project_version_name=project_version_name,
                               stages=stages,
                               current_stage=current_stage,
                               current_stage_name=current_stage_name,
                               stage_data=stage_data,
                               description_data=description_data,
                               defect_description_list=defect_description_list,
                               cause_analysis_data=cause_analysis_data,  # 原因分析数据  包含邀请人和被邀请人
                               cause_analysis_ai = cause_analysis_ai,
                               solution_ai = solution_ai,
                               analysis_data_list=analysis_data_list, # 已经完成分析的数据
                               solution_data=solution_data,  # 解决措施数据  包含分配人和被分配人
                               solution_data_list=solution_data_list,  # 已经提交的解决措施
                               is_same_invitee=is_same_invitee,
                               test_result_data=test_result_data,
                               test_result_data_list=test_result_data_list,
                               divisions=divisions,  # 传递分工信息
                               is_assignee=is_assignee,
                               is_dev_manager=is_dev_manager,  # 是否为开发主管
                               is_test_manager=is_test_manager,  # 是否为测试经理
                               current_user=current_user,
                               defect_flow_histories=defect_flow_histories,
                               DefectStatus=DefectStatus,
                               StageStatus=StageStatus,
                               source_defect=source_defect,
                               user_list=user_list,
                               cause_analysis_invitations=cause_analysis_invitations,
                               solution_divisions=solution_divisions,
                               duplicate_defects_infos=duplicate_defects_infos,
                               DataType=DataType)
    except Exception as e:
        return render_template('defect/error.html',
                               error_message=f'获取缺陷详情时发生错误: {str(e)}',
                               link_to_title='返回缺陷列表',
                               redirect_url=url_for('defect.role_proxy'))


@defect_bp.route('/simplified/<int:defect_id>')
def defect_detail_simplified(defect_id):
    """缺陷详情页面"""
    try:
        current_app.logger.debug(f'get detail for defect. ID:{defect_id}')
        defect = DefectService.get_defect_by_id(defect_id)
        current_user = User.get_user_by_id(g.user_id)
        if not defect:
            return render_template('defect/error.html',
                                   error_message=f'{current_user.company_name} 缺陷单不存在。',
                                   link_to_title='返回缺陷列表',
                                   redirect_url='/defect/?defect_type=simplified')
        defect_type = defect.defect_type
        create_user = defect.creator
        current_app.logger.info(
            f'【current_user.user_id】: {current_user.user_id}, '
            f'【current_user.admin_user_id】: {current_user.admin_user_id}, '
            f'【defect.creator.admin_user_id】: {create_user.admin_user_id}')
        # 检查缺陷单是否为本公司的缺陷单，根据缺陷单的创建人判断

        if create_user.admin_user_id == 0:
            return render_template('defect/error.html',
                                   error_message='当前缺陷单为公司管理员创建，不符合实际业务场景。',
                                   link_to_title='返回缺陷列表',
                                   redirect_url='/defect/?defect_type=simplified')
        if current_user.admin_user_id == 0:
            return render_template('defect/error.html',
                                   error_message='🎉 哇哦！发现一位尊贵的公司管理员！<br>'
                                                 '您可是要处理大事的大佬呢～<br>'
                                                 '这种小缺陷单就交给小伙伴们去处理吧！<br>'
                                                 '💼 您还是继续运筹帷幄，指点江山～',
                                   link_to_title='配置全板块管理员',
                                   redirect_url=url_for('global_settings.global_admin_list'))
        if current_user.admin_user_id != create_user.admin_user_id:
            return render_template('defect/error.html',
                                   error_message=f'{current_user.company_name} 缺陷单不存在。',
                                   link_to_title='返回缺陷列表',
                                   redirect_url='/defect/?defect_type=simplified')
        project_version_name,project_version_id = defect_services.get_project_version(defect)
        stages = DefectStageService.get_stages_by_defect(defect_id)
        current_stage = DefectStageService.get_stage_by_id(defect.current_stage_id)
        current_stage_name = DefectWorkflowService.get_current_stage_name(defect)
        ai_done_act = request.args.get('ai_done_act','')
        current_app.logger.debug(f'current_stage.stage_type: {current_stage.stage_type}')
        current_app.logger.debug(f'current_stage.status: {current_stage.status}')

        # 获取各阶段数据
        stage_data = None  # 当前阶段数据
        if current_stage:
            current_app.logger.info(f'current_stage id: {current_stage.id}')
            stage_data_list = DefectStageDataService.get_all_stage_data_by_criteria(current_stage.id, None, True, None)
            stage_data = stage_data_list[0] if len(stage_data_list) > 0 else None
            if stage_data:
                current_app.logger.debug(f'stage_data.id: {stage_data.id}')
        source_defect = None
        if defect.duplicate_source_id:
            source_defect = DefectService.get_defect_by_id(defect.duplicate_source_id)
        # 检查当前用户是否是阶段负责人
        is_assignee = False
        if current_stage and g.user_id == current_stage.assigned_to:
            is_assignee = True
        current_user = User.get_user_by_id(g.user_id)
        is_test_manager = False
        test_manager_id = DefectWorkflowService.get_test_manager_id(defect)
        dev_manager_id = DefectWorkflowService.get_dev_manager_id(defect)
        if current_user.user_id == test_manager_id:
            is_test_manager = True
        is_dev_manager = False
        if current_user.user_id == dev_manager_id:
            is_dev_manager = True
        # 获取本缺陷单的所有 流程历史记录
        defect_flow_histories = DefectFlowHistoryService.get_flow_history(defect_id)
        current_app.logger.debug(f'len(defect_flow_histories): {len(defect_flow_histories)}')
        # 返回用户列表
        user_list = User.get_company_users_by_user_id(g.user_id)

        # 缺陷描述阶段（待 更新）
        description_data = DefectStageDataService.get_defect_description_data(defect_id)
        print(f"description_data{description_data}")
        current_app.logger.debug(f'description_data length: {len(description_data)}')

        # if (current_stage.stage_type == 'defect_description' or current_stage.stage_type == 'draft_creation') and (
        #         current_stage.status == 'StageStatus.PENDING_UPDATE'
        #         or current_stage.status == 'StageStatus.DRAFT'
        #         or current_stage.status == 'StageStatus.IN_PROGRESS'
        #         or current_stage.status == 'StageStatus.EVALUATING'
        # ):
        #     pass
            # return render_template('defect/detail_simplified.html',
            #                        defect=defect,
            #                        project_version_id=project_version_id,
            #                        project_version_name=project_version_name,
            #                        stages=stages,
            #                        current_stage=current_stage,
            #                        current_stage_name=current_stage_name,
            #                        stage_data=stage_data,
            #                        description_data=description_data,
            #                        defect_description_list=defect_description_list,
            #                        is_assignee=is_assignee,
            #                        is_dev_manager=is_dev_manager,  # 是否为开发主管
            #                        is_test_manager=is_test_manager,  # 是否为测试经理
            #                        current_user=current_user,
            #                        defect_flow_histories=defect_flow_histories,
            #                        DefectStatus=DefectStatus,
            #                        StageStatus=StageStatus,
            #                        source_defect=source_defect,
            #                        user_list=user_list,
            #                        DataType=DataType)
        # 原因分析数据
        cause_analysis_data = DefectStageDataService.get_locale_invitation_data(defect_id, is_simplified=True)
        cause_analysis_ai = None
        if cause_analysis_data:
            defect_stage_id = cause_analysis_data[0]['defect_stage_id']
            cause_analysis_ai = DefectStageCombineRecord.query.filter(DefectStageCombineRecord.defect_stage_id==defect_stage_id).first()
        current_app.logger.debug(f'cause_analysis_data length: {len(cause_analysis_data)}')
        if cause_analysis_data:
            current_app.logger.debug(f"cause_analysis_data: {cause_analysis_data[0].get('content').get('analyses')}")
        analysis_data_list = []
        completed_analysis_data = DefectStageDataService.filter_completed_invitations(cause_analysis_data)
        current_app.logger.debug(f'len(completed_analysis_data): {len(completed_analysis_data)}')
        for data in completed_analysis_data:
            for item in data.get('content').get('analyses'):
                analysis_data_list.append(item)
        # 解决措施数据
        solution_ai = None
        solution_data = DefectStageDataService.get_solution_division_data(defect_id)
        if solution_data:
            defect_stage_id = solution_data[0]['defect_stage_id']
            solution_ai = DefectStageCombineRecord.query.filter(DefectStageCombineRecord.defect_stage_id==defect_stage_id).first()
        solution_data_list = []
        completed_solution_data = DefectStageDataService.filter_completed_divisions(solution_data)
        current_app.logger.debug(f'len(completed_solution_data): {len(completed_solution_data)}')
        for data in completed_solution_data:
            for item in data.get('content').get('solutions'):
                solution_data_list.append(item)
        current_app.logger.debug(f'solution_data_list: {solution_data_list}')
        current_app.logger.debug(f'solution_data: {solution_data}')
        test_result_data = DefectStageDataService.get_test_result_data(defect_id)
        test_result_data_list = []
        if test_result_data:
            content_dict = test_result_data[0].get('content')
            try:
                test_result_data_list = json.loads(content_dict.get('description'))
                if test_result_data_list:
                    current_app.logger.info( f"test_result_data_list[0].get('title') : {test_result_data_list[0].get('title')}")
                    current_app.logger.info(
                        f'current_stage status: {current_stage.status}  test_result_data status: {test_result_data[0].get("stage_status")}')
            except Exception as e:
                current_app.logger.error(f'test_result_data 数据格式不符合要求: {e}')

        # 获取回归测试阶段的状态
        tester_regression_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'tester_regression')
        tester_regression_stage_status = tester_regression_stage.status
        current_app.logger.debug(f'tester_regression_stage_status: {tester_regression_stage_status}')

        # 获取当前阶段的分工信息（如果是developer_solution阶段）
        divisions = []
        if current_stage and current_stage.stage_type == "developer_solution":
            divisions = DefectSolutionDivision.query.filter_by(
                defect_stage_id=current_stage.id
            ).all()

        # 将 solution_data_list 与  divisions 关联起来


        cause_analysis_invitations = DefectLocaleInvitationService.get_cause_analysis_invitations(defect_id)  # 主处理人 在转处理后会发生变化，需要完善
        print("cause_analysis_invitations:")
        print(cause_analysis_invitations)

        invitee_id_set = {invitation.invitee_id for invitation in cause_analysis_invitations}
        is_same_invitee = len(invitee_id_set) <= 1 # 多个邀请是否都针对同一人，这是一种特殊情况，前端已经排除了这种情况（批量邀请时不会多次选中同一用户）

        current_app.logger.info(f'len(cause_analysis_invitations): {len(cause_analysis_invitations)}')

        solution_divisions = DefectSolutionDivisionService.get_solution_divisions_by_defect_id(defect_id)
        current_app.logger.info(f'len(solution_divisions): {len(solution_divisions)}')
        # 获取各阶段第一责任人
        cause_analysis_user = DefectStageService.get_stage_user(defect_id, 'cause_analysis')
        developer_solution_user = DefectStageService.get_stage_user(defect_id, 'developer_solution')
        tester_regression_user = DefectStageService.get_stage_user(defect_id, 'tester_regression')
        # 通过关系获取所有复制生成的问题单
        duplicate_defects_infos = DefectService.get_duplicate_defects_infos(defect)
        if f"self_res_{defect_id}" in session:
            self_ai_done = "1"
        else:
            self_ai_done = ""
        return render_template('defect/detail_simplified.html',
                               self_ai_done = self_ai_done,
                               defect=defect,
                               project_version_id=project_version_id,
                               project_version_name=project_version_name,
                               stages=stages,
                               current_stage=current_stage,
                               current_stage_name=current_stage_name,
                               stage_data=stage_data,
                               description_data=description_data,
                               # defect_description_list=defect_description_list,
                               cause_analysis_data=cause_analysis_data,  # 原因分析数据  包含邀请人和被邀请人
                               cause_analysis_ai = cause_analysis_ai,
                               solution_ai = solution_ai,
                               analysis_data_list=analysis_data_list, # 已经完成分析的数据
                               solution_data=solution_data,  # 解决措施数据  包含分配人和被分配人
                               solution_data_list=solution_data_list,  # 已经提交的解决措施
                               is_same_invitee=is_same_invitee,
                               test_result_data=test_result_data,
                               test_result_data_list=test_result_data_list,
                               divisions=divisions,  # 传递分工信息
                               is_assignee=is_assignee,
                               is_dev_manager=is_dev_manager,  # 是否为开发主管
                               is_test_manager=is_test_manager,  # 是否为测试经理
                               current_user=current_user,
                               defect_flow_histories=defect_flow_histories,
                               DefectStatus=DefectStatus,
                               StageStatus=StageStatus,
                               tester_regression_stage_status=tester_regression_stage_status,  # 回归测试是否完成-通过
                               source_defect=source_defect,
                               user_list=user_list,
                               cause_analysis_invitations=cause_analysis_invitations,
                               solution_divisions=solution_divisions,
                               duplicate_defects_infos=duplicate_defects_infos,
                               cause_analysis_user=cause_analysis_user,
                               developer_solution_user=developer_solution_user,
                               tester_regression_user=tester_regression_user,
                               DataType=DataType)
    except Exception as e:
        return render_template('defect/error.html',
                               error_message=f'获取缺陷详情时发生错误: {str(e)}',
                               link_to_title='返回缺陷列表',
                               redirect_url=url_for('defect.role_proxy'))

@defect_bp.route('/simplified2/<int:defect_id>')
def defect_detail_simplified2(defect_id):
    """缺陷详情页面"""

    current_app.logger.debug(f'get simplified2 detail for defect. ID:{defect_id}')
    defect = DefectService.get_defect_by_id(defect_id)
    current_user = User.get_user_by_id(g.user_id)
    if not defect:
        return render_template('defect/error.html',
                               error_message=f'{current_user.company_name} 缺陷单不存在。',
                               link_to_title='返回缺陷列表',
                               redirect_url='/defect/?defect_type=simplified2')
    defect_type = defect.defect_type
    create_user = defect.creator
    current_app.logger.info(
        f'【current_user.user_id】: {current_user.user_id}, '
        f'【current_user.admin_user_id】: {current_user.admin_user_id}, '
        f'【defect.creator.admin_user_id】: {create_user.admin_user_id}')
    # 检查缺陷单是否为本公司的缺陷单，根据缺陷单的创建人判断

    if create_user.admin_user_id == 0:
        return render_template('defect/error.html',
                               error_message='当前缺陷单为公司管理员创建，不符合实际业务场景。',
                               link_to_title='返回缺陷列表',
                               redirect_url='/defect/?defect_type=simplified2')
    if current_user.admin_user_id == 0:
        return render_template('defect/error.html',
                               error_message='🎉 哇哦！发现一位尊贵的公司管理员！<br>'
                                             '您可是要处理大事的大佬呢～<br>'
                                             '这种小缺陷单就交给小伙伴们去处理吧！<br>'
                                             '💼 您还是继续运筹帷幄，指点江山～',
                               link_to_title='配置全板块管理员',
                               redirect_url=url_for('global_settings.global_admin_list'))
    if current_user.admin_user_id != create_user.admin_user_id:
        return render_template('defect/error.html',
                               error_message=f'{current_user.company_name} 缺陷单不存在。',
                               link_to_title='返回缺陷列表',
                               redirect_url='/defect/?defect_type=simplified2')
    project_version_name,project_version_id = defect_services.get_project_version(defect)
    stages = DefectStageService.get_stages_by_defect(defect_id)
    current_stage = DefectStageService.get_stage_by_id(defect.current_stage_id)
    current_stage_name = DefectWorkflowService.get_current_stage_name(defect)
    ai_done_act = request.args.get('ai_done_act','')
    current_app.logger.debug(f'current_stage.stage_type: {current_stage.stage_type}')
    current_app.logger.debug(f'current_stage.status: {current_stage.status}')

    # 获取各阶段数据
    stage_data = None  # 当前阶段数据
    if current_stage:
        current_app.logger.info(f'current_stage id: {current_stage.id}')
        stage_data_list = DefectStageDataService.get_all_stage_data_by_criteria(current_stage.id, None, True, None)
        stage_data = stage_data_list[0] if len(stage_data_list) > 0 else None
        if stage_data:
            current_app.logger.debug(f'stage_data.id: {stage_data.id}')
    source_defect = None
    if defect.duplicate_source_id:
        source_defect = DefectService.get_defect_by_id(defect.duplicate_source_id)
    # 检查当前用户是否是阶段负责人
    is_assignee = False
    if current_stage and g.user_id == current_stage.assigned_to:
        is_assignee = True
    current_user = User.get_user_by_id(g.user_id)
    is_test_manager = False
    project_manager_id = DefectWorkflowService.get_project_manager_id(defect)
    test_manager_id = DefectWorkflowService.get_test_manager_id(defect)
    dev_manager_id = DefectWorkflowService.get_dev_manager_id(defect)
    is_project_manager = False
    if current_user.user_id == project_manager_id:
        is_project_manager = True
    if current_user.user_id == test_manager_id:
        is_test_manager = True
    is_dev_manager = False
    if current_user.user_id == dev_manager_id:
        is_dev_manager = True
    # 获取本缺陷单的所有 流程历史记录
    defect_flow_histories = DefectFlowHistoryService.get_flow_history(defect_id)
    current_app.logger.debug(f'len(defect_flow_histories): {len(defect_flow_histories)}')
    # 返回用户列表
    user_list = User.get_company_users_by_user_id(g.user_id)

    # 缺陷描述阶段
    description_data = DefectStageDataService.get_defect_description_data(defect_id)
    print(f"description_data{description_data}")
    current_app.logger.debug(f'description_data length: {len(description_data)}')
    # 原因分析数据
    cause_analysis_data = DefectStageDataService.get_stage_data_by_type(defect_id, DataType.CAUSE_ANALYSIS)
    cause_analysis_ai = None
    if cause_analysis_data:
        defect_stage_id = cause_analysis_data[0]['defect_stage_id']
        cause_analysis_ai = DefectStageCombineRecord.query.filter(DefectStageCombineRecord.defect_stage_id==defect_stage_id).first()
    current_app.logger.debug(f'cause_analysis_data length: {len(cause_analysis_data)}')
    if cause_analysis_data:
        current_app.logger.debug(f"cause_analysis_data: {cause_analysis_data[0].get('content').get('analyses')}")
    completed_analysis_data = DefectStageDataService.filter_completed_invitations(cause_analysis_data)
    current_app.logger.debug(f'len(completed_analysis_data): {len(completed_analysis_data)}')
    # 解决措施数据
    solution_ai = None
    solution_data = DefectStageDataService.get_stage_data_by_type(defect_id, DataType.SOLUTION)
    if solution_data:
        defect_stage_id = solution_data[0]['defect_stage_id']
        solution_ai = DefectStageCombineRecord.query.filter(DefectStageCombineRecord.defect_stage_id==defect_stage_id).first()
    current_app.logger.debug(f'solution_data: {solution_data}')
    test_result_data = DefectStageDataService.get_test_result_data(defect_id)
    test_result_data_list = []
    if test_result_data:
        content_dict = test_result_data[0].get('content')
        try:
            test_result_description = content_dict.get('description')
            current_app.logger.info( f"test_result_description: {test_result_description}")
        except Exception as e:
            current_app.logger.error(f'test_result_data 数据格式不符合要求: {e}')

    # 获取回归测试阶段的状态
    tester_regression_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'tester_regression')
    tester_regression_stage_status = tester_regression_stage.status
    current_app.logger.debug(f'tester_regression_stage_status: {tester_regression_stage_status}')

    # 获取当前阶段的分工信息（如果是developer_solution阶段）
    divisions = []
    if current_stage and current_stage.stage_type == "developer_solution":
        divisions = DefectSolutionDivision.query.filter_by(
            defect_stage_id=current_stage.id
        ).all()

    # 将 solution_data_list 与  divisions 关联起来


    cause_analysis_invitations = DefectLocaleInvitationService.get_cause_analysis_invitations(defect_id)  # 主处理人 在转处理后会发生变化，需要完善
    invitee_id_set = {invitation.invitee_id for invitation in cause_analysis_invitations}
    is_same_invitee = len(invitee_id_set) <= 1 # 多个邀请是否都针对同一人，这是一种特殊情况，前端已经排除了这种情况（批量邀请时不会多次选中同一用户）

    current_app.logger.info(f'len(cause_analysis_invitations): {len(cause_analysis_invitations)}')

    solution_divisions = DefectSolutionDivisionService.get_solution_divisions_by_defect_id(defect_id)
    current_app.logger.info(f'len(solution_divisions): {len(solution_divisions)}')
    # 获取各阶段第一责任人
    description_user = DefectStageService.get_stage_user(defect_id, 'defect_description')
    cause_analysis_user = DefectStageService.get_stage_user(defect_id, 'cause_analysis')
    current_app.logger.debug(f'cause_analysis_user-- {cause_analysis_user}')
    developer_solution_user = DefectStageService.get_stage_user(defect_id, 'developer_solution')
    tester_regression_user = DefectStageService.get_stage_user(defect_id, 'tester_regression')
    # 通过关系获取所有复制生成的问题单
    duplicate_defects_infos = DefectService.get_duplicate_defects_infos(defect)
    if f"self_res_{defect_id}" in session:
        self_ai_done = "1"
    else:
        self_ai_done = ""
    if request.args.get('from_page', '') == "":
        template = "defect/detail_simplified2.html"
    else:
        template = "defect/create_simplified2.html"
    return render_template(template,
                           self_ai_done = self_ai_done,
                           defect=defect,
                           project_version_id=project_version_id,
                           project_version_name=project_version_name,
                           stages=stages,
                           current_stage=current_stage,
                           current_stage_name=current_stage_name,
                           stage_data=stage_data,
                           description_data=description_data,
                           # defect_description_list=defect_description_list,
                           cause_analysis_data=cause_analysis_data,  # 原因分析数据  包含邀请人和被邀请人
                           cause_analysis_ai = cause_analysis_ai,
                           solution_ai = solution_ai,
                           solution_data=solution_data,  # 解决措施数据  包含分配人和被分配人
                           is_same_invitee=is_same_invitee,
                           test_result_data=test_result_data,
                           test_result_data_list=test_result_data_list,
                           divisions=divisions,  # 传递分工信息
                           is_assignee=is_assignee,
                           is_project_manager=is_project_manager,  # 是否为项目管理员
                           is_dev_manager=is_dev_manager,  # 是否为开发主管
                           is_test_manager=is_test_manager,  # 是否为测试经理
                           current_user=current_user,
                           defect_flow_histories=defect_flow_histories,
                           DefectStatus=DefectStatus,
                           StageStatus=StageStatus,
                           tester_regression_stage_status=tester_regression_stage_status,  # 回归测试是否完成-通过
                           source_defect=source_defect,
                           user_list=user_list,
                           cause_analysis_invitations=cause_analysis_invitations,
                           solution_divisions=solution_divisions,
                           duplicate_defects_infos=duplicate_defects_infos,
                           description_user=description_user,
                           cause_analysis_user=cause_analysis_user,
                           developer_solution_user=developer_solution_user,
                           tester_regression_user=tester_regression_user,
                           DataType=DataType)
    # except Exception as e:
    #     current_app.logger.error(
    #         f"评估失败异常-get_score_suggestion:{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}")
    #     return render_template('defect/error.html',
    #                            error_message=f'获取缺陷详情时发生错误: {str(e)}',
    #                            link_to_title='返回缺陷列表',
    #                            redirect_url=url_for('defect.role_proxy'))


@defect_bp.route('/<int:defect_id>/submit', methods=['POST'])
def submit_defect(defect_id):
    """提交缺陷进入流程"""
    try:
        defect = DefectService.submit_defect(defect_id, g.user_id)
        if not defect:
            flash('提交缺陷失败', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        db.session.commit()
        flash('缺陷已提交进入流程', 'success')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))

    except Exception as e:
        db.session.rollback()
        flash(f'提交缺陷时发生错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))


@defect_bp.route('/<int:defect_id>/duplicate', methods=['POST'])
def mark_as_duplicate(defect_id):
    """标记缺陷为重复问题"""
    try:
        source_defect_id = request.form.get('source_defect_id')

        defect = DefectService.mark_as_duplicate(defect_id, int(source_defect_id), g.user_id)
        if not defect:
            flash('标记为重复问题失败', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        db.session.commit()
        flash('缺陷已标记为重复问题', 'success')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))

    except Exception as e:
        db.session.rollback()
        flash(f'标记为重复问题时发生错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))


@defect_bp.route('/copy/<int:source_defect_id>', methods=['GET', 'POST'])
def copy_defect(source_defect_id):
    """复制缺陷单"""
    try:
        # 获取项目数据
        project_version_id = request.form.get('project_version_id')
        if not project_version_id:
            flash('请至少选择一个项目', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=source_defect_id))

        version_id, project_id = parse_project_version_id(project_version_id)
        defect = DefectWorkflowService.copy_defect(
            source_defect_id, g.user_id, project_id=project_id, version_id=version_id)
        project_version_name = DefectService.get_project_version_name(defect)
        if not defect:
            flash(f'复制缺陷单到项目 {project_version_name} 失败', 'error')
        else:
            flash(f'复制缺陷单到项目 {project_version_name} 成功', 'success')
            db.session.commit()
        return redirect(url_for('defect.defect_detail', defect_id=source_defect_id))
    except Exception as e:
        db.session.rollback()
        flash(f'复制缺陷单时发生错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=source_defect_id))


@defect_bp.route('/api/<int:source_defect_id>/copy', methods=['POST'])
def copy_defect_api(source_defect_id):
    """复制缺陷单 - API接口"""
    try:
        # 验证用户权限（根据实际需求添加）
        # if not has_permission(g.user_id, 'copy_defect'):
        #     return jsonify({'success': False, 'message': '权限不足'}), 403

        # 获取请求数据
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'message': '缺少请求数据'
            }), 400

        project_version_id = data.get('project_version_id')

        # 参数验证
        if not project_version_id:
            return jsonify({
                'success': False,
                'message': '请至少选择一个项目',
                'error_code': 'MISSING_PROJECT_VERSION'
            }), 400

        # 解析项目版本ID
        try:
            version_id, project_id = parse_project_version_id(project_version_id)
        except Exception as e:
            return jsonify({
                'success': False,
                'message': '项目版本ID格式错误',
                'error_code': 'INVALID_PROJECT_VERSION_FORMAT'
            }), 400

        # 执行复制操作
        defect = DefectWorkflowService.copy_defect(
            source_defect_id, g.user_id, project_id, version_id)

        if not defect:
            project_version_name = DefectService.get_project_version_name(defect)
            return jsonify({
                'success': False,
                'message': f'复制缺陷单到项目 {project_version_name} 失败',
                'error_code': 'COPY_FAILED'
            }), 500

        # 获取项目版本名称用于返回信息
        project_version_name = DefectService.get_project_version_name(defect)
        # 发送邮件和消息
        current_app.logger.debug('copy-api....')
        test_manager_id = DefectWorkflowService.get_test_manager_id(defect)
        if not test_manager_id:
            return jsonify({
                'success': False,
                'message': f'复制缺陷单到项目 {project_version_name} 失败，目标项目没有配置测试经理。',
                'error_code': 'COPY_FAILED'
            }), 500
        MessageCreator.create_review_message(
            defect_id=defect.id,
            reviewer_id=test_manager_id,
            submitter_id=g.user_id,
            review_type='defect_description'
        )

        email_content = email_content = DefectEmailService.get_review_email_content(
            defect=defect,
            review_type='defect_description',
            submitter_id=g.user_id
        )
        email_subject = DefectEmailService.get_email_subject_by_message_type(
            defect=defect,
            message_type=MessageTypes.REVIEW_DEFECT_DESCRIPTION
        )
        send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=test_manager_id,
                                                            admin_user_id=g.admin_user_id,
                                                            current_user_id=g.user_id,
                                                            content=email_content,
                                                            title=email_subject
                                                            )

        # 提交事务
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'复制缺陷单到项目 {project_version_name} 成功',
            'data': {
                'new_defect_id': defect.id,
                'new_defect_num': defect.defect_number,
                'source_defect_id': source_defect_id,
                'project_version_name': project_version_name,
                'project_id': project_id,
                'version_id': version_id
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        # 记录错误日志
        # logger.error(f'复制缺陷单失败: {str(e)}')

        return jsonify({
            'success': False,
            'message': f'复制缺陷单时发生错误: {str(e)}',
            'error_code': 'INTERNAL_SERVER_ERROR'
        }), 500

@defect_bp.route('/<int:defect_id>/terminate', methods=['POST'])
def terminate_defect(defect_id):
    """终止跟踪缺陷"""
    defect = DefectService.get_defect_by_id(defect_id)
    if not defect:
        flash('缺陷单不存在', 'error')
        return redirect(url_for('defect.defect_list'))
    detail_url = 'defect.defect_detail'
    defect_type = defect.defect_type
    if defect_type == 'simplified':
        detail_url = 'defect.defect_detail_simplified'
    if defect_type == 'simplified2':
        detail_url = 'defect.defect_detail_simplified2'
    try:
        reason = request.form.get('reason')
        # 这里调用相应的服务方法处理终止逻辑
        DefectWorkflowService.terminate_defect(defect_id, g.user_id, reason)

        flash('缺陷已终止跟踪', 'success')
        return redirect(url_for(detail_url, defect_id=defect_id))
    except Exception as e:
        flash(f'终止跟踪时发生错误: {str(e)}', 'error')
        return redirect(url_for(detail_url, defect_id=defect_id))


# 新增解决缺陷API接口
@defect_bp.route('/<int:defect_id>/resolve-api', methods=['POST'])
def resolve_defect_api(defect_id):
    """解决缺陷 - JSON API版本"""
    return handle_defect_closure(defect_id, 'resolved')

# 新增挂起缺陷API接口
@defect_bp.route('/<int:defect_id>/suspend-api', methods=['POST'])
def suspend_defect_api(defect_id):
    """挂起缺陷 - JSON API版本"""
    return handle_defect_closure(defect_id, 'suspended')

# 更新原有的终止缺陷API接口，保持兼容性
@defect_bp.route('/<int:defect_id>/terminate-api', methods=['POST'])
def terminate_defect_api(defect_id):
    """终止跟踪缺陷 - JSON API版本"""
    return handle_defect_closure(defect_id, 'terminated')

# 新增挂起缺陷API接口
@defect_bp.route('/<int:defect_id>/reopen-api', methods=['POST'])
def reopen_defect_api(defect_id):
    """重新开启缺陷 - JSON API版本"""
    return handle_defect_closure(defect_id, 'reopen')

# 通用的缺陷关闭处理函数
def handle_defect_closure(defect_id, closure_type):
    """处理缺陷关闭的通用函数"""
    try:
        # 获取请求数据（支持JSON和form格式）
        if request.is_json:
            data = request.get_json()
            reason = data.get('reason', '')
            verification_status = data.get('verificationStatus', closure_type)
        else:
            reason = request.form.get('reason', '')
            verification_status = request.form.get('verificationStatus', closure_type)

        # 参数验证
        if not reason or reason.strip() == '':
            return jsonify({
                'code': 1,
                'message': '必须提供关闭原因'
            }), 400

        # 验证关闭状态
        if verification_status not in ['resolved', 'suspended', 'terminated', 'reopen']:
            return jsonify({
                'code': 1,
                'message': '无效的关闭状态'
            }), 400

        # 获取当前缺陷
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            return jsonify({
                'code': 1,
                'message': '缺陷单不存在'
            }), 404

        # 检查缺陷状态是否可以关闭
        # 这里可以根据业务逻辑添加验证
        # 例如：if defect.status == 'closed':
        #     return jsonify({'code': 1, 'message': '缺陷已关闭，无法再次关闭'}), 403

        try:
            # 根据关闭类型调用不同的服务方法
            if verification_status == 'resolved':
                # 调用解决缺陷的方法
                DefectWorkflowService.resolve_defect(defect_id, g.user_id, reason, closure_type='resolved')
            elif verification_status == 'suspended':
                # 调用挂起缺陷的方法
                DefectWorkflowService.resolve_defect(defect_id, g.user_id, reason, closure_type='suspended')
            elif verification_status == 'terminated':  # 'terminated'
                # 调用终止缺陷的方法
                DefectWorkflowService.resolve_defect(defect_id, g.user_id, reason, closure_type='terminated')
            else:  # reopen
                # 调用重新开启缺陷的方法
                DefectWorkflowService.resolve_defect(defect_id, g.user_id, reason, closure_type='reopen')

            # 根据关闭类型返回不同的成功消息
            messages = {
                'resolved': '缺陷单已成功关闭',
                'suspended': '缺陷单已成功挂起',
                'terminated': '缺陷单已成功终止跟踪',
                'reopen': '缺陷单已成功重新开启'
            }

            return jsonify({
                'code': 0,
                'message': messages.get(verification_status, '操作成功'),
                'data': {
                    'defect_id': defect_id,
                    'closed_by': g.user_id,
                    'closure_type': verification_status,
                    'closure_reason': reason
                }
            })

        except Exception as e:
            # 业务逻辑错误
            return jsonify({
                'code': 1,
                'message': f'操作时发生错误: {str(e)}'
            }), 500

    except json.JSONDecodeError:
        return jsonify({
            'code': 1,
            'message': '请求数据格式错误，必须是有效的JSON'
        }), 400

    except Exception as e:
        # 服务器内部错误
        return jsonify({
            'code': 1,
            'message': f'服务器内部错误: {str(e)}'
        }), 500

@defect_bp.route('/<int:defect_id>/transfer_to_other', methods=['POST'])
def transfer_to_other(defect_id: int):
    """问题单转处理"""
    defect = DefectService.get_defect_by_id(defect_id)
    if not defect:
        flash('缺陷单不存在', 'error')
        return redirect(url_for('defect.defect_list'))
    try:
        reason = request.form.get('reason')
        transfer_to_user_id = request.form.get('transfer_to_user_id')
        if transfer_to_user_id and transfer_to_user_id.strip():
            transfer_to_user_id = int(transfer_to_user_id)
            if not DefectService.validate_user_exists(transfer_to_user_id):
                flash(f"用户ID {transfer_to_user_id} 不存在", 'error')
                return redirect(url_for('defect.defect_detail', defect_id=defect_id))
            if transfer_to_user_id == g.user_id:
                flash(f"不能转交给自己", 'error')
                return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        current_stage = DefectStage.query.get(defect.current_stage_id)
        # 这里调用相应的服务方法处理终止逻辑 (问题分析和解决措施阶段需要特殊处理——修改邀请记录：修改邀请的状态)
        DefectWorkflowService.transfer_to_other(defect_id, g.user_id, int(transfer_to_user_id), reason,
                                                stage_type=current_stage.stage_type)

        flash('缺陷已经转处理成功', 'success')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))
    except Exception as e:
        flash(f'转处理时发生错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))


@defect_bp.route('/<int:defect_id>/transfer_to_other_api', methods=['POST'])
def transfer_to_other_api(defect_id: int):
    """问题单转处理API接口"""
    defect = DefectService.get_defect_by_id(defect_id)
    if not defect:
        return jsonify({
            'success': False,
            'message': '缺陷单不存在',
            'error_code': 'DEFECT_NOT_FOUND'
        }), 404

    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': '请求数据格式错误，请使用application/json',
                'error_code': 'INVALID_JSON'
            }), 400

        reason = data.get('reason')
        transfer_to_user_id = data.get('transfer_to_user_id')

        # 验证必要参数
        if not transfer_to_user_id:
            return jsonify({
                'success': False,
                'message': '缺少必要参数: transfer_to_user_id',
                'error_code': 'MISSING_REQUIRED_FIELD'
            }), 400

        # 验证用户ID格式
        try:
            transfer_to_user_id = int(transfer_to_user_id)
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'message': '用户ID格式错误',
                'error_code': 'INVALID_USER_ID_FORMAT'
            }), 400

        # 验证目标用户是否存在
        if not DefectService.validate_user_exists(transfer_to_user_id):
            return jsonify({
                'success': False,
                'message': f"用户ID {transfer_to_user_id} 不存在",
                'error_code': 'USER_NOT_FOUND'
            }), 400

        current_stage = DefectStage.query.get(defect.current_stage_id)

        # 调用服务方法处理转交逻辑
        DefectWorkflowService.transfer_to_other(
            defect_id,
            g.user_id,
            transfer_to_user_id,
            reason,
            stage_type=current_stage.stage_type
        )

        return jsonify({
            'success': True,
            'message': '缺陷转处理成功',
            'data': {
                'defect_id': defect_id,
                'transferred_to_user_id': transfer_to_user_id,
                'transferred_by_user_id': g.user_id,
                'reason': reason
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'转处理时发生错误: {str(e)}',
            'error_code': 'INTERNAL_SERVER_ERROR'
        }), 500


@defect_bp.route('/<int:defect_id>/reject', methods=['POST'])
def reject_defect(defect_id):
    """驳回缺陷"""
    try:
        reason = request.form.get('reason')
        current_app.logger.debug(f'reject_reason: {reason}')
        # 调用相应的服务方法处理驳回逻辑
        defect = DefectWorkflowService.reject_defect(defect_id, g.user_id, reason)
        if defect:
            flash('流程已驳回', 'success')
        else:
            flash('驳回失败', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))
    except Exception as e:
        flash(f'驳回缺陷时发生错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))


@defect_bp.route('/<int:defect_id>/assign-tester', methods=['POST'])
def assign_tester(defect_id):
    """指定测试人员"""
    current_app.logger.debug(f'assign_tester... retest')
    tester_id = request.form.get('tester_id')
    if tester_id and tester_id.strip():
        tester_id = int(tester_id)
        if not DefectService.validate_user_exists(tester_id):
            flash(f"用户ID {tester_id} 不存在", 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))
    try:
        reason = request.form.get('reason', '')
        # 这里调用相应的服务方法处理分配测试人员逻辑
        DefectWorkflowService.assign_tester(defect_id, tester_id, g.user_id, reason)

        flash('测试人员已分配', 'success')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))
    except Exception as e:
        flash(f'分配测试人员时发生错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))


@defect_bp.route('/<int:defect_id>/invite-developer', methods=['POST'])
def invite_developers(defect_id):
    """邀请开发人员定位问题（支持单人和多人）"""
    try:
        # 检查是否是多人邀请（使用invitees_data字段）
        invitees_data_str = request.form.get('invitees_data')

        if invitees_data_str:
            # 处理多人邀请
            invitees_data = json.loads(invitees_data_str)
            success_count = 0
            if len(invitees_data) == 0:
                flash('请至少添加一个开发人员', 'error')
                return redirect(url_for('defect.defect_detail', defect_id=defect_id))
            for invitee in invitees_data:
                invitee_id = invitee.get('invitee_id')
                review_notes = invitee.get('review_notes', '')
                if int(invitee_id) == g.user_id:
                    flash('开发人员邀请失败，不能邀请自己。', 'error')
                    continue  # 不能分配自己
                # 调用服务方法处理邀请
                invitation = DefectWorkflowService.invite_developer(
                    defect_id, invitee_id, review_notes, g.user_id
                )
                if invitation:
                    success_count += 1

            if success_count > 0:
                flash(f'已成功发送{success_count}个开发人员邀请', 'success')
            else:
                flash('开发人员邀请失败', 'error')
        else:
            # 处理单人邀请（保持向后兼容）
            invitee_id = request.form.get('invitee_id')
            current_app.logger.debug(f'被指定用户的ID: {invitee_id}')
            review_notes = request.form.get('review_notes', '')
            if not invitee_id:
                flash('请设置有效的开发人员', 'error')
                return redirect(url_for('defect.defect_detail', defect_id=defect_id))
            # if int(invitee_id) == g.user_id:
            #     flash('不能邀请自己', 'error')
            #     return redirect(url_for('defect.defect_detail', defect_id=defect_id))
            invitation = DefectWorkflowService.invite_developer(
                defect_id, int(invitee_id), review_notes, g.user_id
            )
            if invitation:
                flash('开发人员邀请已发送', 'success')
            else:
                flash('开发人员邀请失败', 'error')

        return redirect(url_for('defect.defect_detail', defect_id=defect_id))
    except Exception as e:
        flash(f'邀请开发人员时发生错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))

@defect_bp.route('/<int:defect_id>/assign-description-user-api', methods=['POST'])
def assign_description_user_api(defect_id):
    """给 defect.defect_type == 'simplified2' 设置缺陷描述责任人- JSON API版本"""
    try:
        # 获取请求数据（支持JSON和form格式）
        if request.is_json:
            data = request.get_json()
            invitees_data = data.get('invitees', [])
        else:
            invitees_data_str = request.form.get('invitees_data')
            if invitees_data_str:
                invitees_data = json.loads(invitees_data_str)
            else:
                invitees_data = []

        # 参数验证
        if not invitees_data or len(invitees_data) == 0:
            return jsonify({
                'code': 1,
                'message': '请至少添加一个开发人员'
            }), 400

        # 获取当前缺陷和阶段
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            return jsonify({
                'code': 1,
                'message': '指定的缺陷单不存在'
            }), 404

        first_invitee_id = invitees_data[0].get('invitee_id')
        review_notes = invitees_data[0].get('review_notes', '')
        if defect.defect_type == 'simplified' or defect.defect_type == 'simplified2':
            defect_description_stage = DefectStageService.get_stage_by_defect_and_type(defect.id, 'defect_description')
            if int(first_invitee_id) == int(defect_description_stage.assigned_to):
                return jsonify({
                    'code': 1,
                    'message': f'所设置的责任人没有变化，无需重新设置。',
                }), 403
            # 更新阶段信息
            defect_description_stage = DefectStageService.update_stage(stage_id=defect_description_stage.id,
                                                                   assigned_to=first_invitee_id,  # 分配给指定的（开发人员）
                                                                   notes=review_notes,
                                                                   status=StageStatus.IN_PROGRESS)
            message = '你是缺陷描述责任人，请尽快处理。'
            # 发送邮件
            email_content = DefectEmailService.get_general_defect_email_content(defect, message=message + '原因：' +review_notes, action_type="")
            # 简化版
            email_subject = f"【{message}】{defect.defect_number} - {defect.title}"

            send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=int(first_invitee_id),
                                                                admin_user_id=g.admin_user_id,
                                                                current_user_id=g.user_id,
                                                                content=email_content,
                                                                title=email_subject)
            # 发送消息
            extra_params = {'reason': review_notes} if review_notes else None
            DefectMessage.create_message(
                send_to_user_id=int(first_invitee_id),
                send_from_user_id=g.user_id,
                defect_id=defect_id,
                message_type=MessageTypes.ASSIGN_RETEST,
                content=email_subject,
                extra_params=extra_params
            )
            # 提交到数据库
            db.session.commit()

            return jsonify({
                'code': 0,
                'message': f'已成功设置缺陷描述人员',
                'data': {
                    'success_count': 1
                }
            })
        else:
            return jsonify({
                'code': 1,
                'message': f'非简化版DTS不能调用此接口',
            }), 403
    except json.JSONDecodeError:
        return jsonify({
            'code': 1,
            'message': 'invitees_data格式错误，必须是有效的JSON'
        }), 400

    except Exception as e:
        # 服务器内部错误
        return jsonify({
            'code': 1,
            'message': f'设置缺陷描述人员时发生错误: {str(e)}'
        }), 500


@defect_bp.route('/<int:defect_id>/invite-developer-api', methods=['POST'])
def invite_developers_api(defect_id):
    """给 defect.defect_type == 'simplified2' 设置原因分析责任人- JSON API版本"""
    try:
        # 获取请求数据（支持JSON和form格式）
        if request.is_json:
            data = request.get_json()
            invitees_data = data.get('invitees', [])
        else:
            invitees_data_str = request.form.get('invitees_data')
            if invitees_data_str:
                invitees_data = json.loads(invitees_data_str)
            else:
                invitees_data = []

        # 参数验证
        if not invitees_data or len(invitees_data) == 0:
            return jsonify({
                'code': 1,
                'message': '请至少添加一个开发人员'
            }), 400

        # 获取当前缺陷和阶段
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            return jsonify({
                'code': 1,
                'message': '指定的缺陷单不存在'
            }), 404

        first_invitee_id = invitees_data[0].get('invitee_id')
        review_notes = invitees_data[0].get('review_notes', '')
        if defect.defect_type == 'simplified' or defect.defect_type == 'simplified2':
            cause_analysis_stage = DefectStageService.get_stage_by_defect_and_type(defect.id, 'cause_analysis')
            if int(first_invitee_id) == int(cause_analysis_stage.assigned_to):
                return jsonify({
                    'code': 1,
                    'message': f'所设置的责任人没有变化，无需重新设置。',
                }), 403
            # 更新阶段信息
            cause_analysis_stage = DefectStageService.update_stage(stage_id=cause_analysis_stage.id,
                                                                       assigned_to=first_invitee_id,  # 分配给指定的（开发人员）
                                                                       notes=review_notes,
                                                                       status=StageStatus.IN_PROGRESS)

            message = '你是原因分析责任人，请尽快处理。'
            # 发送邮件
            email_content = DefectEmailService.get_general_defect_email_content(defect, message=message + '原因：' +review_notes, action_type="")
            # 简化版
            email_subject = f"【{message}】{defect.defect_number} - {defect.title}"

            send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=int(first_invitee_id),
                                                                admin_user_id=g.admin_user_id,
                                                                current_user_id=g.user_id,
                                                                content=email_content,
                                                                title=email_subject)
            # 发送消息
            extra_params = {'reason': review_notes} if review_notes else None
            DefectMessage.create_message(
                send_to_user_id=int(first_invitee_id),
                send_from_user_id=g.user_id,
                defect_id=defect_id,
                message_type=MessageTypes.REASON_ANALYSIS,
                content=email_subject,
                extra_params=extra_params
            )
            # 提交到数据库
            db.session.commit()

            return jsonify({
                'code': 0,
                'message': f'已成功设置原因分析人员',
                'data': {
                    'success_count': 1
                }
            })
        else:
            return jsonify({
                'code': 1,
                'message': f'非简化版DTS不能调用此接口',
            }), 403
    except json.JSONDecodeError:
        return jsonify({
            'code': 1,
            'message': 'invitees_data格式错误，必须是有效的JSON'
        }), 400

    except Exception as e:
        # 服务器内部错误
        return jsonify({
            'code': 1,
            'message': f'设置原因分析人员时发生错误: {str(e)}'
        }), 500


@defect_bp.route('/locale_invitation/<int:invitation_id>/reject', methods=['POST'])
def reject_locale_invitation(invitation_id):
    """
    驳回定位分析邀请
    :param invitation_id: 邀请ID
    """
    try:
        # 获取当前用户ID
        current_user_id = g.user_id

        # 从表单获取驳回原因
        reason = request.form.get('reason', '').strip()
        current_app.logger.debug(f'驳回邀请的原因： {reason}')
        if not reason:
            flash('请输入驳回原因', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

        # 调用服务层方法
        invitation = DefectWorkflowService.reject_invitation(
            invitation_id=invitation_id,
            user_id=current_user_id,
            reason=reason
        )

        if invitation:
            # 获取关联的缺陷ID用于重定向
            stage = DefectStage.query.get(invitation.defect_stage_id)
            if stage:
                flash('已成功驳回邀请', 'success')
                return redirect(url_for('defect.defect_detail', defect_id=stage.defect_id))
            else:
                flash('邀请已驳回，但未能找到相关缺陷信息', 'warning')
                return redirect(url_for('defect.defect_list'))
        else:
            flash('驳回邀请失败，请检查邀请状态或权限', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

    except ValueError as e:
        flash(f'操作失败: {str(e)}', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))
    except RuntimeError as e:
        flash(f'操作失败: {str(e)}', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))
    except Exception as e:
        current_app.logger.error(f"驳回邀请时发生未预期错误: {str(e)}")
        flash('处理请求时发生错误，请稍后重试', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))


@defect_bp.route('/locale_invitation/<int:invitation_id>/reject_single_analysis', methods=['POST'])
def reject_single_analysis(invitation_id):
    """
    驳回单个的定位分析
    :param invitation_id: 邀请ID
    """
    try:
        # 获取当前用户ID
        current_user_id = g.user_id

        # 从表单获取驳回原因
        reason = request.form.get('reason', '').strip()
        current_app.logger.debug(f'驳回邀请的原因： {reason}')
        if not reason:
            flash('请输入驳回原因', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

        # 调用服务层方法
        invitation = DefectWorkflowService.reject_single_analysis(
            invitation_id=invitation_id,
            user_id=current_user_id,
            reason=reason,
            action_type='reject'
        )

        if invitation:
            # 获取关联的缺陷ID用于重定向
            stage = DefectStage.query.get(invitation.defect_stage_id)
            if stage:
                flash('已成功驳回原因分析', 'success')
                return redirect(url_for('defect.defect_detail', defect_id=stage.defect_id))
            else:
                flash('原因分析已驳回，但未能找到相关缺陷信息', 'warning')
                return redirect(url_for('defect.defect_list'))
        else:
            flash('驳回原因分析失败，请检查邀请状态或权限', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

    except ValueError as e:
        flash(f'操作失败: {str(e)}', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))
    except RuntimeError as e:
        flash(f'操作失败: {str(e)}', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))
    except Exception as e:
        current_app.logger.error(f"驳回原因分析时发生未预期错误: {str(e)}")
        flash('处理请求时发生错误，请稍后重试', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))


@defect_bp.route('/locale_invitation/<int:invitation_id>/cancel_single_analysis', methods=['POST'])
def cancel_single_analysis(invitation_id):
    """
    驳回单个的定位分析
    :param invitation_id: 邀请ID
    """
    try:
        # 获取当前用户ID
        current_user_id = g.user_id

        # 从表单获取驳回原因
        reason = request.form.get('reason', '').strip()
        current_app.logger.debug(f'驳回邀请的原因： {reason}')
        if not reason:
            flash('请输入驳回原因', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

        # 调用服务层方法
        invitation = DefectWorkflowService.reject_single_analysis(
            invitation_id=invitation_id,
            user_id=current_user_id,
            reason=reason,
            action_type='cancel'
        )

        if invitation:
            # 获取关联的缺陷ID用于重定向
            stage = DefectStage.query.get(invitation.defect_stage_id)
            if stage:
                flash('已成功弃用原因分析', 'success')
                return redirect(url_for('defect.defect_detail', defect_id=stage.defect_id))
            else:
                flash('原因分析已弃用，但未能找到相关缺陷信息', 'warning')
                return redirect(url_for('defect.defect_list'))
        else:
            flash('弃用原因分析失败，请检查邀请状态或权限', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

    except ValueError as e:
        flash(f'操作失败: {str(e)}', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))
    except RuntimeError as e:
        flash(f'操作失败: {str(e)}', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))
    except Exception as e:
        current_app.logger.error(f"弃用原因分析时发生未预期错误: {str(e)}")
        flash('处理请求时发生错误，请稍后重试', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))


@defect_bp.route('/solution/<int:division_id>/reject_single_solution', methods=['POST'])
def reject_single_solution(division_id):
    """
    驳回单个人员的解决措施
    :param division_id: 分工ID
    """
    try:
        # 获取当前用户ID
        current_user_id = g.user_id

        # 从表单获取驳回原因
        reason = request.form.get('reason', '').strip()
        current_app.logger.debug(f'驳回解决措施的原因： {reason}')
        current_app.logger.debug(f'reject division_id： {division_id}')
        if not reason:
            flash('请输入驳回原因', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

        # 调用服务层方法
        division = DefectWorkflowService.reject_single_solution(
            division_id=int(division_id),
            user_id=current_user_id,
            reason=reason,
            action_type='reject'
        )

        if division:
            # 获取关联的缺陷ID用于重定向
            stage = DefectStage.query.get(division.defect_stage_id)
            if stage:
                flash('已成功驳回解决措施', 'success')
                return redirect(url_for('defect.defect_detail', defect_id=stage.defect_id))
            else:
                flash('解决措施已驳回，但未能找到相关缺陷信息', 'warning')
                return redirect(url_for('defect.defect_list'))
        else:
            flash('驳回解决措施失败，请检查分工状态或权限', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

    except ValueError as e:
        flash(f'操作失败: {str(e)}', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))
    except RuntimeError as e:
        flash(f'操作失败: {str(e)}', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))
    except Exception as e:
        current_app.logger.error(f"驳回解决措施时发生未预期错误: {str(e)}")
        flash('处理请求时发生错误，请稍后重试', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))


@defect_bp.route('/locale_invitation/<int:invitation_id>/send_reminder', methods=['POST'])
def send_invitation_reminder(invitation_id):
    """
    发送邀请跟催
    :param invitation_id: 邀请ID
    """
    try:
        # 获取当前用户ID
        current_user_id = g.user_id

        # 从表单获取跟催消息
        message = request.form.get('reason', '').strip()
        if not message:
            flash('请输入跟催消息内容', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

        # 调用服务层方法
        success = DefectLocaleInvitationService.send_reminder(
            invitation_id=invitation_id,
            reminder_by=current_user_id,
            message=message
        )

        if success:
            # 获取关联的缺陷ID用于重定向
            invitation = DefectLocaleInvitation.query.get(invitation_id)
            if invitation:
                stage = DefectStage.query.get(invitation.defect_stage_id)
                if stage:
                    defect = Defect.query.get(stage.defect_id)
                    if not defect:
                        flash('缺陷单已经不存在', 'error')
                        return redirect(url_for('defect.defect_detail', defect_id=stage.defect_id))

                    db.session.commit()
                    return redirect(url_for('defect.defect_detail', defect_id=stage.defect_id))
            else:
                flash('跟催邮件发送失败，未能找到相关邀请信息', 'error')
                return redirect(url_for('defect.defect_list'))
        else:
            flash('发送跟催邮件失败，请检查邀请状态或权限', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

    except ValueError as e:
        flash(f'操作失败: {str(e)}', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))
    except RuntimeError as e:
        flash(f'操作失败: {str(e)}', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))
    except Exception as e:
        current_app.logger.error(f"发送跟催消息时发生未预期错误: {str(e)}")
        flash('处理请求时发生错误，请稍后重试', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))


@defect_bp.route('/solution_division/<int:division_id>/send_reminder', methods=['POST'])
def send_division_reminder(division_id):
    """
    发送分工跟催
    :param division_id: 分工ID
    """
    try:
        # 获取当前用户ID
        current_user_id = g.user_id

        # 从表单获取跟催消息
        message = request.form.get('reason', '').strip()
        if not message:
            flash('请输入跟催消息内容', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

        # 调用服务层方法
        success = DefectSolutionDivisionService.send_division_reminder(
            division_id=division_id,
            reminder_by=current_user_id,
            message=message
        )

        if success:
            # 获取关联的缺陷ID用于重定向
            division = DefectSolutionDivision.query.get(division_id)
            if division:
                stage = DefectStage.query.get(division.defect_stage_id)
                if stage:
                    defect = Defect.query.get(stage.defect_id)
                    if not defect:
                        flash('缺陷单已经不存在', 'error')
                        return redirect(url_for('defect.defect_detail', defect_id=stage.defect_id))

                    db.session.commit()
                    return redirect(url_for('defect.defect_detail', defect_id=stage.defect_id))
            else:
                flash('跟催邮件发送失败，未能找到相关分工信息', 'error')
                return redirect(url_for('defect.defect_list'))

        else:
            flash('发送分工跟催消息失败，请检查分工状态或权限', 'error')
            return redirect(request.referrer or url_for('defect.defect_list'))

    except ValueError as e:
        flash(f'操作失败: {str(e)}', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))
    except RuntimeError as e:
        flash(f'操作失败: {str(e)}', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))
    except Exception as e:
        current_app.logger.error(f"发送分工跟催消息时发生未预期错误: {str(e)}")
        flash('处理请求时发生错误，请稍后重试', 'error')
        return redirect(request.referrer or url_for('defect.defect_list'))


@defect_bp.route('/<int:defect_id>/submit_analysis', methods=['POST'])
def submit_analysis(defect_id):
    """提交原因分析 - 支持单个和多个被邀请人情况"""
    detail_url = 'defect.defect_detail'
    try:
        # 获取当前缺陷和阶段
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            flash('缺陷单不存在', 'error')
            return redirect(url_for('defect.defect_list'))
        defect_type = defect.defect_type
        if defect_type == 'simplified':
            detail_url = 'defect.defect_detail_simplified'

        current_stage = DefectStage.query.get(defect.current_stage_id)
        current_stage_id = current_stage.id
        if defect_type == 'simplified':
            current_stage_id = DefectStageService.get_stage_by_defect_and_type(defect_id, 'cause_analysis').id
            stage_type = "cause_analysis"
        else:
            stage_type = "stage_type"
        if (not current_stage or current_stage.stage_type != "cause_analysis") and defect.defect_type != 'simplified':
            flash('当前阶段不是原因分析阶段', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        # 获取原因分析邀请记录
        cause_analysis_invitations = DefectLocaleInvitationService.get_cause_analysis_invitations(defect_id)
        invitee_id_set = {invitation.invitee_id for invitation in cause_analysis_invitations}
        is_same_invitee = len(invitee_id_set) <= 1  # 多个邀请是否都是针对同一人
        current_app.logger.info(f'cause_analysis_invitations 的个数为 {len(cause_analysis_invitations)}')
        if not cause_analysis_invitations:
            flash('还未指定人员进行原因分析定位，无法提交原因分析阶段数据', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))
        # 获取是否暂存参数
        is_draft = request.form.get('is_draft', 'false').lower() == 'true'

        # 判断是单个还是多个被邀请人情况
        is_multi_invitation = len(cause_analysis_invitations) > 1
        print(f"is_multi_invitation{is_multi_invitation}")
        ai_done_act = ""
        if (is_multi_invitation and not is_same_invitee) or defect_type == 'simplified':
            # 多个被邀请人情况 - 只提交当前用户的数据
            invitation_id = request.form.get('invitation_id')
            if not invitation_id:
                flash('缺少邀请记录ID', 'error')
                return redirect(url_for(detail_url, defect_id=defect_id))

            # 查找对应的邀请记录
            current_invitation = None
            for inv in cause_analysis_invitations:
                if str(inv.id) == invitation_id:
                    current_invitation = inv
                    break

            if not current_invitation or current_invitation.invitee_id != g.user_id:
                flash('您没有权限提交此分析', 'error')
                return redirect(url_for(detail_url, defect_id=defect_id))

            # 获取分析内容（新格式：对象数组）
            analyses_json = request.form.get('analyses')
            if not analyses_json and not is_draft:
                flash('原因分析内容不能为空', 'error')
                return redirect(url_for(detail_url, defect_id=defect_id))

            analysis_items = []
            if analyses_json:
                try:
                    # 解析JSON字符串
                    analysis_items = json.loads(analyses_json)

                    # 验证数据格式：应该是对象数组，每个对象包含title和description
                    if not isinstance(analysis_items, list):
                        flash('分析数据格式错误', 'error')
                        return redirect(url_for(detail_url, defect_id=defect_id))

                    # 清理空的分析项
                    cleaned_analysis_items = []
                    for item in analysis_items:
                        if isinstance(item, dict) and 'title' in item and 'description' in item:
                            # 清理描述内容
                            cleaned_description = clean_html_content(item['description'])
                            if cleaned_description:
                                cleaned_analysis_items.append({
                                    'title': item['title'].strip(),
                                    'description': cleaned_description
                                })
                        elif isinstance(item, dict) and 'description' in item:
                            # 兼容只有description的情况
                            cleaned_description = clean_html_content(item['description'])
                            if cleaned_description:
                                cleaned_analysis_items.append({
                                    'title': item.get('title', '原因分析').strip(),
                                    'description': cleaned_description
                                })

                    analysis_items = cleaned_analysis_items
                except json.JSONDecodeError as e:
                    flash('分析数据格式错误', 'error')
                    return redirect(url_for(detail_url, defect_id=defect_id))

            # 构建分析内容（新格式）
            analysis_content = {
                "analyses": analysis_items,
                "submitted_at": datetime.now().isoformat(),
                "invitation_id": invitation_id
            }

            # 提交阶段数据
            stage_data, is_change = DefectStageDataService.submit_stage_data(
                defect_stage_id=current_stage_id,
                data_type=DataType.CAUSE_ANALYSIS,
                content=analysis_content,
                submitted_by=g.user_id,
                locale_invitation_id=current_invitation.id,
                is_draft=is_draft  # 使用is_draft参数
            )

            if not stage_data:
                flash('提交原因分析数据失败', 'error')
                return redirect(url_for(detail_url, defect_id=defect_id))

            # 如果是暂存，则更新邀请状态为InvitationStatus.PENDING, 这种状态不会触发走流程
            if is_draft:
                updated_invitation = DefectLocaleInvitationService.update_invitation_status(
                    current_invitation.id,
                    InvitationStatus.PENDING
                )
                db.session.flush()
                current_app.logger.info(f'暂存更新邀请状态为PENDING: {updated_invitation.status}')
                db.session.commit()
                flash('原因分析已暂存', 'success')
                return redirect(
                    url_for(detail_url, defect_id=defect_id, ai_done_act=request.values.get('ai_done_act', ''),
                            is_change=is_change, stage_type=stage_type))
            else:
                # 更新邀请记录状态为已完成
                updated_invitation = DefectLocaleInvitationService.update_invitation_status(
                    current_invitation.id,
                    InvitationStatus.COMPLETED
                )
                db.session.flush()  # 更新 updated_invitation
                current_app.logger.info(f'updated_invitation.status: {updated_invitation.status}')
                if not updated_invitation:
                    db.session.rollback()
                    flash('更新定位分析邀请状态失败', 'error')
                    return redirect(url_for(detail_url, defect_id=defect_id))

                # 检查是否所有被邀请人都已完成
                all_completed = True
                # 重新获取 cause_analysis_invitations
                new_cause_analysis_invitations = DefectLocaleInvitationService.get_cause_analysis_invitations(defect_id)
                for inv in new_cause_analysis_invitations:
                    # 如果当前状态不是 完成或弃用
                    current_app.logger.debug(f'确认各个邀请的状态： {inv.status}')
                    if str(inv.status) not in ['InvitationStatus.COMPLETED', 'InvitationStatus.CANCELLED']:
                        all_completed = False
                        current_app.logger.info(f'还未完成所有的分析...')
                        break
                if all_completed:
                    ai_done_act = "audit"
                    DefectLocaleInvitationService.update_invitation_status(
                        current_invitation.id,
                        InvitationStatus.PENDING
                    )
                    session['current_invitation'] = current_invitation.id
                    current_stage.status = "StageStatus.EVALUATING"
                    db.session.commit()
                    flash('所有原因分析已提交，等待AI评估中...', 'success')
                else:
                    db.session.commit()
                    flash('原因分析已提交，等待其他人员完成分析', 'success')

        else:
            # 单个被邀请人情况 - 使用新的数据格式
            analyses_json = request.form.get('analyses')
            if not analyses_json and not is_draft:
                flash('原因分析内容不能为空', 'error')
                return redirect(url_for(detail_url, defect_id=defect_id))

            analysis_items = []
            if analyses_json:
                try:
                    # 解析JSON字符串
                    analysis_items = json.loads(analyses_json)

                    # 验证数据格式：应该是对象数组，每个对象包含title和description
                    if not isinstance(analysis_items, list):
                        flash('分析数据格式错误', 'error')
                        return redirect(url_for(detail_url, defect_id=defect_id))

                    # 清理空的分析项
                    cleaned_analysis_items = []
                    for item in analysis_items:
                        if isinstance(item, dict) and 'title' in item and 'description' in item:
                            # 清理描述内容
                            cleaned_description = clean_html_content(item['description'])
                            if cleaned_description:
                                cleaned_analysis_items.append({
                                    'title': item['title'].strip(),
                                    'description': cleaned_description
                                })
                        elif isinstance(item, dict) and 'description' in item:
                            # 兼容只有description的情况
                            cleaned_description = clean_html_content(item['description'])
                            if cleaned_description:
                                cleaned_analysis_items.append({
                                    'title': item.get('title', '原因分析').strip(),
                                    'description': cleaned_description
                                })

                    analysis_items = cleaned_analysis_items
                except json.JSONDecodeError as e:
                    flash('分析数据格式错误', 'error')
                    return redirect(url_for(detail_url, defect_id=defect_id))

            # 构建分析内容（新格式）
            analysis_content = {
                "analyses": analysis_items,
                "submitted_at": datetime.now().isoformat()
            }

            # 提交阶段数据
            stage_data, is_change = DefectStageDataService.submit_stage_data(
                defect_stage_id=current_stage.id,
                data_type=DataType.CAUSE_ANALYSIS,
                content=analysis_content,
                submitted_by=g.user_id,
                locale_invitation_id=cause_analysis_invitations[0].id,
                is_draft=is_draft  # 使用is_draft参数
            )

            if not stage_data:
                flash('提交原因分析失败', 'error')
                return redirect(url_for(detail_url, defect_id=defect_id))

            # 如果是暂存，则更新邀请状态为InvitationStatus.PENDING, 这种状态不会触发走流程
            if is_draft:
                DefectLocaleInvitationService.update_invitation_status(
                    cause_analysis_invitations[0].id,
                    InvitationStatus.PENDING
                )
                session['current_invitation'] = cause_analysis_invitations[0].id
                current_stage.status = "StageStatus.EVALUATING"
                db.session.commit()
                flash('原因分析已暂存', 'success')
                return redirect(
                    url_for(detail_url, defect_id=defect_id, ai_done_act=request.values.get('ai_done_act', '')))
            else:
                # 更新邀请记录状态为已完成
                DefectLocaleInvitationService.update_invitation_status(
                    cause_analysis_invitations[0].id,
                    InvitationStatus.COMPLETED
                )
                session['current_invitation'] = cause_analysis_invitations[0].id
                current_stage.status = "StageStatus.EVALUATING"
                db.session.commit()
                ai_done_act = "audit"
                flash('原因分析已提交，AI评估中...', 'success')
        return redirect(url_for(detail_url, defect_id=defect_id, ai_done_act=ai_done_act, is_change=is_change,
                                stage_type=stage_type))

    except Exception as e:
        db.session.rollback()
        flash(f'提交原因分析时发生错误: {str(e)}', 'error')
        return redirect(url_for(detail_url, defect_id=defect_id))

@defect_bp.route('/<int:defect_id>/assign_for_solution', methods=['POST'])
def assign_for_solution(defect_id):
    """分配开发人员进行解决"""
    try:
        current_app.logger.info('分配开发人员进行解决...')
        # 获取当前缺陷和阶段
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            flash('缺陷单不存在', 'error')
            return redirect(url_for('defect.defect_list'))

        current_stage = DefectStage.query.get(defect.current_stage_id)
        if not current_stage or current_stage.stage_type != "dev_lead_review_analysis":
            flash('当前阶段不是开发主管审核分析阶段', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        # 获取表单中的分工数据
        divisions = []
        i = 1
        while f'division-{i}-module' in request.form:
            module = request.form.get(f'division-{i}-module', '').strip()
            due_date_str = request.form.get(f'division-{i}-due_date', '')
            action_plan = request.form.get(f'division-{i}-action_plan', '').strip()
            assignee_id = request.form.get(f'division-{i}-assignee', '').strip()
            if module and due_date_str and action_plan and assignee_id:
                try:
                    due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                except ValueError:
                    flash(f'分工 {i} 的完成时间格式错误', 'error')
                    return redirect(url_for('defect.defect_detail', defect_id=defect_id))

                divisions.append({
                    'module': module,
                    'due_date': due_date,
                    'action_plan': action_plan,
                    'assign_by_id': int(g.user_id),
                    'assignee_id': int(assignee_id),
                })
            i += 1

        if not divisions:
            flash('至少需要添加一个有效的解决措施分工', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        # 创建开发人员解决措施阶段（先创建 stage 在创建分工）
        # 这里假设有一个获取开发主管ID的方法
        developer_solution_stage = DefectStageService.create_next_stage(
            defect_id=defect_id,
            stage_type_key="developer_solution",
            assigned_to=divisions[0]['assignee_id'],  # 分配给第一个分工的开发人员
            previous_stage_id=current_stage.id,
            user_id=g.user_id
        )
        db.session.flush()

        if not developer_solution_stage:
            db.session.rollback()
            flash('创建解决措施阶段失败', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        # 为每个分工创建记录
        for division in divisions:
            division_obj = DefectSolutionDivisionService.create_division(
                defect_stage_id=developer_solution_stage.id,
                # 需要设置为新创建的的 stage 的id，而非当前dev_lead_review_analysis阶段的 stage id
                module=division['module'],
                due_date=division['due_date'],
                assign_by_id=division['assign_by_id'],
                assignee_id=division['assignee_id'],
                action_plan=division['action_plan']
            )

            extra_params = {'reason': division['action_plan']} if division['action_plan'] else None
            MessageCreator.create_assign_message(
                defect_id=defect_id,
                assignee_id=division['assignee_id'],
                assigner_id=division['assign_by_id'],
                assign_type='solution',
                extra_params=extra_params
            )

            email_content = DefectEmailService.get_assign_email_content(
                defect=defect,
                assign_type='solution',
                assigner_id=division['assign_by_id'],
                reason=division['action_plan']
            )
            email_subject = DefectEmailService.get_email_subject_by_message_type(
                defect=defect,
                message_type=MessageTypes.ASSIGN_SOLUTION
            )
            send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=division['assignee_id'],
                                                                admin_user_id=g.admin_user_id,
                                                                current_user_id=g.user_id,
                                                                content=email_content,
                                                                title=email_subject
                                                                )

            if not division_obj:
                db.session.rollback()
                flash('创建解决措施分工失败', 'error')
                return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        db.session.commit()
        flash('解决措施分工已分配，进入开发人员解决阶段', 'success')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))

    except Exception as e:
        db.session.rollback()
        flash(f'分配解决措施时发生错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))


@defect_bp.route('/<int:defect_id>/assign-for-solution-api', methods=['POST'])
def assign_for_solution_api(defect_id):
    """给 defect.defect_type == 'simplified2' 解决措施- JSON API版本"""
    try:
        # 获取请求数据（支持JSON和form格式）
        if request.is_json:
            data = request.get_json()
            divisions_data = data.get('divisions', [])
        else:
            divisions_data_str = request.form.get('divisions_data')
            if divisions_data_str:
                divisions_data = json.loads(divisions_data_str)
            else:
                divisions_data = []

        # 参数验证
        if not divisions_data or len(divisions_data) == 0:
            return jsonify({
                'error': '参数错误',
                'message': '至少需要添加一个有效的解决措施分工'
            }), 400

        # 获取当前缺陷和阶段
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            return jsonify({
                'code': 1,
                'message': '指定的缺陷单不存在'
            }), 404

        first_invitee_id = divisions_data[0].get('assignee_id')
        review_notes = divisions_data[0].get('review_notes', '')
        if defect.defect_type == 'simplified' or defect.defect_type == 'simplified2':
            developer_solution_stage = DefectStageService.get_stage_by_defect_and_type(defect.id, 'developer_solution')
            if int(first_invitee_id) == int(developer_solution_stage.assigned_to):
                return jsonify({
                    'code': 1,
                    'message': f'所设置的责任人没有变化，无需重新设置。',
                }), 403
            # 更新阶段信息
            developer_solution_stage = DefectStageService.update_stage(stage_id=developer_solution_stage.id,
                                                                       assigned_to=first_invitee_id,  # 分配给指定的（开发人员）
                                                                       notes=review_notes,
                                                                       status=StageStatus.IN_PROGRESS)

            message = '你是解决措施责任人，请尽快处理。'
            # 发送邮件
            email_content = DefectEmailService.get_general_defect_email_content(defect, message=message + '原因：' +review_notes, action_type="")
            # 简化版
            email_subject = f"【{message}】{defect.defect_number} - {defect.title}"

            send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=int(first_invitee_id),
                                                                admin_user_id=g.admin_user_id,
                                                                current_user_id=g.user_id,
                                                                content=email_content,
                                                                title=email_subject)
            # 发送消息
            extra_params = {'reason': review_notes} if review_notes else None
            DefectMessage.create_message(
                send_to_user_id=int(first_invitee_id),
                send_from_user_id=g.user_id,
                defect_id=defect_id,
                message_type=MessageTypes.ASSIGN_SOLUTION,
                content=email_subject,
                extra_params=extra_params
            )
            # 提交到数据库
            db.session.commit()
            return jsonify({
                'code': 0,
                'message': f'已成功设置解决措施人员',
                'data': {
                    'success_count': 1
                }
            })
        else:
            return jsonify({
                'code': 1,
                'message': f'非简化版DTS不能调用此接口',
            }), 403
    except json.JSONDecodeError:
        return jsonify({
            'code': 1,
            'message': 'divisions_data格式错误，必须是有效的JSON'
        }), 400

    except Exception as e:
        # 服务器内部错误
        return jsonify({
            'code': 1,
            'message': f'设置解决措施人员时发生错误: {str(e)}'
        }), 500


@defect_bp.route('/<int:defect_id>/submit_solution', methods=['POST'])
def submit_solution(defect_id):
    """
    提交解决措施 - 支持多个解决措施
    验证缺陷状态、处理解决方案提交、更新分工状态，并在所有分工完成后自动创建下一阶段审核流程。
    """
    detail_url = 'defect.defect_detail'
    try:
        # 获取当前缺陷和阶段
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            flash('缺陷单不存在', 'error')
            return redirect(url_for('defect.defect_list'))
        current_stage = DefectStage.query.get(defect.current_stage_id)
        if defect.defect_type == 'simplified':
            detail_url = 'defect.defect_detail_simplified'
            current_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'developer_solution')
            stage_type = "developer_solution"
        else:
            stage_type = "stage_type"
        if (
                not current_stage or current_stage.stage_type != "developer_solution") and defect.defect_type != 'simplified':
            flash('当前阶段不是开发人员解决措施阶段', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))

        division_id = request.form.get('division_id')
        if not division_id:
            flash('参数错误，缺少分工ID（division_id）字段。', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))

        # 根据 id 获取指定的分工 (无需根据被分工人ID查找)：
        current_division = DefectSolutionDivision.query.get(int(division_id))
        if not current_division:
            flash('未找到对应的分工记录，不能提交解决措施', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))

        # 获取解决措施JSON数据
        solutions_json = request.form.get('solutions', '[]')
        try:
            solutions_data = json.loads(solutions_json)
            # 验证数据结构
            if not isinstance(solutions_data, list):
                flash('解决措施数据格式错误', 'error')
                return redirect(url_for(detail_url, defect_id=defect_id))

            # 提取解决措施内容，确保每个项都有title和description字段
            solutions = []
            for index, item in enumerate(solutions_data):
                if isinstance(item, dict):
                    # 新格式：包含title和description的对象
                    title = item.get('title', f'解决措施 {index + 1}')
                    description = item.get('description', '')

                    # 确保description是字符串类型
                    if description is None:
                        description = ''

                    solutions.append({
                        'title': title,
                        'description': description
                    })
                elif isinstance(item, str):
                    # 旧格式：纯文本，转换为新格式
                    solutions.append({
                        'title': f'解决措施 {index + 1}',
                        'description': item
                    })
                else:
                    # 未知格式，跳过
                    current_app.logger.warning(f'未知的解决措施数据格式: {item}')
                    continue

            # 验证每个解决措施都有非空的title和description（非暂存时才验证）
            is_draft = request.form.get('is_draft', 'false').lower() == 'true'
            if not is_draft:
                for i, solution in enumerate(solutions):
                    if not solution['title'] or not solution['title'].strip():
                        flash(f'第{i + 1}个解决措施的标题不能为空', 'error')
                        return redirect(url_for(detail_url, defect_id=defect_id))

                    # 去除HTML标签检查是否有实际内容
                    import re
                    text_content = re.sub(r'<[^>]+>', '', solution['description'])
                    if not text_content.strip():
                        flash(f'第{i + 1}个解决措施的内容不能为空', 'error')
                        return redirect(url_for(detail_url, defect_id=defect_id))

        except json.JSONDecodeError as e:
            current_app.logger.error(f'解决措施JSON数据解析失败: {str(e)}, 原始数据: {solutions_json}')
            flash(f'解决措施数据格式错误，请检查填写内容', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))

        # 检查是否是暂存操作
        is_draft = request.form.get('is_draft', 'false').lower() == 'true'

        # 如果是暂存，允许空内容
        if not is_draft and not solutions:
            flash('解决措施内容不能为空', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))

        # 构建解决措施内容 - 新的数据结构
        solution_content = {
            "solutions": solutions,  # 现在是一个包含title和description的对象数组
            "submitted_at": datetime.now().isoformat(),
            "division_id": division_id,
            "data_format": "v2"  # 添加数据格式版本标识
        }

        # 提交阶段数据
        stage_data, is_change = DefectStageDataService.submit_stage_data(
            defect_stage_id=current_stage.id,
            data_type=DataType.SOLUTION,
            content=solution_content,
            submitted_by=g.user_id,
            solution_division_id=current_division.id,
            is_draft=is_draft
        )

        if not stage_data:
            flash('提交解决措施数据失败', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))

        # 如果是暂存，则将分工状态设置为 InvitationStatus.PENDING
        if is_draft:
            updated_division = DefectSolutionDivisionService.update_division_status(
                current_division.id,
                InvitationStatus.PENDING,
                '已暂存解决措施'
            )
            db.session.commit()
            flash('解决措施已暂存', 'success')
            return redirect(url_for(detail_url, defect_id=defect_id,
                                    ai_done_act=request.values.get('ai_done_act', ''),
                                    stage_type=stage_type, is_change=is_change))

        # 更新分工状态为已完成
        updated_division = DefectSolutionDivisionService.update_division_status(
            current_division.id,
            InvitationStatus.COMPLETED,
            '已提交解决措施'
        )

        if not updated_division:
            db.session.rollback()
            flash('更新分工状态失败', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))

        # 检查是否所有分工人员都已完成
        all_completed = True
        all_divisions = DefectSolutionDivisionService.get_solution_divisions_by_defect_id(defect_id)

        for div in all_divisions:
            if str(div.status) not in ['InvitationStatus.COMPLETED', 'InvitationStatus.CANCELLED']:
                all_completed = False
                break

        ai_done_act = ""
        if all_completed:
            updated_division = DefectSolutionDivisionService.update_division_status(
                current_division.id,
                InvitationStatus.PENDING,
                '已提交全部解决措施，等待AI评估'
            )
            current_stage.status = "StageStatus.EVALUATING"
            session['current_division_id'] = current_division.id
            ai_done_act = "audit"
            db.session.commit()
            flash('所有解决措施已提交，等待AI评估...', 'success')
        else:
            db.session.commit()
            flash('解决措施已提交，等待其他人员完成', 'success')

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'提交解决措施时发生错误: {str(e)}')
        flash(f'提交解决措施时发生错误: {str(e)}', 'error')
        return redirect(url_for(detail_url, defect_id=defect_id))

    return redirect(url_for(detail_url, defect_id=defect_id,
                            ai_done_act=ai_done_act,
                            stage_type=stage_type,
                            is_change=is_change))

@defect_bp.route('/<int:defect_id>/dev_lead_review_solution', methods=['POST'])
def dev_lead_review_solution(defect_id):
    """开发主管审核解决措施 （同时支持驳回和审核通过进入回归测试阶段），通过则指定回归测试人员"""
    detail_url = 'defect.defect_detail'
    try:
        # 获取当前缺陷和阶段
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            flash('缺陷单不存在', 'error')
            return redirect(url_for('defect.defect_list'))
        if defect.defect_type == 'simplified':
            detail_url = 'defect.defect_detail_simplified'
            current_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'developer_solution')
        elif defect.defect_type == 'simplified2':
            detail_url = 'defect.defect_detail_simplified2'
        # 获取当前用户ID
        user_id = g.user_id
        if not user_id:
            flash('用户未认证', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))

        # 获取表单数据
        approved = request.form.get('approved') == 'true'
        tester_id = request.form.get('tester_id', '') # 指定的回归测试人
        current_app.logger.info('开发主管审核解决措施，通过审核？ {0}'.format(approved))
        review_notes = request.form.get('review_notes', '')

        if tester_id:
            tester_id = int(tester_id)
        # 调用服务层方法进行审核
        tester_regression_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'tester_regression')
        print(f"tester_regression_stage:{tester_regression_stage}")
        if tester_regression_stage and int(tester_id) == int(tester_regression_stage.assigned_to) and defect.defect_type == 'simplified2':
            flash('所设置的责任人没有变化，无需重新设置。', 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))
        defect = DefectWorkflowService.dev_lead_review_solution(
            defect_id, user_id, tester_id, approved, review_notes
        )

        ret_notes = "审核解决措施失败"
        if defect.defect_type == 'simplified' or defect.defect_type == 'simplified2':
            ret_notes = "指定回归测试人员失败"

        if not defect:
            flash(ret_notes, 'error')
            return redirect(url_for(detail_url, defect_id=defect_id))

        # 提交事务
        db.session.commit()

        if approved:
            ret_notes = "解决措施已审核通过，进入测试人员回归测试阶段"
            if defect.defect_type == 'simplified' or defect.defect_type == 'simplified2':
                ret_notes = "指定回归测试人员成功"
            flash(ret_notes, 'success')
        else:
            flash('解决措施已驳回，返回开发人员解决阶段', 'success')

        return redirect(url_for(detail_url, defect_id=defect_id))

    except ValueError as e:
        db.session.rollback()
        flash(f'数据验证错误: {str(e)}', 'error')
        return redirect(url_for(detail_url, defect_id=defect_id))
    except Exception as e:
        db.session.rollback()
        flash(f'审核解决措施时发生错误: {str(e)}', 'error')
        return redirect(url_for(detail_url, defect_id=defect_id))


@defect_bp.route('/<int:defect_id>/submit_regression_test', methods=['POST'])
def submit_regression_test(defect_id):
    """提交回归测试结果"""
    try:
        # 获取当前用户ID
        user_id = g.user_id
        if not user_id:
            flash('用户未认证', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        # 获取当前缺陷和阶段
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            flash('缺陷单不存在', 'error')
            return redirect(url_for('defect.defect_list'))

        current_stage = DefectStage.query.get(defect.current_stage_id)
        if not current_stage or current_stage.stage_type != "tester_regression":
            flash('当前阶段不是回归测试阶段', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        # 获取表单数据
        description = request.form.get('description', '').strip()
        # 检查是否是暂存操作
        is_draft = request.form.get('is_draft', 'false').lower() == 'true'
        # 如果是暂存，允许空内容
        if not is_draft and not description:
            flash('请填写回归测试信息', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        # 构建回归测试内容
        test_content = {
            "description": description,
            "tested_at": datetime.now().isoformat(),
            "test_by": user_id
        }

        # 提交回归测试结果
        stage_data,is_change = DefectStageDataService.submit_stage_data(
            defect_stage_id=current_stage.id,
            data_type=DataType.TEST_RESULT,
            content=test_content,
            submitted_by=user_id,
            is_draft=is_draft
        )

        if not stage_data:
            flash('提交回归测试结果失败', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        # 如果是暂存，则修改阶段状态后提交，无需走流程（创建下一阶段）
        if is_draft:
            current_stage.status = StageStatus.PENDING_UPDATE
            current_stage.updated_time = datetime.now()
            db.session.commit()
            flash('回归测试结果已暂存', 'success')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id,ai_done_act=request.values.get('ai_done_act', ''),is_change=is_change))

        # 创建测试经理审核回归测试阶段
        # test_manager_id = DefectWorkflowService.get_test_manager_id_with_validation(defect)
        #
        # test_manager_review_stage = DefectStageService.create_next_stage(
        #     defect_id=defect_id,
        #     stage_type_key="test_manager_review_regression",
        #     assigned_to=test_manager_id,
        #     previous_stage_id=current_stage.id,
        #     user_id=user_id
        # )
        #
        # if not test_manager_review_stage:
        #     db.session.rollback()
        #     flash('创建审核阶段失败', 'error')
        #     return redirect(url_for('defect.defect_detail', defect_id=defect_id))
        current_stage.status = "StageStatus.EVALUATING"
        db.session.commit()
        flash('回归测试结果已提交，等待AI评估中...', 'success')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id,ai_done_act="audit",is_change=is_change))

    except Exception as e:
        db.session.rollback()
        flash(f'提交回归测试结果时发生错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))


@defect_bp.route('/<int:defect_id>/submit-regression-test-api', methods=['POST'])
def submit_regression_test_api(defect_id):
    """提交回归测试结果 - JSON API版本"""
    try:
        # 获取当前用户ID
        user_id = g.user_id
        if not user_id:
            return jsonify({
                'error': '用户未认证',
                'message': '用户未登录或会话已过期'
            }), 401

        # 获取当前缺陷和阶段
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            return jsonify({
                'error': '缺陷单不存在',
                'message': '指定的缺陷单不存在'
            }), 404
        current_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'tester_regression')
        # 获取请求数据（支持JSON和form格式）
        if request.is_json:
            data = request.get_json()
            description = data.get('description', '').strip()
            is_draft = data.get('is_draft', False)
        else:
            description = request.form.get('description', '').strip()
            is_draft_str = request.form.get('is_draft', 'false')
            is_draft = is_draft_str.lower() == 'true'

        # 检查是否是暂存操作
        # 如果是暂存，允许空内容；如果不是暂存，则必须填写描述
        if not is_draft and not description:
            return jsonify({
                'error': '参数错误',
                'message': '请填写回归测试信息'
            }), 400

        # 构建回归测试内容
        test_content = {
            "description": description,
            "tested_at": datetime.now().isoformat(),
            "test_by": user_id
        }

        # 提交回归测试结果
        stage_data, is_change = DefectStageDataService.submit_stage_data(
            defect_stage_id=current_stage.id,
            data_type=DataType.TEST_RESULT,
            content=test_content,
            submitted_by=user_id,
            is_draft=is_draft
        )

        if not stage_data:
            return jsonify({
                'error': '提交失败',
                'message': '提交回归测试结果失败'
            }), 400

        # 如果是暂存，则修改阶段状态后提交，无需走流程
        if is_draft:
            current_stage.status = StageStatus.PENDING_UPDATE
            current_stage.updated_time = datetime.now()
            db.session.commit()

            return jsonify({
                'code': 0,
                'message': '回归测试结果已暂存',
                'data': {
                    'defect_id': defect_id,
                    'stage_id': current_stage.id,
                    'status': 'draft_saved',
                    'is_draft': True
                }
            })

        current_stage.status = "StageStatus.EVALUATING"
        db.session.commit()

        return jsonify({
            'code': 0,
            'message': '回归测试结果已提交，等待AI评估中...',
            'data': {
                'defect_id': defect_id,
                'stage_id': current_stage.id,
                'status': 'submitted',
                'is_draft': False,
                'next_action': 'ai_evaluation',
                'is_change':is_change
            }
        })

    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'error': '数据验证错误',
            'message': f'数据验证错误: {str(e)}'
        }), 400

    except Exception as e:
        db.session.rollback()
        # 服务器内部错误
        return jsonify({
            'error': '服务器内部错误',
            'message': f'提交回归测试结果时发生错误: {str(e)}'
        }), 500


def clean_html_content(content):
    # 移除空段落（包含空格/nbsp的段落）
    cleaned = re.sub(r'<p>\s*(&nbsp;|\s)*\s*<\/p>', '', content, flags=re.IGNORECASE)

    # 移除只包含空格或&nbsp;的段落
    cleaned = re.sub(r'<p>(\s|&nbsp;)*<\/p>', '', cleaned, flags=re.IGNORECASE)

    # 移除多个连续的<p><br></p>
    cleaned = re.sub(r'(<p><br><\/p>)+', '', cleaned, flags=re.IGNORECASE)

    # 移除<p><br></p>格式
    cleaned = re.sub(r'<p>\s*<br>\s*<\/p>', '', cleaned, flags=re.IGNORECASE)

    # 去除首尾空白
    return cleaned.strip()

@defect_bp.route('/<int:defect_id>/submit-all-api', methods=['POST'])
def submit_all_api(defect_id):
    """简化版2一次性提交所有结果 - JSON API版本"""
    try:
        # 获取当前用户ID
        user_id = g.user_id
        if not user_id:
            return jsonify({
                'error': '用户未认证',
                'message': '用户未登录或会话已过期'
            }), 401

        # 获取当前缺陷和阶段
        defect = DefectService.get_defect_by_id(defect_id)
        if not defect:
            return jsonify({
                'error': '缺陷单不存在',
                'message': '指定的缺陷单不存在'
            }), 404

        defect_description_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'defect_description')
        cause_analysis_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'cause_analysis')
        developer_solution_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'developer_solution')
        tester_regression_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'tester_regression')
        requester_confirm_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'requester_confirm')

        # 获取请求数据（支持JSON和form格式）
        if request.is_json:
            data = request.get_json()
            description_content = data.get('descriptionContent', '').strip()
            if description_content == '' or description_content is None:
                description_content = data.get('description', '').strip()
            analysis_content = data.get('analysisContent', '').strip()
            solution_content = data.get('solutionContent', '').strip()
            regression_content = data.get('regressionContent', '').strip()

            # 新增：获取缺陷基本信息
            title = data.get('title', '').strip()
            severity = data.get('severity', '').strip()
            defect_reproducibility = data.get('defect_reproducibility', '').strip()
            project_version_id = data.get('project_version_id', '').strip()

            # draft、audit、self
            act = data.get('act', '').strip()
            # 回归测试是否通过
            confirmed = data.get('confirmed', False)
            current_app.logger.debug(f'回归是否通过 {confirmed}')
            confirm_notes = data.get('confirm_notes', '')

            stage_assignments_json = data.get('stage_assignments', '')
            if stage_assignments_json:
                try:
                    stage_assignments = json.loads(stage_assignments_json)
                    defect_description_assignee = stage_assignments.get('defect_description', user_id)
                    cause_analysis_assignee = stage_assignments.get('cause_analysis', user_id)
                    developer_solution_assignee  = stage_assignments.get('developer_solution', user_id)
                    tester_regression_assignee = stage_assignments.get('tester_regression', user_id)
                    if defect_description_stage:
                        defect_description_stage.assigned_to = defect_description_assignee
                    if cause_analysis_stage:
                        cause_analysis_stage.assigned_to = cause_analysis_assignee
                    if developer_solution_stage:
                        developer_solution_stage.assigned_to = developer_solution_assignee
                    if tester_regression_stage:
                        tester_regression_stage.assigned_to = tester_regression_assignee
                    else:
                        return jsonify({
                            'code': 1,
                            'message': f'创建缺陷时发生错误: 缺陷描述阶段不存在。'
                        }), 500

                except json.JSONDecodeError as e:
                    current_app.logger.error(f'解析阶段责任人设置失败: {str(e)}')
        else:
            return jsonify({
                'error': '参数格式错误',
                'message': '参数格式错误'
            }), 400

        # 判断是否各阶段都没有填写信息
        all_contents = [description_content, analysis_content, solution_content, regression_content]
        if not any(all_contents) and not any([title, severity, defect_reproducibility, project_version_id]):
            return jsonify({
                'error': '参数错误',
                'message': '请填写缺陷基本信息、缺陷描述、原因分析、解决措施或回归测试信息'
            }), 400

        # 去除空格并检查是否为空
        desc_empty = not (description_content and description_content.strip())
        analysis_empty = not (analysis_content and analysis_content.strip())
        solution_empty = not (solution_content and solution_content.strip())
        regression_empty = not (regression_content and regression_content.strip())

        # 精细化的校验逻辑
        if not desc_empty:
            if not analysis_empty:
                if not solution_empty:
                    # 前三个都有值，regression_content可以有值也可以为空
                    pass
                elif not regression_empty:
                    # 有缺陷描述和原因分析，没有解决措施，但有回归测试信息
                    return jsonify({
                        'error': '参数错误',
                        'message': '请先填写解决措施，再填写回归测试信息'
                    }), 400
            elif not solution_empty or not regression_empty:
                # 有缺陷描述，没有原因分析，但有解决措施或回归测试信息
                return jsonify({
                    'error': '参数错误',
                    'message': '请先填写原因分析，再填写后续内容'
                }), 400
        elif not analysis_empty or not solution_empty or not regression_empty:
            # 没有缺陷描述，但有其他内容
            return jsonify({
                'error': '参数错误',
                'message': '请先填写缺陷描述'
            }), 400

        # 处理缺陷基本信息更新（如果有传入）
        is_defect_basic_info_changed = False
        if any([title, severity, defect_reproducibility, project_version_id]):
            # 解析项目版本ID
            version_id, project_id = parse_project_version_id(project_version_id) if project_version_id else (
            None, None)
            current_app.logger.debug(f'version_id, project_id: {version_id, project_id}')

            # 检查基本信息是否有变化
            if title and title != defect.title:
                is_defect_basic_info_changed = True
                current_app.logger.debug(f'title Changed')
            if severity and severity != defect.severity:
                is_defect_basic_info_changed = True
                current_app.logger.debug(f'severity Changed: new severity: {severity}, old severity: {defect.severity}')
            if defect_reproducibility and defect_reproducibility != defect.defect_reproducibility:
                is_defect_basic_info_changed = True
                current_app.logger.debug(f'defect_reproducibility Changed')
            if version_id and version_id != defect.version_id:
                is_defect_basic_info_changed = True
                current_app.logger.debug(f'version_id Changed')
            if project_id and project_id != defect.project_id:
                is_defect_basic_info_changed = True
                current_app.logger.debug(f'project_id Changed')

            # 如果有变化，更新缺陷基本信息
            if is_defect_basic_info_changed:
                updated_defect = DefectService.update_defect(
                    defect_id=defect_id,
                    title=title if title else defect.title,
                    description=description_content if description_content else defect.description,
                    severity=severity if severity else defect.severity,
                    defect_reproducibility=defect_reproducibility if defect_reproducibility else defect.defect_reproducibility,
                    version_id=version_id if version_id else defect.version_id,
                    project_id=project_id if project_id else defect.project_id,
                    updater_id=user_id
                )
                if not updated_defect:
                    return jsonify({
                        'error': '更新失败',
                        'message': '更新缺陷基本信息失败'
                    }), 400

        # 判断待保存的数据与原有数据是否一致，如果不一致则提交，否则不提交。
        description_data = DefectStageDataService.get_defect_description_data(defect_id)
        # 采用新方法获取原因分析和解决措施数据——不和邀请与分工表关联（与回归测试数据类似）
        cause_analysis_data = DefectStageDataService.get_stage_data_by_type(defect_id, DataType.CAUSE_ANALYSIS)
        solution_data = DefectStageDataService.get_stage_data_by_type(defect_id, DataType.SOLUTION)
        test_result_data = DefectStageDataService.get_test_result_data(defect_id)
        defect_status = defect.status

        is_description_changed = False
        is_analysis_changed = False
        is_solution_changed = False
        is_test_result_changed = False
        all_changed_items = []
        if f"self_res_{defect_id}" in session and 'all_changed_items' in session[f"self_res_{defect_id}"]:
            all_changed_items = session[f'self_res_{defect_id}']['all_changed_items']


        # 检查缺陷描述是否有变化
        if not description_data and description_content:
            is_description_changed = True
        elif description_data and len(description_data) > 0 and description_data[0].get('content') and description_data[
            0].get('content').get('description'):
            original_description = description_data[0].get('content').get('description')
            original_description = clean_html_content(original_description)
            description_content_r = clean_html_content(description_content)
            if  description_content_r != original_description:
                is_description_changed = True
            if defect_description_stage.assigned_to==session['user_id'] and  description_data[0].get('ai_suggestion') is None:
                    if '缺陷基本信息' not in all_changed_items and "缺陷描述" not in all_changed_items:
                        is_description_changed = True
        # 检查原因分析是否有变化
        if not cause_analysis_data and analysis_content:
            is_analysis_changed = True
        elif cause_analysis_data and len(cause_analysis_data) > 0 and cause_analysis_data[0].get('content') and \
                cause_analysis_data[0].get('content').get('analyses'):
            original_analysis = cause_analysis_data[0].get('content').get('analyses')[0] if cause_analysis_data[0].get(
                'content').get('analyses') else ''
            original_analysis = clean_html_content(original_analysis)
            analysis_content_r = clean_html_content(analysis_content)
            if analysis_content and analysis_content_r != original_analysis:
                is_analysis_changed = True
            if  cause_analysis_stage.assigned_to==session['user_id'] and cause_analysis_data[0].get('ai_suggestion') is None:
                if '原因分析' not in all_changed_items:
                    is_analysis_changed = True

        # 检查解决措施是否有变化
        if not solution_data and solution_content:
            is_solution_changed = True
        elif solution_data and len(solution_data) > 0 and solution_data[0].get('content') and solution_data[0].get(
                'content').get('solutions'):
            original_solution = solution_data[0].get('content').get('solutions')[0] if solution_data[0].get(
                'content').get('solutions') else ''
            original_solution = clean_html_content(original_solution)
            solution_content_r = clean_html_content(solution_content)
            if solution_content and solution_content_r != original_solution:
                is_solution_changed = True
            if developer_solution_stage.assigned_to==session['user_id'] and solution_data[0].get('ai_suggestion') is None:
                if '解决措施' not in all_changed_items:
                    is_solution_changed = True

        # 检查回归测试是否有变化
        if not test_result_data and regression_content:
            is_test_result_changed = True
        elif test_result_data and len(test_result_data) > 0 and test_result_data[0].get('content') and test_result_data[
            0].get('content').get('description'):
            original_regression = test_result_data[0].get('content').get('description')
            original_regression = clean_html_content(original_regression)
            regression_content_r = clean_html_content(regression_content)
            if regression_content and regression_content_r != original_regression:
                is_test_result_changed = True
            if tester_regression_stage.assigned_to==session['user_id'] and test_result_data[0].get('ai_suggestion') is None:
                if '回归测试' not in all_changed_items:
                    is_test_result_changed = True

        # 构建缺陷描述内容并提交（如果有变化，并且有权限）
        if is_description_changed and description_content and user_id == defect_description_stage.assigned_to:
            description_data_content = {
                "description": description_content,
                "submitted_at": datetime.now().isoformat(),
                "submitted_by": user_id
            }

            stage_data, is_change = DefectStageDataService.submit_stage_data(
                defect_stage_id=defect_description_stage.id,
                data_type=DataType.DEFECT_DESCRIPTION,
                content=description_data_content,
                submitted_by=user_id,
                is_draft=False
            )
            '''
            if defect.current_stage_id < cause_analysis_stage.id and act not in ['draft', 'self']:  # 非暂存、非自评的提交才需要修改当前阶段
                defect.current_stage_id = cause_analysis_stage.id
            # 发送邮件
            email_content = DefectEmailService.get_general_defect_email_content(defect, "缺陷描述已提交", "原因分析")
            # 简化版
            DESCRIPTION_CHANGED = f"【缺陷描述已提交，请处理原因分析】{defect.defect_number} - {defect.title}"
            email_subject = DESCRIPTION_CHANGED
            send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=cause_analysis_stage.assigned_to,
                                                                admin_user_id=g.admin_user_id,
                                                                current_user_id=g.user_id,
                                                                content=email_content,
                                                                title=email_subject)
            # 发送消息
            DefectMessageService.save_message(
                send_to_user_id=cause_analysis_stage.assigned_to,
                send_from_user_id=g.user_id,
                defect_id=defect_id,
                message_type=MessageTypes.DESCRIPTION_CHANGED,
            )
            '''

            if stage_data:
                defect_description_stage.status = "StageStatus.EVALUATING"

        # 构建原因分析内容并提交（如果有变化，并且有权限）
        if is_analysis_changed and analysis_content and user_id == cause_analysis_stage.assigned_to:
            analyses = [analysis_content] if analysis_content else []
            analysis_data = {
                "analyses": analyses,
                "submitted_at": datetime.now().isoformat(),
                "submitted_by": user_id
            }

            stage_data, is_change = DefectStageDataService.submit_stage_data(
                defect_stage_id=cause_analysis_stage.id,
                data_type=DataType.CAUSE_ANALYSIS,
                content=analysis_data,
                submitted_by=user_id,
                is_draft=False
            )
            '''
            if defect.current_stage_id < developer_solution_stage.id and act not in ['draft', 'self']:  # 非暂存、非自评的提交才需要修改当前阶段
                defect.current_stage_id = developer_solution_stage.id
            # 发送邮件
            email_content = DefectEmailService.get_general_defect_email_content(defect, "原因分析已提交", "解决措施")
            # 简化版
            ANALYSIS_CHANGED= f"【原因分析已提交，请处理解决措施】{defect.defect_number} - {defect.title}"
            email_subject = ANALYSIS_CHANGED
            send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=developer_solution_stage.assigned_to,
                                                            admin_user_id=g.admin_user_id,
                                                            current_user_id=g.user_id,
                                                            content=email_content,
                                                            title=email_subject)
            # 发送消息
            DefectMessageService.save_message(
                send_to_user_id=developer_solution_stage.assigned_to,
                send_from_user_id=g.user_id,
                defect_id=defect_id,
                message_type=MessageTypes.ANALYSIS_CHANGED,
            )
           '''
            if stage_data:
                cause_analysis_stage.status = "StageStatus.EVALUATING"

        # 构建解决措施内容并提交（如果有变化，并且有权限）
        if is_solution_changed and solution_content and user_id == developer_solution_stage.assigned_to:
            solutions = [solution_content] if solution_content else []
            solution_data_content = {
                "solutions": solutions,
                "submitted_at": datetime.now().isoformat(),
                "submitted_by": user_id
            }

            stage_data, is_change = DefectStageDataService.submit_stage_data(
                defect_stage_id=developer_solution_stage.id,
                data_type=DataType.SOLUTION,
                content=solution_data_content,
                submitted_by=user_id,
                is_draft=False
            )

            '''
            if defect.current_stage_id < tester_regression_stage.id and act not in ['draft', 'self']:  # 非暂存、非自评的提交才需要修改当前阶段
                defect.current_stage_id = tester_regression_stage.id
            # 发送邮件
            email_content = DefectEmailService.get_general_defect_email_content(defect, "解决措施已提交", "回归测试")
            # 简化版
            SOLUTION_CHANGED= f"【解决措施已提交，请处理回归测试】{defect.defect_number} - {defect.title}"
            email_subject = SOLUTION_CHANGED
            send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=tester_regression_stage.assigned_to,
                                                                admin_user_id=g.admin_user_id,
                                                                current_user_id=g.user_id,
                                                                content=email_content,
                                                                title=email_subject)
            # 发送消息
            DefectMessageService.save_message(
                send_to_user_id=tester_regression_stage.assigned_to,
                send_from_user_id=g.user_id,
                defect_id=defect_id,
                message_type=MessageTypes.SOLUTION_CHANGED,
            )
            '''
            if stage_data:
                developer_solution_stage.status = "StageStatus.EVALUATING"

        # 构建回归测试内容并提交（如果有变化，并且有权限）
        if is_test_result_changed and regression_content and user_id == tester_regression_stage.assigned_to:
            test_data = {
                "description": regression_content,
                "submitted_at": datetime.now().isoformat(),
                "submitted_by": user_id
            }
            print(f"test_data:{test_data}")

            stage_data, is_change = DefectStageDataService.submit_stage_data(
                defect_stage_id=tester_regression_stage.id,
                data_type=DataType.TEST_RESULT,
                content=test_data,
                submitted_by=user_id,
                is_draft=False
            )
            '''
            if requester_confirm_stage and defect.current_stage_id < requester_confirm_stage.id and act not in ['draft', 'self']:  # 非暂存、非自评的提交才需要修改当前阶段
                defect.current_stage_id = requester_confirm_stage.id
            # 发送邮件
            email_content = DefectEmailService.get_general_defect_email_content(defect, "回归测试已提交", "确认关闭")
            # 简化版
            REGRESSION_CHANGED = f"【回归测试已提交，请确认关闭】{defect.defect_number} - {defect.title}"
            email_subject = REGRESSION_CHANGED
            send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=defect_description_stage.assigned_to,
                                                            admin_user_id=g.admin_user_id,
                                                            current_user_id=g.user_id,
                                                            content=email_content,
                                                            title=email_subject)
          
            # 发送消息
            DefectMessageService.save_message(
                send_to_user_id=defect_description_stage.assigned_to,
                send_from_user_id=g.user_id,
                defect_id=defect_id,
                message_type=MessageTypes.REGRESSION_CHANGED,
            )
             '''
            if stage_data:
                tester_regression_stage.status = "StageStatus.EVALUATING"

        db.session.commit()

        # 构建响应消息
        changed_items = []
        val_tag = False
        if is_defect_basic_info_changed:
            changed_items.append("缺陷基本信息")
            val_tag = True
        if is_description_changed:
            changed_items.append("缺陷描述")
            val_tag = True
        if is_analysis_changed:
            changed_items.append("原因分析")
            val_tag = True
        if is_solution_changed:
            changed_items.append("解决措施")
            val_tag = True
        if is_test_result_changed:
            changed_items.append("回归测试")
            val_tag = True

        need_val = False
        if val_tag:
            if act in ['self','audit']:
                message = f"{'、'.join(changed_items)}已提交，等待AI评估中..."
            elif act=='draft':
                message = f"{'、'.join(changed_items)}已经暂存。"
            else:
                message = '参数错误。'
        else:
            status_changed_message = ''
            if  act=='audit': # 提交
                if f"self_res_{defect_id}" not in session:
                    message = "未检测到评估数据变化，无需评估"
                else:
                    message = "等待AI评估中... " + status_changed_message
                    need_val = True
            else:
                if act=='draft': # 暂存
                    message = "已经暂存"
                else: # self AI自评
                    message = "未检测到数据变化，请自行查看页面表格内已有的评估"
                need_val = False

        return jsonify({
            'code': 0,
            'message': message,
            'need_val':need_val,
            'data': {
                'defect_id': defect_id,
                'status': defect.status,
                'is_draft': False,
                'next_action': 'ai_evaluation',
                'changed_items': changed_items
            }
        })

    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'error': '数据验证错误',
            'message': f'数据验证错误: {str(e)}'
        }), 400

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'提交所有数据时发生错误: {str(e)}')
        return jsonify({
            'error': '服务器内部错误',
            'message': f'提交数据时发生错误: {str(e)}'
        }), 500


@defect_bp.route('/<int:defect_id>/test_manager_review_regression', methods=['POST'])
def test_manager_review_regression(defect_id):
    """测试经理审核回归测试 （支持 驳回给测试人员 和审核通过）"""
    try:
        # 获取当前用户ID
        user_id = g.user_id
        if not user_id:
            flash('用户未认证', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        # 获取表单数据
        approved = request.form.get('approved') == 'true'
        review_notes = request.form.get('review_notes', '')

        # 调用服务层方法进行审核
        defect = DefectWorkflowService.test_manager_review_regression(
            defect_id, user_id, approved, review_notes
        )

        if not defect:
            flash('审核回归测试结果失败', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))


        email_content = DefectEmailService.get_general_defect_email_content(defect, "审核回归测试完成", "提出人确认")
        REVIEW_REGRESSION_TEST = f"【审核回归测试完成，请处理提出人确认】{defect.defect_number} - {defect.title}"
        email_subject = REVIEW_REGRESSION_TEST
        send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=defect.creator.user_id,
                                                            admin_user_id=g.admin_user_id,
                                                            current_user_id=g.user_id,
                                                            content=email_content,
                                                            title=email_subject)
        # 发送消息
        DefectMessageService.save_message(
            send_to_user_id=defect.creator.user_id,
            send_from_user_id=g.user_id,
            defect_id=defect.id,
            message_type=MessageTypes.REVIEW_REGRESSION_TEST,
        )

        # 提交事务
        db.session.commit()
        current_app.logger.info('测试经理审核回归测试，通过审核？ {0}'.format(approved))
        if approved:
            flash('回归测试已审核通过，缺陷流程完成', 'success')
        else:
            flash('回归测试已驳回，返回测试人员重新测试', 'success')

        return redirect(url_for('defect.defect_detail', defect_id=defect_id))

    except ValueError as e:
        db.session.rollback()
        flash(f'数据验证错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))
    except Exception as e:
        db.session.rollback()
        flash(f'审核回归测试时发生错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))


@defect_bp.route('/<int:defect_id>/requester_confirm', methods=['POST'])
def requester_confirm(defect_id):
    """提出人确认缺陷解决 （支持驳回：接收驳回意见并返回上一阶段； 支持确认通过，问题关闭）"""
    try:
        # 获取当前用户ID
        user_id = g.user_id
        if not user_id:
            flash('用户未认证', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        # 获取表单数据
        confirmed = request.form.get('confirmed') == 'true'
        confirm_notes = request.form.get('confirm_notes', '')

        # 调用服务层方法进行确认
        defect = DefectWorkflowService.requester_confirm(
            defect_id, user_id, confirmed, confirm_notes
        )

        if not defect:
            flash('确认缺陷解决失败', 'error')
            return redirect(url_for('defect.defect_detail', defect_id=defect_id))

        # 提交事务
        db.session.commit()

        if confirmed:
            flash('缺陷已确认解决，问题关闭', 'success')
        else:
            flash('流程已驳回，返回上一阶段', 'success')

        return redirect(url_for('defect.defect_detail', defect_id=defect_id))

    except ValueError as e:
        db.session.rollback()
        flash(f'数据验证错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))
    except Exception as e:
        db.session.rollback()
        flash(f'确认缺陷解决时发生错误: {str(e)}', 'error')
        return redirect(url_for('defect.defect_detail', defect_id=defect_id))


@defect_bp.route('/<int:defect_id>/requester-confirm-api', methods=['POST'])
def requester_confirm_api(defect_id):
    """提出人确认缺陷解决 API 版本（支持驳回：接收驳回意见并返回上一阶段；支持确认通过，问题关闭）- JSON API版本"""
    try:
        # 获取当前用户ID
        user_id = g.user_id
        if not user_id:
            return jsonify({
                'error': '用户未认证',
                'message': '用户未登录或会话已过期'
            }), 401

        # 获取请求数据（支持JSON和form格式）
        if request.is_json:
            data = request.get_json()
            confirmed = data.get('confirmed', False)
            confirm_notes = data.get('confirm_notes', '')
        else:
            confirmed_str = request.form.get('confirmed', 'false')
            confirmed = confirmed_str.lower() == 'true'
            confirm_notes = request.form.get('confirm_notes', '')

        # 参数验证
        if confirmed is None:
            return jsonify({
                'error': '参数错误',
                'message': 'confirmed参数不能为空'
            }), 400

        # 调用服务层方法进行确认
        defect = DefectWorkflowService.requester_confirm(
            defect_id, user_id, confirmed, confirm_notes
        )

        if not defect:
            return jsonify({
                'error': '确认失败',
                'message': '确认缺陷解决失败，请检查缺陷状态或权限'
            }), 400

        # 提交事务
        db.session.commit()

        # 构建成功响应
        if confirmed:
            return jsonify({
                'code': 0,
                'message': '缺陷已确认解决，问题关闭',
                'data': {
                    'defect_id': defect_id,
                    'status': 'confirmed',
                    'confirm_notes': confirm_notes
                }
            })
        else:
            return jsonify({
                'code': 0,
                'message': '流程已驳回，返回上一阶段',
                'data': {
                    'defect_id': defect_id,
                    'status': 'rejected',
                    'confirm_notes': confirm_notes
                }
            })

    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'error': '数据验证错误',
            'message': f'数据验证错误: {str(e)}'
        }), 400

    except Exception as e:
        db.session.rollback()
        # 服务器内部错误
        return jsonify({
            'error': '服务器内部错误',
            'message': f'确认缺陷解决时发生错误: {str(e)}'
        }), 500

# 统计接口
@defect_bp.route('/api/di_statistics', methods=['GET'])
def di_statistics():
    """
    一、统计每月缺陷单的DI值

    请求参数:
    - start_date: 开始日期 (YYYY-MM-DD)
    - end_date: 结束日期 (YYYY-MM-DD)
    - project_id: 项目ID (可选)
    - version_id: 版本ID (可选)
    - version_projects: 项目ID 版本ID （多个，逗号分隔，可选）
    - defect_status: 状态筛选 ('all', 'open', 'closed')
    Returns:
        JSON: 包含DI配置和按月统计的DI值
        Example:
    GET /defect/api/di_statistics?start_date=2023-10-01&end_date=2025-10-31&project_id=1&defect_status=all
    """
    return DefectStaticsService.get_di_statistics()

@defect_bp.route('/api/defect_nums_statistics', methods=['GET'])
def get_defect_nums():
    """
    二、按月统计缺陷数量接口

    统计指定条件下每月创建的缺陷数量，支持多种过滤条件。
    参数:
    start_date: 开始日期 (YYYY-MM-DD)
    end_date: 结束日期 (YYYY-MM-DD)
    project_id: 项目ID (可选)
    version_id: 版本ID (可选)
    version_projects: 项目ID 版本ID （多个，逗号分隔，可选）
    severity (str): 严重程度筛选，可选值：'致命'/'严重'/'一般'/'提示'/'all'(全部)
    defect_status (str): 状态筛选，可选值：'open'(未关闭)/'closed'(已关闭)/'all'(全部)

    返回:
        JSON响应对象，包含：
            success: 请求是否成功
            data: 月度统计数组，每个元素包含年、月和缺陷数量
            total: 所有月份的缺陷总数
    Example:
    GET /defect/api/defect_nums_statistics?start_date=2023-10-01&end_date=2025-10-31&project_id=1&severity=严重&defect_status=all

    Response:
    {
      "code": 0,
      "data": [
        {
          "count": 32,
          "month": 9,
          "year": 2025
        }
      ],
      "success": true,
      "total": 32
    }
    """
    return DefectStaticsService.get_defect_monthly_nums()

@defect_bp.route('/api/ai-scores_statistics', methods=['GET'])
def ai_score_stats():
    """
    三、获取AI评分统计信息
    查询参数:
        start_date: 开始日期 (格式: YYYY-MM-DD)
        end_date: 结束日期 (格式: YYYY-MM-DD)
        project_id: 项目ID（可选）
        version_id: 版本ID（可选）
        version_projects: 项目ID 版本ID （多个，逗号分隔，可选）
        defect_status: 缺陷状态 ('all', 'open', 'closed')
    Example:
    GET /defect/api/ai-scores_statistics?start_date=2023-10-01&end_date=2025-10-31&project_id=1&defect_status=all
    Response:
     {
      "code": 0,
      "data": [
        {
          "count": 1,
          "score": 1
        },
        {
          "count": 1,
          "score": 2
        },
        {
          "count": 1,
          "score": 3
        },
        {
          "count": 1,
          "score": 4
        },
        {
          "count": 1,
          "score": 5
        },
        {
          "count": 1,
          "score": 6
        },
        {
          "count": 1,
          "score": 7
        },
        {
          "count": 2,
          "score": 8
        },
        {
          "count": 2,
          "score": 9
        },
        {
          "count": 2,
          "score": 10
        }
      ],
      "success": true,
      "total": 13
    }
    """
    return DefectStaticsService.get_ai_score_statistics()


@defect_bp.route('/api/stage_duration_statistics', methods=['GET'])
def get_stage_duration():
    """
    四、统计问题单在不同阶段停留的平均时间（天数）

        功能说明：
        - 计算缺陷在各个处理阶段的平均停留时间（以天为单位）
        - 支持按创建日期范围、项目ID、版本ID和缺陷状态进行筛选
        - 返回按阶段顺序排序的结果列表

        查询参数：
        - start_date: 开始日期（格式：YYYY-MM-DD），可选
        - end_date: 结束日期（格式：YYYY-MM-DD），可选
        - project_id: 项目ID，整数类型，可选
        - version_id: 版本ID，整数类型，可选
        - version_projects: 项目ID 版本ID （多个，逗号分隔，可选）
        - defect_status: 缺陷状态筛选，可选值：'all'(全部), 'open'(开启), 'closed'(关闭)，默认为'all'
    Example:
    GET /defect/api/stage_duration_statistics?start_date=2023-10-01&end_date=2025-10-31&project_id=1&defect_status=open
    Response:
        {
          "code": 0,
          "data": [
            {
              "avg_duration": 2.59,
              "stage_name": "缺陷描述",
              "stage_order": 1,
              "stage_type": "defect_description"
            },
            {
              "avg_duration": 5.25,
              "stage_name": "测试经理审核描述",
              "stage_order": 2,
              "stage_type": "test_manager_review_desc"
            },
            {
              "avg_duration": 3.77,
              "stage_name": "开发人员定位问题",
              "stage_order": 4,
              "stage_type": "cause_analysis"
            },
            {
              "avg_duration": 4.56,
              "stage_name": "开发主管审核原因分析",
              "stage_order": 5,
              "stage_type": "dev_lead_review_analysis"
            },
            {
              "avg_duration": 4.77,
              "stage_name": "开发人员解决措施",
              "stage_order": 6,
              "stage_type": "developer_solution"
            },
            {
              "avg_duration": 6.76,
              "stage_name": "开发主管审核解决措施",
              "stage_order": 7,
              "stage_type": "dev_lead_review_solution"
            },
            {
              "avg_duration": 4.26,
              "stage_name": "测试人员回归测试",
              "stage_order": 8,
              "stage_type": "tester_regression"
            },
            {
              "avg_duration": 6.08,
              "stage_name": "测试经理审核回归测试",
              "stage_order": 9,
              "stage_type": "test_manager_review_regression"
            },
            {
              "avg_duration": 11.37,
              "stage_name": "提出人确认",
              "stage_order": 10,
              "stage_type": "requester_confirm"
            }
          ],
          "success": true
        }
    """
    return DefectStaticsService.get_stage_duration()




@defect_bp.route('/api/stage_statistics', methods=['GET'])
def defect_stage_statistics():
    """
    五、缺陷阶段统计接口

    统计指定时间范围内、指定项目或版本中、指定状态各缺陷阶段（StageStatus.IN_PROGRESS）的缺陷单数量，
    结果按阶段顺序(stage_order)升序排列

    Query Parameters:
        start_date (str): 开始日期，格式为YYYY-MM-DD，必填
        end_date (str): 结束日期，格式为YYYY-MM-DD，必填
        project_id (int, optional): 项目ID，与version_id二选一
        version_id (int, optional): 版本ID，与project_id二选一
        version_projects: 项目ID 版本ID （多个，逗号分隔，可选）
        defect_status: 缺陷状态筛选，可选值：'all'(全部), 'open'(开启), 'closed'(关闭)，默认为'all'

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

    Example:
        GET /defect/api/stage_statistics?start_date=2023-10-01&end_date=2025-10-31&project_id=1&defect_status=all
        Response:
        {
          "code": 0,
          "statistics": [
            {
              "defect_count": 49,
              "stage_name": "缺陷描述",
              "stage_order": 1
            },
            {
              "defect_count": 27,
              "stage_name": "测试经理审核描述",
              "stage_order": 2
            },
            {
              "defect_count": 27,
              "stage_name": "开发人员定位问题",
              "stage_order": 4
            },
            {
              "defect_count": 5,
              "stage_name": "开发主管审核原因分析",
              "stage_order": 5
            },
            {
              "defect_count": 24,
              "stage_name": "开发人员解决措施",
              "stage_order": 6
            },
            {
              "defect_count": 8,
              "stage_name": "开发主管审核解决措施",
              "stage_order": 7
            },
            {
              "defect_count": 3,
              "stage_name": "测试人员回归测试",
              "stage_order": 8
            },
            {
              "defect_count": 2,
              "stage_name": "测试经理审核回归测试",
              "stage_order": 9
            },
            {
              "defect_count": 10,
              "stage_name": "提出人确认",
              "stage_order": 10
            }
          ]
        }

    Errors:
        400: 参数错误（缺少必要参数、日期格式错误、同时提供了project_id和version_id）
        500: 服务器内部错误
    """
    return DefectStaticsService.defect_stage_statistics()



#自评
@defect_bp.route('/ai_done/<self_or_audit>/<int:defect_id>', methods=['POST','GET'])
def defect_ai_done(self_or_audit,defect_id):
    '''
    :param self_or_audit: self:自评，audit：提交审核
    :param defect_id: 缺陷id
    :param request_stage_type 阶段类型,简化流的时候有效
    :return:
    '''
    defect = Defect.query.join(Defect.current_stage).join(DefectStage.assignee).filter(
            Defect.id==defect_id,
    ).first()
    if defect is None:
        return {"error":"缺陷记录不存在"},400
    defect_type = defect.defect_type
    request_stage_type = request.values.get('request_stage_type',"stage_type")
    print(f"request_stage_type:{request_stage_type}")
    if self_or_audit == "audit": # 提交审核
        infos = '请联系全板块管理员或项目管理员配置项目成员。'
        is_raise_exception = True
        if defect.defect_type == "simplified":
            is_raise_exception = False
        try:
            test_manager_id = DefectWorkflowService.get_test_manager_id_with_validation(defect, is_raise_exception)
        except ValueError as e:
            DefectStage.query.filter(DefectStage.id == defect.current_stage.id).update(
                {"status": "StageStatus.IN_PROGRESS"})
            defect_services.commit_changes()
            # 捕获 ValueError 并返回给前端
            return {"error": str(e) + infos}, 409  # Conflict 请求与服务器当前状态冲突
        try:
            dev_lead_id = DefectWorkflowService.get_dev_manager_id_with_validation(defect, is_raise_exception)
        except ValueError as e:
            DefectStage.query.filter(DefectStage.id == defect.current_stage.id).update(
                {"status": "StageStatus.IN_PROGRESS"})
            defect_services.commit_changes()
            # 捕获 ValueError 并返回给前端
            return {"error": str(e) + infos}, 409  # Conflict 请求与服务器当前状态冲突

    stage_type = defect.current_stage.stage_type
    stage_status = defect.current_stage.status
    if stage_status not in ["StageStatus.IN_PROGRESS","StageStatus.PENDING_UPDATE","StageStatus.DRAFT","StageStatus.EVALUATING"] and request_stage_type=="stage_type" or  request_stage_type!="stage_type" and stage_status not in ["StageStatus.IN_PROGRESS","StageStatus.PENDING_UPDATE","StageStatus.DRAFT","StageStatus.EVALUATING","StageStatus.COMPLETED"]:
        return {
            "error":"缺陷记录状态错误！"
        },400
    payload = {
        "service_type":0,
        "async": False,
        "items":[],
    }
    current_step = -1
    defect_desc_stage_data_id = 0
    record_user_ids  = []
    if stage_type in ["defect_description","draft_creation","tester_confirm_desc","cause_analysis","developer_solution","tester_regression"]:
        current_step =0
        description_data = DefectStageDataService.get_defect_description_data(defect_id)
        project_version_name,_ = defect_services.get_project_version(defect)

        descriptions = f"""
            缺陷所属产品线/技术族:{project_version_name}<br>
            缺陷影响程度:{defect.severity}<br>
            缺陷是否可重现:{defect.defect_reproducibility}<br>
            缺陷标题:{defect.title}<br>
        """
        record_user_ids = []
        for data in description_data:
            defect_desc_stage_data_id = data['id']
            record_user_ids.append(data['submitted_by'])
            if 'description' in data['content']:
                if defect_type == 'simplified':
                    descriptions = data['content']['description']
                else:
                    descs = json.loads(data['content']['description'])
                    for desc in descs:
                        descriptions = descriptions + desc['title'] + "<br>" + desc['description'] + "<br>"
        payload["items"] = [descriptions, "", "", ""]
    cause_analysis_data_ids = []
    defect_cause_analysis_stage_id = 0
    if stage_type in ["cause_analysis", "developer_solution", "tester_regression"]:
        current_step = 1
        cause_analysis_data = DefectStageDataService.get_locale_invitation_data(defect_id)
        record_user_ids = []
        analysis_parts = []
        for data in cause_analysis_data:
            record_user_ids.append(data['invitee_id'])
            defect_cause_analysis_stage_id = data['defect_stage_id']
            cause_analysis_data_ids.append(data['id'])
            current_app.logger.debug(f"data_content: {data['content']}")

            if "analyses" in data['content']:
                # 提取每个分析条目的标题和描述
                analysis_items = []
                for item in data['content']['analyses']:
                    title = item['title']
                    description = item['description']
                    analysis_items.append(f"{title}: {description}")

                # 将当前data的分析内容作为一个部分
                if analysis_items:
                    analysis_parts.append("<br>".join(analysis_items))

        # 用双<br>分隔不同data的分析内容
        analysis = "<br><br>".join(analysis_parts)

        payload["items"][1] = analysis
        if defect_cause_analysis_stage_id== 0:
            defect_description_stage = DefectStageService.get_stage_by_defect_and_type(defect.id, 'cause_analysis')
            defect_cause_analysis_stage_id = defect_description_stage.id
    solution_data_ids = []
    defect_solution_stage_id = 0
    if stage_type in ["developer_solution", "tester_regression"]:
        current_step = 2
        solution_data = DefectStageDataService.get_solution_division_data(defect_id)
        record_user_ids = []
        solution_parts = []

        for data in solution_data:
            record_user_ids.append(data['submitted_by'])
            solution_data_ids.append(data['id'])
            defect_solution_stage_id = data['defect_stage_id']

            # 提取模块和行动措施信息
            module_info = f"修改模块:{data.get('module', '未知模块')},执行措施:{data.get('action_plan', '未指定')}"

            # 构建解决方案内容
            if "solutions" in data.get('content', {}):
                # 提取每个解决方案条目的标题和描述
                solution_items = []
                for item in data['content']['solutions']:
                    title = item.get('title', '无标题')
                    description = item.get('description', '无描述')
                    solution_items.append(f"{title}: {description}")

                # 将当前data的解决方案内容作为一个部分
                if solution_items:
                    # 组合模块信息和解决方案
                    full_solution = f"{module_info}<br>" + "<br>".join(solution_items)
                    solution_parts.append(full_solution)

        # 将所有解决方案部分用两个<br>连接
        solution_contents = "<br><br>".join(solution_parts)
        payload["items"][2] = solution_contents
        if defect_solution_stage_id == 0:
            defect_description_stage = DefectStageService.get_stage_by_defect_and_type(defect.id, 'developer_solution')
            defect_solution_stage_id = defect_description_stage.id

    defect_tester_regression_data_id = 0
    if stage_type in ["tester_regression"]:
        current_step = 3
        test_result_data = DefectStageDataService.get_test_result_data(defect_id)
        test_results = ""
        record_user_ids = []
        for data in test_result_data:
            if defect_tester_regression_data_id == 0:
                defect_tester_regression_data_id = data['id']
            record_user_ids.append(data['submitted_by'])
            if defect_type == 'simplified':
                test_results = data['content']['description']
            else:
                if "description" in data['content']:
                    descs = json.loads(data['content']['description'])
                    for desc in descs:
                        test_results = test_results + desc['title'] +"<br>" +desc['description']+"<br>"
        payload["items"][3] = test_results
    # 数据校验
    res,code= defect_services.ai_done_check(record_user_ids,current_step,g.user_id)
    if res is not None:
        return res,code
    is_change_audit = request.values.get('is_change_audit','')
    ai_sug_score_id = None
    if is_change_audit != "" and self_or_audit=="audit" or self_or_audit=="self" or f"self_res_{defect_id}_{request_stage_type}" not in session:
        try:
            payload['email_user_id'] = g.user_id
            payload['defect_id'] = defect_id
            res = json.loads(Ai.my_val_api_done(payload,g.admin_user_id))
            ai_sug_score_id = res['record_id']
        except Exception as e:
            res = {
                "code":-1,
                "items":[],
                "msg":"评估网络超时"
            }
    elif is_change_audit =="" and self_or_audit =="audit":
        res = session[f"self_res_{defect_id}_{request_stage_type}"]
        ai_sug_score_id = res['record_id']
        session.pop(f"self_res_{defect_id}_{request_stage_type}", None)
    if self_or_audit=="self": #自评
        if  res['code']==1:
            session[f"self_res_{defect_id}_{request_stage_type}"] = res
            print("session:")
            print(session[f"self_res_{defect_id}_{request_stage_type}"])
            flow_history = DefectFlowHistory(
                defect_id=defect_id,
                from_stage_id=defect.current_stage.id,
                to_stage_id=defect.current_stage.id,
                action_type=ActionType.VAL_SELF,
                action_by= g.user_id,
                action_time=datetime.now(),
                notes=f"提交{AiSugScore.pageShowConfig[0][f'step{current_step+1}']}进行AI自评",
                ai_sug_score_id=ai_sug_score_id
            )
            db.session.add(flow_history)
            defect_services.commit_changes()
            return{
                'message': '自评成功',
                'data':res['items'],
                'current_step':current_step
            },200
        else:
            if res['code']==-2:
                return {"error": f"自评失败，原因：{res['msg']}"}, 405
            else:
                return {"error": f"自评失败，原因：{res['msg']}"}, 401

    elif self_or_audit=="audit":
        print(res)
        print(f"current_step:{current_step}")
        print(f"defect_desc_stage_data_id:{defect_desc_stage_data_id}")
        print(f"defect_cause_analysis_stage_id:{defect_cause_analysis_stage_id}")
        print(f"defect_solution_stage_id:{defect_solution_stage_id}")
        print(f"defect_tester_regression_data_id:{defect_tester_regression_data_id}")
        try:
            if res['code'] == 1:
                if current_step==0:
                    DefectStageDataService.evaluate_stage_data(defect_desc_stage_data_id,
                                                               ai_suggestion=res['items'][0][0],
                                                               ai_score=int(res['items'][0][1]))
                    if request_stage_type == "stage_type":
                        stage = DefectStageService.create_next_stage(  # 创建测试经理审核描述阶段（支持从草稿提交或直接创建）
                            defect_id=defect.id,
                            stage_type_key="test_manager_review_desc",
                            assigned_to=test_manager_id,
                            previous_stage_id=defect.current_stage.id,
                            user_id=g.user_id,
                            ai_sug_score_id = ai_sug_score_id
                        )
                        # 更新缺陷状态
                        defect.status = 'DefectStatus.OPEN'
                        defect.updated_time = datetime.now()
                    # create_review_message
                    MessageCreator.create_review_message(
                        defect_id=defect_id,
                        reviewer_id=test_manager_id,
                        submitter_id=g.user_id,
                        review_type='defect_description'
                    )

                    email_content = email_content = DefectEmailService.get_review_email_content(
                        defect=defect,
                        review_type='defect_description',
                        submitter_id=g.user_id
                    )
                    email_subject = DefectEmailService.get_email_subject_by_message_type(
                        defect=defect,
                        message_type=MessageTypes.REVIEW_DEFECT_DESCRIPTION
                    )
                    send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=test_manager_id,
                                                                        admin_user_id=g.admin_user_id,
                                                                        current_user_id=g.user_id,
                                                                        content=email_content,
                                                                        title=email_subject
                                                                        )
                if current_step==1:
                    DefectStageDataService.combine_stage_data(defect_id, defect_cause_analysis_stage_id,
                                                              cause_analysis_data_ids, res['items'][1][0],
                                                              int(res['items'][1][1]))
                    if request_stage_type == "stage_type":
                        dev_lead_review_stage = DefectStageService.create_next_stage(
                            defect_id=defect_id,
                            stage_type_key="dev_lead_review_analysis",
                            assigned_to=dev_lead_id,
                            previous_stage_id=defect.current_stage.id,
                            user_id=g.user_id,
                            ai_sug_score_id=ai_sug_score_id
                        )
                        DefectLocaleInvitationService.update_invitation_status(
                            session['current_invitation'],
                            InvitationStatus.COMPLETED
                        )
                        session.pop('current_invitation', None)
                    MessageCreator.create_review_message(
                        defect_id=defect_id,
                        reviewer_id=dev_lead_id,
                        submitter_id=g.user_id,
                        review_type='reason_analysis',
                    )

                    email_content = email_content = DefectEmailService.get_review_email_content(
                        defect=defect,
                        review_type='reason_analysis',
                        submitter_id=g.user_id
                    )
                    email_subject = DefectEmailService.get_email_subject_by_message_type(
                        defect=defect,
                        message_type=MessageTypes.REVIEW_REASON_ANALYSIS
                    )
                    send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=dev_lead_id,
                                                                        admin_user_id=g.admin_user_id,
                                                                        current_user_id=g.user_id,
                                                                        content=email_content,
                                                                        title=email_subject
                                                                        )
                if current_step == 2:
                    DefectStageDataService.combine_stage_data(defect_id, defect_solution_stage_id,
                                                              solution_data_ids, res['items'][2][0],
                                                              int(res['items'][2][1]))
                    if request_stage_type == "stage_type":
                        dev_lead_review_solution_stage = DefectStageService.create_next_stage(
                            defect_id=defect_id,
                            stage_type_key="dev_lead_review_solution",
                            assigned_to=dev_lead_id,
                            previous_stage_id=defect.current_stage.id,
                            user_id=g.user_id,
                            ai_sug_score_id=ai_sug_score_id
                        )
                        updated_division = DefectSolutionDivisionService.update_division_status(
                            session['current_division_id'],
                            InvitationStatus.COMPLETED,
                            '已提交解决措施'
                        )
                        session.pop('current_division_id', None)
                    MessageCreator.create_review_message(
                        defect_id=defect_id,
                        reviewer_id=dev_lead_id,
                        submitter_id=g.user_id,
                        review_type='solution_measures'
                    )
                    email_content = email_content = DefectEmailService.get_review_email_content(
                        defect=defect,
                        review_type='solution_measures',
                        submitter_id=g.user_id
                    )
                    email_subject = DefectEmailService.get_email_subject_by_message_type(
                        defect=defect,
                        message_type=MessageTypes.REVIEW_SOLUTION_MEASURES
                    )
                    send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=dev_lead_id,
                                                                        admin_user_id=g.admin_user_id,
                                                                        current_user_id=g.user_id,
                                                                        content=email_content,
                                                                        title=email_subject
                                                                        )
                if current_step==3:
                    DefectStageDataService.evaluate_stage_data(defect_tester_regression_data_id,ai_suggestion=res['items'][3][0],ai_score=int(res['items'][3][1]))
                    if request_stage_type == "stage_type":
                        test_manager_review_stage = DefectStageService.create_next_stage(
                            defect_id=defect_id,
                            stage_type_key="test_manager_review_regression",
                            assigned_to=test_manager_id,
                            previous_stage_id=defect.current_stage.id,
                            user_id=g.user_id,
                            ai_sug_score_id=ai_sug_score_id
                        )
                    MessageCreator.create_review_message(
                        defect_id=defect_id,
                        reviewer_id=test_manager_id,
                        submitter_id=g.user_id,
                        review_type='regression_test'
                    )
                    email_content = email_content = DefectEmailService.get_review_email_content(
                        defect=defect,
                        review_type='regression_test',
                        submitter_id=g.user_id
                    )
                    email_subject = DefectEmailService.get_email_subject_by_message_type(
                        defect=defect,
                        message_type=MessageTypes.REVIEW_REGRESSION_TEST
                    )
                    send_result_dict = InnerSrvice.send_mail_for_defect(send_to_user_id=test_manager_id,
                                                                        admin_user_id=g.admin_user_id,
                                                                        current_user_id=g.user_id,
                                                                        content=email_content,
                                                                        title=email_subject
                                                                        )
                defect_services.commit_changes()
                return{
                    'message': '评估完成',
                    'data':[],
                },200
            else:
                DefectStage.query.filter(DefectStage.id == defect.current_stage.id).update({"status":"StageStatus.IN_PROGRESS"})
                defect_services.commit_changes()
                session.pop('current_division_id', None)
                session.pop('current_invitation', None)
                return {"error": f"评估失败，原因：{res['msg']}"}, 401
        except Exception as e:
            print(e)
            DefectStage.query.filter(DefectStage.id == defect.current_stage.id).update({"status": "StageStatus.IN_PROGRESS"})
            defect_services.commit_changes()
            session.pop('current_division_id', None)
            session.pop('current_invitation', None)
            return {"error": f"评估失败"}, 400
    return None


@defect_bp.route('/ai_done2/<self_or_audit>/<int:defect_id>', methods=['POST','GET'])
def defect_ai_done2(self_or_audit,defect_id):
    '''
    简化版2
    '''
    defect = Defect.query.join(Defect.current_stage).join(DefectStage.assignee).filter(
            Defect.id==defect_id,
    ).first()
    if defect is None:
        return {"error":"缺陷记录不存在"},400
    payload = {
        "service_type":0,
        "async": False,
        "items":[],
    }
    defect_desc_stage_data_id = 0
    description_data = DefectStageDataService.get_defect_description_data(defect_id)
    current_app.logger.debug(f"cause_analysis_data: {description_data}")
    project_version_name, _ = defect_services.get_project_version(defect)
    last_val_data = {"defect_description":[None,None],"cause_analysis":[None,None],"developer_solution":[None,None],"tester_regression":[None,None]}
    descriptions = f"""
        缺陷所属产品线/技术族:{project_version_name}<br>
        缺陷影响程度:{defect.severity}<br>
        缺陷是否可重现:{defect.defect_reproducibility}<br>
        缺陷标题:{defect.title}<br>
    """

    for data in description_data:
        defect_desc_stage_data_id = data['id']
        descriptions = descriptions+data['content']['description']
        last_val_data['defect_description'] = [data['ai_score'],data['ai_suggestion']]
    payload["items"] = [descriptions, "", "", ""]
    cause_analysis_data_id = 0
    cause_analysis_data = DefectStageDataService.get_stage_data_by_type(defect_id, DataType.CAUSE_ANALYSIS)
    analysis = ""
    if cause_analysis_data:
        current_app.logger.debug(f"cause_analysis_data: {cause_analysis_data}")
        if cause_analysis_data[0].get('content').get('analyses'):
            analysis = cause_analysis_data[0].get('content').get('analyses')[0]
            last_val_data['cause_analysis'] = [cause_analysis_data[0].get('ai_score'),cause_analysis_data[0].get('ai_suggestion')]
        cause_analysis_data_id = cause_analysis_data[0].get('id')
        if analysis!="":
            payload["items"][1] = analysis
    solution_data_id = 0
    solution_contents = ""
    solution_data = DefectStageDataService.get_stage_data_by_type(defect_id, DataType.SOLUTION)
    current_app.logger.debug(f"solution_data: {solution_data}")
    if solution_data:
        if solution_data[0]['content']['solutions']:
            solution_contents = solution_data[0]['content']['solutions'][0]
            last_val_data['developer_solution'] = [solution_data[0]['ai_score'],solution_data[0]['ai_suggestion']]
        solution_data_id = solution_data[0]['id']
        if solution_contents!="":
            payload["items"][2] = solution_contents
    test_result_data = DefectStageDataService.get_test_result_data(defect_id)
    test_results = ""
    test_result_data_id = 0
    current_app.logger.debug(f"solution_data: {test_result_data}")
    for data in test_result_data:
        test_results = data['content']['description']
        last_val_data['tester_regression'] = [data['ai_score'],data['ai_suggestion']]
        if test_result_data_id==0:
            test_result_data_id = data['id']
    if test_results!="":
        payload["items"][3] = test_results
    is_change_audit = request.values.get('is_change_audit','')
    ai_sug_score_id = None
    changed_items_str = request.values.get('changed_items', '')
    changed_items = []
    if changed_items_str != '':
        changed_items = changed_items_str.split(",")
    all_changed_items = []
    if f"self_res_{defect_id}" in session:
        if 'all_changed_items' in session[f"self_res_{defect_id}"]:
            all_changed_items = session[f"self_res_{defect_id}"]['all_changed_items']
    all_changed_items = list(set(all_changed_items + changed_items))
    step_content = "对" + '、'.join(all_changed_items)
    self_show = [1, 1, 1, 1]
    if is_change_audit != "" and self_or_audit=="audit" or self_or_audit=="self" or f"self_res_{defect_id}" not in session:
        try:
            payload['email_user_id'] = g.user_id
            payload['defect_id'] = defect_id
            res = json.loads(Ai.my_val_api_done(payload,g.admin_user_id))
            ai_sug_score_id = res['record_id']
            ai_sug_score_record = AiSugScore.query.filter(AiSugScore.id==ai_sug_score_id).first()
            if "缺陷基本信息" not in all_changed_items and "缺陷描述" not in all_changed_items :
                ai_sug_score_record.ai_step1 = last_val_data['defect_description'][1]
                ai_sug_score_record.step1_score = last_val_data['defect_description'][0]
                res['items'][0] = [last_val_data['defect_description'][1],last_val_data['defect_description'][0]]
                self_show[0] = 0
            if "原因分析" not in all_changed_items :
                ai_sug_score_record.ai_step2 = last_val_data['cause_analysis'][1]
                ai_sug_score_record.step2_score = last_val_data['cause_analysis'][0]
                res['items'][1] = [last_val_data['cause_analysis'][1],last_val_data['cause_analysis'][0]]
                self_show[1] = 0
            if "解决措施" not in all_changed_items:
                ai_sug_score_record.ai_step3 = last_val_data['developer_solution'][1]
                ai_sug_score_record.step3_score = last_val_data['developer_solution'][0]
                res['items'][2] = [last_val_data['developer_solution'][1],last_val_data['developer_solution'][0]]
                self_show[2] = 0
            if "回归测试" not in all_changed_items:
                ai_sug_score_record.ai_step4 = last_val_data['tester_regression'][1]
                ai_sug_score_record.step4_score = last_val_data['tester_regression'][0]
                res['items'][3] = [last_val_data['tester_regression'][1],last_val_data['tester_regression'][0]]
                self_show[3] = 0
        except Exception as e:
            res = {
                "code":-1,
                "items":[],
                "msg":"评估网络超时"
            }
    elif is_change_audit =="" and self_or_audit =="audit":
        res = session[f"self_res_{defect_id}"]
        ai_sug_score_id = res['record_id']
    if self_or_audit=="self": #自评
        if  res['code']==1:
            res['all_changed_items'] = all_changed_items
            session[f"self_res_{defect_id}"] = res
            flow_history = DefectFlowHistory(
                defect_id=defect_id,
                from_stage_id=defect.current_stage.id,
                to_stage_id=defect.current_stage.id,
                action_type=ActionType.VAL_SELF,
                action_by= g.user_id,
                action_time=datetime.now(),
                notes=step_content+"进行AI自评",
                ai_sug_score_id=ai_sug_score_id
            )
            db.session.add(flow_history)
            defect_services.commit_changes()
            return{
                'message': '自评成功',
                'data':res['items'],
                'current_step':3,
                'self_show':self_show
            },200
        else:
            if res['code']==-2:
                return {"error": f"自评失败，原因：{res['msg']}"}, 405
            else:
                return {"error": f"自评失败，原因：{res['msg']}"}, 401
    elif self_or_audit=="audit":
        print(res)
        print(f"defect_desc_stage_data_id:{defect_desc_stage_data_id}")
        print(f"cause_analysis_data_id:{cause_analysis_data_id}")
        print(f"solution_data_id:{solution_data_id}")
        print(f"test_result_data_id:{test_result_data_id}")
        print(f"all_changed_items:{all_changed_items}")
        try:
            if res['code'] == 1:
                val_step = 0
                defect_description_stage = DefectStageService.get_stage_by_defect_and_type(defect_id,'defect_description')
                cause_analysis_stage = DefectStageService.get_stage_by_defect_and_type(defect_id, 'cause_analysis')
                developer_solution_stage = DefectStageService.get_stage_by_defect_and_type(defect_id,'developer_solution')
                tester_regression_stage = DefectStageService.get_stage_by_defect_and_type(defect_id,'tester_regression')
                if "缺陷基本信息" in all_changed_items or "缺陷描述" in all_changed_items:
                    DefectStageDataService.evaluate_stage_data(defect_desc_stage_data_id, ai_suggestion=res['items'][0][0],ai_score=int(res['items'][0][1]))
                    email_content = DefectEmailService.get_general_defect_email_content(defect, "缺陷描述已提交","原因分析")
                    DESCRIPTION_CHANGED = f"【缺陷描述已提交，请处理原因分析】{defect.defect_number} - {defect.title}"
                    email_subject = DESCRIPTION_CHANGED
                    send_result_dict = InnerSrvice.send_mail_for_defect(
                        send_to_user_id=cause_analysis_stage.assigned_to,
                        admin_user_id=g.admin_user_id,
                        current_user_id=g.user_id,
                        content=email_content,
                        title=email_subject)
                    DefectMessageService.save_message(
                        send_to_user_id=cause_analysis_stage.assigned_to,
                        send_from_user_id=g.user_id,
                        defect_id=defect_id,
                        message_type=MessageTypes.DESCRIPTION_CHANGED,
                    )
                    defect_description_stage = DefectStageService.get_stage_by_defect_and_type(defect_id,'defect_description')
                    defect_description_stage.completed_time = datetime.now()
                    defect_description_stage.status = StageStatus.COMPLETED
                if "原因分析" in all_changed_items:
                    val_step = 1
                    DefectStageDataService.evaluate_stage_data(cause_analysis_data_id, ai_suggestion=res['items'][1][0],ai_score=int(res['items'][1][1]))
                    developer_solution_stage = DefectStageService.get_stage_by_defect_and_type(defect_id,'developer_solution')
                    email_content = DefectEmailService.get_general_defect_email_content(defect, "原因分析已提交","解决措施")
                    # 简化版
                    ANALYSIS_CHANGED = f"【原因分析已提交，请处理解决措施】{defect.defect_number} - {defect.title}"
                    email_subject = ANALYSIS_CHANGED
                    send_result_dict = InnerSrvice.send_mail_for_defect(
                        send_to_user_id=developer_solution_stage.assigned_to,
                        admin_user_id=g.admin_user_id,
                        current_user_id=g.user_id,
                        content=email_content,
                        title=email_subject)
                    # 发送消息
                    DefectMessageService.save_message(
                        send_to_user_id=developer_solution_stage.assigned_to,
                        send_from_user_id=g.user_id,
                        defect_id=defect_id,
                        message_type=MessageTypes.ANALYSIS_CHANGED,
                    )
                    cause_analysis_stage.completed_time = datetime.now()
                    cause_analysis_stage.status = StageStatus.COMPLETED
                if "解决措施" in all_changed_items:
                    val_step = 2
                    DefectStageDataService.evaluate_stage_data(solution_data_id, ai_suggestion=res['items'][2][0],ai_score=int(res['items'][2][1]))
                    tester_regression_stage = DefectStageService.get_stage_by_defect_and_type(defect_id,'tester_regression')
                    email_content = DefectEmailService.get_general_defect_email_content(defect, "解决措施已提交","回归测试")
                    # 简化版
                    SOLUTION_CHANGED = f"【解决措施已提交，请处理回归测试】{defect.defect_number} - {defect.title}"
                    email_subject = SOLUTION_CHANGED
                    send_result_dict = InnerSrvice.send_mail_for_defect(
                        send_to_user_id=tester_regression_stage.assigned_to,
                        admin_user_id=g.admin_user_id,
                        current_user_id=g.user_id,
                        content=email_content,
                        title=email_subject)
                    # 发送消息
                    DefectMessageService.save_message(
                        send_to_user_id=tester_regression_stage.assigned_to,
                        send_from_user_id=g.user_id,
                        defect_id=defect_id,
                        message_type=MessageTypes.SOLUTION_CHANGED,
                    )
                    developer_solution_stage.completed_time = datetime.now()
                    developer_solution_stage.status = StageStatus.COMPLETED
                if "回归测试" in all_changed_items:
                    val_step = 3
                    DefectStageDataService.evaluate_stage_data(test_result_data_id,ai_suggestion=res['items'][3][0],ai_score=int(res['items'][3][1]))
                    requester_confirm_stage = DefectStageService.get_stage_by_defect_and_type(defect_id,'requester_confirm')
                    email_content = DefectEmailService.get_general_defect_email_content(defect, "回归测试已提交","确认关闭")
                    REGRESSION_CHANGED = f"【回归测试已提交，请确认关闭】{defect.defect_number} - {defect.title}"
                    email_subject = REGRESSION_CHANGED
                    send_result_dict = InnerSrvice.send_mail_for_defect(
                        send_to_user_id=requester_confirm_stage.assigned_to,
                        admin_user_id=g.admin_user_id,
                        current_user_id=g.user_id,
                        content=email_content,
                        title=email_subject)
                    DefectMessageService.save_message(
                        send_to_user_id=requester_confirm_stage.assigned_to,
                        send_from_user_id=g.user_id,
                        defect_id=defect_id,
                        message_type=MessageTypes.REGRESSION_CHANGED,
                    )
                    tester_regression_stage.completed_time = datetime.now()
                    tester_regression_stage.status = StageStatus.COMPLETED
                flow_history = DefectFlowHistory(
                    defect_id=defect_id,
                    from_stage_id=defect.current_stage.id,
                    to_stage_id=defect.current_stage.id,
                    action_type=ActionType.VAL_SUBMIT,
                    action_by=g.user_id,
                    action_time=datetime.now(),
                    notes=step_content+"进行AI评估",
                    ai_sug_score_id=ai_sug_score_id
                )


                db.session.add(flow_history)
                stages_types_step = {'defect_description': 0, 'cause_analysis': 1, 'developer_solution': 2,'tester_regression': 3, 'requester_confirm': 4}
                step_stages_types = {0:'defect_description', 1:'cause_analysis', 2:'developer_solution' ,3:'tester_regression', 4:'requester_confirm'}
                current_step = stages_types_step[defect.current_stage.stage_type]
                if current_step!=4 and val_step>=current_step:
                    next_step = val_step + 1
                    next_step_stages_type = step_stages_types[next_step]
                    next_stage = DefectStage.query.filter(DefectStage.stage_type==next_step_stages_type,DefectStage.defect_id==defect_id).first()
                    defect.current_stage_id = next_stage.id
                defect_services.commit_changes()
                session.pop(f"self_res_{defect_id}", None)
                return {
                    'message': '评估完成',
                    'data': [],
                }, 200
            else:
                session.pop(f"self_res_{defect_id}", None)
                return {"error": f"评估失败，原因：{res['msg']}"}, 401
        except Exception as e:
            session.pop(f"self_res_{defect_id}", None)
            print(e)
            return {"error": f"评估失败"}, 400


@defect_bp.route('/role_proxy', methods=['POST','GET'])
def role_proxy():
    role_select = request.values.get('role_select',"")
    defect_type = request.values.get('defect_type',"")
    if session['admin_user_id']==0 or session['user_id']==session['admin_user_id']:
        role_select = "公司管理员"
    if role_select=="":
        show_user_roles = ProjectMemberService.get_show_user_roles(session['user_id'])
        if show_user_roles:
            role_select = show_user_roles[0]
        else:
            role_select = "流程使用者"
    session['role_select'] = role_select
    if role_select=="公司管理员":
        return redirect("/global_settings/global_admin/list?defect_type="+defect_type)
    elif role_select == "全板块管理员":
        return redirect("/product_line/versions?defect_type="+defect_type)
    elif role_select == "全板块查阅人":
        return redirect("/defect/statistics?defect_type="+defect_type)
    elif role_select == "项目管理员":
        return redirect("/project_member/project-members?defect_type="+defect_type)
    elif role_select == "项目查阅人":
        return redirect("/defect/statistics?defect_type="+defect_type)
    elif  role_select=="流程使用者":
        return redirect("/defect/?defect_type="+defect_type)
    else:
        return redirect("/defect/?defect_type="+defect_type)

