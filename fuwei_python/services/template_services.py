from flask import g, session  # 使用 Flask 和 g 对象存储了当前用户信息
from models.template.model import db, TemplateType, Template, TemplateItem
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_


class TemplateTypeService:
    """模板类型服务类"""

    @staticmethod
    def get_all(include_templates: bool = False, include_items: bool = False) -> List[TemplateType]:
        """
        获取所有模板类型

        Args:
            include_templates: 是否包含模板信息
            include_items: 是否包含模板项信息（仅在include_templates为True时有效）
        """
        query = TemplateType.query

        if include_templates:
            # 预加载模板
            query = query.options(db.joinedload(TemplateType.templates))

            if include_items:
                # 预加载模板及其项
                query = query.options(
                    db.joinedload(TemplateType.templates).joinedload(Template.items)
                )

        return query.all()

    @staticmethod
    def get_by_id(type_id: int, include_templates: bool = False,
                  include_items: bool = False) -> Optional[TemplateType]:
        """
        根据ID获取模板类型

        Args:
            type_id: 模板类型ID
            include_templates: 是否包含模板信息
            include_items: 是否包含模板项信息（仅在include_templates为True时有效）
        """
        query = TemplateType.query.filter_by(id=type_id)

        if include_templates:
            # 预加载模板
            query = query.options(db.joinedload(TemplateType.templates))

            if include_items:
                # 预加载模板及其项
                query = query.options(
                    db.joinedload(TemplateType.templates).joinedload(Template.items)
                )

        return query.first()

    @staticmethod
    def get_by_name(name: str, include_templates: bool = False,
                    include_items: bool = False, user_id: int = None) -> Optional[TemplateType]:
        """
        根据名称获取模板类型

        Args:
            name: 模板类型名称
            include_templates: 是否包含模板信息
            include_items: 是否包含模板项信息（仅在include_templates为True时有效）
            user_id: 可选的用户ID过滤（仅在include_templates为True时有效）
        """
        query = TemplateType.query.filter_by(name=name)

        if include_templates:
            # 预加载模板，并根据user_id进行过滤
            if user_id is not None:
                # 使用join和filter来过滤关联的模板
                query = query.join(TemplateType.templates).filter(Template.user_id == user_id)
                # 使用contains_eager来确保预加载的关联对象与过滤条件一致
                query = query.options(db.contains_eager(TemplateType.templates))

                if include_items:
                    # 预加载模板及其项
                    query = query.options(
                        db.joinedload(TemplateType.templates).joinedload(Template.items)
                    )
            else:
                # 如果没有user_id过滤，正常预加载所有模板
                query = query.options(db.joinedload(TemplateType.templates))

                if include_items:
                    # 预加载模板及其项
                    query = query.options(
                        db.joinedload(TemplateType.templates).joinedload(Template.items)
                    )

        return query.first()

    @staticmethod
    def create(name: str, description: str = None) -> TemplateType:
        """创建新的模板类型"""
        template_type = TemplateType(
            name=name,
            description=description
        )
        db.session.add(template_type)
        db.session.commit()
        return template_type

    @staticmethod
    def update(type_id: int, **kwargs) -> Optional[TemplateType]:
        """更新模板类型"""
        template_type = TemplateType.query.get(type_id)
        if template_type:
            for key, value in kwargs.items():
                if hasattr(template_type, key):
                    setattr(template_type, key, value)
            db.session.commit()
        return template_type

    @staticmethod
    def delete(type_id: int) -> bool:
        """删除模板类型"""
        template_type = TemplateType.query.get(type_id)
        if template_type:
            db.session.delete(template_type)
            db.session.commit()
            return True
        return False

    @staticmethod
    def get_templates_by_type(type_id: int, include_items: bool = True,
                              user_id: int = None, name_filter: str = None,
                              only_active: bool = False) -> List[Template]:
        """
        根据模板类型ID获取模板及其项信息

        Args:
            type_id: 模板类型ID
            include_items: 是否包含模板项信息
            user_id: 可选的用户ID过滤
            name_filter: 模板名称过滤条件
            only_active: 是否只返回活跃模板
        """
        query = Template.query.filter_by(type_id=type_id)

        if user_id:
            query = query.filter_by(user_id=user_id)

        if name_filter:
            query = query.filter(Template.name.ilike(f"%{name_filter}%"))

        if only_active:
            query = query.filter_by(is_active=True)

        if include_items:
            query = query.options(db.joinedload(Template.items))

        return query.all()

    @staticmethod
    def get_type_with_templates_and_items(type_id: int, user_id: int = None,
                                          name_filter: str = None,
                                          only_active: bool = False) -> Dict:
        """
        获取模板类型及其所有模板和模板项的完整信息

        Args:
            type_id: 模板类型ID
            user_id: 可选的用户ID过滤
            name_filter: 模板名称过滤条件
            only_active: 是否只返回活跃模板
        """
        # 获取模板类型
        template_type = TemplateTypeService.get_by_id(type_id)
        if not template_type:
            return None

        # 获取模板及其项
        templates = TemplateTypeService.get_templates_by_type(
            type_id=type_id,
            include_items=True,
            user_id=user_id,
            name_filter=name_filter,
            only_active=only_active
        )

        # 构建返回结果
        result = template_type.to_dict()
        result['templates'] = [template.to_dict(include_items=True) for template in templates]

        return result

    @staticmethod
    def get_all_types_with_templates(include_items: bool = False,
                                     user_id: int = None,
                                     only_active: bool = False) -> List[Dict]:
        """
        获取所有模板类型及其模板信息

        Args:
            include_items: 是否包含模板项信息
            user_id: 可选的用户ID过滤
            only_active: 是否只返回活跃模板
        """
        template_types = TemplateTypeService.get_all()

        result = []
        for template_type in template_types:
            # 获取该类型的所有模板
            templates = TemplateTypeService.get_templates_by_type(
                type_id=template_type.id,
                include_items=include_items,
                user_id=user_id,
                only_active=only_active
            )

            # 构建类型信息
            type_info = template_type.to_dict()
            type_info['templates'] = [template.to_dict(include_items=include_items) for template in templates]

            result.append(type_info)

        return result


