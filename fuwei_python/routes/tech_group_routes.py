from flask import Blueprint, request, jsonify, render_template, redirect, url_for,g

from services.inner_service import InnerSrvice
from services.role_services import UserRoleService
from services.tech_group_service import TechGroupService
from datetime import datetime
from models.users.models import User
import json
# 创建统一的 tech_group 蓝图
tech_group_bp = Blueprint('tech_group', __name__)


# 技术族管理
@tech_group_bp.route('/groups', methods=['GET'])
def get_tech_groups():
    """获取产品线列表"""
    filters = {}
    if request.args.get('name'):
        filters['name'] = request.args.get('name')

    result, status_code = TechGroupService.get_tech_groups(filters)
    if status_code != 200:
        return jsonify(result), status_code
    return render_template('product_line/product_lines.html', product_lines=result['data'])


@tech_group_bp.route('/groups', methods=['POST'])
def create_tech_group():
    """创建产品线"""
    data = request.form.to_dict()
    data['admin_user_id'] = g.admin_user_id
    result, status_code = TechGroupService.create_tech_group(data)
    return jsonify(result), status_code

@tech_group_bp.route('/edit_tech_group', methods=['POST'])
def edit_tech_group():
    """
    :return:
    """
    data = request.json
    data['admin_user_id'] = g.admin_user_id
    if data['id']=="":
        return TechGroupService.create_tech_group(data)
    else:
        return TechGroupService.update_tech_group(data)



@tech_group_bp.route('/groups/<int:group_id>', methods=['DELETE'])
def delete_tech_group(group_id):
    """删除产品线"""
    result, status_code = TechGroupService.delete_tech_group(g.admin_user_id,group_id)
    return jsonify(result), status_code


# 平台管理
@tech_group_bp.route('/platforms', methods=['GET'])
def get_platforms():
    """获取平台列表"""
    filters = {}
    if request.args.get('tech_group_name'):
        filters['tech_group_name'] = request.args.get('tech_group_name')
    if request.args.get('product_name'):
        filters['product_name'] = request.args.get('product_name')

    result, status_code = TechGroupService.get_platforms(filters)
    if status_code != 200:
        return jsonify(result), status_code

    # 获取所有产品线用于下拉选择和名称映射
    tech_groups_result, _ = TechGroupService.get_tech_groups()
    tech_groups = tech_groups_result['data'] if 'data' in tech_groups_result else []

    # 创建产品线ID到名称的映射
    tech_group_map = {group['id']: group['name'] for group in tech_groups}

    # 为每个产品添加产品线名称
    for platform in result['data']:
        tech_group_id = platform.get('tech_group_id')
        if tech_group_id and tech_group_id in tech_group_map:
            platform['tech_group_name'] = tech_group_map[tech_group_id]
        else:
            platform['tech_group_name'] = '未知产品线'

    return render_template('tech_group/platforms.html',
                           platforms=result['data'],
                           tech_groups=tech_groups)



@tech_group_bp.route('/edit_platforms', methods=['POST'])
def edit_platform():
    """
    :return:
    """
    data = request.json
    data['admin_user_id'] = g.admin_user_id
    if data['id']=="":
        return TechGroupService.create_platform(data)
    else:
        return TechGroupService.update_platform(data)

@tech_group_bp.route('/platforms/<int:platform_id>', methods=['DELETE'])
def delete_platform(platform_id):
    """删除产品"""
    result, status_code = TechGroupService.delete_platform(platform_id,g.admin_user_id)
    return jsonify(result), status_code


@tech_group_bp.route('/projects', methods=['GET'])
@UserRoleService.check_global_roles(
    allowed_roles=['global_admin', 'global_viewer','company_admin'],
    template='defect/defect_levels.html',
    json_response=True
)
def get_projects():
    """获取版本列表"""
    filters = {}
    if request.args.get('tech_group_name'):
        filters['tech_group_name'] = request.args.get('tech_group_name')
    if request.args.get('platform_name'):
        filters['platform_name'] = request.args.get('platform_name')
    if request.args.get('project_name'):
        filters['project_name'] = request.args.get('project_name')
    filters['admin_user_id'] = g.admin_user_id
    result, status_code = TechGroupService.get_projects(filters)
    if status_code != 200:
        return jsonify(result), status_code
    user_list = User.get_like_defect_user_list(g.admin_user_id)
    return render_template('product_line/version.html',
                           projects=result['data'],
                           pagination=result['pagination'],
                           user_list=json.dumps( [{'real_name': user.real_name,'email' :user.email,'user_id':user.user_id,'dept':user.dept}   for user in user_list]),
                           actions = 'project',
                           keys = {"level2": "platforms", "actions": "project"}
                        )


@tech_group_bp.route('/projects', methods=['POST'])
def edit_project():
    """创建版本"""
    data = request.form.to_dict()
    data['admin_user_id'] = g.admin_user_id
    user_datas = [{'email':data['email'],'real_name':data['real_name']}]
    res,code = InnerSrvice.check_and_add_defect_users(user_datas)
    if code<0:
        return {'error': res['msg']}, 400
    else:
        data['user_id'] = res['user_ids'][0]
    if data['record_id'] == "":
        result, status_code = TechGroupService.create_project(data)
    else:
        result, status_code = TechGroupService.update_project(data['record_id'],data)
    return jsonify(result), status_code



@tech_group_bp.route('/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    """删除版本"""
    result, status_code = TechGroupService.delete_project(project_id,g.admin_user_id)
    return jsonify(result), status_code
@tech_group_bp.route('/delete_projects', methods=['POST'])
def delete_projects():
    """删除版本"""
    data = request.json
    return TechGroupService.delete_project_ids(data,g.admin_user_id)


# 主页面 - 显示所有层级
@tech_group_bp.route('/hierarchy', methods=['GET'])
def get_hierarchy():
    admin_user_id = g.admin_user_id
    hierarchy = TechGroupService.get_hierarchy(admin_user_id)
    return jsonify(hierarchy),200

