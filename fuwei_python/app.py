from flask import Flask, session, render_template, request, g
from flask_migrate import Migrate
from conf.db import db
from data_initializer import DataInitializer
from filters import register_filters
from routes.defect_level_routes import defect_level_bp
from routes.defect_message_routes import defect_message_bp
from routes.defect_routes import defect_bp
from routes.global_settings_routes import global_settings_bp
from routes.product_line_routes import product_line_bp
from routes.project_document_routes import project_document_bp
from routes.project_member_routes import project_member_bp
from routes.tech_group_routes import tech_group_bp
from routes.template_routes import template_bp
from user.routes import user
from user.inner import inner
from user.api import api
from user.aiVal import aiVal
from user.lxAiVal import lxAiVal
from admin.routes import admin
from conf.config import app_config
from conf.scheduler import scheduler
from flask_session import Session
import hashlib
from common.aliSms import aliSms
import sys
from flask_caching import Cache
from conf.logger_config import setup_module_logger

sys.dont_write_bytecode = True
app = Flask(__name__, static_url_path='/static', static_folder='static', template_folder='templates')
migrate = Migrate(app, db)  # 工厂函数中的配置，用于数据库表的创建及迁移
# 注册自定义过滤器
register_filters(app)
app.config['CACHE_TYPE'] = 'SimpleCache'  # 或 'RedisCache' / 'MemcachedCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 1800
cache = Cache()
cache.init_app(app)
app.register_blueprint(user, url_prefix='/user')
app.register_blueprint(inner, url_prefix='/user/inner')
app.register_blueprint(admin, url_prefix='/admin')
app.register_blueprint(api, url_prefix='/user/api')
app.register_blueprint(aiVal, url_prefix='/user/aiVal')
app.register_blueprint(lxAiVal, url_prefix='/user/lxAiVal')
app.register_blueprint(defect_level_bp, url_prefix='/defect_level')
app.register_blueprint(template_bp, url_prefix='/template')
app.register_blueprint(product_line_bp, url_prefix='/product_line')
app.register_blueprint(tech_group_bp, url_prefix='/tech_group')
app.register_blueprint(defect_bp, url_prefix='/defect')
app.register_blueprint(global_settings_bp, url_prefix='/global_settings')
app.register_blueprint(project_member_bp, url_prefix='/project_member')
app.register_blueprint(defect_message_bp, url_prefix='/defect_message')
app.register_blueprint(project_document_bp, url_prefix='/project_document')

from models.users.models import User

dbUri = f'mysql+pymysql://{app_config["mysql_user"]}:{app_config["mysql_password"]}@{app_config["mysql_host"]}:{int(app_config["mysql_port"])}/{app_config["database"]}?charset=utf8mb4'
app.config['SESSION_TYPE'] = 'filesystem'  # session类型为redis
app.config['SESSION_FILE_DIR'] = '/tmp/'  # session类型为redis
app.config['SESSION_FILE_THRESHOLD'] = 1000  # 存储session的个数如果大于这个值时，就要开始进行删除了
app.config['SESSION_FILE_MODE'] = 755  # 文件权限类型

app.config['SESSION_PERMANENT'] = True  # 如果设置为True，则关闭浏览器session就失效。
app.config['SESSION_USE_SIGNER'] = False  # 是否对发送到浏览器上session的cookie值进行加密
app.config['SESSION_KEY_PREFIX'] = 'session:'  # 保存到session中的值的前缀
app.config['SQLALCHEMY_DATABASE_URI'] = dbUri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = False  # 在配置中添加
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 50,
    'max_overflow': 360,
    'pool_timeout': 300,
    'pool_recycle': 1800,
}
db.init_app(app)  # 延迟初始化
app.secret_key = 'your_super_secret_key_here'
app.permanent_session_lifetime = 60 * 60 * 24 * 7  # 会话有效期7天
Session(app)


