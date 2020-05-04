# -*- coding: utf-8 -*-
import shlex
import subprocess
import traceback
import socket

import click
import pickle
from multiprocessing.connection import Listener, Client
from threading import Thread
import os
import sys
import threading
import sqlite3
import time
import shutil
from time import strftime, localtime
import getpass
import signal
import copy
import distutils.dir_util

from .__init__ import __version__


# 处理远程调用
class RPCHandler:
    def __init__(self):
        self._functions = {}

    def register_function(self, func):
        self._functions[func.__name__] = func

    def handle_connection(self, connection):
        try:
            while True:
                # Receive a message
                func_name, args, kwargs = pickle.loads(connection.recv())
                # Run the RPC and send a response
                try:
                    r = self._functions[func_name](*args, **kwargs)
                    connection.send(pickle.dumps(r))
                except Exception as e:
                    connection.send(pickle.dumps(e))
        except EOFError:
            pass


# 客户端调用RPC
class RPCProxy:
    def __init__(self, connection):
        self._connection = connection

    def __getattr__(self, name):
        def do_rpc(*args, **kwargs):
            self._connection.send(pickle.dumps((name, args, kwargs)))
            result = pickle.loads(self._connection.recv())
            if isinstance(result, Exception):
                raise result
            return result

        return do_rpc


# 反射方法，用来根据函数名字来调用具体的函数
class SubTestClassFactory:
    def __init__(self):
        pass

    @staticmethod
    def get_test(p_module_name, p_class_name):
        obj_module = __import__(p_module_name)
        return getattr(obj_module, p_class_name)


