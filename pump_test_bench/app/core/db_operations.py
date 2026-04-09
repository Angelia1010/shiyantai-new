# -*- coding: utf-8 -*-
import os
import io
import sys
import base64
import json
import math
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
    
def store_fault_diagnosis_report(task_id, type, file_name=None, x1=None, x2=None, density=None):
    try:
        dia = Diagnosis(file_name, "")
        new_alarms = dia.diagnosis_process(x1=x1, x2=x2, density=density)
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
    status: str = None,     # 用于精确查询的状态
    start_time: int = None, # 开始时间戳（毫秒）
    end_time: int = None    # 结束时间戳（毫秒）
):
    from sqlalchemy import func, cast, Integer
    query = session.query(FaultDiagnosisTask)

    if task_id:
        query = query.filter(FaultDiagnosisTask.task_id.like(f"%{task_id}%"))
    if status:
        query = query.filter(FaultDiagnosisTask.status == status)
    
    if start_time is not None or end_time is not None:
        timestamp_str = func.substr(FaultDiagnosisTask.task_id, 1, 13)
        timestamp_int = cast(timestamp_str, Integer)
        if start_time is not None:
            query = query.filter(timestamp_int >= start_time)
        if end_time is not None:
            query = query.filter(timestamp_int <= end_time)

    total_count = query.count()

    total_pages = (total_count + page_size - 1) // page_size

    tasks = query.offset((page - 1) * page_size).limit(page_size).all()
    tasks_data = [{"task_id": task.task_id,  "status": task.status, "type":task.type, "files":task.files, "path":task.path} for task in tasks]

    return {
        "tasks": tasks_data,
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size
    }

DEFAULT_DEVIATION_THRESHOLD = 0.15
DEFAULT_EXCEEDED_LIMIT = 3

def preliminary_diagnose(task_id, experiment_data, simulation_data,
                         threshold=None, exceeded_limit=None, file_name=None, path=None, density=None):
    """
    初步诊断：对比仿真数据与试验数据，判断是否存在异常。

    :param task_id: 任务ID
    :param experiment_data: 试验数据，格式为 [{field: {avg, max, min}}, ...]
    :param simulation_data: 仿真数据，格式为 {var_name: [values...]}
    :param threshold: 偏差阈值（相对偏差，默认0.15即15%）
    :param exceeded_limit: 超限变量数量阈值（默认3）
    :param file_name: 文件名（用于精确诊断时传入）
    :param path: 文件路径（用于拼接完整文件路径）
    :param density: 介质密度（kg/m³），用于精确诊断
    :return: dict 包含初步诊断结果
    """
    thr = threshold if threshold is not None else DEFAULT_DEVIATION_THRESHOLD
    limit = exceeded_limit if exceeded_limit is not None else DEFAULT_EXCEEDED_LIMIT

    deviation_details = []
    common_vars = set()

    if simulation_data:
        for var_name in simulation_data.keys():
            common_vars.add(var_name)

    exp_records = experiment_data if isinstance(experiment_data, list) else []
    sim_data_map = simulation_data if isinstance(simulation_data, dict) else {}

    for var_name in common_vars:
        exp_values = []
        for record in exp_records:
            if var_name in record:
                val = record[var_name]
                if isinstance(val, dict) and 'avg' in val:
                    v = val['avg']
                elif isinstance(val, (int, float)):
                    v = val
                else:
                    continue
                try:
                    exp_values.append(float(v))
                except (TypeError, ValueError):
                    continue

        sim_values = sim_data_map.get(var_name, [])
        if isinstance(sim_values, list):
            sim_values = [float(v) for v in sim_values if isinstance(v, (int, float))]

        if not exp_values or not sim_values:
            continue

        exp_avg = sum(exp_values) / len(exp_values)
        sim_avg = sum(sim_values) / len(sim_values)

        if abs(exp_avg) < 1e-9:
            rel_deviation = abs(sim_avg - exp_avg)
        else:
            rel_deviation = abs(sim_avg - exp_avg) / abs(exp_avg)

        exceeded = rel_deviation > thr
        deviation_details.append({
            'variable': var_name,
            'experiment_avg': round(exp_avg, 6),
            'simulation_avg': round(sim_avg, 6),
            'deviation': round(rel_deviation, 6),
            'threshold': thr,
            'exceeded': exceeded
        })

    exceeded_count = sum(1 for d in deviation_details if d['exceeded'])
    is_abnormal = exceeded_count > limit

    result = {
        'is_abnormal': is_abnormal,
        'exceeded_count': exceeded_count,
        'total_compared': len(deviation_details),
        'exceeded_limit': limit,
        'threshold': thr,
        'deviation_details': deviation_details,
        'preliminary_conclusion': (
            f'初步诊断：共对比 {len(deviation_details)} 个变量，'
            f'{exceeded_count} 个变量偏差超过阈值 ({thr*100:.1f}%)，'
            f'超限阈值={limit}。'
            f'{"系统存在异常，将执行精确诊断。" if is_abnormal else "系统状态正常。"}'
        )
    }

    if is_abnormal and file_name:
        try:
            full_file_path = os.path.join(path, file_name) if path else file_name
            store_fault_diagnosis_report(task_id, '0', file_name=full_file_path, density=density)
            result['precise_diagnosis_triggered'] = True
        except Exception as e:
            result['precise_diagnosis_triggered'] = False
            result['precise_error'] = str(e)
    elif not is_abnormal:
        _store_preliminary_normal_result(task_id, result, file_name)
        result['precise_diagnosis_triggered'] = False

    return result


