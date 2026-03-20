# -*- coding: utf-8 -*-
import os
import io
import sys
import base64
from sqlalchemy import create_engine, Column, Integer, String, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(parent_dir)
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
    report_data = Column(LargeBinary, nullable=True)   # Word 文件二进制
    report_json = Column(String(50000), nullable=True) # 结构化诊断结果 JSON

    def __init__(self, task_id, type, files, path, status='Pending', report_data=None, report_json=None):
        self.task_id = task_id
        self.type = type
        self.files = files
        self.status = status
        self.path = path
        self.report_data = report_data
        self.report_json = report_json

# 仿真数据模型表
class SimulationDataModel(Base):
    __tablename__ = 'simulation_data_models'
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(String(2000), nullable=True)
    file_path = Column(String(1000), nullable=True)
    status = Column(String(80), nullable=False, default='Pending')
    result_data = Column(LargeBinary, nullable=True)
    created_at = Column(String(50), nullable=False)

    def __init__(self, name, description='', file_path='', status='Pending', result_data=None):
        self.name = name
        self.description = description
        self.file_path = file_path
        self.status = status
        self.result_data = result_data
        self.created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'file_path': self.file_path,
            'status': self.status,
            'created_at': self.created_at
        }


def get_data_models(page=1, page_size=10, name=None, status=None):
    query = session.query(SimulationDataModel)
    if name:
        query = query.filter(SimulationDataModel.name.like(f'%{name}%'))
    if status:
        query = query.filter(SimulationDataModel.status == status)
    total_count = query.count()
    total_pages = (total_count + page_size - 1) // page_size
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        'items': [m.to_dict() for m in items],
        'total_count': total_count,
        'total_pages': total_pages,
        'current_page': page,
        'page_size': page_size
    }


def get_data_model(model_id):
    model = session.query(SimulationDataModel).filter_by(id=model_id).first()
    if not model:
        return None
    return model.to_dict()


def create_data_model(name, description='', file_path=''):
    model = SimulationDataModel(name=name, description=description, file_path=file_path)
    session.add(model)
    session.commit()
    return model.to_dict()


def update_data_model(model_id, name=None, description=None, file_path=None):
    model = session.query(SimulationDataModel).filter_by(id=model_id).first()
    if not model:
        return None
    if name is not None:
        model.name = name
    if description is not None:
        model.description = description
    if file_path is not None:
        model.file_path = file_path
    session.commit()
    return model.to_dict()


def delete_data_model(model_id):
    model = session.query(SimulationDataModel).filter_by(id=model_id).first()
    if not model:
        return False
    session.delete(model)
    session.commit()
    return True


def set_data_model_status(model_id, status, result_data=None):
    model = session.query(SimulationDataModel).filter_by(id=model_id).first()
    if not model:
        return None
    model.status = status
    if result_data is not None:
        model.result_data = result_data
    session.commit()
    return model.to_dict()


def get_data_model_result(model_id):
    model = session.query(SimulationDataModel).filter_by(id=model_id).first()
    if not model or not model.result_data:
        return None
    return io.BytesIO(model.result_data)


def getOngingJob():
    task = session.query(FaultDiagnosisTask).filter_by(status='Pending').first()
    if task is None:
        return None
    taskData = {"task_id": task.task_id, "type": task.type, "files": task.files, "path": task.path}
    return taskData

def getJobStatus(taskId):
    task = session.query(FaultDiagnosisTask).filter_by(task_id=taskId).first()
    return task.status

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
    
def store_fault_diagnosis_report(task_id, type, file_name=None, x1=None, x2=None):
    try:
        dia = Diagnosis(file_name, "")
        new_alarms = dia.diagnosis_process(x1=x1, x2=x2)
        task = session.query(FaultDiagnosisTask).filter_by(task_id=task_id).first()
        reporter = FuelPumpDiagnosisReporter()
        product_info = {
            'name': '试验台故障诊断报告',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'serial': 'FP-2023-0521',
            'diag_date': datetime.now().strftime('%Y-%m-%d'),
            'operator': '操作员',
            'system': '测试台'
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

        # 结构化 JSON（供前端直接展示）
        report_json = io.StringIO()
        import json
        json.dump({
            'product_info': product_info,
            'indicators': indicators,
            'diagnosis': diagnosis,
            'repair_advice': repair_advice,
        }, report_json, ensure_ascii=False)
        report_json_str = report_json.getvalue()

        if task:
            task.report_data = base64.b64decode(report_base64)
            task.report_json = report_json_str
            task.files = f"{task.files},{file_name}" if task.files else file_name
            task.status = 'Completed'
        else:
            task = FaultDiagnosisTask(
                task_id=task_id,
                type=type,
                files=file_name,
                report_data=base64.b64decode(report_base64),
                report_json=report_json_str,
                status='Completed',
                path=''
            )

        session.add(task)
        session.commit()
        return task.id

    except Exception as e:
        session.rollback()
        raise Exception(f"存储故障诊断报告时出错: {str(e)}")

def get_report_json(task_id):
    task = session.query(FaultDiagnosisTask).filter_by(task_id=task_id).first()
    if not task or not task.report_json:
        return None
    import json
    return json.loads(task.report_json)

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

# 创建数据库表
def create_tables():
    try:
        Base.metadata.create_all(engine)
    except Exception as e:
        raise Exception(f"Error creating database tables: {str(e)}")