class TemplateService:
    """模板服务类"""

    @staticmethod
    def get_all(include_items: bool = True, name_filter: str = None,
                type_id: int = None, type_name: str = None) -> List[Template]:
        """
        获取所有模板，可选项按名称和类型过滤

        Args:
            include_items: 是否包含模板项
            name_filter: 模板名称过滤条件
            type_id: 模板类型ID过滤条件
            type_name: 模板类型名称过滤条件
        """
        query = Template.query

        # 应用名称过滤
        if name_filter:
            query = query.filter(Template.name.ilike(f"%{name_filter}%"))

        # 应用类型ID过滤
        if type_id:
            query = query.filter_by(type_id=type_id)

        # 应用类型名称过滤（需要联表查询）
        if type_name:
            query = query.join(TemplateType).filter(TemplateType.name.ilike(f"%{type_name}%"))

        if include_items:
            # 使用joinedload预加载模板项，避免N+1查询问题
            query = query.options(db.joinedload(Template.items))

        return query.all()

    @staticmethod
    def get_by_id(template_id: int, include_items: bool = True) -> Optional[Template]:
        """
        根据ID获取模板

        Args:
            template_id: 模板ID
            include_items: 是否包含模板项
        """
        query = Template.query.filter_by(id=template_id)

        if include_items:
            query = query.options(db.joinedload(Template.items))

        return query.first()

    @staticmethod
    def get_by_user(user_id: int, include_items: bool = True,
                    name_filter: str = None, only_active: bool = False,
                    type_id: int = None, type_name: str = None) -> List[Template]:
        """
        根据用户ID获取模板

        Args:
            user_id: 用户ID
            include_items: 是否包含模板项
            name_filter: 模板名称过滤条件
            only_active: 是否只返回活跃模板
            type_id: 模板类型ID过滤条件
            type_name: 模板类型名称过滤条件
        """
        query = Template.query.filter_by(user_id=user_id)

        if name_filter:
            query = query.filter(Template.name.ilike(f"%{name_filter}%"))

        if only_active:
            query = query.filter_by(is_active=True)

        if type_id:
            query = query.filter_by(type_id=type_id)

        if type_name:
            query = query.join(TemplateType).filter(TemplateType.name.ilike(f"%{type_name}%"))

        if include_items:
            query = query.options(db.joinedload(Template.items))

        return query.all()

    @staticmethod
    def get_by_type(type_id: int, include_items: bool = True,
                    user_id: int = None, name_filter: str = None,
                    only_active: bool = False) -> List[Template]:
        """
        根据模板类型ID获取模板及其项信息

        Args:
            type_id: 模板类型ID
            include_items: 是否包含模板项信息
            user_id: 可选的用户ID过滤
            name_filter: 模板名称过滤条件
            only_active: 是否只返回活跃模板
        """
        query = Template.query.filter_by(type_id=type_id)

        if user_id:
            query = query.filter_by(user_id=user_id)

        if name_filter:
            query = query.filter(Template.name.ilike(f"%{name_filter}%"))

        if only_active:
            query = query.filter_by(is_active=True)

        if include_items:
            query = query.options(db.joinedload(Template.items))

        return query.all()

    @staticmethod
    def get_by_type_name(type_name: str, include_items: bool = True,
                         user_id: int = None, name_filter: str = None,
                         only_active: bool = False) -> List[Template]:
        """
        根据模板类型名称获取模板及其项信息

        Args:
            type_name: 模板类型名称
            include_items: 是否包含模板项信息
            user_id: 可选的用户ID过滤
            name_filter: 模板名称过滤条件
            only_active: 是否只返回活跃模板
        """
        # 首先获取模板类型
        template_type = TemplateTypeService.get_by_name(type_name)
        if not template_type:
            return []

        # 使用get_by_type方法获取模板
        return TemplateService.get_by_type(
            type_id=template_type.id,
            include_items=include_items,
            user_id=user_id,
            name_filter=name_filter,
            only_active=only_active
        )

    @staticmethod
    def get_by_user_and_type(user_id: int, type_id: int, include_items: bool = True,
                             name_filter: str = None, only_active: bool = False) -> List[Template]:
        """
        根据用户ID和类型ID获取模板

        Args:
            user_id: 用户ID
            type_id: 模板类型ID
            include_items: 是否包含模板项
            name_filter: 模板名称过滤条件
            only_active: 是否只返回活跃模板
        """
        query = Template.query.filter_by(user_id=user_id, type_id=type_id)

        if name_filter:
            query = query.filter(Template.name.ilike(f"%{name_filter}%"))

        if only_active:
            query = query.filter_by(is_active=True)

        if include_items:
            query = query.options(db.joinedload(Template.items))

        return query.all()

    @staticmethod
    def search_templates(user_id: int = None,
                         include_items: bool = True, type_id: int = None,
                         type_name: str = None) -> List[Template]:
        """
        搜索模板，可指定用户搜索模板类型ID、模板类型名称

        Args:
            user_id: 可选的用户ID限制
            include_items: 是否包含模板项
            type_id: 可选的模板类型ID限制
            type_name: 可选的模板类型名称限制（如"缺陷描述"或"回归测试"）
        """
        from sqlalchemy.orm import joinedload  # 确保导入joinedload

        # 创建基础查询
        query = Template.query

        if user_id:
            query = query.filter_by(user_id=user_id)

        if type_id:
            query = query.filter_by(type_id=type_id)

        # 模板类型名称筛选
        if type_name:
            query = query.join(Template.template_type).filter(
                TemplateType.name == type_name
            )

        if include_items:
            query = query.options(joinedload(Template.items))

        return query.all()

    @staticmethod
    def create(user_id: int, type_id: int, name: str, created_by: int,
               updated_by: int = None, is_active: bool = True,
               items: List[Dict] = None) -> Template:
        """
        创建新模板，可同时创建模板项

        Args:
            user_id: 用户ID
            type_id: 模板类型ID
            name: 模板名称
            created_by: 创建者用户ID
            updated_by: 更新者用户ID
            is_active: 是否活跃
            items: 模板项列表
        """
        try:
            template = Template(
                user_id=user_id,
                type_id=type_id,
                name=name,
                is_active=is_active,
                created_by=created_by,
                updated_by=updated_by or created_by
            )
            db.session.add(template)
            db.session.flush()  # 获取模板ID但不提交事务

            # 如果有模板项，创建它们
            if items:
                for index, item_data in enumerate(items):
                    template_item = TemplateItem(
                        template_id=template.id,
                        content=item_data.get('content', {}),
                        sort_order=item_data.get('sort_order', index),
                        is_removable=item_data.get('is_removable', True),
                        is_required=item_data.get('is_required', False)
                    )
                    db.session.add(template_item)

            db.session.commit()
            return template

        except SQLAlchemyError as e:
            db.session.rollback()
            raise e

    @staticmethod
    def update(template_id: int, **kwargs) -> Optional[Template]:
        """
        更新模板

        Args:
            template_id: 模板ID
            **kwargs: 要更新的字段
        """
        template = Template.query.get(template_id)
        if template:
            for key, value in kwargs.items():
                if hasattr(template, key):
                    setattr(template, key, value)
            db.session.commit()
        return template

    @staticmethod
    def delete(template_id: int) -> bool:
        """
        删除模板

        Args:
            template_id: 模板ID
        """
        template = Template.query.get(template_id)
        if template:
            db.session.delete(template)
            db.session.commit()
            return True
        return False

    @staticmethod
    def create_defect_description_template(user_id: int) -> Optional[Template]:
        """
        为用户创建 缺陷描述 默认模板
        包含5个标题:描述模板项

        Args:
            user_id: 用户ID
        """
        try:
            # 首先获取或创建默认模板类型
            template_type = TemplateTypeService.get_by_name("缺陷描述")
            if not template_type:
                template_type = TemplateTypeService.create(
                    name="缺陷描述",
                    description="默认的缺陷描述模板类型"
                )

            # 定义默认的模板项
            default_items = [
                {
                    "content": {"title": "【缺陷现象描述】", "description": ""},
                    "sort_order": 0,
                    "is_removable": True,
                    "is_required": True
                },
                {
                    "content": {"title": "【发现缺陷的测试环境】", "description": ""},
                    "sort_order": 1,
                    "is_removable": True,
                    "is_required": True
                },
                {
                    "content": {"title": "【缺陷的影响描述】", "description": ""},
                    "sort_order": 2,
                    "is_removable": True,
                    "is_required": True
                },
                {
                    "content": {"title": "【对缺陷原因的初步推测】", "description": ""},
                    "sort_order": 3,
                    "is_removable": True,
                    "is_required": True
                }
            ]

            # 使用create方法创建模板和模板项
            template = TemplateService.create(
                user_id=user_id,
                type_id=template_type.id,
                name="默认缺陷描述模板",
                created_by=user_id,
                updated_by=user_id,
                items=default_items
            )

            return template

        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"创建默认模板失败: {str(e)}")
            return None

    @staticmethod
    def create_regression_test_template(user_id: int) -> Optional[Template]:
        """
        为用户创建回归测试默认模板
        包含5个标题:描述模板项

        Args:
            user_id: 用户ID
        """
        try:
            # 首先获取或创建回归测试模板类型
            template_type = TemplateTypeService.get_by_name("回归测试")
            if not template_type:
                template_type = TemplateTypeService.create(
                    name="回归测试",
                    description="默认的回归测试模板类型"
                )

            # 定义回归测试的默认模板项
            regression_items = [
                {
                    "content": {"title": "【回归测试过程与结果描述】", "description": ""},
                    "sort_order": 0,
                    "is_removable": True,
                    "is_required": True
                },
                {
                    "content": {"title": "【回归测试版本】", "description": ""},
                    "sort_order": 1,
                    "is_removable": True,
                    "is_required": True
                },
                {
                    "content": {"title": "【回归测试环境】", "description": ""},
                    "sort_order": 2,
                    "is_removable": True,
                    "is_required": True
                }
            ]

            # 使用create方法创建模板和模板项
            template = TemplateService.create(
                user_id=user_id,
                type_id=template_type.id,
                name="默认回归测试模板",
                created_by=user_id,
                updated_by=user_id,
                items=regression_items
            )

            return template

        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"创建回归测试模板失败: {str(e)}")
            return None

    @staticmethod
    def create_cause_analysis_template(user_id: int) -> Optional[Template]:
        """
        为用户创建原因分析默认模板
        包含3个原因分析项

        Args:
            user_id: 用户ID
        """
        try:
            # 首先获取或创建原因分析模板类型
            template_type = TemplateTypeService.get_by_name("原因分析")
            if not template_type:
                template_type = TemplateTypeService.create(
                    name="原因分析",
                    description="默认的原因分析模板类型"
                )

            # 定义原因分析的默认模板项
            cause_items = [
                {
                    "content": {"title": "【原因1】", "description": "请详细描述第一个可能的原因"},
                    "sort_order": 0,
                    "is_removable": True,
                    "is_required": True
                },
                {
                    "content": {"title": "【原因2】", "description": "请详细描述第二个可能的原因"},
                    "sort_order": 1,
                    "is_removable": True,
                    "is_required": True
                },
                {
                    "content": {"title": "【原因3】", "description": "请详细描述第三个可能的原因"},
                    "sort_order": 2,
                    "is_removable": True,
                    "is_required": True
                }
            ]

            # 使用create方法创建模板和模板项
            template = TemplateService.create(
                user_id=user_id,
                type_id=template_type.id,
                name="默认原因分析模板",
                created_by=user_id,
                updated_by=user_id,
                items=cause_items
            )

            return template

        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"创建原因分析模板失败: {str(e)}")
            return None

    @staticmethod
    def create_solution_measures_template(user_id: int) -> Optional[Template]:
        """
        为用户创建解决措施默认模板
        包含3个解决措施项

        Args:
            user_id: 用户ID
        """
        try:
            # 首先获取或创建解决措施模板类型
            template_type = TemplateTypeService.get_by_name("解决措施")
            if not template_type:
                template_type = TemplateTypeService.create(
                    name="解决措施",
                    description="默认的解决措施模板类型"
                )

            # 定义解决措施的默认模板项
            solution_items = [
                {
                    "content": {"title": "【措施1】", "description": "请详细描述第一个解决措施"},
                    "sort_order": 0,
                    "is_removable": True,
                    "is_required": True
                },
                {
                    "content": {"title": "【措施2】", "description": "请详细描述第二个解决措施"},
                    "sort_order": 1,
                    "is_removable": True,
                    "is_required": True
                },
                {
                    "content": {"title": "【措施3】", "description": "请详细描述第三个解决措施"},
                    "sort_order": 2,
                    "is_removable": True,
                    "is_required": True
                }
            ]

            # 使用create方法创建模板和模板项
            template = TemplateService.create(
                user_id=user_id,
                type_id=template_type.id,
                name="默认解决措施模板",
                created_by=user_id,
                updated_by=user_id,
                items=solution_items
            )

            return template

        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"创建解决措施模板失败: {str(e)}")
            return None

    @staticmethod
    def create_default_templates(user_id: int) -> Dict[str, Optional[Template]]:
        """
        为用户创建所有默认模板
        包括缺陷描述模板、回归测试模板、原因分析模板和解决措施模板

        Args:
            user_id: 用户ID

        Returns:
            包含四个模板的字典
        """
        result = {
            "defect_template": None,
            "regression_template": None,
            "cause_analysis_template": None,
            "solution_measures_template": None
        }

        # 创建缺陷描述模板
        defect_template = TemplateService.create_defect_description_template(user_id)
        result["defect_template"] = defect_template

        # 创建回归测试模板
        regression_template = TemplateService.create_regression_test_template(user_id)
        result["regression_template"] = regression_template

        # 创建原因分析模板
        cause_analysis_template = TemplateService.create_cause_analysis_template(user_id)
        result["cause_analysis_template"] = cause_analysis_template

        # 创建解决措施模板
        solution_measures_template = TemplateService.create_solution_measures_template(user_id)
        result["solution_measures_template"] = solution_measures_template

        return result

    @staticmethod
    def get_template_with_items_dict(template_id: int) -> Optional[Dict]:
        """
        获取模板及其项的字典表示

        Args:
            template_id: 模板ID
        """
        template = TemplateService.get_by_id(template_id, include_items=True)
        if template:
            return template.to_dict(include_items=True)
        return None

    @staticmethod
    def get_templates_by_type_with_info(type_id: int, include_items: bool = True,
                                        user_id: int = None, name_filter: str = None,
                                        only_active: bool = False) -> Dict:
        """
        获取模板类型及其所有模板和模板项的完整信息

        Args:
            type_id: 模板类型ID
            include_items: 是否包含模板项信息
            user_id: 可选的用户ID过滤
            name_filter: 模板名称过滤条件
            only_active: 是否只返回活跃模板
        """
        # 获取模板类型信息
        template_type = TemplateTypeService.get_by_id(type_id)
        if not template_type:
            return None

        # 获取模板及其项
        templates = TemplateService.get_by_type(
            type_id=type_id,
            include_items=include_items,
            user_id=user_id,
            name_filter=name_filter,
            only_active=only_active
        )

        # 构建返回结果
        result = template_type.to_dict()
        result['templates'] = [template.to_dict(include_items=include_items) for template in templates]

        return result


