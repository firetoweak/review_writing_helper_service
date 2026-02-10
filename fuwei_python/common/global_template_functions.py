import json
import time

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, g, render_template, current_app
from sqlalchemy import or_

from models.defect.model import Defect, DefectStage
from models.project_member.model import ProjectMember
from models.users.models import MobileUserRight
from services.product_line_services import ProductLineService
from services.project_member_services import ProjectMemberService, ProjectMemberAuthService
from services.role_services import UserRoleService
from services.tech_group_service import TechGroupService

def get_menu_role():
    user_id = session.get('user_id')
    index = 0
    if session['admin_user_id']==0 or session['user_id']==session['admin_user_id']:
        return json.dumps([['公司管理员',True]])
    else:
        show_user_roles = ProjectMemberService.get_show_user_roles(user_id)
    show_menu_user_role_urls = []
    if 'role_select' not in session:
        session['role_select'] = "流程使用者"
    for role in show_user_roles:
        # if role == "项目查阅人" and index<=2:
        #     continue
        choose = False
        if session['role_select']==role:
            choose = True
        show_menu_user_role_urls.append([role,choose])
    print(f"show_menu_user_role_urls:{show_menu_user_role_urls}")
    return json.dumps(show_menu_user_role_urls)

def get_role_select_session():
    if "role_select" not in session:
        session['role_select'] = "流程使用者"
    return  session['role_select']

def get_url_path():
    return request.path

def get_right_style(record_type,page_type="common"):
    if page_type=="defect":
        if 'role_select' not in session:
            return ''
        if session['role_select'] != "公司管理员" and session['role_select'] != "全板块管理员":
            return ''
    admin_user_id = session['admin_user_id']
    rights = MobileUserRight.get_one_right(admin_user_id, record_type)
    date_end = 0
    request_font_red = 0
    invite_font_red = 0
    if rights is not  None:
        if rights.to_date is not None:
            date_to_check = time.mktime(time.strptime(str(rights.to_date), "%Y-%m-%d %H:%M:%S"))
            current_time_timestamp = time.time()
            if date_to_check > current_time_timestamp:
                date_end = 0
            else:
                date_end = 1
        if rights.request_num <= rights.requested_num:
            request_font_red = 1
        if rights.user_total_num <= rights.invited_user_num:
            invite_font_red = 1
    return render_template("components/right_setting.html",date_end=date_end,request_font_red=request_font_red,invite_font_red=invite_font_red,Rights=rights)
def get_all_version_project():
    checked_ids_str = request.args.get('version_projects', 'all')
    checked_ids = []
    if checked_ids_str!='all' and checked_ids_str!="":
        checked_ids = checked_ids_str.split(',')
    elif checked_ids_str =="all":
        checked_ids = ['all']
    else:
        checked_ids = []
    admin_user_id = session['admin_user_id']
    product_line_data = ProductLineService.get_hierarchy(admin_user_id)
    tech_groups_data = TechGroupService.get_hierarchy(admin_user_id)
    product_line_json =  {
        "title": '产品线',
        "id": 0,
        "children": []
    }
    tech_groups_json = {
        "title": '技术族',
        "id": 1,
        "children": []
    }
    user_projects_versions = None
    if request.path=="/defect/statistics" and session['role_select'] =='项目查阅人' or request.path=="/defect/" and session['role_select'] =='项目查阅人':
        user_projects_versions = ProjectMemberService.get_user_menu_project_versions(session['user_id'])
    for data in product_line_data:
        product_lines = {'id': f"v1-{data['id']}", 'title': data['name'], 'children':[]}
        for product in data['products']:
            products = {'id': f"v2-{product['id']}", 'title': product['name'], 'children':[]}
            for version in product['versions']:
                if user_projects_versions is None:
                    versions = {'id': f"v3-{version['id']}", 'title': version['version_number'],'checked': f"v3-{version['id']}" in checked_ids or 'all' in checked_ids}
                    products['children'].append(versions)
                else:
                    if version['id'] in  user_projects_versions['version_ids']:
                        versions = {'id': f"v3-{version['id']}", 'title': version['version_number'],'checked': f"v3-{version['id']}" in checked_ids or 'all' in checked_ids}
                        products['children'].append(versions)
            if products['children']:
                product_lines['children'].append(products)
        if product_lines['children']:
            product_line_json['children'].append(product_lines)
    for data in tech_groups_data:
        tech_groups = {'id':f"p1-{data['id']}", 'title': data['name'], 'children':[]}
        for platform in data['platforms']:
            platforms = {'id': f"p2-{platform['id']}", 'title': platform['name'], 'children':[]}
            for project in platform['projects']:
                if user_projects_versions is None:
                    projects = {'id': f"p3-{project['id']}", 'title': project['name'] , 'checked': f"p3-{project['id']}" in checked_ids or 'all' in checked_ids}
                    platforms['children'].append(projects)
                else:
                    if project['id'] in user_projects_versions['project_ids']:
                        projects = {'id': f"p3-{project['id']}", 'title': project['name'],'checked': f"p3-{project['id']}" in checked_ids or 'all' in checked_ids}
                        platforms['children'].append(projects)
            if platforms['children']:
                tech_groups['children'].append(platforms)
        if tech_groups['children']:
            tech_groups_json['children'].append(tech_groups)
    timestamp = int(time.time() * 1000)
    product_line_json["_timestamp"] = timestamp # 增加时间戳，解决浏览器未获取最新数据问题
    tree_out_put = []
    if product_line_json['children']:
        tree_out_put.append(product_line_json)
    if tech_groups_json['children']:
        tree_out_put.append(tech_groups_json)
    return json.dumps(tree_out_put)


