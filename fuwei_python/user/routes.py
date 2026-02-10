import json
import time
from flask import Blueprint, render_template, request, redirect, jsonify,session, g
from models.users.models import User, MobileUserRight
import re
import random
from common.smtp import send
import hashlib
import requests
from common.aliSms import aliSms
from conf.scheduler import scheduler
from conf.config import app_config
from models.queue.model import Smsqueue

user = Blueprint('user', __name__)


@user.route('/login', methods=['GET','POST'])
def login():
    if request.method == "GET":
        return render_template('user/login.html')
    else:
        data = request.json
        pattern = r'^1\d{10}$'
        pattern2 = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
        if re.match(pattern, data['mobile'].strip()):
            item = User.get_mobile_login_user(data)
            if item==None:
                return jsonify({'msg': '账号密码错误', "code": -1}), 200
        elif re.match(pattern2, data['mobile'].strip()):
            item = User.get_emai_login_user(data)
            if item==None:
                return jsonify({'msg': '账号密码错误', "code": -1}), 200
            else:
                if item.status ==0:
                    return jsonify({'msg': '请先去你的邮箱认证', "code": -1}), 200
        else:
            return jsonify({'msg': '请按要求填写账号密码', "code": -1}), 200
        session['user_id'] = item.user_id
        if item.mobile!="":
            session['user_name'] = item.mobile
            session['user_type'] = "mobile"
            session['admin_user_id'] = item.user_id
            session['company_name'] = item.company_name
        else:
            adminUser = User.get_user_by_id(item.admin_user_id)
            session['user_name'] = item.email
            session['user_type'] = "email"
            session['admin_user_id'] = item.admin_user_id
            session['company_name'] = adminUser.company_name
        session['randkey'] = hashlib.md5((str(session['user_id'])+session['user_name'] + session['user_type'] + str(session['admin_user_id'])+session['company_name']).encode(encoding='UTF-8')).hexdigest()
        session['sense'] = item.sense
        session['position'] = item.position
        session['dept'] = item.dept
        session['employees_num'] = item.employees_num
        session['real_name'] = item.real_name
        return jsonify({'msg': '登录成功', "code": 1}), 200
@user.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('admin_user_id', None)
    session.pop('user_name', None)
    session.pop('user_type', None)
    session.pop('company_name', None)

    session.pop('randkey', None)
    session.pop('sense', None)
    session.pop('position', None)
    session.pop('dept', None)
    session.pop('employees_num', None)
    session.pop('real_name', None)


    return redirect("/")

@user.route('/register', methods=['GET','POST'])
def register():
    if request.method == "GET":
        code = str(getCode())
        return render_template('user/register.html',code=code)
    else:
        data = request.json
        pattern = r'^1\d{10}$'
        if not re.match(pattern, data['mobile']):
            return jsonify({'msg': '请输入正确的手机号码', "code": -1}), 200
        if len(data['password'])<6:
            return jsonify({'msg': '密码至少6位', "code": -1}), 200
        if data['password'] != data['password2']:
            return jsonify({'msg': '两次输入密码不一致', "code": -1}), 200
        if "mobileCode" in session:
            if session['mobileCode']['create_time']>(time.time()-310):
                if session['mobileCode']['code']!=data['mobileCode']:
                    return jsonify({'msg': '手机验证码错误', "code": -1}), 200
            else:
                return jsonify({'msg': '手机验证码过期', "code": -1}), 200
        else:
            return jsonify({'msg': '请先发送图形验证码获取手机验证码', "code": -1}), 200
        item = User.check_register_user(data)
        user_id = 0
        if item is not None:
            if item.status == 1:
                return jsonify({'msg': '你注册的手机号码已被注册', "code": -1}), 200
            else:
                user_id = item.user_id
        session.pop('mobileCode', None)
        token = hashlib.md5((data['password'] + data['mobile'] + str(time.time())).encode(encoding='UTF-8')).hexdigest()
        data['token'] = token
        user_id = User.add_one(data, user_id)
        session['reg_user_id'] = user_id
        return jsonify({'msg': '请继续录入企业信息',"code":1}),200

