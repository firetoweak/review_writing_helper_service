from flask import Blueprint, request, jsonify, render_template, current_app, g, flash

# 删除 RoleType 导入，直接使用字符串角色类型
from models.project_member.model import ProjectMember, role_dict
from models.users.models import User
from services.project_member_services import ProjectMemberService, ProjectMemberAuthService
from services.role_services import UserRoleService

# 创建蓝图
project_member_bp = Blueprint('project_member', __name__)
@project_member_bp.route('/api/project-members', methods=['GET'])
def get_project_members():
    """
    获取项目成员列表
    ---
    tags:
      - 项目成员管理
    parameters:
      - name: page
        in: query
        type: integer
        default: 1
        description: 页码
      - name: per_page
        in: query
        type: integer
        default: 20
        description: 每页数量
      - name: type_filter
        in: query
        type: string
        enum: ['product_line', 'tech_group', 'all']
        description: 类型过滤
      - name: entity_id
        in: query
        type: integer
        description: 项目ID或版本ID
      - name: role_type
        in: query
        type: string
        description: 角色类型过滤
      - name: user_status
        in: query
        type: integer
        enum: [0, 1]
        description: 用户状态过滤
      - name: search_keyword
        in: query
        type: string
        description: 搜索关键词
    responses:
      200:
        description: 成功获取成员列表
        schema:
          type: object
          properties:
            code:
              type: integer
              example: 200
            message:
              type: string
              example: "success"
            data:
              type: object
              properties:
                data:
                  type: array
                  items:
                    type: object
                    properties:
                      type:
                        type: string
                        example: "tech_group"
                      entity_id:
                        type: integer
                        example: 1
                      path_name:
                        type: string
                        example: "前端技术族-Web平台-用户管理系统"
                      role_type:
                        type: string
                        example: "project_admin"
                      role_name:
                        type: string
                        example: "项目管理员"
                      user_count:
                        type: integer
                        example: 2
                      users:
                        type: array
                        items:
                          type: object
                          properties:
                            member_id:
                              type: integer
                              example: 123
                              description: "project_members表的主键ID，用于删除操作"
                            user_id:
                              type: integer
                              example: 1
                            real_name:
                              type: string
                              example: "张三"
                            email:
                              type: string
                              example: "zhangsan@example.com"
                            mobile:
                              type: string
                              example: "13800138000"
                            company_name:
                              type: string
                              example: "某公司"
                            status:
                              type: integer
                              example: 1
                            status_text:
                              type: string
                              example: "正常"
                pagination:
                  type: object
                  properties:
                    page:
                      type: integer
                      example: 1
                    per_page:
                      type: integer
                      example: 20
                    total:
                      type: integer
                      example: 100
                    pages:
                      type: integer
                      example: 5
      400:
        description: 参数错误
      500:
        description: 服务器内部错误
    """
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        type_filter = request.args.get('type_filter', 'all')
        entity_id = request.args.get('entity_id', type=int)
        role_type = request.args.get('role_type')
        user_status = request.args.get('user_status', type=int)
        search_keyword = request.args.get('search_keyword', '').strip()
        defect_type = request.args.get('defect_type', '').strip()

        # 参数验证
        if page < 1:
            return jsonify({'code': 400, 'message': '页码必须大于0'}), 400

        if per_page < 1 or per_page > 100:
            return jsonify({'code': 400, 'message': '每页数量必须在1-100之间'}), 400

        # 构建过滤条件
        filters = {}
        if type_filter != 'all':
            filters['type_filter'] = type_filter

        if entity_id:
            filters['entity_id'] = entity_id

        if role_type:
            # 支持多个角色类型，用逗号分隔
            role_types = [rt.strip() for rt in role_type.split(',')]
            # 验证角色类型是否有效
            valid_roles = []
            for rt in role_types:
                if rt in role_dict:  # 直接检查角色字典
                    valid_roles.append(rt)

            if valid_roles:
                filters['role_type'] = valid_roles
            else:
                return jsonify({'code': 400, 'message': '无效的角色类型'}), 400

        if user_status is not None:
            filters['user_status'] = user_status

        if search_keyword:
            filters['search_keyword'] = search_keyword

        if defect_type:
            filters['defect_type'] = defect_type
        # 调用服务获取数据
        result = ProjectMemberService.get_member_list(
            page=page,
            per_page=per_page,
            **filters
        )

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': result
        })

    except ValueError as e:
        current_app.logger.error(f"参数错误: {str(e)}")
        return jsonify({'code': 400, 'message': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"获取项目成员列表失败: {str(e)}")
        return jsonify({'code': 500, 'message': '服务器内部错误'}), 500


@project_member_bp.route('/api/project-members/count-project-admins', methods=['GET'])
def count_project_admins():
    """
    获取项目/版本的项目管理员数量
    ---
    tags:
      - 项目成员管理
    parameters:
      - name: entity_type
        in: query
        type: string
        required: true
        enum: ['tech_group', 'product_line']
        description: 实体类型
      - name: entity_id
        in: query
        type: integer
        required: true
        description: 实体ID
    responses:
      200:
        description: 成功获取项目管理员数量
        schema:
          type: object
          properties:
            code:
              type: integer
              example: 200
            message:
              type: string
              example: "success"
            data:
              type: object
              properties:
                count:
                  type: integer
                  example: 2
      400:
        description: 参数错误
      500:
        description: 服务器内部错误
    """
    try:
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id', type=int)

        if not entity_type or not entity_id:
            return jsonify({'code': 400, 'message': '参数 entity_type 和 entity_id 不能为空'}), 400

        if entity_type not in ['tech_group', 'product_line']:
            return jsonify({'code': 400, 'message': 'entity_type 必须是 tech_group 或 product_line'}), 400

        # 查询项目管理员数量
        if entity_type == 'tech_group':
            count = ProjectMember.query.filter_by(
                project_id=entity_id,
                role_type='project_admin'
            ).count()
        else:
            count = ProjectMember.query.filter_by(
                version_id=entity_id,
                role_type='project_admin'
            ).count()

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': {
                'count': count
            }
        })

    except Exception as e:
        current_app.logger.error(f"获取项目管理员数量失败: {str(e)}")
        return jsonify({'code': 500, 'message': '服务器内部错误'}), 500

