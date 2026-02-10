# utils/file_handler.py
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app
import mimetypes


class FileHandler:
    """文件处理器"""

    @staticmethod
    def get_upload_dir(user_id: int) -> str:
        """获取用户上传目录"""
        base_dir = current_app.config.get('UPLOAD_FOLDER', 'static/uploads')
        user_dir = os.path.join(base_dir, str(user_id))

        # 创建目录
        os.makedirs(user_dir, exist_ok=True)

        # 按日期创建子目录
        date_str = datetime.now().strftime('%Y%m%d')
        date_dir = os.path.join(user_dir, date_str)
        os.makedirs(date_dir, exist_ok=True)

        return date_dir

    @staticmethod
    def save_uploaded_file(file, user_id: int) -> str:
        """保存上传的文件"""
        try:
            # 获取原始文件名和扩展名
            original_filename = file.filename

            # 安全文件名
            filename = secure_filename(original_filename)

            # 获取文件扩展名（修复：直接从原始文件名获取）
            if '.' in original_filename:
                file_ext = '.' + original_filename.rsplit('.', 1)[1].lower()
            else:
                # 如果没有扩展名，根据MIME类型推断
                mime_type = file.content_type
                if mime_type:
                    ext_map = {
                        'application/pdf': '.pdf',
                        'application/msword': '.doc',
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
                        'application/vnd.ms-powerpoint': '.ppt',
                        'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx'
                    }
                    file_ext = ext_map.get(mime_type, '')
                else:
                    file_ext = ''

            # 生成唯一文件名（确保有扩展名）
            if file_ext and not file_ext.startswith('.'):
                file_ext = '.' + file_ext

            # 如果文件名已经有扩展名，使用安全文件名的扩展名部分
            if '.' in filename:
                # 保留安全文件名的主干部分，使用检测到的扩展名
                name_without_ext = filename.rsplit('.', 1)[0]
                unique_filename = f"{uuid.uuid4().hex}_{name_without_ext}{file_ext}"
            else:
                # 文件名没有扩展名，直接添加
                unique_filename = f"{uuid.uuid4().hex}{file_ext}"

            # 保存文件
            upload_dir = FileHandler.get_upload_dir(user_id)
            file_path = os.path.join(upload_dir, unique_filename)

            file.save(file_path)

            current_app.logger.info(f"文件保存成功: {file_path}")
            return file_path

        except Exception as e:
            current_app.logger.error(f"保存文件失败: {str(e)}")
            raise

    @staticmethod
    def get_file_info(file_path: str) -> dict:
        """获取文件信息"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)

        return {
            'filename': filename,
            'file_path': file_path,
            'file_size': file_size,
            'mime_type': FileHandler.get_mime_type(filename)
        }

    @staticmethod
    def get_mime_type(filename: str) -> str:
        """获取文件的MIME类型"""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or 'application/octet-stream'

    @staticmethod
    def get_file_size(file_path: str) -> int:
        """获取文件大小"""
        return os.path.getsize(file_path)

    @staticmethod
    def delete_file(file_path: str) -> bool:
        """删除文件"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                current_app.logger.info(f"文件删除成功: {file_path}")
                return True
            return False
        except Exception as e:
            current_app.logger.error(f"删除文件失败: {str(e)}")
            return False