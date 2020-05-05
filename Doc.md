# robotslacker-farm

robotslacker-farm 是一个回归测试管理工具，用来完成各种回归测试用例。 

## Install

Install robotslacker-farm

    pip install -U robotslacker-farm

## Usage
    # 程序体系架构
    farm分为服务端、客户端。
    服务端保留所有的配置数据，并不会具体来完成任何测试程序。我们称之为server.
    客户端用来完成所有的测试任务，我们称之为worker。 worker和server之间将通过RPC来完成通信。
    
    在一个系统中，我们需要有一个server， 多个worker。
    多个worker之间并没有区别，只是运行在不同的服务器上，或者不同的Docker中， 也可以随着业务需要不停扩展。
    
    # 程序用到的环境变量信息
    FARM_HOME    程序启动主目录，farm程序启动后会在这个目录下创建相应的日志目录、配置目录等
    T_WORK       程序工作主目录  worker实际运行目录，这个目录下包含Case可能生成的文件，运行结果等
    T_BACKUP     程序备份主目录  worker运行结果后，所有运行过程文件将会备份在这个目录下
    T_SRCHOME    测试程序目录，所有测试脚本、测试程序放置的目录
    
    # 测试程序的目录组织结构
    $T_SRCHOME\<test_module>\<main test file>

    # 启动farm的主程序
    farm --start_server
    
    # 初始化farm需要的数据库， 初始化完成后将会在FARM_HOME创建数据库文件，并记录日志信息
    farm --init
    
    # 测试模块和测试套件
    我们把一个module_name下的内容定义为一个测试regress。
    除了管理的需要，我们把多个regress合并起来，定义为一个suite.
    通过类似如下的命令可以添加和维护系统内定义的regress和suite.
    farm --add_regress --regress_name xxxx ...
        ...的参数包含：
        --regress_main_entry  回归测试程序主入口程序
        --regress_limit_time  该回归测试最长许可运行的时间，默认为3600
        --regress_type        回归测试的类型，如SHELL,RF,PYTHON等
    farm --add_regress_suite --suite_name xxxx
    farm --update_regress_suite --suite_name xxxx --regress_name xxxx --add
        
    # 资源标签和资源标签组
    我们把每个测试资源都标签化，定义为一个label。对于每一个label，都有他的各种属性，这些属性可能是数据库的地址等
    为了管理方便，对于同一类资源，我们又定义了一个资源标签组。其中包含多个资源信息。
    通过类似如下的命令可以添加和维护系统内定义的label以及label group.
    farm --create_label --label_name xxxx --label_properties XXX=YYY,ZZZ=TTT ...
        ... 包含的其他参数还有
        -- label_capacity 最多允许多少个并发测试在这个资源上
    farm --create_label_group --label_group_name xxxx
    farm --update_label_group --label_group_name xxxx --label_name xxxx --add
    
    # 提交一个测试
    farm --submit [regress name|suite name]  --to_label [label name|label_group_name] ...
        ... 包含的其他参数还有
        --regress_options 程序所需要的其他参数信息
    submit的任务是提交一个测试或者测试套件到指定的资源（或者资源组上）
    若提交的是一个测试套件，farm会分拆这个套件里头的测试程序，并发开始测试
    若提交的是一个测试资源组，在有多个测试任务的时候，farm会分别指派到不同的测试资源上
    若测试资源的容量已经达到限制，则farm会等待，直到有可用资源
    
    # 查看测试完成情况
    farm --show_jobs

    # 测试脚本的编写
    默认我们利用RF的方式来写测试脚本，通过提供RF扩展库的方式来增强RF的功能。

    以下是一个CASE的典型写法, 我们把这个文件名命名为e101.robot：
    *** Settings ***
    Library           SQLCliLibrary
    Library           CompareLibrary
    
    *** Test Cases ***
    E101Test
        set break with difference  TRUE
        Remove File                e101.log
        Execute SQL Script         e101.sql    e101.log
        Compare Files              e101.log    e101.ref
        
    为了完成测试工作，我们还需要准备另外两个文件，分别是e101.sql, e101.ref
    其中e101.sql是测试的SQL脚本，一个典型的SQL脚本例子如下：
    set echo on
    connect admin/123456
    select * from aaa;
    
    其中e101.ref是测试的SQL参考日志，一个典型的参考日志例子如下：
    SQL> connect admin/123456
    Database connected.
    SQL> select * from aaa;
    +----+----------+
    | ID | COL2     |
    +----+----------+
    | 1  | XYXYXYXY |
    | 1  | XYXYXYXY |
    +----+----------+
    2 rows selected.
    
    这里的e101.ref为测试人员在首次完成SQL脚本编写，并验证结果后，复制当前运行结果后生成。
    
    在准备好上述脚本后，我们把测试脚本放置到测试目录下，比如
    $SRC_HOME\test1
    随后，我们在farm中增加相关的配置
    farm --add_regress --regress_name test1 --regress_main_entry e101.robot
    farm --create_label --label_name 71 \
        --label_properties 
        "SQLCLI_CONNECTION_CLASS_NAME=com.xxxxxxx.jdbc.JdbcDriver,
        SQLCLI_CONNECTION_JAR_NAME=xxxxxxx-jdbc-0.0.0.jar,
        SQLCLI_CONNECTION_URL=jdbc:xxxxx:tcp://0.0.0.0:1234/ldb"
    其中，label可能是在Case添加之前就被添加好的
    
    随后，我们提交作业到farm
    farm --submit --label_name 71 --regress_name test1
    这个时候，farm会运行名字为test1目录下的e101.robot测试程序，在71这个资源上运行。
    
    在程序运行结束后，运行的结果将被备份在T_BACKUP目录中，供日后查看