from conf.db import db
from sqlalchemy import inspect
from models.defect.model import DefectStageType
from models.role.model import Role
from models.template.model import TemplateType


class DataInitializer:
    def __init__(self):
        self.db = db

    def table_exists(self, table_name):
        """检查表是否存在"""
        inspector = inspect(self.db.engine)
        return inspector.has_table(table_name)

    def init_roles(self):
        """初始化角色数据"""
        try:
            # 检查表是否存在
            if not self.table_exists(Role.__tablename__):
                print(f"警告: {Role.__tablename__} 表不存在，跳过角色初始化")
                return

            # 获取现有角色
            existing_roles = {role.name for role in Role.query.all()}

            # 默认角色定义
            default_roles = [
                ('company_admin', '公司管理员'),
                ('global_admin', '全板块管理员'),
                ('global_viewer', '全板块查阅人'),
                ('project_admin', '项目管理员'),
                ('project_viewer', '项目查阅人'),
                ('dev_manager', '开发主管'),
                ('test_manager', '测试经理'),
                ('developer', '开发人员'),
                ('tester', '测试人员'),
                ('process_user', '流程使用者')
            ]

            # 筛选需要添加的角色
            roles_to_add = []
            for name, description in default_roles:
                if name not in existing_roles:
                    roles_to_add.append(Role(name=name, description=description))
            print('需要添加的角色个数: {0}'.format(len(roles_to_add)))

            # 批量添加角色
            if roles_to_add:
                self.db.session.bulk_save_objects(roles_to_add)
                self.db.session.commit()
                print(f"成功初始化 {len(roles_to_add)} 个角色")
            else:
                print("角色数据已存在，无需初始化")

        except Exception as e:
            print(f"角色初始化错误: {e}")

    def init_template_types(self):
        """初始化模板类型数据"""
        try:
            # 检查表是否存在
            if not self.table_exists('template_type'):
                print(f"警告: template_type 表不存在，跳过模板类型初始化")
                return

            # 获取现有模板类型
            existing_types = {template_type.name for template_type in TemplateType.query.all()}

            # 默认模板类型定义
            default_template_types = [
                ('缺陷描述', '用于记录缺陷描述的模板'),
                ('回归测试', '用于记录回归测试的模板')
            ]

            # 筛选需要添加的模板类型
            types_to_add = []
            for name, description in default_template_types:
                if name not in existing_types:
                    types_to_add.append(TemplateType(name=name, description=description))

            print(f'需要添加的模板类型数量: {len(types_to_add)}')

            # 批量添加模板类型
            if types_to_add:
                self.db.session.bulk_save_objects(types_to_add)
                self.db.session.commit()
                print(f"成功初始化 {len(types_to_add)} 个模板类型")
            else:
                print("模板类型数据已存在，无需初始化")

        except Exception as e:
            self.db.session.rollback()
            print(f"模板类型初始化错误: {e}")

    def init_defect_stage_types(self):
        """初始化缺陷阶段类型数据"""
        try:
            # 检查表是否存在
            if not self.table_exists(DefectStageType.__tablename__):
                print(f"警告: {DefectStageType.__tablename__} 表不存在，跳过缺陷阶段初始化")
                return False

            # 获取现有阶段类型
            existing_stage_types = {stage_type.stage_key for stage_type in DefectStageType.query.all()}
            print('existing_stage_types 个数：{0}'.format(len(existing_stage_types)))

            # 默认阶段定义
            default_stages = [
                ('draft_creation', '草稿创建', 0),
                ('defect_description', '缺陷描述', 1),
                ('test_manager_review_desc', '测试经理审核描述', 2),
                ('tester_confirm_desc', '测试人员确认描述', 3),
                ('cause_analysis', '开发人员定位问题', 4),
                ('dev_lead_review_analysis', '开发主管审核原因分析', 5),
                ('developer_solution', '开发人员解决措施', 6),
                ('dev_lead_review_solution', '开发主管审核解决措施', 7),
                ('tester_regression', '测试人员回归测试', 8),
                ('test_manager_review_regression', '测试经理审核回归测试', 9),
                ('requester_confirm', '提出人确认', 10)
            ]

            # 筛选需要添加的阶段
            stages_to_add = []
            for stage_key, stage_name, stage_order in default_stages:
                if stage_key not in existing_stage_types:
                    stages_to_add.append(DefectStageType(
                        stage_key=stage_key,
                        stage_name=stage_name,
                        stage_order=stage_order
                    ))

            print(f'需要添加的缺陷阶段个数: {len(stages_to_add)}')

            # 批量添加阶段
            if stages_to_add:
                try:
                    self.db.session.bulk_save_objects(stages_to_add)
                    self.db.session.commit()
                    print(f"成功初始化 {len(stages_to_add)} 个缺陷阶段")
                    return True
                except Exception as e:
                    self.db.session.rollback()
                    print(f"保存缺陷阶段时出错: {e}")
                    return False
            else:
                print("缺陷阶段数据已存在，无需初始化")
                return True

        except Exception as e:
            print(f"缺陷阶段初始化错误: {e}")
            if hasattr(self, 'db') and hasattr(self.db, 'session'):
                self.db.session.rollback()
            return False