@user.route('/record_company', methods=['GET','POST'])
def recordCompany():
    if "reg_user_id" not in session:
        return jsonify({'msg': '请先注册手机号', "code": -1}), 200
    if request.method == "GET":
        return render_template('user/recordCompany.html',allEmployeesNum=User.allEmployeesNum,allSense=User.allSense,allPosition=User.allPosition)
    else:
        data = request.json
        if data['company_name'] =="":
            return jsonify({'msg': '请填写公司名称', "code": -1}), 200
        if data['real_name'] =="":
            return jsonify({'msg': '请填写真实姓名', "code": -1}), 200
        if data['employees_num'] not in User.allEmployeesNum:
            return jsonify({'msg': '请选择正确的员工人数', "code": -1}), 200
        if data['sense'] not in User.allSense:
            return jsonify({'msg': '请选择正确的场景', "code": -1}), 200
        if data['position'] not in User.allPosition:
            return jsonify({'msg': '请选择正确的职位', "code": -1}), 200
        User.update_company_admin_profile(int(session['reg_user_id']), data)
        MobileUserRight.add_one({"user_id":session['reg_user_id'], "type":0})
        MobileUserRight.add_one({"user_id":session['reg_user_id'], "type":1})
        MobileUserRight.add_one({"user_id":session['reg_user_id'], "type":2})
        session.pop('reg_user_id', None)
        session.pop('user_id', None)
        session.pop('admin_user_id', None)
        session.pop('user_name', None)
        session.pop('user_type', None)
        session.pop('company_name', None)
        return jsonify({'msg': '企业信息录入成功',"code":1}),200

@user.route('/search_company')
def searchCompany():
    keyword = request.values.get('keyword',"")
    if keyword == "":
        return []
    try:
        url = 'https://pingcode.com/api/typhon/common/company/search?keyword='+keyword
        rs = requests.get(url)
        dic = json.loads(rs.text)
        values = dic['data']['value']
        names = []
        for v in values:
            names.append(v['company_name'])
        return names
    except Exception as e:
        return []

@user.route('/verifyemail', methods=['GET','POST'])
def verifyEmail():
    randkey = request.values.get('randkey',"")
    admin_user_id = int(request.values.get('admin_user_id',0))
    email = request.values.get('email',"")
    item = User.get_user_by_email(admin_user_id, email)
    if item.status!=0:
        return ''
    if hashlib.md5((item.password+email).encode(encoding='UTF-8')).hexdigest()==randkey:
        User.update_status(item.user_id, 1)
        js_code = """
        <script type="text/javascript">
                alert('验证通过，你现在可以登录了！');
                location.href="/"
        </script>
        """
        return js_code
    else:
        return ''

@user.route('/get_code',methods=['GET'])
def getCode():
    chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    charsLen = len(chars)
    s = ''
    nums = []
    for i in range(0,4):
        randNum = random.randint(0,(charsLen-1))
        s = s + str(chars[randNum])
        nums.append(randNum)
    session['verifyCode'] =  s
    return nums

@user.route('/send_mobile_code',methods=['GET','POST'])
def sendMobileCode():
    data = request.json
    verifyCode = data['verifyCode']
    mobile = data['mobile']
    pattern = r'^1\d{10}$'
    if not re.match(pattern, mobile):
        return jsonify({'msg': '请输入正确的手机号码', "code": -1}), 200
    if verifyCode == '':
        return jsonify({'msg': '图形验证码不能为空', "code": -1}), 200
    if verifyCode.upper()==session['verifyCode'].upper():
        session.pop('verifyCode', None)
        code = str(random.randint(1000,9999))
        session['mobileCode']= {"code":code,"create_time":time.time()}
        aliSms.sendNum(mobile,code)
        session.pop('verifyCode', None)
        return jsonify({'msg': '请查看手机短信接收验证码', "code": 1}), 200
    else:
        return jsonify({'msg': '验证码错误', "code": -1}), 200

