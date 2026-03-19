# -*- coding: utf-8 -*-
import os
from io import BytesIO
from sqlalchemy import create_engine, Column, Integer, String, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from docx import Document
import io
import sys
import base64
from docx.shared import Inches
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(parent_dir)
print(parent_dir)
# 创建基础类
Base = declarative_base()

# 确保 data 目录存在
data_dir = os.path.join(parent_dir, 'data')  # 获取当前工作目录，并指定 data 目录
if not os.path.exists(data_dir):
    os.makedirs(data_dir)  # 如果目录不存在，创建目录
from app.core.diagnosis import Diagnosis
from app.core.generate_report import FuelPumpDiagnosisReporter

# 指定数据库文件路径
DATABASE_URI = f'sqlite:///{os.path.join(data_dir, "your_database_file.db")}'  # 在 data 目录下创建数据库文件

# 设置数据库连接和会话
engine = create_engine(DATABASE_URI, echo=True)
Session = sessionmaker(bind=engine)
session = Session()

# 定义模型
class FaultDiagnosisTask(Base):
    __tablename__ = 'fault_diagnosis_tasks_2'
    id = Column(Integer, primary_key=True)
    task_id = Column(String(80), unique=True, nullable=False)
    type = Column(String(1), nullable=False)
    files = Column(String(10000), nullable=True)
    status = Column(String(80), nullable=False, default='Pending')  
    path = Column(String(1000), nullable=False)
    report_data = Column(LargeBinary, nullable=True)  # 存储 Word 文件的二进制数据

    def __init__(self, task_id, type, files, path, status='Pending',report_data=None):
        self.task_id = task_id
        self.type = type
        self.files = files
        self.status = status
        self.path = path
        self.report_data = report_data  # 添加这一行

def getOngingJob():
    task = session.query(FaultDiagnosisTask).filter_by(status='Pending').first()
    if task is None:
        return None
    taskData = {"task_id": task.task_id, "type": task.type, "files": task.files, "type": task.type,"path":task.path}
    return taskData

def getJobStatus(taskId):
    task = session.query(FaultDiagnosisTask).filter_by(task_id=taskId).first()
    return task.status

def hasOngoingJob():
    task = session.query(FaultDiagnosisTask).filter_by(status='Pending').first()
    return task is not None

def createJob(task_id, type, path, file_name):
    oriTask = session.query(FaultDiagnosisTask).filter_by(task_id=task_id).first()
    if oriTask:
        raise Exception(f"任务： {task_id} 已存在，请勿重复创建")
    task = FaultDiagnosisTask(task_id=task_id, type=type,files=file_name,path=path,status="Stop")
    session.add(task)
    session.commit()

def stopJob(task_id):
    task = session.query(FaultDiagnosisTask).filter_by(task_id=task_id).first()  # 查找第一条记录
    if task:
        task.status = 'Stop'  # 更新字段
        session.commit()  # 提交更改
    else:
        raise Exception(f"Task {task_id} not found")

def startJob(task_id):
    task = session.query(FaultDiagnosisTask).filter_by(task_id=task_id).first()  # 查找第一条记录
    if task:
        task.status = 'Pending'  # 更新字段
        session.commit()  # 提交更改
    else:
        raise Exception(f"Task {task_id} not found")

def deleteJob(task_id):
    task = session.query(FaultDiagnosisTask).filter_by(task_id=task_id).first()
    if task:
        session.delete(task)
        session.commit()
        return True  # 删除成功
    else:
        raise Exception(f"Task {task_id} not found")
    
def store_fault_diagnosis_report(task_id, type, file_name):
    try:
        dia = Diagnosis(file_name, "")
        new_alarms = dia.diagnosis_process() 
        task = session.query(FaultDiagnosisTask).filter_by(task_id=task_id).first()
        reporter = FuelPumpDiagnosisReporter()
        product_info = {
            'name': '试验台故障诊断报告',
            'date': '2023-05-15',
            'serial': 'FP-2023-0521',
            'diag_date': '2024-03-20',
            'operator': '张三',
            'system': '测试台-2号'
        }
        indicators = new_alarms["indicators"]
        diagnosis = new_alarms["diagnosis"]
        repair_advice = new_alarms["repair_advice"]
        report_base64 = reporter.generate_report(
            product_info=product_info,
            indicators=indicators,
            diagnosis=diagnosis,
            repair_advice=repair_advice
        )
        if task:
            # 存在任务，直接覆盖原有报告
            task.report_data = base64.b64decode(report_base64)
            # 更新文件列表和状态
            task.files = f"{task.files},{file_name}" if task.files else file_name
            task.status = 'Completed'
        else:
            # 不存在任务，创建新任务
            task = FaultDiagnosisTask(
                task_id=task_id,
                type=type,
                files=file_name,
                report_data=base64.b64decode(report_base64),
                status='Completed',
                path=''
            )
        
        session.add(task)
        session.commit()
        return task.id

    except Exception as e:
        session.rollback()
        raise Exception(f"存储故障诊断报告时出错: {str(e)}")

def retrieve_fault_diagnosis_report(task_id):
    try:
        task = session.query(FaultDiagnosisTask).filter_by(task_id=task_id).first()
        if not task or not task.report_data:
            return None
            
        return task.report_data  # 直接返回二进制DOCX数据

    except Exception as e:
        raise Exception(f"Error retrieving fault diagnosis report: {str(e)}")

