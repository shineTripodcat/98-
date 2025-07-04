#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from config_manager import ConfigManager
from crawler import WebCrawler
from pan115_manager import Pan115Manager
from utils import setup_logging, get_system_info

# 设置日志
setup_logging()
logger = logging.getLogger(__name__)

# 创建Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# 创建SocketIO实例
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 配置管理器
config_manager = ConfigManager()
# 115网盘管理器
pan115_manager = Pan115Manager(config_manager=config_manager)

# 任务管理器
class TaskManager:
    """多线程任务管理器"""
    def __init__(self):
        self.tasks = {}  # 存储所有任务
        self.lock = threading.Lock()  # 线程锁
        self.max_concurrent_tasks = 10  # 最大并发任务数
    
    def add_task(self, task):
        """添加任务"""
        with self.lock:
            self.tasks[task.task_id] = task
    
    def get_task(self, task_id):
        """获取任务"""
        with self.lock:
            return self.tasks.get(task_id)
    
    def remove_task(self, task_id):
        """移除任务"""
        with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
    
    def get_running_tasks_count(self):
        """获取正在运行的任务数量"""
        with self.lock:
            return sum(1 for task in self.tasks.values() 
                      if task.state in ['PENDING', 'PROGRESS'])
    
    def get_all_tasks(self):
        """获取所有任务"""
        with self.lock:
            return list(self.tasks.values())
    
    def cleanup_finished_tasks(self):
        """清理已完成的任务（保留最近10个）"""
        with self.lock:
            finished_tasks = [(task_id, task) for task_id, task in self.tasks.items() 
                            if task.state in ['SUCCESS', 'FAILURE']]
            
            if len(finished_tasks) > 10:
                # 按完成时间排序，保留最新的10个
                finished_tasks.sort(key=lambda x: x[1].task_id, reverse=True)
                for task_id, _ in finished_tasks[10:]:
                    del self.tasks[task_id]

# 全局任务管理器
task_manager = TaskManager()

# 定时任务调度器
scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
scheduler_job_id = 'crawler_scheduled_task'
scheduler_running = False

def start_scheduler():
    """启动调度器"""
    global scheduler_running
    if not scheduler_running:
        try:
            scheduler.start()
            scheduler_running = True
            logger.info("定时任务调度器已启动")
        except Exception as e:
            logger.error(f"启动调度器失败: {str(e)}")

def stop_scheduler():
    """停止调度器"""
    global scheduler_running
    if scheduler_running:
        try:
            scheduler.shutdown()
            scheduler_running = False
            logger.info("定时任务调度器已停止")
        except Exception as e:
            logger.error(f"停止调度器失败: {str(e)}")

def update_scheduled_task():
    """更新定时任务"""
    try:
        config = config_manager.load_config()
        schedule_config = config.get('schedule', {})
        
        # 移除现有的定时任务
        if scheduler.get_job(scheduler_job_id):
            scheduler.remove_job(scheduler_job_id)
            logger.info("已移除现有定时任务")
        
        # 如果启用了定时任务，添加新的任务
        if schedule_config.get('enabled', False):
            cron_expr = schedule_config.get('cron', '0 */6 * * *')
            mode = schedule_config.get('mode', 'update_magnets')
            
            # 解析cron表达式
            try:
                cron_parts = cron_expr.strip().split()
                if len(cron_parts) != 5:
                    raise ValueError("Cron表达式必须包含5个部分")
                
                minute, hour, day, month, day_of_week = cron_parts
                
                # 创建CronTrigger
                trigger = CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week,
                    timezone='Asia/Shanghai'
                )
                
                # 添加定时任务
                scheduler.add_job(
                    func=execute_scheduled_task,
                    trigger=trigger,
                    id=scheduler_job_id,
                    args=[mode],
                    replace_existing=True,
                    max_instances=1
                )
                
                logger.info(f"已添加定时任务: {cron_expr}, 模式: {mode}")
                
            except Exception as e:
                logger.error(f"解析cron表达式失败: {str(e)}")
                raise
        else:
            logger.info("定时任务未启用")
            
    except Exception as e:
        logger.error(f"更新定时任务失败: {str(e)}")
        raise