class TemplateItemService:
    """模板项服务类"""

    @staticmethod
    def create_template_item(template_id: int, content: str,
                             sort_order: int = 0, is_removable: bool = False,
                             is_required: bool = False) -> TemplateItem:
        """创建模板项"""
        template_item = TemplateItem(
            template_id=template_id,
            content=content,
            sort_order=sort_order,
            is_removable=is_removable,
            is_required=is_required
        )
        db.session.add(template_item)
        db.session.commit()
        return template_item

    @staticmethod
    def get_template_item_by_id(item_id: int) -> Optional[TemplateItem]:
        """根据ID获取模板项"""
        return TemplateItem.query.get(item_id)

    @staticmethod
    def get_template_items_by_template(template_id: int) -> List[TemplateItem]:
        """根据模板ID获取所有模板项"""
        return TemplateItem.query.filter_by(template_id=template_id).order_by(TemplateItem.sort_order).all()

    @staticmethod
    def update_template_item(item_id: int, **kwargs) -> Optional[TemplateItem]:
        """更新模板项"""
        template_item = TemplateItem.query.get(item_id)
        if not template_item:
            return None

        for key, value in kwargs.items():
            if hasattr(template_item, key):
                setattr(template_item, key, value)

        db.session.commit()
        return template_item

    @staticmethod
    def delete_template_item(item_id: int) -> bool:
        """删除模板项"""
        template_item = TemplateItem.query.get(item_id)
        if not template_item:
            return False

        db.session.delete(template_item)
        db.session.commit()
        return True

    @staticmethod
    def delete_template_items_by_template(template_id: int) -> int:
        """删除指定模板的所有模板项，返回删除的数量"""
        deleted_count = TemplateItem.query.filter_by(template_id=template_id).delete()
        db.session.commit()
        return deleted_count