def retrieve_fault_diagnosis_report(task_id):
    try:
        # 查找任务
        task = session.query(FaultDiagnosisTask).filter_by(task_id=task_id).first()
        if not task or not task.report_data:
            return None  # 如果任务不存在或者没有报告数据

        # 将报告数据转换为 BytesIO 对象
        report_data = task.report_data
        byte_io = io.BytesIO(report_data)  # 直接使用 BytesIO 包装二进制数据
        byte_io.seek(0)  # 重置指针到开头，以便后续读取
        return byte_io  # 返回 BytesIO 对象

    except Exception as e:
        raise Exception(f"Error retrieving fault diagnosis report: {str(e)}")

# 获取所有任务的诊断状态
def get_all_diagnosis_tasks():
    try:
        tasks = session.query(FaultDiagnosisTask).all()
        tasks_data = [{"task_id": task.task_id,  "status": task.status, "type":task.type, "files":task.files} for task in tasks]
        return tasks_data  # 返回所有任务的状态数据

    except Exception as e:
        raise Exception(f"Error retrieving all fault diagnosis tasks: {str(e)}")

def query_tasks(
    page: int = 1,          # 第几页，默认第1页
    page_size: int = 10,    # 每页条数，默认10条
    task_id: str = None,    # 用于模糊查询的ID
    status: str = None      # 用于精确查询的状态
):
    # 基础查询
    query = session.query(FaultDiagnosisTask)

    # 条件查询
    if task_id:
        # 模糊查询任务ID
        query = query.filter(FaultDiagnosisTask.id.like(f"%{task_id}%"))
    if status:
        # 精确查询状态
        query = query.filter(FaultDiagnosisTask.status == status)

    # 计算总条数
    total_count = query.count()

    # 计算总页数
    total_pages = (total_count + page_size - 1) // page_size

    # 分页查询
    tasks = query.offset((page - 1) * page_size).limit(page_size).all()
    tasks_data = [{"task_id": task.task_id,  "status": task.status, "type":task.type, "files":task.files, "path":task.path} for task in tasks]

    # 返回结果
    return {
        "tasks": tasks_data,          # 当前页的数据列表
        "total_count": total_count,  # 总条数
        "total_pages": total_pages,  # 总页数
        "current_page": page,    # 当前页码
        "page_size": page_size   # 每页条数
    }

# 更新任务的诊断状态
def update_task_status(task_id, status):
    try:
        # 查找任务并更新状态
        task = session.query(FaultDiagnosisTask).filter_by(task_id=task_id).first()
        if task:
            task.status = status
            session.commit()
            return True  # 更新成功
        return False  # 未找到该任务

    except Exception as e:
        session.rollback()
        raise Exception(f"Error updating task status: {str(e)}")

# 根据任务 ID 删除任务
def delete_task(task_id):
    try:
        task = session.query(FaultDiagnosisTask).filter_by(task_id=task_id).first()
        if task:
            session.delete(task)
            session.commit()
            return True  # 删除成功
        return False  # 未找到该任务

    except Exception as e:
        session.rollback()
        raise Exception(f"Error deleting task: {str(e)}")

# 创建数据库表
def create_tables():
    try:
        Base.metadata.create_all(engine)
    except Exception as e:
        raise Exception(f"Error creating database tables: {str(e)}")

def test_store_and_retrieve_report():
    try:
        # 1. 创建测试任务
        task_id = 'test_task_050'
        data_dir = os.path.join(parent_dir,"app" ,"test_data")
        print(f"数据目录检查: {'存在' if os.path.exists(data_dir) else '不存在'} - {data_dir}")
        
        # 确保测试数据目录存在
        if not os.path.exists(data_dir):
            raise Exception(f"测试数据目录不存在: {data_dir}")
    
        # 数据文件路径
        #data_file = os.path.join(data_dir, "250417134030滑轨磨损 _1.tdms")
        
        data_file = os.path.join(data_dir, "标准泵3.18.xlsx")
        if not os.path.exists(data_file):
            raise Exception(f"测试数据文件不存在: {data_file}")
            
        # 确保path参数有效
        path = data_dir  # 使用数据目录作为path
    
        # 2. 先创建任务
        createJob(task_id=task_id, type='T', path=path, file_name=data_file)
        
        # 3. 存储诊断报告
        print(f"正在存储测试报告，任务ID: {task_id}...")
        stored_task_id = store_fault_diagnosis_report(
            task_id=task_id,
            type='T',
            file_name=data_file
        )
        print(f"存储返回的任务ID: {stored_task_id}")
        
        # 4. 检索并验证报告
        print("正在检索测试报告...")
        report_data  = retrieve_fault_diagnosis_report(task_id)
        print(report_data.read())
        # 保存为Word文件
        output_path = os.path.join(data_dir, "diagnosis_report.docx"+task_id)
        with open(output_path, 'wb') as f:
            if isinstance(report_data, bytes):
                f.write(report_data)
            else:  # 如果是BytesIO对象
                f.write(report_data.getvalue())
        
        print(f"报告已保存到: {output_path}")

    
    except Exception as e:
        print(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
# 创建数据库表并执行测试
def run_test():
    # 创建数据库表
    create_tables()
    
    # 执行测试
    test_store_and_retrieve_report()

if __name__ == '__main__':
    run_test()