def _store_preliminary_normal_result(task_id, prelim_result, file_name=None):
    """
    将初步诊断正常结果存入数据库，格式与精确诊断一致以便前端统一展示。
    """
    product_info = {
        'name': '试验台故障诊断报告',
        'date': datetime.now().strftime('%Y-%m-%d'),
        'serial': 'FP-2023-0521',
        'diag_date': datetime.now().strftime('%Y-%m-%d'),
        'operator': '操作员',
        'system': '测试台'
    }

    indicators = []
    for d in prelim_result.get('deviation_details', []):
        indicators.append({
            'name': f"{d['variable']}（偏差）",
            'reference': f'阈值 ±{d["threshold"]*100:.1f}%',
            'value': f'{d["deviation"]*100:.2f}%{" ⚠️超限" if d["exceeded"] else ""}'
        })
    indicators.append({
        'name': '超限变量数',
        'reference': f'≤{prelim_result["exceeded_limit"]}',
        'value': str(prelim_result['exceeded_count'])
    })
    indicators.append({
        'name': '对比变量总数',
        'reference': '—',
        'value': str(prelim_result['total_compared'])
    })

    diagnosis = {
        'fault_name': '' if not prelim_result['is_abnormal'] else '待精确诊断',
        'location': f'超限变量数: {prelim_result["exceeded_count"]}/{prelim_result["total_compared"]}',
        'analysis': prelim_result['preliminary_conclusion']
    }

    repair_advice = (
        f'【初步诊断结果】\n'
        f'{prelim_result["preliminary_conclusion"]}\n\n'
        f'各变量偏差详情：\n'
    )
    for d in prelim_result.get('deviation_details', []):
        flag = "⚠️" if d['exceeded'] else "✓"
        repair_advice += (
            f'  {flag} {d["variable"]}: '
            f'试验均值={d["experiment_avg"]:.4f}, '
            f'仿真均值={d["simulation_avg"]:.4f}, '
            f'偏差={d["deviation"]*100:.2f}%\n'
        )
    repair_advice += '\n系统状态正常，无需进一步精确诊断。'

    reporter = FuelPumpDiagnosisReporter()
    report_base64 = reporter.generate_report(
        product_info=product_info,
        indicators=indicators,
        diagnosis=diagnosis,
        repair_advice=repair_advice
    )

    report_json_obj = {
        'product_info': product_info,
        'indicators': indicators,
        'diagnosis': diagnosis,
        'repair_advice': repair_advice,
        'is_preliminary': True
    }
    report_json_str = json.dumps(report_json_obj, ensure_ascii=False)

    task = session.query(FaultDiagnosisTask).filter_by(task_id=task_id).first()
    if task:
        task.report_data = base64.b64decode(report_base64)
        task.report_json = report_json_str
        if file_name:
            task.files = f"{task.files},{file_name}" if task.files else file_name
        task.status = 'Completed'
    else:
        task = FaultDiagnosisTask(
            task_id=task_id,
            type='0',
            files=file_name or '',
            report_data=base64.b64decode(report_base64),
            report_json=report_json_str,
            status='Completed',
            path=''
        )

    session.add(task)
    session.commit()


# 创建数据库表
def create_tables():
    try:
        Base.metadata.create_all(engine)
    except Exception as e:
        raise Exception(f"Error creating database tables: {str(e)}")

