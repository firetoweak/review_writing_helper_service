from configparser import ConfigParser
import os
config = ConfigParser()
# 获取当前工作目录的绝对路径
currentDirectory =  "./conf"
config.read(currentDirectory+'/config.ini',encoding='utf-8')

#config_name = os.getenv('FLASK_CONFIG', 'development')
config_name = 'development'
local_file = '/var/.env'
try:
    with open(local_file, mode="rb") as file:
        config_name = file.read().strip().decode()
except Exception as e:
    config_name = 'development'
app_config = dict(config[config_name])