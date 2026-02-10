from flask import Blueprint, render_template, request, redirect, jsonify, session, g, current_app

from models.users.models import User, EmailUserRight, MobileUserRight
import re
import pandas as pd
from common.smtp import send
from conf.config import app_config
import hashlib
import random
import threading
from collections import Counter
from services.inner_service import InnerSrvice

inner = Blueprint('inner', __name__)
@inner.before_request
def before_request():
    if "user_id"  not in session:
        if request.method == "GET":
            js_code = """
            <script type="text/javascript">
                    alert('请重新登录！！！');
                    location.href="/"
            </script>
            """
            return js_code
        else:
            return jsonify({'msg': '请先登录', "code": 1}), 200
    if g.user_type!= 'mobile':
            return jsonify({'msg': '你没有权限', "code": 1}), 200

@inner.route('/list',methods=['GET','POST'])
def lists():
    record_type = str(g.type)
    real_name = request.values.get('real_name','').strip()
    status = request.values.get('status','').strip()
    pagination,items = User.get_inner_user_list(g.user_id, 'type_' + record_type, real_name, status)
    return render_template('user/inner/list.html', items=items, pagination=pagination, type=record_type, real_name=real_name, status=status)
@inner.route('/add',methods=['GET','POST'])
def add():
    if request.method == "GET":
        return render_template('user/inner/add.html',type=g.type)
    else:
        is_batch = request.values.get('is_batch', "0")
        mobile_user_right_record = MobileUserRight.get_one_right(g.admin_user_id, g.type)
        rs, code =  MobileUserRight.check_request_right(mobile_user_right_record, type="invite")
        if code < 0:
            return jsonify(rs), 200
        key_name = "type_" + str(g.type)
        data = request.json
        data['email'] = data['email'].strip()
        if is_batch=='1':
            data['password'] = str(random.randint(100000, 999999))
        if data['real_name']=='' or data['email']=='' or data['dept']=='' or data['position']=='' or data['password']=='':
            return jsonify({'msg': '请填写所有页面所有的内容', "code": -1}), 200
        pattern = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
        if not re.match(pattern, data['email']):
            return jsonify({'msg': '你的电子邮件格式错误', "code": -1}), 200
        item = User.get_register_email(data)
        admin_user_record = User.get_user_by_id(g.admin_user_id)
        if item is not None:
            if item.admin_user_id != g.user_id and item.status==1:
                return jsonify({'msg': '你注册的邮件地址已被注册', "code": -1}), 200
            elif  item.admin_user_id == g.user_id:
                item = EmailUserRight.get_one(item.user_id)
                if getattr(item,key_name)==1:
                    return jsonify({'msg': '你注册的邮件地址已被注册', "code": -1}), 200
                else:
                    EmailUserRight.update_right(key_name, item)
                    MobileUserRight.set_right(mobile_user_right_record, 'invited_user_num', (mobile_user_right_record.invited_user_num + 1))
                    MobileUserRight.inner_user_sms(mobile_user_right_record, g.admin_user_id, g.type)
                    content = f"尊敬的{data['real_name']}，您好！您所在的企业{admin_user_record.company_name}为您开通了{app_config['app_name']}的{User.servModule[int(g.type)]}使用权限，请使用账号：{data['email']}登录使用"
                    thread = threading.Thread(target=send, args=(data['email'], content, "邀请使用"))
                    thread.start()
                    return jsonify({'msg': '新增用户成功', "code": 1}), 200
        data['admin_user_id'] = g.admin_user_id
        user_id = User.add_inner_user(data)
        EmailUserRight.add_one({"user_id":user_id, "type_0":0, "type_1":0, "type_2":0, "admin_user_id":g.user_id}, key_name)
        InnerSrvice.send_mail(user_id,g.admin_user_id,g.user_id)
        MobileUserRight.set_right(mobile_user_right_record, 'invited_user_num', (mobile_user_right_record.invited_user_num + 1))
        MobileUserRight.inner_user_sms(mobile_user_right_record, g.admin_user_id, g.type)
        return jsonify({'msg': '您已成功邀请该用户，邀请信息已经通过Email发送给该用户。', "code": 1}), 200

# @inner.route('/add_defect_users',methods=['POST'])
# def add_defect_users():
#     datas = request.json
#     mobile_user_right_record = MobileUserRight.get_one_right(g.admin_user_id, g.type)
#     rs, code = MobileUserRight.check_request_right(mobile_user_right_record, type="invite",invite_num=len(datas))
#     if code < 0:
#         return jsonify(rs), 200
#     errors = InnerSrvice.check_datas(datas)
#     if len(errors)>0:
#         return jsonify({'msg':"\n".join(errors), "code": -1, 'user_ids': []}), 200
#     return  InnerSrvice.add_defect_users(mobile_user_right_record,datas)

@inner.route('/get_like_defect_user_list',methods=['GET','POST'])
def get_like_defect_user_list():
    data = request.json
    data['admin_user_id'] = g.admin_user_id
    users = InnerSrvice.get_like_defect_user_list(data)
    return jsonify(users), 200