def execute_scheduled_task(mode):
    """执行定时任务"""
    try:
        logger.info(f"开始执行定时任务，模式: {mode}")
        
        # 检查是否有正在运行的任务
        running_count = task_manager.get_running_tasks_count()
        if running_count >= task_manager.max_concurrent_tasks:
            logger.warning(f"已达到最大并发任务数限制({task_manager.max_concurrent_tasks})，跳过定时任务")
            return
        
        # 加载最新配置
        config_data = config_manager.load_config()
        
        # 生成任务ID
        task_id = f"scheduled_task_{int(time.time())}_{threading.current_thread().ident}"
        
        # 创建并启动任务
        task = CrawlTask(task_id, mode, config_data)
        task_manager.add_task(task)
        task.start()
        
        logger.info(f"定时任务已启动，任务ID: {task_id}")
        
        # 清理旧任务
        task_manager.cleanup_finished_tasks()
        
    except Exception as e:
        logger.error(f"执行定时任务失败: {str(e)}")

class CrawlTask:
    """简化的爬虫任务类"""
    def __init__(self, task_id, mode, config_data):
        self.task_id = task_id
        self.mode = mode
        self.config_data = config_data
        self.state = 'PENDING'
        self.progress = 0
        self.status = '任务等待中...'
        self.result = None
        self.error = None
        self.thread = None
        self.stop_flag = False  # 添加停止标志
    
    def start(self):
        """启动任务"""
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        """停止任务"""
        self.stop_flag = True
        self.state = 'FAILURE'
        self.status = '任务已停止'
        self.error = '用户手动停止'
    
    def _run(self):
        """执行任务"""
        try:
            self.state = 'PROGRESS'
            self.status = '初始化爬虫...'
            self.progress = 0
            
            # 检查停止标志
            if self.stop_flag:
                return
            
            # 从ConfigManager加载最新配置并与传入配置合并
            latest_config = config_manager.load_config()
            # 合并配置：以传入的config_data为主，但保留ConfigManager中的max_tid等关键字段
            merged_config = self.config_data.copy()
            merged_config['max_tid'] = latest_config.get('max_tid', '0')
            
            # 创建爬虫实例
            crawler = WebCrawler(merged_config)
            
            # 设置爬虫的停止标志引用
            crawler.stop_flag = lambda: self.stop_flag
            
            # 进度回调函数
            def progress_callback(progress, status):
                if self.stop_flag:
                    return
                self.progress = progress
                self.status = status
                # 通过SocketIO发送进度更新
                socketio.emit('task_progress', {
                    'task_id': self.task_id,
                    'progress': progress,
                    'status': status
                })
            
            # 执行爬虫任务
            if self.stop_flag:
                return
                
            if self.mode == 'crawl_tids':
                result = crawler.crawl_forum_tids(progress_callback=progress_callback)
            elif self.mode == 'crawl_magnets':
                result = crawler.crawl_magnets_full(progress_callback=progress_callback)
            elif self.mode == 'update_magnets':
                result = crawler.crawl_magnets_incremental(progress_callback=progress_callback)
            else:
                raise ValueError(f"未知的爬虫模式: {self.mode}")
            
            if not self.stop_flag:
                self.state = 'SUCCESS'
                self.status = '任务完成'
                self.progress = 100
                self.result = result
                
                # 如果是磁力链接爬取任务且成功，更新配置中的max_tid
                if result.get('success') and self.mode in ['crawl_magnets', 'update_magnets']:
                    max_tid = result.get('max_tid')
                    if max_tid:
                        try:
                            # 使用ConfigManager更新并保存max_tid配置
                            config_manager.update_max_tid(max_tid)
                            logger.info(f"已更新配置中的max_tid: {max_tid}")
                        except Exception as e:
                            logger.error(f"更新max_tid配置失败: {str(e)}")
                    else:
                        logger.warning("爬取结果中未包含max_tid信息")
                    
                    # 检查是否启用自动115网盘转存
                    csv_file = result.get('csv_file') or result.get('result_file')
                    if csv_file and os.path.exists(csv_file):
                        # 检查115网盘配置中的auto_transfer_enabled设置
                        pan115_config = pan115_manager.load_config()
                        if pan115_config.get('auto_transfer_enabled', False):
                            try:
                                self.status = '正在转存到115网盘...'
                                socketio.emit('task_progress', {
                                    'task_id': self.task_id,
                                    'progress': self.progress,
                                    'status': self.status
                                })
                                
                                # 执行115网盘转存
                                transfer_result = pan115_manager.process_csv_file(
                                    csv_file, 
                                    progress_callback=lambda p, s: socketio.emit('task_progress', {
                                        'task_id': self.task_id,
                                        'progress': min(self.progress + p // 10, 99),  # 转存进度占总进度的10%
                                        'status': f'115网盘转存: {s}'
                                    })
                                )
                                
                                if transfer_result.get('success'):
                                    logger.info(f"115网盘转存完成: {transfer_result.get('message')}")
                                    self.result['pan115_transfer'] = transfer_result
                                else:
                                    logger.warning(f"115网盘转存失败: {transfer_result.get('message')}")
                                    self.result['pan115_transfer'] = transfer_result
                                    
                            except Exception as e:
                                logger.error(f"115网盘转存异常: {str(e)}")
                                self.result['pan115_transfer'] = {
                                    'success': False,
                                    'message': f'转存异常: {str(e)}'
                                }
                        else:
                            logger.info("115网盘自动转存未启用，跳过转存步骤")
                            self.result['pan115_transfer'] = {
                                'success': False,
                                'message': '115网盘自动转存未启用'
                            }
            
        except Exception as e:
            logger.error(f"爬虫任务执行失败: {str(e)}")
            self.state = 'FAILURE'
            self.status = f'任务失败: {str(e)}'
            self.progress = 0
            self.error = str(e)
        
        # 发送任务完成通知
        socketio.emit('task_complete', {
            'task_id': self.task_id,
            'state': self.state,
            'status': self.status,
            'progress': self.progress
        })

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """获取配置"""
    try:
        config = config_manager.load_config()
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        logger.error(f"获取配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config', methods=['POST'])
def save_config():
    """保存配置"""
    try:
        config_data = request.json
        config_manager.save_config(config_data)
        
        # 更新定时任务
        try:
            update_scheduled_task()
            logger.info("定时任务配置已更新")
        except Exception as e:
            logger.error(f"更新定时任务失败: {str(e)}")
        
        return jsonify({'success': True, 'message': '配置保存成功'})
    except Exception as e:
        logger.error(f"保存配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/user-agent-options', methods=['GET'])
def get_user_agent_options():
    """获取用户代理选项"""
    try:
        options = config_manager.get_user_agent_options()
        display_names = config_manager.get_user_agent_display_names()
        return jsonify({
            'success': True,
            'options': options,
            'display_names': display_names
        })
    except Exception as e:
        logger.error(f"获取用户代理选项失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/proxy/test', methods=['POST'])
def test_proxy():
    """测试代理连通性"""
    try:
        data = request.json
        proxy_url = data.get('proxy', '').strip()
        
        if not proxy_url:
            return jsonify({'success': False, 'error': '代理地址不能为空'}), 400
        
        import time
        import requests
        from urllib.parse import urlparse
        
        # 验证代理URL格式
        try:
            parsed = urlparse(proxy_url)
            if not parsed.scheme or not parsed.netloc:
                return jsonify({'success': False, 'error': '代理地址格式不正确'}), 400
        except Exception:
            return jsonify({'success': False, 'error': '代理地址格式不正确'}), 400
        
        # 设置代理
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        # 测试连通性
        start_time = time.time()
        try:
            response = requests.get(
                'http://httpbin.org/ip',
                proxies=proxies,
                timeout=10,
                verify=False
            )
            
            if response.status_code == 200:
                response_time = int((time.time() - start_time) * 1000)
                return jsonify({
                    'success': True,
                    'response_time': response_time,
                    'message': '代理连通性测试成功'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': f'HTTP状态码: {response.status_code}'
                })
                
        except requests.exceptions.ProxyError:
            return jsonify({'success': False, 'error': '代理服务器连接失败'})
        except requests.exceptions.ConnectTimeout:
            return jsonify({'success': False, 'error': '代理连接超时'})
        except requests.exceptions.ReadTimeout:
            return jsonify({'success': False, 'error': '代理响应超时'})
        except requests.exceptions.ConnectionError:
            return jsonify({'success': False, 'error': '网络连接错误'})
        except Exception as e:
            return jsonify({'success': False, 'error': f'测试失败: {str(e)}'})
            
    except Exception as e:
        logger.error(f"代理测试失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/crawl/start', methods=['POST'])
def start_crawl():
    """启动爬虫任务"""
    try:
        # 检查并发任务数量限制
        running_count = task_manager.get_running_tasks_count()
        if running_count >= task_manager.max_concurrent_tasks:
            return jsonify({
                'success': False, 
                'error': f'已达到最大并发任务数限制({task_manager.max_concurrent_tasks})，请等待其他任务完成'
            }), 400
        
        data = request.json
        mode = data.get('mode', 'update_magnets')
        config_data = data.get('config', {})
        
        # 验证模式
        if mode not in ['crawl_tids', 'crawl_magnets', 'update_magnets']:
            return jsonify({'success': False, 'error': '无效的爬虫模式'}), 400
        
        # 生成任务ID
        task_id = f"task_{int(time.time())}_{threading.current_thread().ident}"
        
        # 创建并启动任务
        task = CrawlTask(task_id, mode, config_data)
        task_manager.add_task(task)
        task.start()
        
        # 清理旧任务
        task_manager.cleanup_finished_tasks()
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'爬虫任务已启动 (当前运行: {running_count + 1}/{task_manager.max_concurrent_tasks})'
        })
        
    except Exception as e:
        logger.error(f"启动爬虫任务失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/crawl/status/<task_id>', methods=['GET'])
def get_crawl_status(task_id):
    """获取爬虫任务状态"""
    try:
        task = task_manager.get_task(task_id)
        if not task:
            return jsonify({'success': False, 'error': '任务不存在'}), 404
        
        response = {
            'task_id': task.task_id,
            'state': task.state,
            'status': task.status,
            'progress': task.progress
        }
        
        if task.state == 'SUCCESS' and task.result:
            response['result'] = task.result
        elif task.state == 'FAILURE' and task.error:
            response['error'] = task.error
        
        return jsonify({'success': True, 'task': response})
        
    except Exception as e:
        logger.error(f"获取任务状态失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/crawl/stop/<task_id>', methods=['POST'])
def stop_crawl(task_id):
    """停止爬虫任务"""
    try:
        task = task_manager.get_task(task_id)
        if not task:
            return jsonify({'success': False, 'error': '任务不存在'}), 404
        
        # 调用任务的停止方法
        task.stop()
        
        return jsonify({'success': True, 'message': '任务已停止'})
    except Exception as e:
        logger.error(f"停止任务失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/crawl/tasks', methods=['GET'])
def get_all_tasks():
    """获取所有任务列表"""
    try:
        tasks = task_manager.get_all_tasks()
        running_count = task_manager.get_running_tasks_count()
        
        task_list = []
        for task in tasks:
            task_info = {
                'task_id': task.task_id,
                'mode': task.mode,
                'state': task.state,
                'status': task.status,
                'progress': task.progress,
                'created_time': task.task_id.split('_')[1] if '_' in task.task_id else ''
            }
            
            if task.state == 'SUCCESS' and task.result:
                task_info['result'] = task.result
            elif task.state == 'FAILURE' and task.error:
                task_info['error'] = task.error
                
            task_list.append(task_info)
        
        # 按创建时间排序（最新的在前）
        task_list.sort(key=lambda x: x['created_time'], reverse=True)
        
        return jsonify({
            'success': True,
            'tasks': task_list,
            'running_count': running_count,
            'max_concurrent': task_manager.max_concurrent_tasks
        })
        
    except Exception as e:
        logger.error(f"获取任务列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 115网盘相关API
@app.route('/api/pan115/config', methods=['GET'])
def get_pan115_config():
    """获取115网盘配置"""
    try:
        config = pan115_manager.get_config()
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        logger.error(f"获取115网盘配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pan115/config', methods=['POST'])
def save_pan115_config():
    """保存115网盘配置"""
    try:
        config_data = request.json
        if pan115_manager.update_config(config_data):
            return jsonify({'success': True, 'message': '115网盘配置保存成功'})
        else:
            return jsonify({'success': False, 'error': '配置保存失败'}), 500
    except Exception as e:
        logger.error(f"保存115网盘配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pan115/check-login', methods=['POST'])
def check_pan115_login():
    """检查115网盘登录状态"""
    try:
        is_logged_in = pan115_manager.check_login()
        return jsonify({
            'success': True, 
            'logged_in': is_logged_in,
            'message': '登录状态正常' if is_logged_in else '登录状态异常，请检查Cookie配置'
        })
    except Exception as e:
        logger.error(f"检查115网盘登录状态失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pan115/folders', methods=['GET'])
def get_pan115_folders():
    """获取115网盘文件夹列表"""
    try:
        # 检查是否强制刷新
        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
        folders = pan115_manager.get_folders(force_refresh=force_refresh)
        return jsonify({'success': True, 'folders': folders})
    except Exception as e:
        logger.error(f"获取115网盘文件夹列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pan115/manual-transfer', methods=['POST'])
def manual_csv_transfer():
    """手动选择CSV文件进行115网盘转存"""
    try:
        data = request.json
        csv_filename = data.get('csv_filename')
        
        if not csv_filename:
            return jsonify({'success': False, 'error': '未指定CSV文件名'}), 400
        
        # 验证文件类型
        if not csv_filename.lower().endswith('.csv'):
            return jsonify({'success': False, 'error': '请选择CSV文件'}), 400
        
        # 构建文件路径
        data_dir = config_manager.get_data_dir()
        csv_filepath = os.path.join(data_dir, csv_filename)
        
        if not os.path.exists(csv_filepath):
            return jsonify({'success': False, 'error': 'CSV文件不存在'}), 400
        
        # 创建临时文件用于处理
        temp_dir = os.path.join('data', 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = f"manual_transfer_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{csv_filename}"
        temp_filepath = os.path.join(temp_dir, temp_filename)
        
        # 复制原文件到临时目录
        import shutil
        shutil.copy2(csv_filepath, temp_filepath)
        logger.info(f"保存临时CSV文件: {temp_filepath}")
        
        # 执行转存（手动转存强制执行）
        result = pan115_manager.process_csv_file(temp_filepath, force_transfer=True)
        
        # 清理临时文件
        try:
            os.remove(temp_filepath)
            logger.info(f"清理临时文件: {temp_filepath}")
        except Exception as cleanup_error:
            logger.warning(f"清理临时文件失败: {cleanup_error}")
        
        return jsonify({
            'success': True, 
            'total_count': result.get('total', 0),
            'success_count': result.get('success_count', 0),
            'message': result.get('message', '手动转存完成')
        })
        
    except Exception as e:
        logger.error(f"手动CSV转存失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pan115/transfer', methods=['POST'])
def manual_pan115_transfer():
    """手动触发115网盘转存"""
    try:
        data = request.json
        csv_file = data.get('csv_file')
        
        if not csv_file or not os.path.exists(csv_file):
            return jsonify({'success': False, 'error': 'CSV文件不存在'}), 400
        
        # 执行转存
        result = pan115_manager.process_csv_file(csv_file)
        return jsonify({'success': True, 'result': result})
        
    except Exception as e:
        logger.error(f"手动115网盘转存失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pan115/extract-cache', methods=['POST'])
def extract_magnets_cache():
    """从CSV文件提取磁力链接到缓存文件"""
    try:
        data = request.json
        csv_filename = data.get('csv_filename')
        
        if not csv_filename:
            return jsonify({'success': False, 'error': '未指定CSV文件名'}), 400
        
        # 验证文件类型
        if not csv_filename.lower().endswith('.csv'):
            return jsonify({'success': False, 'error': '请选择CSV文件'}), 400
        
        # 构建文件路径
        data_dir = config_manager.get_data_dir()
        csv_filepath = os.path.join(data_dir, csv_filename)
        
        if not os.path.exists(csv_filepath):
            return jsonify({'success': False, 'error': 'CSV文件不存在'}), 400
        
        # 提取磁力链接到缓存
        result = pan115_manager.extract_magnets_to_cache(csv_filepath)
        
        return jsonify({
            'success': True,
            'cache_file': result['cache_file'],
            'total_read': result['total_read'],
            'invalid_count': result['invalid_count'],
            'duplicate_count': result['duplicate_count'],
            'cached_count': result['cached_count'],
            'message': f"缓存完成: 总计{result['total_read']}行, 缓存{result['cached_count']}个有效磁力链接"
        })
        
    except Exception as e:
        logger.error(f"提取磁力链接缓存失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pan115/process-cache', methods=['POST'])
def process_magnets_cache():
    """从缓存文件分批处理磁力链接"""
    try:
        data = request.json
        cache_file = data.get('cache_file')
        batch_size = data.get('batch_size', 100)
        
        if not cache_file:
            return jsonify({'success': False, 'error': '未指定缓存文件'}), 400
        
        if not os.path.exists(cache_file):
            return jsonify({'success': False, 'error': '缓存文件不存在'}), 400
        
        # 验证批次大小
        if not isinstance(batch_size, int) or batch_size < 1 or batch_size > 100:
            batch_size = 100
        
        # 处理缓存文件
        result = pan115_manager.process_cache_file(cache_file, batch_size)
        
        return jsonify({
            'success': True,
            'total_batches': result['total_batches'],
            'total_magnets': result['total_magnets'],
            'success_count': result['success_count'],
            'failed_count': result['failed_count'],
            'message': result['message'],
            'failed_details': result.get('failed_details', [])
        })
        
    except Exception as e:
        logger.error(f"处理磁力链接缓存失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pan115/transfer-with-cache', methods=['POST'])
def transfer_with_cache():
    """使用缓存机制进行115网盘转存"""
    try:
        data = request.json
        csv_filename = data.get('csv_filename')
        batch_size = data.get('batch_size', 100)
        
        if not csv_filename:
            return jsonify({'success': False, 'error': '未指定CSV文件名'}), 400
        
        # 验证文件类型
        if not csv_filename.lower().endswith('.csv'):
            return jsonify({'success': False, 'error': '请选择CSV文件'}), 400
        
        # 构建文件路径
        data_dir = config_manager.get_data_dir()
        csv_filepath = os.path.join(data_dir, csv_filename)
        
        if not os.path.exists(csv_filepath):
            return jsonify({'success': False, 'error': 'CSV文件不存在'}), 400
        
        # 验证批次大小
        if not isinstance(batch_size, int) or batch_size < 1 or batch_size > 100:
            batch_size = 100
        
        # 使用缓存机制处理CSV文件
        result = pan115_manager.process_csv_with_cache(csv_filepath, batch_size, force_transfer=True)
        
        return jsonify({
            'success': True,
            'cache_result': result.get('cache_result', {}),
            'process_result': result.get('process_result', {}),
            'message': result['message']
        })
        
    except Exception as e:
        logger.error(f"缓存转存失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/results', methods=['GET'])
def get_results():
    """获取爬取结果列表"""
    try:
        data_dir = config_manager.get_data_dir()
        results = []
        
        # 扫描结果文件
        for filename in os.listdir(data_dir):
            if filename.endswith('.csv'):
                filepath = os.path.join(data_dir, filename)
                stat = os.stat(filepath)
                results.append({
                    'filename': filename,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'path': filepath
                })
        
        # 按修改时间排序
        results.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        logger.error(f"获取结果列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/results/csv-files', methods=['GET'])
def get_csv_files():
    """获取CSV文件列表（用于手动转存选择）"""
    try:
        data_dir = config_manager.get_data_dir()
        files = []
        
        # 扫描CSV文件
        for filename in os.listdir(data_dir):
            if filename.endswith('.csv'):
                filepath = os.path.join(data_dir, filename)
                stat = os.stat(filepath)
                files.append({
                    'filename': filename,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        
        # 按修改时间排序
        files.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({'success': True, 'files': files})
        
    except Exception as e:
        logger.error(f"获取CSV文件列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/results/download/<filename>', methods=['GET'])
def download_result(filename):
    """下载结果文件"""
    try:
        data_dir = config_manager.get_data_dir()
        filepath = os.path.join(data_dir, filename)
        
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': '文件不存在'}), 404
        
        return send_file(filepath, as_attachment=True)
        
    except Exception as e:
        logger.error(f"下载文件失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/results/preview/<filename>', methods=['GET'])
def preview_result(filename):
    """预览结果文件"""
    try:
        data_dir = config_manager.get_data_dir()
        filepath = os.path.join(data_dir, filename)
        
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': '文件不存在'}), 404
        
        # 读取CSV文件前100行，处理编码和特殊字符
        try:
            df = pd.read_csv(filepath, nrows=100, encoding='utf-8')
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(filepath, nrows=100, encoding='gbk')
            except UnicodeDecodeError:
                df = pd.read_csv(filepath, nrows=100, encoding='latin-1')
        
        # 处理DataFrame中的NaN值和特殊字符
        df = df.fillna('')  # 将NaN替换为空字符串
        
        # 转换为字典时确保所有值都是可序列化的
        rows = []
        for _, row in df.iterrows():
            row_dict = {}
            for col in df.columns:
                value = row[col]
                # 处理各种数据类型
                if pd.isna(value):
                    row_dict[col] = ''
                elif isinstance(value, (int, float)):
                    if pd.isna(value) or value != value:  # 检查NaN
                        row_dict[col] = ''
                    else:
                        row_dict[col] = str(value)
                else:
                    row_dict[col] = str(value)
            rows.append(row_dict)
        
        return jsonify({
            'success': True,
            'data': {
                'columns': df.columns.tolist(),
                'rows': rows,
                'total_rows': len(df)
            }
        })
        
    except Exception as e:
        logger.error(f"预览文件失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/system/info', methods=['GET'])
def get_system_info_api():
    """获取系统信息"""
    try:
        info = get_system_info()
        return jsonify({'success': True, 'info': info})
    except Exception as e:
        logger.error(f"获取系统信息失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """获取日志"""
    try:
        log_file = 'logs/app.log'
        lines = request.args.get('lines', 100, type=int)
        
        if not os.path.exists(log_file):
            return jsonify({'success': True, 'logs': []})
        
        with open(log_file, 'r', encoding='utf-8') as f:
            log_lines = f.readlines()
        
        # 返回最后N行
        recent_logs = log_lines[-lines:] if len(log_lines) > lines else log_lines
        
        return jsonify({
            'success': True,
            'logs': [line.strip() for line in recent_logs]
        })
        
    except Exception as e:
        logger.error(f"获取日志失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/scheduler/status', methods=['GET'])
def get_scheduler_status():
    """获取定时任务调度器状态"""
    try:
        global scheduler_running
        
        status_info = {
            'scheduler_running': scheduler_running,
            'jobs': []
        }
        
        if scheduler_running:
            # 获取所有任务信息
            jobs = scheduler.get_jobs()
            for job in jobs:
                job_info = {
                    'id': job.id,
                    'name': job.name or job.id,
                    'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                    'trigger': str(job.trigger)
                }
                status_info['jobs'].append(job_info)
        
        return jsonify({
            'success': True,
            'status': status_info
        })
        
    except Exception as e:
        logger.error(f"获取调度器状态失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# SocketIO事件处理
@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    logger.info(f"客户端连接: {request.sid}")
    emit('connected', {'message': '连接成功'})

@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开连接"""
    logger.info(f"客户端断开连接: {request.sid}")

if __name__ == '__main__':
    # 确保必要的目录存在
    os.makedirs('data', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    os.makedirs('config', exist_ok=True)
    
    # 启动定时任务调度器
    try:
        start_scheduler()
        # 加载并应用定时任务配置
        update_scheduled_task()
        logger.info("定时任务调度器初始化完成")
    except Exception as e:
        logger.error(f"定时任务调度器初始化失败: {str(e)}")
    
    # 启动应用
    logger.info("启动轻量化Web爬虫应用...")
    try:
        socketio.run(app, host='0.0.0.0', port=8105, debug=False, allow_unsafe_werkzeug=True)
    finally:
        # 应用关闭时停止调度器
        stop_scheduler()