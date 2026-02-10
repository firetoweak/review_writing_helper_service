from sqlalchemy import desc, and_

from models.template.model import db
from typing import List, Optional, Dict, Any
from datetime import datetime

from models.user_image.model import UserImage


class UserImageService:
    """用户图片服务类"""

    @staticmethod
    def create_user_image(user_id: int, url: str,
                          ai_evaluate: Optional[str] = None,
                          evaluate_time: Optional[datetime] = None) -> UserImage:
        """
        创建用户图片记录

        Args:
            user_id: 用户ID
            url: 图片URL
            ai_evaluate: AI评估结果
            evaluate_time: 评估时间

        Returns:
            UserImage: 创建的图片对象
        """
        try:
            user_image = UserImage(
                user_id=user_id,
                url=url,
                ai_evaluate=ai_evaluate,
                evaluate_time=evaluate_time
            )

            db.session.add(user_image)
            db.session.commit()

            return user_image
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def get_user_image_by_id(image_id: int) -> Optional[UserImage]:
        """
        根据ID获取用户图片

        Args:
            image_id: 图片ID

        Returns:
            Optional[UserImage]: 图片对象或None
        """
        return UserImage.query.filter_by(id=image_id).first()

    @staticmethod
    def get_user_images_by_user_id(user_id: int,
                                   page: int = 1,
                                   per_page: int = 20) -> Dict[str, Any]:
        """
        根据用户ID获取用户的所有图片（分页）

        Args:
            user_id: 用户ID
            page: 页码
            per_page: 每页数量

        Returns:
            Dict: 包含图片列表和分页信息
        """
        query = UserImage.query.filter_by(user_id=user_id)

        pagination = query.order_by(desc(UserImage.created_time)).paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )

        return {
            'images': [image.to_dict() for image in pagination.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_prev': pagination.has_prev,
                'has_next': pagination.has_next
            }
        }

    @staticmethod
    def get_recent_user_images(user_id: int, limit: int = 10) -> List[Dict]:
        """
        获取用户最近的图片

        Args:
            user_id: 用户ID
            limit: 限制数量

        Returns:
            List[Dict]: 图片字典列表
        """
        images = UserImage.query.filter_by(user_id=user_id) \
            .order_by(desc(UserImage.created_time)) \
            .limit(limit) \
            .all()

        return [image.to_dict() for image in images]

    @staticmethod
    def update_ai_evaluate(image_id: int,
                           ai_evaluate: str,
                           evaluate_time: Optional[datetime] = None) -> Optional[UserImage]:
        """
        更新AI评估结果

        Args:
            image_id: 图片ID
            ai_evaluate: AI评估结果
            evaluate_time: 评估时间，如果为None则使用当前时间

        Returns:
            Optional[UserImage]: 更新后的图片对象或None
        """
        try:
            user_image = UserImage.query.filter_by(id=image_id).first()

            if not user_image:
                return None

            user_image.ai_evaluate = ai_evaluate
            user_image.evaluate_time = evaluate_time or datetime.now()

            db.session.commit()
            return user_image
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def update_image_url(image_id: int, new_url: str) -> Optional[UserImage]:
        """
        更新图片URL

        Args:
            image_id: 图片ID
            new_url: 新的图片URL

        Returns:
            Optional[UserImage]: 更新后的图片对象或None
        """
        try:
            user_image = UserImage.query.filter_by(id=image_id).first()

            if not user_image:
                return None

            user_image.url = new_url
            db.session.commit()

            return user_image
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def delete_user_image(image_id: int) -> bool:
        """
        删除用户图片

        Args:
            image_id: 图片ID

        Returns:
            bool: 是否删除成功
        """
        try:
            user_image = UserImage.query.filter_by(id=image_id).first()

            if not user_image:
                return False

            db.session.delete(user_image)
            db.session.commit()

            return True
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def get_images_without_evaluation(limit: int = 50) -> List[UserImage]:
        """
        获取尚未进行AI评估的图片

        Args:
            limit: 限制数量

        Returns:
            List[UserImage]: 未评估的图片列表
        """
        return UserImage.query.filter(
            and_(
                UserImage.ai_evaluate.is_(None),
                UserImage.evaluate_time.is_(None)
            )
        ).limit(limit).all()

    @staticmethod
    def get_evaluated_images_count(user_id: int) -> int:
        """
        获取用户已评估图片数量

        Args:
            user_id: 用户ID

        Returns:
            int: 已评估图片数量
        """
        return UserImage.query.filter_by(user_id=user_id) \
            .filter(UserImage.ai_evaluate.isnot(None)) \
            .count()

    @staticmethod
    def get_total_images_count(user_id: int) -> int:
        """
        获取用户总图片数量

        Args:
            user_id: 用户ID

        Returns:
            int: 总图片数量
        """
        return UserImage.query.filter_by(user_id=user_id).count()

    @staticmethod
    def batch_update_evaluation_results(evaluation_data: List[Dict[str, Any]]) -> bool:
        """
        批量更新AI评估结果

        Args:
            evaluation_data: 评估数据列表，每个元素包含image_id和ai_evaluate

        Returns:
            bool: 是否更新成功
        """
        try:
            for data in evaluation_data:
                image_id = data.get('image_id')
                ai_evaluate = data.get('ai_evaluate')

                if image_id and ai_evaluate:
                    user_image = UserImage.query.filter_by(id=image_id).first()
                    if user_image:
                        user_image.ai_evaluate = ai_evaluate
                        user_image.evaluate_time = datetime.now()

            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def search_user_images(user_id: int,
                           keyword: str = None,
                           start_date: datetime = None,
                           end_date: datetime = None) -> List[Dict]:
        """
        搜索用户图片

        Args:
            user_id: 用户ID
            keyword: 搜索关键词（在AI评估结果中搜索）
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            List[Dict]: 匹配的图片列表
        """
        query = UserImage.query.filter_by(user_id=user_id)

        if keyword:
            query = query.filter(UserImage.ai_evaluate.contains(keyword))

        if start_date:
            query = query.filter(UserImage.created_time >= start_date)

        if end_date:
            query = query.filter(UserImage.created_time <= end_date)

        images = query.order_by(desc(UserImage.created_time)).all()

        return [image.to_dict() for image in images]