@inner.route('/test',methods=['GET','POST'])
def test():
    return render_template('defect/p2.html')


@inner.route('/edit',methods=['GET','POST'])
def edit():
    user_id = request.values.get('user_id',0)
    item = User.get_email_user_by_id(user_id, "type_" + str(g.type))
    if item == None:
        return "错误用户id"
    if item.admin_user_id != int(g.admin_user_id) :
        return "没有权限修改"
    if request.method == "GET":
        return render_template('user/inner/edit.html',item=item,type=g.type)
    else:
        data = request.json
        data['email'] = data['email'].strip()
        data['user_id'] = user_id
        '''
        if data['email']!=item.email:
            pattern = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
            if not re.match(pattern, data['email']):
                return jsonify({'msg': '你的电子邮件格式错误', "code": -1}), 200
            itemCheck = User.getRegisterEmail(data)
            if itemCheck is not None:
                if itemCheck.admin_user_id != g.user_id and itemCheck.status == 1:
                    return jsonify({'msg': '你注册的邮件地址已被注册', "code": -1}), 200
                elif itemCheck.admin_user_id == g.user_id:
                    itemRigth = emailUserRight.getOne(item.user_id)
                    keyName = "type_" + str(g.type)
                    if getattr(itemRigth, keyName) == 1:
                        return jsonify({'msg': '你注册的邮件地址已被注册', "code": -1}), 200
        '''
        User.update_inner_user_profile(data, g.user_id)
        if item.status == 0:
            if data['password'] == "":
                password =  item.password
            else:
                password = data['password']
            randkey = hashlib.md5((password + data['email']).encode(encoding='UTF-8')).hexdigest()
            admin_user_record = User.get_user_by_id(g.admin_user_id)
            content = f"尊敬的{data['real_name']}，您好！您所在的企业{admin_user_record.company_name}为您开通了{app_config['app_name']}的{User.servModule[int(g.type)]}使用权限，账号：{data['email']}，初始密码为：：{password}，激活连接：http://{app_config['domain']}/user/verifyemail?randkey={randkey}&email={data['email']}&admin_user_id={g.user_id}"
            thread = threading.Thread(target=send, args=(data['email'], content, "邮箱验证"))
            thread.start()
        return jsonify({'msg': '修改成功',"code":1}),200

@inner.route('/delete',methods=['GET','POST'])
def delete():
    user_id = request.values.get('user_id', 0)
    record_type = request.values.get('type', 0)
    rs = EmailUserRight.del_one_email_user(g.admin_user_id, int(user_id), "type_" + str(g.type))
    if rs:
        User.delete_inner_user(int(user_id), g.admin_user_id)
    mobile_user_right_record = MobileUserRight.get_one_right(g.admin_user_id, record_type)
    MobileUserRight.set_right(mobile_user_right_record, 'invited_user_num', (mobile_user_right_record.invited_user_num - 1))
    return redirect("/user/inner/list?type=" + record_type)

@inner.route('/batch_delete',methods=['GET','POST'])
def batch_delete():
    data = request.json
    record_type = request.values.get('type', 0)
    mobile_user_right_record = MobileUserRight.get_one_right(g.admin_user_id, record_type)
    num = 0
    for iid in data['ids']:
        try:
            rs = EmailUserRight.del_one_email_user(g.admin_user_id, int(iid), "type_" + str(g.type))
            if rs:
                User.delete_inner_user(int(iid), g.admin_user_id)
            num = num+1
        except Exception as e:
            print(e)
            continue
    MobileUserRight.set_right(mobile_user_right_record, 'invited_user_num', (mobile_user_right_record.invited_user_num - num))
    return jsonify({'msg': '批量删除成功', "code": 1}), 200

@inner.route('/batchCheckExcel',methods=['GET','POST'])
def batch_check_excel():
    record_type = str(g.type)
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file:
        filename =  str(g.user_id)+file.filename
        file.save(f'./tmp/upload/{filename}')
        df = pd.read_excel(f'./tmp/upload/{filename}')
        df =  df.fillna('')
        if '真实姓名' not in df or '电子邮件' not in df or '部门' not in df or '职位' not in df:
            return jsonify({'msg': '请下载标准模板', "code": -1}), 200
        s = pd.Series(df['电子邮件'])
        length = len(df['电子邮件'])
        repeats = s[s.duplicated()].unique().tolist()
        items = User.batch_check_email(df['电子邮件'], "type_" + str(record_type))
        repeats_datas = InnerSrvice.get_repeat_datas(items, record_type,g.user_id)
        datas = []
        wrong_datas = []
        for i in range(0,length):
            data = {'real_name': str(df['真实姓名'][i]), 'email': str(df['电子邮件'][i]), 'dept': str(df['部门'][i]),'position': str(df['职位'][i])}
            datas, wrong_datas = InnerSrvice.check_data(data,repeats,repeats_datas,wrong_datas,datas)
        mobile_user_right_record = MobileUserRight.get_one_right(g.admin_user_id, int(record_type))
        rest_num = mobile_user_right_record.user_total_num - mobile_user_right_record.invited_user_num
        return jsonify({'msg': '校验完成', "code": 1,'data':datas,'wrong_data':wrong_datas,'rest_num':rest_num}), 200
    return jsonify({'error': 'No file part'}), 400


