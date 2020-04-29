# robotslacker-farm

robotslacker-farm 是一个回归测试管理工具，用来完成各种回归测试用例。 

## Install

Install robotslacker-farm

    pip install -U robotslacker-farm

## Usage

    # 启动farm的主程序
    farm --start_server
    
    # 初始化farm需要的数据库
    # farm并不需要数据库配置，所有的数据配置在farm自带的sqlite文件中
    setenv FARM_HOME [your work directory]
    farm --init
    # 初始化完成后将会在FARM_HOME创建数据库文件，并记录日志信息
    
    # 创建一个回归测试
    farm --add_regress --regress_name xxxx ...
    ...的参数包含：
    --regress_directory   回归测试程序所在的路径
    --regress_main_entry  回归测试程序主入口程序
    --regress_limit_time  该回归测试最长许可运行的时间
    --regress_type        回归测试的类型，如SHELL,RF,PYTHON等
    
    # 删除一个回归测试
    farm --delete_regress --regress_name xxxx

    # 显示当前所有的测试
    farm --list_regress
    
    # 创建一个回归测试套件
    farm --add_regress_suite --suite_name xxxx
    
    # 添加一个测试到回归测试套件中
    farm --update_regress_suite --suite_name xxxx --regress_name xxxx --add
    
    # 删除一个测试从回归测试套件中
    farm --update_regress_suite --suite_name xxxx --regress_name xxxx --del
    
    # 创建一个测试资源
    farm --create_label --label_name xxxx --label_properties XXX=YYY:ZZZ=TTT ...
    其中label_properties中的信息将被拆分成环境变量信息到传递给具体的测试程序
    ... 包含的其他参数还有
    -- label_capacity 最多允许多少个并发测试在这个资源上
    
    # 创建测试资源组
    farm --create_label_group --label_group_name xxxx
    
    # 添加一个测试资源到测试资源组中
    farm --update_label_group --label_group_name xxxx --label_name xxxx --add
    
    # 删除一个测试资源从测试资源组中
    farm --update_label_group --label_group_name xxxx --label_name xxxx --add
    
    # 提交一个测试
    farm --submit [regress name|suite name]  --to_label [label name|label_group_name] ...
    ... 包含的其他参数还有
    --regress_options 程序所需要的其他参数信息

    # 查看测试完成情况
    farm --show_jobs
    
    # 启动工作进程
    farm --start_worker
    这个可以启动多份，每一份对应一个工作进程，用来执行具体的测试任务
    
    #
