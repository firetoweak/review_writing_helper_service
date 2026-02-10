from datetime import datetime
import re
from flask import jsonify, g, current_app
import random
from models.users.models import User, EmailUserRight, MobileUserRight
import threading
from common.smtp import send
from conf.config import app_config
import hashlib
from models.role.model import UserRole
from conf.db import db
from services.project_member_services import ProjectMemberService


class ErrorCode:
    SUCCESS = 200
    USER_NOT_EXIST = 1001
    USER_ACTIVE = 1002
    USER_ID_MISMATCH = 1003


class InnerSrvice:
    @staticmethod
    def get_repeat_datas(items, record_type, user_id):
        repeat_datas = []
        if items != None and len(items) > 0:
            for item in items:
                print(item.email_right)
                if item.admin_user_id != user_id:
                    repeat_datas.append(item.email)
                else:
                    keyName = "type_" + record_type
                    if getattr(item.email_right, keyName) == "1":
                        repeat_datas.append(item.email)
        return repeat_datas

    @staticmethod
    def check_data(data, repeats, repeats_datas, wrong_datas, datas):
        pattern = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
        wrong_mess = ""
        if not re.match(pattern, data['email']):
            wrong_mess = "邮件格式错误;"
        if data['real_name'].strip() == '' or data['email'].strip() == '' or data['dept'].strip() == '' or data[
            'position'].strip() == '':
            wrong_mess = "全部字段都不可以为空;"
        if data['email'] in repeats:
            wrong_mess = "在导入的数据哪里有重复邮件地址;"
        if data['email'] in repeats_datas:
            wrong_mess = "在导入的电子邮件在系统已经录入"
        if wrong_mess != "":
            data['wrongMess'] = wrong_mess
            wrong_datas.append(data)
        else:
            datas.append(data)
        return datas, wrong_datas

    @staticmethod
    def get_like_defect_user_list(data):
        users = User.get_like_defect_user_list(data)
        rs = []
        for user in users:
            rs.append({'email': user.email, 'real_name': user.real_name, 'user_id': user.user_id})
        return rs

    @staticmethod
    def check_datas(datas):
        errors = []
        pattern = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
        key_name = "type_3"
        for data in datas:
            if not re.match(pattern, data['email']):
                errors.append(f"{data['email']},你的电子邮件格式错误")
                continue
                return jsonify({'msg': '你的电子邮件格式错误', "code": -1}), 200
            if data['real_name'] == '':
                errors.append('真实姓名不可以为空')
                continue
                return jsonify({'msg': '真实姓名不可以为空', "code": -1}), 200
            data['password'] = str(random.randint(100000, 999999))
            data['admin_user_id'] = g.admin_user_id
            data['position'] = ""
            data['dept'] = ""
            item = User.get_register_email(data)
            if item is not None:
                if item.admin_user_id != g.admin_user_id and item.status == 1:
                    errors.append(f"{data['email']},邮件地址已被其他手机用户注册")
                    continue
                    # return jsonify({'msg': '你注册的邮件地址已被注册', "code": -1}), 200
        return errors

    @staticmethod
    def add_defect_users(mobile_user_right_record, datas):
        key_name = "type_0"
        user_ids = []
        try:
            for data in datas:
                data['password'] = str(random.randint(100000, 999999))
                data['admin_user_id'] = g.admin_user_id
                data['position'] = ""
                data['dept'] = ""
                item = User.get_register_email(data)
                admin_user_record = User.get_user_by_id(g.admin_user_id)
                if item is not None:
                    user_id = item.user_id
                    item = EmailUserRight.get_one(item.user_id)
                    if getattr(item, key_name) == 0:
                        EmailUserRight.update_right(key_name, item)
                        content = f"尊敬的{data['real_name']}，您好！您所在的企业{admin_user_record.company_name}为您开通了{app_config['app_name']}的{User.servModule[int(g.type)]}使用权限，请使用账号：{data['email']}登录使用"
                        thread = threading.Thread(target=send, args=(data['email'], content, "邀请使用"))
                        thread.start()
                else:
                    user_id = User.add_inner_user(data, no_commit="Yes")
                    EmailUserRight.add_one(
                        {"user_id": user_id, "type_0": 0, "type_1": 0, "type_2": 0, "admin_user_id": g.user_id},
                        key_name, no_commit="Yes")
                    MobileUserRight.set_right(mobile_user_right_record, 'invited_user_num',(mobile_user_right_record.invited_user_num + 1))
                    randkey = hashlib.md5((data['password'] + data['email']).encode(encoding='UTF-8')).hexdigest()
                    content = f"尊敬的{data['real_name']}，您好！您所在的企业{admin_user_record.company_name}为您开通了{app_config['app_name']}的{User.servModule[int(g.type)]}使用权限，账号：{data['email']}，初始密码为：：{data['password']}，激活连接：http://{app_config['domain']}/user/verifyemail?randkey={randkey}&email={data['email']}&admin_user_id={g.user_id}"
                    thread = threading.Thread(target=send, args=(data['email'], content, "邮箱验证"))
                    thread.start()
                user_ids.append(user_id)
                # role_id = data.get('role_id', 10)  # 默认为流程管理者
                # if 'version_id' in data:
                #     if data['version_id'] != "":
                #         project_member_list = ProjectMemberService.get_user_ids_by_role(project_id=None,version_id=data['version_id'],role_type="project_admin")
                #         if user_id not in project_member_list:
                # if UserRole.get_user_roles(user_id, role_id) is None:
                #     db.session.add(UserRole(user_id=user_id, role_id=role_id))
        except Exception as e:
            print(e)
            db.session.rollback()
            return {'msg': '新增用户失败', "code": -1, 'user_ids': user_ids}, -1
        db.session.commit()
        # MobileUserRight.inner_user_sms(mobile_user_right_record, g.admin_user_id, g.type)
        return {'msg': '新增用户成功', "code": 1, 'user_ids': user_ids}, 1

    @staticmethod
    def check_and_add_defect_users(datas):
        mobile_user_right_record = MobileUserRight.get_one_right(g.admin_user_id, g.type)
        rs, code = MobileUserRight.check_request_right(mobile_user_right_record, type="invite", invite_num=len(datas))
        if code < 0:
            return rs, code
        errors = InnerSrvice.check_datas(datas)
        if len(errors) > 0:
            return {'msg': "\n".join(errors), "code": -1, 'user_ids': []}, -1
        return InnerSrvice.add_defect_users(mobile_user_right_record, datas)

    @staticmethod
    def send_mail(user_id, admin_user_id, current_user_id):
        """
        给待激活的用户发送激活邮件
        """
        user = User.get_user_by_id(user_id)
        if user is None:
            return {"code": ErrorCode.USER_NOT_EXIST, "message": "用户不存在"}
        if user.status == 1:
            return {"code": ErrorCode.USER_ACTIVE, "message": "用户已激活，不用发邮件。请刷新页面查看。"}
        if user.admin_user_id != admin_user_id:
            return {"code": ErrorCode.USER_ID_MISMATCH, "message": "用户id错误，发送者与接收者不是同一个公司的人员。"}
        randkey = hashlib.md5((user.password + user.email).encode(encoding='UTF-8')).hexdigest()
        content = f"尊敬的{user.real_name}，您好！您所在的企业{user.company_name}为您开通了{app_config['app_name']}的{User.servModule[int(g.type)]}使用权限，账号：{user.email}，初始密码为：{user.password}，激活账号请点击：<a href='http://{app_config['domain']}/user/verifyemail?randkey={randkey}&email={user.email}&admin_user_id={g.user_id}' target='_blank'>激活</a>（点击无效请直接拷贝地址:【http://{app_config['domain']}/user/verifyemail?randkey={randkey}&email={user.email}&admin_user_id={g.user_id}】到浏览器地址栏）"
        now = datetime.now()
        thread = threading.Thread(target=send, args=(user.email, content, f'邮箱验证-{now.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]}',"html"))
        thread.start()
        import sys
        print(f"发送邀请邮件：{user.email},by_id:{current_user_id}", file=sys.stdout)
        return {"code": ErrorCode.SUCCESS, "message": "邮件发送成功", "data": []}

    @staticmethod
    def send_mail_for_defect(send_to_user_id, admin_user_id, current_user_id, content, title):
        """
        给缺陷电子流用户发送跟催邮件
        """
        current_app.logger.debug(f'send_mail_for_defect, admin_user_id:  {admin_user_id}')
        user = User.get_user_by_id(send_to_user_id)
        if user is None:
            return {"code": ErrorCode.USER_NOT_EXIST, "message": "用户不存在"}
        if user.status != 1:  # 用户未激活，先发送激活邮件，再发送跟催邮件
            InnerSrvice.send_mail(send_to_user_id, admin_user_id, current_user_id)
            current_app.logger.debug("用户未激活，已经发邮件邀请激活")
        if user.admin_user_id == 0:
            user.admin_user_id = user.user_id

        if user.admin_user_id != admin_user_id:
            current_app.logger.debug(f'user.admin_user_id: {user.admin_user_id}')
            return {"code": ErrorCode.USER_ID_MISMATCH,
                    "message": f"用户id错误，发送者{current_user_id}与接收者{send_to_user_id}不是同一个公司的人员。"}

        # 在title后面添加时间戳
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        title_with_timestamp = f"{title} - {timestamp}"

        thread = threading.Thread(target=send, args=(user.email, content, title_with_timestamp, 'html'))  # 支持富文本发送
        thread.start()
        current_app.logger.debug(f"发送缺陷电子流邮件：{user.email}, by_id:{current_user_id}")
        return {"code": ErrorCode.SUCCESS, "message": "邮件发送成功", "data": []}