def get_all_checked_version_project():
    """
    获取所有版本和项目的ID列表（模拟 checked_ids_str == "all" 的情况）
    返回格式：['v3-1', 'v3-2', 'p3-1', 'p3-2', ...]
    包含用户权限过滤逻辑
    """
    checked_ids = []

    # 获取当前用户ID
    admin_user_id = session.get('admin_user_id')
    if not admin_user_id:
        admin_user_id = session.get('user_id')

    # 获取产品线和技术族数据
    product_line_data = ProductLineService.get_hierarchy(admin_user_id)
    tech_groups_data = TechGroupService.get_hierarchy(admin_user_id)

    # 检查用户角色和权限
    user_projects_versions = None
    request_path = request.path if hasattr(request, 'path') else ''
    role_select = session.get('role_select', '')
    user_id = session.get('user_id')
    user_projects_versions = ProjectMemberService.get_related_entities_by_user_id(user_id)
    # if session['role_select'] == "全板块查阅人" or session['role_select'] == "全板块管理员" or session[
    #     'role_select'] == '流程使用者':
    #     user_projects_versions = ProjectMemberService.get_related_entities_by_user_id(user_id)
    # # 角色权限过滤逻辑 - 与原 get_all_version_project 方法保持一致
    # else:
    #     user_projects_versions = ProjectMemberService.get_user_menu_project_versions(user_id)

    # 处理产品线数据
    for data in product_line_data:
        for product in data.get('products', []):
            for version in product.get('versions', []):
                # 权限过滤：如果 user_projects_versions 不为 None，只添加用户有权限的版本
                if user_projects_versions is None:
                    checked_ids.append(f"v3-{version['id']}")
                else:
                    if version['id'] in user_projects_versions.get('version_ids', []):
                        checked_ids.append(f"v3-{version['id']}")

    # 处理技术族数据
    for data in tech_groups_data:
        for platform in data.get('platforms', []):
            for project in platform.get('projects', []):
                # 权限过滤：如果 user_projects_versions 不为 None，只添加用户有权限的项目
                if user_projects_versions is None:
                    checked_ids.append(f"p3-{project['id']}")
                else:
                    if project['id'] in user_projects_versions.get('project_ids', []):
                        checked_ids.append(f"p3-{project['id']}")

    return checked_ids

def get_defects_num():
    query = Defect.query.join(Defect.current_stage).join(DefectStage.assignee)
    all_projects_versions = ProjectMemberService.get_related_entities_by_user_id(session['user_id'])
    conditions = []
    if all_projects_versions['project_ids']:
        conditions.append(Defect.project_id.in_(all_projects_versions['project_ids']))
    if all_projects_versions['version_ids']:
        conditions.append(Defect.version_id.in_(all_projects_versions['version_ids']))
    if conditions:
        query = query.filter(or_(*conditions))
    else:
        query = query.filter(False)
    defect_type = request.args.get('defect_type', '')
    # 添加缺陷类型过滤条件
    if defect_type == 'simplified':
        query = query.filter(Defect.defect_type == 'simplified')
    elif defect_type == 'simplified2':
        query = query.filter(Defect.defect_type == 'simplified2')
    else:
        # 当缺陷类型为'normal'时，排除简化类型缺陷（包括'simplified'和'simplified2'）
        query = query.filter(or_(Defect.defect_type == None, Defect.defect_type == ""))
    total = query.count()
    print(f"total:{total}")
    sql = query.statement.compile(compile_kwargs={"literal_binds": True})
    print(f"Generated SQL1111: {sql}")  # 实际开发中可用日志记录
    return f"{total}"