@app.before_request
def global_before_request():
    try:
        g.type = int(request.values.get('type', "0"))
        defect_it_process_urls = ['/user/', '/global_settings', '/project_member','/defect','/defect_message','/template','/product_line/','/tech_group/', '/project_document/']
        if g.type not in [0, 1, 2]:
            if  any(request.path.startswith(prefix) for prefix in defect_it_process_urls):
                g.type = 0
                g.type_content = "产品缺陷跟踪系统(DTS)"
                g.type_list_url = '/defect'
        elif g.type == 0:
            g.type_content = "产品缺陷管理"
            g.type_list_url = '/user/aiVal/list'
        elif g.type == 1:
            g.type_content = "产品需求管理"
            g.type_list_url = '/user/aiVal/list'
        elif g.type == 2:
            g.type_content = "产品立项管理"
            g.type_list_url = '/user/lxAiVal/list'
        if any(request.path.startswith(prefix) for prefix in defect_it_process_urls) and not request.path.startswith('/user/api'):
            if request.path not in ["/user/test2", "/user/test1", "/user/login", "/user/register", "/user/forget",
                                    "/user/verifyemail", "/user/record_company", "/user/search_company",
                                    "/user/get_code", "/user/send_mobile_code"]:
                if 'user_id' in session:
                    if session['randkey'] == hashlib.md5((str(session['user_id']) + session['user_name'] + session[
                        'user_type'] + str(session['admin_user_id']) + session['company_name']).encode(
                        encoding='UTF-8')).hexdigest():
                        g.user_id = session['user_id']
                        g.user_name = session['user_name']
                        g.admin_user_id = session['admin_user_id']
                        g.user_type = session['user_type']
                        g.company_name = session['company_name']

                        g.sense = session['sense']
                        g.position = session['position']
                        g.dept = session['dept']
                        g.employees_num = session['employees_num']

                        g.allEmployeesNum = User.allEmployeesNum
                        g.allSense = User.allSense
                        g.allPosition = User.allPosition
                        g.real_name = session['real_name']
                    else:
                        js_code = """
                        <script type="text/javascript">
                                alert('登录状态异常，请重新登录');
                                location.href="/"
                        </script>
                        """
                        aliSms.sendAdminException(session['user_name'])
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

                        return js_code
                else:
                    js_code = """
                    <script type="text/javascript">
                            alert('请重新登录！！');
                            location.href="/"
                    </script>
                    """
                    return js_code
    except:
        print(request.path)


@app.route("/", methods=['GET', 'POST'])
def welcome():
    from user.routes import getCode
    code = str(getCode())
    return render_template('user/welcome.html', welcomePage=1, code=code, allEmployeesNum=User.allEmployeesNum,
                           allSense=User.allSense, allPosition=User.allPosition)


@app.route("/open_api", methods=['GET', 'POST'])
def openApi():
    domain = app_config['domain']
    return render_template('user/openApi.html', type=str(g.type), domain=domain, welcomePage=1)


@app.route('/favicon.ico', methods=['GET', 'POST'])
@app.route('/.well-known/appspecific/com.chrome.devtools.json', methods=['GET', 'POST'])
def favicon():
    return ''

@app.context_processor
def inject_global_functions():
    from common.global_template_functions import get_menu_role,get_role_select_session,get_url_path,get_right_style,get_all_version_project,get_defects_num
    return dict(
        get_menu_role=get_menu_role,
        get_role_select_session = get_role_select_session,
        get_url_path = get_url_path,
        get_right_style = get_right_style,
        get_all_version_project = get_all_version_project,
        get_defects_num = get_defects_num
    )

def init_data():
    """初始化数据"""
    setup_module_logger(app)
    # 创建数据初始化器实例
    initializer = DataInitializer()
    with app.app_context():
        initializer.init_roles()
        initializer.init_template_types()
        initializer.init_defect_stage_types()


if __name__ == '__main__':
    # 初始化数据
    init_data()
    print(app_config["port"])
    # with app.app_context():
    # 可以解决两个表互为外键的情况
    #     db.create_all()
    if not scheduler.running:
        scheduler.init_app(app)
        scheduler.start()
    app.run(host='0.0.0.0', debug=True, port=app_config["port"])
