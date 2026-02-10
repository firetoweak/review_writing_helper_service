import json
import time

from flask import Blueprint, request, jsonify, session, current_app
from services.product_line_services import ProductLineService
from flask import Blueprint, request, jsonify, render_template,g

from services.role_services import UserRoleService
from services.tech_group_service import TechGroupService
from models.users.models import User
from services.inner_service import InnerSrvice
# 创建蓝图
product_line_bp = Blueprint('product_line', __name__)


# 产品线管理
@product_line_bp.route('/lines', methods=['GET'])
def get_product_lines():
    """获取产品线列表"""
    filters = {}
    if request.args.get('name'):
        filters['name'] = request.args.get('name')

    result, status_code = ProductLineService.get_product_lines(filters)
    if status_code != 200:
        return jsonify(result), status_code

    return render_template('product_line/product_lines.html', product_lines=result['data'])


@product_line_bp.route('/lines/<int:line_id>', methods=['DELETE'])
def delete_product_line(line_id):
    """删除产品线"""
    result, status_code = ProductLineService.delete_product_line(g.admin_user_id,line_id)
    return jsonify(result), status_code

# 产品管理
@product_line_bp.route('/products', methods=['GET'])
def get_products():
    """获取产品列表"""
    filters = {}
    if request.args.get('product_line_name'):
        filters['product_line_name'] = request.args.get('product_line_name')
    if request.args.get('product_name'):
        filters['product_name'] = request.args.get('product_name')

    result, status_code = ProductLineService.get_products(filters)
    if status_code != 200:
        return jsonify(result), status_code

    # 获取所有产品线用于下拉选择和名称映射
    product_lines_result, _ = ProductLineService.get_product_lines()
    product_lines = product_lines_result['data'] if 'data' in product_lines_result else []

    # 创建产品线ID到名称的映射
    product_line_map = {line['id']: line['name'] for line in product_lines}

    # 为每个产品添加产品线名称
    for product in result['data']:
        product_line_id = product.get('product_line_id')
        if product_line_id and product_line_id in product_line_map:
            product['product_line_name'] = product_line_map[product_line_id]
        else:
            product['product_line_name'] = '未知产品线'

    return render_template('product_line/products.html',
                           products=result['data'],
                           product_lines=product_lines)

@product_line_bp.route('/edit_product', methods=['POST'])
def edit_product():
    """
    :return:
    """
    data = request.json
    data['admin_user_id'] = g.admin_user_id
    if data['id']=="":
        return ProductLineService.create_product(data)
    else:
        return ProductLineService.update_product(data)


@product_line_bp.route('/edit_product_line', methods=['POST'])
def edit_product_line():
    """
    :return:
    """
    data = request.json
    data['admin_user_id'] = g.admin_user_id
    if data['id']=="":
        return ProductLineService.create_product_line(data)
    else:
        return ProductLineService.update_product_line(data)


@product_line_bp.route('/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    """删除产品"""
    result, status_code = ProductLineService.delete_product(g.admin_user_id,product_id)
    return jsonify(result), status_code

@product_line_bp.route('/versions', methods=['GET'])
@UserRoleService.check_global_roles(
    allowed_roles=['global_admin', 'global_viewer','company_admin'],
    template='defect/defect_levels.html',
    json_response=True
)
def get_versions():
    """获取版本列表"""
    filters = {}
    if request.args.get('product_line_name'):
        filters['product_line_name'] = request.args.get('product_line_name')
    if request.args.get('product_name'):
        filters['product_name'] = request.args.get('product_name')
    if request.args.get('version_number'):
        filters['version_number'] = request.args.get('version_number')
    filters['admin_user_id'] = g.admin_user_id
    result, status_code = ProductLineService.get_versions(filters)
    if status_code != 200:
        return jsonify(result), status_code
    user_list = User.get_like_defect_user_list(g.admin_user_id)
    return render_template('product_line/version.html',
                           versions=result['data'],
                           pagination = result['pagination'],
                           user_list = json.dumps( [{'real_name': user.real_name,'email' :user.email,'user_id':user.user_id,'dept':user.dept}   for user in user_list]),
                           actions = 'version',
                           keys= {"level2":"products","actions":"version"}
                           )

@product_line_bp.route('/versions', methods=['POST'])
@UserRoleService.check_global_roles(
    allowed_roles=['global_admin', 'global_viewer','company_admin'],
    template='defect/defect_levels.html',
    json_response=True
)
def edit_version():
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
        result, status_code = ProductLineService.create_version(data)
    else:
        print(data)
        result, status_code = ProductLineService.update_version(data['record_id'], data)
    return jsonify(result), status_code

@product_line_bp.route('/versions/<int:version_id>', methods=['DELETE'])
def delete_version(version_id):
    """删除版本"""
    result, status_code = ProductLineService.delete_version(g.admin_user_id,version_id)
    return jsonify(result), status_code
@product_line_bp.route('/delete_versions', methods=['POST'])
def delete_versions():
    """删除版本"""
    data = request.json
    return ProductLineService.delete_version_ids(data,g.admin_user_id)


# 主页面 - 显示所有层级
@product_line_bp.route('/hierarchy', methods=['GET'])
def get_hierarchy():
    """获取产品线-产品-版本的全量层级结构"""
    # 获取所有产品线
    admin_user_id = g.admin_user_id
    hierarchy = ProductLineService.get_hierarchy(admin_user_id)
    return jsonify(hierarchy),200
    return render_template('product_line/hierarchy.html', hierarchy=hierarchy)