@user.route('/send_change_mobile_code',methods=['GET','POST'])
def sendChangeMobileCode():
    data = request.json
    mobile = data['mobile']
    pattern = r'^1\d{10}$'
    if not re.match(pattern, mobile):
        return jsonify({'msg': '请输入正确的手机号码', "code": -1}), 200
    code = str(random.randint(1000, 9999))
    session['changeMobileCode'] = {"code": code, "create_time": time.time()}
    aliSms.sendNum(mobile, code,template='changeMobile')
    return jsonify({'msg': '请查看手机短信接收验证码', "code": 1}), 200

@user.route('/change_mobile',methods=['GET','POST'])
def changeUserMobile():
    data = request.json
    pattern = r'^1\d{10}$'
    if not re.match(pattern, data['mobile']):
        return jsonify({'msg': '请输入正确的手机号码', "code": -1}), 200
    if "changeMobileCode" in session:
        if session['changeMobileCode']['create_time'] > (time.time() - 310):
            if session['changeMobileCode']['code'] != data['mobileCode']:
                return jsonify({'msg': '手机验证码错误', "code": -1}), 200
        else:
            return jsonify({'msg': '手机验证码过期', "code": -1}), 200
    else:
        return jsonify({'msg': '请先获取修改手机号的验证码', "code": -1}), 200
    item = User.check_register_user(data)
    user_id = 0
    if item != None:
        if item.status == 1:
            return jsonify({'msg': '你要更改的手机号码已被注册', "code": -1}), 200
        else:
            user_id = item.user_id
    session.pop('changeMobileCode', None)
    data['user_id'] = g.user_id
    User.change_mobile(data, user_id)
    session['user_name'] = data['mobile']
    logout()
    return jsonify({'msg': '修改手机号成功,请用新的手机号重新登录，系统将自动退出登录', "code": 1}), 200


@user.route('/index')
def index():
    env = app_config['env']
    s0 = MobileUserRight.get_user_type_right(g.user_type, g.user_id, g.admin_user_id, 0)
    s1 = MobileUserRight.get_user_type_right(g.user_type, g.user_id, g.admin_user_id, 1)
    s2 = MobileUserRight.get_user_type_right(g.user_type, g.user_id, g.admin_user_id, 2)
    return render_template('user/index.html',s1=s1,s0=s0,s2=s2,env=env)

@user.route('/profile', methods=['GET','POST'])
def profile():
    if request.method == "GET":
        item = User.get_user_by_id(g.user_id)
        return render_template('user/profile.html',item=item,allEmployeesNum=User.allEmployeesNum,allSense=User.allSense,allPosition=User.allPosition,dept=User.dept,user_type=g.user_type)
    else:
        data = request.json
        if data['password']!="" and data['confirm_password']!="":
            if data['password']!= data['confirm_password']:
                return jsonify({'msg': '两次密码输入不一致', "code": 1}), 200
            if len(data['password'])<6:
                return jsonify({'msg': '密码至少六位', "code": 1}), 200
            User.update_pass(g.user_id, data['password'])
        if g.user_type =="mobile":
            if data['company_name'] =="":
                return jsonify({'msg': '请填写公司名称', "code": -1}), 200
            if data['real_name'] =="":
                return jsonify({'msg': '请填写真实姓名', "code": -1}), 200
            if data['employees_num'] not in User.allEmployeesNum:
                return jsonify({'msg': '请选择正确的员工人数', "code": -1}), 200
            if data['sense'] not in User.allSense:
                return jsonify({'msg': '请选择正确的场景', "code": -1}), 200
            if data['position'] not in User.allPosition:
                return jsonify({'msg': '请选择正确的职位', "code": -1}), 200
            User.update_company_admin_profile(g.user_id, data)
            session['company_name'] = data['company_name']
            session['sense'] = data['sense']
            session['position'] = data['position']
            session['employees_num'] = data['employees_num']
            session['real_name'] = data['real_name']
        else:
            if data['position'] =="":
                return jsonify({'msg': '请填写职位', "code": -1}), 200
            if data['dept'] =="":
                return jsonify({'msg': '请填写部门', "code": -1}), 200
            data['user_id'] = g.user_id
            User.update_inner_user_profile(data, g.admin_user_id, 1)
            session['dept'] = data['dept']
            session['position'] = data['position']
        session['randkey'] = hashlib.md5((str(session['user_id']) + session['user_name'] + session['user_type'] + str(session['admin_user_id']) + session['company_name']).encode(encoding='UTF-8')).hexdigest()
        return jsonify({'msg': '修改成功', "code": 1}), 200