# 处理回归测试
class FarmHandler(object):
    HomeDirectory = None
    conn = None
    lock = None

    # 初始化构造函数
    def __init__(self, ):
        self.lock = threading.RLock()

    # 设置FARM的工作目录
    def set_home(self, p_directory):
        self.HomeDirectory = p_directory

    # 连接配置数据库
    def connect_config_db(self):
        dir_config_db = os.path.join(self.HomeDirectory, 'db')
        file_config_db = os.path.join(dir_config_db, 'farm.db')
        if os.path.exists(file_config_db):
            # 连接数据库
            self.conn = sqlite3.connect(file_config_db)
            return
        else:
            raise Exception("Config DB [" + file_config_db + "] not exist!")

    # 断开数据库连接
    def disconnect_config_db(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    # 初始化配置数据库
    def init_config_db(self):
        # 清理之前的文件
        dir_config_db = os.path.join(self.HomeDirectory, 'db')
        file_config_db = os.path.join(dir_config_db, 'farm.db')
        if os.path.exists(file_config_db):
            os.remove(file_config_db)
        if not os.path.exists(dir_config_db):
            os.makedirs(dir_config_db)

        # 连接数据库
        self.conn = sqlite3.connect(file_config_db)

        # 开始创建数据库对象
        sql = 'CREATE TABLE FARM_CONFIG ' + \
              '(' + \
              '   CREATED_DATE    TEXT,' + \
              '   VERSION         TEXT' + \
              ')'
        self.conn.execute(sql)
        # 插入默认数据
        sql = "INSERT INTO FARM_CONFIG(CREATED_DATE, VERSION) VALUES(datetime('now'), '" + __version__ + "')"
        self.conn.execute(sql)

        sql = 'CREATE TABLE FARM_REGRESS ' + \
              '(' + \
              '   NAME            TEXT,' + \
              '   DESCRIPTION     TEXT,' + \
              '   MAIN_ENTRY      TEXT,' + \
              '   LIMIT_TIME      INTEGER,' + \
              '   REGRESS_TYPE    TEXT,' + \
              '   CREATED_DATE    TEXT' + \
              ')'
        self.conn.execute(sql)
        sql = 'CREATE UNIQUE INDEX IDX_FARM_REGRESS ON FARM_REGRESS(NAME)'
        self.conn.execute(sql)

        sql = 'CREATE TABLE FARM_SUITE ' + \
              '(' + \
              '   NAME            TEXT,' + \
              '   DESCRIPTION     TEXT,' + \
              '   CREATED_DATE    TEXT' + \
              ')'
        self.conn.execute(sql)
        sql = 'CREATE UNIQUE INDEX IDX_FARM_SUITE ON FARM_SUITE(NAME)'
        self.conn.execute(sql)

        sql = 'CREATE TABLE FARM_SUITE_REGRESS ' + \
              '(' + \
              '   SUITE_NAME      TEXT,' + \
              '   REGRESS_NAME    TEXT' + \
              ')'
        self.conn.execute(sql)
        sql = 'CREATE UNIQUE INDEX IDX_FARM_SUITE_REGRESS ON FARM_SUITE_REGRESS(SUITE_NAME)'
        self.conn.execute(sql)

        sql = 'CREATE TABLE FARM_LABEL ' + \
              '(' + \
              '   NAME            TEXT,' + \
              '   DESCRIPTION     TEXT,' + \
              '   PROPERTIES      TEXT,' + \
              '   CURRENT_USED    INTEGER,' + \
              '   LABEL_CAPACITY  INTEGER' + \
              ')'
        self.conn.execute(sql)
        sql = 'CREATE UNIQUE INDEX IDX_FARM_LABEL ON FARM_LABEL(NAME)'
        self.conn.execute(sql)

        '''
            STATUS:
                NEW          未操作
                WORKING      已经开始执行
                COMPLETED    执行成功完成
                TIMEOUT      进程执行超时
                ERROR        执行错误完成
        '''
        sql = 'CREATE TABLE FARM_JOBS ' + \
              '(' + \
              '   ID                     INTEGER,' + \
              '   TASK_ID                INTEGER,' + \
              '   SUITE_NAME                TEXT,' + \
              '   REGRESS_NAME              TEXT,' + \
              '   LABEL_NAME                TEXT,' + \
              '   STATUS                    TEXT,' + \
              '   SUBMITTED_DATE            TEXT,' + \
              '   STARTED_DATE              TEXT,' + \
              '   COMPLETED_DATE            TEXT,' + \
              '   WORKER_USER_NAME          TEXT,' + \
              '   WORKER_MACHINE_NAME       TEXT,' + \
              '   WORKER_OS_PID          INTEGER,' + \
              '   WORKER_WORK_DIRECTORY     TEXT,' + \
              '   WORKER_BACKUP_DIRECTORY   TEXT,' + \
              '   REGRESS_OPTIONS           TEXT,' + \
              '   NOTES                     TEXT' + \
              ')'
        self.conn.execute(sql)
        sql = 'CREATE UNIQUE INDEX IDX_FARM_JOBS ON FARM_JOBS(ID)'
        self.conn.execute(sql)
        sql = 'CREATE INDEX IDX_FARM_JOBS_REGRESS ON FARM_JOBS(REGRESS_NAME)'
        self.conn.execute(sql)
        sql = 'CREATE INDEX IDX_FARM_JOBS_LABEL ON FARM_JOBS(LABEL_NAME)'
        self.conn.execute(sql)

        sql = 'CREATE TABLE FARM_TASKS ' + \
              '(' + \
              '   ID                       INTEGER,' + \
              '   SUITE_OR_REGRESS_NAME       TEXT,' + \
              '   LABEL_NAME                  TEXT,' + \
              '   TOTAL_JOBS               INTEGER,' + \
              '   COMPLETED_JOBS           INTEGER,' + \
              '   FAILED_JOBS              INTEGER,' + \
              '   RUNNING_JOBS             INTEGER,' + \
              '   SUBMITTED_DATE              TEXT,' + \
              '   USER_NAME                   TEXT,' + \
              '   STATUS                      TEXT,' + \
              '   STARTED_DATE                TEXT,' + \
              '   COMPLETED_DATE              TEXT,' + \
              '   REGRESS_OPTIONS             TEXT' + \
              ')'
        self.conn.execute(sql)
        sql = 'CREATE UNIQUE INDEX IDX_FARM_TASKS ON FARM_TASKS(ID)'
        self.conn.execute(sql)

        # 提交数据修改
        self.conn.commit()

        print("Database init successful.")

    # 添加新的回归测试
    def add_regress(self,
                    p_regress_name,
                    p_regress_main_entry, p_regress_limit_time,
                    p_regress_type):
        try:

            # 连接数据库
            self.lock.acquire()
            self.connect_config_db()

            # 先判断一下是否之前有相关记录
            m_RowCount = None
            sql = "SELECT COUNT(*) FROM FARM_REGRESS WHERE NAME='" + p_regress_name + "'"
            cursor = self.conn.execute(sql)
            for row in cursor:
                m_RowCount = str(row[0])
                break
            cursor.close()
            if m_RowCount:
                if int(m_RowCount) != 0:
                    return {'Result': False, 'Message': 'Regress [' + p_regress_name + '] already existed. add failed'}

            # 插入新的记录
            sql = 'INSERT INTO FARM_REGRESS(NAME,MAIN_ENTRY,LIMIT_TIME,REGRESS_TYPE) VALUES(' + \
                  "'" + p_regress_name + "','" + p_regress_main_entry + "'," + \
                  str(p_regress_limit_time) + ",'" + p_regress_type + "')"
            self.conn.execute(sql)
            self.conn.commit()
        except Exception as e:
            return {'Result': False, 'Message': str(e)}
        finally:
            # 断开数据库连接
            self.disconnect_config_db()
            self.lock.release()

        # 返回结果
        return {'Result': True}

    # 列出当前所有的回归测试
    # def delete_regress(self, p_regress_name):

    # 增加一个资源
    def create_label(self, p_label_name, p_label_properties, p_label_capacity):
        try:
            # 连接数据库
            self.lock.acquire()
            self.connect_config_db()

            # 先判断一下是否之前有相关记录
            m_RowCount = None
            sql = "SELECT COUNT(*) FROM FARM_LABEL WHERE NAME='" + p_label_name + "'"
            cursor = self.conn.execute(sql)
            for row in cursor:
                m_RowCount = str(row[0])
                break
            cursor.close()
            if m_RowCount:
                if int(m_RowCount) != 0:
                    return {'Result': False, 'Message': 'Label [' + p_label_name + '] already existed. add failed'}

            # 插入新的记录
            sql = 'INSERT INTO FARM_LABEL(NAME,PROPERTIES,LABEL_CAPACITY,CURRENT_USED) VALUES(' + \
                  "'" + p_label_name + "','" + p_label_properties + "'," + str(p_label_capacity) + ",0)"
            self.conn.execute(sql)

            # 提交数据库事务
            self.conn.commit()

        except Exception as e:
            return {'Result': False, 'Message': str(e)}
        finally:
            # 断开数据库连接
            self.disconnect_config_db()
            self.lock.release()

        # 返回结果
        return {'Result': True}

    # 提交一个JOB
    def submit_job(self, p_label_name, p_regress_or_suite_name, p_user_name, p_regress_options):
        try:
            # 连接数据库
            self.lock.acquire()
            self.connect_config_db()

            # 记录到TASK中
            m_TaskID = None
            sql = "SELECT MAX(ID) FROM FARM_TASKS"
            cursor = self.conn.execute(sql)
            for row in cursor:
                m_TaskID = row[0]
                break
            cursor.close()
            if m_TaskID:
                m_TaskID = m_TaskID + 1
            else:
                m_TaskID = 1
            sql = 'INSERT INTO FARM_TASKS(' + \
                  "ID,SUITE_OR_REGRESS_NAME,LABEL_NAME,RUNNING_JOBS,FAILED_JOBS,TOTAL_JOBS,COMPLETED_JOBS," \
                  "SUBMITTED_DATE,USER_NAME, REGRESS_OPTIONS, STATUS) " + \
                  'VALUES(' + str(m_TaskID) + "," + \
                  "'" + p_regress_or_suite_name + "'," + \
                  "'" + p_label_name + "'," + \
                  "0,0,0,0,datetime('now')" + ",'" + p_user_name + "','" + str(p_regress_options) + "','NEW')"
            self.conn.execute(sql)

            # 查看提交的是否是一个测试套件
            b_isTestSuite = False
            m_nCountOfTasks = 0
            sql = "SELECT REGRESS_NAME FROM FARM_SUITE_REGRESS " + \
                  "WHERE SUITE_NAME = '" + p_regress_or_suite_name + "'"
            cursor_suite = self.conn.execute(sql)
            for row_suite in cursor_suite:
                b_isTestSuite = True
                # 依次将每一个测试放入到JOBS中
                m_Regress_Name = row_suite[0]

                # 找到最大的JOB记录
                m_JobID = None
                sql = "SELECT MAX(ID) FROM FARM_JOBS"
                cursor = self.conn.execute(sql)
                for row in cursor:
                    m_JobID = row[0]
                    break
                cursor.close()
                if m_JobID:
                    m_JobID = m_JobID + 1
                else:
                    m_JobID = 1

                # 插入新的记录
                sql = 'INSERT INTO FARM_JOBS(' + \
                      'ID, TASK_ID, SUITE_NAME, REGRESS_NAME,LABEL_NAME,REGRESS_OPTIONS,SUBMITTED_DATE,STATUS) " +' \
                      'VALUES(' + \
                      str(m_JobID) + "," + str(m_TaskID) + "," + \
                      "'" + p_regress_or_suite_name + "'," \
                      "'" + m_Regress_Name + "'," \
                      "'" + p_label_name + "'," \
                      "'" + p_regress_options + "'," \
                      "datetime('now')" + ",'NEW')"
                self.conn.execute(sql)

                m_nCountOfTasks = m_nCountOfTasks + 1
            cursor_suite.close()

            # 不是一个测试组件，就是一个单独的测试, Suite Name和Regress Name一样
            if not b_isTestSuite:
                # 找到最大的JOB记录
                m_JobID = None
                sql = "SELECT MAX(ID) FROM FARM_JOBS"
                cursor = self.conn.execute(sql)
                for row in cursor:
                    m_JobID = row[0]
                    break
                cursor.close()
                if m_JobID:
                    m_JobID = m_JobID + 1
                else:
                    m_JobID = 1

                # 插入新的JOB
                sql = "INSERT INTO FARM_JOBS(" + \
                      "ID, TASK_ID, SUITE_NAME, REGRESS_NAME,LABEL_NAME,REGRESS_OPTIONS,SUBMITTED_DATE,STATUS) " + \
                      'VALUES(' + \
                      str(m_JobID) + "," + str(m_TaskID) + "," + \
                      "'" + p_regress_or_suite_name + "'," \
                      "'" + p_regress_or_suite_name + "'," \
                      "'" + p_label_name + "'," \
                      "'" + p_regress_options + "'," \
                      "datetime('now')" + ",'NEW')"
                self.conn.execute(sql)

                m_nCountOfTasks = 1

            # 更新累计任务数量
            sql = 'UPDATE FARM_TASKS ' + \
                  "SET    TOTAL_JOBS = " + str(m_nCountOfTasks) + " " + \
                  "WHERE  ID = " + str(m_TaskID)
            self.conn.execute(sql)

            # 提交数据库事务
            self.conn.commit()

        except Exception as e:
            return {'Result': False, 'Message': str(e)}
        finally:
            # 断开数据库连接
            self.disconnect_config_db()
            self.lock.release()

        # 返回结果
        return {'Result': True, 'JobID': m_TaskID}

    # 列表所有的JOB
    def show_jobs(self, p_user_name):
        try:
            # 连接数据库
            self.lock.acquire()
            self.connect_config_db()

            # 列出所有的JOB
            m_Task_Details = []
            m_Task_Detail = {}
            sql = "SELECT ID,SUITE_OR_REGRESS_NAME,LABEL_NAME," + \
                  "       TOTAL_JOBS,RUNNING_JOBS,COMPLETED_JOBS,STATUS,SUBMITTED_DATE FROM FARM_TASKS " + \
                  "WHERE  USER_NAME = '" + p_user_name + "' " + \
                  "ORDER BY ID"
            cursor = self.conn.execute(sql)
            for row in cursor:
                m_Task_Detail['ID'] = str(row[0])
                m_Task_Detail['SUITE_OR_REGRESS_NAME'] = str(row[1])
                m_Task_Detail['LABEL_NAME'] = str(row[2])
                m_Task_Detail['TOTAL_JOBS'] = str(row[3])
                m_Task_Detail['RUNNING_JOBS'] = str(row[4])
                m_Task_Detail['COMPLETED_JOBS'] = str(row[5])
                m_Task_Detail['STATUS'] = str(row[6])
                m_Task_Detail['SUBMITTED_DATE'] = str(row[7])
                m_Task_Details.append(copy.copy(m_Task_Detail))
            cursor.close()

        except Exception as e:
            return {'Result': False, 'Message': str(e)}
        finally:
            # 断开数据库连接
            self.disconnect_config_db()
            self.lock.release()

        # 返回结果
        return {'Result': True, 'Details': m_Task_Details}

    # 获得可以运行的JOB
    def get_todo_job(self, p_worker_user_name, p_os_pid, p_machine_name, p_work_directory, p_backup_directory):
        try:
            # 连接数据库
            self.lock.acquire()
            self.connect_config_db()

            # 列出可以执行的JOB
            m_JobInfo = {'Result': False}
            sql = "SELECT R.MAIN_ENTRY, R.REGRESS_TYPE," + \
                  "       J.ID, J.REGRESS_NAME, J.LABEL_NAME, L.PROPERTIES," + \
                  "       R.LIMIT_TIME, J.TASK_ID, J.REGRESS_OPTIONS " + \
                  "FROM   FARM_LABEL L, FARM_JOBS J, FARM_REGRESS R " + \
                  "WHERE  L.NAME = J.LABEL_NAME AND R.NAME = J.REGRESS_NAME " + \
                  "AND    L.CURRENT_USED < L.LABEL_CAPACITY AND J.STATUS = 'NEW' " + \
                  "LIMIT 1"
            cursor = self.conn.execute(sql)
            for row in cursor:
                m_JobInfo['MAIN_ENTRY'] = str(row[0])
                m_JobInfo['REGRESS_TYPE'] = str(row[1])
                m_JobInfo['ID'] = str(row[2])
                m_JobInfo['REGRESS_NAME'] = str(row[3])
                m_JobInfo['LABEL_NAME'] = str(row[4])
                m_JobInfo['PROPERTIES'] = str(row[5])
                m_JobInfo['LIMIT_TIME'] = str(row[6])
                m_JobInfo['TASK_ID'] = str(row[7])
                m_JobInfo['REGRESS_OPTIONS'] = str(row[8])
                m_JobInfo['Result'] = True
                break
            cursor.close()

            if m_JobInfo['Result']:
                # 标记当前作业已经开始执行
                sql = 'UPDATE FARM_JOBS ' + \
                      "SET STARTED_DATE = datetime('now'), " + \
                      "    STATUS = 'WORKING' ," + \
                      "    WORKER_USER_NAME = '" + p_worker_user_name + "' ," + \
                      "    WORKER_OS_PID = '" + p_os_pid + "' ," + \
                      "    WORKER_MACHINE_NAME = '" + p_machine_name + "' ," + \
                      "    WORKER_WORK_DIRECTORY = '" + p_work_directory + "' ," + \
                      "    WORKER_BACKUP_DIRECTORY = '" + p_backup_directory + "' " + \
                      " WHERE ID = " + m_JobInfo['ID']
                self.conn.execute(sql)
                sql = 'SELECT RUNNING_JOBS FROM FARM_TASKS WHERE ID = ' + str(m_JobInfo['TASK_ID'])
                cursor = self.conn.execute(sql)
                m_Running_Jobs = 0
                for row in cursor:
                    m_Running_Jobs = str(row[0])
                    break
                cursor.close()
                if m_Running_Jobs == 0:
                    sql = 'UPDATE FARM_TASKS ' + \
                          "SET STARTED_DATE = datetime('now') " + \
                          "    RUNNING_JOBS = RUNNING_JOBS + 1 " + \
                          "    STARTED_DATE = datetime('now') " + \
                          "    STATUS = 'RUNNING' " + \
                          " WHERE ID = " + m_JobInfo['TASK_ID']
                else:
                    sql = 'UPDATE FARM_TASKS ' + \
                          "SET RUNNING_JOBS = RUNNING_JOBS + 1 " + \
                          " WHERE ID = " + m_JobInfo['TASK_ID']
                self.conn.execute(sql)

                # 提交数据库事务
                self.conn.commit()
            else:
                return {'Result': False, 'Message': 'No TASK TO DO ....'}
        except Exception as e:
            print('str(e):  ', str(e))
            print('repr(e):  ', repr(e))
            print('traceback.print_exc():\n%s' % traceback.print_exc())
            print('traceback.format_exc():\n%s' % traceback.format_exc())
            return {'Result': False, 'Message': str(e)}
        finally:
            # 断开数据库连接
            self.disconnect_config_db()
            self.lock.release()

        return m_JobInfo

    # 完成一个任务
    def finish_job(self, p_job_id, p_job_status, p_notes):
        try:
            # 连接数据库
            self.lock.acquire()
            self.connect_config_db()

            sql = "UPDATE FARM_JOBS " + \
                  "SET    STATUS = ' " + p_job_status + "', " + \
                  "       COMPLETED_DATE = datetime('now'), " + \
                  "       NOTES = '" + p_notes + "'" + \
                  "WHERE  ID = " + str(p_job_id)
            self.conn.execute(sql)

            sql = "UPDATE FARM_TASKS " + \
                  "SET    RUNNING_JOBS = RUNNING_JOBS - 1, " + \
                  "       COMPLETED_JOBS = COMPLETED_JOBS + 1 ," + \
                  "       COMPLETED_DATE = datetime('now') " + \
                  "WHERE  ID IN (SELECT TASK_ID FROM FARM_JOBS WHERE ID = " + str(p_job_id) + ")"
            self.conn.execute(sql)

            # 提交数据库事务
            self.conn.commit()

        except Exception as e:
            return {'Result': False, 'Message': str(e)}
        finally:
            # 断开数据库连接
            self.disconnect_config_db()
            self.lock.release()

        # 返回结果
        return {'Result': True}


# 启动一个RPC服务，远程Worker能够连接上来
def rpc_server(handler, address, authkey):
    sock = Listener(address, authkey=authkey)
    while True:
        client = sock.accept()
        t = Thread(target=handler.handle_connection, args=(client,))
        t.daemon = True
        t.start()


# 运行具体的测试程序
def run_test(p_test_main_file, p_test_main_class, p_sys_argv):
    SubTestClassFactory().get_test(p_test_main_file, p_test_main_class)().run(p_sys_argv)


# 运行RF测试程序
def run_robot_framework_test(
        p_test_main_entry,
        p_test_module_name,
        p_test_label_properties,
        p_sys_argv):
    m_robot_syslog = os.path.join(os.environ['T_WORK'], p_test_module_name + "_syslog.log")
    m_robot_outputdir = os.environ['T_WORK']
    m_repository_home = os.environ['T_SRCHOME']
    os.environ['ROBOT_OPTIONS'] = "--critical regression --suitestatlevel 3"
    os.environ['ROBOT_SYSLOG_FILE'] = m_robot_syslog
    Commands = "robot --loglevel DEBUG:INFO --outputdir " + m_robot_outputdir + " " + p_test_main_entry

    # 将p_test_label_properties中的信息变成环境变量
    m_robot_environs = shlex.shlex(p_test_label_properties)
    m_robot_environs.whitespace = ','
    m_robot_environs.quotes = "'"
    m_robot_environs.whitespace_split = True
    for m_robot_environ_str in list(m_robot_environs):
        m_nPos = m_robot_environ_str.find('=')
        if m_nPos != -1:
            m_robot_environ_key = m_robot_environ_str[0:m_nPos].strip()
            m_robot_environ_value = m_robot_environ_str[m_nPos+1:].strip()
        else:
            m_robot_environ_key = m_robot_environ_str
            m_robot_environ_value = "1"
        os.environ[m_robot_environ_key] = m_robot_environ_value
        print('label ENV [' + m_robot_environ_key + ']=[' + m_robot_environ_value + ']')

    # 将p_sys_argv中的信息变成环境变量
    m_robot_environs = shlex.shlex(p_sys_argv)
    m_robot_environs.whitespace = ','
    m_robot_environs.quotes = "'"
    m_robot_environs.whitespace_split = True
    for m_robot_environ_str in list(m_robot_environs):
        m_nPos = m_robot_environ_str.find('=')
        if m_nPos != -1:
            m_robot_environ_key = m_robot_environ_str[0:m_nPos].strip()
            m_robot_environ_value = m_robot_environ_str[m_nPos+1:].strip()
        else:
            m_robot_environ_key = m_robot_environ_str
            m_robot_environ_value = "1"
        os.environ[m_robot_environ_key] = m_robot_environ_value
        print('Options ENV [' + m_robot_environ_key + ']=[' + m_robot_environ_value + ']')

    # 启动RF程序
    print("Will run robot command [" + Commands + "]")
    if 'win32' in str(sys.platform).lower():
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags = subprocess.CREATE_NEW_CONSOLE | subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        p = subprocess.Popen(Commands,
                             startupinfo=startupinfo)
        p.communicate()
    else:
        p = subprocess.Popen(Commands,
                             shell=True)
        p.communicate()
    print("Finished command [" + Commands + "]")


# 定义中断信号的处理
def signal_handler(signum, frame):
    print('Got interrupt signal! ' + str(signum) + ":" + str(frame))
    sys.exit(1)


@click.command()
@click.option("-V", "--version", is_flag=True, help="Output farm's version.")
@click.option("--init", is_flag=True, help="init farm server.")
@click.option("--add_regress", is_flag=True, help="Add a new regress test.")
# @click.option("--list_regress", is_flag=True, help="list current regress tests")
# @click.option("--delete_regress", is_flag=True, help="delete regress.")
@click.option("--regress_name", type=str, help="Regress name.")
@click.option("--regress_main_entry", type=str, help="Regress main file.")
@click.option("--regress_limit_time", default=3600*1000, type=int, help="Regress limit time(S).")
@click.option("--regress_options", default='', type=str, help="Regress options.")
@click.option("--regress_type", default='RF', type=str, help="Regress type.")
@click.option("--create_label", is_flag=True, help="create a label resource")
@click.option("--label_name", type=str, help="label resource name")
@click.option("--label_properties", type=str, help="label resource properties")
@click.option("--label_capacity", default=100, type=int, help="label resource capacity")
@click.option("--submit", is_flag=True, help="Submit Job to Farm")
@click.option("--show_jobs", is_flag=True, help="Display all jobs")
@click.option("--start_server", is_flag=True, help="Start Farm Server")
@click.option("--port", default=15000, type=int, help="Server Port")
@click.option("--server", default='localhost', type=str, help="Server IP address")
@click.option("--start_worker", is_flag=True, help="Start Farm Worker")
def farm(
        version,
        init,
        add_regress,
        regress_name,
        regress_main_entry,
        regress_limit_time,
        regress_options,
        regress_type,
        create_label,
        label_name,
        label_properties,
        label_capacity,
        submit,
        start_server,
        server,
        port,
        start_worker,
        show_jobs
):
    # 打印版本信息
    if version:
        print("Version:", __version__)
        sys.exit(0)

    # 处理终端信号
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 初始化句柄
    m_FarmHandler = FarmHandler()

    # 如果要求初始化，则清空FARM_HOME/db下面的数据库
    if init:
        # 检查环境变量信息，如果不存在，则程序退出
        if "FARM_HOME" not in os.environ:
            print('Missed env [FARM_HOME].  Please set it and try again')
            sys.exit(1)
        else:
            m_FarmHandler.set_home(os.environ['FARM_HOME'])
        # 初始化数据库配置
        m_FarmHandler.init_config_db()
        sys.exit(0)

    # 新增一个回归测试
    if add_regress:
        if not (regress_name and regress_main_entry):
            # 用户输入的参数有误
            print('Missed necessary information.  Please set it and try again')
            print(
                "--add-regress --regress_name xxx " +
                "--regress_main_entry xxx --regress_limit_time")
            sys.exit(1)
        c = Client((server, port), authkey=b'welcome')
        proxy = RPCProxy(c)
        m_Result = proxy.add_regress(
            p_regress_name=regress_name,
            p_regress_main_entry=regress_main_entry,
            p_regress_limit_time=regress_limit_time,
            p_regress_type=regress_type
        )
        if m_Result['Result']:
            print('Add regresss successful.')
            sys.exit(0)
        else:
            print(m_Result['Message'])
            sys.exit(1)

    # 增加一个资源
    if create_label:
        if not (label_name and label_properties):
            # 用户输入的参数有误
            print('Missed necessary information.  Please set it and try again')
            print("--create_label --label_name xxx --label_properties xxx --label_capacity=100")
            sys.exit(1)
        c = Client((server, port), authkey=b'welcome')
        proxy = RPCProxy(c)
        m_Result = proxy.create_label(
            p_label_name=label_name,
            p_label_properties=label_properties,
            p_label_capacity=label_capacity)
        if m_Result['Result']:
            print('Add label successful.')
            sys.exit(0)
        else:
            print(m_Result['Message'])
            sys.exit(1)

    # 提交一个任务
    if submit:
        if not (label_name and regress_name):
            # 用户输入的参数有误
            print('Missed necessary information.  Please set it and try again')
            print("--submit --label_name xxx --regress_name xxx")
            sys.exit(1)

        c = Client((server, port), authkey=b'welcome')
        proxy = RPCProxy(c)
        m_Result = proxy.submit_job(
            p_label_name=label_name,
            p_regress_or_suite_name=regress_name,
            p_regress_options=regress_options,
            p_user_name=getpass.getuser())
        if m_Result['Result']:
            print('Job add successful. JobID = [' + str(m_Result['JobID']) + ']')
            sys.exit(0)
        else:
            print(m_Result['Message'])
            sys.exit(1)

    # 显示出当前所有的JOB
    if show_jobs:
        c = Client((server, port), authkey=b'welcome')
        proxy = RPCProxy(c)
        m_Result = proxy.show_jobs(p_user_name=getpass.getuser())
        if m_Result['Result']:
            print('%5s %15s %10s %10s %15s %10s %20s' %
                  ('ID',
                   'SUITE',
                   'LABEL',
                   'RUNNING',
                   'TOTAL',
                   'STATUS',
                   'SUBMITTED_DATE'))
            for result_detail in m_Result['Details']:
                print('%5s %15s %10s %10s %15s %10s %20s' %
                      (result_detail['ID'],
                       result_detail['SUITE_OR_REGRESS_NAME'],
                       result_detail['LABEL_NAME'],
                       result_detail['RUNNING_JOBS'],
                       result_detail['COMPLETED_JOBS'] + "/" + result_detail['TOTAL_JOBS'],
                       result_detail['STATUS'],
                       result_detail['SUBMITTED_DATE'])
                      )
            sys.exit(0)
        else:
            print(m_Result['Message'])
            sys.exit(1)

    # 启动Farm服务端
    if start_server:
        try:
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + "Starting ...")

            # 检查环境变量信息，如果不存在，则程序退出
            if "FARM_HOME" not in os.environ:
                print('Missed env [FARM_HOME].  Please set it and try again')
                sys.exit(1)
            else:
                print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'FARM HOME : ' + os.environ['FARM_HOME'])
                m_FarmHandler.set_home(os.environ['FARM_HOME'])

            # 连接配置数据库
            m_FarmHandler.connect_config_db()
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'Database connected.')

            # 注册RPC服务
            handler = RPCHandler()
            handler.register_function(m_FarmHandler.show_jobs)
            handler.register_function(m_FarmHandler.submit_job)
            handler.register_function(m_FarmHandler.create_label)
            handler.register_function(m_FarmHandler.add_regress)
            handler.register_function(m_FarmHandler.get_todo_job)
            handler.register_function(m_FarmHandler.finish_job)
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'RPC service registered.')

            # 启动服务
            worker_thread = threading.Thread(target=rpc_server, args=(handler, ('localhost', port), b'welcome'))
            worker_thread.setDaemon(True)
            worker_thread.start()
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'RPC service started.')
            while True:
                # 打印一下当前的状态吧
                time.sleep(20)

        except Exception as e:
            print('str(e):  ', str(e))
            print('repr(e):  ', repr(e))
            print('traceback.print_exc():\n%s' % traceback.print_exc())
            print('traceback.format_exc():\n%s' % traceback.format_exc())
        finally:
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + "Quit")

    # 启动客户端
    if start_worker:
        # 检查是否存在工作目录和备份目录, 源程序目录
        if "T_WORK" not in os.environ:
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'Missed T_WORK env, please set and retry.')
            sys.exit(1)
        else:
            m_work_directory = os.environ['T_WORK']
        if "T_BACKUP" not in os.environ:
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'Missed T_BACKUP env, please set and retry.')
            sys.exit(1)
        else:
            m_backup_directory = os.environ['T_BACKUP']
        if "T_SRCHOME" not in os.environ:
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'Missed T_SRCHOME env, please set and retry.')
            sys.exit(1)

        if not os.path.exists(m_work_directory):
            os.mkdir(m_work_directory)
        print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'Work directory：' + m_work_directory)
        if not os.path.exists(m_backup_directory):
            os.mkdir(m_backup_directory)
        print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'Backup directory：' + m_backup_directory)

        # 检查作业任务
        print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + "Checking TODO list .......")

        # 查看是否有需要完成的JOB
        c = Client((server, port), authkey=b'welcome')
        proxy = RPCProxy(c)
        m_Result = proxy.get_todo_job(
            p_worker_user_name=getpass.getuser(),
            p_os_pid=str(os.getpid()),
            p_machine_name=socket.gethostname(),
            p_work_directory=m_work_directory,
            p_backup_directory=m_backup_directory
        )
        c.close()

        # 如果没有需要完成的工作,就退出
        if not m_Result['Result']:
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + "Info:: " + str(m_Result['Message']))
            sys.exit(0)

        # 开始工作
        print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) +
              'Will do JOB [' + str(m_Result['ID']) + '] ....')

        # 获得当前程序工作路径
        m_current_directory = os.getcwd()
        if not os.path.exists(m_work_directory):
            os.mkdir(m_work_directory)
        print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'Work directory ：' + m_work_directory)
        os.chdir(m_work_directory)

        # 清空工作目录下所有内容
        print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) +
              'Cleaning all files under [' + m_work_directory + ']')
        fileList = list(os.listdir(m_work_directory))
        for file in fileList:
            if os.path.isfile(file):
                os.remove(file)
            else:
                shutil.rmtree(file)

        # 复制测试目录下所有文件到当前工作目录
        print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'Copying test ')
        m_TestPath = os.path.join(os.environ['T_SRCHOME'], str(m_Result['REGRESS_NAME']))
        if not os.path.exists(m_TestPath):
            c = Client((server, port), authkey=b'welcome')
            proxy = RPCProxy(c)
            m_Finished_Result = proxy.finish_job(
                p_job_id=m_Result['ID'],
                p_job_status='ERROR',
                p_notes='TestPath not exist. [' + str(m_TestPath) + "]"
            )
            c.close()
            if not m_Finished_Result['Result']:
                print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + "Error:: " + str(m_Finished_Result['Message']))
                sys.exit(1)
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'Aborted JOB ' + str(m_Result['ID']))
            sys.exit(0)
        else:
            distutils.dir_util.copy_tree(m_TestPath, m_work_directory)

        # 程序输出、错误定向到新的目录
        m_module_name = m_Result['REGRESS_NAME']
        print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'Will write output log to ：' + m_module_name + '.tlg')
        print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'Will write error log to ：' + m_module_name + '.err')
        sys.stdout = open(m_module_name + '.tlg', 'w')
        sys.stderr = open(m_module_name + '.err', 'w')

        # 运行Case
        m_test_option = m_Result['REGRESS_OPTIONS']
        if m_Result['REGRESS_TYPE'].upper() == 'RF':
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) +
                  'Started RF test ' + m_module_name)
            worker_thread = threading.Thread(
                target=run_robot_framework_test,
                args=(
                    str(m_Result['MAIN_ENTRY']),
                    m_module_name,
                    str(m_Result['PROPERTIES']),
                    m_test_option))
            worker_thread.setDaemon(True)
            worker_thread.start()
            worker_thread.join(int(m_Result['LIMIT_TIME']))
            if worker_thread.is_alive():
                print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) +
                      'Error:  MAX LIMIT TIME EXCEED: ' + str(m_Result['LIMIT_TIME']))
        else:
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) +
                  "Error:: UNKNOWN REGRESS_TYPE [" + m_Result['REGRESS_TYPE'] + "]")

        # 还原程序输出、错误输出的位置
        sys.stdout.close()
        sys.stderr.close()
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

        # 备份工作日志
        print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'backup log ' + str(m_Result['ID']))
        m_backup_directory = os.path.join(m_backup_directory, str(m_Result['ID']))
        if os.path.exists(m_backup_directory):
            os.chdir(m_backup_directory)
            fileList = list(os.listdir(m_backup_directory))
            for file in fileList:
                if os.path.isfile(file):
                    os.remove(file)
                else:
                    shutil.rmtree(file)
            os.chdir(m_current_directory)
            os.rmdir(m_backup_directory)
        shutil.copytree(os.environ.get('T_WORK'), m_backup_directory)

        # 还原工作路径
        os.chdir(m_current_directory)

        # 报告一下，已经完成工作
        c = Client((server, port), authkey=b'welcome')
        proxy = RPCProxy(c)
        m_Finished_Result = proxy.finish_job(
            p_job_id=m_Result['ID'],
            p_job_status='COMPLETED',
            p_notes="")
        c.close()
        if not m_Finished_Result['Result']:
            print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + "Error:: " + str(m_Finished_Result['Message']))
            sys.exit(1)
        print(strftime("%Y-%m-%d %H:%M:%S:  ", localtime()) + 'Completed JOB ' + str(m_Result['ID']))
        sys.exit(0)


if __name__ == "__main__":
    farm()