@project_member_bp.route('/api/project-members/summary', methods=['GET'])
def get_project_members_summary():
    """
    获取项目成员统计摘要
    ---
    tags:
      - 项目成员管理
    responses:
      200:
        description: 成功获取统计摘要
        schema:
          type: object
          properties:
            code:
              type: integer
              example: 200
            message:
              type: string
              example: "success"
            data:
              type: object
              properties:
                tech_group_count:
                  type: integer
                  example: 5
                product_line_count:
                  type: integer
                  example: 3
                role_stats:
                  type: object
                  properties:
                    project_admin:
                      type: integer
                      example: 10
                    dev_manager:
                      type: integer
                      example: 15
                    test_manager:
                      type: integer
                      example: 8
    """
    try:
        summary = ProjectMemberService.get_member_summary()

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': summary
        })

    except Exception as e:
        current_app.logger.error(f"获取项目成员统计摘要失败: {str(e)}")
        return jsonify({'code': 500, 'message': '服务器内部错误'}), 500


@project_member_bp.route('/api/project-members', methods=['POST'])
@ProjectMemberAuthService.require_project_admin  # 添加鉴权装饰器
def add_project_member():
    """
    添加项目成员
    ---
    tags:
      - 项目成员管理
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            project_id:
              type: integer
              description: 项目ID（与version_id二选一）
            version_id:
              type: integer
              description: 版本ID（与project_id二选一）
            user_id:
              type: integer
              required: true
            role_type:
              type: string
              required: true
    responses:
      201:
        description: 成功添加成员
      400:
        description: 参数错误或成员已存在
      500:
        description: 服务器内部错误
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': 400, 'message': '请求数据不能为空'}), 400

        project_id = data.get('project_id')
        version_id = data.get('version_id')
        user_id = data.get('user_id')
        role_type = data.get('role_type')  # 直接使用字符串

        # 参数验证
        if not user_id:
            return jsonify({'code': 400, 'message': '用户ID不能为空'}), 400

        if not role_type:
            return jsonify({'code': 400, 'message': '角色类型不能为空'}), 400

        # 验证角色类型是否有效
        if role_type not in role_dict:
            return jsonify({'code': 400, 'message': f'无效的角色类型: {role_type}'}), 400

        if not project_id and not version_id:
            return jsonify({'code': 400, 'message': '必须提供项目ID或版本ID'}), 400

        if project_id and version_id:
            return jsonify({'code': 400, 'message': '不能同时提供项目ID和版本ID'}), 400

        # 调用服务添加成员（直接传递字符串角色类型）
        member = ProjectMemberService.create_member(
            project_id=project_id,
            version_id=version_id,
            user_id=user_id,
            role_type=role_type
        )

        return jsonify({
            'code': 201,
            'message': '添加成功',
            'data': member.to_dict(include_relations=True)
        }), 201

    except ValueError as e:
        return jsonify({'code': 400, 'message': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"添加项目成员失败: {str(e)}")
        return jsonify({'code': 500, 'message': '服务器内部错误'}), 500


@project_member_bp.route('/api/project-members/batch', methods=['POST'])
@ProjectMemberAuthService.require_project_admin  # 添加鉴权装饰器
def batch_add_project_members():
    """
    批量添加项目/版本成员接口
    POST /api/project-members/batch
    {
        "project_id": 1,           # 可选
        "version_id": 1,           # 可选
        "members": [               # 成员列表
            {
                "user_id": 123,
                "role_type": "developer"
            },
            {
                "user_id": 124,
                "role_type": "tester"
            }
        ]
    }
    """
    try:
        data = request.get_json()

        # 参数验证
        if not data:
            return jsonify({'code': 400, 'message': '请求参数不能为空'}), 400

        project_id = data.get('project_id')
        version_id = data.get('version_id')
        members_data = data.get('members', [])

        if not members_data:
            return jsonify({'code': 400, 'message': '成员列表不能为空'}), 400

        # 转换数据格式
        user_roles = []
        for member in members_data:
            user_id = member.get('user_id')
            role_type = member.get('role_type')

            if not user_id or not role_type:
                return jsonify({
                    'code': 400,
                    'message': f'成员数据格式错误: {member}'
                }), 400

            user_roles.append((user_id, role_type))

        # 调用服务层
        success_members, failed_records = ProjectMemberService.create_members_batch(
            project_id=project_id,
            version_id=version_id,
            user_roles=user_roles
        )

        # 构建响应
        response_data = {
            'code': 200,
            'message': '批量添加成员完成',
            'data': {
                'success_count': len(success_members),
                'failed_count': len(failed_records),
                'success_members': [
                    {
                        'user_id': member.user_id,
                        'role_type': member.role_type,
                        'project_id': member.project_id,
                        'version_id': member.version_id,
                        'id': member.id  # 假设ProjectMember有id字段
                    }
                    for member in success_members
                ],
                'failed_records': failed_records
            }
        }

        return jsonify(response_data), 200

    except ValueError as e:
        return jsonify({'code': 400, 'message': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"批量添加成员接口异常: {str(e)}")
        return jsonify({'code': 500, 'message': '服务器内部错误'}), 500


@project_member_bp.route('/api/project-members/<int:member_id>', methods=['PUT'])
@ProjectMemberAuthService.require_project_admin  # 添加鉴权装饰器
def update_project_member(member_id):
    """
    更新项目成员角色
    ---
    tags:
      - 项目成员管理
    parameters:
      - name: member_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            role_type:
              type: string
              required: true
    responses:
      200:
        description: 成功更新成员
      400:
        description: 参数错误
      404:
        description: 成员不存在
      500:
        description: 服务器内部错误
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': 400, 'message': '请求数据不能为空'}), 400

        role_type = data.get('role_type')  # 直接使用字符串
        if not role_type:
            return jsonify({'code': 400, 'message': '角色类型不能为空'}), 400

        # 验证角色类型是否有效
        if role_type not in role_dict:
            return jsonify({'code': 400, 'message': f'无效的角色类型: {role_type}'}), 400

        # 调用服务更新成员（直接传递字符串角色类型）
        member = ProjectMemberService.update_member_role(member_id, role_type)

        return jsonify({
            'code': 200,
            'message': '更新成功',
            'data': member.to_dict(include_relations=True)
        })

    except ValueError as e:
        if "成员不存在" in str(e):
            return jsonify({'code': 404, 'message': str(e)}), 404
        return jsonify({'code': 400, 'message': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"更新项目成员失败: {str(e)}")
        return jsonify({'code': 500, 'message': '服务器内部错误'}), 500


@project_member_bp.route('/api/project-members/<int:member_id>', methods=['DELETE'])
@ProjectMemberAuthService.require_project_admin  # 添加鉴权装饰器
def delete_project_member(member_id):
    """
    删除项目成员
    ---
    tags:
      - 项目成员管理
    parameters:
      - name: member_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: 成功删除成员
      404:
        description: 成员不存在
      500:
        description: 服务器内部错误
    """
    try:
        ProjectMemberService.delete_member(member_id)

        return jsonify({
            'code': 200,
            'message': '删除成功'
        })

    except ValueError as e:
        return jsonify({'code': 404, 'message': str(e)}), 404
    except Exception as e:
        current_app.logger.error(f"删除项目成员失败: {str(e)}")
        return jsonify({'code': 500, 'message': '服务器内部错误'}), 500


@project_member_bp.route('/api/project-members/check', methods=['GET'])
def check_project_member():
    """
    检查用户在某项目/版本中的角色
    ---
    tags:
      - 项目成员管理
    parameters:
      - name: project_id
        in: query
        type: integer
      - name: version_id
        in: query
        type: integer
      - name: user_id
        in: query
        type: integer
        required: true
    responses:
      200:
        description: 检查结果
        schema:
          type: object
          properties:
            code:
              type: integer
              example: 200
            message:
              type: string
              example: "success"
            data:
              type: object
              properties:
                exists:
                  type: boolean
                  example: true
                member:
                  type: object
                  nullable: true
      400:
        description: 参数错误
    """
    try:
        project_id = request.args.get('project_id', type=int)
        version_id = request.args.get('version_id', type=int)
        user_id = request.args.get('user_id', type=int)

        if not user_id:
            return jsonify({'code': 400, 'message': '用户ID不能为空'}), 400

        if not project_id and not version_id:
            return jsonify({'code': 400, 'message': '必须提供项目ID或版本ID'}), 400

        member = ProjectMemberService.find_member(project_id, version_id, user_id)

        result = {
            'exists': member is not None,
            'member': member.to_dict(include_relations=True) if member else None
        }

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': result
        })

    except Exception as e:
        current_app.logger.error(f"检查项目成员失败: {str(e)}")
        return jsonify({'code': 500, 'message': '服务器内部错误'}), 500