@user.route('/password', methods=['GET','POST'])
def password():
    if request.method == "GET":
        return render_template('user/password.html')
    else:
        data = request.json
        if data['password']!= data['confirm_password']:
            return jsonify({'msg': '两次密码输入不一致', "code": 1}), 200
        if len(data['password'])<6:
            return jsonify({'msg': '密码至少六位', "code": 1}), 200
        User.update_pass(g.user_id, data['password'])
        return jsonify({'msg': '修改成功', "code": 1}), 200
@user.route('/forget', methods=['GET','POST'])
def forget():
    if request.method == "GET":
        return render_template('user/forget.html')
    else:
        data = request.json
        data['mobile'] = data['user_name'].strip()
        data['email'] = data['user_name'].strip()
        if data['mobile']=="" and data['email'] =="":
            return jsonify({'msg': '你填写正确的邮件地址或手机号码', "code": -1}), 200
        item = User.get_register_email(data)
        item2 = User.check_register_user(data)
        if item==None and item2==None:
            return jsonify({'msg': '你填写正确的邮件地址或手机号码', "code": -1}), 200
        newPass = str(random.randint(100000,999999))
        if item!=None:
            try:
                body = f"您的新密码是：{newPass}"
                send(data['email'],body,"忘记密码")
                User.update_pass(item.user_id, newPass)
            except:
                return jsonify({'msg': '发送邮件失败，请联系管理员', "code": -1}), 200
            return jsonify({'msg': '邮件已发送', "code": 1}), 200
        if item2!=None:
            try:
                aliSms.sendNum(data['mobile'],newPass,'forget')
                User.update_pass(item2.user_id, newPass)
            except:
                return jsonify({'msg': '短信发送失败请稍后再请求', "code": -1}), 200
            return jsonify({'msg': '新密码已发送你手机，请查收', "code": 1}), 200

@user.route('/set_remind', methods=['GET','POST'])
def setRemind():
    data = request.json
    data['user_id'] = g.user_id
    data['admin_user_id'] = g.admin_user_id
    MobileUserRight.set_remind_by_user_id(data)
    return jsonify({'msg': '修改成功', "code": 1}), 200

#@scheduler.task('interval', id='do_job_1', seconds=24*3600)
@user.route('/test2', methods=['GET', 'POST'])
def smsDate():
    from app import app
    with app.app_context():
        records = User.get_all_mobile_user()
        for record in records:
            rights = MobileUserRight.get_rights(record.user_id)
            for right in rights:
                if right.to_date== None or right.remind_date == None or right.sended_remind_date_message==1:
                    continue
                if  (time.mktime(time.strptime(str(right.remind_date), "%Y-%m-%d %H:%M:%S"))-time.time())<0:
                    e1 = 0
                    e2 = 0
                    rs1 = aliSms.sendRemind(record.mobile, record.real_name, template=str(right.type), remind_type="日期已到")
                    try:
                        if rs1.body.code == 'OK':
                            right.set_right(right, "sended_remind_date_message", 1)
                    except:
                        e1 = 1
                    rs2 = aliSms.sendAdminRemind(name=record.real_name, serve_type=str(right.type), remind_type="日期已到")
                    try:
                        if rs2.body.code == 'OK':
                            print('ok')
                    except:
                        e2 = 1
                    if e1 == 1 or e2 == 1:
                        data = {}
                        data['admin_user_id'] = record.user_id
                        data['type'] = right.type
                        data['module'] = "toDate"
                        data['e1'] = e1
                        data['e2'] = e2
                        Smsqueue.add_one(data)

        return ""

