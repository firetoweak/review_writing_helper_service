import json

from flask import Blueprint, request, render_template, jsonify, flash, redirect, url_for, g, current_app

from services.role_services import UserRoleService
from services.template_services import TemplateTypeService, TemplateService, TemplateItemService

template_bp = Blueprint('template', __name__)


@template_bp.route('/<template_type_name>', methods=['GET'])
@UserRoleService.check_global_roles(
    allowed_roles=['all'],
    template='defect_template/template_management.html',
    json_response=True)
def get_template(template_type_name):
    """获取指定用户id的指定模板名称的模板项信息"""
    try:
        # 获取当前用户ID（假设已通过认证中间件设置）
        user_id = g.user_id
        if not user_id:
            return jsonify({'error': '用户未认证'}), 401

        # 验证模板类型名称
        valid_template_types = ['缺陷描述', '原因分析', '解决措施', '回归测试']
        if template_type_name not in valid_template_types:
            return jsonify({'error': f'无效的模板类型，支持的模板类型有：{", ".join(valid_template_types)}'}), 400

        # 获取或创建模板
        templates = TemplateService.get_by_type_name(
            type_name=template_type_name,
            include_items=True,
            user_id=g.admin_user_id
        )

        # 如果没有找到模板，则创建默认模板
        if not templates:
            if template_type_name == '缺陷描述':
                template = TemplateService.create_defect_description_template(g.admin_user_id)  # 创建人为 admin_user_id
            elif template_type_name == '回归测试':
                template = TemplateService.create_regression_test_template(g.admin_user_id)  # 创建人为 admin_user_id
            elif template_type_name == '原因分析':
                template = TemplateService.create_cause_analysis_template(g.admin_user_id)  # 创建人为 admin_user_id
            elif template_type_name == '解决措施':
                template = TemplateService.create_solution_measures_template(g.admin_user_id)  # 创建人为 admin_user_id
            else:
                return jsonify({'error': '不支持的模板类型'}), 400

            if not template:
                return jsonify({'error': '创建模板失败'}), 500

            templates = [template]

        # 转换为字典格式返回
        template_data = templates[0].to_dict(include_items=True)
        return jsonify(template_data)

    except Exception as e:
        current_app.logger.error(f"获取模板失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


@template_bp.route('/<template_type_name>', methods=['POST'])
@UserRoleService.check_global_roles(
    allowed_roles=['global_admin'],  # 只允许 global_admin 角色
    template='defect_template/template_management.html',
    json_response=True)
def update_template(template_type_name):
    """更新指定用户id的指定模板名称的模板项信息"""
    try:
        # 获取当前用户ID
        user_id = g.user_id
        if not user_id:
            return jsonify({'error': '用户未认证'}), 401

        current_app.logger.info(f'更新模板: template_type_name:{template_type_name}, user_id:{user_id}')

        # 验证模板类型名称
        valid_template_types = ['缺陷描述', '回归测试', '原因分析', '解决措施']
        if template_type_name not in valid_template_types:
            return jsonify({'error': f'无效的模板类型，支持的模板类型有：{", ".join(valid_template_types)}'}), 400

        # 获取请求数据
        data = request.get_json()
        if not data or 'items' not in data:
            return jsonify({'error': '无效的请求数据'}), 400

        # 获取用户对应的模板
        templates = TemplateService.get_by_type_name(
            type_name=template_type_name,
            include_items=True,
            user_id=g.admin_user_id
        )

        if not templates:
            # 如果没有模板，根据类型创建默认模板
            if template_type_name == '缺陷描述':
                template = TemplateService.create_defect_description_template(g.admin_user_id)
            elif template_type_name == '回归测试':
                template = TemplateService.create_regression_test_template(g.admin_user_id)
            elif template_type_name == '原因分析':
                template = TemplateService.create_cause_analysis_template(g.admin_user_id)
            elif template_type_name == '解决措施':
                template = TemplateService.create_solution_measures_template(g.admin_user_id)
            else:
                return jsonify({'error': '不支持的模板类型'}), 400

            if not template:
                return jsonify({'error': '创建模板失败'}), 500
        else:
            template = templates[0]

        # 删除所有现有模板项
        deleted_count = TemplateItemService.delete_template_items_by_template(template.id)
        current_app.logger.info(f'删除模板项数量: {deleted_count}')

        # 创建新的模板项
        for index, item_data in enumerate(data['items']):
            TemplateItemService.create_template_item(
                template_id=template.id,
                # json.dumps 将Python字典对象序列化为JSON格式字符串
                content=json.loads(item_data.get('content', {})),  # json.loads 将JSON格式字符串反序列化为Python对象
                sort_order=item_data.get('sort_order', index),
                is_removable=item_data.get('is_removable', True),
                is_required=item_data.get('is_required', False)
            )

        # 返回更新后的模板
        updated_template = TemplateService.get_by_id(template.id, include_items=True)
        return jsonify(updated_template.to_dict(include_items=True))

    except Exception as e:
        current_app.logger.error(f"更新模板失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


@template_bp.route('/manage', methods=['GET'])
@UserRoleService.check_global_roles(allowed_roles=['global_admin', 'global_viewer'],
                                    template='defect_template/template_management.html')
def manage_templates():
    """模板管理页面"""
    return render_template('defect_template/template_management.html',
                           is_global_admin=g.is_global_admin,
                           is_global_viewer=g.is_global_viewer)