# 前端页面路由
@project_member_bp.route('/project-members', methods=['GET'])
@UserRoleService.check_global_roles(
    allowed_roles=['project_admin'],
    template='defect/defect_levels.html'
)
def project_members_page():
    """项目成员管理页面 仅获取本公司的项目或版本相关的成员信息，暂不鉴权——对增删进行鉴权"""
    try:
        # 获取用户角色信息
        current_app.logger.debug(f'current_user_id: {g.user_id}')
        current_app.logger.debug(f'current_user admin_user_id: {g.admin_user_id}')
        success, user_info = UserRoleService.get_user_roles_info(g.user_id) # 设置  g.is_company_admin  is_global_admin
        company_user_list = User.get_company_users_by_user_id(g.user_id)
        current_app.logger.debug(f'company_user_list: {company_user_list}')
        company_global_admin_users = UserRoleService.get_company_global_admin_users(g.user_id)

        return render_template('project_member/project_members.html',
                               company_user_list=company_user_list,
                               company_global_admin_users=company_global_admin_users,
                               current_user_id = g.user_id,
                               is_company_admin=g.is_company_admin,
                               is_global_admin=g.is_global_admin,
                               is_global_viewer=g.is_global_viewer)

    except Exception as e:
        current_app.logger.error(f"Route1 获取项目成员列表失败: {str(e)}")
        flash('获取项目成员列表失败，请稍后重试', 'error')
        return render_template('project_member/project_members.html',
                               error_message='获取项目成员列表失败'), 500