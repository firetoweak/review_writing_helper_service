import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from conf.config import app_config


def send(email, body, subject, body_type='plain'):
    """
    发送电子邮件
    Args:
        email (str or list): 收件人邮箱地址，可以是单个字符串或字符串列表
        body (str): 邮件正文内容
        subject (str): 邮件主题
        body_type (str): 邮件正文类型，可选值为 'plain' 或 'html'
                         - 'plain': 纯文本格式（默认）
                         - 'html': HTML格式，支持富文本和样式
    Raises:
        Exception: 当邮件发送失败时抛出异常
    Example:
        # 发送纯文本邮件
        send('user@example.com', 'Hello World', '测试邮件')
        # 发送HTML邮件
        html_content = '<h1>标题</h1><p>内容</p>'
        send('user@example.com', html_content, 'HTML邮件', 'html')
    """
    sender = 'jihesmtp@imblade.com'
    From = formataddr((f'{app_config["app_name"]}', sender))  # 昵称(邮箱没有设置外发指定自定义昵称时有效)+发信地址(或代发)
    # Header("几何蓝军", 'utf-8')
    # 收件人
    receivers = [email]
    # 邮件主题
    # 创建邮件内容，根据body_type指定格式
    message = MIMEText(body, body_type, 'utf-8')
    print(f'body_type {body_type}')
    # 设置发件人和收件人
    message['From'] = From
    # Header("几何蓝军", 'utf-8')
    message['To'] = ','.join([email])
    # 设置邮件主题
    message['Subject'] = Header(subject, 'utf-8')

    smtp_server = 'smtp.qiye.aliyun.com'
    # SMTP服务器端口，默认是25，SSL通常是465，STARTTLS通常是587
    smtp_port = 587
    # 登录SMTP服务器需要的用户名和密码
    username = 'jihesmtp@imblade.com'
    password = '6626854Dm'
    # GDvUzHEGYWbREE4q
    try:
        # 创建SMTP连接对象
        server = smtplib.SMTP(smtp_server, smtp_port)
        # 如果需要加密连接，可以使用SMTP_SSL()，例如：server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        # server.starttls()  # 如果服务器支持STARTTLS，则启用它
        # 登录SMTP服务器
        server.login(username, password)
        # 发送邮件
        server.sendmail(sender, receivers, message.as_string())
    except Exception as e:
        raise Exception(f"邮件发送失败: {str(e)}")
    finally:
        server.quit()
