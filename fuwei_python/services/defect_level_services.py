from models.defect_level.model import db, DefectLevel, ModificationLog, DEFECT_LEVEL_FIELD_DISPLAY_NAMES

from flask import g, session  # 使用 Flask 和 g 对象存储了当前用户信息

from models.users.models import User


class DefectLevelsService:
    @staticmethod
    def get_all_defect_levels():
        # 获取当前用户对应的全板块管理员创建的DI值规则记录
        current_user_id = g.user_id  # 当前用户信息存储在 g 中
        global_admin_user_id = g.admin_user_id
        defect_level = DefectLevel.query.filter_by(user_id=global_admin_user_id).first()
        return defect_level

    @staticmethod
    def update_defect_level_score(level_id, field_name, new_score, modifier):
        # 校验分数必须是大于0的浮点数
        try:
            new_score = float(new_score)
            if new_score <= 0:
                return None, "分数必须大于0"
        except (ValueError, TypeError):
            return None, "分数必须是有效的数字"

        # 验证字段名是否有效
        if field_name not in DEFECT_LEVEL_FIELD_DISPLAY_NAMES:
            return None, "无效的缺陷级别字段"

        defect_level = DefectLevel.query.get(level_id)
        if not defect_level:
            return None, "缺陷等级不存在"

        # 获取旧值
        old_value = getattr(defect_level, field_name)

        # 更新字段值
        setattr(defect_level, field_name, new_score)
        displayed_field_name = DEFECT_LEVEL_FIELD_DISPLAY_NAMES[field_name]
        # 记录修改日志
        if old_value != new_score:
            log = ModificationLog(
                defect_level_id=level_id,
                field_name=displayed_field_name,
                old_value=old_value,  # 直接存储浮点数值
                new_value=new_score,  # 直接存储浮点数值
                modifier=modifier
            )
            db.session.add(log)

        db.session.commit()
        return defect_level, "分数更新成功"

    @staticmethod
    def get_modification_logs():
        # 获取当前用户所在公司的所有用户
        company_user_list = User.get_company_users_by_user_id(g.user_id)
        # 提取用户ID列表
        company_user_ids = [user.get('user_id') for user in company_user_list]

        # 获取当前用户及其公司成员的修改日志
        return ModificationLog.query \
            .join(DefectLevel, ModificationLog.defect_level_id == DefectLevel.id) \
            .filter(DefectLevel.user_id.in_(company_user_ids)) \
            .order_by(ModificationLog.modified_time.desc()) \
            .all()

    @staticmethod
    def get_defect_level_by_user(user_id):
        """获取指定用户的缺陷级别配置"""
        return DefectLevel.query.filter_by(user_id=user_id).first()

    @staticmethod
    def create_default_defect_level(user_id):
        """为用户创建默认的缺陷级别配置"""
        default_defect_level = DefectLevel(
            critical_defects=10.0,
            major_defects=3.0,
            minor_defects=1.0,
            suggestion_defects=0.1,
            user_id=user_id
        )
        db.session.add(default_defect_level)
        db.session.commit()
        return default_defect_level