@scheduler.task('interval', id='do_job_2', seconds=360)
#@user.route('/test1', methods=['GET', 'POST'])
def repeateSend():
    from app import app
    with app.app_context():
        items = Smsqueue.get_all()
        for item in items:
            timestamp = time.mktime(time.strptime(str(item.create_time), "%Y-%m-%d %H:%M:%S"))
            if (timestamp+300)>time.time():
                continue
            mobileUserRightRecord = MobileUserRight.get_one_right(item.admin_user_id, item.type)
            record = User.get_user_by_id(item.admin_user_id)
            e1 = 0
            e2 = 0
            if item.e1 == 1:
                if item.module=='aiVal':
                    if mobileUserRightRecord.remind_request_num >= (mobileUserRightRecord.request_num - mobileUserRightRecord.requested_num) and mobileUserRightRecord.sended_remind_request_message == 0:
                        rs1 = aliSms.sendRemind(record.mobile, record.real_name, template=str(item.type), remind_type="余额不足")
                        try:
                            if rs1.body.code=='OK':
                                print('ok')
                                MobileUserRight.set_right(mobileUserRightRecord, 'sended_remind_request_message', 1)
                        except:
                            e1 =1
                elif item.module=='innerUser':
                    if  mobileUserRightRecord.remind_invited_num >= (mobileUserRightRecord.user_total_num - mobileUserRightRecord.invited_user_num) and mobileUserRightRecord.sended_remind_invite_message == 0:
                        rs1 = aliSms.sendRemind(record.mobile, record.real_name, template=str(item.type), remind_type="余额不足")
                        try:
                            if rs1.body.code == 'OK':
                                print('ok')
                                MobileUserRight.set_right(mobileUserRightRecord, 'sended_remind_invite_message', 1)
                        except:
                            e1 =1
                elif item.module=='toDate':
                    if  (time.mktime(time.strptime(str(mobileUserRightRecord.to_date), "%Y-%m-%d %H:%M:%S"))-time.time())<=mobileUserRightRecord.remind_to_date*24*3600 and mobileUserRightRecord.sended_remind_date_message==0:
                        rs1 = aliSms.sendRemind(record.mobile, record.real_name, template=str(item.type), remind_type="日期已到")
                        try:
                            if rs1.body.code == 'OK':
                                print('ok')
                                MobileUserRight.set_right(mobileUserRightRecord, 'sended_remind_date_message', 1)
                        except:
                            e1 =1
            if item.e2==1:
                if item.module == 'aiVal' or item.module=='innerUser':
                    rs2 = aliSms.sendAdminRemind(name=record.real_name, serve_type=str(item.type), remind_type="余额不足")
                else:
                    rs2 = aliSms.sendAdminRemind(name=record.real_name, serve_type=str(item.type), remind_type="日期已到")
                try:
                    if rs2.body.code == 'OK':
                        print('ok')
                except:
                    e2 = 1
            Smsqueue.set_queue(item, e1, e2)



@user.route('/get_token', methods=['GET', 'POST'])
def getToken():
    type = int(request.values.get('type', 0))
    if request.method == "GET":
        item = User.get_user_by_id(g.user_id)
        domain = app_config['domain']
        if type == 0:
            type_content = "产品缺陷管理"
        elif type == 1 :
            type_content = "产品需求管理"
        elif type ==2 :
            type_content = "立项管理"
        return render_template('user/openApi.html', type=type, token=item.token, domain=domain,type_content=type_content)
    else:
        item = User.get_user_by_id(g.user_id)
        token = hashlib.md5((item.password + item.mobile + str(time.time())).encode(encoding='UTF-8')).hexdigest()
        User.update_token(item, token)
        return jsonify({'msg': '修改成功', "code": 1}), 200