@inner.route('/batchCheckJson',methods=['GET','POST'])
def batch_check_json():
    record_type = str(g.type)
    data = request.json
    users = data['users']
    all_email = []
    for user in users:
        all_email.append(user['email'])
    counts = Counter(all_email)
    repeats = [item for item, c in counts.items() if c > 1]
    items = User.batch_check_email(all_email, "type_" + str(record_type))
    repeats_datas  = InnerSrvice.get_repeat_datas(items,record_type,g.user_id)
    wrong_datas = []
    datas = []
    for user in users:
        data = {'real_name': str(user['real_name']), 'email': str(user['email']), 'dept': str(user['dept']),'position': str(user['position'])}
        datas, wrong_datas = InnerSrvice.check_data(data, repeats, repeats_datas, wrong_datas, datas)
    mobile_user_right_record = MobileUserRight.get_one_right(g.admin_user_id, int(record_type))
    rest_num = mobile_user_right_record.user_total_num - mobile_user_right_record.invited_user_num
    return jsonify({'msg': '校验完成', "code": 1, 'data': datas, 'wrong_data': wrong_datas,'rest_num':rest_num}), 200

@inner.route('/send_invite_email/<int:user_id>',methods=['GET','POST'])
def send_invite_email(user_id):
    current_app.logger.debug(f'g.admin_user_id : ...........{g.admin_user_id}')
    return InnerSrvice.send_mail(user_id,g.admin_user_id,g.user_id)

def thread_batch_add(datas, admin_user_id, record_type, now_invited_user_num):
    '''
    暂时已废弃
    :param datas:
    :param admin_user_id:
    :param record_type:
    :param now_invited_user_num:
    :return:
    '''
    from app import app
    with app.app_context():
        key_name = "type_" + str(record_type)
        num = 0
        admin_user_record = User.get_user_by_id(admin_user_id)
        for data in datas:
            item = User.get_register_email(data)
            try:
                if item is not None:
                    if item.admin_user_id == admin_user_id:
                        record = EmailUserRight.get_one(item.user_id)
                        if getattr(record,key_name)==0:
                            EmailUserRight.update_right(key_name, record)
                            num = num + 1
                    else:
                        newPass = str(random.randint(100000, 999999))
                        data['password'] = newPass
                        data['admin_user_id'] = admin_user_id
                        randkey = hashlib.md5((data['password'] + data['email']).encode(encoding='UTF-8')).hexdigest()
                        user_id = User.add_inner_user(data)
                        EmailUserRight.add_one({"user_id": user_id, "type_0": 0, "type_1": 0, "admin_user_id": admin_user_id}, key_name)
                        num = num + 1
                        content = f"尊敬的{data['real_name']}，您好！您所在的企业{admin_user_record.company_name}为您开通了{app_config['app_name']}的{User.servModule[int(record_type)]}使用权限，账号：{data['email']}，初始密码为：：{newPass}，激活连接：http://{app_config['domain']}/user/verifyemail?randkey={randkey}&email={data['email']}&admin_user_id={admin_user_id}"
                        send(data['email'], content, "邮箱验证")
                else:
                    newPass = str(random.randint(100000, 999999))
                    data['password'] = newPass
                    data['admin_user_id'] = admin_user_id
                    randkey = hashlib.md5((data['password'] + data['email']).encode(encoding='UTF-8')).hexdigest()
                    content = f"尊敬的{data['real_name']}，您好！您所在的企业{admin_user_record.company_name}为您开通了{app_config['app_name']}的{User.servModule[int(record_type)]}使用权限，账号：{data['email']}，初始密码为：：{newPass}，激活连接：http://{app_config['domain']}/user/verifyemail?randkey={randkey}&email={data['email']}&admin_user_id={admin_user_id}"
                    user_id = User.add_inner_user(data)
                    EmailUserRight.add_one({"user_id": user_id, "type_0": 0, "type_1": 0, "admin_user_id":admin_user_id}, key_name)
                    num = num+1
                    send(data['email'], content, "邮箱验证")
            except Exception as e:
                print(e)
                continue
        #num = emailUserRight.getEmailUserNum(admin_user_id, "type_" + str(type))
        mobileUserRightRecord = MobileUserRight.get_one_right(admin_user_id, record_type)
        MobileUserRight.set_right(mobileUserRightRecord, 'invited_user_num', now_invited_user_num - (now_invited_user_num - num))
        MobileUserRight.inner_user_sms(mobileUserRightRecord, admin_user_id, record_type)
        # if mobileUserRightRecord.remind_invited_num >= (mobileUserRightRecord.user_total_num - mobileUserRightRecord.invited_user_num) and mobileUserRightRecord.sended_remind_invite_message == 0:
        #     record = User.getUserById(g.admin_user_id)
        #     aliSms.sendRemind(record.mobile, record.real_name, template=str(g.type), remind_type="余额不足")
        #     mobileUserRight.setRght(mobileUserRightRecord, 'sended_remind_invite_message', 1)
